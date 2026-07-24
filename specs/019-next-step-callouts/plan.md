# Implementation Plan: Clear Next-Step Callouts in the Lifecycle Issue

**Branch**: `spec/019-next-step-callouts` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-next-step-callouts/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Today the pipeline announces the spec-phase PR with freeform agent text and
never announces the implementation/finalize-phase PR at all — the core gap
User Story 1 reports — while every other human-action moment (clarification
questions, remaining manual work, failure/stall states) uses its own
undocumented, inconsistent per-stage icon convention with no shared
"you must act" signal (`research.md` current-state audit).

The approach introduces one new shared composite action,
`wing-commander-callout` (`.github/actions/wing-commander-callout/action.yml`,
following the same self-checkout pattern `wing-commander-context` and
`wing-commander-preflight` already establish), as the single enforcement
point for the action-required/informational convention. Action-required
callouts render inside GitHub's native `[!IMPORTANT]` Markdown alert box —
a distinctly colored, boxed callout GitHub already renders on every surface
with zero custom tooling, directly serving constitution III (GitHub-native,
no dashboard) and SC-002 (identify the next step in under 15 seconds).
Informational messages keep their existing per-stage icon shape, unwrapped,
which already satisfies FR-005 without requiring any change to the ~15
existing purely-informational comment sites this feature doesn't touch.

Ten existing comment sites across six workflow files
(`intake.yml`, `clarify.yml`, `finalize.yml`, `implement.yml`, `rebase.yml`,
`cleanup.yml`) are migrated to invoke the new action, enumerated exactly in
`contracts/callout-points.md` — most importantly a brand-new call after
`finalize.yml` verifies the final PR was created (the User Story 1 fix), and
`finalize.yml`'s remaining-manual-work comment gaining explicit "human
to-do, after this PR merges" framing (User Story 3). Wherever a callout's
body content is naturally freeform (clarification questions, the
remaining-work list), the agent keeps authoring that content into a temp
file exactly as `finalize.yml` already does today; a new deterministic bash
step immediately after decides `kind` from a simple condition (marker
presence, file emptiness, PR-verification success) and invokes the
composite action — so the convention itself is never left to agent
judgment, which is what guarantees SC-003 ("no ambiguous cases") on every
run, not just most. `plan.yml`'s gate-mode-fallback warning and every
`watchdog.yml` comment are deliberately left unmigrated (research.md scope
decision) as outside what `spec.md` describes.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (`workflow_call` reusable
workflows and one new composite action) + POSIX `bash` steps; no application
language — this is CI/CD infrastructure, matching every other spec in this
repo.

**Primary Dependencies**: `gh` CLI (issue comment posting, PR
lookup/verification — no new dependency, every call site already uses it),
`anthropics/claude-code-action` (unaffected — no new agent step; two
existing agent prompts lose their `gh issue comment` instruction and instead
write to a temp file, matching `finalize.yml`'s already-established
pattern), GitHub's native Markdown Alert syntax (`[!IMPORTANT]` — a
GitHub-rendering feature, not a library or package).

**Storage**: N/A — no database, no new file-based store. No new field is
added to `spec-meta.json` (data-model.md, State/lifecycle).

**Testing**: This repo has no unit-test suite for workflows; correctness is
validated by (a) `actionlint` (existing CI lint gate in `release.yml`,
unaffected — a new composite action's YAML is linted the same as any other),
and (b) dogfooded live runs of the pipeline against its own issues
(constitution I). `quickstart.md` documents the manual/CI validation
scenarios that stand in for tests here, consistent with specs 014/016/017/018.

**Target Platform**: GitHub Actions (ubuntu-latest runners), consumed both
by this repo (dogfooded, local `./.wing-commander-pipeline/...` self-checkout
paths — the same cross-repo-resolution pattern `wing-commander-context` and
`wing-commander-preflight` already use) and by adopting repositories
(pinned `uses: owner/repo/.github/workflows/*.yml@ref`, and now also
`uses: owner/repo/.github/actions/wing-commander-callout@ref` inside each
reusable stage).

**Project Type**: Single project — reusable GitHub Actions workflow library
plus this repo's own thin wrapper workflows that dogfood it (constitution I,
VI). No frontend/backend split.

**Performance Goals**: N/A — no latency/throughput target; each new
composite-action invocation is one additional `gh issue comment` API call
per already-existing human-action moment (never a new moment invented by
this feature except the previously-missing finalize-PR-ready callout),
negligible relative to the agent steps already dominating each stage's
runtime.

