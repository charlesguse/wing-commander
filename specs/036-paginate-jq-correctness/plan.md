# Implementation Plan: Multi-Page `gh api` Reads Return What They Claim, and a Gate Keeps Them That Way

**Branch**: `036-paginate-jq-correctness` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-paginate-jq-correctness/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`gh api --paginate` applies `--jq` to each page separately and concatenates
the raw outputs, so a filter that collects results into an array
(`--jq '[.[] | ...]'`), or no `--jq` at all on an array/object endpoint,
emits one page-shaped JSON document per page rather than one document for
the whole read. Spec 033 T067 fixed six call sites with this shape in
`pr-conversation.yml`; this feature fixes the three remaining sites T067
asked to be checked separately (issue #182) — `watchdog.yml`'s annotation
collector (`:743`, silently drops every annotation past page 1 under
`set -uo pipefail`) and the two `spec-kit/releases` reads in
`auto-update-spec-kit.yml` (`:425` detect, `:835` release-note assembly,
both resolve to page-shaped garbage once upstream passes 30 releases) —
and rewrites the two `watchdog.yml` object-endpoint reads (`:665`, `:740`)
that are correct today only because their consumer (`jq -r
'.jobs[]?.id // empty'`) tolerates a multi-value stream, into the same
safe-by-construction form. All five rewrites use the form spec 033 already
proved: stream one JSON value per line under `--paginate --jq '<per-item
filter>'`, collect once with `jq -s '.'` (research.md D1).

Because this defect class is invisible to every test that uses a
single-page fixture and was already independently rediscovered once, the
feature also adds a repository-wide static gate (**Gate 18**, wired into
`lint-workflows.yml`'s existing numbered gate sequence and its
`verify-gate-wiring.py` registry, research.md D2) that flags any
`--paginate` read not written in the safe form — across workflow files,
composite actions, and checked-in scripts (FR-006) — with a declared,
diff-visible exemption escape hatch rather than a hand-maintained
exemption list (FR-013, research.md D3). All three fixed sites gain
executable multi-page coverage that drives the shipped step against a
stubbed API (FR-012): the two auto-update sites through its existing
extract-and-run harness, generalized to make its `gh` stub genuinely
page-aware (research.md D4), and the watchdog's annotation collector
through a new harness, **Gate 19**, built on the same
extract-and-run/`gh`-stub pattern its sibling `verify-sentinel-collector.py`
(Gate 9) already established for the step summary collector (research.md
D5). Separately, every one of the watchdog's evidence collectors gains a
per-read failed/empty distinction that the `diagnose` job is told about as
a new, additive job output (FR-010/016/017, research.md D6) — the property
whose absence let the annotation defect hide for two audits running.
Finally, `docs/agent-friendly-workflows.md`'s existing (and now-stale)
"`gh api --paginate` breaks on `/jobs`" bullet is replaced with the correct
required form (FR-014, research.md D7).

## Technical Context

**Language/Version**: Bash (POSIX-ish `run:` steps, matching every existing
workflow/composite action) + GitHub Actions YAML (`workflow_call` reusable
workflows); the new gate and both test harnesses are Python 3, matching
every existing `.github/scripts/verify-*.py` and the
`auto-update-spec-kit-tests/` harness. No new application language or
runtime.

**Primary Dependencies**: `gh` CLI (`gh api ... --paginate --jq`), `jq`
(`-s` slurp), GitHub Actions (`workflow_call`), PyYAML (already a
`lint-workflows.yml` dependency, used by every static gate that parses
workflow YAML), the repository's own `wc_gate_registry.py` (gate wiring
convention) and `wc_shell_harness.py` (`find_step`/`run_step`/`resolve_bash`
— shared "extract the shipped `run:` block and execute it" plumbing every
behavioral gate already uses).

**Storage**: N/A — every artifact touched is either a workflow `run:` step,
a job-output-carried JSON value (`signals.json`, `collector-outcomes`), or
a repository file scanned in place. No new persisted file.

