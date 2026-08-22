#!/usr/bin/env python3
"""Proves the lifecycle gate's retry actually runs, not merely ships.

WHY THIS EXISTS
---------------
Run 31597186484 died at `Check lifecycle issue state` on a transient
`HTTP 502` from GitHub's GraphQL endpoint: one attempt, no retry, and the
reported error asserted the issue "may not exist, or the token lacks
issues: read" — neither of which was true, because the command substitution
captured stdout only and the real `HTTP 502` on stderr was discarded. The
gate is the first billable step of six stages, so that single unretried read
kills a stage before preflight, before checkout, before any work.

This script drives the SHIPPED `Check lifecycle issue state` step (via
`find_step`, never a copy — gate 5 exists because a copy sat green for weeks
while checking a filter that did not ship) against a stubbed `gh` on PATH,
proving: a transient failure is retried and eventually succeeds (FR-011); a
permanent failure — issue not found, credential rejected — fails after
exactly one attempt (FR-012); a failure the gate has never seen before still
lands in the retry bucket (FR-009, SC-009); and every gate failure names
what the API actually reported (FR-004, FR-005, SC-003, SC-007). The
mutations at the end reintroduce three ways this could regress and assert
each independently fails the suite (FR-013), plus a reflexive check that
Gate 25 itself is still wired into lint-workflows.yml (FR-014) — per #169's
lesson, a harness that can only exercise the success path proves nothing.

Usage: python3 .github/scripts/verify-lifecycle-gate-retry.py [-v]
Requires: bash, jq (same prerequisites every other shell-harness gate needs).
"""
import copy
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, resolve_bash, run_step,
                              use_utf8_stdout)

ACTION = ".github/actions/wing-commander-lifecycle-gate/action.yml"
STEP_NAME = "Check lifecycle issue state"
WORKFLOW = ".github/workflows/lint-workflows.yml"
GATE_PREFIX = "Gate 25"

ISSUE_NUMBER = "184"
TOKEN = "x"

BASH = None


def find_step(path, name):
    """The step dict named `name`, from either a workflow's `jobs` or a
    composite action's `runs.steps`.

    wc_shell_harness.find_step only searches `jobs` — every caller before
    this one targeted a workflow file. The composite-action gates that
    already exist (verify-agent-verdict.py, verify-tool-args-contract.py,
    verify-tooling-statement.py, verify-metrics-turn-accounting.py) each
    read `runs.steps` inline rather than through the shared harness; this
    is that same lookup, kept local so the shared module — reused
    unmodified by every other gate that depends on it — needs no change.
    """
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == name:
            return step
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == name:
                return step
    sys.exit(f"::error file={path}::no step named {name!r}. If it was "
             f"renamed, update the workflow and its harness together — do "
             f"not drop the check.")


def _sq(text):
    """Single-quote `text` for embedding in the generated `/bin/sh` stub."""
    return "'" + text.replace("'", "'\\''") + "'"


def gh_stub_script(behaviors):
    """A `#!/bin/sh` stub for `bindir/gh` that varies by call count.

    `behaviors` is a list of (rc, stdout, stderr) tuples, 1-indexed by call,
    optionally with a fourth element: seconds to sleep BEFORE producing any
    of it. A call beyond the list's length repeats the LAST entry — this is
    how "always fails the same way" scenarios (a single-element list) and
    "fails N times then succeeds" scenarios (an N+1-element list) share one
    generator (research.md D6).

    The sleep exists so a scenario can drive the shipped step's real
    `timeout` rather than simulating its exit code. A stub that sleeps
    longer than the step's `read_timeout` is killed by it, and the step sees
    124 from the same code path production does — including the detail that
    made this worth covering: `timeout` writes NOTHING to stderr, so the
    only witness to what happened is the exit code.
    """
    lines = ["#!/bin/sh",
             'n=$(cat "$GH_CALL_COUNT" 2>/dev/null || echo 0)',
             'n=$((n + 1))',
             'echo "$n" > "$GH_CALL_COUNT"',
             'case "$n" in']
    for i, behavior in enumerate(behaviors, start=1):
        rc, stdout, stderr = behavior[0], behavior[1], behavior[2]
        sleep_secs = behavior[3] if len(behavior) > 3 else 0
        label = str(i) if i < len(behaviors) else "*"
        lines.append(f"  {label})")
        if sleep_secs:
            lines.append(f"    sleep {sleep_secs}")
        if stdout:
            lines.append(f"    printf '%s' {_sq(stdout)}")
        if stderr:
            lines.append(f"    printf '%s' {_sq(stderr)} 1>&2")
        lines.append(f"    exit {rc}")
        lines.append("    ;;")
    lines.append("esac")
    return "\n".join(lines) + "\n"


