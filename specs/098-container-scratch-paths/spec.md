# Feature Specification: A Scratch Path a Container Job Can Actually Reach

**Feature Branch**: `spec-draft/098-container-scratch-paths`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #741 — "Container jobs: `${{ runner.temp }}`
written inside `run:` bodies resolves to a host path; /tmp/wing-commander
files are not keyed per run" (routed from board-loop.yml, originating
issue #602; found by the code review of the #598 fix on branch
`fix/598-meta-json-tmp`)

## Overview

`runner.temp` names the **host** runner's temp directory. When a job
declares a `container:`, the runner bind-mounts that directory into the
container at a different path and then rewrites the *step environment
values* that begin with the host path — the values a step receives through
`env:` and through `with:` (which reach an action as `INPUT_*`) — so that
a step running inside the container sees the container path.

A workflow expression written into the **text of a `run:` script** gets no
such treatment. Expression substitution happens when the script file is
rendered, before the step is handed to a shell; there is no environment
value to rewrite. Inside a container job, `${{ runner.temp }}` in a `run:`
body therefore expands to a host path that does not exist in the
container's filesystem.

The consequence is not simply "a missing directory". It is that a single
job can end up holding **two disagreeing references to the same intended
file**: one reference that the runner translated (an `env:`/`with:` value,
or an `actions/upload-artifact` `path:`) and one that it did not (the same
expression pasted into a `run:` body, or into an agent prompt that tells
the agent where to write). Each reference is individually plausible. The
step that writes succeeds, the step that reads finds nothing, and the
failure surfaces as an empty artifact or a `No such file or directory` in
a job whose scratch handling looks correct on the page.

This repository ships that pattern widely. On the order of three dozen
host-temp references sit inside `run:` bodies and agent-prompt prose
across eight workflow files — `finalize.yml`, `watchdog.yml`,
`clarify.yml`, `intake.yml`, `cleanup.yml`, `rebase.yml`, `board-loop.yml`
and `auto-update-spec-kit.yml`. Nearly every stage workflow declares a
`container:` on its agent job, so nearly every one of those references is
exposed. `specs/038-runner-container-passthrough` records that
container-hosted runs are still unverified against a real adopter image,
which is exactly why none of this has produced a red run yet: the defect
is latent, waiting for the first adopter who supplies a container.

A second, smaller defect travels with it. Four workflows stage files under
a fixed `/tmp/wing-commander/<name>` — `clarify.yml`'s
`clarification-answer.md`, `pr-conversation.yml`'s
`pr-conversation-request.md` and `act-drafted-content.json`,
`board-loop.yml`'s `board-review-*.txt`. That directory is the one
exemption Gate 48's fixed-`/tmp` scan grants, and it is not keyed by run.
Two concurrent jobs on one self-hosted runner, **outside** a container,
share that path and overwrite each other. (Container jobs each get their
own `/tmp`, so they are unaffected — the two defects are exposed by
opposite configurations, which is why one fix cannot serve both.)

Gate 48 is the gate that already owns "where does scratch live" for this
repository: `verify-stage-shell-lint.py` fails any workflow or composite
step naming a fixed `/tmp/<name>` path instead of `$RUNNER_TEMP`. It does
not yet know about the untranslated-expression form, so nothing stops the
next paste.

### Layer

This feature changes the **published contract** (Principle VII): the stage
workflows under `.github/workflows/` and the composite actions under
`.github/actions/**` that adopters pin by release tag. No input, secret or
output name changes — the change is internal to how those stages name
their own scratch files. It also changes the **consuming instrument** where
this repository's own non-published workflows (`board-loop.yml`,
`auto-update-spec-kit.yml`, `pr-conversation.yml`) carry the same pattern.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An adopter's container-hosted stage run finds its own scratch files (Priority: P1)

An adopter pins a Wing Commander release and supplies a `container:` image
for the stage jobs, as `specs/038-runner-container-passthrough` invites
them to. They open an issue, label it, and the lifecycle runs. Every stage
that stages a file for a later step — the clarification questionnaire, the
finalize summary and remaining-work list, the cleanup summary, the PR body
it rewrites, the execution-output artifact — finds that file where it
expects it, and the artifacts upload non-empty.

