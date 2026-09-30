# Contract: Stall Integrity and Stand-Down Invariants (FR-001-005, FR-009-011, FR-012-015)

States, for review, what this feature preserves unchanged versus what it
adds a checked-in case for. No behavior described in this document as
"preserved" is modified by this feature.

## Preserved (FR-001-005 — #782, `add_stalled_label()`)

Every one of the eight stall sites applies `board:stalled` before posting
the `stalled` marker, and fails loudly with no marker on a failed label
application, naming what a later run will do (and, at route/fix/readiness,
naming an already-filed `spec-request` so a retry reuses it rather than
filing a second). This is `board_item_marker.add_stalled_label()`
(`board_item_marker.py:170-213`), already covering every site. This feature
adds no new stall site and changes none of these eight call sites' ordering.

FR-004's derivation (the check enumerates stall sites from the workflow
itself) and FR-005's fixture (reverting one site to marker-before-label must
fail and name that site) are Gate 97-adjacent coverage already in place;
this feature's new gate (research.md D8) is a distinct gate for the
re-admission *rule*, not a re-implementation of this one.

## Preserved (FR-012-015 — #782, readiness stand-down gating)

Every durable action readiness takes is gated on its own pre-action
re-check of the kill switch and stop requests
(`board-loop.yml:3696-3934`), a stand-down leaves the item's marker
unchanged, and the readiness decision's own `kill_switch_paused` refusal
stands as deliberately redundant defence behind the per-write gate. This
feature changes none of it.

## Added: FR-009's budget statement, gated

Restates research.md D4 as a checked property: a re-admitted item that
resumes at `review` (contract: `resume-recovery-readmission.md`, clause 2b)
starts with `round == 0` — the same starting value a freshly selected item
gets, because every stall site's marker call omits `--round` (confirmed at
all eight sites) and clause 2 does not otherwise carry a round value
forward. The new gate (research.md D8) asserts this with a fixture: a
re-admitted item at `review`, spending a fresh `BOARD_LOOP_ROUND_BUDGET`
(5) rounds, stalls again on the same terms (SC-006).

## Added: FR-010's no-extra-invocation property, gated

Restates research.md D5: an FR-002 retry re-enters the stalling job and
reaches its stall/continue decision from the marker's already-recorded
state before any agent step runs. The new gate's fixture set includes a
retry case asserting the job graph's agent step is not reached on the path
from a re-entered job to its label-add retry.

## Added: FR-011's run summary records

Three sites now write a `GITHUB_STEP_SUMMARY` line (research.md D6,
data-model.md "Run Summary Record"): the resume step's clause-2 split
(naming the resolved step and why), a stall site's successful retry after a
prior FR-002 failure (naming the retry), and readiness's stand-down
(already existing, #782, unchanged). SC-009 requires all three to be
readable without log archaeology; the new gate checks that each site's
`run:` step contains the `GITHUB_STEP_SUMMARY` append.

## FR-020: FR-006 does not contradict spec 057 FR-030

`labels-and-cross-links.md`'s table row for `board:stalled` states
"Cleared by: a human removing the label — the sole condition FR-010 [of
spec 057] reads for re-eligibility." FR-006 adds no second label and no
second re-eligibility mechanism — this feature's implementation adds one
sentence to that table row's "Cleared by" cell, cross-referencing this
spec's `resume-recovery-readmission.md` for what happens *after* the label
is cleared, so a future reader of `labels-and-cross-links.md` does not have
to separately discover `resume-recovery.md` to learn the consequence of
removing `board:stalled`. No row, column, or label is added.

## FR-021: published contract unaffected

Every change this feature makes is inside `board-loop.yml` (a consuming-
instrument wrapper workflow) and `.github/scripts/` — no `workflow_call`
stage workflow interface and no published composite action interface
changes (Constitution VII).
