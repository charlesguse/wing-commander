# Contract: shared scripts and composite surface

Layer: internal scripts under `.github/actions/_shared/` (not published,
Principle VII) plus one additive widening of the published
`wing-commander-tasks-checkbox-count` composite.

## count-tasks-checkboxes.sh `<ref> <path>`

Existing outputs unchanged. New `$GITHUB_OUTPUT`-shaped lines:
`impl-checked-count=<n>`, `impl-unchecked-count=<n>`, `standing-count=<n>`,
and heredocs `impl-unchecked-items` (delimiter
`WING_COMMANDER_IMPL_ITEMS_EOF`) and `maintainer-items` (delimiter
`WING_COMMANDER_MAINTAINER_ITEMS_EOF`). Still exits non-zero with no stdout
when `ref:path` is unreadable. A file with no markers classifies every
non-standing line as implementation.

## validate-implement-blocker.sh `<blocker-json-path> <tasks-ref> <tasks-path>`

Prints `blocker-valid=true|false`, `blocker-text=<kind: detail (task)>` (empty
when invalid) and `blocker-invalid-reason=<text>`. Always exits 0 for an
invalid or missing blocker (that is an expected input); exits non-zero only
when tasks.md is unreadable.

## decide-implement-outcome.sh (env or flags per data-model.md)

Prints `converged`, `progressed`, `handoff`, `stall-reason`,
`stall-comment` (empty unless handoff or cap with implementation
outstanding; includes the outstanding count and reason, FR-006).

## render-remaining-work.sh `<maintainer-items-file> <impl-items-file>`

Writes markdown to stdout: `## Maintainer steps`, `## Unfinished
implementation` and a stall statement when the second list is non-empty;
empty output when both are empty. Used for both `finalize-remaining.md` and
the lifecycle announcement body.

## Composite surface

`wing-commander-tasks-checkbox-count` gains outputs `impl-checked-count`,
`impl-unchecked-count`, `impl-unchecked-items`, `maintainer-items`,
`standing-count`. Additive; no existing output renamed or removed.