**Testing**: `python3 .github/scripts/verify-gate-18.py` (Gate 18's
self-test, same synthetic-fixture-table pattern as Gates 15-17),
`python3 .github/scripts/verify-gate-19.py` (new annotation-collector
harness, same extract-and-execute-against-a-`gh`-stub pattern as Gate 9,
with its own mutation self-test per FR-009), `bash
.github/scripts/auto-update-spec-kit-tests/run-tests.sh` (extended `t1_detect.sh`
plus new `t10_notes.sh`), `python3 .github/scripts/run-local-gates.py`
(derives the PR-time gate list — including Gate 18 and 19 once wired —
automatically, no separate registration).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners); harnesses
must also run on a maintainer's Windows machine, which is why they go
through `wc_shell_harness.py` rather than shelling out directly (its
docstring catalogs the three ways a naive `subprocess.run(["bash", ...])`
silently produces false results on Windows).

**Project Type**: Single project — this repository *is* the GitHub Actions
pipeline; there is no separate frontend/backend split. New code lives
entirely under `.github/workflows/` (edits) and `.github/scripts/` (new
gate + harness + shared-module edits).

**Performance Goals**: N/A — no runtime performance target; gates and
harnesses run once per PR/scheduled dispatch, budget is "does not
meaningfully lengthen `lint-workflows.yml`'s existing gate sequence,"
not a numeric target.

