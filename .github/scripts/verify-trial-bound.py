#!/usr/bin/env python3
"""Gate: trial-bound.py stops the diagnose shadow at its bound (spec 110).

Builds a records.jsonl per checked-in fixture case and runs trial-bound.py:
unset SINCE, expiry by the 60-day window, expiry by the 300-run count,
error/no-baseline records not counted, comparator errors and undated
compared records counted (fail closed), and the enabled case. Fails when any
decision differs or the fixture file is missing.

Usage: verify-trial-bound.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "fixtures" / "trial-bound" / "cases.json"
SCRIPT = HERE.parent / "actions" / "_shared" / "trial-bound.py"


def record(outcome, day, **trial):
    rec = {"run_label": "diagnose-shadow",
           "trial": dict(trial, outcome=outcome)}
    if day is not None:
        rec["emitted_at"] = f"{day}T00:00:00Z"
    return json.dumps(rec)


def main():
    if not CASES.is_file():
        print(f"fixtures missing: {CASES}", file=sys.stderr)
        return 1
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, c in sorted(cases.items()):
            lines = [record("agreed", "2026-10-05")] * c["compared"]
            lines += [record("error", "2026-10-05"),
                      record("no-baseline", "2026-10-05")] * (c["errors"] // 2)
            lines += [record("error", "2026-10-05", error_source="comparator")
                      ] * c.get("comparator_errors", 0)
            lines += [record("agreed", None)] * c.get("undated", 0)
            # A diagnose (non-shadow) record and a pre-SINCE record never count.
            lines.append(json.dumps({"run_label": "diagnose",
                                     "trial": {"outcome": "agreed"},
                                     "emitted_at": "2026-10-05T00:00:00Z"}))
            lines.append(record("agreed", "2020-01-01"))
            path = Path(tmp) / f"{name}.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--since", c["since"],
                 "--records", str(path), "--today", c["today"]],
                capture_output=True, text=True, check=False)
            got = proc.stdout.strip()
            if proc.returncode != 0 or got != f"enabled={c['expect']}":
                failures.append(f"{name}: expected enabled={c['expect']}, got "
                                f"{got!r} rc={proc.returncode} {proc.stderr}")
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print(f"trial-bound decides all {len(cases)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
