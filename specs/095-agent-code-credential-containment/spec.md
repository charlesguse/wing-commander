# Feature Specification: Agent-Authored Code Never Runs Beside the Loop's Write Token

**Feature Branch**: `spec-draft/095-agent-code-credential-containment`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #737 — "board-loop: agent-edited code still runs
while the job holds a write token (gate suite, composite actions, reviewer git
tool)" (routed from the board loop, originating issue #590, itself found by the
code review of #583, with two maintainer comments folded in — the #589 code
review's three additional cases and the `.git/hooks` / `.git/config` item).

## Overview

The board loop's `fix` job runs an agent that holds `Write` and `Edit` over the
whole checkout, then commits, pushes, comments and labels with the loop's
GitHub App token. `review` and `readiness` check out the branch that agent
wrote and do the same. The token is not passed step-by-step: the
`wing-commander-context` composite writes it into `$GITHUB_ENV`, so from the
moment it is minted it sits in the environment of **every** later step in the
job.

The repository has spent two features narrowing what that means. #583
established the `$RUNNER_TEMP/wc-pristine` snapshot — a read-only copy of
`.github/scripts` and `.github/schemas` taken from the commit whose
`board-loop.yml` is running, before any agent step — so that post-agent steps
import helpers the agent cannot have edited, with Gate 98
(`verify-board-loop-helper-provenance.py`) holding every `run:` block in those
three jobs to it. Spec 086 did the same for composite actions: every board-loop
job now checks a trusted copy of `github.sha` into `.wc-pristine-repo` and
resolves `uses: ./...` from there, with Gate 104
(`verify-board-loop-composite-provenance.py`) behind it.

Both fixes make post-agent steps *import* trusted code. Neither stops the job
from *executing* code the agent wrote, in an environment that still holds the
token. Four paths remain, and they compose: the first one defeats the other
three.

**1. The gate suite runs the agent's tree, with the token in its env.** The
`Run local gate suite (fixer)` step (`board-loop.yml`) and its review-fixup
twin run `python3 .github/scripts/run-local-gates.py` from the working tree.
That is deliberate and correct — checking the agent's change is the step's
entire purpose, and Gate 98's allowlist carves out exactly this one call. But
the step inherits `WC_BOT_TOKEN` from the job environment, and
`run-local-gates.py` executes every `verify-*.py` the agent's branch carries.
The suite is roughly 440 lines of dispatcher over dozens of gate scripts, any
of which the fixer may legitimately have added or edited — that is what a
gate-shaped fix *is* under Principle X.

**2. Everything the gate suite can do afterwards.** Because it runs as the same
user as every other step, agent code invoked by the gate suite can undo both
existing protections rather than work around them:

- `$RUNNER_TEMP/wc-pristine` and `.wc-pristine-repo` are `chmod -R a-w`, not
  owned by another user. `chmod u+w` and a rewrite are available.
- Appending to `$GITHUB_ENV` or `$GITHUB_PATH` rewrites the environment and the
  `PATH` of **every subsequent step in the job**, including the push, the
  comment, the label and the merge-gate steps.

So the snapshot and the trusted copy protect the steps that run *before* the
gate suite. After it, they hold only if the gate suite runs somewhere the
environment and the filesystem it can reach are not the ones the later steps
use.

**3. A composite's own `run:` step still reaches into the workspace.**
`wing-commander-board-stop-check/action.yml` is resolved from the trusted copy
(spec 086 did that), but the action's `run:` body invokes
`python3 .github/scripts/board_stop_check.py` — a path relative to the
workspace, which in `fix`, `review` and `readiness` is the agent's branch. This
composite is the loop's kill switch re-check before any durable action, and it
is handed the App token. Gate 98 reads `run:` blocks in `board-loop.yml`'s
jobs; it does not look inside composite actions, so nothing fails today.

**4. The agent can plant git hooks and git config.** The fixer's and
review-fixup's tool allowlists grant `Read,Write,Edit` with no `.git/**`
exclusion; only `Bash(git push:*)`, `WebSearch` and `WebFetch` are denied. The
later `git push origin "HEAD:refs/heads/$BRANCH"` steps run after
`wing-commander-refresh-remote` has rewritten the remote to an authenticated
URL, with the token in env, from a config-derived remote and with whatever
`core.hooksPath` says. A `pre-push` hook, or a `core.hooksPath` /
`url.<base>.insteadOf` value written into `.git/config`, would run with that
token or redirect where it is sent. Nothing in the repository currently
constrains either.

