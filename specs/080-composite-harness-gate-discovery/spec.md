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

## Clarifications

### Session 2026-09-25 — answered on [#591](https://github.com/charlesguse/wing-commander/issues/591)

- **FR-001 — which discovery convention**: **option (b)**. `.github/scripts/`
  stays the single discovery root, and a new gate fails when a test harness
  appears under `.github/actions/`. Rationale given with the answer: test
  fixtures stay out of adopter-pinned composite directories. The local suite
  and CI therefore agree because there is exactly one place a harness can
  live and a gate enforces it — not because discovery reaches into two roots.
- **FR-011 — the three relocated harnesses**: **leave all three where they
  are**, which option (b) makes moot: `.github/scripts/<name>-tests/` is the
  supported location, so the three harnesses already sit correctly. What
  remains for them is FR-009's prose consolidation.
- **FR-012 — how wide the check reaches**: the enforcement check fails on
  `run-tests.sh` and on standalone `verify-*.py` / `verify-*.sh` at any depth
  under `.github/actions/`, with an explicit carve-out for
  `.github/actions/_shared/` helpers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The local suite is a true rehearsal of CI (Priority: P1)

A maintainer finishes a change that touches a composite action, runs the one
command `CLAUDE.md` tells them to run before pushing, and sees every gate CI
will run — including the harness that exercises that composite's own shipped
shell. That holds only while every harness sits under `.github/scripts/`,
which is the one place discovery looks; a harness placed beside the composite
it tests runs in CI and is silently absent from the local sweep, so the
maintainer pushes on a green local run that never touched the check most
likely to catch their change.

**Why this priority**: This is the reported defect and the only part of the
feature that changes what a maintainer is told before they push. Everything
else in this spec is the machinery that keeps the promise true for the next
harness. `CLAUDE.md` states the local suite "is the same set CI runs"; until
this story lands, that sentence is true only by accident of where the
harnesses happen to sit today, and nothing notices when that stops being so.

**Independent Test**: Compare the set of gates the local suite runs against
the PR-time gate list CI derives, and confirm the two are identical and that
the comparison is made by a gate that fails on divergence rather than by
inspection. Confirm every harness in the suite's gate list is reported under
an identity distinct from every other.

**Acceptance Scenarios**:

1. **Given** a composite action whose test harness lives at the supported
   location under `.github/scripts/` and is invoked by `lint-workflows.yml`,
   **When** a maintainer runs the local gate suite, **Then** that harness
   appears in the suite's gate list, runs with the same arguments CI passes
   it, and its pass/fail is reported in the final table under an identity no
   other gate shares.
2. **Given** a composite harness CI invokes twice with different arguments,
   **When** the local suite runs, **Then** it is run twice with those same
   two argument lists, matching the existing behaviour for other
   `.github/scripts/` gates.
3. **Given** the set of gates the local suite runs and the set CI's PR-time
   jobs run, **When** the two are compared, **Then** no gate is present in
   one and absent from the other, and a divergence fails the build.

---

### User Story 2 - A harness in the wrong place fails loudly instead of disappearing (Priority: P1)

A contributor adds a test harness for a composite action. If they put it
beside the composite — the intuitive place, and where two of today's
harnesses first shipped — a gate fails, names the file, and names the
supported location under `.github/scripts/`. What they never get is a harness
that CI runs and the registry cannot see — the exact shape Principle VIII
calls a liability, because the job list shows a green check for a gate the
wiring checks are not watching.

**Why this priority**: Equal to Story 1 because Story 1 without Story 2 is a
one-time repair. The originating finding was found by a human running T062,
not by a check; three harnesses in the tree today carry hand-written comments
explaining that they were moved away from their composite to stay visible,
which is a convention documented in prose and enforced by nobody. The next
contributor who does not read those comments reintroduces the defect and
nothing reports it.

**Independent Test**: Add a `run-tests.sh` under `.github/actions/`, run the
enforcement gate, and confirm it fails naming that file and the supported
location. Move the harness to `.github/scripts/<name>-tests/run-tests.sh` and
confirm the gate passes. Repeat with a standalone `verify-*.sh`, and confirm
a helper under `.github/actions/_shared/` is not flagged.

