# Feature Specification: Denied Read-Only Commands — Widen the Grant, or Stop Filing the Recovery

**Feature Branch**: `spec-draft/112-denied-command-policy`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #827 — "Stage agents keep reaching for denied
read-only commands (git show/stash, xargs sh -c, heredoc cat >): widen the
grants or stop filing them as defects"

## Overview

A stage agent reaches for a shell command the permission layer refuses. The
call costs a turn and returns nothing, the agent takes another route, the
stage finishes its work and its run goes green. The watchdog then files a
`pipeline-defect` issue about the refused call, and a maintainer spends a
triage slot on it.

That loop has now run four times since the last fix — #761, #764, #780 and
#801, with occurrences as late as 23:56Z on 2026-09-29 — and each issue
describes a *different* command, so nothing deduplicates onto anything.
Two rounds of fixes have already been aimed at the agents' behaviour
(bad1021f/#767 named the commit-message scratch path; edd05b07/#745 granted
the gate commands, moved file inspection onto Grep/Glob/Read, and moved the
intake PR body onto `--body-file`). Both rounds worked for the exact
commands they named. Neither stopped the class, because the next run reaches
for the next command.

The issue asks the owner to decide a trade-off between three routes, which
are not mutually exclusive:

- **(a) Widen the per-stage allowlists** for the read-only commands the
  agents plainly need.
- **(b) Treat a denial the agent recovered from as noise, not a defect**, so
  the watchdog stops filing it.
- **(c) Change the stage prompts** to steer agents to the granted
  equivalents.

This specification is deliberately written around that decision rather than
around one answer to it. It states what is true today, what each route would
have to satisfy, and it leaves the choice itself as three open questions for
the lifecycle issue to answer.

One correction to the framing, visible in the evidence below and load-bearing
for route (a): the denials are mostly **not** a missing verb. `git show` is
already granted at every implement and plan call site; what was refused was
`git show … > /tmp/file`, because the grant matches a command and a
redirection is not that command. So "widen the grants for read-only
commands" splits into two very different changes — adding a verb, which is
ordinary least-privilege bookkeeping, and permitting a *composition*
(redirection, `;` chains, `xargs sh -c`, heredocs), which is where Principle
V is actually at stake, since `>` writes a file. And `git stash` is not a
read-only command at all: it mutates the working tree.

### Observed facts (verified against `main` at 9d19228; re-check cited line numbers at plan time)

**The denied commands, from the four issues' own evidence.**

| Issue | Stage | Denied command (from `facts.denied-commands`) | Why it was refused |
|-------|-------|----------------------------------------------|--------------------|
| #764 | implement | `git show origin/main:.github/workflows/pr-conversation.yml > /tmp/pr-conv-before.txt` (twice, once piped through `awk`) | redirection, and `awk` is not granted |
| #764 | implement | `git remote -v; echo ---; git config --get credential.helper; …` | `;` chain, `git remote`/`git config` not granted |
| #764 | implement | `mkdir -p …/tests/lifecycle-merge-preconditions/{round-not-…` | brace expansion |
| #764 | implement | `grep -n 'WORKFLOWS\|lifecycle-review-gate' …verify-reviewer-fail-closed.py \| head -20; echo '--- review j` | `;` chain |
| #780 | clarify | `git show origin/main:.github/workflows/board-loop.yml > /tmp/board-loop-main.yml && echo written` | `git show` is not granted to clarify at all, *and* redirection |
| #801 | plan | `grep -l "schedule:" .github/workflows/*.yml \| xargs -I{} sh -c 'echo "== {} =="; grep -n … {}'` | `xargs`/`sh -c` not granted |

