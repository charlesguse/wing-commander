# Implementation Plan: Structured Clarification Questionnaires With a Single Content-and-Decision Artifact

**Branch**: `spec/032-structured-clarification-gate` | **Date**: 2026-08-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/032-structured-clarification-gate/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Today `intake.yml` and `clarify.yml` each produce a clarification
questionnaire through two independent mechanisms — an agent writes freeform
prose to a temp file, and a *separate* deterministic step greps `spec.md`
for the bare `[NEEDS CLARIFICATION` token to decide whether to post it — and
the two can disagree with no trace (#109: the grep never matched, the
authored questionnaire silently vanished; #159: the grep fired on a spec
whose subject matter names the marker token in prose, deleting the correct
"spec PR ready" callout via the branches' mutual exclusivity).

The approach adopts the schema-constrained-output-plus-deterministic-
read-back pattern this repository already uses twice (`watchdog.yml`'s
`diagnose` job; `auto-update-spec-kit.yml`'s reply-interpretation step,
`research.md` current-state findings): both agent steps gain a
`--json-schema` argument requiring a `clarifications` array (question +
optional context + optional answer options); clarify's schema also carries
an `answered` boolean to keep its `none` outcome (the agent's own early-STOP
comment path, untouched — FR-014) distinct from an empty `ready` array,
resolving FR-009 without relying on the artifact's absence, which the
`--json-schema` contract in this codebase never treats as a legitimate
outcome (`research.md`, FR-009 decision). A new deterministic `run:` step
after each agent step parses the same `claude-execution-output.json`
read-back both existing precedents already use, renders the unchanged
`## Question N` markdown from that structured array (not from agent prose),
and decides the callout branch from the array's emptiness alone — content
and decision now come from one artifact (FR-003). The marker grep is kept,
tightened to the colon form `[NEEDS CLARIFICATION:` (FR-008 — not
previously shipped, `research.md` current-state audit), demoted to a
cross-check that writes a `clarification-mismatch` step-summary warning on
disagreement without ever selecting the branch (FR-004–FR-006), and added to
`watchdog.yml`'s one-line sentinel alternation (FR-012) so a recurrence
surfaces as a finding. No fallback questionnaire is ever synthesized from
marker text (FR-007) — this is a negative requirement satisfied by omission,
not new code.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (`workflow_call` reusable
workflows) + POSIX `bash` steps + `jq` for structured-output parsing and
schema composition; no application language — this is CI/CD infrastructure,
matching every other spec in this repo.

**Primary Dependencies**: `anthropics/claude-code-action` (`--json-schema`
structured output — no new dependency, the CLI flag is already exercised
twice in this repo per `research.md`), `jq` (schema composition and
read-back parsing, already used identically by `watchdog.yml`'s
`class-vocab`/`diagnose-outcome` steps), `gh` CLI (unchanged — the callout
posting path is untouched), `wing-commander-callout`
(`.github/actions/wing-commander-callout/action.yml`, unchanged interface —
this feature only changes what writes the `body-file:` it already consumes).

**Storage**: N/A — no database, no new file. The rendered questionnaire
markdown is written to the same runner-temp paths already in use
(`${{ runner.temp }}/intake-clarification.md`,
`${{ runner.temp }}/clarify-followup.md`); no new field is added to
`spec-meta.json`.

**Testing**: This repo has no unit-test suite for workflows; correctness is
validated by (a) `actionlint` (existing CI lint gate in `release.yml`,
unaffected — no new composite action, only edits to existing step bodies),
and (b) dogfooded live runs of the pipeline against its own issues
(constitution I) — this feature's own lifecycle issue #111 will exercise
both intake and clarify's new read-back paths as it moves through the
pipeline. `quickstart.md` documents the manual/CI validation scenarios that
stand in for tests here, consistent with specs 014/016/017/018/019.

**Target Platform**: GitHub Actions (ubuntu-latest runners), consumed both
by this repo (dogfooded) and by adopting repositories via the pinned
`workflow_call` interfaces of `intake.yml`, `clarify.yml`, and `watchdog.yml`
— none of those interfaces (inputs/secrets/outputs) change; this feature is
entirely internal to each stage's own step sequence.

**Project Type**: Single project — reusable GitHub Actions workflow library
plus this repo's own thin wrapper workflows that dogfood it (constitution I,
VI). No frontend/backend split, no new composite action.

**Performance Goals**: N/A — no latency/throughput target. Each affected
agent step already runs one `anthropics/claude-code-action` invocation per
run; adding `--json-schema` does not add an API call (it constrains the
existing one's final turn), and the new read-back/render `run:` step is a
single-digit-millisecond `jq` pass over an artifact both existing
precedents already parse in full.

**Constraints**: Must not change any `workflow_call` input, secret, or
output name on `intake.yml`, `clarify.yml`, or `watchdog.yml` (constitution
VII — these are published-contract stages; this feature is entirely an
internal step-sequence change). Must preserve the exact reader-facing
`## Question N` block shape (`.claude/skills/speckit-specify/SKILL.md`,
FR-010) so a maintainer sees no difference in the posted callout. Must not
widen any agent step's `--allowedTools`/`--disallowedTools` (the schema
change is a CLI flag, not a new tool). Must not alter
`wing-commander-callout`'s interface or `clarify.yml`'s early-STOP
self-comment path (FR-014). The mismatch cross-check must never become the
deciding signal (FR-004) even when it disagrees with the structured output
(FR-006).

