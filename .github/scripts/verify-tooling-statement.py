#!/usr/bin/env python3
"""Gate 19 — the tooling statement matches what the run actually permits.

WHY THIS EXISTS
---------------
`wing-commander-tool-args`'s `shell-commands` output is the prose a stage's
prompt hands its agent to describe what it may run in a shell. Before this
gate existed the render walked `effective_allowed` alone: it never
subtracted a denied command, a bare `Bash` grant rendered as nothing, exact
and prefix grants for the same command collapsed into duplicate text, and an
empty result reached the model as a dangling em dash inside a sentence
claiming the list was "exactly" the allowlist and "authoritative"
(specs/037-rendered-tooling-list). A prompt that overclaims what it enforces
is worse than one that says nothing — an agent trusts it and either wastes a
turn on a command that is silently denied, or believes a narrower run is
unrestricted.

WHAT IT RUNS
------------
The SHIPPED `Compose tool args` `run:` block, extracted from
`wing-commander-tool-args/action.yml` and executed against representative
configurations (mirroring gate 11's `shipped_script()`/`run_step()`
pattern) — there is no copied render logic here to drift out of sync.

It ends with mutation checks that reintroduce each of the four defects and
assert this suite goes red for each, per FR-015/User Story 4.
"""
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-tool-args/action.yml"
STEP_NAME = "Compose tool args"

failures = []
MUTATING = False


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    prefix = "note: (expected, mutation phase) " if MUTATING else \
        f"::error file={ACTION}::"
    print(f"{prefix}{case}: {msg}")


def note(msg):
    print(f"note: {msg}")


def shipped_script():
    """The action's own `Compose tool args` run: block, or a hard failure."""
    doc = yaml.safe_load(open(ACTION, encoding="utf-8"))
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == STEP_NAME:
            run = step.get("run")
            if run:
                return run
    print(f"::error file={ACTION}::gate 19 could not find the step named "
          f"{STEP_NAME!r}. If it was renamed, update this gate and the "
          f"action together — silently checking nothing is the failure mode "
          f"this gate exists to prevent.")
    sys.exit(1)


SCRIPT = shipped_script()

BASE_ENV = {
    "STEP_LABEL": "gate-19-test",
    "DEFAULT_ALLOWED": "Bash(git status:*),Bash(git add:*),Read",
    "DEFAULT_DISALLOWED": "Bash(git push:*)",
    "EXTRA_ALLOWED": "",
    "EXTRA_DISALLOWED": "",
    "ALLOWED_OVERRIDE": "__unset__",
    "DISALLOWED_OVERRIDE": "__unset__",
}

BASH = None  # resolved once in main()


