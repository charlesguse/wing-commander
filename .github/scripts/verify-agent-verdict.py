#!/usr/bin/env python3
"""Gate 22 — the agent verdict composite classifies transcripts correctly.

WHY THIS EXISTS
----------------
wing-commander-agent-verdict (specs/037-agent-turn-budget-guard/) replaces
~8 hand-copied is_error/subtype checks (and ~11 call sites with no such check
at all) with one shared, transcript-only verdict. If this composite silently
mis-classifies a genuinely errored run as healthy, every call site that
trusts it inherits the same blind spot — the exact "one site fixed, the rest
exposed" shape this feature exists to close for turn-budget rejection, now
for the verdict logic itself.

WHAT IT RUNS
------------
The SHIPPED `run:` block, extracted from wing-commander-agent-verdict's YAML
and executed against synthetic transcripts, the same discipline
verify-metrics-turn-accounting.py (Gate 11) already established. The
extracted block calls the shared `.github/actions/_shared/count-turns.sh`
via $GITHUB_ACTION_PATH — this harness points GITHUB_ACTION_PATH at a
per-run temp directory containing a (possibly mutated) copy of that shared
script, so mutation testing never touches the real repo file.

It ends with mutation checks that reintroduce each defect and assert this
suite goes red. A detector that has never fired is indistinguishable from
one that cannot.
"""
import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-agent-verdict/action.yml"
STEP_NAME = "Classify agent run verdict"
SHARED_SCRIPT_PATH = ".github/actions/_shared/count-turns.sh"

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
    doc = yaml.safe_load(open(ACTION, encoding="utf-8"))
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == STEP_NAME:
            run = step.get("run")
            if run:
                return run
    print(f"::error file={ACTION}::gate 22 could not find the step named "
          f"{STEP_NAME!r}. If it was renamed, update this gate and the "
          f"action together — silently checking nothing is the failure "
          f"mode this gate exists to prevent.")
    sys.exit(1)


SCRIPT = shipped_script()
with open(SHARED_SCRIPT_PATH, encoding="utf-8") as _f:
    SHARED_SCRIPT = _f.read()


# --- transcript builders (mirrors Gate 11's) --------------------------------
def assistant(mid, parent=None, chunks=1):
    return [{"type": "assistant", "parent_tool_use_id": parent,
             "message": {"id": mid, "content": []}} for _ in range(chunks)]


def result(**kw):
    base = {"type": "result", "subtype": "success", "is_error": False,
            "num_turns": 0}
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
BASH = None