**Acceptance Scenarios**:

1. **Given** a `run-tests.sh` at any depth under `.github/actions/` outside
   `.github/actions/_shared/`, **When** the enforcement gate runs, **Then**
   it fails, names the offending path, and states the supported location
   under `.github/scripts/`.
2. **Given** a standalone `verify-*.py` or `verify-*.sh` at any depth under
   `.github/actions/` outside `.github/actions/_shared/`, **When** the
   enforcement gate runs, **Then** it fails the same way.
3. **Given** a helper script under `.github/actions/_shared/`, **When** the
   enforcement gate runs, **Then** it is not flagged, and that carve-out is
   itself pinned by a fixture so it cannot silently widen to cover the rest
   of `.github/actions/`.
4. **Given** a composite harness at the supported location that no workflow
   invokes, **When** the wiring gate runs, **Then** it fails as an orphan,
   the same way an unwired `.github/scripts/verify-*.py` does today.
5. **Given** a composite harness the local runner's tokenizer cannot
   reproduce from the workflow text, **When** the wiring gate runs, **Then**
   it fails on the local/CI parity check rather than dropping the harness
   silently.
6. **Given** an edit to a composite test harness and nothing else, **When** a
   pull request is opened, **Then** the lint workflow is triggered and the
   harness runs.

---

### User Story 3 - The reverse direction covers `.github/actions/` paths too (Priority: P2)

A workflow step names a script under `.github/actions/` — a `_shared` helper,
or a harness path someone is in the middle of moving — that has been renamed
or deleted. The wiring gate reports it before the step fails at the worst
possible moment, the same way it already does for every `.github/scripts/...`
path a `run:` block names.

**Why this priority**: The reverse check is the cheaper half of the wiring
promise and currently has a blind spot with the same boundary as the forward
one — its path pattern matches `.github/scripts/` only, while workflows
already invoke `.github/actions/_shared/*.sh` directly from `run:` blocks. A
step pointing at a moved file sits in the job list implying a check that is
not happening. Lower than P1 only because the forward gap is the one that
produced a reported false-green.

**Independent Test**: Point a workflow step at a `.github/actions/` script
path that does not exist on disk and confirm the wiring gate reports it as
missing.

**Acceptance Scenarios**:

1. **Given** a `run:` block naming a `.github/actions/` script path with no
   file on disk, **When** the wiring gate runs, **Then** it reports the path
   and the workflows that name it.
2. **Given** such a path named only inside a shell comment, **When** the
   wiring gate runs, **Then** the mention does not count as an invocation.
3. **Given** a `run:` block reaching a composite script through the
   self-checkout prefix (`./.wing-commander-pipeline/.github/actions/<X>/…`),
   **When** the wiring gate runs, **Then** it resolves to the same file
   rather than reporting a second, missing path.

---

### Edge Cases

- **Harnesses sharing a basename.** All five harnesses under
  `.github/scripts/*-tests/` are named `run-tests.sh`. The local runner
  labels a gate by basename plus arguments and keys its timing cache by that
  label, so today all five collapse to the single label `run-tests.sh`: their
  durations cross-attribute in the cache and a filter token matching the
  label selects every one of them. Keeping one discovery root does not make
  this go away — FR-007 requires a per-gate identity that is unique.
- **Nested and underscore-prefixed directories under `.github/actions/`.**
  The enforcement check must reach any depth, because a harness two levels
  down is exactly as invisible to discovery as one at the top. The one
  carved-out subtree is `.github/actions/_shared/`, which holds scripts
  shared between composites rather than independently-invoked gates.
- **The self-checkout path prefix.** Stages resolve composites by two path
  forms — `./.github/actions/<X>` and
  `./.wing-commander-pipeline/.github/actions/<X>` for a published stage. The
  reverse check must not read the second form as a different, missing file,
  and the enforcement check must be rooted at this repository's own
  `.github/actions/` rather than sweeping a vendored checkout of the
  repository as if it were part of the tree under review.
