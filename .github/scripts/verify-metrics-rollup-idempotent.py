#!/usr/bin/env python3
"""Gate — the cumulative rollup region-builder is idempotent
(specs/043-durable-metrics-record, tasks.md Phase 9 T065, FR-031b).

WHY THIS EXISTS
---------------
wing-commander-metrics-persist/action.yml's "Update cumulative rollup" step
deliberately deviates from tasks.md T035's literal description: instead of
parsing the previous rollup comment back out and appending only new lines,
it regenerates the FULL region fresh from destination-path every time,
reasoning that destination-path is already append-only and already
de-duplicated by record_key, so a fresh read can never produce a duplicate
line. That reasoning was never exercised — nothing ran the region-builder
twice over the same persisted record set and confirmed the two outputs
actually match.

This runs the SHIPPED "Update cumulative rollup" `run:` block (extracted the
same way Gate 11 and T061's gate do — no copied logic to drift out of sync)
against a stubbed `gh` (and `date`, so the region's "as of" timestamp cannot
make two genuinely-identical runs look different) and a fixed
destination-path fixture, twice in a row: once with no prior rollup comment
(POST), once with the first run's comment already in place (PATCH) — and
asserts the region content is byte-for-byte identical both times.
"""
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-metrics-persist/action.yml"
STEP_NAME = "Update cumulative rollup"
SCRIPT = find_step(ACTION, STEP_NAME)["run"]
BASH = None

failures = []

GH_STUB = """#!/usr/bin/env bash
set -uo pipefail
state="${GH_STUB_STATE:?}"
mkdir -p "$state"
if [ "${1:-}" = "api" ]; then
  shift
  method="GET"
  if [ "${1:-}" = "--method" ]; then
    method="$2"; shift 2
  fi
  shift || true
  bodyfile=""
  for a in "$@"; do
    case "$a" in
      body=@*) bodyfile="${a#body=@}" ;;
    esac
  done
  case "$method" in
    GET)
      [ -f "$state/comment-id.txt" ] && cat "$state/comment-id.txt"
      ;;
    POST)
      echo 999 > "$state/comment-id.txt"
      [ -n "$bodyfile" ] && cp "$bodyfile" "$state/comment-body.md"
      printf 'x' >> "$state/post-calls.txt"
      ;;
    PATCH)
      [ -n "$bodyfile" ] && cp "$bodyfile" "$state/comment-body.md"
      printf 'x' >> "$state/patch-calls.txt"
      ;;
  esac
  exit 0
fi
exit 0
"""

DATE_STUB = """#!/usr/bin/env bash
# Frozen so two genuinely-identical rollup runs cannot differ only by the
# region's "as of <now>" line.
echo "2026-01-01T00:00:00Z"
"""


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    print(f"::error file={ACTION}::{case}: {msg}")


def note(msg):
    print(f"note: {msg}")


