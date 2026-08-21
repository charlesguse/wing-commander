# Implementation Plan: A Transient API Blip No Longer Kills Six Stages at Entry, and the Gate Says What Actually Happened

**Branch**: `039-lifecycle-gate-retry` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/039-lifecycle-gate-retry/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`.github/actions/wing-commander-lifecycle-gate/action.yml`'s single step,
`Check lifecycle issue state` (lines 45–82), makes one `gh issue view
--json state --jq .state` call and treats every non-zero exit or empty
result the same way: a fixed `::error::` line guessing "may not exist, or
the token lacks issues: read" — discarding the command's actual stderr
(`HTTP 502: ...` in the source incident) and never retrying. This plan
rewrites that one step, in place, to wrap the read in a bounded retry loop
with per-attempt classification, and changes nothing else about the
composite's declared surface (FR-015): same `issue-number`/`token` inputs,
same `state`/`is-open` outputs, no new `workflow_call` surface for any of
the six calling stages.

**Retry mechanics** (research.md D1): up to 3 attempts total, each wrapped
in `timeout 4` around the `gh` call (a hang or dropped connection with no
status is otherwise unbounded — spec Acceptance Scenario 5), with a 1-second
sleep between attempts (none after the last). Worst case — three timeouts
back to back — is `4+1+4+1+4 = 14` seconds, inside FR-003/SC-004's 15-second
ceiling with a 1-second margin for the `gh` process's own startup cost. The
first-attempt-succeeds path (the overwhelming common case, SC-005) is
byte-for-byte what the step does today: one `gh` call, no `timeout`
wrapper overhead beyond the syscall itself, no sleep.

**Classification** (research.md D2): stderr is now captured (via `2>` to a
per-attempt temp file, replacing today's stdout-only capture) and classified
by pattern match, in this order:
1. **Not found** (`Could not resolve to an.*[Ii]ssue`, `HTTP 404`) → fail
   immediately, keep today's "may not exist" wording (FR-002, FR-005, US3).
2. **Credential rejected** (`HTTP 401`, `Bad credentials`, `Resource not
   accessible by integration`, a scope-shaped message) → fail immediately,
   name the credential, not the issue (FR-002, FR-005, US3).
3. **Everything else** — a recognised transient shape (`HTTP 5\d\d`,
   `timed out`, connection-reset wording), an unrecognised fault, a
   rate-limit rejection (`HTTP 403` that does *not* match the credential
   pattern — `API rate limit exceeded` / `secondary rate limit` carry no
   "scope"/"401"/"authenticate" wording, so they fall through here rather
   than being misclassified as permanent), and a zero-exit call with an
   empty state — is **retried**, tagged internally as `transient` or
   `unclassified` only so the FR-006 exhaustion message can say which.
   This is FR-009's retry-by-default: only the two positively-identified
   permanent conditions above bypass the budget.

Attempts that fail but are retried are logged with `::warning::`, never
`::error::` — an `::error::` workflow command annotates the run as failed
regardless of the step's eventual exit code, which would violate FR-007's
"MUST NOT ... annotate the run as failed" for a run that goes on to
succeed. Only the step's *final* failure (a permanent classification, or
budget exhaustion) emits `::error::`, exactly once, satisfying FR-010.

Captured diagnostic text is bounded and rendered safely before it reaches
any `::error::`/`::warning::` line (FR-018): collapsed to one line
(`\r`/`\n` stripped), capped at 300 characters with a truncation marker,
and `%`-escaped per GitHub's own workflow-command escaping rules — the same
technique that already protects every other annotation in this repository
from being broken by arbitrary command output. No additional redaction is
added for FR-017: `gh` does not echo `$GH_TOKEN`'s literal value into its
own error text (it references the environment variable name, not the
value), so there is nothing to strip beyond not doing anything that would
echo the token — which no line in the rewritten step does.

