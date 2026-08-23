# Feature Specification: An Implement Run That Dies at Entry Still Marks the Record and Says So on the Issue

**Feature Branch**: `041-implement-stall-notice`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "implement's chain-stop is silent: a gate failure skips the stalled job, so spec-meta.json goes unmarked and the lifecycle issue says nothing. Split out of #188 (spec 039), which is scoped to the lifecycle gate composite alone. The retry that #188 adds makes this reachable less often; it cannot make it unreachable. When the gate does exhaust its budget, the chain stops without a word. **What happens**: The lifecycle gate is the first step of the `implement` job (`implement.yml:446`), before preflight, before checkout, before any agent step. If it exits non-zero the whole job dies there, and the job's outputs are never set. `stalled` — the job whose entire purpose is to record that a stage did not complete — is wired to that (`needs: implement`, `if: needs.implement.outputs.final-ok == 'false'`). It is skipped, twice over: (1) `final-ok` is never assigned, so it renders empty, and `'' == 'false'` is false — the comment at `implement.yml:1488-1490` says as much and treats it as intended for pre-flight refusals; (2) independently, that `if:` carries no status-check function, so it inherits an implicit `success()` over its needs-closure. A failed `implement` skips `stalled` regardless of what the expression says. This is the #224 mechanism, still present here — benign today only because arm 1 already suppresses the job. So: `spec-meta.json` is never marked, `stage:stalled` is never applied, and nothing is posted to the lifecycle issue. The requester sees a specification that simply stopped moving. The watchdog's `workflow_run` trigger does catch the red run, so a human eventually hears about it — but through a different channel than the one carrying the feature's state, and nothing restarts. The lifecycle issue, which is the pipeline's own record of where a feature is, still reads as though implementation were in progress. **Why it is not part of #188**: Making a job survive a dead dependency is the exact step-gating class that took this pipeline down twice in the week of 2026-08-13 (#224, #227). It needs its own conditions review and its own gate, not a subclause in a feature about a retry loop. Answered as such on #188 during clarification. **What a fix has to be careful about**: The `'' != 'false'` gap is load-bearing for the refusal contract — a pre-flight *refusal* is meant to skip `stalled`, and a pre-flight *crash* is not. Any fix has to keep those two apart, which means distinguishing 'the job declined to proceed' from 'the job died', and today the empty string means both. Adding `always()` or `!cancelled()` to `stalled` changes when it runs across every existing path, not just this one. Gate 15 exists to catch the shape where an `if:` arm can never be read; it will have opinions about whatever lands here, and should. Whatever the mechanism, the failure branch has to be executed by a test, not merely written — #169 is the standing record of harnesses that model dependencies which cannot fail. **Scope question for the spec**: `implement` is the stage where the consequence is worst, because it is the one with a `stalled` job and a chain to stop. The gate is also the first step of `clarify`, `finalize`, `intake`, `pr-conversation`, and `tasks` (specs/022 FR-001). Whether those need an equivalent notice, or whether a red run plus the watchdog is a sufficient record for a stage that carries no chain state, is a design question rather than a decided one. **Related**: #188 / spec 039 (the retry and error classification; this issue is its deliberate remainder), #224 (needs-closure skip suppression — the same mechanism, present in `stalled`'s condition), #193 (six agent steps unrescued), #169 (harnesses whose failure branches never execute)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The chain stops out loud (Priority: P1)

A requester is watching their lifecycle issue. An implementation cycle is dispatched and dies at its very first step — before preflight, before checkout, before any agent has been asked to do anything. Within the same run, the specification's lifecycle record is marked as not having completed, the issue is relabelled to match, and a comment appears on the issue saying the stage stopped, why, and what to do about it. The requester never has to notice an absence.

**Why this priority**: This is the defect. Today that run produces nothing on the issue at all: the record still names the stage that was running, the label still says implementation is underway, and the only trace is a red run in the Actions tab — a channel the requester is not watching and which carries no lifecycle state. A pipeline whose own record of where a feature stands can silently go stale is worse than one that fails loudly, because the failure is indistinguishable from slowness. Every other story here refines what that notice says or protects it from regressing; this one is the notice existing at all.

**Independent Test**: Drive an implement run whose first step fails, and confirm the lifecycle record is marked stalled, the stall label is applied, and a notice is posted on the lifecycle issue — the same three effects an exhausted-retry stall produces today.

