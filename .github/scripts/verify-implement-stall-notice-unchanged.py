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

SELF-TEST (#410 item 3)
-----------------------
`--self-test` reintroduces each regression this gate exists to catch and
asserts it is caught, for the right reason: a pinned step's `run:` reworded,
a pinned step deleted, a pinned step's `uses:` reshaped, a pin missing from
the fixture, and a dependency-reason script that drifts on either branch
(the agent-ran branch rendering the never-started phrase; the unset branch
no longer rendering it byte-for-byte). The pinned-step mutations are made
on a parsed copy of implement.yml and re-serialised, so the comparison
under test is the one the gate ships; the script mutations are handed to
the same harness run the gate uses.

Usage: python3 .github/scripts/verify-implement-stall-notice-unchanged.py
       python3 .github/scripts/verify-implement-stall-notice-unchanged.py --self-test
"""
import json
import os
import sys
import tempfile

import yaml

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
# Second maintainer review of PR #407 (CLAUDE.md single-home rule): the step
# itself is now a `uses:` call to this composite, not an inline `run:` block
# in implement.yml -- the composite's own copy is what this gate executes.
STALL_REASON_COMPOSITE = ".github/actions/wing-commander-stall-reason/action.yml"


def find_step_in_text(text, name):
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


def check_pinned_steps(new_text, baseline):
    """-> failures: the three pinned steps in `new_text` vs the fixture."""
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
    return failures


def shipped_dependency_script():
    """-> (script, failures): the composite's shipped `run:` block, or why not."""
    if find_step(STAGE, DEPENDENCY_STEP_NAME) is None:
        return None, [f"{DEPENDENCY_STEP_NAME!r} not found in {STAGE} -- the "
                      f"dependency-diagnosis step was removed."]
    step = find_step(STALL_REASON_COMPOSITE, DEPENDENCY_STEP_NAME)
    script = step.get("run") if step else None
    if not script:
        return None, [f"{DEPENDENCY_STEP_NAME!r} has no `run:` block in "
                      f"{STALL_REASON_COMPOSITE} — the dependency-diagnosis step "
                      f"was removed or reshaped."]
    return script, []


def check_dependency_reason_branch(script=None):
    """Execute the "Determine which dependency did not start" script.

    Two cases, matching quickstart.md §5: agent-ran == 'true' must never
    render the pre-existing never-started phrase and must name the agent's
    own conclusion; agent-ran unset must render that literal phrase
    byte-for-byte, unchanged from today (the regression pin).

    Second maintainer review of PR #407 (CLAUDE.md single-home rule): the
    step in implement.yml is now a `uses:` call to
    wing-commander-stall-reason, not an inline `run:` block -- this gate
    executes the composite's own shipped copy instead, confirming
    implement.yml's `if:` guard is unchanged as a structural check
    (shipped_dependency_script), and covering the behavior once here rather
    than re-testing it identically at all six call sites (the composite has
    exactly one body).

    `script` overrides the shipped block; the self-test hands in drifted
    copies so the assertions below are proven to fire.
    """
    if script is None:
        script, failures = shipped_dependency_script()
        if failures:
            return failures

    bash = resolve_bash()
    failures = []
    with tempfile.TemporaryDirectory() as workdir, \
         tempfile.TemporaryDirectory() as runner_temp:
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
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
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
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
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "success",
             "CREDENTIAL_REFRESH_OK": "false", "FAILED_STEP": ""},
            runner_temp)
        reason = outputs.get("reason", "")
        if "credential" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with credential-refresh-ok == "
                f"'false' did not attribute the stall to the credential: "
                f"{reason!r}")

        # Third maintainer review of PR #407 (FR-004): when both a named
        # post-agent step failure AND a credential re-establishment failure
        # are known, the named failure must win precedence -- the credential
        # is context, not the primary cause -- and both facts must appear.
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "success",
             "CREDENTIAL_REFRESH_OK": "false", "FAILED_STEP": "push"},
            runner_temp)
        reason = outputs.get("reason", "")
        if "'push'" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with both a named failed step and "
                f"a credential failure did not name the step: {reason!r}")
        if "credential" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with both a named failed step and "
                f"a credential failure dropped the credential context: "
                f"{reason!r}")

        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
             "AGENT_RAN": "", "AGENT_CONCLUSION": "",
             "CREDENTIAL_REFRESH_OK": "", "FAILED_STEP": ""},
            runner_temp)
        reason = outputs.get("reason", "")
        if reason != NEVER_STARTED_PHRASE:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with agent-ran unset changed from "
                f"the pinned never-started phrase: {reason!r}")
    return failures


