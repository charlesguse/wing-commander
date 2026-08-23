# Feature Specification: Watchdog Precision & Determinism Hardening

**Feature Branch**: `024-watchdog-precision-hardening`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Retrospective on specs/015-pipeline-watchdog after ~200 stage-8 runs. The watchdog's spec measures recall, dedup, remediation parity, write safety, loop bounds, coexistence, and latency — but nothing measures false positives, and five of the ten distinct findings it produced were false positives faithfully reported from bad signals. Five gaps in the 015 spec are named: (1) no precision requirement, and FR-004's false-positive duty is placed on `diagnose`, which cannot discharge it; (2) nothing requires a signal to be attributable to the inspected run; (3) FR-016 requires a *stable* fingerprint but never a *deterministic* one; (4) FR-002's 'cite the evidence' has no validity condition, so findings citing empty facts still satisfy it; (5) FR-021's 'no special-case path' was contradicted by the fix that made self-inspection deterministic. Plus a cross-cutting pattern the fixes all shared — moving judgment out of the agent and into deterministic code — that is written down nowhere, and open decisions about dead rungs 1–2 and untestable success criteria."

## User Scenarios & Testing *(mandatory)*

The pipeline watchdog (spec 015) has now run roughly 200 times. Its record is
that of a tool that reliably *detects* but poorly *discriminates*: of ten
distinct findings, five were false positives — genuine-looking reports built
faithfully on signals that were simply wrong about the world — three were
correct detections of injected test failures, and only two were previously
unknown real problems, both surfaced by the watchdog's deterministic parts
rather than its reasoning agent. Nine of nineteen auto-filed issues were
duplicates the dedup layer failed to catch. The false positives and duplicates
cost maintainer attention every time.

