# Quickstart: Validating the Skill's Example Cannot Silently Go Stale

This feature ships no user-facing command — it adds one gate and a short
wording addition to an existing skill document. Validation is: run the
gate suite locally (CLAUDE.md "Before pushing"), then walk each user
story's independent test against the real tree and a few deliberate
mutations.

## Prerequisites

- A checkout with `.claude/skills/spec-cross-reference/SKILL.md`,
  `.github/workflows/board-loop.yml`,
  `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`, and
  `.github/scripts/skill-example-drift-waivers.json` at the versions this
  feature ships.
- `python3` and this repo's usual local gate dependencies (no new external
  package, research.md's Primary Dependencies).

## 1. Local gate suite (every user story, fixture-level)

```
python .github/scripts/run-local-gates.py
```

Expect green, including:

- **Gate 125** (`verify-skill-board-loop-concurrency-claim.py`), passing
  against the real tree — the skill's Over-rated example currently
  describes `board-loop.yml`'s actual per-job split (spec.md's own
  "Status update" and Assumptions).
- **Gate 125 self-test**, exercising every `DriftFinding` property and the
  waiver stale-check in both directions against synthetic fixtures
  (research.md D9, contracts/skill-drift-gate.md's Self-test section) —
  never the real files, so this step's pass does not depend on either
  file's current wording.

Per Principle VIII/FR-007, also run the **real-tree mutation** below at
least once locally before trusting the gate (this is not part of CI's own
loop — CI's self-test already covers the mutation *shape* on synthetic
fixtures; this step proves the *real* extraction wiring, not just the
fixture logic, actually reaches the real files):

```
# Flip one job's cancel-in-progress in a scratch copy, confirm the gate
# fails naming both SKILL.md and board-loop.yml:
sed -i 's/cancel-in-progress: false/cancel-in-progress: true/' \
    .github/workflows/board-loop.yml   # first match only in practice; revert after
python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py
git checkout -- .github/workflows/board-loop.yml
```

## 2. Story 1 — the reviewer reaches the right verdict either way (Independent Test)

1. **Given `board-loop.yml` as it stands on `main`**: open
   `.claude/skills/spec-cross-reference/SKILL.md`, follow the Over-rated
   example against a hypothesized two-cycles-race finding. Confirm the
   sentence naming Gate 125 (contracts/skill-example-claim.md item 5) is
   present, run the named command, confirm it passes — the example's quote
   is current, so the refutation is trustworthy.
2. **Given a branch where a selecting job has left the shared group**:
   apply the same `cancel-in-progress` or group-membership mutation as
   step 1 above (or remove `fix`'s `concurrency:` block entirely) on a
   scratch branch. Re-run Gate 125: it fails, naming the job and both file
   locations. A reviewer who checks this before trusting the example does
   not refute the finding on a guarantee that no longer holds.
3. **Given an unrelated finding**: confirm the Over-rated example still
   reads as a transferable lesson (a structural guarantee can refute a
   plausible race) independent of whether Gate 125 currently passes —
   this is a reading check, not a gate check (FR-005's teaching-value
   requirement has no mechanical proof).

## 3. Story 2 — changing the workflow surfaces the doc it invalidates (Independent Test)

1. On a scratch branch, remove `review`'s `concurrency:` block from
   `board-loop.yml` (simulating a job leaving the shared group) and leave
   the skill untouched. Run the gate suite: Gate 125 fails, naming
   `spec-cross-reference/SKILL.md`'s line and `board-loop.yml`'s line
   (Acceptance Scenario 1).
2. Update the skill's job-range token to match (or restore the removed
   block) — Gate 125 passes (Acceptance Scenario 2).
3. On a branch touching neither file, confirm Gate 125 adds no failure and
   requires no manual step (Acceptance Scenario 3) — it is part of the
   ordinary `run-local-gates.py` sweep already.
4. Reproduce step 1's divergence, then add a
   `skill-example-drift-waivers.json` entry
   `{"file": ".github/workflows/board-loop.yml", "check":
   "skill-board-loop-concurrency-claim", "property":
   "job-missing-from-group", "job": "review", "issue": "#<tracking>",
   "reason": "..."}`. Confirm the suite passes with the divergence still
   in the tree (Acceptance Scenario 4) — also confirm Gate 124
   (`verify-waiver-citations.py`) accepts the entry's own shape.
5. With that waiver entry still present, restore `review`'s `concurrency:`
   block (closing the divergence). Confirm Gate 125 now fails on the
   *stale waiver* (Acceptance Scenario 5, FR-014) — remove the entry to get
   back to green.

## 4. Story 3 — a triager settles staleness in one command (Independent Test)

Given only the skill and the repository (no reading of spec 060, the issue
history, or `board-loop.yml`'s commit log):

```
python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py
```

A clean exit with `[ok]`-style lines per checked property is the
"currently true" answer (SC-003/SC-004); a non-zero exit with the
FR-006-shaped message is the "currently false, here is exactly what
diverged" answer. Confirm this matches whichever mutation state (real tree,
or one of Story 2's scratch mutations) is checked out at the time — no
other command or file read is needed.

## 5. Edge cases (spec.md "Edge Cases")

- Rename `board-loop.yml` on a scratch branch (or point the gate's constant
  at a nonexistent path) → Gate 125 fails with `subject-missing`, not a
  silent pass.
- Reflow the Over-rated paragraph's prose or fix a typo without touching
  any backtick token or the queuing clause → Gate 125 still passes
  (FR-009).
- Confirm the `.wing-commander-pipeline/` untracked checkout (if present
  locally) is never read by Gate 125 — it only opens the four repo-root
  paths listed in contracts/skill-drift-gate.md's Inputs section.
