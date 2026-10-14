# Feature Specification: Subfolder Project Lifecycles

**Feature Branch**: `114-subfolder-project-lifecycles`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "Run the pipeline on a project in a subfolder, so one repository can hold several projects" (lifecycle issue #1020). Every stage today treats the repository root as the one project. An adopter wants one repository to hold many independent projects as folders ("nodes"), each its own Wing Commander project with its own constitution, `.specify/`, spec-kit skills, `specs/` and code, and nodes may nest inside nodes. Spec Kit already resolves the nearest enclosing `.specify/` and accepts an explicit project-root override; the gaps are on the pipeline side: preflight, spec-directory resolution and validation, feature numbering, and repository-wide names (labels, branches, concurrency groups).

## Clarifications

### Session 2026-10-14

- Q: How does an issue name its project? → A: A maintainer applies a `node:<path>` label before or together with `spec-request`; the prefix is a new optional intake input defaulting to empty (routing off). Intake reads live labels; zero = root, one = that project, two or more = refuse. Only intake reads it; later stages use the recorded identity.
- Q: Per-project or repository-wide feature numbering? → A: Per project, each starting at `001`, scanning `P/specs/` and anchored `refs/heads/<prefix>P/<NNN-slug>` refs; intake concurrency `wing-commander-intake/P`.
- Q: Namespacing scheme? → A: The validated folder path itself, unchanged, placed after the existing flat prefixes; no flattening, hashing or per-piece inputs. Paths are capped at 28 characters so `spec:` labels fit GitHub's 50-character limit; spec-meta stays project-relative and never records the path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a full lifecycle on a project in a subfolder (Priority: P1)

A maintainer of a repository that holds several projects as folders opens an issue for work on one of those projects, names the project, and applies the ordinary entry label. The pipeline carries that lifecycle through intake, clarify, plan, tasks, implement ⟲ converge, finalize and cleanup (with rebase and pr-conversation available along the way) entirely inside that folder: every stage reads the folder's own constitution, `.specify/`, spec-kit skills and `specs/`, its agents work from that folder, and the spec lands at `<project>/specs/<NNN-slug>/`.

**Why this priority**: Nothing else in this feature has value until one lifecycle can run end to end inside a subfolder. Today no lifecycle can run inside a node at all.

**Independent Test**: In a test repository with a root project and one subfolder project carrying its own Spec Kit state, open an issue routed to the subfolder project and drive it to cleanup. Verify the spec, plan, tasks and code changes all live under the subfolder, every agent read the subfolder's constitution (not the root's), and no file outside the subfolder changed except where the lifecycle's own work legitimately required it.

**Acceptance Scenarios**:

1. **Given** a repository with a project in `ideas/alpha/` carrying its own constitution, `.specify/` and spec-kit skills, **When** a maintainer applies `node:ideas/alpha` before or together with the entry label, **Then** intake creates `ideas/alpha/specs/<NNN-slug>/spec.md`, the branches `<prefix>ideas/alpha/<NNN-slug>` and the label `spec:ideas/alpha/<NNN-slug>`, and the matching `spec-meta.json` records the project-relative location `specs/<NNN-slug>`.
2. **Given** that lifecycle's spec PR has merged, **When** plan, tasks, implement, converge and finalize run, **Then** each stage locates the spec directory from the lifecycle's identity (branch, label or dispatch data) without falling back to root `specs/`, and each agent's working directory and allowed paths are the project folder.
3. **Given** a stage receives a spec directory as dispatch data, **When** that directory is a valid project-relative spec path such as `ideas/alpha/specs/003-foo`, **Then** the stage accepts it; **When** it is malformed, escapes the repository, or points outside a recognised project, **Then** the stage rejects it loudly.
4. **Given** the routed folder lacks `.specify/` or the spec-kit skills, **When** preflight runs, **Then** it fails naming the folder and what is missing, rather than silently using the root project.
5. **Given** the lifecycle finishes, **When** cleanup runs, **Then** it deletes only that lifecycle's branches and labels and leaves every other project's lifecycles untouched.

---

### User Story 2 - Two projects in one repository run lifecycles side by side without colliding (Priority: P1)

