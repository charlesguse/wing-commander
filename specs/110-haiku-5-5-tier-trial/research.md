# Research: Haiku 5.5 Tier Upgrade and Measured Trial

No `[NEEDS CLARIFICATION]` markers remain in spec.md. Each "planning decides" item
from the spec is resolved below. Items marked **(assumption)** could not be
verified from the planning sandbox (read-only, no workflow dispatch) and have a
verification task in tasks.

## D1 — Does the pinned action accept `claude-haiku-5-5`?

**Decision**: Treat as accepted; verify with one real run before the model ID
changes anywhere else (first task of the implement stage). **(assumption)**

**Rationale**: Every call site passes the model as `--model <id>` inside
`claude_args`; `anthropics/claude-code-action@v1` hands it to the Claude Code CLI
and holds no model allowlist, as #970's move to `claude-opus-5-5` /
`claude-sonnet-5-5` showed. The helper entry in `per_model` already reports
`claude-haiku-5-5`, so the CLI knows the ID.

**Alternatives**: block the upgrade until a dispatch proves it (adopted as the
first task, not as a precondition of planning).

## D2 — The literal inventory (FR-001/FR-002/FR-004)

Pipeline-chosen `claude-haiku-4-5` in live files:

| File | Kind |
|---|---|
| `.github/workflows/implement.yml` (`summary-model` default) | stage input default |
| `.github/workflows/finalize.yml`, `cleanup.yml` (`summary-model` default) | stage input default |
| `.github/workflows/wing-commander-5-implement.yml`, `-6-finalize.yml`, `-7-cleanup.yml` (x2) | wrapper fallback |
| `.github/workflows/auto-update-spec-kit.yml` (T026, `--model` and its comment) | hardcoded |
| `.specify/memory/constitution.md` Principle II | prose |
| `docs/setup.md` (2), `docs/adoption.md` (2), `docs/architecture.md` (3) | prose |

`watchdog.yml`'s `diagnose-model` is already Opus. `.wing-commander-pipeline/` is a
self-checkout copy created at run time, not a tree to edit.

**Decision (FR-002)**: T026 stays a literal `claude-haiku-5-5`; no new input.
**Rationale**: auto-update-spec-kit.yml is a consuming-instrument workflow for this
repository's own Spec Kit upgrades; a new input would widen the published contract
(VII) for no adopter benefit. The FR-006 check closes the "silently superseded" gap.