**Route (c) is already in place for three of these shapes, in the stage that
produced most of them.** `implement.yml:992-1026` carries a "Shell
constraints in this headless run" block that names, in as many words, the
`$NAME` rejection, the `;` chain, and "no `cd`, `timeout`, redirect
(`> log 2>&1`) or `;`/`echo` chain around it, each of which is denied even
though the gate itself is allowed", and closes with "A denial is not a hint
to retry a variant." The same block is at `intake.yml:764-…`,
`plan.yml:876-…` / `plan.yml:1110-…`, and `tasks.yml:853-…` /
`tasks.yml:1083-…`. `clarify.yml:669-678` carries a shorter hand-written
SHELL paragraph that says "Do not build files by redirecting with `>`; use
Write". #764 and #780 are both a redirect, filed *after* those sentences
shipped.

**The rendered tooling statement exists, and clarify does not use it.**
`.github/actions/wing-commander-tool-args/action.yml` emits a
`shell-commands` output — "a complete sentence stating exactly which shell
commands this run permits", derived from the composed lists so prompt and
grant cannot drift (spec 037). `implement.yml:975`, `plan.yml:869`,
`plan.yml:1103`, `tasks.yml:846` and `tasks.yml:1076` interpolate it as
`Tooling: …`. `clarify.yml` calls the composite (`id: tool-args-clarify`,
line 581) but its prompt contains no `Tooling:` line and no shell-constraints
block; its grant list (line 584) omits `Bash(git show:*)`, which
`implement.yml` (lines 858, 1566), `plan.yml` (755, 994) and `tasks.yml`
(746, 970) all carry. The statement names *commands*; it says nothing about
composition, because the permission layer's composition rules are not
derivable from the tool list.

**`git stash` is granted at no call site in the repository**, and is a
working-tree mutation rather than a read.

**The watchdog treats every denial the same way, by construction.**
`watchdog.yml:606` and `:628` stamp `"class-hint":"denied-tool"` on every
tool-denial signal unconditionally — the collector's only filters are the
run conclusion (`skipped`/`cancelled` contribute nothing, lines 533-538) and
the requirement that a `tool_result` be both `is_error` and carry
permission-denial text (lines 615-625). Nothing downstream asks whether the
agent recovered: the diagnose prompt says a signal whose class-hint is set
"should normally become a Finding of that class" (`watchdog.yml:2428-2431`),
the evidence gate requires only that `{stage, tool}` be present
(`watchdog.yml:3088`), and the issue-filing eligibility step exempts exactly
one class, `narrative-drift` (`watchdog.yml:3013-3024`).

**Spec 109 deliberately preserves this fan-out.** Its FR-013 keeps the
per-`{stage, tool}` separation of tool-denial signals, and its SC-003 names
these same runs: "Replaying the three runs behind #761, #764 and #780
produces three separate issues, one per `{stage, tool}` pair — unchanged from
today." Any route that suppresses a recovered denial contradicts that
sentence and must amend it rather than leave two live requirements
disagreeing.

**A recovered denial is deterministically observable.** The watchdog already
reads the inspected run's conclusion, its terminal result record, and its
stage artifacts; a denial inside a run that reached its own successful
conclusion and produced the artifact its stage owes is distinguishable, in
deterministic code, from one inside a run that stalled, errored, or produced
nothing. This matters because Principle IX puts false-positive suppression
"into the collectors that observe the world, rather than left to `diagnose`'s
judgment over signals it cannot re-verify".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A refused call the agent worked around stops consuming a triage slot (Priority: P1)

A maintainer opens the board. A stage run went green, delivered its spec /
plan / commit, and along the way one Bash call was refused and the agent
took another route. The board shows no `pipeline-defect` issue for that
refused call. The refusal is still recorded where a maintainer can go
looking for it on purpose — it is simply not a filed defect competing with
real ones.

**Why this priority**: It is the whole cost the issue is about. Four issues
in two days, each triaged by hand, each describing a run that did its job.

**Independent Test**: Replay the runs behind #764, #780 and #801 — all three
of which delivered their stage's work — through the watchdog against a clean
tracker, and observe zero `pipeline-defect` issues filed, with each
suppression named and attributable.

**Acceptance Scenarios**:

