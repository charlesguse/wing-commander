#!/usr/bin/env python3
"""Gate: trial-bound.py stops the diagnose shadow at its bound (spec 110).

Builds a records.jsonl per checked-in fixture case and runs trial-bound.py:
unset SINCE, expiry by the 60-day window, expiry by the 300-run count,
error/no-baseline records not counted, comparator errors, undated
compared records and shadow records with no trial object counted (fail
closed), and the enabled case. Fails when any
decision differs or the fixture file is missing.

Usage: verify-trial-bound.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "fixtures" / "trial-bound" / "cases.json"
SCRIPT = HERE.parent / "actions" / "_shared" / "trial-bound.py"
ACTION = HERE.parent / "actions" / "wing-commander-trial-bound" / "action.yml"


def composite_fails_loudly(tmp):
    """The composite's own step, run as shipped: a SINCE still ahead of
    today in UTC (an owner east of UTC setting their local date) must leave
    the shadow off WITH a warning, never silently (code review of #982)."""
    import yaml
    step = yaml.safe_load(ACTION.read_text(encoding="utf-8"))["runs"]["steps"][0]
    out = Path(tmp) / "gh-output"
    out.write_text("", encoding="utf-8")
    env = dict(os.environ, SINCE="2999-01-01", RECORDS_PATH=str(Path(tmp) / "none.jsonl"),
               GITHUB_OUTPUT=str(out), GITHUB_ACTION_PATH=str(ACTION.parent))
    proc = subprocess.run(["bash", "-c", step["run"]], env=env,
                          capture_output=True, text=True, check=False)
    failures = []
    if "enabled=false" not in out.read_text(encoding="utf-8"):
        failures.append("composite: a future SINCE must leave enabled=false")
    if "::warning::" not in proc.stdout:
        failures.append("composite: a SINCE it cannot honour must emit a "
                        "::warning::, not switch the trial off silently")
    return failures


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
            lines += [json.dumps({"run_label": "diagnose-shadow",
                                  "emitted_at": "2026-10-05T00:00:00Z"})
                      ] * c.get("trialless", 0)
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
        failures += composite_fails_loudly(tmp)
        # A records file that is not there cannot show the cap is unmet.
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--since", "2026-10-01",
             "--records", str(Path(tmp) / "absent.jsonl"), "--today",
             "2026-10-05"], capture_output=True, text=True, check=False)
        if proc.returncode != 2:
            failures.append("a missing records file must fail closed "
                            f"(exit 2), got rc={proc.returncode} {proc.stdout!r}")
        # An outcome that is not a string (a list, an object) is a shadow
        # record with no readable trial: counted toward the cap, never a
        # TypeError and exit 1 (review gate round 9).
        odd = Path(tmp) / "unhashable.jsonl"
        odd.write_text("\n".join([record(["error"], "2026-10-05"),
                                   record({"a": 1}, "2026-10-05"),
                                   record("error", "2026-10-05")]) + "\n",
                       encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--since", "2026-10-01",
             "--records", str(odd), "--today", "2026-10-05"],
            capture_output=True, text=True, check=False)
        if proc.returncode != 0 or proc.stdout.strip() != "enabled=true":
            failures.append("a list or object trial.outcome must be read, not "
                            f"crash: rc={proc.returncode} {proc.stderr[-200:]!r}")
        else:
            import datetime
            import importlib.util
            spec = importlib.util.spec_from_file_location("trial_bound", SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            n = mod.compared_count(str(odd), datetime.date(2026, 10, 1))
            if n != 2:
                failures.append("records whose trial.outcome is not a string "
                                f"must count toward the cap (2), got {n}")
        # A corrupt records line is named as such, never as a bad SINCE.
        bad = Path(tmp) / "corrupt.jsonl"
        bad.write_text("not json\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--since", "2026-10-01",
             "--records", str(bad), "--today", "2026-10-05"],
            capture_output=True, text=True, check=False)
        if proc.returncode != 2 or "unreadable metrics records" not in proc.stderr:
            failures.append("a corrupt records.jsonl must exit 2 naming the "
                            f"records, got rc={proc.returncode} {proc.stderr!r}")
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print(f"trial-bound decides all {len(cases)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