**Acceptance Scenarios**:

1. **Given** an implement run whose lifecycle gate step fails, **When** the run ends, **Then** the specification's lifecycle record is marked as stalled, the stall label is applied to the lifecycle issue, and a notice is posted there.
2. **Given** an implement run that fails at any step before it publishes its outcome — not only the gate — **When** the run ends, **Then** the same three effects occur.
3. **Given** an implement run whose entry-level dependency fails so the implement job never starts at all, **When** the run ends, **Then** the same three effects occur; a chain that stopped one job earlier is still a chain that stopped.
4. **Given** any of the above, **When** the notice path runs, **Then** it does so without reading any value the terminated job never published.
5. **Given** any of the above, **When** the run finishes, **Then** the run itself is still reported as failed, so the existing failure-detection channel keeps seeing exactly what it sees today.

---

### User Story 2 - The notice describes the stop that actually happened (Priority: P1)

A maintainer opens the lifecycle issue and reads one comment. They can tell immediately whether the implementation agent ever ran — whether this is an exhausted retry that spent two model tiers and lost, or a stage that never got past its first step — and the restart instructions they are given are the correct ones for that case.

**Why this priority**: The existing stall notice asserts specifics that are false for this path: that iteration N failed, on a named model tier, with no higher tier left to escalate to. None of that happened when the job died at entry — no attempt was made, no tier was used, and the right response is usually to re-dispatch unchanged rather than to go hunting for a broken task. A confidently wrong notice sends a maintainer to diagnose work that never occurred, which is the same misdirection cost #188 documents for the gate's own error text. Equal priority to story 1 because a notice nobody can act on correctly does not discharge the obligation story 1 creates.

**Independent Test**: Produce both stops — an exhausted retry and a death at entry — and confirm each notice names its own case, and that the restart instructions in each identify the iteration a maintainer should actually dispatch.

**Acceptance Scenarios**:

1. **Given** a run that died before any implementation attempt, **When** the notice is posted, **Then** it says the stage did not start rather than that an attempt failed, and it does not name a model tier or an escalation that never happened.
2. **Given** the same run, **When** the notice is posted, **Then** it names where the run stopped and links the failing run.
3. **Given** an exhausted-retry stall, **When** the notice is posted, **Then** it reads exactly as it does today — this feature adds a case, it does not reword the existing one.
4. **Given** either stop, **When** a maintainer follows the notice's restart instructions verbatim, **Then** the stage restarts at the iteration the pipeline's own guard will admit.
5. **Given** a run whose record could not be read or updated, **When** the notice is posted, **Then** it is still posted, and it says the record could not be updated rather than silently omitting it.

---

### User Story 3 - A refusal is still a refusal, and a healthy run is untouched (Priority: P2)

Nothing that is quiet today becomes noisy. A duplicate dispatch the guard drops, a run against a closed lifecycle issue, a successful cycle, and a cycle that fails and is already reported — all behave exactly as they do now.

**Why this priority**: The mechanism this feature must change — the condition on the job that reports a stall — is the same one that has taken this pipeline down twice, and both times by widening when something ran. The empty-outcome gap being closed here is load-bearing for the refusal contract: a stage that declines to proceed is meant to leave the record alone. Marking a specification stalled because a duplicate dispatch was correctly ignored would be a worse defect than the one being fixed, because it would fire on healthy runs rather than rare ones. Below the P1 stories only because nothing here is currently broken; this story is about not breaking it.

**Independent Test**: Exercise each currently-quiet path in turn — duplicate dispatch, closed lifecycle, successful cycle, exhausted retry — and confirm the record, the labels, and the issue's comments are exactly what they are today.

**Acceptance Scenarios**:

1. **Given** a duplicate dispatch that the idempotency guard skips, **When** the run ends successfully, **Then** the record is unchanged, no stall label is applied, and no notice is posted.
2. **Given** a run whose lifecycle issue is closed, **When** the run ends, **Then** the existing closed-lifecycle note is the only thing posted, and no stall notice joins it.
3. **Given** a cycle that completes successfully, **When** the run ends, **Then** nothing about this feature is observable.
4. **Given** an exhausted-retry failure, **When** the run ends, **Then** exactly one stall notice is posted — the existing one — and not a second from the new path.
5. **Given** a run cancelled by a human, **When** the run ends, **Then** no notice is posted and the record is untouched; a deliberate stop is not a stall.
6. **Given** any run at all, **When** it ends, **Then** at most one stall notice exists for that run.

