# Implementation Plan: Stage-Found Defect Filing Through a Deterministic Filing Step

**Branch**: `spec/056-stage-found-defect-filing` | **Date**: 2026-09-20 | **Spec**: [specs/056-stage-found-defect-filing/spec.md](./spec.md)

**Input**: Feature specification from `specs/056-stage-found-defect-filing/spec.md`

## Summary

Every agent stage in the pipeline meets defects outside its own task and
today discards that knowledge at the end of the run. This feature gives
each of the six published stage workflows (`intake`, `clarify`, `plan`,
`tasks`, `implement`⟲converge, `finalize`) one authoritative findings
channel per Constitution Principle IX's discipline — the agent proposes a
structured finding in its existing final message or structured result, and
never files anything itself — and one new post-agent, failure-tolerant
composite action, `wing-commander-stage-findings`, that validates each
proposal against a checked-in schema, computes a fingerprint from
deterministic fields only, dedups and cross-links through an extended and
promoted `durable-failure-issue` composite, caps findings per run, labels
and cross-links to the lifecycle issue, and never affects the stage's own
outcome. Filing ships to all six stages behind a declared `enabled` input
(default on for `implement`/`finalize`, off elsewhere), so the published
surface widens exactly once regardless of which stages a given release
activates.

## Technical Context

**Language/Version**: Bash (workflow/composite steps), Python 3 (gate
scripts and schema validation, matching `.github/scripts/`'s existing
convention), YAML (GitHub Actions workflows/composites), JSON Schema
(draft 2020-12) for the one new checked-in schema.

**Primary Dependencies**: `anthropics/claude-code-action@v1` (unchanged —
no new tool grants), `gh` CLI (issue/label operations, the pipeline's
existing GitHub App token), no new third-party package (research.md D5).

**Storage**: None beyond GitHub Issues (the filed findings) and the
existing `claude-execution-output.json` transcript artifact each stage
already produces.

**Testing**: Composite-level fixtures under
`.github/actions/wing-commander-stage-findings/tests/` (bash harness, no
live network — an injectable `gh` shim covers dedup/API-failure branches),
plus two new/extended gate scripts wired into `lint-workflows.yml` /
`run-local-gates.py`, plus the manual quickstart drills for the
end-to-end and untrusted-content stories that need a real dispatched run.

**Target Platform**: GitHub Actions (`ubuntu`-class runners, the pipeline's
existing self-checkout composite-action model).

**Project Type**: Reusable GitHub Actions pipeline (single project; no
frontend/backend split).

**Performance Goals**: Negligible added wall-clock on the common
zero-findings path (SC-013) — the new step is a single composite
invocation per stage run, no additional agent turns, no polling.

**Constraints**: The filing step MUST NOT be able to fail the stage
(FR-022); MUST run after the stage's existing deterministic read-back
(FR-023); MUST distinguish cancellation from an upstream agent failure
(FR-024); MUST use the pipeline's existing GitHub App identity with no
widened write surface beyond issue-create/comment/label in the consuming
repository (FR-028).

**Scale/Scope**: Six stage workflows instrumented identically; one new
checked-in schema; one new published composite
(`wing-commander-stage-findings`); one existing internal composite
promoted and extended (`durable-failure-issue` →
`wing-commander-durable-failure-issue`); one new small published composite
extracted for reuse (`wing-commander-outstanding-task-item`); two gate
scripts (one new, one extended); per-run cap of 3 findings (default,
adopter-configurable).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide**: This feature is built as an ordinary spec/plan/tasks/
  implement/finalize cycle through the pipeline itself. PASS.
- **II. Cost-Conscious Model Tiering**: No new model invocation is
  introduced — the filing step is entirely deterministic code with zero
  LLM calls; the one paragraph added to each stage's existing prompt adds
  no new agent turn. PASS.
- **III. Simple, GitHub-Native Interaction**: Filings and their cross-links
  land as ordinary issues and an ordinary lifecycle-issue checklist line,
  legible without a dashboard (FR-017–FR-021, SC-008). PASS.
- **IV. Automation-First**: The mechanism is fully automated; a filing
  failure is reported, never left for a human to notice by absence.
  PASS.
