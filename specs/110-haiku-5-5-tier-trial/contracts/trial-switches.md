# Contract: Trial switches and interface changes

## Consuming instrument (this repository; free to change)

| Switch | Effect | Off state |
|---|---|---|
| Repository variable `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE` = `YYYY-MM-DD` | enables the diagnose shadow from that date | unset or empty |
| Label `model:haiku` on a lifecycle issue | implement runs `claude-haiku-5-5`, escalation `claude-sonnet-5-5`, budget `WING_COMMANDER_IMPLEMENT_HAIKU_MAX_TURNS` (180) | label absent |
| `model:opus` also present | Opus wins; `model:haiku` ignored | — |

`pr-conversation` and `board-loop` read only `model:opus`; `model:haiku` (also when
mirrored onto the PR) has no effect on them.

Bound: the shadow is enabled only while `today < SINCE + 60 days` and the count of
compared shadow records since `SINCE` (by `emitted_at`; an undated record counts,
and so do a comparator-error record and a shadow record with no readable `trial`
object, see trial-record.md) is `< 300`. A `SINCE` that cannot be read, or that is
still ahead of today in UTC, leaves the shadow off with a warning. Restart =
set a new `SINCE`. The wrapper's `trial-bound` job reads the metrics branch, which
receives watchdog records through metrics-persist's daily sweep (the watchdog is
sweep-only), so "at most 300" holds to within the runs of the last day not yet
swept. `wing-commander-trial-summary.yml` passes the same `SINCE`, so the summary
covers the window the bound closes.

## Published contract (additive widening, Principle VII)

`watchdog.yml` `workflow_call` inputs, all optional:

| Input | Type | Default | Meaning |
|---|---|---|---|
| `diagnose-shadow-enabled` | boolean | `false` | run the shadow step |
| `diagnose-shadow-model` | string | `claude-haiku-5-5` | shadow model |
| `diagnose-shadow-max-turns` | number | `8` (shadow budget; Opus diagnose uses 2 turns on average, confirmed at implement from `diagnose-max-turns`) | shadow turn budget |

No input, output or secret is removed or renamed. `implement.yml`, `finalize.yml`,
`cleanup.yml` change only the default of the existing `summary-model` input.
`auto-update-spec-kit.yml` gains no input. New composites are internal to the
pipeline checkout; `wing-commander-trial-record` and `-trial-bound` are not part of
the adopter-pinned surface until a release says so. (The planned
`wing-commander-diagnose-agent` composite was not built: no composite may invoke the
agent action, Gate 38, so the shadow's prompt is pasted and held byte-equal to the
Diagnose step's by Gate 146 -- research.md D7's fallback, recorded at tasks.md T005.)

## Shadow step guarantees (checked by `verify-diagnose-shadow-acts-on-nothing.py`)

- Runs only when `inputs.diagnose-shadow-enabled`, as the diagnose job's tail:
  after the acting path's read-back, uploads and reports.
- Every shadow step is `continue-on-error: true`; the agent step has
  `timeout-minutes: 5`; with the Diagnose step's 10 and ten minutes for the other
  steps it fits the job's backstop, raised from 20 to 25 minutes.
- Allowlist is fixed read-only and takes no consumer tool-list input: `Read`,
  `Grep`, the git read wrapper and read-only `gh` subcommands only (not the
  diagnose default's `Bash(gh:*)`, because `github.token` holds `issues: write` in
  this stage); no `Write`/`Edit`; `GH_TOKEN` and `github_token` are `github.token`.
- Its prompt and `--json-schema` are byte-equal to the Diagnose step's.
- Its outputs feed only the comparator and the trial-record upload; no acting step
  and no job output of the diagnose job reads it.
- wing-commander-8b's diagnose-duration ceiling subtracts the shadow's steps, so a
  slow shadow files nothing (SC-003).
