# Feature Specification: Subfolder Project Lifecycles

**Feature Branch**: `114-subfolder-project-lifecycles`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "Run the pipeline on a project in a subfolder, so one repository can hold several projects" (lifecycle issue #1020). Every stage today treats the repository root as the one project. An adopter wants one repository to hold many independent projects as folders ("nodes"), each its own Wing Commander project with its own constitution, `.specify/`, spec-kit skills, `specs/` and code, and nodes may nest inside nodes. Spec Kit already resolves the nearest enclosing `.specify/` and accepts an explicit project-root override; the gaps are on the pipeline side: preflight, spec-directory resolution and validation, feature numbering, and repository-wide names (labels, branches, concurrency groups).

**Layer**: This spec describes both Principle VII layers. The **published contract** (the stage workflows and the composite actions under `.github/actions/**`) gains project-aware resolution, validation, numbering and naming, plus one new optional intake input (the routing-label prefix). That input is a deliberate, optional widening of the published contract; its empty default reproduces today's behaviour. The **consuming instrument** (this repository's own wrappers, labels and constitution) changes only through the constitution amendment (FR-024) and needs no wrapper edits, because this repository stays a root-level adopter with routing off.

## Clarifications

### Session 2026-10-14

- Q: How does an issue name its project? → A: A maintainer applies a `node:<path>` label before or together with `spec-request`; the prefix is a new optional intake input defaulting to empty (routing off). Intake reads live labels; zero = root, one = that project, two or more = refuse. Only intake reads it; later stages use the recorded identity.
- Q: Per-project or repository-wide feature numbering? → A: Per project, each starting at `001`, scanning `P/specs/` and anchored `refs/heads/<prefix>P/<NNN-slug>` refs; intake concurrency `wing-commander-intake/P`.
- Q: Namespacing scheme? → A: The validated folder path itself, unchanged, placed after the existing flat prefixes; no flattening, hashing or per-piece inputs. Paths are capped at 28 characters so `spec:` labels fit GitHub's 50-character limit; spec-meta records the project-relative spec directory and never the project path.

### Spec review of #1021 (2026-10-14)

The three answers above stand. The owner's review settled four follow-on decisions:

- Q: Do the intake re-run refusal, label-first creation and slug-budget check apply to root adopters? → A: No. They apply only when the routing prefix is set; with routing off, intake behaves exactly as today. FR-016 and SC-003 stay unconditional.
- Q: How far does a subfolder lifecycle's write scope reach? → A: Agent-authored changes are confined to `P`, with no "where legitimately required" exception. Whether deterministic code or the deny list enforces it is a plan decision; any guard must still allow whole-folder operations and parent-index edits, which some adopters' constitutions permit.
- Q: Which Spec Kit pin does preflight check? → A: Preflight's version-drift warning reads the resolved project's `.specify/init-options.json`. Having auto-update-spec-kit regenerate per-project copies is out of scope.
- Q: What does spec-meta's `spec_branch` record? → A: The real branch name, kept as a historical pointer. FR-008's no-`P` rule governs `spec_dir`, which is the identity field. No check may require `spec_branch` to resolve after teardown or graduation.

### Spec review round 2 (2026-10-14)

The earlier decisions stand. The owner's second review added:

- Q: How do agents reach the trusted pipeline checkout when their working directory is `P`? → A: Every agent-facing reference resolves to the workspace-root checkout, never inside `P`; a branch tracking `.wing-commander-pipeline/` at any depth is refused (FR-025).
- Q: Does the 50-character label check apply to root lifecycles? → A: No; only with routing on and a subfolder target (Edge Cases, FR-014).
- Q: How far do FR-021's allowances and FR-022's denies reach? → A: Both allowances are inside `P` only. FR-022 applies to subfolder lifecycles, binds every lifecycle agent that holds Edit/Write (on main: intake, clarify, plan, tasks, implement, rebase, finalize, cleanup, and pr-conversation's act and act.fold agents, all already under Principle V's `.claude/` rule), and also covers every enclosing project's `.claude/` between the root and `P`.
- Q: Is the re-run refusal race-safe? → A: Yes; routed intakes serialize per issue as well as per numbering sequence (FR-012).
- Q: What happens with routing on and no `node:` label? → A: The root lifecycle with today's names, groups and numbering, but the re-run refusal and prefix validation still apply.
- Q: Which restart inputs take which form? → A: Plan and tasks restarts take `slug` = `P/<NNN-slug>`; implement, finalize and fold-cycle-guard restarts and hand-offs take `spec_dir` = `P/specs/<NNN-slug>` (FR-018(d)).
- Further wording: FR-013, FR-019 (more fixtures, non-exhaustive), FR-020 (root-resolved skill paths), FR-023 (which prefix sources intake can check) and FR-024 (term usage).

