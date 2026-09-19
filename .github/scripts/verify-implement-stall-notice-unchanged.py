#!/usr/bin/env python3
"""implement.yml's exhausted-retry stall notice reads exactly as it did before.

WHY THIS EXISTS
----------------
specs/041-implement-stall-notice's Out of Scope is explicit: "Rewording the
existing exhausted-retry stall notice ... This feature adds a case; the
current wording for the current case stays" (research.md D7). The safest way
to guarantee that is to never touch the code that renders it — but "we did
not mean to touch it" is not the same claim as "we did not touch it". This
gate makes the second claim mechanically, not by re-reading five hundred
lines of surrounding YAML on every future change.

WHAT THIS CHECKS
----------------
Compares implement.yml's three exhausted-retry steps ("Mark lifecycle record
stalled", "Report stalled on lifecycle issue", "Announce the stall on the
lifecycle issue") in the working tree against
fixtures/implement-stall-notice-baseline.json — their wording pinned from
main at the 2026-08-24 merge (6f04355; spec 040 had already reworded the
pre-041 text, and a git-ref baseline is unreadable in CI's shallow
checkout). Each step's `run:`, `uses:`, and `with:` must match the pin
byte-for-byte; only `if:` guards were 041's to change.

specs/052-agent-credential-lifetime extends this file with a second,
behavioral check over a DIFFERENT step — "Determine which dependency did
not start" in the `stalled` job — which is not one of the three pinned
above and belongs to a different stall path entirely (a post-agent failure,
not an exhausted retry). That check executes the shipped `run:` block via
wc_shell_harness.py's run_step, asserting the new `agent-ran == 'true'`
branch never emits the pre-existing "never started" phrase, and that the
`agent-ran` unset case still emits that phrase byte-for-byte (the
regression pin research.md calls for: this feature's wording change must
land only on the new branch).

Usage: python3 .github/scripts/verify-implement-stall-notice-unchanged.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step, resolve_bash, run_step  # noqa: E402

STAGE = ".github/workflows/implement.yml"
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "implement-stall-notice-baseline.json")

STEP_NAMES = [
    "Mark lifecycle record stalled",
    "Report stalled on lifecycle issue",
    "Announce the stall on the lifecycle issue",
]

DEPENDENCY_STEP_NAME = "Determine which dependency did not start"
NEVER_STARTED_PHRASE = "the implement stage failed before it could run its own steps"


def find_step_in_text(text, name):
    import yaml
    wf = yaml.safe_load(text) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == name:
                return step
    return None


def load_baseline():
    try:
        with open(FIXTURE, encoding="utf-8") as fh:
            return json.load(fh)["steps"]
    except (OSError, KeyError, ValueError) as e:
        sys.exit(f"::error file={FIXTURE}::could not load the pinned "
                 f"baseline: {e}")


def check_dependency_reason_branch():
    """Execute the shipped "Determine which dependency did not start" script.

    Two cases, matching quickstart.md §5: agent-ran == 'true' must never
    render the pre-existing never-started phrase and must name the agent's
    own conclusion; agent-ran unset must render that literal phrase
    byte-for-byte, unchanged from today (the regression pin).
    """
    step = find_step(STAGE, DEPENDENCY_STEP_NAME)
    script = step.get("run")
    if not script:
        return [f"{DEPENDENCY_STEP_NAME!r} has no `run:` block in {STAGE} — "
                f"the dependency-diagnosis step was removed or reshaped."]

    bash = resolve_bash()
    failures = []
    with tempfile.TemporaryDirectory() as workdir, \
         tempfile.TemporaryDirectory() as runner_temp:
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"IMAGE_RESULT": "success", "IMPLEMENT_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "failure",
             "CREDENTIAL_REFRESH_OK": "true", "FAILED_STEP": ""},
            runner_temp)
        reason = outputs.get("reason", "")
        if NEVER_STARTED_PHRASE in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with agent-ran == 'true' still "
                f"rendered the never-started phrase: {reason!r}")
        if "ran" not in reason or "failure" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with agent-ran == 'true' did not "
                f"name the agent's own conclusion: {reason!r}")

        # spec 052 maintainer review of PR #407: the entry job now names the
        # specific post-agent step that failed, when it could identify one.
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"IMAGE_RESULT": "success", "IMPLEMENT_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "failure",
             "CREDENTIAL_REFRESH_OK": "true", "FAILED_STEP": "push"},
            runner_temp)
        reason = outputs.get("reason", "")
        if "'push'" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with a named failed-post-agent-step "
                f"did not name it in the reason: {reason!r}")

        # FR-004: a credential re-establishment failure is attributed to the
        # credential, not to the agent or a downstream step.
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"IMAGE_RESULT": "success", "IMPLEMENT_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "success",
             "CREDENTIAL_REFRESH_OK": "false", "FAILED_STEP": ""},
            runner_temp)
        reason = outputs.get("reason", "")
        if "credential" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with credential-refresh-ok == "
                f"'false' did not attribute the stall to the credential: "
                f"{reason!r}")

        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"IMAGE_RESULT": "success", "IMPLEMENT_RESULT": "failure",
             "AGENT_RAN": "", "AGENT_CONCLUSION": "",
             "CREDENTIAL_REFRESH_OK": "", "FAILED_STEP": ""},
            runner_temp)
        reason = outputs.get("reason", "")
        if reason != NEVER_STARTED_PHRASE:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with agent-ran unset changed from "
                f"the pinned never-started phrase: {reason!r}")
    return failures


def main():
    baseline = load_baseline()
    with open(STAGE, encoding="utf-8") as fh:
        new_text = fh.read()

    failures = []
    for name in STEP_NAMES:
        old_step = baseline.get(name)
        new_step = find_step_in_text(new_text, name)
        if old_step is None:
            failures.append(f"{name!r} not pinned in {FIXTURE} — update "
                            f"the fixture or the step name list together "
                            f"with this gate.")
            continue
        if new_step is None:
            failures.append(f"{name!r} no longer exists in {STAGE} — the "
                            f"exhausted-retry notice path was removed, not "
                            f"just left untouched.")
            continue
        old_run = old_step.get("run")
        new_run = new_step.get("run")
        if old_run is not None and new_run != old_run:
            failures.append(
                f"{name!r}'s `run:` text changed since the pinned baseline "
                f"— Out of Scope / research.md D7 requires this step's "
                f"wording stay byte-for-byte unchanged. If the reword was "
                f"intentional, regenerate the fixture on purpose, in its "
                f"own reviewed change.")
        # uses:/with: shape (the "Announce" step calls a composite, no run:)
        for key in ("uses", "with"):
            if old_step.get(key) != new_step.get(key):
                failures.append(
                    f"{name!r}'s `{key}:` changed since the pinned baseline: "
                    f"{old_step.get(key)!r} -> {new_step.get(key)!r}.")

    failures.extend(check_dependency_reason_branch())

    for f in failures:
        print(f"::error::{f}")
    print(f"implement.yml exhausted-retry notice: {len(STEP_NAMES)} step(s) "
          f"checked against the pinned baseline; dependency-reason branch "
          f"behaviorally checked; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
