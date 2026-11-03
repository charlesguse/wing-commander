# Research: Lifecycle Hold Label

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
fix the points the spec delegates to the plan ("the plan defines/fixes").
Code references were read on 2026-11-03 against main.

## D1. One home for the hold check and one for setting the hold (FR-004, FR-006, FR-019)

- **Decision**: A new composite `.github/actions/wing-commander-lifecycle-hold/`
  with `mode: check | set`, backed by one script
  `.github/scripts/wc_lifecycle_hold.py` (pure functions + CLI, unit-tested).
  `check` reads the lifecycle issue's labels with a fresh `gh issue view`
  and emits `state` = `clear | held | unreadable`; `set` adds the label
  idempotently and posts the reason. Inputs: `issue` (declared, constitution
  VII), `hold-label` (default `lifecycle:held`), `token`, `mode`, `reason`.
- **Rationale**: Two consumers read (implement start, fold-dispatch) and
  three set (issue-comment job, pr-conversation strict-stop path, analyze
  decide). A composite is the repo's established home for cross-workflow
  logic (CLAUDE.md). The decision (`unreadable` → fail closed) is pure
  code, not model judgement (IX).
- **Alternatives**: Inline `gh issue view | jq` in each workflow (rejected:
  the exact pasted-copy failure CLAUDE.md names); two composites (rejected:
  one script keeps label-name and fail-closed semantics together).

## D2. fold-dispatch reads the hold inside the composite (FR-003)

- **Decision**: The fold-dispatch composite gains inputs `hold-label` and
  `hold-state` is computed by a first step that calls the lifecycle-hold
  composite (`mode: check`) — read-only, so no write credential is added.
  It gains an output `withheld` (`held | unreadable | ""`); when set it
  exits before `gh workflow run`, `dispatched=false`, `ticket-unused=true`
  (so the caller releases the carried fold-queue ticket through the path
  T056 already built). Callers (lifecycle-review-gate `disposition`,
  pr-conversation `dispatch-once`) post the "withheld" line on the issue.
- **Rationale**: Reuses the existing `ticket-unused` release path instead
  of a new ticket mechanism (FR-003, spec 074).
- **Alternatives**: Check in each caller (rejected: two copies).

## D3. Implement start check and the "held" outcome (FR-002, FR-021)

- **Decision**: A first step in `implement.yml`'s `implement` job (before
  any agent/write step) runs the hold check. On `held`/`unreadable` all
  later steps are skipped via a job output `held=true`; a short job posts
  the one status line; `final-ok` is consolidated as success with
  `outcome=held`, so the retry and `stalled` jobs (which key off failure)
  do not run, no `stage:stalled` is applied, no next-iteration/finalize
  dispatch fires, and the fold-queue ticket is released by the existing
  `fold-turn-release` job (it already runs after `implement` and
  `stalled`). `wing-commander-implement-outcome` learns the `held` value;
  the watchdog's lost-progress classifier treats `outcome=held` as
  expected, shown by a fixture (FR-021).
- **Alternatives**: Fail the run and teach the watchdog to ignore it
  (rejected: a red run reads as a defect and triggers retry/stall logic).

## D4. Release trigger on the implement wrapper (FR-007)

- **Decision**: `wing-commander-5-implement.yml` adds
  `issues: types: [unlabeled]`. A first job exits unless
  `github.event.label.name == vars.WING_COMMANDER_HOLD_LABEL || 'lifecycle:held'`
  (so every other label removal skips at once). A deterministic script
  (`wc_lifecycle_hold.py release-plan`) then decides "implement due":
  issue open, not `parked`, not `stage:stalled`, spec branch found via the
  existing `wing-commander-spec-meta`/project composites, spec-meta stage
  `tasks` or `implement`; inputs `spec_dir`, `issue`, `iteration` come from
  the spec-meta recorded on the branch (`iteration = recorded + 1`, the
  same formula fold-dispatch uses). If due, it `gh workflow run`s the
  wrapper itself with `workflow_dispatch` (the wrapper already has the
  dispatch inputs fold-dispatch uses) and posts the release note naming
  who removed the label (`github.event.sender.login`). Callers that look up
  "the implement run I just dispatched" gain `--event workflow_dispatch`
  (found by grepping `gh run list --workflow` users; a gate fails if one
  lacks the filter).
