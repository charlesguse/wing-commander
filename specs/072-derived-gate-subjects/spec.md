# Feature Specification: Gate 68 Derives Its Own Subjects

**Feature Branch**: `072-derived-gate-subjects`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "Gate follow-ups from PR #407: derive Gate 68 subjects, close the toJSON(steps.<id>) gap, self-test the stall-notice gate. Found by the code review of #407. PR #407 (spec 052, fixes #345) merged as 6409fd1. Its reviews deferred these gate gaps on purpose so the PR could converge. None of them is a live defect: every stage workflow on main passes Gates 68 and 69 today. They are the places where a future edit could slip past the gates. (1) Derive Gate 68's subjects from the workflow files — `verify-post-agent-credential-refresh.py` names its subject jobs in a hand-kept list (the eight sweep stages). A ninth agent stage added later is not checked until someone remembers to add it. Derive the subjects instead: every job that has an agent step (`claude-code-action`) and reads the bot token afterwards. Keep the existing 'subject list points at a nonexistent file/job' mutations working, or replace them with 'a subject was dropped'. (2) `toJSON(steps.<id>)` used directly in a post-agent step passes Gate 68. (3) Self-test for the stall-notice gate (FR-023). (4) Stale wording in research.md D3. Routed from board-loop.yml (issue #410): reason=under_threshold. Originating issue #410."

## Overview

The post-agent credential gate (Gate 68,
`.github/scripts/verify-post-agent-credential-refresh.py`) decides which
workflow jobs it inspects by reading a list that a maintainer types into
the gate itself. The list names the eight sweep stages spec 052 swept.
Any agent-bearing job added after that — or any agent-bearing job that
already existed and was never typed in — is invisible to the gate: it is
not checked, and nothing reports that it is not checked. The gate reads
as coverage of "every agent job" while proving something only about the
jobs someone remembered to name.

This is not hypothetical on today's `main`. Four workflow files carry
real agent steps and appear nowhere in the gate's subject list:

| Workflow | Agent steps | Post-agent contract adopted? |
|----------|-------------|------------------------------|
| `board-loop.yml` | 5 (`Triage-propose`, `Route-propose`, `Fixer`, `Reviewer`, `Review-fixup`) | relay and credential-status present; no agent-ran-signal |
| `cleanup.yml` | 1 (`Completion summary`) | none |
| `rebase.yml` | 1 (`Resolve conflicts`) | none |
| `watchdog.yml` | 1 (`diagnose`) | none; carries `timeout-minutes: 10` |

Spec 052 recorded an explicit, reasoned exclusion for the two
`auto-update-spec-kit.yml` jobs it deliberately left out. It recorded
none for these four. The gate cannot tell the difference between "out of
scope for a reason" and "never typed in," because the only thing it
consults is the typed list.

The remedy is to let the gate discover its own subjects from the
workflow files, and to keep a loud failure for the case derivation
cannot detect on its own — a subject that disappears, because the very
edit that removes an agent step also removes the job from the derived
set and would otherwise leave the gate silently passing over a smaller
world.

### Relationship to the originating issue's items 2, 3 and 4

