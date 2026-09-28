# Feature Specification: No Stage Is Left Holding Work It Cannot Do — The Implement Stage's Write Boundary

**Feature Branch**: `spec-draft/090-stage-write-boundary`

**Created**: 2026-09-28

**Status**: Draft

**Input**: Lifecycle issue #675 — "Implement stage cannot write under
`.claude/`, so convergence-appended docs tasks can never complete" (routed
from board-loop.yml as `agent_proposed_spec`, originating issue #489). Found
by the implement stage of spec 060, run
https://github.com/charlesguse/wing-commander/actions/runs/36013041955

## Overview

The implement ⟲ converge loop assumes every task in `tasks.md` is a task the
implement stage can perform. Spec 060's cycle found one that is not: `T055`
asks the stage to edit `.claude/skills/spec-cross-reference/SKILL.md`, and the
stage's Edit tool was refused on that path — twice in the one cycle, after
`T053` had already recorded the same refusal in an earlier run. Nothing in the
loop can absorb that outcome. The vendored `/speckit-converge` skill is
append-only by contract, so it can neither tick the task nor withdraw it; it
re-derives the same unbuilt work and appends it again. The convergence signal
is `unchecked-count == 0` at the pushed tip, so the task holds the loop open
for every remaining iteration. When the loop finally ends, the task leaves the
pipeline as one line of prose in the final PR's remaining-manual-work list —
with no issue, no label, and no owner.

The impossible task is the symptom. The defect is that the stage is handed
work without any statement of what it is able to write, and the loop has no
way to discharge work that turns out to be beyond it. This repository already
settled the general form of that rule for a different case: spec 078's FR-007
says that if a site cannot write a path the prompt names, "that site's lists
MUST be corrected as part of this change rather than left with guidance it
cannot follow." The same rule has never been applied to the task list.

So this feature answers two questions and builds the mechanism behind them.
First, the trade-off the route agent flagged: may an automated stage edit this
repository's own agent control surface under `.claude/` at all — the skills
that tell agents how to work, the hooks that fire on their tool calls, the
settings that grant their permissions — or must work that touches it be routed
to someone who can do it? That question is now answered: it may not, and the
work is routed (see Clarifications and FR-002). Second, given that answer: the
boundary must be stated to the stage before it spends turns discovering it,
and work that falls outside it must be discharged deterministically — filed,
labelled, owned, and taken out of the loop's way — rather than resurfacing
each cycle and then evaporating into a PR body.

One thing this feature must not get wrong: `.claude/` is not off-limits to
automation. The auto-update stage changes `.claude/skills/speckit-*` on every
Spec Kit upgrade and requires such a change before it will commit. What was
refused in run 36013041955 was an *agent* editing its own control surface
while running under it. Those are different acts and the boundary this feature
declares must distinguish them.

### Observed facts (verified against `main` at b2e982c)

- `implement.yml:839` (the cycle arm) and `implement.yml:1506` (the retry arm)
  both compose `default-allowed-tools` beginning `Skill,Read,Write,Edit,...`
  — the `Write` and `Edit` grants carry no path scope. Both arms'
  `default-disallowed-tools` is exactly
  `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage`. **Nothing in this
  repository's own composed tool lists denies `.claude/`**, so the refusal the
  stage reported came from outside those lists. Where it does come from is not
  established on `main` today, and this feature has to establish it rather
  than assume it (see Assumptions and FR-001).
- The prompt's Tooling paragraph (`implement.yml:955-970`) renders
  `steps.tool-args-cycle.outputs.shell-commands` and tells the agent that
  "a command's presence or absence here matches what this run actually
  permits. Anything absent is auto-denied and only burns turns." That
  guarantee covers `Bash` commands only. The prompt says nothing about paths
  the `Edit`/`Write` tools cannot reach.
