# Contract: `verify-watchdog-run.sh` suppresses only the reasons rate-limiting explains

Builds on `data-model.md`'s "Stage-8b verification suppression" table;
`research.md` R4 explains the reasoning. This is the deterministic
stage-8b verifier (`wing-commander-8b-watchdog-self.yml` → `verify`
job), unchanged in every respect not listed below.

## New evidence read

```bash
c="$(step diagnose 'Report "rate-limited" to lifecycle issue')"
rate_limited=false
[ -n "$c" ] && [ "$c" != "skipped" ] && rate_limited=true
```

Placed alongside the script's existing checks 3/4 (the block reading
`diagnose_conclusion` and the two `step diagnose ...` calls), using the
same `step()` helper already defined — no new helper, no new API call
(the `jobs_json` fetch already covers this step, since it lives in the
same `diagnose` job the existing checks already read).

## Check 7 — suppressed when `rate_limited`

Existing (unchanged condition, only the action on match changes):

```bash
if ! jq -e '([.[] | select(.type=="result")] | last) as $r
    | $r != null and $r.is_error == false and $r.subtype == "success"' \
    "$out" >/dev/null 2>&1; then
  if [ "$rate_limited" = "true" ]; then
    note "diagnose execution log has no successful terminal result — expected, rate-limited run"
  else
    reason "diagnose execution log has no successful terminal result record (empty output, is_error, or an error subtype) — the agent never produced a real verdict"
  fi
fi
```

## Check 2's floor breach — suppressed when `rate_limited`; ceiling breach unaffected

Existing (unchanged bounds computation, only the floor arm's action
changes):

```bash
if [ "$duration" -lt "$floor" ]; then
  if [ "$rate_limited" = "true" ]; then
    note "run finished in ${duration}s, under the ${floor}s floor — expected, rate-limited run (one-turn rejection)"
  else
    reason "run finished in ${duration}s — under the ${floor}s floor (median ${median}s); too fast to have done real work"
  fi
elif [ "$duration" -gt "$ceiling" ]; then
  reason "run took ${duration}s — over the ${ceiling}s ceiling (median ${median}s); something stalled"   # UNCHANGED — never suppressed
fi
```

## Everything else: unchanged, still fully live

- Check 1 (run conclusion `== success`): unaffected — a rate-limited
  run's job stays green (`continue-on-error`), so this check does not
  fire either way; no suppression needed.
- The diagnose-job duration ceiling (`d_secs -gt 300`): unaffected — a
  rate-limited rejection is fast, not slow, so this never fires for the
  case this feature addresses; left fully live for genuine stalls.
- Check 3 (`"diagnose failed"` reporter ran): **no code change** — the
  reporter step it reads is skipped by construction for a rate-limited
  outcome (contracts/watchdog-reporting.md's mutual-exclusion), so this
  check already produces no reason without any new suppression logic.
- Check 4 (`"Read back diagnose outcome"` step succeeded): unaffected —
  that step still runs and still succeeds for the rate-limited branch;
  still asserted.
- Check 5 (collect's `"could not inspect"` reporter): unaffected,
  unrelated code path.
- Check 6 (the unhandled-failure safety net): unaffected, unrelated code
  path — still catches a genuine internal failure occurring alongside a
  rate-limited diagnose step.
- Check 8 (crash-signature grep of the raw job log): unaffected — left
  fully live. A genuine API-429 rejection is not expected to produce any
  of the three grepped signatures (`Action failed with error`, `SDK
  execution error`, `non-human actor`), so no suppression is designed
  for it; if replay against the real evidence artifacts (research.md R1)
  shows otherwise, that is a fixture-driven finding for `tasks.md`, not
  a change this contract pre-supposes.

## Net effect (FR-012a)

For a stage-8 run whose diagnose step is rate-limited and nothing else
is wrong, `fail_reasons` is empty after the above, and the script's
existing tail (`if [ "${#fail_reasons[@]}" -eq 0 ]; then ... exit 0`)
already reports "verified healthy" and exits 0 — **no new code is needed
for the green-job outcome itself**, only for making the two explained
reasons never enter `fail_reasons` in the first place. For a stage-8 run
that is rate-limited **and** independently breaches the ceiling, or has
a failed job, or trips the unhandled-failure safety net, those reasons
still populate `fail_reasons`, the script still exits 1, and the
existing `CREATE_ISSUE` block still files/comments on the
`pipeline-defect` issue for those reasons alone — text describing a
rate-limited-and-broken run should not claim the run was purely a usage
outage (US1 Acceptance Scenario 4, FR-011).

## Gate 36 (`verify-watchdog-run-failure-paths.sh`) — new fixtures

Per constitution VIII, every branch above needs a checked-in fixture
proving it fires when it should and stays silent when it shouldn't:

1. Rate-limited diagnose, nothing else wrong → verifier exits 0, no
   issue created/commented.
2. Rate-limited diagnose **and** an unrelated red job → verifier exits
   1, `fail_reasons` contains only the unrelated reason, `pipeline-defect`
   issue is filed/commented mentioning only that reason.
3. Rate-limited diagnose **and** a stalled diagnose job (duration over
   ceiling) → verifier exits 1 for the stall alone (proves the ceiling
   arm is genuinely unaffected by the floor-arm suppression).
4. A `gh` stub failure on the new `step diagnose 'Report "rate-limited"...'`
   lookup (the existing `GH_STUB_FAIL` shape from PR #168) → `rate_limited`
   resolves to `false` (fails safe: an unreadable evidence read must
   never silently suppress a real reason) and the run is verified by its
   pre-existing rules, not silently passed.
