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

#889/#972 adds a third behavioral check (check_agent_never_started): the
shipped wing-commander-agent-ran-signal block publishes started='false'
for a failed agent step with no execution transcript, and the shipped
dependency-reason block fed that value says the agent never started
instead of "the agent step ran". The self-test drifts each block in turn.

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
from wc_shell_harness import (find_step, resolve_bash, run_step,  # noqa: E402
                              step_shell)

STAGE = ".github/workflows/implement.yml"
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "implement-stall-notice-baseline.json")

STEP_NAMES = [
    "Mark lifecycle record stalled",
    "Announce the stall on the lifecycle issue",
]

# specs/071-agent-push-credential: this step's `run:` block now carries a
# conditional "commits published" line (FR-016/FR-017) and so can no longer
# byte-pin against the frozen fixture above -- checked behaviorally instead
# (check_commits_published_branch), the same way DEPENDENCY_STEP_NAME below
# already is.
COMMITS_STEP_NAME = "Report stalled on lifecycle issue"

DEPENDENCY_STEP_NAME = "Determine which dependency did not start"
NEVER_STARTED_PHRASE = "the implement stage failed before it could run its own steps"
# Second maintainer review of PR #407 (CLAUDE.md single-home rule): the step
# itself is now a `uses:` call to this composite, not an inline `run:` block
# in implement.yml -- the composite's own copy is what this gate executes.
STALL_REASON_COMPOSITE = ".github/actions/wing-commander-stall-reason/action.yml"