Two projects in the same repository each have their own spec history, and their numbers already overlap (for example both have a `001`–`013`). Their lifecycles run concurrently. Neither collides with the other on branch names, `spec:` labels or concurrency groups, and neither queues behind the other unless they genuinely share a resource.

**Why this priority**: The motivating adopter's planned projects already have overlapping spec numbers; a single project per repository is the only thing that works today, so isolation is required for the feature to be usable at all.

**Independent Test**: Start lifecycles in two subfolder projects that both produce `NNN-slug` values that would be identical without a project key. Verify each has distinct branches, labels and concurrency groups, both proceed in parallel, and the watchdog and fold-cycle guard attribute each run to the correct lifecycle.

**Acceptance Scenarios**:

1. **Given** projects `ideas/alpha` and `ideas/beta` each about to create spec `001-login`, **When** both intakes run, **Then** the resulting branches, `spec:` labels and concurrency groups are distinct and neither run waits on the other's per-spec group.
2. **Given** a stage run in project `ideas/alpha`, **When** the watchdog or fold-cycle guard inspects it, **Then** it resolves the run to `ideas/alpha`'s lifecycle and never to `ideas/beta`'s lifecycle with the same `NNN-slug`.
3. **Given** a project's branches were deleted by teardown, **When** a new intake allocates a number in that project, **Then** it never reissues a number already present in that project's own `specs/`.

---

### User Story 3 - Existing root-level adopters see no change (Priority: P1)

Every adopter today has a single project at the repository root. After this feature ships and they bump their pin, their lifecycles behave exactly as before: same spec paths, branch names, label names, concurrency groups and numbering, with no edits to their wrapper workflows.

**Why this priority**: The stage workflows are a published, adopter-pinned contract; a regression for root-level adopters is a breaking change to every current user.

**Independent Test**: Run this repository's own lifecycle (a root-level adopter) on the new version with unchanged wrappers and compare the branch names, labels, concurrency groups, spec path and allocated number against the pre-change behaviour.

**Acceptance Scenarios**:

1. **Given** a root-level adopter with unchanged wrappers, **When** any stage runs, **Then** spec directories remain `specs/<NNN-slug>`, branches remain `<prefix><NNN-slug>`, labels remain `spec:<NNN-slug>` and concurrency groups keep their current names.
2. **Given** a root-level adopter, **When** a `spec-meta.json` written before this feature is read by the new version, **Then** it passes the self-identity check unchanged.
3. **Given** the published stage interface, **When** this feature ships, **Then** no existing input, secret or output is removed or renamed; any new input is optional with a default that reproduces root-level behaviour.

---

### User Story 4 - A project folder graduates to its own repository by copying (Priority: P2)

A project that outgrows the shared repository is copied out into a new repository. The maintainer adds the standard root wrappers, secrets and labels, and the copy works as an ordinary root-level adopter with no edits inside the copied folder.

**Why this priority**: Self-containment is the reason for running per-folder lifecycles instead of root-level specs; it is valuable but only after Stories 1–3 work.

**Independent Test**: Copy a subfolder project that has completed at least one lifecycle into a fresh repository, add the standard wrappers, secrets and labels, and run a new lifecycle. Verify no file inside the copied folder needed editing and the new lifecycle's number continues the project's own sequence.

**Acceptance Scenarios**:

1. **Given** a subfolder project with completed specs, **When** its folder contents are copied to the root of a new repository, **Then** its `spec-meta.json` files, constitution, `.specify/` and spec-kit skills are valid there as-is.
2. **Given** that graduated repository, **When** a new intake runs, **Then** its allocated number does not collide with the specs the project brought with it.

---

### User Story 5 - Nested projects at any depth (Priority: P3)

A project folder can contain further project folders, to any depth. Each nested project is its own project: its lifecycles use its own Spec Kit state and specs, and the enclosing project's lifecycles never treat the nested project's contents as their own.

**Why this priority**: The motivating adopter nests concepts inside concepts, but single-level projects already unlock the first planned projects.

**Independent Test**: Create `a/` and `a/b/` as projects, run a lifecycle in each, and verify each reads only its own Spec Kit state, allocates from its own `specs/`, and the names derived for each are distinct from each other and from a sibling `b/` at another location.

