# Feature Specification: Composite Test Harness Gate Discovery

**Feature Branch**: `spec-draft/080-composite-harness-gate-discovery`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #591, routed from the board loop (issue #452) as
`agent_proposed_spec`. Originating finding filed by the implement stage of
spec 057 (run 35670951543):

> Gate discovery is scoped to `.github/scripts`, so composite test harnesses
> under `.github/actions` never run locally. `wc_gate_registry.py` discovers
> gates under `.github/scripts` only, so any `run-tests.sh` under
> `.github/actions/<composite>/tests/` is invisible to both
> `verify-gate-wiring.py` and `run-local-gates.py` even though
> `lint-workflows.yml` runs it in CI. Found while running T062 against Gates
> 82 and 87; both were silently absent from `run-local-gates.py`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The local suite is a true rehearsal of CI (Priority: P1)

A maintainer finishes a change that touches a composite action, runs the one
command `CLAUDE.md` tells them to run before pushing, and sees every gate CI
will run — including the harness that exercises that composite's own shipped
shell. Today that harness runs only if it happens to sit under
`.github/scripts/`; a harness sitting beside the composite it tests runs in
CI and is silently absent from the local sweep, so the maintainer pushes on
a green local run that never touched the check most likely to catch their
change.

**Why this priority**: This is the reported defect and the only part of the
feature that changes what a maintainer is told before they push. Everything
else in this spec is the machinery that keeps the promise true for the next
harness. `CLAUDE.md` states the local suite "is the same set CI runs"; until
this story lands, that sentence is false for any composite harness placed
beside its composite, and false silently.

**Independent Test**: Place a wired composite test harness at the supported
location beside a composite action, run the local gate suite, and confirm the
harness appears in the suite's gate list and executes. Compare the local
suite's gate list against the PR-time gate list CI derives; the two sets are
identical.

**Acceptance Scenarios**:

1. **Given** a composite action whose test harness lives beside it and is
   invoked by `lint-workflows.yml`, **When** a maintainer runs the local gate
   suite, **Then** that harness appears in the suite's gate list, runs with
   the same arguments CI passes it, and its pass/fail is reported in the
   final table.
2. **Given** a composite harness CI invokes twice with different arguments,
   **When** the local suite runs, **Then** it is run twice with those same
   two argument lists, matching the existing behaviour for
   `.github/scripts/` gates.
3. **Given** the set of gates the local suite runs and the set CI's PR-time
   jobs run, **When** the two are compared, **Then** no gate is present in
   one and absent from the other.

---

### User Story 2 - A misplaced harness fails loudly instead of disappearing (Priority: P1)

A contributor adds a test harness for a composite action. Whether they put it
in the supported location or somewhere the discovery convention does not
recognise, they get a definite answer: it is picked up, or a gate fails and
names the file and the location it belongs in. What they never get is a
harness that CI runs and the registry cannot see — the exact shape Principle
VIII calls a liability, because the job list shows a green check for a gate
the wiring checks are not watching.

**Why this priority**: Equal to Story 1 because Story 1 without Story 2 is a
one-time repair. The originating finding was found by a human running T062,
not by a check; three harnesses in the tree today carry hand-written comments
explaining that they were moved away from their composite to stay visible,
which is a convention documented in prose and enforced by nobody. The next
contributor who does not read those comments reintroduces the defect and
nothing reports it.

**Independent Test**: Add a harness at an unrecognised path, run the wiring
gate, and confirm it fails naming that file and the supported location. Then
move the harness to the supported location and confirm the gate passes.

**Acceptance Scenarios**:

1. **Given** a `run-tests.sh` at a path under `.github/actions/` that the
   discovery convention does not recognise, **When** the wiring gate runs,
   **Then** it fails, names the offending path, and states the supported
   location.
2. **Given** a composite harness at the supported location that no workflow
   invokes, **When** the wiring gate runs, **Then** it fails as an orphan,
   the same way an unwired `.github/scripts/verify-*.py` does today.
3. **Given** a composite harness the local runner's tokenizer cannot
   reproduce from the workflow text, **When** the wiring gate runs, **Then**
   it fails on the local/CI parity check rather than dropping the harness
   silently.
4. **Given** an edit to a composite test harness and nothing else, **When** a
   pull request is opened, **Then** the lint workflow is triggered and the
   harness runs.

---

### User Story 3 - The reverse direction covers composite paths too (Priority: P2)

