# Phase 1 Data Model: End-to-End Verification Tier That Actually Verifies

This feature extends two of `specs/027-auto-update-spec-kit/data-model.md`'s
existing shapes and adds two entities that did not exist before (the
AI-driven stage run and the scratch repository). It writes no new
persisted file — every shape below is either ephemeral (produced and
consumed within one workflow run) or, for the scratch repository, a real
GitHub resource whose lifecycle is derived from the lifecycle issue rather
than tracked in a separate ledger (research.md).

## Verification (smoke test) result — EXTENDED from specs/027

| Field | Type | Notes |
|---|---|---|
| `tier` | enum: `lightweight` \| `lightweight+end-to-end` | Unchanged — still selected purely by `release_type` (FR-011). |
| `lightweight.passed` | boolean | Unchanged: `create-new-feature.sh` + `check-prerequisites.sh --paths-only` ran and produced the documented JSON shape. |
| `end_to_end.passed` | boolean \| null | **Changed meaning.** `null` when not applicable (patch upgrade, unchanged). For minor/major, now depends on *five* gating checks instead of one copy-and-non-empty check: `spec.md` on-disk non-empty, `setup-plan.sh --json` shape + `plan.md` on-disk non-empty, `setup-tasks.sh --json` shape, and the AI-driven stage's completion + documented output (below). A failure in **any** of the five fails this field (FR-002/FR-018) — there is still exactly one `end_to_end.passed` boolean, not a per-check array; per-check detail lives in `failure_detail`. |
| `failure_detail` | string \| null | **Changed source, same shape.** Now carries whichever single check actually failed, named explicitly (e.g. "setup-plan.sh --json did not produce the documented IMPL_PLAN shape" vs. the old tier's one hardcoded reason) — still what SC-004 requires the issue to carry so a human never needs run logs. When the failing check is a missing-expected-artifact case, this string additionally carries the FR-008 non-clean-bump hint (see Failure narration, below) — narration content only, per FR-009. |

A candidate is "working" only if every check applicable to its tier passed —
unchanged definition (FR-004's own text), now backed by real per-candidate
behaviour instead of a check that could not fail (SC-001/SC-002/SC-003).

## AI-driven stage run (ephemeral, produced by the new `e2e-stage` job, consumed by `verify`'s combine step)

| Field | Type | Notes |
|---|---|---|
| `completed` | boolean | Derived from the agent step's own `outcome` (`success` vs. anything else — `failure`, `cancelled`, `timed_out`, `skipped` from `continue-on-error: true`), never from agent narration (research.md — same "deterministic read-back, never trust narration" convention `evaluate-path`'s `decide-outcome` already establishes). |
| `output_present` | boolean | Whether a non-empty `specs/*/spec.md` exists in the scratch repository's local working tree after the agent step, checked deterministically by the read-back step — the "documented stage output in the documented shape" FR-018 requires. |
| `passed` | boolean | `completed && output_present`. This is the single gating value `end_to_end.passed` folds in as one of its five checks (above). |
| `failure_detail` | string \| null | States explicitly whether the failure was "the stage did not complete" (infrastructure/agent problem) or "the stage completed but produced no/wrong-shaped output" (candidate- or prompt-shape problem) — the FR-021 distinction the narration must preserve. |
| `scratch_repo` | string | `owner/wing-commander-e2e-<issue-number>` — carried through so the combine step and the issue narration (FR-022) can name it regardless of pass/fail/error. |

There is no persisted record of this entity beyond the one workflow run
that produces it — like the existing Verification result, it is consumed
once by `combine` and then only exists as text on the lifecycle issue.

## Scratch repository (a real GitHub repository, not a file — created per run, name derived from the lifecycle issue)

| Field | Type | Notes |
|---|---|---|
| Name | `wing-commander-e2e-<lifecycle-issue-number>` | Deterministic (research.md) — the name *is* the mapping back to its owning lifecycle issue; no separate ledger. |
| Owner | `github.repository_owner` | The consuming repository's own account/org (constitution VI) — never a fixed Wing-Commander-owned account. |
| Visibility | private | No candidate-verification content is meant for public consumption. |
| Contents | The candidate's own regenerated `.specify/` scaffold (from the same `specify init` command `prepare` already runs), plus — best-effort, non-gating — the `e2e-stage` agent's produced `spec.md` if it completed. | Exists so FR-022's "a maintainer... can inspect it" holds even when `e2e-stage` fails or times out (the scaffold push happens before the agent step runs). |
| Created by | The `e2e-stage` job, idempotently (`gh repo view` then create-if-absent) | A re-dispatched run for the same still-open lifecycle issue reuses the existing scratch repository rather than creating a duplicate. |
| Retained while | The named lifecycle issue is open (FR-019) | Survives every run outcome — pass, fail, or error — by construction: nothing in `e2e-stage` or `verify` ever deletes it. |
| Deleted by | (a) the new `issues: {types: [closed]}` trigger's dedicated deletion branch, matched against the closed issue's own settle-tracking marker (self-recognition, unchanged discipline from every other trigger); (b) a scheduled backstop sweep (every `scheduled`/`dispatch` run) that lists all `wing-commander-e2e-*` repositories under the owner and deletes any whose derived issue is closed or missing (FR-023) | Both paths call the same idempotent delete; neither errors on an already-absent repository. |

No field of this entity is ever written to a file in this repository — it
is entirely GitHub-hosted state, discovered by name pattern rather than
tracked, matching the "state that already exists beats a new ledger"
pattern this repository's auto-update feature already established twice
(specs/027's settle-tracking marker and rollback-target lookup).

## Failure narration (EXTENDED from specs/027's "Auto-update lifecycle issue" comments)

specs/027's existing "Auto-update lifecycle issue" entity (label, state,
comment mechanics) is unchanged — this feature only extends what one
specific comment (the verification-failure comment the `act` job already
posts via `wing-commander-callout`) contains:

| Field | Type | Notes |
|---|---|---|
| `failing_check` | string | Which of the tier's checks failed — one of: lightweight (unchanged reason text), a named per-script assertion (spec.md/plan.md non-empty, `setup-plan.sh`/`setup-tasks.sh` shape), or the e2e-stage (distinguishing "did not complete" from "wrong/missing output", FR-021). |
| `expected_vs_observed` | string | What shape/behavior was expected and what was actually observed — FR-007's requirement, present for every failure reason. |
| `non_clean_bump_hint` | string \| null | Present **only** when `failing_check` is a missing-expected-artifact case: states the artifact may have been legitimately relocated/reorganized by the candidate and points at specs/027 FR-018 (FR-008). `null`/absent for every other failure reason (non-zero exit, wrong-shape, e2e-stage-incomplete) — FR-009 requires this be the *only* varying element, never a second outcome path. |
| `scratch_repo_pointer` | string | Present whenever `e2e-stage` ran (i.e., whenever the tier is `lightweight+end-to-end`, regardless of pass/fail): names the scratch repository and states it will be deleted when this issue closes (FR-022, present even on the tier's overall pass — SC-012 doesn't gate this pointer on failure). |

All four fields compose into the single `failure-detail` string the
`combine` step already assembles and the `act` job already posts — no new
comment, no new callout kind, no new label. On a passing run, only
`scratch_repo_pointer`-equivalent information is posted (as part of the
existing pass-path summary/comment, not a new one), satisfying SC-012
without adding a write path.

## State transition (the slice of specs/027's own diagram this feature changes)

```
       prepare (unchanged) → verify
         lightweight fails ─────────────────────▶ combine: passed=false, detail=lightweight reason (unchanged)
         lightweight passes, tier=lightweight ──▶ combine: passed=true (unchanged, patch jump)
         lightweight passes, tier=lightweight+end-to-end:
           spec.md empty/missing ───────────────▶ combine: passed=false, detail names spec.md + non-clean-bump hint
           setup-plan.sh fails or plan.md empty ▶ combine: passed=false, detail names setup-plan.sh (+ hint if template-missing)
           setup-tasks.sh fails ─────────────────▶ combine: passed=false, detail names setup-tasks.sh (+ hint if template-missing)
           e2e-stage did not complete ───────────▶ combine: passed=false, detail states "stage did not complete" (FR-021)
           e2e-stage completed, wrong/no output ─▶ combine: passed=false, detail names expected vs. observed shape
           all five checks pass ─────────────────▶ combine: passed=true, tier=lightweight+end-to-end

(any minor/major verify run, regardless of pass/fail/error)
  └─ e2e-stage created/reused wing-commander-e2e-<issue> before or during its own run;
     survives this run's outcome unconditionally

(issues, type=closed, this feature's own marker present)
  └─ delete wing-commander-e2e-<issue> if present (event-driven path)

(scheduled/dispatch, every run, independent of the day's own upgrade cycle)
  └─ sweep: for each wing-commander-e2e-* repo under the owner,
       derive <issue> from the name; issue closed or missing → delete (backstop path)
```

Everything upstream of `verify` (health-check, detect, settle,
evaluate-path, prepare) and everything downstream of `combine` (`act`'s
PR-open / label-and-comment branches, `pr-merged`, `comment-reply`) is
unchanged from specs/027 — this feature's data-model impact is entirely
contained to what `verify` computes and what one comment says.