**Constraints**: FR-005 (byte-for-byte identical behavior below the page
boundary), FR-015 (no widening of any published stage's declared
inputs/outputs/secrets except the one deliberate, spec-mandated widening —
per-collector read-outcome on `watchdog.yml`'s `collect` job output),
FR-013 (no hand-maintained exemption list — any exemption must be declared
at the read).

**Scale/Scope**: Three broken call sites fixed, two accidentally-safe call
sites rewritten, one new static gate (Gate 18) plus its self-test, one new
behavioral gate (Gate 19) plus its own mutation self-test, one existing
harness (`auto-update-spec-kit-tests/`) extended with page-aware fixtures
and one new suite file, one `watchdog.yml` evidence-collector shape change
(read-outcome tracking across five collectors), one documentation edit.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Guide — The Repo Is Its Own First Example | Pass. This feature is itself flowing through the pipeline (spec → plan → tasks → implement, issue #182). No new capability is added that bypasses dogfooding. |
| II. Cost-Conscious Model Tiering | Pass, N/A. No new Claude invocation is added or changed; every touched step is deterministic shell or a Python gate. `watchdog.yml`'s `diagnose` step's model tier is untouched (Out of Scope: "any change to the watchdog's diagnostic reasoning"). |
| III. Simple, GitHub-Native Interaction | Pass. No new user-facing interaction surface. The gate's failure text is read by a maintainer in a PR check, same as every existing gate; the watchdog's new untrusted-collector information reaches the same lifecycle-issue comment path that already exists. |
| IV. Automation-First | Pass. Nothing here introduces a manual step; the gate and both harnesses are fully automated, and a failed evidence read is now *reported* automatically (FR-016) rather than requiring a human to notice a suspiciously thin verdict. |
| V. Security — Untrusted Content Is Never Instructions | Pass. `watchdog.yml`'s `diagnose` step already frames `signals.json` as untrusted data (FR-023 of spec 015/023); the new per-collector outcome value is a small enum/string the collector step itself computes deterministically (never attacker-controlled content lifted from an annotation body or release note), so it does not enlarge the untrusted-data surface reaching the agent. Release-note bodies fetched at `:835` were already framed as untrusted data before this feature and remain so — only the read's correctness changes, not its trust framing. |
| VI. Portability — The Consuming Repository Owns Its Artifacts | Pass, N/A. Every change is inside Wing Commander's own `.github/` — nothing here reads or writes adopter-specific configuration, and no new dependency on consumer-repo state is introduced. |
| VII. Two Interfaces — The Published Contract and the Consuming Instrument | **Deliberate, spec-scoped widening, not a violation.** `watchdog.yml` is a published `workflow_call` stage; its `collect` job gains one new job output (research.md D6) carrying per-collector read outcomes, and the `diagnose` job's prompt gains one new file it reads. FR-015 explicitly scopes this as the one permitted exception: "MUST NOT widen ... except ... the newly reported trustworthiness of each evidence read." No secret, input, or any other output is added or renamed. See Complexity Tracking. |

**Initial gate result**: PASS (one principle carries a spec-authorized, narrowly-scoped exception — recorded in Complexity Tracking rather than blocking).

## Project Structure

### Documentation (this feature)

```text
specs/036-paginate-jq-correctness/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── pagination-shape-gate.md
│   └── watchdog-read-outcome.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no `src/`/`tests/` split — it *is* the GitHub Actions
pipeline, and every prior spec that touched gates or workflow steps landed
its code under `.github/`. This feature follows the same layout.

```text
.github/
├── workflows/
│   ├── watchdog.yml                    # rewrite :665, :740, :743; add per-collector
│   │                                    # read-outcome tracking + new collect-job output
│   ├── auto-update-spec-kit.yml        # rewrite :425 (detect/compare), :835 (notes)
│   └── lint-workflows.yml              # add Gate 18 + its self-test step, Gate 19,
│                                        # both invoked from the existing numbered
│                                        # gate sequence (no new job)
├── scripts/
│   ├── verify-gate-18.py               # NEW — Gate 18's self-test (static-shape detector)
│   ├── verify-gate-19.py               # NEW — Gate 19 itself (behavioral: extracts and
│   │                                    # runs watchdog's annotation collector against a
│   │                                    # page-aware `gh` stub; carries its own mutation
│   │                                    # self-test, same discipline as verify-sentinel-
│   │                                    # collector.py / Gate 9)
│   ├── wc_gate_registry.py             # unchanged — Gate 18/19 are picked up by the
│   │                                    # existing naming convention, no edit needed
│   └── auto-update-spec-kit-tests/
│       ├── gh_stub.py                  # generalize the `--paginate` handling on the
│       │                               # spec-kit/releases endpoint to chunk fixture
│       │                               # data into pages and apply --jq per page,
│       │                               # matching gh's real per-page semantics
│       ├── t1_detect.sh                # extend with a >1-page fixture scenario (FR-012)
│       ├── t10_notes.sh                # NEW — no existing suite drives "Fetch candidate
│       │                               # release notes" (evaluate-path job) at all;
│       │                               # stood up here, single-page + multi-page cases
│       └── run-tests.sh                # add t10_notes.sh to SUITES
└── docs/  (repo-root docs/, not under .github/)
    └── agent-friendly-workflows.md     # replace the stale ":425/:665/:740/:743"-shaped
                                         # "breaks on /jobs, use ?per_page=100" bullet with
                                         # the correct required form (FR-014)
```

**Structure Decision**: No new top-level directory. Two new gate scripts
join `.github/scripts/` following the existing `verify-*.py` naming
convention (automatically picked up by `wc_gate_registry.py`'s
`gate_scripts()` — no manifest edit). The existing
`auto-update-spec-kit-tests/` harness is extended in place rather than
duplicated, per FR-012's "existing harness" language. `watchdog.yml` gets
no new harness *directory* — Gate 19 is a single script, matching Gate 9's
precedent, not a multi-file `run-tests.sh` harness (that convention is
reserved for the auto-update suite's larger scenario count).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Principle VII: `watchdog.yml`'s `collect` job gains one new `workflow_call` output (a per-collector read-outcome value, consumed by the `diagnose` job) | FR-010/FR-016/FR-017 and User Story 5 require the diagnosis step to be told which collectors could not be trusted for the run being diagnosed — that information does not exist anywhere today and has to cross the job boundary the same way `signals` already does | Folding the read-outcome into the existing `signals` array (no new output) was considered and rejected in research.md D6: a "signal" is evidence *about the inspected run*, and a failed read is evidence about *the watchdog's own instrument*, not the run — conflating them would make `diagnose`'s per-signal reasoning (Out of Scope: untouched) have to special-case a signal kind that isn't really a signal. A same-shaped, separately-named output keeps `signals`'s contract exactly as published today (FR-015's "no other adopter-visible behaviour changes") and is the narrowest widening that satisfies FR-016. |