**Scale/Scope**: 3 files touched (`.github/workflows/intake.yml`,
`.github/workflows/clarify.yml`, `.github/workflows/watchdog.yml`); 2
agent-step prompts gain a `--json-schema` argument and lose their
"write freeform questionnaire prose to a file" instruction in favor of
"decide clarifications structurally"; 2 new deterministic
read-back-and-render `run:` steps (one per stage); 2 existing decision
steps rewritten from a single grep into structured-output-decides plus
grep-cross-check; 1 one-token sentinel-alternation edit in `watchdog.yml`.
0 new composite actions, 0 new labels, 0 new repository variables, 0 new
`workflow_call` inputs. Full schema/render contract in
`contracts/clarification-schema.md`; full per-stage call-site mapping in
`contracts/decision-points.md`; the sentinel addition in
`contracts/watchdog-sentinel.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied — this feature is itself spec 032 flowing through
  the pipeline's own stages, dogfooded against this repo's own lifecycle
  issue #111; the intake/clarify runs that advance issue #111 through its
  own remaining stages will exercise the exact read-back path this plan
  adds, and #109/#159 are this repository's own recorded incidents, not
  hypothetical ones.
- **II. Cost-Conscious Model Tiering**: Not implicated — no new agent step
  and no model-tier change. `intake.yml` and `clarify.yml` keep their
  existing `claude-opus-4-8` default (specification/clarification tier,
  unchanged by this feature); `--json-schema` constrains the existing
  step's output shape, it does not add a call. If anything, agent
  responsibility narrows (structural decision only; rendering moves to
  deterministic code), the same direction spec 019 already established for
  these two prompts.
- **III. Simple, GitHub-Native Interaction**: Reinforced — the reader-facing
  artifact (the `## Question N` callout on the lifecycle issue) is
  byte-shape-unchanged (FR-010); this is purely a reliability change to how
  that same artifact is produced, invisible to a maintainer on the happy
  path and strictly more informative (never silently wrong) on the
  disagreement path.
- **IV. Automation-First**: Directly served — a dropped questionnaire (#109)
  or a wrongly-suppressed "spec PR ready" callout (#159) are exactly the
  "manual step silently assumed" failure constitution IV forbids; this
  feature closes both by construction (FR-001–FR-004) rather than by
  tightening prompt wording, which spec 019's research already found
  insufficient to guarantee consistency for this repository's LLM-authored
  content.
- **V. Security**: Satisfied — no change to trust boundaries, checkout
  refs, token minting, or tool allowlists. The untrusted-content framing
  each prompt already applies to the issue/comment data it reads is
  unchanged; `--json-schema` constrains the agent's *output* shape, it does
  not change what data the agent treats as instructions vs. data.
- **VI. Portability**: Satisfied — no new file outside `.github/workflows/`
  of the three in-scope stages; no project-specific state introduced. The
  schema strings are composed inline by each `run:` step (matching
  `class-vocab`'s precedent), not read from a repository-specific config
  file.
- **VII. Two Interfaces**: Satisfied — `intake.yml`, `clarify.yml`, and
  `watchdog.yml` are all published-contract stage workflows; this plan adds
  no new `workflow_call` input/secret/output and reads no new ambient
  `github.event.*`/`vars.*` state. Every changed step already lived inside
  the stage (the agent step, the decision step); nothing moves from stage
  to wrapper or vice versa, so no deviation registration is needed.

**Result**: PASS. No violations to record in Complexity Tracking.

*Post-Phase-1 re-check*: PASS, unchanged — Phase 1 design
(`data-model.md`, `contracts/clarification-schema.md`,
`contracts/decision-points.md`, `contracts/watchdog-sentinel.md`)
introduces no new agent step, no new trust boundary, no `workflow_call`
interface change, and no default-visible-behavior regression on the happy
path; it only pins down the schema shapes, the read-back/render algorithm,
and the exact call sites the Summary above already commits to.

## Project Structure

### Documentation (this feature)

```text
specs/032-structured-clarification-gate/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output (/speckit-plan command)
├── data-model.md                    # Phase 1 output (/speckit-plan command)
├── quickstart.md                    # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── clarification-schema.md      # Phase 1 output — JSON Schema shapes + render algorithm
│   ├── decision-points.md           # Phase 1 output — per-stage call-site migration contract
│   └── watchdog-sentinel.md         # Phase 1 output — sentinel-set addition contract
└── tasks.md                         # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── intake.yml     # Step 7 agent instruction gains --json-schema (clarifications array);
    │                   # "Check whether the spec still needs clarification" step rewritten:
    │                   # structured-output-decides + colon-form cross-check + mismatch warning;
    │                   # new deterministic render step feeds the unchanged body-file: callout
    ├── clarify.yml     # Step 6 agent instruction gains --json-schema (answered + clarifications);
    │                   # "Determine clarification follow-up outcome" step rewritten: answered
    │                   # discriminator → none, else structured-output-decides + cross-check;
    │                   # new deterministic render step feeds the unchanged body-file: callouts
    └── watchdog.yml    # One-token edit: sentinels alternation (line ~618) gains
                        # "|clarification-mismatch"
```

No new directory, no new composite action, no `tests/` tree — this repo
validates workflow changes via `actionlint` and dogfooded live runs
(Technical Context, Testing), matching every prior spec touching
`.github/workflows/`.

**Structure Decision**: Single project, no new top-level directories, no new
files under `.github/`. Every change is a targeted edit inside one of the
three files above, at the exact steps enumerated in
`contracts/decision-points.md`. (Per the pipeline orchestrator's stated
constraint for this plan stage, none of the files in this section are
edited now — this section documents the touch-set `tasks.md`/implementation
will act on; only files under `specs/032-structured-clarification-gate/`
are written by this plan.)

## Complexity Tracking

*No Constitution Check violations — table intentionally omitted.*
