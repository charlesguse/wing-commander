#!/usr/bin/env python3
"""Validate a stage finding proposal against stage-finding.schema.json.

WHY THIS EXISTS
---------------
specs/056-stage-found-defect-filing (FR-008/FR-009): an agent stage
proposes a finding in its own final message or structured result, and the
deterministic wing-commander-stage-findings composite is the only thing
that may decide whether it gets filed — never the agent. That decision
starts here: a proposal missing a required field, mistyping one, or
carrying `evidence.file_paths: []` is dropped whole, with a reason, never
defaulted or guessed.

`.github/schemas/stage-finding.schema.json` is the checked-in authority a
reviewer reads. This validator is a small hand-written checker rather than
a third-party JSON Schema library dependency (research.md D5, matching
verify-metrics-record-schema.py's existing hand-checked pattern) — but
unlike that gate's REQUIRED_* maps, this one does not hand-duplicate the
schema's required-field/type list as a second literal: it walks the
checked-in schema document itself at import time, so the schema and the
checker cannot drift apart the way a second literal could.

WHAT IT COVERS
--------------
Just enough of JSON Schema draft 2020-12 to express this one document:
object (required/additionalProperties/properties), array
(minItems/items), and string (minLength). Not a general-purpose
validator — stage-finding.schema.json is the only subject, and if that
document ever needs a keyword this does not understand, it needs to grow
here deliberately, not silently accept whatever it cannot check.

Used by wing-commander-stage-findings/action.yml's validation step at
runtime, and directly by wing-commander-stage-findings/tests/run-tests.sh's
fixtures (FR-030), including the case that `evidence.file_paths: []` is
rejected rather than passed through with an empty list.
"""
import json
import os
import sys

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "schemas",
    "stage-finding.schema.json")

with open(SCHEMA_PATH, encoding="utf-8") as _fh:
    SCHEMA = json.load(_fh)


def _validate_string(value, spec, where):
    if not isinstance(value, str):
        return "{0} must be a string, got {1}".format(where, type(value).__name__)
    min_length = spec.get("minLength")
    if min_length is not None and len(value) < min_length:
        return "{0} must be at least {1} character(s) long".format(where, min_length)
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
    return None


def validate_finding(obj):
    """-> (True, "") if `obj` conforms to stage-finding.schema.json, else
    (False, reason) naming the first field that failed."""
    if not isinstance(obj, dict):
        return False, "finding must be a JSON object, got {0}".format(type(obj).__name__)
    err = _validate_value(obj, SCHEMA, "finding")
    if err:
        return False, err
    return True, ""


def main():
    files = sys.argv[1:]
    if not files:
        print("usage: verify-stage-finding-schema.py <finding.json> [...]", file=sys.stderr)
        return 2
    failures = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                finding = json.load(fh)
        except (OSError, ValueError) as exc:
            print("::error::{0}: could not read/parse: {1}".format(path, exc))
            failures += 1
            continue
        ok, reason = validate_finding(finding)
        if ok:
            print("[ok] {0}: valid".format(path))
        else:
            print("::error::{0}: {1}".format(path, reason))
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
