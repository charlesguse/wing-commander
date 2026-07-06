# Phase 0 Research: Plan Stage

All items below were resolved without unblocking [NEEDS CLARIFICATION]
markers in `spec.md` — the specification's own clarification round already
settled the product-level questions. What remains here are implementation
decisions the plan makes on the specification's behalf.

## 1. How is the merged pull request matched to a specification?

- **Decision**: Derive the spec slug from the merged PR's head branch name
  (`spec-draft/NNN-slug` → `NNN-slug`), validated against
  `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`. Fall back to a `workflow_dispatch` `slug`
  input for manual restarts. Refuse (hard error, no branch/PR created) if
  neither source yields a valid slug, or if `specs/NNN-slug/spec.md` and
  `spec-meta.json` are not both present on `main`.
- **Rationale**: Matches FR-001/FR-010 exactly — the head branch name is the
  only signal produced by stage 1 (intake) that identifies the specification,
  and it is already the join key used by the constitution's branch
  conventions. Validating the shape before touching any spec directory
  prevents an unrelated `specs/**`-touching PR from being mis-planned.
- **Alternatives considered**: Parsing PR labels (`spec:NNN-slug`) — rejected
  because stage 1's draft spec PRs are not guaranteed to carry that label
  before merge (the label is applied to the *issue*, not the draft PR);
  reading `spec-meta.json` history via git blame — unnecessarily indirect
  when the branch name already encodes identity.

## 2. How is the persistent `spec/NNN-slug` branch created idempotently?

- **Decision**: `git ls-remote --exit-code origin refs/heads/spec/NNN-slug`;
  if absent, `git push origin HEAD:refs/heads/spec/NNN-slug` from the
  just-merged `main`. No PR, no merge commit — a plain ref creation.
- **Rationale**: FR-002 requires create-if-absent, reuse-if-present. A plain
  push is the minimal operation; there is nothing to review in "branch now
  exists," so a PR would only add ceremony without a decision point for a
  human.
- **Alternatives considered**: Creating the branch via the GitHub API
  (`gh api ... /git/refs`) — equivalent but adds a second auth path for no
  benefit over `git push` with the same App token already in hand.

## 3. How is a duplicate planning attempt for the same spec detected?

- **Decision**: Before generating anything, check
  `git ls-remote --exit-code origin refs/heads/plan/NNN-slug`. If it exists,
  skip all remaining planning steps for this run (no error — a duplicate
  merge-event delivery is expected, not exceptional).
- **Rationale**: FR-009. `plan/NNN-slug` existing is the one durable signal
  that a planning attempt already happened (in flight, in review, merged, or
  stalled) — cheaper and more reliable than trying to de-duplicate on the
  GitHub delivery ID, which the workflow does not have easy access to inside
  `pull_request: closed`.
- **Alternatives considered**: An idempotency key stored in `spec-meta.json`
  — redundant with the branch check and adds a second thing that could drift
  out of sync with reality.

## 4. How does a hand-submitted spec (no lifecycle issue) get one?

- **Decision**: When `spec-meta.json`'s `issue` field is empty/null at the
  start of planning, create the issue (`gh issue create`) before any other
  reporting, using the spec's `# Feature Specification: <name>` heading for
  the title, then create-or-reuse the `spec:NNN-slug` label and apply it plus
  the label created for `stage:plan` later in the same run.
- **Rationale**: FR-007 / User Story 3 — every later reporting step (progress
  comment, stage label) assumes an issue exists; creating it first means
  nothing downstream needs a "does an issue exist" branch.
- **Alternatives considered**: Deferring issue creation to a later stage —
  rejected because it would mean stage 2's own plan-summary comment (FR-006)
  has nowhere to go for hand-submitted specs, violating SC-002 ("100% of
  accepted specifications ... reach the planning stage with a lifecycle issue
  reporting their status").

## 5. How is "the plan pull request was closed without merging" observed?

- **Decision**: A second job (`stalled`) triggered by the same
  `pull_request: closed` event, gated on `merged == false` and the head ref
  starting with `plan/`. It marks `spec-meta.json`'s `stage` as `"stalled"`,
  commits that change directly to `spec/NNN-slug`, and comments on the
  lifecycle issue that a maintainer must delete `plan/NNN-slug` and dispatch
  the workflow manually to retry.
- **Rationale**: FR-012 explicitly forbids silently remaining "in planning"
  forever and forbids auto-reverting or auto-regenerating a plan. A separate
  job (rather than an `if` branch bolted onto the main `plan` job) keeps the
  "PR merged" and "PR closed unmerged" code paths independently readable and
  matches how GitHub Actions naturally expresses "two different things can
  happen when a PR closes."
- **Alternatives considered**: Polling for stale open plan PRs on a schedule
  — unnecessary; `pull_request: closed` already fires exactly once for this
  transition with no polling delay.

## 6. What triggers this workflow, precisely?

- **Decision**: `pull_request: closed` with `paths: ["specs/**"]`, additionally
  gated in the job's `if:` on `merged == true && base.ref == 'main' &&
  head.ref` starting with `spec-draft/` — plus `workflow_dispatch` (input
  `slug`) for manual (re)starts.
- **Rationale**: The `paths` filter alone is too broad (any PR touching
  `specs/**`, including this very plan PR against `spec/NNN-slug`, would
  match); the head-ref-prefix guard in the job condition narrows it to
  exactly "a draft spec PR merged to main," matching known risk #4 in
  `docs/architecture.md` ("`pull_request: closed` + `paths:` false-triggers").
- **Alternatives considered**: A narrower `paths` filter
  (`specs/*/spec.md`) — insufficient on its own since the plan PR itself also
  touches paths under `specs/**` (research.md, plan.md, etc.) once opened
  against `spec/NNN-slug`; the base/head guard is still required regardless.

## 7. Does planning ever block on unresolved `[NEEDS CLARIFICATION]` markers?

- **Decision**: No — per FR-011, the `/speckit-plan` skill's default
  "ERROR on unresolved clarifications" behavior is overridden for this stage:
  the agent documents a reasonable default decision for each remaining marker
  in `research.md` and continues, then lists those decisions in the plan PR
  body under "Decisions made without clarification."
- **Rationale**: The specification's own review gate (stage 1's spec PR
  merge) is the point where a human accepts the spec as-is, markers and all;
  blocking stage 2 on them would contradict FR-011 and stall the pipeline on
  something a human already implicitly accepted by merging.
- **Alternatives considered**: Refusing to plan until a human manually
  resolves every marker — this is the skill's out-of-the-box behavior but is
  explicitly the deviation this specification calls for in a CI context.