The code matches the spec. That is precisely the problem: the specification
never asked for precision, never required a signal to belong to the run it
describes, never required a fingerprint to be reproducible, and never required
cited evidence to actually contain anything. This feature closes those gaps by
strengthening the watchdog's requirements and the project's governing
principles so that the watchdog files a finding **only** when the problem is
real, attributable, reproducibly identified, and backed by non-empty evidence —
and so that the hard-won lesson behind every fix ("move judgment out of the
agent and into deterministic code") is written down where the next contributor
will read it before reaching for a prompt fix.

The audience is the maintainers of this repository. The deliverable is a set of
corrected and added requirements to `specs/015-pipeline-watchdog/spec.md`,
supporting governance changes, and — where decisions are made — the collector
and dedup behavior those requirements demand.

### User Story 1 - Hold the watchdog to a measured precision bar (Priority: P1)

As a maintainer, I want the watchdog to be judged on how often its findings are
*wrong*, not only on how often it catches real problems, so that a watchdog
that cries wolf five times out of ten is recognized as failing a requirement
rather than passing every requirement on the books.

**Why this priority**: Precision is the single missing dimension that reframes
the whole retrospective. Without a false-positive requirement, every one of the
five false positives was, by the letter of the spec, correct behavior. This is
the root gap; the others are the specific mechanisms by which it manifested.

**Independent Test**: Confirm the watchdog's success criteria now include a
precision criterion stated against a real denominator (findings filed) with a
numerator (findings a maintainer confirms as real), and that the criterion is
measurable against the existing run record — not an aspirational number with no
way to compute it.

**Acceptance Scenarios**:

1. **Given** the watchdog's success criteria, **When** a maintainer reviews them, **Then** at least one criterion measures the fraction of filed findings that are genuine (precision), expressed with an explicit numerator and denominator that can be computed from filed findings and their confirmed/rejected dispositions.
2. **Given** the false-positive-avoidance obligation (formerly FR-004), **When** a maintainer reads which component owns it, **Then** the obligation is placed on the collectors that produce signals — the components that can observe the world — and no longer solely on the `diagnose` step, which sees only pre-computed signals and cannot know a signal is wrong.
3. **Given** a run that exhibited no real problem but for which a collector produced a spurious signal, **When** the watchdog processes it under the strengthened requirements, **Then** the spurious signal is suppressed at its source and no finding is filed.
4. **Given** the precision criterion, **When** a maintainer checks whether the watchdog passes it, **Then** the target is ≥70% over the most recent 20 distinct (post-dedup) filed findings, the criterion is not evaluated until at least 10 distinct findings exist, and the window counts distinct findings rather than runs so a correctly-deduplicated recurrence neither inflates nor deflates the result.

---

### User Story 2 - Require every signal to belong to the run it describes (Priority: P1)

As a maintainer, I want a collector to raise a signal about a run **only** when
that run was actually in a position to cause the condition — it executed, and it
owned the artifact being measured — so that the watchdog stops attributing to a
run a branch it never pushed or a stage transition it never promised to make.

**Why this priority**: Two of the five false positives (#112 and #125) were the
same defect twice: a collector measured something the inspected run had no hand
in. Each was patched as a one-off guard on one collector; the underlying
invariant is enforced on two collectors out of five and stated nowhere. A
general requirement prevents the third occurrence.

**Independent Test**: Confirm the requirements state an attribution invariant
that every collector must satisfy, and that a collector fed a run which did not
execute, or which did not own the artifact being measured, emits no signal.

**Acceptance Scenarios**:

1. **Given** the watchdog's requirements, **When** a maintainer reads them, **Then** an attribution invariant requires that a collector emit a signal only when the inspected run both executed and owned the artifact whose condition the signal describes.
2. **Given** a run that never reached the step that would touch a particular branch, **When** the branch-drift collector inspects it, **Then** it attributes no branch condition to that run and emits no signal.
3. **Given** a run that made no stage transition, **When** the stage-transition collector inspects it, **Then** it emits no signal about a transition the run never promised.
4. **Given** the attribution invariant, **When** a maintainer audits the collectors, **Then** the invariant applies to all collectors, not to a subset patched individually.

---

### User Story 3 - Make finding identity deterministic, not merely stable (Priority: P1)

As a maintainer, I want the same defect recurring across runs to produce the
**exact same** finding fingerprint every time, computed the same way from the
same inputs, so that the dedup layer can actually recognize a recurrence and
stop filing the near-nine-in-nineteen duplicates it filed under a fingerprint
that drifted from run to run.

**Why this priority**: Duplicates were the single largest category in the
record (9 of 19). The cause was a fingerprint whose stability was entrusted to
model-authored facts that drifted along several axes. Determinism is a stronger,
testable property than the "stable" the current requirement asks for.

**Independent Test**: Confirm the fingerprint requirement demands determinism —
identical inputs always yield an identical fingerprint — that the fingerprint
basis is the deterministic collector signals rather than free-form
model-authored text, and that inspecting one run twice yields byte-identical
fingerprints.

**Acceptance Scenarios**:

1. **Given** the fingerprint requirement (formerly FR-016), **When** a maintainer reads it, **Then** it requires the fingerprint to be *deterministic* — a pure function of stated inputs producing an identical value on repeated computation — in addition to being stable across cosmetic run-to-run differences.
2. **Given** the same defect present in two different runs, **When** the watchdog computes each finding's fingerprint, **Then** the two fingerprints are identical and the second finding deduplicates against the first.
3. **Given** the fingerprint basis, **When** a maintainer inspects what it is derived from, **Then** it is derived from the deterministic collector signals, not from model-authored narrative text that can vary between otherwise-identical runs.

---

### User Story 4 - Reject findings whose cited evidence is empty (Priority: P2)

As a maintainer, I want a finding to be suppressed rather than filed when the
evidence it cites is missing or malformed, so that a `denied-tool` finding whose
tool and denial list are both empty can no longer satisfy the "cite the
evidence" requirement merely by naming the run.

**Why this priority**: Every `denied-tool` finding in the record carried empty
facts and still passed the current evidence requirement, because the requirement
only asked that a finding *reference* the run, not that its cited specifics
actually exist. A validity condition turns an unfalsifiable requirement into a
gate.

**Independent Test**: Confirm the evidence requirement now imposes a validity
condition — cited facts must be present and match their expected shape — and
that a finding whose cited facts are empty or malformed is suppressed instead of
filed.

**Acceptance Scenarios**:

1. **Given** the evidence requirement (formerly FR-002), **When** a maintainer reads it, **Then** it requires the finding's cited facts to be non-empty and to conform to the expected shape for that finding's class.
2. **Given** a `denied-tool` finding whose cited tool and denial list are both empty, **When** the watchdog validates it, **Then** the finding fails the validity condition and is suppressed, not filed.
3. **Given** a finding whose cited facts are present and well-shaped, **When** the watchdog validates it, **Then** it passes the validity condition and proceeds to triage and dedup.

---

### User Story 5 - Amend the self-inspection requirement to match what was learned (Priority: P2)

As a maintainer, I want the self-inspection requirement to say that the watchdog
must inspect itself *without exemption*, not that it must inspect itself with
*identical* machinery, so that the deterministic self-checker — which replaced a
reasoning step that was elevating benign self-matches into false findings — is
recognized as the stronger form of self-inspection rather than as a forbidden
"special-case path."

**Why this priority**: The current requirement forbids any special-case path for
self-inspection. Reality overruled it: the fix for the watchdog inspecting
itself was to make that checker deterministic, which the requirement's letter
forbids. The requirement is still on the books contradicting the shipped code.

**Independent Test**: Confirm the self-inspection requirement is amended to
require that self-inspection be *unexempted* (never skipped or softened for the
watchdog) rather than *identical* in mechanism, and that it recognizes a
deterministic checker as a valid — indeed stronger — form of self-inspection.

**Acceptance Scenarios**:

1. **Given** the self-inspection requirement (formerly FR-021), **When** a maintainer reads it, **Then** it requires that the watchdog's own runs be inspected with no exemption and no softened checks, and no longer requires the *mechanism* to be identical to the mechanism used for other stages.
2. **Given** the amended requirement, **When** a maintainer compares it to the shipped deterministic self-checker, **Then** the deterministic checker satisfies the requirement rather than violating it.
3. **Given** any watchdog run that exhibits a detectable problem, **When** the watchdog inspects it, **Then** the checks are neither skipped nor weakened relative to the discrimination applied to other stages.

---

### User Story 6 - Write down the deterministic-judgment principle (Priority: P2)

As a maintainer, I want the principle behind every fix in this cluster —
"judgment that gates a durable action belongs in deterministic code, not in an
agent's prompt" — recorded in the project's governing documents, so that the next
contributor reaches for a deterministic gate instead of a prompt tweak, as this
spec's authors did four times before learning otherwise.

**Why this priority**: The pattern is the reusable lesson; without it recorded,
the same class of fix (deterministic 8b, deterministic rung gate, signal-derived
fingerprints, suppression pushed into collectors, an enum the model cannot leave)
will be re-derived by trial and error on the next feature.

**Independent Test**: Confirm the principle is stated in the appropriate
governing document such that a reviewer can cite it when a future change places
gating judgment in an agent prompt.

**Acceptance Scenarios**:

1. **Given** the project's governing documents, **When** a maintainer looks for guidance on where gating judgment should live, **Then** a stated principle establishes that judgment gating a durable action (a filed finding, a fingerprint, a dedup outcome, an autonomous write) belongs in deterministic code rather than an agent prompt.
2. **Given** a future change that places such gating judgment in an agent prompt, **When** a reviewer evaluates it, **Then** they can cite the recorded principle as grounds to move the judgment into deterministic code.

---

### User Story 7 - Never let a failed dedup lookup masquerade as "nothing found" (Priority: P1)

As a maintainer, I want a dedup lookup that could not be completed to be reported
as **unknown** and to suppress filing, rather than collapsing into the "found
nothing, so file it as new" branch, so that a broken lookup degrades into silence
instead of into a stream of duplicate issues.

**Why this priority**: The dedup requirements name three outcomes (none,
match-open, match-closed) and never name a fourth, so the code took the
convenient branch and files on failure — the watchdog's own warning admits it
"may file a duplicate issue". This is the same defect that reached production in
another stage (#167, fixed in #168), and it is a live candidate explanation for
the nine historical duplicates surviving a fix aimed only at fingerprint
stability. Deterministic identity (US3) is necessary but not sufficient if the
lookup that uses the identity cannot report its own failure.

**Independent Test**: Confirm the requirements name an `unknown` dedup outcome
distinct from `none`, that `unknown` suppresses filing, and that the lookup is
specified as a bounded direct read within a finding's class rather than as a
query against an eventually-consistent search index.

**Acceptance Scenarios**:

1. **Given** the dedup requirements, **When** a maintainer reads the enumerated outcomes, **Then** a fourth outcome `unknown` exists, defined as "the lookup could not be completed" and explicitly distinguished from `none` ("the lookup completed and found no prior finding").
2. **Given** a dedup lookup that fails, **When** the watchdog decides what to do with the candidate finding, **Then** filing is suppressed and the failure is surfaced to a maintainer, rather than the finding being treated as new and filed.
3. **Given** the dedup lookup specification, **When** a maintainer inspects what it queries, **Then** it is a bounded, strongly-consistent enumeration within the finding's class rather than a full-text search index query, which requires filed findings to carry their class as a durable queryable attribute.

---

### Edge Cases

- **A real problem with weak evidence**: A run genuinely misbehaved but the artifact that would prove it is expired or truncated. The evidence-validity condition suppresses the finding; the run is recorded as un-inspectable rather than filed on thin evidence, consistent with the existing missing-evidence behavior.
- **An attributable signal that is still benign**: A run owned the artifact and executed, but the measured condition is expected (not a defect). Attribution is necessary but not sufficient; the precision obligation still requires the collector not to raise a signal for a non-problem.
- **A precision window that is not yet full**: Fewer than 10 distinct findings exist (including the zero-findings case, where there is no denominator at all). The criterion is reported as not-applicable rather than as a divide-by-zero failure or a pass; once 10 exist it is evaluated over the most recent 20 distinct findings, and over however many exist between 10 and 20.
- **A dedup lookup that fails on a genuine, previously-unseen finding**: The `unknown` outcome suppresses a finding that would have been correct to file. This is the accepted trade: a suppressed real finding costs one missed report and is surfaced as a lookup failure, whereas filing on failure costs an unbounded stream of duplicates. The failure must be visible so the underlying lookup can be repaired.
- **Fingerprint of a class with legitimately variable specifics**: A defect class whose only distinguishing evidence is itself variable must still yield a deterministic fingerprint by normalizing on the stable subset of its signals; if no stable subset exists, the class cannot be safely deduplicated and that must be surfaced, not hidden.
- **Retroactive scoring of the historical record**: Applying the new precision criterion to the ~200 existing runs requires each past finding to be labeled real or false. The absence of a labeled corpus (noted for SC-001) is itself a gap the precision criterion depends on.

## Requirements *(mandatory)*

The requirements below are expressed as changes to the watchdog's existing
specification (`specs/015-pipeline-watchdog/spec.md`) and to the project's
governing documents. Existing FR/SC identifiers refer to that spec.

### Precision as a first-class requirement

- **FR-001**: The watchdog's success criteria MUST include a precision criterion expressed with an explicit numerator (findings a maintainer confirms as genuine) and denominator (findings filed), computable from the filed-finding record, and MUST define its behavior when the window is not yet full (including a denominator of zero).
- **FR-002**: The false-positive-avoidance obligation currently expressed by FR-004 ("MUST NOT produce a finding when a run exhibits no detectable problem") MUST be restated as an obligation on the collectors that produce signals — the components able to observe the world — and MUST NOT rest solely on the `diagnose` step, which consumes pre-computed signals and cannot determine that a signal is wrong.
- **FR-003**: A signal that a collector cannot substantiate as describing a real condition MUST be suppressed at the collector before it becomes a candidate finding, rather than faithfully carried through to a filed finding.

### Attribution invariant

- **FR-004**: The requirements MUST state an attribution invariant: a collector MUST emit a signal about a run only when the inspected run both (a) executed, and (b) owned the artifact whose condition the signal describes.
- **FR-005**: The attribution invariant MUST apply to every collector, not to an individually-patched subset; a collector fed a run that did not execute, or that did not own the measured artifact, MUST emit no signal for that condition.

### Deterministic finding identity

- **FR-006**: The fingerprint requirement (FR-016) MUST require the fingerprint to be *deterministic* — a pure function of its stated inputs that yields an identical value on repeated computation — in addition to being stable across cosmetic run-to-run differences.
- **FR-007**: The fingerprint MUST be derived from the deterministic collector signals rather than from model-authored narrative text, so that two runs exhibiting the same defect produce identical fingerprints and the later finding deduplicates against the earlier one.

### Evidence validity

- **FR-008**: The evidence-citation requirement (FR-002 of spec 015) MUST impose a validity condition: the facts a finding cites MUST be non-empty and MUST conform to the expected shape for that finding's class.
- **FR-009**: A finding whose cited facts are absent, empty, or malformed MUST be suppressed rather than filed, even if it references a valid run.

### Self-inspection, amended

- **FR-010**: The self-inspection requirement (FR-021) MUST be amended to require that self-inspection be *unexempted* — never skipped or softened for the watchdog's own runs — rather than requiring the inspection *mechanism* to be *identical* to that used for other stages.
- **FR-011**: The amended self-inspection requirement MUST recognize a deterministic self-checker as a valid and stronger form of unexempted self-inspection, so that the shipped deterministic checker satisfies the requirement instead of contradicting it.

### Governance of deterministic judgment

- **FR-012**: The project's governing documents MUST record the principle that judgment which gates a durable action — filing a finding, computing a fingerprint, resolving a dedup outcome, or performing an autonomous write — belongs in deterministic code rather than in an agent's prompt.
- **FR-013**: The recorded principle MUST be citable by a reviewer as grounds to require that gating judgment introduced in a future change be moved out of an agent prompt and into deterministic code.

### Disposition of unexercised and unmeasured requirements

- **FR-014**: Triage rungs 1 (autonomous auto-fix) and 2 (open-a-PR) MUST be removed, and the watchdog MUST be restated as a pure reporter whose remediation ladder is detection, dedup, and issue-filing only. The requirements that exist solely to describe rungs 1–2 — the guardrail configuration, the diff-size limit, and the change-class allowlist — MUST be removed from the watchdog spec along with them, and no requirement may be left on the books describing a rung the watchdog no longer has.
- **FR-015**: The precision criterion (FR-001) MUST state its target as **≥70%**, measured over a window of the most recent 20 *distinct* (post-dedup) filed findings, and MUST NOT be evaluated until at least 10 distinct findings exist. The window MUST be counted by distinct finding rather than by run, so that a recurrence which deduplicates correctly neither inflates nor deflates the measurement.
- **FR-016**: SC-001's untestable "100% detection" claim and SC-007's never-measured latency MUST be addressed: SC-001 MUST be restated so it is verifiable (which depends on a labeled corpus of runs known to exhibit each problem class), and SC-007 MUST either be measured or explicitly deferred with the reason recorded.
- **FR-017**: The stale spec directory `specs/023-reliable-diagnose-verdict/`, which sits on `main` marked `"stage": "spec"` for abandoned work, MUST be removed entirely; git history is the record of the abandoned exploration, and `main` MUST NOT advertise an in-flight spec that is not in flight.

### Dedup lookup failure

- **FR-018**: The dedup requirements (FR-012–FR-016 of spec 015) MUST define a fourth lookup outcome, `unknown`, distinct from `none`: `unknown` means the lookup could not be completed, whereas `none` means the lookup completed and found no prior finding.
- **FR-019**: An `unknown` dedup outcome MUST suppress filing rather than falling through to the "file it as new" branch. `unknown` and `none` MUST NOT share a code path or a recovery behavior, and a lookup failure MUST be surfaced (not swallowed) so the suppressed finding is visible to a maintainer.
- **FR-020**: The dedup lookup MUST NOT depend on an eventually-consistent search index where a bounded, strongly-consistent direct read is available. Because findings are partitioned by a bounded finding class, the lookup MUST be expressible as a direct enumeration within that class, which requires filed findings to carry their class as a durable, queryable attribute.

### Scope boundaries

- **FR-021**: This feature MUST NOT change the watchdog's detection recall, its dedup-and-reopen behavior for genuinely distinct findings, its loop-prevention caps, or its coexistence with existing stalled/cleanup automation, except where a named gap above requires it.
- **FR-022**: The documentation corrections tracked separately as issue #139 (updates to `docs/architecture.md`, the collector fixture gate, and a triage runbook) are out of scope for this specification and MUST NOT be duplicated here.
- **FR-023**: The failure-injection test tier that would exercise a failing dedup lookup is tracked separately as issue #169 and is out of scope for this specification; this spec states the required `unknown` behavior, and #169 supplies the tier that can prove it.

### Key Entities *(include if feature involves data)*

- **Collector**: A component that observes a run's artifacts and emits deterministic signals. Under this feature it becomes the owner of false-positive suppression, the attribution invariant, and the deterministic basis for fingerprints.
- **Signal**: A deterministic, machine-produced observation about a run, attributable to that run, and the substance from which fingerprints and cited facts are derived.
- **Finding**: A candidate report about a run. Under this feature it is filed only when it is real (precision), attributable, deterministically fingerprinted, and backed by non-empty valid cited facts.
- **Precision criterion**: A measurable success criterion defined as confirmed-genuine findings over filed findings, targeted at ≥70% over the most recent 20 distinct (post-dedup) findings, evaluated only once at least 10 distinct findings exist and reported as not-applicable before then.
- **Dedup outcome**: The result of looking up a finding's fingerprint against previously filed findings — one of `none`, `match-open`, `match-closed`, or `unknown`. `unknown` means the lookup itself could not be completed and, unlike `none`, suppresses filing.
- **Deterministic-judgment principle**: The recorded governance rule that gating judgment lives in deterministic code, not agent prompts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The watchdog's success criteria include a precision criterion with an explicit numerator and denominator, and a maintainer can compute it against the filed-finding record without ambiguity.
- **SC-002**: Re-scoring the retrospective's five false positives (#102, #104, #105, #112, #125) against the strengthened requirements, each one is attributable to a specific gap now closed (unattributable signal, empty evidence, or absent precision bar), demonstrating the requirements would have suppressed it.
- **SC-003**: The attribution invariant is stated once and applies to 100% of collectors, replacing the two individual guards (PRs #135, #137) with a single stated rule that covers the remaining three collectors.
- **SC-004**: Inspecting the same run twice produces byte-identical fingerprints for every finding, and none of the nine historical duplicate issues (#106, #113, #115, #116, #122, #126, #129–131) could recur under the deterministic fingerprint requirement.
- **SC-005**: A finding whose cited facts are empty or malformed is suppressed in 100% of cases, eliminating the empty-fact `denied-tool` findings the prior requirement admitted.
- **SC-006**: The amended self-inspection requirement is satisfied by the shipped deterministic self-checker, resolving the standing contradiction between FR-021 and the code with no requirement left on the books that the code violates.
- **SC-007**: The deterministic-judgment principle is recorded in a governing document and is specific enough that a reviewer, given a future change that puts gating judgment in an agent prompt, can point to it as grounds to move the judgment into deterministic code.
- **SC-008**: Every named gap (1 through 6) and every "worth deciding" item (rungs 1–2, SC-001/SC-007 testability, the stale 023 directory) is resolved by either a concrete requirement change or an explicitly recorded decision — none is left drifting.
- **SC-009**: After the rungs-1–2 removal, the watchdog spec describes exactly one remediation outcome — file an issue — and no requirement, guardrail configuration, diff-size limit, or change-class allowlist remains on the books describing machinery the watchdog no longer has.
- **SC-010**: The dedup outcomes are enumerated as four, and a dedup lookup that cannot complete files nothing in 100% of cases while surfacing the failure, so a broken lookup produces zero duplicate issues rather than one per finding.

## Assumptions

- **The subject is the spec, not a rewrite of the watchdog**: The watchdog's detection engine, ladder, and dedup machinery exist and work for genuine, distinct findings; this feature corrects the requirements and governance that let false positives and duplicates through, and the collector/dedup behavior those corrected requirements demand.
- **"The code matches the spec" is the premise**: The five false positives were faithful reports of bad signals, so the fix is at the requirement and collector layer, not in the reasoning agent.
- **Collectors can observe the world; `diagnose` cannot**: Assigning false-positive suppression and attribution to collectors reflects that only they see the artifacts, while `diagnose` sees only pre-computed signals.
- **Deterministic gating is preferred to prompt gating**: Consistent with every fix in the cluster, gating judgment is assumed to belong in deterministic code; this is the principle being codified.
- **Humans still own merges and dispositions**: The rungs-1–2 decision, the precision target, and the 023 cleanup were maintainer decisions, surfaced as clarifications rather than presumed. All three were answered on issue #140: remove rungs 1–2 and make the watchdog a pure reporter; hold it to ≥70% precision over the most recent 20 distinct findings once 10 exist; and delete the stale 023 directory outright.
- **Removing rungs 1–2 loses nothing in practice**: Across ~200 runs every finding landed on rung 3, so the removed machinery has no demonstrated finding class behind it; an unexercised path is treated as a liability rather than as a reserve.
- **A missed report is cheaper than a duplicate stream**: The `unknown` dedup outcome suppresses filing on lookup failure, trading a possible missed finding for the guarantee that a broken lookup cannot spam issues.
- **Untrusted content rule is unchanged**: Inspected transcripts and artifacts remain data, never instructions, per the constitution's non-negotiable security principle.
