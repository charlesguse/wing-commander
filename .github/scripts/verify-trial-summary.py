#!/usr/bin/env python3
"""Gate: trial-summary.py reports the FR-017 bar from records alone (spec 110).

Builds a records.jsonl per case and checks the summary's verdict line:
meets, misses, sample too small, no-baseline runs excluded from the sample,
and a Sonnet implement record carrying a claude-haiku-5-5 per_model helper
entry NOT being counted as a Haiku lifecycle. Also (review gate rounds 4-5):

* --since windows the diagnose section exactly as trial-bound.py windows
  its cap -- the same mixed record set gives the same compared count from
  both scripts, so a restarted trial is summarised over the window its
  bound closes;
* a comparator error is reported on its own line;
* wing-commander-trial-summary.yml and wing-commander-8-watchdog.yml read
  the metrics branch and path with the same defaults
  wing-commander-metrics-persist.yml writes them with, and the summary
  wrapper passes the trial's SINCE.

Usage: verify-trial-summary.py
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "trial-summary.py"
BOUND = HERE.parent / "actions" / "_shared" / "trial-bound.py"
WORKFLOWS = HERE.parent / "workflows"
PERSIST = WORKFLOWS / "wing-commander-metrics-persist.yml"
READERS = (WORKFLOWS / "wing-commander-trial-summary.yml",
           WORKFLOWS / "wing-commander-8-watchdog.yml")


def shadow(outcome, agree=True):
    return {"run_label": "diagnose-shadow", "model": "claude-haiku-5-5",
            "trial": {"outcome": outcome, "filing_agree": agree,
                      "class_shared": 1,
                      "class_agree": 1 if outcome == "agreed" else 0}}


def cycle(issue, model, label="cycle"):
    return {"stage": "implement", "model": model, "run_label": label,
            "spec": {"issue": issue}, "emitted_at": "2026-10-01T00:00:00Z",
            "cost_available": True, "cost_usd": 1.0}


def paired(run, label, model, cost, outcome=None):
    rec = {"run_label": label, "model": model, "run": {"workflow_run_id": run},
           "cost_available": True, "cost_usd": cost}
    if outcome:
        rec["trial"] = {"outcome": outcome, "filing_agree": True,
                        "class_shared": 0, "class_agree": 0}
    return rec


def sonnet_with_helper():
    return {"stage": "implement", "model": "claude-sonnet-5-5",
            "spec": {"issue": 7}, "emitted_at": "2026-10-01T00:00:00Z",
            "per_model": [{"model": "claude-haiku-5-5"}]}


def dated(rec, day):
    return dict(rec, emitted_at=f"{day}T00:00:00Z")


# A restarted trial: 50 agreed runs in an earlier window, 30 in this one,
# 5 undated (counted inside, as trial-bound counts them), and one
# comparator error (counted toward the cap, reported on its own line).
WINDOW = ([dated(shadow("agreed"), "2026-08-01")] * 50
          + [dated(shadow("agreed"), "2026-10-05")] * 30
          + [shadow("agreed")] * 5
          + [dated({"run_label": "diagnose-shadow",
                    "trial": {"outcome": "error",
                              "error_source": "comparator"}},
                   "2026-10-06")])

CASES = {
    "meets": ([shadow("agreed")] * 200, "**Diagnose bar (200 compared runs): meets**", None),
    # (b) vacuous: a meets with no shared finding says (b) went unmeasured.
    "meets-b-unmeasured": ([dict(shadow("agreed"), trial={
        "outcome": "agreed", "filing_agree": True, "class_shared": 0,
        "class_agree": 0})] * 200, "**Diagnose bar (200 compared runs): meets**",
        "Bar (b) was not measured"),
    "misses": ([shadow("agreed")] * 180 + [shadow("disagreed", False)] * 20,
               "**Diagnose bar (200 compared runs): misses**", None),
    "too-small": ([shadow("agreed")] * 10, "sample too small", None),
    "no-baseline-excluded": ([shadow("agreed")] * 199 + [shadow("no-baseline")] * 50,
                             "sample too small", "Compared runs (error and no-baseline excluded): 199"),
    "helper-not-counted": ([sonnet_with_helper()], None, "| none | | | | | |"),
    # A Sonnet lifecycle's Haiku-tier progress comment and its branch-advance
    # record are not implement cycles: it stays the Sonnet baseline.
    "progress-comment-not-counted": (
        [cycle(8, "claude-sonnet-5-5"),
         cycle(8, "claude-haiku-5-5", "progress comment"),
         cycle(8, None, "branch advance")],
        "| none | | | | | |", "median Sonnet lifecycle over 1: cycles 1"),
    # Both rows cover the compared runs only: run 2 had no shadow, run 3's
    # shadow was no-baseline (never called).
    "acting-row-paired": (
        [paired("1", "diagnose", "claude-opus-5-5", 0.08),
         paired("1", "diagnose-shadow", "claude-haiku-5-5", 0.002, "agreed"),
         paired("2", "diagnose", "claude-opus-5-5", 9.0),
         paired("3", "diagnose", "claude-opus-5-5", 0.0),
         paired("3", "diagnose-shadow", "claude-haiku-5-5", 0.0, "no-baseline")],
        "| Opus diagnose (acting, same runs) | 1 | n/a | $0.0800 |",
        "| claude-haiku-5-5 shadow (compared runs) | 1 | n/a | $0.0020 |"),
}


def load_bound():
    spec = importlib.util.spec_from_file_location("trial_bound", BOUND)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_window(tmp, failures):
    path = Path(tmp) / "window.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in WINDOW) + "\n",
                    encoding="utf-8")
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "--records",
                           str(path), "--since", "2026-10-01"],
                          capture_output=True, text=True, check=False)
    m = re.search(r"Compared runs \(error and no-baseline excluded\): (\d+)",
                  proc.stdout)
    summary_n = int(m.group(1)) if m else None
    if summary_n != 35:
        failures.append(f"window: --since 2026-10-01 must count the 35 "
                        f"in-window compared runs, got {summary_n} "
                        f"(rc={proc.returncode}) {proc.stderr[:200]}")
    import datetime
    bound_n = load_bound().compared_count(str(path),
                                          datetime.date(2026, 10, 1))
    # trial-bound also counts the comparator error toward its cap.
    if summary_n is not None and bound_n != summary_n + 1:
        failures.append(f"window: trial-summary counts {summary_n} compared "
                        f"runs but trial-bound counts {bound_n} (expected "
                        "summary + 1 comparator error): the two windows "
                        "have drifted")
    if "of which comparator errors: 1" not in proc.stdout:
        failures.append("window: a comparator error must be reported on its "
                        "own line")


def check_single_home(failures):
    """The window/label rules live only in _shared/trial-bound.py; a
    re-pasted date parse or run_label rule in trial-summary.py is the drift
    CLAUDE.md's single-home rule forbids."""
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in ("fromisoformat", '"started_at"', 'get("run_label")',
                   '{"error", "no-baseline"}'):
        if needle in text:
            failures.append(f"trial-summary.py carries its own {needle!r}: "
                            "import the rule from _shared/trial-bound.py")


