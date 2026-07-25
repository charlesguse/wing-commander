# Phase 1 Data Model: Restore Reliable Watchdog Diagnosis

This feature adds no new persisted entity — `specs/015-pipeline-watchdog/
data-model.md` remains authoritative for Run under inspection, Signals,
Finding, Fingerprint, Pipeline-defect issue, and Lifecycle issue. This
document records the one shape this feature changes (Diagnose outcome, to add
a bounded retry attempt) and the one it clarifies (Lifecycle issue verdict's
"diagnose failed" wording).

## Diagnose outcome (existing entity, extended)

`specs/015-pipeline-watchdog/` and `specs/020-fix-watchdog/` already define
the diagnose job's terminal outcome as one of `passed-inspection`,
`findings`, or `diagnose-failed`, derived from a single `Diagnose` agent
attempt's execution-output file. This feature adds a classification step
between a failed attempt and that outcome, and — only when the
classification says so — a second attempt.

| Field | Source | Notes |
|---|---|---|
| Attempt 1 execution-output | `${{ runner.temp }}/claude-execution-output.json`, written by the `Diagnose` step | Unchanged shape (SDK's own JSON transcript; terminal record has `type=="result"`) |
| `agent-ok` (attempt 1) | New "Classify diagnose attempt" step, `if: always()` | Same boolean the existing read-back step already computes (`is_error==false && subtype=="success"`), computed one step earlier so retry gating can use it |
| `retryable` | Same step | `true` only when attempt 1's file has a `type=="result"` record (the SDK reached a terminal state) that is not OK — i.e. a recognized transient/infrastructure shape (research.md R2); `false` when `agent-ok` is already `true`, or when no such record exists at all (a declined/rejected-before-execution shape) |
| Attempt-1 forensic copy | Same step, before any retry can overwrite the fixed-path file | Copied to a distinct filename so it survives even if attempt 2 runs; uploaded only when a retry actually happened |
| Attempt 2 (`Diagnose (retry)`) | New step, `if: agent-ok != 'true' && retryable == 'true'`, otherwise `skipped` | Byte-for-byte same `with:`/`claude_args:` as attempt 1 (same model, prompt, schema, allowlists) — a genuine repeat, not a degraded fallback |
| Final execution-output | `${{ runner.temp }}/claude-execution-output.json` | If attempt 2 ran, it overwrote this file with its own result — this is now the authoritative attempt; if attempt 2 did not run, attempt 1's file is still authoritative, unchanged from today |
| `outcome` | "Read back diagnose outcome" step (existing, now reads whichever attempt is final) | `passed-inspection` \| `findings` \| `diagnose-failed` — same three values as today; unchanged meaning |
| `agent-step-outcome` | Same step | Now the *final* attempt's pre-`continue-on-error` outcome (attempt 2's if it ran, else attempt 1's) — this is what `report-unhandled-failure`'s safety net reads, so it must reflect the attempt that actually determined the outcome |
| `retried` (new) | Same step | `true` iff the retry step ran (not `skipped`) — surfaced only for the "diagnose failed" report's wording; not read by `verify-watchdog-run.sh` (FR-007: the verifier's contract is unchanged) |

No new job, no new output consumed by `triage`/`act`/`report-unhandled-
failure` beyond the existing `outcome`/`findings`/`agent-step-outcome` shape
those jobs already depend on — this feature changes what feeds those outputs
internally, not their shape or downstream contract.

## Lifecycle issue verdict (existing entity, wording clarified)

The "diagnose failed" report (`specs/020-fix-watchdog/data-model.md`'s
honest-failure path) gains attempt-count wording so a maintainer can tell,
from the lifecycle issue alone, whether a retry was already tried before the
run gave up — directly serving SC-005 ("a maintainer can determine from the
lifecycle issue alone... that the run was not inspected").

| Field | Before this feature | After this feature |
|---|---|---|
| Report text (not retried — deterministic failure) | `"...the diagnose agent failed, so this run was not inspected..."` | Unchanged — a non-retryable failure reports exactly as fast and as plainly as today |
| Report text (retried — still failed) | N/A (retry did not exist) | `"...the diagnose agent failed after 2 attempts, so this run was not inspected..."` — same surrounding sentence, attempt count inserted |

This is the only change to any lifecycle-issue-facing text; the
"passed inspection" report (whether attempt 1 or the retry produced it) is
byte-for-byte unchanged, since a genuine pass reads identically regardless of
which attempt reached it (FR-008: the healthy path is preserved).

## State transition (extends `specs/015-pipeline-watchdog/data-model.md`'s diagram, refines the `diagnose` box)

```
collect → diagnose:
            Diagnose (attempt 1)
              │
              ├─ agent_ok == true ──────────────────────────────▶ outcome: passed-inspection | findings
              │                                                    (unchanged from today)
              └─ agent_ok != true ─▶ Classify diagnose attempt
                                        │
                                        ├─ retryable == false ───▶ outcome: diagnose-failed
                                        │                           (unchanged from today — no retry)
                                        └─ retryable == true ────▶ Diagnose (retry)
                                                                      │
                                                                      ├─ agent_ok == true ─▶ outcome: passed-inspection | findings
                                                                      └─ agent_ok != true ─▶ outcome: diagnose-failed
                                                                                              (report notes 2 attempts)
          → triage → act   (unchanged; gated on the same three `outcome` values as today)
```

No new persisted entity, no new external write surface — the retry writes
only to the same job-scoped temp file every attempt already uses, and the
job still produces exactly one of the same three outcomes it produces today.
