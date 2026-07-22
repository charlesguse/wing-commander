# Quickstart: Validating Parameterized Model Overrides

Validation scenarios for spec 017, cross-referenced to the acceptance
scenarios in `spec.md` and the contract in
`contracts/model-override-points.md`. This repo has no unit-test harness for
workflow YAML (`research.md` Technical Context); validation is a mix of the
existing CI gate (`release.yml` Gate 1b) and manual/dogfooded checks, the
same validation style spec 016 used.

## Prerequisites

- A checkout of this repository (or a fork/adopting repo with its own
  `specify init` output) on a branch containing this feature's changes.
- `gh` CLI authenticated with repo scope, for setting repository variables
  and inspecting workflow runs.
- (Optional, for full end-to-end scenarios) A test issue with the
  `spec-request` label to drive a real pipeline run — expensive in agent
  cost, so scenario 2 below also documents a cheaper `actionlint`-only check.

## Scenario 1 — No overrides: identical default behavior (User Story 2, FR-005, SC-002)

**Setup**: Ensure none of the five variables in
`contracts/model-override-points.md` Layer 2 are set in the repository (or
run against a fresh fork with no variables configured).

**Steps**:
```bash
# Confirm every new/changed input's default matches contracts/model-override-points.md Layer 1
grep -A4 "escalation-model:" .github/workflows/implement.yml
grep -A4 "summary-model:" .github/workflows/implement.yml
```

**Expected**: `escalation-model` defaults to `claude-opus-4-8`;
`summary-model` defaults to `claude-haiku-4-5`. No other reusable stage
workflow's `model`/`summary-model`/`diagnose-model`/`propose-fix-model`
default changed from its pre-017 value (diff the eight reusable stage files
against the branch point and confirm no `default:` line under an existing
model input changed).

**Then**: Run (or dogfood) any stage end-to-end, including an `implement.yml`
cycle that hits its retry path (e.g. a spec whose first attempt fails
verification). Confirm the retry step still invokes `claude-opus-4-8` and the
progress comment step still invokes `claude-haiku-4-5` — i.e., behavior is
byte-for-byte identical to pre-017.

## Scenario 2 — Full override: every tier redirected (User Story 1, FR-001, FR-004, SC-001, SC-003)

**Setup**: Set all five repository variables to distinct, obviously-non-default
sentinel values (does not need to be real, invokable models — this scenario
only proves *routing*, not that the sentinel model runs successfully):

```bash
gh variable set WING_COMMANDER_SPEC_MODEL --body "sentinel-spec-model"
gh variable set WING_COMMANDER_PLAN_MODEL --body "sentinel-plan-model"
gh variable set WING_COMMANDER_SUMMARY_MODEL --body "sentinel-summary-model"
gh variable set WING_COMMANDER_IMPLEMENT_MODEL --body "sentinel-implement-model"
gh variable set WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL --body "sentinel-escalation-model"
```

**Steps** (cheap, no agent cost — static contract check): confirm every
Layer-1 input in `contracts/model-override-points.md` is reachable from a
Layer-2 variable by tracing the wrapper wiring:

```bash
grep -n "WING_COMMANDER_SPEC_MODEL" .github/workflows/wing-commander-1-intake.yml .github/workflows/wing-commander-2-clarify.yml
grep -n "WING_COMMANDER_PLAN_MODEL" .github/workflows/wing-commander-3-plan.yml .github/workflows/wing-commander-4-tasks.yml .github/workflows/wing-commander-rebase.yml
grep -n "WING_COMMANDER_SUMMARY_MODEL" .github/workflows/wing-commander-6-finalize.yml .github/workflows/wing-commander-7-cleanup.yml .github/workflows/wing-commander-5-implement.yml .github/workflows/watchdog.yml
grep -n "WING_COMMANDER_IMPLEMENT_MODEL" .github/workflows/wing-commander-5-implement.yml .github/workflows/watchdog.yml
grep -n "WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL" .github/workflows/wing-commander-5-implement.yml
```