1. **Given** an inspected run that reached its own successful conclusion and
   produced the artifact its stage owes, **When** its execution-output
   records one or more permission denials, **Then** no `pipeline-defect`
   issue is filed for them.
2. **Given** the same run, **When** the watchdog reports to the lifecycle
   issue, **Then** the report names the denial, the stage, the denied
   command, and the reason it was not filed.
3. **Given** a run with both a denial and an unrelated genuine failure,
   **When** the watchdog diagnoses it, **Then** the genuine failure is still
   filed on its own class and only the denial is suppressed.

---

### User Story 2 - A refusal that actually cost the stage its work still reaches the board (Priority: P1)

A stage agent is refused a command, cannot find a granted equivalent,
and the stage ends without the artifact it owes — or burns its turn budget
retrying variants. That is a genuine pipeline defect, and it is filed,
exactly as today.

**Why this priority**: It is the correctness bound on User Story 1. A rule
that suppresses recovered denials is only safe if the unrecovered ones are
still visible; otherwise the change trades noise for blindness.

**Independent Test**: Replay a run whose conclusion is `failure` (or which
produced no stage artifact) and which carries a tool denial, and observe the
`denied-tool` issue filed exactly as it is today.

**Acceptance Scenarios**:

1. **Given** an inspected run that did not reach a successful conclusion,
   **When** it carries a tool denial, **Then** a `denied-tool`
   `pipeline-defect` issue is filed.
2. **Given** a run that reached a successful conclusion but did not produce
   the artifact its stage owes, **When** it carries a tool denial, **Then**
   the denial is filed rather than suppressed.
3. **Given** a run whose denial count crosses whatever bound the adopted
   answer sets, **When** the watchdog diagnoses it, **Then** it is filed even
   though the run went green.

---

### User Story 3 - The commands the stages genuinely need are reachable by a granted route (Priority: P2)

A stage agent needs to read a file as it exists on `origin/main`, or to
enumerate workflow files by content. There is a route it can take that the
permission layer accepts, the prompt names it, and the agent's first attempt
uses it.

**Why this priority**: It removes the cause rather than the symptom, and it
is the half that keeps the pipeline capable. But it is P2, not P1, because
two rounds of this have already shipped and the class survived both — it
reduces the rate, it does not close the loop.

**Independent Test**: For each denied command in the Observed-facts table,
name the granted route that satisfies the same need in the stage that
reached for it, and confirm that route is both granted at that call site and
named in that stage's prompt.

**Acceptance Scenarios**:

1. **Given** a stage whose prompt tells the agent to read git history or a
   blob at a ref, **When** the agent follows the prompt literally, **Then**
   the call is permitted at that stage's call site.
2. **Given** the clarify stage, **When** its agent needs to compare a file
   against `origin/main`, **Then** the prompt names a route clarify is
   actually granted.
3. **Given** any stage prompt that names a shell command, **When** the
   grant list for that call site changes, **Then** a gate fails unless the
   prompt's statement of permitted commands moves with it.

---

### User Story 4 - The decision is proven by a checked-in fixture, and a mutation breaks it (Priority: P2)

Whatever is adopted, the PR-time gate suite carries a fixture for each arm of
the new behaviour, and reverting the behaviour makes the suite fail and name
the fixture.

**Why this priority**: Principle VIII. A suppression rule with no fixture is
indistinguishable from a suppression rule that suppresses everything, and
the failure mode — a defect class silently stopping — produces no signal at
all.

**Independent Test**: Revert the adopted rule in a scratch commit and
confirm the suite fails naming the fixture; do the same for the
counter-arm (the unrecovered denial that must still file).

**Acceptance Scenarios**:

1. **Given** the shipped rule, **When** a mutation makes it suppress every
   denial including unrecovered ones, **Then** the gate suite fails.
2. **Given** the shipped rule, **When** a mutation makes it suppress
   nothing, **Then** the gate suite fails.
3. **Given** a widened grant list, **When** a grant named in a prompt is
   removed from the call site (or vice versa), **Then** the gate suite fails.