The originating issue (#410) listed four follow-ups. Items 2, 3 and 4
are already on `main`, landed by commit `2a1cf1b` ("Gate 68 catches a
whole-step toJSON dump; the stall-notice gate gets a self-test; research
D10 points at D10a (#410 items 2-4)"):

- **Item 2** — `TOKEN_REF_RE` in `verify-post-agent-credential-refresh.py`
  now matches `toJSON(steps.<id>)` and `toJSON(steps)`, and
  `SIMPLE_MUTATIONS` carries the two `#410`-labelled mutations
  (`mut_whole_step_dump_credential_reference`,
  `mut_whole_steps_context_dump`).
- **Item 3** — `verify-implement-stall-notice-unchanged.py` has a
  `self_test()` and a `--self-test` step wired next to the existing one
  in `lint-workflows.yml`.
- **Item 4** — `specs/052-agent-credential-lifetime/research.md` now
  reads "It read `toJSON(steps)` when this was written; D10a records its
  replacement by the `wing-commander-failed-post-agent-step` composite
  fed an explicit candidate list (#410 item 4)."

They are therefore out of scope here and named in Out of Scope below, so
that the record shows they were checked rather than forgotten. This
feature is item 1 only.

## Clarifications

### Session 2026-09-25

- Q: Which structural rule defines the derived subject set? → A: Every
  job in every `.github/workflows/` file that contains an agent step is
  a subject — no behavioural narrowing. A job is a subject on the
  presence of an agent step alone, so any agent job the repository grows
  is covered the day it ships (Constitution Principle VIII), and
  `board-loop.yml`, `cleanup.yml`, `rebase.yml` and `watchdog.yml` come
  into scope and each needs a disposition. Narrowing to "an agent step
  *and* a later bot-acting step" would make the gate's reach depend on a
  second reading of each job, and restricting derivation to the eight
  sweep-stage files would leave a new workflow file uncovered — the same
  hole one level up. (FR-002)
- Q: What is the derived set compared against so a disappearing subject
  fails? → A: A checked-in floor naming the agent-bearing jobs known to
  exist. Derivation MUST cover every member of the floor and MAY exceed
  it: a job the floor names that derivation no longer yields fails
  loudly, while a job derivation yields that the floor does not name is
  still inspected — so forgetting to update the floor fails safe rather
  than silently shrinking coverage. A minimum subject count was rejected
  because it tolerates one job disappearing while another appears.
  (FR-004, FR-009, SC-002, SC-004)
- Q: What disposition do the agent-bearing jobs derivation newly
  surfaces get? → A: Decide per workflow, following spec 052's
  precedent: adopt the post-agent credential contract where the agent
  step carries no wall-clock bound and a step that acts as the bot
  follows it; exclude every other job with its reason recorded in place.
  `watchdog.yml`'s `diagnose` is excluded on the stated basis that its
  agent step carries `timeout-minutes: 10`. Adopting the contract
  everywhere would touch four workflows outside the original sweep for
  jobs that cannot hold a stale credential; excluding everything would
  leave real gaps recorded as intentional. (FR-012, FR-013, FR-014)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A new agent-bearing job is checked the day it ships (Priority: P1)

A maintainer adds a job that runs an agent step to a workflow — a tenth
stage, a new arm of an existing stage, a new autonomous loop. They do
not edit the post-agent credential gate, because nothing tells them to.
On the pull request that adds the job, the gate inspects it anyway: if
the new job holds a credential minted before its agent step, or runs an
agent step with no re-establishment after it, the gate names the
workflow, the job and the step and fails.

**Why this priority**: This is the defect. Every other story in this
feature exists to keep this one honest. Without it the gate's coverage
decays silently with every workflow the repository grows.

**Independent Test**: Add a job with an agent step and a stale
post-agent credential reference to a workflow, run the gate locally, and
observe it fail naming that job — with no edit to the gate itself.
Remove the stale reference and observe it pass.

**Acceptance Scenarios**:

1. **Given** a workflow file containing a job with an agent step that is
   not named in any list inside the gate, **When** the gate runs,
   **Then** that job is inspected and appears in the gate's reported
   subject set.
2. **Given** such a newly-discovered job whose post-agent step reads a
   credential captured before its agent step, **When** the gate runs,
   **Then** the gate fails and the message names the workflow file, the
   job and the offending step.
3. **Given** a job whose agent step is added and whose post-agent
   contract is complete, **When** the gate runs, **Then** the gate
   passes and no edit to the gate was required to make it do so.

---

### User Story 2 - A subject that disappears fails loudly (Priority: P1)

A maintainer's edit removes an agent step from a job, renames the agent
action, deletes a workflow file, or otherwise shrinks the set of jobs
the gate would derive. Under a purely derived subject set this is the
one regression derivation cannot see — the edit deletes the evidence
that the job was ever a subject. The gate must notice that its world got
smaller and fail, rather than report a pass over a reduced set.

**Why this priority**: Constitution Principle VIII: a gate that cannot
reach its subject must fail loudly rather than report a pass it did not
earn. The hand-kept list gave this for free (pointing it at a missing
file or job failed); derivation gives it away unless it is replaced
deliberately. Shipping US1 without US2 trades one silent-coverage hole
for another.

**Independent Test**: Remove the agent step from one currently-derived
job in a working copy, run the gate, and observe it fail naming the job
that vanished. Restore it and observe it pass.

**Acceptance Scenarios**:

1. **Given** the shipped tree, **When** one subject job's agent step is
   replaced by a non-agent step, **Then** the gate fails with a message
   that names the job that is no longer a subject.
2. **Given** the shipped tree, **When** a whole workflow file that
   contributes subjects is removed, **Then** the gate fails naming that
   file rather than passing over the remaining files.
3. **Given** a tree in which derivation yields zero subjects, **When**
   the gate runs, **Then** it fails as misconfigured rather than passing
   over an empty result set.
4. **Given** the gate's `--self-test`, **When** it runs, **Then** it
   exercises the "a subject was dropped" regression above and reports
   that each documented mutation fails.

---

### User Story 3 - Every agent-bearing job is covered or recorded with a reason (Priority: P2)

Turning derivation on surfaces the four workflows that carry agent steps
and are checked by nothing today. Each one ends this feature in exactly
one of two states: covered by the gate and passing it, or recorded in a
checked-in exclusion that states why the post-agent credential defect
cannot occur there. No agent-bearing job ends the feature in neither
state, and a job in neither state fails the gate.

**Why this priority**: Derivation without a disposition rule either
fails the whole suite on day one or is quietly narrowed until it matches
the old list again. Recording the reason is what stops the next
maintainer re-deriving the same judgement, and it matches spec 052's own
SC-005 ("zero stages neither covered nor recorded with a reason").

**Independent Test**: Run the gate on the shipped tree and confirm it
passes; then, for each of the four workflows above, confirm the tree
shows either the job in the gate's passing subject set or an exclusion
entry naming it with a reason.

**Acceptance Scenarios**:

1. **Given** the shipped tree after this feature, **When** the gate
   runs, **Then** it passes, and every job in the repository with an
   agent step is either inspected by it or listed in the exclusion
   record.
2. **Given** a job with an agent step that is neither compliant nor
   excluded, **When** the gate runs, **Then** it fails naming that job.
3. **Given** the exclusion record, **When** a reader opens it, **Then**
   each entry names the workflow, the job, and the reason the defect
   cannot occur there.

---

### Edge Cases

- **An agent step named only in a comment or a documentation fixture.**
  `lint-workflows.yml` and `release.yml` mention the agent action inside
  comments and gate fixtures, not as a step. Derivation must read
  structure, not text, so a mention is never mistaken for a subject.
- **A job whose agent step is its last step and which never acts as the
  bot afterwards.** There is no stale credential to hold, but under
  FR-002 it is still a subject — the agent step alone makes it one. Its
  disposition is settled by FR-014's rule: no bot-acting step follows,
  so it is excluded with that reason recorded, never silently skipped.
- **A job whose agent step carries a short wall-clock bound.** Spec 052
  excluded two jobs on exactly this basis (`timeout-minutes: 10`, an
  order of magnitude under the credential's one-hour lifetime);
  `watchdog.yml`'s agent step carries the same bound. The exclusion
  record must be able to express this without re-hand-keeping the
  subject list.
- **A reusable-workflow call or matrix job.** A job whose steps are not
  visible in the file being read contributes no derived subject; the
  gate must not treat "no steps I can see" as "no agent step here."
- **The agent action referenced at a different version or through a
  local path.** Derivation keyed on an exact pinned reference would miss
  a version bump; keyed too loosely it would match unrelated actions.
- **The gate's own companion maps.** The stall-reason job map, the
  failed-step job map, and the no-remote-refresh exemption are keyed to
  the same jobs. Deriving the subject set while leaving those hand-kept
  reintroduces the same decay one layer down.
- **A workflow file that cannot be parsed.** An unreadable or malformed
  file must fail the gate, never silently contribute zero subjects.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The post-agent credential gate MUST determine the set of
  jobs it inspects by reading the repository's workflow files, not from
  a list of workflow paths and job names maintained by hand inside the
  gate.

- **FR-002**: The gate MUST define the derived subject set by a stated,
  structural rule over the workflow files: every job in every
  `.github/workflows/` file that contains an agent step is a subject.
  The presence of an agent step in the job is the whole condition — no
  further reading of the job narrows the set, whether or not a later
  step acts as the bot, and no restriction to a subset of workflow files
  applies. `board-loop.yml`, `cleanup.yml`, `rebase.yml` and
  `watchdog.yml` are therefore in scope, and each of their agent-bearing
  jobs needs the disposition FR-012 through FR-014 require.

- **FR-003**: A job that satisfies the derivation rule MUST be subjected
  to the gate's existing post-agent credential checks with no further
  registration step — no edit to the gate, and no entry in any list, is
  required for a newly added agent-bearing job to be checked.

- **FR-004**: The gate MUST fail when the derived subject set loses a
  member relative to the set the repository is known to contain —
  including an agent step removed from a job, an agent step renamed to a
  reference the rule no longer matches, and a workflow file deleted. The
  comparison MUST be against a checked-in floor that names the
  agent-bearing jobs the repository is known to contain — including the
  jobs the exclusion record covers, since the floor answers "is this job
  still here" and the exclusion record answers "does the contract apply
  to it". Derivation MUST cover every member of the floor and MAY exceed
  it:

  - a job the floor names that derivation no longer yields MUST fail the
    gate, naming that job;
  - a job derivation yields that the floor does not name MUST be
    inspected like any other subject and MUST NOT fail the gate merely
    for being absent from the floor, so a newly added agent-bearing job
    is covered with no edit to the gate and an un-updated floor fails
    safe.

- **FR-005**: The gate MUST fail when derivation yields zero subjects,
  reporting that it is misconfigured or cannot reach its subject, rather
  than reporting a pass over an empty result set.

- **FR-006**: The gate MUST fail when a workflow file it must read
  cannot be read or parsed, naming the file.

- **FR-007**: The gate MUST report, on both a passing and a failing run,
  the subject set it derived — the workflow files and job names it
  actually inspected — so a reader can confirm coverage without
  re-deriving it.

- **FR-008**: Derivation MUST be structural: an agent step is recognised
  by the step's own action reference, never by a match against the file
  as text, so that a mention of the agent action inside a comment,
  a documentation block, or a gate fixture never becomes a subject.

- **FR-009**: The gate's `--self-test` MUST cover the regressions
  derivation newly makes possible, at minimum: a subject dropped
  (FR-004 — a job the floor names that derivation no longer yields), a
  derived set emptied (FR-005), and an agent step spelled in a way the
  derivation rule fails to recognise. Each mutation MUST be asserted to
  fail the gate.

- **FR-010**: The `--self-test` MUST preserve the intent of the existing
  subject-list mutations (`the subject list pointed at a 9th,
  nonexistent workflow file`, `the subject list pointed at zero workflow
  files`, `the subject list pointed at a nonexistent job inside an
  existing file`) — either by keeping them working against the derived
  set, or by replacing each with the equivalent "a subject was dropped"
  mutation. A mutation MUST NOT be deleted without a replacement that
  exercises the same failure branch.

- **FR-011**: The `--self-test` MUST continue to fail loudly when a
  mutation changes nothing in the shipped tree — the existing "the code
  it edits was rewritten; update the mutation" signal — so that
  derivation cannot quietly turn an existing mutation into a no-op.

- **FR-012**: Every job in the repository that contains an agent step
  MUST end this feature either inspected and passing, or listed in a
  checked-in exclusion record that names the workflow, the job, and the
  reason the post-agent credential defect cannot occur there.

- **FR-013**: The gate MUST fail when it derives a subject that is
  neither compliant nor present in the exclusion record; an exclusion
  MUST be an explicit, checked-in act, never the absence of an entry.

- **FR-014**: The disposition of the agent-bearing jobs derivation newly
  surfaces — `board-loop.yml`'s five agent steps, `cleanup.yml`'s
  `Completion summary`, `rebase.yml`'s `Resolve conflicts`, and
  `watchdog.yml`'s `diagnose` — MUST be decided per workflow, following
  spec 052's precedent, by this rule: a job whose agent step carries no
  wall-clock bound **and** which is followed by a step that acts as the
  bot MUST adopt the post-agent credential contract in this feature;
  every other agent-bearing job MUST be excluded with its reason
  recorded per FR-012. `watchdog.yml`'s `diagnose` is excluded on the
  stated basis that its agent step carries `timeout-minutes: 10`, an
  order of magnitude under the credential's one-hour lifetime — the same
  reason spec 052 recorded for the two `auto-update-spec-kit.yml` jobs.
  `board-loop.yml`'s five agent steps, `cleanup.yml`'s `Completion
  summary` and `rebase.yml`'s `Resolve conflicts` MUST each be assessed
  against the rule and land in whichever of the two states it yields,
  with the outcome recorded either way.

- **FR-015**: Any companion map inside the gate that is keyed to the
  same jobs as the subject list — the stall-reason job map, the
  failed-step-required job map, and the per-agent-step composite
  exemptions — MUST either be derived by the same rule, or carry a
  stated reason in the gate for why it remains enumerated. A map left
  hand-kept without a reason reintroduces the decay this feature
  removes, one layer down.

- **FR-016**: The gate MUST remain reachable through the existing gate
  registry and MUST run the same subject with the same arguments locally
  (`python .github/scripts/run-local-gates.py`) as it does in CI, and
  MUST be triggered by changes to the workflow files it inspects.

- **FR-017**: The gate's own docstring and its comment block in the
  lint-workflows registry MUST describe the derived subject set rather
  than a fixed count of named stages, since the count is no longer
  fixed.

- **FR-018**: This feature MUST NOT weaken any check the gate performs
  today: every check that fails on the shipped tree under a given
  mutation before this feature MUST still fail under that mutation
  after it.

### Key Entities

- **Subject job**: a workflow job the gate inspects — identified by
  workflow file path and job name, produced by the derivation rule
  rather than typed in.
- **Agent step**: a step whose action reference is the agent action;
  the structural marker derivation keys on.
- **Exclusion record**: the checked-in statement that a given
  agent-bearing job is deliberately not subject to the post-agent
  credential contract, with the reason the defect cannot occur there.
- **Subject floor**: the checked-in list of agent-bearing jobs the
  repository is known to contain, which the derived set is compared
  against so a disappearing subject fails. Derivation must cover it and
  may exceed it (FR-004).
- **Mutation**: a deliberate, reversible edit to an in-memory copy of
  the shipped tree that the gate's `--self-test` asserts must fail the
  gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding a job with an agent step and a stale post-agent
  credential reference to any workflow causes the gate to fail, with
  zero lines changed in the gate itself.

- **SC-002**: Removing an agent step from any currently-derived subject
  job causes the gate to fail, naming the job that is no longer a
  subject.

- **SC-003**: Zero jobs in the repository contain an agent step and are
  neither inspected by the gate nor named in the exclusion record — down
  from the four workflows (eight agent steps) in that state today.

- **SC-004**: Zero workflow paths or job names are enumerated by hand in
  the gate for the purpose of selecting subjects; any remaining
  enumeration exists for a stated reason other than subject selection —
  the FR-004 floor (drop detection), the FR-012 exclusion record
  (disposition), or an FR-015 companion map with its reason stated.

- **SC-005**: The gate's `--self-test` reports that every documented
  mutation fails, and the mutation count does not decrease relative to
  the shipped gate — each retired mutation has a named replacement.

- **SC-006**: The full local gate suite passes on the shipped tree
  before and after this feature, and the gate passes on the tree it
  ships with.

- **SC-007**: A reader of a gate run's output can name every workflow
  file and job the gate inspected without opening the gate's source.

## Assumptions

- The originating issue's items 2, 3 and 4 are already on `main`
  (commit `2a1cf1b`, "#410 items 2-4"); this feature is item 1 only.
  Verified against the shipped `TOKEN_REF_RE`, the shipped
  `verify-implement-stall-notice-unchanged.py --self-test` and its
  registry wiring, and `research.md`'s D3 pointer at D10a.
- The gate keeps its current shape: a single Python verifier over
  statically parsed workflow YAML, run from the repository root, with a
  `--self-test` mode that mutates in-memory copies of the shipped tree.
  Deriving subjects is a change to how it chooses what to read, not a
  change to what the checks mean.
- The eight sweep-stage jobs that pass the gate today continue to pass
  it after derivation; the derived set is expected to be a superset of
  today's list, never a different one.
- `AGENTLESS_JOBS` exists today because `tasks-approved` is in the
  hand-kept list for the checks that apply to every job regardless of
  agent-step presence (the over-budget tolerance check and the
  single-home composite check). Those checks' own population is
  independent of the agent-step derivation and is expected to keep its
  current reach.
- No change to the credential mechanism, the relay design, or any
  composite this gate checks for is implied by this feature; the subject
  of the change is the gate's subject selection.
- The repository's workflow files remain the single source of truth for
  which jobs run agents — there is no external registry of stages to
  derive from.

## Out of Scope

- **Item 2 of the originating issue** — extending the token-reference
  pattern to `toJSON(steps.<id>)` / `toJSON(steps)`. Already on `main`
  with its two self-test mutations.
- **Item 3** — a `--self-test` for
  `verify-implement-stall-notice-unchanged.py`. Already on `main` and
  wired in the registry.
- **Item 4** — the stale `toJSON(steps)` wording in spec 052's
  `research.md`. Already corrected to point at D10a.
- Changing what any post-agent check asserts, the credential relay
  mechanism, the refresh composites, or the one-hour credential
  lifetime.
- Deriving subjects for any gate other than the post-agent credential
  gate, however similar its hand-kept-list shape.
- Retrofitting the post-agent credential contract onto agent steps
  outside this repository's workflows.
- Any new agent-facing surface, prompt, or model judgement; this feature
  is deterministic throughout (Constitution Principle IX).

## Dependencies

- `.github/scripts/verify-post-agent-credential-refresh.py` — the gate
  whose subject selection changes.
- `.github/workflows/lint-workflows.yml` — the gate registry that wires
  Gate 68 and its self-test, and the comment block FR-017 updates.
- `.github/scripts/run-local-gates.py` — the local suite FR-016 requires
  the gate to remain reachable through.
- `specs/052-agent-credential-lifetime/` — the governing spec for what
  the post-agent checks mean (FR-007, FR-020, FR-021, FR-022, SC-005)
  and the precedent for recording a reasoned scope exclusion.
- `.specify/memory/constitution.md` — Principle VIII (a gate that cannot
  reach its subject fails loudly; every failure branch exercised by a
  checked-in fixture) and Principle IX (deterministic, not prompted).
- `CLAUDE.md` — the single-home rule the gate's composite checks
  enforce, unchanged by this feature.
