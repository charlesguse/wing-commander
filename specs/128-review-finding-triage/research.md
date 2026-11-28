# Research: Review finding triage (spec 128)

No `[NEEDS CLARIFICATION]` markers remained in spec.md. The decisions below
resolve the build-level choices the spec leaves to the plan.

## D1 — One routing module, two call sites

- **Decision**: a new `.github/scripts/wc_finding_triage.py` is the single
  home of the record / drop / reject / fix-now rule and of the rendering of
  the dropped-and-rejected list. `lifecycle-review-gate.yml` (review and
  disposition jobs) and `wing-commander-stage-findings/action.yml` (prepare
  step) import it; neither carries its own copy of the rule.
- **Rationale**: FR-008 / SC-005 require identical outcomes on both paths;
  CLAUDE.md "Shared logic has exactly one home". The gate already imports
  trusted helpers from the pristine checkout (`wc_convergence`,
  `wc_review_finding_fingerprint`); the composite already loads
  `verify-stage-finding-schema.py` by `GITHUB_ACTION_PATH`. Both idioms
  reuse as-is.
- **Alternatives**: duplicating the rule in each call site (rejected: the
  exact drift CLAUDE.md warns of); a composite action (rejected: it is pure
  Python with no `gh`, so a script module with unit fixtures is simpler and
  matches `wc_convergence`).

## D2 — Field names and schemas

- **Decision**: add four fields to a finding: `failure_class`
  (`silent|loud|none`), `silent_description` (one line string),
  `severity` (`important|nit|pre_existing`), `security` (boolean). All four
  are *optional* in both JSON schemas (`board-review-finding.schema.json`,
  `stage-finding.schema.json`); the routing module, not the schema,
  enforces "silent needs a description" and "absent class means record".
- **Rationale**: FR-009 says an absent or unreadable class must be recorded,
  never discarded as malformed — a schema `required` would drop it. Optional
  fields keep the published `wing-commander-stage-findings` inputs/outputs
  unchanged (Principle VII), so this is not a contract break. The board
  loop's reviewer shares `board-review-finding.schema.json`; optional fields
  leave it validating exactly as today, and its routing is untouched.
- **Unreadable value** (e.g. `failure_class: "maybe"`): the validators must
  accept any value for it so the finding survives to the router, which
  treats an unrecognised value as absent (record). `silent_description`
  must be a one-line string when present; a multi-line value is
  treated as absent.

## D3 — Severity and security override

- **Decision**: `wc_finding_triage.route()` never returns `drop` when
  `severity == "important"` or `security is True`. Such an out-of-scope
  finding is recorded; if it is also `silent` with no description it is
  *rejected* (FR-009), still not dropped. Absent `severity`/`security` mean
  nit / false.
- **Rationale**: FR-007, FR-010, SC-003. A rejection is not a drop.

## D4 — Where the lifecycle gate triages

- **Decision**: triage runs in two places on the gate, both calling D1:
  1. The review job's *extract* step annotates each kept finding with its
     `triage` outcome and reason, and writes the annotated list to the
     existing `lifecycle-review-findings.json` artifact. "Compose the review
     body" renders a "Dropped and rejected" section from those annotations
     (routing code renders it; the agent writes none of it — FR-011) and
     labels each finding's scope line accordingly instead of the hard-coded
     "out-of-scope (filed as its own issue)".
  2. The disposition job's *partition* step filters
     `out_of_scope_survivors` to outcome `record` **before** the existing
     `[:3]` cap, so dropped findings do not consume cap slots (spec
     Assumptions). In-scope findings keep today's path regardless of class.
- **Rationale**: the PR review comment is posted by the review job before
  disposition runs, so the report must be rendered there; the round record
  it carries is what a later pass reads to recognise an already-dropped
  finding (edge case "rediscovers a finding"). Disposition re-derives the
  outcome from the same module rather than trusting the artifact's
  annotation, so a tampered artifact cannot widen what is filed (IX).
- **Alternatives**: triage only in disposition (rejected: the PR comment
  would not list drops); triage only in review and pass the outcome through
  the artifact (rejected: trusts an artifact).

## D5 — Where the stage-findings composite triages

- **Decision**: in `prepare`, after validation, spec-errata and in-flight
  filtering and before the cap, each remaining survivor is routed by D1.
  Only `record` survivors continue to the cap and to the three report slots.
  Dropped and rejected ones are added to `state.json` as
  `triaged_out: [{title, outcome, reason}]` and rendered by the same module
  in the "Emit summary" step; a rejected finding also emits
  `::warning::` (static text; the title never goes into the annotation,
  FR-026). The recorded issue body gains a "## How it fails silently"
  section. `finding-kind: routed-task` skips triage: it is assigned work, not
  a defect proposal, and spec 090 FR-007 files each one.
- **Rationale**: matches the composite's existing order and its
  always-exit-0 rule (FR-022 of spec 056); the in-flight route is already
  "fix in this PR", the analogue of fix now.

## D6 — Report wording

- **Decision**: drop reasons are exactly `fails loudly` and
  `no output change`; the rejection reason is exactly
  `silent, no description` (FR-006, FR-009). Each line renders the finding's
  title as a code span with backticks removed (same sanitising as
  `code_span` in the composite), because titles are agent-authored data.
- **Rationale**: literal strings are what the PR-time gate compares.

## D7 — The PR-time gate (FR-011)

- **Decision**: a new `.github/scripts/verify-finding-triage-report.py`,
  registered in the gate registry and wired into `lint-workflows.yml`
  (so `run-local-gates.py` picks it up). It (a) runs a checked-in fixture
  corpus through `wc_finding_triage` and fails if any drop or reject is
  absent from the rendered list or lacks its reason; (b) fails if any
  important/security finding in the corpus is dropped; (c) fails if the
  gate workflow or the composite does not import the module, or reimplements
  the rule (single-home check, per CLAUDE.md); (d) asserts the two call
  sites agree on a shared corpus (SC-005) by driving both entry points.
  Every failure branch ships a fixture (Principle VIII).
- **Rationale**: a gate that runs on every PR and checks the *renderer's*
  own output against its own outcomes is the closest a deterministic check
  gets to "cannot omit a dropped finding".

## D8 — Reviewer prompt

- **Decision**: the gate reviewer's prompt (the fenced
  `wing-commander-review-findings` template near the `in_scope` instruction)
  and the stage prompts' `wing-commander-findings` instruction gain the four
  fields. This is a proposal vocabulary only; routing stays in code (IX).
  Stage prompts are edited in the workflow files, which is implement-stage
  work, not this plan's.

## D9 — Backlog sweep (FR-012)

- **Decision**: not built. After the final PR merges, a session sweeps #889
  through `python .github/scripts/board_backlog_edit.py` and posts one
  comment. The plan adds nothing for it beyond the task list noting it as a
  post-merge, owner-session action. The implement stage must not touch #889.

## D10 — Docs and contracts (FR-014)

- **Decision**: update the live contract
  `specs/062-lifecycle-review-gate/contracts/review-and-findings.md` and
  `specs/056-stage-found-defect-filing/contracts/wing-commander-stage-findings.md`
  (contracts stay live per CLAUDE.md) and `docs/reference.md` where it lists
  the findings cap and filing defaults. New contract for the shared module is
  in this spec's `contracts/finding-triage.md`.
