# Contract: Gate 135 — `verify-stop-point-recording.py` (FR-019)

Gate number confirmed at plan time was 128 (current maximum on `main` was
then 127, `specs/091-gh-api-error-capture`); renumbered to 135 (maintainer
review fold leg-3): 128 collided with spec 074's own gate (PR #821,
confirmed open), and 129-134 are taken or allocated to specs 089/108/109
and others. Gate numbers are a convention enforced by
`verify-gate-wiring.py`/`run-local-gates.py`, not a stored list —
`.github/scripts/wc_gate_registry.py`. Registered in `.github/workflows/
lint-workflows.yml` as a "Gate 135 — ..." step plus a "Gate 135 self-test
— ..." step, following the exact two-step pattern every other gate uses
(e.g. Gate 97/`verify-board-loop-resume-gating.py`, Gate
47/`verify-comment-canonical-pointers.py`).

## What it must fail on (pre-fix) and pass on (post-fix) — SC-009

| # | Check | Fails when | Passes when |
|---|---|---|---|
| 1 | Composite record-write present | `.github/actions/wing-commander-board-stop-check/action.yml` has no step that, gated on `stop-cause == "stop-request"`, invokes `board_item_marker.py --step stalled ... --add-label "board:stalled"` | the step is present |
| 2 | Provenance | that invocation (and `board_stop_check.py`'s own) references a bare `.github/scripts/...` path instead of `$GITHUB_ACTION_PATH/../../scripts/...` | both are invoked from the composite's own trusted directory (spec 095 FR-011/FR-012, research.md D8/D8 addendum) |
| 3 | Cause-aware messaging | any of the six stand-down message strings in `board-loop.yml` hardcodes "kill switch" prose unconditionally (the pre-fix shape at, e.g., `board-loop.yml:1412`) | each reads `stop-cause` (or the composite's `stop-cause` output) to select its wording (FR-014) |
| 4 | Decision-function agreement | `find_stop_command_comment()`'s "did a comment win" answer disagrees with `find_stop_request()`'s `stand_down` on any fixture in Gate 87's corpus, or on the new FR-016/FR-009/FR-006/FR-008 fixtures this gate adds | the two agree on every fixture (research.md D2's invariant) |
| 5 | Selection exclusion | a fixture issue carrying `{"step": "stalled", "round": 0, "pr": null, "branch": null, "base_sha": null}` plus `board:stalled` is still returned by `board_eligibility.in_flight_candidate()` or `select()` | it is excluded by both, on every one of ten simulated successive selection passes (SC-001) |
| 6 | No write on kill-switch-only / closed-issue | a fixture composite invocation with `stop-cause` resolving to `"kill-switch"` or `"closed-issue"` still reaches the record-write block | it never does (FR-011/FR-013) |
| 7 | No caller-populated snapshot dependency | the composite's own script resolutions reference `$RUNNER_TEMP/wc-pristine` (maintainer review fold leg-0) | they resolve only via `$GITHUB_ACTION_PATH`, never a caller-populated snapshot (spec 086 FR-003) |

## Self-test (Principle VIII: the gate must be shown to fail its own subject)

For each check above, `--self-test` applies the corresponding mutation to
an in-memory or temp-file copy of the checked artifact and asserts the
check then reports failure:

1. Delete the record-write step's `if:` condition or its body → check 1
   fails.
2. Rewrite the invocation to a bare `.github/scripts/...` path → check 2
   fails.
3. Restore one hardcoded "kill switch" string → check 3 fails.
4. Feed a hand-crafted fixture where a comment matches `is_stop_command()`
   but predates a synthetic baseline in one function's copy of the logic
   and not the other → check 4 fails (this is the mutation Gate 87 cannot
   catch, since Gate 87 only proves `find_stop_request()` alone). A second
   mutation reverts `find_stop_request()` alone to a baseline computation
   that advances on every marker, including same-run-id ones (the pre-fold-
   leg-1 shape) → check 4 fails on the own-run-record fixture (FR-006/
   FR-008), since `find_stop_command_comment()` still disagrees using the
   current (fixed) same-run exclusion.
5. Feed a marker fixture with `board:stalled` label omitted → check 5's
   assertion about exclusion no longer holds *because* the fixture is now
   a normal in-flight marker, proving the check is actually reading the
   label, not vacuously passing.
6. Force `stop-cause` to `"kill-switch"` in a fixture that also satisfies
   the record-write block's own gating condition (a deliberately broken
   `if:` that ignores `stop-cause`) → check 6 fails.
7. Revert the `check` step's `board_stop_check.py` invocation to
   `$RUNNER_TEMP/wc-pristine/scripts/board_stop_check.py` (the pre-fold-
   leg-0 shape) → check 7 fails.

## What this gate does NOT check

- It does not re-verify `find_stop_request()`'s own decision correctness —
  that is Gate 87's job, unchanged (research.md D1).
- It does not execute `board-loop.yml` in Actions — like Gate 97, it is a
  structural/text-and-fixture check runnable locally via `python .github/
  scripts/run-local-gates.py`, per CLAUDE.md's "Before pushing" section.
- It does not check spec 100's resume-step behaviour (which step a released
  item resumes at) — out of scope for this feature (data-model.md "Stop
  Point Record" lifecycle note).

## Acceptance mapping

- FR-019 — checks 1–3 and 6 directly test "a change that removes the
  recording..., that makes the kill-switch-only path write..., or that lets
  a recorded stop be re-selected" fails this gate.
- SC-009 — the self-test section proves each check can fail its own
  subject, on the pre-fix shape specifically (the mutations above restore
  exactly the pre-fix code shape observed in spec.md's "Observed facts"
  and 2026-09-30 status update sections).