- The prompt's only path restriction is soft and is about a different
  directory: "do not edit files under .github/workflows unless the task list
  explicitly requires it" (`implement.yml:945-946`). Read literally, a task
  list that explicitly requires a path is authorization — which is exactly
  what `T055` is, and it still could not be done.
- `/speckit-converge` is append-only by contract
  (`.claude/skills/speckit-converge/SKILL.md`, "Operating Constraints"): its
  only write is appending a `## Phase N: Convergence` section, and it "MUST
  NOT rewrite, renumber, reorder, or delete any existing task (including tasks
  from a prior Convergence phase)". It therefore cannot tick, defer, or
  withdraw `T055`, and it re-appends the work it still sees as unbuilt. It is
  a vendored Spec Kit artifact under the `speckit_version` pin, maintained by
  the auto-update stage — not this repository's file to edit.
- Convergence is decided deterministically from `tasks.md`'s checkbox state at
  the pushed tip, not from whether a `converge:` commit landed
  (`implement.yml:1354-1358`, spec 059 FR-001/FR-002): `converged=true` iff
  `UNCHECKED_TIP` is 0. One permanently unchecked task keeps that false
  forever.
- Spec 059's early hand-off (`implement.yml:1365-1367`) requires
  `converged=false` **and** `progressed=false` **and** no `converge:` commit.
  A cycle that completes any other task has `progressed=true`, so the loop
  dispatches another iteration; the hand-off only fires on a later cycle whose
  only remaining work is the impossible task, or the loop reaches the
  iteration cap (default 5).
- When the loop ends, `finalize.yml:715-721` asks the agent to write "every
  tasks.md item that is still unchecked (`- [ ]`)" to the final PR's remaining
  manual work. The impossible task's terminal state is therefore a line of
  prose in a PR body. Constitution Principle IV requires the opposite: "Any
  manual step that survives must be reported explicitly to the lifecycle
  issue, never silently assumed."
- `.claude/` is already written by automation, deterministically and without
  an agent: `auto-update-spec-kit.yml:1615-1622` fails its prepare step unless
  `git status --porcelain -- '.specify' ':(glob).claude/skills/speckit-*/**'`
  reports a change, then commits it. The implement stage also holds
  `Bash(git add:*)` and `Bash(git commit:*)`, so it can commit a `.claude/`
  change it did not author with `Edit`.
