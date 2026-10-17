# Contract: `wing-commander-fold-analyze` composite (published contract — additive)

## Placement
`fold-commit` → **`fold-analyze` (mode `stage`)** → the caller's read-only analyze agent step → **`fold-analyze` (mode `decide`)** → (`fold-dispatch` iff `decision` is `dispatch` or `skipped`). Callers: `pr-conversation.yml` (`dispatch-once`, after the `act` path's folds), `lifecycle-review-gate.yml` (`disposition`), and the hold-release job `wing-commander-fold-hold.yml` (`release`, on a `retry` answer).

A composite never invokes the agent (`verify-actions-layer-invariants.py`), so the agent step lives in each caller's job; the composite holds the deterministic halves only. Gate 166 (`verify-fold-analyze-wiring.py`) holds the order and the agent's shape in every caller.

## Inputs (all declared; no ambient state read)
| Name | Mode | Required | Notes |
|---|---|---|---|
| mode | both | yes | `stage` \| `decide` |
| spec-dir | stage | yes | e.g. `specs/116-review-convergence-analyze` |
| project | stage | no | the lifecycle's project folder (spec 114); empty for the root |
| fold-ref-before | stage | yes | tip before the fold commit (scopes the fold section) |
| fold-ref-after | stage | yes | tip after the fold commit |
| folded-json | stage | yes | `[{id, summary}]` from fold-commit/fold-evidence |
| fold-id, tasks | decide | yes | the stage mode's outputs |
| agent-outcome | decide | yes | the caller's agent step `outcome` |
| agent-verdict | decide | yes | `wing-commander-agent-verdict`'s verdict for that step |
| execution-output-path | decide | no | defaults to `${{ runner.temp }}/claude-execution-output.json` |

No credential input: the composite runs no agent.

## Outputs
| Name | Mode | Meaning |
|---|---|---|
| fold-id | stage | the fold's id |
| tasks | stage | task lines the fold section adds; `0` means skip the agent |
| section-file | stage | the staged fold section the agent reads as data |
| instructions-file | stage | the staged agent instructions (their one home); the caller's prompt points at it |
| decision | decide | `dispatch` \| `hold` \| `skipped` (no tasks in fold) |
| hold-reason | decide | `constitution-conflict` \| `analyze-failed` \| empty |
| report-file | decide | the analyze report to link on the lifecycle issue (FR-015) |
| question-file | decide | owner question when `hold`, naming the task and, for constitution conflicts, the principle |

## The caller's agent step
Model `claude-sonnet-5-5` (Constitution II, FR-016); a `--max-turns` ceiling (12 turns); `--allowedTools "Read,Grep,Glob"` and `--disallowedTools` naming Write, Edit and Bash (FR-017); prompt pointing at `instructions-file`; transcript uploaded whatever the outcome (Gate 16); a `continue-on-error` fail-loud step on a non-healthy verdict (Gate 23).

## Agent output schema
The agent's final message ends with a ```` ```wing-commander-fold-analyze ```` fenced block: `{"findings":[{"severity","category","fold_task","location","principle","detail"}]}`; `category` ∈ constitution-conflict | inconsistency | duplication | other. The last such block counts. A missing block, a schema mismatch, a failed agent step or a non-healthy verdict ⇒ `hold` with `analyze-failed`.

## Decision rule (deterministic, `decide.py`, never the prompt)
`hold` iff any finding has `category == constitution-conflict` or the check failed. Otherwise `dispatch` (report linked). No findings ⇒ `dispatch`.

## Hold protocol
The question opens with `<!-- wing-commander-fold-hold: fold=<id> -->`; the caller posts it through `wc_fold_hold.py post-outcome`, which appends a `wing-commander-fold-hold-state` marker carrying what a release needs (spec dir and branch, base SHA, fold refs, folded-json, implement workflow). A maintainer (OWNER/MEMBER/COLLABORATOR) answers with a line `/fold-hold <answer>` on the lifecycle issue:

| Hold reason | Answers |
|---|---|
| constitution-conflict | `proceed` (dispatch), `drop` (commit the fold section's removal, then dispatch), `amend` (stays held; `proceed` once the amendment lands) |
| analyze-failed | `proceed`, `retry` (re-run the check; it posts a fresh outcome) |

`wing-commander-fold-hold.yml` resolves the answer through `wc_fold_hold.py resolve` and records a released hold with a `wing-commander-fold-hold-resolved` marker, so a hold is released once.

## Compatibility
Existing composites gain only optional inputs/outputs; no rename or removal. An adopter's `pr-conversation` gains one bounded read-only agent run per fold that adds tasks; it needs no new input or secret. Without a hold-release wrapper of its own, an adopter dispatches a held fold by hand.
