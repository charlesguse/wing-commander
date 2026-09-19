#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: turn budget" step
# (id: collect-turn-budget) — specs/046-watchdog-supervision-collectors,
# contracts/gate-coverage-046.md's verify-turn-budget-collector.sh row.
#
# FILTER below is EXTRACTED from watchdog.yml's live TURN_BUDGET_FILTER at
# run time (wc_shell_harness.extract_quoted_var), not a hand-typed copy —
# mutation testing found a hand copy here stayed green through a shipped
# critical-band-condition break (constitution VIII). This is the
# self-contained function of (this run's own metrics record, the stage's
# recent history, the two thresholds) the live collect-turn-budget step
# evaluates. No live watchdog run or gh/git call is needed: this feeds
# fixture inputs directly and asserts the per-run signal and severity band
# the collector would compute (SC-002).
#
# Usage: .github/scripts/verify-turn-budget-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-turn-budget-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-turn-budget-collector: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-turn-budget-collector: jq and python3 are both required."
  exit 1
fi

FILTER="$(python3 - <<'PY'
import sys
sys.path.insert(0, ".github/scripts")
from wc_shell_harness import extract_quoted_var
print(extract_quoted_var(".github/workflows/watchdog.yml", "TURN_BUDGET_FILTER"))
PY
)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

run_filter() {
  jq -c "$FILTER" <<<"$1"
}

# ── Fixture 1 (positive, critical): three consecutive at-or-over-budget
#    runs (185, 300, 400 against budget 180) whose max consumed-ceiling-
#    fraction (400/450 = 0.889) also crosses the 0.6 climb trigger — both
#    conditions met in the same window (research.md R4's three-value
#    ladder).
critical_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":400,"intended":180,"ceiling":450},"history":[{"run":"r1","counted":185,"intended":180,"ceiling":450},{"run":"r2","counted":300,"intended":180,"ceiling":450}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$critical_in")"
note "critical fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "critical" ]; then
  reason "climbing history (185,300,400 vs budget 180, ceiling 450) expected band 'critical', got '$band'"
else
  note "climbing history correctly produced band 'critical'"
fi
per_run_frac="$(jq -r '."per-run".facts."consumed-ceiling-fraction"' <<<"$out")"
if [ "$per_run_frac" != "0.889" ]; then
  reason "per-run consumed-ceiling-fraction expected 0.889 for 400/450, got '$per_run_frac'"
fi
# T041: the per-run signal's own facts.band must match this window's band —
# it is what Stamp signal ids now keys the per-run signal's identity on
# ({stage, band}, not {stage, run}), so the two signals a Finding cites
# together must agree on the same value.
per_run_band="$(jq -r '."per-run".facts.band // "null"' <<<"$out")"
if [ "$per_run_band" != "critical" ]; then
  reason "per-run signal's facts.band expected 'critical' to match the trend band, got '$per_run_band'"
else
  note "per-run signal's facts.band correctly matches the trend band 'critical'"
fi

# ── Fixture 2 (positive, watch): three consecutive at-or-over-budget runs
#    but a high ceiling keeps the consumed fraction low — consecutive
#    trigger alone met.
watch_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":200,"intended":180,"ceiling":2000},"history":[{"run":"r1","counted":185,"intended":180,"ceiling":2000},{"run":"r2","counted":190,"intended":180,"ceiling":2000}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$watch_in")"
note "watch fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "watch" ]; then
  reason "three consecutive at-or-over-budget runs under a high ceiling expected band 'watch', got '$band'"
else
  note "consecutive-only history correctly produced band 'watch'"
fi
per_run_band="$(jq -r '."per-run".facts.band // "null"' <<<"$out")"
if [ "$per_run_band" != "watch" ]; then
  reason "per-run signal's facts.band expected 'watch' to match the trend band, got '$per_run_band'"
else
  note "per-run signal's facts.band correctly matches the trend band 'watch'"
fi

# ── Fixture 3 (positive, elevated): the climb-fraction trigger alone met
#    (one run at 280/300 = 0.933), but the trailing (most recent) run is
#    under budget, so the consecutive count is 0.
elevated_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":90,"intended":180,"ceiling":300},"history":[{"run":"r1","counted":100,"intended":180,"ceiling":300},{"run":"r2","counted":280,"intended":180,"ceiling":300}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$elevated_in")"
note "elevated fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "elevated" ]; then
  reason "a lone high-fraction run (280/300) with no trailing consecutive run expected band 'elevated', got '$band'"
else
  note "climb-only history correctly produced band 'elevated'"
fi
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "own run 90/180 is under budget and must not emit a per-run signal, got $per_run"
else
  note "under-budget own run correctly emitted no per-run signal"
fi

