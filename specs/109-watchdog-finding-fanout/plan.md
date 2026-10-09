# Implementation Plan: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

**Branch**: `spec/109-watchdog-finding-fanout` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/109-watchdog-finding-fanout/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The watchdog's dedup identity today is an opaque `sha256(class |
sorted(cited signal ids))` matched by exact string equality inside a
finding's own class label — a filter that misses two known shapes of the
same underlying failure: a citation set that drifts run to run (three open
`gate-suite-failure` issues, `#729`/`#732`/`#765`, all cite signal
`1bcf7944887991cd` and never deduplicated), and one red gate suite
described under six different class labels by a converging implement
cycle (run 36484099706, six issues in one minute). Per the answers on
issue #792, this plan adopts **overlap matching within a class** (an open
issue citing any signal id in common is a match, resolved to the
lowest-numbered match when several tie) for the first shape, and a new
**filing condition** — a converging implement cycle's red gate suite is
never filed, only a stalled or finalize-still-red one is — for the
second, leaving cross-class grouping explicitly rejected. The deliverable
is: (1) a new readable `signal-ids=` marker each occurrence writes,
additive alongside the unchanged opaque `fingerprint=` marker so
pre-existing issues (FR-015) and the closed-issue exact-reopen path
(FR-006) are untouched; (2) a widened, still-one-call dedup read (`gh
issue list --json ...,comments`) that computes each open candidate's
accumulated, 30-id-capped (FR-008) matchable set locally; (3) a new
`gate-suite-failure` signal kind and a new `Collect: cycle outcome`
artifact handoff from `implement.yml` to `watchdog.yml`, which together
let `triage` decide the FR-009 filing condition from deterministic state
alone (Constitution IX); (4) checked-in, mutation-tested fixtures for all
of the above (FR-020–FR-022); and (5) the corresponding amendment of
`specs/015-pipeline-watchdog/{spec.md,data-model.md,contracts/
watchdog-workflow.md,quickstart.md}` (FR-023/FR-024), following spec 024's
own precedent for amending that same governing document. Per FR-025,
nothing about the already-open duplicates this feature was filed over is
touched, closed, or consolidated.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML, `jq` —
identical toolchain to specs 015/024; no new language introduced.

**Primary Dependencies**: `gh` CLI (`issue list` gains the `comments`
JSON field; `run download`/`run list`, both already used elsewhere in this
workflow, cover the new artifact handoff), `jq`, `anthropics/
claude-code-action@v1` (`diagnose` only — unchanged, still `claude-opus-5`
per issue #124's carve-out; no new agent step is introduced by this
feature). No new dependency is added.

**Storage**: No new persistent storage. The `signal-ids=` marker and the
per-occurrence "matched on / new" text are ordinary GitHub issue
body/comment content (Constitution III: no new dashboard, no new file
format) — the same convention the existing `fingerprint=` marker already
uses. The `wing-commander-cycle-outcome` artifact is an ephemeral,
per-run CI artifact (same retention/lifecycle as the existing
`claude-execution-output-*` artifact `collect-execution-output` already
downloads) — not a new durable store. `specs/015-pipeline-watchdog/
{spec.md,data-model.md,contracts/watchdog-workflow.md,quickstart.md}` are
amended in place (FR-023/FR-024), mirroring exactly how spec 024 amended
the same four files for the same governing requirements (FR-012–FR-016).

**Testing**: No automated test suite exists for any pipeline stage in
this repository (unchanged from specs 015/024). This feature's own
coverage requirement (FR-020–FR-022) follows the established
`verify-act-dedup-guard.py`/`verify-dedup-key-canonical-rule.py` pattern:
a Python harness that extracts the real shipped step(s) from
`watchdog.yml`/`implement.yml`, executes them against a fixture through
`wc_shell_harness`, asserts the real outcome, and is itself proven capable
of failing by a companion mutation (reverting overlap matching to
exact-set equality; reverting the FR-009 condition to "always file";
reverting the `tool-denial` id projection to a shared key) that the suite
must catch. Registered in `run-local-gates.py` so it runs identically
locally and in CI (Constitution VIII) — the specific gate number is
`tasks.md`-level detail (research.md).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), unchanged
triggers (`workflow_run` + `workflow_dispatch` for `watchdog.yml`; no
trigger change to `implement.yml`).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, unchanged.

