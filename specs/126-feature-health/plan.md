# Implementation Plan: Feature Health

**Branch**: `126-feature-health` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/126-feature-health/spec.md`

**Layer**: consuming instrument (Principle VII). One repository-only scheduled workflow, its scripts, one registry file, and the content of one section of the "Board status" issue, which that issue's one writer publishes. Nothing is added to the `workflow_call` published contract.

## Summary

A daily, read-only, agent-free workflow reads the last 30+ days of run history for each feature in a single registry, reads each feature's declared output signal, and classifies every feature (and each lifecycle stage) into exactly one of eight states: *unreadable, paused, not configured, failing, not running, quiet, idle, healthy*. It hands a Markdown section (call-outs above, full table collapsed beneath) to `board-status.yml`, whose writer publishes it. It files nothing and starts no run.

Technical approach (decisions in [research.md](research.md)):

1. **Classifier as pure code** (D1, D7). `wc_feature_health.py` has a pure half (state rules, worst-of, rendering) taking readings and an injected `now`, and a runtime half (`collect`, `build`) that reads through `gh` and fails loudly on an incomplete read, marking only the affected feature *unreadable*.
2. **One registry** (D2). `.github/scripts/feature-health-registry.json`; `verify-feature-health.py` fails when reference.md lists a workflow with no entry, an entry names a missing workflow or an unknown kill switch.
3. **Complete reads** (D4). Date-bounded run listing per workflow, sliced by day past the 1,000-run cap, else *unreadable*.
4. **Signals from the repository's own records** (D5), reusing marker/branch/ground constants from the scripts that own them (`board_triage.py` for the triage grounds).
5. **Publication by hand-off** (D3, D8). New workflow `wing-commander-feature-health.yml` (daily 06:29 UTC, dispatch from the default branch only, read permissions, own concurrency group, pause step first) uploads artifact `feature-health-section`. `wc_board_status.py` gains `feature_health_snapshot()`, a `SWITCH_ENV` entry for `WING_COMMANDER_FEATURE_HEALTH_PAUSED` and the section render; `board-status.yml` gains the env line. This mirrors spec 124's proof-list hand-off.
6. **SC-001 replay** (D9) from a checked-in corpus captured by a `[maintainer]` task, with a pending exemption until then.
7. **Docs** (D10, FR-016).

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, as `wc_board_status.py`); GitHub Actions YAML; bash only for `gh` glue

**Primary Dependencies**: `gh` CLI (REST via `gh api`, `gh run download`), PyYAML. Reused, not copied: `wc_board_status` (`_switch_on`, `SWITCH_ENV`, snapshot/render/publish), `board_triage` (triage grounds), the proof-list hand-off pattern, `wc_shell_harness.gh_error_stub_arm` for error fixtures.

**Storage**: none of its own; 7-day artifact, then the Board status section.

**Testing**: checked-in fixtures drive `verify-feature-health.py` (new, an unnumbered `lint-workflows.yml` step, as `verify-proof-list.py` is, derived by `wc_gate_registry`), `verify-board-status.py` (extended). Fixtures in `.github/scripts/fixtures/feature-health/` already sit inside the suite's trigger paths.

**Target Platform**: GitHub-hosted `ubuntu-latest`

**Project Type**: repository automation (scripts + one workflow + gates)

**Performance Goals**: within a 15-minute job timeout for about 20 features / 35 workflows and some thousands of runs.

**Constraints**:
- No durable write other than the artifact; no agents; no dispatches; no issue/PR writes (FR-012, FR-013).
- A reading that fails marks that feature *unreadable*; never classify from a partial read (FR-010).
- API budget: about 40-80 REST calls per build (run listings at `per_page=100`, a handful of signal reads); `rate_limit` checked first, failing below a floor like the proof list's.
- Section fits the issue body (`MAX_BODY_UNITS`).

**Scale/Scope**: about 20 features, 35 workflows, about 1,000+ runs per hot wrapper per 30 days (board loop alone ~790).

## Constitution Check

*Passed pre-research; re-checked after design — still passes.*

| Principle | Outcome |
|---|---|
| I Guide | Built through the pipeline; PR cites this spec. Pass |
| II Model tiering | No Claude invocation (FR-012). Pass (n/a) |
| III GitHub-native | Report is a section of an existing issue, read with `gh`; hand-off is an Actions artifact. Pass |
| IV Automation-first | Scheduled; pausing uses a variable only the owner creates. Pass |
| V Security | No agent; run/issue/PR text is parsed as data (conclusions, timestamps, labels, markers) and never reaches the report except feature names from the registry and fixed reason strings. No write permission, `persist-credentials: false`, default-branch-only dispatch. Pass |
| VI Portability | No hardcoded repo or branch name; default branch from the API/event; features come from the registry. Pass |
| VII Two interfaces | Repository-only wrapper, not `workflow_call`. Pass |
| VIII Green check | Every branch has a fixture, including each failed read and the all-unreadable build failure; the registry drift gate has a failing fixture; a read that fails never reads healthy. Pass |
| IX Deterministic judgment | All classification is code; `now` injected. Pass |
| X Bounded autonomy | Files nothing, acts on nothing. Pass |

No violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/126-feature-health/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── feature-health-report.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── wing-commander-feature-health.yml   # new: schedule + dispatch; refuse, pause step, build, upload
│   ├── board-status.yml                    # gains FEATURE_HEALTH_PAUSED env line
│   └── lint-workflows.yml                  # gains the unnumbered verify-feature-health.py step
└── scripts/
    ├── wc_feature_health.py                # new: pure classifier/renderer + collect/build
    ├── feature-health-registry.json        # new: the one registry
    ├── wc_board_status.py                  # gains SWITCH_ENV entry, feature_health_snapshot(), section render
    ├── verify-feature-health.py            # new gate: fixtures, registry drift, workflow file, SC-001 replay
    ├── verify-board-status.py              # gains the writer's feature-health paths
    └── fixtures/feature-health/            # synthetic cases; sc001/ from the [maintainer] capture only
docs/reference.md, docs/setup.md, README.md # FR-016
```

