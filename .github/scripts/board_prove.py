#!/usr/bin/env python3
"""Board loop prove-step decision (specs/057-autonomous-board-loop,
contracts/prove-step.md, research.md D15).

WHY THIS EXISTS
---------------
A merged fix that changed behaviour running only inside Actions must be
re-driven and proven before its issue closes (FR-041); a merge that
changed nothing but docs/specs, or only a gate script the merged PR's own
required checks already re-executed, proves nothing a fresh dispatch would
add. This is a deterministic, path-based rule (Principle IX) -- never an
agent's guess.
"""
import fnmatch
import os
import re
import sys

import json
import yaml

DOCS_ONLY_GLOBS = ("docs/**", "specs/**")
VERIFY_SCRIPT_GLOB = ".github/scripts/verify-*.py"
RUN_NAME_ATTEMPT_TOKEN_RE = re.compile(r"^run-name:.*inputs\.attempt-token", re.MULTILINE)
WORKFLOW_REF_RE = re.compile(r"\.github/workflows/[A-Za-z0-9._-]+\.ya?ml")
COMPOSITE_REF_RE = re.compile(r"\.github/actions/[A-Za-z0-9._-]+")
DIRECTED_GROUP = "wing-commander-board-loop-directed-proof"
ORDINARY_GROUP = "wing-commander-board-loop"

# research.md D2: select's own job body *is* the item-picking logic -- a
# directed run of it would either pick nothing or violate FR-002's "MUST
# NOT select a board item". route can push a branch/PR for the
# size-and-path backstop's post-push breach case, and fix exists to open
# the fix PR -- both are mutating actions FR-002 forbids a directed proof
# run from taking. Read directly (never re-derived) by Gate 91's own
# structural assertion.
aimable_jobs = frozenset({"triage", "review", "readiness", "prove"})


