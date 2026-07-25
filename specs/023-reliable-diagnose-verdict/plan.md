# Implementation Plan: Restore Reliable Watchdog Diagnosis — Stop Masked Diagnose-Agent Crashes

**Branch**: `023-reliable-diagnose-verdict` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/023-reliable-diagnose-verdict/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Issue #117 was filed by the stage-8b deterministic verifier against watchdog
run 30161188955: the diagnose agent crashed, produced no genuine terminal
result, and the run therefore never actually inspected the stage it was
watching. Reading the current `watchdog.yml` (research.md R1) shows the
**honesty** half of this problem — never presenting a crashed/empty/error
diagnose result as "passed inspection" — was already fixed on 2026-07-24
(the `agent_ok` read-back check, the "diagnose failed" reporter, and the
`report-unhandled-failure` safety net from `specs/020-fix-watchdog/` are all
present and are exactly why issue #117 was reported *honestly* instead of
silently). What issue #117 exposes is the remaining gap: the diagnose agent
still crashes outright with no recovery, so a run that hits a recognized
transient/infrastructure crash signature ends in an honest failure it did not
need to end in, and the exact issue-#117 crash signature itself has not been
root-caused.

The fix (per the maintainer's Q1:C/Q2:C answers on issue #117, already
encoded in FR-009/FR-010) adds a **bounded one-time retry** to the `diagnose`
job, gated by an in-job classification of the failed attempt: a genuine
terminal "result" record whose `is_error`/`subtype` shows the SDK ran but hit
an execution-layer problem is treated as recognized-transient and gets one
retry; a missing/empty output (the agent declined or crashed before reaching
any terminal state — e.g. an actor-allowlist rejection or a malformed CLI
argument) is treated as deterministic and reported as an honest failure
immediately, with no retry, because retrying identical inputs would only
reproduce it. This classification is computed entirely from the same
execution-output artifact the existing read-back step already reads — no new
dependency on live job-log fetches, which (research.md R3, same limitation
`specs/020-fix-watchdog/`'s planning hit) are not reachable from this
sandboxed planning stage. The existing honesty mechanisms, the stage-8b
verifier, and the reporter step names/conditions it greps for are left
unmodified (FR-007) — retry is entirely internal to the `diagnose` job and
changes only which attempt's output feeds the unchanged downstream logic.
Root-causing the specific issue-#117 signature (FR-005) is scoped as a
decision tree (research.md R3) the implement stage executes once it has the
job-log access this plan does not.

## Technical Context

**Language/Version**: Bash (workflow `run:` steps, `ubuntu-latest` default shell) + GitHub Actions workflow YAML

**Primary Dependencies**: `gh` (GitHub CLI), `jq`, `anthropics/claude-code-action@v1` — all already in use by `watchdog.yml`'s `diagnose` job; no new dependency introduced

**Storage**: N/A — state lives in the job's own step outputs, the `${{ runner.temp }}/claude-execution-output.json` file each `Diagnose` attempt writes, and the existing uploaded artifact / lifecycle-issue comment; no database

**Testing**: No unit-test framework for workflow YAML in this repo (dogfooding per constitution I). Verification is: (a) re-triggering real workflow runs and reading the posted verdict, and (b) fault-injecting a diagnose crash of each classified shape (retryable vs. not) on a throwaway branch to prove the retry fires only where intended — see quickstart.md

**Target Platform**: GitHub Actions, `ubuntu-latest` runners, this repository's own Actions environment (and any adopting repository that calls the reusable `watchdog.yml`)

**Project Type**: Single project — a GitHub Actions reusable-workflow pipeline component; no application `src/`/`tests/` split applies

**Performance Goals**: A bounded one-time retry, worst case, roughly doubles the `diagnose` job's own runtime (research.md R4); the job's `timeout-minutes` moves from 20 to 35 to keep two 10-minute step attempts plus setup/read-back overhead safely inside budget without materially changing the common (no-crash, no-retry) path's latency, which still finishes in well under a minute as today

**Constraints**: Constitution V (least privilege, untrusted content never instructions, no tool-allowlist broadening — the retry reuses the identical `--allowedTools`/`--disallowedTools`/prompt as attempt 1, nothing broadened); Constitution II (no new model tier — the retry reuses the same resolved `diagnose-model`, no LLM call added beyond the bounded retry itself); FR-007 (must not weaken, disable, or bypass the stage-8b verifier — `verify-watchdog-run.sh` and the reporter step names/conditions it inspects are unchanged); Constitution VI (fix stays inside the reusable `watchdog.yml` stage, no repo-specific hardcoding)

**Scale/Scope**: This repository's own dogfooded pipeline usage, plus any adopting repository consuming `watchdog.yml` as a reusable workflow (per Constitution VI, the fix is repo-name-agnostic)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — the repo is its own first example | Fix flows through spec → plan → tasks → implement → converge, against a real issue (#117) and a real lifecycle issue | PASS |
| II. Cost-conscious model tiering | No new model tier introduced; the retry reuses the diagnose job's already-resolved `claude-haiku-4-5`-tier model exactly once more; no LLM call added anywhere else | PASS |
| III. Simple, GitHub-native interaction | Verdict still lands only on the lifecycle issue or the run's own summary — no new external surface; the "diagnose failed" message gains attempt-count wording, not a new surface | PASS |
| IV. Automation-first | The fix removes a class of failure that previously required a maintainer to notice a `pipeline-defect` issue and manually re-dispatch the watchdog; retry absorbs the recognized-transient case automatically and reports the rest exactly as honestly as today | PASS |
| V. Security — untrusted content is never instructions | The retry step is a byte-for-byte duplicate of the existing `Diagnose` step's tool allowlist, prompt framing, and structured-output schema — no broadening; classification reads only the SDK's own structured execution-output file, never untrusted run content | PASS |
| VI. Portability | Change is confined to `watchdog.yml` (the published, reusable stage) and `docs/architecture.md`; no repository name/owner hardcoded; the two wrapper workflows and `verify-watchdog-run.sh` are expected to need no change | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/023-reliable-diagnose-verdict/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── watchdog-diagnose-retry-delta.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no application `src/`/`tests/` split — it *is* a
GitHub Actions pipeline. The feature's changes are confined to:

```text
.github/workflows/
└── watchdog.yml          # reusable stage — diagnose job gets a classify step,
                           # a gated one-time retry step, and read-back/report
                           # steps updated to consider whichever attempt is
                           # final; job timeout-minutes 20 → 35. Root cause fix
                           # for the specific issue-#117 signature (FR-005)
                           # lands here too, once the implement stage identifies
                           # it (research.md R3's decision tree).

.github/scripts/
└── verify-watchdog-run.sh  # unchanged — read-only from this stage; retry is
                             # internal to diagnose and must not require any
                             # change here (FR-007)

docs/
└── architecture.md       # Stage 9 — Watchdog section: document the bounded
                           # retry and the new job timeout

specs/015-pipeline-watchdog/          # unchanged — remains the source of
                                       # truth for overall watchdog design
specs/020-fix-watchdog/               # unchanged — its safety-net job and
                                       # honest-reporting fix are preserved
                                       # as-is, not re-litigated
specs/023-reliable-diagnose-verdict/  # this feature's own spec-kit artifacts
```

**Structure Decision**: Single project, no option-1/2/3 split applies. Every
functional change lives inside the existing reusable workflow file
`watchdog.yml`'s `diagnose` job — the fix is additive (one classify step, one
gated retry step, small edits to the existing read-back/report steps) rather
than a restructuring, consistent with the spec's Assumption that the
watchdog's existing honest-reporting steps are the intended mechanism and
should keep firing unchanged when a genuine failure occurs.

## Complexity Tracking

> Not applicable — Constitution Check has no violations to justify.
