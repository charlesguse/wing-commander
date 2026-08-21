# Phase 0 Research: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

spec.md carries no literal `[NEEDS CLARIFICATION]` markers. It does carry one
explicit "filing for discussion rather than as an agreed change" framing and
several places where the spec defers a mechanism decision to planning
(consecutive-truncation counter storage, exact progress-test shape, gate
number). Those are resolved below as planning decisions, each with the
rejected alternatives, per FR/US they satisfy. None of them re-open a
question the spec already closed (R1's blocking risk, R3's deferral, the
FR-004 either-arm test) — those are treated as settled requirements, not
research questions.

## D1 — Truncation is read from the verdict composite already computed upstream, not from a new parse

**Decision**: `implement.yml`'s cycle job already computes
`steps.cycle-verdict.outputs.verdict` via the shared
`wing-commander-agent-verdict` composite (`.github/workflows/implement.yml:798-804`,
composite at `.github/actions/wing-commander-agent-verdict/action.yml:94-114`)
*before* "Read back cycle outcome" runs. That composite already
distinguishes `exhausted` (subtype `error_max_turns`, checked before the
generic `is_error` branch specifically so it stays distinguishable —
action.yml:97-104) from `failed` and `healthy`, and never fails its own step
(`action.yml:10-14`, "never fails its own step"). "Read back cycle outcome"
(`implement.yml:878-926`) is rewired to also read this output
(`VERDICT: ${{ steps.cycle-verdict.outputs.verdict }}`) rather than
inferring everything from `steps.cycle.outcome` (success/failure), which
today conflates `exhausted` and `failed` — both are forced to
`steps.cycle.outcome = failure` by "Fail loud on non-healthy agent verdict
(cycle)" (`implement.yml:820-828`, `continue-on-error: true`).

