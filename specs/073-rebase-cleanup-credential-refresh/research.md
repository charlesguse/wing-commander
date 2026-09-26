# Phase 0 Research: rebase.yml / cleanup.yml Credential Refresh + Derived Gate 68 Subjects

Every "NEEDS CLARIFICATION" that would otherwise block this plan was
already resolved in spec.md's own Clarifications-equivalent (the two
"Decided" callouts in the Overview, answered on issue #558,
2026-09-25). This document records the *implementation-shape* decisions
those answers still leave open, each traced to the FR/edge-case that
constrains it, plus what was found by reading the current tree rather than
the spec's own prose (which, per the maintainer's own investigation, drifted
from `board-loop.yml`'s current line numbers).

## D1 — Spec 072 is superseded in place, not sequenced before this feature

**Decision**: Spec 072 (`072-derived-gate-subjects`, issue #410 item 1) is
`Draft`, carries no `plan.md`/`data-model.md`/`contracts/`, and its own
spec.md explicitly left `board-loop.yml`, `cleanup.yml`, and `rebase.yml`'s
disposition undecided ("needs individual assessment"). Spec 073's own
FR-009 states plainly that it "resolves #410 item 1 within this feature."
This feature therefore implements spec 072's entire clarified derivation
rule (structural agent-step detection, checked-in floor, exclusion record)
as part of its own scope — it does not wait for a separate spec-072
implementation cycle, and none is expected to run. Issue #410 item 1
closes against this feature, per spec.md's own Dependencies section.

**Rationale**: The clarification on #558 said so directly, and re-deriving
the same design decision inside spec 072 instead of consuming its already-
answered Clarifications session would violate CLAUDE.md's single-home rule
one level up (two specs converging on one design question).

**Alternatives considered**: Blocking this feature on a prerequisite
spec-072 implementation cycle — rejected because spec 072 was explicitly
routed *not* to happen separately (the #558 clarification), and because
`board-loop.yml`/`cleanup.yml`/`rebase.yml`'s disposition is inseparable
from spec 073's own FR-005 trade-off (full mechanism vs. wall-clock bound),
so splitting the work would put the same three workflows' disposition
in two specs' hands at once.

## D2 — Derivation is structural, reusing the gate's existing agent-step detector

**Decision**: The derived subject set is computed by globbing every
`.github/workflows/*.yml` file, parsing each with `yaml.safe_load`, and, for
every job, testing every step with the gate's existing `_is_agent_step`
helper (`AGENT_ACTION_RE` matched against `step["uses"]`) — the same
structural test check 2/7 already use to find a job's agent steps today,
just no longer gated behind "is this path a `SUBJECTS` key." A job with at
least one such step is a derived subject. `load_all()` changes from
"read the paths in `SUBJECTS`" to "read every `.github/workflows/*.yml`
path", and `SUBJECTS` (the hand-typed dict) is deleted — its role splits
into the floor (D3) and the per-job disposition table (D4).

**Rationale**: Spec 072 FR-002/FR-008 require the rule to be structural
("the step's own action reference, never a match against the file as
text") and to apply with no narrowing — reusing `_is_agent_step` rather than
inventing a second pattern satisfies both and keeps the "mention in a
comment or fixture" edge case (spec 072) free: `AGENT_ACTION_RE` already
only matches a real `uses:` value, since `yaml.safe_load` never treats a
comment as structure.

**Alternatives considered**: A separate regex/text scan for speed —
rejected, since the gate already loads and parses every subject file with
`yaml.safe_load` and the added file count (workflows outside the old
8-file list: `rebase.yml`, `cleanup.yml`, `watchdog.yml`, `board-loop.yml`,
and any agentless workflow that costs one cheap parse and zero matches) is
small enough that a second, weaker detection path would only be one more
place derivation and reality could drift apart (Constitution VIII).

## D3 — The subject floor is a checked-in Python constant, kept for drop-detection only

**Decision**: A new `SUBJECT_FLOOR` structure (workflow path → set of job
names) replaces `SUBJECTS` as the thing that is hand-typed — but its
job changes: derivation no longer *reads* it to decide what to inspect (D2
does that structurally); the gate instead computes the derived set first,
then asserts `SUBJECT_FLOOR ⊆ derived` and fails, naming the missing
member, when it is not. A derived job absent from the floor is still fully
inspected (never fails merely for that), per spec 072 FR-004. The floor is
seeded with today's ten known agent-bearing jobs: the original eight
(`intake`, `clarify`, `plan`, `tasks`/`tasks-approved` — noting
`tasks-approved` remains agentless per `AGENTLESS_JOBS`, so it is not
actually an agent-bearing job and does not belong in the *agent-step*
floor, only in the pre-existing agentless-but-in-scope set — `implement`,
`finalize`, `pr-conversation`'s `classify-and-announce`/`act`,
`auto-update-spec-kit.yml`'s `e2e-stage`), plus the six this feature
newly disposes of: `rebase.yml`'s `rebase`, `cleanup.yml`'s
`teardown-done`, `watchdog.yml`'s `diagnose`, and `board-loop.yml`'s
`triage`, `route`, `fix`, `review` (one floor entry per job, not per agent
step within a job — `review` contains two agent steps, `Reviewer` and
`Review-fixup`, but is one job).

**Rationale**: Spec 072 FR-004/FR-015 explicitly permit a companion map to
stay hand-kept "for a stated reason" — the floor's stated reason is that it
answers a different question than selection ("is this job still here"),
and a structural rule cannot itself notice a job's disappearance (there is
nothing left to match against once the step is gone). This is also why a
minimum-count check was rejected in spec 072's own clarification: it
tolerates one job vanishing while an unrelated one appears.

**Alternatives considered**: Deriving the floor from git history (e.g. "the
derived set as of the last commit that touched this gate") — rejected as
needless indirection; a `git` dependency inside a static-YAML gate is a new
failure mode (detached HEAD, shallow clone) for a fact three lines of
Python already state plainly, and CLAUDE.md's single-home principle is
about not *duplicating* logic, not about avoiding every checked-in literal.

## D4 — The exclusion/exemption record lives beside the floor, keyed the same way, condition-checked in code

**Decision**: A new `EXEMPT_JOBS` structure (keyed by `(workflow_path,
job_name)`) replaces the binary "in `SUBJECTS`, therefore fully checked"
model with three states: *full subject* (all of checks 1/2/7/etc. apply),
*exempt with an asserted condition* (checks 1/2/7 — the post-agent-
composite requirements — do not apply; a **different**, per-entry condition
function does, and must return true or the gate fails naming the entry),
and *neither* (fails per spec 072 FR-013 — "a derived subject that is
neither compliant nor exempt"). Each entry carries `reason` (prose) and
`issue` (the deciding issue number, for FR-007 of this spec) plus a
`condition` callable that inspects the same parsed job YAML the rest of the
gate already has in hand:

| Job | Condition asserted | Reason / issue |
|---|---|---|
| `cleanup.yml` / `teardown-done` | agent step `timeout-minutes` present and `<= 10` | cites #558 |
| `watchdog.yml` / `diagnose` | agent step `timeout-minutes` present and `<= 10` (already `10` today — see D6) | cites #558 |
| `board-loop.yml` / `triage`, `route`, `fix`, `review` | every agent step in the job is followed, before the next agent step or job end, by a `wing-commander-context` call and a `wing-commander-post-agent-credential-status` call (the two composites `board-loop.yml` already adopted voluntarily per spec 057 T012 — **not** `wing-commander-agent-ran-signal`, which `board-loop.yml` never adopted and spec 072's own table records as a known gap, not a regression to fail on) | cites #558 and #410 |

**Rationale**: This is the mechanical form FR-007 of this spec requires
("its condition MUST be one the check can assert mechanically... the check
MUST fail on it rather than honour it" if it cannot). Reusing the same
per-agent-step-window walk that check 7 already performs for
`REQUIRED_PER_AGENT_STEP_COMPOSITES` — just against a smaller composite
set for `board-loop.yml` — avoids a second traversal implementation for the
same structural question (single-home, one level down, inside the script
itself).

**Alternatives considered**: A single boolean `EXEMPT = {...}` set with the
reason only in a comment — rejected outright; that is exactly the "reason
stated only in prose no check consults" shape FR-007 forbids. A separate
YAML/JSON exemption file — rejected: the exemption is read by exactly one
Python script and by no other tool, so a second file format is a second
thing to keep in sync with zero benefit (CLAUDE.md single-home: "the same
place the check that honours it reads").

## D5 — `rebase.yml`'s `rebase` job: full adoption, five concrete edits

**Decision**: `rebase.yml`'s `rebase` job moves from `SUBJECTS`-absent to a
full subject, mirroring the eight already-covered stages' call-site
convention (`wing-commander-context-relay.md`):

1. After `Resolve conflicts` (the agent step, line ~693): add "Record
   agent-ran signal" (`wing-commander-agent-ran-signal`), "Re-establish
   Wing Commander context (post-agent)" (`wing-commander-context`), and
   "Refresh authenticated spec-branch remote (post-agent)"
   (`wing-commander-refresh-remote`) — `rebase.yml` is **not** added to
   `NO_REMOTE_REFRESH_JOBS`, because its `Checkout spec branch as
   wing-commander-bot` step (line ~590) does persist the credential into
   the git remote the publish arm's `git push --force-with-lease` later
   rides (FR-002).
2. `Report over-budget agent run` (line ~833), `Publish rebased branch`
   (line ~951, including its `git push --force-with-lease` at ~955),
   `Abandon and escalate` (line ~993), and `Announce the rebase escalation
   on the lifecycle issue` (line ~1056) each switch their credential
   reference from `steps.ctx.outputs.token` to `env.WC_BOT_TOKEN` (or, for
   `GH_TOKEN` env blocks, the same substitution) — matching check 1's
   requirement once this job is a subject.
3. `Report over-budget agent run` gains `continue-on-error: true`. This is
   not a credential fix — it is check 3's job-independent tolerance
   requirement ("every step whose name matches..., in every job scanned"),
   which today never scanned `rebase.yml` because `load_all()` never read
   it; once derivation reads every workflow file, this step is scanned and
   would fail check 3 as shipped. Fixing it is in scope as a direct,
   mechanical consequence of D2's file-glob widening, not a new
   requirement invented here. The identical gap exists in `cleanup.yml`'s
   `Report over-budget agent run` (line ~826); D9 confirms `cleanup.yml`
   is not a full subject, but check 3 is *not* gated on subject/exemption
   status (see D9's note), so this step gains `continue-on-error: true`
   too.
4. Immediately before `Abandon and escalate`: add "Determine failed
   post-agent step" (`wing-commander-failed-post-agent-step`), fed the
   job's own hard-failing candidate steps in order (mirroring the six
   entry jobs' existing pattern) — this satisfies FR-004 ("the arm that
   runs when the agent step did not succeed MUST be able to name an
   expired or unrefreshed credential"). `rebase.yml` is **not** added to
   `STALL_REASON_JOBS` or `FAILED_STEP_REQUIRED_JOBS`: per spec.md's own
   Edge Cases, it has no separate survivor/`stalled` job — the arm that
   would read a stall reason is *inside* the same job, so the composite's
   `outputs.step` is consumed directly by `Abandon and escalate`'s own
   step (reading `steps.determine-failed-step.outputs.step`), not relayed
   through a job output to a second job. This is a new, job-local
   consumption pattern the six-stage precedent doesn't need, since none of
   those six read their own `FAILED_STEP` output inside the same job.
5. After the job's last bot-acting step (or immediately after the
   refresh-remote/agent-ran-signal pair, matching the eight stages'
   placement): add "Determine post-agent credential status"
   (`wing-commander-post-agent-credential-status`), feeding FR-003 — when
   it reports not-ok, `Abandon and escalate`'s own comment names the
   credential as the cause (the composite's `ok` output is available to
   that step's `run:` block already, since it runs later in the same job).

**Existing `if:` gating on all four bot-acting steps is preserved
byte-for-byte** (FR-014): `Publish rebased branch`'s
`!cancelled() && (...)`, `Abandon and escalate`'s `!cancelled() && (...)`,
and `Announce the rebase escalation`'s `always() &&
steps.escalate.outputs.issue != ''` are not rewritten. The new composites
(`agent-ran`, `re-establish`, `refresh-remote`) get their own
`if: "!cancelled() && steps.agent.outcome != 'skipped'"` guard — matching
the eight-stage precedent exactly — so a cancelled leg never runs them
(spec.md Edge Cases: "a leg cancelled at 25 minutes never reaches its
post-agent steps at all; the remedy must not make a cancelled leg report a
false failure"). `Announce...`'s pre-existing `always()` is left as-is
rather than tightened to `!cancelled()`, because FR-014 only requires the
*publish* and *abandon/escalate* arms keep their existing semantics and
FR-013 requires unaffected-path behaviour stay unchanged; Gate 68's checks
are structural (they verify a composite call exists in the right position,
not that it *ran* on a given trace), so `always()` here does not weaken
any check — a cancelled run's `Announce...` step running with whatever
`env.WC_BOT_TOKEN` state it finds is the pre-existing behaviour this
feature does not touch.

**Rationale**: This is the literal remedy FR-001 through FR-004 describe,
applied via the one call-site convention `wing-commander-context-relay.md`
already documents for every other job. Not inventing a sixth pattern keeps
the "one home" rule intact one layer up (the composites, not the calling
convention, are what's shared).

**Alternatives considered**: Skipping the `Determine failed post-agent
step` composite and having `Abandon and escalate` read
`steps.reestablish.outcome`/`steps.refresh-remote.outcome` directly —
rejected, because that re-derives, inline, exactly the logic the composite
already centralizes (CLAUDE.md single-home), and it is the "candidates"
composite, not the mint/refresh composites themselves, that names *which*
step failed for FR-004's "name the reason."

## D6 — `watchdog.yml`: no behavioural change, one exemption entry, one comment

**Decision**: `diagnose`'s `timeout-minutes: 10` (line ~2286) already
satisfies D4's condition today — no workflow edit is required beyond
adding an issue citation to the step's existing explanatory comment (which
currently explains *why* the bound exists but cites no issue), so a human
reading the step sees the same reason the gate's `EXEMPT_JOBS` entry
states. The gate-side `EXEMPT_JOBS` entry is the enforcement; the comment
is FR-007's "the same place... a reader" would look, which is documentation
courtesy, not a second enforcement path.

**Rationale**: Spec 072's own clarification already named this exact
disposition and reason ("`watchdog.yml`'s `diagnose` is excluded on the
stated basis that its agent step carries `timeout-minutes: 10`"); spec 073
inherits it rather than re-deciding it.

## D7 — `board-loop.yml`: no behavioural change, one exemption entry per job

**Decision**: No workflow edit to `board-loop.yml` itself — its four
agent-bearing jobs (`triage`, `route`, `fix`, `review`) already call
`wing-commander-context` and `wing-commander-post-agent-credential-status`
after every agent step (confirmed present at every one of the five agent
steps' post-step windows). D4's condition function asserts exactly that
adoption; because it already holds, the gate passes on the shipped tree
with no code change to `board-loop.yml`. The spec's own note that this
exemption is "provisional... for now" (Assumptions) is recorded in the
`EXEMPT_JOBS` entry's `reason` text, not enforced mechanically — promoting
`board-loop.yml` to a full subject later (e.g. once it also adopts
`wing-commander-agent-ran-signal`) is a follow-up re-classification, not
something this feature's gate needs to predict.

**Rationale**: Matches spec.md's Assumptions section directly ("it is
exempt because it already consumes the post-agent composites, not because
it is out of reach").

## D8 — `cleanup.yml`'s `teardown-done`: bound only, explicitly not the composites

**Decision**: Add `timeout-minutes: 10` to the `Completion summary` agent
step (line ~691). No `wing-commander-context`/`-refresh-remote`/
`-agent-ran-signal`/`-post-agent-credential-status` calls are added — FR-005
states this explicitly ("It MUST NOT receive the post-agent composites").
`Delete pipeline branches`'s persisted-remote push (FR-002) is covered by
the same bound: the whole `teardown-done` job — mint, checkouts, the
now-bounded agent step, and every step after it — cannot run past
approximately `10 + (the job's own non-agent-step wall-clock, historically
≤1 minute)` minutes, which stays inside the token's ~60-minute lifetime
with an order-of-magnitude margin, so no later step in this job can ever
observe a credential past its lifetime even though every one of them keeps
reading the pre-agent `steps.ctx.outputs.token` (unchanged, per FR-013).

**Rationale**: This is FR-005's explicit choice, made on issue #558's
clarification, not a new decision — the Overview's own trade-off table
already weighed "full mechanism everywhere" against "cheaper bound with a
weaker-coverage objection" and the clarification chose the bound precisely
because `cleanup.yml`'s agent step measured ~1 minute on every one of 40
runs.

## D9 — Check 3 (`Report over-budget agent run` tolerance) is job-agnostic, not gated on subject/exemption status

**Decision**: Confirmed by reading the gate's own docstring point 3 ("in
every job scanned... since the tolerance is a property of the step itself")
— this check does not consult `SUBJECTS`/derived-subject/exempt status at
all, only "does a step named `Report over-budget agent run`[, variant] exist
in a scanned job." Once `load_all()` (D2) reads every workflow file instead
of eight, this check's scope widens automatically to every workflow file,
which is why both `rebase.yml`'s and `cleanup.yml`'s copies of this step
(D5 point 3, D8) need `continue-on-error: true` regardless of whether their
job ends up a full subject or an exemption entry.

**Rationale**: Recorded here so the tasks stage does not read D5/D8's
`continue-on-error` additions as scope creep — they are load-bearing for
Gate 68 to pass once file-glob derivation ships, not an unrelated cleanup.

## D10 — Matrix jobs need no gate-side accommodation

**Decision**: `rebase.yml`'s `rebase` job runs as a `strategy.matrix` job,
but Gate 68 reads the job's *static definition* in the YAML file (one
`steps:` list shared by every matrix leg), not a runtime trace of any
particular leg's execution. "Each matrix leg is its own job instance with
its own mint; the remedy must hold per leg, not once per workflow" (spec.md
Edge Cases) is satisfied by construction: the composites this feature adds
run inside the one shared job definition, so every leg gets its own
mint/refresh/status sequence at runtime with no additional gate logic.

**Rationale**: This is a restatement of why static-structure checking
(existing design note in the gate's own docstring, "this gate's subject is
step ordering and reference shape, not step behaviour") already generalizes
to matrix jobs with zero new code.

## D-Registry — `run-local-gates.py` needs no change

**Decision**: Confirmed by reading `run-local-gates.py`: it derives its
gate list from `lint-workflows.yml` via `wc_gate_registry.py`, not from a
hand-kept table, so Gate 68 (and its `--self-test` companion step) are
already included with no separate registration edit. FR-011/FR-016 of this
spec are satisfied here with no code change — only Gate 68's own docstring
and `lint-workflows.yml`'s comment block above its two steps need updating
to describe a derived set rather than "the 8 sweep stages" (spec 072
FR-017, inherited).

**Rationale**: Verified directly against `run-local-gates.py`'s own
docstring and structure rather than assumed.

## D11 — Contract documentation: amend in place, one new document for the mechanism spec 072 never shipped

**Decision**: `specs/052-agent-credential-lifetime/contracts/
wing-commander-context-relay.md` gains a `rebase.yml` section (following
its existing per-workflow subsection pattern for `implement.yml`'s
three-agent-step job and `auto-update-spec-kit.yml`'s `e2e-stage`); its
"consumed by all 8 sweep-stage workflows" opening line is corrected to
name the derived set instead of a fixed count.
`post-agent-credential-refresh-gate.md`'s "Subject" section — which today
literally states "the 8 workflow files FR-007 names" — is rewritten to
describe the derivation rule, the floor, and the exemption table (D4),
since that section is the literal target FR-016 of this spec names
("the documented set and the checked set are the same set"). Both edits
happen **in the existing files**, not as new copies, per CLAUDE.md's
single-home rule. A new document,
`specs/073-.../contracts/gate-68-derived-subjects.md` (this feature's own
Phase 1 output), is the design record for the derivation/floor/exemption
mechanism itself, because spec 072 — the spec that decided its shape —
never reached Phase 1 and has no contract of its own to amend; this
feature is what actually builds the mechanism, so it is the mechanism's
first and only contract author.

**Rationale**: Two failure modes to avoid: (a) a second, drifting copy of
the "who's covered" table (CLAUDE.md's named cost of pasted prose), and (b)
losing the derivation mechanism's own design rationale because it has
nowhere to live (spec 072 is Draft and this feature does not touch its
files, per this run's own edit-scope constraint).

## D12 — Self-test additions (FR-012 of this spec, FR-009/FR-010 of spec 072)

**Decision**: The gate's `--self-test` gains, at minimum, one mutation per
row of spec.md's FR-012 list, implemented as new `mut_*` functions in the
existing `SIMPLE_MUTATIONS`/`SUBJECT_MUTATIONS` inline-mutation style
(no new fixture files, matching the gate's existing self-test design):

- `rebase.yml` `Publish rebased branch` reverted to `steps.ctx.outputs.token`
  (credential check 1 regression on the new subject).
- `rebase.yml`'s post-agent `wing-commander-context` call deleted (check 2
  regression).
- `rebase.yml`'s `wing-commander-refresh-remote` call deleted (check 7
  regression, since `rebase.yml` is not in `NO_REMOTE_REFRESH_JOBS`).
- `cleanup.yml`'s `timeout-minutes: 10` removed from `Completion summary`
  (exemption-condition regression).
- `cleanup.yml`'s `timeout-minutes` raised past the credential's lifetime,
  e.g. to `90` (same condition, upper-bound direction).
- `watchdog.yml`'s `timeout-minutes: 10` removed from `diagnose` (same
  condition, second exempt job — proves the condition function is not
  hardcoded to one job).
- A synthetic agent-bearing job added to a workflow with neither a
  `SUBJECT_FLOOR`/derivation-implied subject status nor an `EXEMPT_JOBS`
  entry — must fail naming that job (spec 072 FR-013 restated for the new
  exemption model).
- `board-loop.yml`'s exemption condition broken (one job's post-agent
  `wing-commander-context` call deleted) — must fail naming the job, not
  silently keep treating it as exempt.
- A `SUBJECT_FLOOR` member's agent step replaced with a non-agent step —
  must fail naming the dropped subject (spec 072 FR-004/US2, generalized
  from the old "subject list points at a nonexistent job" mutation this
  replaces).

**Rationale**: Direct translation of FR-012's own list plus spec 072's
FR-009/FR-010 ("preserve the intent of the existing subject-list mutations
... by replacing each with the equivalent 'a subject was dropped'
mutation").

## D13 — Constitution/CLAUDE.md gate-review skills this change requires

**Decision**: Because this feature edits `if:`-adjacent gating (new
`!cancelled()` guards on the composites added to `rebase.yml`) and a
`continue-on-error:`-bearing step (D5 point 3, D8), the implementing PR
gets a pass from the `review-step-gating` skill per CLAUDE.md's own rule,
as spec.md's own Assumptions section already states. No `container:` block
or in-container `run:` step is added anywhere, so `container-shell-safety`
does not apply.