A workflow step names a composite harness path that has been renamed or
deleted. The wiring gate reports it before the step fails at the worst
possible moment, the same way it already does for every `.github/scripts/...`
path a `run:` block names.

**Why this priority**: The reverse check is the cheaper half of the wiring
promise and currently has a blind spot with the same boundary as the forward
one — its path pattern matches `.github/scripts/` only. A composite harness
step pointing at a moved file sits in the job list implying a check that is
not happening. Lower than P1 only because the forward gap is the one that
produced a reported false-green.

**Independent Test**: Point a workflow step at a composite harness path that
does not exist on disk and confirm the wiring gate reports it as missing.

**Acceptance Scenarios**:

1. **Given** a `run:` block naming a composite harness path with no file on
   disk, **When** the wiring gate runs, **Then** it reports the path and the
   workflows that name it.
2. **Given** a composite harness path named only inside a shell comment,
   **When** the wiring gate runs, **Then** the mention does not count as an
   invocation.

---

### Edge Cases

- **Two harnesses sharing a basename.** `.github/scripts/<x>-tests/run-tests.sh`
  and `.github/actions/<x>/tests/run-tests.sh` both end in `run-tests.sh`. The
  local runner labels gates and keys its timing cache by that label, so two
  harnesses that collapse to one label would cross-attribute results and
  corrupt the schedule. Every discovered harness must carry an identity that
  is unique across discovery roots.
- **Nested composite directories.** `.github/actions/_shared/` holds scripts
  shared between composites and is not itself a composite action. Discovery
  must give a defined answer for a harness under a nested or
  underscore-prefixed directory rather than depending on how deep a glob
  happens to reach.
- **The self-checkout path prefix.** Stages resolve composites by two path
  forms — `./.github/actions/<X>` and
  `./.wing-commander-pipeline/.github/actions/<X>` for a published stage.
  Discovery and the reverse check must not read the second form as a
  different, missing file.
- **A composite with no harness at all.** Most composites have none. The
  absence of a harness is not a failure; only a harness in an unrecognised
  place is.
- **A harness wired to a workflow other than the PR-time lint suite.** As
  with `verify-watchdog-run.sh` today, such a harness is wired but is not
  part of what the local suite claims to cover; it must not be reported as
  missing from the local suite.
- **A harness that exists on disk under an unrecognised path but is invoked
  by no workflow either.** It is dead weight in an unsupported place; the
  failure must be unambiguous about which of the two problems it is.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Gate discovery MUST recognise composite action test harnesses
  as gates, not only scripts under `.github/scripts/`, so that a single
  answer to "what is a gate" is shared by the wiring gate and the local
  runner. [NEEDS CLARIFICATION: which convention — (a) add
  `.github/actions/<composite>/tests/run-tests.sh` as a second discovery
  root so harnesses may live beside the composite they test, (b) keep
  `.github/scripts/` as the single home and add a check that fails when any
  harness appears under `.github/actions/`, or (c) both — discover the
  beside-the-composite location AND fail on any other location under
  `.github/actions/`]
- **FR-002**: The local gate suite MUST run every discovered composite
  harness that the PR-time lint workflow runs, with the same argument lists
  CI passes, including a harness CI invokes more than once with different
  arguments.
- **FR-003**: The wiring gate's forward direction MUST report a discovered
  composite harness that no workflow invokes, the same way it reports an
  orphaned `verify-*` script.
- **FR-004**: The wiring gate's reverse direction MUST report a composite
  harness path that a workflow `run:` block names but that does not exist on
  disk, and MUST NOT count a mention inside a shell comment as an invocation.
- **FR-005**: The local/CI parity check MUST cover composite harnesses, so a
  harness CI runs that the local runner cannot reproduce fails the wiring
  gate rather than being dropped from the local suite.
- **FR-006**: A test harness placed at a path the convention does not
  recognise MUST cause a gate to fail loudly, naming the offending path and
  the supported location. Silent non-discovery is not an acceptable outcome
  for any path under `.github/actions/` or `.github/scripts/`.
- **FR-007**: Every discovered gate MUST have an identity that is unique
  across all discovery roots, so that two harnesses sharing a filename are
  never conflated in the local runner's output, its timing cache, or the
  wiring gate's attribution of invocations to files.
- **FR-008**: The lint workflow's pull-request path filter MUST trigger the
  gate suite on an edit to a composite test harness, so a harness is never
  wired but untriggered.
- **FR-009**: The discovery convention MUST be documented in exactly one
  canonical place. Each existing composite harness that today carries its own
  prose explaining why it does not live beside its composite MUST either lose
  that prose or replace it with a pointer to the canonical home, leaving no
  second copy to drift.