# ── Fixture 4 (negative, under both thresholds): comfortably under budget
#    the whole window — no cross-run signal at all (Acceptance Scenario 6).
none_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":120,"intended":180,"ceiling":500},"history":[{"run":"r1","counted":100,"intended":180,"ceiling":500},{"run":"r2","counted":110,"intended":180,"ceiling":500}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$none_in")"
note "under-threshold fixture output: $out"
trend="$(jq -c '.trend' <<<"$out")"
if [ "$trend" != "null" ]; then
  reason "a window comfortably under both thresholds must emit no cross-run signal, got $trend"
else
  note "under-threshold history correctly emitted no cross-run signal"
fi
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "own run 120/180 is under budget and must not emit a per-run signal, got $per_run"
else
  note "under-budget own run correctly emitted no per-run signal"
fi

# ── Fixture 5 (negative, turns.available: false): no per-run signal, and
#    the collector still reports outcome "ok" (Acceptance Scenario 7) — the
#    outcome itself is a bash-level concern outside this filter, so this
#    assertion covers the filter's own half of that contract: available:
#    false must never synthesize a per-run signal from stale counted/intended
#    values.
unavailable_in='{"stage":"implement","run":"r3","own":{"available":false,"counted":226,"intended":180,"ceiling":450},"history":[],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$unavailable_in")"
note "turns.available:false fixture output: $out"
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "turns.available: false must produce no per-run signal even when counted >= intended, got $per_run"
else
  note "turns.available: false correctly produced no per-run signal"
fi

# ── Fixture 6 (boundary): counted-turns EQUALS intended-budget exactly
#    (180 == 180, no prior history) — the per-run gate is `counted >=
#    intended`, so the boundary itself, not just strictly-over, must emit.
boundary_counted_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":180,"intended":180,"ceiling":450},"history":[],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$boundary_counted_in")"
note "counted==intended boundary fixture output: $out"
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" = "null" ]; then
  reason "counted-turns exactly equal to intended-budget (180 == 180) must still emit a per-run signal ('>=', not '>'), got null"
else
  note "counted-turns exactly equal to intended-budget correctly emitted a per-run signal"
fi

# ── Fixture 7 (boundary): the window's max consumed-ceiling-fraction lands
#    on EXACTLY climb_fraction (0.6), isolated from the consecutive trigger
#    (both contributing runs are individually under their own budget, so
#    consecutive stays 0) — the climb gate is `max_frac >= climb_fraction`,
#    so the boundary itself must still produce band "elevated".
boundary_climb_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":100,"intended":500,"ceiling":1000},"history":[{"run":"r1","counted":300,"intended":500,"ceiling":500}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$boundary_climb_in")"
note "climb_fraction==0.6 boundary fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
max_frac="$(jq -r '.trend."max-consumed-ceiling-fraction" // "null"' <<<"$out")"
if [ "$max_frac" != "0.6" ]; then
  reason "boundary fixture expected max-consumed-ceiling-fraction exactly 0.6, got '$max_frac' (fixture no longer isolates the climb boundary)"
elif [ "$band" != "elevated" ]; then
  reason "a window whose max consumed-ceiling-fraction lands exactly on climb_fraction (0.6 >= 0.6) must produce band 'elevated' ('>=', not '>'), got '$band'"
else
  note "max-consumed-ceiling-fraction exactly at climb_fraction correctly produced band 'elevated'"
fi

# ── Note on the skipped/cancelled fixture (attribution invariant, FR-004):
#    that guard is a bash-level `case "$RUN_CONCLUSION" in skipped|cancelled)`
#    exit-0 before this filter is ever invoked (mirrors every other
#    collector's attribution guard in watchdog.yml) — there is no filter
#    input to construct for it, so it is verified by inspecting the shipped
#    step directly rather than by feeding this filter a fixture that could
#    never reach it in production.
if [ -f ".github/workflows/watchdog.yml" ]; then
  if grep -A3 'id: collect-turn-budget' .github/workflows/watchdog.yml | grep -q 'continue-on-error: true'; then
    note "collect-turn-budget step present with continue-on-error: true"
  fi
  if grep -A40 'id: collect-turn-budget' .github/workflows/watchdog.yml | grep -q 'skipped|cancelled'; then
    note "collect-turn-budget carries the skipped|cancelled attribution guard"
  else
    reason "collect-turn-budget no longer carries a skipped|cancelled attribution guard (FR-004)"
  fi
else
  reason "cannot find .github/workflows/watchdog.yml to verify the attribution guard — run this from the repository root"
fi