- `.claude/` holds three materially different things. Vendored Spec Kit skills
  (`.claude/skills/speckit-*`, ten of them) belong to the pin and to
  Principle VI. This repository's own skills
  (`spec-cross-reference`, `review-step-gating`, `container-shell-safety`) are
  its own instrument under Principle VII — `T055`'s target is one of these.
  The control surface proper is `.claude/settings.json` (the `permissions.allow`
  list and the `PreToolUse` hook registration) and `.claude/hooks/` (one
  script, `constitution-reminder.sh`, deliberately advisory: it "never denies
  the tool call").
- The deterministic filing path Principle X requires already exists:
  `implement.yml:2163` calls `wing-commander-stage-findings` with
  `label-prefix: ${{ inputs.findings-label-prefix }}`, wired by
  `wing-commander-5-implement.yml:100` to
  `vars.WING_COMMANDER_FINDINGS_LABEL_PREFIX || 'found-by'`, producing a
  `found-by:<stage>` label. Its input is the agent's
  ```wing-commander-findings``` block, which is for "a defect that is not your
  own task to fix" — not for a task the stage was assigned and could not
  perform.
- Prior art for the rule: spec 078 FR-007 — "if a site cannot write the named
  path or commit from it under its existing lists, that site's lists MUST be
  corrected as part of this change rather than left with guidance it cannot
  follow." Spec 078's Edge Cases also already name "A path the run cannot
  write" as a first-class case.
- `wing-commander-tasks-checkbox-count` is the single home the convergence
  signal and the progress test both read `tasks.md` through
  (`implement.yml:1210-1224`, spec 059 research.md D2). Any new `tasks.md`
  state would have to be understood there, not beside it.

## Clarifications

### Session 2026-09-28 — answered on lifecycle issue #675

- Q: May an automated stage's agent edit this repository's agent control
  surface under `.claude/`, and if narrowly, which subpaths? → A: **No — do
  not widen the implement agent's write access to `.claude/`, for any
  subpath.** Principle V requires each stage to hold the least-privilege tool
  allowlist it needs; write access under `.claude/` would let an agent rewrite
  its own permission settings and hooks mid-run; and Principle IX puts the
  gating of durable writes in deterministic code rather than in an agent's
  judgement. Work that targets `.claude/` is routed out of the loop instead.
  (FR-002, FR-018, User Story 2)
- Q: How is an already-assigned out-of-boundary task discharged so the loop
  terminates honestly — by a new `tasks.md` state the checkbox-count composite
  understands, or by leaving the task unchecked and having a deterministic
  step route it and end the loop? → A: **Leave the task unchecked and route it
  deterministically, outside the checkbox loop.** The checkbox format is
  vendored Spec Kit and belongs to the pin rather than to the consuming
  repository (Principle VI), and a new marker would reach every reader of the
  checkbox count. FR-011's distinct reason line already explains the
  non-converged verdict, so no new `tasks.md` state is introduced.
  (FR-010, FR-011, User Story 3)
- Q: Is the boundary defined for `.claude/` specifically, or as a general
  declared no-write set per stage? → A: **One general declared no-write list,
  defined in exactly one place** (the "Shared logic has exactly one home"
  rule, FR-003), exposed as a new optional stage input that defaults to
  `.claude/` — so an adopter who configures nothing keeps today's behaviour,
  and the next unwritable path is a list entry rather than a second mechanism.
  (FR-003, FR-019, FR-021, User Story 4)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The stage knows what it may write before it tries (Priority: P1)

The implement stage begins a cycle holding a task list it did not write. It
should be able to tell, without spending a turn on a refused tool call,
whether a path a task names is one it can write. Today the prompt makes that
promise for `Bash` commands and makes no statement at all about paths, so the
stage discovered the boundary the only way available to it: by being refused,
twice, in one cycle.

**Why this priority**: Every other story here depends on the boundary being a
knowable fact rather than a discovery. It also stands alone — even if nothing
else in this feature ships, a stage that reads its own write boundary stops
burning turns on refusals and can report the obstruction accurately.

**Independent Test**: Read the rendered implement prompt for one run with no
other context and answer "may this run's agent edit
`.claude/skills/spec-cross-reference/SKILL.md`?" correctly, then confirm the
answer matches what the run actually permits.

**Acceptance Scenarios**:

1. **Given** an implement cycle, **When** the agent reads its prompt,
   **Then** the prompt states which paths in the checkout its `Edit`/`Write`
   tools may not write, in the same derived-from-this-run's-own-configuration
   terms the Tooling paragraph already uses for shell commands.
2. **Given** a task naming a path outside that boundary, **When** the agent
   reaches that task, **Then** it can identify the task as out of its reach
   from the prompt alone and does not attempt the edit.
3. **Given** the stated boundary, **When** the agent attempts a write inside
   it, **Then** the write succeeds — the statement is not a superset that
   forbids work the run would in fact allow.
4. **Given** the boundary statement, **When** the run's permitted paths
   change, **Then** the statement changes with them rather than being a
   hand-maintained literal that can drift from what the run permits.

---

### User Story 2 - Work beyond the stage's reach is routed, not resurfaced (Priority: P1)

A task the implement stage cannot perform is still work someone has to do. It
needs an owner outside the loop. Today it has none: converge re-appends it,
the loop carries it to the iteration cap, and finalize turns it into prose in
a PR body that no board step reads.

**Why this priority**: This is the loss the issue is about. The boundary being
knowable (Story 1) stops the wasted turns; only routing stops the work from
being dropped.

**Independent Test**: Drive one cycle against a `tasks.md` containing a task
whose path is outside the stage's write boundary, and confirm that after the
run there is exactly one tracked, labelled item naming that task and its path,
and that a second cycle over the same `tasks.md` does not produce a second
one.

**Acceptance Scenarios**:

1. **Given** an unchecked task whose path lies outside the stage's write
   boundary, **When** the cycle ends, **Then** a deterministic step — never
   the agent's own hand — has filed exactly one tracked item naming the task
   id, the path, and the spec it came from, under a pipeline-owned label.
2. **Given** the same out-of-boundary task still present on a later cycle,
   **When** that cycle ends, **Then** no duplicate item is filed.
3. **Given** such a task, **When** the cycle reports to the lifecycle issue,
   **Then** the report names the task, says it was outside the stage's reach,
   and points at where the work now lives.
4. **Given** a task whose path is inside the boundary but which the stage
   simply did not finish, **When** the cycle ends, **Then** nothing is filed
   and nothing is routed — ordinary unfinished work still belongs to the next
   cycle.

---

### User Story 3 - The loop's convergence verdict is honest about it (Priority: P1)

A maintainer reading the loop's outcome needs "not converged" to mean "there
is more for the stage to do". A task no cycle can ever complete makes that
verdict permanently, uninformatively false, and consumes iterations that would
otherwise have gone to real work.

**Why this priority**: It is the cost the issue measured — the task "will
resurface every cycle" — and it is what turns one impossible task into a
spec-wide stall.

**Independent Test**: With one out-of-boundary task and every other task
checked, confirm the loop terminates without exhausting its iteration budget,
and that its terminal report distinguishes "all in-reach work is done, one
item was routed out" from both "converged" and "stalled".

**Acceptance Scenarios**:

1. **Given** a `tasks.md` whose only unchecked task is out of the stage's
   write boundary, **When** the cycle completes, **Then** the loop does not
   dispatch a further cycle for the sake of that task alone.
2. **Given** that same state, **When** the outcome is reported, **Then** it is
   not reported as converged, and not reported as a stall or a failure
   either — the reason names the routed work.
3. **Given** a cycle that both completed real work and met one out-of-boundary
   task, **When** the outcome is computed, **Then** the real progress is still
   recognized as progress and the routed task does not mask it.
4. **Given** the final PR, **When** its remaining-manual-work list is read,
   **Then** any routed item appears with a pointer to the tracked item rather
   than as an orphan line of prose.

---

### User Story 4 - The rule is not re-derived for the next unwritable path (Priority: P2)

`.claude/` is the path that produced this issue. It will not be the last:
`.git/` is already refused, paths outside the checkout are already refused for
`Bash` but not for `Write` (spec 078 relies on exactly that asymmetry), and
any future scoping of a stage's write grants creates another. A fix written
only for `.claude/` leaves the next one to be found the same way this one was
— by an agent being refused mid-cycle.

**Why this priority**: It is scope, not correctness, and the Story 1–3
mechanism delivers value for `.claude/` alone. It ranks here because the cost
of retrofitting generality later is a second pass over every consumer of the
boundary — a cost FR-019 has now resolved by declaring the set general from
the start, with `.claude/` as its default sole entry.

**Independent Test**: Introduce a second unwritable path and confirm that the
boundary statement, the routing, and the report all cover it with no change to
the mechanism itself.

**Acceptance Scenarios**:

1. **Given** the shipped mechanism, **When** a reader asks where the set of
   paths a stage may not write is defined, **Then** there is exactly one
   answer, in one place, per the "Shared logic has exactly one home" rule.
2. **Given** a new path added to that set, **When** a cycle runs, **Then** the
   prompt statement, the routing decision, and the lifecycle report all
   reflect it with no further edit.

---

### Edge Cases

- **A task naming several paths, only one of which is out of reach.** The
  in-reach part is real work the stage should still do; routing the whole task
  would drop it. Splitting it is not something an append-only converge can do.
- **A task whose text names no path at all** ("update the skill's guidance").
  A path-based boundary cannot classify it, and guessing would route real work
  away. It must fall through to ordinary unfinished-work handling.
- **A task already ticked in an earlier cycle whose path is out of reach.** It
  was either done by other means or ticked in error; a boundary check must not
  retroactively un-tick or re-file it.
- **The same out-of-boundary task in two specs at once.** Two concurrent specs
  can meet the same `.claude/` path; the dedup key has to distinguish them or
  collapse them deliberately, not accidentally.
- **A cycle cancelled or exhausted mid-way** (`truncated`). The stage may not
  have reached the out-of-boundary task at all. Filing on a run that never
  looked is a false report; spec 059 already refuses to read convergence from
  a truncated run's `tasks.md`.
- **The boundary is empty** — a run configured to permit every path. The
  prompt must say so plainly rather than rendering an empty clause the agent
  has to interpret.
- **A path inside the boundary that the run still refuses** for some other
  reason. The statement would then be a promise the run does not keep, which
  is the same failure as making no statement at all, only harder to notice.
- **The task is to change the boundary itself** — a task under
  `.claude/settings.json` that would grant the very permission the stage lacks.
  Under FR-002 this is squarely out of reach and is routed like any other
  `.claude/` task; the mechanism must reach that outcome explicitly rather
  than letting it fall out of a path-prefix comparison, because an agent
  widening its own grants mid-run is the case the policy exists to prevent.
- **An adopting repository with no `.claude/` skills of its own.** The boundary
  is a per-stage input on the published contract, so an adopter's default must
  be sensible without their configuring anything (Principle VI/VII).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The actual write boundary of the implement stage's agent MUST be
  established and recorded from observation — which paths its `Edit`/`Write`
  tools are refused on, and what imposes the refusal — before anything is
  built on top of it. `main` shows both arms granting unscoped `Write`/`Edit`
  and no `.claude/` entry in either disallowed list, so the refusal reported in
  run 36013041955 is not explained by this repository's own configuration, and
  no requirement below may assume it is.

- **FR-002**: An automated stage's agent MUST NOT write under `.claude/` with
  `Edit`/`Write`, for any of its three parts — the vendored
  `.claude/skills/speckit-*` artifacts under the Spec Kit pin, this
  repository's own skills, and the control surface (`.claude/settings.json`,
  `.claude/hooks/`). The repository MUST record this as a decision rather than
  an inherited accident: it is the least-privilege allowlist Principle V
  requires, it denies an agent the ability to rewrite its own permission
  settings and hooks mid-run, and it keeps the gating of durable writes in
  deterministic code per Principle IX. The decision MUST distinguish an
  agent's in-run `Edit`/`Write` from the deterministic, non-agent writes
  `auto-update-spec-kit.yml` already performs under `.claude/skills/speckit-*`,
  which remain permitted and are not in question here.

