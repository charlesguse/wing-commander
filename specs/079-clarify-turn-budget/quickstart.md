# Quickstart: Validating the Re-Based Clarify Budget

Prerequisites: a checkout of this repository on the implementation
branch, `jq`, `awk`, and Python 3 available (the same toolchain every
existing gate already assumes — no new dependency).

## 1. Confirm the declared budget and ceiling moved together

```bash
grep -A2 "max-turns:" .github/workflows/clarify.yml | head -6
```

Expected: `default: 65`, with the accepted-range/ceiling comment above it
(contracts/clarify-turn-budget-delta.md).

```bash
awk 'BEGIN{ i=65; m=2.5; p=i*m; c=int(p); if (p>c) c+=1; print c }'
```

Expected: `163` — the same arithmetic `wing-commander-turn-ceiling`
performs; confirms FR-003's "state the resulting ceiling" independently
of the workflow.

## 2. Replay the cited history against the new configuration (SC-001, SC-002)

Feed the three recorded clarify runs to the same jq filter
`watchdog.yml`'s `collect-turn-budget` step runs
(`.github/scripts/verify-turn-budget-collector.sh` already carries this
harness — extend it with a clarify-shaped fixture, or run ad hoc):

```bash
echo '{"stage":"clarify","run":"r4","own":{"available":true,"counted":61,"intended":65,"ceiling":163},
       "history":[{"run":"r1","counted":39,"intended":65,"ceiling":163},
                  {"run":"r2","counted":45,"intended":65,"ceiling":163}],
       "history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}' \
  | jq '.own.counted >= .own.intended'
```

Expected: `false` for every one of {39, 45, 61} against budget `65` — no
run is flagged over budget (SC-002), and (per the collector's own
`max_frac`/`meets_climb` arithmetic, research.md R1) the window's band
computes to `null`, not `elevated` (SC-001).

## 3. Confirm every other stage is untouched (SC-005)

```bash
git diff main -- .github/workflows/ | grep -E '^\+\+\+|^---' | sort -u
```

Expected: only `clarify.yml` (and, if the gate lands in the same file,
`lint-workflows.yml`) appear — no other stage workflow's diff.

## 4. Run the new gate (FR-018)

```bash
python .github/scripts/verify-stage-turn-budget-docs.py --self-test
python .github/scripts/verify-stage-turn-budget-docs.py
```

Expected: all fixtures pass under `--self-test`
(contracts/gate-coverage-079.md); the live run against the working tree
exits 0 once `docs/adoption.md`'s `### clarify` row is updated to `65`.

## 5. Run the full local gate suite (CLAUDE.md: before pushing)

```bash
python .github/scripts/run-local-gates.py
```

Expected: green, including the newly registered gate and the unmodified
Gates 22/23.

## 6. Confirm the invalid-budget guard still fires (FR-011, SC-008)

```bash
.github/actions/wing-commander-turn-ceiling  # composite; exercise via its existing fixture/test harness
```

No new fixture needed here — research.md R3 confirms this guard is a
function of whatever `intended-turns` arrives, unrelated to clarify's
specific literal; the existing fixture set (unchanged by this feature)
still proves empty/zero/negative/non-numeric fail loudly.
