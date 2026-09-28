# Contract: `verify-errexit-claim-comments.py` (FR-007/FR-008/FR-009)

This is the new gate this feature ships. It is registered in
`lint-workflows.yml` as `Gate <N>` (the next sequential number after the
highest shipped at tasks-generation time — see research.md D5) and is
therefore part of the PR-time suite `run-local-gates.py` derives
automatically; no separate wiring is needed beyond adding the step.

## Scope

| Directory | Pattern | Included? |
|---|---|---|
| `.github/workflows/` | `*.yml` | yes |
| `.github/actions/` | `*/action.yml` (direct children) | yes |
| `.github/actions/` | `**/action.yml` (recursive, e.g. `_shared/`-nested) | yes |
| `.github/scripts/`, `docs/`, `specs/` | — | **no** — comment scanning is scoped to executable workflow/action YAML, where a false errexit claim can mislead a reviewer of *running* shell; prose docs are out of scope for this feature (FR-007 names five specific comment sites, all in `.github/workflows/` or `.github/actions/`) |

Deliberately **not** matching Gate 24's `.github/workflows/*.yml`-only
scope (research.md D5): the FR-001 violation this feature fixes lives in
`.github/actions/wing-commander-board-stop-check/action.yml`, so a gate
that could not see action files could not have caught it.

## What counts as a violation

A comment block (per `verify-comment-canonical-pointers.py`'s
`comment_blocks()`/`_joined()` — imported, not re-implemented, per
CLAUDE.md "Shared logic has exactly one home") contains one of the phrase
patterns in research.md D6:

- `run(s) without -e` / `run(s) without errexit`
- `without errexit`
- `` with no `-e` ``
- `` no `-e` `` (bare, un-negated)
- `` clears `-e` `` / `` clear `-e` `` (bare, un-negated)

**Excluded** (not violations):

- The match falls within three words of a negation term (`not`, `never`,
  an `n't`-suffixed word, `doesn't`, `does`, `cannot`) — covers "does not
  clear `-e`", "never runs without errexit".
- The match falls inside a quoted span (`"..."`, `'...'`, `` `...` ``)
  longer than the flag token alone — covers a comment that quotes the
  wrong claim in order to correct it.

## Failure output

One `::error::` per surviving violation, naming the file and the comment
block's starting line (matching `verify-comment-canonical-pointers.py`'s
own `::error file=...::` convention), plus a final summary line
(`N file(s) scanned, M violation(s)`) matching this repository's other
gate scripts' summary-line convention. Exit `1` if any violation survives,
else `0`.

## Self-test (`--self-test`)

Synthetic fixtures built in a tempdir (not checked-in files — the subject
is the *live* tree's comments, per `verify-comment-canonical-pointers.py`'s
own stated rationale for the same choice), asserting:

1. A comment correctly stating errexit is active (using the gate's own
   canonical phrasing) produces no violation.
2. A comment quoting the false claim to correct it (inside a longer quoted
   span) produces no violation.
3. A comment using the negated true form ("does not clear `-e`") produces
   no violation.
4. Each of the five bare, un-negated phrase patterns above, introduced
   fresh, is caught, naming the right file and line.
5. **Mutation coverage (FR-009)**: taking the *shipped, corrected* text of
   each of the five corrected sites (the real `run:`-adjacent comments this
   feature ships) and mutating it back to its pre-fix false claim must be
   caught — proving the gate can fail its own subject, not only a
   fixture written for the gate.

## Relationship to Gate 47 (`verify-comment-canonical-pointers.py`)

Independent gates, no shared registration:

- Gate 47 validates that a `-- see FILE.` pointer resolves and shares
  vocabulary with its target — it does not know what a "false errexit
  claim" is.
- This gate validates that no comment (anywhere in its scope) asserts the
  false claim — it does not validate pointer syntax.

The five corrected sites use both: a short local statement plus a
`-- see verify-errexit-claim-comments.py.` pointer at the canonical
statement (this gate's own docstring, D4). The four workflow-file sources
are validated as real Gate 47 pointers (target exists, topic overlap); the
`board-stop-check` composite's pointer is not a Gate 47 source (action
files aren't scanned by Gate 47) but is still real prose for a human
reader, and this gate's own scope (including action files) is what
actually enforces correctness there.

## What this gate does not do

- It does not rewrite or deduplicate comment prose (same exclusion Gate 47
  states for itself).
- It does not evaluate whether a step's *logic* actually depends on the
  false premise (FR-010's re-check is a one-time, hand-performed step
  recorded in spec.md's Observed Facts and research.md D9, not an ongoing
  gate — the four already-corrected sites are declared safe there).
- It does not touch `.github/scripts/*.py`, `docs/**`, or `specs/**` (out
  of scope, see table above).
