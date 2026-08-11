# Quickstart: Validating PR Conversation Commands

**Feature**: 033-pr-conversation-commands

How to prove the feature works end-to-end once implemented, mapped to
`spec.md`'s acceptance scenarios and success criteria. No full
implementation code here — see `contracts/` for the exact step/field
shapes and `data-model.md` for the entities being validated.

## Prerequisites

- A checkout with this feature implemented: `.github/workflows/pr-conversation.yml`
  (`contracts/reusable-pr-conversation.md`) and
  `.github/workflows/wing-commander-9-pr-conversation.yml`
  (`contracts/wrapper-gate.md`), plus the drafted
  `stage-interfaces.md` addition carried over.
- `actionlint`/`yamllint`/`lint-workflows.yml` Gate 7 (CI-gated per specs
  025 and 031) passing on both new workflow files.
- An open implementation PR for a real in-flight spec in this repository
  (head `spec/<slug>`, base the default branch, per `data-model.md`
  `PullRequestIdentity`) — the natural one is this feature's own
  eventual implementation PR (constitution I).
- Ability to leave all three PR conversation surfaces on it (issue-style
  comment, a formal review with a body, an inline review-thread comment),
  and control over the commenting account's association (a
  collaborator/maintainer account and a non-collaborator account).
- `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` and
  `WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT` unset for the
  act-then-report scenarios below, and set (with the named environment
  configured with a required reviewer) for the propose-and-confirm
  scenario.

## Static validation (no agent run required)

1. `actionlint`/`yamllint` pass on both new workflow files; `lint-workflows.yml`
   Gate 7 passes on `pr-conversation.yml`'s `environment:` binding shape.
