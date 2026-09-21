# Implementation Plan: The Board Loop — A Scheduled Run Takes One Open Issue From Triage To Proven

**Branch**: `spec/057-autonomous-board-loop` | **Date**: 2026-09-21 | **Spec**: [specs/057-autonomous-board-loop/spec.md](./spec.md)

**Input**: Feature specification from `specs/057-autonomous-board-loop/spec.md`

## Summary

One new, repository-only workflow (`board-loop.yml`, no `workflow_call`
trigger, in the `auto-release.yml` shape per FR-062) takes exactly one open
issue per scheduled/dispatched run through five of the six board steps —
triage, route, fix, review, and (via a `pull_request: closed` resume)
prove — and hands the sixth, merge, to a human. Every durable action (a
close, a route, a push, a readiness claim) is decided by deterministic
code that re-derives its own evidence from GitHub state or a cited run's
execution-output record; an agent may only propose. Four things this
feature reuses rather than re-implements: the rate-limit verdict
(`wing-commander-agent-verdict`, spec 047) for triage's first close
ground; the durable-failure-issue composite's fingerprint/dedup discipline
(spec 056) for out-of-scope review findings; the credential-refresh
pattern (spec 052) across a fix→review cycle that can outlive one App
token; and the correlated-dispatch-and-poll idiom `auto-release.yml`
already has inline, promoted to a shared composite so the prove step does
not paste a second copy. Two things have no prior art and are new
deterministic code this feature introduces: the upstream-action-bump
triage ground, and the check-green-on-exact-head-SHA readiness logic
(FR-036/FR-037). The route backstop reuses `pr-conversation.yml`'s
size-and-path idiom by extracting its inline `jq` logic to a shared
composite parameterized by threshold, rather than pasting the board's own
(larger) thresholds inline a second time.

## Technical Context

**Language/Version**: Bash (workflow/composite `run:` steps, the existing
convention), Python 3 (new gate/decision scripts under `.github/scripts/`,
matching the repository's existing `verify-*.py` convention), YAML (the
new workflow and composites), JSON Schema (draft 2020-12) for the one new
review-finding schema.

**Primary Dependencies**: `anthropics/claude-code-action@v1` (existing, no
new tool grants — FR-057 forbids web tools on every invocation this
feature adds), `gh` CLI under the existing wing-commander-bot GitHub App
token (`wing-commander-context`, spec 052), `git`, no new third-party
package.

**Storage**: None beyond GitHub Issues/PRs (the board item's durable state
lives entirely in issue labels, an HTML-comment marker in the loop's own
latest status comment, and the fix branch/PR themselves — data-model.md
"Board Item Marker") and the existing `claude-execution-output.json`
transcript/metrics-record mechanism every agent step already produces.

**Testing**: New decision scripts under `.github/scripts/` each carry an
embedded self-test mode exercised against checked-in fixtures (the
existing `verify-post-agent-credential-refresh.py` / stage-finding-schema
convention: one script, two invocations — real GitHub data at runtime,
checked-in fixtures at PR time), registered in `lint-workflows.yml` so
`run-local-gates.py` picks them up automatically (FR-065); a bash
`tests/run-tests.sh` harness beside each new composite (the
`wing-commander-stage-findings/tests/` convention) for composite-level
fixtures; the manual `quickstart.md` drills for the two stories (fix→PR,
prove) that need a real dispatched run.

**Target Platform**: GitHub Actions (`ubuntu`-class runners), this
repository's own self-checkout composite-action model.

**Project Type**: Reusable GitHub Actions pipeline (single project; no
frontend/backend split).

**Performance Goals**: The overwhelmingly common case — no eligible issue
— MUST be a single cheap read with zero agent invocations (SC-009); the
loop's own cost is otherwise bounded by its round budget and per-step turn
ceilings (FR-050), reported through the existing metrics-summary
mechanism (FR-047) like every other stage.

