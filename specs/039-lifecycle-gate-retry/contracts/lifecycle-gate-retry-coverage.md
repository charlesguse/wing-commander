# Contract: `.github/scripts/verify-lifecycle-gate-retry.py` (new, Gate 25)

Follows the calling convention every other `verify-*.py` gate script in
`.github/scripts/` already establishes: a standalone script, invoked with
no arguments as `python3 .github/scripts/verify-lifecycle-gate-retry.py`
from a `lint-workflows.yml` step, exit code 0 on pass / non-zero on any
assertion failure, using `wc_shell_harness.py`'s `resolve_bash`,
`ensure_jq`, `find_step`, `run_step`, `parse_github_output`,
`use_utf8_stdout` unmodified.

## Purpose

Prove, by actually executing the shipped `Check lifecycle issue state`
step's real `run:` text against a stubbed `gh`, that: a transient failure
is retried and eventually succeeds (FR-011); a permanent failure fails
after exactly one attempt (FR-012); and that reverting, widening, or
narrowing the retry/classification each independently breaks this proof
(FR-013), so the gate cannot silently stop proving what it claims to
(FR-014).

## Stub mechanism

A `#!/bin/sh` script written to `bindir/gh` (mirroring `verify-stall-
restart-runbook.py`'s pattern), `chmod 0o755`, with `PATH` set to
`bindir:$PATH` in `run_step`'s `env_extra`. Each scenario's stub
increments a call-count file on every invocation and branches on the
resulting count (research.md D6):

```sh
#!/bin/sh
n=$(cat "$GH_CALL_COUNT" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$GH_CALL_COUNT"
# scenario-specific branch on "$n" goes here, generated per test case
```

`GH_CALL_COUNT` is a path under the per-test `RUNNER_TEMP`, unique per
`run_step` invocation so scenarios never share state.

## Scenarios asserted (each a call to `run_step` against the real, unmutated step)

| Scenario | Stub behavior | Assertion | FR/US |
|---|---|---|---|
| Transient-then-succeed | Fails with `HTTP 502` on calls 1–2, succeeds on call 3 | `rc == 0`, correct `state`/`is-open` outputs, `GH_CALL_COUNT` shows `3` (more than one read attempted) | FR-011, US1 |
| Unclassified-then-succeed | Fails with an unrecognised, made-up fault string on call 1, succeeds on call 2 | `rc == 0`, correct outputs, more than one attempt — proves FR-009's retry-by-default is exercised, not only stated | FR-011, FR-009 |
| Always not-found | Every call emits `Could not resolve to an issue...`, exit 1 | `rc != 0`, `GH_CALL_COUNT == 1` (exactly one attempt), `::error::` output names the issue, not the credential | FR-012, US3 |
| Always credential-rejected | Every call emits `HTTP 401: Bad credentials`, exit 1 | `rc != 0`, `GH_CALL_COUNT == 1`, `::error::` output names the credential, not the issue | FR-012, US3 |
| Budget exhausted (always transient) | Every call fails with `HTTP 503` | `rc != 0`, `GH_CALL_COUNT == 3` (the full budget was spent), `::error::` states 3 attempts were made and quotes the last diagnostic, tagged as a recognised transient class | FR-006, US2, spec Edge Case "every attempt fails transiently" |
| Budget exhausted (always unclassified) | Every call fails with an unrecognised fault | `rc != 0`, `GH_CALL_COUNT == 3`, `::error::` states the attempts "could not be classified," not that they were a known transient fault | FR-006, US2 acceptance scenario 6 |
| Success, empty state | Call exits 0 with empty stdout on call 1, returns `OPEN` on call 2 | `rc == 0`, correct outputs — proves the empty-successful-read case is retried (FR-009, D5), not folded into a generic failure | US1 acceptance scenario 6, spec Edge Case "read succeeds but returns nothing" |
| Success, unrecognised value | Call exits 0 with `MERGED` (a real but unhandled state) on call 1 | `rc != 0` immediately, `GH_CALL_COUNT == 1` — proves an unrecognised *answer* is not retried (unchanged FR-008 behavior) | FR-008, US3 acceptance scenario 4 |

## Required mutations (FR-013) — each must turn a passing scenario failing

| Mutation | Expected effect |
|---|---|
| Revert the retry (collapse the loop to a single attempt, as today) | Transient-then-succeed scenario now fails (`rc != 0` where it should be `0`) |
| Widen the permanent-pattern classifier so it also matches a transient shape (e.g. make the not-found pattern also match `HTTP 502`) | Transient-then-succeed scenario now fails after exactly one attempt instead of retrying |
| Narrow the retry to a fixed list of known transient shapes, so an unclassified failure fails immediately | Unclassified-then-succeed scenario now fails after exactly one attempt |
| Disable/remove Gate 25's own step from `lint-workflows.yml` | A separate, minimal check within this same script (or a lightweight companion assertion) confirms the step is present and not `if: false` — this is the FR-014 reflexive check; per repository convention (Gate 15's own finding) this is the one mutation this script must detect about *itself* rather than about the composite |

Each mutation uses the `if mutated == steps: raise` guard `verify-stall-
restart-runbook.py:345` establishes, so a mutation helper that silently
fails to apply is itself caught rather than producing a false pass.

## Non-goals

- Does not test against the real GitHub API — every scenario runs against
  a stubbed `gh` on `PATH`, per `wc_shell_harness.py`'s existing model.
- Does not modify `wc_shell_harness.py` — reused exactly as-is.
- Does not assert on wall-clock timing (the 1-second inter-attempt delay
  and 4-second per-attempt timeout are structural constants asserted by
  reading the step's own script text, not by timing a live run, since
  timing-based assertions would make the gate flaky under CI load).