### Spec review round 3 (2026-10-14)

The earlier decisions stand, with round 2's FR-022 agent list corrected (above). The owner's third review added:

- Q: Which agents does FR-022 bind? → A: Every lifecycle agent that holds `Edit`/`Write`; the examples are those on main: intake, clarify, plan, tasks, implement, rebase, finalize, cleanup, and pr-conversation's act and act.fold agents. How each gets the deny stays a plan decision.
- Q: Does FR-021 forbid the runner-temp files stages already write? → A: No. It forbids *repository* writes outside `P`; job-scoped runner-temp files outside the checkout stay permitted.
- Q: Does a routing-on, root-targeted intake keep today's concurrency groups exactly? → A: All but one: FR-012's per-issue intake serialization also applies, because the race it closes includes a root-targeted intake (Edge Cases, Story 2 AS-5).
- Q: What shape must the routing prefix have, and what may it not overlap? → A: Lowercase segment characters ending in exactly one `:`; the overlap check also covers the `board:` and `disposition:` families and the entry labels `spec-request` and `spec-proposal` (a prefix `spec-` would capture `spec-request`), with FR-019 reject fixtures (FR-023).
- Q: Must a project already have `specs/`? → A: No; the Project entity says `specs/` (when present), matching FR-002, since a new project's first lifecycle has none.
- Q: Where does repository-level tooling named in grants resolve under working directory `P`? → A: To the workspace root, the same as the trusted pipeline checkout, whether named in default or adopter-supplied grants (FR-025); the adoption guide notes it for `extra-allowed-tools` (FR-018).

## Terms

- **Repository-relative spec directory**: `P/specs/<NNN-slug>` (just `specs/<NNN-slug>` for the root project). Used in dispatch data, concurrency groups and metrics.
- **Project-relative spec directory**: `specs/<NNN-slug>`. Used in `spec-meta.json` and in every path handed to Spec Kit or to an agent working inside `P`.

For the root project, the two forms are the same.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a full lifecycle on a project in a subfolder (Priority: P1)

A maintainer of a repository that holds several projects as folders opens an issue for work on one of those projects, names the project, and applies the ordinary entry label. The pipeline carries that lifecycle through intake, clarify, plan, tasks, implement ⟲ converge, finalize and cleanup (with rebase and pr-conversation available along the way) entirely inside that folder: every stage reads the folder's own constitution, `.specify/`, spec-kit skills and `specs/`, its agents work from that folder, and the spec lands at `<project>/specs/<NNN-slug>/`.

**Why this priority**: Nothing else in this feature has value until one lifecycle can run end to end inside a subfolder. Today no lifecycle can run inside a node at all.

**Independent Test**: In a test repository with a root project and one subfolder project carrying its own Spec Kit state, open an issue routed to the subfolder project and drive it to cleanup. Verify the spec, plan, tasks and code changes all live under the subfolder, every agent read the subfolder's constitution (not the root's), and no agent-authored change touched any file outside the subfolder.

**Acceptance Scenarios**:

1. **Given** a repository with a project in `ideas/alpha/` carrying its own constitution, `.specify/` and spec-kit skills, and intake's routing prefix set to `node:`, **When** a maintainer applies `node:ideas/alpha` before or together with the entry label, **Then** intake creates `ideas/alpha/specs/<NNN-slug>/spec.md`, the spec-draft branch `<spec-draft-prefix>ideas/alpha/<NNN-slug>` and the label `spec:ideas/alpha/<NNN-slug>`, and the matching `spec-meta.json` records the project-relative spec directory `specs/<NNN-slug>`.
2. **Given** that lifecycle's spec PR has merged, **When** plan, tasks, implement, converge and finalize run, **Then** each stage locates the spec directory from the lifecycle's identity (branch, label or dispatch data) without falling back to root `specs/`, each agent's working directory is the project folder, and every agent-authored change lies inside the project folder.
3. **Given** a stage receives a spec directory as dispatch data, **When** that directory is a valid repository-relative spec directory such as `ideas/alpha/specs/003-foo`, **Then** the stage accepts it; **When** it is malformed, escapes the repository, or points outside a recognised project, **Then** the stage rejects it loudly.
4. **Given** the routed folder lacks `.specify/` or the spec-kit skills, **When** preflight runs, **Then** it fails naming the folder and what is missing, rather than silently using the root project.
5. **Given** the lifecycle finishes, **When** cleanup runs, **Then** it deletes only that lifecycle's branches and labels and leaves every other project's lifecycles untouched.
6. **Given** `ideas/alpha/specs/003-foo/spec-meta.json`, **When** the self-identity check reads it, **Then** it passes if the record's spec directory is exactly `specs/003-foo` and fails if the record carries any project path (for example `ideas/alpha/specs/003-foo`).

