#!/usr/bin/env python3
"""Validate a board-loop review finding against
board-review-finding.schema.json (specs/057-autonomous-board-loop,
contracts/review-and-findings.md, research.md D11).

WHY THIS EXISTS
---------------
The reviewer's fenced `wing-commander-review-findings` block is agent
output, never trusted directly (FR-028/FR-031): each entry is validated
here before it can drive a fixer follow-up commit or an out-of-scope
filing. A malformed entry is dropped and logged, never defaulted or
guessed (matching spec 056's D5/D11 discipline).

Distinct from `.github/schemas/stage-finding.schema.json`
(verify-stage-finding-schema.py): this schema's items carry an additional
required field, `in_scope`, the datum FR-033's open-finding count is
computed from without parsing prose (research.md D11). This validator is a
small hand-written checker (D5-style, no third-party JSON Schema library)
that walks the checked-in schema document itself at import time, so the
schema and the checker cannot drift apart the way a second literal could.

WHAT IT COVERS
--------------
Just enough of JSON Schema draft 2020-12 to express this one document:
object (required/additionalProperties/properties), array
(minItems/items), and string (maxLength). Not a general-purpose validator.
"""
import argparse
import glob
import json
import os
import re
import sys

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "schemas",
    "board-review-finding.schema.json")

with open(SCHEMA_PATH, encoding="utf-8") as _fh:
    SCHEMA = json.load(_fh)
ITEM_SCHEMA = SCHEMA["items"]


def _validate_string(value, spec, where):
    if not isinstance(value, str):
        return "{0} must be a string, got {1}".format(where, type(value).__name__)
    max_length = spec.get("maxLength")
    if max_length is not None and len(value) > max_length:
        return "{0} must be at most {1} character(s) long".format(where, max_length)
    pattern = spec.get("pattern")
    if pattern is not None and re.search(pattern, value) is None:
        return "{0} does not match the required pattern {1!r}".format(where, pattern)
    return None


def _validate_boolean(value, where):
    if not isinstance(value, bool):
        return "{0} must be a boolean, got {1}".format(where, type(value).__name__)
    return None


def _validate_array(value, spec, where):
    if not isinstance(value, list):
        return "{0} must be an array, got {1}".format(where, type(value).__name__)
    min_items = spec.get("minItems")
    if min_items is not None and len(value) < min_items:
        return "{0} must have at least {1} item(s), got {2}".format(
            where, min_items, len(value))
    items_spec = spec.get("items")
    if items_spec is not None:
        for i, item in enumerate(value):
            err = _validate_value(item, items_spec, "{0}[{1}]".format(where, i))
            if err:
                return err
    return None


def _validate_object(value, spec, where):
    if not isinstance(value, dict):
        return "{0} must be an object, got {1}".format(where, type(value).__name__)
    for field in spec.get("required", []):
        if field not in value:
            return "{0}.{1} is missing".format(where, field)
    properties = spec.get("properties", {})
    if spec.get("additionalProperties") is False:
        extra = sorted(set(value.keys()) - set(properties.keys()))
        if extra:
            return "{0} has field(s) not allowed by the schema: {1}".format(where, extra)
    for field, field_spec in properties.items():
        if field in value:
            err = _validate_value(value[field], field_spec, "{0}.{1}".format(where, field))
            if err:
                return err
    return None


def _validate_value(value, spec, where):
    kind = spec.get("type")
    if kind == "object":
        return _validate_object(value, spec, where)
    if kind == "array":
        return _validate_array(value, spec, where)
    if kind == "string":
        return _validate_string(value, spec, where)
    if kind == "boolean":
        return _validate_boolean(value, where)
    return None


def validate_finding(obj):
    """-> (True, "") if `obj` conforms to board-review-finding.schema.json's
    item shape, else (False, reason) naming the first field that failed."""
    if not isinstance(obj, dict):
        return False, "finding must be a JSON object, got {0}".format(type(obj).__name__)
    err = _validate_value(obj, ITEM_SCHEMA, "finding")
    if err:
        return False, err
    return True, ""


# ----------------------------------------------------------------------------
# Self-test: one well-formed finding (validates) and one per omitted
# required field (title, what, evidence.file_paths, in_scope,
# fingerprint_basis) -- each rejected with the missing field named
# (FR-064's own bullet-5 enumeration for this gate).
# ----------------------------------------------------------------------------
FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-review-finding-schema")


def _fixture_files():
    if not os.path.isdir(FIXTURES_DIR):
        return []
    found = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.json")))
    if len(found) != 6:
        sys.exit("::error::board-review-finding-schema: expected exactly 6 "
                 "fixtures under {0}, found {1} -- a fixture was added or "
                 "removed without updating this pin.".format(FIXTURES_DIR, len(found)))
    return found


def self_test():
    bad = 0
    total = 0
    for path in _fixture_files():
        total += 1
        name = os.path.basename(path)
        expect_valid = name.startswith("valid-")
        with open(path, encoding="utf-8") as fh:
            finding = json.load(fh)
        ok, reason = validate_finding(finding)
        if expect_valid and not ok:
            bad += 1
            print("[FAIL] {0}: expected valid, got: {1}".format(name, reason))
        elif not expect_valid and ok:
            bad += 1
            print("[FAIL] {0}: expected rejection, but validated cleanly".format(name))
        else:
            print("[ok] {0}: {1}".format(
                name, "valid" if ok else "rejected ({0})".format(reason)))
    if total == 0:
        print("[FAIL] no fixtures found under {0}".format(FIXTURES_DIR))
        return 1
    print("verify-board-review-finding-schema self-test: {0}/{1} fixtures "
          "behaved as specified.".format(total - bad, total))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate a board-loop review finding against "
                    "board-review-finding.schema.json")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    files = args.files
    if not files:
        print("usage: verify-board-review-finding-schema.py <finding.json> "
              "[...] | --self-test", file=sys.stderr)
        return 2
    failures = 0
    for path in files:
        with open(path, encoding="utf-8") as fh:
            finding = json.load(fh)
        ok, reason = validate_finding(finding)
        if ok:
            print("[ok] {0}: valid".format(path))
        else:
            print("::error::{0}: {1}".format(path, reason))
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
