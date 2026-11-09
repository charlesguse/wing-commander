# Contract: `spec-pr-review.yml` (consuming instrument)

Layer: consuming instrument only (Constitution VII). Adds no
`workflow_call` input, secret or output to the published contract.

## Triggers

- `schedule` (cron, same cadence family as `lifecycle-review-gate.yml`).
- `workflow_dispatch` with one input `pr` (PR number). The triggering actor
  must be a maintainer and not a bot (FR-027).

## Jobs

1. **select** — stand-down check on `vars.WING_COMMANDER_SPEC_REVIEW_PAUSED`; list open PRs; build a `SpecPrSnapshot` per candidate; call `spec_pr_review.py select`; emit at most one PR and head SHA, or a recorded skip reason per PR.
2. **review** — checkout the PR head (same-repo `spec-draft/` ref only); re-check eligibility on a fresh snapshot; run the reviewer (`claude-opus-5-5`, `high`, bounded turns) with spec content framed as untrusted data; extract and validate findings; `spec_pr_review.py classify-and-check` produces the verified `ActionPlan`; post one `COMMENT` review (verdict, findings, round record last, cost line from the metrics-summary composite).
3. **act** — re-fetch PR state and head; if still open and head unchanged, push fixes/markers via the hardened-push composite (spec directory only), move label (only after markers pushed), post issue questions, post the one-line outcome, post the ready announcement when `ActionPlan.post_announcement`; post commit status (own context, workflow token, job-level `statuses: write`).

## Guarantees

- Never `APPROVE` or `REQUEST_CHANGES`; never merges (FR-010).
- Status context differs from spec 062's and is not made required (FR-016).
- Failure paths report failure and never "ready for the owner" (FR-021).
- Concurrency: one run at a time (group `spec-pr-review`), no cancel of an in-progress round.

## Repository variables (documented in `docs/setup.md`)

| Variable | Default | Effect |
|---|---|---|
| `WING_COMMANDER_SPEC_REVIEW_PAUSED` | unset | `true` ⇒ no round, stand-down recorded |
| `WING_COMMANDER_SPEC_REVIEW_MODEL` | `claude-opus-5-5` | reviewer model |
| `WING_COMMANDER_SPEC_REVIEW_EFFORT` | `high` | reviewer effort |
