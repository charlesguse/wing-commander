# Feature Specification: Genuinely Empty `spec-dir` For Non-Qualifying PRs

**Feature Branch**: `102-nonqualifying-spec-dir-empty`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "`classify-and-announce`'s identity step (`.github/workflows/pr-conversation.yml`) always runs `echo \"spec-dir=specs/$slug\"`, even on the non-qualifying branch where `slug=\"\"`. That produces the literal string `specs/`, which is non-empty, so nothing that treats an empty `spec-dir` as \"this PR does not qualify\" can actually rely on it. The `stalled` job's own independent identity step further down the same file already gets this right — it initializes `spec_dir=\"\"` and only sets it inside the branch where a slug was actually resolved. This PR applies the same guard to `classify-and-announce`'s identity step so both stay consistent and `spec-dir` is truly empty whenever `qualifies=false`. No behavior change for existing consumers: every current use of `steps.identity.outputs.spec-dir` inside `classify-and-announce` is already gated on `steps.identity.outputs.qualifies == 'true'`, not on `spec-dir`'s emptiness, so this only tightens an output that was already documented (and, per the linked issue, assumed elsewhere) to be empty on the non-qualifying path. Closes #633." (routed from the board loop, issue #633, reason `contract_widening`)

## Overview

The pipeline has one written convention for spec identity outputs: an empty
`spec-dir` means *no spec record was resolved*. It is stated in
`specs/041-implement-stall-notice/contracts/wing-commander-chain-stop-notice.md`
("Empty means 'no record to mark'… always empty for any stage where
independent identity re-derivation itself failed") and honoured by three
identity steps that can legitimately resolve nothing — `clarify.yml`'s
"Resolve spec identity independently", `pr-conversation.yml`'s `stalled`
job, and the `wing-commander-inspected-run-identity` composite.

The `classify-and-announce` job of `pr-conversation.yml` is the one identity
step that can legitimately resolve no slug and does *not* honour it. It
emits `spec-dir=specs/` — a non-empty string that reads as a real path — on
every PR the stage declines to act on. The emptiness signal is therefore
unusable as a "does this PR qualify?" test anywhere downstream of that job,
and a consumer that trusts the stated convention gets a wrong answer with no
error.

Nothing is broken today: every present consumer of that output happens to
gate on the sibling `qualifies` output instead. This feature makes the
convention true where it is currently false, and — because a convention with
nothing enforcing it survives only until the next edit (Constitution
Principle VIII) — puts a gate behind it so the next hand-written identity
step cannot reintroduce the same hole.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A non-qualifying PR reports no spec directory (Priority: P1)

A maintainer (or a future step) inspects what the `pr-conversation` stage
resolved for a pull request the stage does not act on — a PR onto a
non-default base, a `plan/` or `tasks/` head, a head whose suffix is not a
well-formed `NNN-slug`. The identity the stage publishes for that PR names
no spec directory at all, matching what the stage actually decided.

**Why this priority**: This is the defect. Until the published identity is
empty, the documented signal is false and any consumer written against it is
silently wrong. Every other story in this spec exists to keep this one true.

**Independent Test**: Drive the stage against a PR that does not qualify and
read the job's published identity: `spec-dir` is the empty string, not
`specs/`. Drive it against a qualifying PR and confirm `spec-dir` still names
the real directory.

**Acceptance Scenarios**:

1. **Given** a pull request whose base is not the default branch, **When**
   the `pr-conversation` stage resolves its identity, **Then** the published
   `spec-dir` is empty and `qualifies` is `false`.
2. **Given** a pull request whose head carries the spec-branch prefix but
   whose remainder is not a well-formed `NNN-slug`, **When** the stage
   resolves its identity, **Then** the published `spec-dir` is empty and
   `qualifies` is `false`.
3. **Given** a pull request whose head is a plan, tasks, or draft-spec
   branch, **When** the stage resolves its identity, **Then** the published
   `spec-dir` is empty and `qualifies` is `false`.
4. **Given** a pull request the stage does act on, **When** the stage
   resolves its identity, **Then** the published `spec-dir` is
   `specs/<NNN-slug>` exactly as it is today and every downstream job,
   concurrency group, metrics record, and reply is unchanged.
5. **Given** an identity resolution that refuses outright because a required
   reference could not be read from the API, **Then** the run still fails
   loudly as it does today — an empty `spec-dir` is never substituted for a
   failed lookup.

---

### User Story 2 - The convention cannot silently regress (Priority: P2)

A contributor adds or edits an identity step that may resolve no spec slug.
If that step can publish a non-empty `spec-dir` while resolving nothing, the
PR-time gate suite fails and names the step and the file, before the change
reaches `main`.

**Why this priority**: The defect being fixed is a one-line divergence
between four hand-written copies of the same idiom. Fixing the fourth copy
without a check simply resets the clock. It is P2 rather than P1 because the
correctness win of Story 1 stands on its own.

**Independent Test**: Run the gate suite against a fixture in which an
identity step emits a spec directory unconditionally on a path where the slug
may be empty; the gate fails and names it. Run it against the corrected tree;
the gate passes.

**Acceptance Scenarios**:

1. **Given** a workflow or composite identity step that can leave its slug
   empty, **When** that step publishes a spec directory outside the branch
   where a slug was resolved, **Then** the gate fails with a message naming
   the file, the step, and the rule.
2. **Given** the repository after this feature lands, **When** the gate suite
   runs, **Then** the new gate passes.
3. **Given** the new gate, **When** it is run locally through the repository's
   local gate runner, **Then** it runs the same subject with the same
   arguments it runs in CI, and it is reachable through the gate registry.
4. **Given** a checked-in failing fixture for the gate, **When** the gate
   suite runs, **Then** that failure branch is exercised rather than merely
   demonstrated by hand.

---

### User Story 3 - The convention has one written home (Priority: P3)

Someone writing the next identity step can find, in one place, the statement
that an unresolved spec identity publishes an empty `spec-dir`, and the gate
that enforces it points at that statement.

**Why this priority**: Documentation value only — the behaviour is already
correct once Stories 1 and 2 land. It is worth doing in the same change
because the rule is currently implied by one composite's input table and
re-derived by comment in three workflows.

**Independent Test**: Read the canonical statement, then read each identity
step that can resolve nothing and confirm each points at it rather than
restating it.

**Acceptance Scenarios**:

1. **Given** the identity steps that can resolve no slug, **When** a reader
   opens any one of them, **Then** it either carries the canonical statement
   or a one-line pointer to it, and no two carry divergent restatements of
   the rule.

---

### Edge Cases

- **A PR that qualifies but whose lifecycle issue is closed, or whose actor
  is unauthorized**: identity resolution succeeded, so `spec-dir` is
  populated; emptiness is a statement about identity, never about
  authorization or about whether the stage chose to act.
- **The identity step refuses (a required reference could not be read)**: the
  step already fails the job and publishes a refusal reason. It must keep
  failing; an empty `spec-dir` must never become the way an API failure is
  reported, because that is exactly the "silently drop the request"
  behaviour the existing refusal guard was written to prevent.
- **Derived values built by string concatenation from `spec-dir`**: the
  stage composes a per-spec concurrency group from the spec directory. On
  the non-qualifying path that composition is not reached today, but with a
  genuinely empty `spec-dir` any such composition would degrade to a bare
  prefix rather than a plausible-looking `specs/` path. Every consumer that
  concatenates must therefore remain gated on `qualifies`, not on the
  emptiness of `spec-dir`.
- **A slug that is the empty string only because the head ref equals the
  prefix exactly** (e.g. head ref is exactly the spec prefix): treated as
  not qualifying, `spec-dir` empty.
- **Identity steps in stages that hard-fail on an unresolvable slug**
  (cleanup, plan, tasks): these have no empty-slug path at all, so the rule
  is vacuously satisfied and they are not the subject of this change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `pr-conversation` stage's entry identity resolution MUST
  publish an empty spec directory whenever it resolves no spec slug.
- **FR-002**: That identity resolution MUST publish `specs/<slug>`
  unchanged whenever it does resolve a slug, so that every existing consumer
  of the qualifying path — concurrency group, agent prompt context, metrics
  record, chain-stop notice, replies — behaves exactly as it does today.
- **FR-003**: The stage MUST continue to distinguish "this PR does not
  qualify" (publish empty identity, stop with no reply) from "a required
  reference could not be resolved" (fail loudly with a refusal reason); this
  change MUST NOT collapse the second case into the first.
- **FR-004**: `qualifies` MUST remain the authoritative gate every in-stage
  consumer of the identity is conditioned on. An empty `spec-dir` is a
  corroborating invariant, not a replacement signal.
  [NEEDS CLARIFICATION: should any existing consumer be migrated to test
  `spec-dir`'s emptiness instead of `qualifies`, or does `qualifies` stay
  the sole gate with emptiness as a defensive invariant only?]
- **FR-005**: A deterministic PR-time gate MUST fail when an identity step
  that can leave its spec slug empty publishes a spec directory outside the
  branch in which a slug was resolved.
- **FR-006**: That gate MUST be registered in the repository's gate registry,
  MUST run under the local gate runner with the same subject and arguments it
  uses in CI, and MUST be triggered by changes to the workflows and composite
  actions it checks.
- **FR-007**: Every failure branch the gate ships MUST be exercised by a
  checked-in fixture, not by a one-off demonstration.
- **FR-008**: The gate MUST fail loudly rather than report a pass when it
  cannot reach its subject — an empty file list, a missing path, or a
  workflow it could not parse.
- **FR-009**: The set of identity steps in scope MUST be stated explicitly in
  the change, so a reader can tell at a glance whether a given step is
  governed by the rule or exempt because it hard-fails on an unresolvable
  slug.
  [NEEDS CLARIFICATION: is the scope only `pr-conversation`'s
  `classify-and-announce` step (the single outlier), or every identity step
  across workflows and composites that can legitimately resolve no slug —
  which would also rewrite three steps that are already correct into one
  shared idiom?]
- **FR-010**: The rule that an unresolved spec identity publishes an empty
  spec directory MUST have exactly one canonical written statement, with
  every other site pointing at it rather than restating it.
- **FR-011**: The change MUST NOT alter any `workflow_call` input, output, or
  secret of any stage workflow, and MUST NOT add a new one.

### Key Entities

- **Spec identity**: the pair (`slug`, `spec-dir`) a stage derives for the
  pull request or issue it was handed, plus the `qualifies` verdict that says
  whether the stage acts at all. `spec-dir` is a job-level output within
  `pr-conversation.yml`, deliberately not re-exported to callers.
- **Non-qualifying pull request**: a PR whose base is not the default branch,
  or whose head is not a well-formed spec branch — the stage stops with no
  reply.
- **Identity gate**: the deterministic PR-time check that the empty-identity
  convention holds across the identity steps in scope.

## Success Criteria *(mandatory)*

- **SC-001**: For 100% of non-qualifying pull requests, the identity the
  `pr-conversation` stage publishes names no spec directory.
- **SC-002**: For 100% of qualifying pull requests, the published spec
  directory is byte-identical to what the stage publishes today, and no
  downstream behaviour observable to a requester changes.
- **SC-003**: An intentionally reintroduced instance of the defect is caught
  by the gate suite before merge, in 100% of runs, and the failure message
  names the offending file and step without the reader opening the gate's
  source.
- **SC-004**: A reader looking for the empty-identity rule finds exactly one
  statement of it; the count of divergent restatements across identity steps
  is zero.
- **SC-005**: A failed identity lookup continues to stop the run with a
  visible refusal in 100% of cases — zero occurrences of an API failure being
  reported as a non-qualifying PR.
- **SC-006**: The gate adds no new required manual step to the release or
  review process; it runs inside the existing PR-time gate suite.

## Assumptions

- This output is not part of the adopter-pinned published contract: the
  stage's interface documentation states that `qualifies`/`spec-dir`/`slug`
  exist as job-level outputs for the stage's own jobs and are deliberately
  not re-exported as `workflow_call` outputs. The change is therefore
  invisible to pinned adopters and is not a breaking-change event under
  Principle VII, despite the routing note's `contract_widening` label.
- Every current in-stage consumer of the identity already gates on
  `qualifies`, so Story 1 is behaviour-preserving for qualifying PRs and
  reaches no consumer on non-qualifying ones.
- The idiom involved is two lines of shell, repeated in four places. A shared
  composite action for it would cost more indirection than it saves, so
  "single home" is satisfied here by one canonical written statement plus a
  gate, rather than by extracting a composite. The clarification on FR-009
  may revisit this if the scope widens.
- Stages that hard-fail when they cannot resolve a slug (cleanup, plan,
  tasks) are out of scope: they have no empty-slug path for the rule to
  govern.
- The gate is expected to inspect workflow and composite sources statically;
  it is not expected to execute a stage.
- This behaviour only runs in Actions, so the fix is proven after merge by
  re-driving one run against a non-qualifying pull request and recording the
  evidence, per the repository's board-loop rule.
