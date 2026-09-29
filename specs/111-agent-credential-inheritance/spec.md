# Feature Specification: The Reviewer Holds No Key — A Read-Only Agent Step Inherits No Write-Capable Credential

**Feature Branch**: `spec-draft/111-agent-credential-inheritance`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #815 — "Agent steps inherit the bot's write token
through `$GITHUB_ENV` (`WC_BOT_TOKEN`), contradicting \"no credential is
reachable\"". Found by the investigation of the lifecycle-review-gate Reviewer
failure (run 36640266298). The `wing-commander-context` composite exports the
minted bot token as `WC_BOT_TOKEN` through `$GITHUB_ENV`; every later step in
the job inherits it, agent steps included. Spec 062's F9 removed `GH_TOKEN`
and `github_token` from the lifecycle review gate's Reviewer so a
prompt-injected reviewer could not reach or echo a write-capable credential,
and the step's comment says none is reachable — but the reviewer process still
inherits one through its environment. The same pattern probably applies to
every agent step that runs after `wing-commander-context` in any stage:
board-loop's reviewer, the implement agents, and others; the extent needs
auditing. The issue routes this to the pipeline because it needs a design
choice between stopping the `$GITHUB_ENV` export, clearing the variable on
agent steps, and splitting context minting so it happens after the agent
steps — each with a different blast radius across the stage workflows — and
any of them also needs a gate, so that no agent step can inherit a
write-capable token. Related: #759 (read-only agents hold no write-capable
`gh` grant) covers a neighbouring surface, and its spec might absorb this.

## Overview

The pipeline's least-privilege story for its read-only agents is written in
two places and they disagree. The tool allowlists are real: the lifecycle
review gate's reviewer, board-loop's reviewer, and a handful of other agent
steps are handed `Read`, `Grep`, `Glob`, a read-only git shim and `cat`, with
no `gh` grant at all. The claim built on top of those allowlists is the part
that does not hold. `lifecycle-review-gate.yml` tells the next reader that
"a prompt-injected reviewer has no credential reachable via its allowed
`Bash(cat:*)` (e.g. reading its own process environment)" — and then the
reviewer's own process environment carries `WC_BOT_TOKEN`, the minted
installation token that can push, comment, label and merge.

Nothing in the allowlist has to change for that to matter. The credential is
not something the agent has to *fetch*; it is already in the environment of
the process the agent runs in, put there one step earlier by a composite whose
job is to make the token survive an agent step. `Read`, `Grep` and `cat` all
reach `/proc/self/environ`. The exposure is not a log line — GitHub masks the
minted token in logs — it is the reviewer's own published output: this
reviewer's findings are extracted from its final message and posted to a
public pull request, so a token folded into a finding leaves the masked
surface entirely.

The relay itself is not a mistake. It exists because the minted App token
lives an hour and some agent steps run longer, so every agent-bearing job
re-mints after each agent step and later steps read the fresh value through
`env.WC_BOT_TOKEN` rather than a stale step output — a design Gate 68
(`verify-post-agent-credential-refresh.py`) actively enforces, down to
forbidding any *other* `$GITHUB_ENV` credential name. That is what makes this
a trade-off rather than a typo: the mechanism that keeps post-agent writes
working is the same mechanism that hands the agent a key it was promised it
could not reach.

This feature closes the gap in the direction the repository already trusts:
name the property, make deterministic code decide which agent steps must hold
it, correct every step that does not, put a gate behind it so the next agent
step cannot quietly reintroduce the inheritance, and make the two comments
that currently overstate the guarantee say something a reader can check.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A read-only agent cannot reach a write-capable credential (Priority: P1)

A maintainer reading the lifecycle review gate's Reviewer step needs the
step's own claim to be true: that a reviewer which has been talked into
misbehaving by content in the diff it is reviewing has no write-capable
GitHub credential available to it — not to push with, and not to copy into
the findings it publishes on a public pull request.

Today that reviewer is the *only* one of the repository's twenty-four agent
steps that passes neither `GH_TOKEN` (env) nor `github_token` (with), and it
is still handed the token through the job environment. Every other agent step
with no `gh` grant in its allowlist — board-loop's triage-propose,
route-propose, fixer, reviewer and review-fixup, the implement stage's
progress-comment agent, finalize's, cleanup's and rebase's agents, and
pr-conversation's act step on its fold route — receives the token twice over:
explicitly *and* by inheritance.