---

### User Story 2 - Two projects in one repository run lifecycles side by side without colliding (Priority: P1)

Two projects in the same repository each have their own spec history, and their numbers already overlap (for example both have a `001`–`013`). Their lifecycles run concurrently. Neither collides with the other on branch names, `spec:` labels or concurrency groups, and neither queues behind the other unless they genuinely share a resource.

**Why this priority**: The motivating adopter's planned projects already have overlapping spec numbers; a single project per repository is the only thing that works today, so isolation is required for the feature to be usable at all.

**Independent Test**: Start lifecycles in two subfolder projects that both produce `NNN-slug` values that would be identical without a project path. Verify each has distinct branches, labels and concurrency groups, both proceed in parallel, and the watchdog and fold-cycle guard attribute each run to the correct lifecycle.

**Acceptance Scenarios**:

1. **Given** projects `ideas/alpha` and `ideas/beta` each about to create spec `001-login`, **When** both intakes run, **Then** the resulting branches, `spec:` labels and concurrency groups are distinct and neither run waits on the other's per-spec group.
2. **Given** a stage run in project `ideas/alpha`, **When** the watchdog or fold-cycle guard inspects it, **Then** it resolves the run to `ideas/alpha`'s lifecycle and never to `ideas/beta`'s lifecycle with the same `NNN-slug`.
3. **Given** a project's branches were deleted by teardown, **When** a new intake allocates a number in that project, **Then** it never reissues a number already present in that project's own `specs/`.
4. **Given** `ideas/alpha` and `ideas/beta` both have a spec numbered `004`, **When** the watchdog's spec-collision check (or any other spec-number uniqueness check) inspects a run in `ideas/alpha`, **Then** it does not flag the `004` in `ideas/beta`.
5. **Given** routing is on, the wrappers are set up as FR-018 describes, and a root lifecycle and a subfolder lifecycle with the same `NNN-slug` run concurrently, **When** both run to cleanup, **Then** the root lifecycle's branch names, labels, concurrency groups (apart from FR-012's per-issue intake serialization) and numbering match today's, and neither lifecycle's cleanup touches the other's refs or labels.

---

### User Story 3 - Existing root-level adopters see no change (Priority: P1)

Every adopter today has a single project at the repository root. After this feature ships and they bump their pin, their lifecycles behave exactly as before: same spec paths, branch names, label names, concurrency groups and numbering, with no edits to their wrapper workflows.

**Why this priority**: The stage workflows are a published, adopter-pinned contract; a regression for root-level adopters is a breaking change to every current user.

**Independent Test**: Run this repository's own lifecycle (a root-level adopter) on the new version with unchanged wrappers and compare the branch names, labels, concurrency groups, spec path and allocated number against the pre-change behaviour.

**Acceptance Scenarios**:

1. **Given** a root-level adopter with unchanged wrappers, **When** any stage runs, **Then** spec directories remain `specs/<NNN-slug>`, branches remain `<prefix><NNN-slug>`, labels remain `spec:<NNN-slug>` and concurrency groups keep their current names.
2. **Given** a root-level adopter, **When** a `spec-meta.json` written before this feature is read by the new version, **Then** it passes the self-identity check unchanged.
3. **Given** the published stage interface, **When** this feature ships, **Then** no existing input, secret or output is removed or renamed; any new input is optional with a default that reproduces root-level behaviour.
4. **Given** a root-level adopter with routing off, **When** intake runs (including a re-run on an issue that already has a `spec:` label), **Then** it behaves exactly as today: no re-run refusal, no label-first creation and no new slug-budget check.

---

### User Story 4 - A project folder graduates to its own repository by copying (Priority: P2)

A project that outgrows the shared repository is copied out into a new repository. The maintainer adds the standard root wrappers, secrets and labels, and the copy works as an ordinary root-level adopter with no edits inside the copied folder.

**Why this priority**: Self-containment is the reason for running per-folder lifecycles instead of root-level specs; it is valuable but only after Stories 1–3 work.

**Independent Test**: Copy a subfolder project that has completed at least one lifecycle into a fresh repository, add the standard wrappers, secrets and labels, and run a new lifecycle. Verify no file inside the copied folder needed editing and the new lifecycle's number continues the project's own sequence.

**Acceptance Scenarios**:

1. **Given** a subfolder project with completed specs, **When** its folder contents are copied to the root of a new repository, **Then** its `spec-meta.json` files, constitution, `.specify/` and spec-kit skills are valid there as-is.
2. **Given** that graduated repository, **When** a new intake runs, **Then** its allocated number does not collide with the specs the project brought with it.
3. **Given** the `spec-meta.json` files that passed the self-identity check inside `P` (User Story 1, scenario 6), **When** they are copied to the root of the new repository, **Then** the same files pass the check there unchanged, even though their `spec_branch` no longer resolves.