---

### User Story 4 - The failure branch is executed, not merely written (Priority: P2)

Before this ships, a check drives an implement run whose dependency actually fails and asserts the notice happened. Removing the guard that lets the notice survive a dead dependency, or narrowing the condition so the new path can never be reached, fails a check.

**Why this priority**: This is a path that runs only when something else has already gone wrong, which is precisely the class of code that rots unnoticed — a stall notice that quietly stopped being reachable looks exactly like a stall notice that never had to fire. The repository has already written this lesson down twice: as issue #169, and as the constitution's requirement that every shipped failure branch be exercised by a checked-in fixture. Worse, the specific mistake being fixed here is one an existing gate cannot see: the current condition carries no result arm and depends on nothing guarded, so it passes the job-suppression gate while being suppressed exactly as #224 described. Below the P1 stories because it protects the fix rather than being the fix.

**Independent Test**: Make the modelled dependency fail and confirm the coverage observes the record mark and the notice; then make the notice path unreachable and confirm a check goes red. Coverage that can only model a dependency which succeeds does not satisfy this story.

**Acceptance Scenarios**:

1. **Given** coverage that models an implement job which failed at its first step, **When** the coverage runs, **Then** it asserts the notice path is reached and produces the record mark and the issue notice.
2. **Given** the status-check function removed from the notice path's condition, **When** the checks run, **Then** a check fails.
3. **Given** the condition narrowed so an abnormally-terminated run can no longer reach the notice, **When** the checks run, **Then** a check fails.
4. **Given** the condition widened so a duplicate-dispatch or closed-lifecycle run reaches the notice, **When** the checks run, **Then** a check fails.
5. **Given** the new coverage disabled, removed, or made unreachable, **When** the checks run, **Then** a check fails — the coverage is wired into the same registry that proves every other gate is run.

---

### Edge Cases