---

### User Story 5 - The governing documents and the four open issues are reconciled (Priority: P3)

A maintainer reading spec 109's SC-003, spec 024's filing requirements, and
this feature's requirements finds one consistent story about when a denial is
filed. #761, #764, #780 and #801 are closed against this route with that
reason recorded, not left open describing behaviour that no longer exists.

**Why this priority**: No run behaves differently because of it, but the next
agent to touch the watchdog reads these documents to decide what is
intentional.

**Independent Test**: Read spec 109's FR-013/SC-003 and this spec's
requirements in sequence and confirm no sentence in one is falsified by the
other.

**Acceptance Scenarios**:

1. **Given** the adopted answer suppresses recovered denials, **When** spec
   109's SC-003 is read, **Then** it has been amended in the same feature so
   it no longer asserts those three runs file three issues.
2. **Given** this feature has been routed, **When** #761, #764, #780 and
   #801 are read, **Then** each is closed with this lifecycle issue named as
   what covers it.

---

### Edge Cases

- **A denial in a run the collector cannot judge.** The
  execution-output artifact is missing, expired past retention, or
  unreadable, so whether the agent recovered is unknown. The run conclusion
  is still readable, but the denial itself is not. The rule must have a
  stated default for "cannot tell", and it must be the conservative one for
  whichever direction the owner picks.
- **Many denials in a green run.** An agent that burned twelve turns on
  refused variants and still finished has cost real budget even though it
  recovered. A pure recovered/not-recovered rule files nothing for it.
- **A denial of a command that is granted, refused for its composition.**
  `git show … > /tmp/f` is the live example. The finding's `denied-commands`
  fact carries the full composed string, so the two cases are
  distinguishable in the evidence but are one class today.
- **A denial of something the agent should not have (`git push` in a
  read-only stage).** That is the permission layer working, and arguably the
  one denial worth filing loudly, since it means a prompt is asking for
  something a deliberate boundary forbids.
- **A stage whose prompt was edited to name a route it is not granted.** The
  prompt is now the cause of the denial. This is the shape edd05b07 fixed
  twice and the shape a gate can hold.
- **`git stash` specifically.** It is in the issue's list of "read-only
  commands" but it writes. A route-(a) grant list assembled from the issue's
  own wording would grant a mutation.
- **The board loop reading its own noise.** A `pipeline-defect` issue the
  loop triages, routes and closes costs pipeline turns from the same usage
  window the stages draw on, so the noise is not only a human cost.

## Requirements *(mandatory)*

### Functional Requirements

#### The adopted route

- **FR-001**: The repository MUST adopt an explicit, recorded policy for what
  happens when a stage agent's shell call is refused by the permission layer.
  [NEEDS CLARIFICATION: which of the three routes is adopted, and in what
  combination? (a) widen the per-stage grants for the commands the agents
  need; (b) stop filing a denial the agent recovered from; (c) sharpen the
  stage prompts toward the granted equivalents. (b) is the only one that
  bounds the issue rate rather than reducing it, and (c) has already shipped
  twice with the class surviving both — but (b) alone leaves the agents still
  losing a turn per refusal.]
- **FR-002**: Whatever is adopted MUST be recorded in a form a later run can
  read back — a requirement in a live spec, not a code comment alone — so the
  next maintainer can tell an intended suppression from a regression.
- **FR-003**: The policy MUST state, for each of the six denied-command
  shapes in the Observed-facts table, what happens to a run that produces it.

#### If a recovered denial stops being filed

- **FR-004**: The decision not to file MUST be made by deterministic code
  from evidence that code itself reads, never by the diagnose agent's
  judgment (Principle IX). The collector or a deterministic filing condition
  is the home; a prompt instruction is not.
