#!/usr/bin/env python3
"""Gate 79 -- the metrics wrapper no longer reacts to the watchdog, and its
daily sweep does not collide with another schedule (FR-030(b)/(c)).

Spec 058 stops persisting per watchdog completion. That trigger fired for
every inspection in the repository, and after FR-031 a healthy one emits
no record at all — so the run it started discovered nothing and billed a
job-minute for the privilege. A signal-bearing inspection still emits, and
the daily sweep is what collects it.

Both halves of that are one-line facts in a trigger block, which is
exactly the kind of thing a later edit restores without noticing:

  * re-adding "Wing Commander · 8 watchdog" to workflow_run.workflows
    silently reinstates the per-inspection run, and nothing fails;
  * a `schedule:` entry that shares its minute AND hour with another
    scheduled workflow in this repository queues behind it. GitHub's
    scheduled dispatch is best-effort and already skews under load; two
    workflows asking for the same instant is a self-inflicted delay on the
    one job this feature deliberately added (research.md R-C6).

This gate reads the trigger blocks of every workflow in the repository and
asserts both, plus that the `sweep` job the schedule exists to start is
actually wired to it.

It also owns the wrapper's coverage (#889): every workflow in this
repository that uploads a `metrics-record*` artifact -- itself, through a
local composite that does, or through a reusable workflow it calls -- is
named in BOTH the wrapper's `workflow_run.workflows` (by display name) and
its sweep's `sweep-workflow-paths` (by path). A workflow missing from both
is a record nobody persists, and nothing fails: the artifact simply
expires. board-loop.yml shipped that way. The watchdog (FR-030(b) above)
and board-loop are the sweep-only exceptions, and must stay OFF the
completion trigger: board-loop runs hourly and nothing reads its records
promptly, so a per-completion run is the same ~24 job-minutes a day the
watchdog's removal was made to save (FR-030(a) keeps the trigger to the
promptly-read stages). The discovery itself is pinned by
an in-memory fixture tree (a direct uploader, a composite uploader, a
reusable uploader reached through its caller, a non-uploader), so a
discovery that stops following one of those edges fails here instead of
quietly shrinking the required set. The 043 wrapper contract's published
trigger list must match the shipped one too, as the 058 delta's must, and
a spelled-out count of the completion path's workflows in the live docs
must equal the shipped list's length.

Twelve subject mutations and two discovery mutations must each break an
assertion.

Wiring: lint-workflows.yml, Gate 79.
"""
import glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate, truthy  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WRAPPER = os.path.join(".github", "workflows", "wing-commander-metrics-persist.yml")
WORKFLOWS = os.path.join(".github", "workflows")
# The delta document states this trigger block literally, as the contract an
# adopter forking the wrapper reads. A document that drifts from the file it
# describes is worse than no document: it is the one a reader trusts.
CONTRACT = os.path.join("specs", "058-per-job-minute-floor", "contracts",
                        "metrics-persist-sweep-delta.md")
# The 043 contract publishes the wrapper's trigger block as the worked
# example an adopter copies (its first ```yaml block).
WRAPPER_CONTRACT = os.path.join("specs", "043-durable-metrics-record",
                                "contracts", "wrapper-contract.md")
ACTIONS = os.path.join(".github", "actions")
WATCHDOG_NAME = "Wing Commander · 8 watchdog"
WATCHDOG_PATH = ".github/workflows/wing-commander-8-watchdog.yml"
BOARD_LOOP_NAME = "board-loop"
# Record owners that must be ABSENT from workflow_run.workflows: reached by
# the daily sweep only (FR-030(a)/(b)). Their paths must still be swept.
SWEEP_ONLY = {WATCHDOG_NAME, BOARD_LOOP_NAME}
RECORD_PREFIX = "metrics-record"
SWEEP_JOB = "sweep"
PERSIST_JOB = "persist"


def triggers(doc):
    """A workflow's `on:` block. PyYAML resolves the bare key `on` to the
    boolean True (YAML 1.1 truthiness), so both spellings are checked."""
    return doc.get("on") or doc.get(True) or {}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def other_crons():
    """(workflow path, cron) for every scheduled workflow but the wrapper."""
    found = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, "*.yml"))
                       + glob.glob(os.path.join(WORKFLOWS, "*.yaml"))):
        if os.path.abspath(path) == os.path.abspath(WRAPPER):
            continue
        for entry in (triggers(load(path)).get("schedule") or []):
            cron = str((entry or {}).get("cron") or "").strip()
            if cron:
                found.append((path, cron))
    return found


