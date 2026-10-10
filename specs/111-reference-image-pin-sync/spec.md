# Feature Specification: Reference-Image Pin Sync on Rebuild

**Feature Branch**: `111-reference-image-pin-sync`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Sync the reference-image pin to every repository that uses it when the image is rebuilt (#985). `WING_COMMANDER_CONTAINER_IMAGE` holds the reference image's digest pin in two places: this repository and the end-to-end test repository (`WING_COMMANDER_AUTO_RELEASE_E2E_REPO`). Each rebuild requires both copies to be updated by hand; `docs/setup.md` says the image workflow never writes the variable itself. On 2026-10-09 #973 rebuilt the image, this repository's pin was updated, the test repository's was not, and auto-release ended `fail-infra` with the pin-drift outcome (#979) until the owner re-pinned by hand. Cloud sessions cannot do the step because their proxy blocks the variables endpoints. Proposal: after `wing-commander-e2e-reference-image.yml` builds a new image and it passes its prerequisite check, the workflow writes the new digest to the test repository's variable, and to this repository's unless the owner keeps that as a human step. specs/067's drift check stays as the safety net; auto-release still only reads the variable (067 FR-003 unchanged). Owner decisions: write credential, this repository's own pin, failure handling."

## Clarifications

### Session 2026-10-10

- Q: Which write credential does the sync use? → A: A dedicated token
  granted Variables (write) on only the synced repositories (option B). It
  has the narrowest reach, and a containment check in the manner of
  specs/066-fine-grained-maintainer-token can require that it reaches
  exactly the sync set and nothing more; rotating one more secret is an
  accepted cost.
- Q: Is this repository's own pin written automatically too, or kept as a
  human step? → A: Written automatically (option A): both pins are written
  on every successful rebuild. Removing the manual copy is the point of
  this feature. The image's prerequisite check and the agent start-up
  check from #974 (spec 112) must both pass before any pin is written, so
  a bad image stops at the build.
- Q: How is a failed or partial sync surfaced? → A: Both (option C), with
  dedup: the build run fails, and one tracked issue is filed or updated
  naming each repository left unsynced, the value it holds and the value
  it should hold. Repeated failures update that one issue rather than
  filing duplicates, following auto-release's single
  `auto-release:failed` issue (#977) and the watchdog verifier's
  per-fingerprint filing (#976).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A rebuild keeps both pins current (Priority: P1)

A maintainer changes the reference image's definition (or its required-tools
list), the change merges, and the reference image is rebuilt. Without anyone
touching repository configuration by hand, both this repository's and the
end-to-end test repository's container image settings now name the new
image by the same digest. The next
container-mode auto-release run finds the two pins equal and goes on to
exercise the stage chain inside the new image.

**Why this priority**: This is the failure that cost a day of
container-mode coverage on 2026-10-09. Closing it removes the manual step
nobody, including cloud sessions, could reliably perform.

**Independent Test**: Rebuild the image (merge a change to its definition or
dispatch the build), then read both repositories' container image
settings and compare them with the digest the build published. Both are
equal to it, and the next container-mode auto-release run passes the
pin-match check.

**Acceptance Scenarios**:

1. **Given** a rebuild produces a new digest and the new image passes its
   prerequisite check and the agent start-up check, **When** the build run
   finishes, **Then** both this repository's and the test repository's
   container image settings hold the new image pinned by that digest, and
   the build run's summary states which repositories it updated and the
   value it wrote.
2. **Given** a rebuild produces an image that fails its prerequisite check
   or the agent start-up check, **When** the build run finishes, **Then**
   no repository's container image setting is changed and the summary says
   why the sync was skipped.
3. **Given** a rebuild produces the same digest already pinned everywhere,
   **When** the build run finishes, **Then** nothing is rewritten and the
   summary reports the pins as already current.

---

### User Story 2 - A failed sync never leaves the pins silently apart (Priority: P1)

A rebuild succeeds but writing one of the pins fails (credential missing,
expired, lacking permission, reaching the wrong repositories, or the write
itself refused). The maintainer learns about it from the build itself,
not a day later from a `fail-infra` auto-release verdict.

**Why this priority**: The sync is only an improvement if its failure is
loud. A silent failure recreates the original incident with extra
confidence that it cannot happen.

**Independent Test**: Run the build with the sync credential removed or
under-permissioned and confirm the build run fails and one tracked issue is
filed or updated (FR-007), naming the repository whose pin was not written
and the digest it should hold; repeat the failure and confirm the same
issue is updated rather than a second one filed.

**Acceptance Scenarios**:

1. **Given** the sync credential is unset or cannot authenticate, **When**
   the build reaches the sync, **Then** no pin is written, the build run
   fails, and the tracked sync-failure issue names the credential (never
   its value) and the repositories left unsynced.
2. **Given** one pin is written and the other write fails, **When** the
   build finishes, **Then** the build run fails and the tracked
   sync-failure issue names the repository left behind, the value it still
   holds, and the value it should hold.
3. **Given** an open tracked sync-failure issue from an earlier failed
   build, **When** a later build's sync also fails, **Then** that same
   issue is updated with the later failure and no second issue is filed.
4. **Given** a sync failed and nobody acted on it, **When** the next
   container-mode auto-release run starts, **Then** it still ends with the
   existing named pin-drift `fail-infra` outcome of
   specs/067-e2e-container-image-evidence, unchanged.

---

### User Story 3 - The sync credential reaches exactly what it syncs (Priority: P2)

The owner grants the sync the ability to write the container image setting
on the repositories it keeps in step, and nothing else. Before writing,
the build confirms the credential's reach and refuses to write if it can
change anything beyond that set.

**Why this priority**: Adding a write path to repository configuration
widens what automation can change. Containment keeps that widening to the
single variable on the named repositories, the same way
specs/066-fine-grained-maintainer-token's containment check confines the
maintainer token.

**Independent Test**: Configure a credential that also reaches an extra
repository and confirm the build refuses to sync and reports the
containment failure; configure a correctly scoped one and confirm it syncs.

**Acceptance Scenarios**:

1. **Given** a sync credential whose reach is exactly the repositories in
   the sync set, **When** the build syncs, **Then** the writes succeed.
2. **Given** a sync credential that reaches any repository outside the sync
   set, **When** the build reaches the sync, **Then** it writes nothing and
   reports a containment failure as a sync failure under FR-007.
3. **Given** a sync credential that lacks Variables (write) on either
   repository in the sync set, **When** the build reaches the sync,
   **Then** it writes nothing and reports a sync failure under FR-007.

---

### Edge Cases

- The build is dispatched by hand with no change to the image definition:
  the digest may be unchanged, in which case the sync is a no-op that still
  reports the pins as checked.
- Two builds run close together: the pin left in place must be the digest of
  the image the most recently started successful build published, never an
  older one overwriting a newer one.
- `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` is unset on this repository: there
  is no test repository to sync; the build still writes this repository's
  pin, reports that the test-repository sync was skipped for that reason,
  and does not fail on it.
- Someone sets a pin by hand to a different value after a sync: the sync
  does not reconcile it until the next rebuild; the existing drift check
  surfaces it in the meantime.
- The image registry digest output is empty or malformed: nothing is
  written, and this is reported as a sync failure.
- An auto-release run is in flight while the sync writes: that run read the
  pins at its start; the sync does not interrupt or alter it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After the reference-image build publishes a new image, and
  only after that image passes both the same prerequisite check the stages
  apply to a configured container image (the check Gate 62 enforces at PR
  time for the image definition) and the agent start-up check from #974
  (spec 112), the build MUST write the published image, pinned by digest
  and never by a moving tag, to the end-to-end test repository's
  `WING_COMMANDER_CONTAINER_IMAGE` setting. If either check fails, no pin
  is written.
- **FR-002**: This repository's own `WING_COMMANDER_CONTAINER_IMAGE` pin MUST
  be written automatically by the same build, under the same conditions as
  FR-001 and to the same value, on every successful rebuild; it is no
  longer a manual step.
- **FR-003**: The sync MUST NOT write any variable other than
  `WING_COMMANDER_CONTAINER_IMAGE`, and MUST NOT write it on any repository
  outside the sync set (this repository and the end-to-end test
  repository).
- **FR-004**: The sync MUST use a dedicated token, held as its own secret
  and used for nothing else, granted Variables (write) on exactly the
  repositories in the sync set and nothing else.
- **FR-005**: Before writing, the sync MUST verify the credential's reach at
  run time, in the manner of specs/066-fine-grained-maintainer-token's
  containment check, and MUST write nothing if the credential can reach any
  repository outside the sync set or lacks the write permission on any
  repository inside it.
- **FR-006**: The sync MUST skip writing a pin that already holds the
  published value, and MUST report it as already current.
- **FR-007**: A build whose sync fails, wholly or partly, MUST NOT leave the
  pins silently apart; the failure MUST both fail the build run and file
  or update one tracked sync-failure issue, naming each repository left
  unsynced, the value it holds, and the value it should hold, and never
  printing a credential value. The issue MUST be deduplicated: while one is
  open, a repeated failure updates it rather than filing another (as
  auto-release keeps one `auto-release:failed` issue, #977, and the
  watchdog verifier files per fingerprint, #976).
- **FR-008**: The build's run summary MUST state, for each repository in the
  sync set, whether its pin was written, already current, skipped (and
  why), or failed (and why).
- **FR-009**: auto-release's behaviour MUST be unchanged: it MUST continue to
  only read the container image settings (specs/067-e2e-container-image-evidence
  FR-003), and its named pin-drift `fail-infra` outcome MUST remain the
  safety net for a failed sync or a value set by hand.
- **FR-010**: When concurrent builds race, the pin left in place MUST be the
  digest from the most recently started successful build, never an older
  build's digest overwriting a newer one.
- **FR-011**: The live documentation that currently describes copying the
  digest as a manual step after each rebuild (the `WING_COMMANDER_CONTAINER_IMAGE`
  row of `docs/setup.md`, and the build workflow's own header comment) MUST
  be updated to describe the sync, the credential it needs, and what a
  maintainer does when it fails.
- **FR-012**: Adopters MUST see no change: the sync is wing-commander's own
  maintenance tooling, not a published stage, and adds no adopter-facing
  configuration.

### Key Entities

- **Reference-image pin**: The `WING_COMMANDER_CONTAINER_IMAGE` setting on a
  repository, holding the reference image's registry path pinned by digest.
  Exists on this repository and on the end-to-end test repository.
- **Sync set**: The repositories whose pin the build writes: this
  repository and the end-to-end test repository.
- **Sync credential**: A dedicated token that writes the pins, confined to
  the sync set and to Variables (write).
- **Sync-failure issue**: The single tracked issue a failed sync files or
  updates, naming each unsynced repository with its held and expected
  values.
- **Sync outcome**: Per repository: written, already current, skipped (with
  reason), or failed (with reason, held value, and expected value).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful rebuild, both this repository's and the
  test repository's pins equal the published digest without any manual
  step, verified on at least one re-driven build after merge.
- **SC-002**: Zero container-mode auto-release runs end with the pin-drift
  outcome because of a rebuild whose sync reported success.
- **SC-003**: Every failed sync is visible to the maintainer from the build
  itself within the same run, as a failed build run plus a filed or
  updated tracked issue (FR-007), in 100% of injected failure cases
  (credential unset, under-permissioned, over-reaching, write refused),
  with zero duplicate issues across repeated failures.
- **SC-004**: A credential that reaches one repository beyond the sync set
  causes zero writes in 100% of tested cases.
- **SC-005**: The manual "copy the digest across" instruction no longer
  appears in the live documentation as a required post-rebuild step.

## Assumptions

- The checks that gate the sync are the existing image prerequisite
  verification that stages already run against a configured container
  image and the agent start-up check delivered by #974 (spec 112); this
  feature invents no new check and depends on spec 112 for the latter.
- "Considered and not taken" alternatives from the request are out of scope:
  auto-release syncing before each container run (it would reverse 067
  FR-003) and giving sessions direct variable access. A dispatchable,
  allow-listed "set variable" workflow for manual overrides is out of scope
  for this feature and may be proposed separately.
- The end-to-end test repository is identified by this repository's
  existing `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` setting; no new setting
  names it.
- The scheduled auto-release cadence and the drift check of
  specs/067-e2e-container-image-evidence are unchanged.
- The sync behaviour runs only in Actions, so it is proven after merge by
  re-driving one build and recording the evidence.
