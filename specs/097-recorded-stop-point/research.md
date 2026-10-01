# Phase 0 Research: An Honoured Stop Records Its Stop Point

All items below are plan-stage decisions this feature needs in order to
implement FR-001..FR-020 against the actual state of `main`. spec.md itself
carries no `[NEEDS CLARIFICATION]` markers (its own Clarifications session
and the 2026-09-30 status update already resolved every open question with
the owner or with a merged sibling spec), so every decision below is a
plan-stage design choice, not a spec clarification — each is called out
explicitly for the "Decisions made without clarification" section of the
lifecycle issue comment.

## D1 — Where the recording logic lives, and what it must not touch

**Decision**: All new logic — deciding *which* stand-down cause applies and
writing the stop-point record — lives inside
`.github/actions/wing-commander-board-stop-check/action.yml` and a small,
additive extension of `.github/scripts/board_stop_check.py`. The existing
`find_stop_request()` function, its `StopDecision(stand_down,
cancel_run_id)` two-field return shape, and its `main()` stdin/stdout CLI
contract are **not modified** — not even refactored internally — because
spec 097's own Dependencies section binds this: *"This feature adds a
consequence to `stand_down`; it must not alter the decision itself or the
cancel path."* Gate 87 mutation-proves `find_stop_request()` today
(`specs/057-autonomous-board-loop/contracts/gate-87-coverage.md`); leaving
its body untouched removes any risk of that gate suite drifting out of
sync with this change.

**Addendum (maintainer review fold leg-1, FR-006/FR-008)**: this "not
modified" decision turned out to have a real gap once the record-write
itself existed: `find_stop_request()`'s own baseline loop treats any
bot-authored `**Run:**` marker, from any run, as advancing the baseline —
including THIS run's own stop-point record, which carries write_marker()'s
`**Run:**` line like every other loop-posted comment. Left as designed, the
record's own marker (posted strictly after the stop comment it is
recording — in the common case, it is the run's ONLY same-run marker, since
a job that stands down does not go on to post its own ordinary outcome
marker too) would move the baseline past that stop comment, so a later job
in the SAME run would recompute `stand_down=false` and the stand-down would
not actually hold for the rest of the run — the opposite of what
FR-006/FR-008 require. The fix, scoped as narrowly as the original "not
modified" intent allows: `find_stop_request()`'s baseline loop now skips
EVERY bot-authored marker carrying the CURRENT run's own id — none of them
advance the baseline, however many exist or in what order; only a marker
from a genuinely different run id still does, exactly as before. This is
also the semantically correct general rule, not just a workaround for the
record's own marker: within one continuous run, a stop posted partway
through must stay honoured for the rest of that run regardless of what
other same-run progress markers accumulate after it. The cross-run case is
unaffected — FR-009/FR-016's scenario is a PAST run's own stop-point record
(a DIFFERENT, non-current run id) correctly preventing its old stop comment
from re-triggering the NEXT run, which still works exactly as designed.
`StopDecision`'s shape and `main()`'s stdin/stdout contract are still
untouched; Gate 87's existing fixture corpus has at most one marker per run
id per fixture, so it is unaffected by this change and still mutation-
proves `find_stop_request()` end-to-end.

**Rationale**: `find_stop_request()` already computes everything the
*decision* needs. What is new is: (a) identifying *which* comment among the
same input is the one that made `stand_down` true, so the record can name
it (FR-004), and (b) distinguishing *why* a job is standing down — a stop
request, the kill switch, or a closed issue — which today collapses into
one `paused` boolean (`action.yml:66-69`, frozen by
`specs/085-stop-request-cancel-contract/contracts/composite-invocation.md`
as "Unchanged surface (FR-008)").

**Alternatives considered**: Extending `StopDecision` with a third field
(the winning comment) was rejected — it would change the return shape of a
mutation-tested, contractually-frozen function for no benefit, and every
existing caller of `find_stop_request()` (there is exactly one, the
composite) would have to be touched to ignore the new field anyway.
Refactoring `find_stop_request()`'s internal baseline loop into a shared
private helper both it and the new function call was also considered and
rejected in favor of a small, independent duplicate (~10 lines): the
duplicate is separately testable, carries no risk of silently changing
`find_stop_request()`'s own behaviour under refactor, and Gate 87's
existing fixture suite keeps proving `find_stop_request()` unchanged
end-to-end. A new gate (D7) instead proves the two functions agree on every
fixture, which is the actual invariant that matters.

