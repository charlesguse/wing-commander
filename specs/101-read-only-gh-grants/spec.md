# Feature Specification: Read-Only Agents Hold No Write-Capable `gh` Grant

**Feature Branch**: `101-read-only-gh-grants`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #759, routed from board-loop.yml (originating
issue #609): "watchdog diagnose agent holds `Bash(gh:*)` with the App token:
remote writes and local file writes are allowed", plus the two maintainer
comments folded in (the `auto-update-spec-kit.yml` evaluate-path agent holds
`Bash(gh api:*)` and has the same gap; `Bash(gh:*)` additionally permits
`gh alias set` and `gh extension install`, so the grant alone reaches
arbitrary command execution).

## Overview

Two of this repository's agent steps are described everywhere as read-only
and are not:

- `watchdog.diagnose` (`.github/workflows/watchdog.yml`) is granted
  `Bash(gh:*)` and runs with the pipeline's App token.
- `auto-update-spec-kit.yml`'s evaluate-path agent ("Decide upgrade path")
  is granted `Bash(gh api:*)` and runs with the same token.

Both agents read material that a non-maintainer can influence — run logs,
step summaries, annotations, execution transcripts, upstream release notes —
so both are prompt-injection surfaces. What each grant actually authorizes
goes well past reading:

- remote writes (`gh issue close`, `gh pr merge`, `gh api -X POST …` — and
  `gh api` cannot be scoped to GET, because the method lives in `--method`
  and `-f` arguments rather than in the command prefix);
- local file writes (`gh run download`, `gh release download`, `gh api
  --cache`/output redirection surrogates) — the same class of hole #513
  closed for raw `git log --output=<path>`;
- arbitrary command execution, via `gh alias set` (an alias may shell out
  with `!`) and `gh extension install`, neither of which the `cd`/`pushd`/
  `popd` denials from #613 constrain.

Gate 93's check 4 already forbids every `gh` grant on a read-only agent —
but only inside `board-loop.yml`. Check 4b, which covers the rest of the
fleet, deliberately checks only the *git* half of check 4 and states that
"Other Bash grants (`gh ...`) are not this check's business outside
board-loop.yml". So the two grants above are unguarded by construction: no
gate can fail on them, and nothing stops the next read-only agent from
being born with the same grant.

This feature closes that hole at the two known sites and makes the rule
mechanical for every future one.

## Clarifications

### Session 2026-09-29 — answered on lifecycle issue #759

