# Implementation Plan: Routed-Original Disposition

**Branch**: `spec/108-routed-original-disposition` | **Date**: 2026-09-29 | **Spec**: [specs/108-routed-original-disposition/spec.md](./spec.md)

**Input**: Feature specification from `specs/108-routed-original-disposition/spec.md`

## Summary

Today, when the board loop routes an open issue to the spec pipeline, it
files a new `spec-request` issue and leaves the originating issue open
with `board:stalled` plus a comment — one routed request, two open issues.
This feature makes the loop close the originating issue as a duplicate of
the spec-request (REST `state_reason: duplicate`) at the moment the
spec-request is filed, at all three sites that file one (route's spec
verdict, fix's post-push backstop breach, readiness's backstop breach),
through one new shared, idempotent disposition operation
(`contracts/duplicate-disposition.md`) rather than three inline copies.
Re-admission becomes "a maintainer reopens the originating issue," which
needs one new carve-out in `board_eligibility.is_excluded()`
(`contracts/eligibility-and-readmission-delta.md`) keyed off the linked
spec-request's live state — closed re-admits, still-open does not — so
"at most once per reopen" falls out of the existing newest-marker-wins
property with no new counter. FR-004's two-way cross-link reuses the
existing `wing-commander-outstanding-task-item` composite a second time
rather than inventing a second link format. Gate 93 check 3 — which
already enumerates the three spec-request sites for the create side — is
extended, not duplicated, to also require the disposition call at each
site (`contracts/gate-93-check-3-delta.md`). A new `select`-job scan step
posts an idempotent notice on both issues when a spec-request this loop
filed closes without its `spec-meta.json` ever reaching the finalize
stage's terminal state (`contracts/closed-without-landing-notice.md`).
Nothing here widens the published stage-workflow contract (Principle
VII) — `board-loop.yml` carries no `workflow_call` trigger and every
change stays inside this repository's own consuming instrument.

## Technical Context

**Language/Version**: Python 3.11 (`.github/scripts/*.py`, this
repository's existing convention), Bash (workflow/composite `run:`
steps), YAML (`board-loop.yml`, new/edited contracts).

**Primary Dependencies**: GitHub CLI (`gh`), `jq`, PyYAML (already used by
`verify-issue-context-single-home.py`). No new third-party dependency.

**Storage**: None beyond GitHub Issues/PRs/labels/comments, already the
board loop's entire durable state (spec 057 data-model.md), plus a
read-only lookup of `specs/<NNN-slug>/spec-meta.json`'s `stage` field for
the FR-017 notice (research.md D8) — this feature never writes
`spec-meta.json`.

**Testing**: This repository's checked-in fixture / `--self-test`
convention (no pytest) for every gate/decision script, run via
`python .github/scripts/run-local-gates.py`; `quickstart.md`'s live drills
for the scenarios that need a real dispatched run (stop-request
mid-breach, reopen-and-reroute).

**Target Platform**: GitHub Actions (`ubuntu-latest`), `board-loop.yml`'s
existing `schedule`/`workflow_dispatch`/`pull_request` triggers — no new
trigger added.

**Project Type**: Reusable GitHub Actions pipeline (single project; no
frontend/backend split).

**Performance Goals**: N/A — hourly-cron and event-driven, not
latency-sensitive. No new agent/LLM invocation (the disposition, the
carve-out, and the notice are all deterministic code, Principle IX), so no
new model-tier decision applies.