### What this feature does not cover (already closed)

Three of the items carried in on issue #590 and its comments have since been
fixed. They are recorded here so this spec's scope is legible and nobody
re-opens them:

- **Composite actions loading from the working tree** — closed by spec 086
  (`.wc-pristine-repo` + Gate 104). Item 3 above is the *residue* of that fix
  (a composite's own `run:` body), not a reopening of it.
- **The reviewer's git tool** — `board_git_read.py` became `git_read.py`, and
  the review job's grant is now rooted at
  `${{ runner.temp }}/wc-pristine/scripts/git_read.py`, the snapshot path.
- **`verify-stage-finding-schema.py`'s trailing-`$` fail-open** — closed by
  #593, which moved the `$` → `\Z` translation into `wc_schema_pattern.py`;
  `verify-stage-finding-schema.py` imports `python_pattern` from it and Gate
  "single home" holds it there.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The gate suite cannot reach the loop's credentials (Priority: P1)

A maintainer wants the step that executes agent-authored code to be the one
step in the loop that holds nothing worth stealing. When `run-local-gates.py`
and the gate scripts on the fixer's branch run, no token that can write to the
repository — the App token, the checkout credential, any `GH_TOKEN` — is
reachable from that process, and the suite's verdict still reaches the steps
that decide whether to push.

**Why this priority**: It is the exposure with the widest blast radius and the
one that makes the other three matter. Every gate script on an agent-written
branch runs unsandboxed with a repository-write credential in its environment.
Closing it alone converts the remaining items from "token theft" into "local
mischief".

**Independent Test**: Place a gate script on a fix branch that prints the value
of every environment variable it can see and writes what it finds to its
output; drive the fix job; confirm the loop's App token does not appear, and
confirm the job still reported the suite's pass/fail correctly and took the
matching branch (push on green, `board:stalled` comment on red).

**Acceptance Scenarios**:

1. **Given** a fix branch whose gate suite reads its own environment, **When**
   the fix job runs the suite, **Then** no credential that can write to this
   repository is present in that environment.
2. **Given** a fix branch whose gate suite fails, **When** the fix job
   completes, **Then** nothing was pushed, no PR was opened, the first failing
   gate was quoted on the issue inside a fence, and `board:stalled` was
   applied — exactly today's behaviour.
3. **Given** a fix branch whose gate suite passes, **When** the fix job
   completes, **Then** the branch is pushed and the PR opened as today.
4. **Given** a fix branch whose gate suite never terminates or crashes the
   runner, **When** the job reaches the push decision, **Then** the absent
   result is treated as a failure, not as a pass.

---

### User Story 2 - Nothing the agent wrote can take over a later step (Priority: P2)

A maintainer wants the trusted snapshot to still be trusted *after* the gate
suite has run. Agent-authored code executed anywhere in the loop must not be
able to rewrite the pristine snapshot or the trusted composite copy, and must
not be able to change the environment, the `PATH`, or the interpreter that
later steps in the job use.

**Why this priority**: It is what makes #583's and #086's guarantees hold for
the whole job instead of its first half. Without it, every later "we import
from the trusted copy" claim in the repository is conditional on the gate suite
having behaved.

**Independent Test**: Place a fixture gate on a branch that (a) `chmod u+w`s and
rewrites a file under the snapshot and (b) appends a variable to `$GITHUB_ENV`
and a directory to `$GITHUB_PATH`; drive the job; confirm both attempts are
either impossible or detected, and that no later step observed the injected
variable or the shadowed executable.

**Acceptance Scenarios**:

1. **Given** agent-authored code that rewrites a file under the pristine
   snapshot, **When** a later step imports that helper, **Then** it imports the
   content of the trusted commit, or the job fails loudly before the durable
   action.
2. **Given** agent-authored code that appends to `$GITHUB_ENV` or
   `$GITHUB_PATH`, **When** a later step in the same job runs, **Then** that
   step's environment and `PATH` are the ones the workflow established, not the
   ones the agent's code wrote.
3. **Given** agent-authored code that overwrites `.wc-pristine-repo`, **When** a
   later step resolves a composite, **Then** it resolves the trusted commit's
   copy or the job fails loudly.

---

### User Story 3 - A composite's own body imports from the trusted copy too (Priority: P3)

A maintainer wants the provenance rule to be a property of the loop, not a
property of `board-loop.yml`'s own YAML. Every composite action the loop calls
from a job whose workspace holds agent-written content must reach its helper
scripts and schemas through the trusted snapshot, and a gate must see inside
composites so the rule cannot be re-broken by moving a `run:` block into one.

**Why this priority**: One concrete instance exists today
(`wing-commander-board-stop-check` → `board_stop_check.py`), and it is the
loop's kill switch. The wider value is closing Gate 98's structural blind spot:
today, moving any `run:` block out of `board-loop.yml` and into a composite
silently exits the gate's field of view.

**Independent Test**: Run the provenance gate against a composite that a
board-loop job calls and that invokes a workspace-relative script; confirm the
gate fails. Repeat with the script invoked from the snapshot; confirm it
passes.

**Acceptance Scenarios**:

1. **Given** the kill-switch re-check running in `fix`, `review` or
   `readiness`, **When** the item's branch carries an edited
   `board_stop_check.py`, **Then** the edited copy is not what decides whether
   the loop stands down.
2. **Given** a composite reached from one of those jobs whose `run:` body calls
   a workspace-relative script, **When** the gate suite runs, **Then** it
   fails and names the composite and the call.
3. **Given** the same composite calling the snapshot copy, **When** the gate
   suite runs, **Then** it passes.

---

### User Story 4 - A planted hook or config value cannot steer the push (Priority: P4)

A maintainer wants the loop's pushes to go where the workflow says, run only
the code the workflow intends, and carry the token only to the intended host.
Neither a hook file nor a repository-, global- or system-level git config value
that the agent could have written may influence a push the loop makes with the
App token.

**Why this priority**: It is the narrowest of the four and needs the agent to
have written to `.git/` specifically, but its payoff is direct token
exfiltration rather than local mischief, and the mitigation is small and
self-contained.

**Independent Test**: Place a `pre-push` hook and a `url.<base>.insteadOf`
entry on a fix branch's `.git/`; drive the fix job through a green gate suite;
confirm the hook did not execute and the push reached the intended remote.

**Acceptance Scenarios**:

1. **Given** a `pre-push` hook planted in the working checkout, **When** the
   loop's push step runs, **Then** the hook does not execute.
2. **Given** a `core.hooksPath` or `url.*.insteadOf` value planted in git
   config, **When** the loop's push step runs, **Then** the push is unaffected
   by it and reaches the intended remote.
3. **Given** the fixer agent, **When** it attempts to write under `.git/`,
   **Then** the write is refused, or the plant is neutralised at push time, or
   both — per the decision recorded against FR-018.

---

### Edge Cases

- **A legitimate gate needs the repository.** Some checked-in gates read the
  git history or call `gh`. If the gate suite loses all credentials, a gate
  that genuinely needs read access to this repository fails. The containment
  must distinguish "cannot write" from "cannot function", and any gate that
  needs a credential must be identified before the containment ships rather
  than discovered by a red board-loop run.
- **The gate suite never returns a verdict.** A hung, killed or timed-out suite
  must be a failure at the push decision, never an absent value that reads as
  green (Principle VIII).
- **The containment itself fails to start.** If the isolated gate-suite
  execution cannot be established at all, the job must fail loudly before any
  durable action, not fall back to running the suite beside the token.
- **A fix PR that edits the containment.** The fixer may legitimately author a
  change to the very steps that contain it. The backstop and the gate must
  treat that as a change like any other and still run the *current* commit's
  containment, not the branch's.
- **The trusted snapshot is already unwritable but the agent runs as root.**
  Any reliance on file permissions alone must state what it assumes about the
  runner's user model, or use a mechanism that does not depend on it.
- **An in-flight board item.** An item whose branch was cut before this feature
  ships reaches the changed jobs afterwards; the change must not hard-fail such
  an item (the failure mode spec 086 named).
- **Self-hosted or container runners.** Adopters run this pipeline on runners
  this repository does not control; anything the containment assumes about the
  runner must hold there or be stated as a constraint.

## Requirements *(mandatory)*

### Functional Requirements

**Containment of agent-authored code**

- **FR-001**: The board loop MUST execute `run-local-gates.py` and the gate
  scripts from a board item's branch in an execution context that holds no
  credential able to write to this repository — not the App token, not a
  checkout credential, not any `GH_TOKEN`.
- **FR-002**: The gate suite's verdict (pass/fail and the first failing gate's
  text) MUST reach the steps that decide whether to push, comment and label,
  and MUST keep today's downstream behaviour on both outcomes.
