#!/usr/bin/env python3
"""Compare the watchdog diagnose shadow against the acting diagnose agent.

Emits the `trial` object of specs/110-haiku-5-5-tier-trial/contracts/trial-record.md.
Deterministic (Principle IX): no model call decides agreement.

Usage:
  compare-diagnose-shadow.py --baseline-findings F --baseline-verdict V
      --shadow-findings F --shadow-verdict V --shadow-refusal true|false
      --schema S [--candidate-model M]

Exit 0 for any classifiable input; exit 2 for unreadable arguments.
"""
import argparse
import json
import re
import sys

STEP = "watchdog.diagnose"
CANDIDATE = "claude-haiku-5-5"
BASELINE_LABEL = "diagnose"


def die(msg):
    print(f"compare-diagnose-shadow: {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        die(f"cannot read {what} {path}: {exc}")


def read_or_none(path):
    """The parsed JSON at `path`, or None when it is absent/unparseable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def unwrap(data, wrapped_only=False):
    """Return the findings list, or None when there is none.

    The baseline is the read-back's bare array. The shadow's result is the
    agent's own structured output, which the diagnose schema requires to be
    an object with a `findings` array (wrapped_only): a bare array misses the
    schema and is malformed, not compared."""
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        return data["findings"]
    if isinstance(data, list) and not wrapped_only:
        return data
    return None


def normalise(name):
    name = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return name.strip("-")


def class_of(finding):
    cls = finding.get("class")
    if cls == "__new__":
        return normalise(finding.get("proposedClass"))
    return cls


def signal_ids(finding):
    return frozenset(e.get("signalId") for e in finding.get("evidence") or []
                     if isinstance(e, dict))


JSON_TYPES = {"object", "array", "string", "boolean", "null", "integer",
              "number"}
SUPPORTED = {"type", "enum", "properties", "required",
             "additionalProperties", "items", "description"}


class UnsupportedSchema(Exception):
    """The schema uses a keyword, or a keyword value, this checker does not
    implement."""


def check_schema(schema, where="schema"):
    """Vet the WHOLE schema tree once, before any value is checked, so a
    constraint this checker cannot honour fails loudly on every run, not
    only on runs whose result happens to reach that node."""
    if not isinstance(schema, dict):
        raise UnsupportedSchema(f"{where} is not an object")
    extra = set(schema) - SUPPORTED
    if extra:
        raise UnsupportedSchema(f"{where}: unsupported keyword(s) {sorted(extra)}")
    types = schema.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not all(isinstance(t, str) and t in JSON_TYPES for t in types):
            raise UnsupportedSchema(f"{where}: bad type {schema['type']!r}")
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise UnsupportedSchema(f"{where}: enum is not a list")
    req = schema.get("required", [])
    if not (isinstance(req, list) and all(isinstance(k, str) for k in req)):
        raise UnsupportedSchema(f"{where}: required is not a list of names")
    if not isinstance(schema.get("additionalProperties", True), bool):
        raise UnsupportedSchema(f"{where}: additionalProperties is not a boolean")
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        raise UnsupportedSchema(f"{where}: properties is not an object")
    for key, sub in props.items():
        check_schema(sub, f"{where}.properties.{key}")
    if "items" in schema:
        check_schema(schema["items"], f"{where}.items")


def is_type(value, t):
    """JSON's types, not Python's: a bool is never a number, and 3.0 is an
    integer."""
    if isinstance(value, bool):
        return t == "boolean"
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "null": value is None,
        "number": isinstance(value, (int, float)),
        "integer": isinstance(value, int) or (
            isinstance(value, float) and value.is_integer()),
    }.get(t, False)


def json_equal(a, b):
    """Equality as JSON sees it, at every depth: 1 == 1.0, but true != 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(map(json_equal, a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return a == b


def conforms(value, schema):
    """The JSON Schema subset the diagnose schema uses -- type (one or a
    list), enum, properties, required, additionalProperties: false, items --
    applied recursively over a schema check_schema has already vetted, so
    the shadow's result is held to the whole schema the acting agent's
    --json-schema enforces, not only its enums."""
    types = schema.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(is_type(value, t) for t in types):
            return False
    if "enum" in schema and not any(json_equal(v, value) for v in schema["enum"]):
        return False
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        if any(k not in value for k in schema.get("required") or []):
            return False
        if schema.get("additionalProperties") is False and \
                any(k not in props for k in value):
            return False
        if not all(conforms(value[k], props[k]) for k in value if k in props):
            return False
    if isinstance(value, list) and "items" in schema:
        if not all(conforms(v, schema["items"]) for v in value):
            return False
    return True


def schema_valid(result, findings, schema):
    """The shadow's whole result -- the object the acting agent's
    --json-schema governs, top-level keys included, not only its findings
    array -- against the full diagnose schema, plus the comparator's own
    invariants whatever the schema says: every finding is an object whose
    evidence is a list of objects each carrying a signalId, and a `__new__`
    class names its proposedClass."""
    if not isinstance(schema, dict) or not conforms(result, schema):
        return False
    for f in findings:
        if not baseline_usable(f):
            return False
        ev = f.get("evidence")
        if not isinstance(ev, list) or not all(
                isinstance(e, dict) and "signalId" in e for e in ev):
            return False
        if f.get("class") == "__new__" and not normalise(
                f.get("proposedClass") if isinstance(f.get("proposedClass"), str) else ""):
            return False
    return True


def baseline_usable(f):
    """A finding whose class (for `__new__`, its proposedClass) and
    signalIds are strings. The schema gives class and signalId no other
    type, so a baseline 1 (or null, or a missing signalId) could never meet
    a shadow "1": comparing it would score a disagreement no model made.
    Such a baseline -- an acting result that skipped the schema -- is no
    baseline. The schema does let a `__new__` proposedClass be null, but a
    shadow finding with no proposal names no class to compare and is
    malformed (review gate round 4); the acting read-back never leaves a
    `__new__` in the baseline."""
    if not isinstance(f, dict):
        return False
    cls = f.get("class")
    if cls == "__new__":
        cls = f.get("proposedClass")
    ev = f.get("evidence") or []
    if not isinstance(cls, str) or not isinstance(ev, list):
        return False
    return all(isinstance(e, dict) and isinstance(e.get("signalId"), str)
               for e in ev)


def keys(findings):
    return {(class_of(f), signal_ids(f)) for f in findings}


def render_key(key):
    return f"{key[0]}:{','.join(sorted(str(s) for s in key[1]))}"


def trial(outcome, baseline_verdict, filing_agree=None, shared=None,
          agree=None, differing=None):
    return {
        "step": STEP,
        "candidate_model": CANDIDATE,
        "baseline_run_label": BASELINE_LABEL,
        "outcome": outcome,
        "baseline_verdict": baseline_verdict,
        "filing_agree": filing_agree,
        "class_shared": shared,
        "class_agree": agree,
        "differing_fields": differing or [],
    }


def compare(args, schema):
    bv = args.baseline_verdict
    if bv != "healthy":
        return trial("no-baseline", bv)
    if args.shadow_refusal == "true":
        return trial("refused", bv, False)
    if args.shadow_verdict == "exhausted":
        return trial("exhausted", bv, False)
    if args.shadow_verdict != "healthy":
        return trial("error", bv)
    result = read_or_none(args.shadow_findings)
    shadow = unwrap(result, wrapped_only=True)
    if shadow is None or not schema_valid(result, shadow, schema):
        return trial("malformed", bv, False)
    baseline = unwrap(read_or_none(args.baseline_findings))
    if baseline is None or not all(baseline_usable(f) for f in baseline):
        return trial("no-baseline", bv)

    bkeys, skeys = keys(baseline), keys(shadow)
    filing_agree = bkeys == skeys
    differing = sorted(render_key(k) for k in bkeys ^ skeys)

    # Class agreement over findings sharing a signalId set.
    bclass, sclass = {}, {}
    for f in baseline:
        bclass.setdefault(signal_ids(f), set()).add(class_of(f))
    for f in shadow:
        sclass.setdefault(signal_ids(f), set()).add(class_of(f))
    shared_sets = set(bclass) & set(sclass)
    agree = 0
    for sid in shared_sets:
        if bclass[sid] == sclass[sid]:
            agree += 1
        else:
            differing.append("class:" + ",".join(sorted(str(s) for s in sid)))
    differing = sorted(set(differing))
    # Equal key sets already mean equal classes on every shared signalId
    # set, so the outcome is the filing decision; the class counts are the
    # FR-017(b) statistic, accumulated over runs by trial-summary.
    outcome = "agreed" if filing_agree else "disagreed"
    return trial(outcome, bv, filing_agree, len(shared_sets), agree, differing)


def main(argv):
    p = argparse.ArgumentParser()
    for name in ("baseline-findings", "baseline-verdict", "shadow-findings",
                 "shadow-verdict", "shadow-refusal", "schema"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--candidate-model", default=CANDIDATE)
    try:
        args = p.parse_args(argv)
    except SystemExit:
        sys.exit(2)
    if args.shadow_refusal not in ("true", "false"):
        die("--shadow-refusal must be true or false")
    schema = load_json(args.schema, "schema")
    try:
        check_schema(schema)
        result = compare(args, schema)
    except UnsupportedSchema as exc:
        die(f"cannot check the shadow against this schema: {exc}")
    result["candidate_model"] = args.candidate_model
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