---

### User Story 5 - Nested projects at any depth (Priority: P3)

A project folder can contain further project folders, to any depth within the 28-character path cap. Each nested project is its own project: its lifecycles use its own Spec Kit state and specs, and the enclosing project's lifecycles never treat the nested project's contents as their own.

**Why this priority**: The motivating adopter nests concepts inside concepts, but single-level projects already unlock the first planned projects.

**Independent Test**: Create `a/` and `a/b/` as projects, run a lifecycle in each, and verify each reads only its own Spec Kit state, allocates from its own `specs/`, and the names for each are distinct from each other and from a sibling `b/` at another location.

**Acceptance Scenarios**:

1. **Given** projects at `a/` and `a/b/`, **When** a lifecycle runs in `a/b/`, **Then** it uses `a/b/`'s constitution and `.specify/`, not `a/`'s.
2. **Given** projects at `a/b/` and `c/b/`, **When** both run lifecycles, **Then** their names differ, because the full project path is used verbatim, not the last segment.

---

### Edge Cases

- An issue's `node:` label names a project folder that does not exist, or one that exists but is not a Spec Kit project: intake fails loudly on the lifecycle issue naming the folder; no branch, label or spec directory is created.
- The adopter has not enabled routing (the routing prefix is empty): the lifecycle runs at the root exactly as today.
- Routing is on but the issue carries no `node:` label: the lifecycle targets the root project with today's names, concurrency groups and numbering, but FR-003's re-run refusal, FR-012's per-issue intake serialization and FR-023's prefix validation still apply.
- An issue carries two or more `node:` labels: intake refuses with a callout on the lifecycle issue and creates nothing.
- A `node:` label is added, removed or changed after intake: it has no effect; every later stage reads the project from the recorded identity. With routing on, re-running intake on an issue that already has a `spec:` label refuses; with routing off, intake behaves as today.
- A project path that fails FR-002's grammar (spaces, uppercase, a `specs` segment, a segment shaped like `NNN-`, or more than 28 characters) is rejected, never normalised.
- With the routing prefix set and the lifecycle targeting a subfolder project, a `spec:` label for the lifecycle would exceed GitHub's 50-character limit: intake fails loudly before any branch exists rather than truncating (FR-014). Root lifecycles keep today's behaviour (FR-016).
- A branch tracks a `.wing-commander-pipeline/` directory at any depth (for example `P/.wing-commander-pipeline/…`): it is refused, so no planted copy can shadow the trusted pipeline checkout (FR-025).
- A project path attempts traversal (`..`, absolute paths, symlinks): rejected as untrusted input before any stage uses it.
- A project's `.specify/`, `.claude/`, `specs/` or constitution is a symlink rather than a real entry inside the folder: the project is rejected (FR-002, FR-005).
- The recorded project folder no longer exists, or is no longer a Spec Kit project, on the ref a stage works from (for example after the folder was moved or renamed mid-lifecycle): the stage fails loudly naming the folder and never writes to the stale path. Numbering does not reconcile refs recorded under a former path.
- A root project's or enclosing project's lifecycle touches files inside a nested project's folder: nested projects' *contents* are out of the enclosing lifecycle's scope. The adopter's constitution defines that boundary (some permit whole-folder operations or parent-index edits). Whether the pipeline enforces it or leaves it to the adopter's constitution is decided in planning.
- Watchdog and fold-cycle guard currently read repository-wide prefix variables or defaults: they must identify a run's project without assuming it is encoded in a prefix, without depending on any single wrapper's per-call inputs, and without defaults that ignore the project (FR-013).
- Preflight requires each configured branch prefix to be a single segment ending in exactly one `/` (for example `spec-draft/`). That check stays unchanged, because the project path is appended after the prefix rather than folded into it.

## Requirements *(mandatory)*

### Functional Requirements

**Project resolution**

