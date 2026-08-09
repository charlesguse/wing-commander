#!/usr/bin/env python3
"""Gate 11 — the metrics summary counts the turns the budget actually caps.

WHY THIS EXISTS
---------------
`wing-commander-metrics-summary` renders "turns used / budgeted" into every
agent step's job summary, and those numbers are what turn budgets get tuned
from. It shipped reading `.num_turns` off the result record, which is NOT the
counter `--max-turns` enforces:

  * `--max-turns` cuts a run off after N distinct MAIN-LOOP assistant API
    responses. Every genuinely exhausted run in this repository's history
    stopped at exactly 100 of those under a 100 cap — 13 of 13.
  * `.num_turns` is a larger, differently-defined total. Against the same
    runs it read 1.0x-2.3x higher, always upward.

The visible damage: the 2026-08-06 implement cycle rendered "198 / 100 turns
(198%)" and a budget warning for a run that used 87 of 100 and was never at
risk. Nineteen of 47 implement runs carried a warning; 13 had actually
exhausted the budget. A ratio that is wrong in the alarming direction trains
you to ignore it, and it is the only instrument pointed at the one knob this
pipeline tunes by hand.

Two distinct traps this asserts against, because fixing one and not the
other reintroduces the same wrong number:

  1. Counting assistant RECORDS instead of distinct `.message.id`. One
     response streams as several records (text chunk, then tool_use chunk),
     so records inflate the count ~1.6x.
  2. Counting subagent responses. Task-tool subagents are inlined into the
     same transcript but do not spend the parent's budget — a 2026-07-24
     retry ran 180 distinct assistant responses under a 100 cap without
     tripping it, because 86 belonged to subagents.

WHAT IT RUNS
------------
The SHIPPED `run:` block, extracted from the composite action's YAML and
executed against synthetic transcripts. There is no copied logic here to
drift out of sync — the same discipline as gates 5-9, and gate 5 exists
precisely because a hand-copied fixture kept asserting against a filter that
no longer shipped.

It ends with mutation checks that reintroduce each defect and assert this
suite goes red. A detector that has never fired is indistinguishable from
one that cannot.
"""
import json
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-metrics-summary/action.yml"
STEP_NAME = "Render agent run metrics summary"

failures = []
MUTATING = False


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    # Only a failure against the SHIPPED action is an annotation. The
    # mutation phase deliberately breaks the script and expects failures;
    # annotating those would decorate a passing gate with red ::error lines
    # describing defects that are not in the tree.
    prefix = "note: (expected, mutation phase) " if MUTATING else \
        f"::error file={ACTION}::"
    print(f"{prefix}{case}: {msg}")


def note(msg):
    print(f"note: {msg}")


def shipped_script():
    """The action's own run: block, or a hard failure naming what moved."""
    doc = yaml.safe_load(open(ACTION, encoding="utf-8"))
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == STEP_NAME:
            run = step.get("run")
            if run:
                return run
    print(f"::error file={ACTION}::gate 11 could not find the step named "
          f"{STEP_NAME!r}. If it was renamed, update this gate and the action "
          f"together — silently checking nothing is the failure mode this "
          f"gate exists to prevent.")
    sys.exit(1)


SCRIPT = shipped_script()


# --- transcript builders ---------------------------------------------------
def assistant(mid, parent=None, chunks=1):
    """One assistant API response, streamed as `chunks` records sharing an id.

    Real transcripts split a single response across records; a counter that
    reads records rather than ids reports this as `chunks` turns.
    """
    return [{"type": "assistant", "parent_tool_use_id": parent,
             "message": {"id": mid, "content": []}} for _ in range(chunks)]


def result(**kw):
    base = {"type": "result", "subtype": "success", "num_turns": 0,
            "duration_ms": 60000, "total_cost_usd": 1.5,
            "usage": {"input_tokens": 10, "output_tokens": 20}}
    base.update(kw)
    return [base]


def transcript(main=0, sub=0, chunks=1, **result_kw):
    recs = []
    for i in range(main):
        recs += assistant(f"msg_main_{i}", None, chunks)
    for i in range(sub):
        recs += assistant(f"msg_sub_{i}", "toolu_parent", chunks)
    return recs + result(**result_kw)


TRANSCRIPT_NAME = "claude-execution-output.json"
BASH = None          # resolved once in main()


