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

The counting itself now lives in the shared `.github/actions/_shared/
count-turns.sh` script the shipped block calls via
`$GITHUB_ACTION_PATH/../_shared/count-turns.sh`
(specs/037-agent-turn-budget-guard/research.md R5). Each case reads that
real file's current contents and lays them out beside a stand-in action
directory inside the case's own temp tree, pointing GITHUB_ACTION_PATH
there. The bytes under test are always the shipped script's — but staging
them per case is what lets the mutation checks below swap in a defective
copy without touching the checkout on disk.

It ends with mutation checks that reintroduce each defect and assert this
suite goes red. A detector that has never fired is indistinguishable from
one that cannot.
"""
import json
import os
import re
import shutil
import subprocess
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

SHARED_SCRIPT_PATH = ".github/actions/_shared/count-turns.sh"
with open(SHARED_SCRIPT_PATH, encoding="utf-8") as _f:
    SHARED_SCRIPT = _f.read()


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


def run_case(name, records, max_turns="100", warn_fraction=None, raw=None,
             ceiling="", counter=None, with_outputs=False):
    """Execute the shipped script over one transcript; return (rc, summary).

    with_outputs=True also returns the parsed $GITHUB_OUTPUT (the metrics
    record rides in record-json). counter= stages a stand-in count-turns.sh
    instead of the shipped one.

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

        # The shipped block resolves the shared counting script as
        # "$GITHUB_ACTION_PATH/../_shared/count-turns.sh" — lay out a
        # sibling "_shared/" next to a stand-in action dir so that
        # resolution finds THIS run's (possibly mutated) SHARED_SCRIPT,
        # never the real repo file, keeping mutation testing isolated from
        # the checkout on disk.
        action_dir = os.path.join(tmp, "actiondir")
        shared_dir = os.path.join(tmp, "_shared")
        os.makedirs(action_dir, exist_ok=True)
        os.makedirs(shared_dir, exist_ok=True)
        with open(os.path.join(shared_dir, "count-turns.sh"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(SHARED_SCRIPT if counter is None else counter)

        rc, output, outputs, summary = run_step(
            BASH, SCRIPT, tmp,
            {"TRANSCRIPT_PATH": TRANSCRIPT_NAME,
             "MODEL": "claude-sonnet-5",
             "MAX_TURNS": max_turns,
             "CEILING": ceiling,
             "RUN_LABEL": "cycle",
             "WARN_FRACTION": warn_fraction or "0.8",
             "GITHUB_ACTION_PATH": action_dir},
            tmp)
        if with_outputs:
            return rc, output, summary, outputs
        return rc, output, summary
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expect(case, records, want, unwanted=(), max_turns="100", exit_zero=True,
           ceiling=""):
    rc, output, summary = run_case(case, records, max_turns, ceiling=ceiling)
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


def case_exhaustion_names_the_ceiling_not_the_intended_budget():
    """The number a run is cut off at is the ceiling, and only the ceiling.

    Since specs/037-agent-turn-budget-guard the runtime enforces
    ceil(intended * 2.5), so `error_max_turns` at a site with a 15-turn
    intended budget means the run made 38 turns, not 15. Naming max-turns
    in that banner sends a maintainer looking for a 15-turn cap that no
    longer exists anywhere (PR #221 review).
    """
    expect("the exhaustion banner names the enforced ceiling",
           transcript(main=38, subtype="error_max_turns", num_turns=44),
           max_turns="15", ceiling="38",
           want=["Turn budget exhausted", "38-turn runaway ceiling",
                 "15-turn intended budget", "2.5x"],
           unwanted=["15-turn cap"])
    expect("with no ceiling given it still names the cap it was told about",
           transcript(main=100, subtype="error_max_turns", num_turns=101),
           want=["100-turn cap"])
    note("the exhaustion banner names the ceiling the runtime enforced and "
         "the intended budget it derives from, never the intended budget "
         "alone")


def case_over_intended_is_not_a_warning():
    """Exceeding the intended budget is now ordinary, and reads that way.

    Before the ceiling existed, used > budget was impossible — the runtime
    stopped you at the budget. Now a healthy run routinely passes it and
    keeps going. Rendering that through the threshold-warning branch
    reprints exactly the "198 / 100 turns (198%)" alarm this file's header
    documents as the bug it was written to kill.
    """
    summary = expect("over the intended budget reads as information",
                     transcript(main=24, num_turns=30),
                     max_turns="15", ceiling="38",
                     want=["Over intended budget", "24 turns", "38-turn "
                           "runaway ceiling"],
                     unwanted=["Turn budget warning", "Turn budget "
                               "exhausted"])
    if "160%" not in summary:
        fail("over the intended budget reads as information",
             f"expected the true ratio (160%) to still be stated, got:\n"
             f"{summary.strip()[:400]}")
    expect("at/below the intended budget the threshold warning still fires",
           transcript(main=14, num_turns=20),
           max_turns="15", ceiling="38",
           want=["Turn budget warning", "14/15"],
           unwanted=["Over intended budget"])
    # The boundary is shared with wing-commander-agent-verdict, whose
    # `over-budget` is counted-turns >= intended-turns. A caller renders
    # both: that output gates the "used its full intended turn budget"
    # callout on the lifecycle issue, this one picks the summary line. While
    # this side used a strict `>`, the single run that lands exactly on the
    # budget got the callout AND the threshold warning the callout is
    # describing (PR #221 review).
    expect("exactly at the intended budget agrees with the verdict action",
           transcript(main=15, num_turns=20),
           max_turns="15", ceiling="38",
           want=["Over intended budget", "15 turns", "(100%)"],
           unwanted=["Turn budget warning"])
    # The ceiling clause is an inline command substitution that exits 1 when
    # CEILING is empty, and composite `shell: bash` steps run under -e that
    # the action's own `set` cannot remove. A caller that has not wired
    # `ceiling` yet must still get the line, and the step must still exit 0.
    expect("a caller with no ceiling wired still renders the line and exits 0",
           transcript(main=24, num_turns=30),
           max_turns="15", ceiling="",
           want=["Over intended budget", "24 turns", "160%"],
           unwanted=["runaway ceiling", "Turn budget warning"])
    note("a run past its intended budget but inside the ceiling is reported "
         "as information, not as a threshold warning — the warning is still "
         "the right voice below the budget")


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


# --- #572: count-turns.sh input shapes and value validation ----------------
COUNTER_LINE = re.compile(r"^(main_turns|sub_turns|reported)=[0-9]*$")


def _ndjson(records):
    return "".join(json.dumps(r) + "\n" for r in records)


def _marker():
    """A path an injected `touch` would create, outside every case's tree."""
    return os.path.join(tempfile.mkdtemp(prefix="wc-metrics-inj-"),
                        "ran").replace("\\", "/")


def _injections(marker):
    """String num_turns values a caller's unfiltered eval would act on."""
    return (f"1; touch {marker}",
            f"$(touch {marker})",
            f"1\nmain_turns=999\ntouch {marker}")


def run_counter(case, raw):
    """Run this pass's (possibly mutated) count-turns.sh over a raw
    transcript the way its callers do, output straight into an `eval`, but
    WITHOUT their digits-only filter, so the script's own header promise is
    what is under test. Returns the three bound values, or None.

    Every line must already be `name=<digits or empty>`."""
    tmp = tempfile.mkdtemp(prefix="wc-count-turns-")
    try:
        with open(os.path.join(tmp, TRANSCRIPT_NAME), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(raw)
        with open(os.path.join(tmp, "count-turns.sh"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(SHARED_SCRIPT)
        with open(os.path.join(tmp, "caller.sh"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write('main_turns=""; sub_turns=""; reported=""\n'
                    'out="$(bash ./count-turns.sh "$1")"\n'
                    'printf "%s\\n" "$out" > raw.txt\n'
                    'eval "$out"\n'
                    'printf "%s|%s|%s" "$main_turns" "$sub_turns" '
                    '"$reported" > bound.txt\n')
        proc = subprocess.run([BASH, "caller.sh", TRANSCRIPT_NAME], cwd=tmp,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        try:
            with open(os.path.join(tmp, "raw.txt"), encoding="utf-8") as f:
                lines = f.read().splitlines()
            with open(os.path.join(tmp, "bound.txt"), encoding="utf-8") as f:
                bound = f.read().split("|")
        except OSError:
            fail(case, f"the caller's eval died (rc {proc.returncode}): "
                       f"{(proc.stdout + proc.stderr).strip()[:300]}")
            return None
        if [ln.split("=", 1)[0] for ln in lines] != \
                ["main_turns", "sub_turns", "reported"] \
                or not all(COUNTER_LINE.match(ln) for ln in lines):
            fail(case, f"expected exactly three name=<digits or empty> "
                       f"lines, got {lines!r}")
        if proc.returncode != 0:
            fail(case, f"the caller's eval exited {proc.returncode}: "
                       f"{(proc.stdout + proc.stderr).strip()[:300]}")
        return dict(zip(("main_turns", "sub_turns", "reported"), bound))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expect_counts(case, raw, main, sub, reported):
    values = run_counter(case, raw)
    want = {"main_turns": main, "sub_turns": sub, "reported": reported}
    if values is not None and values != want:
        fail(case, f"expected {want!r}, got {values!r}")


def case_counter_accepts_every_transcript_shape():
    """One array, NDJSON, several concatenated documents and non-object
    elements all count the same. Read per document, NDJSON printed one line
    per document and the callers' eval ran a bare "0" (exit 127); a bare
    number made `.type` a jq error that emptied all three counts."""
    recs = transcript(main=3, sub=2, chunks=2, num_turns=7)
    expect_counts("counter: one JSON array", json.dumps(recs), "3", "2", "7")
    expect_counts("counter: NDJSON", _ndjson(recs), "3", "2", "7")
    expect_counts("counter: multi-document (arrays and objects)",
                  json.dumps(recs[:3], indent=2) + "\n"
                  + "\n".join(json.dumps(r, indent=2) for r in recs[3:]),
                  "3", "2", "7")
    expect_counts("counter: non-object elements [1, {...}]",
                  json.dumps([1, "x", None] + recs), "3", "2", "7")
    expect_counts("counter: NDJSON ending in false",
                  _ndjson(recs) + "false\n", "3", "2", "7")
    expect_counts("counter: unparseable", "{not json", "", "", "")
    note("count-turns.sh counts one array, NDJSON, multi-document input, "
         "non-object elements and NDJSON ending in false identically")


def case_counter_reported_is_an_integer_or_empty():
    """`reported` is the transcript's own .num_turns. Only an integer >= 0
    is printed; a string an eval would run, a newline that would add an
    assignment, a float, a negative or an object all print empty."""
    marker = _marker()
    values = [(repr(v), v) for v in _injections(marker)] + [
        ("a numeric string", "7"), ("a float", 1.5), ("a negative", -3),
        ("an object", {"n": 1})]
    for label, value in values:
        expect_counts(f"counter: num_turns as {label}",
                      _ndjson(transcript(main=2, num_turns=value)),
                      "2", "0", "")
    if os.path.exists(marker):
        fail("counter: string num_turns", "an injected command ran through "
                                          "the caller's eval")
    expect_counts("counter: num_turns 0 is kept",
                  json.dumps(transcript(main=2, num_turns=0)), "2", "0", "0")
    note("a string, float, negative or object num_turns prints an empty "
         "reported, and nothing in it runs through an unfiltered eval")


def _record(outputs):
    try:
        return json.loads(outputs.get("record-json") or "{}")
    except ValueError:
        return {}


def case_metrics_summary_ndjson_record():
    """The shipped block over NDJSON: exit 0 (it was 127), the counted
    turns rendered, and a record carrying them."""
    case = "metrics summary over an NDJSON transcript"
    recs = transcript(main=40, sub=5, chunks=2, num_turns=60)
    rc, output, summary, outputs = run_case(case, None, raw=_ndjson(recs),
                                            with_outputs=True)
    if rc != 0:
        fail(case, f"exited {rc}: {output.strip()[:300]}")
        return
    for needle in ("| 40 / 100 |", "Subagent turns**: 5"):
        if needle not in summary:
            fail(case, f"expected {needle!r} in the summary, got:\n"
                       f"{summary.strip()[:400]}")
    record = _record(outputs)
    turns = record.get("turns") or {}
    got = (turns.get("counted"), turns.get("reported"),
           turns.get("available"), record.get("record_available"))
    if got != (40, 60, True, True):
        fail(case, f"expected turns counted=40 reported=60 available=true "
                   f"and record_available=true, got {record!r}")
    note("NDJSON exits 0, renders 40/100 and writes a record with "
         "counted=40, reported=60")


def case_metrics_summary_string_num_turns():
    """A string num_turns runs nothing through the eval, and the record
    survives with reported=null instead of degrading to {}."""
    marker = _marker()
    for value in _injections(marker):
        case = f"metrics summary with num_turns {value!r}"
        rc, output, summary, outputs = run_case(
            case, transcript(main=12, num_turns=value), with_outputs=True)
        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:300]}")
            continue
        turns = _record(outputs).get("turns") or {}
        if (turns.get("counted"), turns.get("reported")) != (12, None):
            fail(case, f"expected turns counted=12 reported=null, got "
                       f"{outputs.get('record-json')!r}")
        if "| 12 / 100 |" not in summary:
            fail(case, f"expected '| 12 / 100 |', got:\n"
                       f"{summary.strip()[:400]}")
    if os.path.exists(marker):
        fail("metrics summary with a string num_turns",
             "an injected command ran through the eval")
    note("a string num_turns executes nothing and the record keeps "
         "counted=12 with reported=null")


def case_metrics_summary_filters_hostile_counter():
    """count-turns.sh validates its own output, so the digits-only filter
    before metrics-summary's eval is defence in depth. A stand-in counter
    printing what the old one could (a per-document line, a string
    num_turns, a foreign assignment) proves that filter on its own."""
    case = "metrics summary filters a hostile counter's output"
    marker = _marker()
    counter = ("printf '%s\\n' 'main_turns=7' '0' "
               f"'sub_turns=$(touch {marker})' "
               "'availability=unavailable' "
               f"'reported=1; touch {marker}'\n")
    rc, output, summary = run_case(case, transcript(main=1, num_turns=1),
                                   counter=counter)
    if rc != 0:
        fail(case, f"exited {rc}: {output.strip()[:300]}")
    if os.path.exists(marker):
        fail(case, "the eval ran a command from the counter's output")
    if "| 7 / 100 |" not in summary:
        fail(case, f"expected the one valid line (main_turns=7) to bind, "
                   f"got:\n{summary.strip()[:400]}")
    note("only name=<digits> lines of the counter's output reach "
         "metrics-summary's eval")


CASES = [
    case_streamed_chunks_are_one_turn,
    case_subagent_turns_excluded,
    case_exhausted_is_called_out,
    case_exhaustion_names_the_ceiling_not_the_intended_budget,
    case_over_intended_is_not_a_warning,
    case_warning_boundary,
    case_no_budget_no_ratio,
    case_uncountable_falls_back_labelled,
    case_never_fails,
    case_counter_accepts_every_transcript_shape,
    case_counter_reported_is_an_integer_or_empty,
    case_metrics_summary_ndjson_record,
    case_metrics_summary_string_num_turns,
    case_metrics_summary_filters_hostile_counter,
]


# --- mutation checks -------------------------------------------------------
# Each mutation reintroduces a real defect and asserts this suite catches it.
# Without these, a rewrite that quietly stops counting anything would leave
# every case above passing on a constant. Most key on
# .github/actions/_shared/count-turns.sh (research.md R5's extraction) rather
# than the action's own run: block — the "target" tells run_case() which one
# to mutate for that pass.
MUTATIONS = [
    ("reads .num_turns for the ratio again", "action",
     lambda s: s.replace('turns_used="$main_turns"',
                         'turns_used="$reported_turns"')),
    ("counts assistant records instead of distinct message ids", "shared",
     lambda s: s.replace("| unique | length", "| length")),
    ("counts subagent turns against the parent's budget", "shared",
     lambda s: s.replace('and (.parent_tool_use_id // null) == null)', ')')),
    # #572: count-turns.sh's input shapes, its value validation, and the
    # filter before metrics-summary's eval.
    ("reads the transcript per document instead of normalising it to one "
     "flat array", "shared",
     lambda s: s.replace(
         """jq -cs 'map(if type=="array" then .[] else . end)""",
         """jq -c 'if type=="array" then . else [.] end""", 1)),
    ("reads .type without first dropping non-object elements", "shared",
     lambda s: s.replace("\n    | map(objects)'", "'", 1)),
    ("prints .num_turns without validating it as an integer >= 0", "shared",
     lambda s: s.replace(
         '\n      | select(type=="number" and . >= 0 and . == floor)'
         '\n      | tostring | select(test("^[0-9]+$"))', "", 1)),
    ("evals count-turns.sh's output without filtering it to name=digits "
     "lines", "action",
     lambda s: s.replace(
         "| grep -E '^(main_turns|sub_turns|reported)=[0-9]*$' || true)\"",
         "| cat)\"", 1)),
    ("reads the record's reported turns from the raw .num_turns again "
     "instead of count-turns.sh's validated value", "action",
     lambda s: s.replace('reported_turns="$reported"',
                         'reported_turns="$(jqget \'.num_turns\')"', 1)),
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
            print(f"::error file={source_file}::gate 11's mutation {label!r} "
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
            print(f"::error file={source_file}::gate 11 mutation {label!r} "
                  f"was NOT caught — the suite passed against a knowingly "
                  f"broken script, so its green verdict on the real one "
                  f"means nothing. Add a case that fails on this mutation.")
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