- **A composite with no harness at all.** Most composites have none. The
  absence of a harness is not a failure; only a harness in an unsupported
  place is.
- **A harness wired to a workflow other than the PR-time lint suite.** As
  with `verify-watchdog-run.sh` today, such a harness is wired but is not
  part of what the local suite claims to cover; it must not be reported as
  missing from the local suite.
- **A `run-tests.sh` under `.github/actions/` that no workflow invokes
  either.** It is dead weight in an unsupported place, but placement is the
  only question the enforcement check answers, and moving the file is the
  fix; the failure must name placement rather than orphan-hood, which is a
  second question the wiring gate answers only once the file has moved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `.github/scripts/` MUST remain the single discovery root, and
  the repository MUST enforce that no test harness or standalone gate script
  lives under `.github/actions/`, so that a single answer to "what is a gate"
  is shared by the wiring gate and the local runner and is enforced rather
  than assumed.
- **FR-002**: The local gate suite MUST run every composite harness that the
  PR-time lint workflow runs, with the same argument lists CI passes,
  including a harness CI invokes more than once with different arguments.
- **FR-003**: The wiring gate's forward direction MUST report a discovered
  composite harness that no workflow invokes, the same way it reports an
  orphaned `verify-*` script.
- **FR-004**: The wiring gate's reverse direction MUST report a
  `.github/actions/` script path that a workflow `run:` block names but that
  does not exist on disk, and MUST NOT count a mention inside a shell comment
  as an invocation.
- **FR-005**: The local/CI parity check MUST cover composite harnesses, so a
  harness CI runs that the local runner cannot reproduce fails the wiring
  gate rather than being dropped from the local suite.
- **FR-006**: A test harness or standalone gate script placed under
  `.github/actions/` MUST cause a gate to fail loudly, naming the offending
  path and the supported location under `.github/scripts/`. Silent
  non-discovery is not an acceptable outcome for any path under
  `.github/actions/` or `.github/scripts/`, with the single bounded exception
  of the `.github/actions/_shared/` carve-out in FR-012.
- **FR-007**: Every gate the local runner lists MUST carry an identity that
  is unique across the whole gate population, so that harnesses sharing a
  filename are never conflated in the local runner's output, its timing
  cache, its filter arguments, or the wiring gate's attribution of
  invocations to files. This is a live defect, not a hypothetical: the five
  `run-tests.sh` harnesses in the tree today already share one label.
- **FR-008**: The lint workflow's pull-request path filter MUST trigger the
  gate suite on an edit to a composite test harness at its supported location
  and on an edit to a composite action, so a harness is never wired but
  untriggered.
- **FR-009**: The convention — a composite's test harness lives under
  `.github/scripts/<name>-tests/`, never beside the composite — MUST be
  documented in exactly one canonical place, together with both reasons for
  it: gate discovery reads only that root, and test fixtures stay out of the
  adopter-pinned composite directories. Each existing composite harness that
  today carries its own prose explaining why it does not live beside its
  composite MUST either lose that prose or replace it with a pointer to the
  canonical home, leaving no second copy to drift. The enforcement gate's
  failure message MUST point at the same canonical home.
- **FR-010**: Every failure branch introduced by this change MUST be
  exercised by a checked-in fixture — at minimum: a `run-tests.sh` under
  `.github/actions/`, a standalone `verify-*` script under
  `.github/actions/`, a `.github/actions/_shared/` helper that must NOT be
  flagged, an unwired harness at the supported path, a workflow-named
  `.github/actions/` script path absent from disk, and two harnesses whose
  identities would otherwise collide.
- **FR-011**: The three composite harnesses that today live under
  `.github/scripts/*-tests/` MUST stay where they are — that path is the
  supported location, so no harness is relocated by this feature. Only their
  explanatory prose changes, per FR-009.
- **FR-012**: The enforcement check's subject MUST be bounded explicitly: it
  fails on any file named `run-tests.sh` and on any standalone `verify-*.py`
  or `verify-*.sh`, at any depth under `.github/actions/`, with exactly one
  carve-out — `.github/actions/_shared/`, which holds helper scripts invoked
  by composites and workflows rather than independently-invoked gates. No
  other file type under `.github/actions/` is in scope.
