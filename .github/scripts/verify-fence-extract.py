#!/usr/bin/env python3
"""Gate 94 — wc_fence_extract.py is the single fenced-JSON extractor for
board-loop.yml's three agent result parsers, and it behaves correctly.

WHY THIS EXISTS
----------------
SF1 (#499 code review, round 3): triage-propose and the reviewer's own
inline extractors used a non-greedy first-fence match
(`re.search(r"```TAG\s*\n(.*?)```", text, re.S)`) that can truncate on an
embedded ``` (a diff, a quoted code block) the same way route-propose's
did, fixed in an earlier round of this same review for route alone.
wc_fence_extract.py (.github/scripts/) is now the one place this logic
lives for all three sites; this gate (1) exercises it directly against
the shapes that broke the old per-site regexes (an embedded fence, CRLF
line endings, a missing/malformed block), and (2) confirms all three
extract steps in board-loop.yml actually import it, so a future edit
cannot quietly paste a fourth, drifting copy back in.

WHAT IT CHECKS
--------------
1. `extract_fenced_json()` behavior: a normal block; a block whose
   payload embeds a ``` fence (the SF1 regression, must still parse); CRLF
   line endings; no opening fence; no closing fence (a model that omits
   the trailing fence -- treated as "read to end of text", the existing
   fallback shape); and malformed JSON. Each asserts both the returned
   value and the failure reason text.
2. board-loop.yml's three extract steps ("Extract the triage-propose
   fenced proposal", "Extract the route-propose fenced proposal", and
   "Extract and validate the review findings") each import
   wc_fence_extract — a regression to an inline `re.search(...)` in any
   of the three fails this gate by name.
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_fence_extract import extract_fenced_json  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
EXTRACT_STEP_NAMES = (
    "Extract the triage-propose fenced proposal",
    "Extract the route-propose fenced proposal",
    "Extract and validate the review findings",
)
IMPORT_MARKER = "from wc_fence_extract import extract_fenced_json"


def check_extractor_behavior():
    """Return a list of failure strings; empty when every case passes."""
    failures = []

    def expect(label, text, tag, want_value, want_err_substr):
        value, err = extract_fenced_json(text, tag)
        if want_value is not None and value != want_value:
            failures.append(f"{label}: expected value {want_value!r}, got {value!r} (err={err!r})")
            return
        if want_value is None and value is not None:
            failures.append(f"{label}: expected no value, got {value!r}")
            return
        if want_err_substr is None and err is not None:
            failures.append(f"{label}: expected no error, got {err!r}")
            return
        if want_err_substr is not None and (err is None or want_err_substr not in err):
            failures.append(f"{label}: expected error containing {want_err_substr!r}, got {err!r}")

    expect(
        "normal block",
        '```mytag\n{"a": 1}\n```',
        "mytag", {"a": 1}, None)

    expect(
        "embedded fence in payload (SF1 regression)",
        '```mytag\n{"a": 1, "diff": "line1\\n```\\nline2\\n```\\n"}\n```',
        "mytag", {"a": 1, "diff": "line1\n```\nline2\n```\n"}, None)

    expect(
        "CRLF line endings",
        '```mytag\r\n{"a": 1}\r\n```\r\n',
        "mytag", {"a": 1}, None)

    expect(
        "no opening fence",
        'no fenced block here at all',
        "mytag", None, "no ```mytag``` block found")

    expect(
        "no closing fence (reads to end of text)",
        '```mytag\n{"a": 1}',
        "mytag", {"a": 1}, None)

    expect(
        "malformed JSON",
        '```mytag\nnot valid json\n```',
        "mytag", None, "did not parse as JSON")

    expect(
        "last opening fence wins over an earlier quoted one",
        'Earlier I quoted an example:\n```mytag\n{"decoy": true}\n```\n'
        'My real answer:\n```mytag\n{"real": true}\n```',
        "mytag", {"real": True}, None)

    return failures


def check_single_home():
    """Every extract step in board-loop.yml must import wc_fence_extract,
    not re-implement its own regex."""
    failures = []
    if not os.path.isfile(BOARD_LOOP):
        return [f"{BOARD_LOOP} not found"]
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    found_names = set()
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            name = step.get("name")
            if name not in EXTRACT_STEP_NAMES:
                continue
            found_names.add(name)
            run = str(step.get("run") or "")
            if IMPORT_MARKER not in run:
                failures.append(
                    f"step {name!r} does not import wc_fence_extract "
                    f"(missing {IMPORT_MARKER!r}) -- it may have "
                    f"regressed to an inline, drifting regex (SF1).")

    missing = set(EXTRACT_STEP_NAMES) - found_names
    if missing:
        failures.append(
            f"expected extract step(s) not found in {BOARD_LOOP}: "
            f"{sorted(missing)} -- this gate's own detection may have "
            f"drifted from the shipped step names.")
    return failures


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github"):
        sys.exit("::error::run this from the repository root; "
                  ".github not found.")

    failures = check_extractor_behavior() + check_single_home()
    for f in failures:
        print(f"::error::Gate 94: {f}")
    if failures:
        print(f"Gate 94: {len(failures)} failure(s).")
        return 1
    print("Gate 94: wc_fence_extract.py behaves correctly (including the "
          "SF1 embedded-fence and CRLF cases), and all three board-loop "
          "extract steps consume it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
