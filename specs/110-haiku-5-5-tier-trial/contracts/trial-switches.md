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
compared shadow records since `SINCE` is `< 300`. Restart = set a new `SINCE`.

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
pipeline checkout; `wing-commander-diagnose-agent`, `-trial-record`, `-trial-bound`
are not part of the adopter-pinned surface until a release says so.

## Shadow step guarantees (checked by `verify-diagnose-shadow-acts-on-nothing.py`)

- Runs only when `inputs.diagnose-shadow-enabled`, after the acting path's
  read-back and uploads.
- `continue-on-error: true`, `timeout-minutes: 5`.
- Allowlist is the diagnose read-only default; no `Write`/`Edit`; `GH_TOKEN` is
  `github.token`.
- Its outputs feed only the comparator and the trial-record upload; no job output of
  the diagnose job depends on it.