def run_case(name, records, max_turns="100", warn_fraction=None, raw=None):
    """Execute the shipped script over one transcript; return (rc, summary).

    run_step() is the shared harness gates 8 and 9 use: it hands the block
    over as a file under `bash -e` exactly as the runner does, owns
    $GITHUB_STEP_SUMMARY, and decodes as UTF-8 (this action's output carries
    emoji). Reusing it is also why this gate does not need its own Windows
    workarounds — resolve_bash() rejects a bash that would not inherit the
    environment these inputs arrive through.
    """
    tmp = tempfile.mkdtemp(prefix="wc-metrics-")
    try:
        if raw is not None:
            with open(os.path.join(tmp, TRANSCRIPT_NAME), "w",
                      encoding="utf-8") as f:
                f.write(raw)
        elif records is not None:
            with open(os.path.join(tmp, TRANSCRIPT_NAME), "w",
                      encoding="utf-8") as f:
                json.dump(records, f)
        rc, output, _outputs, summary = run_step(
            BASH, SCRIPT, tmp,
            {"TRANSCRIPT_PATH": TRANSCRIPT_NAME,
             "MODEL": "claude-sonnet-5",
             "MAX_TURNS": max_turns,
             "RUN_LABEL": "cycle",
             "WARN_FRACTION": warn_fraction or "0.8"},
            tmp)
        return rc, output, summary
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expect(case, records, want, unwanted=(), max_turns="100", exit_zero=True):
    rc, output, summary = run_case(case, records, max_turns)
    if exit_zero and rc != 0:
        fail(case, f"the action exited {rc}, breaking its never-fail-the-step "
                   f"contract. output: {output.strip()[:300]}")
        return summary
    for needle in want:
        if needle not in summary:
            fail(case, f"expected {needle!r} in the rendered summary, got:\n"
                       f"{summary.strip()[:400]}")
    for needle in unwanted:
        if needle in summary:
            fail(case, f"did NOT expect {needle!r} in the rendered summary, "
                       f"got:\n{summary.strip()[:400]}")
    return summary


# --- the cases -------------------------------------------------------------
def case_streamed_chunks_are_one_turn():
    """87 responses streamed as 3 records each is 87 turns, not 261.

    This is the 2026-08-06 implement cycle exactly: it rendered "198 / 100
    (198%)" and a budget warning. 87/100 is genuinely above the 0.8 warning
    threshold, so a warning still belongs here — but it must quote 87, and
    the 198 must appear nowhere.
    """
    expect("streamed chunks count once",
           transcript(main=87, chunks=3, num_turns=198),
           want=["| 87 / 100 |", "used 87/100 turns (87%)"],
           unwanted=["261", "198"])
    note("87 responses x3 stream records under a 100 cap render 87/100 and "
         "warn at 87%, with the run's own num_turns=198 appearing nowhere "
         "(the exact 2026-08-06 implement cycle)")


def case_subagent_turns_excluded():
    """The 2026-07-24 retry shape: 94 main + 86 subagent under a 100 cap."""
    summary = expect("subagent turns stay out of the ratio",
                     transcript(main=94, sub=86, num_turns=118),
                     want=["| 94 / 100 |", "Subagent turns**: 86"],
                     unwanted=["180 / 100"])
    if "Turn budget warning" not in summary:
        fail("subagent turns stay out of the ratio",
             "94/100 is 94%, above the 0.8 threshold — the warning should "
             "still fire on the MAIN-loop count")
    note("94 main + 86 subagent responses render 94/100 with the subagents "
         "reported separately, not folded into the budget ratio")


def case_exhausted_is_called_out():
    expect("exhaustion is stated, not inferred",
           transcript(main=100, subtype="error_max_turns", num_turns=101),
           want=["Turn budget exhausted", "100-turn cap", "| 100 / 100 |"])
    note("an error_max_turns run says the budget ran out in words, rather "
         "than leaving a reader to infer it from a ratio")


def case_warning_boundary():
    """FR-004's strict boundary, now measured on the counted total."""
    expect("at the threshold the warning fires",
           transcript(main=80, num_turns=140),
           want=["Turn budget warning", "(80%)"])
    expect("below the threshold it does not",
           transcript(main=79, num_turns=140),
           unwanted=["Turn budget warning"], want=["| 79 / 100 |"])
    note("the 0.8 boundary is strict and is evaluated against counted "
         "main-loop turns, not against num_turns")


