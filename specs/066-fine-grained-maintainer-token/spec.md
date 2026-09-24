# Feature Specification: Fine-grained maintainer token for the auto-release end-to-end harness

**Feature Branch**: `066-fine-grained-maintainer-token`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue [#506](https://github.com/charlesguse/wing-commander/issues/506) — "auto-release E2E: consider a fine-grained maintainer token owned by the machine account (instead of a classic token)". The issue carries no drafted body; it was routed from `board-loop.yml` (originating issue #388) as `under_threshold`, so the title is the whole request.

## Context

`auto-release.yml`'s `verify-e2e` job drives the four human gates of an
unattended end-to-end run (one clarification reply, three pull request
merges) as a dedicated machine **user** account, because the clarify entry
point's actor gate rejects bot identities outright
(specs/055-unattended-e2e-gates FR-003).

That account authenticates with a **classic** personal access token stored as
`WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`. The credential's own shape
therefore says nothing about what it can reach: a classic token carries
whatever access its account has. "Contained to the test repository alone"
(FR-011) rests on two things outside the token — the account's own repository
memberships, and a runtime containment check that lists every repository the
token can reach and requires the set to be exactly
`WING_COMMANDER_AUTO_RELEASE_E2E_REPO`.

The recorded reason for choosing that shape (specs/055 research.md D1,
`docs/setup.md` §2, and the comment above the credential step in
`auto-release.yml`) is a real GitHub constraint: a fine-grained personal
access token can only select repositories its own account **owns** (or, for an
organization-owned repository, ones an organization owner has pre-approved),
and the machine account is merely an invited **Write collaborator** on the
test repository.

This request asks for the shape that constraint does not rule out: make the
machine account the **owner** of the test repository, and issue a fine-grained
token scoped to that one repository with only the permissions the harness
actually uses. Containment then becomes a property of the credential itself,
verified rather than merely asserted, and the credential acquires a mandatory
expiry it does not have today.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The harness authenticates with a repository-scoped credential (Priority: P1)

The maintainer issues a credential for the fixture maintainer identity whose
own scope is the single end-to-end test repository and whose permissions are
exactly those the harness exercises (commenting on an issue, merging a pull
request), stores it in the existing secret, and an unattended end-to-end run
drives all four gates with it unchanged.

**Why this priority**: this is the whole request. Everything else in this
feature exists to keep the change safe and legible; without this the
credential's blast radius stays bounded only by account memberships.

**Independent Test**: issue the credential, set the secret (and, if ownership
moves, the test-repository variable and the App installation that follow it),
dispatch one auto-release verification attempt, and observe the credential
precheck passing and all four gates driven to a terminal verdict.

**Acceptance Scenarios**:

1. **Given** the secret holds a credential scoped to exactly the test
   repository with the harness's permissions, **When** a verification attempt
   runs, **Then** the credential precheck passes and the attempt proceeds to
   drive the gates as it does today.
2. **Given** that same credential, **When** the attempt reaches each of the
   four gates, **Then** the clarification reply and the three merges are
   attributed to the machine account's login, and no gate is stalled for want
   of permission.
3. **Given** the credential is scoped more broadly than the test repository,
   **When** the attempt runs, **Then** it ends with an infrastructure verdict
   naming the secret to reconfigure and drives no gate.

---

### User Story 2 - A wrong or expired credential is named before any spend (Priority: P1)

Every way the new credential shape can be misconfigured — expired, missing one
of the permissions the harness needs, scoped to the wrong repository, issued
by the wrong account, or unset — is detected before the attempt starts a
lifecycle it cannot finish, and is reported as a named infrastructure outcome
rather than as a stalled gate hours later.

**Why this priority**: a fine-grained credential adds a failure mode the
current one does not have (mandatory expiry) and turns "has write access" into
a per-permission question. The existing precheck's whole purpose is that a
misconfiguration costs nothing; that property must survive the change, or the
change trades a security improvement for a class of expensive silent stalls.

**Independent Test**: run the credential precheck against each
misconfiguration in turn (no network needed) and assert every one ends the
attempt with an infrastructure verdict that names what to fix and never quotes
the credential.

**Acceptance Scenarios**:

1. **Given** an expired credential, **When** the precheck runs, **Then** the
   attempt ends with an infrastructure verdict that says the credential was
   rejected and names the secret, distinguishably from "the account was never
   granted access" and from "the credential authenticates as a different
   account".
2. **Given** a credential that can read the test repository but lacks a
   permission a later gate needs, **When** the precheck runs, **Then** the
   attempt ends before the first gate rather than stalling at the gate that
   needed it.
3. **Given** a credential that is valid and correctly scoped but whose expiry
   falls within the configured warning window, **When** the attempt runs,
   **Then** it proceeds normally and its report states that the credential is
   approaching expiry.
4. **Given** any failing precheck branch, **When** its verdict is produced,
   **Then** the verdict text contains no part of the credential and no
   unredacted machine-account login.

---

### User Story 3 - The containment guarantee is still proved, not assumed (Priority: P2)

The runtime check that the credential reaches exactly the test repository
keeps discriminating under the new shape: it still fails an attempt whose
credential reaches a second repository, and it never passes because it
observed nothing at all.

**Why this priority**: the obvious simplification once the token is
self-scoping is to delete the containment check and trust the token's claimed
scope. Constitution Principle VIII ("a green check means what it says") is the
reason not to: a check that cannot fail its subject, or one that a permission
change silently turns into "reached 0 repositories, close enough", is worse
than no check because it reports confidence it no longer has.

**Independent Test**: exercise the containment check under the new credential
shape with a correctly scoped credential, an over-scoped one, and one that
cannot enumerate repositories at all, and assert the three outcomes differ.

**Acceptance Scenarios**:

1. **Given** a correctly scoped credential, **When** containment is checked,
   **Then** it passes.
2. **Given** a credential that reaches the test repository plus one other
   repository, **When** containment is checked, **Then** the attempt ends with
   an infrastructure verdict that names the extra repository (with the machine
   account's own login redacted) and drives no gate.
3. **Given** a credential whose permissions do not let it enumerate the
   account's repositories at all, **When** containment is checked, **Then** the
   attempt ends with an infrastructure verdict that says containment could not
   be established — never a pass, and never a message indistinguishable from
   "this credential reaches nothing".

---

### User Story 4 - One statement of the accepted credential shape (Priority: P2)

After the change, exactly one place in the repository states which credential
shapes are accepted and why; the setup documentation, the workflow comment
above the credential step, the precheck's own expectation text, and
specs/055's recorded decision agree with it, and a gate fails if a
contradicting statement reappears.

**Why this priority**: "a **classic** PAT, not fine-grained" is currently
asserted in at least four places (`docs/setup.md` §2, `auto-release.yml`'s
credential-step comment, specs/055-unattended-e2e-gates research.md D1/D2 and
its Clarifications session, and a gate scenario's expected text). A change
that flips the shape in three of them and leaves the fourth is exactly the
drift CLAUDE.md's "shared logic has exactly one home" rule exists to prevent,
and here the drifted copy would be a security claim.

**Independent Test**: after the change, sweep the repository for statements
about the credential's shape and assert every one either is the canonical
statement or points at it; assert the sweep fails when a contradicting
statement is reintroduced.

**Acceptance Scenarios**:

1. **Given** the change is complete, **When** the repository is swept for
   assertions about the credential's shape, **Then** every site agrees with the
   canonical statement, and each non-canonical site points at it.
2. **Given** a contradicting assertion is reintroduced anywhere, **When** the
   PR-time gate suite runs, **Then** it fails and names the site.
3. **Given** specs/055-unattended-e2e-gates recorded the superseded decision,
   **When** a reader reaches D1/D2 or its Clarifications session, **Then** the
   record is preserved as history and carries a pointer to this feature's
   decision rather than being rewritten or deleted.

---

### Edge Cases

- **Ownership implies Admin.** If the machine account owns the test
  repository, its permission there is necessarily Admin, which the current
  prerequisite explicitly avoids ("Write — never Admin", `docs/setup.md` §2).
  What must be true for that to be acceptable is an open question (Q3).
- **A credential scoped to "all repositories of this account".** Fine-grained
  tokens allow it; the containment check must still catch it, and the
  precheck's expectation text must describe per-repository selection rather
  than merely "fine-grained".
- **The repository-enumeration read under the new shape.** If the credential
  cannot list the account's repositories, today's check would compute an empty
  set and report "reached 0 repositories" — the same text an authentication
  failure produces. The two must be distinguishable (User Story 3).
- **Expiry during a long attempt.** A credential that is valid at the precheck
  and expires before the last merge must end the attempt with a named outcome,
  not an unexplained gate stall.
- **Rotation.** Replacing an expiring credential must not require a code
  change, and the repository must state the maximum lifetime the maintainer
  should choose.
- **Ownership move fallout.** Moving the test repository changes its
  `OWNER/NAME`, so the test-repository variable, the wing-commander App
  installation on it, its Claude credential secret, its container-image
  variable, and its `spec-request` label all follow. A partially moved fixture
  must produce a named infrastructure verdict, not a half-driven run.
- **The self-repository refusal.** Whatever the credential's shape, an attempt
  whose configured test repository resolves to this repository must still
  refuse before acting (specs/055 FR-013).
- **Adopters.** No adopter configures this secret. The change must leave the
  published stage contract and every adopter-facing default untouched.

## Requirements *(mandatory)*

### Functional Requirements

#### The credential

- **FR-001**: The fixture maintainer identity MUST remain a dedicated GitHub
  **user** account (never a bot identity), so the clarify entry point's actor
  gate is satisfied exactly as it stands today; this feature MUST NOT widen
  that gate or any other actor, merge, or human gate.
- **FR-002**: The repository MUST accept, for that account, a credential whose
  own scope is the end-to-end test repository alone and whose granted
  permissions are no broader than the acts the harness performs (comment on an
  issue, merge a pull request, and read what the precheck reads). A
  self-scoping credential is only issuable if the account owns the fixture:
  [NEEDS CLARIFICATION: does the end-to-end test repository move under the
  machine account's own ownership (making a single-repository fine-grained
  token issuable, at the cost of Admin there), move under an organization that
  pre-approves fine-grained access, or stay where it is (in which case the
  classic shape stands and this feature records the refusal — FR-020)?]
- **FR-003**: The set of credential shapes the verification job accepts MUST
  be stated explicitly and enforced by the precheck. Whether the classic shape
  remains accepted alongside the repository-scoped one is
  [NEEDS CLARIFICATION: is the classic PAT still an accepted shape after this
  change (dual acceptance, so a credential can be rotated without a code
  change), or is the repository-scoped fine-grained token the only accepted
  shape from the moment this ships?]
- **FR-004**: The credential MUST continue to be read only by
  `auto-release.yml`'s verification job, and MUST NOT be granted any access to
  this repository.
- **FR-005**: Issuing, scoping, and rotating the credential MUST remain a
  maintainer act performed outside the pipeline, stated as a prerequisite. No
  workflow in this repository may create, elevate, or rotate it.
- **FR-006**: The repository MUST state the maximum credential lifetime a
  maintainer should choose and the rotation act, such that rotation requires
  setting a secret and nothing else.

#### Prechecks before any spend

- **FR-007**: Before the attempt drives any gate or starts any lifecycle, the
  verification job MUST confirm: the credential secret and the login secret are
  set; the credential authenticates; it authenticates as the login the login
  secret names (compared case-insensitively, whitespace-stripped, as today); it
  carries at least the access each of the four gate-driving acts needs; and it
  is contained to the test repository alone.
- **FR-008**: Each distinct failure above MUST end the attempt with a
  `fail-infra` verdict that names the secret or prerequisite to fix and the
  observed condition, and MUST NOT crash the job or leave a lifecycle running.
  Distinct causes MUST produce distinguishable verdicts — in particular
  "rejected/expired credential", "authenticated as a different account",
  "insufficient permission on the test repository", and "containment could not
  be established" MUST not collapse into one message.
- **FR-009**: No verdict, step output, log line, or job summary produced by
  these checks may contain the credential, and none may contain the machine
  account's login unredacted — a masked value in a step output is dropped
  wholesale by GitHub, which would replace the very verdict that was meant to
  name the problem.
- **FR-010**: When the credential's expiry is observable, an attempt whose
  credential expires within a configured warning window MUST proceed and MUST
  state the approaching expiry in its report; an already-expired credential
  MUST end the attempt under FR-008.
- **FR-011**: A gate-driving act that fails at runtime because the credential
  was insufficient or expired MUST end the attempt with a named outcome that
  identifies the credential as the cause, rather than an undifferentiated gate
  stall.

#### Containment

- **FR-012**: The credential MUST be contained to the end-to-end test
  repository alone, and containment MUST continue to be **verified at runtime**
  against the credential's own reachable-repository set rather than inferred
  from its claimed type or scope.
- **FR-013**: The containment check MUST distinguish "reaches exactly the test
  repository" from "reaches more than the test repository" from "could not
  determine what it reaches", and MUST fail the attempt in the latter two
  cases. It MUST NOT be possible for the check to pass because it observed
  nothing.
- **FR-014**: A containment failure MUST name the repositories reached, with
  the machine account's own login replaced by a placeholder, and MUST never
  name the credential.
- **FR-015**: The containment invariant and every FR-008 branch MUST be
  covered by a gate that runs the real precheck and that demonstrates it can
  fail — a mutation of the precheck must break at least one of the gate's
  assertions.
- **FR-016**: If the accepted shape requires the machine account to own the
  test repository, the repository MUST state what the resulting Admin
  permission there is allowed to be used for and what it must not, and the
  containment requirement MUST be restated in terms of the account's whole
  repository set, not of its permission level on one repository.
  [NEEDS CLARIFICATION: is Admin on the fixture (unavoidable under ownership)
  acceptable as a restatement of today's "Write — never Admin" prerequisite, or
  must the precheck additionally assert a bound — that the credential grants no
  Administration permission, and that the account owns no other repository?]

#### Single home and record

- **FR-017**: Exactly one location MUST carry the canonical statement of the
  accepted credential shape, its scope, its permissions, its lifetime, and how
  containment is enforced. Every other mention — the workflow comment, the
  precheck's expectation text, the setup documentation row, this and prior
  specs — MUST agree with it and point at it rather than restating it.
- **FR-018**: A gate MUST fail when a statement contradicting the canonical
  one reappears anywhere in the repository, so the corrected claim cannot
  silently drift back.
- **FR-019**: The superseded decision in specs/055-unattended-e2e-gates
  (research.md D1/D2 and its Clarifications session) MUST be preserved as
  history and annotated with a pointer to this feature's decision; it MUST NOT
  be rewritten to read as though the new shape had always been chosen.
- **FR-020**: If the decision is that the credential shape does **not**
  change, the canonical statement MUST record the machine-account-ownership
  option and why it was refused, so the same question does not need
  re-deriving; FR-007 through FR-015 still apply to the credential as it
  stands.

#### Boundaries

- **FR-021**: This feature MUST NOT change which gates the unattended run
  drives, the verdict schema, the release decision, or any published stage
  workflow's behaviour for adopters.
- **FR-022**: Any migration MUST be provable: after the change, one unattended
  end-to-end run under the new credential MUST reach a terminal verdict, and
  its evidence MUST be recorded on the pull request or the lifecycle issue.

### Key Entities

- **Fixture maintainer identity**: the dedicated GitHub user account the
  harness acts as. Attributes: login (held in a masked secret), relationship to
  the test repository (owner or invited collaborator), the complete set of
  repositories it can reach.
- **Maintainer credential**: the secret the harness authenticates with.
  Attributes: shape (classic / repository-scoped fine-grained), repository
  selection, granted permissions, expiry.
- **End-to-end test repository**: the disposable onboarded fixture the run
  resets and drives. Attributes: `OWNER/NAME`, its wing-commander App
  installation, its own secrets and variables, absence of branch protection.
- **Credential precheck outcome**: for one attempt — pass, or a `fail-infra`
  verdict naming the secret or prerequisite and the observed condition, plus an
  optional approaching-expiry note.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The credential the harness authenticates with reaches exactly
  one repository — the end-to-end test repository — and this is confirmed at
  runtime on every attempt, before any gate is driven.
- **SC-002**: Every misconfiguration listed in the Edge Cases ends the attempt
  with a named infrastructure verdict and zero gate-driving agent cost; none
  produces a crashed job, a stalled gate, or a verdict that fails to parse.
- **SC-003**: Rotating the credential requires only setting a secret: a
  maintainer completes it using the repository's own setup documentation, with
  no change to any workflow, script, or gate.
- **SC-004**: Exactly one location states the accepted credential shape, and a
  repository-wide sweep finds zero statements that contradict it. Reintroducing
  a contradicting statement fails the PR-time gate suite.
- **SC-005**: The containment check is demonstrably able to fail: mutating the
  precheck so that an over-scoped or unverifiable credential would pass makes
  at least one gate assertion fail.
- **SC-006**: One unattended end-to-end run completes under the credential
  shape this feature settles on, with all four gates driven and the evidence
  recorded.
- **SC-007**: No adopter-facing behaviour changes: the published stage
  workflows and their documented configuration surface are identical before and
  after, apart from the setup row describing this repository-only secret.

## Assumptions

- The request is scoped to `auto-release.yml`'s end-to-end maintainer
  credential only. The wing-commander App credentials, the Claude credentials,
  the container-registry secrets, and the `auto-update-spec-kit` scratch
  repository's wiring are out of scope.
- The GitHub constraint recorded in specs/055 research.md D1 still holds: a
  fine-grained personal access token can select only repositories its own
  account owns, or organization-owned repositories an organization owner has
  pre-approved. Making the credential self-scoping therefore requires changing
  **who owns the test repository**, not just which token type is issued — which
  is why Q1 below is a scope question rather than a detail.
- The permissions the harness needs on the test repository are those the four
  gate-driving acts require (issue comment write, pull request merge, and the
  reads the precheck performs); no Administration permission is needed for the
  acts themselves, since the fixture carries no branch protection
  (specs/053-e2e-scratch-provisioning).
- Default expiry handling, unless the owner says otherwise: choose the
  shortest lifetime that does not force rotation more often than the release
  cadence, treat an expired credential as `fail-infra`, and state an
  approaching expiry in the attempt's report when it is observable.
- The existing runtime containment check is kept rather than deleted, even
  though a correctly scoped credential makes it redundant on paper — it is what
  turns the scoping claim into an observation (Constitution Principle VIII).
- `WING_COMMANDER_AUTO_RELEASE_PAUSED` stays set and its documented resume
  condition (specs/055 FR-028/FR-029) is unchanged by this feature; this
  feature's own proving run is a dispatch, not a resume.
- This repository is public, so the canonical statement names secret and
  variable names and permission levels only — never an account login, an
  organization, or a repository that is not already public.

## Out of Scope

- Changing which human gates the unattended run drives, or how it drives them.
- Automating account provisioning, repository transfer, or credential
  rotation from inside the pipeline.
- Any change to the `verify-e2e` verdict schema or to the release decision.
- Adopter-facing configuration: no adopter sets this secret, and none gains a
  new one.

## Clarifications

### Session 2026-09-24 — open questions (not yet answered)

**Q1 — Which ownership shape does the test repository take?** (FR-002,
FR-003, FR-016, Assumptions)

A fine-grained token can only be scoped to a repository its own account owns,
so this is the decision that determines whether the request is buildable at
all: keep the fixture where it is and the credential stays classic; move it
under the machine account and the credential becomes self-scoping but the
account necessarily holds Admin there; move it under an organization and
scoping works via owner pre-approval at the cost of an organization to
administer.

**Q2 — Does the classic shape remain accepted?** (FR-003, FR-006, FR-017)

Dual acceptance keeps rotation a secret-only act and makes the migration
reversible without a code change, but leaves the weaker shape available
indefinitely; single acceptance makes the guarantee unconditional but turns
any fallback into a code change under time pressure.

**Q3 — Is the Admin permission that ownership confers acceptable, and what
must bound it?** (FR-016, FR-012, specs/055 FR-011)

Today's prerequisite is deliberately "Write — never Admin". An account that
owns the fixture has Admin on it by construction, so either the "never Admin"
rule is restated as "Admin on the fixture only, never elsewhere", or the
containment check must additionally assert something about what the credential
may not do (for instance, that it grants no Administration permission and that
the account owns no other repository).
