#!/usr/bin/env python3
"""Decide whether the watchdog diagnose shadow is still inside its bound.

enabled = SINCE set && today < SINCE + 60d && compared < 300
where `compared` counts records on the metrics branch with top-level
run_label == "diagnose-shadow", trial.outcome not in {error, no-baseline}
and an emitted_at date >= SINCE. See specs/110-haiku-5-5-tier-trial/
research.md D10. One kind of error does count: a trial whose
error_source is "comparator" (wing-commander-trial-record) marks a defect
in the comparator, not infrastructure, and the shadow still spent a run on
it; left out, a broken comparator would keep the shadow running for the
whole 60 days (contracts/trial-record.md). For the same reason a
diagnose-shadow record with no readable `trial` object counts.

Usage: trial-bound.py --since ISO_DATE --records records.jsonl [--today ISO_DATE]
Prints `enabled=true|false` (GITHUB_OUTPUT format). Exit 2 for an unreadable
SINCE or records file that exists but is unparseable; a missing records file
counts as zero records.
"""
import argparse
import datetime
import json
import os
import sys

WINDOW_DAYS = 60
MAX_COMPARED = 300
NOT_COUNTED = {"error", "no-baseline"}


def parse_date(text):
    return datetime.date.fromisoformat(text.strip()[:10])


def compared_count(path, since):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(f"{path}:{lineno}: record is not an object")
            # The metrics record carries run_label at the top level; the
            # contract's run.run_label spelling is accepted too.
            label = rec.get("run_label") or (rec.get("run") or {}).get("run_label")
            if label != "diagnose-shadow":
                continue
            trial = rec.get("trial")
            outcome = trial.get("outcome") if isinstance(trial, dict) else None
            # A shadow record with no readable trial object (the trial
            # merge failed) still spent a shadow run, and nothing says it
            # was infrastructure: it counts, like a comparator error, so a
            # broken trial-record step cannot hold the cap open.
            if (outcome in NOT_COUNTED
                    and trial.get("error_source") != "comparator"):
                continue
            stamp = rec.get("started_at") or rec.get("emitted_at")
            try:
                when = parse_date(stamp)
            except (AttributeError, TypeError, ValueError):
                # Fail closed: an undated compared record still counts toward
                # the cap, so the cap can never stay open past 300 real runs.
                # It cannot come from an earlier window in practice: every
                # record the persist collector accepts carries emitted_at.
                n += 1
                continue
            if when >= since:
                n += 1
    return n


def decide(since_text, records, today):
    if not since_text or not since_text.strip():
        return False
    since = parse_date(since_text)
    if since > today:
        raise ValueError(f"SINCE {since} is in the future")
    if today >= since + datetime.timedelta(days=WINDOW_DAYS):
        return False
    return compared_count(records, since) < MAX_COMPARED


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="")
    p.add_argument("--records", required=True)
    p.add_argument("--today", default="")
    args = p.parse_args(argv)
    try:
        today = parse_date(args.today) if args.today else datetime.datetime.now(
            datetime.timezone.utc).date()
        enabled = decide(args.since, args.records, today)
    except ValueError as exc:
        print(f"trial-bound: unreadable date: {exc}", file=sys.stderr)
        return 2
    print(f"enabled={'true' if enabled else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