def case_no_budget_no_ratio():
    """FR-005: never fabricate a budget."""
    rc, _output, summary = run_case("no budget",
                                    transcript(main=40, num_turns=70),
                                    max_turns="")
    if rc != 0:
        fail("no budget", f"exited {rc}")
    if "| 40 |" not in summary:
        fail("no budget", f"expected a bare counted turn total, got:\n"
                          f"{summary.strip()[:400]}")
    if "/ " in summary.split("Cost")[-1] or "warning" in summary.lower():
        fail("no budget", "rendered a ratio or warning with no budget given")
    note("with max-turns absent the counted total renders alone — no "
         "invented denominator, no warning")


def case_uncountable_falls_back_labelled():
    """A transcript with no assistant ids must not silently borrow num_turns
    as if it were comparable to the budget."""
    recs = [{"type": "assistant", "parent_tool_use_id": None, "message": {}}]
    recs += result(num_turns=42)
    expect("uncountable transcript degrades honestly", recs,
           want=["42 (reported, not comparable to budget)"],
           unwanted=["42 / 100", "Turn budget warning"])
    note("when main-loop turns cannot be counted the fallback is labelled "
         "and the ratio suppressed, rather than reviving the old bug")


def case_never_fails():
    """FR-009, unchanged by this rework and worth re-proving here.

    The new counting runs BEFORE the availability verdict and on the whole
    transcript rather than one record, so it is a fresh way for this action
    to die on malformed input — exactly the contract FR-009 protects.
    """
    for label, recs, raw in (("missing transcript", None, None),
                             ("no result record", transcript(main=5)[:-1], None),
                             ("empty array", [], None),
                             ("invalid json", None, "{not json at all")):
        rc, output, summary = run_case(label, recs, raw=raw)
        if rc != 0:
            fail(label, f"exited {rc}: {output.strip()[:200]}")
        if "Agent run metrics" not in summary:
            fail(label, "rendered no heading at all")
    note("missing / result-less / empty / unparseable transcripts still exit "
         "0 with a heading (the never-fail-the-step contract)")


CASES = [
    case_streamed_chunks_are_one_turn,
    case_subagent_turns_excluded,
    case_exhausted_is_called_out,
    case_warning_boundary,
    case_no_budget_no_ratio,
    case_uncountable_falls_back_labelled,
    case_never_fails,
]


# --- mutation checks -------------------------------------------------------
# Each mutation reintroduces a real defect into the shipped script and
# asserts this suite catches it. Without these, a rewrite that quietly stops
# counting anything would leave every case above passing on a constant.
MUTATIONS = [
    ("reads .num_turns for the ratio again",
     lambda s: s.replace('turns_used="$main_turns"',
                         'turns_used="$reported_turns"')),
    ("counts assistant records instead of distinct message ids",
     lambda s: s.replace("| unique | length", "| length")),
    ("counts subagent turns against the parent's budget",
     lambda s: s.replace('and (.parent_tool_use_id // null) == null)', ')')),
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
        print(f"Gate 11: {len(real)} failure(s) against the shipped action.")
        return 1

    global SCRIPT, MUTATING
    original = SCRIPT
    mutation_failures = 0
    MUTATING = True
    for label, mutate in MUTATIONS:
        mutated = mutate(original)
        if mutated == original:
            print(f"::error file={ACTION}::gate 11's mutation {label!r} no "
                  f"longer changes the script — the code it keys on has been "
                  f"rewritten, so this mutation proves nothing. Re-point it "
                  f"at the current implementation.")
            mutation_failures += 1
            continue
        SCRIPT = mutated
        caught = run_suite()
        SCRIPT = original
        if not caught:
            print(f"::error file={ACTION}::gate 11 mutation {label!r} was NOT "
                  f"caught — the suite passed against a knowingly broken "
                  f"action, so its green verdict on the real one means "
                  f"nothing. Add a case that fails on this mutation.")
            mutation_failures += 1
        else:
            print(f"note: mutation caught ({label}): "
                  f"{len(caught)} case(s) failed as intended")

    # Re-run clean so a mutation left behind cannot read as a pass.
    MUTATING = False
    residual = run_suite()
    if residual:
        print(f"::error::gate 11 left the script mutated; {len(residual)} "
              f"failure(s) on the re-run.")
        mutation_failures += 1

    print(f"Gate 11: {len(CASES)} case(s) and {len(MUTATIONS)} mutation(s) "
          f"checked; {mutation_failures} failure(s).")
    return 1 if mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