- **FR-005**: "Recovered" MUST be defined as a predicate over facts the
  watchdog already gathers about the inspected run. [NEEDS CLARIFICATION:
  what exactly counts as recovered? (i) the inspected run reached a
  successful conclusion; (ii) that, plus the run produced the artifact its
  stage owes; (iii) that, plus the denial count for the run is at or below a
  stated bound; (iv) that, plus the denied command is on a named list of
  shapes known to be recoverable. Each is strictly narrower than the one
  before and files strictly more.]
- **FR-006**: A denial that fails the FR-005 predicate MUST be filed exactly
  as it is today — same class, same `{stage, tool}` identity, same dedup
  path.
- **FR-007**: A suppressed denial MUST still be reported where a maintainer
  can find it deliberately, naming the stage, the tool, the denied command
  and the reason it was not filed. [NEEDS CLARIFICATION: what is the
  reporting surface? (i) the lifecycle-issue report only, reusing the
  `narrative-drift` issueless path at `watchdog.yml:3013-3024`; (ii) the run's
  own step summary only; (iii) both; (iv) both plus a periodic digest issue
  that accumulates recovered denials so the rate stays visible without one
  issue per run.]
- **FR-008**: A suppressed denial MUST NOT be silently dropped: every
  tool-denial signal a run produces MUST end in exactly one named outcome —
  filed, attached to an existing issue, or suppressed under a named reason.
- **FR-009**: When the evidence needed to evaluate FR-005 could not be read
  this run — the execution-output artifact is missing, expired or malformed,
  or the collector is named in `watchdog-untrusted-collectors.json` — the
  outcome MUST be the conservative one, and it MUST be named as
  "undecidable" rather than silently taking either branch.
- **FR-010**: The suppression MUST be scoped to permission denials. No other
  finding class may become unfilable through the same mechanism.

#### If the grants widen

- **FR-011**: Every added grant MUST be least-privilege (Principle V): named
  to the specific verb and stage that needs it, never a bare `Bash(git:*)`
  or a whole-interpreter grant, and never added to a stage that has no
  demonstrated need.
- **FR-012**: A grant MUST NOT be added for a command that mutates state in
  a stage whose boundary forbids that mutation. In particular `git stash`
  MUST NOT be granted on the strength of the issue's "read-only" framing
  without a stated need, because it writes the working tree.
- **FR-013**: Permitting a *composition* — redirection, `;`/`&&` chains with
  ungranted parts, `xargs sh -c`, brace expansion, heredocs — MUST be treated
  as a separate decision from adding a verb, and MUST NOT be adopted merely
  because the verb inside it is already granted. A redirection writes a file;
  a grant that permits it widens the write boundary specs 090 and 078 drew.
- **FR-014**: Where a need is better served by an existing granted route than
  by a new grant, that route MUST be used. `git_read.py` (`log`/`diff`/`show`
  with `--output`) is the route watchdog, board-loop, pr-conversation,
  auto-update and implement's own report step already take for git reads;
  Grep/Glob/Read is the route for file inspection; Write is the route for
  creating a file.
- **FR-015**: Every grant added or route adopted MUST be reachable from the
  prompt of the stage that needs it — the agent MUST be able to learn the
  route from the prompt without guessing.
- **FR-016**: The documented per-stage default tool-list table
  (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) MUST move
  with any changed call-site literal, and Gate 27
  (`verify-stage-tool-lists.py`) MUST continue to hold it.

#### If the prompts change

- **FR-017**: A stage prompt that states which shell commands the run permits
  MUST derive that statement from the run's own composed tool lists rather
  than restating them by hand, so the two cannot drift.
- **FR-018**: The clarify stage MUST be brought to the same footing as
  implement, plan, tasks and intake: it already composes its tool lists
  through `wing-commander-tool-args` but its prompt neither renders the
  `shell-commands` statement nor carries the shell-constraints block.
- **FR-019**: Prompt guidance about *composition* MUST state the rule the
  permission layer actually applies, not a list of examples: the observed
  failures are compositions of granted parts, and an example list is one
  unlisted shape away from being wrong.
