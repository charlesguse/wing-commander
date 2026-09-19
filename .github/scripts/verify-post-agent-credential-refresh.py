#!/usr/bin/env python3
"""Gate 68 - a bot-acting step after an agent step always holds a fresh
credential, and a tolerated observability callout is actually tolerated.

WHY THIS EXISTS
---------------
spec 052: the minted App installation token has a one-hour lifetime,
shorter than some agent steps run. Every agent-bearing job now relays its
mint into a job-scoped env.WC_BOT_TOKEN / env.WC_SCRATCH_TOKEN variable and
re-mints it immediately after each agent step (contracts/
wing-commander-context-relay.md). Nothing stops a future edit from adding a
new post-agent step that reads the stale `steps.<id>.outputs.token` form
directly, or a second agent step in the same job with no refresh between it
and the one before it, or a new "Report over-budget agent run" copy with no
`continue-on-error: true` -- each of those quietly reintroduces the defect
this feature fixed. This gate catches all three, structurally, on every PR
that touches a workflow file.

WHAT THIS CHECKS
----------------
For each of the 8 sweep-stage jobs (FR-007's list) that contains at least
one agent step (a step whose `uses:` resolves to
`anthropics/claude-code-action@*`):

1. No step positioned after the job's first agent step references
   `steps.<any-id>.outputs.*token*` directly -- it must resolve its
   credential through `env.WC_BOT_TOKEN` / `env.WC_SCRATCH_TOKEN` instead.
   The one exemption is the relay step itself (`name` starting with "Relay"
   and containing "token to the job environment") -- that step's entire job
   is to read the fresh mint's raw output and put it in the job environment,
   so it necessarily reads the raw form (FR-020 care point 1).
2. Every agent step in a job after the first is preceded, since the
   previous agent step, by a `wing-commander-context` (or, for
   auto-update-spec-kit.yml's e2e-stage job, `scoped-app-token`) invocation
   (FR-020 care point 2).
3. Every step whose name is exactly "Report over-budget agent run" carries
   `continue-on-error: true` (FR-021), in every job scanned -- not just
   jobs with an agent step, since the tolerance is a property of the step
   itself.
4. If any of the 8 named files is missing, a named job cannot be located,
   or zero agent steps are found across the whole named subject, the gate
   fails loudly rather than passing vacuously over an empty result set
   (FR-022, Constitution Principle VIII).

Static structure only (`yaml.safe_load`) -- this gate's subject is step
*ordering and reference shape*, not step *behaviour*, so no
`wc_shell_harness.py` execution pass is needed (research.md D6).

Self-test (--self-test): loads the real shipped trees, then reintroduces
each way this could regress -- a post-agent step's credential reference
reverted to the stale form, the refresh step between implement.yml's retry
and progress agent steps deleted, `continue-on-error: true` stripped from
clarify.yml's canonical over-budget step, the subject list pointed at a 9th
nonexistent file, and the subject list emptied -- and asserts each one
fails.

Usage: python3 .github/scripts/verify-post-agent-credential-refresh.py [--self-test]
"""
import copy
import io
import os
import re
import sys

import yaml

AGENT_ACTION_RE = re.compile(r"^anthropics/claude-code-action@")
TOKEN_REF_RE = re.compile(r"steps\.[\w-]+\.outputs\.[\w-]*token[\w-]*", re.IGNORECASE)
RELAY_STEP_NAME_RE = re.compile(r"^Relay\b.*token to the job environment", re.IGNORECASE)
MINT_USES_MARKERS = ("wing-commander-context", "scoped-app-token")
OVER_BUDGET_NAME = "Report over-budget agent run"

# path -> job names in scope, per FR-007's eight named stages.
SUBJECTS = {
    ".github/workflows/intake.yml": ["intake"],
    ".github/workflows/clarify.yml": ["clarify"],
    ".github/workflows/plan.yml": ["plan"],
    ".github/workflows/tasks.yml": ["tasks", "tasks-approved"],
    ".github/workflows/implement.yml": ["implement"],
    ".github/workflows/finalize.yml": ["finalize"],
    ".github/workflows/pr-conversation.yml": ["classify-and-announce", "act"],
    ".github/workflows/auto-update-spec-kit.yml": ["e2e-stage"],
}


def _is_agent_step(step):
    return bool(AGENT_ACTION_RE.match(str((step or {}).get("uses", ""))))


def _is_mint_step(step):
    uses = str((step or {}).get("uses", ""))
    return any(marker in uses for marker in MINT_USES_MARKERS)


def _is_relay_step(step):
    return bool(RELAY_STEP_NAME_RE.match(str((step or {}).get("name", ""))))


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _step_text(step):
    return "\n".join(_walk_strings(step))


def load_all(root="."):
    """-> {path: parsed_yaml_or_None} for every subject file."""
    out = {}
    for path in SUBJECTS:
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            out[path] = None
            continue
        with io.open(full, encoding="utf-8") as f:
            out[path] = yaml.safe_load(f) or {}
    return out


