# Feature Specification: Post-agent full-suite verdict for implement cycles

**Feature Branch**: `spec-draft/133-post-agent-gate-verdict`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "run-local-gates cannot complete in the 10-minute
tool limit. The full gate suite (294 gates) exceeds the 600000 ms Bash cap, so
an implement agent cannot get a full-suite verdict in one call
(verify-sentinel-collector.py alone took 180 s, verify-agent-verdict.py 167 s;
found by spec 127's implement stage, run 45050237725). Owner decisions
(2026-11-26): the verdict comes from a credential-free full-suite gate job that
runs after the implement agent decides the cycle, only on a cycle that would
converge, where red means not converged — the board loop's fix-agent →
gate-suite-fix pattern, keeping spec 095's boundary. The agent runs only the
gates for the files it changed, by name, with `run-local-gates.py`'s existing
name filter, and leaves the verdict to the post-agent job. There is no automatic
changed-file selector (#1281 built one and was closed unmerged: its file map
went stale within days and never changed a verdict)." Lifecycle issue #1180,
routed from #1178.

## Background

Today an implement cycle runs the full local gate suite once before its agent
starts (the credential-free cycle-start job spec 095 introduced) and hands the
result to the agent as a starting point. The agent is then told to run the full
suite itself before pushing. That second run cannot finish inside one agent
tool call: the suite takes longer than the 10-minute tool limit. So the agent
either burns turns on a run that is cut off, or pushes without a full-suite
verdict, and the cycle's "converged" decision — which today reads only whether
tasks.md has unchecked tasks — hands the spec to finalize without any full
suite having judged the head that is handed off.

## Clarifications

### Session 2026-11-26

- Q: Should a converging cycle whose post-agent suite cannot run because a
  prerequisite is missing be held not converged, or converge with a visible
  "suite skipped" note? → A: If the repository has a gate suite, hold it not
  converged (fail closed); an adopter repository with no suite converges on
  tasks alone (FR-013).
- Q: Does spec 117's stall hand-off to finalize also wait on a passing
  post-agent verdict? → A: The post-agent full suite also runs on the stall
  hand-off; its verdict goes to finalize as information and does not block the
  hand-off (FR-014).

### Session 2026-11-27

- Q: Which of spec 117's hand-offs to finalize get the informational
  post-agent suite run: blocker hand-offs only, or cap-reached hand-offs too?
  → A: Every hand-off spec 117 marks `handoff=true` — the named-blocker
  hand-off and the iteration-cap hand-off alike, matching spec 117's own
  definition (FR-014).
- Q: On a stall hand-off, does finalize's dispatch wait (bounded by the suite
  budget) for the informational verdict, and where must finalize show it?
  → A: Finalize's dispatch waits for the post-agent job, at most its suite
  budget; the verdict's outcome never blocks the hand-off, and finalize shows
  it in the final PR body. The verdict is delivered without widening the
  finalize wrapper's fixed dispatch signature (FR-014, SC-007).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A converging cycle is judged by the full suite before hand-off (Priority: P1)

The owner relies on the pipeline to hand a spec to finalize only when its
branch passes the full gate suite. When an implement cycle's agent finishes and
the cycle would converge (no implementation task left unchecked, as
convergence counts them today), a separate job that holds no
credential able to write to the repository runs the full suite on the exact
head the agent pushed. Only a pass lets the cycle converge; a red or absent
verdict makes the cycle not converged, so the next implement cycle runs instead
of finalize.

**Why this priority**: This is the defect: no full-suite run currently decides
whether a cycle converges, and the agent cannot produce one itself.

**Independent Test**: Drive one implement cycle on a branch whose tasks are all
checked but where one gate fails; observe that the post-agent job reports red
naming that gate and that the cycle is recorded not converged and re-dispatches
implement rather than finalize. Repeat with the gate passing and observe
convergence and the hand-off to finalize.

**Acceptance Scenarios**:

1. **Given** a cycle whose agent pushed a head with zero outstanding
   implementation tasks and a passing suite, **When** the post-agent gate job finishes, **Then** the cycle
   is recorded converged and the next stage (finalize) is dispatched, exactly as
   a converged cycle is today.
2. **Given** a cycle whose agent pushed a head with zero outstanding
   implementation tasks and a failing gate, **When** the post-agent gate job finishes, **Then** the cycle
   is recorded not converged, the lifecycle shows the first failing gate's
   text, and the next implement cycle is dispatched instead of finalize.
3. **Given** a cycle whose agent left tasks unchecked, **When** the agent step
   ends, **Then** no post-agent full-suite run happens and the cycle proceeds as
   a non-converged cycle does today.
4. **Given** the post-agent gate job hangs, is cancelled, crashes, or leaves no
   readable verdict bound to the pushed head, **When** convergence is decided,
   **Then** the cycle is treated as not converged, never as converged.
5. **Given** a repository with the local gate suite and a converging cycle
   whose post-agent suite cannot run because a prerequisite or the pipeline
   checkout is missing, **When** convergence is decided, **Then** the cycle is
   recorded not converged and the reason names the missing prerequisite.
6. **Given** a cycle that hands off to finalize under spec 117 with
   `handoff=true` (a named blocker or the iteration cap), **When** the
   hand-off to finalize happens, **Then** the post-agent suite runs on the
   handed-off head, finalize's dispatch waits for it at most the suite
   budget, its verdict is shown in the final PR body, and a red, missing or
   late verdict does not stop the hand-off.

---

### User Story 2 - The agent runs only the gates its change touches (Priority: P2)

An implement agent runs, by name, the gates that cover the files it changed,
using the gate runner's existing name filter, and does not attempt the full
suite. Its instructions tell it the full-suite verdict is decided after it
finishes, by a job it does not control.

**Why this priority**: It stops agents spending turns on a full-suite run that
cannot complete, but the verdict (Story 1) is what protects the hand-off, so
this ranks second.

**Independent Test**: Read the instructions an implement agent receives in a
cycle where the suite can run; confirm they name the targeted-gate form, do not
ask for a full-suite run, and say the verdict comes after the agent. Inspect one
cycle's agent transcript and confirm no full-suite invocation was attempted.

**Acceptance Scenarios**:

1. **Given** an implement cycle in a repository that has the local gate suite,
   **When** the agent reads its instructions, **Then** they direct it to run
   only the gates for the files it changed by name and state that the full
   suite runs after it to decide convergence.
2. **Given** the cycle-start suite was red, **When** the agent reads its
   instructions, **Then** it still sees the cycle-start result and first failing
   gate as a starting point, as today.
3. **Given** a repository with no local gate suite, **When** the agent reads its
   instructions, **Then** they still say there is no suite and not to run one,
   as today.

---

### User Story 3 - The owner can see why a cycle did not converge (Priority: P3)

When the post-agent verdict holds a cycle back, the owner can tell from the
lifecycle issue and the run summary that the full suite — not unchecked tasks —
is the reason, and which gate failed.

**Why this priority**: Visibility only; the behaviour in Story 1 is correct
without it, but a silent "not converged" would look like a stall.

**Independent Test**: In the red case of Story 1, read the cycle's run summary
and lifecycle comment and confirm both name the post-agent suite as the reason
and quote the first failing gate.

**Acceptance Scenarios**:

1. **Given** a cycle held back by a red post-agent verdict, **When** the owner
   reads the lifecycle issue, **Then** the non-convergence reason names the
   post-agent full suite and its first failing gate, distinct from the
   unchecked-tasks reason.

---

### Edge Cases

- The agent's run was truncated (turn budget exhausted with progress): such a
  cycle is already forced not converged, so no post-agent suite runs.
- The retry leg produced the cycle's final result: the post-agent verdict
  judges the head the cycle's final outcome refers to, whichever leg pushed it.
- The spec branch moved after the agent pushed (another push landed): the
  verdict is bound to the head it judged; a verdict for a different head than
  the one convergence would hand off is treated as absent.