**Acceptance Scenarios**:

1. **Given** projects at `a/` and `a/b/`, **When** a lifecycle runs in `a/b/`, **Then** it uses `a/b/`'s constitution and `.specify/`, not `a/`'s.
2. **Given** projects at `a/b/` and `c/b/`, **When** both run lifecycles, **Then** their derived names differ (the key is derived from the full path, not the last segment).

---

### Edge Cases

- An issue's `node:` label names a project folder that does not exist, or one that exists but is not a Spec Kit project: intake fails loudly on the lifecycle issue naming the folder; no branch, label or spec directory is created.
- An issue carries no `node:` label (or the adopter has not enabled routing): the lifecycle runs at the root exactly as today.
- An issue carries two or more `node:` labels: intake refuses with a callout on the lifecycle issue and creates nothing.
- A `node:` label is added, removed or changed after intake: it has no effect; every later stage reads the project from the recorded identity. Re-running intake on an issue that already has a `spec:` label refuses.
- A project path contains characters not valid in branch names, label names or concurrency group names (spaces, uppercase, a `specs` segment, a segment shaped like `NNN-`, or more than 28 characters): it is rejected, never normalised.
- A `spec:` label for the derived name would exceed GitHub's 50-character limit: intake fails loudly before any branch exists rather than truncating.
- A project path attempts traversal (`..`, absolute paths, symlinks): rejected as untrusted input before any stage uses it.
- A root project's lifecycle touches files inside a nested project's folder: the root's lifecycle treats nested project folders as out of its scope (consistent with the adopter's own constitution keeping root lifecycles out of node contents); whether the pipeline enforces this or leaves it to the adopter's constitution is decided in planning.
- Watchdog and fold-cycle guard currently read repository-wide prefix variables or defaults: they must identify a run's project without depending on any single wrapper's per-call inputs.
- A configured branch prefix containing `/` is rejected by preflight today; that check stays unchanged, because the project path is appended after the flat prefix rather than folded into it.

## Requirements *(mandatory)*

### Functional Requirements

**Project resolution**

- **FR-001**: The pipeline MUST let a lifecycle target a project that lives in a subfolder of the repository, identified by its folder path relative to the repository root, through a `node:<path>` routing label that a maintainer applies before or together with `spec-request`. Routing is controlled by a new optional intake input naming the label prefix; it defaults to empty, which turns routing off so root-level adopters are unaffected. Intake MUST read the issue's live labels through its `issue-number` input, never from the event payload or the issue body. Zero routing labels means the root project, exactly one means that project, and two or more MUST make intake refuse with a callout on the lifecycle issue and create nothing. (Only triage-or-higher users can apply labels, so routing carries the same authority as entry; an issue-form field would stay author-editable after approval, and per-project wrappers cannot split the repository-wide watchdog, cleanup, rebase and fold-cycle-guard triggers.)
- **FR-002**: The project path MUST be treated as untrusted input and validated by deterministic code, never by an agent's judgment, before any use. A valid path is one or more segments matching `^[a-z0-9][a-z0-9-]*$` joined by `/`, contains no segment equal to `specs` and no segment matching `^[0-9]{3}-`, is at most 28 characters long, and names a real directory (not a symlink, and with no symlinked ancestor) on the default branch that contains `.specify/` and `.claude/skills/speckit-*`. Any other path, including absolute paths and `..` traversal, MUST be rejected, never normalised.
- **FR-003**: Once a lifecycle's project is resolved, it MUST be recorded in the lifecycle's durable identity — its branch names, its `spec:` label and the spec directory carried as dispatch data — and every later stage, plus the watchdog and fold-cycle guard, MUST derive the project from that record, never re-infer it. Only intake reads the routing label: adding, removing or changing a `node:` label after intake has no effect, and re-running intake on an issue that already carries a `spec:` label MUST refuse. `spec-meta.json` is deliberately not part of this record (see FR-008).
- **FR-004**: Projects MUST be supported at any folder depth, and a project nested inside another project MUST be treated as a distinct project.

**Per-project Spec Kit state**

