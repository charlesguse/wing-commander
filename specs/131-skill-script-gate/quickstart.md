# Quickstart: validating the skill-script gate

Prerequisites: repo checkout, Python 3 with PyYAML, git.

1. **Clean tree passes**
   `python3 .github/scripts/verify-skill-scripts.py` -> exit 0, `OK` line
   showing six scripts and one self-test (`thrash_signals.py`).
2. **Rename is caught (US1)** On a scratch copy, rename `diff_name_list` in
   `.github/scripts/board_route_backstop.py`; rerun -> exit 1, line names
   `redrive_candidates.py`, `board_route_backstop`, `diff_name_list`. Repeat
   for `wc_convergence.decide` (attribute use) and `wc_board_status.render`.
   Delete a whole imported module -> `missing-module`.
3. **Self-test runs (US2)** Change an expected value in
   `thrash_signals.py`'s self-test on the scratch copy -> exit 1,
   `self-test-failed`.
4. **Gate can fail (US3)** `python3 .github/scripts/verify-skill-scripts.py --self-test`
   -> exit 0; see the cases in
   [contracts/verify-skill-scripts.md](contracts/verify-skill-scripts.md).
5. **Derived into the suite (FR-007)** `python .github/scripts/run-local-gates.py skill-scripts`
   runs both steps.
6. **Housekeeping (FR-009)** PR #1205 is closed with a pointer to #1206;
   backlog line `bl-ddabf5f6` is ticked via `board_backlog_edit.py` on merge.
7. **Timing (SC-004)** the two steps together finish in under one minute.
