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
while checking a filter that did not ship), which runs the read's one home,
`.github/actions/_shared/lifecycle-issue-state.sh`, from its own
$GITHUB_ACTION_PATH (#1210), against a stubbed `gh` on PATH,
proving: a transient failure is retried and eventually succeeds (FR-011); a
permanent failure — issue not found, credential rejected — fails after
exactly one attempt (FR-012); a failure the gate has never seen before still
lands in the retry bucket (FR-009, SC-009); and every gate failure names
what the API actually reported (FR-004, FR-005, SC-003, SC-007). The
mutations at the end reintroduce three ways this could regress and assert
each independently fails the suite (FR-013), plus a reflexive check that
Gate 25 itself is still wired into lint-workflows.yml (FR-014) — per #169's
lesson, a harness that can only exercise the success path proves nothing.

#1210 moved the read out of the step into the shared script so that
wing-commander-board-stop-check can run it from its own directory instead of
a nested `uses: ./.github/actions/wing-commander-lifecycle-gate`, which
resolves against the caller's workspace. check_single_home() fails if either
composite stops running the script, if a composite gains a nested
workspace-relative `uses: ./.github/...` step again, or if the read's body is pasted
back into any other file.

Usage: python3 .github/scripts/verify-lifecycle-gate-retry.py [-v]
Requires: bash, jq (same prerequisites every other shell-harness gate needs).
"""
import copy
import os
import shlex
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_repo_files import repo_files  # noqa: E402
from wc_shell_harness import (ensure_jq, resolve_bash, run_step,
                              step_shell, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-lifecycle-gate/action.yml"
STEP_NAME = "Check lifecycle issue state"
SCRIPT = ".github/actions/_shared/lifecycle-issue-state.sh"
# Every composite step that performs the "is this issue open" read: each
# must run SCRIPT from its own $GITHUB_ACTION_PATH, exactly this way (#1210).
# The `gh issue view` argv stays in each step so Gate 12 can resolve its
# token there (it refuses a gh call inside a _shared script).
SCRIPT_INVOCATION = ('bash "$GITHUB_ACTION_PATH/../_shared/lifecycle-issue-state.sh" '
                     'gh issue view "$ISSUE_NUMBER" --json state --jq .state')
SCRIPT_CALLERS = (
    (ACTION, STEP_NAME),
    (".github/actions/wing-commander-board-stop-check/action.yml",
     "Check whether the issue is already closed"),
)
# A line only the read's body carries: its presence anywhere but SCRIPT is a
# pasted second copy.
BODY_SIGNATURE = 'last_class_phrase="the failures could not be classified"'
WORKFLOW = ".github/workflows/lint-workflows.yml"
GATE_PREFIX = "Gate 25"

ISSUE_NUMBER = "184"
TOKEN = "x"

BASH = None
SHIPPED_STEP_RUN = None


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
            lines.append(f"    printf '%s' {shlex.quote(stdout)}")
        if stderr:
            lines.append(f"    printf '%s' {shlex.quote(stderr)} 1>&2")
        lines.append(f"    exit {rc}")
        lines.append("    ;;")
    lines.append("esac")
    return "\n".join(lines) + "\n"


def run_scenario(step_script, behaviors, root):
    """Execute the shared script (`step_script`, its text, possibly mutated)
    through the shipped step's own `run:` line against one stubbed `gh`.

    The script is written where the step's `$GITHUB_ACTION_PATH/../_shared/`
    resolution expects it, inside this scenario's own workdir, and the
    shipped step's `run:` text is what executes -- so a step that stopped
    calling the script would fail every scenario.

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
    action_path = os.path.join(workdir, "actions", "wing-commander-lifecycle-gate")
    shared_dir = os.path.join(workdir, "actions", "_shared")
    os.makedirs(action_path)
    os.makedirs(shared_dir)
    with open(os.path.join(shared_dir, os.path.basename(SCRIPT)), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(step_script)
    open(call_count_file, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(gh_stub_script(behaviors))
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    rc, out, outputs, _ = run_step(
        BASH, SHIPPED_STEP_RUN, workdir,
        {"GH_TOKEN": TOKEN, "ISSUE_NUMBER": ISSUE_NUMBER,
         "GH_CALL_COUNT": call_count_file,
         "GITHUB_ACTION_PATH": action_path,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp, shell=step_shell(ACTION, STEP_NAME))
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

# The other GraphQL not-found form. `gh issue view --json` resolves the
# repository before the issue, so a token that cannot see the repository
# fails on the Repository node and never reaches the Issue one. Permanent
# by definition and worth zero retries, exactly like the issue form.
ALWAYS_REPOSITORY_UNRESOLVABLE = _expect_failure(
    "always repository-unresolvable",
    [(1, "", "GraphQL: Could not resolve to a Repository with the name "
             "'charlesguse/wing-commander'.")],
    calls=1,
    contains=["could not be resolved", "#184"],
    excludes=["could not be classified", "retried attempts",
              "was rejected"])

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
    ALWAYS_REPOSITORY_UNRESOLVABLE,
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


PERMANENT_PATTERN = "'Could not resolve to an? .*(issue|repository)|HTTP 404'"


def _mut_widen_permanent_classifier(steps):
    """Make the not-found pattern also match a transient shape (HTTP 502)."""
    assert PERMANENT_PATTERN in steps[STEP_NAME], (
        "the permanent-failure pattern is not where this mutation expects "
        "it; a mutation that matches nothing proves nothing.")
    new = PERMANENT_PATTERN[:-1] + "|HTTP 502'"
    steps[STEP_NAME] = steps[STEP_NAME].replace(PERMANENT_PATTERN, new, 1)


def _mut_narrow_permanent_to_issue_only(steps):
    """Revert the classifier to the issue-only form it shipped with.

    GraphQL names the node it could not resolve, so a token that cannot see
    the repository at all reports a Repository, not an Issue. The original
    pattern therefore matched neither it nor the credential branch below,
    and a permanent permission fault spent the full retry budget before
    being reported as unclassifiable.
    """
    assert PERMANENT_PATTERN in steps[STEP_NAME], (
        "the permanent-failure pattern is not where this mutation expects "
        "it; a mutation that matches nothing proves nothing.")
    steps[STEP_NAME] = steps[STEP_NAME].replace(
        PERMANENT_PATTERN, "'Could not resolve to an.*issue|HTTP 404'", 1)


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
    ("narrow the permanent classifier back to issue-only, sending a "
     "repository-permission fault down the retry path",
     _mut_narrow_permanent_to_issue_only,
     ALWAYS_REPOSITORY_UNRESOLVABLE,
     lambda rc, out, outputs, calls: (rc != 0 and calls == 3
                                      and "could not be classified" in out)),
    ("stop classifying a timeout, reporting the hang as unclassifiable",
     _mut_drop_timeout_classification,
     BUDGET_EXHAUSTED_TIMEOUT,
     lambda rc, out, outputs, calls: (rc != 0
                                      and "could not be classified" in out)),
]


def _composite_steps(path):
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    return [s or {} for s in ((doc.get("runs") or {}).get("steps") or [])]


def _github_files(repo_root):
    """The tracked files under repo_root/.github -- an untracked scratch copy
    or editor backup is not a second home (wc_repo_files falls back to a
    walk outside a git work tree, as for the self-test's fixtures)."""
    return [os.path.join(repo_root, rel) for rel in repo_files(repo_root)
            if rel.startswith(".github/")]


def check_single_home(repo_root="."):
    """#1210's checks, in this gate because the read is this gate's subject.

    1. Each SCRIPT_CALLERS step runs SCRIPT_INVOCATION and nothing else, as
       a `shell: bash` run: step (not a `uses:`).
    2. No composite under .github/actions/ has a `uses: ./.github/...`
       step: inside a composite that path resolves against the CALLER's
       $GITHUB_WORKSPACE root, not the composite's own directory, so it
       either does not exist or runs whatever copy the caller's own
       checkout carries (#488, #1210). A composite runs a sibling's logic
       through a script under _shared/ instead. (A `uses:` naming the
       stage workflows' explicit pipeline checkout,
       `./.wing-commander-pipeline/...`, is that convention's own
       documented contract and is not this check's subject.)
    3. BODY_SIGNATURE appears in SCRIPT and in no other tracked file under
       .github/ -- a pasted copy of the read is a second home.
    """
    failures = []
    for path, name in SCRIPT_CALLERS:
        full = os.path.join(repo_root, path)
        step = next((s for s in _composite_steps(full)
                     if s.get("name") == name), None)
        if step is None:
            failures.append(f"{path}: no step named {name!r} -- it is a "
                            f"SCRIPT_CALLERS entry; update this gate with it.")
            continue
        if "uses" in step:
            failures.append(f"{path}: step {name!r} uses "
                            f"{step['uses']!r}; it must run {SCRIPT} from its "
                            f"own $GITHUB_ACTION_PATH instead (#1210).")
        if (step.get("run") or "").strip() != SCRIPT_INVOCATION:
            failures.append(f"{path}: step {name!r} must run exactly "
                            f"{SCRIPT_INVOCATION!r} (got "
                            f"{(step.get('run') or '').strip()!r}).")
        if step.get("shell") != "bash":
            failures.append(f"{path}: step {name!r} must declare shell: bash.")

    actions_dir = os.path.join(repo_root, ".github", "actions")
    for entry in sorted(os.listdir(actions_dir)):
        action = os.path.join(actions_dir, entry, "action.yml")
        if not os.path.isfile(action):
            continue
        for step in _composite_steps(action):
            uses = str(step.get("uses") or "")
            if uses.startswith("./.github/"):
                failures.append(
                    f".github/actions/{entry}/action.yml: step "
                    f"{step.get('name') or step.get('id')!r} uses {uses!r}. "
                    f"Inside a composite a `./.github/` path resolves against the "
                    f"caller's $GITHUB_WORKSPACE, not this composite's "
                    f"directory (#1210, #488): run the logic through a "
                    f"script under .github/actions/_shared/ instead.")

    script_full = os.path.normpath(os.path.join(repo_root, SCRIPT))
    this_file = os.path.normpath(os.path.abspath(__file__))
    found_in_script = False
    for full in _github_files(repo_root):
        full = os.path.normpath(full)
        if os.path.abspath(full) == this_file:
            continue
        try:
            text = open(full, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        if BODY_SIGNATURE not in text:
            continue
        if full == script_full:
            found_in_script = True
        else:
            failures.append(
                f"{os.path.relpath(full, repo_root)}: carries a copy of "
                f"the lifecycle read ({BODY_SIGNATURE!r}); its one home "
                f"is {SCRIPT} -- run that instead.")
    if not found_in_script:
        failures.append(f"{SCRIPT}: missing {BODY_SIGNATURE!r} -- update "
                        f"BODY_SIGNATURE with the script.")
    return failures


def _single_home_fixture(root, name, mutate):
    """A minimal tree check_single_home() passes on, then `mutate(tree)`."""
    tree = os.path.join(root, "single-home-" + name)
    caller_steps = {
        path: [{"name": step_name, "shell": "bash",
                "run": SCRIPT_INVOCATION + "\n"}]
        for path, step_name in SCRIPT_CALLERS}
    mutate(tree, caller_steps)
    for path, steps in caller_steps.items():
        full = os.path.join(tree, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            yaml.safe_dump({"runs": {"using": "composite", "steps": steps}}, fh)
    script = os.path.join(tree, SCRIPT)
    os.makedirs(os.path.dirname(script), exist_ok=True)
    if not os.path.exists(script):
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(BODY_SIGNATURE + "\n")
    return tree


def _write(tree, rel, text):
    full = os.path.join(tree, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text)


def _fixture_nested_uses(tree, caller_steps):
    caller_steps[".github/actions/x/action.yml"] = [
        {"name": "nested", "uses": "./.github/actions/wing-commander-lifecycle-gate"}]


def _fixture_pasted_copy(tree, caller_steps):
    _write(tree, ".github/actions/_shared/pasted.sh", BODY_SIGNATURE + "\n")


def _fixture_caller_uses(tree, caller_steps):
    path, name = SCRIPT_CALLERS[1]
    caller_steps[path] = [{"name": name,
                           "uses": "./.github/actions/wing-commander-lifecycle-gate"}]


def _fixture_script_lost_body(tree, caller_steps):
    _write(tree, SCRIPT, "#!/usr/bin/env bash\n")


SINGLE_HOME_FIXTURES = [
    ("a composite with a nested `uses: ./.github/actions/...` step",
     _fixture_nested_uses, "resolves against the"),
    ("a pasted copy of the read in another file", _fixture_pasted_copy,
     "carries a copy of the lifecycle read"),
    ("a SCRIPT_CALLERS step that `uses:` the lifecycle gate",
     _fixture_caller_uses, "must run"),
    ("the shared script no longer carries BODY_SIGNATURE",
     _fixture_script_lost_body, "missing"),
]


def check_single_home_selftest(root):
    """#169's lesson for check_single_home(): a clean fixture passes, and
    each one-defect fixture fails with a message naming that defect."""
    failures = []
    clean = check_single_home(_single_home_fixture(root, "clean", lambda t, c: None))
    if clean:
        failures.append(f"single-home self-test: the clean fixture failed: {clean}")
    for i, (label, mutate, needle) in enumerate(SINGLE_HOME_FIXTURES):
        got = check_single_home(_single_home_fixture(root, str(i), mutate))
        ok = any(needle in msg for msg in got)
        print(f"[{'ok' if ok else 'FAIL'}] single-home self-test: {label} is caught")
        if not ok:
            failures.append(f"single-home self-test: {label} was not caught "
                            f"(expected a failure naming {needle!r}, got {got!r})")
    return failures


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
    global SHIPPED_STEP_RUN
    SHIPPED_STEP_RUN = find_step(ACTION, STEP_NAME)["run"]
    with open(SCRIPT, encoding="utf-8") as fh:
        steps = {STEP_NAME: fh.read()}

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

        single_home = check_single_home()
        print(f"[{'FAIL' if single_home else 'ok'}] single home: both "
              f"composites run {SCRIPT}, no composite has a nested `uses: ./.github/` "
              f"step, and no other file carries a copy of the read")
        failures.extend(single_home)
        failures.extend(check_single_home_selftest(root))
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