- **FR-003**: Text the gate suite produces MUST continue to be treated as
  untrusted when it is rendered into an issue comment — control characters
  stripped and the body fenced, as today.
- **FR-004**: A gate suite that produces no verdict — hung, cancelled, crashed,
  or whose containment could not be established — MUST be treated as a failure
  at the push decision, never as a pass.
- **FR-005**: The same containment MUST apply to both call sites: the fix job's
  gate suite and the review-fixup gate suite. [NEEDS CLARIFICATION: does this
  containment property extend beyond `board-loop.yml` to the feature-lifecycle
  stages that also run an agent and then push with the App token — `implement`,
  `converge`, `pr-conversation` — or is this feature bounded to the board loop,
  with the lifecycle stages filed separately?]
- **FR-006**: The mechanism MUST be one of the containment strategies recorded
  against the decision below, applied uniformly at both call sites rather than
  chosen per site. [NEEDS CLARIFICATION: which containment strategy — (a) a
  separate job with `permissions: read` and no App token, results passed back
  as an artifact; (b) the same job with the credential-bearing variables
  scrubbed from that step's environment; (c) a stronger isolation boundary
  (container, separate runner) around the suite?]

**Integrity of the trusted snapshot and the job environment**

- **FR-007**: Code the board loop executes from an item's branch MUST NOT be
  able to alter what a later step in the same job imports from
  `$RUNNER_TEMP/wc-pristine` or resolves from `.wc-pristine-repo`.
