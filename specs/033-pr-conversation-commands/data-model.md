# Data Model: Maintainer Commands and Spec Kit Routing Through PR Conversation

**Feature**: 033-pr-conversation-commands

Like every other stage in this pipeline, this feature has no application
data store. Its "entities" are the values that flow through one
`pr-conversation.yml` run: GitHub event → deterministic gates → a staged
untrusted-data file → one classify+draft agent step → deterministic
per-category action steps. Documented here as data shapes/validation
rules, mirroring `spec.md`'s own Key Entities section and `research.md`'s
decisions (D1–D11).

## Entities

### PRConversationEvent (read, from the triggering GitHub event — untrusted)

Per spec.md's Key Entities: "a maintainer review body, inline
review-thread comment, or issue-style PR comment on an implementation PR
tied to an in-flight spec."

| Field | Type | Source | Notes |
|---|---|---|---|
| `kind` | enum `review` \| `review-comment` \| `issue-comment` | derived from which trigger fired (`wrapper-gate.md`) | Determines which event fields below are populated. |
| `pr-number` | integer | `github.event.pull_request.number` (review/review-comment) or `github.event.issue.number` (issue-comment) | Identifies the PR (see `PullRequestIdentity` below). |
| `body` | string (untrusted) | `github.event.review.body` \| `github.event.comment.body` | Never shell-interpolated, never pasted into the agent prompt string (mirrors `clarify.yml`'s staging convention) — reaches the agent only via a staged file. |
| `comment-id` / `review-id` | integer | `github.event.comment.id` \| `github.event.review.id` | Used for the `pr-feedback:` commit trailer (D5) and for locating this event's own intent-announcement later (D10). |
| `actor.login` | string | `github.event.comment.user.login` \| `github.event.review.user.login` | Display only. |
| `actor.id` | integer | `...user.id` | Not currently needed (no requester carve-on exists to compare against, unlike clarify — research D1/FR-019), kept for audit/logging only. |
| `actor.type` | enum `User` \| `Bot` \| ... | `...user.type` | `"Bot"` → wrapper-level exclusion, no run at all (FR-002, FR-021). |
| `actor.association` | enum (`OWNER`, `MEMBER`, `COLLABORATOR`, ...) | `...author_association` | Qualifies only when `OWNER`/`MEMBER`/`COLLABORATOR` (FR-019) — **no** author/requester carve-out, unlike clarify/intake. |
| `thread-context` | string (untrusted, review-comment only) | `github.event.comment.path`/`.diff_hunk` | Passed through to the staged file so the agent knows which inline thread it's replying in; still untrusted. |

### PullRequestIdentity (read, deterministic — determines whether this stage applies at all)

| Field | Type | Source | Notes |
|---|---|---|---|
| `base-ref` | string | `gh pr view <n> --json baseRefName` | Must equal the resolved default branch (D4). |
| `head-ref` | string | `gh pr view <n> --json headRefName` | Must start with the configured `spec-prefix` (default `spec/`) and **not** `spec-draft-prefix`/`plan-prefix`/`tasks-prefix` (D4, FR-018). |
| `slug` | string | stripped from `head-ref` | `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, same validation `resolve-spec` jobs elsewhere already apply. |
| `spec-dir` | string | `specs/<slug>` | Used for the concurrency group (D6) and every `spec-meta.json`/`tasks.md` read/write. |
| `qualifies` | boolean | `base-ref == default-branch AND head-ref starts-with spec-prefix` | `false` ⇒ the run no-ops with no reply at all (this PR is out of scope for this stage entirely, not merely unauthorized — it is not "an implementation PR" per FR-018). |

### RequestClassification (produced by the classify+draft agent step — one per distinguishable request-part)

Per spec.md's Key Entities: "the category assigned to an actionable
request... that determines its route." A single `PRConversationEvent` may
decompose into more than one `RequestClassification` (edge case: "request
mixes in-scope and out-of-scope items in one comment").

| Field | Type | Notes |
|---|---|---|
| `category` | enum: `in-scope-change` \| `question` \| `needs-info` \| `push-back` \| `new-functionality` \| `small-unrelated-change` \| `manual-step-permission` \| `stop` \| `no-action` | FR-003's taxonomy, plus `no-action` for pure acknowledgement (FR-017, edge case). |
| `summary` | string | One-line human-readable description, used verbatim in the intent-announcement (FR-023). |
| `drafted-content` | object (shape depends on `category`) | E.g. for `new-functionality`+"own spec": issue title/body (D7); for `small-unrelated-change`: the diff/PR description (D8); for `push-back`: the constitution principle cited and the reason (FR-010); for `question`: the answer text (FR-025); for `manual-step-permission`: either the performed-step report or the permission-request PR body + capability name (FR-011/FR-012). |
| `fold-target` | enum `current-spec` \| `new-spec` | Only present when `category == new-functionality` (FR-006). |
| `constitution-conflict` | string \| null | Non-null only for `push-back` — names the specific principle (FR-010). |
| `requires-confirmation` | boolean | Computed deterministically from `category` against `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` (D9) — not agent-decided, so autonomy configuration can never be influenced by comment content (FR-020). Computed AFTER `small-unrelated-change`'s size backstop (D8) has already rewritten `category`/`fold-target`/`drafted-content` in place, so this check (and `act`'s `environment:` binding, which reads its result) always sees the backstop-corrected category, never the raw classify-time one — see D8's ordering note. |
| `risk-note` | string \| null | Only present when this classification resulted from a maintainer-relayed non-maintainer request (`RelayedRequest`, below) carrying security/permission/hard-to-undo risk (FR-022). |

### IntentAnnouncement (posted before any mutation — also the stop mechanism's only state)

Per spec.md's Key Entities: "the reply the stage posts before mutating
anything... which is also what makes the run cancellable."

| Field | Type | Notes |
|---|---|---|
| `classification` | `RequestClassification.category` + `.summary` | Rendered into the callout body. |
| `planned-action` | string | One sentence, e.g. "re-run implement/converge iteration 4" or "open a spin-off PR to main". |
| `run-url` | string | `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` (D10) — the **only** field the stop mechanism actually parses back out of the posted comment. |
| `posted-to` | `pr` \| `pr+issue` | `pr+issue` only for classifications whose action is itself out-of-PR (FR-013 requires cross-referencing then; in-PR actions post to the PR only). |

### StopRequest (a `RequestClassification` with `category == "stop"`)

| Field | Type | Notes |
|---|---|---|
| `target-run-url` | string \| null | Extracted by scanning the PR thread for the most recent bot-posted `IntentAnnouncement` **other than one this run posted itself** (D10; the stop run announces its own `stop` classification before `act` starts, so its own announcements are always the newest and must be skipped); `null` if none found (e.g. the prior action already finished and its announcement is stale/unmatched). |
| `outcome` | enum `cancelled` \| `already-completed` \| `not-found` | Deterministic result of `gh run cancel` (and, for `in-scope-change`, also cancelling the dispatched `wing-commander-5-implement.yml` run) — reported back on the PR per FR-024. |

### AutonomyConfiguration (trusted, wrapper-resolved — never derived from PR content)

Per spec.md's Key Entities: "trusted, consumer-supplied configuration
selecting act-then-report... or propose-and-confirm per action category."

| Field | Type | Source | Notes |
|---|---|---|---|
| `confirm-categories` | set of `RequestClassification.category` \| `all` | `vars.WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` (comma-separated), empty = none (D9) | Read only in the wrapper, passed as a `workflow_call` input. |
| `confirm-environment` | string | `vars.WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT`, default `pr-conversation-confirm` | Name of the GitHub deployment environment the `act` job binds to when `requires-confirmation == true` (D9); pass-through, no existence validation (same contract as spec 031). |

### RelayedRequest (a maintainer endorsing a non-maintainer's request — FR-022)

| Field | Type | Notes |
|---|---|---|
| `relaying-maintainer` | `PRConversationEvent.actor` | Must itself pass the authorized-actor gate (FR-019) — a relay from a non-maintainer is not honored. |
| `relayed-text` | string (untrusted) | The non-maintainer's original request, quoted by the maintainer or referenced; treated with the same untrusted-data framing as any other request body. |
| `risk` | boolean | Agent-judged, conservative bias (spec.md Assumptions) — security/permission/hard-to-undo consequence. |
| `confirmed` | boolean | `true` only once the relaying maintainer's follow-up reply explicitly accepts the stated risk (FR-022) — until then the stage takes no action beyond asking. |

### SpinOffArtifact / OutstandingTaskItem (created outside the PR — FR-008/FR-013)

| Field | Type | Notes |
|---|---|---|
| `kind` | enum `new-lifecycle-issue` \| `small-unrelated-pr` \| `permission-request-pr` | Matches D7/D8/D11's three spin-off mechanisms. |
| `url` | string | The created issue/PR's URL — what gets cross-linked (FR-013). |
| `recorded-on-issue` | boolean | Always `true` once created (FR-008 is a MUST, not conditional) — the stage's own deterministic step, not the agent, appends the outstanding-task-item line to the lifecycle issue via `wing-commander-callout` (`kind: action`, `pr-url` pointing at the new artifact), so this can't be silently skipped by a drafting miss. |

### WithheldPermissionConversation (looked up, not created — FR-012, D11)

| Field | Type | Notes |
|---|---|---|
| `label` | literal `permission-request` | Applied to every permission-request issue/PR this stage creates (D11), searched via `gh search issues --label permission-request --state all`. |
| `match-confidence` | enum `confident` \| `uncertain` \| `none` | `confident` ⇒ link it instead of re-requesting; `uncertain`/`none` ⇒ err toward explaining the situation rather than guessing (spec.md edge case), per the conservative-bias rule already established for `RelayedRequest.risk` and `small-unrelated-change` sizing (D8). |

## Relationships

```
PRConversationEvent (untrusted) ──▶ PullRequestIdentity.qualifies?
                                        │ (false → no-op, no reply)
                                        ▼ (true)
                          actor gate (bot? association?) — FR-002/FR-019/FR-021
                                        │ (fails → notice-only reply, no mutation, unless bot: no reply)
                                        ▼ (passes)
                       staged untrusted-data file (mirrors clarify.yml)
                                        │
                                        ▼
                     classify+draft agent step ──▶ RequestClassification[] (1..N)
                                        │
                        ┌───────────────┼──────────────────────────────┐
                        ▼               ▼                              ▼
             AutonomyConfiguration   IntentAnnouncement            per-category
             (deterministic lookup)  (posted before mutation,      drafted-content
                        │            embeds run-url)                    │
                        ▼                                               ▼
        requires-confirmation? ──yes──▶ act job bound to            act job executes:
        (environment gate, D9)          confirm-environment          in-scope→D5 fold-in+dispatch
                        │                                            new-functionality→D7/fold
                        no                                           small-unrelated→D8 PR
                        ▼                                            manual-step/permission→D11
                  act job runs immediately                           push-back/question/needs-info→reply only
                        │                                            stop→StopRequest (D10)
                        ▼
        SpinOffArtifact? ──yes──▶ OutstandingTaskItem on lifecycle issue (FR-008/FR-013)
```

## State / lifecycle

No new persistent schema. State this feature reads and writes is entirely
state that already exists:

- **`spec-meta.json`** (`spec/<slug>` branch): read for `stage`/`iteration`
  (D4/D5); written only for the in-scope-change path, flipping `stage`
  back to `"implement"` before re-dispatch (D5) — every other classify
  category leaves it untouched.
- **`tasks.md`** (same branch): gains one new, append-only
  `## Maintainer Feedback` section per in-scope-change request (D5) — same
  append-only discipline `/speckit-converge` already follows for its own
  sections.
- **The PR's own comment thread**: the sole store for `IntentAnnouncement`
  lookups (D10) — no new file, label, or cache. A stop request that can't
  find a matching announcement (thread edited/deleted, or none posted yet)
  degrades to `StopRequest.outcome == "not-found"`, reported as such rather
  than assumed.
- **The lifecycle issue's labels**: gains `permission-request` on spin-off
  permission PRs/issues (D11), following the same `gh label create --force`
  idiom every other stage already uses for its own labels (`stage:*`,
  `spec:*`).

Everything else (`RequestClassification`, `IntentAnnouncement`'s in-memory
form before posting, `AutonomyConfiguration`) is transient, scoped to a
single `pr-conversation.yml` run.
