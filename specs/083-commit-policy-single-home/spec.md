# Feature Specification: Commit-Message-Policy Prompt Text Has One Home

**Feature Branch**: `083-commit-policy-single-home`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #605 (routed from the board loop, issue #458;
originating review finding on PR #440): "implement.yml's
commit-message-policy paragraph has no single home (3-way duplicate with
clarify.yml)".

## Context

`implement.yml` runs the implement stage twice from two separate agent
steps — a *cycle* attempt and a *retry* attempt — each with its own
`prompt: |` block. PR #440 added a commit-message-policy paragraph telling
the agent how to write a multi-line commit message: compose it with the
Write tool to a named scratch file under the runner temp directory, then
`git commit -F` that path; never a heredoc or `$(cat …)` on the command
line (the permission layer denies both); never a path under the repository
(inside `.git/` it is denied outright, anywhere else it would be swept
into the commit).

That paragraph was pasted into both prompts. Its closing rationale clause —
why a scratch file must not live under the repository — is also carried,
near-verbatim, by `clarify.yml`'s own prompt, where it governs a PR-body
file rather than a commit message. Three copies, two files, one idea.

The usual consolidation tools in this repository do not reach it:

- A canonical-comment pointer (`-- see clarify.yml`) cannot work. This is
  agent-facing prompt text, not a human-facing `#` comment. Each agent step
  is a separate process whose only knowledge of the policy is the text
  handed to it; replacing that text with a pointer to another file deletes
  the instruction instead of redirecting it.
- Gate 47 (`verify-comment-canonical-pointers.py`) is scoped to `#` YAML
  comments and cannot see prompt text at all.
- Gate 60 (`verify-single-home-idioms.py`) keys on a closed list of named
  idioms in `DECLARED_HOMES`; this paragraph is not one of them, and every
  existing check matches shell/jq fragments rather than prose.

`implement.yml` already demonstrates the mechanism that does work for
cycle/retry-shared prompt content: the `Tooling:` sentence is composed once
by the `wing-commander-tool-args` composite and interpolated at each call
site (`steps.tool-args-cycle.outputs.shell-commands` /
`steps.tool-args-retry.outputs.shell-commands`), never hand-copied.

The review that filed this also recorded a dissent worth weighing: the
cycle and retry prompts in `implement.yml` are *already* extensively
duplicated as an accepted pattern, so singling out this one paragraph may
buy little. The dissent is why this arrives as a spec rather than a
mechanical extraction PR — the owner decides whether, and how far, to act.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A policy fix lands once and reaches both attempts (Priority: P1)

A maintainer discovers the commit-message policy is wrong or incomplete —
a newly denied shell form, a changed scratch-file rule, a clearer
explanation. They edit the policy in exactly one place, and both the cycle
agent and the retry agent receive the corrected text on the next run.

**Why this priority**: This is the defect. Today the same fix must land in
two places with nothing failing if only one is edited, so a retry attempt
can run under a policy its cycle attempt no longer follows — and the retry
is precisely the attempt that runs after something already went wrong.

**Independent Test**: Change the policy text at its single home. Render or
inspect both agent prompts and confirm both carry the change, with no
second edit.

**Acceptance Scenarios**:

1. **Given** the policy text lives at one declared home, **When** a
   maintainer edits it there, **Then** both the cycle and the retry prompt
   carry the edited text, and no other file needed editing.
2. **Given** the consolidation has landed, **When** the cycle and retry
   prompts are compared, **Then** each still names its own distinct scratch
   file, and the retry still carries its "use a name distinct from the
   cycle step's scratch file" instruction.
3. **Given** the consolidation has landed, **When** the full PR-time gate
   suite runs, **Then** it passes — including the gates that read stage
   prompt text and scratch-file paths.

---

### User Story 2 - A third paste is caught by a gate, not by a reader (Priority: P2)

Someone adds a new stage, or a new attempt inside an existing stage, and
pastes the policy paragraph into it. A gate fails the PR and names the
single home.

**Why this priority**: CLAUDE.md's own rule — "a rule with no gate behind
it lasts until the next session". Consolidating without a check leaves the
repository one paste away from the state this issue describes, and the two
gates that would normally catch it are both structurally blind to prompt
prose.

