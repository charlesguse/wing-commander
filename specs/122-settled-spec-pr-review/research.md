# Research: Settled Spec PR Review

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
settle plan-level choices the spec leaves open; each was made without
asking and is listed on the lifecycle issue.

## D1. Workflow shape

- **Decision**: One new wrapper `spec-pr-review.yml` (schedule + `workflow_dispatch` with a `pr` input), jobs select → review → act, copying the *structure* (not the text) of `lifecycle-review-gate.yml`, with shared steps taken from composites.
- **Rationale**: FR-003/FR-022; the trigger cannot be event-driven because the ready announcement is a bot comment (spec Assumptions).
- **Alternatives**: Extending `lifecycle-review-gate.yml` (rejected: FR-001 keeps final PRs solely spec 062's, and its fold/dispatch paths do not apply); event-driven trigger (rejected: bot actors ignored, App lacks Actions permission).

## D2. Where decisions live

- **Decision**: One module `.github/scripts/spec_pr_review.py` exposing pure functions (`is_settled`, `eligible`, `verdict`, `check_fixes`, `plan_actions`, `failed_attempts_exceeded`) with JSON in/out, driven by fixtures.
- **Rationale**: Constitution IX/VIII, FR-025; one home avoids the paste problem in CLAUDE.md.
- **Alternatives**: Inline jq/shell in the workflow (rejected: untestable, drifts).

## D3. Reuse of existing homes (FR-023)

- Marker scan: `.github/actions/wing-commander-clarification-marker` / `_shared/open-clarification-marker.sh`.
- Convergence: `wc_convergence.py` per `specs/116-review-convergence-analyze/contracts/convergence-signals.md`; round records are appended last in the review body and read back from App-authored reviews only.
- Findings shape/fingerprint: `wc_review_finding_fingerprint.py`; rendering via the existing review-body composition used by spec 062 (extracted to a callable if currently inline in the workflow — a task, done by moving, not copying).
- Cost line: `wing-commander-metrics-summary` `cost-line` output.
- Posting: `wing-commander-post-review-comment`, `COMMENT` event only.
- Backstop: `wing-commander-size-path-backstop` for the path/size part of FR-026, with the path bound set to the lifecycle's spec directory.
- **Alternatives**: Re-implementing any of these (rejected by FR-023).

## D4. Settledness inputs

- **Decision**: Select reads, per open PR with head ref prefix `spec-draft/` from this repo: lifecycle issue labels, spec.md at the head SHA, the latest ready announcement comment authored by the App (identified by a stable marker string intake/clarify already emit), and the head commit date. The decision module receives these as a snapshot and returns settled/unsettled with a named reason.
- **Rationale**: Re-derive at selection and again immediately before every write (spec Edge Cases).
- **Open detail resolved**: The announcement is matched on author (App login) plus the existing announcement marker; the implement task confirms the exact marker text in intake/clarify and the verifier fails if it cannot find one.

## D5. Round budget, failed attempts, hand-off

- **Decision**: Budget `5` as a one-line knob in the workflow env; failed attempts capped at `2` per head, counted from per-head failure notes on the lifecycle issue carrying the head SHA; both caps evaluated in the decision module.
- **Rationale**: FR-018, FR-028. Counting from issue comments keeps state GitHub-native (III).
- **Alternatives**: Artifacts or a variable (rejected: expire / write permission).

## D6. Fix backstop (FR-026)

- **Decision**: Compute the round's diff in a clean checkout of the reviewed head; the module checks (1) every path under the spec directory, (2) added+deleted lines ≤ cap (default 200, one-line knob), (3) each fix's cited precedent resolves: default-branch `file:line` via `git show origin/main:path`, head `file:line` in spec files via the checkout, issue-comment citation via `gh issue view`/API read confirming the comment exists. Marker-line additions are checked for path and size only.
- **Rationale**: Mirrors constitution X's size-and-path backstop.

## D7. Pushing and credentials

- **Decision**: Push with the App token via `wing-commander-hardened-push` to the PR's `spec-draft/` branch only after re-fetching head SHA and PR state; push refusal downgrades to report-only (FR-015c fallback). The commit status uses the workflow `GITHUB_TOKEN` with job-level `statuses: write`.
- **Rationale**: FR-016, FR-015b. No Workflows permission is needed because only spec-dir files change.

## D8. Model, effort and knobs

- **Decision**: Variables `WING_COMMANDER_SPEC_REVIEW_MODEL` (default `claude-opus-5-5`), `WING_COMMANDER_SPEC_REVIEW_EFFORT` (default `high`), kill switch `WING_COMMANDER_SPEC_REVIEW_PAUSED`. Turn budget set via the `turn-ceiling` composite. Documented in `docs/setup.md`.
- **Rationale**: FR-008, FR-020, Constitution II.

## D9. Maintainer dispatch (FR-027)

- **Decision**: Dispatch input `pr`; the module receives `triggering_actor_type` and the actor's association; a bot actor or a non-maintainer is rejected. A valid dispatch bypasses only the announcement and unchanged-head checks.

## D10. Vendor tests for SC-004

- **Decision**: Replay fixtures for #1078 (spec 119 FR-022) and #1086 (spec 120 FR-002) are recorded as *decision-module* fixtures (snapshot of facts → expected finding class), since the agent's prose cannot be gated in CI. A one-off live replay is part of quickstart, not a gate.
