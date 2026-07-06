# Phase 0 Research: Tasks Stage — Plan to Task List

`spec.md` for this feature has no `[NEEDS CLARIFICATION]` markers (confirmed
by `checklists/requirements.md`): the two review modes and their hand-off
behavior are already fully determined by `docs/architecture.md`'s Stage 3
section. The items below are implementation-level decisions the spec
deliberately left open ("this specification concerns when and how task
generation is triggered, reviewed, and reported, not the task list's internal
format") and that a plan must pin down before tasks can be generated.

## Decision: Trigger shape and spec-identity resolution

**Decision**: Reuse the plan stage's pattern exactly. Trigger on
`pull_request: closed` with `branches: ["spec/**"]` and `paths: ["specs/**"]`
(already in the stub), gated in the job's `if:` on
`merged == true && startsWith(head.ref, 'plan/')`. Resolve the slug by
stripping the `plan/` prefix from `head.ref` and validating it against
`^[0-9]{3}-[a-z0-9][a-z0-9-]*$`; refuse (FR-012) rather than guess if it
doesn't match, or if `specs/$slug/spec.md`, `spec-meta.json`, or `plan.md`
are missing from the `spec/$slug` branch.

**Rationale**: The base branch (`spec/**`) is exactly the persistent
per-spec branch this stage acts on, and the head prefix (`plan/`) is exactly
what the plan stage names its work branches — the same head-prefix-guard
idiom the plan stage uses against `spec-draft/` PRs into `main`. No new
resolution mechanism is needed.

**Alternatives considered**: Parsing the lifecycle issue number out of the
PR body — rejected; `spec-meta.json` on the `spec/$slug` branch is already
the durable source of truth and requires no string-parsing of free text.

## Decision: Idempotency mechanism (FR-011)

**Decision**: Before generating anything, read `stage` from
`specs/$slug/spec-meta.json` on the `spec/$slug` branch. Proceed only if
`stage == "plan"` (the expected predecessor per the constitution's
"a stage may only start when its predecessor's gate has passed"). If `stage`
is already `"tasks"` or later (or `"stalled"`), treat the event as a
duplicate/late notification: log a step-summary note and exit the job
successfully without generating a second task list, PR, or dispatch. In `pr`
review mode, additionally check for an existing `tasks/$slug` branch before
creating one (mirroring the plan stage's `plan/$slug` duplicate-branch
check) so two near-simultaneous merge notifications can't race to open two
review PRs.
Additionally, `concurrency: { group: speckit-tasks-<slug>, cancel-in-progress: false }`
on the job serializes same-spec runs so the second of two duplicate events
observes the first one's completed state change rather than racing it.

**Rationale**: `stage` is already the durable, machine-checked field the
plan stage itself writes and the constitution's stage-gate language
describes; checking it is cheaper and more robust than trying to fingerprint
"the same merge event" (PR merges are not naturally idempotent identifiers
across redeliveries).

**Alternatives considered**: Tracking processed PR numbers in a side file —
rejected as an unnecessary second source of truth alongside `spec-meta.json`.

## Decision: Review-mode branch/PR naming

**Decision**: The review-required mode's task-list PR uses branch
`tasks/NNN-slug` (parallel to `plan/NNN-slug`, `impl/NNN-slug-iterN`) and
targets `spec/NNN-slug`, exactly as `docs/architecture.md` names it.

**Rationale**: Consistent with the constitution's documented branch
conventions and the existing naming family; no new convention introduced.

## Decision: Issue comment authorship (no separate haiku summarization step)

**Decision**: The same `claude-sonnet-5` agent step that runs `/speckit-tasks`
also writes the lifecycle issue comment (total task count, per-story
breakdown, MVP scope — all present in `/speckit-tasks`'s own completion
report) and, in `pr` mode, the review PR body. No separate `claude-haiku-4-5`
summarization step is added for this.

**Rationale**: The plan stage sets the precedent — its own sonnet planning
step authors the plan PR body and issue comment directly, with haiku
reserved (per constitution II and `docs/architecture.md`'s model-tiering
table) for "triage, diff summaries, labels" — i.e. stages 5/6 where a
*separate* agent summarizes a diff/log it didn't produce. Here the content
being summarized (the tasks.md the same agent just wrote) doesn't need a
second model invocation.

**Alternatives considered**: A haiku post-step summarizing `tasks.md` after
the fact — rejected as an unjustified extra agent invocation for content the
authoring step already has fully in context.

## Decision: Dispatching the implementation stage

**Decision**: `gh workflow run speckit-5-implement.yml -f spec_dir=specs/$slug -f issue=$issue -f iteration=1`,
run as a deterministic (non-agent) step after the tasks commit is verified
(`auto` mode) or after the tasks PR is verified merged (`pr` mode) —
analogous to the plan stage's deterministic "verify PR exists, then flip
label" step that spends no agent turns on mechanical verification.

**Rationale**: Matches `docs/architecture.md`'s Stage 3 design verbatim and
the plan stage's existing pattern of doing verifiable, mechanical steps
outside the agent invocation.

**Alternatives considered**: Having the Claude agent itself run
`gh workflow run` — rejected; dispatch is a pure mechanical action gated on
a verifiable fact (tasks.md committed / PR merged), so it belongs in a
deterministic step, not inside the agent's own turn budget.

## Decision: Stalled path (FR-013)

**Decision**: A second job in the same workflow file, gated on
`pull_request: closed` with `merged == false` and `head.ref` starting with
`tasks/`, sets `spec-meta.json` `stage: "stalled"`, adds a `stage:stalled`
label (created if missing, as the plan stage's stalled job already does),
removes the `stage:tasks` label, and comments that a maintainer must delete
`tasks/$slug` and manually restart the tasks stage. This only applies when
`SPECKIT_TASKS_REVIEW=pr`; direct-commit mode has no review PR that can be
closed unmerged.

**Rationale**: Byte-for-byte the same shape as the plan stage's existing
`stalled` job (`speckit-3-plan.yml`), just re-keyed to the `tasks/` prefix
and the tasks-stage labels/messages.

**Alternatives considered**: A separate workflow file for the stalled path —
rejected; the plan stage keeps both jobs in one file, and there's no reason
to diverge from that precedent.