- **FR-003**: The set of paths a stage's agent may not write MUST have exactly
  one definition in the repository, consumed by every site that needs it,
  rather than a literal repeated in a prompt, a routing step, and a report.

- **FR-004**: Each in-scope agent prompt MUST state the paths that run's agent
  may not write, derived from that run's own configuration in the same way the
  Tooling paragraph's shell-command sentence is derived from its own composed
  tool lists — so presence or absence in the statement matches what the run
  actually permits, and the statement cannot drift from it.

- **FR-005**: The boundary statement MUST NOT forbid a path the run would in
  fact permit. An over-broad statement suppresses real work, and suppressed
  work is indistinguishable from work the stage chose not to do.

- **FR-006**: An unchecked task whose named path lies outside the stage's
  write boundary MUST be recognized as such by deterministic code, never by
  the agent's judgement alone, consistent with Principle IX — the recognition
  gates a durable action (a filed item and a changed loop verdict).

- **FR-007**: Such a task MUST be routed to an owner outside the loop by a
  deterministic filing step under a pipeline-owned label, naming the task id,
  the path, and the originating spec — never by the agent's own hand, and
  never only as prose in a report a later stage composes.

- **FR-008**: Routing MUST be idempotent across cycles and across reruns: the
  same out-of-boundary task MUST NOT produce a second tracked item on the next
  cycle, on a retry of the same iteration, or on a re-driven run.