- **The run died at its first step, so nothing about the specification was ever resolved.** The notice path cannot ask the dead job which specification this was. It identifies the specification, the lifecycle issue, and the iteration from the stage's own declared inputs, which are present regardless of how far the run got.
- **The dependency one level above the implement job fails, so the implement job never starts.** The chain has still stopped and the issue still says work is underway; the notice is posted. This is a different arm of the same suppression mechanism and must not be left to accident.
- **The run is cancelled.** No notice. A cancellation is someone deciding to stop, and reporting it as a stall would turn every deliberate cancel into a stalled specification.
- **The record already reads stalled** from an earlier failed iteration. Having nothing to commit must not abort the notice — the same hazard the existing stall path already handles.
- **The record cannot be written** — the spec branch was force-pushed by the scheduled rebase between read and write, or the branch is not there to check out. The notice is still posted, and it says the record could not be updated.
- **The notice path itself fails partway.** Its reporting must not be suppressed by its bookkeeping: a step that only tells a human must survive the step in front of it failing, exactly as the existing stall report does.
- **Two stops in one run.** A run that both consolidated a failed outcome and then died cannot produce two notices; exactly one is posted, and it is the more specific one.
- **The watchdog also reports the red run.** Two channels observe the same failure, and this feature changes neither the watchdog nor the run's red status. The lifecycle record is the authority on where the specification stands; the watchdog's report is a separate observation and is not deduplicated against it.
- **A pre-flight refusal that is expressed as a failed run** — missing credentials, a missing spec-kit skill, a malformed hand-off. Today these are silent by the same accident this feature removes, and the refusal contract says a stage that declines to proceed leaves the record alone. See FR-005.
- **The stall notice fires for a specification whose lifecycle issue was closed while the run was in flight.** The gate already declines that run; a closed issue receives no stall notice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When an implement run ends without publishing an implementation outcome — the job terminated abnormally, or never started because something it depends on failed — the stage MUST still mark the specification's lifecycle record as stalled, apply the stall label to the lifecycle issue, and post a notice there. These are the same three effects an exhausted-retry stall produces today.
- **FR-002**: The path that produces that notice MUST be reachable when the job it reports on has failed or has been skipped. Its condition MUST be evaluated rather than suppressed before it is read; a job whose entire purpose is to react to a failure MUST NOT be one the platform skips because that failure occurred.
- **FR-003**: The notice path MUST NOT depend on any value the terminated job failed to publish. It MUST identify the specification, the lifecycle issue, and the iteration from the stage's own declared inputs.
- **FR-004**: Widening when the notice runs MUST NOT make any currently-quiet path noisy. A duplicate dispatch the idempotency guard skips, a run against a closed lifecycle issue, and a successful cycle MUST each leave the record and the labels untouched and post nothing new.
- **FR-005**: A pre-flight refusal MUST remain distinguishable from an abnormal termination, and the treatment each receives MUST be a declared decision rather than a consequence of an unset value. Today both present as a job that produced no outcome, which is why one accident silences both. [NEEDS CLARIFICATION: when the implement job refuses to proceed for a declared reason and exits non-zero doing so — missing credentials, a missing spec-kit skill, a malformed spec hand-off — should the specification be marked stalled and the issue told, as for a crash, or should that path stay entirely silent as it is today?]
- **FR-006**: Exactly one stall notice MUST be produced per run, on every path. A run that both recorded a failed outcome and then terminated abnormally MUST NOT produce two.
- **FR-007**: The notice MUST describe the stop that actually occurred. A run that ended before any implementation attempt MUST NOT be reported as an attempt that failed, MUST NOT name a model tier it never used, and MUST NOT claim an escalation was exhausted. It MUST name where the run stopped and link the failing run.
- **FR-008**: The restart instructions in the notice MUST be correct for a run that performed no work — the iteration they name MUST be the one the stage's own idempotency guard will admit.
- **FR-009**: A cancelled run MUST NOT produce the notice and MUST NOT alter the record.
- **FR-010**: The run's overall failed status MUST be unchanged, so the existing run-level failure detection keeps observing exactly what it observes today. This feature adds a channel; it does not replace or quieten one.
- **FR-011**: Within the notice path, a step that reports to the requester MUST NOT be suppressed by the failure of a bookkeeping step ahead of it. If the record cannot be updated, the notice is still posted and says so.
- **FR-012**: Executable coverage MUST exercise the notice path against a modelled implement run that actually failed, and MUST assert that the record was marked and the notice produced. Coverage whose modelled dependency cannot fail does not satisfy this requirement.
- **FR-013**: Removing the guard that lets the notice survive a dead dependency, narrowing the condition so an abnormally-terminated run can no longer reach the notice, or widening it so a refused or skipped run does reach it, MUST each fail a check.
- **FR-014**: The new coverage MUST be wired into the repository's existing gate registry, so coverage that stops being run is itself a failure.
- **FR-015**: The delivered conditions MUST satisfy the repository's existing job-suppression gate. If that gate's rules must change to admit the new condition, the change MUST NOT reduce the set of shapes it detects, and the shape this feature fixes — a job that reacts to a failure without a status-check function of its own — MUST be detectable afterwards rather than merely absent from the tree.
- **FR-016**: The stage's declared inputs, outputs, and secrets MUST NOT change, and no adopter may need to edit a wrapper workflow to receive this fix.
- **FR-017**: This feature MUST deliver the notice for the implement stage, which is the stage that carries chain state and a bookkeeping job. [NEEDS CLARIFICATION: should the other five stages that enter through the same gate — clarify, finalize, intake, pr-conversation, tasks — also gain an equivalent notice when they die at entry, or is a red run plus the existing watchdog observation a sufficient record for a stage that carries no chain state?]
- **FR-018**: The specification's lifecycle record MUST remain the authority on where a specification stands. After any run covered by FR-001, the record MUST NOT read as though the stage were still in progress.

### Key Entities

- **Lifecycle record**: the per-specification file that is the machine-readable source of truth for a specification's stage. When a stage stops without updating it, every consumer — the requester, the restart guard, the watchdog — reads a state that is no longer true.
- **Chain-stop notice**: the combination of record mark, label change, and issue comment that tells a human a stage did not complete and how to restart it. It exists today for exactly one cause (an exhausted retry) and is unreachable for every other way the stage can stop.
- **Abnormal termination**: an implement run that ends without publishing an outcome, whether because a step failed, because the job never started, or because something it depends on failed.
- **Refusal**: an implement run that declines to proceed for a declared reason. It is not a stall, and today it is indistinguishable from an abnormal termination because both leave the same absent value behind.
- **Job-suppression gate**: the existing check for conditions that can never be read because the platform skips the job before evaluating them. It is the gate this change must satisfy, and the class of defect it exists to catch is the one being fixed.
- **Executable coverage**: a check that drives the shipped condition against a modelled failure, rather than asserting that the condition's text looks right.

