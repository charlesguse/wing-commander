# Feature Specification: An Honest Read-Failure Policy for board-stop-check's Closed Check

**Feature Branch**: `spec-draft/088-stop-check-closed-read`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #623 — "board-stop-check's closed-check
continue-on-error is a real fail-open change, not a preserved fallback
(`set -uo pipefail` keeps `-e` active)" (routed from board-loop.yml,
originating issue #471)

## Overview

GitHub Actions runs a `shell: bash` step as
`bash --noprofile --norc -eo pipefail {0}`. Errexit is therefore active
from the **outer** invocation, before the script's first line executes. A
script that opens with `set -uo pipefail` — which is the universal opening
line of this repository's shell steps — does **not** clear it: `set` only
touches the options it is explicitly passed, so `-e`'s existing value
carries through unchanged. A failing command inside a `var="$(...)"`
assignment aborts the step immediately; it does not fall through with an
empty variable.

Several shipped comments in this repository state the opposite. The one
that matters most sits on the step this feature is about.

`wing-commander-board-stop-check` is the composite every board-loop job
calls immediately before its own next durable action. Only the `prove`
job passes `check-issue-closed: "true"`, which arms a `closed-check` step
that delegates to `wing-commander-lifecycle-gate` under
`continue-on-error: true`. The comment above it claims that tolerance
preserves prior behaviour. It does not: the code it replaced was a bare
`state="$(gh issue view … --jq .state)"` with no tolerance, running under
the same errexit-active semantics, so a failed read **failed the step and
the job**. `continue-on-error: true` is a real, deliberate behaviour
change — fail-loud to fail-open — that shipped as an accident under a
comment asserting it was a no-op.

This feature does three things. It makes the read-failure policy for that
step an explicit decision and states it truthfully in the composite. It
settles whether a tolerated read failure can manufacture a watchdog
`pipeline-defect` against an otherwise-healthy `prove` run. And because
the same misreading of `-e` is what let the mistake through every review
pass, it corrects the repository's other comments that repeat the claim
and puts a gate behind the corrected fact so the next one cannot ship.

### Observed facts (verified against main at 53b7450)

- `.github/actions/wing-commander-board-stop-check/action.yml:78-81`
  reads: "continue-on-error: the behaviour this replaces already treated a
  failed read as 'not closed, keep going' rather than failing the job;
  this keeps that same fallback…". The behaviour it replaced did fail the
  job. CLAUDE.md: "Workflow comments are load-bearing… treat comment edits
  as code edits."
- When `closed-check` fails all three of `lifecycle-gate`'s attempts, its
  `is-open` output is never written. The next step's
  `ISSUE_IS_OPEN` is therefore empty, `[ "$ISSUE_IS_OPEN" = "false" ]` is
  false, and the composite proceeds as though the issue were open — the
  fail-open path, reached silently, with the stop-request scan and the
  kill switch still honoured.
- `wing-commander-board-stop-check` is the only one of the seven
  `wing-commander-lifecycle-gate` call sites (`intake.yml`, `tasks.yml`,
  `clarify.yml`, `implement.yml`, `finalize.yml`, `pr-conversation.yml`,
  and this composite) that pairs it with `continue-on-error: true`.
- `lifecycle-gate` emits one `::warning::` per failed attempt and a final
  `::error::` on total failure. `watchdog.yml`'s `Collect: annotations`
  step (`.github/workflows/watchdog.yml:1136-1189`) fetches check-run
  annotations for every job whose **job conclusion** is not `skipped` or
  `cancelled`; it never asks whether the job succeeded. Those annotations
  become `annotations`-kind signals, are fingerprinted, and are fed to the
  diagnose agent that can open a `pipeline-defect`. A green `prove` job
  whose tolerated `closed-check` exhausted its retries therefore carries
  `warning`/`failure` annotations into the classifier today.
- `action.yml:171` interpolates raw, potentially multi-line `gh` stderr
  into a workflow command:
  `echo "::warning::gh run cancel $stop_run_id failed: $cancel_error"`.
  `lifecycle-gate`, called two steps above, already carries a
  `sanitize()` helper (newline/tab flattening, 300-char truncation, `%`
  escaping) written for exactly this hazard.
- `verify-gate-24.py` sets `WORKFLOWS_GLOB = ".github/workflows/*.yml"`
  and globs nothing else, so Gate 24 never inspected this composite's
  `if:`/`continue-on-error:` pair. #465's "Gate 24: 0 findings" was true
  only because the text had moved to a file Gate 24 does not scan.
  Re-checked by hand: the guard is **not** stranded today, because the
  next step reads `steps.closed-check.outputs.is-open` with no `if:`
  condition on that step's outcome. No live bug — a correction to what
  the stated evidence established.