- **FR-020**: No prompt change may be counted as satisfying FR-001 on its own
  unless the adopted answer says so explicitly, because a prompt instruction
  is a request the model can silently fail to follow (Principle IX) and two
  such rounds have already been observed not to close this class.

#### Coverage

- **FR-021**: Each arm of the adopted behaviour MUST be exercised by a
  checked-in fixture in the nearest existing gate or self-test harness
  (CLAUDE.md: extend the nearest existing gate), not by a manual
  demonstration.
- **FR-022**: Each fixture MUST be accompanied by a mutation that reverts the
  behaviour it covers and makes the PR-time suite fail naming that fixture
  (Principle VIII).
- **FR-023**: If a suppression ships, a fixture MUST cover the
  "cannot tell" path of FR-009, not only the two decided branches.

#### Governing documents and the originating issues

- **FR-024**: Spec 109's FR-013 and SC-003, which assert that the runs behind
  #761, #764 and #780 file three separate `pipeline-defect` issues "unchanged
  from today", MUST be reconciled with whatever this feature adopts, in the
  same feature — never left as two live requirements that disagree.
- **FR-025**: Spec 024's requirements on when a finding is filed MUST name
  any new write-suppression outcome this feature introduces, alongside the
  existing ones.
- **FR-026**: #761, #764, #780 and #801 MUST be closed as covered by this
  lifecycle issue, with that reason recorded on each, through the disposition
  route spec 108 defines rather than by hand-editing each issue.
- **FR-027**: This feature changes go-forward behaviour only. It MUST NOT
  retroactively relabel, reopen or rewrite any `pipeline-defect` issue other
  than the four named in FR-026.

### Key Entities

- **Tool-denial signal** — a collector-produced signal carrying
  `{stage, tool, denials, denied-commands}`, stamped
  `"class-hint":"denied-tool"`. Its `{stage, tool}` pair is the identity the
  evidence gate and the fingerprint projection require.
- **Denied command** — the composed command string the permission layer
  refused, carried as a descriptive fact (truncated to 120 characters) and
  deliberately not part of the signal's identity.
- **Recovery status** — the new, deterministically computed property of an
  inspected run that FR-005 defines: whether the stage delivered its work
  despite the refusal. Not currently computed anywhere.
- **Filing outcome** — the single named end state of a tool-denial signal:
  filed, attached, or suppressed-with-reason (FR-008).
- **Per-stage grant list** — the `default-allowed-tools` literal at a
  `wing-commander-tool-args` call site, composed with the consumer's
  append/override inputs into the run's effective `--allowedTools`.
- **Rendered tooling statement** — the composite's `shell-commands` output:
  one sentence naming exactly the commands this run permits, derived from the
  composed lists.

## Success Criteria *(mandatory)*

- **SC-001**: Replaying the runs behind #764, #780 and #801 against a clean
  tracker produces the number of `pipeline-defect` issues the adopted answer
  predicts, and a maintainer reading the adopted requirements alone predicts
  that number correctly before running the replay.
- **SC-002**: Replaying a run that carries a tool denial and did not deliver
  its stage's work files a `denied-tool` issue — unchanged from today.
- **SC-003**: Across any 20 consecutive watchdog runs after this ships, the
  count of `denied-tool` `pipeline-defect` issues filed for runs that
  delivered their stage's work is zero if a suppression was adopted, and
  every such run's denial is still accounted for by a named outcome.
- **SC-004**: Every tool-denial signal in every replayed scenario ends in
  exactly one named outcome; no scenario produces a signal with no recorded
  disposition.
- **SC-005**: Reverting the adopted rule — in either direction, suppress-all
  or suppress-nothing — makes the PR-time gate suite fail and name the
  fixture that covers it.
- **SC-006**: For each of the six denied-command shapes in the Observed-facts
  table, the stage that produced it has a granted route to the same
  information, and that route is named in that stage's prompt. Verified by
  inspection at review time, one row at a time.
- **SC-007**: No stage's prompt states a permitted-command list that differs
  from the list its own call site composes; a gate fails if one does.