2. Exercise the wrapper's actor-gate `if:` expression standalone against
   representative event-payload fixtures for all three event kinds
   (`contracts/wrapper-gate.md`'s table): a bot comment → job does not run
   at all; a `NONE`-association human comment → job runs (the *stage's*
   own notice-and-stop check is what fires, not the wrapper); an
   `OWNER`/`MEMBER`/`COLLABORATOR` comment → job runs and proceeds past the
   gate. Confirm there is **no** carve-out for the lifecycle issue's
   original author (unlike `wing-commander-2-clarify.yml`'s fixture
   behavior) — a comment from that account with `author_association: NONE`
   must be treated identically to any other non-collaborator.
3. Exercise the `PullRequestIdentity.qualifies` check
   (`data-model.md`/research.md D4) against fixture PR metadata: head
   `spec-draft/<slug>` → base default branch ⇒ `qualifies=false`; head
   `plan/<slug>` → base `spec/<slug>` ⇒ `qualifies=false`; head
   `spec/<slug>` → base default branch ⇒ `qualifies=true`.
4. Exercise the small-unrelated-change size backstop
   (`contracts/spinoff-routing.md`) against a fixture diff at, and one
   line over, the documented threshold — confirm the over-threshold case
   re-routes rather than opening a PR.
5. **Multi-page comment threads (T067)**: every comment-thread scan in
   `pr-conversation.yml` (relay-resume, the relayed-request risk gate, and
   the stop procedure) must survive a PR with **more than one page** of
   comments — the default page size is 30, which real dogfood PRs pass
   quickly. `gh` applies `--jq` to *each page separately* and concatenates
   the results, so an array-collecting filter (`--paginate --jq '[.[] |
   ...]'`) emits `[...]\n[...]` — one array per page — and any
   `jq --argjson` consuming it dies with "Extra data"/"invalid JSON text",
   aborting the step under `set -euo pipefail`. Required shape: stream one
   object per line (`--paginate --jq '.[] | ...'`) and slurp once with
   `jq -s '.'`, as `intake.yml` does. Fixture check: concatenate two
   single-page filter outputs and confirm the consuming `jq -n --argjson`
   parses them — it must, which it only does for the streamed-and-slurped
   form. Grep guard: `--paginate --jq '[` must not appear in
   `.github/workflows/pr-conversation.yml`.

## End-to-end scenario checks (one dogfood run each, or combined)

Map directly to `spec.md`'s acceptance scenarios:

1. **User Story 1 / SC-001**: on the implementation PR, leave a review
   requesting an in-scope change (e.g. "this function is missing a null
   check"). Confirm: an `IntentAnnouncement` posts before anything else
   (FR-023); `tasks.md` on `spec/<slug>` gains a `## Maintainer Feedback`
   section (`contracts/converge-fold-in.md`); `spec-meta.json.stage` reads
   `"implement"` again; `wing-commander-5-implement.yml` is dispatched at
   `iteration = recorded+1`; the same PR updates once that cycle
   completes; a status reply lands on the PR (not only the issue).
2. **User Story 1, Acceptance #3**: confirm the lifecycle issue gains
   **no** new comment/task-item from this cycle — implementation-detail
   conversation for an in-scope change stays entirely on the PR.
3. **User Story 2(a) / FR-007**: leave a comment describing a genuinely
   tiny, unrelated docs fix. Confirm a separate PR to the default branch
   opens, is referenced from both the current PR and the lifecycle issue,
   and the lifecycle issue shows it as an unchecked outstanding-task-item
   line (`contracts/spinoff-routing.md`).
4. **User Story 2(b) / FR-006**: leave a comment requesting new,
   substantial functionality. Confirm the stage decides fold-in vs.
   new-issue and records which (PR reply either way); for the new-issue
   branch, confirm the created issue carries the `spec-request` label and
   that `wing-commander-1-intake.yml` picks it up on its own (research.md
   D7) with no further manual step.
5. **User Story 2, Acceptance #4 / SC-004**: leave a comment describing an
   unrelated change that is clearly not tiny (many files). Confirm no PR
   to `main` opens — it routes to the new-functionality path instead.
6. **User Story 3 / SC-003**: leave a comment asking the stage to merge
   the current PR to the default branch itself. Confirm a decline reply
   naming the specific constitution principle (V), and that no merge
   occurs.
7. **User Story 3, Acceptance #2**: leave a deliberately ambiguous request.
   Confirm a clarifying question is posted rather than any action taken.
8. **User Story 4 / FR-011, FR-012**: ask for a manual step the stage can
   perform (confirm it does, reports outcome); ask for one it cannot
   (confirm it explains why); ask for something requiring an unheld
   permission with no prior discussion (confirm a `permission-request`
   -labeled PR opens, recorded on the issue); repeat with a prior
   permission-request PR/issue already present and confirm the new run
   links it instead of opening a duplicate (research.md D11).
9. **User Story 5 / FR-023, SC-008**: leave any actionable comment;
   confirm the announcement (classification, planned action, run link)
   is visible on the PR **before** any artifact/commit/push exists —
   inspect timestamps to confirm ordering, not just presence.
10. **User Story 5, Acceptance #2 / FR-024**: repeat scenario 1 above, then
    immediately reply "stop" (or cancel the linked run directly). Confirm
    no further commits land and the stop is acknowledged on the PR
    (`contracts/autonomy-and-confirmation.md`).
11. **User Story 5, Acceptance #3**: repeat scenario 3 above (a fast
    small-PR spin-off likely to finish before a stop reply can land), send
    the stop reply after it has already completed, and confirm the reply
    reports what was already done (`StopRequest.outcome == "already-completed"`)
    rather than implying prevention.
12. **User Story 5, Acceptance #4 / FR-020**: with
    `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES=new-functionality,small-unrelated-change`
    and the confirm environment configured with a required reviewer, repeat
    scenario 3. Confirm the proposal posts and the `act` job visibly waits
    for approval before the PR is opened; approve it and confirm it then
    proceeds. Separately confirm an in-scope-change request (scenario 1)
    still runs immediately despite the same configuration (FR-020's
    "in-PR actions still run immediately").
13. **User Story 6 / SC-010**: ask a question about the new code on the PR.
    Confirm an answer posts and the branch, lifecycle issue, and
    repository are otherwise untouched.
14. **User Story 6, Acceptance #2**: leave a comment mixing a question with
    an actionable in-scope request. Confirm both a direct answer and the
    normal in-scope routing occur from the single comment
    (`contracts/classification-schema.md`'s multi-classification support).
15. **User Story 7 / SC-002**: after driving scenarios 3, 4 (new-issue
    branch), and 8 (permission-PR branch), inspect the lifecycle issue and
    confirm each of the three spin-off artifacts appears as its own
    outstanding-task-item line, cross-linked to the PR — while the User
    Story 1 in-scope cycle (scenario 1) left no trace there at all.

## Edge case checks

- **Bot comment**: have a pipeline bot account leave a comment on the PR
  (or reuse an existing automated status comment). Confirm zero reaction —
  no reply, no run at all (distinct from the unauthorized-human case,
  which does get a brief notice).
- **Concurrent requests, same spec**: leave two distinct in-scope requests
  in quick succession. Confirm the second run queues on the
  `wing-commander-<spec-dir>` concurrency group (research.md D6) rather
  than racing the first's `implement.yml` dispatch.
- **Relayed request with risk** (FR-022): have a maintainer relay a
  non-maintainer's request that involves a permission/security change.
  Confirm the stage asks the relaying maintainer to confirm the stated
  risk once, and takes no action until that confirmation arrives; repeat
  with an in-scope relayed request carrying no risk and confirm it
  proceeds without an extra confirmation round.
- **Pure acknowledgement** (FR-017): leave a comment like "thanks,
  looks good." Confirm `category: "no-action"` and zero mutation, zero
  reply beyond (at most) the classification step's own internal decision
  — no PR reply is required for genuinely non-actionable content per
  FR-014's "actionable request" scoping.

## Regression check

Run a completely ordinary implementation-detail review comment (the kind
this pipeline already handled today by a human reading and acting on it
manually) through the new stage and confirm the PR ends up in the same
final state a manual maintainer response would have produced — same
branch, same tests passing, same PR — just without the manual
translation step (SC-001, SC-007).