**Independent Test**: Paste the policy paragraph into a third workflow or
composite, run the gate suite, and observe a failure that names the
declared home. Remove the paste and observe the suite pass.

**Acceptance Scenarios**:

1. **Given** the policy has a declared home, **When** a copy of it appears
   in any other workflow or composite action, **Then** the gate suite fails
   with a message naming the file, the line, and the declared home.
2. **Given** a copy that the owner has deliberately accepted, **When** it is
   registered as a waiver with a reason and an issue reference, **Then** the
   suite passes, and it fails again if the waiver later matches nothing.
3. **Given** the gate exists, **When** its self-test runs, **Then** it
   demonstrates that the check can actually fail on a synthetic third paste
   — not merely that it passes on the current tree.

---

### User Story 3 - The clarify.yml overlap ends in a written decision (Priority: P3)

A reader comparing `clarify.yml`'s scratch-file rationale with the
implement policy can tell, from the repository itself, whether the two are
deliberately separate or accidentally divergent.

**Why this priority**: The overlap is partial — `clarify.yml` governs a PR
body, `implement.yml` governs a commit message — so it is a judgement call,
not a mechanical merge. Left unrecorded, the next reviewer re-opens the
same question. Lowest priority because the fleet behaves correctly either
way.

**Independent Test**: Read the artifacts a maintainer would reach for (the
workflow text and the gate's declared homes) and determine, without
guessing, whether `clarify.yml` shares the source.

**Acceptance Scenarios**:

1. **Given** the decision is "share", **When** the shared source is edited,
   **Then** `clarify.yml`'s prompt carries the change too.
2. **Given** the decision is "stay separate", **When** a reader inspects
   `clarify.yml`'s clause, **Then** a recorded reason explains why it is not
   the same text, and the gate does not flag it as an unexplained copy.

### Edge Cases

- **The two implement copies are not byte-identical.** Each names its own
  scratch file (`…-cycle.txt` vs `…-retry.txt`), and the retry copy carries
  two extra sentences the cycle copy does not. Any single source must admit
  a per-site value and a per-site addendum, or the retry loses an
  instruction it needs. (The originating issue describes the paragraph as
  pasted byte-identical; the tree shows near-identical with a per-site
  parameter.)
- **The clarify overlap is partial, not total.** Only the "not under the
  repository, because `.git/` is denied and anything else is swept into the
  commit" rationale is common; the surrounding instruction differs in
  subject (PR body vs commit message) and in the tool that consumes the
  file.
- **A gate that keys on exact prose is brittle.** Reflowing the paragraph
  across different line widths, or re-wrapping it inside a different YAML
  indentation, must not let a copy slip past — nor should an ordinary,
  unrelated mention of `git commit -F` trip it.
- **Prose must not travel through a job-level output.** Gate 49 forbids a
  published stage lifting free prose into a job output; whatever mechanism
  is chosen has to stay clear of that path.
- **The retry runs after a failure.** Whatever mechanism supplies the text
  must be available to the retry step even on the paths where the cycle
  attempt failed, so the retry never receives an empty policy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The commit-message-policy text MUST have exactly one home in
  the repository, from which every site that needs it draws at run time.
- **FR-002**: Both `implement.yml` agent prompts (cycle and retry) MUST
  obtain the policy from that single home rather than from a hand-written
  copy.
- **FR-003**: The single home MUST support a per-site scratch-file value,
  so the cycle and retry attempts continue to name different files.
- **FR-004**: The retry site MUST continue to convey its additional
  instruction that its scratch file be named distinctly from the cycle
  step's, since a stale cycle file may survive into a session that never
  read it.
- **FR-005**: The policy text each agent receives MUST remain semantically
  equivalent to today's text: compose multi-line messages with the Write
  tool to a named runner-temp path, commit with `-F` against that path, no
  heredoc or `$(cat …)` on the command line, no path under the repository.
- **FR-006**: The mechanism MUST NOT carry the policy prose through a
  job-level workflow output.
- **FR-007**: A gate MUST fail when the policy text appears at any site
  other than its declared home, naming the offending file, the line, and
  the declared home.
- **FR-008**: That gate MUST tolerate benign reformatting of the text it
  guards (line re-wrapping, indentation changes) without either missing a
  real copy or flagging unrelated text that merely mentions committing.
- **FR-009**: That gate MUST carry a self-test demonstrating it fails on a
  synthetic third copy and passes on a clean tree, in the style of the
  existing single-home gate.
- **FR-010**: Deliberate exceptions MUST be expressible as registered
  waivers carrying a reason and an issue reference, and a waiver that no
  longer matches anything MUST fail the gate.
- **FR-011**: The single home's mechanism MUST be one already used by this
  repository for shared prompt content, or a documented extension of one;
  it MUST NOT introduce a second, parallel way of sharing prompt text.
- **FR-012**: `clarify.yml`'s overlapping scratch-file rationale MUST end
  in a recorded decision — either drawing from the same source, or carrying
  a written reason for remaining separate. [NEEDS CLARIFICATION: Does
  clarify.yml's clause consume the same shared source, stay separate with a
  recorded reason, or get reworded so the overlap no longer exists?]
- **FR-013**: The mechanism holding the single home MUST be chosen
  deliberately. [NEEDS CLARIFICATION: Which mechanism holds the policy — a
  job-level `env:` var in implement.yml (contained, but a third mechanism
  in the fleet), a new output on an existing composite such as
  wing-commander-tool-args (reuses the proven cycle/retry pattern, but
  widens a published composite's surface), a new dedicated composite
  (cleanest boundary, most new plumbing), or no extraction at all with only
  a detection gate added?]
- **FR-014**: The blast radius of the consolidation MUST be bounded.
  [NEEDS CLARIFICATION: Does this change cover only the commit-message-policy
  paragraph, or does it also address the wider cycle/retry prompt
  duplication in implement.yml that the dissenting review view describes as
  an accepted pattern?]
- **FR-015**: The full PR-time gate suite MUST pass after the change,
  including the gates that read stage prompt text, tool statements, and
  runner-temp scratch-file paths.

### Key Entities

- **Commit-message policy**: The unit of prose being consolidated — the
  instruction telling an implement-stage agent how to author a multi-line
  commit message and where its scratch file may live.
- **Policy home**: The one location the policy text is authored in, and
  from which every consuming prompt draws it at run time.
- **Consuming site**: An agent prompt that must receive the policy — today
  the implement cycle prompt and the implement retry prompt, and possibly
  the clarify prompt depending on FR-012.
- **Per-site scratch file**: The runner-temp path each consuming site names,
  which must stay distinct between cycle and retry.
- **Single-home check**: The gate entry that fails when the policy appears
  outside its declared home, together with its waiver register and
  self-test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Changing the commit-message policy requires editing exactly
  one location; no second file needs a matching edit for the change to
  reach every consuming agent.
- **SC-002**: Both implement-stage attempts receive policy text that is
  semantically identical, differing only in the scratch-file name and the
  retry's additional distinct-name instruction.
- **SC-003**: Introducing a copy of the policy at any new site fails the
  gate suite, and the failure message names the single home — verified by
  the gate's own self-test rather than only by inspection.
- **SC-004**: A reader can determine the repository's position on the
  `clarify.yml` overlap from the repository alone, without reconstructing
  it from issue history.
- **SC-005**: The full PR-time gate suite passes after the change, with no
  gate newly waived to accommodate it.
- **SC-006**: Implement-stage runs after the change continue to produce
  multi-line commit messages through the scratch-file path, with no new
  permission denials attributable to the policy text — confirmed on at
  least one real post-merge run.

## Assumptions

- The policy's *content* is correct as written and is not being revised by
  this feature; only where it lives and how it reaches each agent changes.
- A gate is mandatory, not optional: consolidating without one leaves the
  rule unenforced, per CLAUDE.md. Its most likely home is a new declared
  idiom in the existing single-home gate rather than a brand-new script,
  but the planning stage may place it elsewhere as long as FR-007 through
  FR-010 hold.
- The dissenting view (that this duplication is an accepted pattern and not
  worth fixing) is recorded here for the owner to weigh through FR-013 and
  FR-014; if the owner chooses not to extract, the detection-only option in
  FR-013 keeps something honest in the tree.
- No stage's runtime behaviour changes for any consuming repository — this
  is an internal-instrument change, with no effect on the published stage
  interfaces.
- Verification of the runtime half (SC-006) happens after merge by
  re-driving one implement-stage run, since the behaviour only exists in
  Actions.