**Why this priority**: This is the defect. Everything else in this feature
either prevents its return or cleans up a neighbour. Without it, a
container-supplying adopter gets stages that fail in ways whose cause is
invisible from the workflow text.

**Independent Test**: Re-drive one container-hosted stage run (the
wrapper that can dispatch it) and confirm the staged file is read
successfully by the step downstream of the one that wrote it, and that the
`claude-execution-output` and `metrics-record` artifacts are present and
non-empty.

**Acceptance Scenarios**:

1. **Given** a stage job running in a `container:`, **When** a `run:` step
   writes a scratch file and a later step in the same job reads it,
   **Then** both steps resolve the same path inside the container and the
   read succeeds.
2. **Given** a stage job running in a `container:` whose agent is
   instructed to write a file for a later step to read, **When** the agent
   writes it, **Then** the later step — and any `with:`/`env:` value
   naming the same file — resolves the path the agent used.
3. **Given** the same stage job running directly on a host runner with no
   `container:`, **When** the stage runs, **Then** its behaviour is
   unchanged from before this feature.
4. **Given** a stage job in a `container:` whose scratch file is uploaded
   by `actions/upload-artifact`, **When** the job finishes, **Then** the
   artifact contains the file the `run:` step wrote, not an empty
   directory.

---

### User Story 2 - The next paste of the broken form fails at PR time (Priority: P2)

A maintainer or a pipeline stage adds a `run:` step that names a scratch
file. They reach for the expression form out of habit. The PR-time gate
suite fails, names the file and line, and says which form to use instead.

**Why this priority**: Principle VIII — a rule with no gate behind it
lasts until the next session, and CLAUDE.md says so explicitly. The P1 fix
touches three dozen sites across eight files; without a gate it will decay
back one paste at a time, and the decay is silent because no run goes red.

**Independent Test**: Reintroduce one host-temp expression into one `run:`
body, run `python .github/scripts/run-local-gates.py`, and confirm Gate 48
fails naming that file and line. Revert, re-run, confirm green.

**Acceptance Scenarios**:

1. **Given** the shipped tree after this feature, **When** the gate suite
   runs, **Then** the new scan reports zero findings and says how many
   files it scanned.
2. **Given** a workflow with a host-temp expression inside a `run:` body,
   **When** the gate runs, **Then** it fails and names the file and the
   line.
3. **Given** a composite action under `.github/actions/**` with the same
   construct in its own `run:` step, **When** the gate runs, **Then** it
   fails the same way.
4. **Given** a workflow using the host-temp expression in an `env:` or
   `with:` value — the form the runner does translate — **When** the gate
   runs, **Then** it does not flag it.
5. **Given** the gate's own self-test, **When** it runs, **Then** it
   exercises both directions: a fixture that must fail, and the shipped
   tree that must pass.

---

### User Story 3 - Two concurrent jobs on one self-hosted runner don't trample each other's staging file (Priority: P3)

A maintainer runs two lifecycle stages concurrently on one self-hosted
runner, outside a container — two specs in flight, which the constitution
explicitly supports. Each job's staged input file belongs to that job
alone.

**Why this priority**: Real but narrower: it needs a self-hosted runner,
concurrency, and no container. It carries the one open design trade-off in
this feature, which is why it is separable from P1 and P2.

**Independent Test**: Run two jobs that stage the same-named file
concurrently on one runner outside a container and confirm each reads back
what it wrote.

**Acceptance Scenarios**:

1. **Given** two jobs staging the same-named file concurrently on one
   self-hosted runner outside a container, **When** both write and then
   read, **Then** each reads its own content.
2. **Given** the staged file must be read by an agent's file-reading tool,
   **When** the remediation moves or renames it, **Then** the agent can
   still read it and the prompt names the path it can reach.

---

### Edge Cases

- An expression that reaches a `run:` body **indirectly** — a job-level or
  workflow-level `env:` whose value is `${{ runner.temp }}/x`, consumed as
  `"$SOME_VAR"` in the script. The `env:` value is translated, so this
  form is correct; the gate must not flag it, and the audit must not
  "fix" it into something worse.