def _write_exec(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def run_rollup(tmp, records_jsonl, spec_dir, issue, gh_state, stub_dir):
    """Execute the shipped rollup step once inside `tmp`; return
    (rc, region_text, comment_body_text)."""
    os.makedirs(tmp, exist_ok=True)
    dest_path = "records.jsonl"
    with open(os.path.join(tmp, dest_path), "w", encoding="utf-8") as f:
        f.write(records_jsonl)

    wc_dir = os.path.join(tmp, "wc-metrics-persist")
    os.makedirs(wc_dir, exist_ok=True)

    env = {
        "DEST_PATH": dest_path,
        "BRANCH": "metrics",
        "SPEC_DIRS": spec_dir,
        "GITHUB_REPOSITORY": "acme/wing-commander",
        "GH_TOKEN": "stub-token",
        "GH_STUB_STATE": gh_state,
        "PATH": stub_dir + os.pathsep + os.environ.get("PATH", ""),
    }
    rc, output, _outputs, _summary = run_step(BASH, SCRIPT, tmp, env, tmp)
    region_path = os.path.join(wc_dir, "rollup-region.md")
    region = None
    if os.path.exists(region_path):
        with open(region_path, encoding="utf-8") as f:
            region = f.read()
    comment_path = os.path.join(gh_state, "comment-body.md")
    comment = None
    if os.path.exists(comment_path):
        with open(comment_path, encoding="utf-8") as f:
            comment = f.read()
    return rc, output, region, comment


RECORDS = "\n".join([
    '{"schema_version":1,"spec":{"spec_dir":"specs/043-durable-metrics-record","issue":148,"identity_available":true},'
    '"stage":"implement","cost_available":true,"cost_usd":1.5,'
    '"turns":{"available":true,"counted":12},"model":"claude-sonnet-5",'
    '"run":{"record_key":"1000:cycle:0"},"emitted_at":"2026-01-01T00:00:00Z"}',
    '{"schema_version":1,"spec":{"spec_dir":"specs/043-durable-metrics-record","issue":148,"identity_available":true},'
    '"stage":"clarify","cost_available":true,"cost_usd":0.25,'
    '"turns":{"available":true,"counted":4},"model":"claude-sonnet-5",'
    '"run":{"record_key":"1001:clarify:0"},"emitted_at":"2026-01-01T00:10:00Z"}',
]) + "\n"


def case_repeat_rollup_over_the_same_records_is_byte_for_byte_stable():
    case = "repeat rollup over an unchanged record set"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-rollup-")
    stub_dir = os.path.join(tmp, "stubbin")
    os.makedirs(stub_dir, exist_ok=True)
    _write_exec(os.path.join(stub_dir, "gh"), GH_STUB)
    _write_exec(os.path.join(stub_dir, "date"), DATE_STUB)
    gh_state = os.path.join(tmp, "gh-state")
    os.makedirs(gh_state, exist_ok=True)

    try:
        rc1, out1, region1, comment1 = run_rollup(
            os.path.join(tmp, "run1"), RECORDS,
            "specs/043-durable-metrics-record", 148, gh_state, stub_dir)
        if rc1 != 0:
            fail(case, f"first run exited {rc1}: {out1.strip()[:300]}")
            return
        if region1 is None:
            fail(case, "first run wrote no rollup-region.md")
            return
        if not os.path.exists(os.path.join(gh_state, "post-calls.txt")):
            fail(case, "first run (no prior comment) should have POSTed a "
                       "new comment, but no POST call was recorded")
        if os.path.exists(os.path.join(gh_state, "patch-calls.txt")):
            fail(case, "first run should not have PATCHed — no comment "
                       "existed yet")
        if comment1 != region1:
            fail(case, "the comment body the first run posted does not "
                       "match the region it computed")

        rc2, out2, region2, comment2 = run_rollup(
            os.path.join(tmp, "run2"), RECORDS,
            "specs/043-durable-metrics-record", 148, gh_state, stub_dir)
        if rc2 != 0:
            fail(case, f"second run exited {rc2}: {out2.strip()[:300]}")
            return
        if region2 is None:
            fail(case, "second run wrote no rollup-region.md")
            return
        if not os.path.exists(os.path.join(gh_state, "patch-calls.txt")):
            fail(case, "second run (comment already exists) should have "
                       "PATCHed the existing comment, but no PATCH call was "
                       "recorded")

        if region1 != region2:
            fail(case, "the rollup region changed between two runs over the "
                       "identical persisted record set — a repeat rollup "
                       "must not duplicate or drift the cumulative summary:\n"
                       f"--- run 1 ---\n{region1}\n--- run 2 ---\n{region2}")
        if comment2 != region2:
            fail(case, "the comment body the second run PATCHed does not "
                       "match the region it computed")
        note("two rollup runs over the same persisted record set produced "
             "a byte-for-byte identical region (POST then PATCH, no "
             "duplicated history or totals)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = [case_repeat_rollup_over_the_same_records_is_byte_for_byte_stable]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    for case in CASES:
        case()
    if failures:
        print(f"{len(failures)} failure(s).")
        return 1
    print(f"verify-metrics-rollup-idempotent: {len(CASES)} case(s) checked; "
          f"all passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
