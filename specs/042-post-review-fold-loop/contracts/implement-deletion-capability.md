# Contract: `implement.yml` and `stage-interfaces.md` — tracked-file deletion capability

Delta against the published stage contract
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`, "Per-stage
default tool lists," 248–294). No `workflow_call` input, output, or
secret changes (FR-016) — this is a tool-grant widening only.

## Call-site edits

| Call site | File:line | Change |
|---|---|---|
| `implement.cycle` | `implement.yml:725` (`default-allowed-tools`) | append `,Bash(git rm:*)` |
| `implement.retry` | `implement.yml:1086` (`default-allowed-tools`) | append `,Bash(git rm:*)` |

No edit to `implement.yml:1492` (`implement.post-progress-comment`) —
read-only, out of scope.

## Contract-document edit

`specs/010-reusable-pipeline/contracts/stage-interfaces.md`: the
`implement.cycle` row (line 274) and `implement.retry` row (line 275) each
gain `Bash(git rm:*)`, matching the call-site edits exactly, in the same
change (per the table's own maintenance note, 289–294).

## Scope and guardrails (FR-011a, FR-013)

- Confined to the specification branch checkout — no new checkout, no new
  token, no new working-directory change; `git rm` operates within the
  same single-branch clone (`implement.yml:554–561`) every other write verb
  already operates within.
- Tracked files only: `git rm <path>` fails (non-zero exit, no working-tree
  change) against a path git does not track. No new logic distinguishes
  tracked from untracked — the command's own semantics are the boundary.
  An untracked-file removal request continues to surface as "remaining
  manual work," exactly as today (FR-011a's explicit exclusion, Out of
  Scope's "removing files that are not tracked").
- No constraint on any existing write verb is weakened to accommodate
  this grant (FR-013) — `git rm` is additive to the existing literal list,
  nothing removed.

## Divergence enforcement (FR-014)

Enforced by the existing Gate 27 (`verify-stage-tool-lists.py`,
`lint-workflows.yml:2730–2734`), unmodified by this feature. Gate 27 already
parses every `wing-commander-tool-args` call site and cross-checks it
against `stage-interfaces.md`'s table; editing the call sites without the
table (or vice versa) fails Gate 27 on the next run. No new gate is added
for this sub-feature (research.md D12).

## Adoption (FR-015)

The grant lives in `implement.yml`'s own `default-allowed-tools` value,
resolved through the existing `wing-commander-tool-args` composite
(specs/026) — an adopting repository receives it automatically on the next
pin bump, with no wrapper-workflow edit, and any per-repository
`extra-allowed-tools`/`allowed-tools-override` an adopter has already set
continues to compose exactly as it does today (the composite's existing
`extra-*`/`*-override` precedence is unmodified).

## FR-012 — cycle, retry, and convergence do not diverge

Satisfied by construction: convergence (`/speckit-converge`) is step 3 of
the same agent prompt as steps 1–2 in both `implement.cycle` and
`implement.retry` (`implement.yml:798–803`, `1184–1189`), sharing whichever
of the two edited grants above is active for that job. There is no third,
independently-maintained tool list for convergence to drift from.
