# Feature Specification: E2E-Stage Failure Detail Travels as an Artifact

**Feature Branch**: `118-e2e-stage-detail-artifact`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Give auto-update-spec-kit's e2e-stage failure-detail the artifact treatment (Gate 49 PROSE exception). `verify-job-outputs-prose-free.py:156` (Gate 49) exempts `auto-update-spec-kit.yml`'s `e2e-stage` output `failure-detail`. The entry describes itself as '#287's defect class waiting to recur — needs the artifact treatment in its own change'. That change has no tracking issue, so this issue tracks it. Done when `failure-detail` moves to an artifact (or another prose-free form) the way #287's fix did for the other stages, and the PROSE exception is deleted. Found by the code review of #730."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A failed Spec Kit candidate always explains itself on the lifecycle issue (Priority: P1)

A maintainer watches the auto-update stage evaluate a minor or major Spec
Kit candidate. The end-to-end stage runs a disposable agent against a
scratch repository, the candidate misbehaves, and the stage records why —
a diagnostic built from the agent run's own verdict.

Today that diagnostic rides a job-level output. The runner inspects every
job output at job completion and drops the whole value if any substring of
it looks like a masked secret; the mask fires on any `key=value` token
whose key is one of two well-known credential words, whether or not a real
secret matches. A diagnostic that happens to quote such a line from the
scaffolded repository empties the output silently. The lifecycle issue
then carries a callout that says verification failed and nothing else, and
the maintainer has to open run logs to learn anything — which is exactly
what the issue text is required to spare them.

After this feature the diagnostic body travels as a run artifact, the way
issue #287's fix moved the other stages' bodies, and the job output no
longer carries it. The text a maintainer reads on the issue is byte-for-byte
what the stage wrote, whatever it quotes.

**Why this priority**: This is the reported defect and the whole of the
issue's "done when". Every other story in this spec is a consequence of it.

**Independent Test**: Drive the stage with a diagnostic that contains a
masker-triggering token and confirm the lifecycle issue's callout carries
the full text. Delivers the user value on its own.

**Acceptance Scenarios**:

1. **Given** the end-to-end stage produced a diagnostic containing a
   `key=value` token the runner's masker redacts, **When** the cycle
   reports the failure, **Then** the lifecycle issue's callout body is the
   complete diagnostic, with no part of it dropped.
2. **Given** the end-to-end stage produced an ordinary diagnostic with no
   masker-triggering token, **When** the cycle reports the failure,
   **Then** the issue text is identical to what it is today — this change
   alters the transport, not the wording.
3. **Given** the end-to-end stage passed, **When** the version-bump pull
   request is opened, **Then** its body carries the same scratch-repository
   pointer sentence it carries today.

---

### User Story 2 - Gate 49's register stops advertising a pending defect (Priority: P2)

A maintainer reads Gate 49's exception register to see what the rule does
not yet cover. Today one entry names this output and describes itself as
"#287's defect class waiting to recur". A register entry that names work
nobody is tracking reads as a permanent carve-out rather than a debt.

After this feature the PROSE entry for this output is gone, and the gate
itself is what stops the shape from returning: reinstating a prose-carrying
job output on this job fails the gate rather than being tolerated.

**Why this priority**: Deleting the entry is the issue's second "done
when". It is also what keeps the fix from being undone by the next edit,
which is the only reason the transport change stays true.

**Independent Test**: Remove the entry, run the gate, and confirm it
passes; re-introduce a prose job output on the job and confirm the gate
fails.

**Acceptance Scenarios**:

1. **Given** the diagnostic has moved to an artifact, **When** Gate 49
   runs, **Then** it passes with no PROSE exception registered for this
   job.
2. **Given** a change reinstates a prose-carrying job output on this job,
   **When** Gate 49 runs, **Then** it fails and names that output.
3. **Given** the exception entry were deleted without the transport
   change, **When** Gate 49 runs, **Then** it fails — the entry and the
   shape are removed together or not at all.

---

### User Story 3 - A body that cannot be loaded is still narrated (Priority: P3)

The diagnostic's new transport introduces a way for the body to be absent
that a job output did not have: the artifact was never uploaded, the
download failed, or the file is empty. The stage already has a degradation
path for its neighbouring case — a stage that did not complete at all is
reported as "a stage/infrastructure problem, not a candidate defect", with
the run URL — and the reporting job is required to never post a bodyless
callout.

After this feature the missing-body case joins that path: the maintainer
reads a sentence saying the diagnostic could not be loaded and where to
look, never an empty callout.

**Why this priority**: It protects the P1 outcome against the new failure
mode this change creates. It is lower priority only because it fires on a
path P1 does not exercise.

**Independent Test**: Run the reporting leg with the artifact absent and
confirm the posted body is non-empty and names the cause.

**Acceptance Scenarios**:

1. **Given** the end-to-end stage failed but its diagnostic artifact is
   absent or empty, **When** the cycle reports the failure, **Then** the
   lifecycle issue carries a non-empty body naming the missing diagnostic
   and pointing at the run.
2. **Given** the end-to-end stage job did not complete at all, **When** the
   cycle reports the failure, **Then** the issue carries today's
   "stage/infrastructure problem, not a candidate defect" narration
   unchanged.

---

### Edge Cases

- The end-to-end stage is skipped entirely (a patch candidate never reaches
  it). No diagnostic exists and none is expected; the reporting job must
  not treat the absent artifact as an error on this path.
- The stage passes. A diagnostic body may still exist — today the
  scratch-repository pointer is appended to the same string on the pass
  path and lands in the pull request body — so a pass must not be a case
  where the body is skipped.
