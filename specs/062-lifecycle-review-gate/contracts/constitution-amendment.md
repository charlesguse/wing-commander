# Contract: Constitution Amendment (FR-031–FR-033, FR-038)

This document states what the amendment PR must contain; it is not itself
that PR (research.md D16). The amendment is drafted and merged separately
from this feature's own implementation, by a human, against `main`.

## Required edits (FR-031)

1. **Principle V**'s sentence: "The only merges the bot may perform are
   the two classes Principle X defines — the bounded fix-PR merge and the
   verified dependency-bump merge — behind X's deterministic gates and
   kill switch; a bot merge outside those classes violates this principle
   rather than extending X." becomes three classes, naming the lifecycle
   pull request merge this feature adds.
2. **Principle X**'s closing sentence: "What stays human is unchanged:
   the spec, plan and final PR merges of the feature lifecycle, every
   amendment to this document, and every route that reaches
   `spec-request`." is corrected — the *final PR merge* clause can no
   longer read as unconditionally human once the setting is on; the
   amendment states precisely that it stays human **only while
   `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is off**, mirroring how Principle
   X already states the fix-PR-merge and dependency-bump-merge classes'
   own bounds inline rather than by cross-reference alone.
3. **Principle X**'s body gains a paragraph for the third class, in the
   same terms the fix-PR class already uses (FR-032): the deterministic
   gates it must clear (data-model.md §5 — the eight conditions
   `lifecycle_merge_preconditions.py` checks), the kill switch that stops
   it (`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED`), and that it is a
   squash commit one human action reverts (FR-028).

## Required Sync Impact Report entry (FR-032)

A new stacked comment block at the top of the file, following the
existing convention exactly (version bump, "Modified principles",
"Modified sections", "Added sections", "Removed sections", "Templates
requiring updates" checklist, "Motivation", "Worked example", "Follow-up
TODOs"). Version bump: MINOR at minimum (a new authorized class, not a
breaking redefinition of an existing one — unlike the 1.6.1 → 2.0.0 bump
that first introduced Principle X, this amendment adds a third instance
of an already-established pattern rather than redefining what "the bot
never merges" meant). The Sync Impact Report's own "Templates requiring
updates" checklist must be walked the same way every prior amendment's
has been (README.md's principle-list summary, docs/architecture.md's
merge-authority bullet, per the 2.0.0 entry's own precedent).

## Gate: `verify-constitution-merge-class-parity.py` (FR-038)

**What it checks**: presence-implies-documented, not absence-implies-
forbidden (the inverse of `verify-board-readiness.py`'s
`check_no_merge_invariant`, which scans for forbidden merge calls in
`board-loop.yml`). This gate scans `.github/workflows/lifecycle-review-
gate.yml` for the merge capability's own code (a `gh pr merge` call
gated by `WING_COMMANDER_LIFECYCLE_AUTO_MERGE`); if that code is present,
the gate requires `.specify/memory/constitution.md`'s Principle V and
Principle X text to name a third class (a regex/text-presence check for
language distinguishing three classes rather than two, and for the
`WING_COMMANDER_LIFECYCLE_AUTO_MERGE`/`WING_COMMANDER_LIFECYCLE_REVIEW_
GATE_PAUSED` variable names or an equivalent named reference). If the
merge code exists and the constitution does not name the class, the gate
fails and says so (US5 scenario 1, SC-007).

**Self-test / fixtures**: a synthetic workflow fixture carrying the merge
call with no matching constitution text (must fail), a synthetic
constitution fixture carrying the class language with no merge call in
the tree (must pass — capability absent is never itself a failure; only
the presence-without-documentation direction is checked), and the real
repository state both before this feature's merge code lands (passes
vacuously — no merge call to require documentation for) and after
(requires the amendment to be present too).

**Ordering this gate enforces in practice**: a maintainer can merge this
feature's own implementation PR (adding the merge *code*, inert while
`WING_COMMANDER_LIFECYCLE_AUTO_MERGE` defaults off) before or after the
constitution amendment PR, but `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` can
never be safely set to `true` until the amendment PR is also merged — the
gate is what makes that a checked fact rather than a documented
expectation a maintainer has to remember.