- **FR-010**: Every failure branch introduced by this change MUST be
  exercised by a checked-in fixture — at minimum: a harness at an
  unrecognised path, an unwired harness at the supported path, a
  workflow-named harness path absent from disk, and a basename collision
  across discovery roots.
- **FR-011**: The three composite harnesses that today live under
  `.github/scripts/*-tests/` for the sole reason that discovery could not see
  them elsewhere MUST be handled explicitly rather than left undecided.
  [NEEDS CLARIFICATION: migrate all three beside their composites as part of
  this feature, leave all three where they are and treat the new location as
  additive for future harnesses, or migrate one as a worked example and leave
  the rest]
- **FR-012**: The scope of what discovery recognises under `.github/actions/`
  MUST be bounded explicitly. [NEEDS CLARIFICATION: harness entrypoints only
  (`run-tests.sh`), or also standalone `verify-*.py|.sh` gates and other
  independently-invoked scripts placed under a composite's directory]
- **FR-013**: Discovery MUST resolve a composite harness path consistently
  regardless of which checkout-relative prefix a workflow uses to reach the
  composite, so the self-checkout form used by published stages does not read
  as a separate, missing file.
- **FR-014**: The convention MUST remain mechanical — read off the directory
  tree — rather than a manifest of harness names that a new harness can be
  born exempt from by omission.

### Key Entities

- **Gate**: a check that must be invoked by at least one workflow. Today:
  `verify-*` scripts and multi-file harness entrypoints under
  `.github/scripts/`. This feature widens the population to include composite
  action test harnesses.
- **Discovery root**: a directory prefix under which the naming convention is
  applied. There is exactly one today (`.github/scripts/`); this feature
  either adds a second or makes the single root enforced rather than assumed.
- **Composite test harness**: the entrypoint of a test suite whose subject is
  a composite action's own shipped shell — extracted and run against fixtures
  so it cannot drift from what ships.
- **Gate identity**: the label by which a gate is listed, reported, and
  cached by the local runner. Must be unique across discovery roots.
- **Wiring**: the two-directional relationship between gates on disk and the
  `run:` blocks that invoke them — forward (every gate is invoked) and
  reverse (every invoked path exists).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The set of gates the local suite runs and the set the PR-time
  CI jobs run are identical — zero gates present in one and absent from the
  other — and this equality is asserted by a gate, not by inspection.
- **SC-002**: Every composite action in the tree that has a test harness has
  that harness represented in the local suite's gate list. Measured today
  against the three known harnesses and the two harnesses (Gates 82 and 87's
  subjects) the originating finding reported as silently absent.
- **SC-003**: Adding a new composite test harness at the supported location
  and wiring it to a workflow makes it run in the local suite with no edit to
  any registry, list, or manifest of gate names.
- **SC-004**: A harness placed at an unrecognised path is reported by a
  failing gate within a single CI run, and the failure message names both the
  offending path and the supported location.
- **SC-005**: Each failure branch listed in FR-010 is demonstrated by a
  checked-in fixture that fails when the corresponding behaviour is removed.
- **SC-006**: The prose describing where a composite test harness belongs
  exists in exactly one file; every other mention is a pointer to it.
- **SC-007**: No existing gate changes which subject it runs or which
  arguments it receives as a result of this change — the gate count may grow,
  but no currently-passing gate starts checking something different.

## Assumptions

- The repository's existing convention-over-manifest principle holds: gate
  membership stays a rule read off the directory tree, because a list is what
  issue #149 was and a new gate born exempt from a list is invisible.
- `lint-workflows.yml` already lists `.github/actions/**` in its
  pull-request path filter, so FR-008 is expected to be satisfied already and
  needs verification rather than new plumbing.
- A `tests/` directory inside a composite action's directory is internal
  detail, not part of the adopter-pinned compatibility surface Principle VII
  defines (which is inputs, outputs, and secrets). Test fixtures shipping
  inside a pinned release are acceptable; this assumption should be
  re-confirmed if FR-001 resolves toward option (a) or (c).
- The three composite harnesses under `.github/scripts/*-tests/` pass today
  and are correctly wired; this feature changes where discovery looks, not
  what those harnesses check.
- No change to the published `workflow_call` interface of any stage workflow
  is required.
- The board loop's size-and-path backstop is not a constraint on this
  feature — it arrives through the spec lifecycle, not as a fix PR.