- **FR-001**: The pipeline MUST let a lifecycle target a project that lives in a subfolder of the repository, identified by its folder path relative to the repository root, through a `node:<path>` routing label that a maintainer applies before or together with `spec-request`. Routing is controlled by a new optional intake input naming the label prefix; it defaults to empty, which turns routing off so root-level adopters are unaffected. Intake MUST read the issue's live labels through its `issue-number` input, never from the event payload or the issue body. Zero routing labels means the root project, exactly one means that project, and two or more MUST make intake refuse with a callout on the lifecycle issue and create nothing. (Only triage-or-higher users can apply labels, so routing carries the same authority as entry; an issue-form field would stay author-editable after approval, and per-project wrappers cannot split the repository-wide watchdog, cleanup, rebase and fold-cycle-guard triggers.)
- **FR-002**: The project path MUST be treated as untrusted input and validated by deterministic code, never by an agent's judgment, before any use. A valid path is one or more segments matching `^[a-z0-9][a-z0-9-]*$` joined by `/`, contains no segment equal to `specs` and no segment matching `^[0-9]{3}-`, is at most 28 characters long, and names a real directory (not a symlink, and with no symlinked ancestor) on the default branch. That directory's `.specify/`, `.claude/` (including the `.claude/skills/speckit-*` skills), `specs/` (when present) and constitution MUST be real entries inside it, not symlinks. Any other path, including absolute paths and `..` traversal, MUST be rejected, never normalised.
- **FR-003**: Once a lifecycle's project is resolved, it MUST be recorded in the lifecycle's durable identity — its branch names, its `spec:` label and the repository-relative spec directory carried as dispatch data — and every later stage, plus the watchdog and fold-cycle guard, MUST derive the project from that record, never re-infer it. Every slug-shaped carrier MUST take the project-qualified form `P/<NNN-slug>` and be parsed by the shared parser (FR-013): this includes the plan→tasks `slug` hand-off and the plan and tasks manual-restart `slug` inputs. Root values stay `<NNN-slug>`, unchanged. Only intake reads the routing label: adding, removing or changing a `node:` label after intake has no effect. When the routing prefix is set, re-running intake on an issue that already carries a `spec:` label MUST refuse, whether or not the issue carries a `node:` label, and the refusal MUST be race-safe (FR-012); with routing off, intake behaves exactly as today. `spec-meta.json` is deliberately not part of this record (see FR-008).
- **FR-004**: Projects MUST be supported at any folder depth within the 28-character path cap (FR-002), and a project nested inside another project MUST be treated as a distinct project.

**Per-project Spec Kit state**

- **FR-005**: Preflight MUST check for `.specify/` and the spec-kit skills in the resolved project folder (the root when no project is named), and fail naming the folder and the missing piece when they are absent or are symlinks rather than real entries inside the folder (FR-002). Preflight's Spec Kit version-drift warning MUST read the resolved project's `.specify/init-options.json`.
- **FR-006**: Every stage MUST read the constitution, `.specify/` templates and scripts, spec-kit skills and `specs/` from the resolved project folder, and its agent MUST run with that folder as its working project, including the paths in agent prompts and allowed-tools lists. Paths handed to Spec Kit or to the agent inside `P` are project-relative.
- **FR-007**: Every place that derives, validates or classifies a spec directory (stage dispatch validation, branch- or label-based reconstruction, the shared context and inspected-run-identity actions, the shared spec-meta reader, and the deterministic code that classifies a changed file path as a spec document or a contract) MUST accept a repository-relative spec directory of the form `P/specs/<NNN-slug>` and continue to accept root `specs/<NNN-slug>`, while still rejecting anything malformed.
- **FR-008**: A spec's `spec-meta.json` MUST record its `spec_dir` project-relative (`specs/<NNN-slug>`) and MUST NOT record the project path in it, so that it remains valid after the project folder is copied to the root of another repository, with no edits inside the folder (Story 4). The self-identity check MUST pass `P/specs/<NNN-slug>/spec-meta.json` only when its `spec_dir` is exactly `specs/<NNN-slug>`, and MUST fail a record whose `spec_dir` carries any project path. `spec_branch` keeps the real branch name (which includes `P` for a subfolder project) as a historical pointer; no check may require `spec_branch` to resolve after teardown or graduation.

**Feature numbering**

- **FR-009**: Feature numbers MUST be allocated per project, each project's sequence starting at `001`. For project P, the next number is 1 plus the highest `NNN` found in `P/specs/` and in branch refs that exactly match `refs/heads/<prefix>P/<NNN-slug>` for the spec-draft and spec branch prefixes (anchored full refnames, so a nested or sibling project's refs never count). The root project counts only refs whose remainder after the prefix contains no `/`. Numbering does not reconcile refs recorded under a project's former path. (Projects moved into a shared repository keep their existing numbers without renumbering, graduated copies continue their own sequence, and this matches Spec Kit.)
- **FR-010**: Number allocation MUST always include the target project's own `specs/` directory in its scan, so that teardown deleting a project's branches can never cause a number already present in that project to be reissued.

**Isolation and names**

