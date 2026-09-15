# Feature Specification: One read-only inspection policy for stage tool allowlists

**Feature Branch**: `051-read-only-inspection-policy`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description (GitHub issue #338): "Stage tool allowlists lag what agents are told to do: nine denied-tool occurrences on #266 across plan, intake, clarify and implement need one read-only inspection policy"

## Overview

The watchdog's `denied-tool` fingerprint (#266, open since 2026-08-25,
`disposition:confirmed`) has collected nine occurrences across four stages.
In every one of them the agent was doing what it had been told to do — by its
own stage prompt, or by this repository's `CLAUDE.md` — and the stage's
`default-allowed-tools` list did not cover the *shape* the command was typed
in. None of the denied commands wrote anything; all nine were read-only
inspection.

Occurrences as recorded on #266:

| Stage | Runs | Denied commands |
|---|---|---|
| plan | 32849659993, 34160921063 (23 denials), 34664853479 | `cd .github/workflows && for …` loops; pipelines of allowed primitives (`grep … \| sort \| tail`, `ls … \| grep`); `gh api repos/{owner}/{repo}/pulls/224`; `gh auth status`; `printenv SPECIFY_FEATURE_DIRECTORY` |
| intake | 34666884809, 34799900127 | `printenv SPECIFY_FEATURE_DIRECTORY`; `python .github/scripts/run-local-gates.py` (three times) |
| clarify | 34791425104, 34802081261 | `gh issue view N --json comments --jq … > /tmp/q.md` (redirect); `gh api repos/<repo>/issues/comments/N --jq '.body'` |
| implement | 34709026525 | `git stash; actionlint … ; git stash pop` (compound) |

Each occurrence on its own looks like a one-line allowlist patch. Together
they say something structural: **the allowlists have no owner-level policy for
what a read-only inspection is allowed to look like**, so every new prompt
instruction ships a denial first and an allowlist patch second — and the patch
lands on whichever stage happened to hit it. `printenv
SPECIFY_FEATURE_DIRECTORY` was denied in intake and in plan; today it is
granted in `plan.*` and `tasks.*` and still absent from `intake`. Plan's list
grew `grep/head/tail/sort/uniq/wc/cut` one primitive at a time in response to
denials; intake and clarify never received them.

Three distinct shapes sit behind the nine occurrences, and none is settled by
a one-line edit:

1. **Compound, piped and redirected commands built from allowed primitives.**
   Claude Code matches each command in a pipeline or `;`/`&&` chain
   separately, so `grep … | sort` is denied whenever `sort` is unlisted, and
   any `> file` redirect or `cd … &&` prefix is denied regardless of what the
   list contains. Chasing this with more primitives is unbounded; so the
   decision (#338) is to do both — standardise the primitive set every
   read-capable stage carries, *and* tell the agent, in the one place that
   already describes its tooling, to use the built-in Read/Grep/Glob tools and
   single commands for anything multi-step.
2. **`gh api` reads.** Agents reach for `gh api` when no `gh <noun> view`
   exposes the field they need — a single comment body, a PR's raw JSON.
   `Bash(gh api:*)` cannot be narrowed to GET (`--method POST` and `-f` live
   under the same prefix), and the App token in clarify and intake can write
   issues. The decision (#338) is that no stage gains `gh api`: clarify's
   comment bodies are staged deterministically by the workflow the way intake
   already stages them, and plan's PR read is met by the `gh pr view --json`
   grant it already holds.
3. **Running the repository's own gate suite.** `CLAUDE.md` tells every agent
   that reads it to run `python .github/scripts/run-local-gates.py` before
   pushing. Intake tried three times and was denied three times; implement
   will do the same. The decision (#338) is that the suite runs in implement
   only — one more read-only self-check at roughly three and a half minutes
   against a cycle that runs far longer, turning a CI round trip into an
   in-cycle fix — under an explicit timeout, with a preflight for its
   container prerequisites, and with `CLAUDE.md`'s instruction scoped by
   audience so no spec-writing agent is told to do what its own allowlist
   forbids.

This feature replaces nine reactive patches with one policy, expressed in the
places that already own this material: the per-stage default tool-list table
in `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (Gate 27), the
rendered tooling statement produced by `wing-commander-tool-args` (Gate 21),
and — where the answer is "the agent should not do this" — the stage prompts
and `CLAUDE.md`. It also lands the deterministic leftovers that need no
decision, and puts a gate behind the rule so the next prompt instruction that
outruns its allowlist fails CI instead of burning a run.

#266 remains the fingerprint sink for new occurrences until this change ships.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A read-only inspection succeeds in the shape the agent was taught (Priority: P1)

A stage agent needs to look at something in the checkout — which workflows
carry a given string, how many call sites a composite has, what the last three
commits touched. It reaches for the shape its prompt and the rendered tooling
statement taught it, and that shape is either permitted by the stage's
composed allowed list or is explicitly named in the prompt as the wrong way to
do it, with the right way given in the same sentence. No turn is spent
discovering a denial.

**Why this priority**: This is the shape behind the majority of the recorded
denials (the 23-denial plan run is almost entirely this), and it is the one
that recurs every time a prompt gains an instruction. It is also the shape
whose fix has two halves that must ship together: standardising the primitive
set closes the per-stage drift, and the tooling statement's shape rule closes
the compound/piped/redirected family that no list can close.

**Independent Test**: Replay the recorded denied commands of this shape
(`cd .github/workflows && for …`, `grep … | sort | tail`, `ls … | grep`,
`git stash; actionlint …; git stash pop`) against each stage's composed
allowed list and against that stage's rendered prompt. Every one must either
be permitted, or be covered by a prompt sentence that names a permitted
alternative.

**Acceptance Scenarios**:

1. **Given** a read-capable stage, **When** its composed allowed list is
   inspected, **Then** the inspection primitives the policy names are present
   in that stage's list, with no stage silently missing one that a peer stage
   has.
2. **Given** a stage prompt, **When** the agent reads the tooling statement,
   **Then** the statement tells it how a multi-step inspection is expected to
   be performed under this run's permissions, rather than leaving the agent to
   infer it from a list of primitives.
3. **Given** a command that chains, pipes into an unlisted primitive, or
   redirects, **When** an agent considers it, **Then** the prompt has already
   stated that this shape is denied whole and named the alternative, so the
   agent does not spend a turn on it.
4. **Given** a new stage or a new internal agent step is added later,
   **When** CI runs, **Then** a gate fails if that step's default allowed list
   omits the policy's inspection set without recording why.

---

### User Story 2 - The reads that drove `gh api` have a sanctioned route (Priority: P2)

An agent needs a field GitHub's `gh <noun> view` verbs do not surface — the
body of one specific issue comment (clarify), the raw JSON of a pull request
(plan). Instead of typing `gh api` and being denied, it has the route this
repository has decided on: no stage gains `gh api`, so the field is delivered
to the agent another way — staged into the checkout by the workflow for
clarify, read through the `gh pr view --json` grant plan already holds — and
the prompt says so.

**Why this priority**: Two of the four stages hit this, and one of them
(clarify) hits it while holding an App token that can write issues — so the
answer carries a security decision, not just an ergonomics one. It is P2
because the affected reads are narrower than User Story 1's.

**Independent Test**: For each recorded `gh api` denial, confirm the field it
was after is obtainable by that stage through a route the stage's own prompt
names, and that no stage's write surface widened without the widening being
recorded in the Gate 27 table and the security-policy record.

**Acceptance Scenarios**:

1. **Given** clarify needs the body of a specific issue comment, **When** it
   follows its prompt, **Then** it obtains that body without `gh api` and
   without a shell redirect.
2. **Given** a stage that is not granted `gh api`, **When** its rendered
   tooling statement is read, **Then** `gh api` is absent from the permitted
   commands and the agent is not left guessing.
3. **Given** `watchdog.diagnose`, which reaches `gh api` through its
   pre-existing wider `Bash(gh:*)` grant, **When** the per-stage table is
   read, **Then** that grant is recorded as pre-existing and untouched by this
   change, and no other stage's row shows a `gh api`-equivalent grant.

---

### User Story 3 - No agent is instructed to run what its allowlist forbids (Priority: P3)

`CLAUDE.md`'s "Before pushing" section is read by every agent that works in
this checkout, including the intake agent that only ever writes a spec
directory. After this change the agent that is told to run the gate suite —
implement — can run it, and the spec-writing agents are no longer addressed by
the instruction at all.

**Why this priority**: One recorded occurrence (three denials in one intake
run), but it is the clearest instance of the underlying defect — a repository
instruction and a permission list disagreeing — and the cheapest to prove with
a gate.

**Independent Test**: Enumerate the commands that repository-level guidance
instructs a pipeline agent to run, resolve each against the composed allowed
list of every stage whose agent reads that guidance, and assert no
instruction/permission mismatch remains.

**Acceptance Scenarios**:

1. **Given** the intake, clarify, plan or tasks agent reads repository
   guidance, **When** it reaches the "before pushing" material, **Then** that
   material is scoped so it does not address that agent, and the agent spends
   no turn attempting the gate suite.
2. **Given** the implement agent, **When** it is told to verify its change
   before pushing, **Then** it is permitted to run the gate suite, the run is
   bounded by an explicit timeout, and a missing container prerequisite leaves
   a note in the stage summary instead of a denial or a failed stage.
3. **Given** repository guidance later gains a new mandated command, **When**
   CI runs, **Then** a gate fails if that command is not permitted in the
   stages whose agents are told to run it.

---

### Edge Cases

- A consumer of the reusable pipeline sets `extra-allowed-tools` or
  `allowed-tools-override`. The policy describes this repository's *defaults*;
  an override that drops an inspection primitive is the consumer's choice and
  must not fail their run, but the rendered tooling statement must still
  describe what they actually permit (Gate 21's existing contract).
- A stage whose allowed list is deliberately read-only and minimal
  (`implement.post-progress-comment`, `finalize`, `cleanup`, `rebase`,
  `watchdog.diagnose`, `pr-conversation.classify`). The policy must say
  whether "read-capable" means "does file inspection as part of its job" or
  "has any Bash grant at all", so these rows are not widened by accident when
  the inspection set is standardised (FR-003, FR-005).
- `watchdog.diagnose` already carries the broad `Bash(gh:*)` grant, which
  covers `gh api` today. The policy's "no stage gains `gh api`" sentence
  (FR-006) is about grants this change makes; `watchdog.diagnose`'s wider
  prefix is recorded as pre-existing rather than removed or re-granted here
  (FR-008).
- `intake`'s prompt states "the variable is already exported for you" about
  `SPECIFY_FEATURE_DIRECTORY`, but `intake.yml` sets no such variable for the
  agent step — so granting `Bash(printenv SPECIFY_FEATURE_DIRECTORY)` alone
  would turn a denial into an empty result and a second wasted turn.
- `plan` and `tasks` grant `Bash(gh auth status)` while all four
  shell-constraint prompt blocks tell the agent that `gh auth status` will not
  explain a denial. Grant and prose point in opposite directions.
- A denial that is genuinely correct — the agent tried something it should not
  do (`git stash` in implement). The policy must leave room to say "denied on
  purpose" so such an occurrence is closed as working-as-intended rather than
  patched into the list.

## Requirements *(mandatory)*

### Functional Requirements

**The policy itself**

- **FR-001**: The repository MUST carry one written read-only inspection
  policy that states, for every agent-running stage and internal agent step,
  what a read-only inspection is permitted to look like. It MUST live in the
  record that already owns the per-stage lists
  (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`, the source
  Gate 27 compares against), with every other mention pointing at it rather
  than restating it.
- **FR-002**: The policy MUST state explicitly that each command in a
  pipeline or `;`/`&&` chain is matched separately, and that output redirects
  and `cd … &&` prefixes are denied regardless of list contents — so the
  reason a shape fails is recorded once, not rediscovered per stage.
- **FR-003**: The policy MUST standardise the shell inspection primitives:
  it names one inspection set — the set `plan.*`/`tasks.*` carry today
  (`grep`, `head`, `tail`, `sort`, `uniq`, `wc`, `cut`) — and every
  read-capable stage's default allowed list MUST either contain that whole set
  or record in its table row why it does not. `intake`, `clarify` and
  `implement` therefore gain the primitives `plan` already had, with the set
  named in the Gate 27 table so a stage cannot silently miss one a peer has.
- **FR-004**: The rendered tooling statement (the `shell-commands` output of
  `wing-commander-tool-args`, which every stage prompt embeds) MUST convey the
  policy's guidance on inspection shape — both FR-002's rule that chains,
  pipes into an unlisted primitive, redirects and `cd … &&` prefixes are
  denied whole, and the expectation that multi-step inspection uses the
  built-in Read/Grep/Glob tools and single shell commands. Standardising the
  primitive set (FR-003) does not close the compound/piped/redirected family,
  so both halves ship together. The guidance reaches the agent from the same
  single home as the permitted-command list and cannot drift per workflow.
- **FR-005**: The policy MUST define "read-capable stage" precisely enough
  that the deliberately-minimal read-only steps
  (`implement.post-progress-comment`, `finalize`, `cleanup`, `rebase`,
  `pr-conversation.classify`) are not widened as a side effect of applying it.
  FR-003's standardisation makes this definition load-bearing: it is what
  decides which table rows gain the inspection set.

**`gh api` and the reads behind it**

- **FR-006**: No stage gains `gh api`. Each stage's row MUST record that
  decision together with the sanctioned route for the reads that drove agents
  to it: clarify's issue-comment body MUST be staged for the agent
  deterministically by the workflow, the way `specs/029-intake-issue-comments`
  already stages comments for intake, and plan's pull-request read MUST be met
  by the `gh pr view --json` grant plan already holds. `Bash(gh api:*)` cannot
  be bounded to GET and clarify's and intake's App token can write issues, so
  granting it would widen a write surface for reads that already have a
  documented path (Constitution V).
- **FR-007**: Because FR-006's answer is "not granted", the affected stage
  prompts (clarify, plan) MUST name the sanctioned route in the same sentence
  that tells the agent what it needs, so the agent never reaches the `gh api`
  attempt.
- **FR-008**: No stage's write surface widens in this change.
  `watchdog.diagnose` continues to reach `gh api` through its pre-existing,
  wider `Bash(gh:*)` grant; the change MUST record in the per-stage table that
  this is pre-existing and untouched, not a grant made here. Should a later
  change add a `gh api`-equivalent grant anywhere, that grant's write exposure
  under that stage's token MUST be recorded in the same change, in the
  per-stage table and in the repository's security-policy record.

**The gate suite instruction**

- **FR-009**: The implement agent — and only the implement agent — MUST be
  permitted to run `python .github/scripts/run-local-gates.py`, under an
  explicit timeout, as a pre-push self-check alongside the
  actionlint/yamllint/shellcheck checks it already runs. No other stage agent
  is granted it.
- **FR-009a**: The gate-suite run MUST be preceded by a preflight that
  confirms its prerequisites (pyyaml, jq, actionlint) are present in the
  implement container. When a prerequisite is missing the run MUST degrade to
  a note in the stage's summary — never a denial and never a stage failure —
  so a container that has drifted costs a line of output rather than a cycle.
- **FR-009b**: `CLAUDE.md`'s "Before pushing" section MUST be scoped by
  audience so that the spec-writing agents (intake, clarify, plan, tasks) are
  not addressed by it, and the implement agent and human/local sessions are.
  The scoping lives in `CLAUDE.md` itself, not restated per stage prompt.
- **FR-010**: Repository guidance that instructs an agent to run a command
  MUST be reconcilable against that agent's composed allowed list — every
  command repository guidance mandates for a stage agent is permitted for
  every stage whose agent reads that guidance.

**Deterministic leftovers (no decision needed)**

- **FR-011**: `intake`'s default allowed list MUST grant
  `Bash(printenv SPECIFY_FEATURE_DIRECTORY)`, matching `plan.*` and `tasks.*`,
  and the change MUST confirm that parity rather than assume it.
- **FR-012**: `intake`'s prompt MUST NOT claim that
  `SPECIFY_FEATURE_DIRECTORY` is exported to the agent unless the intake job
  exports it; the claim and the runtime MUST agree (either the export is added
  alongside FR-011's grant, or the sentence is scoped to the stages that do
  export it).
- **FR-013**: The `Bash(gh auth status)` grant in `plan.*`/`tasks.*` and the
  prompt sentence telling agents that `gh auth status` cannot explain a denial
  MUST be reconciled — one of the two goes, and the table records which.

**Keeping it true**

- **FR-014**: The change MUST update the Gate 27 per-stage table in the same
  change as any default-list edit (the existing rule), and MUST extend Gate
  21's cases so the tooling statement's new guidance is covered by a mutation
  check, not merely written once.
- **FR-015**: A gate MUST fail CI when a stage's default allowed list drifts
  from the policy — a new agent step that omits the inspection set without
  recording an exception, or repository guidance that mandates a command a
  stage agent cannot run (FR-010). The gate is the rule's single home, added
  to the nearest existing gate rather than as a free-standing check where one
  already covers the artifact.
- **FR-016**: The change MUST record, per recorded occurrence on #266, which
  decision resolves it — including occurrences resolved as
  "denied on purpose" (`git stash` in implement) — so the fingerprint can be
  closed against evidence rather than closed as stale.
- **FR-017**: No consumer-visible behaviour beyond the documented list edits
  may change: a consumer who sets none of `extra-allowed-tools`,
  `extra-disallowed-tools`, `allowed-tools-override`,
  `disallowed-tools-override` gets exactly the lists the table states
  (the existing SC-005 guarantee of specs/026-configurable-tool-lists).

### Key Entities

- **Read-only inspection policy**: the owner-level statement of what shape an
  inspection command may take in an agent stage — which primitives, which
  compound forms are impossible, when the built-in tools are expected instead
  of a shell. One home; everything else points at it.
- **Per-stage default tool list**: the `default-allowed-tools` /
  `default-disallowed-tools` literals at each `wing-commander-tool-args` call
  site, mirrored in the stage-interfaces table that Gate 27 compares against.
- **Rendered tooling statement**: the `shell-commands` sentence composed from
  a run's effective lists and embedded in the stage prompt; the only
  per-run-accurate description of permissions the agent sees (Gate 21).
- **Repository guidance**: `CLAUDE.md` plus the stage prompts — what the agent
  is told to do, as distinct from what it is permitted to do. The defect is
  the gap between the two.
- **Denied-tool occurrence**: one recorded denial on the #266 fingerprint,
  carrying a stage, a run, and a command; the unit this feature is measured
  against.

## Success Criteria *(mandatory)*

- **SC-001**: All nine recorded occurrences on #266 are resolved by a named
  decision — permitted, routed to a sanctioned alternative the prompt states,
  or recorded as denied on purpose. Zero occurrences left without a
  disposition.
- **SC-002**: For every agent-running stage, every command that repository
  guidance or that stage's prompt instructs the agent to run is permitted by
  that stage's composed default allowed list. Count of mismatches: zero,
  verified mechanically rather than by reading.
- **SC-003**: A gate fails when the policy is violated: introducing a stage
  step that omits the inspection set, or adding a mandated command a stage
  agent cannot run, turns CI red. Demonstrated by a mutation check that
  reintroduces each defect, in the style of the existing gates.
- **SC-004**: An agent reading only its rendered tooling statement and prompt
  can tell, before typing a command, whether a piped or chained inspection
  will be permitted — verified by the statement naming the rule, not by the
  agent inferring it from a primitive list.
- **SC-005**: Across the first 20 pipeline runs after the change ships, no new
  `denied-tool` occurrence is attributable to the three shapes this feature
  addresses (compound/piped/redirected inspection, `gh api` reads, the gate
  suite instruction).
- **SC-006**: A consumer who sets none of the four tool-list inputs receives
  the lists exactly as documented, with the stage-interfaces table matching
  every call site byte-for-byte.
- **SC-007**: #266 can be closed with the evidence of SC-001 quoted on it, and
  the closing comment names the policy's home for the next reader.
- **SC-008**: The implement stage's gate-suite self-check either completes
  within its stated timeout or leaves a summary note naming the missing
  prerequisite; in neither case does it produce a denied-tool occurrence or
  fail the stage. Demonstrated with the prerequisite absent and present.

## Assumptions

- The per-stage table in
  `specs/010-reusable-pipeline/contracts/stage-interfaces.md` remains the
  single home for default tool lists, and Gate 27 remains the check that keeps
  it honest; this feature adds policy text to that record rather than opening
  a new one.
- `wing-commander-tool-args`'s `shell-commands` output remains the single home
  for per-run tooling prose; guidance that must reach every stage agent goes
  there rather than being pasted into each workflow's prompt, consistent with
  "Shared logic has exactly one home".
- The "Shell constraints in this headless run" prompt block that currently
  appears in `intake.yml`, `plan.yml`, `tasks.yml` and `implement.yml` is
  in-scope material for this feature to the extent the policy changes what it
  says; whether those four copies are consolidated is a design question for
  the plan stage, not a requirement here.
- No stage gains a write capability it does not have today. Everything this
  spec grants is read-only inspection; the one decision that could have
  widened a write surface — `gh api` under a writable token — was answered
  "no stage gains it" on #338 and is held to that by FR-006 and FR-008.
- The recorded run IDs and denial counts come from #266's thread and are taken
  as given; this feature does not re-derive them from Actions logs.
- `#266` stays open as the fingerprint sink until this change ships, then is
  closed against SC-001's evidence.

## Out of Scope

- Changing the watchdog's `denied-tool` detection, its fingerprinting, or its
  false-positive filters. This feature reduces the denials; it does not touch
  the collector.
- The turn-ceiling and cost behaviour of any stage, except the explicit
  timeout FR-009 puts around implement's gate-suite run.
- Consumer-facing configuration surface: no new `extra-*`/`*-override` inputs
  are introduced.
- Any allowlist change motivated by something other than the recorded
  occurrences and the policy that covers them.

## Dependencies

- `specs/010-reusable-pipeline/contracts/stage-interfaces.md` and Gate 27
  (`verify-stage-tool-lists.py`) — the per-stage table and its check.
- `specs/026-configurable-tool-lists` — the `extra-*`/`*-override` composition
  semantics the defaults compose under, and the SC-005 no-change guarantee.
- `specs/037-rendered-tooling-list` and Gate 21
  (`verify-tooling-statement.py`) — the rendered tooling statement contract.
- `specs/029-intake-issue-comments` — the existing pattern of staging issue
  comments deterministically for an agent, a candidate route for FR-006.
- `specs/011-security-policy` — where a widened write surface, if any, is
  recorded.
- Issue #266 — the fingerprint this feature closes.