- **SC-008**: Reading spec 109's FR-013/SC-003, spec 024's filing
  requirements and this spec's requirements in sequence, a reviewer finds no
  sentence in one contradicted by another.
- **SC-009**: #761, #764, #780 and #801 are closed with this lifecycle issue
  recorded as what covers them, and no other `pipeline-defect` issue changed
  state because of this feature.

## Assumptions

- The four issues (#761, #764, #780, #801) and the six command shapes drawn
  from them are the working corpus. They are the acceptance corpus, not an
  exhaustive one — the next denial will be a seventh shape, which is the
  premise behind preferring a rule to another list of examples.
- A run that reached its own successful conclusion and produced its stage's
  artifact did its job. This is the premise a recovery predicate rests on;
  FR-005 is written so the owner can narrow it.
- The watchdog stays a pure reporter — it files, comments on and reopens
  issues, and nothing else (spec 024 FR-014). Nothing here adds a
  remediation action.
- The diagnose agent's behaviour is not the lever. It is told a class-hinted
  signal "should normally become a Finding", and the fix belongs in the
  collector or a deterministic filing condition (Principle IX).
- Stage agents will keep reaching for shapes the permission layer refuses at
  some nonzero rate, however well the prompts are written. Two rounds of
  prompt fixes are the evidence.
- The cost being optimised is a maintainer's triage slot and the pipeline's
  own turn budget, which come from one shared usage window (CLAUDE.md).
- `git_read.py` is available to a stage that is granted it; whether every
  stage that needs git reads can reach it is a plan-stage question, not an
  assumption this spec makes.
- Spec 101 (#759, read-only `gh` grants) may change the same per-stage grant
  literals. If both land, the later one rebases onto the earlier; neither
  owns the other's grants.

## Dependencies

- `.github/workflows/watchdog.yml`'s `collect` → `diagnose` → `triage` →
  `act` chain: the `collect-execution-output` collector (lines 509-640), the
  diagnose prompt's class-hint sentence (2428-2431), the issue-filing
  eligibility step (3013-3024), the evidence-validity gate (3050-3110) and
  its per-class required-key list (3088).
- The per-stage grant literals at every `wing-commander-tool-args` call site,
  and `.github/actions/wing-commander-tool-args/action.yml`'s
  `shell-commands` renderer.
- `specs/010-reusable-pipeline/contracts/stage-interfaces.md` (live
  contract), held by Gate 27 (`verify-stage-tool-lists.py`), and
  `verify-tooling-statement.py`.
- `specs/015-pipeline-watchdog` and `specs/024-*` — the governing dedup and
  filing requirements; `specs/109-watchdog-finding-fanout` FR-013/SC-003,
  which this feature must reconcile (FR-024).
- `specs/108-routed-original-disposition` — the route by which #761, #764,
  #780 and #801 are closed (FR-026).
- `specs/090-stage-write-boundary` and `specs/078-plan-tasks-commit-scratch-path`
  — the write boundaries a composition grant would widen (FR-013).
- Constitution Principles V (least-privilege allowlists), VIII (a green check
  means what it says) and IX (deterministic judgment gates durable actions).
- Spec 101 (#759) — read-only `gh` grants, in flight on an unmerged branch,
  touching the same grant literals.

## Out of Scope

- Changing the finding-class vocabulary, the `__new__` resolution path, or the
  dedup/fingerprint mechanism — spec 109 owns those.
- Widening the `gh` grants specifically; spec 101 (#759) carries that.
- Any change to what the permission layer itself accepts. Its composition
  rules are upstream behaviour this repository observes, not code it owns.
- Granting a stage a write it does not already have, beyond what FR-013
  forces the owner to decide deliberately.
- Retiring or rewriting the existing shell-constraints prompt blocks wholesale
  — FR-017 to FR-019 sharpen them, they do not propose removing them.
- Closing, relabelling or consolidating any `pipeline-defect` issue other
  than the four named in FR-026.