- **FR-011**: Branch names, `spec:` labels and per-spec concurrency groups for a subfolder project MUST be unique across the repository, so that two projects with the same `NNN-slug` never collide on branches or labels and never serialize on each other's per-spec concurrency group. The namespacing key is the validated project path P itself, used verbatim (no flattening, hashing or per-piece inputs), placed after the existing flat prefixes: branches `<prefix>P/<NNN-slug>` and `<impl-prefix>P/<NNN-slug>-iterN`, label `spec:P/<NNN-slug>`, repository-relative spec directory `P/specs/<NNN-slug>`, per-spec concurrency group `wing-commander-<repository-relative spec dir>`. The root project's path is empty, so every root name is unchanged. Preflight's existing prefix rule (each prefix is a single segment ending in exactly one `/`) stays.
- **FR-012**: The intake concurrency group MUST serialize only the intakes that share a numbering sequence: the root project keeps `wing-commander-intake`, and project P uses `wing-commander-intake/P`, so intakes in different projects never queue behind each other. When the routing prefix is set, intakes MUST additionally serialize per lifecycle issue, alongside the per-project numbering group, so that two intakes for the same issue routed to different projects (and so sitting in different numbering groups) cannot both pass FR-003's re-run refusal.
- **FR-013**: The watchdog and fold-cycle guard MUST identify each inspected run's project and lifecycle correctly regardless of which wrapper started it, by reading the project from the branch, label, slug or spec-directory names they already parse. The project MUST NOT be assumed to be encoded in a prefix, its identification MUST NOT depend on any single wrapper's per-call inputs, and it MUST NOT use defaults that ignore the project. One shared parser MUST be used everywhere and MUST cover each name type; its first step stays stripping the repository-wide flat prefixes: strip the branch prefix (or `spec:`), strip a trailing `-iterN` from implement branches, take the last segment as the `NNN-slug`, and the rest is P; for a project-qualified slug (`P/<NNN-slug>`) and a repository-relative spec directory (`P/specs/<NNN-slug>`) it yields the same (P, `NNN-slug`). Branch listing and deletion MUST use anchored full refnames.
- **FR-014**: Any name built from a project path MUST be computed deterministically and MUST fail loudly rather than silently truncate or merge two projects. Because validated paths are used verbatim, distinct paths always yield distinct names and no separate collision search is needed. GitHub caps labels at 50 characters, so `spec:` + P + `/` + `NNN-slug` must fit: for a subfolder project, len(`NNN-slug`) ≤ 44 − len(P). When the routing prefix is set and the lifecycle targets a subfolder project, deterministic code, not the agent's prompt, MUST hand the intake agent its slug budget, check the result, and create the `spec:` label before any branch exists; a slug over budget fails, never truncates. The root project keeps today's behaviour (FR-016). Paths over 28 characters are refused (FR-002), which leaves at least 16 characters for `NNN-slug`; this caps path length, not nesting depth.
- **FR-015**: Cleanup MUST tear down only the finishing lifecycle's branches and labels within its own project's namespace.

**Containment**

- **FR-021**: A subfolder lifecycle's agent-authored changes MUST be confined to its project folder `P`. Planning decides whether deterministic code or the deny list enforces this; any guard MUST still allow, inside `P`, whole-folder operations on nested project folders and edits to a child-project index in a README inside `P`, where the adopter's constitution permits them; no repository write outside `P` is allowed. The job-scoped runner-temp files that stages already write outside the checkout stay permitted.
- **FR-022**: For a subfolder lifecycle in project P, every lifecycle agent that holds `Edit`/`Write` (for example intake, clarify, plan, tasks, implement, rebase, finalize, cleanup, and pr-conversation's act and act.fold agents, all already covered by Principle V's `.claude/` rule) MUST have `Edit`/`Write` denies covering the root `.claude/`, the repository `.git/`, the `.claude/` of every enclosing project between the root and `P` (for `P` = `a/b`, also `a/.claude/`), `P/.claude/` and the `.claude/` of every project nested inside `P`, whatever the agent's working directory. This MUST hold under the default `no-write-paths` and under any override, and the denies MUST still come from the single no-write-paths definition (spec 090). How the deny reaches each agent is a plan decision. Root lifecycles keep today's semantics (FR-016).
- **FR-023**: When the routing prefix is set, deterministic code MUST validate it before use: it has the shape of a label prefix such as `node:`, that is, lowercase segment characters ending in exactly one `:`; it does not overlap any pipeline label family (`spec:`, `stage:`, `model:`, `board:`, `disposition:`, the findings family and the write-boundary family) or the entry labels (`spec-request`, `spec-proposal`), so for example a prefix `spec-` is rejected because it would capture `spec-request`; and it is short enough that the prefix plus a 28-character path fits GitHub's 50-character label limit. Because intake cannot see another stage's inputs, it checks the findings family against its own `findings-label-prefix` input and the write-boundary family against the pipeline default `route-out-of-boundary`. An invalid prefix MUST fail intake loudly.
- **FR-025**: Every agent-facing reference to the trusted pipeline checkout (`.wing-commander-pipeline/`) — tool grants, prompt text and script invocations, such as read-only agents' grant for `.wing-commander-pipeline/.github/scripts/git_read.py` — MUST resolve to the workspace-root checkout whatever the agent's working directory, and never to a path inside `P`, where any branch could commit a planted copy. Repository-level tooling named in default or adopter-supplied grants, such as `.github/scripts/run-local-gates.py`, MUST likewise resolve to the workspace root under working directory `P`. A branch that tracks a `.wing-commander-pipeline/` directory at any depth MUST be refused, not only at the repository root.

