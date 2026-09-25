# Feature Specification: Every Granted Script Is Checked, Not Just The `.specify` Ones At Composite Call Sites

**Feature Branch**: `spec-draft/082-script-grant-existence-scope`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #599 — "Gate 27's script-grant existence check
misses non-composite and non-`.specify` grants"

## Overview

Gate 27 (`.github/scripts/verify-stage-tool-lists.py`) grew a third check in
PR #436, closing #426: a `Bash(...)` grant that names a helper script must
name a script that actually exists in the working tree. The defect it closed
was real and silent — Spec Kit stopped shipping `update-agent-context.sh`,
both `plan` call sites kept granting it, and the prompt kept describing the
step that ran it, with nothing failing.

The check as shipped is narrower than the defect class. It finds a stale
grant only when **both** of two conditions hold:

1. the grant is spelled at a `wing-commander-tool-args` composite call site,
   in that step's `default-allowed-tools` literal (`collect_sites()` walks
   nothing else); **and**
2. the granted path starts with the literal prefix `.specify/scripts/bash/`
   (`SCRIPT_GRANT`'s regex hardcodes it).

A grant that misses either condition is invisible to the check, and the
repository ships grants in both blind spots today. None of them is stale
right now — this is not a live bug — but the #426 failure mode can recur in
either blind spot with nothing reporting it.

### The grants that exist today and are not checked

**Outside the path prefix, inside the composite** (condition 2 fails):

- `.github/workflows/board-loop.yml` lines 963, 1300, 2338 —
  `Bash(python3 .github/scripts/board_git_read.py:*)`, at three composite
  call sites (`board-loop.triage-propose`, `board-loop.route-propose`,
  `board-loop.reviewer`). This is a first-party script that a future rename
  would strand exactly the way Spec Kit's rename stranded
  `update-agent-context.sh` — and the three prompts name the command in
  their text, so a rename would leave three prompts describing a denied
  command.
- `.github/workflows/implement.yml` lines 833, 1401 —
  `Bash(python .github/scripts/run-local-gates.py:*)`, at
  `implement.cycle` / `implement.retry`.

**Outside the composite entirely** (condition 1 fails):

- `.github/workflows/wing-commander-5-implement.yml` line 96 — the wrapper
  passes `extra-allowed-tools: "Bash(python3 .github/scripts/run-local-gates.py:*),Bash(bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh:*)"`
  as a *reusable-workflow call-site input*. These grants reach the agent
  composed with the defaults, but `collect_sites()` only reads a
  composite step's `with:`, so it never sees them.
- `.github/workflows/auto-update-spec-kit.yml` line 2042 — a bare
  `claude_args: --allowedTools "Bash(e2e-scratch/.specify/scripts/bash/create-new-feature.sh:*),Bash(bash e2e-scratch/.specify/scripts/bash/create-new-feature.sh:*),..."`
  on a `claude-code-action` step that never touches the composite. Note
  that this one would *also* fail condition 2: the `e2e-scratch/` prefix
  means the path does not start with `.specify/scripts/bash/`.

### Why this is a spec, not a mechanical widening

That last grant is the reason the issue was filed rather than folded into
PR #436. `e2e-scratch/.specify/scripts/bash/create-new-feature.sh` is a path
that is **supposed** not to exist in the checkout: the e2e provisioning step
creates `e2e-scratch/` at run time from a candidate Spec Kit release. A
check that simply widened its regex to "any granted path must exist on disk"
would fail permanently on a grant that is entirely correct. So widening the
check requires deciding, as policy:

- which grant-composition surfaces are in scope (the composite only, or the
  other two the repository actually uses);
- what counts as a "script grant" worth resolving at all, versus a bare
  command name like `jq` or `yamllint` that names no path;
- and how a grant whose target is legitimately absent at check time is
  recorded, so the check stays fail-closed rather than being widened into
  something that has to be switched off.

The current docstring already states the narrow scope honestly ("Scoped to
`.specify/scripts/bash/` only … a script grant rooted elsewhere, or composed
through a different mechanism (e.g. a bare `claude_args` string), is not
this check's job yet"). This feature decides what the job actually is and
makes the docstring's scope statement true of a wider scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A renamed first-party helper script fails the gate (Priority: P1)

A maintainer renames `.github/scripts/board_git_read.py` (or moves it, or
deletes it after folding it into another script) and forgets the three
`board-loop.yml` composite call sites that grant it. Today the gate suite is
green and the loop's three read-only agent steps ship with a grant for a
command that cannot run, while their prompts still instruct the agent to run
it. This story makes that rename fail Gate 27 with a message naming the
step-label, the grant, and the missing path.

**Why this priority**: This is the exact #426 failure mode, on a path the
repository controls and renames far more often than it renames a vendored
Spec Kit script. It is the largest live exposure and it needs no policy
decision beyond "resolve the path, whatever directory it is in".

**Independent Test**: Delete or rename any granted `.github/scripts/*.py`
helper in a scratch tree and run Gate 27 — it must report a failure naming
the grant and the step-label. Restore it and the gate is green again.

**Acceptance Scenarios**:

1. **Given** a composite call site granting `Bash(python3 .github/scripts/board_git_read.py:*)`
   and no such file in the tree, **When** Gate 27 runs, **Then** it fails
   with a message naming `board-loop.triage-propose`, the grant text, and
   the unresolvable path.
2. **Given** the same grant and the file present, **When** Gate 27 runs,
   **Then** it reports no failure for that grant.
3. **Given** a grant whose path differs from the file on disk only in case
   (`Board_Git_Read.py`), **When** Gate 27 runs on a case-insensitive
   filesystem, **Then** it still fails — matching the behaviour the existing
   `.specify` check already has for Actions' case-sensitive runners.
4. **Given** a grant that names no path at all (`Bash(jq:*)`,
   `Bash(git status:*)`, `Bash(yamllint:*)`, `Read`), **When** Gate 27 runs,
   **Then** it raises no failure for it.

---

### User Story 2 - A grant composed outside the composite is checked too (Priority: P2)

Grants reach an agent step through three surfaces in this repository: the
composite's `default-allowed-tools`, a reusable-workflow caller's
`extra-allowed-tools` / `allowed-tools-override` input, and a bare
`claude_args: --allowedTools "…"` string on a `claude-code-action` step. A
stale script grant is equally silent on all three, and the wrapper at
`wing-commander-5-implement.yml:96` and the e2e agent step at
`auto-update-spec-kit.yml:2042` are both live examples. This story extends
the existence check to the surfaces the repository actually uses.

**Why this priority**: It closes the other half of the filed defect, but the
grants involved are fewer and change less often than P1's, and it is the
half that needs the policy decision about absent-by-design paths — so it
lands second, on top of a resolver P1 has already proven.

**Independent Test**: Point a `claude_args` `--allowedTools` grant (or a
wrapper's `extra-allowed-tools`) at a script path that does not exist and is
not recorded as absent-by-design; Gate 27 must fail naming the workflow, the
job and the step.

**Acceptance Scenarios**:

1. **Given** a wrapper workflow passing `extra-allowed-tools` containing
   `Bash(bash .github/scripts/<missing>.sh:*)`, **When** Gate 27 runs,
   **Then** it fails naming the wrapper file, the job, and the missing path.
2. **Given** a `claude-code-action` step whose bare `claude_args`
   `--allowedTools` string grants a script that does not exist, **When**
   Gate 27 runs, **Then** it fails naming that step.
3. **Given** the repository exactly as it stands today, **When** Gate 27
   runs across all three surfaces, **Then** it reports zero failures — every
   grant either resolves or is recorded as absent-by-design.
4. **Given** a grant whose value is or contains an unexpanded
   `${{ … }}` expression (a passthrough such as
   `extra-allowed-tools: ${{ inputs.extra-allowed-tools }}`), **When**
   Gate 27 runs, **Then** it skips that value rather than reporting a
   failure for a path it cannot know.

---

### User Story 3 - A grant for a path created at run time is recorded, not exempted by accident (Priority: P3)

The e2e verification step grants a script under `e2e-scratch/`, a directory
the provisioning step creates during the run and that is never committed.
The check must not fail on it, and must not stop failing on anything else in
order to let it through. This story gives such a grant an explicit,
reviewable record of *why* it is absent, so the exemption is visible in a
diff rather than implied by a regex that happens not to match.

**Why this priority**: Without it, US2 cannot ship green; with it, the
exemption is auditable. It is smaller than either of the other two and
depends on the decision recorded in FR-006.

**Independent Test**: Remove the e2e grant's absent-by-design record and run
Gate 27 — it must fail. Restore the record and it must pass. Add a record
for a path that *does* resolve, and the gate must report the record as
stale.

**Acceptance Scenarios**:

1. **Given** the `e2e-scratch/.specify/scripts/bash/create-new-feature.sh`
   grant and its absent-by-design record, **When** Gate 27 runs, **Then** no
   failure is reported for it.
2. **Given** the same grant with the record removed, **When** Gate 27 runs,
   **Then** it fails naming the grant.
3. **Given** an absent-by-design record for a path that does resolve in the
   tree, **When** Gate 27 runs, **Then** it reports the record as no longer
   needed, so the exemption list cannot silently outlive its reason.

---

### Edge Cases

- A grant spelled with a leading `bash `, `sh `, `python `, `python3 ` or
  `./`, with or without a trailing argument before the wildcard — all four
  prefixes already appear in shipped grants and each must resolve to the
  same path.
- A grant that names a path with no file extension, or a bare command
  (`Bash(jq:*)`), where no on-disk target is implied.
- A grant carrying a `${{ github.workspace }}` prefix (the e2e step's
  `Write(${{ github.workspace }}/e2e-scratch/**)` neighbours one), where the
  literal text is not a repository-relative path.
- A `--allowedTools` value spread across a multi-line `claude_args` block,
  or quoted differently from the two spellings shipped today.
- A workflow whose YAML does not parse, or a `claude_args` string with no
  `--allowedTools` flag at all.
- The same script granted at a dozen call sites — one failure per site is
  noise; the existing check already memoizes the on-disk lookup.
- A grant that appears only in a `default-disallowed-tools` / 
  `--disallowedTools` list, where a non-existent path denies nothing and is
  harmless.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Gate 27's script-grant existence check MUST resolve a granted
  script path regardless of which directory it lives in, replacing the
  hardcoded `.specify/scripts/bash/` prefix.
- **FR-002**: The check MUST continue to accept every grant spelling it
  accepts today (bare, `bash `-prefixed, `sh `-prefixed, `./`-prefixed, with
  or without a trailing argument before the wildcard) and MUST additionally
  accept the `python `/`python3 `-prefixed spelling the repository ships at
  six grant sites.
- **FR-003**: The check MUST distinguish a grant that names a
  repository-relative path from one that names a bare command, and MUST
  raise no failure for the latter. [NEEDS CLARIFICATION: what makes a
  granted token a path worth resolving — a known interpreter prefix
  (`bash`/`sh`/`python`/`python3`/`./`), the presence of a `/`, a known
  script extension (`.sh`/`.py`), or some combination?]
- **FR-004**: The check MUST inspect grants composed at every surface this
  repository uses to reach an agent step, not the composite call site
  alone. [NEEDS CLARIFICATION: which surfaces are in scope — composite
  `default-allowed-tools` only (status quo, widened by path); plus
  reusable-workflow caller inputs (`extra-allowed-tools`,
  `allowed-tools-override`); plus bare `claude_args --allowedTools` strings
  on `claude-code-action` steps; or every `Bash(<path>)` grant found
  anywhere under `.github/workflows/`?]
- **FR-005**: For a grant found outside a composite call site, the failure
  message MUST identify the grant by workflow file, job and step, since no
  `step-label` exists to name it by.
- **FR-006**: A granted path that is absent from the checkout by design (a
  run-time-provisioned directory such as `e2e-scratch/`) MUST be recorded
  explicitly rather than excluded by a pattern that would also hide an
  unrelated stale grant. [NEEDS CLARIFICATION: how is such a grant
  recorded — a waiver file alongside the repository's existing
  `single-home-waivers.json` / `stage-invariant-waivers.json` /
  `spec-branch-push-waivers.json`; an in-script constant listing the
  absent-by-design path prefixes with their reason; or a comment marker at
  the grant's own call site that the check reads?]
- **FR-007**: A recorded absent-by-design entry whose path *does* resolve in
  the working tree MUST be reported, so the record cannot outlive the reason
  it was written — the same fail-closed posture the check itself has.
- **FR-008**: The check MUST skip any grant value that contains an
  unexpanded `${{ … }}` expression, since the literal text is not a path,
  and MUST NOT treat the skip as a pass it can report on.
- **FR-009**: A malformed or unparseable workflow encountered while
  collecting grants MUST be reported as a failure, not skipped silently.
- **FR-010**: The check MUST keep its current case-sensitive resolution
  behaviour on every path it resolves, so a case-mangled grant fails locally
  on a case-insensitive filesystem exactly as it would on Actions' Ubuntu
  runners.
- **FR-011**: The check MUST report at most one failure per distinct
  (grant site, path) pair, and MUST NOT repeat a filesystem lookup for a
  path it has already resolved.
- **FR-012**: `verify-stage-tool-lists.py --self-test` MUST prove every new
  branch fails for the right reason: a missing non-`.specify` script at a
  composite site, a missing script at each newly-in-scope surface, a bare
  command raising nothing, an expression-valued grant raising nothing, a
  stale absent-by-design record, and the real repository passing clean as a
  baseline. A gate that cannot fail its own subject is worthless here.
- **FR-013**: Gate 27's module docstring MUST state the check's new scope in
  the same terms the current one states its narrow scope, so the next reader
  can tell in-scope from out-of-scope without reading the regex.
- **FR-014**: The change MUST leave Gate 27's other checks (table/call-site
  agreement, ordering, the read-only inspection set, mandated commands) and
  their failure messages unchanged in behaviour.
- **FR-015**: The repository MUST be green under the widened check on the
  day it lands — every grant listed in this spec's Overview either resolves
  or carries an absent-by-design record.

### Key Entities

- **Grant**: one `--allowedTools` entry, e.g.
  `Bash(python3 .github/scripts/board_git_read.py:*)`. Carries an optional
  interpreter prefix, a command or path, an optional trailing argument, and
  a wildcard.
- **Grant site**: where a grant's literal text is written. Today: a
  `wing-commander-tool-args` step's `default-allowed-tools`; a
  reusable-workflow caller job's `extra-allowed-tools` /
  `allowed-tools-override`; a `claude-code-action` step's bare
  `claude_args --allowedTools` string. A composite site additionally has a
  `step-label`; the other two do not.
- **Resolvable path**: the repository-relative path a grant implies, if any,
  checked case-sensitively against the working tree.
- **Absent-by-design record**: the reviewable statement that a named granted
  path is expected not to exist in the checkout, with the reason it does not.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Renaming, moving or deleting any helper script that a workflow
  grants causes the local gate suite to fail, in 100% of cases, naming both
  the grant and the site — where today it fails for none of the grants
  outside `.specify/scripts/bash/`.
- **SC-002**: Every script grant in the repository is covered by the check
  or carries an absent-by-design record; zero are covered by neither. That
  includes the nine grants this spec's Overview identifies as invisible
  today (three `board_git_read.py`, three `run-local-gates.py`, one
  `run-tests.sh`, two spellings of `create-new-feature.sh`), spread across
  all three grant surfaces.
- **SC-003**: The check raises zero failures against the repository as it
  stands, so the widening lands green and every subsequent failure is a real
  regression.
- **SC-004**: The self-test fails if any newly added branch is removed or
  inverted, demonstrated by one mutation per branch.
- **SC-005**: A reader can determine the check's scope — which grant
  surfaces, which path shapes, which exemptions — from the gate's docstring
  and the exemption record alone, without reading its regex.
- **SC-006**: The widened check adds no external dependency and no
  perceptible time to the local gate suite, keeping its per-path filesystem
  lookups memoized as today.

## Assumptions

- The three grant surfaces named in Key Entities are the complete set in use
  today; a fourth would be a new finding rather than a gap in this spec.
- `e2e-scratch/` is the only absent-by-design granted path today. The record
  mechanism must accept more than one, but the repository starts with one.
- The check stays inside Gate 27 rather than becoming a new numbered gate:
  it reads the same call sites, and splitting it would duplicate the
  collection the gate already does — which the repository's "shared logic
  has exactly one home" rule argues against.
- Grants in a *disallowed* list are out of scope. A denied path that does
  not exist denies nothing and misleads nobody about what an agent can run.
- The `stage-interfaces.md` table stays the documentation of record for the
  composite's default lists; this feature does not ask the table to grow
  rows for the non-composite surfaces, because the table's promise
  (FR-013/SC-006 of spec 026) is about a *consumer's* view of stage
  defaults, not about internal wrapper wiring.
- Actions runs on Ubuntu, so path resolution is case-sensitive in the
  environment that matters; the gate reproduces that locally on any host.
- No behaviour of any agent step changes. This feature only changes what the
  gate suite will refuse to let past.