## Out of Scope

- **The lifecycle gate itself.** Its retry behaviour and its error text are a separate feature (#188 / specs/039), already specified. This feature assumes nothing about whether that landed: it addresses what happens when the gate — or anything else at entry — ultimately fails.
- **Automatically restarting a stage that stopped.** Making the stop visible and actionable is this feature's job. Deciding when a pipeline may re-dispatch itself is a policy question with its own blast radius, and the existing stall path does not restart either.
- **Any change to the watchdog.** It already observes the red run through its own trigger, and this feature must leave that observation exactly as it is.
- **A general "every job publishes an outcome" convention for the whole fleet.** This is one stage's chain-stop, fixed with its own conditions review, not a refactor of how every stage reports.
- **Rewording the existing exhausted-retry stall notice.** This feature adds a case; the current wording for the current case stays.
- **Extending the notice to the other five gate-calling stages** — pending the answer to FR-017. If the answer is that they need it, that becomes part of this feature's scope; if not, it is not raised again here.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every implement run that ends without recording an outcome leaves a stall notice on the lifecycle issue and a stalled lifecycle record — up from none today.
- **SC-002**: The number of implement runs whose lifecycle record still reads "in progress" after the run has ended falls to zero.
- **SC-003**: A maintainer reading only the lifecycle issue can tell whether the implementation agent ever ran, without opening the failing run.
- **SC-004**: Following the restart instructions in the notice verbatim restarts the stage at an iteration the guard admits, for both stop causes.
- **SC-005**: No path that posts nothing today posts anything new: duplicate dispatch, closed lifecycle, and successful cycles are byte-for-byte unchanged in what reaches the issue.
- **SC-006**: Exactly one stall notice is produced per run on every path, including a run that recorded a failed outcome and then terminated abnormally.
- **SC-007**: Removing the guard that lets the notice survive a dead dependency fails a check; narrowing the condition so the new path is unreachable fails a check; widening it so a refused run reaches it fails a check; disabling the new coverage fails a check.
- **SC-008**: The change reaches adopters without any wrapper edit, and the stage's declared inputs, outputs, and secrets are unchanged.
- **SC-009**: The run's failed status and the existing run-level failure detection are unchanged, verified by the failure still being observed through that channel after the change.

## Assumptions

- Reusing the existing stalled state and stall label for this cause is correct rather than inventing a new one. The label already means "the stage did not complete; manual restart required", which is exactly this case, and the restart guard already admits a stalled stage at the recorded iteration plus one — so a run that died before recording anything restarts at the right number without a new admission rule.
- The stage already declares, as inputs, everything the notice needs to identify the specification and the issue. Nothing new has to be threaded through a wrapper for the notice to know what it is reporting on.
- The repository already contains the shape this needs and does not have to invent one: a workflow-level safety net that runs despite a dead dependency, reports what happened, and is deliberately best-effort so it cannot itself become a new single point of failure. This feature follows that precedent rather than establishing a new pattern.
- A cancelled run is a deliberate human act and is not a stall. Treating cancellation as a stall would fire on ordinary operations.
- The distinction between a refusal and an abnormal termination has to be carried by a positive signal, not by the absence of a value. Whatever the answer to FR-005, a treatment that depends on a variable being empty is what produced this defect and is not an acceptable mechanism for the fix.
- The two reporting channels — the lifecycle issue and the run-level failure observation — are allowed to both fire for the same failure. They serve different readers, and suppressing either to avoid duplication would recreate a single point of failure.
- This feature is independent of #188 / specs/039. It neither requires that work nor conflicts with it: the retry changes how often the gate fails, and this changes what happens when it does.
- Coverage for a job-level condition can be driven without a live run of the whole stage — the same way the repository's existing checks reason about conditions and drive shipped shell against modelled inputs.
