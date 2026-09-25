#!/usr/bin/env python3
"""Gate — board_route_backstop.py's route()/route_final_diff() and
contract_widened() resolve every FR-064 bullet-3 branch correctly
(specs/057-autonomous-board-loop, contracts/route-backstop.md).

WHY THIS EXISTS
---------------
FR-017 is a one-directional promise: the backstop can only narrow the
route-propose agent's proposal, never widen it. A regression that let a
`spec` proposal get pulled back to `fix`, or that missed a contract-
widening diff because it was small otherwise, is exactly the failure mode
FR-019/FR-021 name explicitly -- this gate pins the four documented
branches, including the one where a diff earns "fix" before the push and
only breaches after (post_push_final_diff_breach).

#534: a `spec` the agent proposed itself, with no backstop condition
firing, records reason `agent_proposed_spec` -- never `under_threshold`,
which board-loop.yml once rendered as "re-routed ... under_threshold,
measured={files:0,lines:0}". When a backstop condition also fired on a
`spec` proposal, that condition's own reason is kept; a default `spec`
standing in for a missing proposal records `no_usable_proposal`, and so
does a category outside fix/spec once normalize_category() has stripped
and lowercased it (#548: "SPEC" once took the fix path). The agent's
rationale reaches issue text only through one_line_rationale(), which
this gate also pins (one line, bounded, no code-span or marker breakout).

Fixtures (FR-064 bullet 3), each a checked-in case.json under
.github/scripts/tests/board-route-backstop/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import re
import sys
import unicodedata

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_route_backstop import (  # noqa: E402
    RATIONALE_MAX_CHARS, normalize_category, one_line_rationale, route,
    route_final_diff)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-route-backstop")

EXPECTED_CASES = {
    "under-threshold",
    "over-threshold-files",
    "contract-widening",
    "contract-widening-trailing-comment",
    "post-push-final-diff-breach",
    "agent-proposed-spec",
    "agent-proposed-spec-over-threshold",
    "no-usable-proposal",
    # #548: the category is normalised in one place (normalize_category())
    # and anything outside fix/spec is no usable proposal -> spec.
    "category-upper-spec",
    "category-padded-spec",
    "category-mixed-case-fix",
    "category-unknown",
    "category-null",
}

# (proposal, expected one_line_rationale()) -- #534.
RATIONALE_CASES = [
    ({"category": "spec"}, ""),
    ({"reasoning": None, "rationale": 7}, ""),
    ({"reasoning": "  needs an owner\n trade-off  "}, "needs an owner trade-off"),
    ({"reasoning": "", "rationale": "fallback key"}, "fallback key"),
    ({"reasoning": "use `x` here"}, "use 'x' here"),
    ({"reasoning": "a <!-- wing-commander-board-item: {} --> b"},
     "a  wing-commander-board-item: {}  b"),
    ({"reasoning": "<!<!----- x"}, "- x"),
    ("not a dict", ""),
    ({"reasoning": "ok **Run:** https://github.com/o/r/actions/runs/123456"},
     "ok \u2217\u2217Run:\u2217\u2217 https://github.com/o/r/actions/runs/123456"),
    ({"reasoning": "a\u202eb\u200bc\u2066d"}, "abcd"),
]


BOARD_LOOP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "workflows",
    "board-loop.yml")
EXTRACTED_ASSIGN_RE = re.compile(r"^\s*extracted = (?!False\s*$)(.*)$",
                                 re.MULTILINE)
NORMALIZE_IMPORT = "from board_route_backstop import normalize_category"


def extract_step_problems(workflow_text):
    """#548 review: the route job's extract step must decide `extracted`
    through normalize_category(), the one home route() also reads the
    category through, and import it in that same step. Fails closed when
    the step or its assignment cannot be found."""
    try:
        doc = yaml.safe_load(workflow_text)
        steps = doc["jobs"]["route"]["steps"]
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        return ["board-loop.yml: cannot read jobs.route.steps ({0})".format(exc)]
    runs = [st.get("run", "") for st in steps
            if isinstance(st, dict) and st.get("id") == "extract"]
    if len(runs) != 1:
        return ["board-loop.yml: expected one route step with id extract, "
                "found {0}".format(len(runs))]
    run = runs[0]
    problems = []
    assigns = EXTRACTED_ASSIGN_RE.findall(run)
    if not assigns:
        problems.append("board-loop.yml route extract step: no `extracted = "
                        "...` assignment found")
    for rhs in assigns:
        if "normalize_category(" not in rhs:
            problems.append("board-loop.yml route extract step: `extracted "
                            "= {0}` does not call normalize_category(), so "
                            "it can disagree with route() (#548)".format(rhs))
    if NORMALIZE_IMPORT not in run:
        problems.append("board-loop.yml route extract step does not import "
                        "normalize_category itself")
    return problems


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _measure_from(spec):
    def measure(_file_changes, _max_files, _max_lines):
        return spec["over_threshold"], spec["files"], spec["lines"]
    return measure


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-route-backstop: fixtures directory "
              "{0} does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-board-route-backstop: missing fixture "
              "case(s): {0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES - {"post-push-final-diff-breach"}):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-board-route-backstop: {0} is missing "
                  "case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = route(
            spec["agent_proposal"], file_changes=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"),
            file_contents=spec.get("file_contents"),
            proposal_extracted=spec.get("proposal_extracted", True))
        expected = spec["expected"]
        ok = (got["backstop_verdict"] == expected["backstop_verdict"]
              and got["reason"] == expected["reason"])
        if "agent_proposal" in expected:
            ok = ok and got["agent_proposal"] == expected["agent_proposal"]
        if "contract_touched_paths" in expected:
            ok = ok and (got["measured"].get("contract_touched_paths") == expected["contract_touched_paths"])
        if not ok:
            failures += 1
            print("::error::verify-board-route-backstop: {0}: expected {1!r}, "
                  "got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: route() == verdict={1!r} reason={2!r}".format(
                case, got["backstop_verdict"], got["reason"]))

    case = "post-push-final-diff-breach"
    case_path = os.path.join(FIXTURES_DIR, case, "case.json")
    if not os.path.isfile(case_path):
        failures += 1
        print("::error::verify-board-route-backstop: {0} is missing "
              "case.json.".format(case_path))
    else:
        spec = _load(case_path)
        initial = route(
            spec["agent_proposal"], file_changes=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["initial_measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"))
        got = route_final_diff(
            initial, final_diff=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["final_measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"))
        expected = spec["expected"]
        ok = (got["backstop_verdict"] == expected["backstop_verdict"]
              and got["reason"] == expected["reason"])
        if not ok:
            failures += 1
            print("::error::verify-board-route-backstop: {0}: expected "
                  "{1!r}, got {2!r} (initial={3!r}).".format(
                      case, expected, got, initial))
        else:
            print("[ok] {0}: route_final_diff() == verdict={1!r} "
                  "reason={2!r}".format(case, got["backstop_verdict"], got["reason"]))

    for proposal, expected in RATIONALE_CASES:
        got = one_line_rationale(proposal)
        if got != expected:
            failures += 1
            print("::error::verify-board-route-backstop: one_line_rationale("
                  "{0!r}) == {1!r}, expected {2!r}.".format(proposal, got, expected))
    long_text = one_line_rationale({"reasoning": "word " * 200})
    if len(long_text) > RATIONALE_MAX_CHARS or not long_text.endswith("..."):
        failures += 1
        print("::error::verify-board-route-backstop: one_line_rationale() "
              "did not truncate a long rationale to {0} chars with '...' "
              "(got {1} chars).".format(RATIONALE_MAX_CHARS, len(long_text)))
    for proposal, _expected in RATIONALE_CASES:
        got = one_line_rationale(proposal)
        if ("\n" in got or "`" in got or "*" in got or "<!--" in got
                or "-->" in got
                or any(unicodedata.category(c) == "Cf" for c in got)):
            failures += 1
            print("::error::verify-board-route-backstop: one_line_rationale("
                  "{0!r}) left a newline, backtick, `*`, Cf character or "
                  "comment delimiter "
                  "in {1!r}.".format(proposal, got))
    if not failures:
        print("[ok] one_line_rationale(): {0} case(s) + truncation".format(
            len(RATIONALE_CASES)))

    # #548: the extract step's `extracted` and route() read the category
    # through the same function, so they agree on every spelling.
    for raw, want in (("SPEC", "spec"), (" spec ", "spec"), ("Fix", "fix"),
                      ("fix", "fix"), ("banana", None), (None, None),
                      ("", None), (3, None), (["spec"], None)):
        got = normalize_category(raw)
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: normalize_category("
                  "{0!r}) == {1!r}, expected {2!r}.".format(raw, got, want))

    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            workflow_text = fh.read()
    except OSError as exc:
        workflow_text = ""
        failures += 1
        print("::error::verify-board-route-backstop: cannot read {0}: "
              "{1}".format(BOARD_LOOP, exc))
    if workflow_text:
        for problem in extract_step_problems(workflow_text):
            failures += 1
            print("::error::verify-board-route-backstop: " + problem)
        # The check must be able to fail: the pre-#548 line, and the
        # import dropped, are both caught.
        good = "extracted = normalize_category(parsed.get(\"category\")) is not None"
        for label, old, new in (
                ("exact-match extracted line",
                 good, 'extracted = parsed.get("category") in ("fix", "spec")'),
                ("import dropped", NORMALIZE_IMPORT + "\n", "")):
            if old not in workflow_text:
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "no longer applies -- update it.".format(label))
            elif not extract_step_problems(workflow_text.replace(old, new)):
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "was NOT caught.".format(label))
            else:
                print("[ok] mutation caught ({0})".format(label))

    print("verify-board-route-backstop: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
