# Phase 1 Data Model: Run-Scoped Fold Evidence

Like spec 042, this feature has no application database — every entity
below is a git commit shape, a GitHub Actions job/step input or output
(ephemeral, run-scoped), or a PR comment. This document gives each entity's
concrete shape, referencing research.md's decisions (D1–D7) for the
reasoning behind each. Every entity not listed here (the classification
schema, `spec-meta.json`, the final PR body's machine-owned region) is
unchanged from spec 042's data-model.md.

## 1. Fold commit (extended)

Written by a fold-route leg in the `act` job (`pr-conversation.yml`
~2009–2013), unchanged in its user-visible subject line.

| Part | Shape | Added by | Notes |
|---|---|---|---|
| Subject | `fold(<leg-id>): <summary>` | spec 042 | Unchanged — Gate 34's structural check still asserts this literal substring appears in the agent's prompt. |
| Trailer | `Wing-Commander-Run-Id: <github.run_id>` | **this feature** (D1) | Appended by a `prepare-commit-msg` git hook the `act` job installs on the leg's checkout before the agent runs — never written by the agent itself. One trailer line, present on every commit made in that checkout for the duration of the leg. |

A commit with no `Wing-Commander-Run-Id:` trailer (made before this
feature shipped, or made by a human directly on the spec branch) is not
absent from git history — it is absent from **evidence**: D2's composite
never returns it, regardless of which leg id its subject names (FR-007).

## 2. `act` job (extended)

No new job output. One new step, "Install run-attribution hook for this
leg's commits," between "Checkout working tree for this leg" (~1911) and
"Act on this classification" (~1959):

| Behavior | Notes |
|---|---|
| Writes a `prepare-commit-msg` script to a path outside the checked-out working tree (so `git status`/`git add -A` in the leg's own checkout never sees it as an untracked file) | Script body: append a blank line then `Wing-Commander-Run-Id: ${{ github.run_id }}` to the file named in its first argument, using `git interpret-trailers --if-exists addIfDifferent` semantics via a plain `printf`/`>>` append, since the hook fires once per commit and the trailer is always the same value. |
| Runs `git config core.hooksPath <that path>` in the leg's checkout | Local to this checkout only — never a global git config, never touching any other job's or leg's working tree. |

## 3. `wing-commander-fold-evidence` composite action (new)

`.github/actions/wing-commander-fold-evidence/action.yml` — the single
home (FR-009) for reading which fold commits, in a given range, belong to
a given run (D2).

**Inputs**:

| Name | Type | Required | Default | Notes |
|---|---|---|---|---|
| `working-directory` | string | true | — | Path to the spec-branch checkout (`fetch-depth: 0`) holding the commit range to read. |
| `base-sha` | string | true | — | Range start (exclusive), same value as today's `BASE_SHA`. |
| `tip-sha` | string | true | — | Range end (inclusive), same value as today's `TIP_SHA`; caller computes this exactly as it does today (D2 — each caller keeps its own independently-read tip). |
| `run-id` | string | false | `${{ github.run_id }}` | The run whose evidence to select. Callers pass the default; the input exists so Gate 34's harness can drive the composite with a synthetic run id without depending on a real Actions context. |

**Output**:

| Name | Type | Notes |
|---|---|---|
| `folded-json` | string (JSON array) | `[{"id": "leg-0", "summary": "..."}, ...]` — one entry per commit in `base-sha..tip-sha` whose subject matches `^fold(<id>): <summary>$` and whose body contains the trailer `Wing-Commander-Run-Id: <run-id>` (exact match). Empty array (`[]`), never a missing output, when `base-sha == tip-sha` or the range is otherwise empty — callers must not special-case a missing output. |

**Logic**:

```
candidates = git -C <working-directory> log --grep '^fold(' \
             --format='%H%x1f%s' <base-sha>..<tip-sha>
result = []
for (sha, subject) in candidates:
    match = subject =~ /^fold\(([^)]+)\): (.*)$/
    if not match: continue
    body = git -C <working-directory> show -s --format=%B <sha>
    if body contains line "Wing-Commander-Run-Id: <run-id>":
        result.append({id: match[1], summary: match[2]})
echo "folded-json=$(json_encode result)" >> "$GITHUB_OUTPUT"
```

## 4. `dispatch-once` job (changed)

`needs`/`if:` unchanged from spec 042. Step "Dispatch implement once for
the whole review" (~2688–2751) changes its evidence source; the tip-read
step (~2663–2672) and the standalone-mode reply path (~2716–2727,
`implement-workflow` empty) are unchanged.

| Before (spec 042) | After (this feature) |
|---|---|
| `folded=$(git log --grep '^fold(' --format='%s' "$BASE_SHA..$TIP_SHA" \| sed ...)` | Calls `wing-commander-fold-evidence` with this job's own `base-sha`/`tip-sha`; `folded` is `folded-json`'s entries rendered the same `- <id>: <summary>` way for the PR comment. |
| Dispatch condition: `tip != base-sha` | Dispatch condition: `folded-json` is non-empty (D3). |
| No behavior when tip moved but nothing was this run's own fold | **New**: post one declined-dispatch notice (D4, FR-015) when `tip != base-sha` **and** `folded-json` is empty; post nothing when `tip == base-sha` (unchanged silent path). |

## 5. `report-fold-outcomes` job (changed)

`needs`/`if:` unchanged. Step "Report fold-route leg outcomes"
(~2764–2954) changes only its per-leg `folded` check (~2923–2926); the job-
conclusion read (~2890, including the #417 caller-prefixed job-name match)
and the outcome derivation (~2928–2935) are unchanged.

| Before (spec 042 + #417) | After (this feature) |
|---|---|
| `folded=false; if git log --grep "^fold($id):" ... "$range" \| grep -q .; then folded=true; fi` | Calls `wing-commander-fold-evidence` once with this job's own `base-sha`/`tip-sha`; `folded=true` iff `id` is a member of `folded-json`. |
| Evidence could belong to any run | Evidence is scoped to this run only (FR-001), read once per job invocation and reused for every announced leg id, not re-queried per leg. |

Outcome table (unchanged from spec 042's data-model.md §4 — restated here
because the input to it changed, not the table itself):

| Job conclusion | This run's own fold evidence | Outcome |
|---|---|---|
| `success` | present | healthy — no report |
| anything else | present | partly folded |
| anything | absent | not folded |

## 6. Declined-dispatch notice (new, FR-015)

Posted by `dispatch-once` as a single PR comment, distinct from both the
existing dispatch-confirmation comment and `report-fold-outcomes`'s
warning comment.

| Field | Value |
|---|---|
| Trigger | `folded-json` empty **and** branch tip moved during this run's window. |
| Content | States plainly that this run folded nothing of its own and therefore dispatched no implement cycle — so the absence of a dispatched cycle reads as this run's decision, not a lost one (Constitution III). |
| Cardinality | At most one per run, same as every other `dispatch-once` comment. |
| Distinct from | #415 option 4's concurrency-cancellation notice (out of scope here) and `report-fold-outcomes`'s per-leg warning (a different job, a different trigger, a different reader concern). |

## 7. `workflow_call` interface (unchanged, FR-016 analog)

No `pr-conversation.yml` `workflow_call` input, output, or secret is added,
renamed, or removed by this feature. The new composite action is an
internal implementation detail resolved by self-checkout, not a published
interface change.
