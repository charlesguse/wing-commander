# Phase 0 Research: An Implement Run That Dies at Entry Still Marks the Record and Says So on the Issue

spec.md carries no `[NEEDS CLARIFICATION]` markers. It does, however, leave
several *design* questions genuinely open — it says so explicitly ("a design
question rather than a decided one" for the five-stage scope; edge cases that
describe a shape without naming a mechanism). Phase 0 resolves those,
including three decisions this plan makes without a clarification round,
called out below and reported on the lifecycle issue per this pipeline's own
process (they are design calls within the spec's stated intent, not
ambiguities the spec left the requester to answer).

## D1 — Two mechanisms, not one: in-job refusal callout vs. a survivor job

**Decision**: Refusal and abnormal termination are handled by two different
shapes, not one shared job.

- **Refusal** is always detected and reported from *inside the job that
  refused* — an `always()`-gated step added immediately after each
  refusing step, in the same job, calling the existing
  `wing-commander-callout` composite. This works because a refusing step, by
  definition, ran: the job did not skip, it failed after one of its own
  steps declined. `always()` on a later step of a job that ran (as opposed to
  a job that was skipped outright) resumes execution at that step
  regardless of what failed before it — no cross-job `needs:` machinery is
  needed at all.
- **Abnormal termination** needs a genuinely separate **survivor job**,
  because its defining case (spec Acceptance Scenario 3: "the entry-level
  dependency fails so the implement job never starts at all") means the job
  in question ran *zero* steps. `always()` on a step inside a skipped job
  does nothing — the job itself never started, so none of its steps
  evaluate, `always()` included. Only a separate job, related by `needs:`
  with its own status-check function, can react to an ancestor that never
  ran (research.md D4 below; this is exactly why `implement.yml`'s `stalled`
  job already exists as a separate job for the one case it covers today).

**Rationale**: Building one mechanism for both would force the survivor job
to also carry refusal-detection logic across a `needs.*` boundary, which is
exactly the boundary spec's own edge case worries about ("A refusing step
that emits no signal ... is treated as a crash. The safe default is to speak
loudly rather than to infer a refusal from an absent value"). Keeping refusal
in-job means the refusal signal never has to cross a job boundary to be
*acted on* — only the one narrow fact "did a refusal happen" (D3 below) needs
to cross that boundary, and only so the survivor job can avoid firing a
second notice for the same failure (FR-006).

**Alternatives considered**:
- *One job, both mechanisms, distinguishing by re-reading step outputs
  across `needs.*`* — rejected: forces every refusal detail (which step,
  what reason, what to tell the human) through the same fragile
  cross-job-output channel FR-003 already warns is unreliable for a
  terminated job, when the in-job path needs none of that plumbing at all.
- *Route refusal through the survivor job too, for a single "one job posts
  everything" narrative* — rejected: would mean every refusal pays for a
  second job's scheduling/checkout/token-mint overhead for no behavioral
  gain, on the *common* not-a-stall path (a refusal is not rare the way an
  entry-level dependency failure is — it is the pipeline's normal response
  to a missing secret on first adopter setup).

## D2 — The refusal signal: outputs written before `exit 1` survive the step's own failure

**Decision**: Every refusal-shaped step gains two outputs, `refused`
(`"true"`/unset) and `reason` (free text), written to `$GITHUB_OUTPUT` as the
*last thing the step does before `exit 1`*. This is the entirety of FR-005a's
"positive signal": a step that refuses always writes `refused=true` before
failing; a step that crashes never reaches that line, so `refused` stays
unset — never inferred from absence, always set by the step that means it.

This relies on one GitHub Actions guarantee this repository has not
previously needed to state explicitly: **a step's outputs, once written to
`$GITHUB_OUTPUT`, are captured by the runner and available to
`steps.<id>.outputs.*` regardless of the step's own exit code.** Only a
*skipped* step (never ran) has no outputs; a step that ran, wrote its output
file, and then exited non-zero keeps what it wrote. Every existing refusal
site in this fleet (`wing-commander-preflight`'s `fail()`, `implement.yml`'s
`Resolve and validate spec identity` and `Verify spec artifacts match the
dispatch`) already follows the shape `echo "::error::..."; exit 1` with no
output write at all — this plan adds exactly one line, `echo
"refused=true" >> "$GITHUB_OUTPUT"` (`fail()`'s case: parameterized by the
caller's reason text) or `echo "reason=$msg" >> "$GITHUB_OUTPUT"` immediately
before each existing `exit 1`, changing nothing else about those steps.

**Rationale**: This is the only mechanism available that satisfies FR-005a's
"MUST NOT be inferred from an absent, empty, or unset value" — the value is
either explicitly written (refusal) or genuinely never written (crash), with
no third state and no reliance on an `if:` that treats "empty" as meaningful
on its own (which is precisely the `'' == 'false'` defect this whole feature
exists to close, spec.md's own framing of the bug).

**Alternatives considered**:
- *A shared exit-code convention* (e.g. refusals exit 2, crashes exit 1) —
  rejected: GitHub Actions does not expose a step's raw exit code to `if:`
  expressions on other steps or jobs, only `outcome`/`conclusion`
  (`success`/`failure`/`cancelled`/`skipped`), so a distinct exit code carries
  no information a downstream `if:` could read at all. Outputs are the only
  channel that survives.
- *A file dropped in `$RUNNER_TEMP`, checked by a later step* — rejected:
  works within a job (no advantage over an output) but cannot cross the job
  boundary the survivor job needs, unlike a declared job output.

## D3 — Job outputs from a job that ran and failed are reliable; job outputs from a skipped job are not

**Decision**: The six entry jobs each gain one new job-level output,
`refusal-reason`, mapped as `${{ steps.a.outputs.reason || steps.b.outputs.reason || ... }}`
across every refusal-shaped step in that job. The survivor job (D1) reads
`needs.<entry-job>.outputs.refusal-reason` to decide whether the
abnormal-termination arm should stay silent (a refusal already produced its
own notice, in-job, per D1 — firing again here would violate FR-006). This
is safe specifically because refusal only ever happens in a job that *ran* —
by construction (D1), a job that never started cannot have refused, so this
read is only ever attempted in the branch where it is trustworthy.

The contrast this decision rests on: `watchdog.yml`'s `report-unhandled-
failure` job deliberately does **not** trust `needs.collect.outputs.
lifecycle-issue`, and instead re-derives the lifecycle issue independently.
That precedent is not evidence that failed-job outputs are unreliable in
general — it is guarding against a narrower hazard: `collect` might fail
*before* the specific step that would have set that output ever ran, so the
output was genuinely never written, for the ordinary reason (D2) that a
step which never executes has no output to give. `refusal-reason` does not
have this problem: every refusal-shaped step in a given job runs early
(preflight, spec-identity/spec-artifact validation), before any step whose
own failure could pre-empt it, and the `||` chain across all of a job's
refusal-shaped steps means the output resolves correctly regardless of which
one (if any) actually refused.

This is also exactly why identity (spec-dir, issue-number, iteration) is
**not** read this way (FR-003) — those values are set by steps that may sit
*after* an earlier failure, so the failed-before-computing hazard applies to
them but not to `refusal-reason`. Section D6 details per-stage identity
resolution using only `inputs.*` and independent re-derivation instead.

**Rationale**: Confirms and narrows FR-003 rather than contradicting it —
FR-003 is about identity, and this decision is about a single boolean-shaped
signal read only in a branch where its trustworthiness is structurally
guaranteed, not read speculatively.

**Alternatives considered**: See D1's alternatives — the rejected "route
refusal detection through the survivor job for everything" option would have
made this decision moot by never needing to cross the job boundary in the
first place; it was rejected on cost grounds (D1), not because this
boundary-crossing read is unsafe.

## D4 — Survivor job condition: `!cancelled()`, not `always()`

**Decision**: Every new/widened `stalled` job's `if:` opens with
`!cancelled()`, following the `#224` idiom's own general form
(`always() && needs.X.result == '<value>' && ...`) but substituting
`!cancelled()` for `always()` at the top level.

```yaml
needs: [<one-level-above-dependency>, <entry-job>]
if: |
  !cancelled() &&
  ( needs.<one-level-above-dependency>.result == 'failure' ||
    needs.<entry-job>.result == 'failure' ||
    needs.<entry-job>.result == 'skipped' ||
    needs.<entry-job>.outputs.<exhausted-retry-flag> == 'false' )
```

**Rationale**: `always()` also evaluates true when the run was cancelled;
`!cancelled()` evaluates true whenever the job would otherwise run
(success/failure/skipped ancestors) but false specifically when a human
cancelled the run — exactly FR-009 ("A cancelled run MUST NOT produce the
notice and MUST NOT alter the record") and the Edge Cases entry it restates
("A cancellation is someone deciding to stop... reporting it as a stall would
turn every deliberate cancel into a stalled specification"). This repository's
one existing precedent for this shape, `watchdog.yml`'s
`report-unhandled-failure`, uses `always()` — but the watchdog has no
requirement analogous to FR-009 (a cancelled watchdog run reporting nothing
useful is merely wasted effort, not a mislabeled specification), so it is not
a reason to prefer `always()` here. Gate 15's own prescribed fix text ("Prefix
the `if` with `!cancelled() &&` (or `always() &&`)") already treats the two
as interchangeable defaults for its shape check; this feature is the case
where they are *not* interchangeable, and picks the one FR-009 requires.

**Alternatives considered**:
- *`always()` plus an explicit `github.event.workflow_run.conclusion !=
  'cancelled'`-style guard* — rejected: more verbose than `!cancelled()` for
  the same effect, and `!cancelled()` is GitHub's own documented function for
  exactly this purpose (true unless the run was cancelled), needing no
  reference to event payload shape at all — consistent with constitution VII
  (a stage reads no `github.event.*`).

## D5 — Intake's "no record yet" is the same branch as "record could not be written," not a special case

**Decision**: The new composite (`wing-commander-chain-stop-notice`) is
called with an empty `spec-dir` for intake — always, because `intake`'s dying
at entry means, by construction, no `spec-meta.json` was ever written for
this feature. The composite's record-mark step is unconditionally skipped
when `spec-dir` is empty, and the notice it posts uses the *same* wording
path spec.md's own Edge Cases entry already requires for a different cause
("The record cannot be written... The notice is still posted, and it says the
record could not be updated"). Intake does not get a bespoke "no specification
exists" sentence; it always takes the branch every other stage takes only on
the rarer force-push-race/missing-branch failure.

**Rationale**: The spec's Scope Question explicitly leaves "whether those
[five non-implement stages] need an equivalent notice" open as "a design
question rather than a decided one," but FR-017 answers it in the
affirmative for all six stages, including intake — so intake must produce
*some* notice. What it cannot do is the literal three-effect FR-001 sequence,
because "mark the specification's lifecycle record as stalled" presupposes a
record. Re-using the existing "could not be updated" branch, rather than
inventing a fourth notice shape, keeps the composite's contract to exactly
two rendered outcomes ("marked" / "could not be updated") regardless of
*why* the mark did not happen — simpler to build, simpler for Gate 28 to
cover, and it reads correctly to a maintainer either way: "this stage did not
start, and the record could not be confirmed as stalled" is true whether the
record does not exist yet or could not be reached this time.

For intake specifically, the label half of the notice (FR-001's second
effect) still applies: `stage:stalled` can be applied to the issue even
though no spec-slug/spec label exists yet, since the label lives on the
*issue*, not inside `spec-meta.json`.

**Alternatives considered**:
- *A fourth, intake-specific notice wording ("this feature never became a
  specification")* — rejected: adds a rendered-output variant Gate 28 would
  need its own fixture for, for a distinction (never-existed vs.
  can't-currently-write) a maintainer does not need to act on differently —
  the runbook response ("re-dispatch intake") is identical either way.

## D6 — Per-stage identity resolution, using only declared inputs and independent re-derivation

**Decision** (FR-003's operative table): the survivor job never reads
`needs.<entry-job>.outputs.*` for spec-dir/issue-number/iteration (only
`refusal-reason`, D3) — it resolves identity from that stage's own
`workflow_call` inputs, re-deriving anything not directly declared using the
same read-only lookups the pipeline already performs elsewhere.

| Stage | Directly declared | Re-derivation needed | Mechanism |
|---|---|---|---|
| implement | `spec-dir`, `issue-number`, `iteration` | none | already available (today's job, unchanged) |
| finalize | `spec-dir`, `issue-number` | none | already available |
| clarify | `issue-number` | `spec-dir` | independent `gh issue view --json labels`, parse `spec:*` label — the same lookup `wing-commander-context`'s `resolve` step already performs, run again here rather than trusted from a job that may not have reached it |
| intake | `issue-number` | `spec-dir` — none exists (D5) | N/A — record-could-not-be-updated branch always taken |
| pr-conversation | `pr-number` | `spec-dir`, `issue-number` | independent `gh pr view` on the head ref to recover the `spec/NNN-slug` branch name, then the same `spec-meta.json`-read `meta` step already performs, run again here. When this re-derivation itself fails, the notice posts to `pr-number` directly (`gh issue comment` — a PR *is* an issue at the API level) rather than to an unknown lifecycle issue: `pr-number` is the one identifier guaranteed present regardless of how early the job died |
| tasks (`mode: generate`) | `head-ref` or `slug` | `spec-dir` (string derivation only, `specs/<slug>`), `issue-number` | `spec-dir` needs no lookup — `slug` parses directly from `head-ref` when `slug` itself is empty; `issue-number` via `gh api .../contents/$SPEC_DIR/spec-meta.json -f ref=<branch>` (no full checkout), the same call `pr-conversation`'s `meta` step already makes |
| tasks (`mode: approved`) | `head-ref` or `slug` | same as `generate` | same as `generate` |

**Rationale**: This is FR-003 read literally — "identify the specification,
the lifecycle issue, and the iteration from the stage's own declared inputs,
which are present regardless of how far the run got" — combined with the
watchdog precedent (independent re-derivation over trusting a possibly-unset
job output) for every value not directly declared. No stage needs a new
`workflow_call` input to make this table work (FR-016); every re-derivation
uses a lookup the pipeline already performs somewhere in that same file.

**Alternatives considered**:
- *Add `spec-dir`/`issue-number` as new declared inputs to clarify/
  intake/pr-conversation/tasks* — rejected outright: this is exactly the
  `workflow_call` surface widening FR-016/SC-008 forbid, and would require
  every wrapper workflow calling those stages to be edited, which FR-016
  also forbids ("no adopter may need to edit a wrapper workflow to receive
  this fix").

## D7 — The existing exhausted-retry arm stays untouched, at the cost of one internal duplication

**Decision**: `implement.yml`'s `stalled` job keeps its current three steps
(`Mark lifecycle record stalled`, `Report stalled on lifecycle issue`,
`Announce the stall on the lifecycle issue`) exactly as they are today,
each additionally guarded by `needs.implement.outputs.final-ok == 'false'`
(true today, stated explicitly now that the job's `if:` admits more than
this one case). The new abnormal-termination steps, calling the new
composite, are added alongside — guarded by the complementary condition
(`needs.implement.outputs.final-ok != 'false'`, i.e., not the
exhausted-retry case) `&& needs.implement.outputs.refusal-reason == ''`
(D3, mutual exclusion with the in-job refusal callout).

**Rationale**: Out of Scope is explicit — "Rewording the existing
exhausted-retry stall notice ... This feature adds a case; the current
wording for the current case stays" — and User Story 2's third acceptance
scenario requires the exhausted-retry notice to "read exactly as it does
today." The safest way to guarantee zero characters of that notice change is
to not touch the code that renders it. The cost is that `implement.yml` ends
up with two notice-producing code paths inside one job (today's inline steps,
and the new composite call) rather than a single unified path — accepted
explicitly as a one-time cost against the risk of an accidental rewording a
text-diff review might miss in five hundred lines of surrounding YAML.

**Alternatives considered**:
- *Migrate the exhausted-retry arm into the new composite too, rendering
  byte-identical output* — rejected: the existing notice's markdown
  (runbook table, restart command, `<details>` block) is bespoke enough that
  parameterizing the composite to reproduce it exactly adds real complexity
  to the composite's contract for a case this feature is not asked to change
  at all, in exchange for internal tidiness only.

## D8 — Gate 28's mechanism: a minimal `needs.*` expression evaluator, not a live workflow run

**Decision**: `.github/scripts/verify-chain-stop-notice.py` implements a
small evaluator for the subset of GitHub Actions expression syntax the six
survivor-job conditions (D4) and the refusal-mutual-exclusion conditions (D7)
actually use — `!cancelled()`, `&&`/`||`, `==`/`!=`, and
`needs.<job>.result`/`needs.<job>.outputs.<name>` substitution — parameterized
by a table of `(needs.* result/output values) -> expected boolean` fixtures
per survivor job, extracted from the shipped `if:` string via `wc_shell_
harness.py`'s existing `find_step`-style YAML access (extended to jobs, not
just steps). This is new: neither Gate 15 (checks the condition's *shape*
via regex/AST, never evaluates it against modelled inputs) nor
`wc_shell_harness.py` (executes step-level shell only, never a job-level
`if:`) provides this today.

**Rationale**: FR-012/User Story 4 require coverage that "models a stage run
which actually failed" and asserts the notice path is *reached* — this can
only be proven by evaluating the shipped condition against a modelled
`needs.*` value, not by inspecting its text. FR-013's four negative
mutations (widen, narrow, remove-guard, wire-a-stage-off-the-shared-shape)
are, likewise, mutations to the condition string whose effect is only
checkable by re-evaluating it. A full `act`-style local runner was
considered and is disproportionate: this feature needs to evaluate a small,
fixed expression grammar against a table of inputs, not execute arbitrary
job graphs.

**Alternatives considered**:
- *Extend Gate 15 itself to also do behavioral evaluation, not just shape
  detection* — rejected: Gate 15's whole design is a fast, purely static
  scan across every job in every workflow (its `NON_SUCCESS_ARM`/
  needs-closure walk apply uniformly, with no per-job fixture data). Folding
  in a per-job table of expected results for six specific survivor jobs would
  turn a general-purpose gate into a special case of itself; a second,
  focused gate (28) is more in keeping with this repository's one gate =
  one property convention (Gate 14 vs. Gate 15 is the direct precedent: two
  neighboring but distinct checks over the same job).
- *Shell out to a real `act` invocation* — rejected: not installed in this
  repository's CI image today, adds a real dependency for a grammar this
  feature only needs a slice of, and would make Gate 28 slower and harder to
  reason about than a ~100-line Python evaluator scoped to exactly the
  expressions this feature ships.

## D9 — Gate 15 amendment: broaden `NON_SUCCESS_ARM` to output-based conditions

**Decision**: `.github/scripts/verify-gate-15.py`'s pattern for "an `if:`
arm that only means something on non-success, with no status-check function"
is extended to also match `needs.<job>.outputs.<name> == '<value>'`
comparisons that are structurally analogous to a `.result` comparison — not
just literal `needs.X.result == 'failure'|'skipped'|'cancelled'`. The
existing `CASES` fixture list keeps every current entry unchanged and gains
new cases for the output-based shape, run against a synthetic fixture
mirroring `stalled`'s actual pre-fix condition
(`needs.implement.outputs.final-ok == 'false'`, no status function) so the
regression this feature fixes is provably caught by Gate 15 from this point
forward — not merely fixed once and left undetectable if it recurs
elsewhere.

**Rationale**: FR-015 requires exactly this — "If that gate's rules must
change to admit the new condition, the change MUST NOT reduce the set of
shapes it detects, and the shape this feature fixes ... MUST be detectable
afterwards rather than merely absent from the tree." Fixing `stalled`'s
condition without teaching Gate 15 to see the *class* of defect would leave
the next output-based survivor job (any future stage that copies this
pattern without the `!cancelled()`/`needs.*.result` guard) invisible to the
one gate whose job is to catch it.

**Alternatives considered**:
- *Leave Gate 15 as-is, rely on Gate 28 alone to prove this feature's six
  conditions are correct* — rejected: Gate 28 only covers the six shipped
  conditions this feature adds; it says nothing about a *seventh* stage
  added later with the same defect. Gate 15's value is exactly that it scans
  every job in every workflow, unconditionally — narrowing its blind spot is
  a strictly cheaper, more durable fix than adding more fixed-shape coverage
  per stage forever.

## D10 — What is genuinely a "refusal" today: preflight and the two implement identity checks, and nothing wider

**Decision** (made without further clarification — reported on the lifecycle
issue): the lifecycle-gate composite's own permanent failures (issue
not-found, credential rejected — spec 039's already-landed classification)
are treated as **abnormal termination**, not refusal, even though they are
also "declared reasons" in a loose sense. Only `wing-commander-preflight`'s
credential/spec-kit checks and `implement.yml`'s `Resolve and validate spec
identity` / `Verify spec artifacts match the dispatch` steps (which already
say "refusing" in their own error text) gain the refusal signal in this
plan's scope; the other five stages' equivalent validation steps (identified
during Phase 2 tasks generation by grepping each workflow for the same
`wing-commander-preflight` call and any analogous inline "refusing" check)
get the same treatment, applied by the same rule, not by an enumerated list
fixed at plan time.

**Rationale**: spec.md's own refusal examples are consistently
precondition-shaped ("a missing credential, a missing spec-kit skill, a
malformed spec hand-off") — properties of *this stage's own inputs and
environment* that it can check before doing anything. The lifecycle gate's
failures are a different kind of thing: an inability to read shared state
(the issue) that every stage depends on symmetrically, not a precondition of
the *specific* stage being asked to run. Classifying it as abnormal
termination means a lifecycle-gate failure gets the fuller stall treatment
(record marked, label flipped, restart runbook) — arguably the more useful
response anyway, since "the issue could not be read" is exactly the kind of
transient-infrastructure-shaped problem a maintainer would want flagged as
stalled-and-restartable rather than dismissed as a declared, expected
refusal.

**Two further decisions made without clarification**, both already
documented in-line above and restated here for the issue comment:
- D5: intake's chain-stop notice always renders as "record could not be
  updated," never a distinct "no specification exists" wording.
- D6 (pr-conversation row): when spec/issue identity cannot be re-derived
  independently, the notice posts to the PR itself (`pr-number`) rather than
  to an unresolvable lifecycle issue — the PR conversation is the surface
  the maintainer is already on, and is the only identifier FR-003 guarantees
  survives every failure shape on this stage.

## D11 — An image-prerequisite failure is excluded from the chain-stop notice (Gate 23 fix, maintainer feedback)

**Decision**: each of the seven survivor-job `if:` conditions (D4) gained a
new leading conjunct, `needs.verify-image-prerequisites.result == 'success'
&&`, so the chain-stop notice no longer fires when `verify-image-
prerequisites` itself failed. It is still true that a stage whose image
prerequisites failed died at entry — but the survivor job that would post the
notice runs its own steps inside `${{ inputs.container-image }}`, the very
image `verify-image-prerequisites` just failed to validate, where `gh`/`jq`/
`git` cannot be trusted to run at all. `verify-image-prerequisites`'s own
loud failure is the adopter-facing signal for this cause instead; asking the
survivor job to also report from inside a container that may not work is the
defect Gate 23 (`lint-workflows.yml`) flags.

**Rationale**: Gate 23 already treats "a job whose steps assume a container
that a same-run dependency failed to validate" as a defect pattern across
this repository; the chain-stop notice's own survivor jobs were not exempt
from that pattern merely because they exist to report failure. Excluding
this one upstream cause keeps the survivor job itself confined to
`verify-image-prerequisites == success`, where its `gh`/`jq`/`git` steps are
trustworthy again.

**Scope note**: this narrows spec.md's Acceptance Scenario 3 and the
matching Edge Cases bullet ("the dependency one level above the implement
job fails ... the notice is posted") to exclude specifically the
`verify-image-prerequisites` upstream case. The rest of Acceptance
Scenario 3 — a stage's own entry job failing or being skipped for a
non-image reason — is unaffected and still fires the notice.

**Verification**: `wc_chain_stop_conditions.py`'s `fixtures_for()` row
"upstream dependency failure, entry job skipped" now expects `False` for
every call site (was `True`); Gate 33 (`verify-chain-stop-notice.py`) gained
a fifth mutation, stripping this new leading conjunct, which the existing
fixture table now catches without further changes; the refusal-exclusion
check (User Story 3) reuses the same shared fixture table and inherits both
changes automatically.
