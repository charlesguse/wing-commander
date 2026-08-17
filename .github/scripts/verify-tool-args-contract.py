#!/usr/bin/env python3
"""Gate 20 — every output the tool-args composite emits is declared, and
every declared output is emitted.

WHY THIS EXISTS
---------------
`wing-commander-tool-args` declares outputs in its own `outputs:` block,
writes them via `echo "<name>=<value>" >> "$GITHUB_OUTPUT"` in its shipped
shell, and lists them again by hand in
`specs/026-configurable-tool-lists/contracts/tool-composition-action.md`'s
Outputs table — three surfaces, nothing holding them in agreement. That is
exactly how `shell-commands` shipped in #214 already emitted before this
repository had a check that would have caught it: `action.yml`'s own
`outputs:` block happened to be correct by the time this gate was written,
but nothing kept it that way, and the published contract could just as
easily have drifted the other direction (a declared-but-dead output, or a
value nobody documents). specs/037-rendered-tooling-list exists to close
that gap.

WHAT IT CHECKS
--------------
Three name sets, all derived from files already in the repository — no new
manifest:

  1. `action.yml`'s `outputs:` keys.
  2. Every `<name>` in an `echo "<name>=<value>" >> "$GITHUB_OUTPUT"` line
     in the SHIPPED `Compose tool args` step's `run:` block.
  3. The first-column entries of `tool-composition-action.md`'s `## Outputs`
     table.

A name in one set but not all three fails, naming the specific output and
which set(s) it is missing from. This is a repository-development-time
check — it says nothing about whether a declared output's *value* is
correct; see `verify-tooling-statement.py` for that.

The self-test runs the same check against two scratch fixtures built from
the real files: one with a fourth `outputs:` entry that is never emitted,
one with `shell-commands` deleted from `outputs:` while the `run:` block
still emits it (this spec's own motivating defect, reproduced as a
regression fixture) — and asserts both fail for the expected reason while
the real, unmodified files pass (FR-015, User Story 4 Acceptance 4).
"""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

ACTION = ".github/actions/wing-commander-tool-args/action.yml"
CONTRACT = "specs/026-configurable-tool-lists/contracts/tool-composition-action.md"
STEP_NAME = "Compose tool args"

DECLARED_LABEL = "declared in action.yml's outputs:"
EMITTED_LABEL = "emitted to $GITHUB_OUTPUT"
DOCUMENTED_LABEL = "documented in tool-composition-action.md's Outputs table"


def declared_outputs(action_text):
    doc = yaml.safe_load(action_text) or {}
    return set((doc.get("outputs") or {}).keys())


def emitted_outputs(action_text):
    """Names written via `echo "<name>=..." >> "$GITHUB_OUTPUT"` in the
    shipped `Compose tool args` step — the same step
    `verify-tooling-statement.py` drives, extracted identically here rather
    than via a second, independently-drifting YAML walk."""
    doc = yaml.safe_load(action_text) or {}
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == STEP_NAME:
            run = step.get("run")
            if run:
                return set(re.findall(
                    r'echo "([A-Za-z0-9_-]+)=[^"]*"\s*>>\s*"\$GITHUB_OUTPUT"',
                    run))
            break
    sys.exit(f"::error file={ACTION}::gate 20 could not find the step "
              f"named {STEP_NAME!r}. If it was renamed, update this gate "
              f"and the action together — silently checking nothing is "
              f"the failure mode this gate exists to prevent.")


def documented_outputs(contract_text):
    m = re.search(r"^## Outputs\n(.*?)(?=\n## |\Z)", contract_text,
                  re.S | re.M)
    if not m:
        sys.exit(f"::error file={CONTRACT}::gate 20 could not find a "
                  f"'## Outputs' section. If it was renamed, update this "
                  f"gate and the contract together.")
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", m.group(1), re.M))


