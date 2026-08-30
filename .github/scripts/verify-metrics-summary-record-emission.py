#!/usr/bin/env python3
"""Gate — every wing-commander-metrics-summary invocation emits a
conforming, non-colliding metrics record (specs/043-durable-metrics-record,
tasks.md Phase 9 T061 / FR-009 / FR-010).

WHY THIS EXISTS
---------------
T001-T005 built record emission and T047-T056 (User Story 5) shipped gates
for the record's SHAPE (verify-metrics-record-schema.py) and for the
persistence/rollup layer that consumes records once they exist. Nothing
exercised the shipped "Render agent run metrics summary" step itself against
a real transcript to prove it actually PRODUCES that shape end to end — the
degraded-record branch (missing/empty/unparseable transcript, T003) and the
one-job-many-invocations case (T009's cycle/retry/progress sites sharing a
job, T061) shipped as reasoned-through code, never as executed code.

This runs the SHIPPED `run:` block, extracted from the composite action's
YAML exactly the way Gate 11 (verify-metrics-turn-accounting.py) does — no
copied logic to drift out of sync — and validates the record it writes with
the real verify-metrics-record-schema.py gate rather than re-deriving the
schema here.

It also pins the composite's `cost-line` output (FR-031c) on both the
healthy and the degraded branch, and asserts the formatter behind it has
NO other home: it was once pasted into 12 "Compute cost line" run-blocks
across 9 stage workflows, where a rounding fix would have had to land 12
times with nothing failing on a drifted copy (PR #277 review). The stage
workflows now consume the output; a pasted copy reappearing in any
workflow OR composite action under .github/actions/ fails here (PR #277
round-4 review: the original scan missed .github/actions/, the likeliest
paste target for shared logic per CLAUDE.md).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-metrics-summary/action.yml"
STEP_NAME = "Render agent run metrics summary"
ACTION_DIR = os.path.abspath(os.path.dirname(ACTION))
SCHEMA_GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "verify-metrics-record-schema.py")
TRANSCRIPT_NAME = "claude-execution-output.json"

failures = []
MUTATING = False
BASH = None
SCRIPT = find_step(ACTION, STEP_NAME)["run"]


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    prefix = "note: (expected, mutation phase) " if MUTATING else \
        f"::error file={ACTION}::"
    print(f"{prefix}{case}: {msg}")


def note(msg):
    print(f"note: {msg}")


# --- transcript builders (mirrors Gate 11's shape) --------------------------
def assistant(mid):
    return [{"type": "assistant", "parent_tool_use_id": None,
             "message": {"id": mid, "content": []}}]


def result(**kw):
    base = {"type": "result", "subtype": "success", "num_turns": 12,
            "duration_ms": 45000, "total_cost_usd": 1.5,
            "usage": {"input_tokens": 100, "output_tokens": 200,
                      "cache_read_input_tokens": 10,
                      "cache_creation_input_tokens": 5},
            "modelUsage": {"claude-sonnet-5": {
                "inputTokens": 100, "outputTokens": 200,
                "cacheReadInputTokens": 10, "cacheCreationInputTokens": 5,
                "costUSD": 1.5}}}
    base.update(kw)
    return [base]


def healthy_transcript(main=5):
    recs = []
    for i in range(main):
        recs += assistant(f"msg_{i}")
    return recs + result()


def validate_schema(case, record):
    """Reuse the real schema gate rather than re-deriving its rules here."""
    tmp = tempfile.mkdtemp(prefix="wc-metrics-record-schema-check-")
    try:
        record_path = os.path.join(tmp, "record.json")
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(record, f)
        proc = subprocess.run([sys.executable, SCHEMA_GATE, record_path],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            fail(case, "produced record failed verify-metrics-record-schema.py: "
                       + (proc.stdout + proc.stderr).strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_case(tmp, records=None, raw=None, missing=False, env_over=None):
    """Execute the shipped record-emission step once inside `tmp`.

    Returns (rc, outputs, summary, record, raw_output). `tmp` is reused
    across calls within one case so a caller can model several invocations
    sharing one job's $RUNNER_TEMP the way implement.yml's cycle/retry/
    progress sites do.
    """
    transcript_path = os.path.join(tmp, TRANSCRIPT_NAME)
    if missing:
        transcript_path = os.path.join(tmp, "does-not-exist.json")
    elif raw is not None:
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(raw)
    elif records is not None:
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(records, f)

    record_path = os.path.join(tmp, "wing-commander-metrics-record.json")
    env = {
        "TRANSCRIPT_PATH": transcript_path,
        "MODEL": "claude-sonnet-5",
        "MAX_TURNS": "60",
        "CEILING": "150",
        "WARN_FRACTION": "0.8",
        "RUN_LABEL": "cycle",
        "VERDICT": "",
        "VERDICT_REASON": "",
        "RECORD_PATH": record_path,
        "STAGE": "implement",
        "SPEC_DIR": "specs/043-durable-metrics-record",
        "SPEC_ISSUE": "148",
        "STEP_INDEX": "0",
        "RUN_ID": "555000111",
        "JOB_KEY": "cycle",
        "GITHUB_ACTION_PATH": ACTION_DIR,
    }
    if env_over:
        env.update(env_over)
    rc, output, outputs, summary = run_step(BASH, SCRIPT, tmp, env, tmp)
    record = None
    if os.path.exists(record_path):
        with open(record_path, encoding="utf-8") as f:
            try:
                record = json.load(f)
            except ValueError:
                record = None
    return rc, outputs, summary, record, output


# --- cases -------------------------------------------------------------
def case_healthy_transcript_emits_a_valid_record():
    case = "healthy transcript"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-record-")
    try:
        rc, outputs, summary, record, output = run_case(
            tmp, records=healthy_transcript(main=5))
        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:300]}")
            return
        if record is None:
            fail(case, "record-path was not written")
            return
        validate_schema(case, record)
        if record.get("record_available") is not True:
            fail(case, f"expected record_available true, got "
                       f"{record.get('record_available')!r}")
        if record.get("run", {}).get("record_key") != "555000111:cycle:0":
            fail(case, f"unexpected record_key "
                       f"{record.get('run', {}).get('record_key')!r}")
        if outputs.get("record-key") != record.get("run", {}).get("record_key"):
            fail(case, "record-key output did not match the written "
                       "record's run.record_key")
        if record.get("cost_usd") != 1.5:
            fail(case, f"expected cost_usd 1.5, got {record.get('cost_usd')!r}")
        if record.get("outcome") != "healthy":
            fail(case, f"expected outcome healthy, got {record.get('outcome')!r}")
        if not record.get("per_model_available") or len(record.get("per_model") or []) != 1:
            fail(case, f"expected exactly one per_model entry, got "
                       f"{record.get('per_model')!r}")
        if "$1.50" not in summary:
            fail(case, "the rendered summary's cost cell disagreed with "
                       "the record's cost_usd (expected $1.50)")
        want_line = "**Cost**: $1.50 · 5/60 turns · claude-sonnet-5"
        if outputs.get("cost-line") != want_line:
            fail(case, f"cost-line output: expected {want_line!r}, got "
                       f"{outputs.get('cost-line')!r} — the stage "
                       f"workflows' status comments post this verbatim")
        note("a healthy transcript produces a schema-valid record whose "
             "cost/outcome/per_model agree with the rendered "
             "$GITHUB_STEP_SUMMARY table, and a matching cost-line output")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _degraded_case(case, **run_kwargs):
    tmp = tempfile.mkdtemp(prefix="wc-metrics-record-")
    try:
        rc, outputs, _summary, record, output = run_case(tmp, **run_kwargs)
        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:300]}")
            return
        if record is None:
            fail(case, "record-path was not written")
            return
        validate_schema(case, record)
        # The cost-line output degrades per-part, never to empty/absent:
        # cost and turns come from the (missing) transcript, the model is
        # caller-supplied and survives.
        want_line = "**Cost**: cost unavailable · turns unavailable · claude-sonnet-5"
        if outputs.get("cost-line") != want_line:
            fail(case, f"degraded cost-line output: expected {want_line!r}, "
                       f"got {outputs.get('cost-line')!r}")
        if record.get("record_available") is not False:
            fail(case, f"expected record_available false, got "
                       f"{record.get('record_available')!r}")
        if record.get("cost_available") is not False or record.get("cost_usd") is not None:
            fail(case, "degraded record must null out cost, not just mark "
                       "it unavailable")
        # T003: run/stage/spec/model still come from the job environment,
        # never from the (missing/broken) transcript.
        if record.get("stage") != "implement" or record.get("run", {}).get("job_key") != "cycle":
            fail(case, "degraded record must still carry the "
                       "job-environment fields (stage/run.job_key)")
        if record.get("model") != "claude-sonnet-5":
            fail(case, "degraded record must still carry the "
                       "caller-supplied model")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_missing_transcript_degrades():
    _degraded_case("missing transcript", missing=True)


def case_empty_transcript_degrades():
    _degraded_case("empty transcript file", raw="")


def case_unparseable_transcript_degrades():
    _degraded_case("unparseable transcript", raw="{not json at all")


def case_repeated_invocation_in_one_job_gets_distinct_record_keys():
    """implement.yml's cycle/retry/progress shape: one job, one shared
    $RUNNER_TEMP, three invocations at step_index 0/1/2 — each call site
    uploads its metrics-record artifact before the next runs (tasks.md T009),
    so this captures each record immediately after its call, exactly as
    production does, then asserts none of the three record_keys collide."""
    case = "repeated invocation, distinct step_index"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-record-")
    try:
        captured = []
        labels = {"0": "cycle", "1": "retry", "2": "progress"}
        for step_index in ("0", "1", "2"):
            rc, _outputs, _summary, record, output = run_case(
                tmp, records=healthy_transcript(main=3 + int(step_index)),
                env_over={"STEP_INDEX": step_index,
                          "RUN_LABEL": labels[step_index]})
            if rc != 0:
                fail(case, f"step_index={step_index} exited {rc}: "
                           f"{output.strip()[:300]}")
                return
            if record is None:
                fail(case, f"step_index={step_index}: record-path was not "
                           f"written")
                return
            validate_schema(f"{case} (step_index={step_index})", record)
            captured.append(record)
        keys = [r["run"]["record_key"] for r in captured]
        if len(set(keys)) != 3:
            fail(case, f"expected 3 distinct record_keys across the job's "
                       f"three invocations, got {keys!r} — a downstream "
                       f"persist reading all three artifacts back could not "
                       f"tell them apart")
        note(f"one job's three same-run_id/job_key invocations "
             f"(step_index 0/1/2) produced distinct record_keys: {keys!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_cost_line_formatter_has_exactly_one_home():
    """The 12-site paste this gate's docstring describes must not creep
    back: a workflow or composite action needing the cost line consumes
    the composite's cost-line output (plus its own one-line fallback for
    the action-never-ran case), never a copy of the jq formatter.

    PR #277's round-4 review found this scan covered only
    .github/workflows/*.yml — leaving .github/actions/ (CLAUDE.md's own
    prescribed home for cross-workflow shell/jq) as an unchecked blind
    spot, so a copy pasted into the likeliest paste target, a composite
    action, would evade the gate entirely. Widened to also walk every
    composite action.yml/action.yaml (any depth) plus any *.sh/*.py under
    .github/actions/, excluding only the canonical home (ACTION) itself."""
    case = "cost-line formatter single home"
    hits = []

    def scan(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "def usd(" in text or "costpart" in text:
            hits.append(path)

    wf_dir = ".github/workflows"
    for name in sorted(os.listdir(wf_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        scan(os.path.join(wf_dir, name))

    actions_dir = ".github/actions"
    canonical = os.path.normpath(ACTION)
    for root, _dirs, files in os.walk(actions_dir):
        for name in sorted(files):
            if name in ("action.yml", "action.yaml") or \
                    name.endswith((".sh", ".py")):
                path = os.path.join(root, name)
                if os.path.normpath(path) == canonical:
                    continue
                scan(path)

    if hits:
        fail(case, "the per-run cost-line formatter's only home is "
                   f"{ACTION} (its cost-line output); a copy pasted into a "
                   "workflow or composite action drifts silently the next "
                   "time the formatter changes. Found in: " + ", ".join(hits))
    else:
        note("no workflow or composite action carries a copy of the "
             "cost-line formatter; all consume the composite's cost-line "
             "output")


CASES = [
    case_healthy_transcript_emits_a_valid_record,
    case_missing_transcript_degrades,
    case_empty_transcript_degrades,
    case_unparseable_transcript_degrades,
    case_repeated_invocation_in_one_job_gets_distinct_record_keys,
    case_cost_line_formatter_has_exactly_one_home,
]


def run_suite():
    global failures
    failures = []
    for case in CASES:
        case()
    return list(failures)


# --- mutation check ---------------------------------------------------------
# Proves the suite can fail for the reason it exists: if step_index ever
# stopped being part of record_key, this file's whole point (T061 — "neither
# record overwriting the other") would be silently lost.
MUTATION_LABEL = "record_key drops step_index (records collide across a job's repeated invocations)"


def mutate(script):
    return script.replace(
        'RECORD_KEY="${RUN_ID}:${JOB_KEY}:${STEP_INDEX}"',
        'RECORD_KEY="${RUN_ID}:${JOB_KEY}"')


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    real = run_suite()
    if real:
        print(f"{len(real)} failure(s) against the shipped action.")
        return 1

    global SCRIPT, MUTATING
    original = SCRIPT
    mutated = mutate(original)
    if mutated == original:
        print(f"::error file={ACTION}::this gate's mutation no longer "
              f"changes the script — the code it keys on has been "
              f"rewritten. Re-point it at the current implementation.")
        return 1

    MUTATING = True
    SCRIPT = mutated
    caught = run_suite()
    SCRIPT = original
    MUTATING = False
    mutation_failed = False
    if not caught:
        print(f"::error file={ACTION}::mutation {MUTATION_LABEL!r} was NOT "
              f"caught — the suite passed against a knowingly broken "
              f"script, so its green verdict on the real one means nothing.")
        mutation_failed = True
    else:
        print(f"note: mutation caught ({MUTATION_LABEL}): {len(caught)} "
              f"case(s) failed as intended")

    residual = run_suite()
    if residual:
        print(f"::error::gate left the script mutated; {len(residual)} "
              f"failure(s) on the re-run.")
        mutation_failed = True

    print(f"verify-metrics-summary-record-emission: {len(CASES)} case(s) "
          f"checked; {'mutation caught' if not mutation_failed else 'FAILED'}.")
    return 1 if mutation_failed else 0


if __name__ == "__main__":
    sys.exit(main())