**Constraints**: Touches only `board-loop.yml`, its composites/scripts,
and this repository's own docs/contracts — never a `workflow_call`-only
stage under `.github/workflows/<stage>.yml` (Principle VII; spec.md's own
Assumptions section states this explicitly). The disposition MUST NOT run
before the existing create-guard (#514) has confirmed the spec-request
exists (FR-011, unchanged). No new label-config mechanism
(`.github/labels.yml`) — `disposition:duplicate` is documented manually in
`docs/setup.md` exactly as `board:stalled` already is.

**Scale/Scope**: Three call sites edited in one workflow file
(`board-loop.yml`); one new shared Python module (the disposition
operation) plus its `--self-test` fixtures; one extension to
`board_eligibility.py`/`verify-board-eligibility.py`; one extension to
`verify-issue-context-single-home.py`'s Gate 93 check 3 (no new gate
script, no registry-file edit — FR-012/FR-013); one new `select`-job step
for the FR-017 notice; one new label (`disposition:duplicate`); doc/
contract updates to `docs/setup.md` and two of
`specs/057-autonomous-board-loop/contracts/*.md` (FR-014 — those remain
live per CLAUDE.md since Gate 93/`verify-board-eligibility.py` read the
behaviour they describe).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide — repo is its own first example**: Built through the pipeline
  itself (issue #791 → this spec → this plan → tasks → implement). PASS.
- **II. Cost-Conscious Model Tiering**: This feature adds no new agent
  invocation of any kind — the disposition, the eligibility carve-out, and
  the closure-notice scan are all deterministic code (Principle IX), so no
  model-tier decision is introduced or changed. PASS.
- **III. Simple, GitHub-Native Interaction**: Every outcome (a close, a
  label, a comment, a reciprocal link) lands on the originating issue or
  the spec-request itself — a maintainer reads either issue and reaches
  the other in one click (SC-004). PASS.
- **IV. Automation-First**: The disposition, both cross-links, the gate
  extension, and the closure notice are all automated; the one surviving
  manual step — a maintainer reopening a disposed issue to reconsider it —
  is explicitly reported via the FR-017 notice and FR-014's documentation
  update, never silently assumed. PASS.
- **V. Security — Untrusted Content Is Never Instructions**: The
  disposition's reason text and the closure notice are deterministic
  template strings built from issue/spec-request numbers and URLs, never
  from an issue or comment body; no new agent step is added, so no new
  untrusted-content boundary is created. The disposition reuses the
  existing App token's `issues: write` scope, already exercised by `gh
  issue close`/`edit` calls elsewhere in `board-loop.yml` (e.g. `prove`).
  PASS.
- **VI. Portability**: Every new/edited artifact lives under this
  repository's own `.github/{workflows,actions,scripts}`, `docs/`, and
  `specs/` — nothing is bundled with or resolved from Wing Commander
  itself, and no repository name/owner is hardcoded (unchanged from
  today's sites, which already parameterize on `GITHUB_REPOSITORY`). PASS.
- **VII. Two Interfaces**: `board-loop.yml` carries no `workflow_call`
  trigger before or after this feature — it is not part of the published
  surface, and this feature does not touch any file under
  `.github/workflows/<stage>.yml`'s published contract. PASS.
- **VIII. A Green Check Means What It Says**: Gate 93 check 3's extension
  is itself in service of this principle — FR-012 requires it to fail
  loudly rather than pass vacuously on zero sites (already true of the
  base check, confirmed not changed) and to ship a checked-in fixture per
  failure branch (`contracts/gate-93-check-3-delta.md`'s fixture list).
  `run-local-gates.py` picks up the extended check automatically, with no
  registry edit, so the same subject runs the same way locally and in CI
  (FR-013). PASS.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The disposition decision (idempotency pre-check, close-as-
  duplicate, label, comment, reciprocal link), the re-admission carve-out,
  and the closed-without-landing detection are all deterministic code
  reading live GitHub/`spec-meta.json` state — no agent judgment decides
  any of them (research.md D3/D6/D8). PASS.
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: This feature
  changes only what the route/fix/readiness steps' existing, already-
  autonomous spec-request filing does to the originating issue afterward —
  it introduces no new bot-merge class, no new autonomous scope, and the
  change itself was routed as `spec-request` (this very pipeline run)
  because Q1 required a maintainer trade-off among three dispositions,
  exactly the shape Principle X reserves for the spec pipeline rather than
  a fix PR. PASS.

No violations. **Complexity Tracking is intentionally empty**: one new
shared module (the disposition operation) replacing three inline
close/label/comment sequences is CLAUDE.md's single-home rule applied
once, not new complexity; the eligibility carve-out is one new branch in
an existing, already-tested function; the gate extension is additive to
an existing check, per FR-012's own instruction not to stand up a second
gate.

## Project Structure

### Documentation (this feature)

```text
specs/108-routed-original-disposition/
├── plan.md                 # This file
├── research.md             # Phase 0 output — D0-D8 decisions
├── data-model.md           # Phase 1 output — entities and marker/label shapes
├── contracts/              # Phase 1 output
│   ├── duplicate-disposition.md
│   ├── eligibility-and-readmission-delta.md
│   ├── gate-93-check-3-delta.md
│   └── closed-without-landing-notice.md
├── quickstart.md            # Phase 1 output — validation drills
├── checklists/               # from intake, unchanged by this stage
└── spec-meta.json
```

### Source Code (repository root)

This is a GitHub Actions pipeline repository; "source" is workflows,
composite actions, and gate/decision scripts — no `src/`/`tests/` split.

```text
.github/
├── scripts/
│   ├── board_duplicate_disposition.py            # NEW — contracts/duplicate-disposition.md (FR-001/003/004/009/010/011/015)
│   ├── verify-board-duplicate-disposition.py       # NEW gate (fixtures: contract's failure-semantics table)
│   ├── board_eligibility.py                        # EDITED — is_excluded() carve-out, TERMINAL_STEPS (FR-005/006/007)
│   ├── verify-board-eligibility.py                  # EDITED — 3 new fixture pairs (contracts/eligibility-and-readmission-delta.md)
│   ├── board_item_marker.py                         # EDITED — write_marker() gains spec_request; "duplicate" step
│   ├── verify-issue-context-single-home.py           # EDITED — Gate 93 check 3 extension, no new dispatcher entry (FR-012/013)
│   └── board_closed_without_landing.py               # NEW — contracts/closed-without-landing-notice.md (FR-017)
├── actions/
│   └── wing-commander-outstanding-task-item/         # UNCHANGED — reused a second time per site (research.md D5)
└── workflows/
    ├── board-loop.yml         # EDITED — 3 sites call the disposition module; select job gains the FR-017 scan step
    └── lint-workflows.yml     # EDITED — Gate 93's existing invocation lines cover the extended check; no new gate line needed unless verify-board-duplicate-disposition.py ships as its own registered check

docs/
└── setup.md                # EDITED — `disposition:duplicate` row added; `board:stalled` row's re-admission column updated (FR-014)

specs/057-autonomous-board-loop/contracts/
├── eligibility-and-selection.md    # EDITED — re-admission text updated per FR-014 (live contract, CLAUDE.md)
└── labels-and-cross-links.md       # EDITED — cross-link table gains the reciprocal spec-request row; board:stalled row's re-admission column updated
```

**Structure Decision**: No new top-level directory. The disposition
operation becomes its own script/gate pair (`board_duplicate_disposition.py`
+ `verify-board-duplicate-disposition.py`) rather than folding into
`board_eligibility.py` or `board_item_marker.py`, because it owns a
distinct responsibility (a durable write sequence with its own
idempotency contract) from either — `board_eligibility.py` stays a pure
read-only decision module (its existing shape, per spec 057's own
Constitution Check) and `board_item_marker.py` stays a marker read/write
primitive with no GitHub side effects beyond the marker comment itself;
mixing the close/label/reason-comment/reciprocal-link sequence into either
would blur that boundary for no benefit. Whether the new script also needs
a fourth `verify-*.py` gate of its own, or whether its checks fold into
Gate 93 check 3's existing extension, is a tasks.md-level call — this plan
fixes the contract (`contracts/duplicate-disposition.md`'s sequence and
failure table) and leaves that packaging decision to tasks, which is where
`.github/scripts/gate-registry`-equivalent wiring already gets decided in
this repository's convention (see spec 057's own plan.md, which likewise
deferred a script/gate naming split it later finalized in tasks.md).