def minute_hour(cron):
    parts = cron.split()
    return tuple(parts[:2]) if len(parts) >= 2 else (cron, "")


def contract_block():
    """The `on:` block the delta document publishes as the amended
    contract, parsed as YAML — not scanned for substrings, so a clause
    that moved rather than changed still reads correctly."""
    with open(CONTRACT, encoding="utf-8") as fh:
        text = fh.read()
    # The document carries an "Amended contract" paragraph per delta; the
    # one with the trigger block is the wrapper's, so anchor on its heading
    # rather than on the first match.
    marker = "**Amended contract**:"
    section = text.find("## Wrapper")
    at = text.find(marker, section) if section != -1 else -1
    if section == -1 or at == -1:
        sys.exit(f"::error file={CONTRACT}::no '## Wrapper' section with an "
                 f"'{marker}' paragraph -- this gate compares the shipped "
                 f"trigger block against the one this document publishes; "
                 f"update them together.")
    fence = text.find("```yaml", at)
    end = text.find("```", fence + 7)
    if fence == -1 or end == -1:
        sys.exit(f"::error file={CONTRACT}::the amended contract no longer "
                 f"carries a ```yaml block to compare against.")
    return triggers(yaml.safe_load(text[fence + 7:end]) or {})


def wrapper_contract_workflows():
    """The workflow_run list of the 043 wrapper contract's first ```yaml
    block (its "## Trigger" section)."""
    with open(WRAPPER_CONTRACT, encoding="utf-8") as fh:
        text = fh.read()
    fence = text.find("```yaml", text.find("## Trigger"))
    end = text.find("```", fence + 7)
    if fence == -1 or end == -1:
        sys.exit(f"::error file={WRAPPER_CONTRACT}::no ```yaml block under "
                 f"'## Trigger' -- this gate compares its published "
                 f"workflow_run list against the shipped wrapper's.")
    on = triggers(yaml.safe_load(text[fence + 7:end]) or {})
    return list((on.get("workflow_run") or {}).get("workflows") or [])


_ACTION_REF = re.compile(r"(?:^|/)\.github/actions/(.+?)/?$")
_WORKFLOW_REF = re.compile(r"\.github/workflows/([^/@]+\.ya?ml)(?:@.*)?$")


def _steps(doc):
    """Every step of a workflow's jobs, or of a composite's `runs:`."""
    if isinstance(doc.get("runs"), dict):
        yield from (doc["runs"].get("steps") or [])
        return
    for job in (doc.get("jobs") or {}).values():
        yield from ((job or {}).get("steps") or [])


def _uploads_record(step):
    uses = str((step or {}).get("uses") or "")
    name = str(((step or {}).get("with") or {}).get("name") or "")
    return uses.startswith("actions/upload-artifact") and \
        name.startswith(RECORD_PREFIX)


