#!/usr/bin/env python3
"""Gate 101 -- no comment may claim a `shell: bash` step runs without errexit.

WHY THIS EXISTS
---------------
GitHub Actions runs a `shell: bash` step as
`bash --noprofile --norc -eo pipefail {0}`. Errexit is therefore active
from the OUTER invocation, before the script's first line ever executes.
This repository's universal opening line, `set -uo pipefail`, does not
change that: `set` only touches the options it is explicitly passed, so
`-e`'s existing value carries through unchanged. A failing command inside
a plain `var="$(...)"` assignment therefore still aborts the step
immediately -- it does not fall through with an empty variable.

specs/088-stop-check-closed-read (issue #623, originating from #465): five
shipped comments asserted the opposite -- that a `shell: bash` step "runs
without -e" or that `set -uo pipefail` "clears" it -- and every review pass
on #465, including the reviewer who later caught the real defect, assumed
the wrong semantics. This is the canonical statement of the correct fact;
every corrected site points here with a `-- see
verify-errexit-claim-comments.py.` pointer rather than restating the
mechanism (CLAUDE.md "Shared logic has exactly one home").

WHAT COUNTS AS A VIOLATION
---------------------------
A comment block (this repo's own comment_blocks()/_joined(), imported from
verify-comment-canonical-pointers.py rather than reimplemented) whose
joined text matches one of five phrase patterns for "this step runs
without errexit" / "clears -e", UNLESS:

  1. the match falls within three words of a negation term (`not`,
     `never`, an `n't`-suffixed word, `doesn't`, `does`, `cannot`) --
     covers "does not clear `-e`", "never runs without errexit"; or
  2. the match falls inside a `"..."` / `'...'` / `` `...` `` quoted span
     longer than the flag token alone -- covers a comment that quotes the
     wrong claim in order to correct it.

SCOPE
-----
`.github/workflows/*.yml` and `.github/actions/**/action.yml` (both
directly-nested composites and `_shared/`-nested ones -- the same
two-glob shape `verify-actions-layer-invariants.py` already uses).
Deliberately wider than Gate 24's `.github/workflows/*.yml`-only glob
(see verify-gate-24.py's own docstring): the FR-001 violation this
feature fixes lived in `wing-commander-board-stop-check/action.yml`, an
action file, so a gate that could not see action files could not have
caught it.

Usage:
    python3 .github/scripts/verify-errexit-claim-comments.py
    python3 .github/scripts/verify-errexit-claim-comments.py --self-test
"""
import glob
import importlib.util
import os
import re
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS_GLOB = os.path.join(".github", "workflows", "*.yml")
ACTIONS_BASE = os.path.join(".github", "actions")


