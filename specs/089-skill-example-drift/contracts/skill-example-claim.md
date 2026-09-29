# Contract: The Over-rated Example's Gate-Readable Shape

This is the contract between whoever edits
`.claude/skills/spec-cross-reference/SKILL.md`'s Over-rated example and Gate
125, the check that keeps it honest (FR-002, FR-003, FR-005). It does not
constrain the example's prose beyond the tokens below — FR-005 requires the
example to stay a natural, concrete illustration, not a copy of this
contract's boilerplate the way Gate 101's canonical sentence is deliberately
verbatim-restated (contracts/concurrency-groups.md in spec 060). Reword
freely; keep the tokens and the one clause below.

## What the paragraph must carry (extracted per data-model.md `SkillClaim`)

1. A job-range phrase of the shape `` `JOB_A` through `` `JOB_B`` naming, in
   backticks, the first and last job (in `board-loop.yml`'s own job order)
   that joins the ordinary group. Today: `` `select` `` through
   `` `readiness` ``.
2. The ordinary group name in backticks immediately associated with that
   phrase (a "joins `GROUP`" construction or equivalent). Today:
   `` `wing-commander-board-loop` ``.
3. The directed-proof group name in backticks, associated with "the only
   run allowed to overlap them." Today:
   `` `wing-commander-board-loop-directed-proof` ``.
4. **New in this feature** (research.md D6): a clause asserting the
   queuing/non-cancelling property — the reason the race is refuted is not
   merely "shares a group name" but "a second run in the same group queues
   rather than racing or cancelling." Phrase it however reads naturally;
   the gate looks for the *presence* of this clause, not fixed wording (see
   Verification below), because unlike the three backtick tokens this
   clause has no single canonical token to anchor on.
5. Immediately following the example (same paragraph or the next one): one
   sentence naming Gate 125 by its script path, so a reader can run one
   command to settle currency (FR-008, research.md D8). Example: "This
   claim is mechanically checked against `board-loop.yml` by Gate 125
   (`python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py`)."

## What the paragraph must NOT do

- Restate every structural fact `concurrency-groups.md`'s table already
  owns (e.g., `prove-gate`/`prove`'s split) — the Over-rated example is
  illustrating a review technique, not duplicating the contract. Only the
  four tokens/clause above are load-bearing for the gate.
- Get reduced to a generic "a structural guarantee can refute a race"
  statement with the concrete tokens removed — FR-005 forbids this
  explicitly; Gate 125 would then report `subject-missing` (D-1 in
  data-model.md's `DriftFinding` vocabulary), which is a deliberate,
  loud failure, not a silent pass.

## Verification

Gate 125's extraction (research.md D3) is a bounded scan: find the
Over-rated bullet's anchor phrase, read forward to the next paragraph
break, and pull out items 1-3 as literal backtick-quoted substrings. Item 4
(the queuing clause) is checked by a narrower substring test — the
paragraph must contain a queuing/cancellation word (`queue`, `cancel`) in
the same paragraph as the group tokens, tolerant of exact phrasing but not
absent entirely. Item 5 is checked by requiring the literal script path
`.github/scripts/verify-skill-board-loop-concurrency-claim.py` to appear
within two paragraphs of the anchor. None of these three checks does
sentence-level diffing (FR-009) — a reflow, a typo fix elsewhere in the
paragraph, or rewording around the tokens leaves all three checks
unaffected.

## Ownership

This file is not itself a subject Gate 125 reads at runtime (unlike
`concurrency-groups.md`, which the gate's `JobClassification` extraction
does read, per data-model.md). It documents the shape so a human editing
the skill (or a future implement-stage agent) knows what the gate expects
without reverse-engineering the extraction regexes.
