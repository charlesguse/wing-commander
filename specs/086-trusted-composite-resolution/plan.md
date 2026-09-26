# Implementation Plan: The Loop's Own Code Comes From a Trusted Commit — Composite Resolution in board-loop's Item-Branch Jobs

**Branch**: `spec/086-trusted-composite-resolution` | **Date**: 2026-09-26 | **Spec**: [specs/086-trusted-composite-resolution/spec.md](./spec.md)

**Input**: Feature specification from `specs/086-trusted-composite-resolution/spec.md`

## Summary

Every job in `board-loop.yml` gains one extra, lightweight
`actions/checkout@v5` step — a shallow checkout of this repository at
`github.sha` (the commit whose `board-loop.yml` is running) into a
gitignored sidecar directory, `.wc-pristine-repo` — placed before that
job's first composite reference, before any credential-minting composite,
and before any agent step. Every `uses: ./.github/actions/<name>` in the
file is rewritten to `uses: ./.wc-pristine-repo/.github/actions/<name>`,
so no job ever resolves a composite from the workspace again, uniformly
(FR-011) — including the five jobs that check out only trusted content
today, which gain the same wiring so the rule and its gate stay one
unconditional statement rather than an allowlist. `.wc-pristine-repo` is
added to `.gitignore` so no `git add` invocation — including the fixer and
review-fixup agents' own `Bash(git add:*)` grant — can ever stage it into
the item's branch (FR-007), a deterministic guarantee that needs no
agent-followed instruction (Principle IX) and needs no reliance on the
`clean: false` / exclude-pathspec disciplines the existing published-stage
and auto-update-stage sidecars each use instead, because board-loop's
agents hold broader git tool grants than either of those callers does.
This pairs, without replacing, the existing `git archive`-based
`.github/scripts`/`.github/schemas` snapshot (issue #583, Gate 98) at the
same commit, so a single run's workflow definition, composites, and
helper scripts are all provably one provenance (FR-003/FR-004). A new
gate, Gate 99 (`verify-board-loop-composite-provenance.py`), replaces the
per-job allowlist shape Gate 98 uses for `run:` blocks with an
unconditional, file-wide rule for `uses:` blocks: no
`uses: ./.github/actions/` may appear anywhere in `board-loop.yml`, and
every sidecar-relative reference must be preceded, in its own job, by a
correctly-shaped, fail-closed checkout step. FR-013's provenance
observability is a one-line `$GITHUB_STEP_SUMMARY` echo the checkout step
itself writes, reusing the pattern the fix job's own branch-cut step
already uses for the same purpose.

## Technical Context

**Language/Version**: YAML (the one edited workflow, `board-loop.yml`),
Python 3 (the new gate script, matching every existing
`.github/scripts/verify-*.py`), Bash (the checkout step's own tiny
provenance-echo line; no new `run:` logic of any complexity).

**Primary Dependencies**: `actions/checkout@v5` — already used by every
job in this file and by every published stage's own sidecar pattern; this
feature adds one more call site per job, never a new action.

**Storage**: None. No new persisted state; FR-013's provenance record is
a `$GITHUB_STEP_SUMMARY` line, not a durable store, matching how the
fix job's branch-cut step already reports its own base SHA.

**Testing**: Gate 99 carries an embedded `--self-test` mode against
mutations of the real workflow text, following Gate 97/98's exact
convention (a `MUTATIONS` list, each asserted caught, plus a
clean-on-unmutated-input baseline check) — registered in
`lint-workflows.yml` so `run-local-gates.py` and `verify-gate-wiring.py`
pick it up automatically, no manifest edit. Two of the spec's user
stories (composite/helper rewrite defeated, old-branch composite
resolution) need a real dispatched run against a disposable/test
repository and are covered by `quickstart.md` drills, not the gate.

**Target Platform**: GitHub Actions (`ubuntu`-class runners),
`board-loop.yml` itself — a repository-only workflow with no
`workflow_call` trigger (unaffected by this feature).

**Project Type**: Reusable GitHub Actions pipeline (single project).

**Performance Goals**: One additional shallow, single-ref
`actions/checkout@v5` per job that already runs (select, triage, route,
fix, review, readiness, prove-gate, prove — eight call sites; `resolve-model`
has no checkout and no composite reference today and gains neither). No
new agent turn, no new billed Claude invocation, no new third-party
network call beyond the checkout itself.

**Constraints**: FR-002/FR-006 — the sidecar checkout MUST precede every
composite reference, every credential mint, and every agent step in its
job, and MUST be fail-closed (no `continue-on-error`, no fallback to a
workspace-relative `uses:`). FR-007 — the sidecar MUST NOT reach the
item's branch or PR under any git command an agent might run. FR-011 —
uniform across every job, no per-job allowlist. FR-013 — the ref and
resolved commit MUST be observable in the run record.

**Scale/Scope**: One workflow file edited (`board-loop.yml`: eight new
checkout steps, every `uses: ./.github/actions/` reference rewritten, one
header addition); one new gate script and its two `lint-workflows.yml`
registration steps; one `.gitignore` entry; three small documentation
pointer edits (`board-loop.yml`'s own header as the canonical statement,
one pointer line added to `wing-commander-context`'s header, one pointer
line added to Gate 98's `lint-workflows.yml` comment block). No new
composite action, no new schema, no change to what the loop decides about
an item (FR-015).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide — repo is its own first example**: Built through the pipeline
  itself (issue #468 → #504 → #615 → this spec → this plan → tasks →
  implement). PASS.
- **II. Cost-Conscious Model Tiering**: No agent invocation is added,
  changed, or retiered by this feature — it is pure workflow/gate
  plumbing. N/A/PASS.
- **III. Simple, GitHub-Native Interaction**: No new user-facing surface;
  FR-013's provenance line lands in the run's own `$GITHUB_STEP_SUMMARY`,
  legible from the Actions run itself, not a new dashboard. PASS.
- **IV. Automation-First**: Fully automated; no new manual step survives
  this feature. PASS.
- **V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)**:
  This feature IS the extension of V's guarantee spec.md's Assumptions
  section names — the loop's judging surface (composites, not just
  helper scripts) can no longer be edited by the branch it judges. PASS,
  and the primary deliverable.