**Performance Goals**: The dedup lookup stays exactly one `gh` API call
per triaged finding (research.md: `comments` is added to the existing
bulk `gh issue list` call rather than requiring a per-candidate follow-up
read) — no increase in API call count per finding despite the widened
matching logic. The matchable-set union/cap computation (FR-008: capped
at 30 distinct ids) is local `jq` over already-fetched data, adding no
network round-trips.

**Constraints**: Per Out of Scope: this feature MUST NOT touch issue
`#705`'s separate, unbounded dedup lookup (`wing-commander-durable-
failure-issue/action.yml`); MUST NOT change the finding-class vocabulary,
the `__new__` resolution path, or `diagnose`'s prompt; MUST NOT add any
remediation action beyond file/comment/reopen (FR-007's multi-match names
other issues but never merges, closes, or relabels them); MUST NOT adopt
cross-class grouping (matching stays inside the `🐕 · <class>` label
filter, FR-001/FR-012); MUST NOT close, relabel, or consolidate the
already-open duplicates the feature was filed over (FR-025) —
`#729`/`#732`/`#765` and `#708`–`#713` are triaged by the owner, by hand,
outside this feature.

**Scale/Scope**: Touched: `.github/workflows/watchdog.yml` (`collect`
gains a sixth collector and a new signal kind; `triage` gains the FR-009
branch ahead of dedup search, widens the dedup read, and gains the
`overlap`/`converging-gate-suite` outcomes; `act` gains the `signal-ids=`
marker write and the multi-match naming); `.github/workflows/
implement.yml` (one new step after each of the two existing "Read back
cycle outcome" steps — `(cycle)` and `(retry)` legs — uploading the new
artifact); one new `.github/scripts/verify-*.py` gate plus its fixtures,
registered in `run-local-gates.py`; `specs/015-pipeline-watchdog/
{spec.md,data-model.md,contracts/watchdog-workflow.md,quickstart.md}`
(amended, FR-023/FR-024). No workflow file is added or deleted; no
`workflow_call` input, output, or secret is added, removed, or renamed on
either touched workflow (Principle VII).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue
  #792 → this spec → this plan → tasks → implementation), and its subject
  is the pipeline's own watchdog correcting a gap its own tracker exposed
  — as direct a worked example as spec 024's identical shape. **Pass.**
- **II. Cost-Conscious Model Tiering**: No model-tier change. `diagnose`
  stays `claude-opus-5` (issue #124's carve-out, unchanged). No new agent
  step is introduced anywhere in this feature — the FR-009 filing
  condition, the widened matching, and the multi-match resolution are all
  deterministic code (Principle IX), never a new model invocation.
  **Pass.**
- **III. Simple, GitHub-Native Interaction**: The new `signal-ids=` marker
  and the "matched on / new ids" legibility text (FR-017) are ordinary
  issue body/comment content, read with `gh issue view`/`gh issue list` —
  no new dashboard, no new CLI. A maintainer reading a filed issue's
  comments alone can already answer "what does this issue cover"
  (FR-017/SC-006). **Pass.**
- **IV. Automation-First**: Every new behavior (the FR-009 suppression,
  the overlap match, the multi-match naming) is fully automated; no new
  manual step is introduced, and the one place a human is explicitly
  still needed — merging the other matches FR-007 names in a multi-match
  comment — is unchanged from today's status quo (the watchdog has never
  merged issues). **Pass.**
- **V. Security (NON-NEGOTIABLE)**: The matching identity (which ids an
  issue accumulates, which issue a finding attaches to, whether a finding
  is suppressed under FR-009) is derived entirely from deterministic
  collector signal ids and run state — never from `diagnose`'s prose —
  extending, not weakening, spec 024's own fingerprint-determinism fix.
  No new agent step, no widened untrusted-content surface: the new
  `gate-suite-failure` signal is stamped from `run-local-gates.py`'s own
  `FAIL` line text, read the same attribution-guarded way every other
  collector already reads run state. **Pass.**