**Variable**: `WING_COMMANDER_SUMMARY_MODEL` — read with `gh variable list` by the
implementer; if set to `claude-haiku-4-5`, delete it with the change (#970 precedent).
Planning cannot read repository variables. **(assumption: unset, per spec)**

## D3 — Turn budgets for existing Haiku steps (spec assumption)

**Decision**: Leave the budgets unchanged (progress comment 15, finalize/cleanup 20,
T026 8). **Rationale**: ~30% more tokens does not change the turn count of
single-purpose summary steps; the agent-verdict guard already reports exhaustion, and
SC-002's post-merge re-drive observes it.

## D4 — Requests Haiku 5.5 rejects with a 400

**Decision**: No change. `grep` for `thinking`, `budget_tokens`, `temperature`,
`top_p`, `prefill` and computer-use in `.github/` is a task (T-audit); the workflows
only pass `--model`, `--max-turns`, `--allowedTools`, `--disallowedTools`,
`--json-schema`, so Claude Code builds the request. **(assumption until the grep runs)**

## D5 — How the constitution amendment reaches `main` (FR-003)

**Decision**: A separate amendment PR against `main`, as spec 062 did, containing
only `constitution.md` (2.3.1 → 2.4.0), the Sync Impact Report moved to the top of
`constitution-history.md`, and the Principle II edits. It merges before the lifecycle
PR. The lifecycle PR contains no constitution edit.
**Rationale**: Principle V — the bot never merges an amendment; Governance — amend
first. The FR-006 check covers `constitution.md`, so the check lands on `main` only
after the amendment.
**Alternative rejected**: carry the amendment in the lifecycle PR (would let the
lifecycle merge gate land it).
**Consequence for tasks**: the implement stage cannot open or merge the amendment PR
itself without breaking its "edit only inside specs/" style limits for plan/tasks, but
implement may write the amendment text to a branch; a task hands the PR to the owner.
The tasks stage records this as a manual step reported on the lifecycle issue (IV).

## D6 — FR-006 check design

**Decision**: New gate `verify-haiku-tier-model-id.py`, registered in the gate
registry and wired to lint-workflows.yml like its siblings. It scans
`.github/workflows/`, `.github/actions/`, `.specify/memory/constitution.md`, `docs/`
for `claude-haiku-4-5` (any suffix, including `-20251001`; after this change nothing
remains in scope, so any hit fails). It does not scan `.github/scripts/` fixtures,
`constitution-history.md`, `specs/`. Failure branches have checked-in fixtures
(Principle VIII): a workflow hit, a docs hit, a constitution hit, an empty scan root
(fails loudly rather than passing).
**Alternative**: extend an existing model-pin gate — none exists for the Haiku tier
(spec FR-005).

## D7 — Shadow placement and the shared-prompt problem (FR-008, FR-009)

**Decision**: Run the shadow as a second agent step in the existing `diagnose` job,
after the acting path has finished everything it publishes (read-back, findings
upload, metrics record), `continue-on-error: true`, `timeout-minutes: 5`, read-only
allowlist, `GH_TOKEN` = `github.token` (job `permissions` read-only for the step's
purposes). The prompt and `claude_args` move to a new composite
`wing-commander-diagnose-agent` that both the acting and shadow steps call with
different `model`, `max-turns`, `output-name`. The class-vocabulary schema step is
already a step output and is reused unchanged.
**Rationale**: a separate job would need the vocabulary and signals steps duplicated;
a pasted 140-line prompt violates "shared logic has one home". The acting step's
timeout (10 min) + shadow (5 min) stays under the job backstop (20 min), so a hung
shadow cannot cost the acting path its outputs (SC-003).
**Risks**: (a) gates that scan workflows for `claude-code-action` steps (Gate 68's
timeout exemption, the verdict/metrics pairing gates) may not look inside composites.
Task order handles this: an extraction-only commit with the gate suite green
precedes any shadow code. (b) A second claude-code-action in one job rewrites
`$RUNNER_TEMP/claude-execution-output.json`; the shadow step runs last and its
transcript is copied to `claude-execution-output-diagnose-shadow.json` before upload.
(c) The action's post-step credential handling (Gate 68) must be re-checked.
**Fallback if extraction proves unworkable under the gates**: paste the prompt into
the shadow step and add a byte-equality gate between the two blocks (the repo's
existing "gates byte-compare comments" practice), recorded as a decision in tasks.

## D8 — Trial record shape (FR-011)

**Decision**: The shadow produces a normal metrics record through
`wing-commander-metrics-summary` with `run-label: diagnose-shadow` and `stage:
watchdog`, so it has its own `record_key` and `run_label` and satisfies the schema
(`schema_version` 1). A new composite `wing-commander-trial-record` then adds one
additive top-level object `trial` before upload:

```
"trial": {"step":"watchdog.diagnose","candidate_model":"claude-haiku-5-5",
          "baseline_run_label":"diagnose","outcome":"agreed|disagreed|exhausted|malformed|error|refused|no-baseline",
          "filing_agree":true|null,"class_agree":{"shared":N,"agree":M}|null,
          "differing_fields":["..."], "baseline_verdict":"..."}
```

`outcome` (top level) keeps its agent-verdict meaning. The artifact is named
`metrics-record-diagnose-shadow` so persist's `*.json` sweep picks it up. The
existing turn-budget trend collector filters by `run_label`; implement verifies it
ignores `diagnose-shadow` and adds a fixture if it does not.

**Refusal**: the verdict composite does not distinguish `stop_reason: "refusal"`.
**Decision**: `wing-commander-metrics-summary` writes an additive boolean `refusal`
(true iff the transcript's terminal result carries `stop_reason == "refusal"`);
`compare-diagnose-shadow.py` and the summary read it. Implement-trial cycles get it
through the same composite, so no separate implement trial record is needed (FR-011
"may be the cycle's normal metrics record").

## D9 — Deterministic comparison (FR-010, Principle IX)

**Decision**: `.github/scripts/compare-diagnose-shadow.py` takes the two structured
results (Opus findings array, shadow findings array) plus both verdicts and emits the
`trial` object. Rules, in order: Opus verdict not `healthy` → `no-baseline`; shadow
`refusal` → `refused`; shadow verdict `exhausted` → `exhausted`; shadow failed/rate
limited/infra → `error`; shadow output fails the same JSON schema as Opus →
`malformed`; else compare. Filing agreement is equality of the sets of `(class, signalId set)`
keys — "the same findings would be filed, or nothing would be" — and class agreement is
over findings sharing a signalId set: fraction with equal `class`. `__new__` classes
compare by `proposedClass` normalised. Differing fields list the finding keys present
on one side only and shared keys whose class differs. Fixtures cover each outcome.

## D10 — Bound and switch (FR-012, FR-013, SC-006, SC-007)

**Decision**: One repository variable `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE`
(ISO date) is the single switch: unset = off (default for adopters and for this
repository until the owner sets it; FR-016 does not forbid enabling it). A
deterministic composite `wing-commander-trial-bound` runs in the wrapper
(`wing-commander-8-watchdog.yml` and `-8b-`), reads the metrics branch's
`records.jsonl`, counts records with top-level `run_label == "diagnose-shadow"`,
`trial.outcome` not in `{error, no-baseline}` and `emitted_at >= SINCE`, and outputs
`enabled = SINCE set && today < SINCE + 60d && compared < 300`. The wrapper passes it
as new `watchdog.yml` input `diagnose-shadow-enabled` (boolean, default false). The
stage reads no `vars.*` for it (VII; watchdog.yml's existing documented `vars.*`
exception is not extended). Restarting = setting a new SINCE.
**Race**: concurrent watchdog runs can overshoot 300 by a few records; accepted and
stated — "at most 300" is enforced to within the runs in flight.
**Alternative rejected**: a counter variable (writes a repo variable per run; needs
a credential scope the watchdog does not hold).

## D11 — Implement opt-in (FR-014)

**Decision**: Wrapper 5's `resolve-model` job: after computing the default tier, if
the lifecycle issue has `model:haiku` and not `model:opus` → `model=claude-haiku-5-5`,
`escalation-model=claude-sonnet-5-5`; `model:opus` wins; `model:haiku` alone no-ops
when `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` is unrelated (the Haiku case forces
Sonnet for the retry; the variable still governs non-Haiku cycles). The `escalation-
model` output becomes step-computed rather than a bare `vars` expression.
The wrapper passes `max-turns`. implement.yml is unchanged: `model` and
`escalation-model` are existing inputs, so no contract widening.
**Turn budget**: 180, the same as Sonnet's measured default (implement.yml comment:
real work median 153 turns, p75 182). There is no Haiku 5.5 data yet; a tighter
number would only manufacture exhaustion, and the value also budgets the Sonnet
retry. The wrapper's `resolve-model` job outputs `max-turns` always: Haiku cycles
get `vars.WING_COMMANDER_IMPLEMENT_HAIKU_MAX_TURNS || '180'`; other cycles get the
literal `180`. That literal repeats implement.yml's input default, which is a second
home for the number; a gate asserting the two are equal (extending the nearest
existing input-default gate, else a small new one) is the price of not widening
implement.yml. Alternative rejected: omit `max-turns` for non-Haiku cycles, which a
`with:` expression cannot do for a typed number input.
**pr-conversation / board loop**: they grep only `model:opus`; the change adds a gate
fixture asserting neither greps `model:haiku` nor treats it as Opus. finalize's label
mirroring is checked, not changed.

## D12 — Trial summary (FR-015, Story 4)

**Decision**: `.github/scripts/trial-summary.py` reads `records.jsonl` and prints
markdown; a `workflow_dispatch`-only wrapper `wing-commander-trial-summary.yml`
checks out the metrics branch and writes it to the job summary. Diagnose: groups
records by `run_label` `diagnose` vs `diagnose-shadow`, joins on the shadow's
`trial` object, reports runs, agreement, refusal/exhaustion counts, median turns, cost
per run per model, and "meets"/"misses"/"sample too small" at 200 compared runs per
FR-017. Implement: records with `stage == implement`, top-level `model ==
claude-haiku-5-5`, grouped by `spec.issue`, against the median Sonnet lifecycle;
no verdict. Model identity is always the top-level `model`, never `per_model`.
Fixtures include a Sonnet record with a `claude-haiku-5-5` helper `per_model` entry
that must not count.

## D13 — Gates and docs

New gates (each with failure fixtures, registered, wired to lint-workflows.yml):
`verify-haiku-tier-model-id.py`; `verify-diagnose-shadow-acts-on-nothing.py` (the
shadow step has no write tools, uses `github.token`, runs after the acting outputs,
is `continue-on-error`); `verify-compare-diagnose-shadow.py` (comparator fixtures);
`verify-trial-bound.py`; `verify-trial-summary.py`. Docs: `docs/setup.md` (new
variable, label), `docs/adoption.md` (new `watchdog.yml` inputs), `docs/architecture.md`.