**Structure Decision**: same as the proof list: pure and runtime halves in one script, one workflow, the existing writer publishes. The registry is JSON so both the build and the gate read it with the stdlib.

## For the tasks stage

Each line is a requirement on `tasks.md`.

- **Ordinary tasks** (implement-buildable):
  - Registry file and `verify-feature-health.py` drift checks (D2) with `EXEMPT_UNREGISTERED` citing #889, table passed as a parameter (Gate 124 forbids mutating `EXEMPT_*` names).
  - `wc_feature_health.py` pure half: `classify_workflow`, `classify_feature`, `render_section`; one fixture per state and rule listed in quickstart.md step 1, each failing without the code it tests.
  - Runtime half: date-sliced run reader, signal readers per kind, variables/switch reads; failed reads become *unreadable*; all-unreadable fails the build (FR-010).
  - `wing-commander-feature-health.yml` (refuse non-default-branch dispatch first, pause step, checkout `actions/checkout@v5` with `persist-credentials: false`, build with `GH_TOKEN: ${{ github.token }}`, upload; later steps gated by `success()` only, no `always()`).
  - `wc_board_status.py` / `board-status.yml` extension; `verify-board-status.py` fixtures (`SNAP` gains `feature_health`; artifact name constant checked against the upload step; error stubs via `wc_shell_harness.gh_error_stub_arm`; `_switch_on` is called, not reimplemented).
  - A `review-step-gating` pass over the new workflow and the `board-status.yml` change.
  - SC-001 replay check with `EXEMPT_SC001_PENDING` citing #889. The implement stage must not create or edit `corpus.json` or `expected.json`.
  - **Docs task**: reference.md (board-status row, new Housekeeping row, Kill switches, Schedules 06:29, At a glance), setup.md §3 row for the new variable, README workflow list.
- **Final "Maintainer follow-up" phase**, each line tagged `[maintainer]`:
  - `[maintainer]` Capture the SC-001 corpus and expected file from a local session with full history and `gh` auth; scrub private names; delete `EXEMPT_SC001_PENDING`'s entry in the same commit.
  - `[maintainer]` Create `WING_COMMANDER_FEATURE_HEALTH_PAUSED` only if the owner wants it; then after-merge proof as quickstart.md step 3 lists.
