#!/usr/bin/env python3
"""Gate: compare-diagnose-shadow.py classifies every trial outcome (spec 110).

Drives the comparator over one checked-in fixture per outcome (agreed,
disagreed, exhausted, malformed, error, refused, no-baseline) and fails when
any classification differs, when an outcome has no fixture, or when the
fixture file is missing. A comparator that always printed one outcome fails.

Usage: verify-compare-diagnose-shadow.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "compare-diagnose-shadow"
COMPARATOR = HERE.parent / "actions" / "_shared" / "compare-diagnose-shadow.py"
OUTCOMES = {"agreed", "disagreed", "exhausted", "malformed", "error",
            "refused", "no-baseline"}


def run_case(name, case, tmp, extra=()):
    paths = {}
    for key in ("baseline", "shadow"):
        paths[key] = Path(tmp) / f"{name}-{key}.json"
        paths[key].write_text(json.dumps(case[key]), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", str(COMPARATOR),
         "--baseline-findings", str(paths["baseline"]),
         "--baseline-verdict", case["baseline_verdict"],
         "--shadow-findings", str(paths["shadow"]),
         "--shadow-verdict", case["shadow_verdict"],
         "--shadow-refusal", case["refusal"],
         "--schema", str(FIXTURES / "schema.json"), *extra],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None, proc.stderr.strip()
    return json.loads(proc.stdout), ""


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
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print(f"compare-diagnose-shadow classifies all {len(cases)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