**Rationale**: FR-003 requires truncation be identified "from the agent's
machine-readable run record, never inferred from the agent step's exit
status or from the step appearing red." The verdict composite already *is*
that positive identification — it was built for exactly this purpose
(specs/037-agent-turn-budget-guard) and every other call site in the
repository already treats `exhausted` as a distinct value from `failed`
(Gate 22, `.github/scripts/verify-agent-verdict.py`). Building a second,
independent way to detect `error_max_turns` inside "Read back cycle
outcome" would duplicate logic the fleet already trusts, and risks the two
detectors disagreeing — the exact failure mode Gate 22 exists to prevent
for the composite itself. A run whose transcript is missing or unparseable
already resolves to `verdict=unclassifiable` (action.yml:80-81), which is
neither `exhausted` nor `healthy`, so it falls through to the `failed`
path automatically (spec Edge Cases: "The run record is missing,
unreadable... Not truncation").

**Alternatives considered**:
- *Parse the transcript's `subtype` directly inside "Read back cycle
  outcome"* — rejected: duplicates `wing-commander-agent-verdict`'s
  existing, tested classification (Gate 22) for no benefit, and risks
  drift between the two if the runtime ever adds a new terminal subtype.
- *Add a new composite output specifically for "was this exhausted"* —
  rejected: `verdict=exhausted` already *is* that answer; wrapping it in a
  second boolean output would be a distinction without a difference.

## D2 — Three-way classification collapses onto the existing `ok` boolean, plus one new `truncated` output

**Decision**: "Read back cycle outcome" gains one new output,
`truncated` (`"true"`/`"false"`), alongside its existing `ok`/`converged`/
`reason`/`remaining`. The step's internal logic becomes:

```
advanced = (CYCLE_RESULT == "success" OR VERDICT == "exhausted")
           AND spec-meta.json on origin/<branch> reads stage=implement,
               iteration=$ITERATION
```

then:
- `VERDICT == "exhausted"` AND `advanced` AND progress (D3) →
  `ok=true`, `truncated=true`, `converged=false` (forced — D4).
- `VERDICT == "exhausted"` AND (`!advanced` OR no progress) →
  `ok=false`, `truncated=false` — today's failed path (US3, FR-002's "if
  any one fails, the cycle MUST take today's path").
- `CYCLE_RESULT == "success"` AND `VERDICT != "exhausted"` AND `advanced`
  → `ok=true`, `truncated=false` — today's completed path, byte-for-byte
  unchanged (FR-017).
- Everything else → `ok=false`, `truncated=false` — today's failed path.

No fourth path exists (FR-001): every branch above lands on exactly one of
completed (`ok=true, truncated=false`), truncated (`ok=true,
truncated=true`), or failed (`ok=false`).

**Rationale**: Every downstream consumer of `steps.outcome.outputs.ok`
already exists and already means "advance / hand off rather than retry."
A truncated-with-progress cycle *is* an "advance" outcome (FR-006: no
escalated retry; FR-007/FR-008: start the next iteration or hand off to
finalize, exactly what `ok=true` already drives via "Dispatch next step").
Collapsing truncated onto `ok=true` rather than inventing a third value
that every `if:` condition in the job would need to learn about is the
smallest change that satisfies FR-001–FR-009: the retry step's existing
gate (`steps.outcome.outputs.ok == 'false'`, `implement.yml:962`) already
stops firing for a truncated cycle for free, and the `stalled` job's
existing gate (`needs.implement.outputs.final-ok == 'false'`,
`implement.yml:1494`) already stops firing for free — satisfying FR-006
and FR-009 (including the escalation-tier case, S5/US4) without touching
either gate's condition text. Only `converged` (forced false — D4) and the
reporting steps (D6) need new logic that reads the new `truncated` output.

**Alternatives considered**:
- *A new tri-state `classification` output (`completed`/`truncated`/
  `failed`), rewriting every downstream `if:` to match on it* — rejected:
  touches more surface for the same behavior, and every rewritten `if:`
  is one more place a future edit could silently regress FR-017 (every
  non-truncated path must stay byte-for-byte unchanged). Keeping `ok` as
  the single boolean every existing gate already reads, and adding
  `truncated` only where new behavior is needed, minimizes the diff
  against a stage every one of the six other consumers depends on
  unchanged (constitution VII).
- *Reuse `reason` to encode truncation (e.g. a magic string)* — rejected:
  brittle, and FR-013/FR-015 need a first-class true/false signal for
  reporting, not a string a future edit could reword without noticing it
  was load-bearing.

## D3 — Progress test: two arms, diffed directly, no lifecycle-advance exclusion logic needed

**Decision**: When `VERDICT == "exhausted"` and `advanced` (spec-meta.json
moved to the dispatched iteration), test:

- **Arm A** (task list): count lines matching a checked task in
  `tasks.md` at `BASE_SHA` (`steps.base.outputs.base-sha`,
  `implement.yml:613-616`, recorded before the cycle's agent step runs)
  versus the same file at `origin/<branch>` tip. Progress if the tip's
  count is higher.
  `git show "$BASE_SHA:$SPEC_DIR/tasks.md" | grep -c '^\s*- \[[xX]\]'`
  (defaulting to 0 if the file did not exist at `BASE_SHA`, e.g. a
  first-ever cycle) versus the same read against
  `origin/${SPEC_PREFIX}$SLUG`.
- **Arm B** (work outside the spec directory): any file outside
  `$SPEC_DIR` changed between `BASE_SHA` and the branch tip —
  `git diff --name-only "$BASE_SHA..origin/${SPEC_PREFIX}$SLUG" -- . ":(exclude)$SPEC_DIR/**"`
  non-empty.

Progress is Arm A OR Arm B (FR-004, "either arm alone is sufficient").

**Rationale**: FR-004a requires the lifecycle-record advance (the
`spec-meta.json` commit every cycle — completed or truncated — makes) be
excluded from this comparison and never count as progress on its own.
Because `spec-meta.json` lives *inside* `$SPEC_DIR` and is not `tasks.md`,
it structurally satisfies neither arm — Arm A only reads `tasks.md`'s
checkbox count, Arm B explicitly excludes the whole spec directory. This
means FR-004a's exclusion falls out of the two arms' own scope rather than
needing a third rule that identifies and subtracts one specific commit by
SHA or message prefix (which would be fragile: the cycle prompt uses the
same `implement:` message prefix for every phase commit *and* the
lifecycle-record commit — `implement.yml:722-725,1011-1014` — so
prefix-matching cannot distinguish them). A cycle whose *only* landed
change is the spec-meta.json advance (spec Edge Cases: "whose only commit
is its own lifecycle bookkeeping") therefore fails both arms automatically
and is correctly classified failed — this is FR-018's second required
coverage case.

Counting checked boxes (not diffing added `+- [x]` lines) is deliberate:
it is agnostic to whether a task was newly added and checked in the same
cycle, reordered, or whether the diff algorithm chooses to render the
change as add+remove of a whole line versus an in-place edit — all of
which would perturb a line-diff-based test but not a before/after count.

**Alternatives considered**:
- *Diff `tasks.md` and grep added lines for `- [x]`* — rejected: a
  reformatted or reordered task list would show as remove+add of an
  already-checked task, which a diff-of-added-lines test would
  miscount as new progress; a before/after count of checked boxes is
  immune to reordering.
- *Identify and explicitly exclude the lifecycle-advance commit by SHA*
  — rejected per FR-004a's own wording ("MUST NOT be used as the test")
  and the message-prefix collision noted above; the two-arm scope
  exclusion is simpler and cannot be defeated by a future prompt change
  that reorders which commit carries the advance.
- *Require BOTH arms* — rejected: spec FR-004 explicitly requires either
  arm alone to suffice, and the Assumptions section states the guard is
  deliberately generous ("errs toward carrying forward").

## D4 — Convergence forced false for truncated, independent of the converge-commit scan

**Decision**: "Read back cycle outcome"'s existing convergence scan
(`implement.yml:909-918`, scanning `$BASE_SHA..origin/<branch>` for a
`converge:`-prefixed commit touching `tasks.md`) runs only when
`truncated == false`. When `truncated == true`, `converged` is set to
`false` directly, without running the scan at all — not merely
overriding its result. Edge case "A truncated cycle that was cut off
*after* its convergence pass ran" (a `converge:` commit *is* present) is
handled identically: `converged=false` regardless, one extra cheap cycle
next iteration.

**Rationale**: This is R1 in the source request and User Story 2's
blocking risk — the naive version's failure mode is exactly "infer
convergence from commit absence for a run that never reached the step
that writes the commit." Not running the scan (rather than running it and
discarding a `true` result) makes the invariant impossible to silently
regress by a future edit that reorders the override after the scan:
there is no `converged=true` value ever assigned on the truncated path
for a later line to fail to overwrite.

**Alternatives considered**:
- *Run the scan unconditionally, then `if [ "$TRUNCATED" = "true" ]; then
  converged=false; fi` afterward* — rejected: functionally equivalent but
  leaves a `converged=true` intermediate value sitting in a shell variable
  for one extra `if` to guard against not misordering — exactly the shape
  of defect the spec's R1 names ("a naive flip of ok to true would
  compute converged=true... any implementation must special-case
  error_max_turns to force converged=false, never inferring convergence
  from commit absence"). Skipping the scan entirely removes the
  intermediate state a future edit could accidentally ship past.

## D5 — Consecutive-truncation counter lives in spec-meta.json, written deterministically alongside the outcome, not by the agent

**Decision**: `spec-meta.json` gains one new field, `truncated_count`
(integer, absent/treated as 0 by every reader — `jq -r '.truncated_count
// 0'`). A new deterministic step, "Record truncated-cycle count",
running immediately after "Consolidate final outcome"
(`implement.yml:1201-1230`) and before "Flip stage label (first cycle)"
(`implement.yml:1401-1414`)/"Dispatch next step"
(`implement.yml:1422-1485`), computes `new_count =
truncated=="true" ? current+1 : 0` against the current value read from
`origin/<branch>`'s `spec-meta.json`, and — only when `new_count !=
current` — commits and pushes the patched file (`jq '.truncated_count =
$new_count'`, message `implement: record truncated cycle (consecutive
count=$new_count)"` or `"implement: reset truncated-cycle count"`),
mirroring the `stalled` job's existing no-agent jq-patch-commit-push
shape (`implement.yml:1580-1600`) rather than asking the agent to
maintain it. The step's own output (`count=$new_count`) feeds "Dispatch
next step"'s reporting (D6).

**Rationale**: The agent that ran the truncated cycle cannot reliably
report on its own truncation — by definition it never got to write a
final summary of what happened to it; the pipeline's own deterministic
bookkeeping is the only thing that reliably observes `truncated=true`
after the fact (the same reasoning `implement.yml`'s existing lifecycle-
record advance and the `stalled` job's stage-flip already use — spec-meta
state that describes what happened to a run is written by the workflow
that observed it, not by the run itself). Running this step unconditionally
(not gated on `ok=='true'`) — so it also fires and resets the counter on a
genuine failure — satisfies FR-011's "a cycle that completed or failed
MUST reset that count" for every terminal shape, including a failed
cycle that goes on to `stalled`: without this, a feature that stalls once
after two truncations, gets manually restarted, and truncates again would
report "third consecutive truncation" when the failed/stalled cycle in
between should have reset it to one.

**Alternatives considered**:
- *Have the agent prompt update `truncated_count` alongside `stage`/
  `iteration`* — rejected: the agent that would need to write "I was
  truncated" is precisely the agent that got cut off before finishing
  its own turn; a truncated run has no reliable opportunity to record
  anything about itself beyond what it already pushed mid-phase. Every
  other piece of state this feature needs (the verdict, the classification,
  the progress test) is already computed by the workflow after the run
  ends, for the same reason.
- *Gate the reset-write on `ok=='true'` only, leaving a stalled run's
  stale count untouched* — rejected per the FR-011 gap identified above:
  a stall-then-restart sequence would otherwise under-report or over-count
  consecutive truncations across the manual restart boundary.
- *Store the counter as a GitHub Actions run output threaded through
  workflow dispatch inputs instead of spec-meta.json* — rejected:
  `implement.yml`'s self-dispatch (`implement.yml:1447-1448`) does not
  carry arbitrary state between separately-dispatched runs today, and
  adding a new `workflow_call`/`workflow_dispatch` input for it would
  touch the stage's declared inputs, which FR-021 forbids. `spec-meta.json`
  is already the machine-readable state carried across dispatches
  (constitution "Operational Constraints": "the machine-readable source
  of truth for a spec's lifecycle state").

## D6 — Reporting: extend "Dispatch next step"'s existing deterministic branches, not the agent-authored progress comment

**Decision**: "Dispatch next step" (`implement.yml:1422-1485`) gains a
`TRUNCATED`/`TRUNCATED_COUNT` env pair (from `steps.final.outputs.truncated`
and the new counting step's `count` output) and two new message branches,
inserted before the existing `CONVERGED != true` branches so a truncated
cycle never falls into the generic "completed without converging" wording:

- Not at cap: "⏱️ **Cycle N ran out of its turn budget.** N tasks/work
  already landed on the branch; cycle N+1 continues on `$TIER` (consecutive
  truncations: K)." — never says "failed," never says "did not converge"
  with no explanation (US1 AS4, FR-013, FR-015).
- At cap: "⚠️ **Iteration cap reached** — the last cycle (N of MAX) ran
  out of turns before it could assess what remained. Handing off to
  finalization flagged **converged=false**." — replaces the
  `$REMAINING`-block body (which would otherwise print nothing, since a
  truncated cycle never writes the `converge:` commit `$REMAINING` is
  derived from) with the FR-014-required explanation instead of an empty
  fenced block that reads as "nothing left to do."

The existing "Report run started on lifecycle issue" step
(`implement.yml:598-609`) and "Flip stage label (first cycle)"
(`implement.yml:1401-1414`) need no change — both already fire on any
`ok=='true'` cycle including a truncated one, at the tier it actually ran
on (`inputs.model`), which is what US1 AS1 requires ("the next iteration is
started at the same tier the cycle ran on").

**Rationale**: Every existing lifecycle-issue post in this job is
deterministic bash, not an agent turn — the file's own comment at
`implement.yml:874-877` states the "Read back cycle outcome" family is
"deterministic (no agent turns): the attempt 'completed' only if..."
Extending that same deterministic step keeps the reporting behavior
provably tied to the same `steps.final.outputs.*` values the rest of the
job's control flow already uses, rather than duplicating the truncation
signal into a second, agent-driven surface ("Post progress comment
(haiku)", `implement.yml:1274-1321`) whose wording an LLM composes and
which is materially harder to pin down in coverage (FR-018 requires the
coverage assert on exact classification/convergence outcomes, which a
free-text agent-authored comment cannot be asserted against
deterministically).

**Alternatives considered**:
- *Add the truncation line to the haiku-authored progress comment's
  prompt instead* — rejected: that comment is agent-composed free text;
  making the truncation disclosure depend on an agent correctly
  incorporating a prompt instruction (rather than a deterministic branch
  a coverage script can assert on byte-for-byte) is a weaker guarantee for
  exactly the requirement (FR-013/FR-015) whose whole point is legibility.
  The progress comment is left unchanged; the truncation disclosure lives
  entirely in the deterministic "Dispatch next step" body, which already
  is the step a maintainer reads for "what happens next."

## D7 — The escalated retry, when it itself truncates, is classified by the identical rule against its own base

**Decision**: "Read back retry outcome" (`implement.yml:1146-1196`)
receives the same treatment as D1–D4, reading
`steps.retry-verdict.outputs.verdict` (the retry's own copy of the verdict
composite, already computed by "Compute agent run verdict (retry)"
upstream of it in the existing job) and gaining its own `truncated`
output. Its progress test (D3) is measured against a **new** "Record retry
base SHA" step, added immediately before "Implement and converge (retry at
escalation model)" runs, capturing `origin/<branch>`'s tip at that moment
— i.e., wherever the primary attempt left the branch — not the original
`steps.base.outputs.base-sha` from before the primary attempt ran. "Consolidate
final outcome" (`implement.yml:1201-1230`) picks the retry's `truncated`
value when the retry ran, exactly as it already picks `ok`/`converged`/
`remaining`/`tier` from whichever attempt ran (`implement.yml:1217-1221`).

**Rationale**: Spec Edge Cases: "The escalated redo itself runs out of
turns... it is carried forward on the same terms as any other truncated
cycle" and FR-016: "classified by the same rules as any other cycle
(FR-002)." "The same rules" includes the progress test's own definition —
"comparing the branch as it stood at the *start* of the cycle" (FR-004).
For the retry, "the cycle" is the retry itself: the retry's own prompt
explicitly starts from wherever the primary attempt's push left the
branch (`git reset --hard origin/<branch>`, `implement.yml:1000-1002`,
"some work from that attempt may already be committed — take the branch
as you find it"), not from a cold reset to the original `base-sha`.
Measuring the retry's progress against the *original* `base-sha` would
count the primary attempt's own partial work as the retry's progress even
if the retry itself achieved nothing in its own turns — exactly the S2
no-progress failure mode this feature must not let happen at the
escalation tier.

**Alternatives considered**:
- *Reuse the original `steps.base.outputs.base-sha` for the retry's
  progress test too* — rejected per the rationale above: it would let a
  retry that made zero progress of its own inherit "progress" from the
  primary attempt's partial work and be wrongly carried forward instead
  of escalating further (there is nowhere further to escalate to at that
  tier, which is exactly S5/US4's scenario) or (correctly) stalling.

## D8 — Coverage: Gate 26, following Gate 14's real-git-repo shape, not Gate 22's transcript-only shape

**Decision**: New `.github/scripts/verify-truncated-cycle-carry-forward.py`,
wired as **Gate 26** (next unused — confirmed against every `Gate N —`
occurrence in `.github/workflows/lint-workflows.yml`; the highest in use
is Gate 25, `lint-workflows.yml:1729`, from specs/039-lifecycle-gate-retry)
in `.github/workflows/lint-workflows.yml`, following `verify-stall-restart-
runbook.py`'s (Gate 14) shape — a real git repository with a local bare
remote, driving the shipped `run:` blocks of "Read back cycle outcome",
"Read back retry outcome" (a lighter pass, D7), "Consolidate final
outcome", "Record truncated-cycle count" (D5), and "Dispatch next step"
(D6) directly out of `implement.yml`'s own text via `wc_shell_harness.py`'s
`find_step`/`run_step`, exactly as Gate 14 does for "Mark lifecycle record
stalled". Gate 22's shape (a synthetic transcript JSON fed to the verdict
*composite*) is not reused directly here because this feature's steps
never read a transcript — they read `steps.cycle-verdict.outputs.verdict`,
which the harness supplies as a plain env var standing in for the upstream
step's output, the same way Gate 14 already supplies `RECORDED`/
`ISSUE`/etc. as env inputs to the step under test without re-running every
upstream step in the job.

Six synthetic scenarios (FR-018): (1) exhausted, Arm-A progress (task
newly ticked), no converge commit → truncated, not converged; (2)
exhausted, only the lifecycle-record-advance commit landed → failed,
today's path; (3) exhausted, Arm-A-only progress → truncated; (4)
exhausted, Arm-B-only progress (a file outside `$SPEC_DIR` changed, no
task ticked) → truncated; (5) an ordinary failure (`verdict=failed`, or
`CYCLE_RESULT=failure` with a non-exhausted verdict) → failed, today's
path unchanged; (6) a normal successful cycle (`verdict=healthy`) →
today's completed/converged behavior, byte-for-byte unchanged.

Five required mutations (FR-019), each applied to a copy of the shipped
step text and asserted to flip at least one scenario's expected result:
revert D4 (let the converge-commit scan set `converged=true` on a
truncated cycle); revert D2's no-progress guard (classify `exhausted` as
`truncated` without checking either arm); drop Arm A; drop Arm B; widen
the `VERDICT == "exhausted"` check to also match `VERDICT == "failed"`
(an ordinary failure gets carried forward). A sixth "reflexive" check —
Gate 26 itself present and wired in `lint-workflows.yml`, per Gate 25's
own D7 pattern — satisfies FR-020.

**Rationale**: This feature's shipped logic lives entirely in `run:`
blocks inside one workflow file with real git commit/push side effects
(the counter write, D5) — Gate 14's shape (a real repo, a real bare
remote, the actual step text executed by the actual shell) is what proves
a commit/push path really executes, exactly as Gate 14's own rationale
states ("It runs in a real git repo with a local bare remote so the
step's commit/push path executes for real"). Gate 22's shape fits a
composite whose entire job is transcript classification with no git
side effects; this feature's steps are the opposite — they assume the
verdict is already known and act on git state.

**Alternatives considered**:
- *Feed a real synthetic transcript through the verdict composite and
  the outcome step together, end-to-end* — rejected as unnecessary
  coupling: the verdict composite's own correctness is Gate 22's job, already
  proven; re-testing it here would duplicate coverage without adding
  confidence in *this* feature's own logic (the progress test and the
  forced-not-converged rule), and would make Gate 26 fail on the wrong
  thing if the verdict composite itself ever regressed.
- *A paired self-test step (the Gates 16/18/22/23 shape)* — rejected for
  the same reason as spec 039's D7: this gate directly executes shipped
  step text and asserts on outputs, matching Gate 14's shape, not a
  detector-plus-self-test shape.
