# Contract: `wing-commander-fold-analyze` composite (published contract — additive)

## Placement
`fold-commit` → **`fold-analyze` (mode `stage`)** → the caller's read-only analyze agent step → **`fold-analyze` (mode `decide`)** → (`fold-dispatch` iff `decision` is `dispatch` or `skipped`). Callers: `pr-conversation.yml` (`fold-analyze` then `dispatch-once`, after the `act` path's folds), `lifecycle-review-gate.yml` (`disposition`'s fold commit, then `fold-analyze` and `fold-decide`), and the published hold-release stage `fold-hold.yml` (`fold-analyze` then `release`, on a `retry` answer).

A composite never invokes the agent (`verify-actions-layer-invariants.py`), so the agent step lives in each caller; the composite holds the deterministic halves only. The stage step and the agent run in a job of their own with `contents: read` and no write scope (lifecycle-review-gate's and pr-conversation's `fold-analyze`, and the hold-release workflow's for a retry). That job uploads the agent's transcript (`claude-execution-output-fold-analyze`) and outputs `tasks` and `agent-outcome`. The deciding job downloads the transcript, re-derives the verdict from it with `wing-commander-agent-verdict` (no value read from the agent crosses a job boundary), and runs mode `decide` on it. A deciding job that has no tasks output holds the fold as `analyze-failed` (it passes `tasks: 1` and an empty agent outcome). Gate 166 (`verify-fold-analyze-wiring.py`) holds the order, the agent's shape and its job's permissions in every caller.

## Inputs (all declared; no ambient state read)
| Name | Mode | Required | Notes |
|---|---|---|---|
| mode | both | yes | `stage` \| `decide` |
| spec-dir | stage | yes | e.g. `specs/116-review-convergence-analyze` |
| project | stage | no | the lifecycle's project folder (spec 114); empty for the root |
| fold-ref-before | stage | yes | tip before the fold commit; scopes the fold section only when no folded-json entry carries a `commit_sha` (a single fold commit) |
| fold-ref-after | stage | yes | tip after the fold commit |
| folded-json | stage | yes | `[{id, summary, commit_sha?}]` from fold-commit/fold-evidence, or the round's folded items (pr-conversation, each with its fold's `commit_sha`). When entries carry a `commit_sha`, the section is each of those commits' own tasks.md diff (`git show <sha> -- tasks.md`), so no other tasks.md edit between them is analyzed; a commit the checkout cannot read fails the stage, which holds as `analyze-failed` |
| fold-id, tasks | decide | yes | the stage mode's outputs |
| agent-outcome | decide | yes | the caller's agent step `outcome` |
| agent-verdict | decide | yes | `wing-commander-agent-verdict`'s verdict for that step |
| execution-output-path | decide | no | defaults to `${{ runner.temp }}/claude-execution-output.json` |
| open-holds | decide | yes | `wing-commander-fold-open-holds`'s output: `none`, or the fold ids of the other holds open on the lifecycle |

The deciding job reads the open holds first with `wing-commander-fold-open-holds`, which takes `issue`, `github-token` (the App token) and `bot-login`, and outputs `open-holds`. While any fold hold other than this fold's own is open, a `dispatch` or `skipped` becomes `blocked`. An empty `open-holds` means the read never ran or failed. It holds the fold as `analyze-failed`, never dispatches past a hold it could not see. Every caller wires the read into the decide step in the same job (Gate 166).

**The per-lifecycle fold lock.** Each deciding job reads the open holds, and posts a hold or dispatches, while it holds the spec's fold-queue ticket (spec 074's ledger, `wing-commander-fold-queue-admit`, kind `dispatch`). The ledger grants one ticket per spec at a time, so lifecycle-review-gate's `fold-decide`, pr-conversation's `dispatch-once` and the hold release never read the holds while another of them is posting a hold or dispatching.
- pr-conversation already holds its dispatch ticket from `fold-turn-dispatch` through `dispatch-once`.
- `fold-decide` takes its own ticket before the read. It still has no concurrency group, so the wait cannot cancel a committed fold's dispatch the way a group's pending slot would.
- `fold-hold.yml` takes its ticket in `release-turn`, a job with no concurrency group, before `release` enters the per-spec group. A ticket waited for inside that group could deadlock against the ticket holder's own grouped job.
- Each deciding job releases its ticket last with `if: always()`. `release-cancelled` abandons the ticket of a `release` GitHub cancelled while it was pending.
- A ticket that cannot be taken (the admit's wait timed out) never dispatches blind. In `fold-decide` the holds stay unread, so the fold holds as `analyze-failed`. In the release, `release` does not run, and `release-cancelled` tells the owner the answer was not applied and the hold is still open.
- Gate 166 holds the lock in every caller, and Gate 128 holds every ticket job free of a concurrency group.

`wing-commander-fold-analyze` itself takes no credential input: it runs no agent and reads no issue.

## Outputs
| Name | Mode | Meaning |
|---|---|---|
| fold-id | stage | the fold's id |
| tasks | stage | task lines the fold section adds; `0` means skip the agent |
| section-file | stage | the staged fold section the agent reads as data |
| instructions-file | stage | the staged agent instructions (their one home); the caller's prompt points at it |
| decision | decide | `dispatch` \| `hold` \| `skipped` (no tasks in fold) \| `blocked` (another fold hold is open on the lifecycle) |
| hold-reason | decide | `constitution-conflict` \| `analyze-failed` \| empty |
| report-file | decide | the analyze report to link on the lifecycle issue (FR-015) |
| question-file | decide | owner question when `hold`, naming the task and, for constitution conflicts, the principle |

## The caller's agent step
Model `claude-sonnet-5-5` (Constitution II, FR-016); a `--max-turns` ceiling (12 turns); `--allowedTools "Read,Grep,Glob"` and `--disallowedTools` naming Write, Edit and Bash (FR-017); prompt pointing at `instructions-file`; transcript uploaded whatever the outcome (Gate 16); a `continue-on-error` fail-loud step on a non-healthy verdict (Gate 23).

## Agent output schema
The agent's final message ends with a ```` ```wing-commander-fold-analyze ```` fenced block: `{"findings":[{"severity","category","fold_task","location","principle","detail"}]}`; `category` ∈ constitution-conflict | inconsistency | duplication | other. The last such block counts. A missing block, a schema mismatch, a failed agent step or a non-healthy verdict ⇒ `hold` with `analyze-failed`.

## Decision rule (deterministic, `decide.py`, never the prompt)
`hold` iff any finding has `category == constitution-conflict` or the check failed. Otherwise `dispatch` (report linked). No findings ⇒ `dispatch`. A `dispatch` or `skipped` is `blocked` while another fold hold is open on the lifecycle. An open hold blocks every fold dispatch until it is answered. The report naming the open holds is posted on the lifecycle issue, and nothing is dispatched.

## Hold protocol
The question opens with `<!-- wing-commander-fold-hold: fold=<id> -->`; the caller posts it through `wc_fold_hold.py post-outcome`, which appends a `wing-commander-fold-hold-state` marker carrying what a release needs (spec dir and branch, base SHA, fold refs, folded-json, implement workflow). A maintainer (OWNER/MEMBER/COLLABORATOR) answers with a line `/fold-hold <answer>` on the lifecycle issue:

| Hold reason | Answers |
|---|---|
| constitution-conflict | `proceed` (dispatch), `drop` (commit the fold section's removal, then dispatch), `amend` (stays held; `proceed` once the amendment lands) |
| analyze-failed | `proceed`, `retry` (re-run the check; it posts a fresh outcome) |

The hold-release stage `fold-hold.yml` (`on: workflow_call` only; this repository's wrapper `wing-commander-fold-hold.yml` owns the `issue_comment` trigger and passes `issue`, `body` and `actor-association`) resolves the answer through `wc_fold_hold.py resolve` and records a released hold with a `wing-commander-fold-hold-resolved` marker, so a hold is released once. An answer addresses the newest open hold. Its release re-reads the holds inside the per-spec concurrency group. While another hold is still open, the release records its own hold as resolved and dispatches nothing; the release that answers the last open hold dispatches implement.

A `drop` reverses only what the fold added: each fold commit's own tasks.md diff when the hold state's `folded_json` names them, else the `fold_ref_before..fold_ref_after` range of a single fold commit. A tasks.md edit made between the fold commits is never reversed, and an implement tick inside a reversed range is kept. If one reversal no longer applies, tasks.md is left as it was and the hold stays open. The hold state's `fold_ref_before` is pr-conversation's classify base SHA.

A `drop` answer also dismisses the fold's findings. The lifecycle gate's hold state carries them as `fingerprints` on each `folded_json` entry (`post-outcome --fold-fingerprints`), and its later rounds read every App-authored `drop` resolved marker into the convergence ledger's dismissed list (contracts/convergence-signals.md): the reviewer raising one again is neither a recurrence nor re-folded. Any other answer dismisses nothing.

## Compatibility
Existing composites gain only optional inputs/outputs; no rename or removal. An adopter's `pr-conversation` gains one bounded read-only agent run per fold that adds tasks; it needs no new input or secret. The hold release is a new published stage, `fold-hold.yml`, which an adopter wires in beside `pr-conversation` (docs/adoption.md). Only its resolved marker closes a hold, so without it a hold never closes, and every later fold on that lifecycle stays `blocked` (FR-014). Gate 166 holds it to `on: workflow_call` only, and its wrapper to delegating only.
