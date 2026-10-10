#!/usr/bin/env python3
"""Gate: compare-diagnose-shadow.py classifies every trial outcome (spec 110).

Drives the comparator over one checked-in fixture per outcome (agreed,
disagreed, exhausted, malformed, error, refused, no-baseline) and fails when
any classification differs, when an outcome has no fixture, or when the
fixture file is missing. A comparator that always printed one outcome fails.

Usage: verify-compare-diagnose-shadow.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "compare-diagnose-shadow"
COMPARATOR = HERE.parent / "actions" / "_shared" / "compare-diagnose-shadow.py"
OUTCOMES = {"agreed", "disagreed", "exhausted", "malformed", "error",
            "refused", "no-baseline"}


def run_case(name, case, tmp, extra=(), schema=None):
    """Run the comparator on one case; `schema` (a dict) replaces the
    fixture schema. Returns (trial, stderr) -- trial is None on a non-zero
    exit, and stderr then carries the exit code."""
    paths = {}
    for key in ("baseline", "shadow"):
        paths[key] = Path(tmp) / f"{name}-{key}.json"
        paths[key].write_text(json.dumps(case[key]), encoding="utf-8")
    schema_path = FIXTURES / "schema.json"
    if schema is not None:
        schema_path = Path(tmp) / f"{name}-schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", str(COMPARATOR),
         "--baseline-findings", str(paths["baseline"]),
         "--baseline-verdict", case["baseline_verdict"],
         "--shadow-findings", str(paths["shadow"]),
         "--shadow-verdict", case["shadow_verdict"],
         "--shadow-refusal", case["refusal"],
         "--schema", str(schema_path), *extra],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None, f"rc={proc.returncode} {proc.stderr.strip()}"
    return json.loads(proc.stdout), ""


TRIAL_RECORD = (Path(__file__).resolve().parent.parent / "actions"
                / "wing-commander-trial-record" / "action.yml")
ERROR_JQ = re.compile(r"""jq -cn --arg bv "\$BASELINE_VERDICT" --arg m "\$model" '([^']*)'""")


def error_shape_failures(trial):
    """wing-commander-trial-record writes the comparator-error trial itself
    (the comparator is what failed), so that jq literal is a second spelling
    of trial()'s shape: it must carry exactly the comparator's keys plus
    error_source, or a contract change lands in one and not the other."""
    m = ERROR_JQ.search(TRIAL_RECORD.read_text(encoding="utf-8"))
    if not m:
        return [f"{TRIAL_RECORD}: comparator-error trial literal not found"]
    proc = subprocess.run(["jq", "-cn", "--arg", "bv", "healthy", "--arg", "m",
                           "claude-haiku-5-5", m.group(1)],
                          capture_output=True, text=True, check=False)
    try:
        err = json.loads(proc.stdout)
    except ValueError:
        return [f"comparator-error literal does not evaluate: {proc.stderr}"]
    want = set(trial or {}) | {"error_source"}
    if set(err) != want or err.get("outcome") != "error" \
            or err.get("error_source") != "comparator":
        return ["the comparator-error trial in wing-commander-trial-record "
                f"has keys {sorted(err)}, the comparator's trial() plus "
                f"error_source is {sorted(want)}"]
    return []


WATCHDOG = Path(__file__).resolve().parent.parent / "workflows" / "watchdog.yml"
SCHEMA_JQ = re.compile(r"""--argjson sid "\$sigid_schema" '(\{.*?\})'\)"$""", re.S | re.M)


def production_schema():
    """The diagnose schema exactly as watchdog.yml's class-vocabulary step
    builds it, for a two-class vocabulary and signals s1/s2: the fixture
    schema is a stand-in, so the comparator is also checked against the
    shape it meets in Actions."""
    m = SCHEMA_JQ.search(WATCHDOG.read_text(encoding="utf-8"))
    if not m:
        return None
    proc = subprocess.run(
        ["jq", "-cn", "--argjson", "cls",
         '{"type":"string","enum":["pipeline-defect","denied-tool","__new__"]}',
         "--argjson", "sid", '{"type":"string","enum":["s1","s2"]}', m.group(1)],
        capture_output=True, text=True, check=False)
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def full(cls="pipeline-defect", **extra):
    f = {"class": cls, "description": "d",
         "evidence": [{"signalId": "s1", "source": "x", "locator": "y"}],
         "normalizedFacts": {"tool": "gh", "stage": "implement"},
         "severityHint": "minor", "alreadyHandledBy": None}
    f.update(extra)
    return f