**Expected**: Every grep above returns at least one match — no variable is
declared in `docs/setup.md` without a corresponding read in the wrapper
layer.

**Steps** (thorough, real run — do this at least once before merging):
Trigger a live pipeline run (e.g. a throwaway test issue through
`spec-request`, or `workflow_dispatch` on individual wrapper workflows where
supported) with the sentinels set, deliberately including an `implement.yml`
cycle that fails its primary attempt to exercise the retry/escalation path,
and watchdog's propose-fix path. Inspect each stage's step summary / job
logs for the `--model` value actually passed to `claude-code-action`.

**Expected**: Every stage's agent invocation — including the retry step and
watchdog's propose-fix step — uses its corresponding sentinel value, never a
literal from `contracts/model-override-points.md` Layer 1's default column.
(The run itself will fail at the API call, since the sentinel isn't a real
model — that failure, occurring *after* the correct model string was
selected, is sufficient evidence for this scenario; do not chase it further,
per spec.md's Assumptions: identifier validation is out of scope.)

**Cleanup**: `gh variable delete WING_COMMANDER_SPEC_MODEL` etc. for all five
sentinels — do not leave sentinel values configured on a working repository.

## Scenario 3 — Partial override: independence (FR-006, SC-004, Edge Case "Partial override")

**Setup**: Set only `WING_COMMANDER_SUMMARY_MODEL` to a sentinel; leave the
other four unset.

**Expected**: Stages/steps wired to `WING_COMMANDER_SUMMARY_MODEL`
(`cleanup.yml`, `finalize.yml`, `implement.yml`'s progress comment,
`watchdog.yml`'s diagnose step) use the sentinel; every other stage
(`intake`, `clarify`, `plan`, `tasks`, `rebase`, `implement`'s primary and
retry attempts, `watchdog`'s propose-fix) uses its documented default,
unaffected by the one variable being set.

**Cleanup**: `gh variable delete WING_COMMANDER_SUMMARY_MODEL`.

## Scenario 4 — Blank override falls back to default (FR-009, Edge Case "Empty / blank override")

**Setup**: `gh variable set WING_COMMANDER_PLAN_MODEL --body ""`.

**Expected**: `plan.yml`, `tasks.yml`, and `rebase.yml` all resolve to
`claude-sonnet-5` (the documented default) — not to an empty string passed as
`--model`. Confirm by inspecting the resolved `with: model:` value in the
wrapper's job output, or by checking that the `${{ vars.X || 'default' }}`
expression (or bash `${VAR:-default}`) is used everywhere in Layer 2, since
GitHub Actions expressions and bash parameter expansion both treat an empty
string as falsy/unset for this purpose.

**Cleanup**: `gh variable delete WING_COMMANDER_PLAN_MODEL`.

## Scenario 5 — Configuration is discoverable without reading pipeline internals (FR-007, SC-005)

**Steps**: Starting only from `docs/setup.md`, with a 5-minute timer, list
every model a run may select and its default.

**Expected**: All five Layer-2 variables from
`contracts/model-override-points.md` are listed in `docs/setup.md`'s
"Repository variables" table, each with a default matching the contract, and
the list is reachable without opening any `.github/workflows/*.yml` file.

## Scenario 6 — Maintainer audit: no literal remains (User Story 3, SC-001)

**Steps**:
```bash
grep -rn "claude-opus-4-8\|claude-haiku-4-5\|claude-sonnet-5\|claude-fable-5" .github/workflows/*.yml \
  | grep -v "default:" \
  | grep -v "^\S*:[0-9]*:\s*#"
```

**Expected**: Every remaining match is either a `default:` line (a
`workflow_call` input's documented fallback — allowed) or a prose comment
(already filtered above) — zero matches where a `claude-*` string is used
directly as a `--model` flag value, a `model:` field value, or a bash
variable assignment outside of an input's own `default:`.