def check_wrappers(failures):
    text = PERSIST.read_text(encoding="utf-8")
    want = {var: set(re.findall(r"vars\." + var + r" \|\| '([^']*)'", text))
            for var in ("WING_COMMANDER_METRICS_BRANCH",
                        "WING_COMMANDER_METRICS_PATH")}
    for var, defaults in want.items():
        if len(defaults) != 1:
            failures.append(f"{PERSIST.name}: expected one default for "
                            f"{var}, found {sorted(defaults)}")
    for reader in READERS:
        rtext = reader.read_text(encoding="utf-8")
        for var, defaults in want.items():
            got = set(re.findall(r"vars\." + var + r" \|\| '([^']*)'", rtext))
            if not got or got != defaults:
                failures.append(f"{reader.name}: {var} defaults {sorted(got)} "
                                f"differ from {PERSIST.name}'s "
                                f"{sorted(defaults)}")
    summary = READERS[0].read_text(encoding="utf-8")
    if "vars.WING_COMMANDER_DIAGNOSE_SHADOW_SINCE" not in summary \
            or "--since" not in summary:
        failures.append(f"{READERS[0].name} must pass the trial's SINCE to "
                        "trial-summary.py --since")


def main():
    failures = []
    check_wrappers(failures)
    check_single_home(failures)
    with tempfile.TemporaryDirectory() as tmp:
        check_window(tmp, failures)
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