- **FR-013**: The wiring gate MUST resolve a `.github/actions/` script path
  consistently regardless of which checkout-relative prefix a workflow uses
  to reach it, so the self-checkout form used by published stages does not
  read as a separate, missing file.
- **FR-014**: The convention MUST remain mechanical — read off the directory
  tree — rather than a manifest of harness names that a new harness can be
  born exempt from by omission. The `_shared` carve-out is part of the rule,
  not an entry on a list of exempt files.

### Key Entities

- **Gate**: a check that must be invoked by at least one workflow. `verify-*`
  scripts and multi-file harness entrypoints under `.github/scripts/`,
  including the harnesses whose subject is a composite action.
- **Discovery root**: the directory prefix under which the naming convention
  is applied. There is exactly one, `.github/scripts/`; this feature makes
  that single root enforced rather than assumed.
- **Composite test harness**: the entrypoint of a test suite whose subject is
  a composite action's own shipped shell — extracted and run against fixtures
  so it cannot drift from what ships. Lives under `.github/scripts/`, not
  beside its subject.
- **Unsupported location**: any path under `.github/actions/`, outside the
  `.github/actions/_shared/` carve-out, holding a `run-tests.sh` or a
  standalone `verify-*` script. The enforcement check's only subject.
- **Gate identity**: the handle by which a gate is listed, reported, filtered
  and cached by the local runner. Must be unique per gate, not per basename.
- **Wiring**: the two-directional relationship between gates on disk and the
  `run:` blocks that invoke them — forward (every gate is invoked) and
  reverse (every invoked path exists).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The set of gates the local suite runs and the set the PR-time
  CI jobs run are identical — zero gates present in one and absent from the
  other — and this equality is asserted by a gate, not by inspection.
- **SC-002**: Every composite action in the tree that has a test harness has
  that harness at the supported location and represented in the local suite's
  gate list. Measured today against the five harnesses under
  `.github/scripts/*-tests/`, which include the ones the originating finding
  reported as silently absent before they were moved.
- **SC-003**: Adding a new composite test harness at the supported location
  and wiring it to a workflow makes it run in the local suite with no edit to
  any registry, list, or manifest of gate names.
- **SC-004**: A harness placed under `.github/actions/` is reported by a
  failing gate within a single CI run, and the failure message names both the
  offending path and the supported location.
- **SC-005**: Each failure branch listed in FR-010 is demonstrated by a
  checked-in fixture that fails when the corresponding behaviour is removed.
- **SC-006**: The prose describing where a composite test harness belongs
  exists in exactly one file; every other mention is a pointer to it.
- **SC-007**: No existing gate changes which subject it runs or which
  arguments it receives as a result of this change — the gate count may grow,
  but no currently-passing gate starts checking something different.
- **SC-008**: The local suite's gate list contains no two entries sharing an
  identity, measured across the whole list rather than within a directory.

## Assumptions

- The repository's existing convention-over-manifest principle holds: gate
  membership stays a rule read off the directory tree, because a list is what
  issue #149 was and a new gate born exempt from a list is invisible.
- `lint-workflows.yml` already lists `.github/scripts/**` and
  `.github/actions/**` in its pull-request path filter, so FR-008 is expected
  to be satisfied already and needs verification rather than new plumbing.
- Principle VII's adopter-pinned compatibility surface is a standing reason
  to keep test fixtures out of `.github/actions/` altogether, and the
  clarified convention takes that position: no fixture ships inside a pinned
  composite release. This removes the need to decide whether a `tests/`
  directory inside a composite would have counted as internal detail.
- The three composite harnesses under `.github/scripts/*-tests/` pass today
  and are correctly wired; this feature changes what the tree is checked
  against, not what those harnesses check.
- No change to the published `workflow_call` interface of any stage workflow
  is required.
- The board loop's size-and-path backstop is not a constraint on this
  feature — it arrives through the spec lifecycle, not as a fix PR.
