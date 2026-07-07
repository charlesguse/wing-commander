# Phase 1 Data Model: Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection

This feature has no application data model — it manipulates GitHub
branches, a pull request event payload, GitHub issue comments/labels, and
(on one path only) one JSON file. The "entities" below are the ones named
in `spec.md`'s Key Entities section, expressed as their concrete
on-disk/on-GitHub representation, plus the `tasks/NNN-slug` branch
research.md adds to the deletion set.

## Pipeline pull request close event (`pull_request: closed`, repo-wide)

The signal that starts this stage — not persisted, read once per run
directly from `github.event.pull_request`.

| Field | Type | Used for |
|---|---|---|
| `head.ref` | string | Recognizing a pipeline branch prefix (`spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`) and deriving the slug |
| `base.ref` | string | Distinguishing "final/draft PR into `main`" from "non-final PR into `spec/NNN-slug`" (FR-009, FR-010) |
| `merged` | boolean | Selecting merged-teardown vs. rejected/stalled |
| `number` | integer | Fallback report target when identity resolution fails (research.md) |
| `merge_commit_sha` | string | Merged path only — the range the completion-summary step diffs |

Any event whose `head.ref`/`base.ref`/`merged` combination doesn't match
one of the three outcome shapes below is not owned by this stage and
produces no action (FR-010).

## Outcome resolution (computed, not stored)

The full disambiguation this stage performs, combining the job-level
gate and the in-job refusal check (research.md):

```
head=spec-draft/*, base=main, merged=true   → not owned here (plan stage's own trigger)
head=spec-draft/*, base=main, merged=false  → teardown-rejected
head=spec/*,        base=main, merged=true  → teardown-done
head=spec/*,        base=main, merged=false → mark-stalled (final-PR-rejected wording)
head∈{plan/*,tasks/*,impl/*}, base=main     → refused (FR-010 edge case: wrong merge target)
head∈{plan/*,tasks/*,impl/*}, base≠main,
  base derived-from-head ≠ actual base      → refused (FR-009/FR-010: not this spec's own base)
head∈{plan/*,tasks/*,impl/*}, base=spec/<slug>, merged=true  → not owned here (owning stage's own trigger)
head∈{plan/*,tasks/*,impl/*}, base=spec/<slug>, merged=false → mark-stalled (non-final-PR wording)
anything else (ordinary PR, unrecognized head prefix)        → not owned here
```

## Specification pipeline branches (deletion targets, `teardown-done` only)

| Branch | Deleted? | Notes |
|---|---|---|
| `spec-draft/NNN-slug` | Yes | May already be gone if the platform auto-deletes merged heads elsewhere in the pipeline; absent ⇒ success (FR-011) |
| `spec/NNN-slug` | Yes | The just-merged head itself; commonly already auto-deleted by GitHub's "automatically delete head branches" repo setting — absent ⇒ success (edge case) |
| `plan/NNN-slug` | Yes | |
| `tasks/NNN-slug` | Yes | Not named in `spec.md`'s Key Entities; included per research.md's decision (real branch in `SPECKIT_TASKS_REVIEW=pr` mode, required for SC-004) |
| `impl/NNN-slug-iter*` (glob) | Yes | Presently never created by the implemented Stage 4 (research.md finding); deletion attempt is a harmless no-op today |

On `mark-stalled`, **none** of these are deleted — FR-012/FR-013
explicitly preserve them for revival. On `teardown-rejected`, only
`spec-draft/NNN-slug` is deleted (the other branches don't exist yet at
the draft stage).

## Lifecycle record (`specs/NNN-slug/spec-meta.json`)

| Field | Read by this stage? | Written by this stage? | Notes |
|---|---|---|---|
| `issue` | Yes, on every path (identity check) | No | Must resolve to a real, matching lifecycle issue (FR-009) |
| `spec_dir` | Yes, on every path (identity check) | No | Must match the slug derived from `head.ref` |
| `stage` | Yes, on `mark-stalled` only (to know what to replace) | **`mark-stalled` only**, set to `"stalled"` | Committed onto the still-intact `spec/NNN-slug`, replacing the retired per-stage jobs' identical write (research.md) |

**State transition** (the slice of the full pipeline state machine this
stage owns):

```
(any)                     ──(final PR spec/NNN-slug → main merges)───────────▶ branches deleted, issue closed,
                                                                                 label → done; spec-meta.json on the
                                                                                 now-deleted branch is the last write
"draft" (no meta yet)      ──(draft PR spec-draft/NNN-slug → main closes,
                              unmerged)───────────────────────────────────────▶ draft branch deleted, stage+identity
                                                                                 labels removed, issue commented,
                                                                                 left OPEN (FR-014)
"implement"/"review"/etc.  ──(final PR spec/NNN-slug → main closes,
                              unmerged)───────────────────────────────────────▶ "stalled" (branches intact)
"plan"/"tasks"/"implement" ──(plan/tasks/impl PR → spec/NNN-slug closes,
                              unmerged)────────────────────────────────────────▶ "stalled" (branches intact)
(any of the above)         ──(event doesn't match an owned shape)─────────────▶ unchanged, no action (FR-010)
```

Only the `mark-stalled` row writes `spec-meta.json`; the other two rows
delete the branch that would have carried it (research.md's "never
commits to `main`" decision).

## Lifecycle issue (GitHub issue, unchanged shape from stages 1–5)

This stage's writes, all gated on the outcome-specific idempotency check
(research.md) passing:

| Outcome | Comment | Close/open | Labels |
|---|---|---|---|
| `teardown-done` | Completion summary, posted via `gh issue close --comment` (atomic) | **Closed** | `stage:done` added, whatever `stage:*` label was present removed |
| `teardown-rejected` | Rejection notice | Left **open** (FR-014) | `stage:*` **and** `spec:NNN-slug` both removed |
| `mark-stalled` | Rejection notice + full-teardown runbook (link + manual commands, FR-015) | Left open | `stage:stalled` added, whatever prior `stage:*` label was present removed; `spec:NNN-slug` identity label untouched |

## Completion summary (`teardown-done` only)

The one agent step's sole output — a human-readable narrative of what the
merged specification delivered, derived from
`git diff ${merge_commit_sha}^1..${merge_commit_sha}` and
`${merge_commit_sha}`'s own `git log` on a checkout of `main` (research.md
— never a checkout of `spec/NNN-slug`, so branch deletion and summary
generation are independent). Written to a plain-text temp file, consumed
verbatim by `gh issue close --comment` — no separate "PR body" surface
exists on this path (the final PR already merged; this stage never edits
it), unlike the finalize stage's dual PR-body/issue-comment mirror.

## Stalled-comment full-teardown runbook (`mark-stalled` only)

Not a stored entity — assembled deterministically per FR-015, following
`speckit-3-plan.yml`'s existing stalled-comment precedent: a link to the
closed pull request and to `docs/architecture.md`'s Stage 6 section, plus
literal `git push origin --delete <branch>` / `gh label` commands scoped
to whichever branches this specific specification still has (draft PR
stalled ⇒ nothing to preserve differently; final/non-final PR stalled ⇒
`spec/NNN-slug`, `plan/NNN-slug`, `tasks/NNN-slug`, any `impl/*` — the
same five-branch set `teardown-done` would otherwise delete, offered here
as an opt-in manual action instead).
