# Feature Specification: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

**Feature Branch**: `078-plan-tasks-commit-scratch-path`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue [#585](https://github.com/charlesguse/wing-commander/issues/585) — "plan/tasks: give the agent a scratch path for multi-line commit messages", routed from board-loop for originating issue [#441](https://github.com/charlesguse/wing-commander/issues/441) ("Found by the code review of #440")

## Context

Every stage agent in this pipeline runs headless behind a permission
allowlist. The allowlist rejects a command containing a shell expansion or a
heredoc **before** it consults the allowed-tool list, so the ordinary way to
write a multi-line commit message from a prompt —
`git commit -m "$(cat <<'EOF' ... EOF)"` — is denied outright. The denial is
silent about its cause, so an agent that hits it spends turns retrying
variants of a command that can never be permitted. This exposure has been
recorded three times (#266, #323's reopen, #441).

PR #440 closed it for the implement stage. Its fix was a sentence added to
both implement agent prompts naming an exact scratch path outside the
repository and telling the agent to commit from it:

> A commit message longer than one line goes through the Write tool to exactly
> `${{ runner.temp }}/implement-commit-message-cycle.txt` and then
> `git commit -F` with that path; never a heredoc or `$(cat ...)` on the command
> line, which the permission layer denies, and never a file under the
> repository (a path inside `.git/` is denied outright, and any other path
> there would be swept into the commit).
>
> — `.github/workflows/implement.yml:938-945`. Its retry twin
> (`implement.yml:1530-1539`) says the same with
> `implement-commit-message-retry.txt`, and adds a line telling that agent to
> use a name distinct from the cycle site's because the two can both run in one
> job invocation.

The plan and tasks stages have the same shape and none of the fix. Each has
two agent sites — a direct-commit arm and a PR arm, selected by the workflow's
`mode` input — and all four instruct the agent to commit. Three further agent
prompts instruct a commit with no scratch path named, and the clarification
reply puts them in scope too (see [What was settled](#what-was-settled)):

| Workflow | Site | Prompt step | Scratch path named? |
|---|---|---|---|
| `plan.yml` | auto / direct-commit | step 3, `plan.yml:748-752` | no |
| `plan.yml` | pr | step 4, `plan.yml:941-944` | no |
| `tasks.yml` | auto / direct-commit | step 3, `tasks.yml:740-743` | no |
| `tasks.yml` | pr | step 4, `tasks.yml:928-930` | no |
| `board-loop.yml` | fix agent (first site) | `board-loop.yml:1852` | no |
| `board-loop.yml` | fix agent (second site) | `board-loop.yml:2864` | no |
| `pr-conversation.yml` | fold agent | `pr-conversation.yml:2003` | no |
| `implement.yml` | cycle | `implement.yml:938-945` | yes (#440) |
| `implement.yml` | retry | `implement.yml:1530-1539` | yes (#440) |

The commit message these prompts dictate is a one-liner
(`"plan: <slug> (#<issue>)"`), so the gap is latent rather than actively
failing today. It surfaces the first time an agent judges the change worth a
body — a plan that records decisions made without clarification, a tasks run
that explains a re-generation — which is exactly the situation where the
message matters most. The tool permissions needed for the fix are already
granted at all four plan/tasks sites: `Write` and `Bash(git commit:*)` are in
every one of the four `default-allowed-tools` lists
(`plan.yml:681`, `plan.yml:883`, `tasks.yml:683`, `tasks.yml:870`), so at those
sites this is prompt wording, not a permissions change. The three sites brought
in by FR-010 have not been checked the same way; FR-007 governs what happens if
one of them lacks either half.

`finalize.yml` and `cleanup.yml` are not affected: their commits are
deterministic one-liners in `run:` steps, not agent-composed messages.

### What was settled

Three things the issue's drafted change decided by implication rather than by
argument were carried as clarification markers and answered on
[#585](https://github.com/charlesguse/wing-commander/issues/585):

1. **Scope — every agent prompt that instructs a commit.** Not just
   `plan.yml` and `tasks.yml`'s four sites: `board-loop.yml:1852` and
   `board-loop.yml:2864` (the fix agents) and `pr-conversation.yml:2003` (the
   fold agent) instruct a commit with no scratch path named, and fixing only
   two workflows would leave the same latent denial in three more places. This
   is the fourth appearance of the exposure (#266, #323, #441), so it is closed
   everywhere it exists rather than one stage at a time. Carried by FR-010.
2. **Single home — one canonical source rendered into each prompt.** The
   guidance text lives in exactly one place and is rendered into each site,
   the way `wing-commander-metrics-summary` owns the per-run cost line, rather
   than being copied per site with a pointer comment. A pointer is something
   only a human editor can follow; the agent must receive the full sentence in
   its own prompt, so rendering — not pointing — is what satisfies both
   `CLAUDE.md`'s "Shared logic has exactly one home" and the agent's needs.
   The source must be designed so `implement.yml`'s two existing sites (#605)
   can draw from it too. Carried by FR-011.
3. **Gate backing — a new `verify-*.py` gate.** Nothing today can fail when an
   agent prompt instructs a commit without naming a scratch path; #440's fix is
   unprotected and this one would be too. A new gate covers the in-scope sites
   and carries a visible exemption list for agents whose commits are always
   deterministic one-liners, so an exemption is a recorded decision rather than
   a blind spot. `CLAUDE.md`: "a rule with no gate behind it lasts until the
   next session". Carried by FR-012.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A committing agent writes a multi-line message on the first attempt (Priority: P1)

A plan run finishes generating `plan.md`, `research.md` and the contracts, and
has three decisions it made without clarification that belong in the commit
body. It composes a subject line plus a body, writes the message to the scratch
path its prompt names, and commits from that file. The commit lands on the
first attempt.

**Why this priority**: This is the whole feature. Without it the agent's first
multi-line commit is a denial it cannot diagnose from the error, burning turns
out of a bounded budget at the end of a stage, and the likely recovery — drop
the body, commit a one-liner — silently loses the reasoning the body carried.

**Independent Test**: Drive a plan run (either mode) and a tasks run (either
mode) whose agent composes a commit message with a body. The commit succeeds
with no denied tool call, and `git log -1 --format=%B` on the pushed branch
shows subject *and* body. For the in-scope sites that are harder to drive on
demand (`board-loop.yml`'s two fix agents, `pr-conversation.yml`'s fold agent),
read the rendered prompt and confirm it names a path and `git commit -F`.

**Acceptance Scenarios**:

1. **Given** a plan agent in auto mode with a message longer than one line,
   **When** it follows its prompt, **Then** it writes the message to the named
   scratch path and commits with `git commit -F <that path>`, and no command
   it issues is rejected by the permission layer.
2. **Given** a tasks agent in PR mode with a message longer than one line,
   **When** it follows its prompt, **Then** the same holds at that site.
3. **Given** a `board-loop.yml` fix agent or the `pr-conversation.yml` fold
   agent with a message longer than one line, **When** it follows its prompt,
   **Then** the same holds there too — the guidance reaches every in-scope
   site, not only the plan and tasks stages.
4. **Given** any in-scope site and a message that is a single line,
   **When** the agent follows its prompt, **Then** committing with an inline
   `-m` remains available — the scratch file is not forced on every commit.
5. **Given** an agent at any in-scope site, **When** it reads its prompt,
   **Then** the prompt tells it both what to do (Write to an exact named path,
   `git commit -F`) and what will be refused (heredoc, `$(cat ...)`, any path
   under the repository), so a denial is not something it has to discover by
   experiment.
6. **Given** the rendered guidance at two different in-scope sites, **When**
   they are compared, **Then** they differ only in the file path — the rest of
   the sentence is identical because both were rendered from the one canonical
   source.

---

### User Story 2 - The scratch file never becomes part of the repository (Priority: P2)

The message file is workspace debris, not an artifact. It must not be added to
the commit it describes, pushed to the spec branch, or left where a later
`git add` would sweep it up.

**Why this priority**: A stray file committed to a spec branch is a defect
visible in the PR every downstream reviewer reads, and a message file inside
`.git/` is itself denied — so a fix that names a careless path trades one
failure for a worse one.

**Independent Test**: After a plan run and a tasks run that each used the
scratch path, `git status --porcelain` on the branch is clean and
`git show --stat HEAD` lists only the stage's own artifacts.

**Acceptance Scenarios**:

1. **Given** a completed plan or tasks commit made from the scratch file,
   **When** the branch is inspected, **Then** no commit-message file appears in
   the tree or in the commit's file list.
2. **Given** two commits in one run at the same agent site, **When** the second
   message is written, **Then** it replaces the first rather than appending to
   it, and the second commit carries only its own message.
3. **Given** two agent sites that can both execute inside one job invocation,
   **When** each writes a commit message, **Then** neither can overwrite the
   other's file before it is used.

---

### User Story 3 - The convention cannot silently regress (Priority: P3)

A future edit that adds a new agent prompt instructing a commit, or that
rewords an existing one and drops the scratch-path sentence, is caught before
merge rather than by the next denied run.

**Why this priority**: This is the fourth recorded appearance of the same
exposure (#266, #323, #441, and now the plan/tasks half of it). Each previous
fix was correct and each was point-in-time; nothing has ever been able to fail
on its removal.

**Independent Test**: Delete the scratch-path sentence from one agent prompt in
the working tree and run the repository's PR-time gate suite; the suite fails
and names the site.

**Acceptance Scenarios**:

1. **Given** the repository's gate suite, **When** an agent prompt that
   instructs a commit does not name a scratch path, **Then** the suite fails
   and identifies the workflow and the site.
2. **Given** the gate suite, **When** every in-scope agent prompt names one,
   **Then** the suite passes.
3. **Given** a site that is deliberately exempt (an agent whose commits are
   always deterministic one-liners), **When** the suite runs, **Then** the
   exemption is recorded where a reader can see it, not achieved by the check
   being unable to see the site at all.

### Edge Cases

- **Both arms of one stage in one run.** `plan.yml`'s auto and PR agent steps
  are mutually exclusive per run (`mode == 'auto'` vs `mode == 'pr'`), as are
  `tasks.yml`'s, so one filename per stage cannot collide today. implement.yml
  uses per-site filenames because its `cycle` and `retry` sites *can* both run
  in one job invocation. Whichever naming is chosen must remain correct if a
  future change makes two sites in one stage co-runnable. `board-loop.yml`'s
  two fix-agent sites must be checked the same way before they are given a
  shared filename: FR-006 applies to them exactly as it does to implement's
  pair.
- **A rendered copy that drifts from its source.** With one canonical source
  (FR-011), a hand-edit at a call site would put that site out of step with
  every other. The FR-012 gate is what makes such a drift fail rather than sit
  unnoticed until the next divergent fix.
- **Single-line message.** The guidance must be conditional on the message
  being longer than one line; an unconditional rule adds a Write call and a
  turn to every routine commit.
- **Repeated commits at one site.** An agent that commits more than once reuses
  the path; the file must be overwritten, and a stale body from an earlier
  commit must not leak into a later one.
- **A path the run cannot write.** The named path lies outside the checkout.
  The `Write` tool reaches it (implement.yml has relied on this since #440) but
  a Bash-based write would not, because Bash in these runs cannot reach paths
  outside the checkout.
- **Multi-line text that is not a commit message.** The PR-arm prompts also
  ask for a PR body (`plan.yml:949-952`, `tasks.yml:935-936`), which has the
  same composition hazard via `gh pr create --body`. No agent prompt in the
  repository currently gives `--body-file` guidance; see Out of Scope.
- **A stage whose commit message is not agent-composed.** `finalize.yml` and
  `cleanup.yml` commit from `run:` steps with fixed one-line messages and need
  nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every in-scope agent prompt that instructs the agent to create a
  commit MUST tell it that a commit message longer than one line goes to an
  exact named file and that the commit is then made from that file, rather
  than from an inline command-line message.
- **FR-002**: Each such prompt MUST name the file path literally and completely
  — no placeholder the agent has to resolve, no shell variable, and no value it
  must derive — because a reference to a shell variable is itself rejected by
  the permission layer in these runs.
- **FR-003**: The named path MUST lie outside the repository working tree, and
  each prompt MUST state that a path under the repository is unusable: inside
  `.git/` it is refused, and anywhere else it would be swept into the commit.
- **FR-004**: Each such prompt MUST name the composition forms the permission
  layer refuses (a heredoc, `$(cat ...)` on the command line) and say that the
  refusal comes from the permission layer, so an agent that is tempted by them
  does not spend turns discovering this.
- **FR-005**: The guidance MUST apply only to messages longer than one line;
  committing a one-line message inline MUST remain available.
- **FR-006**: Two agent sites that can execute within the same job invocation
  MUST be given distinct file paths, so one site's pending message cannot be
  overwritten by the other's.
- **FR-007**: The change MUST require no new entries in any site's allowed-tool
  or disallowed-tool lists; if a site cannot write the named path or commit
  from it under its existing lists, that site's lists MUST be corrected as part
  of this change rather than left with guidance it cannot follow.
- **FR-008**: The change MUST NOT alter workflow logic, job structure,
  triggers, permissions, concurrency, or step gating at any touched site.
- **FR-009**: Every in-scope site MUST express this guidance with the same
  meaning and the same named forms, so that the convention reads as one rule
  with a per-site path rather than as several similar rules.
- **FR-010**: The set of agent prompts this applies to MUST be every agent
  prompt in the repository that instructs the agent to create a commit — not
  only `plan.yml` and `tasks.yml`'s four sites, but also `board-loop.yml`'s two
  fix agents and `pr-conversation.yml`'s fold agent, plus `implement.yml`'s two
  already-conforming sites (FR-013). A site that instructs a commit and is left
  without the guidance MUST be an explicit exemption under FR-012, not an
  omission.
- **FR-011**: The guidance text MUST be maintained as one canonical source that
  is rendered into each in-scope prompt, so that every agent receives the full
  sentence in its own prompt while the wording exists in exactly one editable
  place — the way `wing-commander-metrics-summary` owns the per-run cost line.
  A per-site copy carrying a canonical-pointer comment MUST NOT be used, since
  a pointer is followable only by a human editor and not by the agent reading
  the prompt. The canonical source MUST be shaped so that `implement.yml`'s two
  existing sites can draw from it as well (#605), even if converting them is
  not part of this change.
- **FR-012**: A new deterministic `verify-*.py` gate MUST fail when an in-scope
  agent prompt instructs a commit without naming a scratch path, and MUST name
  the workflow and the site in its failure output. The gate MUST carry a
  visible exemption list for agent sites whose commit messages are always
  deterministic one-liners, so that an exempt site is a recorded entry a reader
  can audit rather than a site the check cannot see.
- **FR-013**: `implement.yml`'s two existing sites MUST keep working exactly as
  they do today; any consolidation or check introduced here MUST treat them as
  already-conforming rather than requiring their wording to change meaning.

### Key Entities

- **Agent prompt site**: one `prompt:` body handed to one agent invocation in
  one workflow job. A stage may have several (plan and tasks have two each,
  implement has two); each is a separate place the convention must appear.
- **Commit-message scratch file**: a run-scoped file outside the checkout
  holding one multi-line commit message. Written by the agent, read by
  `git commit -F`, never added to a commit, not expected to survive the job.
- **Canonical guidance source**: the single place the guidance sentence is
  written. Every in-scope prompt's copy is rendered from it with that site's
  path substituted; editing the wording means editing this one place (FR-011).
- **Exemption list**: the gate's visible record of agent sites that instruct a
  commit but are deliberately not required to name a scratch path because their
  messages are always deterministic one-liners (FR-012).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every in-scope agent prompt that instructs a commit names a
  scratch path — zero such sites remain without one, counted by reading the
  prompts.
- **SC-002**: A plan run and a tasks run whose agent composes a multi-line
  commit message each complete the commit with zero permission denials
  attributable to message composition, and zero retry attempts of a denied
  composition form.
- **SC-003**: After those runs, the branch contains no commit-message file:
  `git status --porcelain` is clean and the commit's file list holds only the
  stage's own artifacts.
- **SC-004**: The pushed commit retains its body — subject and body both
  present — rather than being reduced to a one-line message.
- **SC-005**: The repository's PR-time gate suite passes on the change, and no
  gate's behaviour on unrelated inputs changes.
- **SC-006**: Removing the guidance from any one in-scope site causes the new
  gate to fail and name that workflow and site; with every in-scope site
  conforming, the gate passes.
- **SC-007**: A reader can establish the convention's current wording from one
  location, and confirm every site agrees with it, without comparing nine
  paragraphs by eye; changing the wording requires editing exactly one file.
- **SC-008**: Every agent site that instructs a commit is either covered by the
  gate's conformance check or listed in its exemption list — the two sets
  together account for all of them, with none unaccounted for.

## Out of Scope

- Multi-line **PR and issue bodies** composed by agents (`gh pr create --body`,
  `gh issue comment --body`). The same hazard exists and no prompt currently
  addresses it; it is a separate change with its own sites and its own
  `--body-file` convention to settle.
- Deterministic `run:`-step commits in `finalize.yml`, `cleanup.yml`,
  `auto-release.yml` and `auto-update-spec-kit.yml`. Their messages are fixed
  one-liners composed by shell the allowlist already permits.
- Changing what the plan or tasks agent is asked to *put* in a commit message.
  This feature makes a multi-line message possible; it does not mandate one.
- Widening or narrowing any site's tool allowlist beyond what FR-007 requires.
- Rewriting `implement.yml`'s two existing sites to consume the canonical
  source. FR-011 requires the source to be shaped so they *can* draw from it
  and FR-013 requires them to keep working unchanged; performing that
  conversion is #605's work, not this change's.

## Assumptions

- The four plan/tasks sites' existing allowed-tool lists already permit both
  halves of the fix (`Write`, `Bash(git commit:*)`), so no permission change is
  expected; FR-007 exists to catch the case where a site brought into scope by
  FR-010 does not.
- `implement.yml`'s post-#440 sentence is the reference wording: it is already
  merged, already proven in runs, and any consolidation should preserve its
  meaning rather than re-derive it.
- A run-scoped temporary location outside the checkout exists and is writable
  by the agent's file-writing tool at every in-scope site — this is what
  implement.yml already depends on.
- Each stage's two arms remain mutually exclusive per run unless a future
  change says otherwise; FR-006 states the invariant so the naming stays
  correct either way.
- This change is drafted against current `main`. Issue #585 notes it should be
  rebased if spec 058 (#434), whose implement cycle touches both files, lands
  first.
- The exposure is latent, not currently failing: the commit messages the four
  plan/tasks prompts dictate today are one-liners. The value of the change is
  that the first agent-composed body does not cost a denial.
- The nine sites named in the Context table are the complete set of agent
  prompts that instruct a commit as of this drafting. FR-012's gate is what
  keeps that list honest as prompts are added or reworded, so the count is an
  observation rather than a fixed constant the change depends on.
- `board-loop.yml`'s two fix agents and `pr-conversation.yml`'s fold agent
  compose their own commit messages and so belong in scope on the same grounds
  as plan and tasks; if one of them turns out to commit only deterministic
  one-liners, it becomes an FR-012 exemption entry rather than silently
  dropping out of scope.