**Compatibility**

- **FR-016**: A repository whose only project is at the root, with unchanged wrapper workflows, MUST behave exactly as it does today: same spec paths, branch names, labels, concurrency groups, numbering and spec-meta format. This holds unconditionally; with routing off, intake adds no re-run refusal, label-first creation or slug-budget check (FR-003, FR-014).
- **FR-017**: Changes to the published stage interface MUST be additive only: every new input is optional, its default reproduces root-level behaviour, and no existing input, secret or output is removed or renamed.
- **FR-018**: A multi-project repository MUST keep one shared set of wrapper workflows. The adoption guide MUST document how to set it up: (a) setting the intake routing-prefix input; (b) widening the plan wrapper's path filter, and the tasks wrapper's path filter in `pr` review mode, to match every project's `specs/` at any depth, because otherwise a subfolder spec PR's merge never starts plan; (c) creating one `node:<path>` label per project; (d) passing the project-qualified forms to manual restarts and hand-offs: plan and tasks restarts take `slug` = `P/<NNN-slug>`, while implement, finalize and fold-cycle-guard restarts and hand-offs take the repository-relative `spec_dir` = `P/specs/<NNN-slug>`. It MUST also mention that agent instruction files from enclosing projects may reach a subfolder agent (see Assumptions), note that repository-level paths in adopter-supplied `extra-allowed-tools` resolve to the workspace root, not to `P` (FR-025), and MUST keep the existing root-level setup instructions valid.
- **FR-024**: This repository's constitution MUST be amended so it no longer forbids lifecycles in project subfolders (repository-relative spec directories of the form `P/specs/<NNN-slug>`). The amendment changes these clauses: Principle VI's artifact path list (constitution, `.specify/`, `.claude/skills/speckit-*` and `specs/` resolve relative to the lifecycle's project folder, the root by default); Principle V's `.claude/` write-deny scope, to cover the `.claude/` directories FR-022 names for a subfolder lifecycle (the root's, every enclosing project's between the root and `P`, `P`'s own and every nested project's inside `P`); and the Operational Constraints bullets for spec paths (`[<P>/]specs/<NNN-slug>/`) and branch conventions (`<prefix>[<P>/]<NNN-slug>`, `<impl-prefix>[<P>/]<NNN-slug>-iterN`). It is one MINOR amendment (2.4.0 → 2.5.0), with its Sync Impact Report moved to the top of `constitution-history.md` in the same commit. A human merges it (Principles V and X): it MUST NOT reach `main` through the lifecycle pull request merge, and it MUST reach `main` no later than the lifecycle pull request. Planning decides how (modelled on spec 110 FR-003).

**Verification**

- **FR-019**: Each new or changed validation MUST be covered by deterministic gates or tests with checked-in fixtures that exercise both the accept and every reject branch. The validations include, and are not limited to: the routing-label count; the routing prefix (FR-023), with reject fixtures for a malformed shape and for overlap with each listed family and entry label (including `spec-`); the project path format and the real-entry (no symlink) rule (FR-002, FR-005); acceptance and rejection of repository-relative spec directories; the spec-meta self-identity rule, including the same files after copy-out (FR-008); the `spec:` label length budget; the shared name parser for every name type; the per-project numbering scan; the `.claude/` and `.git/` write denies for subfolder, enclosing and nested projects (FR-022), including a fixture where, with `P` = `a/b`, a write to `a/.claude/` is denied; project-scoped spec-number collision checks; the re-run refusal as a pair (routing on refuses, routing off unchanged) plus a test with two concurrent intakes for the same issue routed to different projects, of which only one proceeds (FR-003, FR-012); the stale-folder failure, when the recorded folder is missing or is no longer a Spec Kit project on the working ref; and the trusted-checkout containment (FR-025), with a fixture showing a read-only agent's grant still naming the workspace-root `.wing-commander-pipeline/` copy under working directory `P`, and a reject fixture for a branch tracking `P/.wing-commander-pipeline/…`; and the same workspace-root resolution for repository-level tooling in grants. Any spec-number collision or uniqueness check, today the watchdog's spec-collision collector, MUST be scoped to the inspected lifecycle's project, so the same `NNN` in another project is never flagged.
- **FR-020**: A gate MUST fail if a stage workflow or a composite action under `.github/actions/**` (including `_shared/`) reintroduces a hard-coded root-only spec-directory pattern, root-only `.specify/` or constitution path, root-only `specs/` scan, or root-resolved spec-kit skill path (`.claude/skills/speckit-*` in deterministic checks such as preflight) where the project-aware form is required. Each rejected pattern, including the root-resolved skill path, MUST have a checked-in fixture.

### Key Entities

- **Project (node)**: A folder in the repository (possibly the root, possibly nested) that holds its own constitution, `.specify/`, spec-kit skills and `specs/` (when present; a new project's first lifecycle has none yet) as real entries. Identified by its path relative to the repository root; the root project has the empty path.
- **Routing label**: A `node:<path>` label (prefix set by an optional, validated intake input, routing off by default) applied by a maintainer before or with `spec-request`; read only by intake.
- **Project path (used verbatim)**: The validated project path itself, used unchanged after the existing flat prefixes to namespace repository-wide names (branches, labels, concurrency groups) and in project-qualified slugs. Empty for the root project, so root names are unchanged.
- **Lifecycle identity**: The tuple (project, `NNN-slug`) that uniquely identifies a lifecycle across the repository, recorded durably in its branch names, `spec:` label, repository-relative dispatched spec directory and project-qualified slug carriers (`P/<NNN-slug>`: the plan→tasks hand-off and the plan and tasks manual-restart inputs; implement, finalize and fold-cycle-guard restarts and hand-offs carry the repository-relative spec directory, FR-018(d)), and read by every stage, the watchdog and the fold-cycle guard through one shared parser.
- **Spec directory**: Repository-relative `P/specs/<NNN-slug>/` (`specs/<NNN-slug>/` for the root project) in dispatch data, concurrency groups and metrics; project-relative `specs/<NNN-slug>/` in `spec-meta.json` and in paths handed to Spec Kit or the agent inside `P`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A lifecycle routed to a subfolder project completes every stage from intake to cleanup with 100% of its spec artifacts and agent-authored file changes inside that project's folder.
- **SC-002**: Two projects in one repository that each create a spec with the same `NNN-slug` produce 0 shared branch names, 0 shared `spec:` labels and 0 shared per-spec concurrency groups, and their lifecycles run concurrently.
- **SC-003**: This repository's own lifecycles (a root-level adopter), with unchanged wrappers, produce identical spec paths, branch names, labels, concurrency groups and number allocation before and after the change.
- **SC-004**: A subfolder project copied to the root of a fresh repository runs a new lifecycle after only adding root wrappers, secrets and labels, with 0 files edited inside the copied folder.
- **SC-005**: Projects nested at least three levels deep each run a lifecycle that reads only their own constitution and Spec Kit state.
- **SC-006**: Every new validation's reject branches are exercised by checked-in fixtures, and the local gate suite passes on the change.

## Assumptions

- The adopting repository is a single GitHub repository; GitHub reads workflows only from the root `.github/workflows/`, so a multi-project repository keeps one shared wrapper set there (FR-018).
- Spec Kit's own nearest-`.specify/` resolution and explicit project-root override (present in the pinned version) are sufficient on the Spec Kit side; no change to vendored Spec Kit files is needed.
- Each project pins its own Spec Kit version through its `.specify/init-options.json`, which preflight reads (FR-005). Having auto-update-spec-kit regenerate per-project copies is out of scope.
- Agent instruction files from enclosing projects (a parent `CLAUDE.md`, the root `.claude/settings`) may reach a subfolder agent. Excluding them is out of scope; the adoption guide mentions it (FR-018), and planning confirms how claude-code-action and skill discovery behave when the working directory is a subfolder.
- Secrets, the GitHub App, repository variables such as kill switches and auto-merge settings, and the issue board remain repository-wide; per-project settings beyond what routing and namespacing need are out of scope.
- The lifecycle issue, the `spec-request` entry label and the maintainer authorization rules (Principle V) stay unchanged; routing adds a project designation, not a new authorization path.
- Nesting depth is limited only by the 28-character path cap that keeps `spec:` labels within GitHub's 50-character limit (FR-002, FR-014), which caps path length, not depth.
- Enforcing that an enclosing project's lifecycles stay out of nested projects' contents is left to each adopter's own constitution unless planning finds a cheap deterministic guard.
- Moving existing adopters' projects into a shared repository, and migrating their issue/label history, is out of scope; this feature makes it possible, it does not perform it.