# ── Regression (maintainer review of #354): a metrics-record-branch-advance
#    artifact (specs/050-branch-drift-sha-baseline, deliberately
#    transcript-less — turns.available:false) sorts before
#    metrics-record-cycle in glob order. Selecting the first downloaded
#    record instead of the named cycle/retry/progress artifact would let it
#    silently shadow the real record and skip turn-budget coverage for
#    every run that also emits one. Runs the REAL shipped step end-to-end
#    (wc_shell_harness), not just TURN_BUDGET_FILTER above, since the
#    selection bug lives in the surrounding bash.
if ! command -v git >/dev/null 2>&1; then
  reason "git is not on PATH — the shadow-selection regression check needs a local repo for collect-turn-budget's durable-store fetch"
else
  shadow_work="$work/shadow-selection"
  mkdir -p "$shadow_work"
  shadow_out="$(python3 - "$shadow_work" <<'PY'
import json
import os
import subprocess
import sys

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step

work = sys.argv[1]
ensure_jq()
bash = resolve_bash()


def git(*args, cwd=work):
    # An argument list, never a shell string: quoted paths in a shell string
    # reach cmd.exe on Windows with their quotes intact, so `git init --bare`
    # exits 128 there (#393). No shell also means no quoting to get wrong.
    subprocess.run(["git", *args], check=True, cwd=cwd)


remote = os.path.join(work, "remote.git")
repo = os.path.join(work, "repo")
git("init", "--bare", "-q", "-b", "main", remote)
git("clone", "-q", remote, repo)
git("config", "user.email", "h@example.invalid", cwd=repo)
git("config", "user.name", "h", cwd=repo)
with open(os.path.join(repo, "f.txt"), "w", newline="\n") as seed:
    seed.write("x\n")
git("add", "-A", cwd=repo)
git("commit", "-q", "-m", "seed", cwd=repo)
git("push", "-q", "origin", "main", cwd=repo)

runner_temp = os.path.join(work, "runner_temp")
shared = os.path.join(runner_temp, "metrics-record-shared")
cycle_dir = os.path.join(shared, "metrics-record-cycle")
ba_dir = os.path.join(shared, "metrics-record-branch-advance")
os.makedirs(cycle_dir)
os.makedirs(ba_dir)
cycle_record = {
    "schema_version": 1, "record_available": True,
    "run": {"workflow_run_id": "999000222", "job_key": "cycle", "job_id": None,
            "step_index": 1, "record_key": "999000222:cycle:1"},
    "stage": "implement", "stage_available": True,
    "turns": {"counted": 20, "reported": 20, "intended_budget": 180,
              "enforced_ceiling": 450, "available": True},
}
ba_record = {
    "schema_version": 1, "record_available": False,
    "run": {"workflow_run_id": "999000222", "job_key": "cycle", "job_id": None,
            "step_index": 3, "record_key": "999000222:cycle:3"},
    "stage": "implement", "stage_available": True,
    "turns": {"counted": None, "reported": None, "intended_budget": None,
              "enforced_ceiling": None, "available": False},
}
with open(os.path.join(cycle_dir, "wing-commander-metrics-record.json"), "w",
          encoding="utf-8") as fh:
    json.dump(cycle_record, fh)
with open(os.path.join(ba_dir, "wing-commander-metrics-record-branch-advance.json"), "w",
          encoding="utf-8") as fh:
    json.dump(ba_record, fh)
os.makedirs(runner_temp, exist_ok=True)
with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
          encoding="utf-8") as fh:
    fh.write("[]")
with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
    fh.write("[]")

step_text = find_step(".github/workflows/watchdog.yml", "Collect: turn budget")["run"]
env = {
    "GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "RUN_ID": "999000222",
    "RUN_CONCLUSION": "success",
    "METRICS_BRANCH": "metrics", "METRICS_PATH": "records.jsonl",
    "HISTORY_WINDOW": "10", "CONSECUTIVE_TRIGGER": "3", "CLIMB_FRACTION": "0.6",
    "PATH": os.environ["PATH"],
}
rc, out, _outputs, summary = run_step(bash, step_text, repo, env, runner_temp)

reasons = []
if rc != 0:
    reasons.append(f"exited {rc}: {out.strip()[:400]}")
if "stage unresolved or turns.available is false" in summary:
    reasons.append("branch-advance record shadowed the real cycle record")
if "no metrics record (durable store or artifact) found" in summary:
    reasons.append("selection found no usable record at all")
if reasons:
    for r in reasons:
        print(f"FAIL: {r}")
    sys.exit(1)
print("PASS")
PY
)"
  if [ $? -ne 0 ]; then
    reason "maintainer review of #354: collect-turn-budget's artifact selection did not pick the real cycle record over a shadowing metrics-record-branch-advance artifact — $shadow_out"
  else
    note "collect-turn-budget correctly selects the named cycle/retry/progress record over a shadowing branch-advance artifact"
  fi
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-turn-budget-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-turn-budget-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