**Constraints**: Exactly one item in flight repository-wide under a single
concurrency group (FR-048); the loop MUST decline to start while an
implement cycle is in flight (FR-049); the kill switch MUST be checked
before every durable action, including between rounds (FR-051); no agent
invocation may carry web tools (FR-057); the workflow MUST NOT merge,
approve, or enable auto-merge on any PR (FR-068); nothing the loop writes
may name a downstream consumer of this repository (FR-058).

**Scale/Scope**: One new repository-only workflow; two new promoted/shared
composites (`wing-commander-size-path-backstop`,
`wing-commander-dispatch-and-wait`); one new review-finding schema and its
hand-written validator; five new decision scripts, each doubling as a gate
via a checked-in fixture set (eligibility, triage, route backstop,
readiness, review-finding schema); one extension to
`verify-single-home-idioms.py`'s `DECLARED_HOMES`; one new label
(`board:stalled`) documented in `docs/setup.md`; no change to the feature
lifecycle's eight published stages (FR-004).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide — repo is its own first example**: Built through the pipeline
  itself (issue #408 → this spec → this plan → tasks → implement). PASS.
- **II. Cost-Conscious Model Tiering**: Every agent invocation the loop
  makes (triage-propose, route-propose, fixer, reviewer) runs at the
  default `claude-sonnet-5` tier with the existing `model:opus` label
  escalation honored verbatim (FR-027, research.md D20), never a new
  always-on premium tier. PASS.
- **III. Simple, GitHub-Native Interaction**: Every step's outcome lands
  as a comment, label, PR, or review on the originating issue or its PR
  (FR-044) — the exact legibility gap #401/#403 demonstrate. PASS.
- **IV. Automation-First**: The scheduled trigger plus the
  `pull_request: closed` resume make the six-step procedure run without a
  human re-reading CLAUDE.md each time. PASS.
- **V. Security — Untrusted Content Is Never Instructions**: Issue/comment
  bodies are framed as data in every invocation (FR-055); only
  maintainer-association comments reach the fixer as directives, decided
  in code (FR-056); entry itself is code-decided from author association
  and the `labeled` event's actor, never from text (FR-008). This
  feature's entry rule is the sentence Constitution 2.0.0/Principle X
  added to V. PASS.
- **VI. Portability**: Every new artifact lives under this repository's
  own `.github/{workflows,actions,scripts}` and `docs/`, resolved the same
  self-checkout way every existing composite is. PASS.
- **VII. Two Interfaces**: `board-loop.yml` carries no `workflow_call`
  trigger at all (FR-062/FR-063) — it is not part of the published
  surface. The two composites this feature promotes/extracts
  (`wing-commander-size-path-backstop`, `wing-commander-dispatch-and-wait`)
  are new internal composites with no adopter-pinned interface prior to
  this feature, so widening their shape (parameterized thresholds/inputs)
  is not a break. PASS.
- **VIII. A Green Check Means What It Says**: Every new decision script is
  reachable through the gate registry, runs the same subject with the same
  arguments locally and in CI (`run-local-gates.py` derives its list from
  `lint-workflows.yml`), fails loudly rather than passing vacuously when it
  cannot locate its subject, and ships a checked-in fixture per failure
  branch (FR-064, contracts/gates.md). A head with no checks is treated as
  not green (FR-037). PASS.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The organizing principle of this entire feature — every close,
  route, push, and readiness claim is re-derived by a script from
  GitHub/transcript state; an agent's proposal narrows but never widens a
  verdict (FR-012, FR-017). PASS.
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: This feature
  is Principle X's own referent. It exercises the bound exactly as X
  states it: the shape of the change decides the route, never the
  model's confidence (FR-016/FR-017/FR-019), and the merge — X's step 5 —
  is deferred as one block per FR-003's clarification, narrower than X
  permits but not in conflict with it. PASS.

No violations. **Complexity Tracking is intentionally empty**: the spread
across one workflow, two composites, one schema, and five decision
scripts is FR-059/FR-061's single-home rule applied to five genuinely
distinct deterministic checks (eligibility, triage, route, readiness,
review-finding shape) plus two extractions of logic already duplicated by
a second caller — not incidental complexity invented for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/057-autonomous-board-loop/
├── plan.md                 # This file
├── research.md             # Phase 0 output — 27 recorded decisions
├── data-model.md           # Phase 1 output — entities and state shapes
├── contracts/              # Phase 1 output
│   ├── board-loop-workflow.md
│   ├── eligibility-and-selection.md
│   ├── triage.md
│   ├── route-backstop.md
│   ├── fix-step.md
│   ├── review-and-findings.md
│   ├── readiness-report.md
│   ├── prove-step.md
│   ├── board-item-marker.md
│   ├── gates.md
│   └── labels-and-cross-links.md
├── quickstart.md            # Phase 1 output — validation drills
├── checklists/requirements.md   # from intake, unchanged by this stage
└── spec-meta.json
```

### Source Code (repository root)

This is a GitHub Actions pipeline repository; "source" is workflows,
composite actions, gate scripts, and one schema.

```text
.github/
├── schemas/
│   └── board-review-finding.schema.json        # NEW (contracts/review-and-findings.md)
├── scripts/
│   ├── board_eligibility.py                    # NEW — FR-006/FR-008/FR-009/FR-010
│   ├── verify-board-eligibility.py              # NEW gate (fixtures: FR-064 bullet 2)
│   ├── board_triage.py                          # NEW — FR-011/FR-012/FR-014
│   ├── verify-board-triage.py                    # NEW gate (fixtures: FR-064 bullet 1)
│   ├── board_route_backstop.py                  # NEW — FR-016..FR-021 (contract-widening + final-diff checks; delegates size/path to the shared composite)
│   ├── verify-board-route-backstop.py            # NEW gate (fixtures: FR-064 bullet 3)
│   ├── board_readiness.py                       # NEW — FR-036/FR-037/FR-066/FR-067
│   ├── verify-board-readiness.py                 # NEW gate (fixtures: FR-064 bullet 4)
│   ├── verify-board-review-finding-schema.py     # NEW gate — hand-written validator, D5-style
│   └── verify-single-home-idioms.py              # EXTENDED — 2 new DECLARED_HOMES entries
├── actions/
│   ├── wing-commander-size-path-backstop/        # NEW, extracted from pr-conversation.yml
│   │   └── tests/                                # NEW fixtures
│   └── wing-commander-dispatch-and-wait/         # NEW, extracted from auto-release.yml's dispatch-release job
│       └── tests/                                # NEW fixtures
└── workflows/
    ├── board-loop.yml         # NEW — repository-only, no workflow_call (FR-062/FR-063)
    ├── pr-conversation.yml    # EDITED: size/path backstop calls the new shared composite instead of inline jq
    ├── auto-release.yml       # EDITED: dispatch-release calls the new shared composite instead of its inline correlation/poll block
    └── lint-workflows.yml     # EDITED: register the 5 new gates + extended single-home gate

docs/
└── setup.md                # EDITED: add `board:stalled` to the manual label table
```

**Structure Decision**: No new top-level directory beyond
`.github/schemas/` (already established by spec 056). The route backstop
and the prove step's dispatch-and-wait each become a shared composite
the moment this feature is their second consumer — following CLAUDE.md's
"before pasting a second copy, move it" rule exactly — rather than two
more inline copies of logic `pr-conversation.yml` and `auto-release.yml`
already have. Every genuinely new deterministic check (eligibility,
triage, readiness, the route's contract-widening/final-diff checks, the
review-finding schema) is its own script with its own fixture set, per
FR-064's explicit enumeration of four separate gates.

## Complexity Tracking

*No violations to justify — table intentionally empty (see Constitution Check).*