def _matches_any(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def actions_only(changed_paths):
    """research.md D15: docs/**/specs/**-only, or
    .github/scripts/verify-*.py-only -> False (with the reason implied by
    which branch matched); any other changed path -> True."""
    if not changed_paths:
        return False, "no changed paths"

    if all(_matches_any(p, DOCS_ONLY_GLOBS) for p in changed_paths):
        return False, "docs/**/specs/**-only change"

    if all(fnmatch.fnmatch(p, VERIFY_SCRIPT_GLOB) for p in changed_paths):
        return False, "verify-*.py-only change, already proven by the merged PR's own required checks"

    return True, "changed path(s) outside docs/**, specs/**, and .github/scripts/verify-*.py"


def is_safe_redrive_target(workflow_text, workflow_dispatch_inputs=None):
    """Whether wing-commander-dispatch-and-wait can actually redrive this
    workflow unattended (research.md D14, its own action.yml header):

    1. Its own `run-name:` must read `inputs.attempt-token` -- the
       composite correlates the run it dispatches by that token embedded
       in the run's own name, never by recency, and cannot correlate a
       run whose name doesn't carry it.
    2. It must declare no *other* required `workflow_dispatch` input --
       the composite always supplies `attempt-token` itself but has no
       source for anything else a workflow like release.yml's `version`
       would need, and `gh workflow run` rejects a dispatch missing a
       required input outright.

    A candidate failing either check must never be offered to
    redrive_target(): a rejected or uncorrelatable dispatch is
    indistinguishable, from board-loop.yml's side, from an ordinary
    correlation failure (FR-043 anticipates an undispatchable proof run,
    but that must be because nothing reaches the change, never because
    this module picked a target that could never have worked).

    `workflow_dispatch_inputs`: {input_name: {"required": bool, ...}}, as
    parsed from the workflow's own `on.workflow_dispatch.inputs`."""
    if not RUN_NAME_ATTEMPT_TOKEN_RE.search(workflow_text or ""):
        return False
    for name, input_spec in (workflow_dispatch_inputs or {}).items():
        if name == "attempt-token":
            continue
        if (input_spec or {}).get("required"):
            return False
    return True


def scan_dispatchable_and_uses_graph(workflows_dir):
    """Single home for the repo-tree scan `redrive_target()`'s own inputs
    come from (previously duplicated inline as a `board-loop.yml` `run:`
    step -- CLAUDE.md "shared logic has exactly one home"). Reads every
    workflow file under `workflows_dir` off the checked-out tree, exactly
    as the `prove` job's own comment requires ("the merge commit's own
    tree, so a wrapper added or removed by the very merge being proven is
    accounted for") -- callers must invoke this against that checkout,
    never a cached/prior tree.

    Also closes a testability gap a runtime-only duplicate of this scan
    had: `is_safe_redrive_target()` was previously exercised only against
    synthetic fixtures, never against the repository's own real workflow
    files, so a scan that filtered out every real workflow (this one did,
    until board-loop.yml's own run-name/attempt-token wiring was added)
    passed the gate suite while being dead code at runtime. A caller that
    wants that regression caught again should assert against this
    function's own output, not a fixture.

    Returns (dispatchable, uses_graph): dispatchable is the sorted list of
    repo-relative workflow paths `is_safe_redrive_target()` accepts;
    uses_graph maps every workflow path (dispatchable or not) to the
    repo-relative workflow/composite paths its text references."""
    dispatchable = []
    uses_graph = {}
    for name in sorted(os.listdir(workflows_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        path = "{0}/{1}".format(workflows_dir, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        # PyYAML resolves the bare key `on:` to the boolean True.
        triggers = doc.get("on", doc.get(True)) or {}
        if isinstance(triggers, dict) and "workflow_dispatch" in triggers:
            wd = triggers.get("workflow_dispatch") or {}
            wd_inputs = wd.get("inputs") if isinstance(wd, dict) else None
            if is_safe_redrive_target(text, wd_inputs or {}):
                dispatchable.append(path)

        referenced = set()
        for match in WORKFLOW_REF_RE.findall(text):
            if match != path:
                referenced.add(match)
        for directory in set(COMPOSITE_REF_RE.findall(text)):
            for dirpath, _dirs, names in os.walk(directory):
                for fname in names:
                    referenced.add(os.path.join(dirpath, fname).replace(os.sep, "/"))
        uses_graph[path] = sorted(referenced)

    return sorted(dispatchable), uses_graph


def scan_job_uses_graph(workflow_path):
    """research.md D1: per-job extension of scan_dispatchable_and_uses_graph()'s
    whole-workflow scan -- which changed path(s) each job of the one
    checked-out workflow at workflow_path actually executes, consumed only
    by directed_stage(). Parses that single file with yaml.safe_load and
    walks doc["jobs"][job]["steps"], joining each step's own run:/uses:
    text into one string per job before applying the same
    WORKFLOW_REF_RE/COMPOSITE_REF_RE scan_dispatchable_and_uses_graph()
    already uses (single home, CLAUDE.md) -- never a second regex set.

    The prove-gate and prove jobs are folded into one "prove" key: research.md
    D2 aims a directed proof run at that pair jointly (aimable_jobs has no
    separate "prove-gate" entry), so directed_stage() only ever needs to
    know whether *either* half of the pair references a changed path.

    T045 (Phase 7) extends the per-job text this scans with a script-import
    resolution pass shared with scan_dispatchable_and_uses_graph(), rather
    than either function carrying its own copy of that resolution.

    Returns {job_name: sorted(referenced_paths)}."""
    with open(workflow_path, encoding="utf-8") as fh:
        text = fh.read()
    doc = yaml.safe_load(text) or {}
    jobs = doc.get("jobs") or {}

    graph = {}
    for job_name, job_body in jobs.items():
        steps = (job_body or {}).get("steps") or []
        job_text = "\n".join(
            "{0}\n{1}".format(step.get("run") or "", step.get("uses") or "")
            for step in steps if isinstance(step, dict)
        )
        referenced = set(WORKFLOW_REF_RE.findall(job_text))
        referenced.discard(workflow_path)
        for directory in set(COMPOSITE_REF_RE.findall(job_text)):
            for dirpath, _dirs, names in os.walk(directory):
                for fname in names:
                    referenced.add(os.path.join(dirpath, fname).replace(os.sep, "/"))

        key = "prove" if job_name in ("prove-gate", "prove") else job_name
        graph.setdefault(key, set()).update(referenced)

    return {job_name: sorted(paths) for job_name, paths in graph.items()}


def redrive_target(changed_paths, dispatchable, uses_graph):
    """Which workflow to re-drive to prove the merged change (FR-042,
    contracts/prove-step.md "Re-drive": "the wrapper workflow that can
    dispatch the changed behavior").

    Deterministic and code-derived, never the agent's pick:

    1. A changed workflow that is itself `workflow_dispatch`-capable is its
       own wrapper -- re-drive it directly.
    2. Otherwise the changed behaviour is only reachable through something
       that calls it (a `workflow_call`-only published stage, or a
       composite under .github/actions/): re-drive the dispatchable
       workflow that references it.
    3. Neither exists -- there is no run that would prove this change, so
       say so rather than dispatching an unrelated workflow. The caller
       leaves the issue open carrying that fact (FR-043's own
       uncorrelated-dispatch discipline).

    `dispatchable` is the set of repo-relative workflow paths carrying a
    workflow_dispatch trigger -- the caller MUST have already narrowed
    this to workflows `is_safe_redrive_target()` accepts, never every
    workflow_dispatch-capable file in the repository, or this can pick a
    target the composite can dispatch but never correlate. `uses_graph`
    maps each workflow path to the repo-relative workflow/composite paths
    it references. Ties break lexicographically so two runs over the same
    merge pick the same target.

    Returns (workflow_file_basename_or_None, reason).
    """
    dispatchable = sorted(set(dispatchable))
    changed = set(changed_paths)

    direct = [p for p in dispatchable if p in changed]
    if direct:
        return direct[0].rsplit("/", 1)[-1], "the changed workflow dispatches itself"

    for candidate in dispatchable:
        referenced = set(uses_graph.get(candidate) or ())
        hit = sorted(referenced & changed)
        if hit:
            return (candidate.rsplit("/", 1)[-1],
                    "wrapper reaching the changed {0}".format(hit[0]))

    return None, "no workflow_dispatch-capable workflow reaches the changed path(s)"


def directed_stage(changed_paths, job_uses_graph, aimable_jobs):
    """research.md D1/D2: which aimable job of board-loop.yml a directed
    proof run should target, given the job-uses-graph scan_job_uses_graph()
    produces. Only meaningful when the caller already knows redrive_target()
    chose board-loop.yml as the workflow to re-drive (contracts/directed-proof-run.md).

    - exactly one aimable job's referenced set intersects changed_paths ->
      that job is the directed stage;
    - more than one does (a shared helper, e.g. board_item_marker.py) -> the
      tie is broken by pipeline order, latest-stage-wins: prove > readiness
      > review > triage, because a later stage's own proof subsumes an
      earlier stage's use of the same helper;
    - none does -> None, FR-010a's "no directed run reaches the changed
      behaviour", never a fallback to a whole iteration (FR-002b).

    Returns a job name from aimable_jobs, or None."""
    changed = set(changed_paths)
    hits = {
        job for job in aimable_jobs
        if changed & set(job_uses_graph.get(job) or ())
    }
    for job in ("prove", "readiness", "review", "triage"):
        if job in hits:
            return job
    return None


def joins_directed_group(target_workflow_path, target_job, aimable_jobs):
    """research.md D4, FR-001 (static): whether dispatching target_job of
    target_workflow_path would join a concurrency group the calling run (an
    ordinary board-loop.yml run, which holds wing-commander-board-loop)
    already holds -- determined by reading the tree, before ever
    dispatching, never by observing a timeout after the fact.

    Self-target case (target is board-loop.yml, target_job in aimable_jobs):
    True by construction once the per-job concurrency split ships (research.md
    D3) -- a directed dispatch's prove-gate/prove pair always joins the
    separate DIRECTED_GROUP, never the caller's own ORDINARY_GROUP. This
    check exists so a future edit narrowing or removing that split fails
    loudly here rather than silently reintroducing the deadlock.

    For any other target, reads that workflow's own concurrency: block text
    off the checked-out tree and confirms its group name is neither
    ORDINARY_GROUP nor DIRECTED_GROUP (FR-004: correctness for a target
    outside the caller's own group)."""
    if target_workflow_path.rsplit("/", 1)[-1] == "board-loop.yml" and target_job in aimable_jobs:
        return True
    with open(target_workflow_path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh.read()) or {}
    group = (doc.get("concurrency") or {}).get("group") or ""
    return group not in (ORDINARY_GROUP, DIRECTED_GROUP)


def directed_proof_group_busy(run_list_json):
    """research.md D4, FR-001a (dynamic): whether DIRECTED_GROUP is already
    occupied by another directed dispatch, read from a live `gh run list
    --workflow=board-loop.yml --json databaseId,displayTitle,status -L 20`
    call -- the Actions API exposes no direct concurrency-group membership,
    so the run-name marker board-loop.yml's run-name: expression embeds for
    a directed dispatch (`[directed:<stage>]`) is the only deterministic,
    tree-derived proxy this repository can construct for itself, generalizing
    board_stand_down.py's own gh-run-list-occupancy idiom.

    True if any row's status is not "completed" and its displayTitle
    contains the literal "[directed:" marker."""
    runs = json.loads(run_list_json) if isinstance(run_list_json, str) else (run_list_json or [])
    return any(
        row.get("status") != "completed" and "[directed:" in (row.get("displayTitle") or "")
        for row in runs
    )


OUTCOME_REASONS = (
    "group-busy", "not-started", "unfinished", "displaced", "uncorrelated",
    "no-target", "nothing-reaches", "success", "failure",
)


def outcome_reason(group_busy, redrive_workflow, directed_stage_value,
                    conclusion, disambiguated_reason):
    """contracts/proof-outcome-taxonomy.md's eight-reason table (research.md
    D6), computed in one place rather than a workflow `run:` block's own
    shell `if`/`elif` chain (Principle IX) -- the judgment gates whether an
    issue closes, a durable action.

    Priority order mirrors the sequence the `prove` job's own steps run in:
    a busy directed-proof group means no dispatch was even attempted
    (checked before anything else); no dispatchable workflow at all beats a
    workflow that exists but reaches no aimable job (a workflow-level gap
    is checked before a job-level one, FR-010a); only once a dispatch could
    genuinely have been attempted does the composite's own conclusion (or,
    when it is inconclusive, the caller's own disambiguation of WHY --
    T028/T029's not-started/unfinished/displaced/uncorrelated read) decide
    the outcome.

    `disambiguated_reason` is one of "not-started"/"unfinished"/"displaced"/
    "uncorrelated" -- the caller's own post-dispatch read (research.md D6),
    passed through unchanged when `conclusion` is neither "success" nor
    "failure"."""
    if group_busy:
        return "group-busy"
    if not redrive_workflow:
        return "nothing-reaches"
    if redrive_workflow == "board-loop.yml" and not directed_stage_value:
        return "no-target"
    if conclusion in ("success", "failure"):
        return conclusion
    return disambiguated_reason


def main():
    """Reads {"changed_paths": [...], "dispatchable": [...],
    "uses_graph": {...}} from stdin, prints
    {"actions_only": bool, "reason": str, "redrive_workflow": str|null,
    "redrive_reason": str} as JSON."""
    payload = json.load(sys.stdin)
    changed_paths = payload.get("changed_paths") or []
    only, reason = actions_only(changed_paths)
    target, target_reason = redrive_target(
        changed_paths, payload.get("dispatchable") or [],
        payload.get("uses_graph") or {})
    print(json.dumps({"actions_only": only, "reason": reason,
                      "redrive_workflow": target,
                      "redrive_reason": target_reason}))


if __name__ == "__main__":
    main()