def run_case(overrides):
    """Execute the shipped step once; return (rc, output, outputs, summary)."""
    env = {**BASE_ENV, **overrides}
    tmp = tempfile.mkdtemp(prefix="wc-tooling-statement-")
    try:
        return run_step(BASH, SCRIPT, tmp, env, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expect(case, overrides, want_shell_commands, exit_zero=True):
    rc, output, outputs, _summary = run_case(overrides)
    if exit_zero and rc != 0:
        fail(case, f"the action exited {rc}: {output.strip()[:300]}")
        return outputs
    got = outputs.get("shell-commands")
    if got != want_shell_commands:
        fail(case, f"expected shell-commands={want_shell_commands!r}, "
                   f"got {got!r}")
    if not (got or "").endswith("."):
        fail(case, f"shell-commands does not end in a period: {got!r}")
    return outputs


# --- the cases ---------------------------------------------------------
def case_no_configuration():
    """Acceptance 1.3, SC-003: no consumer config → exactly the defaults."""
    expect("no configuration",
           {},
           "This run permits these shell commands: `git status`, "
           "`git add`.")
    note("no extra-*/*-override inputs renders exactly the step's "
         "hard-coded default shell commands")


def case_extra_disallowed_subtracts():
    """Acceptance 1.1, 1.2: a deny that fully covers a default allow removes
    it from the statement, and allowed-tools is unaffected by the deny."""
    baseline = run_case({})[2]
    outputs = expect("extra-disallowed-tools subtracts",
                      {"EXTRA_DISALLOWED": "Bash(git status:*)"},
                      "This run permits these shell commands: `git add`.")
    if outputs.get("allowed-tools") != baseline.get("allowed-tools"):
        fail("extra-disallowed-tools subtracts",
             "allowed-tools changed when only extra-disallowed-tools was "
             f"set: {outputs.get('allowed-tools')!r} vs "
             f"{baseline.get('allowed-tools')!r}")
    note("a fully-covering deny drops the command from the statement "
         "while allowed-tools stays byte-identical to the no-subtraction "
         "case")


def case_allowed_override_replaces():
    """Acceptance 1.4: a wholesale allow replacement is what is stated."""
    expect("allowed-tools-override replaces",
           {"ALLOWED_OVERRIDE": "Bash(git log:*)"},
           "This run permits these shell commands: `git log`.")
    note("allowed-tools-override replaces the defaults wholesale, and the "
         "statement is derived from the replacement")


def case_deny_then_reallow():
    """Acceptance 1.5: explicit-allow-beats-default-deny (spec 026 D4)."""
    expect("deny then re-allow",
           {"EXTRA_DISALLOWED": "Bash(git status:*)",
            "EXTRA_ALLOWED": "Bash(git status:*)"},
           "This run permits these shell commands: `git status`, "
           "`git add`.")
    note("a command denied via extra-disallowed-tools and separately "
         "re-allowed via extra-allowed-tools is stated as permitted, "
         "agreeing with the enforced outcome")


def case_unrestricted_no_exception():
    """Acceptance 2.1: bare Bash allow, no matching deny."""
    expect("unrestricted, no exception",
           {"ALLOWED_OVERRIDE": "Bash", "DISALLOWED_OVERRIDE": ""},
           "This run permits any shell command.")
    note("a bare Bash allow with no deny states the unrestricted case "
         "plainly")


def case_unrestricted_with_exception():
    """research.md D3: bare Bash allow, one command-specific deny."""
    expect("unrestricted, with exception",
           {"ALLOWED_OVERRIDE": "Bash",
            "DISALLOWED_OVERRIDE": "Bash(git push:*)"},
           "This run permits any shell command except: `git push`.")
    note("a bare Bash allow under a partial deny names the denied command "
         "as an exception rather than staying silent about the narrowing")


def case_no_shell_entry_at_all():
    """Acceptance 2.2: no Bash/Bash(...) entry, other tools present."""
    expect("no shell grant at all",
           {"ALLOWED_OVERRIDE": "Read,Grep", "DISALLOWED_OVERRIDE": ""},
           "This run permits no shell command.")
    note("an allowed list with other tools but no shell grant renders the "
         "empty case as a complete sentence, other tools untouched")


def case_exact_only():
    """Acceptance 2.3: Bash(cmd) with no trailing :* is exact-only."""
    expect("exact-only grant",
           {"ALLOWED_OVERRIDE": "Bash(git status)",
            "DISALLOWED_OVERRIDE": ""},
           "This run permits these shell commands: `git status` (exact "
           "command only).")
    note("Bash(cmd) with no wildcard is distinguished from the "
         "any-arguments form")


def case_prefix_and_exact_together():
    """Acceptance 2.4: both forms granted → stated once, prefix form."""
    expect("prefix and exact together",
           {"ALLOWED_OVERRIDE": "Bash(git status),Bash(git status:*)",
            "DISALLOWED_OVERRIDE": ""},
           "This run permits these shell commands: `git status`.")
    note("Bash(cmd) and Bash(cmd:*) both granted collapse to one entry, in "
         "the broader prefix form")


def case_partial_overlap_deny():
    """Edge case: an EXACT deny does not cover a PREFIX allow."""
    expect("partial-overlap deny leaves it stated",
           {"ALLOWED_OVERRIDE": "Bash(git status:*)",
            "DISALLOWED_OVERRIDE": "Bash(git status)"},
           "This run permits these shell commands: `git status`.")
    note("a deny that only partially overlaps an allow (EXACT deny under a "
         "PREFIX allow) leaves the command stated")


def case_prefix_deny_covers_exact_allow():
    """research.md D2: a PREFIX deny covers an EXACT allow for the same
    command (PREFIX superset of EXACT)."""
    expect("prefix deny covers exact allow",
           {"ALLOWED_OVERRIDE": "Bash(git status)",
            "DISALLOWED_OVERRIDE": "Bash(git status:*)"},
           "This run permits no shell command.")
    note("a PREFIX deny fully covers an EXACT allow for the same command, "
         "dropping it to the empty case")


def case_any_deny_covers_any_allow():
    """research.md D2: a bare Bash deny covers a bare Bash allow entirely.

    Uses DEFAULT_ALLOWED/DEFAULT_DISALLOWED rather than the *-override
    inputs: an override value also becomes spec 026's `explicit_allow`
    (action.yml step 2), which would subtract "Bash" out of
    effective_disallowed before this gate's render ever saw it and end up
    testing spec 026's composition instead of this render's own coverage
    logic.
    """
    expect("any deny covers any allow",
           {"DEFAULT_ALLOWED": "Bash", "DEFAULT_DISALLOWED": "Bash"},
           "This run permits no shell command.")
    note("a disallowed bare Bash covers an allowed bare Bash entirely, "
         "producing the empty case rather than silence")


CASES = [
    case_no_configuration,
    case_extra_disallowed_subtracts,
    case_allowed_override_replaces,
    case_deny_then_reallow,
    case_unrestricted_no_exception,
    case_unrestricted_with_exception,
    case_no_shell_entry_at_all,
    case_exact_only,
    case_prefix_and_exact_together,
    case_partial_overlap_deny,
    case_prefix_deny_covers_exact_allow,
    case_any_deny_covers_any_allow,
]


# --- mutation checks -----------------------------------------------------
# Each mutation reintroduces one of the four defects this gate exists to
# catch, and each must turn at least one DISTINCT case red (FR-015, User
# Story 4 Acceptance 2).
MUTATIONS = [
    ("reverts the subtraction (D2)",
     lambda s: s.replace('[ "$covered" = "1" ] && continue', 'true')),
    ("reverts the unrestricted-shell case (D3/D5)",
     lambda s: s.replace(
         'if [ "$allowed_has_any" = "1" ] && [ "$disallowed_has_any" != "1" ]; then',
         'if [ "$allowed_has_any" = "1" ] && [ "1" != "1" ]; then')),
    ("reverts the empty-list fallback (D5)",
     lambda s: s.replace(
         'shell_commands="This run permits no shell command."',
         'shell_commands=""')),
    ("reverts the deduplication (D4)",
     lambda s: s.replace(
         '[ -n "${entry_seen[$cmd]+x}" ] && continue', 'true')),
]


def run_suite():
    global failures
    failures = []
    for case in CASES:
        case()
    return list(failures)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    real = run_suite()
    if real:
        print(f"Gate 19: {len(real)} failure(s) against the shipped action.")
        return 1

    global SCRIPT, MUTATING
    original = SCRIPT
    mutation_failures = 0
    MUTATING = True
    for label, mutate in MUTATIONS:
        mutated = mutate(original)
        if mutated == original:
            print(f"::error file={ACTION}::gate 19's mutation {label!r} no "
                  f"longer changes the script — the code it keys on has "
                  f"been rewritten, so this mutation proves nothing. "
                  f"Re-point it at the current implementation.")
            mutation_failures += 1
            continue
        SCRIPT = mutated
        caught = run_suite()
        SCRIPT = original
        if not caught:
            print(f"::error file={ACTION}::gate 19 mutation {label!r} was "
                  f"NOT caught — the suite passed against a knowingly "
                  f"broken action, so its green verdict on the real one "
                  f"means nothing. Add a case that fails on this mutation.")
            mutation_failures += 1
        else:
            print(f"note: mutation caught ({label}): "
                  f"{len(caught)} case(s) failed as intended")

    MUTATING = False
    residual = run_suite()
    if residual:
        print(f"::error::gate 19 left the script mutated; {len(residual)} "
              f"failure(s) on the re-run.")
        mutation_failures += 1

    print(f"Gate 19: {len(CASES)} case(s) and {len(MUTATIONS)} mutation(s) "
          f"checked; {mutation_failures} failure(s).")
    return 1 if mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