- **FR-005**: Preflight MUST check for `.specify/` and the spec-kit skills in the resolved project folder (the root when no project is named), and fail naming the folder and the missing piece when they are absent.
- **FR-006**: Every stage MUST read the constitution, `.specify/` templates and scripts, spec-kit skills and `specs/` from the resolved project folder, and its agent MUST run with that folder as its working project, including the paths in agent prompts and allowed-tools lists.
- **FR-007**: Every place that derives or validates a spec directory (stage dispatch validation, branch- or label-based reconstruction, the shared context and inspected-run-identity actions, and the shared spec-meta reader) MUST accept a project-relative spec directory of the form `<project>/specs/<NNN-slug>` and continue to accept root `specs/<NNN-slug>`, while still rejecting anything malformed.
- **FR-008**: A spec's `spec-meta.json` MUST record its spec directory project-relative (`specs/<NNN-slug>`) and MUST NOT record the project path, so that it remains valid after the project folder is copied to the root of another repository, with no edits inside the folder (Story 4).

**Feature numbering**

- **FR-009**: Feature numbers MUST be allocated per project, each project's sequence starting at `001`. For project P, the next number is 1 plus the highest `NNN` found in `P/specs/` and in branch refs that exactly match `refs/heads/<prefix>P/<NNN-slug>` for the spec-draft and spec branch prefixes (anchored full refnames, so a nested or sibling project's refs never count). The root project counts only refs whose remainder after the prefix contains no `/`. (Projects moved into a shared repository keep their existing numbers without renumbering, graduated copies continue their own sequence, and this matches Spec Kit.)
- **FR-010**: Number allocation MUST always include the target project's own `specs/` directory in its scan, so that teardown deleting a project's branches can never cause a number already present in that project to be reissued.

**Isolation and names**