- **V. Security — Untrusted Content Is Never Instructions**: Findings that
  quote agent-read content are filed as framed, quoted data (FR-026); any
  downstream reader (documented for #408) treats a `found-by:*` body as
  data (FR-027); filing uses the pipeline's existing GitHub App identity,
  no PAT, no widened credential (FR-028, research.md's reuse of the
  existing token wiring). PASS.
- **VI. Portability**: All new artifacts (`.github/schemas/`,
  `.github/actions/wing-commander-*`, `.github/scripts/verify-*`) live in
  the consuming repository's own checkout, resolved the same
  self-checkout way every other published composite already is. PASS.
- **VII. Two Interfaces**: The published `workflow_call` surface widens by
  exactly three declared inputs per stage (data-model.md's "Stage Filing
  Configuration"), and one internal composite is deliberately promoted
  (`durable-failure-issue` → `wing-commander-durable-failure-issue`) — both
  are the kind of deliberate act this principle requires rather than an
  accidental surface change, and FR-029 already names this a MINOR release
  change. PASS, with the promotion and widening tracked as the deliberate
  acts research.md D8/D12 document.
- **VIII. A Green Check Means What It Says**: Both new/extended gates are
  registered through the existing gate registry so `run-local-gates.py`
  derives their arguments automatically, are triggered by changes to the
  stage workflows/composites they check, fail loudly if they can't reach
  their subject, and ship a checked-in fixture per failure branch
  (FR-030, `contracts/gates.md`). PASS.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: This is the feature's organizing principle — the agent proposes
  a finding; validation, fingerprinting, dedup, capping, filing, and
  cross-linking are all deterministic code (`wing-commander-stage-findings`,
  `wing-commander-durable-failure-issue`). PASS.
- **X. Bounded Autonomy**: Not directly exercised by this feature (it ships
  no autonomous merge), but it is the feed X's board loop (#408) will read
  from later; this feature adds no dependency on X and changes nothing X
  already governs. PASS (not applicable beyond feeding #408, per spec's
  own "No constitution dependency" framing).

No violations. **Complexity Tracking is intentionally empty** — the spread
across two composites, one schema file, and two gates is the direct
consequence of FR-016/FR-032's single-home rule (reusing and extending one
existing idiom, and factoring out a second one already duplicated once,
rather than writing either inline a sixth or seventh time), not
incidental complexity.

## Project Structure

### Documentation (this feature)

```text
specs/056-stage-found-defect-filing/
├── plan.md              # This file
├── research.md          # Phase 0 output — 14 recorded decisions
├── data-model.md         # Phase 1 output — entities and configuration shape
├── contracts/            # Phase 1 output
│   ├── stage-finding-schema.md
│   ├── wing-commander-durable-failure-issue.md
│   ├── wing-commander-outstanding-task-item.md
│   ├── wing-commander-stage-findings.md
│   ├── stage-wiring.md
│   └── gates.md
├── quickstart.md         # Phase 1 output — validation drills
├── checklists/requirements.md   # from intake, unchanged by this stage
└── spec-meta.json
```

### Source Code (repository root)

This is a GitHub Actions pipeline repository, not an application; "source"
is workflows, composite actions, and gate scripts. No frontend/backend
split applies.

```text
.github/
├── schemas/
│   └── stage-finding.schema.json                  # NEW (contracts/stage-finding-schema.md)
├── scripts/
│   ├── verify-stage-finding-schema.py             # NEW
│   ├── verify-stage-findings-wiring.py            # NEW
│   └── verify-single-home-idioms.py               # EXTENDED (DECLARED_HOMES entries + repointed failure-issue path)
├── actions/
│   ├── wing-commander-durable-failure-issue/       # RENAMED+EXTENDED from _shared/durable-failure-issue/
│   ├── wing-commander-outstanding-task-item/       # NEW, extracted from pr-conversation.yml
│   └── wing-commander-stage-findings/              # NEW
│       └── tests/                                  # NEW fixtures (FR-030)
└── workflows/
    ├── intake.yml            # EDITED: +3 inputs, +findings property on json-schema, +paragraph, +filing step
    ├── clarify.yml           # EDITED: same shape
    ├── plan.yml               # EDITED: +3 inputs, +fenced-block paragraph (both agent steps), +filing step
    ├── tasks.yml               # EDITED: same shape
    ├── implement.yml           # EDITED: same shape (single attribution surface, research.md D1)
    ├── finalize.yml            # EDITED: same shape
    ├── auto-release.yml        # EDITED: repoint 3 durable-failure-issue call sites
    ├── auto-update-spec-kit.yml # EDITED: repoint 1 durable-failure-issue call site
    ├── pr-conversation.yml     # EDITED: outstanding-task-item step replaced by composite call
    ├── lint-workflows.yml      # EDITED: register the new/extended gates
    ├── wing-commander-1-intake.yml    # EDITED: pass through 3 new inputs
    ├── wing-commander-2-clarify.yml   # EDITED: same
    ├── wing-commander-3-plan.yml      # EDITED: same
    ├── wing-commander-4-tasks.yml     # EDITED: same
    ├── wing-commander-5-implement.yml # EDITED: same
    └── wing-commander-6-finalize.yml  # EDITED: same

docs/
└── adoption.md            # EDITED (FR-033): document the label, per-stage
                            # defaults, and the enable/disable input
```

**Structure Decision**: This feature touches no application source tree —
every artifact is a workflow, a composite action, a gate script, or a
schema/doc file, following the repository's existing
`.github/{workflows,actions,scripts}` + `docs/` layout exactly. No new
top-level directory is introduced except `.github/schemas/` (research.md
D4), whose scope is deliberately narrower than `specs/`-per-feature (it is
permanent, cross-spec infrastructure) and narrower than `.github/actions/`
(it is data, not an executable step).

## Complexity Tracking

*No violations to justify — table intentionally empty (see Constitution Check).*