**Why this priority**: it is the defect the issue reports, and it is the one
that makes a shipped security claim false. Until it is fixed, the step comment
and the `#503`/`#513`/F9 rationale behind three separate features describe a
protection the pipeline does not have.

**Independent Test**: for one credential-free agent step, drive a live run and
show that the environment the agent process sees carries no write-capable
GitHub credential, while the job's post-agent steps still complete their own
writes.

**Acceptance Scenarios**:

1. **Given** an agent step classified credential-free, **When** its job runs,
   **Then** the environment the agent process can read carries no
   write-capable GitHub credential, by any name.
2. **Given** that same job, **When** a step after the agent step performs a
   bot write (a comment, a label, a push, a merge), **Then** it still resolves
   a credential minted after the agent step ran, exactly as it does today.
3. **Given** an agent step that legitimately performs GitHub writes of its own
   (the intake, plan, tasks, implement, clarify, watchdog, pr-conversation and
   auto-update agents, whose allowlists carry `gh` grants), **When** its job
   runs, **Then** it still receives its credential and nothing about its
   behaviour changes.
4. **Given** a credential-free agent step, **When** a reader opens the
   workflow at that step, **Then** the comment beside it states the guarantee
   that actually holds and names what enforces it, rather than a guarantee
   that rests on the tool allowlist alone.

---

### User Story 2 - A new agent step cannot reintroduce the inheritance (Priority: P2)

A maintainer adding the pipeline's twenty-fifth agent step, or moving an
existing one, needs the repository to refuse the change if that step is
credential-free by classification and a write-capable credential is reachable
from it — whether it was passed in explicitly or inherited from a step above.

A hand-audited fix is a fix for exactly one reading of the tree. The
inheritance is invisible at the step itself: the step's own YAML shows no
token at all, which is precisely how the current defect survived F9's review,
a maintainer's review of the same step, and every run since.

**Why this priority**: Principle VIII — a correction with no gate behind it
lasts until the next session. Principle IX — whether a given agent step may
hold a credential is judgment that gates a durable action (a write, a
published finding), so it belongs in deterministic code, not a comment.

**Independent Test**: reintroduce the inheritance in a checked-in fixture, by
each route separately, and show the check fails and names the step.

**Acceptance Scenarios**:

1. **Given** a fixture in which a credential-free agent step is handed a
   write-capable credential explicitly, **When** the check runs, **Then** it
   fails, naming the workflow file, the job, the step and the route.
2. **Given** a fixture in which a credential-free agent step passes no token
   but inherits one from a `$GITHUB_ENV` export above it, **When** the check
   runs, **Then** it fails, naming the export site as well as the agent step.
3. **Given** a fixture in which an agent step's mask or clearing is removed,
   renamed, or moved below the agent step, **When** the check runs, **Then**
   it fails.
4. **Given** the shipped tree with every violation corrected, **When** the
   check runs locally and in CI, **Then** it passes, and it runs the same
   subject with the same arguments in both places.
5. **Given** a change that touches a workflow file, **When** the PR gate suite
   runs, **Then** the check is among the gates it runs, reachable through the
   gate registry.

---

### User Story 3 - The audit is recorded, not re-derived by the next reader (Priority: P3)

A maintainer picking up the next credential question needs the extent the
issue asked for to exist as an artifact: every agent step in the repository,
its classification, and — where it keeps a credential — the reason.

The issue says "the extent needs auditing" and names three probable sites. An
audit whose only output is a set of edits leaves the next reader to rediscover
which of twenty-four steps were considered and why the ones that kept a token
were allowed to.

**Why this priority**: it is the durable half of the work, but the pipeline is
safer the moment US1 and US2 land; the record can follow in the same feature
without gating them.

**Independent Test**: read the recorded classification and confirm every agent
step in the tree appears exactly once, and that the check derives the same set
from the tree rather than from the record.

**Acceptance Scenarios**:

1. **Given** the recorded classification, **When** it is compared against the
   agent steps the workflow tree actually contains, **Then** every step
   appears exactly once and no entry names a step that does not exist.
2. **Given** an agent step that keeps a write-capable credential, **When** its
   entry is read, **Then** it names why the step needs one.