- **VI. Portability**: All changes land inside `.github/workflows/**`
  (this repo's own consuming-repo-owned wrapper/stage layer) and
  `specs/015-pipeline-watchdog/**` (this repo's own spec-kit output); no
  new top-level convention, and nothing is bundled with or resolved from
  a location outside this repository's own checkout. **Pass.**
- **VII. Two Interfaces**: Neither `watchdog.yml` nor `implement.yml`
  gains, loses, or renames a `workflow_call` input, output, or secret —
  the new artifact handoff and the new collector are entirely internal to
  each stage's own job graph, resolved through the stages' existing
  self-checkout of `.github/actions/**`. The published contract is
  unchanged; this is a same-surface, additive change. **Pass.**
- **VIII. A Green Check Means What It Says**: FR-020–FR-022 require a
  checked-in fixture for every new branch this feature adds (overlap
  match, multi-match, the FR-009 converging/stalled/finalize-red arms, the
  preserved `{stage, tool}` separation), each with a mutation the suite
  must be shown to fail under — the exact discipline this principle
  requires, applied to new code rather than retrofitted to old.
  **Pass.**
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: This is the organizing principle of the whole feature. Which
  issue a finding attaches to (overlap matching), which of several
  matches receives the write (lowest-numbered), and whether a finding is
  filed at all (the FR-009 condition) are all computed from deterministic
  collector signal ids and run state — never from `diagnose`'s class
  choice or prose (FR-002/FR-010 both say so explicitly). The model may
  still propose a class and a description; it never decides whether its
  own output is well-formed enough to act on, matching this principle's
  own framing verbatim. **Pass.**
- **X. Bounded Autonomy**: Not directly exercised by this plan (a plan-PR
  review, not a board-loop fix/merge action) — noted for completeness:
  this feature changes watchdog *stage* behavior, not board-loop routing
  or merge-gate logic, so Principle X's fix-shaped/spec-shaped boundary
  and merge classes are unaffected. **N/A.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/109-watchdog-finding-fanout/
├── plan.md                # This file (/speckit-plan command output)
├── research.md            # Phase 0 output (/speckit-plan command)
├── data-model.md           # Phase 1 output (/speckit-plan command)
├── quickstart.md           # Phase 1 output (/speckit-plan command)
├── contracts/              # Phase 1 output (/speckit-plan command)
│   └── watchdog-dedup-fanout-delta.md
└── tasks.md                 # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── watchdog.yml         # AMENDED — new collector, FR-009 branch, widened
│   │                          dedup read, new marker, new outcomes
│   └── implement.yml        # AMENDED — one new step per cycle-outcome
│                               read-back leg (cycle + retry), uploading the
│                               new artifact
└── scripts/
    ├── verify-<gate-name>.py  # NEW — mutation-tested fixtures for
    │                            FR-020–FR-022 (name/number: tasks.md)
    └── run-local-gates.py     # AMENDED — registers the new gate

specs/015-pipeline-watchdog/
├── spec.md                  # AMENDED — FR-012–FR-016 restated per FR-023
├── data-model.md            # AMENDED — Matchable id set, Cycle outcome,
│                               Occurrence record entities (this feature's
│                               data-model.md, folded in)
├── contracts/
│   └── watchdog-workflow.md   # AMENDED — per this feature's contract delta
└── quickstart.md             # AMENDED — new scenarios folded in
```

**Structure Decision**: Single-project CI/CD feature, matching specs
015/024's own footprint — no `src/`/`tests/` split. Every code change
lands inside `watchdog.yml`'s existing `collect`/`triage`/`act` jobs plus
one small addition to `implement.yml`'s existing cycle/retry legs; no new
job or workflow file is added. `specs/015-pipeline-watchdog/` remains the
sole governing document this feature amends, per FR-023's own framing
("the dedup requirements of spec 015... MUST be updated") and spec 024's
established precedent for doing so.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