- The stage's read-back step is itself the degradation path for a
  non-healthy agent verdict and runs unconditionally today. Whatever
  produces the artifact must fire on that path too, or the very failures
  the diagnostic exists to explain lose their explanation.
- Two consecutive cycles for the same lifecycle issue. Artifact names must
  not collide across runs in a way that lets one cycle read another's body.
- The diagnostic is multi-line and may contain characters that are awkward
  in a shell here-document; the transport must not re-introduce a
  delimiter-collision hazard the current heredoc-style output write already
  guards against.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The end-to-end stage MUST publish its failure diagnostic as a
  run artifact rather than as a job-level output value.
- **FR-002**: After this change the end-to-end stage's job-level outputs
  MUST NOT include the diagnostic text. The remaining outputs MUST carry
  only synthesized or enumerated values (the pass/fail verdict, the scratch
  repository and branch, the agent-ran facts).
- **FR-003**: The job that composes the cycle's report MUST load the
  diagnostic body from that artifact, and the load MUST be positioned so
  that an absent or unreadable body is detected before any report text is
  composed or posted.
- **FR-004**: The composed report MUST preserve today's precedence and
  wording exactly: the "never reached the check" arm, the end-to-end tier's
  own diagnostic, the stage-did-not-complete synthesis, and the appended
  scratch-repository pointer. A reader MUST NOT be able to tell from the
  issue text that the transport changed.
- **FR-005**: When the end-to-end stage ran but no diagnostic body can be
  loaded, the report MUST state that the diagnostic is unavailable and name
  where to look, and MUST NOT be empty.
- **FR-006**: The artifact MUST be produced on every path where the stage
  records a diagnostic, including the degradation path taken when the agent
  step's verdict is not healthy.
- **FR-007**: The PROSE exception entry naming this job and output MUST be
  deleted from Gate 49's register in the same change that moves the
  transport.
- **FR-008**: Gate 49 MUST continue to fail if a prose-carrying job output
  is reinstated on this job, and MUST continue to fail if a registered
  exception stops being flagged. Neither behaviour may be weakened to let
  this change pass.
- **FR-009**: Every failure branch this change ships — at minimum the
  missing-body branch of FR-005 — MUST be exercised by a checked-in
  fixture, not by a manual demonstration.
- **FR-010**: If the load step must exist in more than one job, the change
  MUST give it a single home — a composite action, or registration as a
  twin-step pair whose copies a gate holds byte-identical — never a second
  pasted copy.
- **FR-011**: The diagnostic artifact MUST be scoped to its own run so that
  a later cycle for the same lifecycle issue cannot read an earlier cycle's
  body.
- **FR-012**: [NEEDS CLARIFICATION: Does this change stop at the end-to-end
  stage's output, or does it also move the composing job's own diagnostic
  output — which carries the same model-derived text across a second job
  boundary that Gate 49 does not currently inspect?]
- **FR-013**: [NEEDS CLARIFICATION: When the stage ran and failed but its
  diagnostic body cannot be loaded, should the reporting leg fail loudly
  (matching how the watchdog's per-finding loader treats a missing body) or
  degrade to a synthesized message (matching this stage's existing
  stage-did-not-complete arm)?]
- **FR-014**: [NEEDS CLARIFICATION: Should Gate 49 be widened in this
  change to follow taint across job boundaries, so the new shape is
  enforced rather than merely adopted, or is widening the gate a separate
  piece of work?]

### Key Entities

- **Failure diagnostic**: the plain-language explanation of why a Spec Kit
  candidate was not adopted. Model-derived, multi-line, may quote text from
  the scaffolded repository. Read by a maintainer on the lifecycle issue,
  and on the pass path by a reviewer on the version-bump pull request.
- **Diagnostic artifact**: the run-scoped carrier the diagnostic travels
  in, replacing the job output. Produced by the end-to-end stage, consumed
  by the job that composes the report.
- **Gate 49 exception register**: the list of tolerated (file, job, output)
  triples. Each entry is reported as a warning and the gate fails when an
  entry stops being flagged, so an entry can only be retired together with
  the shape it excuses.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A failure diagnostic containing a masker-triggering token
  reaches the lifecycle issue complete, 100% of the time — the drop rate
  for such diagnostics goes from "whenever the token appears" to zero.
- **SC-002**: The exception register carries zero entries describing
  themselves as a defect class waiting to recur.
- **SC-003**: For an unchanged diagnostic, the text posted on the lifecycle
  issue and in the pull request body is identical before and after the
  change.
- **SC-004**: Every reporting path — pass, candidate failure, stage did not
  complete, diagnostic unavailable — posts a non-empty body; no path can
  produce an empty callout.
- **SC-005**: Reinstating a prose-carrying job output on this job is caught
  by the gate suite before merge, in under one full local gate run.
- **SC-006**: A maintainer diagnosing a failed cycle needs zero run-log
  reads to learn why the candidate was rejected.

## Assumptions

- The workflow declares no `workflow_call`-level outputs, so removing a
  job-level output is internal plumbing and not a change to the
  adopter-pinned published contract.
- "Artifact treatment" means the pattern issue #287's fix established
  elsewhere in this repository: the body travels in a run artifact, the job
  output carries only synthesized identifiers, and the consuming job loads
  the body before it does anything with it.
- The wording of every existing diagnostic string stays as it is. This
  change moves text, it does not rewrite it.
- The end-to-end stage only runs for minor and major candidates; patch
  candidates never reach it, and nothing about the patch path changes.
- The existing agent-transcript artifact this stage already uploads stays
  as it is; it serves a different purpose (the maintainer's route to the
  agent's own log) and is not the carrier this feature introduces.
- Spec directories for features whose final pull request has already merged
  are historical records, so the two specs that describe this workflow's
  current behaviour are read here as context and are not edited by this
  feature.