3. **Given** a future agent step added without an entry, **When** the check
   runs, **Then** the check still classifies it from the tree and holds it to
   the requirement, rather than skipping it for want of a record.

---

### Edge Cases

- **One step, two allowlists.** pr-conversation's act step chooses between a
  write-capable allowlist and a read-only fold allowlist at run time, on the
  same step. A step whose classification depends on a runtime route cannot be
  resolved statically to one answer; the requirement must state which answer
  a static check takes (the safe one) and what the step does at run time.
- **The credential arrives as an action input.** The model credentials the
  agent step needs (`claude_code_oauth_token`, `anthropic_api_key`, and the
  Bedrock path's AWS credentials) reach the step as `with:` inputs, which
  become environment variables on the same step. No form of this feature can
  remove them; the scope statement must say so rather than imply a
  credential-free environment.
- **Masking versus absence.** Overriding an inherited variable with an empty
  value at the step leaves the *name* present and empty. A check that looks
  for the absence of a name, and a check that looks for an empty value, catch
  different mistakes; the requirement must say which one holds.
- **A credential the agent reads from a file, not the environment.** A job
  that has already configured an authenticated git remote, or a `gh`
  credential file, puts a token where a read-only agent's `Read` tool reaches
  it without touching the environment at all. That is a neighbouring surface;
  this feature must report what it finds there rather than silently treat the
  environment as the whole boundary.
- **The re-mint after the agent step.** The post-agent re-mint calls the same
  composite, which exports the variable again. A mask placed on the agent step
  must not be defeated by the ordering of the re-mint, and a second agent step
  later in the same job must be covered by its own mask, not by the first
  step's.
- **A stage a gate cannot see.** `board-loop.yml` and
  `lifecycle-review-gate.yml` are this repository's own instruments, not
  published stages, and they resolve composites through their own sidecar
  checkouts. The check must reach them on the same terms as the published
  stage workflows, or it covers the wrong half of the tree.
- **An adopter's job that exports its own token.** A consuming repository's
  wrapper can export a credential into the job environment before calling a
  published stage. This repository's gate cannot see that job; the
  requirement must say whether the guarantee is a property of the stage or of
  the job, and document the limit either way.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every agent step in this repository MUST resolve to exactly one
  classification — **credential-bearing** (the step performs GitHub writes of
  its own and needs a write-capable credential) or **credential-free** (it
  does not) — and that classification MUST be computed by deterministic code
  from the workflow tree, never asserted by a code comment alone.

- **FR-002**: A credential-free agent step MUST NOT have a write-capable
  GitHub credential available to the agent process it launches, by any route:
  not as a step-level `env:` entry, not as an action input the step passes,
  and not inherited from the job environment a step above it wrote.

- **FR-003**: The basis of the FR-001 classification MUST be
  [NEEDS CLARIFICATION: derive "credential-free" mechanically from the step's
  resolved tool allowlist containing no `gh` grant; or require each agent step
  to declare its classification explicitly in the workflow, with the check
  cross-examining the declaration against the allowlist; or scope this feature
  to the two reviewer steps whose own comments make the false claim and leave
  the remaining agent steps for a later feature]. The choice sets how many of
  the twenty-four agent steps this feature has to touch and whether a future
  step is classified for free or has to say so.

- **FR-004**: The mechanism by which FR-002 is achieved MUST be
  [NEEDS CLARIFICATION: clear or shadow the relayed variable at each
  credential-free agent step, leaving the job-wide relay intact; or stop
  relaying the token through `$GITHUB_ENV` altogether and pass it explicitly
  to the non-agent steps that need it; or split context minting so the mint
  that produces the relayed value happens after the agent steps rather than
  before]. The first is the smallest change and leaves Gate 68's design
  untouched; the second contradicts the post-agent-freshness design Gate 68
  enforces today and reaches every agent-bearing job; the third reorders steps
  in every stage workflow.

- **FR-005**: The set of credentials FR-002 covers MUST be
  [NEEDS CLARIFICATION: write-capable GitHub credentials only (the relayed bot
  installation token and any other App or installation token); or that set
  plus every other repository-scoped credential an agent step's environment
  can carry, such as the scratch-scoped token]. The model credentials the
  agent step itself requires are out of scope either way (see Out of Scope),
  so a literally secret-free environment is not achievable and must not be
  what the requirement claims.

- **FR-006**: The post-agent credential freshness this repository already
  relies on MUST be preserved: after this feature, every step that performs a
  bot write after an agent step in the same job MUST still resolve a
  credential minted after that agent step ran, and Gate 68's existing checks
  MUST continue to hold.

- **FR-007**: A gate MUST fail a pull request in which a credential-free agent
  step has a write-capable credential reachable, naming the workflow file, the
  job, the step, and the route by which the credential reaches it.

- **FR-008**: That gate MUST cover the inherited route, not only the explicit
  one: a step that passes no token of its own but sits below a step that wrote
  a credential into the job environment MUST fail, and the failure message
  MUST name the export site as well as the agent step.

- **FR-009**: The gate's subject set MUST be derived from the workflow tree —
  every step whose `uses:` names the agent action, in every job of every
  `.github/workflows/*.yml` file — never a hand-maintained list, with a
  checked-in floor of known subjects asserted to be a subset of the derived
  set on every run so that a subject silently disappearing fails the gate.

- **FR-010**: A workflow file the gate cannot parse, a derived subject set of
  size zero, and an unresolvable reference MUST each fail the gate loudly,
  naming the cause, rather than reporting a pass the gate did not earn.

- **FR-011**: Every failure branch the gate ships MUST be exercised by a
  checked-in fixture, including at minimum: the explicit route, the inherited
  route, a removed or relocated mask, and a second agent step in a job whose
  first agent step is correct.

- **FR-012**: The gate MUST be reachable through the repository's gate
  registry, MUST run on changes to the workflow tree it checks, and MUST run
  the same subject with the same arguments locally as in CI.

- **FR-013**: Every agent step that is credential-free by FR-001 and holds a
  write-capable credential today MUST be corrected before the gate is turned
  on. Where a step classified credential-free must nevertheless keep a
  credential, it MUST carry a per-site exempt marker that states the reason,
  and the gate MUST fail on a marker with no reason. No baseline file of
  tolerated sites: a baseline is a second home that drifts and it passes on
  sites already known to be wrong.

- **FR-014**: The two shipped comments that overstate the guarantee — the
  lifecycle review gate's Reviewer step and board-loop's reviewer step — MUST
  be corrected to state what holds after this feature and to name the gate
  that enforces it. The corrected text MUST NOT rest the claim on the tool
  allowlist: any file-reading tool an agent holds reaches its own process
  environment, so `Bash(cat:*)` is an example of the reach, never the extent
  of it.

- **FR-015**: The correction MUST have exactly one canonical home. One agent
  step's comment carries the full rationale and every other credential-free
  agent step points at it, rather than each site restating the rule.

- **FR-016**: The audit the issue asks for MUST be recorded as an artifact
  listing every agent step in the repository with its FR-001 classification,
  and — for each credential-bearing step — the reason it needs a credential.
  Every agent step in the tree MUST appear exactly once, and no entry may name
  a step that does not exist.

- **FR-017**: The audit MUST also report, for each credential-free agent step,
  whether its job leaves a credential reachable through a file rather than the
  environment — an authenticated git remote, a `gh` credential file, a staged
  context file — and record the disposition of each. Reporting is required;
  fixing a file-borne credential is in scope only where the same change that
  satisfies FR-002 removes it.

- **FR-018**: Where a credential-free agent step's classification depends on a
  run-time route (one step, two allowlists), the step MUST be treated as
  credential-free by the gate — the safe answer — and the requirement MUST be
  satisfied on every route that step can take, or the step split so each route
  has its own step.

- **FR-019**: No declared input, secret, or output of a published stage
  workflow or of a composite action under `.github/actions/**` may be removed
  or renamed by this feature. The `wing-commander-context` composite's `token`
  output in particular remains part of the published surface regardless of
  what happens to the job-environment relay.

- **FR-020**: The scope of the guarantee MUST be stated where an adopter can
  read it: whether a credential-free agent step is credential-free as a
  property of the stage alone, or only when the calling job did not export a
  credential of its own, and what this repository's gate can and cannot see
  in an adopter's wrapper.

- **FR-021**: The feature MUST record its relationship to #759 (read-only
  agents hold no write-capable `gh` grant) explicitly — absorbed, adjacent, or
  superseded — so the two do not land overlapping gates on the same subject.

