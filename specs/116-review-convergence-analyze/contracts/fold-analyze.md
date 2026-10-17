# Contract: `wing-commander-fold-analyze` composite (published contract — additive)

## Placement
`fold-commit` → **`fold-analyze`** → (`fold-dispatch` iff `decision == dispatch`). Used by `pr-conversation.yml` (`act` path) and `lifecycle-review-gate.yml` (`disposition`).

## Inputs (all declared; no ambient state read)
| Name | Required | Notes |
|---|---|---|
| spec-dir | yes | e.g. `specs/116-review-convergence-analyze` |
| fold-ref-before | yes | tip before the fold commit (scopes the fold section) |
| fold-ref-after | yes | tip after the fold commit |
| folded-json | yes | `[{id, summary}]` from fold-commit/fold-evidence |
| anthropic-api-key / app credentials | yes | as other agent composites declare |
| max-turns | no | default bounded constant |

Model is fixed inside the composite: `claude-sonnet-5-5` (Constitution II). Tools: Read, Grep, Glob only (FR-017).

## Outputs
| Name | Meaning |
|---|---|
| decision | `dispatch` \| `hold` \| `skipped` (no tasks in fold) |
| hold-reason | `constitution-conflict` \| `analyze-failed` \| empty |
| report-markdown | the analyze report to link on the lifecycle issue (FR-015) |
| question-markdown | owner question when `hold`, naming the task and, for constitution conflicts, the principle |

## Agent output schema
`{"findings":[{"severity","category","fold_task","location","principle","detail"}]}`; `category` ∈ constitution-conflict | inconsistency | duplication | other. Schema mismatch or step error ⇒ `hold` with `analyze-failed`.

## Decision rule (deterministic, script not prompt)
`hold` iff any finding has `category == constitution-conflict` or the step failed. Otherwise `dispatch` (report linked). No findings ⇒ `dispatch`.

## Hold protocol
Question comment marker `<!-- wing-commander-fold-hold: fold=<id> -->`. Options: amend the spec / drop the fold task / proceed anyway (analyze-failed: proceed anyway / retry the check). Maintainer-authorized reply releases it; see research D9.

## Compatibility
Existing composites gain only optional inputs/outputs; no rename or removal. Adopters not wiring `fold-analyze` keep today's behaviour.