- The same "no `-e`" claim appears in at least four more places:
  `board-loop.yml:1653` ("this step runs without -e, so a failed create
  would otherwise still post the re-route comment"),
  `metrics-persist.yml:348` ("under `set -uo pipefail` with no `-e` the
  resulting empty window_start/list_from silently listed the
  repository's ENTIRE run history"), `implement.yml:2785` ("No `-e`: an
  unreadable file degrades to empty fields… this step must never fail,
  since 'Mark lifecycle record stalled' below carries no always() and
  would be stranded"), and `lint-workflows.yml:1921` (Gate 19's
  motivating narrative). Each of those steps is `shell: bash` and so runs
  with errexit on. Re-checked by hand: all three of the live ones happen
  to be safe anyway — `board-loop.yml`'s URL guard is belt-and-braces
  behind an assignment that would already have aborted,
  `implement.yml`'s reads are each `|| true`-guarded and its writes
  cannot fail — so these are false premises, not live bugs. A premise
  nobody can trust is what produced this issue.
- `verify-board-stop-check.py` already extracts this composite's `check`
  step and drives it under `bash -eo pipefail` against a stub `gh`,
  including a mutation that must be caught. It is the nearest existing
  home for any new assertion about this step, as CLAUDE.md asks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The read-failure policy is a decision, stated truthfully (Priority: P1)

A maintainer reading `wing-commander-board-stop-check` wants to know what
happens when the `prove` job cannot determine whether its lifecycle issue
is closed, and to see that the answer was chosen rather than inherited.
Today the comment tells them tolerance preserves the old behaviour, which
is the opposite of what the old code did, so the honest answer is not
recoverable from the file at all.

**Why this priority**: This is the correction the issue exists for, it
touches a load-bearing comment on the repository's kill-switch path, and
every other item here is either downstream of the policy choice or
cosmetic. It also stands alone: correcting the comment and naming the
policy delivers value even if nothing else in this feature ships.

**Independent Test**: Read the composite with no other context and state
(a) what happens on a total read failure and (b) what the pre-#465 code
did. Both answers must be present and must match the shipped behaviour
and the git history respectively.

**Acceptance Scenarios**:

1. **Given** the shipped composite, **When** a reader reaches the
   `closed-check` step, **Then** its comment states the actual
   read-failure behaviour and does not claim that behaviour was inherited
   from the code it replaced.
2. **Given** the `prove` job and a lifecycle-issue state read that fails
   every retry, **When** the composite runs, **Then** the outcome matches
   the policy the comment states, and the reason the step took that path
   is visible in the run without reading the composite's source.
3. **Given** the chosen policy is fail-open, **When** the read fails
   totally, **Then** the kill switch and the stop-request scan are still
   evaluated and can still set `paused=true` — a failed closed-check
   never weakens the two checks that do not depend on it.
4. **Given** the chosen policy is fail-loud, **When** the read fails
   totally, **Then** the job stops before its next durable action rather
   than proceeding on an unknown issue state, and the `prove` job's
   close-or-redrive step does not run.

---

### User Story 2 - A tolerated read failure does not accuse a healthy run (Priority: P1)

A maintainer watching the board loop wants `pipeline-defect` issues to
mean something. If a transient, retried, and deliberately tolerated
issue-state read can leave `::warning::`/`::error::` annotations that the
watchdog collects from a green `prove` job and hands to the classifier,
the loop can open a defect issue against a run that behaved exactly as
designed — and then spend a board cycle triaging it.

**Why this priority**: A false `pipeline-defect` consumes the autonomous
loop's own capacity and erodes the signal the watchdog exists to provide
(constitution Principle VIII, "A Green Check Means What It Says"). The
collection path is confirmed to reach the classifier today.

**Independent Test**: Drive `prove` with a lifecycle-gate read that fails
all attempts and a tolerated `closed-check`, then inspect what the
watchdog's signal set contains for that run and whether a
`pipeline-defect` can be filed from it.

**Acceptance Scenarios**:

1. **Given** a `prove` job that completes green with a tolerated
   `closed-check` that exhausted its retries, **When** the watchdog
   inspects that run, **Then** no `pipeline-defect` is opened on the
   strength of that step's annotations alone.
2. **Given** a genuine, untolerated `lifecycle-gate` failure at any of
   its other six call sites, **When** the watchdog inspects that run,
   **Then** its annotations still reach the classifier unchanged — the
   remedy must not blind the watchdog to real failures.
3. **Given** the chosen policy under FR-002 is fail-loud, **When** this
   story is evaluated, **Then** it is satisfied by construction (no
   tolerated step remains) and requires no further change.

---

### User Story 3 - The `-e` fact has one home and a gate behind it (Priority: P2)

A contributor writing or reviewing a `run:` step needs to know, without
re-deriving it, that `set -uo pipefail` leaves errexit on. Five shipped
comments currently tell them the opposite, and every review pass on #465
— including the reviewer who later caught it — assumed the wrong
semantics. Correcting only the one comment on the `closed-check` step
leaves the belief that produced it intact and undocumented.

**Why this priority**: It is the root cause, and it is the part most
likely to recur. It ranks below the first two because no live defect is
known to follow from the other four comments today; their cost is the
next mistake, not the current run.

**Independent Test**: Search the repository for any comment claiming a
`shell: bash` step runs without errexit; the search returns nothing, and
one canonical statement of the correct semantics exists that the other
sites point at. Then add such a claim and confirm the gate suite fails.

**Acceptance Scenarios**:

1. **Given** the repository after this feature, **When** every `run:`
   step comment is read, **Then** none asserts that `set -uo pipefail`
   clears `-e` or that a `shell: bash` step runs without errexit.
2. **Given** the corrected fact, **When** a second site needs to explain
   it, **Then** it points at the single canonical statement rather than
   restating it, per CLAUDE.md's "Shared logic has exactly one home".
3. **Given** a new comment that claims a `shell: bash` step runs without
   `-e`, **When** the PR-time gate suite runs, **Then** it fails and
   names the file, the line, and the corrected fact.
4. **Given** the corrected comments, **When** each affected step's actual
   behaviour is checked, **Then** any step whose logic depended on the
   false premise is either shown safe in the comment or fixed — a comment
   correction must not paper over a real fall-through.

---

### User Story 4 - The small inconsistencies in the same file are closed (Priority: P3)

A maintainer reading a `gh run cancel` failure in the log wants the whole
diagnostic on one line. Raw multi-line `gh` stderr interpolated into a
`::warning::` can be truncated or misparsed by Actions at an embedded
newline, and the sibling composite called two steps above already has the
helper that prevents it.

**Why this priority**: Cosmetic worst case — a garbled log line — but it
is an inconsistency introduced by the same change that reused
`sanitize()`'s reasoning without reusing `sanitize()`, and it needs no
design decision.

**Independent Test**: Drive the composite's cancel path with a stub `gh`
whose stderr is multi-line and contains a `%`, and confirm the emitted
warning is a single, complete, bounded line.

**Acceptance Scenarios**:

1. **Given** a `gh run cancel` that fails with multi-line stderr, **When**
   the composite reports it, **Then** the warning is one line, length-
   bounded, and its `%` characters do not corrupt the workflow command.
2. **Given** the flattening behaviour, **When** a second composite needs
   it, **Then** it is reached from one shared home rather than pasted a
   third time.
3. **Given** Gate 24's documented scope, **When** a reader asks whether
   it inspected this composite, **Then** the answer is recorded in the
   gate itself rather than left to be rediscovered by a future PR making
   the same vacuous claim.

---

### Edge Cases

- The state read succeeds but returns a value that is neither OPEN nor
  CLOSED. `lifecycle-gate` already fails loudly rather than guessing; the
  `closed-check` policy must not convert that deliberate refusal into a
  silent "assume open".
- The state read fails on attempt 1 and 2 and succeeds on attempt 3. Two
  `::warning::` annotations exist on a job that behaved perfectly. This is
  the common transient case and must not produce a defect issue either.
- The read fails with a permanent classification (not-found, credentials
  rejected). `lifecycle-gate` exits after one attempt with `::error::`.
  Under a fail-open policy this is indistinguishable, to the composite,
  from a transient exhaustion — and a permanently unreadable lifecycle
  issue is a configuration fault, not a blip.
- The issue is genuinely CLOSED and the read succeeds. Unchanged: `paused`
  becomes true and `prove` stands down.
- The kill switch is already on (`initial-paused: true`) and the state
  read fails. `paused` must remain true regardless of policy; a failed
  closed-check can never *un*-pause.
- A comment that discusses errexit correctly, or quotes the wrong claim in
  order to correct it, must not trip the new gate.
- The four other "no `-e`" comments include historical narrative about
  past bugs. Correcting the semantics must not erase the record of what
  actually happened in those runs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `closed-check` step's comment in
  `wing-commander-board-stop-check` MUST state what the step actually
  does on a read failure, and MUST NOT claim that behaviour was preserved
  from the code it replaced. If it describes the prior behaviour at all,
  it MUST describe it as failing the job.

- **FR-002**: The read-failure policy for the `prove` job's lifecycle-issue
  state check MUST be one explicit decision, recorded in the composite
  alongside the trade-off it resolves.
  [NEEDS CLARIFICATION: fail-open or fail-loud? Keeping
  `continue-on-error: true` means a `prove` job whose state read fails all
  three retries proceeds treating the issue as open — it may close or
  redrive an issue a maintainer already closed. Dropping it matches the
  pre-#465 fail-loud behaviour and this repository's stated preference for
  refusing to guess (`lifecycle-gate`: "fails on any other value rather
  than guessing"; Gate 25), at the cost of failing a `prove` job on a
  transient read that three retries and a 4s timeout already survive most
  of the time.]

- **FR-003**: Whatever FR-002 resolves to, a `closed-check` that cannot
  determine the issue state MUST NOT weaken the kill-switch re-check or
  the stop-request scan: `paused` MUST still become `true` when
  `initial-paused` is true or a valid stop request is found.

- **FR-004**: A `closed-check` read failure MUST be visible in the run it
  occurred in — naming which issue could not be read and what the policy
  did about it — rather than only inferable from the absence of an output.

- **FR-005**: A `prove` job that completes successfully MUST NOT, on the
  strength of a tolerated `closed-check`'s retry warnings or total-failure
  error alone, cause the watchdog to open a `pipeline-defect` issue.
  [NEEDS CLARIFICATION: where does this remedy live? (a) the tolerated
  call site suppresses or downgrades the annotations, e.g. via a new
  `lifecycle-gate` input, which changes a composite seven call sites
  share; (b) the watchdog's annotation collector or classifier learns to
  discount annotations produced by a step the caller declared survivable,
  which changes classification for the whole fleet; (c) accept the noise
  and document it, on the grounds that a triage pass closing it with
  quoted evidence is cheap. Moot if FR-002 resolves to fail-loud.]

- **FR-006**: The remedy chosen for FR-005 MUST NOT suppress annotations
  from an untolerated `lifecycle-gate` failure at any of its other call
  sites, nor from any other step whose failure is not declared
  survivable.

- **FR-007**: No comment in this repository may assert that a
  `shell: bash` step runs without errexit, or that `set -uo pipefail`
  clears `-e`. The five known sites
  (`wing-commander-board-stop-check/action.yml`, `board-loop.yml`,
  `metrics-persist.yml`, `implement.yml`, `lint-workflows.yml`) MUST be
  corrected, preserving the historical record each was written to carry.

- **FR-008**: The corrected semantics MUST have exactly one canonical
  statement in the repository, with every other site that needs it
  pointing at that statement rather than restating it.

- **FR-009**: A PR-time gate MUST fail on a newly introduced comment that
  makes the FR-007 claim, naming the file and line, and MUST have
  mutation coverage proving it can fail its own subject.

- **FR-010**: For each comment corrected under FR-007, the step's actual
  behaviour MUST be re-checked against the corrected premise, and any step
  that genuinely relied on falling through MUST be fixed rather than only
  re-commented.

- **FR-011**: `gh` stderr interpolated into a workflow command by
  `wing-commander-board-stop-check` MUST be flattened to a single line,
  length-bounded, and `%`-escaped before emission, reusing the existing
  helper's behaviour from one shared home rather than a third copy.

- **FR-012**: Gate 24's documented scope MUST state which paths it
  inspects and that `.github/actions/**` is outside them, so a future PR
  cannot cite "Gate 24: 0 findings" as evidence about a composite.
  [NEEDS CLARIFICATION: does this feature also widen Gate 24 to scan
  `.github/actions/**`, or only record the boundary? Widening would put
  the composite fleet under the gate — `wing-commander-stage-findings`
  alone carries eleven `continue-on-error: true` steps — and any finding
  it surfaces would have to be resolved in this feature's PR. Recording
  the boundary is a one-line change with no blast radius but leaves the
  blind spot open.]

- **FR-013**: Every behavioural requirement above that concerns the
  composite's own shell MUST be covered by the existing
  `verify-board-stop-check.py` harness, which already extracts and drives
  that step, rather than by a new parallel harness.

### Key Entities

- **Lifecycle-issue state read**: the `prove` job's pre-durable-action
  question "is this issue still open?". Resolves to one of three
  outcomes — OPEN, CLOSED, or **undetermined** — where the third is the
  one this feature is about and the one the shipped comment does not
  acknowledge exists.
- **Read-failure policy**: the repository's chosen answer to "what does
  `prove` do when the read is undetermined?" Today implicitly fail-open;
  FR-002 makes it explicit.
- **Tolerated-step annotation**: a `::warning::`/`::error::` emitted by a
  step whose caller declared its failure survivable. Distinguished from an
  ordinary annotation only by the caller's `continue-on-error:`
  declaration, which the watchdog's collector does not currently read.
- **Errexit premise**: the belief, held by a comment, about whether its own
  step aborts on an unguarded failure. A wrong premise is invisible until
  a step is written to depend on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer reading `wing-commander-board-stop-check`'s
  `closed-check` step can state its read-failure behaviour and the
  pre-#465 behaviour correctly, with no reference to git history — and
  both statements match what the code and the history actually do.
- **SC-002**: Zero comments remain in the repository asserting that a
  `shell: bash` step runs without errexit; a search for the claim returns
  no hits.
- **SC-003**: Introducing one such comment fails the PR-time gate suite
  (`python .github/scripts/run-local-gates.py`), and the gate's own
  mutation self-test fails when the check is disabled.
- **SC-004**: A `prove` run whose lifecycle-issue read fails every attempt
  produces zero `pipeline-defect` issues attributable to that step alone,
  across the next 30 days of scheduled board-loop runs.
- **SC-005**: An untolerated `lifecycle-gate` failure at any other call
  site still reaches the watchdog classifier, demonstrated by driving one
  such run.
- **SC-006**: Driving the composite's cancel path with multi-line,
  `%`-containing `gh` stderr yields exactly one complete log line, with
  no truncation at an embedded newline.
- **SC-007**: Every branch of the read-failure policy — read succeeds
  OPEN, succeeds CLOSED, fails transiently then succeeds, fails all
  attempts, returns an unrecognized value — is exercised by
  `verify-board-stop-check.py`, and a mutation of the policy is caught.
- **SC-008**: The full PR-time gate suite passes, and no gate's pass is
  vacuous for the files this feature changes — each gate that is cited as
  evidence actually inspects them.

## Assumptions

- The three retries and 4s per-attempt timeout that `lifecycle-gate`
  already performs are adequate hardening for the transient class; this
  feature changes the policy after those retries are exhausted, not the
  retry strategy itself.
- `prove` remains the only job passing `check-issue-closed: "true"`, so
  the FR-002 decision changes behaviour for that job alone.
- The `board-loop.yml`, `metrics-persist.yml`, `implement.yml` and
  `lint-workflows.yml` comments named in FR-007 describe steps that are
  safe under correct errexit semantics (hand-checked: guarded reads,
  belt-and-braces validation, or historical narrative). FR-010 exists in
  case that check missed one, not because a fix is expected.
- The `prove` job's downstream close-or-redrive step is idempotent enough
  that a fail-loud policy leading to a retried run on the next schedule
  does not duplicate durable action — the resume path already handles a
  job that stopped mid-item.
- Gate 24's `.github/workflows/*.yml` scope is deliberate as shipped, not
  an oversight to be silently widened; whether it changes is the FR-012
  decision.
- No adopter consumes `wing-commander-board-stop-check` directly today, so
  a behaviour change to its `closed-check` needs no published-contract
  migration note beyond the composite's own documentation.

## Dependencies

- `.github/actions/wing-commander-board-stop-check/action.yml` — the
  subject.
- `.github/actions/wing-commander-lifecycle-gate/action.yml` — the
  `closed-check` delegate, its `sanitize()` helper, and the composite
  whose other six call sites FR-006 protects.
- `.github/workflows/board-loop.yml` — the `prove` job at the
  `check-issue-closed: "true"` call site, plus one FR-007 comment.
- `.github/workflows/watchdog.yml` — `Collect: annotations`, the signal
  projection, and the diagnose step that files `pipeline-defect`.
- `.github/scripts/verify-board-stop-check.py` — the existing harness
  FR-013 extends.
- `.github/scripts/verify-gate-24.py` and its self-test — FR-012's
  subject.
- `.github/workflows/lint-workflows.yml` and
  `.github/scripts/run-local-gates.py` — where FR-009's gate is wired in,
  plus one FR-007 comment.

## Out of Scope

- Changing `lifecycle-gate`'s retry count, timeout, or failure
  classification.
- Redesigning the board loop's redrive or concurrency model (issue #460).
- Auditing `continue-on-error:` on steps other than `closed-check`,
  except as FR-012's decision may surface them.
- Any change to the stop-request detection rules in
  `board_stop_check.py` (issues #539, #547, #580).
- Making the watchdog's classifier generally better at distinguishing
  benign from real annotations, beyond the narrow FR-005/FR-006 case.