### Key Entities

- **Agent step**: a workflow step that invokes the agent action. The
  repository ships twenty-four across thirteen workflow files. The unit this
  feature classifies and checks.
- **Classification**: credential-bearing or credential-free, computed per
  agent step. The judgment that gates whether a write-capable credential may
  be present.
- **Relayed job credential**: the minted bot installation token as it exists
  in the job environment after the context composite runs — the value every
  later step in the job inherits, agent steps included.
- **Reachable environment**: the set of environment variables the agent
  process can read, which is the step's environment: the job environment, the
  step's own `env:` entries, and the action inputs the step passes.
- **Exempt marker**: a per-site annotation, carrying a stated reason, that
  lets one named credential-free step keep a credential without disabling the
  gate.
- **Audit record**: the per-agent-step classification artifact FR-016
  requires.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero agent steps classified credential-free have a write-capable
  GitHub credential reachable from the agent process, measured by the new gate
  over the shipped tree and confirmed once against a live run of one such step.

- **SC-002**: The new gate fails on each of at least four checked-in fixtures
  — explicit route, inherited route, removed or relocated mask, and an
  uncovered second agent step in the same job — and passes on the shipped
  tree, with identical results locally and in CI.

- **SC-003**: Every agent step the workflow tree contains appears exactly once
  in the audit record, and the record names no step that does not exist.