def run():
    baseline = load_baseline()
    with open(STAGE, encoding="utf-8") as fh:
        new_text = fh.read()
    return check_pinned_steps(new_text, baseline) + check_dependency_reason_branch()


# --------------------------------------------------------------------------
# Self-test (#410 item 3)
# --------------------------------------------------------------------------
def _mutated_stage_text(edit):
    """implement.yml parsed, `edit(step)` applied to each pinned step, and
    re-serialised. The gate's own parser reads the result, so what is under
    test is the shipped comparison, not a string the test invented. An edit
    returning "delete" removes the step."""
    with open(STAGE, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    for job in (doc.get("jobs") or {}).values():
        steps = (job or {}).get("steps") or []
        for step in list(steps):
            if (step or {}).get("name") in STEP_NAMES and edit(step) == "delete":
                steps.remove(step)
    return yaml.safe_dump(doc, sort_keys=False)


# Drifted dependency-reason scripts: one renders the never-started phrase on
# the agent-ran branch (the regression spec 052 forbids), one drops it from
# the unset branch (the pin spec 041 keeps). Both are otherwise well-formed.
ALWAYS_NEVER_STARTED = (
    'echo "reason=' + NEVER_STARTED_PHRASE + '" >> "$GITHUB_OUTPUT"\n')
NEVER_NEVER_STARTED = (
    'echo "reason=the agent ran and ended with conclusion \'failure\' '
    '(failed step: \'push\'; credential re-establishment failed)" '
    '>> "$GITHUB_OUTPUT"\n')


def self_test():
    problems = []

    def expect(label, failures, *substrings):
        joined = " | ".join(failures)
        if failures and all(s in joined for s in substrings):
            print(f"[ok] {label}")
        else:
            problems.append(f"{label}: expected failure(s) containing "
                            f"{list(substrings)}, got: {failures or 'clean'}")

    baseline = load_baseline()
    clean = run()
    if clean:
        problems.append("the shipped tree should be clean, got: " + " | ".join(clean))
    else:
        print("[ok] baseline: the shipped implement.yml matches the pin and the "
              "dependency-reason script behaves")

    # The re-serialised, UNmutated text must still pass: otherwise every
    # mutation below would fail for a reason that is not the mutation.
    identity = check_pinned_steps(_mutated_stage_text(lambda s: None), baseline)
    if identity:
        problems.append("the re-serialised implement.yml no longer matches the "
                        "pin, so the mutations below cannot be trusted: "
                        + " | ".join(identity))
    else:
        print("[ok] the parse/dump round trip of implement.yml matches the pin")

    def reword(step):
        if step.get("run") is not None:
            step["run"] = step["run"] + "\necho reworded\n"
    expect("a pinned step's `run:` reworded",
           check_pinned_steps(_mutated_stage_text(reword), baseline),
           "`run:` text changed")

    expect("a pinned step deleted",
           check_pinned_steps(_mutated_stage_text(lambda s: "delete"), baseline),
           "no longer exists")

    def reshape(step):
        if step.get("uses") is not None:
            step["uses"] = "./.github/actions/something-else"
    expect("a pinned step's `uses:` reshaped",
           check_pinned_steps(_mutated_stage_text(reshape), baseline),
           "`uses:` changed")

    with open(STAGE, encoding="utf-8") as fh:
        shipped_text = fh.read()
    short = dict(baseline)
    short.pop(STEP_NAMES[0])
    expect("a pin missing from the fixture",
           check_pinned_steps(shipped_text, short), "not pinned")

    expect("a dependency-reason script rendering the never-started phrase on "
           "the agent-ran branch",
           check_dependency_reason_branch(ALWAYS_NEVER_STARTED),
           "still rendered the never-started phrase")

    expect("a dependency-reason script dropping the pinned phrase on the "
           "agent-ran-unset branch",
           check_dependency_reason_branch(NEVER_NEVER_STARTED),
           "changed from the pinned never-started phrase")

    for p in problems:
        print(f"::error::{p}")
    print(f"implement.yml exhausted-retry notice self-test: {len(problems)} "
          f"failure(s).")
    return 1 if problems else 0


def main():
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    failures = run()
    for f in failures:
        print(f"::error::{f}")
    print(f"implement.yml exhausted-retry notice: {len(STEP_NAMES)} step(s) "
          f"checked against the pinned baseline; dependency-reason branch "
          f"behaviorally checked; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