**Constraints**: Must not change any trust boundary, checkout ref policy, or
token-minting flow (constitution V) — `wing-commander-callout` receives only
an already-minted token, a validated integer issue number, and
already-computed strings (PR URLs from `gh pr view`/`gh pr list`, agent-
authored text already framed as untrusted display data per existing
practice); it must post via `--body-file`, never shell-interpolate
agent-authored content into a `--body "$(...)"` string (research.md,
injection-safety decision). Must not remove or weaken any existing
label mutation, dedup marker (`rebase.yml`'s `<!-- wing-commander-rebase:
blocked ... -->`), or idempotency guard (`finalize.yml`'s "existing PR"
check) — the new action only adds a comment, callers keep their own
existing state changes unmodified. Must not migrate any comment site outside
`contracts/callout-points.md`'s ten rows (scope discipline, research.md).

**Scale/Scope**: 1 new composite action (`wing-commander-callout`); 10
migrated comment sites across 6 workflow files (`intake.yml`, `clarify.yml`,
`finalize.yml` ×4 sites, `implement.yml`, `rebase.yml`, `cleanup.yml`); 2
existing agent prompts trimmed (their `gh issue comment` instruction
replaced with "write to a temp file," mirroring `finalize.yml`'s existing
split); 0 new repository variables, 0 new labels. Full site-by-site mapping
is in `contracts/callout-points.md`; the action's interface is in
`contracts/callout-format.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied — this feature is itself spec 019 flowing through
  the pipeline's own stages, dogfooded against this repo's own lifecycle
  issue #93; the finalize-PR-review callout this plan adds is exactly the
  callout issue #93 itself will receive when this feature's own
  implementation PR opens.
- **II. Cost-Conscious Model Tiering**: Not implicated — no new agent step
  and no model-selection change. If anything this reduces agent-authored
  surface: two existing agent prompts (`intake.yml` step 7, `clarify.yml`
  step 6) lose their freeform "post a comment" instruction in favor of
  "write content to a file," with the posting decision moved to
  deterministic bash — same agent call, narrower agent responsibility, zero
  added cost.
- **III. Simple, GitHub-Native Interaction**: Directly reinforced — the
  chosen convention (GitHub's own `[!IMPORTANT]` alert rendering) is a
  native GitHub Markdown feature; no external dashboard, no custom UI, no
  new dependency. The lifecycle remains legible from the issue alone, and
  becomes *more* legible (SC-002) than before.
- **IV. Automation-First**: This feature *is* the automation-first
  principle's own enforcement mechanism catching up to itself — "any manual
  step that survives must be reported explicitly to the lifecycle issue,
  never silently assumed" is the constitution text `spec.md`'s User Story 1
  names as currently violated for the implementation-review gate; this plan
  closes that gap.
- **V. Security**: Satisfied — no change to trust boundaries, label gating,
  checkout refs, or token minting. The new composite action's only inputs
  are an already-minted token, an integer issue number, and strings each
  caller already computes today (PR URLs via `gh pr view`/`gh pr list`,
  agent-authored markdown already written to a file rather than executed).
  The `--body-file`-only contract (never shell-interpolated `--body`) is a
  hardening: it removes a latent injection surface that existed implicitly
  wherever a caller might otherwise have been tempted to inline agent text
  into a `--body "..."` string.
- **VI. Portability**: Satisfied — the new composite action lives under
  `.github/actions/` in this repo, self-checked-out via the existing
  `.wing-commander-pipeline` pattern every reusable stage already uses to
  reach shared composites cross-repo; nothing project-specific to this repo
  is introduced (the convention is generic to any adopter using the
  published stage workflows).

**Result**: PASS. No violations to record in Complexity Tracking.

*Post-Phase-1 re-check*: PASS, unchanged — Phase 1 design
(`data-model.md`, `contracts/callout-format.md`,
`contracts/callout-points.md`) introduces no new agent step, no new trust
boundary, and no default-visible-behavior regression for any comment site
outside the ten rows in scope; it only pins down the composite action's
interface and the exact call sites designed above.

## Project Structure

### Documentation (this feature)

```text
specs/019-next-step-callouts/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output (/speckit-plan command)
├── data-model.md                    # Phase 1 output (/speckit-plan command)
├── quickstart.md                    # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── callout-format.md            # Phase 1 output — wing-commander-callout interface contract
│   └── callout-points.md            # Phase 1 output — per-stage call-site migration contract
└── tasks.md                         # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   └── wing-commander-callout/
│       └── action.yml               # New — composite action implementing contracts/callout-format.md
├── workflows/
│   ├── intake.yml                   # Step 7 agent instruction narrowed to "write file"; + 2 deterministic wing-commander-callout steps (rows 1, 2)
│   ├── clarify.yml                  # Step 6 agent instruction narrowed to "write file"; + 2 deterministic wing-commander-callout steps (rows 3, 4)
│   ├── finalize.yml                 # + wing-commander-callout step after final-PR verification (row 5); remaining-manual-work step migrated (row 6); ⚠️/❌ sites migrated (rows 7a/7b)
│   ├── implement.yml                # "Report stalled on lifecycle issue" step migrated (row 8), runbook content unchanged
│   ├── rebase.yml                   # Blocked-escalation comment migrated (row 9), existing dedup marker preserved in body
│   ├── cleanup.yml                  # Draft-rejected comment migrated (row 10)
│   ├── plan.yml                     # Unchanged (research.md scope decision)
│   ├── tasks.yml                    # Unchanged
│   ├── watchdog.yml                 # Unchanged
│   └── release.yml                  # Unchanged — no new vars.* reads, no published-stage-invariant impact
docs/
└── architecture.md                  # Comment-convention note added: action-required (GitHub alert box) vs informational, pointing at contracts/callout-format.md as the source of truth
```

**Structure Decision**: Single project, no new top-level directories. The
only new file under `.github/` is the one composite action; every other
change is a targeted edit to an existing workflow file's already-identified
comment-posting step, per `contracts/callout-points.md`. (Per the pipeline
orchestrator's stated constraint for this plan stage, none of the files in
this section are edited now — this section documents the touch-set
`tasks.md`/implementation will act on; only files under
`specs/019-next-step-callouts/` are written by this plan.)

## Complexity Tracking

*No Constitution Check violations — table intentionally omitted.*
