# Contract: Rename migration for downstream consumers

This project has no library/API surface; its external "interface" is the set
of names a downstream repository pins by exact value: reusable workflow
paths, the `pipeline-repo` default, and the App-token secrets/variables a
wrapper workflow declares. This document is the contract the release that
ships this rename (task/implementation phase) must satisfy, per FR-007 and
FR-010 and the existing release contract
(`specs/010-reusable-pipeline/contracts/versioning.md`).

## What does NOT require adopter action

- `charlesguse/speckit-action/...@v1` (or any exact `v1.y.z`) pins keep
  resolving via GitHub's repository-rename redirect
  (`charlesguse/speckit-action` → `charlesguse/wing-commander`, already in
  effect at the platform level). No file in an adopter's own repo needs to
  change for existing `@v1` pins to keep working.
- Any adopter not yet ready to move to `@v2` is unaffected by every rename
  in this feature — the `v1` floating tag and every existing `v1.y.z` exact
  tag are never modified (`contracts/versioning.md` — breaking releases
  never touch the previous major).
- The GitHub App an adopter already created and named (commonly
  `speckit-bot`) needs no rename; GitHub Apps authenticate by App ID, not
  display name.

## What DOES require adopter action (only on adopting `@v2`)

An adopter moving their pin from `@v1`/`v1.y.z` to `@v2`/a new `v2.y.z` must,
in the same change:

1. Update every `uses:` line from
   `charlesguse/speckit-action/.github/workflows/reusable-<stage>.yml@v1` to
   `charlesguse/wing-commander/.github/workflows/<stage>.yml@v2`
   (both the owner/repo **and** the filename change — the `reusable-`
   prefix is dropped, per FR-009a).
2. Rename their repository secrets/variables:

   | Old name | New name |
   |---|---|
   | `SPECKIT_APP_ID` | `WING_COMMANDER_APP_ID` |
   | `SPECKIT_APP_PRIVATE_KEY` | `WING_COMMANDER_APP_PRIVATE_KEY` |
   | `SPECKIT_TASKS_REVIEW` | `WING_COMMANDER_TASKS_REVIEW` |
   | `SPECKIT_IMPLEMENT_MODEL` | `WING_COMMANDER_IMPLEMENT_MODEL` |
   | `SPECKIT_MAX_ITERATIONS` | `WING_COMMANDER_MAX_ITERATIONS` |

   and update the `secrets:`/`vars:` references in their own wrapper
   workflow YAML to the new names — the underlying values (App ID, private
   key, etc.) do not change, only the secret/variable name.
3. If they pin `pipeline-repo` explicitly (rather than relying on the
   published default), update it from `charlesguse/speckit-action` to
   `charlesguse/wing-commander`.

No other adopter-visible interface changes (job outputs, `workflow_call`
input names other than the filename, label conventions, PR/issue comment
formats) are part of this rename.

## Release process this ships under

Per `specs/010-reusable-pipeline/contracts/versioning.md`: this is a
breaking release (renamed secrets/variables and renamed published
filenames are both "renaming an input/secret" — the contract's own
definition of breaking). It ships via `release.yml`'s `workflow_dispatch`
with `breaking: true` and a `breaking-notes` input enumerating exactly the
two tables above, starting a new major (`v2`) rather than advancing the
existing `v1` floating tag. The GitHub Release's mandatory Breaking-changes
section carries this same content so it is visible to anyone about to
upgrade, before they upgrade.

## Verification

- `grep -rn 'SPECKIT_' .github/workflows/` and `grep -rn 'charlesguse/
  speckit-action' .` return zero hits outside `specs/001-011` (excluded
  historical record) and this feature's own `research.md`/`data-model.md`/
  this contract (which document the old names intentionally).
- `release.yml`'s existing invariant-check gate (the `grep -n
  'charlesguse/speckit-action' .github/workflows/reusable-*.yml` step) is
  updated to check `charlesguse/wing-commander` against the renamed
  `.github/workflows/*.yml` stage files instead, so the gate keeps enforcing
  "the publisher owner/repo string appears only as the `pipeline-repo`
  input default" (FR-005) under the new name.