- The reverse split: a `run:` body that correctly uses the environment
  variable while a sibling `with:` value in the same job still uses the
  expression. Both resolve to the container path, so they agree — but the
  gate must not create a false sense that only one form is ever right.
- An agent prompt that embeds the path **mid-prose** rather than as the
  whole value. Even as a `with:` input, the value does not *begin* with
  the host path, so the runner's rewrite does not apply. This is the case
  behind the clarification in FR-007.
- A scratch file written by one job and read by another job (via an
  artifact). The host/container distinction does not carry across jobs;
  only the artifact name does.
- A composite action invoked from a container job and from a host job in
  the same repository. It must be correct under both without a per-caller
  branch.
- A `run:` step whose shell is not bash (a `container:` image with a
  different default shell — see the `container-shell-safety` skill). The
  environment-variable form must not assume a bash-only expansion.
- The gate's own subject list going empty (a glob that matches nothing).
  Principle VIII requires that to fail loudly, as the existing
  fixed-`/tmp` scan already does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: No `run:` step in any workflow under `.github/workflows/` or
  any composite action under `.github/actions/**` MUST reference the
  runner's temp directory through a workflow expression. Such a reference
  MUST instead be made through the runner-provided environment variable,
  which the container receives already translated.

- **FR-002**: Each converted site MUST name the same file as before on a
  host runner. The conversion is a path-resolution fix, not a rename: no
  file changes its name, its directory, or the step that writes or reads
  it.

- **FR-003**: Within a single job, every reference to one scratch file —
  the `run:` body that writes it, the `run:` body that reads it, the
  `with:` or `env:` value that names it, the artifact `path:` that uploads
  it, and the agent prompt that instructs an agent to write it — MUST
  resolve to the same filesystem path both on a host runner and inside a
  `container:`. A job MUST NOT hold a translated and an untranslated
  reference to the same intended file.

- **FR-004**: The PR-time gate that already owns scratch-path policy
  (Gate 48) MUST additionally fail any workflow or composite whose `run:`
  body contains a runner-temp workflow expression, reporting the file and
  the line. It MUST NOT flag the same expression in an `env:` value, a
  `with:` value, or a comment.