- **SC-004**: Post-agent writes are unaffected: Gate 68 passes unchanged, and
  one live run of a stage whose post-agent steps write to GitHub shows those
  writes succeeding after the agent step.

- **SC-005**: Credential-bearing agent steps behave exactly as before — no
  stage loses a `gh` capability its prompt actually uses, measured by one live
  run per affected stage whose agent performs a GitHub write.

- **SC-006**: No declared input, secret, or output of a published stage
  workflow or composite action is removed or renamed by the change.

- **SC-007**: A reader who opens either reviewer step can check its claim
  against the same file and the named gate, with no statement that rests on
  the tool allowlist alone.

- **SC-008**: Re-running the audit against `main` after the feature merges
  reproduces the recorded classification with no manual steps.

## Assumptions

- The minted installation token is masked in Actions logs, so the exposure
  this feature closes is the agent's own published output (posted findings,
  comments, commit messages, artifacts), not the run log.
- An agent holding any file-reading tool can read its own process
  environment; the tool allowlist therefore bounds what an agent can *do*
  with a credential, never whether it can *see* one.
- The job-environment relay exists for post-agent credential freshness (specs
  052 and 073) and Gate 68 enforces it. Any option that removes the relay
  changes that feature's design and its gate, and the decision to do so is the
  owner's, not this spec's.
- Agent steps that hold `gh` grants their prompts actually use — intake, plan,
  tasks, implement, clarify, watchdog, pr-conversation's write route, and
  auto-update — are credential-bearing and stay so. This feature does not
  narrow a stage's capability.
- The counts stated here (twenty-four agent steps across thirteen workflow
  files; one step passing no token today; ten steps with no `gh` grant in
  their allowlist plus pr-conversation's fold route) were read from `main` at
  `c80476f` and are the audit's starting point, not its conclusion. The audit
  FR-016 requires supersedes them.
- Specs numbered between the last merged spec and this one are in flight on
  unmerged branches; the plan stage confirms none of them already covers
  #759's surface before this feature lands a gate on it (FR-021).
- The guarantee is scoped to this repository's own workflows and the stages it
  publishes. An adopter's wrapper job can put anything it likes in the job
  environment, and no gate in this repository can see that.

## Out of Scope

- The model credentials an agent step must receive to run at all (the
  Claude OAuth token, the Anthropic API key, the Bedrock path's AWS
  credentials). They arrive as inputs to the action being invoked; removing
  them removes the agent.
- Narrowing or widening any agent's tool allowlist. This feature changes what
  is in an agent's environment, not what the agent is permitted to run.
- The default `GITHUB_TOKEN` and the job `permissions:` blocks that scope it.
- Prompt-injection defences generally — the framing of untrusted content, the
  trust filters on staged context, the findings-extraction contract. This
  feature assumes an agent may be injected and removes one thing an injected
  agent could reach.
- Agent steps in repositories that adopt the published stages, beyond the
  documentation FR-020 requires.
- Retroactive changes to merged specs' spec.md, plan.md, research.md or
  tasks.md, including spec 062's T080 record of F9.