- Q: What replaces `Bash(gh:*)` on `watchdog.diagnose` — a named read-only
  subcommand allow-list, removal with everything staged, or removal plus a
  deterministic job-log fetch? → A: **Remove `gh` entirely and stage the
  failed jobs' logs** (Question 1, Option C). A deterministic step stages
  those logs as files before the agent runs, the way `board-loop.reviewer`'s
  gather step does (#503). That fetch MUST fail loudly rather than silently
  under the App token, and a fetch that fails is reported through the
  untrusted-collectors mechanism rather than widening the token. Because
  both named agents therefore end with zero `gh` grants, the fleet rule is
  the same total rule board-loop's check 4 already applies — a read-only
  agent gets no `gh` command at all — and no per-subcommand write review is
  needed. (FR-002, FR-003, FR-007, FR-018, FR-019, User Story 1, User
  Story 3)
- Q: Does the rule bind consumer-supplied
  `extra-allowed-tools`/`allowed-tools-override`, or only this repository's
  shipped defaults? → A: **Shipped defaults only**, as Gate 93 does today
  (Question 2, Option A). The consuming repository owns its configuration
  (Principle VI), so an adopter who re-grants a write-capable `gh` to a
  read-only step is making its own call and this repository's gates stay
  green; no published-stage runtime refusal is added. (FR-014, User Story 3)
- Q: What does diagnose do when staged evidence cannot adjudicate a signal?
  → A: **Reuse the existing untrusted-collectors mechanism** (Question 3,
  Option A): the verdict states which kinds of evidence could not be
  gathered on that run. The signal is neither dropped silently nor chased
  through a route the agent no longer holds, and the verdict stays
  schema-valid. (FR-006, FR-020, User Story 1)

### Status update 2026-09-30 — reconciled with current `main` (maintainer spec review)

- **Both named grants are unchanged on `main`.** `watchdog.diagnose`'s
  shipped list at `watchdog.yml:2363` still carries `Bash(gh:*)`, and the
  "Decide upgrade path" step's inline list at
  `auto-update-spec-kit.yml:1105` still carries `Bash(gh api:*)`. Gate 93's
  check 4b docstring still scopes `gh` out of the fleet check
  (`verify-issue-context-single-home.py:168`).
- **A third read-only agent holds `gh` grants (open, owner decision).**
  `pr-conversation.classify` (`pr-conversation.yml:843`) is named in
  `FLEET_READ_ONLY_STEP_LABELS` (`verify-issue-context-single-home.py:456`),
  runs with `WC_BOT_TOKEN`, and is granted `Bash(gh pr view:*)`,
  `Bash(gh issue view:*)` and `Bash(gh search issues:*)`. Its prompt
  advertises them. FR-007's total rule ("any `gh` grant at all") would fail
  the gate on this site on a clean tree once US1 and US2 land, which
  contradicts US3 scenario 4, SC-001 ("down from the two") and the first
  Assumption. No owner answer covers this site. It is flagged here and not
  resolved; FR-007 and US3 scenario 4 stand as drafted until it is
  answered.
- **Diagnose's logs are already fetched once, under `github.token`.** The
  `collect-step-summary` collector fetches every job's log for the inspected
  run (`watchdog.yml:1133`, `1146`) through `ACTIONS_TOKEN: ${{
  github.token }}`, because the App token has no Actions read
  (`watchdog.yml:224-233`, `docs/setup.md`, Gate 12). FR-018's staging
  therefore reuses that fetch, or a shared helper with it, rather than a
  second copy (CLAUDE.md "Shared logic has exactly one home"). It runs under
  the same `github.token` route, which the workflow already grants
  (`actions: read`). This is not the App-token change Out of Scope
  excludes. The owner's "fail loud rather than silently under the App
  token" is met by not using the App token and by FR-019.
- **Spec 091 (merged) governs the staging step's capture.** If FR-018's
  fetch is a `gh api` command-substitution capture, spec 091 FR-002/FR-005
  apply. A failed read must exit, reassign or carry the FR-008 marker, and
  must never become the staged log's content. That is FR-019 stated
  mechanically.
- **Specs 109 (merged) and 099 (#750, in flight)** also change
  `watchdog.yml`. 109 changes finding dedup, and 099 changes how collectors
  identify the inspected stage. Neither touches diagnose's tool list or the
  untrusted-collectors mechanism Q3 reuses, and FR-018's staging step does
  not identify a stage, so there is no overlap.
- **More live contracts record the removed grants** than FR-016 named:
  `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md:81`,
  `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md:104`,
  and a second paragraph of
  `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (line 293) as
  well as its table (line 339). FR-016 now lists them.
- **Gate numbers corrected.** Deterministic `gh` calls in `run:` steps are
  covered by Gate 12 (token permission), Gate 18 (pagination) and Gate 28
  (explicit method). Gate 84 is the board loop's route backstop and was
  cited in error.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A prompt-injected diagnose agent cannot touch the repository (Priority: P1)

The watchdog inspects a failed run whose logs contain attacker-influenced
text (a branch name, a test assertion message, a PR title echoed into a job
log, an agent transcript quoting an issue body). The diagnose agent reads
that text as evidence. Even if the text successfully redirects the agent,
the tools it holds cannot close an issue, merge a PR, post to the API, or
drop a file into the workspace — because no such tool is granted.

**Why this priority**: This is the reported vulnerability, it runs on every
watchdog invocation (the highest-frequency agent step in the repository),
and it holds the App token. Delivering only this story already removes the
exposure the issue was filed for.

**Independent Test**: Read the composed allowed list for
`watchdog.diagnose` and confirm it grants no `gh` command at all, that the
failed jobs' logs it used to be able to fetch are staged as files a
deterministic step wrote, and that the agent still reaches a verdict on a
real watchdog run re-driven after merge.

**Acceptance Scenarios**:

1. **Given** `watchdog.yml`'s `watchdog.diagnose` tool-args site, **When**
   its shipped `default-allowed-tools` is read, **Then** no `gh` grant
   remains in any spelling, and every remaining `Bash(...)` grant is one a
   reviewer can point at as unable to write a file or perform a remote
   mutation.
2. **Given** a diagnose agent under the narrowed list, **When** it attempts
   any `gh` invocation, **Then** the attempt is denied by the allow-list and
   the denial is visible in the step's execution output.
3. **Given** a watchdog run re-driven after merge, **When** the diagnose
   step completes, **Then** it produces a schema-valid verdict with
   evidence grounded in signals it could still read.
4. **Given** a watchdog run over a failed workflow run, **When** the
   deterministic log-staging step has completed, **Then** the failed jobs'
   logs are on disk at the literal paths the diagnose prompt names, and the
   prompt names no fetch the agent would have to perform itself.
5. **Given** a run in which the log fetch cannot be performed (the App
   token cannot read the logs, the run is gone, the response is empty),
   **When** the staging step runs, **Then** the failure is recorded
   explicitly rather than left as an empty or absent file, and the diagnose
   verdict states that that kind of evidence could not be gathered.

---

### User Story 2 - The Spec Kit upgrade agent is held to the same rule (Priority: P1)

The auto-update stage's evaluate-path agent reads upstream release notes —
text written by a third party outside this repository entirely — and
decides whether an upgrade is a clean bump. Its `Bash(gh api:*)` grant is
removed outright — its evidence is already staged, so nothing replaces it —
and a release note crafted to redirect the agent reaches nothing.

**Why this priority**: Same token, same write capability, and the evidence
it reads has an even weaker provenance than the watchdog's. Its own prompt
already stages every piece of evidence it is told to use
(`release-notes.json`) and instructs it not to fetch anything else, so the
grant is doing no declared work today. Fixing it alongside US1 is what
makes the gate in US3 able to pass on a clean tree.

**Independent Test**: Read the inline `--allowedTools` on the "Decide
upgrade path" step and confirm no `gh` grant remains, then
confirm the stage still reaches one of its three outcomes with sources
cited from the staged release-notes file.

**Acceptance Scenarios**:

1. **Given** the "Decide upgrade path" step's inline `--allowedTools`,
   **When** it is read, **Then** `Bash(gh api:*)` is absent and no other
   `gh` grant has taken its place.
2. **Given** that step's prompt, **When** it is read, **Then** it no longer
   describes `gh api` as one of the agent's evidence tools, and every
   evidence route it names is a file a deterministic step staged before the
   agent ran.
3. **Given** an upgrade evaluation, **When** the agent runs under the
   narrowed list, **Then** it still returns `clean-bump`,
   `needs-migration`, or `ambiguous-options` with its sources drawn from
   the staged release notes.

---

### User Story 3 - The rule is mechanical, so the next read-only agent cannot be born with the grant (Priority: P1)

A maintainer adds a new read-only agent step, or widens an existing one's
allowed list, and the PR-time gate suite fails with a message naming the
offending grant and the route to take instead. The rule is not a comment in
a contract that the next author has to have read.

**Why this priority**: Constitution VIII — the repository's own history is
that every instance of this class was found by accident, never by a check.
Both US1 and US2 are one paste away from regressing without this, and the
issue asks for the gate explicitly. It is P1 rather than P2 because the two
narrowings above are exactly the kind of change that a later "the agent
needed it" commit silently reverses.

**Independent Test**: Run the gate against a fixture that grants a
read-only agent a `gh` command and confirm it fails with a message naming
that grant; run it against the real tree after US1 and US2 land and confirm
it passes.

**Acceptance Scenarios**:

1. **Given** a checked-in fixture whose read-only tool-args site grants a
   `gh` command, **When** the gate runs, **Then** it fails and the message
   names the grant and points at the staged-file route.
2. **Given** a checked-in fixture whose read-only agent step appends a `gh`
   grant to its own `claude_args` `--allowedTools` (bypassing the
   composite), **When** the gate runs, **Then** it fails.
3. **Given** a checked-in fixture whose read-only agent step is inline (no
   tool-args site, the `auto-update-spec-kit.yml` shape), **When** the gate
   runs, **Then** the same rule is applied to its inline list.
4. **Given** the real tree with US1 and US2 landed, **When**
   `python .github/scripts/run-local-gates.py` runs, **Then** the gate
   passes, and it runs with the same subject and arguments locally as in
   CI.
5. **Given** a mutation of the real `watchdog.yml` or
   `auto-update-spec-kit.yml` that restores the removed grant, **When** the
   gate's self-test runs, **Then** the mutation is caught.
6. **Given** a read-only call site that forwards a consumer's
   `${{ inputs.extra-allowed-tools }}` or
   `${{ inputs.allowed-tools-override }}`, **When** the gate runs, **Then**
   it does not fail on the forwarded value — its subject is this
   repository's shipped defaults — and that scope is stated where the check
   is defined.

---

### User Story 4 - The written record stops teaching the old grant (Priority: P2)

A maintainer or an adopter reading this repository's documented posture
finds the narrowed grant, not `Bash(gh:*)`, described as what a read-only
diagnosis agent gets. The contracts that record per-step tool lists agree
with the workflows they describe.

**Why this priority**: `docs/agent-friendly-workflows.md` currently offers
`--allowedTools "Read,Grep,Bash(gh:*)"` as the *exemplar* of a read-only
tool allow-list — a published document actively recommending the defect to
adopters. The live contracts under `specs/*/contracts/` record the grant as
deliberate ("deliberately read-only") and as pre-existing-and-untouched;
left alone they become false and will be cited by the next author as
authority. It is P2 only because it changes no runtime behaviour.

**Independent Test**: Grep the documentation and live contracts for the
removed grant spellings and confirm each remaining occurrence is a
historical note that says so, not a current description.

**Acceptance Scenarios**:

1. **Given** `docs/agent-friendly-workflows.md`'s read-only tool-allow-list
   guidance, **When** it is read, **Then** its example is a list that
   cannot write, and it states why a bare `gh` grant is not read-only.
2. **Given** each live contract that records `watchdog.diagnose`'s or
   evaluate-path's tool lists, **When** it is read, **Then** the recorded
   list matches the workflow's shipped list.
3. **Given** the `specs/051-read-only-inspection-policy` contract's
   statement that `watchdog.diagnose` reaches `gh api` through a
   "pre-existing, wider `Bash(gh:*)` grant … untouched by this policy",
   **When** it is read after this feature, **Then** it no longer describes
   a present-tense grant that no longer exists.

---

### Edge Cases

- **The narrowed agent needs a fact only the Actions API holds.** Diagnose
  today can reach for job logs itself; the collectors that fetch them use a
  separate Actions-scoped token, and under the App token those reads
  already fail silently (a limitation `watchdog.yml` records inline). The
  resolution is a deterministic staging step that fetches those logs before
  the agent runs and fails loudly when it cannot, with the failure reported
  through the untrusted-collectors mechanism so the verdict says what it
  could not see (FR-018, FR-019, FR-020).
- **An adopter re-grants the command.** Published stages accept
  `extra-allowed-tools` and `allowed-tools-override`; Gate 93 deliberately
  ignores `${{ inputs.* }}` values and checks shipped defaults only, so an
  adopter can hand `watchdog.diagnose` back `Bash(gh:*)` at call time. That
  stays the adopter's call: the rule binds this repository's shipped
  defaults only (FR-014, Principle VI). A literal grant written at a call
  site in this repository's own workflows is a shipped default and is
  gated (FR-009).
- **A `gh` command that reads but writes a file.** `gh run view --log`
  writes nothing; `gh run download`, `gh release download` and `gh api
  --cache` do. A per-subcommand allow-list would have to be decided one
  option at a time, and a prefix rule cannot see the option — the same
  reason #513 refused to deny `git --output` by listing its spellings. This
  case does not arise, because no `gh` subcommand survives on a read-only
  agent; it is why the rule is total rather than per-subcommand.
- **A `gh` command that reads unfiltered comments.** `gh pr view
  --comments` and `gh issue view --comments` return every comment from
  anyone; board-loop's check 4 forbids both for that reason (FR-056,
  #503). The total rule cannot reopen that, since it ships no subcommand
  allow-list at all.
- **A read-only agent with no tool-args site at all.** The
  `auto-update-spec-kit.yml` shape: its lists are inline in `claude_args`.
  The gate already handles this shape for git and must for `gh`.
- **A grant spelled to evade a substring test.** `gh:*`, `gh*`, `gh *`,
  `Bash`, `Bash(*)`, `Bash(/usr/bin/gh …)` all authorize `gh`; check 4
  already closes these for board-loop and the fleet rule must close the
  same set.
- **A deterministic `run:` step that calls `gh api`.** Many do, correctly —
  they are code a reviewer reads, not a model's discretion. They stay in
  scope of Gates 12, 18 and 28 (and spec 091's capture check) and out of
  scope here.
- **Zero sites to check.** If a rename or a refactor leaves the new check
  with no read-only site to inspect, it must fail rather than report a pass
  it did not earn (Constitution VIII).

## Requirements *(mandatory)*

### Functional Requirements

#### The two named agents

- **FR-001**: `watchdog.diagnose`'s shipped allowed-tools list MUST NOT
  grant `Bash(gh:*)`, nor any other spelling that authorizes every `gh`
  subcommand (`gh*`, `gh *`, bare `Bash`, `Bash(*)`).
- **FR-002**: `watchdog.diagnose`'s shipped allowed-tools list MUST NOT
  grant any `gh` command at all — not a subcommand, not an API path, not a
  path-qualified spelling. The end state of its `gh` access is zero grants;
  every route it loses is replaced by a file a deterministic step stages
  before it runs (FR-005, FR-018). This total form is the FR-002 test the
  requirements below refer to, and it is the same rule board-loop's check 4
  already applies to its own read-only agents.
- **FR-003**: The auto-update stage's evaluate-path agent ("Decide upgrade
  path") MUST NOT grant `Bash(gh api:*)`, and MUST NOT grant any `gh`
  command subject to the same FR-002 test. Nothing is staged in its place:
  its evidence (`release-notes.json`) is staged already.
- **FR-004**: Each narrowed agent's prompt MUST name only evidence routes
  its own composed tool list actually authorizes. A prompt sentence that
  describes `gh` or `gh api` as one of the agent's evidence tools MUST be
  removed or rewritten when the grant behind it is removed, so a denied
  call cannot be coached by the prompt itself.
- **FR-005**: Whatever evidence a narrowed agent still needs and can no
  longer fetch MUST be staged by a deterministic step that runs before the
  agent, at a literal path the prompt names exactly — the
  `board-loop.reviewer` pattern from #503 and the intake/clarify
  staged-comments pattern from #029.
- **FR-006**: Each narrowed agent MUST still reach its declared outcome:
  diagnose a schema-valid verdict, evaluate-path one of its three
  outcomes. A narrowing that leaves either unable to produce a verdict is
  not an acceptable outcome of this feature (Constitution II's reason for
  giving diagnose `claude-opus-5` at all: a step that reaches no verdict is
  worse than no step). When staged evidence is insufficient, the verdict is
  still produced and carries the gap (FR-020).

#### The gate

- **FR-007**: A gate reachable through the gate registry and run by the
  PR-time suite MUST fail when any read-only agent step in
  `.github/workflows/` — in any workflow, not only `board-loop.yml` — is
  granted a `gh` command that fails the FR-002 test, i.e. any `gh` grant at
  all.
- **FR-008**: The gate MUST identify read-only agent steps the same way
  Gate 93's existing checks do: the labels it names explicitly, plus any
  tool-args site whose shipped allowed list carries neither `Write` nor
  `Edit` (whole or path-scoped), plus any agent step with no tool-args site
  whose own inline `--allowedTools` carries neither.
- **FR-009**: The gate MUST read grants from every route that reaches the
  agent from this repository's own workflows: the tool-args site's
  `default-allowed-tools`, `extra-allowed-tools` and
  `allowed-tools-override` inputs, and the agent step's own `claude_args`
  `--allowedTools` text. Literal grant text at any of those routes is in
  scope; a forwarded `${{ inputs.* }}` expression is a consumer value and is
  not (FR-014).
- **FR-010**: The gate MUST match on whitespace-split token prefixes of the
  granted command, not on substrings, and MUST treat every open-wildcard
  spelling (`gh:*`, `gh*`, `gh *`, bare `Bash`, `Bash(*)`) and every
  path-qualified spelling (`/usr/bin/gh …`) as authorizing `gh`.
- **FR-011**: The gate MUST fail loudly rather than silently pass when it
  cannot reach its subject: a named read-only label whose workflow or step
  is missing, or zero read-only sites discovered overall, is a failure.
- **FR-012**: Every failure branch the gate ships MUST be exercised by a
  checked-in fixture, and every mutation of the real tree that restores a
  removed grant (in either named workflow, through either the composite or
  inline `claude_args`) MUST be caught by the gate's self-test.
- **FR-013**: The gate MUST NOT be suppressible by an unrelated gate's
  failure in the same job, and MUST run the same subject with the same
  arguments locally (`run-local-gates.py`) as in CI.
- **FR-014**: The rule MUST bind this repository's shipped defaults only,
  as Gate 93 does today: the gate ignores `${{ inputs.* }}` values, and no
  published stage gains a runtime refusal of a consumer
  `extra-allowed-tools`/`allowed-tools-override` that re-grants `gh` to a
  read-only step. The consuming repository owns its configuration
  (Principle VI), and no published-stage behaviour changes, so this feature
  is not a compatibility event under Principle VII. That scope MUST be
  stated where the check is defined, so the next author does not read a
  green gate as a guarantee about adopters.

#### The record

- **FR-015**: `docs/agent-friendly-workflows.md`'s read-only tool-allow-
  list guidance MUST NOT present any `gh` grant as a read-only example, and
  MUST state why a bare `gh` grant is write-capable and why the rule is
  total rather than per-subcommand.
- **FR-016**: Every live contract under `specs/*/contracts/` that records
  `watchdog.diagnose`'s or evaluate-path's tool lists MUST match the
  shipped lists after this change, including the per-stage table and the
  `gh api` disposition paragraph in
  `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, the `gh api`
  disposition paragraph in
  `specs/051-read-only-inspection-policy/contracts/inspection-policy.md`,
  the diagnose `--allowedTools` in
  `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md`, and the
  evaluate-path `--allowedTools` in
  `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`.
- **FR-017**: The rationale for the narrowing — that `gh` reaches remote
  writes, local file writes, and arbitrary execution via aliases and
  extensions — MUST have exactly one canonical home, with every other site
  pointing at it rather than restating it.

#### The replacement route for diagnose

- **FR-018**: A deterministic step in `watchdog.yml` MUST stage the failed
  jobs' logs for the run under diagnosis as files, at literal paths, before
  the diagnose agent runs, following the `board-loop.reviewer` gather
  pattern (#503). The diagnose prompt MUST name those paths exactly and MUST
  NOT name a fetch the agent would have to perform itself. The logs MUST be
  fetched once per run: the step reuses `collect-step-summary`'s per-job
  fetch (or one helper shared with it) under the workflow's existing
  `github.token` Actions-read route, not the App token and not a second
  copy of the fetch.
- **FR-019**: That staging step MUST fail loudly rather than silently: an
  authorization failure, a missing run, or an empty response MUST be
  recorded as an explicit gather failure that the diagnose step can read,
  never left as an absent or empty file the agent would read as "there was
  nothing there". Widening the App token is not the remedy and is out of
  scope; reporting the failure is.
- **FR-020**: When the staged evidence cannot adjudicate a signal —
  including because FR-019 recorded a gather failure — diagnose MUST reuse
  the existing untrusted-collectors mechanism and state in its verdict which
  kinds of evidence could not be gathered on that run. It MUST NOT drop the
  signal without saying so, and MUST NOT be coached toward a route it no
  longer holds.

### Key Entities

- **Read-only agent step**: an agent invocation whose composed allowed
  tools carry no write tool. Identified by an explicit label or by the
  absence of `Write`/`Edit` in its shipped list.
- **Tool grant**: one `Bash(...)` entry in an allowed or disallowed list,
  reaching the agent through a tool-args composite input or the step's own
  `claude_args`.
- **Write-capable `gh` command**: a `gh` invocation that can mutate a
  remote resource, write a local file, define an alias, or install an
  extension — including bare `gh`, which authorizes all of them. This is the
  rationale for the rule, not its unit of enforcement: because the write
  behaviour of several subcommands lives in an option a prefix rule cannot
  see, the rule forbids `gh` outright on a read-only agent (FR-002).
- **Staged evidence file**: a literal-path file a deterministic step writes
  before the agent runs, which the agent's prompt names exactly; the
  sanctioned replacement for an agent's own fetch.
- **Gate check**: the deterministic fleet-wide rule, its fixtures, and its
  mutation self-test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero read-only agent steps across `.github/workflows/` hold
  any `gh` grant, counted from the shipped allowed lists — down from the two
  that hold one today.
- **SC-002**: A maintainer who re-adds either removed grant sees the PR-time
  gate suite fail, with a message naming the grant and the staged-file
  route, before the change can merge.
- **SC-003**: Every failure branch of the new check is covered by a
  checked-in fixture; a reviewer can confirm coverage without re-running a
  manual demonstration.
- **SC-004**: One re-driven watchdog run after merge produces a
  schema-valid diagnose verdict, and its execution output records no
  denied-tool event attributable to a route the prompt still names.
- **SC-005**: One auto-update evaluation after merge returns one of the
  three declared outcomes with its sources drawn from the staged release
  notes.
- **SC-006**: Zero occurrences remain, in documentation or live contracts,
  of a bare `gh` grant presented as a read-only tool list; occurrences that
  survive are labelled as historical.
- **SC-007**: The narrowing rationale appears in full in exactly one file;
  every other mention is a pointer.
- **SC-008**: A run whose job-log staging cannot fetch its logs ends with a
  recorded gather failure and a schema-valid diagnose verdict naming the
  evidence it could not gather — zero runs where the failure is
  indistinguishable from "there was nothing to read".

## Assumptions

- The two agents named in the issue and its comments were taken as the
  complete set of `gh` grants on read-only agent steps. **This does not hold
  on `main`:** `pr-conversation.classify` also holds three `gh` grants (see
  the 2026-09-30 status update; open owner decision). The gate in US3 is what turns that from an audit result into a
  standing guarantee, so the feature does not depend on the audit being
  exhaustive.
- Diagnose's *primary* evidence is already staged: the collectors write
  `watchdog-signals.json` and `watchdog-untrusted-collectors.json` before
  the agent runs, and the prompt directs the agent to them and tells it not
  to explore the repository open-endedly. Its `gh` grant is therefore a
  fallback route rather than its declared evidence path.
- Evaluate-path's evidence is entirely staged already (`release-notes.json`),
  and its prompt tells it not to fetch anything else, so removing its `gh`
  access removes no declared capability.
- The existing git-wrapper grant (`python3 -I …/git_read.py`) stays as-is
  for both agents; #518 already settled that route and this feature does
  not revisit it.
- The rule belongs as an extension of the existing Gate 93 check 4b rather
  than as a new numbered gate, because 4b already discovers read-only sites
  fleet-wide, already parses both grant routes, and already carries the
  fixtures and mutation harness — the issue's own phrasing ("add a Gate 93
  fleet check") assumes this. A separate gate number is an
  implementation-time call if that assumption does not hold.
- Deterministic `run:` steps that call `gh` or `gh api` are unaffected.
  They are code under review, not a model's discretion, and are already
  governed by the gates that cover them.
- `gh` cannot be scoped to read-only by prefix rule alone for the
  subcommands whose write behaviour lives in an option (`gh run download`,
  `gh api --method`, `gh api --cache`). This feature therefore ships no `gh`
  subcommand allow-list at all, and the per-entry reasoning
  `READ_ONLY_BASH_GRANTS` records today is not extended with `gh` entries.
- No transcript of a real diagnose run was available while specifying, so
  which `gh` commands diagnose has actually invoked is unknown. The
  specification states the required end state (zero `gh`) and the
  degradation behaviour; deciding exactly which logs FR-018 stages — and
  confirming that nothing else diagnose used goes unreplaced — is
  planning/implementation work.

## Dependencies

- Gate 93 (`.github/scripts/verify-issue-context-single-home.py`): its
  check 4/4b machinery, `READ_ONLY_BASH_GRANTS`,
  `FLEET_READ_ONLY_STEP_LABELS`, fixtures and mutation self-test.
- The gate registry (`.github/scripts/wc_gate_registry.py`) and the PR-time
  suite (`.github/scripts/run-local-gates.py`, `lint-workflows.yml`).
- `.github/actions/wing-commander-tool-args`: the composite that composes
  the shipped defaults with consumer inputs.
- The staged-evidence patterns this feature reuses: #503
  (`board-loop.reviewer`'s gather step) and specs/029-intake-issue-comments
  (staged, code-filtered comments).
- Prior decisions this feature amends rather than contradicts: #513
  (read-only agents get no raw git), #518 (the git wrapper, and check 4b's
  fleet scope), #613 (`cd`/`pushd`/`popd` denials),
  specs/051-read-only-inspection-policy (which recorded the
  `watchdog.diagnose` grant as pre-existing and untouched).

## Out of Scope

- Deterministic `run:` steps' use of `gh`/`gh api`, including the watchdog
  collectors' Actions-token job-log reads and the new log-staging step
  FR-018 adds — that step is work this feature does, but it is code under
  review rather than a grant the new rule inspects.
- `board-loop.yml`'s read-only agents, already covered by check 4.
- Write-capable agent steps (intake, clarify, plan, tasks, implement,
  finalize, the board-loop fixer), whose `gh` grants are deliberate.
- Revisiting the git-wrapper route from #518.
- The App token's own permission scopes. Narrowing — or widening — what the
  token can do is a different change with a different blast radius; this
  feature narrows what the agent can reach. If the App token cannot read the
  logs FR-018 stages, the remedy here is the loud, reported failure FR-019
  requires, not a token change.
- A runtime refusal in the published stages of a consumer-supplied tool list
  (Question 2, Option B) and an adopter-facing warning in `docs/adoption.md`
  (Option C). The rule binds shipped defaults only (FR-014).
- Errata against merged specs' `spec.md`/`plan.md`/`research.md`/`tasks.md`
  (repository rule); only live contracts and live docs are corrected.

## Open Questions

All three `[NEEDS CLARIFICATION]` markers were answered on lifecycle issue
#759 and are recorded in [Clarifications](#clarifications) above.

One question raised by the 2026-09-30 maintainer review is open for the
owner: what happens to `pr-conversation.classify`'s three read-only `gh`
grants (`gh pr view`, `gh issue view`, `gh search issues`) under FR-007's
total rule. See the status update.
