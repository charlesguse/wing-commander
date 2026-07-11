# Phase 0 Research: Per-Run Agent Metrics (Tier 1)

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — the committed scope
is unambiguous (FR-012: tier 1 only, User Story 1). This document resolves
the *technical* unknowns needed to turn that scope into a plan, each as
Decision / Rationale / Alternatives. One decision (D6) is made without a
clarifying answer from a human and is called out in the plan PR body per
the CI deviation rules.

## D1 — No agent call: a deterministic post-step (FR-001, FR-011)

**Decision**: Metrics extraction and summary rendering run as plain
`bash`/`jq` in a normal `run:` step — no `anthropics/claude-code-action@v1`
invocation anywhere in this feature.

**Rationale**: Every field the spec asks for (model, turns, duration,
tokens, cost) is already structured JSON in the execution transcript; there
is nothing here that benefits from a language model, and FR-011 requires
metrics surfacing to be strictly read-only with respect to the agent's own
work. Constitution II's tiering table (`claude-haiku-4-5` for "triage,
classification, labeling, and summaries") describes *natural-language*
summarization tasks (e.g. `speckit-6-finalize.yml`'s diff-to-prose step);
turning `.num_turns` into "36/80 turns" is arithmetic, not summarization,
so no tier applies — the cheapest and most reliable choice is no model at
all. This also matches the repo's own idiom for "verify a fact, don't spend
turns on it" (e.g. `speckit-3-plan.yml`'s "Verify plan PR and flip stage
label" step, `speckit-5-implement.yml`'s "Read back cycle outcome" step).

**Alternatives considered**: A `claude-haiku-4-5` step that reads the
transcript and writes the summary — rejected: adds cost, latency, and a
turn budget of its own to a task with no ambiguity to resolve, and would
itself need a `claude-execution-output.json` upload/summary, infinitely
recursing on the very thing this feature measures.

## D2 — Shared logic lives in one composite action (FR-001–FR-005)

**Decision**: New composite action `.github/actions/speckit-metrics-summary`
(`runs: using: composite`), parallel to the repo's only existing composite,
`.github/actions/speckit-context`. Every agent-invoking workflow adds one
`uses: ./.github/actions/speckit-metrics-summary` step immediately after
each `claude-code-action` step, `if: always()`.

**Rationale**: The extraction/rendering logic (parse JSON, compute the
used/budgeted ratio, apply the warning threshold, format the summary block,
handle missing/malformed input) is identical across all nine call sites
across eight workflow files (`speckit-1` through `speckit-7`, plus
`speckit-rebase.yml`); duplicating ~40 lines of `jq`/bash nine times would
mean nine places to fix the same bug. `speckit-context` already establishes
the "shared composite action, consumed the same way by every stage" pattern
this repo uses for cross-cutting concerns.

**Alternatives considered**: A shared shell script under
`.specify/scripts/bash/` invoked identically from every workflow —
rejected: those scripts are explicitly spec-kit's own portable surface
(constitution VI); this feature is pipeline-internal tooling, not something
`/speckit-*` skills need, so a `.github/actions/` composite (already the
home for pipeline-internal shared logic) is the better fit. Inlining the
same `run:` block nine times via a copy-paste — rejected for the
duplication reason above and because it's the one thing composite actions
exist to solve.

## D3 — Placement: once per agent invocation, before the next one in the same job (FR-008)

**Decision**: The new step runs immediately after its corresponding
`claude-code-action` step and *before* any other agent step that could run
later in the same job. Concretely:

- Single-invocation stages (intake, clarify, plan, tasks, finalize,
  cleanup, rebase's per-matrix-entry conflict step): one metrics step,
  right after the one agent step, `if: always()` (so a failed/timed-out
  agent step still gets a metrics line — FR-009).
- `speckit-5-implement.yml`, which can run up to three agent invocations in
  one job (primary "cycle" attempt, conditional opus "retry" attempt,
  conditional haiku "progress comment"): **three** separate metrics steps,
  one after each, each reading the runner's shared temp file at the moment
  right after its own invocation and before the next one overwrites it.

**Rationale**: The execution transcript always lands at the same fixed
path, `${{ runner.temp }}/claude-execution-output.json` — this is the
`claude-code-action`'s own output location, not something a stage
controls, and it is **not** disambiguated per invocation within a job. The
existing "Upload Claude execution log (cycle)" / "(retry)" steps in
`speckit-5-implement.yml` already prove this constraint out: they run
immediately after their respective agent steps specifically so the next
invocation's transcript doesn't clobber the one just uploaded. Metrics
extraction has the exact same ordering requirement, so it piggybacks on
the same placement discipline rather than inventing a new one.

**Alternatives considered**: One metrics step at the end of the job reading
whatever transcript happens to remain — rejected outright: it would only
ever report the *last* invocation's metrics, silently dropping the
earlier ones, which directly violates FR-008 and the spec's own edge case
("each agent invocation is treated as its own run... not just the last").

## D4 — The haiku progress-comment invocation gets a summary too (FR-008, edge case)

**Decision**: Add a fourth (new) metrics step after `speckit-5-implement.yml`'s
"Post progress comment (haiku)" step, even though that invocation currently
has **no** `claude-execution-output` artifact upload at all.

**Rationale**: FR-008 and the spec's edge case are explicit that *every*
agent invocation gets its own per-run summary, not just the ones that
happen to already have artifact uploads today. Tier 1 only requires a
`$GITHUB_STEP_SUMMARY` line (FR-002), not a durable artifact, so this is
achievable without also adding a new upload step for that invocation —
uploading the transcript remains a separate, pre-existing concern this
feature doesn't need to touch.

**Alternatives considered**: Skipping the haiku step because "it's just a
progress comment" — rejected: the spec draws no such distinction, and a
haiku step consuming an unexpectedly large number of turns is exactly the
kind of budget drift Story 1 exists to surface.

## D5 — Turn budget comes from the workflow, not the transcript (FR-003, FR-005)

**Decision**: The composite action takes the run's configured `--max-turns`
value as an explicit input (`max-turns`), supplied literally by each call
site from the same value already hardcoded in that step's `claude_args`
(e.g. `50` for intake, `80` for plan, `100` for implement, `15` for the
haiku progress comment). The input is optional; when omitted, the summary
reports turns used and omits the ratio and the warning entirely (spec.md
edge case: "stage was configured without a discoverable turn budget").

**Rationale**: The execution transcript records turns *used*
(`.num_turns` on the final `result` record, confirmed by this repo's own
existing parse at `speckit-5-implement.yml`'s "Extract agent final
message" step) but never the turn *budget* — `--max-turns` is a CLI flag
baked into the workflow YAML at author time, not part of the agent's own
output. Every current call site already declares `--max-turns` as a literal
(constitution II: "Every agent step sets `--max-turns`"), so passing that
same literal into the new composite action's input costs nothing and keeps
the budget check accurate without inventing a way to "discover" a value
that isn't actually recorded anywhere else.

**Alternatives considered**: Parsing `--max-turns` back out of the
`claude_args` string the step itself passed to `claude-code-action` —
rejected as needlessly indirect (the value is already known at the call
site; re-parsing it from a multi-line string it's embedded in adds
fragility for no benefit). Requiring every call site to hardcode a budget —
rejected: the input's optionality is exactly what lets FR-005's "no
discoverable budget" edge case degrade gracefully instead of forcing a
fabricated value.

## D6 — Field extraction is defensive; exact upstream field names are a documented assumption

**Decision**: The composite action extracts each metric independently with
a `jq ... // empty`-style fallback per field (model, `num_turns`,
`duration_ms`, `total_cost_usd`, and a best-effort read of token usage and
any per-model breakdown), and renders "unavailable" for any field that
comes back empty, rather than failing the step. Field names are taken from
spec.md's own worked example (`num_turns`, `duration_ms`,
`total_cost_usd`, "token usage," "a per-model breakdown") — the only
concrete reference available, since no schema fixture, sample artifact, or
upstream schema documentation exists in this repository, and this
CI-driven planning session had no network access to confirm the exact
upstream `claude-code-action`/Claude Code `--output-format json` schema
against live documentation. The one field this repo's own code already
relies on (`.result`, the free-text final message on the last
`.type == "result"` record — `speckit-5-implement.yml`'s "Extract agent
final message" step) is confirmed and reused as the anchor for finding
that record; the metrics fields sit on the same record.

**Rationale**: FR-009 already requires the system to degrade to "metrics
unavailable" on any missing/malformed data rather than fail the stage, so
defensive per-field extraction is the correct design regardless of whether
every field name turns out to be exactly right — a wrong or renamed field
simply reports as unavailable instead of breaking anything. This is safer
than hardcoding a rigid schema that would either error or silently misreport
if a field name differs from expectation.

**Decision made without clarification** (to flag in the plan PR body): the
exact JSON paths for token usage and the per-model breakdown are an
assumption, not a confirmed contract. The tasks phase should verify the
real field names — by inspecting a `claude-execution-output` artifact
downloaded from one of this repository's own past workflow runs (several
already exist, e.g. the runs spec.md itself references) — before or while
implementing the composite action, and adjust the `jq` paths if the live
schema differs from this assumption. Because every field is extracted
defensively (this decision) and the summary is purely informational
(spec.md Assumptions), a wrong field name degrades to "unavailable"
rather than causing incorrect data to be reported as if it were reliable.

**Alternatives considered**: Blocking planning on confirming the exact
schema first — rejected: it would stall the plan stage on information not
obtainable in this environment, when the spec's own FR-009 already makes
the design robust to the field names being slightly off. Hardcoding a
single rigid `jq` path per field with no fallback — rejected: a schema
mismatch would either error (violating FR-009) or, worse, silently pull
the wrong value.

## D7 — Warning-fraction default, kept simple

**Decision**: The 80% warning fraction (FR-004) is a constant inside the
composite action, exposed as one optional input (`warn-fraction`, default
`0.8`) rather than a repository variable or per-stage override.

**Rationale**: Spec.md states 80% is "a tunable default, not a fixed
requirement" but does not ask for a configuration surface, and no stage
currently needs a different value. An input keeps the door open for a
future call site to pass something else without inventing unused
infrastructure (a repo variable, a label) that nothing reads yet —
consistent with not designing for hypothetical requirements beyond what's
asked.

**Alternatives considered**: A repo variable like the existing
`SPECKIT_IMPLEMENT_MODEL`/`SPECKIT_TASKS_REVIEW` pattern — rejected as
premature: those vars back an actual per-repo behavioral choice documented
in the constitution/architecture; no such choice exists yet for the warning
fraction.

## D8 — Output surface: `$GITHUB_STEP_SUMMARY` only (FR-002, FR-010, SC-006)

**Decision**: The composite action appends a small Markdown block to
`$GITHUB_STEP_SUMMARY` and nothing else — no new artifact, no issue
comment, no external call. Tiers 2/3 (lifecycle-issue rollup, durable
trend record) are explicitly out of scope (FR-012) and are not stubbed or
partially built.

**Rationale**: `$GITHUB_STEP_SUMMARY` is the surface every existing stage
already writes deterministic, human-readable status to (e.g.
`speckit-3-plan.yml`'s "Plan PR #$pr opened..." line); it satisfies FR-002
("attached to that stage's own workflow run") and SC-006/constitution III
(GitHub-native, no dashards) with zero new infrastructure.

**Alternatives considered**: Also posting to the lifecycle issue — this is
exactly tier 2 (FR-006), explicitly deferred; building it now would
contradict FR-012's scope line and the spec's own tiering rationale
(each tier is independently valuable and separately shippable).

## D9 — Verification approach

**Decision**: Same as every other stage in this repo — no automated test
suite; `quickstart.md`'s scenarios are run by hand: a real workflow
dispatch for the happy path, and the composite action invoked directly
against hand-crafted fixture transcripts (valid, missing, empty, truncated,
partial-fields) for the edge cases, since those are impractical to trigger
live against a real agent run on demand.

**Rationale**: Consistent with stages 1–8 (`specs/00{1,2,3,5,6,7,8}-*`,
`004-clarify-on-pr`), none of which have an automated test framework for
GitHub Actions workflow bodies; a composite action's shell logic can still
be exercised locally (e.g. `bash` sourcing its `run:` steps against a fixture
file) without needing the full Actions runtime, which is the same
verification depth those stages' deterministic steps received.

**Alternatives considered**: Standing up a workflow-testing framework
(e.g. `act`) for this feature alone — rejected as disproportionate to a
handful of `jq` calls, and inconsistent with every prior stage's approach.