def run_scenario(step_script, behaviors, root):
    """Execute the shipped step's `run:` text against one stubbed `gh`.

    Returns (rc, output, outputs, call_count). `GH_CALL_COUNT` lives under
    this scenario's own workdir, unique per call so scenarios never share
    state (contracts/lifecycle-gate-retry-coverage.md's stub mechanism).
    """
    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    bindir = os.path.join(workdir, "bin")
    call_count_file = os.path.join(workdir, "gh_call_count")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    open(call_count_file, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(gh_stub_script(behaviors))
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    rc, out, outputs, _ = run_step(
        BASH, step_script, workdir,
        {"GH_TOKEN": TOKEN, "ISSUE_NUMBER": ISSUE_NUMBER,
         "GH_CALL_COUNT": call_count_file,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)
    with open(call_count_file, encoding="utf-8") as fh:
        raw = fh.read().strip()
    return rc, out, outputs, int(raw) if raw else 0


def _expect_success(name, behaviors, state, is_open, calls):
    def check(rc, out, outputs, call_count):
        failures = []
        if rc != 0:
            failures.append(f"{name}: expected the step to succeed, exited "
                            f"{rc}: {out.strip()}")
            return failures
        if outputs.get("state") != state:
            failures.append(f"{name}: expected state={state!r}, got "
                            f"{outputs.get('state')!r}")
        if outputs.get("is-open") != is_open:
            failures.append(f"{name}: expected is-open={is_open!r}, got "
                            f"{outputs.get('is-open')!r}")
        if call_count != calls:
            failures.append(f"{name}: expected {calls} gh call(s), got "
                            f"{call_count} — a retry that runs more or "
                            f"fewer attempts than intended is itself a "
                            f"defect this gate must catch.")
        return failures
    return {"name": name, "behaviors": behaviors, "check": check}


def _expect_failure(name, behaviors, calls, contains=(), excludes=()):
    def check(rc, out, outputs, call_count):
        failures = []
        if rc == 0:
            failures.append(f"{name}: expected the step to fail, but it "
                            f"succeeded (state={outputs.get('state')!r})")
            return failures
        if call_count != calls:
            failures.append(f"{name}: expected exactly {calls} gh call(s), "
                            f"got {call_count} — a test that cannot tell "
                            f"one attempt from several does not satisfy "
                            f"this story.")
        for text in contains:
            if text not in out:
                failures.append(f"{name}: expected the reported failure to "
                                f"contain {text!r}; got: {out.strip()}")
        for text in excludes:
            if text in out:
                failures.append(f"{name}: expected the reported failure "
                                f"NOT to contain {text!r}; got: {out.strip()}")
        return failures
    return {"name": name, "behaviors": behaviors, "check": check}


# US1 (FR-001, FR-011, SC-001, SC-005) — a transient blip costs a retry, not
# a run, and a first-attempt success is unchanged.
FIRST_ATTEMPT_SUCCESS = _expect_success(
    "first-attempt success (SC-005 baseline)",
    [(0, "OPEN", "")], "OPEN", "true", 1)

TRANSIENT_THEN_SUCCEED = _expect_success(
    "transient-then-succeed",
    [(1, "", "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)"),
     (1, "", "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)"),
     (0, "OPEN", "")],
    "OPEN", "true", 3)

UNCLASSIFIED_THEN_SUCCEED = _expect_success(
    "unclassified-then-succeed",
    [(1, "", "a completely unfamiliar fault, never seen before (code Q7)"),
     (0, "CLOSED", "")],
    "CLOSED", "false", 2)

SUCCESS_EMPTY_STATE = _expect_success(
    "success, empty state",
    [(0, "", ""), (0, "OPEN", "")],
    "OPEN", "true", 2)

# US2 (FR-004, FR-005, FR-006, SC-003, SC-007) — the error says what
# actually happened, and budget exhaustion distinguishes recognised
# transient from unclassified.
BUDGET_EXHAUSTED_TRANSIENT = _expect_failure(
    "budget exhausted, recognised transient",
    [(1, "", "HTTP 503: Service Unavailable")],
    calls=3,
    contains=["after 3", "HTTP 503", "recognised transient class"],
    excludes=["could not be classified"])

BUDGET_EXHAUSTED_UNCLASSIFIED = _expect_failure(
    "budget exhausted, unclassified",
    [(1, "", "a totally unfamiliar fault, code Q9")],
    calls=3,
    contains=["after 3", "code Q9", "could not be classified"],
    excludes=["recognised transient class"])

# A hung read — the transient class FR-001 names first, and Acceptance
# Scenario 5's subject. It is the only class that says nothing for itself:
# `timeout` exits 124 having written nothing to stderr, so before this was
# covered the step reported a hang as "could not be classified. Last attempt
# reported: no diagnostic output" — the message SC-007 exists to prevent, on
# the fault that motivated the feature.
#
# The two scenarios split deliberately. TIMEOUT_THEN_SUCCEED drives the
# REAL `timeout`: the stub sleeps past `read_timeout` and is killed, so the
# 124 comes from production's own code path and not from an assumption
# about it. It costs one `read_timeout` of wall clock, which buys the only
# proof that the exit code is what we think. BUDGET_EXHAUSTED_TIMEOUT then
# has the stub exit 124 directly — `timeout` propagates the child's status
# when it exits on its own — so the message wording is asserted across a
# full budget without paying three more timeouts.
TIMEOUT_THEN_SUCCEED = _expect_success(
    "timeout-then-succeed (Acceptance Scenario 5, real timeout)",
    [(0, "OPEN", "", 30), (0, "OPEN", "")],
    "OPEN", "true", 2)

BUDGET_EXHAUSTED_TIMEOUT = _expect_failure(
    "budget exhausted, every read timed out",
    [(124, "", "")],
    calls=3,
    contains=["after 3", "timed out", "recognised transient class"],
    excludes=["could not be classified", "no diagnostic output"])

# US3 (FR-002, FR-008, FR-012, SC-002) — a real failure still fails
# immediately, spending none of the retry budget; the message content
# assertions here also satisfy US2's Acceptance Scenarios 2-3 (T006).
ALWAYS_NOT_FOUND = _expect_failure(
    "always not-found",
    [(1, "", "Could not resolve to an issue with the number of 184.")],
    calls=1,
    contains=["may not exist", "#184"],
    excludes=["was rejected"])

ALWAYS_CREDENTIAL_REJECTED = _expect_failure(
    "always credential-rejected",
    [(1, "", "HTTP 401: Bad credentials")],
    calls=1,
    contains=["was rejected", "Bad credentials"],
    excludes=["may not exist"])

SUCCESS_UNRECOGNISED_VALUE = _expect_failure(
    "success, unrecognised value",
    [(0, "MERGED", "")],
    calls=1,
    contains=["unrecognized state", "MERGED"])

# Convergence Phase 8 (missing coverage found after the first implement
# pass) — a transient failure followed by a permanent one must stop
# retrying at the permanent failure rather than treating it as more
# transient noise (US3/AC3), and a rate-limited 403 must retry rather
# than being mistaken for a rejected credential (Edge Case "The API
# rejects the read for rate-limiting reasons", research.md D2).
TRANSIENT_THEN_NOT_FOUND = _expect_failure(
    "transient-then-not-found",
    [(1, "", "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)"),
     (1, "", "Could not resolve to an issue with the number of 184.")],
    calls=2,
    contains=["may not exist"],
    excludes=["retried attempts", "recognised transient class",
              "could not be classified"])

RATE_LIMITED_403 = _expect_failure(
    "rate-limited 403 retries rather than failing immediately",
    [(1, "", "HTTP 403: API rate limit exceeded for installation ID "
             "12345678.")],
    calls=3,
    contains=["after 3"],
    excludes=["was rejected"])

# Convergence Phase 9 (missing coverage found after the second implement
# pass) — sanitize() (research.md D4, FR-017, FR-018) is implemented in
# action.yml but nothing in this feature's own coverage had ever driven a
# diagnostic long/multi-line/percent-bearing enough to prove the truncation,
# whitespace-folding, and %-escaping actually run rather than merely ship.
# The percent sign and both newline forms sit well inside the retained
# first-300-characters, so this exercises sanitize() folding real content,
# not content it discarded anyway.
_LONG_MULTILINE_PERCENT_DIAGNOSTIC = (
    "Could not resolve to an issue with the number of 184. "
    "Line one carries a literal percent 100% sign.\r\n"
    "Line two arrives after a CRLF sequence.\n"
    "Line three arrives after a bare LF.\n"
    + ("Padding to push this diagnostic past the sanitize() 300 character "
       "cap so truncation actually executes. " * 4)
)


def _check_long_multiline_percent_not_found(rc, out, outputs, call_count):
    name = ("not-found diagnostic longer than 300 chars, with an embedded "
            "percent sign and raw CRLF/LF newlines")
    failures = []
    if rc == 0:
        failures.append(f"{name}: expected the step to fail, but it "
                        f"succeeded (state={outputs.get('state')!r})")
        return failures
    if call_count != 1:
        failures.append(f"{name}: expected exactly 1 gh call, got "
                        f"{call_count} — a not-found diagnostic must fail "
                        f"on the first attempt regardless of its length.")
    if "may not exist" not in out:
        failures.append(f"{name}: expected the reported failure to contain "
                        f"'may not exist'; got: {out.strip()}")
    if "… (truncated)" not in out:
        failures.append(f"{name}: expected the reported failure to contain "
                        f"the truncation marker '… (truncated)'; got: "
                        f"{out.strip()}")
    if "%25" not in out:
        failures.append(f"{name}: expected the reported failure to contain "
                        f"the escaped percent sign '%25'; got: {out.strip()}")
    for line in out.split("\n"):
        if line.strip() and not (line.startswith("::error::")
                                  or line.startswith("::warning::")):
            failures.append(f"{name}: expected every non-blank line to be "
                            f"an ::error::/::warning:: annotation command, "
                            f"but a raw diagnostic line reached the output "
                            f"unescaped: {line!r}")
    return failures


LONG_MULTILINE_PERCENT_NOT_FOUND = {
    "name": ("not-found diagnostic longer than 300 chars, with an embedded "
             "percent sign and raw CRLF/LF newlines"),
    "behaviors": [(1, "", _LONG_MULTILINE_PERCENT_DIAGNOSTIC)],
    "check": _check_long_multiline_percent_not_found,
}

SCENARIOS = [
    FIRST_ATTEMPT_SUCCESS,
    TRANSIENT_THEN_SUCCEED,
    UNCLASSIFIED_THEN_SUCCEED,
    SUCCESS_EMPTY_STATE,
    BUDGET_EXHAUSTED_TRANSIENT,
    BUDGET_EXHAUSTED_UNCLASSIFIED,
    TIMEOUT_THEN_SUCCEED,
    BUDGET_EXHAUSTED_TIMEOUT,
    ALWAYS_NOT_FOUND,
    ALWAYS_CREDENTIAL_REJECTED,
    SUCCESS_UNRECOGNISED_VALUE,
    TRANSIENT_THEN_NOT_FOUND,
    RATE_LIMITED_403,
    LONG_MULTILINE_PERCENT_NOT_FOUND,
]


# US4 (FR-013, SC-006) — reverting, widening, or narrowing the retry each
# independently fails a check. Each mutation is applied to a deep copy of
# the REAL extracted step text, never to the file on disk.

def _mut_revert_retry(steps):
    """Collapse the loop back to today's single attempt."""
    steps[STEP_NAME] = steps[STEP_NAME].replace(
        "max_attempts=3", "max_attempts=1", 1)


def _mut_widen_permanent_classifier(steps):
    """Make the not-found pattern also match a transient shape (HTTP 502)."""
    old = "'Could not resolve to an.*issue|HTTP 404'"
    new = "'Could not resolve to an.*issue|HTTP 404|HTTP 502'"
    steps[STEP_NAME] = steps[STEP_NAME].replace(old, new, 1)


def _mut_narrow_retry(steps):
    """Fail immediately on an unclassified fault instead of retrying it."""
    old = ('  else\n'
           '    last_class_phrase="the failures could not be classified"\n'
           '  fi')
    new = ('  else\n'
           '    safe="$(sanitize "$diagnostic")"\n'
           '    echo "::error::wing-commander-lifecycle-gate: unclassified '
           'failure for issue #$ISSUE_NUMBER: $safe"\n'
           '    exit 1\n'
           '  fi')
    steps[STEP_NAME] = steps[STEP_NAME].replace(old, new, 1)


def _mut_drop_timeout_classification(steps):
    """Stop naming a `timeout` expiry, sending it back to unclassified.

    Indentation-independent on purpose: the literal below is the test
    itself, not a whole line, so this mutation cannot quietly stop applying
    if the surrounding block is ever re-indented — a mutation that no longer
    mutates passes for the wrong reason.
    """
    old = '[ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]'
    assert old in steps[STEP_NAME], (
        "the timeout classifier is not where this mutation expects it; "
        "a mutation that matches nothing proves nothing.")
    steps[STEP_NAME] = steps[STEP_NAME].replace(old, "false", 1)


MUTATIONS = [
    ("revert the retry to a single attempt",
     _mut_revert_retry,
     TRANSIENT_THEN_SUCCEED,
     lambda rc, out, outputs, calls: rc != 0),
    ("widen the permanent-pattern classifier to match a transient shape",
     _mut_widen_permanent_classifier,
     TRANSIENT_THEN_SUCCEED,
     lambda rc, out, outputs, calls: rc != 0 and calls == 1),
    ("narrow the retry so an unclassified failure fails immediately",
     _mut_narrow_retry,
     UNCLASSIFIED_THEN_SUCCEED,
     lambda rc, out, outputs, calls: rc != 0 and calls == 1),
    ("stop classifying a timeout, reporting the hang as unclassifiable",
     _mut_drop_timeout_classification,
     BUDGET_EXHAUSTED_TIMEOUT,
     lambda rc, out, outputs, calls: (rc != 0
                                      and "could not be classified" in out)),
]


def check_gate_wired():
    """FR-014's reflexive check: this script cannot see its own absence
    from a workflow it isn't in, so it reads lint-workflows.yml directly
    (not the step text `find_step` extracts) and confirms Gate 25 is both
    present and enabled — per repository convention, Gate 15's own finding.
    """
    wf = yaml.safe_load(open(WORKFLOW, encoding="utf-8")) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name") or ""
            if name.startswith(GATE_PREFIX):
                if str(step.get("if", "")).strip().lower() == "false":
                    return [f"{GATE_PREFIX} step is present in {WORKFLOW} "
                            f"but disabled (if: false) — its own coverage "
                            f"would not run (FR-014)."]
                return []
    return [f"no step named {GATE_PREFIX!r} found in {WORKFLOW} — this "
            f"script's own coverage would not run if it were dropped from "
            f"the registry (FR-014)."]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    steps = {STEP_NAME: find_step(ACTION, STEP_NAME)["run"]}

    failures = []
    root = tempfile.mkdtemp()
    try:
        for scenario in SCENARIOS:
            rc, out, outputs, calls = run_scenario(
                steps[STEP_NAME], scenario["behaviors"], root)
            scen_failures = scenario["check"](rc, out, outputs, calls)
            failures.extend(scen_failures)
            print(f"[{'FAIL' if scen_failures else 'ok'}] {scenario['name']} "
                  f"(rc={rc}, calls={calls})")
            if verbose or scen_failures:
                text = out.strip()
                if text:
                    print(text)

        for label, apply_mutation, target, expect_caught in MUTATIONS:
            mutated = copy.deepcopy(steps)
            apply_mutation(mutated)
            if mutated[STEP_NAME] == steps[STEP_NAME]:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation "
                      f"so this harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            rc, out, outputs, calls = run_scenario(
                mutated[STEP_NAME], target["behaviors"], root)
            if expect_caught(rc, out, outputs, calls):
                print(f"Mutation OK — {label}: caught "
                      f"(rc={rc}, calls={calls}).")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing "
                      f"{label!r} broke nothing this suite catches "
                      f"(rc={rc}, calls={calls}). Fix the scenarios, not "
                      f"the mutation.")
                failures.append(f"mutation survived: {label}")

        failures.extend(check_gate_wired())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"lifecycle gate retry: {len(SCENARIOS)} scenario(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    for f in failures:
        print(f"::error::{f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
