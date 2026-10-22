# Research: Board Loop Self-Merge

The spec has no `[NEEDS CLARIFICATION]` markers; the switch question was settled in its Clarifications. The decisions below are made without owner input, so they are listed in the issue comment.

## D1: Where the merge runs

- **Decision**: A new `merge` job in `board-loop.yml` with `needs: [select, readiness]`. It runs in the same concurrency group and re-fetches its own snapshot.
- **Rationale**: SC-001 asks for a merge in the same run. A separate job gets its own fresh snapshot, so nothing is carried from `readiness`. It also leaves the `readiness` job's text and behaviour untouched while the switch is off (SC-006). It mirrors the lifecycle gate's `merge` job.
- **Alternatives**: Merging inside `readiness` (it would blur "never merges" with the switch-off path and widen Gate 97's scope). A separate workflow (no access to the readiness outputs, and a second concurrency story).

## D2: Fix-class condition sources

- **Decision**: Reuse `board_readiness`'s `_checks_green`/`_gate_suite_green` for checks and gate suite. Readiness's own "ready" decision and the backstop it measured are consumed as `readiness` job outputs, bound to the head readiness measured (`readiness_head_sha`). The merge job re-fetches the snapshot and re-reads the kill switch immediately before the call; the switch variable is the job-start value (no token can re-read it). It also re-reads the issue's review verdicts and requires the newest to have converged on the snapshot's head.
- **Rationale**: This follows the spec's assumption that existing evaluations are reused. The backstop is a function of the head's final diff, so the value readiness measured in the same run is as fresh as a re-measurement while the snapshot's head equals the one it measured; a moved head fails it. Readiness's "ready" is not enough alone: readiness resumed from an earlier run's `step=readiness` marker never re-checks that the review saw the current head, so the merge job binds review convergence to the head itself (FR-003).
- **Alternatives**: Re-running the backstop in the merge job (a second checkout of the PR branch for the same answer). Trusting `readiness` outputs without a head binding (it violates FR-003).

## D3: The bump class's verification record

- **Decision**: The auto-update act job posts a bot-authored PR comment carrying a hidden marker, `wc-bump-verification`, with `head_sha`, `tier` (the verification the stage assigned to the jump), `result` (`passed`/`failed`) and `run_id`. `board_merge.evaluate_bump` accepts a record only if the bot's own login wrote it, `result` is `passed`, and `head_sha` equals the fresh head.
- **Rationale**: The spec says deterministic code must be able to read it. A SHA-bound marker follows the repo's marker pattern, and a head moved by a later push voids it automatically.
- **Alternatives**: A commit status or check run (it needs a new permission, and the stage runs in a consumer-style reusable workflow). Reading the e2e artifact (it is not addressable from the board loop).

## D4: Attributing a PR to the auto-update stage

- **Decision**: The bump class requires all of these: the PR author is the App's bot login; the head ref matches `auto-update-spec-kit/v<semver>`; the PR carries the `auto-update:tracking` linkage in its body marker; and every commit on the PR is authored by the bot (no human-pushed commit on top).
- **Rationale**: This matches the spec's "deterministic signals, never the title" assumption, and User Story 2 scenario 4.
- **Alternatives**: A label alone (anyone with triage rights can apply it).

## D5: Candidate discovery for bumps

- **Decision**: The `merge` job takes a candidate from two sources: the readiness-ready fix PR of this run, or, when select picked no fix, one open PR matching D4. The job picks at most one per run: of the auto-update-shaped PRs not handed over at their current head, the oldest that may merge, else the oldest (review round 1 of PR #1059: one stuck PR must not hide a newer verified one).
- **Rationale**: The loop works one item at a time. The bump PR is not a board item, so select never hands it over.
- **Alternatives**: A separate scheduled poller (a second trigger surface and a concurrency conflict).

## D6: Refusal handling and release

- **Decision**: The merge's stderr is classified in `board_merge.classify_refusal` into `workflow-scope`, `conflict`, `protection` or `other`; the quoted text is always posted. On refusal the handover is posted on the PR and the issue, and the issue marker is written `step=handed-over`. Select treats that step like `awaiting-merge`, so the item is not re-attempted. A bump PR is released by the `refused` outcome marker on the PR until its head moves. Nothing else is tried. A `transient` failure (head or base moved, a 5xx, mergeability being computed) is not a refusal: it is retried once after the decision is re-derived from a re-fetched snapshot, and a second transient failure is announced without a handover (review round 1 of PR #1059).
- **Rationale**: This mirrors the lifecycle merge job's refusal branch and meets FR-010.
- **Alternatives**: Pre-checking the diff for `.github/workflows/` paths (a refusal still has to be handled, and the App's scope could change).

## D7: Switch and kill switch

- **Decision**: `merge` is gated by `vars.WING_COMMANDER_BOARD_AUTO_MERGE == 'true' && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`. The existing `wing-commander-board-stop-check` composite is re-run immediately before the merge step, and every durable step carries `steps.killswitch-recheck.outputs.paused == 'false'` (Gate 97's pattern). The switch variable is read from the `vars` context at job start: re-reading it through the API is not possible, since the App has no Variables permission and `github.token` can never hold one (Gate 12). The stop-check re-run is what catches a mid-run stop.
- **Rationale**: This satisfies FR-006/FR-007 and the edge case for switching off mid-run.

## D8: Prove after an autonomous merge

- **Decision**: After `merged=true`, the job writes the merged item's marker (`step=merged`, with `merge_sha`). The existing `prove-gate`/`prove` jobs then run, and the announcement states why no re-drive is needed when the merged paths run only in gates. Whether a diff is Actions-only is classified by the existing prove-gate logic; this plan adds no second classifier.
- **Rationale**: Spec 096 already holds the durable prove entry (FR-011); wiring is a marker handoff.
- **Alternatives**: Dispatching prove directly from `merge` (it bypasses prove-gate's eligibility).

## D9: Gate design

- **Decision**: `verify-board-merge.py` loads one fixture per condition and refusal branch, asserts `may_merge` is false with the named reason for each, and fails if a fixture directory lacks a case for any name in `board_merge.CONDITIONS` or `REFUSAL_CLASSES`. It also asserts statically that the workflow contains `--match-head-commit`, no `--admin`, no `--auto`, no `gh pr review --approve`, and that the `merge` job's `if:` carries both variables.
- **Rationale**: FR-015 and the CLAUDE.md rule that a "single home" rule needs a gate behind it. `verify-constitution-merge-class-parity.py` is extended so the variable name appears in the constitution and the workflow.