- **Rationale**: Release stays one action and adds no release workflow
  (FR-018). `issues: unlabeled` is authorised by the owner session answer.
- **Alternatives**: Poll on schedule (rejected: latency, extra runs).

## D5. Setting the hold from stop comments (FR-005, FR-020, FR-024)

- **Decision**:
  - Issue comments: a new job `lifecycle-stop` in the existing
    pr-conversation wrapper (`wing-commander-9-pr-conversation.yml`) on
    `issue_comment` for issues (not PRs). Steps: skip bots; require
    `author_association` in OWNER/MEMBER/COLLABORATOR; find the lifecycle
    (issue carries `stage:*`/`spec:*` and has a spec branch — reuse the
    existing lifecycle-issue resolver the wrappers use); call
    `board_stop_check.is_stop_command` through the existing
    `wing-commander-board-stop-check` composite (no regex copy); call the
    lifecycle-hold composite `mode: set`.
  - PR comments: pr-conversation's deterministic pre-classify step does the
    same strict check on a lifecycle PR and sets the hold; for a classified
    non-strict `stop`, the reply template adds the "post exactly `stop` or
    `/stop`, or add the label" sentence.
  - clarify: its comment-trigger `if:`/guard calls the same parser and
    skips (no run, not an answer) when the comment is a strict stop on a
    lifecycle issue.
- **Acknowledgement text** names that a maintainer with triage access
  releases it (stop author may be a read-only collaborator).

## D6. Fold-time analyze placement (FR-008–FR-014, FR-016)

- **Decision**: Split `lifecycle-review-gate.yml`'s `disposition` job at the
  fold commit: `disposition` (fold commit; new outputs `fold-base-sha`,
  `fold-head-sha`, `tasks-changed`) → `fold-analyze` → `fold-decide` →
  `fold-dispatch` (dispatch through the composite). Fixed shapes:
  - `fold-analyze`: `permissions: contents: read` only, checks out the
    spec branch at fold-head-sha plus the default-branch constitution;
    input is built by a deterministic prepare step
    (`wc_fold_analyze.py prepare`) as `fold-input.json` = {added tasks from
    `git diff base..head -- tasks.md` over the fold's own commits only,
    spec.md text, constitution text, principle names}. Agent: Claude Sonnet
    (`claude-sonnet-5-5`), `--max-turns 8`, no write tools, JSON schema
    output (data-model). Output uploaded as an artifact.
  - `fold-decide` (issues:write, no agent): `wc_fold_analyze.py decide`
    validates schema, principle existence, task membership; outputs
    `hold`, posts records via the lifecycle-hold composite `mode: set`
    only when `hold=true`.
  - Skipped entirely when `tasks-changed=false`.
  - Re-run (FR-016): `github.run_attempt > 1` on the analyze/decide jobs
    re-reads constitution from the default branch and spec/tasks from the
    branch tip at re-run time; the task set is fold additions still in
    tasks.md. Downstream `dispatch`, review post and merge jobs are guarded
    by `run_attempt == 1`-style output (`first-attempt`), which `decide`
    computes, so a retry only posts the verdict and, on conflict, the label.
  - Failure (FR-013): agent step is `continue-on-error`; decide treats
    missing/invalid artifact as `agent-failed`, reports it, dispatch proceeds.
  - Kill switch: the gate's existing `kill-switch` job gates all of it.
- **Alternatives**: Run analyze as a step inside `disposition` (rejected:
  agent and write credential would share a job — owner decision 15).

## D7. Link from a fold task to its fingerprints and dismissal derivation (FR-017)