## D2 — The new pure function: identifying the winning stop comment

**Decision**: Add `find_stop_command_comment(comments, current_run_id,
bot_login)` to `board_stop_check.py`, next to `find_stop_request()`. It
recomputes the same baseline `find_stop_request()` computes (the newest
is_loop_marker_author() comment's last_run_match(), with the same
current-run-id handling D1's addendum describes) and returns the **last**
comment at or after that baseline satisfying `author_association in
MAINTAINER_ASSOCIATIONS and is_stop_command(body)` — i.e. the same comment
whose existence makes `find_stop_request(...).stand_down` true — or `None`.
Also add `stop_command_reason(body)`, reusing the existing private
`_command_line()` and public `STOP_COMMAND_RE`: the text on the matched
line after `STOP_COMMAND_RE`'s match end, stripped (empty when there is
none — a bare `stop.` carries no reason). `current_run_id` was added to
this function's own signature after D1's addendum (it originally took only
`(comments, bot_login)`): the composite's own `--stop-comment` call already
has `$GITHUB_RUN_ID` in scope, the same way the `check` step's call does.

**Rationale**: FR-004 needs the specific comment (to link/identify it) and
FR-005 needs its reason text (to fence it as inert data). Both read the
same "which comment won" fact `find_stop_request()` already decides
internally but never surfaces. A pure function over the same input the
composite already fetches (`board-stop-check-comments.json`) keeps this
inside `board_stop_check.py` — the one home CLAUDE.md and FR-018 both name
— rather than re-deriving any part of the match/authorization rule in the
composite's `run:` shell or in board-loop.yml.

**Invariant this creates**: for every input, `find_stop_request(comments,
run_id, bot_login).stand_down == (find_stop_command_comment(comments,
run_id, bot_login) is not None)`. The new gate (D7) checks this holds over
Gate 87's own fixture corpus, so the two functions can never quietly
diverge.

## D3 — Composite contract: a new `stop-cause` output, unchanged `paused`

**Decision**: `wing-commander-board-stop-check` gains one new output,
`stop-cause`, with exactly four values: `""` (not standing down),
`"closed-issue"`, `"kill-switch"`, `"stop-request"`. Priority order (a
single `if/elif` chain, evaluated once per invocation):

1. `check-issue-closed == "true"` and the issue reads closed →
   `"closed-issue"` — regardless of whatever `find_stop_request()` would
   otherwise say. (Spec 097 edge cases: *"the loop does not comment on an
   issue a human deliberately closed"* — unconditional, not merely
   "solely.")
2. else `find_stop_request(...).stand_down == true` → `"stop-request"`
   (this also covers FR-012's kill-switch-and-stop-request case, since this
   branch is checked before the kill-switch branch).
3. else `initial-paused == "true"` → `"kill-switch"`.
4. else `""`.

`paused` keeps its exact existing meaning and computation (`true` iff
`stop-cause != ""`) — the frozen surface
`specs/085-.../contracts/composite-invocation.md` describes stays true to
the letter; every one of the ~30 existing `steps.killswitch-recheck.outputs.
paused` reads across `board-loop.yml` keeps working unchanged.

**Rationale**: FR-014 needs each caller to "name the cause they actually
observed," and FR-011/FR-012/FR-013 need different write behaviour per
cause. A single new enum-shaped output, computed once, gives every caller
one fact to branch its message text and its `if:` gate on, instead of each
of six call sites re-deriving "is this a stop, a kill switch, or a closed
issue" from raw inputs (which would be exactly the per-job duplication
CLAUDE.md's single-home rule and FR-018 forbid).