- **FR-009**: A routed task MUST be reported to the lifecycle issue by the
  cycle that routed it, naming the task, the reason it was out of reach, and
  where the work now lives — satisfying Principle IV's requirement that a
  surviving manual step is reported explicitly rather than silently assumed.

- **FR-010**: The loop MUST NOT dispatch a further iteration for the sake of
  out-of-boundary work alone. A `tasks.md` whose only unchecked items are
  routed MUST terminate the loop. The discharge MUST leave the task's
  `tasks.md` line unchecked and untouched: a deterministic step routes it
  (FR-007) and ends the loop, and NO new `tasks.md` state or checkbox marker
  is introduced. The checkbox format belongs to the vendored Spec Kit pin
  (Principle VI), and a new marker would reach every reader of the checkbox
  count; the honest terminal verdict is carried by FR-011's reason line
  instead.

- **FR-011**: A terminal outcome reached under FR-010 MUST be reported as
  neither converged nor stalled nor failed: the reason line MUST name the
  routed work, so a maintainer can tell "everything in reach is done, one item
  went elsewhere" from both a clean convergence and a stall.

- **FR-012**: Real progress in a cycle that also met an out-of-boundary task
  MUST still be recognized as progress; the routed task MUST NOT suppress the
  existing checked-count progress test or the existing early hand-off for the
  cases those already cover.