def record_owners(root=".", follow_composites=True, follow_callers=True):
    """{workflow path: display name} for every workflow under `root` whose
    OWN runs can carry a metrics-record artifact. A workflow_call-only
    (reusable) workflow owns no run -- its uploads land in the caller's
    run -- so its record is credited to every workflow that calls it,
    transitively. The wrapper itself is not a candidate."""
    wf_dir = os.path.join(root, WORKFLOWS)
    act_dir = os.path.join(root, ACTIONS)
    docs = {}
    for path in sorted(glob.glob(os.path.join(wf_dir, "*.yml"))
                       + glob.glob(os.path.join(wf_dir, "*.yaml"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel == WRAPPER.replace(os.sep, "/"):
            continue
        docs[rel] = load(path)

    composite_cache = {}

    def composite_uploads(name, seen=()):
        if name in composite_cache:
            return composite_cache[name]
        found = False
        for fname in ("action.yml", "action.yaml"):
            apath = os.path.join(act_dir, name, fname)
            if os.path.exists(apath) and name not in seen:
                found = steps_upload(load(apath), seen + (name,))
                break
        composite_cache[name] = found
        return found

    def steps_upload(doc, seen=()):
        for step in _steps(doc):
            if _uploads_record(step):
                return True
            m = _ACTION_REF.search(str((step or {}).get("uses") or ""))
            if follow_composites and m and composite_uploads(m.group(1), seen):
                return True
        return False

    def callees(doc):
        out = []
        for job in (doc.get("jobs") or {}).values():
            m = _WORKFLOW_REF.search(str((job or {}).get("uses") or ""))
            if m:
                out.append(f".github/workflows/{m.group(1)}")
        return out

    def emits(rel, seen=()):
        doc = docs.get(rel)
        if doc is None or rel in seen:
            return False
        if steps_upload(doc):
            return True
        return follow_callers and any(emits(c, seen + (rel,))
                                      for c in callees(doc))

    owners = {}
    for rel, doc in docs.items():
        on = triggers(doc)
        events = set(on) if isinstance(on, dict) else (
            {on} if isinstance(on, str) else set(on or []))
        if not events - {"workflow_call"}:
            continue  # reusable-only: credited to its callers
        if emits(rel):
            owners[rel] = str(doc.get("name") or rel)
    return owners


# Prose that states how many workflows the completion path covers. It went
# stale once already: "the unchanged nine-stage path" outlived board-loop's
# addition (#889). A spelled-out count before "completion-trigger
# workflows" or "-stage path" in these live files must equal the shipped
# trigger list's length; prose that names no number is not checked.
COUNT_CLAIM_FILES = [WRAPPER, CONTRACT, WRAPPER_CONTRACT,
                     os.path.join(WORKFLOWS, "metrics-persist.yml"),
                     os.path.join("docs", "adoption.md")]
_NUMWORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve", "thirteen",
             "fourteen", "fifteen"]
_COUNT_CLAIM = re.compile(
    r"\b(" + "|".join(_NUMWORDS) + r")"
    r"(?:-stage(?:[\s#]+)path|(?:[\s#]+)completion-trigger(?:[\s#]+)workflows)\b",
    re.IGNORECASE)


def count_claims():
    """[(file, line, count)] for every count claim in COUNT_CLAIM_FILES."""
    out = []
    for path in COUNT_CLAIM_FILES:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for m in _COUNT_CLAIM.finditer(text):
            out.append((path, text.count("\n", 0, m.start()) + 1,
                        _NUMWORDS.index(m.group(1).lower())))
    return out


def sweep_paths(jobs):
    raw = (((jobs.get(SWEEP_JOB) or {}).get("with") or {})
           .get("sweep-workflow-paths") or "[]")
    try:
        return list(json.loads(raw)) if isinstance(raw, str) else list(raw)
    except ValueError:
        return [f"<unparseable sweep-workflow-paths: {raw!r}>"]


# A fixture tree for record_owners() itself: (relative path, document).
FIXTURE_TREE = [
    (".github/workflows/direct.yml",
     {"name": "fx direct", "on": {"schedule": [{"cron": "1 1 * * *"}]},
      "jobs": {"j": {"steps": [{"uses": "actions/upload-artifact@v6",
                                "with": {"name": "metrics-record-x"}}]}}}),
    (".github/workflows/via-composite.yml",
     {"name": "fx via composite", "on": {"workflow_dispatch": None},
      "jobs": {"j": {"steps": [
          {"uses": "./.wc-pristine-repo/.github/actions/fx-uploader"}]}}}),
    (".github/actions/fx-uploader/action.yml",
     {"runs": {"using": "composite", "steps": [
         {"uses": "actions/upload-artifact@v6",
          "with": {"name": "metrics-record"}}]}}),
    (".github/workflows/reusable.yml",
     {"name": "reusable · fx", "on": {"workflow_call": None},
      "jobs": {"j": {"steps": [{"uses": "actions/upload-artifact@v6",
                                "with": {"name": "metrics-record-r"}}]}}}),
    (".github/workflows/wrapper.yml",
     {"name": "fx wrapper", "on": {"push": None},
      "jobs": {"call": {"uses": "./.github/workflows/reusable.yml"}}}),
    (".github/workflows/silent.yml",
     {"name": "fx silent", "on": {"schedule": [{"cron": "2 2 * * *"}]},
      "jobs": {"j": {"steps": [{"uses": "actions/upload-artifact@v6",
                                "with": {"name": "claude-execution-output"}}]}}}),
]
FIXTURE_OWNERS = {
    ".github/workflows/direct.yml": "fx direct",
    ".github/workflows/via-composite.yml": "fx via composite",
    ".github/workflows/wrapper.yml": "fx wrapper",
}


def discovery_failures(**opts):
    with tempfile.TemporaryDirectory() as root:
        for rel, doc in FIXTURE_TREE:
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(doc, fh, allow_unicode=True)
        got = record_owners(root, **opts)
    if got != FIXTURE_OWNERS:
        return [f"record-owner discovery over the fixture tree found {got}, "
                f"expected {FIXTURE_OWNERS} -- a discovery that misses an "
                f"edge shrinks the set this gate requires the wrapper to "
                f"cover, and nothing else notices"]
    return []


def load_subject():
    doc = load(WRAPPER)
    on = triggers(doc)
    documented = contract_block()
    return {
        "workflows": list((on.get("workflow_run") or {}).get("workflows") or []),
        "schedule": [str((e or {}).get("cron") or "").strip()
                     for e in (on.get("schedule") or [])],
        "dispatch-inputs": dict((on.get("workflow_dispatch") or {}).get("inputs") or {}),
        "jobs": dict(doc.get("jobs") or {}),
        "documented-workflows": list(
            (documented.get("workflow_run") or {}).get("workflows") or []),
        "documented-schedule": [str((e or {}).get("cron") or "").strip()
                                for e in (documented.get("schedule") or [])],
        "sweep-paths": sweep_paths(dict(doc.get("jobs") or {})),
        "record-owners": record_owners(),
        "wrapper-contract-workflows": wrapper_contract_workflows(),
        "count-claims": count_claims(),
    }


# Every trigger shape the wrapper can see, and which job must own it.
# (label, context, job that must run)
EVENTS = [
    ("a stage completion", {"github.event_name": "workflow_run",
                            "github.event.workflow_run.conclusion": "success",
                            "inputs.since": ""}, PERSIST_JOB),
    ("the daily schedule", {"github.event_name": "schedule",
                            "github.event.workflow_run.conclusion": "",
                            "inputs.since": ""}, SWEEP_JOB),
    ("a single-run dispatch", {"github.event_name": "workflow_dispatch",
                               "github.event.workflow_run.conclusion": "",
                               "inputs.since": ""}, PERSIST_JOB),
    ("a sweep dispatch", {"github.event_name": "workflow_dispatch",
                          "github.event.workflow_run.conclusion": "",
                          "inputs.since": "2026-09-01T00:00:00Z"}, SWEEP_JOB),
]
PAUSE_VAR = "vars.WING_COMMANDER_METRICS_PAUSED"


def suite(subject):
    broke = []

    if WATCHDOG_NAME in subject["workflows"]:
        broke.append(f"{WRAPPER} still lists {WATCHDOG_NAME!r} under "
                     f"workflow_run.workflows -- that reinstates one whole "
                     f"persistence run per inspection, and after FR-031 a "
                     f"healthy inspection has no record for it to find")
    for name in sorted(SWEEP_ONLY - {WATCHDOG_NAME}):
        if name in subject["workflows"]:
            broke.append(f"{WRAPPER} lists the sweep-only {name!r} under "
                         f"workflow_run.workflows -- nothing reads its "
                         f"records promptly, so that is a persistence run "
                         f"per completion for what the daily sweep already "
                         f"collects (FR-030(a))")
    if not subject["workflows"]:
        broke.append(f"{WRAPPER} lists no workflow_run workflows at all -- the "
                     f"per-completion path for the promptly-read stages "
                     f"is not supposed to go away with the watchdog's")

    crons = subject["schedule"]
    if len(crons) != 1:
        broke.append(f"the wrapper declares {len(crons)} cron entr(ies) "
                     f"({crons}); FR-030(c) is one daily sweep")
    else:
        mine = minute_hour(crons[0])
        for path, cron in other_crons():
            if minute_hour(cron) == mine:
                broke.append(f"the sweep's cron {crons[0]!r} shares its minute "
                             f"and hour with {path} ({cron!r}) -- two "
                             f"workflows asking for the same instant queue "
                             f"behind each other (research.md R-C6)")

    if subject["documented-workflows"] != subject["workflows"]:
        broke.append(f"{CONTRACT}'s published workflow_run list "
                     f"{subject['documented-workflows']} does not match the "
                     f"shipped one {subject['workflows']} -- an adopter forking "
                     f"this wrapper reads the document, not the file")
    if subject["documented-schedule"] != subject["schedule"]:
        broke.append(f"{CONTRACT} publishes cron {subject['documented-schedule']} "
                     f"and the wrapper ships {subject['schedule']}")

    # Coverage (#889): every record owner is persisted by both paths.
    if not subject["record-owners"]:
        broke.append("no workflow in this repository uploads a "
                     f"{RECORD_PREFIX}* artifact -- the discovery this "
                     "coverage check relies on has stopped seeing them")
    for path, name in sorted(subject["record-owners"].items()):
        if name not in SWEEP_ONLY and name not in subject["workflows"]:
            broke.append(f"{path} uploads a {RECORD_PREFIX}* artifact but its "
                         f"name {name!r} is not under {WRAPPER}'s "
                         f"workflow_run.workflows -- its records are only ever "
                         f"persisted if the sweep happens to reach them")
        if path not in subject["sweep-paths"]:
            broke.append(f"{path} uploads a {RECORD_PREFIX}* artifact but is "
                         f"not in {WRAPPER}'s sweep-workflow-paths -- a "
                         f"completion the trigger missed is never swept, and "
                         f"the artifact expires unpersisted")
    if subject["wrapper-contract-workflows"] != subject["workflows"]:
        broke.append(f"{WRAPPER_CONTRACT}'s published workflow_run list "
                     f"{subject['wrapper-contract-workflows']} does not match "
                     f"the shipped one {subject['workflows']}")

    for path, line, n in subject["count-claims"]:
        if n != len(subject["workflows"]):
            broke.append(f"{path}:{line} says the completion path covers {n} "
                         f"workflow(s); {WRAPPER} ships "
                         f"{len(subject['workflows'])} -- stale prose about "
                         f"the trigger list (#889)")

    if "since" not in subject["dispatch-inputs"]:
        broke.append("workflow_dispatch declares no `since` input -- the "
                     "hand-driven sweep re-drive has no way in")

    # The schedule has to start something. Evaluate the real job guards.
    for label, ctx, want in EVENTS:
        full = dict(ctx)
        full[PAUSE_VAR] = ""
        ran = []
        for job_id in (PERSIST_JOB, SWEEP_JOB):
            expr = str((subject["jobs"].get(job_id) or {}).get("if") or "")
            if not expr.strip():
                broke.append(f"job {job_id!r} has no `if:` -- it would run on "
                             f"every trigger this wrapper hears")
                continue
            try:
                if truthy(evaluate(expr, full)):
                    ran.append(job_id)
            except (ValueError, IndexError) as exc:
                broke.append(f"{label}: job {job_id!r}'s if: did not evaluate: {exc}")
        if ran != [want]:
            broke.append(f"{label}: job(s) {ran} run, expected exactly "
                         f"[{want!r}] -- a schedule reaching `persist` would "
                         f"persist run-id '', and a completion reaching "
                         f"`sweep` would sweep on every stage run")

    # The kill switch covers both jobs, including the one added here.
    for job_id in (PERSIST_JOB, SWEEP_JOB):
        expr = str((subject["jobs"].get(job_id) or {}).get("if") or "")
        if PAUSE_VAR not in expr:
            broke.append(f"job {job_id!r}'s `if:` does not read {PAUSE_VAR} -- "
                         f"the wrapper owns the pause switch (constitution VII) "
                         f"and a job it does not cover cannot be paused")
    return broke


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_watchdog_restored(subject):
    s = dict(subject)
    s["workflows"] = subject["workflows"] + [WATCHDOG_NAME]
    return s


def mut_board_loop_on_trigger(subject):
    s = dict(subject)
    s["workflows"] = subject["workflows"] + [BOARD_LOOP_NAME]
    s["wrapper-contract-workflows"] = list(s["workflows"])
    s["documented-workflows"] = list(s["workflows"])
    s["count-claims"] = [(p, ln, len(s["workflows"]))
                         for p, ln, _ in subject["count-claims"]]
    return s


def mut_cron_collides(subject):
    s = dict(subject)
    collide = other_crons()
    s["schedule"] = [collide[0][1]] if collide else ["43 5 * * *"]
    return s


def mut_schedule_reaches_persist(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["jobs"].items()}
    jobs[PERSIST_JOB] = dict(jobs.get(PERSIST_JOB, {}),
                             **{"if": f"{PAUSE_VAR} != 'true'"})
    s["jobs"] = jobs
    return s


def mut_sweep_unpausable(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["jobs"].items()}
    jobs[SWEEP_JOB] = dict(jobs.get(SWEEP_JOB, {}), **{
        "if": "github.event_name == 'schedule' || "
              "(github.event_name == 'workflow_dispatch' && inputs.since != '')"})
    s["jobs"] = jobs
    return s


def mut_contract_cron_drifts(subject):
    s = dict(subject)
    s["documented-schedule"] = ["5 5 * * *"]
    return s


def _first_named_owner(subject):
    named = [(p, n) for p, n in sorted(subject["record-owners"].items())
             if n not in SWEEP_ONLY]
    return named[0] if named else ("", "")


def mut_owner_dropped_from_trigger(subject):
    s = dict(subject)
    _, name = _first_named_owner(subject)
    s["workflows"] = [w for w in subject["workflows"] if w != name]
    s["wrapper-contract-workflows"] = list(s["workflows"])
    s["documented-workflows"] = list(s["workflows"])
    # Keep the count prose in step with the shorter list, so only the
    # trigger-coverage check can catch this mutation.
    s["count-claims"] = [(p, ln, len(s["workflows"]))
                         for p, ln, _ in subject["count-claims"]]
    return s


def mut_owner_dropped_from_sweep(subject):
    s = dict(subject)
    path, _ = _first_named_owner(subject)
    s["sweep-paths"] = [p for p in subject["sweep-paths"] if p != path]
    return s


def mut_watchdog_unswept(subject):
    s = dict(subject)
    s["sweep-paths"] = [p for p in subject["sweep-paths"] if p != WATCHDOG_PATH]
    return s


def mut_new_owner_unlisted(subject):
    s = dict(subject)
    s["record-owners"] = dict(subject["record-owners"], **{
        ".github/workflows/fx-new-uploader.yml": "fx new uploader"})
    return s


def mut_wrapper_contract_drifts(subject):
    s = dict(subject)
    s["wrapper-contract-workflows"] = subject["workflows"] + [WATCHDOG_NAME]
    return s


def mut_stale_count_claim(subject):
    s = dict(subject)
    # One off the shipped length -- the "ten" this list briefly carried.
    s["count-claims"] = subject["count-claims"] + [
        (CONTRACT, 50, len(subject["workflows"]) + 1)]
    return s


DISCOVERY_MUTATIONS = [
    ("discovery stops following local composites",
     {"follow_composites": False}),
    ("discovery stops crediting a reusable workflow's records to its caller",
     {"follow_callers": False}),
]


MUTATIONS = [
    ("a record owner is dropped from the completion trigger",
     mut_owner_dropped_from_trigger),
    ("a record owner is dropped from the sweep's workflow paths",
     mut_owner_dropped_from_sweep),
    ("the sweep-only watchdog is dropped from the sweep's workflow paths",
     mut_watchdog_unswept),
    ("a new record-uploading workflow is listed in neither",
     mut_new_owner_unlisted),
    ("the 043 wrapper contract's trigger list drifts from the shipped one",
     mut_wrapper_contract_drifts),
    ("live prose keeps a stale completion-workflow count",
     mut_stale_count_claim),
    ("the watchdog is restored to the completion trigger", mut_watchdog_restored),
    ("the sweep-only board-loop joins the completion trigger, docs and all",
     mut_board_loop_on_trigger),
    ("the published contract's cron drifts from the shipped one",
     mut_contract_cron_drifts),
    ("the sweep's cron collides with another schedule", mut_cron_collides),
    ("the schedule also reaches the single-run job", mut_schedule_reaches_persist),
    ("the sweep job stops honouring the pause switch", mut_sweep_unpausable),
]


def main():
    use_utf8_stdout()
    subject = load_subject()
    failures = suite(subject) + discovery_failures()
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        mutated = mutate(subject)
        if mutated == subject:
            print(f"::error::mutation {label!r} changed nothing -- the shape it "
                  f"targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        if suite(mutated):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    for label, opts in DISCOVERY_MUTATIONS:
        if discovery_failures(**opts):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 79: {len(EVENTS)} trigger shape(s), "
          f"{len(other_crons())} other schedule(s), "
          f"{len(subject['record-owners'])} record-owning workflow(s), "
          f"{len(MUTATIONS) + len(DISCOVERY_MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