def check_job(path, job_name, job):
    """-> (failures: list[str], agent_step_count: int)."""
    failures = []
    steps = list((job or {}).get("steps") or [])

    # check 3 -- tolerance, independent of whether the job has an agent step.
    for step in steps:
        if str((step or {}).get("name", "")) == OVER_BUDGET_NAME \
                and not (step or {}).get("continue-on-error"):
            failures.append(
                f"{path} [{job_name}]: {OVER_BUDGET_NAME!r} does not carry "
                f"continue-on-error: true -- its own failure can strand the "
                f"deterministic read-back and every step below it (FR-021)")

    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]
    if not agent_idxs:
        return failures, 0

    first = agent_idxs[0]

    # check 1 -- no stale credential reference after the first agent step.
    for step in steps[first + 1:]:
        if _is_relay_step(step):
            continue
        name = (step or {}).get("name", "<unnamed step>")
        m = TOKEN_REF_RE.search(_step_text(step))
        if m:
            failures.append(
                f"{path} [{job_name}] step {name!r} references "
                f"{m.group(0)} after the job's first agent step -- it must "
                f"resolve its credential through env.WC_BOT_TOKEN / "
                f"env.WC_SCRATCH_TOKEN instead (FR-020 care point 1)")

    # check 2 -- every agent step after the first is preceded, since the
    # previous agent step, by a fresh mint.
    prev = first
    for idx in agent_idxs[1:]:
        between = steps[prev + 1:idx]
        if not any(_is_mint_step(s) for s in between):
            name = (steps[idx] or {}).get("name", "<unnamed step>")
            failures.append(
                f"{path} [{job_name}]: agent step {name!r} is not preceded, "
                f"since the previous agent step, by a wing-commander-context "
                f"(or scoped-app-token) mint -- it runs on a stale "
                f"credential (FR-020 care point 2)")
        prev = idx

    return failures, len(agent_idxs)


def scan(loaded, subjects=None):
    subjects = SUBJECTS if subjects is None else subjects
    failures = []
    total_agent_steps = 0
    for path, job_names in subjects.items():
        wf = loaded.get(path)
        if wf is None:
            failures.append(
                f"{path}: file not found -- cannot check its credential "
                f"handling (FR-022)")
            continue
        jobs = wf.get("jobs") or {}
        for job_name in job_names:
            job = jobs.get(job_name)
            if job is None:
                failures.append(
                    f"{path}: job {job_name!r} not found -- cannot check "
                    f"its credential handling (FR-022)")
                continue
            job_failures, n_agent = check_job(path, job_name, job)
            failures += job_failures
            total_agent_steps += n_agent

    if total_agent_steps == 0:
        failures.append(
            "zero agent steps were found across the named workflow "
            "files/jobs -- the subject list is misconfigured or "
            "unreachable, never a silent pass over an empty result set "
            "(FR-022)")

    return failures


# --------------------------------------------------------------------------
# Self-test -- mutations reintroducing each way this could regress.
# --------------------------------------------------------------------------
def _find_step(job, name):
    for step in (job or {}).get("steps") or []:
        if (step or {}).get("name") == name:
            return step
    return None


def mut_stale_credential_reference(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ steps.ctx.outputs.token }}"


def mut_drop_retry_progress_refresh(loaded):
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    name = "Re-establish Wing Commander context (post-agent, retry)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_drop_tolerance(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, OVER_BUDGET_NAME)
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("continue-on-error") is True, \
        "fixture assumption broken: tolerance already missing"
    del step["continue-on-error"]


def mut_nonexistent_ninth_file(loaded_and_subjects):
    loaded, subjects = loaded_and_subjects
    subjects["nonexistent-ninth-workflow.yml"] = ["some-job"]


def mut_zero_files(loaded_and_subjects):
    loaded, subjects = loaded_and_subjects
    subjects.clear()


SIMPLE_MUTATIONS = [
    ("a post-agent step's credential reference reverted to the stale "
     "steps.ctx.outputs.token form", mut_stale_credential_reference),
    ("the refresh step between implement.yml's retry and progress agent "
     "steps deleted", mut_drop_retry_progress_refresh),
    ("continue-on-error: true stripped from clarify.yml's canonical "
     "over-budget step", mut_drop_tolerance),
]

SUBJECT_MUTATIONS = [
    ("the subject list pointed at a 9th, nonexistent workflow file",
     mut_nonexistent_ninth_file),
    ("the subject list pointed at zero workflow files", mut_zero_files),
]


def self_test():
    base = load_all()
    problems = []

    clean = scan(copy.deepcopy(base))
    if clean:
        problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))

    for label, apply_mutation in SIMPLE_MUTATIONS:
        mutated = copy.deepcopy(base)
        apply_mutation(mutated)
        if mutated == base:
            problems.append(f"mutation {label!r} changed nothing -- the "
                            f"code it edits was rewritten; update the "
                            f"mutation.")
            continue
        broke = scan(mutated)
        if not broke:
            problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} "
                            f"broke nothing in this gate.")
        else:
            print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")

    for label, apply_mutation in SUBJECT_MUTATIONS:
        mutated_loaded = copy.deepcopy(base)
        mutated_subjects = copy.deepcopy(SUBJECTS)
        apply_mutation((mutated_loaded, mutated_subjects))
        broke = scan(mutated_loaded, mutated_subjects)
        if not broke:
            problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} "
                            f"broke nothing in this gate.")
        else:
            print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")

    for p in problems:
        print(f"::error::Gate 68 self-test: {p}")
    if problems:
        return 1
    print("Gate 68 self-test: clean tree passes; each mutation fails.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()

    failures = scan(load_all())
    for f in failures:
        print(f"::error::Gate 68: {f}")
    print(f"Gate 68: post-agent credential refresh; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
