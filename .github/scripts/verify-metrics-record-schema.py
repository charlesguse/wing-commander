#!/usr/bin/env python3
"""Gate: agent run metrics records conform to schema version 1.

WHY THIS EXISTS
---------------
specs/043-durable-metrics-record's whole durability story rests on one
invariant: every record wing-commander-metrics-summary emits, and every
record wing-commander-metrics-persist accepts, has the shape
contracts/metrics-record-schema.md documents. Nothing enforces that by
construction — the composite actions build/read the shape in bash/jq, which
has no schema of its own. This gate is the independent, structural check
that the documented shape is actually enforceable: a well-formed record
validates, a record missing/mistyping/renaming a required field is rejected
and named, and the per_model sum invariant is checked, not just present.

This does not run against a live record — none is checked into the
repository, and none should be (records are runtime artifacts). Its subject
is the checked-in fixture set under
.github/scripts/fixtures/metrics-record-schema/: the positive fixture must
always validate (catching schema/fixture drift), and --self-test drives every
fixture (positive and negative) through the validator, asserting each is
accepted or rejected for the reason it exists to demonstrate.

WHAT IT CHECKS
--------------
Field presence and type against contracts/metrics-record-schema.md's field
table (schema_version 1 only — an unknown version is out of scope for this
gate; see verify-metrics-schema-version-tolerance.py), and the per_model sum
invariant when both tokens.available and per_model_available are true.

WHY THE FIELD SETS ARE CROSS-CHECKED AGAINST THE DOC (MF-F3)
--------------------------------------------------------------
The REQUIRED_* maps below are hand-maintained, not parsed from the contract
directly — a single JSON example cannot express a field's full type union
(neither of the doc's two examples ever shows `stage` as null, though
`stage_available: false` makes that a legal record). Left at that, the doc's
lint-workflows.yml path trigger (PR #267 review) buys a trigger and no
check: editing the "## Shape" block — adding, removing, or renaming a
field — reruns this gate, but nothing in it ever reads the doc, so nothing
would fail. check_fields_match_contract() closes that gap the other way: it
parses the doc's "## Shape" JSON block and asserts its key set, at every
level, is EXACTLY the REQUIRED_* maps' key set. A field added/removed/
renamed in the doc without updating the map fails loudly here, naming the
mismatch, instead of the map silently drifting from the contract it claims
to enforce.
"""
import argparse
import glob
import json
import os
import re
import sys

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "metrics-record-schema")

CONTRACT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "specs", "043-durable-metrics-record", "contracts",
    "metrics-record-schema.md")

REQUIRED_TOP = {
    "schema_version": int,
    "record_available": bool,
    "run": dict,
    "stage": (str, type(None)),
    "stage_available": bool,
    "run_label": (str, type(None)),
    "spec": dict,
    "model": (str, type(None)),
    "model_available": bool,
    "turns": dict,
    "tokens": dict,
    "cost_usd": (int, float, type(None)),
    "cost_available": bool,
    "duration_ms": (int, float, type(None)),
    "duration_available": bool,
    "outcome": str,
    "per_model": list,
    "per_model_available": bool,
    "emitted_at": str,
}
REQUIRED_RUN = {
    "workflow_run_id": str,
    "job_key": str,
    "job_id": (str, int, type(None)),
    "step_index": int,
    "record_key": str,
}
REQUIRED_SPEC = {
    "spec_dir": (str, type(None)),
    "issue": (int, type(None)),
    "identity_available": bool,
}
REQUIRED_TURNS = {
    "counted": (int, type(None)),
    "reported": (int, type(None)),
    "intended_budget": (int, type(None)),
    "enforced_ceiling": (int, type(None)),
    "available": bool,
}
REQUIRED_TOKENS = {
    "input": (int, type(None)),
    "output": (int, type(None)),
    "cache_read": (int, type(None)),
    "cache_creation": (int, type(None)),
    "available": bool,
}
PER_MODEL_FIELD_TYPES = {
    "model": str,
    "input_tokens": (int, float),
    "output_tokens": (int, float),
    "cache_read_tokens": (int, float),
    "cache_creation_tokens": (int, float),
    "cost_usd": (int, float),
}


