#!/usr/bin/env python3
"""Gate: trial-summary.py reports the FR-017 bar from records alone (spec 110).

Builds a records.jsonl per case and checks the summary's verdict line:
meets, misses, sample too small, no-baseline runs excluded from the sample,
and a Sonnet implement record carrying a claude-haiku-5-5 per_model helper
entry NOT being counted as a Haiku lifecycle.

Usage: verify-trial-summary.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "trial-summary.py"


def shadow(outcome, agree=True):
    return {"run_label": "diagnose-shadow", "model": "claude-haiku-5-5",
            "trial": {"outcome": outcome, "filing_agree": agree,
                      "class_shared": 1,
                      "class_agree": 1 if outcome == "agreed" else 0}}


def sonnet_with_helper():
    return {"stage": "implement", "model": "claude-sonnet-5-5",
            "spec": {"issue": 7}, "emitted_at": "2026-10-01T00:00:00Z",
            "per_model": [{"model": "claude-haiku-5-5"}]}


CASES = {
    "meets": ([shadow("agreed")] * 200, "**Diagnose bar (200 compared runs): meets**", None),
    "misses": ([shadow("agreed")] * 180 + [shadow("disagreed", False)] * 20,
               "**Diagnose bar (200 compared runs): misses**", None),
    "too-small": ([shadow("agreed")] * 10, "sample too small", None),
    "no-baseline-excluded": ([shadow("agreed")] * 199 + [shadow("no-baseline")] * 50,
                             "sample too small", "Compared runs (error and no-baseline excluded): 199"),
    "helper-not-counted": ([sonnet_with_helper()], None, "| none | | | | | |"),
}


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, (records, verdict, extra) in sorted(CASES.items()):
            path = Path(tmp) / f"{name}.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n",
                            encoding="utf-8")
            proc = subprocess.run([sys.executable, "-I", str(SCRIPT),
                                   "--records", str(path)],
                                  capture_output=True, text=True, check=False)
            for want in (verdict, extra):
                if want and want not in proc.stdout:
                    failures.append(f"{name}: missing {want!r} (rc="
                                    f"{proc.returncode}) {proc.stderr[:200]}")
        missing = subprocess.run([sys.executable, "-I", str(SCRIPT), "--records",
                                  str(Path(tmp) / "absent.jsonl")],
                                 capture_output=True, text=True, check=False)
        if missing.returncode != 2:
            failures.append("a missing records file must exit 2")
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print(f"trial-summary verdicts hold for all {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