- **FR-013**: A cycle that did not complete healthily — `truncated`,
  cancelled, or failed — MUST NOT file or route anything on the strength of a
  `tasks.md` it may never have reached, mirroring spec 059's refusal to read
  convergence from a truncated run.

- **FR-014**: A checked (completed) task MUST never be re-opened, re-filed, or
  re-routed by the boundary check, whatever its path.

- **FR-015**: A task the boundary check cannot classify — no path in its text,
  or a path only partly out of reach — MUST fall through to today's ordinary
  unfinished-work handling rather than being routed on a guess. Routing real
  work away is a worse failure than leaving it in the loop.

- **FR-016**: This feature MUST NOT edit any vendored
  `.claude/skills/speckit-*` artifact. `/speckit-converge`'s append-only
  contract and `/speckit-implement`'s behaviour are the pin's, maintained by
  the auto-update stage; every mechanism here MUST live in this repository's
  own layer.

- **FR-017**: Spec 060's `T055` — the task that produced this issue — MUST end
  in a tracked, owned state rather than as an unchecked line in a `tasks.md`
  on a spec branch.

- **FR-018**: FR-002's policy — no agent write under `.claude/`, deterministic
  non-agent writes unaffected — MUST be recorded where a future change will
  read it: the boundary's single definition (FR-003), and the governing
  document to the extent the policy states something about an agent's own
  control surface that the constitution does not already say. The next session
  MUST be able to read the policy rather than re-derive it from a refused tool
  call.

- **FR-019**: The boundary MUST be a general declared no-write set per stage,
  not a `.claude/`-specific special case: `.claude/` is its first entry. The
  set MUST be exposed as a new optional stage input whose default is
  `.claude/`, so adding the next unwritable path is a list entry rather than a
  second mechanism, and the prompt statement (FR-004), the routing decision
  (FR-006/FR-007), and the lifecycle report (FR-009) all read the one
  definition FR-003 requires.

- **FR-020**: Every behavioural requirement above MUST be covered by a gate
  reachable through the gate registry and runnable locally through
  `python .github/scripts/run-local-gates.py`, extending the nearest existing
  harness rather than adding a parallel one, with a checked-in fixture for
  every failure branch it ships (Principle VIII).