- **VI. Portability**: The sidecar checks out this same consuming
  repository at its own commit — no bundling with or resolution from Wing
  Commander as a separate project; `board-loop.yml` remains this
  repository's own artifact. PASS.
- **VII. Two Interfaces**: `board-loop.yml` carries no `workflow_call`
  trigger before or after this feature (FR-062/FR-063 of spec 057
  untouched) — nothing here widens the published, adopter-pinned surface.
  PASS.
- **VIII. A Green Check Means What It Says**: Gate 99 is reachable through
  the gate registry, runs the same subject with the same arguments locally
  and in CI, is triggered by any change to `board-loop.yml`, fails loudly
  when it cannot parse its subject, is not suppressible by an unrelated
  gate, and ships a checked-in-fixture mutation per rule it enforces
  (FR-008/FR-009, User Story 3). PASS.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: Composite resolution becomes a fixed-ref checkout, not an agent
  instruction to "resolve trusted code" — and FR-007's non-staging
  guarantee is a `.gitignore` entry, not a prompt telling the fixer never
  to `git add -A`, so it holds regardless of what the fixer's own
  `Bash(git add:*)` grant is used to type. PASS, applied more strictly
  than the two existing sidecar precedents this feature otherwise follows.
- **X. Bounded Autonomy — The Pipeline Works Its Own Board**: This feature
  hardens exactly the boundary Principle X depends on for board-loop's
  autonomy to be trustworthy — "the bound is the shape of the change,
  never the confidence of the model" only holds if the code deciding that
  shape cannot be edited by the change being shaped. FR-012 deliberately
  keeps X's "work the item normally" rule intact for a branch that touches
  the loop's own judging surface, relying on trusted resolution alone
  rather than adding a stand-down path X does not call for. PASS.

No violations. **Complexity Tracking is intentionally empty**: one gate
script and one repeated (not duplicated — a single shared step shape)
checkout step across a fixed set of jobs in one file is the minimum
surface FR-001/FR-011's unconditional rule can be expressed in; splitting
it into a composite action would need its own `uses:` reference, which is
exactly the resolution problem this feature is fixing and cannot itself
depend on.

## Project Structure

### Documentation (this feature)

```text
specs/086-trusted-composite-resolution/
├── plan.md                          # This file
├── research.md                      # Phase 0 output — 13 recorded decisions
├── data-model.md                    # Phase 1 output — entities and shapes
├── contracts/
│   ├── trusted-copy-checkout.md     # The sidecar checkout step's exact shape and placement rule
│   ├── gate-99.md                   # Gate 99's rules, self-test mutations, registration
│   └── documentation-updates.md     # FR-014's canonical-statement/pointer map
├── quickstart.md                    # Phase 1 output — validation drills
├── checklists/requirements.md       # from intake, unchanged by this stage
└── spec-meta.json
```

### Source Code (repository root)

This is a GitHub Actions pipeline repository; "source" is workflows, gate
scripts, and one ignore-file entry.

```text
.github/
├── workflows/
│   ├── board-loop.yml        # EDITED — sidecar checkout added to select,
│   │                         # triage, route, fix, review, readiness,
│   │                         # prove-gate, prove; every uses: ./.github/actions/
│   │                         # rewritten to uses: ./.wc-pristine-repo/.github/actions/;
│   │                         # header gains the canonical trusted-copy
│   │                         # statement (FR-014, contracts/documentation-updates.md)
│   └── lint-workflows.yml    # EDITED — registers Gate 99 (2 steps + prose
│                             # comment); Gate 98's own comment block gains
│                             # one pointer line to Gate 99 for the
│                             # composite half of the same provenance rule
├── scripts/
│   └── verify-board-loop-composite-provenance.py   # NEW — Gate 99, --self-test mode (contracts/gate-99.md)
└── actions/
    └── wing-commander-context/action.yml           # EDITED — header gains
        # one pointer line to board-loop.yml's own trusted-copy statement,
        # for the non-published-stage variant of "the general rule for
        # shared composites" (contracts/documentation-updates.md)

.gitignore                    # EDITED — adds the sidecar path so no git
                               # add invocation, agent or script, can ever
                               # stage it (FR-007, research.md D4)
```

**Structure Decision**: No new composite action and no new schema. The
mechanism this feature needs — a checkout step plus a path rewrite in
`uses:` references — is data, not orchestration logic, so extracting it
into a composite would need its own `uses:` reference to be invoked,
which begs the exact resolution question this feature answers. The one
new script follows the existing `verify-*.py` gate convention exactly,
kept separate from Gate 98 because it checks a structurally distinct
surface (`uses:` blocks, file-wide and unconditional) from Gate 98's
`run:`-block, three-job-allowlist scope (FR-011's own reasoning: a
per-job list is the same shape as the gap being fixed, so the new gate
must not inherit Gate 98's `JOBS = (...)` shape).

## Complexity Tracking

*No violations to justify — table intentionally empty (see Constitution Check).*
