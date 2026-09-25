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
import re
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


def rate_limit_event(**kw):
    base = {"type": "rate_limit_event", "status": "rejected"}
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
LAST_RAW_OUTPUT = ""
BASH = None


def run_case(name, records, intended_turns="40", raw=None, with_shared=True,
             run_label="", runner_temp=None, counter=None):
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
    # counter= stages a stand-in count-turns.sh instead of the shipped one,
    # for the case that proves the eval's own filter without leaning on
    # the counter's validation.
    if with_shared:
        with open(os.path.join(shared_dir, "count-turns.sh"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(SHARED_SCRIPT if counter is None else counter)

    rc, output, outputs, _summary = run_step(
        BASH, SCRIPT, tmp,
        {"TRANSCRIPT_PATH": TRANSCRIPT_NAME,
         "INTENDED_TURNS": intended_turns,
         "RUN_LABEL": run_label,
         "GITHUB_ACTION_PATH": action_dir,
         # runner_temp overrides where the normalised copy is written; a
         # path that does not exist forces the normaliser-failure path.
         "RUNNER_TEMP": runner_temp or tmp},
        tmp)
    # The raw $GITHUB_OUTPUT text, for cases that must assert on the line
    # structure itself (an injected line) rather than the parsed dict.
    global LAST_RAW_OUTPUT
    try:
        with open(os.path.join(tmp, "gh_output"), encoding="utf-8") as f:
            LAST_RAW_OUTPUT = f.read()
    except OSError:
        LAST_RAW_OUTPUT = ""
    return rc, output, outputs


def expect(case, records, verdict, over_budget=None, intended_turns="40",
           raw=None, reason_contains=None, run_label=""):
    rc, output, outputs = run_case(case, records, intended_turns, raw=raw,
                                   run_label=run_label)
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


def case_rate_limited_terminal_429():
    """Mirrors the real evidence in #300/#278 (2026-09-12 x3, 2026-08-28):
    a rate_limit_event (status=rejected) plus a terminal result whose
    is_error=true, terminal_reason=api_error, api_error_status=429."""
    recs = rate_limit_event(resetsAt="2026-09-12T10:10:00Z",
                            rateLimitType="five_hour") \
        + result(is_error=True, subtype="success", terminal_reason="api_error",
                 api_error_status=429, num_turns=0)
    outputs = expect("rate-limited: terminal 429 rejection", recs,
                     "rate-limited")
    reason = outputs.get("reason") or ""
    if "five_hour" not in reason:
        fail("rate-limited: terminal 429 rejection",
             f"expected reason to name the window, got {reason!r}")
    if "2026-09-12T10:10:00Z" not in reason:
        fail("rate-limited: terminal 429 rejection",
             f"expected reason to name the reset time, got {reason!r}")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z":
        fail("rate-limited: terminal 429 rejection",
             f"expected rate-limit-reset=2026-09-12T10:10:00Z verbatim, "
             f"got {outputs.get('rate-limit-reset')!r}")
    note("a terminal 429 rejection classifies rate-limited, names the "
         "window and reset time, and carries the reset time verbatim in "
         "the structured output")


def case_rate_limited_recovered_mid_run_stays_healthy():
    """spec.md edge case: a rate_limit_event anywhere in the transcript
    must never demote an otherwise-successful run."""
    recs = assistant("msg_main_0") \
        + rate_limit_event(resetsAt="2026-09-12T10:10:00Z") \
        + assistant("msg_main_1") \
        + result(is_error=False, subtype="success", num_turns=2)
    outputs = expect("rate-limited event mid-run, recovered -> healthy",
                     recs, "healthy")
    if outputs.get("rate-limit-reset") not in ("", None):
        fail("rate-limited event mid-run, recovered -> healthy",
             f"expected empty rate-limit-reset for a healthy verdict, got "
             f"{outputs.get('rate-limit-reset')!r}")
    note("a rate_limit_event followed by a successful terminal result "
         "classifies healthy, never rate-limited")


def case_non_429_api_error_stays_failed():
    """429-specific corroboration must not widen to any API error, and a
    non-429 failure with no rate_limit_event record anywhere keeps its
    pre-existing reason text unchanged."""
    recs = result(is_error=True, subtype="success", terminal_reason="api_error",
                 api_error_status=500, num_turns=0)
    outputs = expect("non-429 api error stays failed", recs, "failed",
                     reason_contains="is_error=true")
    if outputs.get("rate-limit-reset") not in ("", None):
        fail("non-429 api error stays failed",
             f"expected empty rate-limit-reset for a failed verdict, got "
             f"{outputs.get('rate-limit-reset')!r}")
    note("a non-429 api_error with no rate_limit_event record classifies "
         "failed, unchanged reason text")


def nested_rate_limit_event(status, **info):
    """The runtime's own shape: status/resetsAt/rateLimitType nested under
    .rate_limit_info rather than at the record's top level."""
    return [{"type": "rate_limit_event",
             "rate_limit_info": dict({"status": status}, **info)}]


def _expect_failed_despite_event(case, event):
    """#544: a non-429 failure that merely logged an informational
    rate_limit_event along the way is a real failure, never rate-limited."""
    recs = assistant("msg_main_0") + event + assistant("msg_main_1") \
        + result(is_error=True, subtype="error_during_execution", num_turns=2)
    outputs = expect(case, recs, "failed", reason_contains="is_error=true")
    if outputs.get("rate-limit-reset") not in ("", None):
        fail(case, f"expected empty rate-limit-reset for a failed verdict, "
                   f"got {outputs.get('rate-limit-reset')!r}")


def case_allowed_warning_event_on_failure_stays_failed():
    _expect_failed_despite_event(
        "allowed_warning event (top-level status) on a non-429 failure -> failed",
        rate_limit_event(status="allowed_warning",
                         resetsAt="2026-09-12T10:10:00Z",
                         rateLimitType="five_hour"))
    note("an informational allowed_warning event does not turn a non-429 "
         "failure into rate-limited")


def case_allowed_nested_event_on_failure_stays_failed():
    _expect_failed_despite_event(
        "allowed event (rate_limit_info.status) on a non-429 failure -> failed",
        nested_rate_limit_event("allowed", resetsAt="2026-09-12T10:10:00Z",
                                rateLimitType="five_hour"))
    note("an informational allowed event in the nested rate_limit_info "
         "shape does not turn a non-429 failure into rate-limited")


def case_informational_after_rejected_still_rate_limited():
    """A rejected event followed by a later informational one: the
    rejection is still evidence, and its reset time is the one reported."""
    case = "rejected event then an informational one -> rate-limited"
    recs = rate_limit_event(resetsAt="2026-09-12T10:10:00Z") \
        + rate_limit_event(status="allowed_warning",
                           resetsAt="2026-09-12T99:99:99Z") \
        + result(is_error=True, subtype="error_during_execution", num_turns=1)
    outputs = expect(case, recs, "rate-limited")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z":
        fail(case, f"expected the rejected event's resetsAt, got "
                   f"{outputs.get('rate-limit-reset')!r}")


def _expect_rate_limited_from_event(case, event):
    """A rejected event on a failing run with NO terminal api_error 429 --
    the event alone must carry the verdict, so this proves the event path
    rather than the terminal-429 path."""
    recs = event + result(is_error=True, subtype="error_during_execution",
                          num_turns=1)
    outputs = expect(case, recs, "rate-limited",
                     reason_contains="five_hour")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z":
        fail(case, f"expected rate-limit-reset=2026-09-12T10:10:00Z, got "
                   f"{outputs.get('rate-limit-reset')!r}")


def case_rejected_event_top_level_rate_limited():
    _expect_rate_limited_from_event(
        "rejected event (top-level status), no terminal 429 -> rate-limited",
        rate_limit_event(resetsAt="2026-09-12T10:10:00Z",
                         rateLimitType="five_hour"))


def case_rejected_event_nested_rate_limited():
    _expect_rate_limited_from_event(
        "rejected event (rate_limit_info.status), no terminal 429 -> rate-limited",
        nested_rate_limit_event("rejected", resetsAt="2026-09-12T10:10:00Z",
                                rateLimitType="five_hour"))
    note("a rejected event classifies rate-limited in both the top-level "
         "and the nested rate_limit_info shape, with window and reset read "
         "from either")


def case_statusless_event_rate_limited():
    """A bare rate_limit_event with no status anywhere still counts: the
    real refused-run transcript pinned from #231 carries exactly this."""
    recs = [{"type": "rate_limit_event"}] \
        + result(is_error=True, subtype="success", num_turns=1)
    outputs = expect("statusless event on a failure -> rate-limited", recs,
                     "rate-limited")
    if outputs.get("rate-limit-reset") != "unknown":
        fail("statusless event on a failure -> rate-limited",
             f"expected rate-limit-reset=unknown, got "
             f"{outputs.get('rate-limit-reset')!r}")


def case_terminal_429_without_event_rate_limited():
    recs = result(is_error=True, subtype="success", terminal_reason="api_error",
                  api_error_status=429, num_turns=0)
    outputs = expect("terminal api_error 429 with no event -> rate-limited",
                     recs, "rate-limited")
    if outputs.get("rate-limit-reset") != "unknown":
        fail("terminal api_error 429 with no event -> rate-limited",
             f"expected rate-limit-reset=unknown, got "
             f"{outputs.get('rate-limit-reset')!r}")
    note("a terminal api_error 429 alone classifies rate-limited, reset "
         "unknown")


def case_epoch_reset_becomes_iso():
    """The runtime's nested shape carries resetsAt as epoch seconds; the
    reset output and reason must carry ISO-8601 (data-model.md)."""
    case = "numeric nested resetsAt -> ISO-8601 reset"
    recs = nested_rate_limit_event("rejected", resetsAt=1757671800,
                                   rateLimitType="five_hour") \
        + result(is_error=True, subtype="success", num_turns=1)
    outputs = expect(case, recs, "rate-limited",
                     reason_contains="2025-09-12T10:10:00Z")
    if outputs.get("rate-limit-reset") != "2025-09-12T10:10:00Z":
        fail(case, f"expected rate-limit-reset=2025-09-12T10:10:00Z, got "
                   f"{outputs.get('rate-limit-reset')!r}")


def case_terminal_429_reset_from_informational_event():
    """FR-003: a terminal 429 whose only event is informational still
    exposes that event's reset time; the 429 alone classifies. The window
    does NOT fall back: an informational event may name a different window
    from the one that rejected the call."""
    case = "allowed_warning event then terminal 429 -> reset from the event"
    recs = rate_limit_event(status="allowed_warning",
                            resetsAt="2026-09-12T10:10:00Z",
                            rateLimitType="seven_day") \
        + result(is_error=True, subtype="success", terminal_reason="api_error",
                 api_error_status=429, num_turns=0)
    outputs = expect(case, recs, "rate-limited",
                     reason_contains="usage window exhausted, resets at "
                                     "2026-09-12T10:10:00Z")
    if "seven_day" in (outputs.get("reason") or ""):
        fail(case, f"the informational event's window must not be named, "
                   f"got reason {outputs.get('reason')!r}")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z":
        fail(case, f"expected rate-limit-reset=2026-09-12T10:10:00Z, got "
                   f"{outputs.get('rate-limit-reset')!r}")


def case_implausible_epoch_reset_is_unknown():
    """spec.md: never epoch-zero, never a fabricated timestamp. Zero,
    negative, millisecond-scale and unconvertible numbers are 'unknown'."""
    for value in (0, -1, 1790000000000, 1e20):
        case = f"numeric resetsAt {value!r} -> unknown"
        recs = nested_rate_limit_event("rejected", resetsAt=value) \
            + result(is_error=True, subtype="success", num_turns=1)
        outputs = expect(case, recs, "rate-limited",
                         reason_contains="resets at unknown")
        if outputs.get("rate-limit-reset") != "unknown":
            fail(case, f"expected rate-limit-reset=unknown, got "
                       f"{outputs.get('rate-limit-reset')!r}")


def case_empty_top_level_reset_falls_through_to_nested():
    case = "empty top-level resetsAt -> nested rate_limit_info.resetsAt"
    recs = [{"type": "rate_limit_event", "resetsAt": "", "rateLimitType": "",
             "rate_limit_info": {"status": "rejected",
                                 "resetsAt": "2026-09-12T10:10:00Z",
                                 "rateLimitType": "five_hour"}}] \
        + result(is_error=True, subtype="success", num_turns=1)
    outputs = expect(case, recs, "rate-limited", reason_contains="five_hour")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z":
        fail(case, f"expected rate-limit-reset=2026-09-12T10:10:00Z, got "
                   f"{outputs.get('rate-limit-reset')!r}")


def case_status_case_insensitive():
    for status in ("Rejected", "REJECTED"):
        for shape, event in (
                ("top-level", rate_limit_event(
                    status=status, resetsAt="2026-09-12T10:10:00Z")),
                ("nested", nested_rate_limit_event(
                    status, resetsAt="2026-09-12T10:10:00Z"))):
            expect(f"status {status!r} ({shape}) -> rate-limited",
                   event + result(is_error=True,
                                  subtype="error_during_execution",
                                  num_turns=1),
                   "rate-limited")


def case_reset_newline_cannot_inject_output():
    """A resetsAt/rateLimitType carrying CR/LF must not add lines to
    $GITHUB_OUTPUT: a second `verdict=` line would override the real one."""
    case = "resetsAt carrying a newline cannot inject an output line"
    recs = rate_limit_event(resetsAt="2026-09-12T10:10:00Z\nverdict=healthy",
                            rateLimitType="five_hour\r\nover-budget=true") \
        + result(is_error=True, subtype="error_during_execution", num_turns=1)
    outputs = expect(case, recs, "rate-limited")
    lines = LAST_RAW_OUTPUT.splitlines()
    verdict_lines = [ln for ln in lines if ln.startswith("verdict=")]
    if verdict_lines != ["verdict=rate-limited"]:
        fail(case, f"expected exactly one verdict line, got {verdict_lines!r}")
    budget_lines = [ln for ln in lines if ln.startswith("over-budget=")]
    if budget_lines != ["over-budget=false"]:
        fail(case, f"expected exactly one over-budget line, got "
                   f"{budget_lines!r}")
    if len(lines) != 7:
        fail(case, f"expected exactly 7 output lines, got {len(lines)}: "
                   f"{lines!r}")
    if outputs.get("rate-limit-reset") != "2026-09-12T10:10:00Z verdict=healthy":
        fail(case, f"expected the newline flattened to a space, got "
                   f"{outputs.get('rate-limit-reset')!r}")


OUTPUT_KEYS = ("verdict", "reason", "rate-limit-reset", "counted-turns",
               "reported-turns", "over-budget", "subagent-turns")


def _expect_output_lines_intact(case, verdict):
    """Assert on the raw $GITHUB_OUTPUT text: exactly the seven keys, each
    once, in order, and a single verdict line carrying the real verdict."""
    lines = LAST_RAW_OUTPUT.splitlines()
    keys = [ln.split("=", 1)[0] for ln in lines]
    if keys != list(OUTPUT_KEYS):
        fail(case, f"expected exactly the {len(OUTPUT_KEYS)} output keys "
                   f"{list(OUTPUT_KEYS)!r}, got {keys!r}")
    verdict_lines = [ln for ln in lines if ln.startswith("verdict=")]
    if verdict_lines != [f"verdict={verdict}"]:
        fail(case, f"expected exactly one verdict line, got {verdict_lines!r}")
    if "\r" in LAST_RAW_OUTPUT:
        fail(case, "a CR reached $GITHUB_OUTPUT")


# --- #551: transcript shapes other than one JSON array, and injection ------
def _ndjson(records):
    return "".join(json.dumps(r) + "\n" for r in records)


def case_ndjson_transcript():
    """One record per line. Fed raw to count-turns.sh, each per-document
    jq printed one line per record and the eval ran "0" as a command:
    exit 127, the step failed (#551 item 1)."""
    case = "NDJSON transcript with a failed terminal result"
    recs = transcript(main=3, is_error=True, subtype="error_during_execution",
                      num_turns=3)
    outputs = expect(case, None, "failed", raw=_ndjson(recs),
                     reason_contains="is_error=true")
    if outputs.get("counted-turns") != "3":
        fail(case, f"expected counted-turns=3, got "
                   f"{outputs.get('counted-turns')!r}")
    if outputs.get("reported-turns") != "3":
        fail(case, f"expected reported-turns=3, got "
                   f"{outputs.get('reported-turns')!r}")
    _expect_output_lines_intact(case, "failed")
    note("an NDJSON transcript classifies from its terminal result, counts "
         "its turns, and exits 0")


def case_multi_document_transcript():
    """Several JSON documents back to back: a pretty-printed array, then
    two bare objects, the last of them the failed terminal result."""
    case = "multi-document transcript with a failed terminal result"
    first = assistant("msg_main_0") + assistant("msg_main_1")
    rest = assistant("msg_main_2") + result(
        is_error=True, subtype="error_during_execution", num_turns=3)
    raw = json.dumps(first, indent=2) + "\n" \
        + "\n".join(json.dumps(r, indent=2) for r in rest) + "\n"
    outputs = expect(case, None, "failed", raw=raw,
                     reason_contains="is_error=true")
    if outputs.get("counted-turns") != "3":
        fail(case, f"expected counted-turns=3, got "
                   f"{outputs.get('counted-turns')!r}")
    _expect_output_lines_intact(case, "failed")


def case_non_object_elements_are_skipped():
    """A bare number or string among the records: `.type` on either is a
    jq error that `|| true` swallowed, so the result record was never found
    ("no terminal result record") and a rejected event never counted
    (#551 item 2)."""
    case = "non-object elements before the result record"
    expect(case, [1, "x"] + transcript(main=2, num_turns=2), "healthy",
           reason_contains="subtype=success")
    case = "non-object elements before a rejected rate_limit_event"
    expect(case, [1, "x"] + rate_limit_event(rateLimitType="five_hour")
           + [2] + result(is_error=True, subtype="error_during_execution",
                          num_turns=1),
           "rate-limited", reason_contains="five_hour")
    note("bare numbers and strings in the transcript are skipped, never "
         "hiding the result record or a rejected event")


def case_subtype_newline_cannot_inject_output():
    """The reason interpolates the transcript's subtype: a newline in it
    must not add a second `verdict=` line to $GITHUB_OUTPUT."""
    case = "subtype carrying a newline cannot inject an output line"
    for subtype in ("error_during_execution\nverdict=healthy",
                    "error_during_execution\r\nverdict=healthy"):
        outputs = expect(case, transcript(main=1, subtype=subtype,
                                          num_turns=1),
                         "failed", reason_contains="unexpected terminal subtype")
        _expect_output_lines_intact(case, "failed")
        if "verdict=healthy" not in (outputs.get("reason") or ""):
            fail(case, f"expected the newline flattened into the reason, "
                       f"got {outputs.get('reason')!r}")


def case_num_turns_newline_cannot_inject_output():
    """reported-turns is the transcript's own .num_turns, which
    count-turns.sh prints verbatim for the composite to eval: a string
    value carrying a newline must neither reassign the verdict inside the
    step nor run a command substitution."""
    case = "string num_turns carrying a newline cannot inject an output line"
    marker = os.path.join(tempfile.mkdtemp(prefix="wc-verdict-inj-"), "ran")
    outputs = expect(case, transcript(
        main=1, num_turns=f"1\nverdict=failed\nreported=$(touch {marker})"),
        "healthy")
    _expect_output_lines_intact(case, "healthy")
    if os.path.exists(marker):
        fail(case, "a command substitution in num_turns was executed by the "
                   "eval of count-turns.sh's output")
    if not (outputs.get("reported-turns") or "").isdigit() \
            and outputs.get("reported-turns") not in ("", None):
        fail(case, f"expected a bare integer or empty reported-turns, got "
                   f"{outputs.get('reported-turns')!r}")


def case_run_label_newline_cannot_inject_output():
    """run-label is caller input interpolated into the reason."""
    case = "run-label carrying CR/LF cannot inject an output line"
    for label in ("retry\nverdict=healthy", "retry\r\nover-budget=true",
                  "retry\rverdict=healthy"):
        outputs = expect(case, transcript(main=1, is_error=True, num_turns=1),
                         "failed", run_label=label)
        _expect_output_lines_intact(case, "failed")
        if not (outputs.get("reason") or "").endswith(")"):
            fail(case, f"expected the label flattened into the reason, got "
                       f"{outputs.get('reason')!r}")
        if outputs.get("over-budget") != "false":
            fail(case, f"expected over-budget=false, got "
                       f"{outputs.get('over-budget')!r}")


def case_non_string_subtype_stays_one_line():
    """A non-string subtype: `jq -r` pretty-prints an array or object over
    several lines, which the runner rejects as an invalid $GITHUB_OUTPUT
    ("Invalid format") and the step fails. It is read as compact JSON."""
    for subtype, shown in ((["a\nverdict=healthy"],
                            'subtype=["a\\nverdict=healthy"]'),
                           ({"k": "v"}, 'subtype={"k":"v"}')):
        case = f"non-string subtype {subtype!r} stays one output line"
        expect(case, transcript(main=1, subtype=subtype, num_turns=1),
               "failed", reason_contains=shown)
        _expect_output_lines_intact(case, "failed")


def case_normaliser_failure_keeps_output_lines():
    """RUNNER_TEMP unwritable: no normalised copy, so the classifier reads
    the raw NDJSON, where each per-document jq prints one line per result
    record and subtype comes back as two lines. Only the write-site
    flatten keeps $GITHUB_OUTPUT intact on this path."""
    case = "normaliser failure (RUNNER_TEMP unwritable) keeps output lines"
    recs = assistant("msg_main_0") \
        + result(is_error=True, subtype="error_during_execution",
                 num_turns=1) \
        + assistant("msg_main_1") \
        + result(is_error=True, subtype="error_during_execution",
                 num_turns=2)
    missing = os.path.join(tempfile.mkdtemp(prefix="wc-verdict-rt-"),
                           "does-not-exist")
    rc, output, outputs = run_case(case, None, raw=_ndjson(recs),
                                   runner_temp=missing)
    if rc != 0:
        fail(case, f"exited {rc}: {output.strip()[:300]}")
        return
    _expect_output_lines_intact(case, outputs.get("verdict") or "")
    if outputs.get("verdict") != "failed":
        fail(case, f"expected verdict=failed, got {outputs.get('verdict')!r}")


def case_ndjson_ending_in_null_is_parseable():
    """`jq -e .` takes its status from the last document only, so NDJSON
    whose last line is null or false read as unparseable."""
    for tail in ("null", "false"):
        case = f"NDJSON ending in {tail} is still classified"
        recs = transcript(main=2, is_error=True,
                          subtype="error_during_execution", num_turns=2)
        outputs = expect(case, None, "failed", raw=_ndjson(recs) + tail + "\n",
                         reason_contains="is_error=true")
        # count-turns.sh drops non-object elements itself (#572), so a
        # trailing `false` counts the same as a trailing `null`.
        if outputs.get("counted-turns") != "2":
            fail(case, f"expected counted-turns=2, got "
                       f"{outputs.get('counted-turns')!r}")
        _expect_output_lines_intact(case, "failed")


def case_ndjson_last_result_record_decides():
    """NDJSON carrying two result records, a failed one then a successful
    one. Read per document instead of as one normalised array, each
    document's jq prints its own result record, so result_json holds both
    and is_error reads back as two lines."""
    case = "NDJSON with two result records classifies from the last"
    recs = assistant("msg_main_0") \
        + result(is_error=True, subtype="error_during_execution",
                 num_turns=1) \
        + assistant("msg_main_1") \
        + result(is_error=False, subtype="success", num_turns=2)
    outputs = expect(case, None, "healthy", raw=_ndjson(recs),
                     reason_contains="subtype=success")
    if outputs.get("counted-turns") != "2":
        fail(case, f"expected counted-turns=2, got "
                   f"{outputs.get('counted-turns')!r}")
    _expect_output_lines_intact(case, "healthy")


def case_hostile_counter_output_is_filtered():
    """count-turns.sh validates its own values (#572), so the digits-only
    filter before the eval here is defence in depth. A stand-in counter
    that prints what the old one could (a string num_turns verbatim, a
    per-document line) proves that filter on its own: no command runs, no
    variable outside the three is reassigned, and only valid lines bind."""
    case = "hostile counter output is filtered before the eval"
    marker = os.path.join(tempfile.mkdtemp(prefix="wc-verdict-ctr-"), "ran")
    counter = (
        "printf '%s\\n' 'main_turns=5' '0' 'sub_turns=$(touch "
        + marker + ")' 'verdict=failed' 'reported=1; touch " + marker
        + "'\n")
    rc, output, outputs = run_case(case, transcript(main=1, num_turns=1),
                                   counter=counter)
    if rc != 0:
        fail(case, f"exited {rc}: {output.strip()[:300]}")
        return
    if os.path.exists(marker):
        fail(case, "the eval ran a command from the counter's output")
    if outputs.get("verdict") != "healthy":
        fail(case, f"expected verdict=healthy, got {outputs.get('verdict')!r}")
    if outputs.get("counted-turns") != "5":
        fail(case, f"expected counted-turns=5, got "
                   f"{outputs.get('counted-turns')!r}")
    for key in ("subagent-turns", "reported-turns"):
        if outputs.get(key) not in ("", None):
            fail(case, f"expected {key} empty, got {outputs.get(key)!r}")
    _expect_output_lines_intact(case, "healthy")


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
    case_rate_limited_terminal_429,
    case_rate_limited_recovered_mid_run_stays_healthy,
    case_non_429_api_error_stays_failed,
    case_allowed_warning_event_on_failure_stays_failed,
    case_allowed_nested_event_on_failure_stays_failed,
    case_informational_after_rejected_still_rate_limited,
    case_rejected_event_top_level_rate_limited,
    case_rejected_event_nested_rate_limited,
    case_statusless_event_rate_limited,
    case_terminal_429_without_event_rate_limited,
    case_epoch_reset_becomes_iso,
    case_terminal_429_reset_from_informational_event,
    case_implausible_epoch_reset_is_unknown,
    case_empty_top_level_reset_falls_through_to_nested,
    case_status_case_insensitive,
    case_reset_newline_cannot_inject_output,
    case_shared_counter_absent,
    case_ndjson_transcript,
    case_multi_document_transcript,
    case_non_object_elements_are_skipped,
    case_subtype_newline_cannot_inject_output,
    case_num_turns_newline_cannot_inject_output,
    case_run_label_newline_cannot_inject_output,
    case_non_string_subtype_stays_one_line,
    case_normaliser_failure_keeps_output_lines,
    case_ndjson_ending_in_null_is_parseable,
    case_ndjson_last_result_record_decides,
    case_hostile_counter_output_is_filtered,
    case_never_fails,
]


# --- mutation checks ---------------------------------------------------------
# The seven write-site lines, each `name="${name//[$'\r\n']/ }"`.
WRITE_SITE_FLATTEN = re.compile(
    r"^[ \t]*(\w+)=\"\$\{\1//\[\$'\\r\\n'\]/ \}\"\n", re.M)


def without_write_site(s):
    """Drop the write-site CR/LF flatten. The read-site mutations below
    apply this too: with both layers in place, removing one read-site rule
    is invisible in $GITHUB_OUTPUT by design (the write site catches it),
    so each read-site mutation removes BOTH layers for its value. The
    write-site layer is proven on its own by the normaliser-failure case,
    where no read-site rule applies. Returns s unchanged unless all seven
    lines are found, so a rewrite trips the no-op check."""
    out, n = WRITE_SITE_FLATTEN.subn("", s)
    return out if n == 7 else s


MUTATIONS = [
    ("reads is_error/subtype from anywhere other than the last result record",
     "action",
     lambda s: s.replace(
         "map(objects | select(.type==\"result\")) | last // empty",
         "map(objects | select(.type==\"result\")) | first // empty")),
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
    ("disables the rate-limited branch by comparing rate_limit_evidence "
     "against an impossible value", "action",
     lambda s: s.replace(
         '[ "$rate_limit_evidence" = "true" ]; then\n      verdict="rate-limited"',
         '[ "$rate_limit_evidence" = "bogus" ]; then\n      verdict="rate-limited"')),
    # #544: the rate_limit_event status filter and the reset/window read.
    ("counts any rate_limit_event as evidence, whatever its status "
     "(the #544 defect)", "action",
     lambda s: s.replace('else . end) == "rejected";',
                         'else . end) != "__any__";', 1)),
    ("reads status only at the top level, ignoring rate_limit_info.status",
     "action",
     lambda s: s.replace('then .rate_limit_info.status else null end',
                         'then null else null end', 1)),
    ("stops counting a statusless rate_limit_event as evidence", "action",
     lambda s: s.replace('// .status // "rejected";',
                         '// .status // "none";', 1)),
    ("matches the status case-sensitively", "action",
     lambda s: s.replace('if type=="string" then ascii_downcase else . end',
                         'if type=="string" then . else . end', 1)),
    ("reads reset/window only at the top level, ignoring rate_limit_info",
     "action",
     lambda s: s.replace('then .rate_limit_info[$k] else null end',
                         'then null else null end', 1)),
    ("drops the any-status fallback for the reset time (FR-003)", "action",
     lambda s: s.replace('(($q // ($ev | last)) // {}) as $src',
                         '($q // {}) as $src', 1)),
    ("prints an epoch resetsAt raw instead of as ISO-8601", "action",
     lambda s: s.replace(
         '(if . > 0 and . < 1e11 then (try todate catch null) else null end)',
         '.', 1)),
    ("converts any numeric resetsAt, fabricating dates from 0, negative "
     "or millisecond values", "action",
     lambda s: s.replace(
         '(if . > 0 and . < 1e11 then (try todate catch null) else null end)',
         '(try todate catch tostring)', 1)),
    ("lets the window fall back to an informational event", "action",
     lambda s: s.replace('window: (($q // {}) | field("rateLimitType")',
                         'window: ($src | field("rateLimitType")', 1)),
    ("lets an empty top-level resetsAt hide the nested one", "action",
     lambda s: s.replace('map(select(. != null and . != ""))',
                         'map(select(. != null))', 1)),
    ("stops stripping CR/LF from the reset/window values (and drops the "
     "write-site flatten)", "action",
     lambda s: without_write_site(s).replace(
         'tostring | gsub("[\\r\\n]"; " ") end;', 'tostring end;', 1)),
    # #551: transcript shape and $GITHUB_OUTPUT line injection.
    ("reads the raw transcript instead of the normalised array, so an "
     "NDJSON transcript's result records are read per document", "action",
     lambda s: s.replace(
         "jq -cs 'map(if type==\"array\" then .[] else . end)'",
         "jq -c '.'", 1)),
    ("selects the result record without skipping non-object elements",
     "action",
     lambda s: s.replace('map(objects | select(.type=="result"))',
                         'map(select(.type=="result"))', 1)),
    ("selects rate_limit_event records without skipping non-object "
     "elements", "action",
     lambda s: s.replace('map(objects | select(.type=="rate_limit_event"))',
                         'map(select(.type=="rate_limit_event"))', 1)),
    ("evals count-turns.sh's output without filtering it to name=digits "
     "lines", "action",
     lambda s: s.replace(
         "| grep -E '^(main_turns|sub_turns|reported)=[0-9]*$' || true)\"",
         "| cat)\"", 1)),
    ("stops flattening CR/LF in the run-label (and drops the write-site "
     "flatten)", "action",
     lambda s: without_write_site(s).replace(
         'RUN_LABEL="$(printf \'%s\' "${RUN_LABEL:-}" | tr \'\\r\\n\' \'  \')"',
         'RUN_LABEL="${RUN_LABEL:-}"', 1)),
    ("stops flattening CR/LF in the transcript's subtype (and drops the "
     "write-site flatten)", "action",
     lambda s: without_write_site(s).replace(
         'if type=="string" then . else tojson end | gsub("[\\r\\n]"; " ")',
         'if type=="string" then . else tojson end', 1)),
    ("prints a non-string subtype with jq -r instead of as compact JSON",
     "action",
     lambda s: s.replace(
         'if type=="string" then . else tojson end | gsub("[\\r\\n]"; " ")',
         'if type=="string" then gsub("[\\r\\n]"; " ") else . end', 1)),
    ("drops the write-site CR/LF flatten", "action", without_write_site),
    ("checks parseability with `jq -e .` (last document only) instead of "
     "`jq empty`", "action",
     lambda s: s.replace('&& jq empty "$TRANSCRIPT" >/dev/null 2>&1; then',
                         '&& jq -e . "$TRANSCRIPT" >/dev/null 2>&1; then', 1)),
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