def _check_fields(obj, spec, where, failures):
    if not isinstance(obj, dict):
        failures.append("{0} is not an object".format(where))
        return
    for field, types in spec.items():
        if field not in obj:
            failures.append("{0}.{1} is missing".format(where, field))
            continue
        if not isinstance(types, tuple):
            types = (types,)
        # bool is a subclass of int in Python; a field typed strictly `bool`
        # must not accept an int, and vice versa, or a renamed/miscoded
        # `record_available: 1` would pass as "boolean enough".
        value = obj[field]
        ok = False
        for t in types:
            if t is bool:
                ok = ok or isinstance(value, bool)
            elif t is int:
                ok = ok or (isinstance(value, int) and not isinstance(value, bool))
            else:
                ok = ok or isinstance(value, t)
        if not ok:
            failures.append(
                "{0}.{1} has the wrong type: expected {2}, got {3}".format(
                    where, field, types, type(value).__name__))


def validate_record(record):
    """-> list of failure strings; empty means valid schema-version-1 shape."""
    failures = []
    if not isinstance(record, dict):
        return ["record is not a JSON object"]
    if record.get("schema_version") != 1:
        return ["schema_version is not 1 — not this gate's subject "
                "(verify-metrics-schema-version-tolerance.py covers "
                "unknown versions)"]
    _check_fields(record, REQUIRED_TOP, "record", failures)
    if isinstance(record.get("run"), dict):
        _check_fields(record["run"], REQUIRED_RUN, "record.run", failures)
    if isinstance(record.get("spec"), dict):
        _check_fields(record["spec"], REQUIRED_SPEC, "record.spec", failures)
    if isinstance(record.get("turns"), dict):
        _check_fields(record["turns"], REQUIRED_TURNS, "record.turns", failures)
    if isinstance(record.get("tokens"), dict):
        _check_fields(record["tokens"], REQUIRED_TOKENS, "record.tokens", failures)

    per_model = record.get("per_model")
    if isinstance(per_model, list):
        for i, entry in enumerate(per_model):
            _check_fields(entry, PER_MODEL_FIELD_TYPES,
                          "record.per_model[{0}]".format(i), failures)

    # The invariant (contracts/metrics-record-schema.md): only checked when
    # both flags claim the numbers are comparable at all.
    tokens = record.get("tokens") if isinstance(record.get("tokens"), dict) else {}
    if (tokens.get("available") is True and record.get("per_model_available") is True
            and isinstance(per_model, list) and not failures):
        sums = {
            "input_tokens": "input",
            "output_tokens": "output",
            "cache_read_tokens": "cache_read",
            "cache_creation_tokens": "cache_creation",
        }
        for pm_field, tok_field in sums.items():
            total = sum(entry.get(pm_field, 0) for entry in per_model)
            expected = tokens.get(tok_field)
            if expected is not None and total != expected:
                failures.append(
                    "per_model sum mismatch: sum(per_model[].{0})={1} != "
                    "tokens.{2}={3}".format(pm_field, total, tok_field, expected))
        cost_total = sum(entry.get("cost_usd", 0) for entry in per_model)
        cost_expected = record.get("cost_usd")
        if (record.get("cost_available") is True and cost_expected is not None
                and abs(cost_total - cost_expected) > 1e-9):
            failures.append(
                "per_model sum mismatch: sum(per_model[].cost_usd)={0} != "
                "cost_usd={1}".format(cost_total, cost_expected))
    return failures


# ----------------------------------------------------------------------------
# Contract cross-check (MF-F3)
# ----------------------------------------------------------------------------
SHAPE_HEADING_RE = re.compile(r"^## Shape\s*$", re.M)
JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def _load_contract_shape():
    """The doc's "## Shape" example, parsed — the first ```json fence
    after that heading (not the "Degraded record" example further down,
    which shares the same field names but nulls several values)."""
    with open(CONTRACT_PATH, encoding="utf-8") as handle:
        text = handle.read()
    heading = SHAPE_HEADING_RE.search(text)
    if not heading:
        sys.exit("::error file={0}::verify-metrics-record-schema: no "
                  "'## Shape' heading found — this gate's contract "
                  "cross-check has nothing to read.".format(CONTRACT_PATH))
    fence = JSON_FENCE_RE.search(text, heading.end())
    if not fence:
        sys.exit("::error file={0}::verify-metrics-record-schema: no "
                  "```json fence found after '## Shape' — this gate's "
                  "contract cross-check has nothing to parse.".format(CONTRACT_PATH))
    try:
        return json.loads(fence.group(1))
    except ValueError as exc:
        sys.exit("::error file={0}::verify-metrics-record-schema: the "
                  "'## Shape' example is not valid JSON: {1}".format(CONTRACT_PATH, exc))


