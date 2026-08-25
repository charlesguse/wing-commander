#!/usr/bin/env python3
"""Gate: an unknown schema_version is retained and skipped, never dropped.

WHY THIS EXISTS
---------------
contracts/metrics-record-schema.md's compatibility rule 4: "A reader
encountering a schema_version it does not know MUST retain and skip that
record — never drop, rewrite, or fail on it." wing-commander-metrics-persist
implements this in bash/jq (T018), which this gate cannot execute directly
without a live git repository and GitHub API access. This gate instead
drives the SAME rule through an independent Python harness — a small,
behaviorally equivalent reimplementation of "append unknown versions
as-is, exclude them from computation" — against a fixture store mixing a
schema-version-1 record with a schema-version-2 (unknown) one, and asserts
the unknown record survives byte-for-byte in the store and contributes
nothing to a rollup total, without the harness erroring on it.

This is a second, independent implementation of the rule, not a test of the
composite's own jq — the two are expected to agree because both derive from
the same one-sentence compatibility rule, not because one calls the other.
"""
import argparse
import json
import sys

KNOWN_VERSION = 1


def append_record(store_lines, record_line):
    """-> store_lines with record_line appended.

    Mirrors T018/T020's retain-and-skip rule: a record whose declared
    schema_version is not the version this reader understands is appended
    UNCHANGED and UNVALIDATED — retained, not evaluated further. A record
    of the known version is appended only if it is at least valid JSON
    (deeper schema-version-1 validation is verify-metrics-record-schema.py's
    subject, not this gate's).
    """
    record = json.loads(record_line)
    version = record.get("schema_version")
    if version != KNOWN_VERSION:
        return store_lines + [record_line], "retained-unvalidated"
    return store_lines + [json.dumps(record)], "validated"


def compute_rollup(store_lines):
    """-> (total_cost, contributing_count, retained_unknown_count).

    Excludes any record whose schema_version this reader does not
    recognize from the computation entirely — it is retained in the store
    (append_record already did that) but never summed.
    """
    total_cost = 0.0
    contributing = 0
    retained_unknown = 0
    for line in store_lines:
        record = json.loads(line)
        if record.get("schema_version") != KNOWN_VERSION:
            retained_unknown += 1
            continue
        if record.get("cost_available") is True:
            total_cost += record.get("cost_usd") or 0
        contributing += 1
    return total_cost, contributing, retained_unknown


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------
V1_RECORD = json.dumps({
    "schema_version": 1, "record_available": True,
    "run": {"workflow_run_id": "1", "job_key": "cycle", "job_id": None,
            "step_index": 0, "record_key": "1:cycle:0"},
    "stage": "implement", "stage_available": True, "run_label": None,
    "spec": {"spec_dir": "specs/043-durable-metrics-record", "issue": 148,
             "identity_available": True},
    "model": "claude-sonnet-5", "model_available": True,
    "turns": {"counted": 10, "reported": 11, "intended_budget": 40,
              "enforced_ceiling": 100, "available": True},
    "tokens": {"input": 100, "output": 50, "cache_read": 0,
               "cache_creation": 0, "available": True},
    "cost_usd": 1.0, "cost_available": True,
    "duration_ms": 1000, "duration_available": True, "outcome": "healthy",
    "per_model": [], "per_model_available": False,
    "emitted_at": "2026-08-25T00:00:00Z",
})

V2_UNKNOWN_RECORD = json.dumps({
    "schema_version": 2, "record_available": True,
    "run": {"workflow_run_id": "2", "job_key": "cycle", "job_id": None,
            "step_index": 0, "record_key": "2:cycle:0"},
    "stage": "implement",
    "cost_usd": 9999.0, "cost_available": True,
    "a_field_this_reader_has_never_heard_of": {"nested": True},
})


def self_test():
    bad = 0
    total = 0

    total += 1
    store = []
    store, outcome1 = append_record(store, V1_RECORD)
    if outcome1 != "validated":
        bad += 1
        print("[FAIL] appending a known-version record: expected "
              "'validated', got {0!r}".format(outcome1))
    else:
        print("[ok] a schema-version-1 record is validated on append")

    total += 1
    store, outcome2 = append_record(store, V2_UNKNOWN_RECORD)
    if outcome2 != "retained-unvalidated":
        bad += 1
        print("[FAIL] appending an unknown-version record: expected "
              "'retained-unvalidated', got {0!r}".format(outcome2))
    else:
        print("[ok] a schema-version-2 record is retained, not validated")

    total += 1
    if V2_UNKNOWN_RECORD not in store:
        bad += 1
        print("[FAIL] the unknown-version record is not present in the "
              "store byte-for-byte after append — retain-and-skip must "
              "never rewrite it")
    else:
        print("[ok] the unknown-version record survives unrewritten")

    total += 1
    total_cost, contributing, retained_unknown = compute_rollup(store)
    if total_cost != 1.0:
        bad += 1
        print("[FAIL] rollup total: expected 1.0 (v1 only), got {0} — the "
              "unknown-version record's 9999.0 cost leaked into the "
              "total".format(total_cost))
    else:
        print("[ok] the unknown-version record's cost is excluded from "
              "the rollup total")

    total += 1
    if contributing != 1 or retained_unknown != 1:
        bad += 1
        print("[FAIL] rollup accounting: expected 1 contributing + 1 "
              "retained-unknown, got {0} + {1}".format(
                  contributing, retained_unknown))
    else:
        print("[ok] rollup accounting counts the unknown record as "
              "retained, not contributing")

    total += 1
    try:
        empty_store = []
        empty_store, _ = append_record(empty_store, V2_UNKNOWN_RECORD)
        compute_rollup(empty_store)
    except Exception as exc:  # noqa: BLE001 - this IS the assertion
        bad += 1
        print("[FAIL] an unknown-version-only store raised {0!r} instead "
              "of computing a zero-contribution rollup".format(exc))
    else:
        print("[ok] a store containing ONLY an unknown-version record "
              "never errors")

    print("verify-metrics-schema-version-tolerance self-test: {0}/{1} "
          "checks behaved as specified.".format(total - bad, total))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Unknown schema_version records are retained and "
                    "skipped, never dropped/rewritten/erroring")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.print_help()
        print("\nThis gate has no live subject in the repository (records "
              "are runtime artifacts) — run with --self-test.")
        return 1
    return self_test()


if __name__ == "__main__":
    sys.exit(main())