def outcome_of(tmp, name, baseline, shadow, schema):
    trial, err = run_case(name, {"baseline": baseline, "shadow": shadow,
                                 "baseline_verdict": "healthy",
                                 "shadow_verdict": "healthy",
                                 "refusal": "false"}, tmp, schema=schema)
    return (trial or {}).get("outcome"), err


def schema_failures(tmp):
    failures = []
    prod = production_schema()
    if prod is None:
        return ["cannot build the production diagnose schema from "
                "watchdog.yml's class-vocabulary step"]
    cases = {
        "prod-agreed": ([full()], {"findings": [full()]}, "agreed"),
        "prod-missing-description": (
            [full()], {"findings": [{k: v for k, v in full().items()
                                     if k != "description"}]}, "malformed"),
        "prod-unknown-fact-key": (
            [full()], {"findings": [full(normalizedFacts={"run": "1"})]},
            "malformed"),
        "prod-evidence-without-locator": (
            [full()], {"findings": [full(evidence=[{"signalId": "s1"}])]},
            "malformed"),
    }
    f = {"class": "pipeline-defect", "evidence": [{"signalId": "s1"}]}
    typed = {"type": "object", "properties": {"findings": {"type": "array",
             "items": {"type": "object", "properties": {
                 "class": {"type": "string"},
                 "n": {"type": "integer"}, "k": {"enum": [0, 1]},
                 "evidence": {"type": "array"}}}}}}
    cases.update({
        # JSON types: 3 and 3.0 are integers, true is not; enum likewise.
        "int-ok": ([f], {"findings": [dict(f, n=3)]}, "agreed", typed),
        "int-float": ([f], {"findings": [dict(f, n=3.0)]}, "agreed", typed),
        "int-bool": ([f], {"findings": [dict(f, n=True)]}, "malformed", typed),
        "enum-bool": ([f], {"findings": [dict(f, k=True)]}, "malformed", typed),
        "enum-float": ([f], {"findings": [dict(f, k=1.0)]}, "agreed", typed),
    })
    for name, case in cases.items():
        base, shadow, want = case[:3]
        schema = case[3] if len(case) > 3 else prod
        got, err = outcome_of(tmp, name, base, shadow, schema)
        if got != want:
            failures.append(f"{name}: expected {want}, got {got} {err}")
    # A keyword, or keyword value, the checker cannot honour is a loud
    # comparator failure (exit 2) on EVERY run -- also when the shadow's
    # result never reaches that schema node (an empty findings array).
    items = prod["properties"]["findings"]["items"]
    unsupported = {
        "minItems": dict(prod, properties={"findings": dict(
            prod["properties"]["findings"], minItems=1)}),
        "deep-unvisited": dict(prod, properties={"findings": dict(
            prod["properties"]["findings"], items=dict(items, minProperties=3))}),
        "bad-type-value": dict(prod, properties={"findings": dict(
            prod["properties"]["findings"], items=dict(items, type={"a": 1}))}),
        "required-string": dict(prod, required="findings"),
        "additional-zero": dict(prod, properties={"findings": dict(
            prod["properties"]["findings"], items=dict(
                items, additionalProperties=0))}),
    }
    for name, schema in unsupported.items():
        _got, err = outcome_of(tmp, name, [], {"findings": []}, schema)
        if not err.startswith("rc=2"):
            failures.append(f"unsupported schema {name}: must exit 2, got "
                            f"{err or 'a trial'}")
    return failures


def main():
    cases_file = FIXTURES / "cases.json"
    if not cases_file.is_file():
        print(f"fixtures missing: {cases_file}", file=sys.stderr)
        return 1
    cases = json.loads(cases_file.read_text(encoding="utf-8"))
    failures = []
    for missing in sorted(OUTCOMES - {c["expect"] for c in cases.values()}):
        failures.append(f"no fixture exercises outcome {missing}")
    with tempfile.TemporaryDirectory() as tmp:
        for name, case in sorted(cases.items()):
            trial, err = run_case(name, case, tmp)
            got = (trial or {}).get("outcome")
            if got != case["expect"]:
                failures.append(f"{name}: expected {case['expect']}, got "
                                f"{got} {err}")
        # candidate_model is the record's own model (wing-commander-trial-
        # record passes it), never a hard-coded Haiku ID.
        trial, err = run_case("agreed", cases["agreed"], tmp,
                              ("--candidate-model", "claude-haiku-9-9"))
        if (trial or {}).get("candidate_model") != "claude-haiku-9-9":
            failures.append("--candidate-model must reach the trial's "
                            f"candidate_model, got {trial} {err}")
        failures += error_shape_failures(trial)
        failures += schema_failures(tmp)
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print(f"compare-diagnose-shadow classifies all {len(cases)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
