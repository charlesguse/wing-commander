# Contract: `auto-release-container-evidence-decision.sh`

Follows the fetch/decide split
`specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md`
documents for `auto-release-e2e-clarify-decision.sh` /
`auto-release-e2e-merge-decision.sh`: the workflow step performs the `gh`
calls and captures their raw results; this script is a pure function from
those captured results to a classification, callable directly by the new
gate's fixtures with no network access.

## Location

`.github/actions/_shared/auto-release-container-evidence-decision.sh`

## Inputs (positional arguments; exact ordering finalized at implement time, shape fixed here)

1. `check` — `config` or `execution`, selecting which half of the evidence
   this call decides.
2. `read_status` — `ok`, `unreadable`, or `rate-limited`, the captured
   result of the `gh` read(s) this decision is based on.
3. `expected` — the expected value (this repository's pin, for `config`;
   the set of stage jobs expected to run containerized, for `execution`).
   Empty when `read_status != ok`.
4. `observed` — the observed value (the test repository's variable value,
   for `config`; the stage jobs actually observed containerized, for
   `execution`). Empty when `read_status != ok`.

## Output

Three lines on stdout, in this order, matching
`auto-release-verdict.sh`'s corresponding positional arguments:

```text
failing_check=<one of the exact strings in contracts/container-evidence-outcomes.md §2, or empty for a pass>
expected=<the expected text to carry into the verdict>
observed=<the observed text to carry into the verdict>
```

An empty `failing_check` on the `config` call means "proceed" (the
workflow continues to `scaffold`/`kickoff`, not to a verdict write); an
empty `failing_check` on the `execution` call means the existing `pass`
call is unblocked. A non-empty `failing_check` on either call means the
calling step MUST write a `fail-infra` verdict with that triple and MUST
NOT proceed further (config call) or MUST NOT reach the `pass` write
(execution call).

## Behavior table

| `check` | `read_status` | `expected` vs `observed` | Output `failing_check` |
|---|---|---|---|
| `config` | `unreadable` | — | `container-mode evidence unreadable` |
| `config` | `rate-limited` | — | `container-mode evidence rate-limited` |
| `config` | `ok` | `observed` empty/absent | `container image not configured on the test repository` |
| `config` | `ok` | `observed` non-empty, `!= expected` | `container image configured but does not match this repository's pin` |
| `config` | `ok` | `observed == expected`, non-empty | *(empty — proceed)* |
| `execution` | `unreadable` | — | `container-mode evidence unreadable` |
| `execution` | `rate-limited` | — | `container-mode evidence rate-limited` |
| `execution` | `ok` | stage jobs not all containerized | `container image configured but stage jobs did not execute inside a container` |
| `execution` | `ok` | all stage jobs containerized | *(empty — pass unblocked)* |

## Testability

Every row above is a fixture in the new gate (`verify-gate-<N>.py`,
research.md D7), invoked as a subprocess with fixed arguments and asserted
stdout — no `gh`, no network, no workflow execution required to exercise
this script directly (SC-006).