- **FR-021**: The published contract MUST NOT be narrowed by this change: any
  new stage input MUST be optional with a default that leaves an adopter who
  configures nothing behaving sensibly, and no existing input, secret, or
  output may be renamed or removed (Principle VII).

### Key Entities

- **Write boundary**: the set of paths in the checkout a given stage's agent
  may not write with `Edit`/`Write`. Distinct from its shell-command allowlist,
  distinct from what a deterministic `run:` step in the same job can write, and
  — as `main` stands — not expressed anywhere.
- **Out-of-boundary task**: an unchecked `tasks.md` item whose named path lies
  outside the write boundary of the stage assigned to complete it. `T055` is
  the first identified instance; `T053` recorded the same refusal one run
  earlier.
- **Agent control surface**: the part of `.claude/` that governs how agents in
  this checkout behave — `settings.json`'s permission allowlist and hook
  registration, `hooks/`, and the skills agents are told to run. FR-002 puts
  all of it beyond an agent's `Edit`/`Write` reach while it runs under it;
  deterministic non-agent writes are a separate act and remain permitted.
- **Routed work**: work the pipeline has removed from the loop and handed to a
  tracked owner outside it. Today's nearest relatives are the
  `found-by:<stage>` finding (a defect the stage met, not work it was assigned)
  and finalize's remaining-manual-work prose (untracked). Neither fits.
- **Convergence verdict**: `unchecked-count == 0` at the pushed tip. The
  quantity an impossible task holds above zero indefinitely.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent in an implement cycle can answer "may I write this
  path?" for every path in the checkout from its prompt alone, and the answer
  matches what the run permits in 100% of cases checked.
- **SC-002**: Zero turns are spent on `Edit`/`Write` calls refused for being
  out of the stage's write boundary, across the implement runs following this
  change — the refusal is knowable in advance, so reaching one is a defect in
  the statement.
- **SC-003**: A `tasks.md` whose only unchecked item is out of boundary
  terminates the loop in one cycle rather than consuming the remaining
  iteration budget, and the terminal report's reason names the routed item.
- **SC-004**: An out-of-boundary task produces exactly one tracked, labelled
  item — verified by running two consecutive cycles over the same `tasks.md`
  and finding one, not two.
- **SC-005**: Zero out-of-boundary tasks reach the final PR as untracked
  prose: every item in the final PR's remaining-manual-work list that was
  routed carries a pointer to its tracked item.
- **SC-006**: Spec 060's `T055` is closed out as tracked, routed work — FR-002's
  policy puts its path beyond any agent's reach, so it cannot be completed by
  the stage — with the outcome recorded on issue #675.
- **SC-007**: A mutation that disables the boundary check, and a mutation that
  makes the boundary statement drift from the run's real permissions, are each
  caught by the gate suite; the full suite
  (`python .github/scripts/run-local-gates.py`) passes.
- **SC-008**: An adopter who sets none of this feature's inputs sees no change
  in their implement stage's behaviour beyond the added boundary statement.

## Assumptions

- The refusal the spec 060 cycle reported is real and reproducible: two
  denied `Edit` attempts in one cycle, on top of `T053`'s record of the same
  refusal in an earlier run. The observation is trusted; its *cause* is not
  assumed, because `main`'s own tool lists do not explain it (FR-001).
- Because the cause may lie outside this repository's configuration, FR-002's
  "no agent write under `.claude/`" may be redundant for some subpaths — the
  harness may already refuse them regardless of policy. Stating it as a
  decision is still what matters: the repository now routes such work by
  choice rather than merely by inability, and only that survives a change in
  the harness. FR-001's observation therefore still has to be done, but its
  outcome cannot reopen FR-002.
- `tasks.md` task text names its target paths often enough for a path-based
  check to classify the cases that matter. `T055` names its path; FR-015
  exists for the tasks that do not.
- Spec 059's convergence signal, progress test, and early hand-off are correct
  as shipped for the cases they cover; this feature adds a case they do not
  cover rather than revisiting their logic.