- The suite exceeds its own time budget in the post-agent job: that is a red
  verdict naming the budget, as the cycle-start job does today.
- The repository has no local gate suite (an adopter repository): no
  post-agent suite runs and convergence is decided by tasks alone, as today.
- The suite's prerequisites, or the pipeline checkout the job needs, are
  missing from the job's environment: in a repository that has the local gate
  suite, a cycle that would converge is held not converged (fail closed) and
  the reason names the missing prerequisite; it does not degrade to a skip the
  way the cycle-start job does. A repository with no local gate suite still
  converges on tasks alone (owner answer on #1180, 2026-11-26, Q1).
- The cycle hands off to finalize under spec 117 with `handoff=true` (a
  named blocker or the iteration cap), rather than converging: the post-agent
  full suite also runs on the head being handed off, finalize's dispatch
  waits for it at most the suite budget, and its verdict is passed to
  finalize as information and shown in the final PR body. It does not block
  the hand-off — a red, absent, late or unrunnable verdict is reported, not
  used to hold the cycle (owner answers on #1180, 2026-11-26 Q2 and
  2026-11-27).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When an implement cycle's agent leg completes and the cycle would
  converge (the completed, non-truncated attempt left zero outstanding
  implementation tasks at its pushed head, counted exactly as convergence
  counts them today under specs 059 and 117, so `[maintainer]` and
  unbuildable lines do not count), the full local gate suite MUST run on that
  exact head before the cycle is recorded converged.
- **FR-002**: The post-agent suite MUST run in an execution context that holds
  no credential able to write to the repository, on a runner of its own,
  separate from the job holding the App token — the boundary spec 095 (FR-001,
  FR-005) sets for every gate-suite call site.
- **FR-003**: The post-agent suite MUST NOT run on a cycle that would not
  converge (tasks unchecked, truncated, or failed), except for spec 117's
  stall hand-off to finalize, which FR-014 governs.
- **FR-004**: A cycle MUST be recorded converged only when the post-agent
  verdict is a pass bound to the head being handed off. A red verdict, or a
  verdict that is absent, unreadable, malformed or bound to a different head,
  MUST make the cycle not converged (spec 095 FR-004's fail-closed reading).
- **FR-005**: A cycle held back by FR-004 MUST follow today's non-converged
  path: below the iteration cap the next implement cycle is dispatched and
  finalize MUST NOT be; at the cap it takes today's cap-reached path (finalize
  dispatched with converged=false), never a converged hand-off.
- **FR-006**: The dispatch of the next stage, the converged output the stage
  publishes to its callers, and the metrics record's convergence field MUST all
  reflect the post-agent verdict, never the pre-verdict tasks-only reading.
- **FR-007**: The post-agent suite's time budget MUST be below its job's own
  timeout, so a slow suite yields a red verdict naming the budget rather than
  an absent one.
- **FR-008**: The instructions an implement agent receives MUST direct it to
  run only the gates covering the files it changed, by name, with the gate
  runner's existing name filter, and MUST state that the full-suite verdict is
  decided after the agent finishes. They MUST NOT ask the agent to run the full
  suite. This applies to the repository's agent guidance that addresses the
  implement stage agent as well as the stage's own prompt, so the two do not
  contradict each other.
- **FR-009**: No automatic changed-file-to-gate selector MUST be introduced;
  the agent chooses the gate names itself (owner decision on #1281).
- **FR-010**: When a red post-agent verdict holds a cycle back, the lifecycle
  issue and run summary MUST name the post-agent full suite as the
  non-convergence reason and quote its first failing gate, rendered as
  untrusted text the way gate-suite output is today (spec 095 FR-003).
- **FR-011**: The cycle-start gate suite and the information it gives the agent
  MUST keep today's behaviour.
- **FR-012**: The live reference documentation MUST describe the post-agent
  gate job, its budget and its effect on convergence, as docs/reference.md
  requires of changes to a stage's loops and limits.
- **FR-013**: In a repository that has the local gate suite, when the
  post-agent suite cannot run because a prerequisite or the pipeline checkout
  the job needs is missing, a cycle that would converge MUST be recorded not
  converged (fail closed), and the non-convergence reason MUST name the
  missing prerequisite. It MUST NOT degrade to a converged cycle with a
  "suite skipped" note. A repository with no local gate suite MUST still
  converge on tasks alone, with no post-agent suite run.
- **FR-014**: When a cycle hands off to finalize under spec 117 with
  `handoff=true` — the named-blocker hand-off and the iteration-cap hand-off
  alike — the post-agent full suite MUST also run on the head being handed
  off, in the same credential-free context as FR-002, and its verdict (pass or
  fail, first failing gate, head judged) MUST be passed to finalize as
  information. Finalize's dispatch MUST wait for the post-agent job, for at
  most the suite budget of FR-007. The verdict's outcome MUST NOT block the
  hand-off: a red, absent, unreadable, unrunnable or late verdict is reported
  to finalize as such, and the hand-off proceeds as it does today. Finalize
  MUST show the verdict (or the report that none was produced) in the final
  PR body. The verdict MUST reach finalize without widening the finalize
  wrapper's fixed dispatch signature.

### Key Entities

- **Post-agent verdict**: the result of one full-suite run on a cycle's pushed
  head — pass or fail, the first failing gate's text, and the head it judged.
- **Converging cycle**: a completed, non-truncated implement attempt whose
  pushed head has zero outstanding implementation tasks, counted as
  convergence counts them today (FR-001); the only kind of cycle whose
  convergence the post-agent verdict decides.
- **Stall hand-off**: a spec 117 hand-off to finalize with `handoff=true`
  (a named blocker or the iteration cap); the post-agent suite also judges
  its head, but the verdict is information for finalize, shown in the final
  PR body, not a gate on the hand-off.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of implement cycles that hand a spec to finalize by
  converging have a passing full-suite verdict bound to the handed-off head.
- **SC-002**: In a cycle with a deliberately failing gate and all tasks
  checked, the spec is not handed to finalize, and the next implement cycle is
  dispatched with the failing gate named.
- **SC-003**: Across implement cycles after rollout, zero agent tool calls
  attempt the full gate suite; the agent's gate runs each finish inside the
  10-minute tool limit.
- **SC-004**: No job that runs the post-agent suite holds a credential able to
  write to the repository.
- **SC-005**: Cycles that do not converge incur no additional full-suite run,
  except a spec 117 stall hand-off to finalize, which incurs exactly one.
- **SC-006**: In a repository with the local gate suite, 0% of cycles whose
  post-agent suite could not run are recorded converged.
- **SC-007**: 100% of spec 117 `handoff=true` hand-offs to finalize carry a
  post-agent verdict (or a report that none could be produced) to finalize
  and show it in the final PR body; none is blocked by the verdict's outcome,
  and none waits longer than the suite budget for it.

## Assumptions

- The board loop's fix-agent → gate-suite-fix → fix split is the pattern to
  follow: the agent job publishes its head, the credential-free gate job judges
  it, and a later step that holds the App token reads the verdict fail-closed.
- The existing credential-free contained-gate-suite path used by the
  cycle-start job is reused for the post-agent run rather than a new runner
  being built.
- The retry leg's own in-job suite (spec 095 T015, deferred) stays out of
  scope; this feature only adds the verdict that decides convergence.
- The next cycle's cycle-start suite already reports a red head to the agent,
  so a held-back cycle needs no new hand-over of the failure to the next
  agent; reusing the post-agent verdict at the next cycle's start, when the
  head is unchanged, is permitted but not required.
- Changing the repository's agent guidance that addresses the implement stage
  agent (FR-008) is a change to the rules agents run under, and is approved by
  the owner with the final PR.
- An earlier comment on #1180 mentions a `--changed` filter; the later owner
  decision (closing #1281) supersedes it, and the existing name filter is used.