def run_case(name, records, intended_turns="40", raw=None, with_shared=True):
    tmp = tempfile.mkdtemp(prefix="wc-verdict-")
    if raw is not None:
        with open(os.path.join(tmp, TRANSCRIPT_NAME), "w",
                  encoding="utf-8") as f:
            f.write(raw)
    elif records is not None:
        with open(os.path.join(tmp, TRANSCRIPT_NAME), "w",
                  encoding="utf-8") as f:
            json.dump(records, f)

    # Same isolation approach as Gate 11: a sibling _shared/ next to a
    # stand-in action dir, so $GITHUB_ACTION_PATH/../_shared/count-turns.sh
    # resolves to THIS run's (possibly mutated) shared script, never the
    # real repo file.
    action_dir = os.path.join(tmp, "actiondir")
    shared_dir = os.path.join(tmp, "_shared")
    os.makedirs(action_dir, exist_ok=True)
    os.makedirs(shared_dir, exist_ok=True)
    # with_shared=False leaves _shared/ empty, standing in for a partial or
    # misplaced .wing-commander-pipeline/ self-checkout.
    if with_shared:
        with open(os.path.join(shared_dir, "count-turns.sh"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(SHARED_SCRIPT)

    rc, output, outputs, _summary = run_step(
        BASH, SCRIPT, tmp,
        {"TRANSCRIPT_PATH": TRANSCRIPT_NAME,
         "INTENDED_TURNS": intended_turns,
         "RUN_LABEL": "",
         "GITHUB_ACTION_PATH": action_dir},
        tmp)
    return rc, output, outputs


def expect(case, records, verdict, over_budget=None, intended_turns="40",
           raw=None, reason_contains=None):
    rc, output, outputs = run_case(case, records, intended_turns, raw=raw)
    if rc != 0:
        fail(case, f"the action exited {rc}, breaking its never-fail-the-"
                   f"step contract. output: {output.strip()[:300]}")
        return outputs
    got = outputs.get("verdict")
    if got != verdict:
        fail(case, f"expected verdict={verdict!r}, got {got!r} "
                   f"(reason={outputs.get('reason')!r})")
    if over_budget is not None and outputs.get("over-budget") != over_budget:
        fail(case, f"expected over-budget={over_budget!r}, got "
                   f"{outputs.get('over-budget')!r}")
    if reason_contains and reason_contains not in (outputs.get("reason") or ""):
        fail(case, f"expected reason to contain {reason_contains!r}, got "
                   f"{outputs.get('reason')!r}")
    return outputs


# --- the five FR-015 cases plus the contract's additional cases ------------
def case_healthy_but_would_be_rejected():
    """Mirrors run 31918153816: num_turns=47 far above max-turns=40, but
    counted turns (36) sit comfortably below the intended budget."""
    outputs = expect("healthy but would be post-hoc-rejected",
                     transcript(main=36, num_turns=47), "healthy",
                     over_budget="false", intended_turns="40")
    if outputs.get("counted-turns") != "36":
        fail("healthy but would be post-hoc-rejected",
             f"expected counted-turns=36, got {outputs.get('counted-turns')!r}")
    if outputs.get("reported-turns") != "47":
        fail("healthy but would be post-hoc-rejected",
             f"expected reported-turns=47, got {outputs.get('reported-turns')!r}")
    note("36 counted / 47 reported / 40 intended classifies healthy, "
         "over-budget=false — the exact #204 shape")


def case_genuinely_errored():
    expect("genuinely errored",
           transcript(main=10, is_error=True, subtype="success", num_turns=10),
           "failed", reason_contains="is_error=true")
    note("is_error=true (even with subtype=success) classifies failed")


def case_exhausted():
    expect("exhausted",
           transcript(main=40, subtype="error_max_turns", is_error=True, num_turns=41),
           "exhausted", reason_contains="ceiling")
    note("subtype=error_max_turns classifies exhausted, distinguishable "
         "from a generic failed")


def case_streamed_chunks_count_once():
    """Gate 11's own fixture shape (quickstart Scenario 7 / US2 Acceptance
    Scenario 3): 87 responses streamed as 3 records each is 87 counted
    turns, never 261 (records) or 198 (num_turns) — proving the shared
    count-turns.sh extraction behaves identically for this composite and
    for wing-commander-metrics-summary."""
    outputs = expect("streamed chunks count once", transcript(main=87, chunks=3, num_turns=198),
                     "healthy", intended_turns="200")
    if outputs.get("counted-turns") != "87":
        fail("streamed chunks count once",
             f"expected counted-turns=87, got {outputs.get('counted-turns')!r}")


def case_subagent_turns_reported_separately():
    """Gate 11's other fixture shape: 94 main + 86 subagent responses ->
    counted-turns=94, subagent-turns=86, never folded together."""
    outputs = expect("subagent turns reported separately", transcript(main=94, sub=86, num_turns=118),
                     "healthy", intended_turns="200")
    if outputs.get("counted-turns") != "94":
        fail("subagent turns reported separately",
             f"expected counted-turns=94, got {outputs.get('counted-turns')!r}")
    if outputs.get("subagent-turns") != "86":
        fail("subagent turns reported separately",
             f"expected subagent-turns=86, got {outputs.get('subagent-turns')!r}")


def case_unreadable_missing():
    expect("unreadable: missing file", None, "unclassifiable")


def case_unreadable_empty():
    rc, output, outputs = run_case("unreadable: empty file", None, raw="")
    if rc != 0:
        fail("unreadable: empty file", f"exited {rc}: {output.strip()[:200]}")
    if outputs.get("verdict") != "unclassifiable":
        fail("unreadable: empty file",
             f"expected verdict=unclassifiable, got {outputs.get('verdict')!r}")


def case_unreadable_invalid_json():
    expect("unreadable: invalid json", None, "unclassifiable",
           raw="{not json at all")


def case_no_result_record_at_all():
    expect("no terminal result record", transcript(main=5)[:-1], "failed",
           reason_contains="no terminal result record")


def case_over_budget_healthy():
    expect("over-budget but healthy",
           transcript(main=42, num_turns=60), "healthy",
           over_budget="true", intended_turns="40")


def case_under_budget_healthy():
    expect("under-budget and healthy",
           transcript(main=36, num_turns=47), "healthy",
           over_budget="false", intended_turns="40")


def case_bad_subtype():
    expect("subtype neither success nor error_max_turns",
           transcript(main=10, subtype="error_during_execution", num_turns=10),
           "failed", reason_contains="unexpected terminal subtype")


def case_only_the_last_result_record_is_authoritative():
    """Two result records in one transcript (a mid-run partial result,
    then the real terminal one) — the FIRST reads as a genuine error, the
    LAST as healthy. Reading anything but the last record would report
    'failed' here, which the mutation phase below reintroduces and expects
    this case to catch."""
    recs = assistant("msg_main_0") \
        + [{"type": "result", "subtype": "success", "is_error": True,
            "num_turns": 5}] \
        + assistant("msg_main_1") \
        + [{"type": "result", "subtype": "success", "is_error": False,
            "num_turns": 10}]
    expect("only the last result record is authoritative", recs, "healthy",
           intended_turns="40")


def case_never_fails():
    """Every fixture, including malformed ones, must exit 0."""
    for label, recs, raw in (("missing transcript", None, None),
                             ("no result record", transcript(main=5)[:-1], None),
                             ("empty array", [], None),
                             ("invalid json", None, "{not json at all")):
        rc, output, _outputs = run_case(label, recs, raw=raw)
        if rc != 0:
            fail(label, f"exited {rc}: {output.strip()[:200]}")
    note("missing / result-less / empty / unparseable transcripts still "
         "exit 0 (the never-fail-the-step contract)")


def case_shared_counter_absent():
    """_shared/count-turns.sh is not in the checkout at all.

    That script prints its three key=value lines unconditionally and never
    exits non-zero, so the only way its `eval` here binds nothing is the
    file being absent — a partial or misplaced .wing-commander-pipeline/
    self-checkout. The classify block runs under `set -u`, so an unbound
    $main_turns on the next line kills the step before $GITHUB_OUTPUT is
    ever written: no verdict at all, from the one action documented never
    to fail its own step. The verdict itself never depended on turn
    counting, so it must still be answered from the transcript; only the
    three turn fields go empty.
    """
    case = "shared count-turns.sh absent from the checkout"
    rc, output, outputs = run_case(case, transcript(main=36, num_turns=47),
                                   with_shared=False)
    if rc != 0:
        fail(case, f"the action exited {rc} with no _shared/count-turns.sh "
                   f"to read, breaking its never-fail-the-step contract. "
                   f"output: {output.strip()[:300]}")
        return
    if outputs.get("verdict") != "healthy":
        fail(case, f"expected the verdict to still be answered from the "
                   f"transcript alone (healthy), got "
                   f"{outputs.get('verdict')!r}")
    for key in ("counted-turns", "subagent-turns", "reported-turns"):
        if outputs.get(key) not in ("", None):
            fail(case, f"expected {key} to be empty when the counter is "
                       f"absent — never a fabricated zero — got "
                       f"{outputs.get(key)!r}")
    if outputs.get("over-budget") != "false":
        fail(case, f"expected over-budget=false with no counted turns to "
                   f"compare, got {outputs.get('over-budget')!r}")
    note("a missing _shared/count-turns.sh empties the three turn fields "
         "and still exits 0 with a verdict")


CASES = [
    case_healthy_but_would_be_rejected,
    case_genuinely_errored,
    case_exhausted,
    case_streamed_chunks_count_once,
    case_subagent_turns_reported_separately,
    case_unreadable_missing,
    case_unreadable_empty,
    case_unreadable_invalid_json,
    case_no_result_record_at_all,
    case_over_budget_healthy,
    case_under_budget_healthy,
    case_bad_subtype,
    case_only_the_last_result_record_is_authoritative,
    case_shared_counter_absent,
    case_never_fails,
]


# --- mutation checks ---------------------------------------------------------
MUTATIONS = [
    ("reads is_error/subtype from anywhere other than the last result record",
     "action",
     lambda s: s.replace(
         "map(select(.type==\"result\")) | last // empty",
         "map(select(.type==\"result\")) | first // empty")),
    ("collapses unclassifiable and failed into one case", "action",
     lambda s: s.replace('verdict="unclassifiable"', 'verdict="failed"')),
    ("stops seeding the three names count-turns.sh's eval defines, so an "
     "absent counter kills the step under set -u", "action",
     lambda s: s.replace('main_turns=""\nsub_turns=""\nreported=""\n', "", 1)),
    ("computes over-budget from reported-turns instead of counted-turns",
     "action",
     lambda s: s.replace('printf \'%s\' "$counted_turns" | grep -Eq \'^[0-9]+$\'',
                         'printf \'%s\' "$reported_turns" | grep -Eq \'^[0-9]+$\'')
                .replace('[ "$counted_turns" -ge "$INTENDED_TURNS" ]',
                        '[ "$reported_turns" -ge "$INTENDED_TURNS" ]')),
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
        print(f"Gate 22: {len(real)} failure(s) against the shipped action.")
        return 1

    global SCRIPT, SHARED_SCRIPT, MUTATING
    original_script = SCRIPT
    original_shared = SHARED_SCRIPT
    mutation_failures = 0
    MUTATING = True
    for label, target, mutate in MUTATIONS:
        original = original_script if target == "action" else original_shared
        source_file = ACTION if target == "action" else SHARED_SCRIPT_PATH
        mutated = mutate(original)
        if mutated == original:
            print(f"::error file={source_file}::gate 22's mutation {label!r} "
                  f"no longer changes the script — the code it keys on has "
                  f"been rewritten, so this mutation proves nothing. "
                  f"Re-point it at the current implementation.")
            mutation_failures += 1
            continue
        if target == "action":
            SCRIPT = mutated
        else:
            SHARED_SCRIPT = mutated
        caught = run_suite()
        SCRIPT = original_script
        SHARED_SCRIPT = original_shared
        if not caught:
            print(f"::error file={source_file}::gate 22 mutation {label!r} "
                  f"was NOT caught — the suite passed against a knowingly "
                  f"broken script, so its green verdict on the real one "
                  f"means nothing. Add a case that fails on this mutation.")
            mutation_failures += 1
        else:
            print(f"note: mutation caught ({label}): "
                  f"{len(caught)} case(s) failed as intended")

    MUTATING = False
    residual = run_suite()
    if residual:
        print(f"::error::gate 22 left the script mutated; {len(residual)} "
              f"failure(s) on the re-run.")
        mutation_failures += 1

    print(f"Gate 22: {len(CASES)} case(s) and {len(MUTATIONS)} mutation(s) "
          f"checked; {mutation_failures} failure(s).")
    return 1 if mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