- **FR-008**: Code the board loop executes from an item's branch MUST NOT be
  able to alter the environment variables, the `PATH`, or the interpreter that
  a later step in the same job uses — specifically, appends to `$GITHUB_ENV`
  and `$GITHUB_PATH` must not take effect for later steps.
- **FR-009**: The repository MUST state, in the workflow comment that documents
  the snapshot, exactly which steps the snapshot's guarantee covers and what
  that guarantee rests on, so a future reader cannot mistake "read-only" for
  "unalterable by the agent".
- **FR-010**: Where FR-007 or FR-008 rests on a property of the runner (user
  model, filesystem permissions, process isolation), that assumption MUST be
  written down at the point the protection is established.

**Provenance inside composite actions**

- **FR-011**: A composite action reached from a board-loop job whose workspace
  holds agent-written content MUST resolve the helper scripts and schemas its
  own `run:` steps execute from the trusted snapshot, never from a
  workspace-relative path.
- **FR-012**: `wing-commander-board-stop-check` MUST satisfy FR-011 — the
  kill-switch decision MUST NOT be computed by a copy of `board_stop_check.py`
  that an agent could have written.
- **FR-013**: A gate MUST inspect the `run:` bodies of the composite actions
  reachable from `fix`, `review` and `readiness`, so that moving a `run:` block
  from `board-loop.yml` into a composite cannot exit the provenance rule's
  field of view.
- **FR-014**: FR-013's gate MUST fail loudly, rather than pass, when it cannot
  determine the set of composites a job reaches (Principle VIII).

**Git hooks and git configuration**

- **FR-015**: A hook file present in the working checkout MUST NOT execute
  during any git operation the board loop performs with the App token.
- **FR-016**: A git configuration value present in the repository-, global- or
  system-level config MUST NOT be able to redirect where the loop's push sends
  the App token, nor cause additional code to run during it.
- **FR-017**: The loop's pushes MUST target an explicitly stated destination
  rather than one derived from configuration an agent could have written.
- **FR-018**: The agent's ability to write under `.git/` MUST be addressed at
  the point the decision below records. [NEEDS CLARIFICATION: deny `.git/**` in
  the fixer's and review-fixup's disallowed tools, harden the push steps so a
  plant is inert, or both — and is the tool-level deny alone acceptable given
  that a tool allowlist is a request the model can fail to honour (Principle
  IX)?]

**Gates and evidence**

- **FR-019**: Each of FR-001, FR-007/FR-008, FR-011 and FR-015/FR-016/FR-017
  MUST be held by a gate reachable through the gate registry, running the same
  subject with the same arguments locally as in CI.
- **FR-020**: Every failure branch each new gate ships MUST be exercised by a
  checked-in fixture, not by a manual demonstration (Principle VIII).
- **FR-021**: Each new gate MUST be triggered by changes to the workflow,
  composite, or script it checks.
