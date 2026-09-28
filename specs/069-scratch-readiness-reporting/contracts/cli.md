# Contract amendment: `provision-e2e-target.sh` CLI (readiness/exit behavior)

Amends `specs/053-e2e-scratch-provisioning/contracts/cli.md` in place
(FR-010). Everything in that document not named below is unchanged:
invocation shape, flags, preconditions, the `--check-only` semantics, the
no-deletion/no-credential-printing/no-App-token/idempotency guarantees.

## Exit status (replaces 053 cli.md's step 5)

5. Exit status is a faithful summary of `ReadinessReport.verdict`
   (`../data-model.md`), never computed any other way:

   | `verdict` | Exit status | Meaning |
   |---|---|---|
   | `all_clear` | `0` | Every required element is `ready`. |
   | `not_clear` | `1` | At least one required element is `missing` — same code this script already uses for every other failure (bad flags, self-refusal, a failed privileged write), so "something is wrong" stays one code across all of this script's failure modes. |
   | `unverified` | `2` | Nothing is `missing`, but at least one required element is `not_checkable` by this route. |

   A run MUST NOT exit `0` for `unverified` or `not_clear` (FR-004). A
   caller that only reads the exit status alone tells all three outcomes
   apart (SC-008) — this is the one behavioral difference from 053's
   original two-valued (`0`/`1`) contract, and the reason 053's cli.md is
   corrected rather than left to imply a caller can treat any non-zero exit
   as "not ready" in the old sense.

## Scratch-marker refusal scope (053 cli.md `:17`/`:51` correction, FR-010)

The `scratch_marker` refusal described in 053's cli.md applies to the
**mutating path only** (no `--check-only`). It was already implemented this
way (`.github/scripts/e2e-provisioning/checks.sh`'s
`WC_CHECK_ONLY` exemption, T044) before this feature; 053's own contract
text is the only thing out of date, and User Story 2 corrects it to state
this scope explicitly rather than describing the refusal as if it also
gated the read-only path.

## Honoured-hint disclosure (new, FR-015)

When a run's `app_installation` outcome is `ready` because
`WC_APP_INSTALLATION_KNOWN_READY=true` was set (see
`../data-model.md`'s `AppInstallationAssertionHint`), the human-readable
summary this script prints on stderr states that the hint was honoured, so
a false-`ready` report traceable to a stray shell value is traceable from
the script's own output, not only from re-reading its source
(`docs/setup.md` names the hazard, FR-016).

## Failed repository creation (new, FR-013)

If the privileged `repository` action (`gh repo create`) fails, the run
stops immediately, reports repository creation by name as the failed
action, and attempts no further privileged action — in particular it never
reaches the `scratch_marker` write, and never reports "failed to write the
scratch marker" for what was actually a failed repository creation. This
corrects the one behavior 053's cli.md never claimed but its
implementation silently violated (originating review item 7, `#374`).
