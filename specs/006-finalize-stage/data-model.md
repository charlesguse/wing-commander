# Phase 1 Data Model: Finalize Stage — Final Pull Request & Manual-Task Report

This feature has no application data model — it manipulates one git branch,
one GitHub pull request, GitHub issue comments/labels, and one JSON file. The
"entities" below are the ones named in `spec.md`'s Key Entities section,
expressed as their concrete on-disk/on-GitHub representation.

## Finalization hand-off (`workflow_dispatch` inputs)

The signal that starts this stage — not persisted, validated once per run.

| Field | Type | Validation | Source |
|---|---|---|---|
| `spec_dir` | string | `^specs/[0-9]{3}-[a-z0-9][a-z0-9-]*$` | Dispatched by the implement stage (`speckit-5-implement.yml`), or a manual restart |
| `issue` | string (integer) | `^[0-9]+$` | Lifecycle issue number |
| `converged` | string (bool) | `^(true|false)$` | Whether the last implement/converge cycle converged before hitting `SPECKIT_MAX_ITERATIONS` |

Any value failing its validation, or a `spec_dir` whose
`spec.md`/`plan.md`/`tasks.md`/`spec-meta.json` are missing on
`spec/NNN-slug`, or a `spec-meta.json` whose own `issue`/`spec_dir` fields
disagree with the dispatch inputs, is refused before any further action
(FR-014, research.md's refusal-check decision).

## Lifecycle record (`specs/NNN-slug/spec-meta.json`)

Durable source of truth for a specification's pipeline position (already
defined by stages 1–4; this stage reads it only as part of the refusal
check and writes exactly one field).

| Field | Type | Written by this stage? | Notes |
|---|---|---|---|
| `issue` | integer | read only | Must match the dispatch input (refusal check). |
| `spec_dir` | string | read only | Must match the dispatch input (refusal check). |
| `feature_num` | string | read only | `NNN`. |
| `stage` | string | **written** | Set to `"review"` once the final PR is verified to exist (research.md's verify-then-write decision) — transition from `"implement"` (converged) or `"implement"` (cap reached, not converged; the implement stage does not change `stage` on hand-off). Left untouched on any refusal, duplicate, no-diff, or own-work-failure path. |
| `iteration` | integer | read only | Not interpreted by this stage; belongs to the implement stage. |
| `spec_branch` | string | read only | `spec/NNN-slug`; the final PR's head. |

**State transition** (the slice of the full pipeline state machine this
stage is responsible for):

```
"implement" ──(no existing final PR, real diff vs main, PR opens)──▶ "review"
"implement" ──(a final PR for this spec already exists, any state)──▶ "implement" (no-op, FR-012)
"implement" ──(spec branch has no diff against main)─────────────────▶ "implement" (no-op, anomaly reported, FR-013)
(any)       ──(hand-off doesn't match a valid specification)─────────▶ (unchanged, refused, FR-014)
"implement" ──(PR creation cannot be verified)────────────────────────▶ "implement" (no-op, failure reported, FR-015)
```

Only the first row advances `stage`; every other row leaves the durable
record exactly as the implement stage last wrote it, so a subsequent
dispatch can still tell "already finalized" (the PR-reuse check, keyed off
the PR itself, not this field — research.md) from "never successfully
finalized yet, safe to retry."

## Final pull request (`spec/NNN-slug → main`)

The single review surface this stage opens. Not itself a stored entity —
its existence is queried live via `gh pr list --head spec/NNN-slug --base
main --state all` both for the idempotency check (before) and the
verification check (after `gh pr create`).

| Attribute | Source |
|---|---|
| Head / Base | `spec/NNN-slug` / `main` |
| Title | e.g. `Finalize: <feature name> (#<issue>)`, derived from `spec.md`'s title heading |
| Body | Assembled deterministically (see Change summary / Remaining-manual-work list / Convergence flag below) |
| Opened by | This stage, via `gh pr create` using the App token |
| Merged by | A human, never this stage (FR-011) |

## Change summary

The Haiku step's first output artifact — a human-readable narrative of what
changed between `main` and `spec/NNN-slug`, derived from `git log`/`git
diff --stat` over that range. Written to a plain-text temp file (e.g.
`${{ runner.temp }}/finalize-summary.md`); consumed verbatim by the
PR-body-assembly step. The "how to see it" half of FR-004 (compare link +
changed-file list) is *not* part of this artifact — it is computed by a
separate deterministic step (research.md).

## Remaining-manual-work list

The Haiku step's second output artifact — the unchecked and human-only
items drawn from `tasks.md`, one per line, written to a second plain-text
temp file (e.g. `${{ runner.temp }}/finalize-remaining.md`). This is the
single source of truth two independent writes read verbatim:

| Consumer | Behavior when the file has content | Behavior when the file is empty |
|---|---|---|
| PR body's "Remaining manual work" section | The file's content, unmodified | Literal "No manual work remains." (FR-006) |
| Lifecycle issue comment | The same file's content, unmodified | The same literal "No manual work remains." |
| ⚠️ Not-converged banner's task count (`converged=false` only) | Count of non-empty lines in this file | N/A (banner not shown when `converged=true`) |

Reading both consumers (and the banner count) from the same file is what
guarantees SC-003 ("the remaining-manual-work list shown in the final pull
request matches the list posted to the lifecycle issue") without relying on
an agent to reproduce identical text twice.

## Convergence flag (`converged` input)

Carried by the hand-off, consumed as-is (this stage does not re-judge
convergence, per `spec.md`'s Assumptions).

| Value | PR body effect |
|---|---|
| `true` | No banner; PR body opens directly with the change summary. |
| `false` | A prominent note near the top of the PR body: "⚠️ **Not fully converged — N tasks remain**" (N from the remaining-manual-work file's line count above), before the change summary (FR-010). |

## Lifecycle issue (GitHub issue, unchanged shape from stages 1–4)

This stage's writes, all gated on the final PR being verified to exist
(research.md):

- **Comment**: the remaining-manual-work list (or "No manual work
  remains."), posted once (FR-005). On a duplicate/no-diff/refused/failed
  run, no comment beyond the anomaly/failure report below is posted.
- **Label**: `stage:review` added, removing `stage:implement` (FR-007) —
  the last write this stage performs, after the metadata commit and the
  remaining-manual-work comment.
- **Anomaly / failure reports** (do not advance `stage` or the label):
  no-diff anomaly (FR-013), refusal reason if the hand-off doesn't match a
  valid specification (FR-014, reported if an issue number was at least
  resolvable), own-work failure if PR creation cannot be verified (FR-015).