- **FR-022**: Shared logic introduced by this feature — a scrubbing helper, an
  artifact contract, a hardened push idiom — MUST have exactly one home, with a
  gate behind the "single home" claim, before it appears at a second call site
  (CLAUDE.md, "Shared logic has exactly one home").
- **FR-023**: The already-closed items listed in this spec's Overview MUST NOT
  be re-implemented; the feature's scope is the four open paths only.
- **FR-024**: The behaviour this feature changes runs only in Actions, so it
  MUST be proven after merge by re-driving one board-loop run, with the
  evidence recorded on the PR or the lifecycle issue.

### Key Entities

- **Trusted commit**: `github.sha` — the commit whose `board-loop.yml` is
  executing. Everything the loop trusts is resolved from it.
- **Pristine snapshot** (`$RUNNER_TEMP/wc-pristine`): the read-only tar extract
  of the trusted commit's `.github/scripts` and `.github/schemas` that
  post-agent `run:` blocks import from.
- **Trusted copy** (`.wc-pristine-repo`): the read-only sidecar checkout of the
  trusted commit that `uses: ./...` references resolve from.
- **Item workspace**: the job's main checkout — for `fix` after its resume
  path, `review` and `readiness`, this holds agent-written content.
- **Loop credential**: the GitHub App token, exported as `WC_BOT_TOKEN` into
  `$GITHUB_ENV` by `wing-commander-context` and therefore present in every
  later step of the job.
- **Gate verdict**: the pass/fail outcome and first-failing-gate text the gate
  suite produces, consumed by the push, comment and label decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A gate script placed on a board item's branch that enumerates its
  own environment finds zero credentials able to write to this repository.
- **SC-002**: A gate script placed on a board item's branch that attempts to
  rewrite the pristine snapshot or the trusted copy, or to append to
  `$GITHUB_ENV` or `$GITHUB_PATH`, changes the behaviour of zero later steps in
  the job.
- **SC-003**: Zero composite actions reachable from `fix`, `review` or
  `readiness` execute a workspace-relative helper script.
- **SC-004**: A `pre-push` hook and a `url.*.insteadOf` value planted on a fix
  branch influence zero pushes the loop performs.
- **SC-005**: A fix PR whose gate suite fails still produces exactly today's
  outcome — no push, no PR, the first failing gate quoted on the issue inside a
  fence, `board:stalled` applied — measured over the feature's fixtures.
- **SC-006**: Every new gate this feature ships has at least one checked-in
  fixture per failure branch, and a maintainer can run each gate locally with
  the same invocation CI uses.
- **SC-007**: Each of the four open paths named in the Overview is either
  closed by a requirement above or explicitly deferred with the deferral
  recorded on the lifecycle issue — none is left silently unaddressed.
- **SC-008**: One board-loop run is re-driven after merge and its evidence
  recorded, demonstrating the loop still takes an item from `fix` through a
  green gate suite to a pushed branch and an opened PR.

## Assumptions

- The board loop's existing behaviour on both gate-suite outcomes — push and
  open a PR on green; comment the first failing gate and apply `board:stalled`
  on red — is correct and is preserved unchanged; only where the suite runs and
  what it can reach changes.
- The `fix` and `review-fixup` agents keep their `Write`/`Edit` grants over the
  workspace; this feature constrains what that access can reach, not whether
  the agent has it.
- The three items recorded as already closed (composite resolution via spec
  086, the reviewer's `git_read.py` grant, `verify-stage-finding-schema.py`'s
  `\Z` translation via #593) stay closed; this feature does not re-verify them
  beyond not regressing them.
- The existing Gate 98 carve-out for `python3 .github/scripts/run-local-gates.py`
  remains correct in spirit — the suite must run the agent's tree — and this
  feature changes the *environment* that call runs in, not the fact that it
  runs the agent's code.
- `board-loop.yml` is this repository's own consuming instrument, not a
  published stage (its own header says so), so changes confined to it do not
  widen the adopter-pinned contract. Changes to composites under
  `.github/actions/` that adopters resolve do touch the published surface and
  are treated accordingly (Principle VII).
- Gate-suite runtime may increase if the suite moves to a separate execution
  context; a modest increase is acceptable, and no specific budget is asserted
  here.
- No checked-in gate today requires a repository-write credential to pass; any
  that requires repository *read* access is identified during planning rather
  than assumed absent.
</content>
</invoke>
