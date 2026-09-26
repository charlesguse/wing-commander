# Contract amendment: the generalized readiness-check workflow (job summary)

Amends `specs/053-e2e-scratch-provisioning/contracts/readiness-workflow.md`
in place (FR-010, User Story 1 Acceptance Scenario 5). Location, trigger,
inputs, target resolution, token minting, and the cost contract (SC-006)
are unchanged. Only step 4's job-summary rendering and exit behavior
change, to carry the tri-state `ElementCheckOutcome`/`AggregateVerdict`
`../data-model.md` defines.

## Behavior (replaces 053 readiness-workflow.md's step 4)

4. Write the `ReadinessReport` (`../contracts/readiness-report.schema.json`)
   as a `GITHUB_STEP_SUMMARY` table, one row per element, rendering
   `outcome` as three visually and textually distinct states — not the
   binary ✅/❌ 053 originally specified:

   | `outcome` | Rendering |
   |---|---|
   | `ready` | ✅ |
   | `missing` | ❌ |
   | `not_checkable` | ➖ (or an equivalently distinct glyph — never ✅ or ❌) |

   Each row's "Remaining action" column is populated the same way for
   `missing` and `not_checkable` (both carry a non-null
   `remaining_action`); a reader must be able to tell the two apart from
   the status glyph and text alone, without reading the remaining-action
   prose (User Story 1 Acceptance Scenario 5, SC-002).

   The summary's aggregate line names which of the three verdicts the run
   reached (`all_clear` / `not_clear` / `unverified`), not just pass/fail,
   and the step exits with `provision-e2e-target.sh`'s own exit status
   (`0`/`1`/`2` — `../contracts/cli.md`) unchanged from how the existing
   step already propagates `rc`.

## Compatibility

A dispatch with no inputs still reproduces the `spec-kit-scratch` profile's
existing `all_clear`/exit-`0` outcome on a fully onboarded target
byte-for-byte in substance (FR-011) — the rendering changes (three glyphs
instead of two, a named verdict instead of an implicit pass/fail), but a
target that was `ready: true` under 053's contract is `verdict: all_clear`
under this one, with the same exit code (`0`).
