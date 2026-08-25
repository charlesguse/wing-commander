# Contract: the `refused`/`reason` output convention

This is a **convention applied to existing steps**, not a new composite — it
has no single file of its own. It is documented here because FR-005a makes
it a load-bearing cross-cutting contract: every step in the fleet that
declines to proceed for a declared reason must follow it identically, or the
survivor job (data-model.md) cannot distinguish a refusal from a crash.

## The rule

A step that refuses — declines to proceed because a precondition of *this
stage itself* is unmet, and says so in its own error text today — MUST,
immediately before its `exit 1`:

```bash
echo "reason=<the same message already sent to ::error::>" >> "$GITHUB_OUTPUT"
echo "refused=true" >> "$GITHUB_OUTPUT"
```

A step that fails for any other reason (a crash, an unexpected `gh`/`jq`
error, a genuinely unclassified fault) MUST NOT write `refused`. The absence
of the output is what marks abnormal termination — never the presence of an
empty or false-y value (FR-005a's explicit prohibition).

For a **composite action** whose refusal logic lives inside one `run:` step
(e.g. `wing-commander-preflight`'s single `fail()`-driven step), the
composite's own `outputs:` block maps these through:

```yaml
outputs:
  refused:
    value: ${{ steps.check.outputs.refused }}
  reason:
    value: ${{ steps.check.outputs.reason }}
```

so a caller reads `steps.preflight.outputs.refused` / `.reason` exactly as
it would for any inline step.

## Call sites in this feature's scope

| File | Step | Existing message reused verbatim |
|---|---|---|
| `wing-commander-preflight/action.yml` | `fail()` helper (all callers of it: credential check, spec-kit check, `require-files`, `require-meta-stage`) | `"wing-commander preflight: $1"` |
| `implement.yml` | `Resolve and validate spec identity` (`id: spec`) | each of the three `grep -Eq` failure branches' existing `::error::` text |
| `implement.yml` | `Verify spec artifacts match the dispatch` (`id: meta`) | both existing `msg="..."` failure branches |
| clarify.yml / finalize.yml / intake.yml / pr-conversation.yml / tasks.yml | whichever step(s) call `wing-commander-preflight`, and any stage-local inline validation step matching the same "declares a precondition, says so, exits 1" shape | enumerated during Phase 2 tasks generation by grepping each file for `uses: .../wing-commander-preflight` and for inline `exit 1` blocks whose message already reads as a refusal (research.md D10's rule, not a fixed list) |

## Explicitly NOT covered by this contract

- `wing-commander-lifecycle-gate`'s own permanent failures (issue not found,
  credential rejected) — classified as abnormal termination, not refusal
  (research.md D10). Its `state`/`is-open` outputs are unchanged; no
  `refused`/`reason` output is added to this composite by this feature.
- The `Note closed lifecycle and stop` step and its `is-open != 'true'`
  condition — unrelated mechanism, already quiet-by-design (FR-004), not
  touched.
- A step failing for a reason it does not itself recognize (an unhandled
  exception, an infrastructure fault) — by construction, never writes
  `refused`, and is therefore correctly classified as abnormal termination
  by the survivor job, per FR-005a's "a failure that emits no such signal
  MUST be treated as an abnormal termination."

## Verification

Gate 28 (contracts/chain-stop-gate-coverage.md) drives each listed step's
shipped shell against a fixture that forces its refusal branch, asserting
`refused=true` and a non-empty `reason` land in `$GITHUB_OUTPUT`, and a
second fixture forcing an *unrelated* failure in the same step (where
possible) asserting `refused` is absent.