def _load_canonical_pointers():
    """verify-comment-canonical-pointers.py's comment_blocks()/_joined() --
    a hyphenated filename, so this loads it by path rather than `import`."""
    path = os.path.join(SCRIPTS_DIR, "verify-comment-canonical-pointers.py")
    spec = importlib.util.spec_from_file_location("_canonical_pointers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_cp = _load_canonical_pointers()
comment_blocks = _cp.comment_blocks
_joined = _cp._joined


# --- Phrase patterns (research.md D6) ---------------------------------------

PHRASE_PATTERNS = [
    # `(?!\w)` rather than a trailing `\b` after a closing backtick: a
    # backtick is itself a non-word character, so `` `-e`\b `` only matches
    # when the NEXT character happens to be a word character -- never true
    # for real prose, where `-e` is followed by whitespace or punctuation.
    re.compile(r"\brun(?:s)?\s+without\s+(?:`?-e`?(?!\w)|errexit\b)", re.IGNORECASE),
    re.compile(r"\bwithout\s+errexit\b", re.IGNORECASE),
    re.compile(r"\bwith\s+no\s+`-e`(?!\w)", re.IGNORECASE),
    re.compile(r"\bno\s+`-e`(?!\w)", re.IGNORECASE),
    re.compile(r"\bclears?\s+`-e`(?!\w)", re.IGNORECASE),
]

NEGATION_WORDS = {"not", "never", "doesn't", "does", "cannot"}
_WORD_RE = re.compile(r"[A-Za-z']+")
QUOTE_SPAN_RE = re.compile(r'"[^"]*"|\'[^\']*\'|`[^`]*`')


def _is_negated(text, start):
    """One of the three words immediately before `start` is a negation
    term -- covers "does not clear `-e`", "never runs without errexit"."""
    before = text[:start]
    words = _WORD_RE.findall(before)[-3:]
    return any(w.lower() in NEGATION_WORDS or w.lower().endswith("n't") for w in words)


def _is_quoted(text, start, end):
    """The match sits inside a quoted span strictly longer than the flag
    token alone -- a comment quoting the wrong claim to correct it."""
    for m in QUOTE_SPAN_RE.finditer(text):
        if m.start() <= start and end <= m.end() and len(m.group(0)) > len("`-e`"):
            return True
    return False


def find_violations(text):
    """-> [(start, end), ...] surviving (start, end) spans in `text`."""
    hits = []
    for pattern in PHRASE_PATTERNS:
        for m in pattern.finditer(text):
            if _is_negated(text, m.start()) or _is_quoted(text, m.start(), m.end()):
                continue
            hits.append((m.start(), m.end()))
    return hits


# --- File discovery -----------------------------------------------------

def action_manifest_paths(root="."):
    base = os.path.join(root, ACTIONS_BASE)
    out = []
    for pattern in ("action.yml", "action.yaml"):
        out.extend(glob.glob(os.path.join(base, "*", pattern)))
        out.extend(glob.glob(os.path.join(base, "**", pattern), recursive=True))
    return sorted(set(out))


def scanned_paths(root="."):
    workflows = sorted(glob.glob(os.path.join(root, WORKFLOWS_GLOB)))
    return workflows + action_manifest_paths(root)


def check_file(path):
    """-> [(path, line), ...] one entry per surviving violation in `path`."""
    out = []
    for block in comment_blocks(path):
        if find_violations(_joined(block)):
            out.append((path, block["start"]))
    return out


def run_gate(root="."):
    paths = scanned_paths(root)
    violations = []
    for path in paths:
        violations.extend(check_file(path))
    for path, line in violations:
        print(f"::error file={path}::verify-errexit-claim-comments: {path}:{line}: "
              f"comment asserts a `shell: bash` step runs without errexit, or that "
              f"`set -uo pipefail` clears `-e` -- both are false (see this script's "
              f"own module docstring).")
    print(f"verify-errexit-claim-comments: {len(paths)} file(s) scanned, "
          f"{len(violations)} violation(s).")
    return 1 if violations else 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------

def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


# (name, real corrected file, needle in its CURRENT (corrected) joined
# comment text, the pre-fix false phrase it mutates that needle back to)
MUTATION_SITES = (
    ("wing-commander-board-stop-check/action.yml (T006)",
     os.path.join(ACTIONS_BASE, "wing-commander-board-stop-check", "action.yml"),
     "does not clear `-e`", "clears `-e`"),
    ("board-loop.yml (T014)",
     os.path.join(".github", "workflows", "board-loop.yml"),
     "errexit is already active on this `shell: bash` step",
     "this step runs without -e"),
    ("metrics-persist.yml (T015)",
     os.path.join(".github", "workflows", "metrics-persist.yml"),
     "Errexit is already active on this `shell: bash`",
     "under `set -uo pipefail` with no `-e`"),
    ("implement.yml (T016)",
     os.path.join(".github", "workflows", "implement.yml"),
     "Errexit is already active on this `shell: bash` step",
     "No `-e`: an unreadable file degrades to empty fields, the same as a missing one"),
    ("lint-workflows.yml (T017)",
     os.path.join(".github", "workflows", "lint-workflows.yml"),
     '"set -uo pipefail with no -e"', "set -uo pipefail with no `-e`"),
)


def self_test(root="."):
    """Synthetic fixtures (built fresh in a tempdir, not checked-in files --
    the subject is the LIVE tree's comments, per
    verify-comment-canonical-pointers.py's own rationale for the same
    choice) plus mutation coverage over this feature's own five shipped
    corrections."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        wf = os.path.join(td, ".github", "workflows")

        # 1. Correct, canonical (negated) phrasing produces no violation.
        _write(os.path.join(wf, "correct.yml"), (
            "on: push\njobs:\n  a:\n    steps:\n"
            "      # Errexit is already active on this `shell: bash` step;\n"
            "      # `set -uo pipefail` does not clear `-e` -- see\n"
            "      # verify-errexit-claim-comments.py.\n"
            "      - run: echo ok\n"))
        v = check_file(os.path.join(wf, "correct.yml"))
        check("canonical negated phrasing produces no violation", not v, f"got {v!r}")

        # 2. The false claim, quoted (longer than the flag alone) to
        # correct it, produces no violation.
        _write(os.path.join(wf, "quoted-correction.yml"), (
            "on: push\njobs:\n  a:\n    steps:\n"
            '      # Previously this said "runs without -e" -- wrong;\n'
            "      # errexit is already active.\n"
            "      - run: echo ok\n"))
        v = check_file(os.path.join(wf, "quoted-correction.yml"))
        check("false claim quoted to correct it produces no violation", not v, f"got {v!r}")

        # 3. The negated true form ("does not clear -e") produces no
        # violation.
        _write(os.path.join(wf, "negated-true.yml"), (
            "on: push\njobs:\n  a:\n    steps:\n"
            "      # `set -uo pipefail` does not clear `-e`.\n"
            "      - run: echo ok\n"))
        v = check_file(os.path.join(wf, "negated-true.yml"))
        check("negated true form produces no violation", not v, f"got {v!r}")

        # 4. Each of the five bare, un-negated phrase patterns, introduced
        # fresh, is caught, naming the right file and line.
        bare_cases = (
            ("bare-1.yml", "      # This step runs without -e, so a failure falls through.\n"),
            ("bare-2.yml", "      # This step runs without errexit if the read fails.\n"),
            ("bare-3.yml", "      # Under `set -uo pipefail` with no `-e` this silently\n      # continues.\n"),
            ("bare-4.yml", "      # No `-e`: an unreadable file degrades to empty fields.\n"),
            ("bare-5.yml", "      # `set -uo pipefail` clears `-e` here.\n"),
        )
        for fname, comment in bare_cases:
            path = os.path.join(wf, fname)
            _write(path, "on: push\njobs:\n  a:\n    steps:\n" + comment + "      - run: echo bad\n")
            v = check_file(path)
            check(f"bare pattern caught: {fname}",
                  v == [(path, 5)], f"got {v!r}")

        # 5. Mutation coverage: the real, shipped corrected text of each of
        # the five sites this feature fixes, mutated back to its pre-fix
        # false claim, must be caught.
        for name, rel_path, needle, false_phrase in MUTATION_SITES:
            path = os.path.join(root, rel_path)
            found = False
            for block in comment_blocks(path):
                joined = _joined(block)
                if needle in joined:
                    found = True
                    mutated = joined.replace(needle, false_phrase)
                    hits = find_violations(mutated)
                    check(f"mutation caught: {name}", bool(hits),
                          f"mutated text: {mutated!r}")
                    clean = find_violations(joined)
                    check(f"shipped corrected text has no violation: {name}",
                          not clean, f"got {clean!r}")
                    break
            if not found:
                failures += 1
                print(f"FAIL mutation site not found: {name}: {path!r} has no "
                      f"comment block containing {needle!r} -- has the shipped "
                      f"text drifted from what this self-test expects?")

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