def check_fields_match_contract():
    """Every REQUIRED_* map's key set must exactly match the doc's "##
    Shape" example at the same level — the check that makes editing the
    doc without updating the map fail loudly, per this file's module
    docstring."""
    shape = _load_contract_shape()
    levels = [
        ("record", REQUIRED_TOP, shape),
        ("record.run", REQUIRED_RUN, shape.get("run", {})),
        ("record.spec", REQUIRED_SPEC, shape.get("spec", {})),
        ("record.turns", REQUIRED_TURNS, shape.get("turns", {})),
        ("record.tokens", REQUIRED_TOKENS, shape.get("tokens", {})),
    ]
    per_model_shape = shape.get("per_model") or [{}]
    levels.append(("record.per_model[]", PER_MODEL_FIELD_TYPES, per_model_shape[0]))

    failures = []
    for where, required, doc_obj in levels:
        doc_fields = set(doc_obj.keys())
        gate_fields = set(required.keys())
        missing_from_gate = doc_fields - gate_fields
        missing_from_doc = gate_fields - doc_fields
        if missing_from_gate:
            failures.append(
                "{0}: {1}'s '## Shape' example has field(s) this gate "
                "does not check: {2} — add them to verify-metrics-record-"
                "schema.py's REQUIRED_* map or the doc and the gate have "
                "drifted apart".format(where, CONTRACT_PATH, sorted(missing_from_gate)))
        if missing_from_doc:
            failures.append(
                "{0}: this gate requires field(s) {1} that {2}'s '## "
                "Shape' example no longer has — the doc and the gate "
                "have drifted apart".format(where, sorted(missing_from_doc), CONTRACT_PATH))
    return failures


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _fixture_files():
    if not os.path.isdir(FIXTURES_DIR):
        return []
    return sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))


def self_test():
    bad = 0
    total = 0
    contract_failures = check_fields_match_contract()
    for f in contract_failures:
        print("[FAIL] contract cross-check: {0}".format(f))
        bad += 1
    for path in _fixture_files():
        total += 1
        name = os.path.basename(path)
        expect_valid = "invalid" not in name and "bad" not in name
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError) as exc:
            print("[FAIL] {0}: could not read/parse fixture: {1}".format(name, exc))
            bad += 1
            continue
        failures = validate_record(record)
        if expect_valid and failures:
            bad += 1
            print("[FAIL] {0}: expected valid, got: {1}".format(
                name, "; ".join(failures)))
        elif not expect_valid and not failures:
            bad += 1
            print("[FAIL] {0}: expected rejection, but validated cleanly".format(name))
        else:
            print("[ok] {0}: {1}".format(
                name, "valid" if not failures else "rejected ({0})".format(
                    failures[0])))
    if total == 0:
        print("[FAIL] no fixtures found under {0}".format(FIXTURES_DIR))
        return 1
    fixture_bad = bad - len(contract_failures)
    print("verify-metrics-record-schema self-test: {0}/{1} fixtures behaved "
          "as specified; contract cross-check {2}.".format(
              total - fixture_bad, total,
              "passed" if not contract_failures else "FAILED"))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate agent run metrics records against "
                    "contracts/metrics-record-schema.md")
    parser.add_argument("files", nargs="*",
                        help="record JSON file(s) to validate; default is "
                             "the checked-in positive fixture")
    parser.add_argument("--self-test", action="store_true",
                        help="run every fixture (positive and negative) and "
                             "assert each behaves as its name claims")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    contract_failures = check_fields_match_contract()
    for f in contract_failures:
        print("::error::verify-metrics-record-schema: contract cross-check: {0}".format(f))

    files = args.files
    if not files:
        files = [p for p in _fixture_files()
                 if "invalid" not in os.path.basename(p)
                 and "bad" not in os.path.basename(p)]
        if not files:
            print("::error::verify-metrics-record-schema: no positive "
                  "fixture found under {0}".format(FIXTURES_DIR))
            return 1

    failures_total = len(contract_failures)
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError) as exc:
            print("::error::verify-metrics-record-schema: {0}: could not "
                  "read/parse: {1}".format(path, exc))
            failures_total += 1
            continue
        failures = validate_record(record)
        if failures:
            failures_total += len(failures)
            for f in failures:
                print("::error::verify-metrics-record-schema: {0}: {1}".format(
                    path, f))
        else:
            print("verify-metrics-record-schema: {0}: valid".format(path))
    return 1 if failures_total else 0


if __name__ == "__main__":
    sys.exit(main())