**Coverage** (research.md D6/D7): a new
`.github/scripts/verify-lifecycle-gate-retry.py`, built on the existing
`wc_shell_harness.py` (`resolve_bash`, `find_step`, `run_step`,
`parse_github_output`), extends the `bin/gh` stub pattern from
`verify-stall-restart-runbook.py` (PR #186) to a per-call-count shim: a
counter file the stub increments on each invocation, branching its
exit code / stdout / stderr by call count so a single stub can fail N
times then succeed, or fail permanently, or fail in an unrecognised shape.
It is wired into `.github/workflows/lint-workflows.yml` as **Gate 25**,
following the mutation-testing shape Gate 14 already established (apply a
mutation to the shipped step, rerun the same suite, require it to fail) —
this is FR-013's own requirement, so the gate proves itself rather than
only asserting the happy path.

See [research.md](./research.md) for the full decision record,
[data-model.md](./data-model.md) for the classification/entity shapes, and
[contracts/](./contracts/) for the composite's updated I/O contract and the
new coverage script's contract.

## Technical Context

**Language/Version**: Bash (the composite's own `run:` step), Python 3
(`.github/scripts/verify-lifecycle-gate-retry.py`, matching every existing
`verify-*.py` gate script) — no new language introduced.

**Primary Dependencies**: `gh` CLI (already the sole dependency of this
step), coreutils `timeout` (already present on `ubuntu-latest`, the only
runner `lint-workflows.yml` uses), `wc_shell_harness.py` (existing, reused
unmodified — its `run_step`/`find_step`/`parse_github_output` API already
covers everything this feature's coverage needs).

**Storage**: N/A — no persisted state. The retry loop's counters and
per-attempt diagnostic text live only for the duration of the step.

**Testing**: New `.github/scripts/verify-lifecycle-gate-retry.py`, wired
into `.github/workflows/lint-workflows.yml` as Gate 25, using a stubbed
`gh` on `PATH` per `wc_shell_harness.py`'s established pattern (research.md
D6). Covers: retry-then-succeed (US1, FR-001, FR-011), fast-fail on
not-found and on credential-rejected with exactly one attempt each (US3,
FR-002, FR-012), budget exhaustion with the correct diagnostic/attempt-count
message (US2, FR-006), an unclassifiable failure landing in the retry path
rather than failing at entry (FR-009, FR-011, SC-009), and the four
regression mutations FR-013 requires (revert the retry; widen retry to
permanent failures; narrow retry to only recognised transient shapes;
disable the coverage itself).

**Target Platform**: GitHub Actions composite action, `ubuntu-latest`
runner, called by six `workflow_call` stage workflows exactly as today.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: Zero added latency on a first-attempt success
(SC-005) — the common-case path executes the same one `gh` call it does
today, no `timeout` retries, no sleep. Worst case (every attempt transient)
adds no more than 15 seconds (FR-003, SC-004), per the D1 budget above.

**Constraints**:
- The composite's declared `issue-number`/`token` inputs and `state`/
  `is-open` outputs do not change (FR-015) — no caller among the six stages
  needs editing.
- No calling stage's job graph or job conditions change (FR-016) — this
  feature is confined to the one composite file; the `implement` silent
  chain-stop on gate failure is explicitly out of scope, tracked as #231.
- Attempt count, per-attempt timeout, and inter-attempt delay are fixed
  constants inside the step, not new inputs — widening the published
  contract of a composite whose whole virtue is being small is explicitly
  rejected (spec Assumptions).
- Nothing the step reports may expose the token (FR-017).
- The reported failure stays a single readable line even when the captured
  diagnostic is long, multi-line, or contains characters that would
  otherwise break a workflow-command annotation (FR-018).

**Scale/Scope**: One file changed (`.github/actions/wing-commander-
lifecycle-gate/action.yml`, one step rewritten in place), one new file
added (`.github/scripts/verify-lifecycle-gate-retry.py`), one new gate
step (plus, per the repository's established pairing, its own inline
mutation assertions rather than a separate self-test step — Gate 14's
shape) added to `.github/workflows/lint-workflows.yml`. Zero edits to any
of the six calling stage workflows (`clarify.yml`, `finalize.yml`,
`implement.yml`, `intake.yml`, `pr-conversation.yml`, `tasks.yml`) or to
any other composite.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #188 → this spec → this plan → tasks → implement), with the fix validated by the same shell-harness/gate-registry machinery the repository already uses on itself. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (`plan.yml`'s planning-weight default). The feature adds no agent invocation of any kind — it is a deterministic bash retry loop and a Python test script. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface. The gate's failure is still read from the job log/annotations a maintainer already checks; this feature only makes that text accurate. | ✅ Pass |
| IV. Automation-First | No new manual step. A retry is fully automatic; an exhausted-budget failure is reported explicitly via `::error::`, never silently assumed. | ✅ Pass |
| V. Security — untrusted content is never instructions | No change to what the step trusts: it still reads only its own declared `issue-number`/`token` inputs and the live API response, never `github.event.*` or issue/comment text. FR-017 (no credential exposure) is satisfied by construction (Summary above). | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | Unaffected — this composite already lives under `.github/actions/**`, resolved from the pipeline repository's own checkout; nothing here changes that resolution or reads consumer-specific state. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | The composite's published contract (inputs, outputs, required access) is explicitly unchanged (FR-015) — this is an internal-behavior fix to the published contract's implementation, not a surface change, and it introduces no new stage-side ambient-state read. No deviation to register. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms the retry lives entirely inside the one
existing step, adds no new input/output/secret, and introduces no new
untrusted-input path — the classification patterns match only `gh`'s own
diagnostic text, which is trusted operational output, not user content.

## Project Structure

### Documentation (this feature)

```text
specs/039-lifecycle-gate-retry/
├── plan.md                                  # This file (/speckit-plan command output)
├── research.md                              # Phase 0 output (/speckit-plan command)
├── data-model.md                            # Phase 1 output (/speckit-plan command)
├── quickstart.md                            # Phase 1 output (/speckit-plan command)
├── contracts/                               # Phase 1 output (/speckit-plan command)
│   ├── wing-commander-lifecycle-gate.md     # updated composite I/O contract (delta)
│   └── lifecycle-gate-retry-coverage.md     # new coverage script's contract
├── checklists/
│   └── requirements.md                      # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                 # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   └── wing-commander-lifecycle-gate/
│       └── action.yml               # "Check lifecycle issue state" step
│                                     #   rewritten in place: bounded retry
│                                     #   loop, stderr capture, per-attempt
│                                     #   classification, safe diagnostic
│                                     #   quoting. Inputs/outputs unchanged.
├── scripts/
│   ├── wc_shell_harness.py          # UNCHANGED — reused as-is
│   ├── verify-stall-restart-runbook.py  # prior art for the gh-stub/
│   │                                 #   mutation-testing shape (read only)
│   └── verify-lifecycle-gate-retry.py   # NEW — Gate 25's script
└── workflows/
    └── lint-workflows.yml           # + Gate 25 — "the lifecycle gate
                                      #   retries transient failures and
                                      #   fails fast on permanent ones"
```

**Structure Decision**: No new top-level directories, no new composite, no
edits to any of the six calling stage workflows or any other composite
action. The entire change is: one step of one existing file rewritten in
place, one new verification script, and one new gate step registering that
script — matching the spec's own framing ("a bounded retry on transient
classes, not a general resilience framework").

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
