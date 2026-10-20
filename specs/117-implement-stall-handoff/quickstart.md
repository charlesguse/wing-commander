# Quickstart: validating the feature

Prerequisite: the repository checkout with Python 3 and PyYAML.

1. Run the full local gate suite: `python .github/scripts/run-local-gates.py`.
   It includes `verify-implement-stall-handoff.py`, which drives the
   fixtures in `.github/scripts/fixtures/117-implement-stall-handoff/`
   through the shared scripts (see contracts/shared-scripts.md).
2. Classification (US1/US2): run `count-tasks-checkboxes.sh` against the
   mixed fixture tasks.md; expect maintainer, implementation and standing
   counts as in the fixture's expected file.
3. Stop rule (US3): the decide fixtures cover no-blocker (dispatch), valid
   blocker (handoff with quoted reason), malformed blocker (dispatch), cap
   (handoff), progress (dispatch), last task checked (converge).
4. Finalize (US1): render the #1022 and #737 replay fixtures; expect SC-001
   and SC-002.
5. After merge, prove in Actions: dispatch implement manually on a
   review-stage lifecycle and confirm the lifecycle-issue comment (FR-010);
   use the `prove-after-merge` skill.