- `wing-commander-tasks-checkbox-count` remains the single home through which
  `tasks.md` state is read. FR-010 introduces no new `tasks.md` state, so the
  composite is unchanged by this feature; if a later change ever needs one, it
  is taught there rather than counted a second way.
- The implement stage is the only stage whose agent is assigned `tasks.md`
  work, so it is the only stage where an out-of-boundary *task* can arise. The
  boundary statement itself may still be worth rendering in other stages'
  prompts; FR-019's per-stage no-write set makes that a configuration
  question for the plan, not an assumption here.
- Filing and labelling capacity already exists (`wing-commander-stage-findings`,
  `found-by:<stage>`); whether routed work reuses it or needs its own label is
  a design choice for the plan, not a new capability.
- Deferring a routed item to a human or to the board loop's fix track is
  acceptable: the board loop already works filed issues in a fixed order, and
  a `.claude/` documentation edit is well within the fix-shaped bound
  Principle X defines.

## Dependencies

- `.github/workflows/implement.yml` — both arms' composed tool lists
  (`:839`, `:1506`), both prompts' Tooling and Constraints paragraphs, the
  convergence/progress/hand-off computation (`:1330-1406`), and the
  `wing-commander-stage-findings` call (`:2163`).
- `.github/actions/wing-commander-tool-args/action.yml` — where the
  run-derived `shell-commands` sentence is composed, and the natural home for a
  run-derived paths clause (FR-004).
- `.github/actions/wing-commander-tasks-checkbox-count/action.yml` — the single
  home for reading `tasks.md` state; read for the convergence signal, and left
  unchanged, since FR-010 adds no new `tasks.md` state.
- `.github/actions/wing-commander-stage-findings/action.yml` — the existing
  deterministic filing step and its `found-by:<stage>` label (FR-007).
- `.github/workflows/finalize.yml:715-721` — the remaining-manual-work prompt
  that currently terminates a routed task's life (FR-011, SC-005).
- `.claude/skills/speckit-converge/SKILL.md` — read for its append-only
  contract; never edited (FR-016).
- `.claude/settings.json`, `.claude/hooks/constitution-reminder.sh` — the
  control surface FR-002 is about.
- `.github/workflows/auto-update-spec-kit.yml:1615-1622` — the existing
  deterministic, non-agent write under `.claude/skills/speckit-*` that FR-002
  must not disturb.
- `.github/workflows/lint-workflows.yml` and
  `.github/scripts/run-local-gates.py` — where FR-020's gate is registered.
- `specs/060-self-redrive-concurrency/tasks.md` (on its spec branch) — `T053`
  and `T055`, the subject instances (FR-017).
- `.specify/memory/constitution.md` — Principles IV, VI, VII, VIII, IX, X; and
  FR-018's possible amendment target if FR-002 narrows or widens what an agent
  may do to its own control surface.

## Out of Scope

- Editing any vendored `.claude/skills/speckit-*` artifact, or changing
  `/speckit-converge`'s append-only contract or `/speckit-implement`'s
  behaviour (FR-016).
- Changing the Spec Kit pin, or the auto-update stage's own `.claude/` writes.
- Revisiting spec 059's convergence signal, progress test, iteration cap, or
  early hand-off for the cases they already cover.
- Scoping the implement stage's `Write`/`Edit` grants for reasons other than
  the boundary this feature declares — a general least-privilege pass over
  every stage's tool lists is its own change.
- Teaching the tasks stage or the plan stage not to generate out-of-boundary
  tasks in the first place. Both run vendored skills; prevention at generation
  time is a separate question from discharge at implement time, and would need
  its own decision about where the judgement lives.
- The completion of `T055`'s actual content — whatever guidance it asked to add
  to `spec-cross-reference/SKILL.md`. This feature ensures that work is owned
  and tracked; doing it is the owner's.
- Any change to how findings are fingerprinted or deduplicated by the watchdog.
