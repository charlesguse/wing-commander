#!/usr/bin/env python3
"""Gate 50 -- the three release-contract checks over every published stage.

Three checks that used to run only on a workflow_dispatch release, as
inline bash in release.yml's Gate 1b, now run on every pull request and
in run-local-gates.py as well -- and release.yml calls this same script,
so the release-time answer and the PR-time answer cannot drift (the
Gate 31 arrangement). Issue #308, the same shape as #291 (Gate 48).

WHY "STAY HERE" WAS FALSE
-------------------------
Gate 1b had two defects (#149): COVERAGE, a hardcoded brace expansion of
eight file names while eleven workflows declared workflow_call, so the
largest stage was the one file nothing examined; and TIMING, a
workflow_dispatch-only step that never saw the pull request introducing
a violation. Gate 31 (verify-stage-invariants.py) took the layer-
boundary half out of release.yml and fixed both. The three checks
below stayed behind, and their comment said they could, because their
stage set was now DERIVED from wc_published_stages.py -- which fixed
COVERAGE and left TIMING exactly where it was. A stage that hardcoded
`ref: main`, or lost its `--max-turns`, merged with every PR-time gate
green and turned red on the next release dispatch, weeks later, in the
hands of whoever cut the release rather than whoever made the change.
The derived list was necessary, not sufficient.

THE THREE CHECKS
----------------
Over every published stage (wc_published_stages.py, the derivation
Gates 7, 31 and 48 share -- a hardcoded list is what caused #149), read
line by line as `grep` read them. An empty derivation fails: these
checks examining nothing must never read as a pass.

  1. No literal `main` as a branch ref. The word may appear in prose, so
     only the wired forms are matched: `--base main`, `ref: main`,
     `origin/main` (not `origin/main_...`), `'main'`, `"main"`. A
     reusable stage must use the default-branch input or its derived
     value (spec edge case 3).

  2. The publisher's owner/repo string appears only as the pipeline-repo
     input default -- a line carrying `default: charlesguse/wing-commander`
     -- never as a hardcoded target (FR-005).

  3. Every agent step carries both `--model ` and `--max-turns `
     (constitution II). Count-based, per file: agent steps must not
     outnumber `--model ` lines or `--max-turns ` lines. Agent steps are
     counted on the `uses: anthropics/claude-code-action` wiring form,
     NOT a bare mention of the action, because a comment referring to
     the action's issue tracker (`anthropics/claude-code-action#1462`)
     would otherwise be counted as an agent step with no model.

The matching is deliberately textual and line-based, exactly as the
bash it replaces: `grep -c` counts lines, the trailing space on
`--model ` and `--max-turns ` is part of the pattern, and a comment
line is not stripped before matching. Changing any of that changes the
contract, and this script is the one place the contract lives.

USAGE
-----
    python3 .github/scripts/verify-release-contract.py
    python3 .github/scripts/verify-release-contract.py --self-test
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_published_stages import published_stages  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

# Check 1: the wired forms of a literal default-branch name. Applied per
# line, as `grep -nE` applies it: `[^_]` can never match a newline.
MAIN_REF_RE = re.compile(r"""(--base main|ref: main|origin/main[^_]|'main'|"main")""")

# Check 2: the publisher, and the one line shape it is allowed on.
PUBLISHER = "charlesguse/wing-commander"
PUBLISHER_ALLOWED = "default: charlesguse/wing-commander"

# Check 3: the wiring form of an agent step, and the two declarations
# every one of them must carry. Trailing spaces are part of the pattern.
AGENT_USES = "uses: anthropics/claude-code-action"
MODEL_FLAG = "--model "
TURNS_FLAG = "--max-turns "


def _lines(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def main_ref_errors(stages):
    """Check 1 -> [hit lines..., one ::error sentence] or []."""
    hits = []
    for f in stages:
        for n, line in enumerate(_lines(f), 1):
            if MAIN_REF_RE.search(line):
                hits.append(f"{f}:{n}:{line}")
    if not hits:
        return []
    return hits + [
        "::error::reusable stages must not hardcode the branch name main "
        "-- use the default-branch input or its derived value (spec edge "
        "case 3)."]


def publisher_errors(stages):
    """Check 2 -> [stray lines..., one ::error sentence] or []."""
    stray = []
    for f in stages:
        for n, line in enumerate(_lines(f), 1):
            if PUBLISHER in line and PUBLISHER_ALLOWED not in line:
                stray.append(f"{f}:{n}:{line}")
    if not stray:
        return []
    return stray + [
        "::error::the publisher's owner/repo may appear only as the "
        "pipeline-repo input default (FR-005)."]


def agent_flag_errors(stages):
    """Check 3 -> one ::error sentence per offending file, or []."""
    errors = []
    for f in stages:
        lines = _lines(f)
        agents = sum(AGENT_USES in l for l in lines)
        models = sum(MODEL_FLAG in l for l in lines)
        turns = sum(TURNS_FLAG in l for l in lines)
        if agents > models or agents > turns:
            errors.append(
                f"::error::{f}: {agents} agent step(s) but only {models} "
                f"--model / {turns} --max-turns declarations (constitution "
                f"II requires both on every agent step).")
    return errors


def contract_errors(stages):
    """All three checks, plus the empty-set guard, over openable paths.

    Returns the lines to print; a non-empty list is a failing gate. Hit
    lines precede their ::error sentence, as the grep output did.
    """
    if not stages:
        return ["::error::no workflow declares on.workflow_call -- these "
                "checks examined nothing, which must never read as a pass."]
    return (main_ref_errors(stages) + publisher_errors(stages)
            + agent_flag_errors(stages))


def run_gate():
    stages = published_stages()
    out = contract_errors(stages)
    for line in out:
        print(line)
    print(f"Gate 50: {len(stages)} published stage(s) checked.")
    return 1 if out else 0


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# A stage that exercises every ALLOWED form, so the clean pass below is a
# pass over the exemptions rather than over nothing: the pipeline-repo
# default, an issue-tracker mention of the action in a comment, the word
# main in prose, `origin/main_` with the underscore, and an agent step
# that declares both flags.
CLEAN_STAGE = (
    "# Tracks anthropics/claude-code-action#1462 -- not an agent step.\n"
    "# The default branch is usually main; never assume it here.\n"
    "on:\n"
    "  workflow_call:\n"
    "    inputs:\n"
    "      pipeline-repo:\n"
    "        type: string\n"
    "        default: charlesguse/wing-commander\n"
    "      default-branch:\n"
    "        type: string\n"
    "jobs:\n"
    "  a:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - run: git fetch origin origin/main_archive\n"
    "      - uses: anthropics/claude-code-action@v1\n"
    "        with:\n"
    "          claude_args: --model x --max-turns 5\n")

DISPATCH_ONLY = ("on: workflow_dispatch\njobs:\n  a:\n"
                 "    runs-on: ubuntu-latest\n    steps:\n"
                 "      - run: echo ok\n")


def self_test():
    """Each check fails on the one mutation it exists to catch, passes on
    a fixture that carries every allowed form, and an empty stage set is
    a failure rather than a clean pass."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    def fixture(td, mutate=None):
        """Two published stages plus a dispatch-only file that must be
        ignored; `mutate` rewrites the second stage's text."""
        wf = os.path.join(td, ".github", "workflows")
        _write(os.path.join(wf, "s1.yml"), CLEAN_STAGE)
        text = CLEAN_STAGE if mutate is None else mutate(CLEAN_STAGE)
        _write(os.path.join(wf, "s2.yml"), text)
        _write(os.path.join(wf, "dispatch.yml"),
               DISPATCH_ONLY.replace("echo ok", "gh pr create --base main"))
        return published_stages(td)

    with tempfile.TemporaryDirectory() as td:
        stages = fixture(td)
        check("fixture derives two published stages (the dispatch-only "
              "file, which hardcodes main, is not one)",
              len(stages) == 2 and all(s.endswith((".github/workflows/s1.yml",
                                                   ".github/workflows/s2.yml"))
                                       for s in stages), f"got {stages!r}")
        out = contract_errors(stages)
        check("the clean fixture passes all three checks (every allowed "
              "form present)", not out, f"got {out!r}")
        check("the clean fixture really carries the allowed forms",
              PUBLISHER_ALLOWED in CLEAN_STAGE
              and "anthropics/claude-code-action#1462" in CLEAN_STAGE
              and "origin/main_" in CLEAN_STAGE and " main" in CLEAN_STAGE)

    with tempfile.TemporaryDirectory() as td:
        stages = fixture(td, lambda t: t.replace(
            "      - run: git fetch origin origin/main_archive\n",
            "      - run: git fetch origin origin/main_archive\n"
            "      - uses: actions/checkout@v5\n"
            "        with:\n"
            "          ref: main\n"))
        out = contract_errors(stages)
        check("check 1: a literal `ref: main` fails, naming the line",
              any("spec edge case 3" in l for l in out)
              and any(l.endswith("s2.yml:18:          ref: main")
                      for l in out)
              and not any("FR-005" in l or "constitution II" in l
                          for l in out),
              f"got {out!r}")

    with tempfile.TemporaryDirectory() as td:
        stages = fixture(td, lambda t: t.replace(
            "      - run: git fetch origin origin/main_archive\n",
            "      - run: gh repo view charlesguse/wing-commander\n"))
        out = contract_errors(stages)
        check("check 2: the publisher outside the input default fails, "
              "naming the line",
              any("FR-005" in l for l in out)
              and any("s2.yml:15:" in l and "gh repo view" in l for l in out)
              and not any("spec edge case 3" in l or "constitution II" in l
                          for l in out),
              f"got {out!r}")

    with tempfile.TemporaryDirectory() as td:
        stages = fixture(td, lambda t: t.replace(
            "--model x --max-turns 5", "--model x"))
        out = contract_errors(stages)
        check("check 3: an agent step without --max-turns fails, with the "
              "counts",
              len(out) == 1 and "s2.yml: 1 agent step(s) but only 1 --model "
              "/ 0 --max-turns declarations (constitution II" in out[0],
              f"got {out!r}")

    with tempfile.TemporaryDirectory() as td:
        stages = fixture(td, lambda t: t.replace(
            "      - uses: anthropics/claude-code-action@v1\n"
            "        with:\n"
            "          claude_args: --model x --max-turns 5\n",
            "      # anthropics/claude-code-action#99 is the only mention.\n"))
        out = contract_errors(stages)
        check("check 3: a comment mentioning the action is not an agent "
              "step (anchored on the uses: wiring form)",
              not out, f"got {out!r}")

    with tempfile.TemporaryDirectory() as td:
        _write(os.path.join(td, ".github", "workflows", "dispatch.yml"),
               DISPATCH_ONLY)
        stages = published_stages(td)
        out = contract_errors(stages)
        check("an empty stage set is a failure, not a clean pass",
              stages == [] and len(out) == 1 and "examined nothing" in out[0],
              f"got {out!r}")

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    # Hit lines are quoted verbatim; a cp1252 console must not turn a
    # non-ASCII one into a traceback in place of the verdict.
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or "
                 f"nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