- **FR-005**: The new scan MUST live in the same script as the existing
  fixed-`/tmp` scan, sharing its subject-file discovery — not in a second
  script and not duplicated into a second workflow (CLAUDE.md, "Shared
  logic has exactly one home").

- **FR-006**: The new scan MUST fail loudly if its subject-file list is
  empty, and MUST report how many files it scanned and how many findings
  it produced, matching the existing scan's reporting (Principle VIII).

- **FR-007**: The rule's treatment of **agent-prompt prose** MUST be
  decided and stated. A prompt is a `with:` value, but one that embeds the
  path mid-string, so the runner's begins-with rewrite does not apply to
  it; `finalize.yml`, `cleanup.yml` and `clarify.yml` all instruct an
  agent to write a file at a runner-temp expression this way.
  [NEEDS CLARIFICATION: does the ban in FR-001 and the gate in FR-004
  extend to runner-temp expressions inside agent-prompt values, or is
  FR-001 limited to `run:` bodies with prompt prose handled separately?]

- **FR-008**: Fixed `/tmp/wing-commander/<name>` staging files MUST NOT be
  shared by two concurrent jobs on one runner outside a container.
  [NEEDS CLARIFICATION: which remediation — key the files by run (a
  per-run subdirectory), or relocate them under the runner temp directory
  after confirming the agent's file-reading tool can reach it, or a third
  option? The two differ in blast radius: keying preserves the existing
  `/tmp/wing-commander` exemption and the agent-readability that is
  already proven, while relocating removes the exemption entirely but must
  re-establish that the agent can read the new location.]

- **FR-009**: The gaps the code review identified in Gate 48's existing
  fixed-`/tmp` scan MUST be resolved — either closed or explicitly
  recorded as out of scope with the reason.
  [NEEDS CLARIFICATION: which of the three gaps are in scope: a `/tmp`
  prefix followed by a variable; a bare `/tmp` used as a directory
  operand; a `/tmp` path with no separating space before it; and
  job-level or workflow-level `env:` values, which the scan does not read
  at all?]

- **FR-010**: Every failure branch the new scan ships MUST be exercised by
  a checked-in fixture in the gate's self-test — both a fixture that must
  be flagged and the shipped tree that must not be (Principle VIII).

- **FR-011**: The behaviour of every stage running directly on a host
  runner, with no `container:`, MUST be unchanged by this feature. No
  stage may branch its scratch-path handling on whether a container is
  present.

- **FR-012**: Because this behaviour only manifests in Actions, the fix
  MUST be proven after merge by re-driving at least one container-hosted
  run and recording the evidence on the PR or the lifecycle issue
  (CLAUDE.md, "Working the issue board"). The evidence MUST show a staged
  file written and then read successfully inside the container, not merely
  a green job.

- **FR-013**: The audit that produces the site inventory MUST cover every
  workflow and every composite action in the repository, not only the
  sites the originating issue listed, and its result MUST be recorded so a
  reviewer can confirm the list is complete without repeating the scan.

### Key Entities

- **Runner temp directory**: The per-run scratch directory the runner
  provides. Has two names for one directory when a container is in play —
  a host path and a container path — and the runner translates between
  them only for step environment values.
- **Scratch reference**: One mention of one scratch file at one site: a
  `run:` body, an `env:` value, a `with:` value, an artifact `path:`, or
  agent-prompt prose. Each is either translated or untranslated; a correct
  job's references all agree.
- **Staging file**: A file a `run:` step writes for an agent to read in
  the same job, currently under a fixed `/tmp/wing-commander` path. Its
  identity today is its name alone, which is what makes two concurrent
  jobs collide.
- **Gate 48 scratch-path scan**: The PR-time check in
  `verify-stage-shell-lint.py` that owns scratch-path policy, its
  subject-file discovery, its exemption list, and its self-test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A repository-wide scan of every workflow and composite
  reports zero runner-temp workflow expressions inside `run:` bodies,
  down from the roughly three dozen across eight files present today.

- **SC-002**: Reintroducing a single such expression into any one `run:`
  body causes the PR-time gate suite to fail, and the failure message
  names that file and that line.

- **SC-003**: At least one container-hosted run of a stage that writes a
  scratch file in one step and reads it in a later step completes with the
  read succeeding and the run's artifacts present and non-empty, and the
  run is linked from the PR or the lifecycle issue.

- **SC-004**: `python .github/scripts/run-local-gates.py` passes on the
  final diff, including the new scan and its self-test.

- **SC-005**: Two concurrent jobs staging the same-named file on one
  self-hosted runner outside a container each read back their own content,
  with no cross-read.

- **SC-006**: Every stage run on a host runner with no `container:`
  behaves identically to the pre-change baseline — no new failure, no new
  skipped step, no changed artifact contents.

- **SC-007**: A reviewer can determine, from the recorded audit result
  alone, that no site was missed — without re-running the scan.

## Assumptions

- The runner's translation of step environment values applies to values
  that *begin* with a mounted host path; a value that merely contains one
  mid-string is not rewritten. This is what makes agent-prompt prose a
  distinct case from an ordinary `with:` value, and it is the basis of
  FR-007's question.
- No failing run has yet been observed for either defect. The evidence is
  the actions/runner source the code review cited, plus
  `specs/038-runner-container-passthrough`'s own record that container
  runs are unverified. This feature is preventive, and its proof
  obligation (FR-012) exists because a preventive fix with no observed
  failure has no failing run to re-drive.
- Container jobs each receive their own `/tmp`, so the fixed-`/tmp`
  collision in FR-008 is a host-runner concern only, and the two defects
  in this feature are exposed by opposite configurations.
- Nearly every stage workflow already declares a `container:` on its agent
  job, so the P1 scope is "most stages", not "one stage".
- Gate 48 remains the single home for scratch-path policy; this feature
  extends it rather than adding a parallel gate.
- No adopter is currently supplying a container image to these stages, so
  the fix is not a live-incident response and can be sequenced behind its
  own gate and proof.
- The published contract's input, secret and output names are untouched,
  so this is not a breaking change under Principle VII.
- Contracts under `specs/*/contracts/` that a gate reads remain live and
  are updated if this feature changes what they describe; merged
  `spec.md`/`plan.md`/`tasks.md` of earlier features are frozen records
  and are not edited.