- **FR-011**: Branch names, `spec:` labels and per-spec concurrency groups for a subfolder project MUST be unique across the repository, so that two projects with the same `NNN-slug` never collide on branches or labels and never serialize on each other's per-spec concurrency group. The namespacing key is the validated project path P itself, unchanged (no flattening, hashing or per-piece inputs), placed after the existing flat prefixes: branches `<prefix>P/<NNN-slug>` and `<impl-prefix>P/<NNN-slug>-iterN`, label `spec:P/<NNN-slug>`, spec directory `P/specs/<NNN-slug>`, per-spec concurrency group `wing-commander-<spec dir>`. The root project's key is empty, so every root name is unchanged. The configured branch prefixes themselves still may not contain `/` (preflight's existing check stays).
- **FR-012**: The intake concurrency group MUST serialize only the intakes that share a numbering sequence: the root project keeps `wing-commander-intake`, and project P uses `wing-commander-intake/P`, so intakes in different projects never queue behind each other.
- **FR-013**: The watchdog and fold-cycle guard MUST identify each inspected run's project and lifecycle correctly regardless of which wrapper started it, by reading the project from the branch, label or spec-directory names they already parse, without relying on a single repository-wide prefix or on defaults that ignore the project. One shared parser MUST be used everywhere: strip the prefix (or `spec:`), take the last segment as the `NNN-slug`, and the rest is P. Branch listing and deletion MUST use anchored full refnames.
- **FR-014**: Any name derived from a project path MUST be computed deterministically and MUST fail loudly rather than silently truncate or merge two projects. Because validated paths are used verbatim, distinct paths always yield distinct names and no separate collision search is needed. GitHub caps labels at 50 characters, so `spec:` + P + `/` + `NNN-slug` must fit, i.e. len(P) + len(`NNN-slug`) ≤ 44. Deterministic code, not the agent's prompt, MUST hand the intake agent its slug budget, check the result, and create the `spec:` label before any branch exists; a slug over budget fails, never truncates. Paths over 28 characters are refused (FR-002), which leaves at least 16 characters for `NNN-slug`; this caps path length, not nesting depth.
- **FR-015**: Cleanup MUST tear down only the finishing lifecycle's branches and labels within its own project's namespace.

**Compatibility**

- **FR-016**: A repository whose only project is at the root, with unchanged wrapper workflows, MUST behave exactly as it does today: same spec paths, branch names, labels, concurrency groups, numbering and spec-meta format.
- **FR-017**: Changes to the published stage interface MUST be additive only: every new input is optional, its default reproduces root-level behaviour, and no existing input, secret or output is removed or renamed.
- **FR-018**: The adoption guide MUST document how to set up a multi-project repository, including wrapper path and branch filters that select one project's changes, and MUST keep the existing root-level setup instructions valid.

**Verification**

- **FR-019**: Each new or changed validation (routing-label count, project path format, project-relative spec directory acceptance and rejection, `spec:` label length budget, the shared name parser, per-project numbering scan) MUST be covered by deterministic gates or tests with checked-in fixtures that exercise both the accept and every reject branch.
- **FR-020**: A gate MUST fail if a stage reintroduces a hard-coded root-only spec-directory pattern, root-only `.specify/` or constitution path, or root-only `specs/` scan where the project-aware form is required.

### Key Entities

- **Project (node)**: A folder in the repository (possibly the root, possibly nested) that holds its own constitution, `.specify/`, spec-kit skills and `specs/`. Identified by its path relative to the repository root; the root project has the empty path.
- **Routing label**: A `node:<path>` label (prefix set by an optional intake input, routing off by default) applied by a maintainer before or with `spec-request`; read only by intake.
- **Project key**: The validated project path itself, used verbatim after the existing flat prefixes to namespace repository-wide names (branches, labels, concurrency groups). Empty for the root project, so root names are unchanged.
- **Lifecycle identity**: The tuple (project, `NNN-slug`) that uniquely identifies a lifecycle across the repository, recorded durably in its branch names, `spec:` label and dispatched spec directory, and read by every stage, the watchdog and the fold-cycle guard through one shared parser.
- **Spec directory**: `<project>/specs/<NNN-slug>/` for a subfolder project, `specs/<NNN-slug>/` for the root project.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A lifecycle routed to a subfolder project completes every stage from intake to cleanup with 100% of its spec artifacts and agent-authored file changes inside that project's folder.
- **SC-002**: Two projects in one repository that each create a spec with the same `NNN-slug` produce 0 shared branch names, 0 shared `spec:` labels and 0 shared per-spec concurrency groups, and their lifecycles run concurrently.
- **SC-003**: This repository's own lifecycles (a root-level adopter), with unchanged wrappers, produce identical spec paths, branch names, labels, concurrency groups and number allocation before and after the change.
- **SC-004**: A subfolder project copied to the root of a fresh repository runs a new lifecycle after only adding root wrappers, secrets and labels, with 0 files edited inside the copied folder.
- **SC-005**: Projects nested at least three levels deep each run a lifecycle that reads only their own constitution and Spec Kit state.
- **SC-006**: Every new validation's reject branches are exercised by checked-in fixtures, and the local gate suite passes on the change.

## Assumptions

- The adopting repository is a single GitHub repository; GitHub reads workflows only from the root `.github/workflows/`, so every project's wrappers (however routing works) live side by side there.
- Spec Kit's own nearest-`.specify/` resolution and explicit project-root override (present in the pinned version) are sufficient on the Spec Kit side; no change to vendored Spec Kit files is needed.
- Secrets, the GitHub App, repository variables such as kill switches and auto-merge settings, and the issue board remain repository-wide; per-project settings beyond what routing and namespacing need are out of scope.
- The lifecycle issue, the `spec-request` entry label and the maintainer authorization rules (Principle V) stay unchanged; routing adds a project designation, not a new authorization path.
- Nesting depth is unbounded, per the issue; the only limit is the 28-character path cap that keeps `spec:` labels within GitHub's 50-character limit (FR-002, FR-014), which caps path length, not depth.
- Enforcing that a root project's lifecycles stay out of nested projects' contents is left to each adopter's own constitution unless planning finds a cheap deterministic guard.
- This repository's constitution states spec artifacts live in `specs/<NNN-slug>/` (Operational Constraints) and Principle VI lists root paths for project artifacts; supporting project-relative paths is expected to need a constitution amendment (PATCH or MINOR), which is a human-merged change and is noted here for the plan stage.
- Moving existing adopters' projects into a shared repository, and migrating their issue/label history, is out of scope; this feature makes it possible, it does not perform it.