# #889/#972: the agent-started signal the never-started branch reads.
AGENT_RAN_SIGNAL_COMPOSITE = ".github/actions/wing-commander-agent-ran-signal/action.yml"
AGENT_RAN_SIGNAL_STEP_NAME = "Record agent-ran signal"


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
    """-> (script, failures): the composite's shipped `run:` block, or why not.

    `find_step` never returns None on a miss -- it exits the process itself,
    with its own generic "no step named" message (#439 review). The lookup
    against STAGE below is kept for that loud-failure side effect (the step
    vanishing from implement.yml entirely still stops the run, just with
    that more generic message instead of the one this function used to
    return). Only the composite lookup's `run:` block can be legitimately
    absent while the step itself still exists -- reshaped into a `uses:`
    call, say -- so only that case is reported through the (script,
    failures) return convention `check_dependency_reason_branch` expects.
    """
    find_step(STAGE, DEPENDENCY_STEP_NAME)
    step = find_step(STALL_REASON_COMPOSITE, DEPENDENCY_STEP_NAME)
    script = step.get("run")
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
    executes the composite's own shipped copy instead, confirming the step
    still exists in implement.yml and still has a `run:` block in the
    composite (shipped_dependency_script; this does NOT inspect the step's
    `if:` guard -- nothing in this file does, #439 review), and covering
    the behavior once here rather than re-testing it identically at all six
    call sites (the composite has exactly one body).

    `script` overrides the shipped block; the self-test hands in drifted
    copies so the assertions below are proven to fire.
    """
    if script is None:
        script, failures = shipped_dependency_script()
        if failures:
            return failures

    bash = resolve_bash()
    # The self-test hands in drifted one-line copies run_step cannot trace
    # back to the composite step on its own, so name the step they stand in for.
    shell = step_shell(STALL_REASON_COMPOSITE, DEPENDENCY_STEP_NAME)
    failures = []
    with tempfile.TemporaryDirectory() as workdir, \
         tempfile.TemporaryDirectory() as runner_temp:
        rc, _out, outputs, _summary = run_step(
            bash, script, workdir,
            {"STAGE_NAME": "implement", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "failure",
             "CREDENTIAL_REFRESH_OK": "true", "FAILED_STEP": ""},
            runner_temp, shell=shell)
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
            runner_temp, shell=shell)
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
            runner_temp, shell=shell)
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
            runner_temp, shell=shell)
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
            runner_temp, shell=shell)
        reason = outputs.get("reason", "")
        if reason != NEVER_STARTED_PHRASE:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} with agent-ran unset changed from "
                f"the pinned never-started phrase: {reason!r}")
    return failures


def check_agent_never_started(signal_script=None, reason_script=None):
    """#889/#972: an agent step whose action failed in its own setup.

    Run 37866026318's intake agent step concluded failure because
    claude-code-action's own runtime install failed, before the agent
    started; the stall comment still said "the agent step ran ... its pushed
    commits are on the branch". Executes the two shipped blocks that now
    tell those apart, chained the way the stage wires them:
    wing-commander-agent-ran-signal's `started` (failure plus an absent or
    empty transcript reads 'false'; a non-empty transcript, or any other
    outcome, reads 'true'), then the stall reason fed that value -- which
    must say the agent never started, keep a named post-agent step only as
    context, and never claim the agent ran.

    `signal_script`/`reason_script` override the shipped blocks; the
    self-test hands in drifted copies.
    """
    if signal_script is None:
        signal_script = find_step(AGENT_RAN_SIGNAL_COMPOSITE,
                                  AGENT_RAN_SIGNAL_STEP_NAME).get("run") or ""
    if reason_script is None:
        reason_script, failures = shipped_dependency_script()
        if failures:
            return failures
    bash = resolve_bash()
    signal_shell = step_shell(AGENT_RAN_SIGNAL_COMPOSITE,
                              AGENT_RAN_SIGNAL_STEP_NAME)
    reason_shell = step_shell(STALL_REASON_COMPOSITE, DEPENDENCY_STEP_NAME)
    failures = []
    with tempfile.TemporaryDirectory() as workdir, \
         tempfile.TemporaryDirectory() as runner_temp:
        transcript = os.path.join(workdir, "claude-execution-output.json")

        def started_for(outcome, content):
            if os.path.exists(transcript):
                os.remove(transcript)
            if content is not None:
                with open(transcript, "w", encoding="utf-8") as fh:
                    fh.write(content)
            _rc, _out, outputs, _summary = run_step(
                bash, signal_script, workdir,
                {"AGENT_OUTCOME": outcome, "TRANSCRIPT_PATH": transcript},
                runner_temp, shell=signal_shell)
            return outputs.get("started", "")

        cases = [
            ("failure", None, "false"),
            ("failure", "", "false"),
            ("failure", '[{"type":"result","subtype":"error"}]', "true"),
            ("success", None, "true"),
        ]
        never_started = None
        for outcome, content, want in cases:
            got = started_for(outcome, content)
            if got != want:
                shape = ("absent" if content is None
                         else "empty" if content == "" else "non-empty")
                failures.append(
                    f"{AGENT_RAN_SIGNAL_STEP_NAME!r} with outcome "
                    f"{outcome!r} and an {shape} transcript published "
                    f"started={got!r}, expected {want!r} (#889)")
            if (outcome, content) == ("failure", None):
                never_started = got

        _rc, _out, outputs, _summary = run_step(
            bash, reason_script, workdir,
            {"STAGE_NAME": "intake", "IMAGE_RESULT": "success",
             "ENTRY_RESULT": "failure",
             "AGENT_RAN": "true", "AGENT_CONCLUSION": "failure",
             "AGENT_STARTED": never_started or "",
             "CREDENTIAL_REFRESH_OK": "true",
             "FAILED_STEP": "Fail loud on non-healthy agent verdict"},
            runner_temp, shell=reason_shell)
        reason = outputs.get("reason", "")
        if "before the agent started" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} for an agent action that failed "
                f"before the agent started did not say so: {reason!r} (#889)")
        if "the agent step ran" in reason or "pushed commits" in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} for an agent action that failed "
                f"before the agent started still claims the agent ran: "
                f"{reason!r} (#889)")
        if "'Fail loud on non-healthy agent verdict'" not in reason:
            failures.append(
                f"{DEPENDENCY_STEP_NAME!r} for an agent action that failed "
                f"before the agent started dropped the named post-agent "
                f"step as context: {reason!r} (#889)")
    return failures


def check_commits_published_branch(script=None):
    """Execute the "Report stalled on lifecycle issue" script (COMMITS_STEP_NAME).

    specs/071-agent-push-credential FR-016/FR-017: this step consumes an
    already-rendered $PUBLISHED_LINE (computed by the separate "Compute
    published-commits line" step, which fronts the single-homed
    _shared/published-commits-line.sh -- a published stage may not resolve
    _shared/ directly, Gate 60's promotion check; wing-commander-published-
    commits-line/action.yml is the one composite that does, and its own
    construction logic is covered where it is actually exercised,
    verify-chain-stop-notice-body.py's scenario_commits_published). This
    check's own job is narrower: given a rendered line (or none), does the
    notice embed it correctly, without disturbing anything around it --
    the regression pin for "the notice is unchanged from today"
    (research.md D7's "adds a case, the current wording for the current
    case stays" rule, applied to this step the same way spec 052 already
    applied it to DEPENDENCY_STEP_NAME above).

    `script` overrides the shipped block; the self-test hands in drifted
    copies so the assertions below are proven to fire.
    """
    if script is None:
        step = find_step(STAGE, COMMITS_STEP_NAME)
        script = step.get("run")
        if not script:
            return [f"{COMMITS_STEP_NAME!r} has no `run:` block in {STAGE} — "
                    f"the exhausted-retry notice step was removed or reshaped."]

    bash = resolve_bash()
    failures = []
    base_env = {
        "GH_TOKEN": "x", "ISSUE": "231", "ITERATION": "2",
        "TIER": "sonnet", "REASON": "agent exhausted its turn budget",
        "AGENT_MSG": "", "SELF_WORKFLOW": "wing-commander-5-implement.yml",
        "RUN_URL": "https://example.invalid/actions/runs/1",
        "GITHUB_REPOSITORY": "example/example",
    }
    with tempfile.TemporaryDirectory() as workdir, \
         tempfile.TemporaryDirectory() as runner_temp:
        spec_dir = os.path.join(workdir, "specs", "041-implement-stall-notice")
        os.makedirs(spec_dir, exist_ok=True)
        with open(os.path.join(spec_dir, "spec-meta.json"), "w", encoding="utf-8") as fh:
            fh.write('{"iteration": 2}')
        # The script's own first four lines are `gh label create`/`gh issue
        # edit` calls, unconditional -- stub gh on PATH so those become
        # no-ops instead of "command not found" under this step's own
        # `bash -e` (production always has a real gh).
        bindir = os.path.join(workdir, "bin")
        os.makedirs(bindir, exist_ok=True)
        with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        env = dict(base_env)
        env["SPEC_DIR"] = "specs/041-implement-stall-notice"
        env["PATH"] = bindir + os.pathsep + os.environ["PATH"]

        published_line = ("3 commit(s) the agent could not push during the "
                          "run were published after it.")
        # A generic marker, not the exact expected string: a mutation that
        # renders SOME (wrong) line regardless of PUBLISHED_LINE must still
        # be caught even though its wording differs from the fixture value
        # below (code review of this PR).
        any_line_marker = "the agent could not push during the run"
        for line, expect_present in (("", False), (published_line, True)):
            env_run = dict(env)
            env_run["PUBLISHED_LINE"] = line
            run_step(bash, script, workdir, env_run, runner_temp, path_prepend=bindir)
            try:
                with open(os.path.join(runner_temp, "stall-comment.md"),
                          encoding="utf-8") as fh:
                    body = fh.read()
            except OSError:
                body = ""
            where = f"{COMMITS_STEP_NAME!r} with PUBLISHED_LINE={line!r}"
            has_line = any_line_marker in body
            if expect_present and published_line not in body:
                failures.append(f"{where} did not embed the "
                                f"published-commits line: {body!r}")
            if not expect_present and has_line:
                failures.append(f"{where} embedded a published-commits "
                                f"line it was not given (regression, "
                                f"research.md D7): {body!r}")
            # Broader regression pin (code review of this PR): the runbook
            # heading alone left the diagnose/fix/restart steps and the
            # restart-table rows entirely uncovered.
            for expected_fragment in (
                "### Runbook — restarting this specification",
                "1. **Diagnose**", "2. **Fix the cause**", "3. **Restart**",
                "| `spec_dir` | `specs/041-implement-stall-notice` |",
                "| `issue` | `231` |", "| `iteration` | `3` |",
                "gh workflow run wing-commander-5-implement.yml",
            ):
                if expected_fragment not in body:
                    failures.append(f"{where} dropped pinned runbook "
                                    f"content {expected_fragment!r}: {body!r}")

        # The <details> block only renders with a non-empty agent message --
        # a separate pass covers it (code review of this PR).
        env_msg = dict(env)
        env_msg["PUBLISHED_LINE"] = ""
        env_msg["AGENT_MSG"] = "the agent could not find spec.md"
        run_step(bash, script, workdir, env_msg, runner_temp, path_prepend=bindir)
        try:
            with open(os.path.join(runner_temp, "stall-comment.md"), encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            body = ""
        for expected_fragment in (
            "<details><summary><b>Agent's final message</b>",
            "````", "the agent could not find spec.md", "</details>",
        ):
            if expected_fragment not in body:
                failures.append(f"{COMMITS_STEP_NAME!r} with a non-empty "
                                f"agent message dropped {expected_fragment!r}: "
                                f"{body!r}")
    return failures


def run():
    baseline = load_baseline()
    with open(STAGE, encoding="utf-8") as fh:
        new_text = fh.read()
    return (check_pinned_steps(new_text, baseline)
            + check_dependency_reason_branch()
            + check_agent_never_started()
            + check_commits_published_branch())


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

    signal_script = find_step(AGENT_RAN_SIGNAL_COMPOSITE,
                              AGENT_RAN_SIGNAL_STEP_NAME).get("run") or ""
    always_started = signal_script.replace('started="false"', 'started="true"')
    if always_started == signal_script:
        problems.append("self-test setup: the always-started mutation's "
                        "target text was not found in the shipped signal -- "
                        "update the mutation together with the step.")
    expect("an agent-ran signal that always reports the agent started, even "
           "with no transcript (#889)",
           check_agent_never_started(signal_script=always_started),
           "expected 'false'", "did not say so")

    reason_script, _ = shipped_dependency_script()
    no_branch = (reason_script or "").replace(
        'if [ "$AGENT_RAN" = "true" ] && [ "$AGENT_STARTED" = "false" ]; then',
        'if false; then')
    if no_branch == reason_script:
        problems.append("self-test setup: the never-started-branch mutation's "
                        "target text was not found in the shipped reason "
                        "script -- update the mutation together with it.")
    expect("a dependency-reason script that ignores agent-started and says "
           "the agent ran (#889)",
           check_agent_never_started(reason_script=no_branch),
           "still claims the agent ran")

    commits_script = find_step(STAGE, COMMITS_STEP_NAME).get("run") or ""
    passthrough_line = 'published_line="$PUBLISHED_LINE"'
    always_published = commits_script.replace(
        passthrough_line,
        'published_line="always shown commit(s) the agent could not push '
        'during the run were published after it."')
    if always_published == commits_script:
        problems.append("self-test setup: the always-published mutation's "
                        "target text was not found in the shipped script — "
                        "update the mutation together with the step.")
    expect("a stall-comment script that always renders a published-commits "
           "line, even when PUBLISHED_LINE is empty",
           check_commits_published_branch(always_published),
           "embedded a published-commits line it was not given")

    never_published = commits_script.replace(passthrough_line, 'published_line=""')
    if never_published == commits_script:
        problems.append("self-test setup: the never-published mutation's "
                        "target text was not found in the shipped script — "
                        "update the mutation together with the step.")
    expect("a stall-comment script that ignores PUBLISHED_LINE and never "
           "embeds it",
           check_commits_published_branch(never_published),
           "did not embed the published-commits line")

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