**Constitution note (Principle VII)**: this composite lives under
`.github/actions/` (not an underscore-prefixed `_shared` directory), so it
is part of the published, adopter-pinned contract. Adding `stop-cause` and
two new optional inputs (D4) **widens** that surface. Per Principle VII
("widening the surface is a deliberate act rather than a convenience, never
a breaking one") this is recorded here as that deliberate act: both new
inputs default to `""`, the new output is additive, and no existing input
or output name, default, or meaning changes. `specs/085-.../contracts/
composite-invocation.md` itself remains untouched by this plan (this task
may only edit `specs/097-recorded-stop-point/`); a follow-up during
implementation should extend that contract doc (it is a live, gate-read
contract per CLAUDE.md, not a historical artifact) to describe the new
surface, or record a superseding note in this feature's own contracts.

## D4 — New inputs: caller-supplied branch/base-sha context

**Decision**: Add two new optional composite inputs, `marker-branch`
(default `""`) and `marker-base-sha` (default `""`). Every one of the six
callers passes `needs.select.outputs.branch` / `needs.select.outputs.
base-sha` — the exact values the `select` job's own resume step already
resolved for this item this run (`board-loop.yml:148-149`), already reused
verbatim by the fix job today (`EXISTING_BRANCH`/`EXISTING_BASE_SHA`,
`board-loop.yml:2060-2061`). Triage and route naturally pass empty strings
(no branch exists yet pre-fix), matching the "no branch or PR" edge case
without any special-casing.

**Rationale**: FR-010 requires the record to "preserve the item's branch
and base commit, and only those — the same in-flight context the fix job's
existing stalled path already keeps" (`board-loop.yml:2267`:
`--branch "$FIX_BRANCH" --base-sha "$BASE_SHA"`, no `--pr`). Every caller
already has this exact pair of values on hand via `needs.select.outputs.*`
with zero new computation — `select`'s resume step is the one place that
already re-derives them from live state per item, regardless of which
downstream job runs.

**Alternative considered and rejected**: having the composite re-derive
branch/base-sha itself (a fresh `gh` lookup inside the composite). Rejected
because `select`'s resume step is already the single home for that
derivation (`contracts/board-item-marker.md` "Read (resume)"); duplicating
it inside the stop-check composite would be exactly the kind of second,
parallel implementation CLAUDE.md warns against, for a value every caller
already has for free.

## D5 — Recording itself: label first, then marker+comment, reusing `add_stalled_label()`

**Decision**: Inside the composite, when `stop-cause == "stop-request"`:

1. Fresh-read the issue's current labels (`gh issue view $ISSUE_NUMBER
   --json labels`). If `board:stalled` is already present, skip straight to
   step 4 (idempotency — see D6). This is one small additive read; the
   existing comments fetch does not carry labels.
2. Run `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py"
   --step stalled --issue "$ISSUE_NUMBER" --add-label "board:stalled"
   [--branch "$MARKER_BRANCH"] [--base-sha "$MARKER_BASE_SHA"]` — the exact
   CLI every other stall site already uses, run from the trusted snapshot
   (D8). A non-zero exit (the label add failed) fails this step loudly;
   nothing else in this branch runs, and no label was left on with no
   marker (`add_stalled_label()`'s own established contract,
   `board_item_marker.py:170-195`).
3. Post the human-legible comment (contract: D9) with `gh issue comment`,
   embedding the marker text step 2 produced. This call's own exit code is
   checked explicitly (`|| { echo "::error::..."; exit 1; }`) — stricter
   than several existing stall sites' bare `gh issue comment` calls, since
   this is new code with no legacy call site to match, and FR-017 requires
   the failure to be loud rather than merely logged.
4. Set the composite's own `paused` output (already `true` from `stop-
   cause == "stop-request"`, unaffected by whether step 1 short-circuited).

**Rationale**: FR-018 requires "the label-then-marker write MUST go through
the existing stall helper, `add_stalled_label()` ... not a new
implementation" — reused verbatim, not reimplemented. FR-017 requires a
failure here to be loud and to leave the item either fully recorded or
retryable; label-add failure is already retryable by
`add_stalled_label()`'s own contract (nothing is added when it fails), and
this design does not weaken that.

**Accepted residual risk (documented, not new)**: if the label add
succeeds but the *comment post* then fails, the item is excluded from
selection (`board:stalled` is on) with no explanatory comment yet — the
same residual risk every one of the eight existing `add_stalled_label()`
call sites already carries (see `board_item_marker.py:176-189`'s own
docstring). This plan does not introduce a new failure mode; it keeps the
established one and, per step 3, at least always fails the job loudly on
that specific failure (several existing call sites do not even do that).
Closing that residual gap repo-wide is out of scope for this feature.

## D6 — At-most-one-record-per-run (FR-007): idempotency, not job coordination

**Decision**: FR-007's "at most one stop-point record... even when several
jobs in that run each reach their own stop check" is satisfied by the
fresh-label-read short-circuit in D5 step 1, not by any new
cross-job signalling. Under the current job graph exactly one of
triage/route/fix/review/readiness actually executes for the selected item
per scheduled run (each gated on `needs.select.outputs.step`), and each
such job calls the composite exactly once — so today this scenario is not
concretely reachable, but the idempotency check costs one extra `gh issue
view` only on the already-rare stop-request path and makes the invariant
hold regardless of future job-graph changes (e.g. a future directed-dispatch
mode that chains stages within one run) rather than relying on today's
topology to keep it true by accident.

**FR-008 interaction**: the short-circuit only ever skips the *write*.
`stop-cause` and `paused` are computed independently, every time, from live
comments — so a stop check reached later in the same run (or on the very
same call, since D3's ordering runs regardless of D5) still reports
`paused = true` / `stop-cause = "stop-request"` even after the record was
already written; nothing about having written the record is read back as
"the stop is satisfied."

## D7 — New PR-time gate (FR-019): Gate 128

**Decision**: The next unused gate number in this repository is 128 (127
is the current maximum, `specs/091-gh-api-error-capture`; gate numbers are
a naming convention checked by `verify-gate-wiring.py`/`run-local-gates.py`,
not a stored list — `.github/scripts/wc_gate_registry.py`). New gate:
`.github/scripts/verify-stop-point-recording.py`, wired into
`.github/workflows/lint-workflows.yml` as "Gate 128" with its own
`--self-test`, following the same two-step pattern as every other gate
(e.g. Gate 97/`verify-board-loop-resume-gating.py`, Gate 47/`verify-
comment-canonical-pointers.py`).

**What it checks** (fails on the pre-fix shape, passes on the fixed one —
Principle VIII, SC-009):

1. **Structural** (parses `action.yml`, `board_stop_check.py`, and
   `board-loop.yml`'s six call sites as text/YAML, no execution): the
   composite's `stop-cause`-gated record-write block exists and reuses
   `board_item_marker.py --step stalled ... --add-label "board:stalled"`
   from `$RUNNER_TEMP/wc-pristine/scripts/` (not a bare `.github/scripts/`
   path — this also covers spec 095 FR-011/FR-012's provenance rule for
   this one file, once spec 095 lands); each of the six stand-down message
   strings in `board-loop.yml` reads `stop-cause` (or the composite's
   output) rather than hardcoding "kill switch" prose unconditionally.
2. **Function-level** (imports `board_stop_check` directly, no Actions
   runtime): `find_stop_command_comment()` agrees with `find_stop_request()`
   on `stand_down` over every fixture in Gate 87's existing corpus (D2's
   invariant) plus a small new fixture set covering FR-016's empty-baseline
   case and FR-009's post-release case.
3. **Eligibility-level** (imports `board_eligibility` directly): a fixture
   issue carrying a `stalled` marker plus `board:stalled` — exactly what
   D5 writes — is excluded by `is_excluded()` and never returned by
   `in_flight_candidate()`/`select()`, proving SC-001's "selected by zero of
   the next ten runs" property from the actual selection code rather than
   by inspection.
4. **Self-test**: each check's mutation (record-write block deleted;
   hardcoded kill-switch message restored; a fixture where the two stop
   functions are made to disagree; a fixture marker without `board:stalled`
   fed to `is_excluded()`) makes the corresponding check fail, proving the
   gate can fail its own subject (Principle VIII, SC-009).

**Rationale**: this mirrors Gate 97's own shape (structural checks over the
same resume machinery, self-test-driven) since FR-019 is functionally the
same kind of requirement Gate 97 already satisfies for a neighboring part
of this same job graph — reuse the established gate pattern rather than
inventing a new one.

## D8 — Provenance: composite `run:` steps import from the trusted snapshot

**Decision**: Both the existing `board_stop_check.py` invocation
(`action.yml:113`, currently `python3 .github/scripts/board_stop_check.py`)
and the new `add_stalled_label()`/marker-write invocation (D5) run as
`python3 -I "$RUNNER_TEMP/wc-pristine/scripts/<name>.py"` — the same idiom
`board-loop.yml` callers already use for `board_item_marker.py` at the
fix/review/readiness stall sites (`board-loop.yml:2267`, `2471`, `3310`,
`3315`, `3323`, `3917`).

**Rationale**: FR-018's last sentence requires exactly this: "The composite
MUST run that helper, and `board_stop_check.py`, from the trusted snapshot
rather than the workspace (spec 095 FR-011/FR-012)." Spec 097's own status
update independently confirms `action.yml:113` is today's gap. Spec 095
(provenance rule) is itself still in review on a draft branch
(`spec-draft/095-agent-code-credential-containment`, not merged to `main`
in this checkout) and **no existing composite** anywhere in the repo yet
imports a `.github/scripts/*.py` file from `$RUNNER_TEMP/wc-pristine`
inside its own `run:` step — every existing use of that path is in a
*caller workflow's* own step, never inside a composite's `action.yml`. This
feature is therefore first to establish that this idiom works the same way
inside a composite (the composite always runs with `cwd == $GITHUB_
WORKSPACE` regardless of which directory its own `action.yml` was loaded
from, so `$RUNNER_TEMP` — an ambient runner variable, not something the
caller's checkout populates specially for the caller's own steps — resolves
identically). This is implemented regardless of spec 095's own merge
timing, since FR-018 requires it unconditionally, not contingent on spec
095 landing first; if spec 095 lands first, this becomes an ordinary
instance of its rule rather than the first one.

## D9 — Stop-point record content (FR-004, FR-005)

**Decision**: The comment posted in D5 step 3 has this shape:

```text
This item stopped because a maintainer posted a stop request.

Stop comment: <html_url> (from @<login>, <created_at>)

<fenced_section("Reason given:", reason, 2000)>   [omitted when reason == ""]

To resume this item, remove the `board:stalled` label.

<marker>
```

`<html_url>` is the specific comment `find_stop_command_comment()`
identified — added to the composite's existing `gh api .../comments`
`--jq` projection (`action.yml:108`) as one more object field, purely
additive to a JSON shape `specs/085-.../contracts/composite-invocation.md`
calls "Unchanged," which is safe since nothing downstream reads the object
positionally. `@<login>` intentionally has **no leading `@`** in the
rendered text (a literal `@handle` would ping that maintainer every time
the loop stands down on their behalf — an unwanted notification, not the
point of the record) — GitHub does not autolink a bare login. The reason,
when present, goes through `fenced_section()`
(`.github/scripts/board_spec_request_body.py:159`, imported the same way
the fix job's own gate-failure rendering already does,
`board-loop.yml:2272`) — "the loop's existing fencing rule for quoted
content" FR-005 itself names, so the reason renders as inert text inside a
code fence: no `@mention`, `#N` reference, link, or HTML from it is ever
live markdown.

**Rationale**: FR-004 requires naming the cause, identifying the specific
comment, and stating the release condition — all three appear as plain
prose plus a real GitHub permalink (not user-authored content, so no
fencing risk). FR-005 requires the *maintainer's own reason text*
specifically be inert; reusing the one existing fencing helper is the
CLAUDE.md-required single home rather than a second, hand-rolled quoting
routine.

## D10 — FR-009/FR-016 need no new logic

**Observation, not a decision**: `write_marker()` always emits a `**Run:**
<url>` line for the current run (`board_item_marker.py:158-164`, ambient
`GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`). Because D5's
comment is produced via the same `write_marker()` call, the run that
honours a stop **always** advances `find_stop_request()`'s own baseline to
this run's timestamp — with no code change to the baseline computation
itself. This means:

- **FR-016** ("honoured exactly once"): an empty-baseline ancient stop
  comment is honoured on the first run that reaches the stop check (baseline
  `""` matches everything); that same run's own stop-point comment becomes
  the new newest bot-authored `**Run:**` comment, so on any later run the
  ancient comment now predates the baseline and no longer counts. No
  post-release re-trigger is possible from that same old comment.
- **FR-009** (post-release, "the stop request that was already recorded
  MUST NOT stand the item down again"): once a maintainer removes
  `board:stalled`, the item becomes selectable again; on the run that
  selects it, `find_stop_request()`'s baseline is (at least) the recorded
  stop-point comment's own timestamp, so the original stop comment is
  already before that baseline and is never re-evaluated. A genuinely new
  stop comment posted after release is, by construction, after that
  baseline and is honoured normally.

Both properties fall out of D5 + the existing, unmodified
`find_stop_request()` — confirming D1's choice not to touch that function
was sufficient, not merely safe.

## D11 — Metrics/cost-line classification (FR-015, SC-008)

**Decision**: Each of the six resume-stage jobs (triage, route, fix,
review, readiness, prove) gains one additional, unconditional
(`if: always()`) "Record run outcome (<job>)" step at the end of the job,
modeled directly on the `select` job's own existing accounting-only
`wing-commander-metrics-summary` invocation (`board-loop.yml:901-911`:
`transcript-path` pointing at the ambient `wing-commander-no-transcript.
json` placeholder, `model: ''`, no agent cost) — the same "no-op run still
gets a cost line and a metrics record" idiom FR-046/FR-047 already
established for the `select` job's own kill-switch stand-down (`board-
loop.yml:127-129`). Its `run-label` input distinguishes, in order of
priority: `"<job>: stopped (stop-request)"` when `stop-cause ==
"stop-request"`; `"<job>: stood down (kill-switch)"` when `stop-cause ==
"kill-switch"`; `"<job>: stood down (issue closed)"` when `stop-cause ==
"closed-issue"` (`prove` only); otherwise the job's own existing outcome
label (e.g. `outcome` for triage, `ready`/`not ready` for readiness).

**Rationale**: `run_label` is already a literal top-level field in the
emitted metrics record JSON (`wing-commander-metrics-summary`'s
`emit_record()`), uploaded as an artifact per job
(`actions/upload-artifact`, `retention-days: 90`) — SC-008's "count...from
the records alone" is satisfied by a distinguishable, greppable
`run_label` value with no schema-version bump and no change to the existing
`outcome` enum (`healthy|exhausted|rate-limited|failed|unclassifiable|
unavailable`), which describes an *agent invocation's* own outcome and
should not be overloaded to also mean "the job's durable action stood
down." A run's existing per-agent metrics record (e.g. `triage-propose`'s,
emitted *before* the stop check runs) is left exactly as is — it still
correctly reports how the agent step itself went; the new step is a
second, separate, low-cost record capturing what the *job as a whole* did
with that result.

**Exact per-job label wording and precisely which existing outcome variable
each job substitutes in the "otherwise" branch is left to tasks.md/
implementation** — the requirement fixed here is the mechanism (one
`always()` accounting step per resume job, reusing `wing-commander-metrics-
summary`'s established no-agent-cost shape) and the three stand-down label
categories, not the literal strings.

## D12 — Stand-down message text (FR-014)

**Decision**: Every one of the six existing "standing down" messages in
`board-loop.yml` (e.g. `board-loop.yml:1412`: *"kill switch set immediately
before triage's durable action -- standing down without acting."*) is
rewritten to read `steps.killswitch-recheck.outputs.stop-cause` and name
the actual cause, e.g.: *"a maintainer stop request"* / *"the kill switch"*
/ *"the issue being closed"*. `readiness`'s message
(`board-loop.yml:3720`) already says "kill switch or stop request found" —
generalized the same way for consistency, and prove's generic "stood down"
label (`board-loop.yml:4524`) gains the same cause name.

## Summary of touched files

- `.github/scripts/board_stop_check.py` — additive: two new functions,
  `find_stop_command_comment()` and `stop_command_reason()`; nothing
  existing changed.
- `.github/actions/wing-commander-board-stop-check/action.yml` — new
  inputs (`marker-branch`, `marker-base-sha`), new output (`stop-cause`),
  new record-writing steps, provenance fix for the existing `board_stop_
  check.py` invocation (D8), `html_url` added to the comments `--jq`
  projection (D9).
- `.github/workflows/board-loop.yml` — six call sites gain the two new
  inputs and read `stop-cause`; six stand-down messages reworded (D12); six
  new `always()` "Record run outcome" steps (D11).
- `.github/scripts/verify-stop-point-recording.py` (new) + its `lint-
  workflows.yml` wiring as Gate 128 (D7).
- `.github/scripts/tests/` — new fixtures for Gate 128's function-level and
  eligibility-level checks (D7), reusing Gate 87's existing corpus where
  possible.