- **Decision**: No new marker. The gate already writes the fold record
  (`folded_fingerprints` in the review marker, wc_lifecycle_review_marker.py)
  and matches tasks.md lines `- [ ] Review finding: <title>` /
  `- [ ] Recurring review finding: <title>` by title (disposition step,
  lifecycle-review-gate.yml ~1232–1315). The derivation
  (`wc_dismissals.py derive`) is a pure function over:
  1. the lifecycle branch's commits that carry the drop trailer (D8),
  2. for each, the unchecked fold-task lines it removed (diff),
  3. the marker's title→fingerprints records (all rounds), and
  4. the current tasks.md.
  A fingerprint is dismissed iff every *unchecked* fold task carrying its
  title (in any fold) is absent from the current tasks.md **and** each
  such absence is attributed to a verified drop commit; already-checked
  tasks are ignored; identical titles for different fingerprints require
  all copies dropped. Output is the list the gate passes as
  `evaluate(dismissed=...)`, and the gate additionally excludes dismissed
  fingerprints from folding and from the open in-scope count.
- **Risk noted for tasks**: the exact marker shape for title→fingerprints
  must be confirmed when implementing; if the marker only stores
  fingerprints, the title is recomputed with the same function the
  disposition step uses to write it (single home, extracted if needed).

## D8. Drop action and unforgeable attribution (FR-017, FR-023)

- **Accepted form**: a maintainer comment on the lifecycle PR whose first
  non-quoted line is `drop` (optionally `drop:`), followed by one line per
  task: the exact fold title line, e.g.
  `- Review finding: <title>` or `- Recurring review finding: <title>`
  (leading `- [ ] ` accepted and ignored). Parsed by
  `wc_fold_drop.py parse`; disjoint from the stop grammar.
- **Placement**: a deterministic job in pr-conversation (`drop`) runs
  *before* classification; a handled drop sets an output that makes the
  agent/classify path skip the comment. It uses the existing fold-queue
  admit/push path (spec 074 composites) and does not dispatch implement.
- **Commit identification**: the commit message carries trailers
  `Wing-Commander-Drop: <comment-id>` and the removed titles. Derivation
  does not trust the trailer alone: for each trailer'd commit it fetches
  the comment by id through the API and requires (a) author association
  OWNER/MEMBER/COLLABORATOR and not a bot, (b) the comment parses as a drop
  naming exactly the removed task lines. An agent cannot forge a
  maintainer's comment, and the trailer is part of the commit message so it
  survives the rebase stage's replay.
- **Replies**: removed / unknown / not-a-fold-task / already-checked /
  already-absent / non-maintainer, one fixture each.

## D9. Merge gate condition (FR-022)

- **Decision**: Add condition 9 "no hold label" to the lifecycle merge
  preconditions (`verify-lifecycle-merge-preconditions.py` fixtures,
  `lifecycle-review-gate.yml` `readiness`/`merge`, and spec 062's
  `contracts/readiness-and-merge.md`). The `merge` job additionally calls
  `wc_lifecycle_hold.py check` (fresh read, fail closed) and a
  constitution-X check (`wc_lifecycle_hold.py constitution-names-hold`)
  that reads constitution.md from the default branch via
  `git show origin/<default>:...` and requires X to mention the hold
  condition (match on the literal hold wording the amendment adds, fixed in
  the amendment PR: "no hold label"). Unreadable → refuse. Fixtures: the
  unamended text (refuse) and amended text (allow).
- **Ordering**: the constitution X amendment PR is a separate human-merged
  PR; this plan only tracks it as a task.

## D10. Label copy and gates

- Steps that copy issue labels onto PRs (intake, plan, tasks, finalize) get
  the hold label name excluded via one shared jq filter in an existing
  `_shared` helper (not four copies). Gates (new `verify-*.py`, registered
  in `run-local-gates.py`): single-home for check/set; every
  `gh run list` for a dispatched implement filters `workflow_dispatch`;
  label-copy excludes hold; fixtures cover every FR-014/FR-023 branch.
- Docs: `docs/adoption.md` gets the wrapper trigger note (FR-007).
