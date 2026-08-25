# Phase 1 Data Model: The Post-Review Fold Loop

This feature has no application database — every entity below is either a
GitHub Actions job/step output (ephemeral, run-scoped), a field in
`spec-meta.json` (the pipeline's existing persisted lifecycle record, per
constitution "Operational Constraints"), or a delimited region of a PR
body. This document gives each entity's concrete shape, referencing
research.md's decisions (D1–D13) for the reasoning behind each.

## 1. Classification item (extended)

Produced by `pr-conversation.yml`'s `classify-and-announce` job
(`steps.confirm.outputs.classifications`, a JSON array), one entry per
classified review item. This feature adds one field; every other field is
unchanged from specs/033's `contracts/classification-schema.md`.

| Field | Type | Added by | Notes |
|---|---|---|---|
| `id` | string | **this feature** (D6) | `"leg-" + <0-based index>`, assigned before the existing `sort_by` reorders the array, so `id` is stable regardless of confirm-gated-vs-ready ordering. |
| `category` | string | specs/033 | Unchanged. |
| `requires-confirmation` | boolean | specs/033 | Unchanged. |
| `confirm-environment` | string | specs/033 | Unchanged. |
| *(all other existing fields)* | — | specs/033 | Unchanged — see specs/033's own contract for the full shape. |

## 2. `classify-and-announce` job outputs (extended)

| Output | Type | Added by | Notes |
|---|---|---|---|
| `base-sha` | string (git SHA) | **this feature** (D3) | The spec branch's tip immediately before `act` starts, read via `git ls-remote`. Consumed by `dispatch-once` to detect whether any leg folded. |
| `spec-dir`, `slug`, `default-branch`, `issue-number`, `classifications`, `concurrency-group`, `qualifies`, `refusal-reason` | — | specs/033/etc. | Unchanged — already present (`pr-conversation.yml:389–403`); reused as-is by both new jobs. |

## 3. `dispatch-once` job (new)

`needs: [classify-and-announce, act]`, `if: always() && needs.classify-and-announce.outputs.qualifies == 'true' && needs.classify-and-announce.outputs.classifications != '[]'`.

**Inputs it reads**: `needs.classify-and-announce.outputs.{base-sha,spec-dir,slug,default-branch,issue-number}`.

**Logic**:
```
tip = git ls-remote origin refs/heads/<spec-prefix><slug> | cut -f1
if tip == base-sha:
    no-op (nothing to dispatch — every leg was held-timed-out, failed, a
           question, or a no-action note)
else:
    iteration = jq '.iteration' spec-meta.json (at tip)
    gh workflow run implement.yml -f spec_dir=<spec-dir> -f issue=<issue> -f iteration=<iteration + 1>
    post ONE PR comment: "Implementation cycle <n> dispatched — folded
    items from this review: <list of item ids/summaries whose fold
    evidence (D6) is present at this tip>."
```

**Outputs**: none consumed downstream within this workflow; the dispatch
itself is the effect (mirrors today's per-leg dispatch step's contract,
just consolidated to run once).

## 4. `report-fold-outcomes` job (new)

`needs: [classify-and-announce, act]`, `if: always()`.

**Inputs it reads**: `needs.classify-and-announce.outputs.classifications`
(for the announced-item id/category/summary list, excluding `no-action`),
`needs.classify-and-announce.outputs.base-sha`, `github.run_id`,
`github.repository`.

**Logic**:
```
jobs = gh api repos/$REPO/actions/runs/$RUN_ID/jobs --paginate
       | jq '[.jobs[] | select(.name | startswith("act (leg-"))]'
for each announced item (excluding no-action):
    job = jobs entry whose .name contains item.id
    conclusion = job.conclusion  // "missing" (job never ran at all —
                                     e.g. matrix job itself crashed before
                                     the leg started)
    folded = git log --grep="^fold(<item.id>):" <base-sha>..<tip> --oneline
             is non-empty
    if conclusion == "success" and folded:
        healthy — no report for this item
    elif folded and conclusion != "success":
        outcome = "partly folded"
    else:
        outcome = "not folded"
if any non-healthy outcomes:
    post ONE PR comment listing each item's id/summary/outcome, stating
    it needs attention
else:
    post nothing
```

**Outcome table** (US2 acceptance criteria mapped to the two signals):