def check(action_text, contract_text):
    """Return a list of human-readable problems, empty when all three sets
    agree on every name."""
    declared = declared_outputs(action_text)
    emitted = emitted_outputs(action_text)
    documented = documented_outputs(contract_text)

    problems = []
    for name in sorted(declared | emitted | documented):
        present = {
            DECLARED_LABEL: name in declared,
            EMITTED_LABEL: name in emitted,
            DOCUMENTED_LABEL: name in documented,
        }
        have = [label for label, ok in present.items() if ok]
        missing = [label for label, ok in present.items() if not ok]
        if missing and have:
            problems.append(
                f"{name!r} is {', '.join(have)} but not "
                f"{', '.join(missing)}.")
    return problems


def main():
    use_utf8_stdout()
    if not (os.path.isfile(ACTION) and os.path.isfile(CONTRACT)):
        sys.exit("::error::run this from the repository root; "
                  f"{ACTION} or {CONTRACT} not found.")

    action_text = open(ACTION, encoding="utf-8").read()
    contract_text = open(CONTRACT, encoding="utf-8").read()

    real_problems = check(action_text, contract_text)
    for p in real_problems:
        print(f"::error file={ACTION}::Gate 20: {p}")
    if real_problems:
        print(f"Gate 20: {len(real_problems)} disagreement(s) against the "
              f"shipped files.")
        return 1
    print("Gate 20: action.yml, its shipped run: block, and "
          "tool-composition-action.md's Outputs table agree.")

    # --- self-test (FR-015, User Story 4 Acceptance 4) ---------------------
    self_test_failures = []

    # Fixture 1: a fourth outputs: entry, declared but never emitted.
    fixture1 = action_text.replace(
        "outputs:\n  allowed-tools:",
        "outputs:\n  gate-20-fixture-output:\n"
        "    description: Fixture only — declared, never emitted.\n"
        "    value: unused\n  allowed-tools:",
        1)
    if fixture1 == action_text:
        self_test_failures.append(
            "fixture 1 setup: 'outputs:\\n  allowed-tools:' was not found "
            "in action.yml — the self-test's insertion point has drifted.")
    else:
        problems = check(fixture1, contract_text)
        joined = " ".join(problems)
        if "gate-20-fixture-output" not in joined:
            self_test_failures.append(
                "fixture 1 (declared but never emitted) was not caught: "
                f"{problems!r}")
        elif "declared" not in joined or "not emitted" not in joined:
            self_test_failures.append(
                f"fixture 1 was caught but not reported as declared/not "
                f"emitted: {problems!r}")
        else:
            print("note: fixture 1 (declared, never emitted) caught: "
                  f"{problems}")

    # Fixture 2: shell-commands deleted from outputs: while the run: block
    # still emits it — this spec's own motivating defect.
    fixture2_doc = yaml.safe_load(action_text)
    del fixture2_doc["outputs"]["shell-commands"]
    fixture2 = yaml.safe_dump(fixture2_doc, sort_keys=False)
    problems = check(fixture2, contract_text)
    joined = " ".join(problems)
    if "shell-commands" not in joined:
        self_test_failures.append(
            f"fixture 2 (emitted but never declared) was not caught: "
            f"{problems!r}")
    elif "emitted" not in joined or "not declared" not in joined:
        self_test_failures.append(
            f"fixture 2 was caught but not reported as emitted/not "
            f"declared: {problems!r}")
    else:
        print("note: fixture 2 (emitted, never declared) caught: "
              f"{problems}")

    # Re-confirm the real files still pass, so a self-test fixture leaking
    # into the real check cannot read as green.
    if check(action_text, contract_text):
        self_test_failures.append(
            "the real files no longer pass after running the self-test "
            "fixtures — the fixtures mutated shared state.")

    if self_test_failures:
        for f in self_test_failures:
            print(f"::error file={ACTION}::Gate 20 self-test: {f}")
        print(f"Gate 20 self-test: {len(self_test_failures)} failure(s).")
        return 1

    print("Gate 20 self-test: both fixtures failed for the expected "
          "reason, and the real files pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