| Job conclusion | Fold evidence (`fold(id):` commit present) | Outcome | Maps to |
|---|---|---|---|
| `success` | present | healthy — no report | US2 AS5 |
| `cancelled` | absent | not folded | US2 AS1, AS3 (leg cancelled or never started) |
| `failure` | absent | not folded | US2 AS2 (fold itself failed) |
| `failure` | present | partly folded | US2 AS2 ("distinguishes not folded from partly folded") |
| `cancelled` | present | partly folded | fold commit landed, then cancellation struck before the leg's own confirmation reply completed |
| `missing` (job record absent) | absent | not folded | leg never started at all — report does not depend on any value it would have published (FR-006a) |

## 5. `spec-meta.json` (extended)

Existing fields (`stage`, `iteration`, `spec_dir`, `feature_num`,
`spec_branch`, `issue`, and — per specs/040 — `truncated_count`) are
unchanged. This feature adds:

| Field | Type | Written by | Cleared by | Notes |
|---|---|---|---|---|
| `pending_re_review_from` | array of strings (GitHub logins) | `pr-conversation.yml`'s `dispatch-once` job, unioned with any existing entries, at fold time (D10) | `finalize.yml`'s refresh path, after issuing (or attempting) the re-review request | Absent/treated as `[]` when not present — a spec branch predating this feature reads as "no lifecycle-record identity; fall back to PR review records" (D10). |

## 6. Final PR body — machine-owned region (new structure, D9/D9a)

```
<human prose, if any — preserved verbatim across refreshes>

<!-- wing-commander-finalize:state:begin -->
**Branch**: `<spec-prefix><slug>` → `<default-branch>`
**Iteration**: <n> | **Stage**: review
**Tasks**: <checked>/<total> checked in tasks.md
<!-- wing-commander-finalize:state:end -->

<!-- wing-commander-finalize:fold-log:begin -->
- Fold (<date>, review by <@login[, @login...]>, #<issue>) <short-sha>: <n> items folded — <one-line summary>.
- Fold (<date>, review by <@login>, #<issue>) <short-sha>: <n> items folded — <one-line summary>.
<!-- wing-commander-finalize:fold-log:end -->

<!-- wing-commander-finalize:narrative:begin -->
<summary, "## How to see it", "## Remaining manual work", lifecycle issue link — regenerated wholesale every run>
<!-- wing-commander-finalize:narrative:end -->

<human prose, if any — preserved verbatim across refreshes>
```

**Regeneration rule** (D9): on every refresh, everything between
`state:begin` and `state:end` is fully overwritten from the current branch
state. Everything between `fold-log:begin` and `fold-log:end` is the
existing entries, re-emitted unchanged, plus at most one new entry (D9a).
Everything between `narrative:begin` and `narrative:end` is fully
overwritten from the current run, same as the state block — it is
machine-generated on every run (what changed, what remains), not prose a
human added, so it must never be preserved from a prior body (PR #253
review: an earlier shape left the narrative outside the delimited region,
so "preserve everything outside the region" preserved the PRIOR run's own
narrative and a fresh one was appended below it on every refresh).
Everything outside `state:begin`…`narrative:end` is copied byte-for-byte
from the PR's current body.

**Idempotency key** (D9a): the short-sha embedded in each fold-log entry
is the branch tip the entry describes. Before appending, the refresh
compares the current tip to the most recent existing entry's sha; equal
means no new entry is appended (FR-010a).

## 7. `implement.yml` tool grant (extended, D11)

| Call site | File:line | Existing grant (excerpt) | Added |
|---|---|---|---|
| `implement.cycle` | `implement.yml:725` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),...` | `Bash(git rm:*)` |
| `implement.retry` | `implement.yml:1086` | same, plus `Bash(git pull:*),Bash(git fetch:*),Bash(git reset:*)` | `Bash(git rm:*)` |

Convergence (`/speckit-converge`, run as step 3 of the same agent prompt
in both call sites — `implement.yml:798–803`, `1184–1189`) shares whichever
of the two grants above is active for that job; no third call site exists,
so FR-012 ("cycle, retry, convergence... MUST NOT diverge") holds by
construction.

## 8. Published contract delta

`specs/010-reusable-pipeline/contracts/stage-interfaces.md`, "Per-stage
default tool lists" table (248–294): the `implement.cycle` (line 274) and
`implement.retry` (line 275) rows each gain `Bash(git rm:*)`, matching
`implement.yml`'s two literal edits exactly — enforced by the existing
Gate 27 (D12), not a new check.

## 9. `workflow_call` input additions (both optional, both preserve current default behavior — FR-016)

| Workflow | Input | Type | Default | Used by |
|---|---|---|---|---|
| `pr-conversation.yml` | `confirm-timeout-minutes` | number | `1440` | `act` job's `timeout-minutes:` (D5) |

No other `workflow_call` input, output, or secret is added, renamed, or
removed on any of the three affected stages (FR-016).
