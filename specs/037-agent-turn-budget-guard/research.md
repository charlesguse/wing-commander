# Phase 0 Research: A Successful Agent Step Is No Longer Failed by the Wrong Turn Counter

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers — the three
genuine ambiguities (scope relative to #193, over-budget handling,
upstream-report deliverable) were already resolved during the clarify
stage and are cited inline in the spec's Clarifications section. What
follows are the implementation-shape decisions this plan makes to turn
the spec's functional requirements into something `tasks.md` can build
against, grounded in a fresh read of every one of the 19 call sites (not
the issue's line numbers, which have already drifted) and the existing
gate/composite conventions this repository has built up since Gate 5.
Decisions explicitly not dictated by the spec text are marked "(made
without clarification)" and are repeated in the transmittal comment on
issue #206, per this pipeline's own convention (precedent:
`specs/027-auto-update-spec-kit/research.md`).

## R1: Ceiling multiplier — 2.5x, computed by a dedicated composite, not per-site literals

**Decision**: `wing-commander-turn-ceiling` takes `intended-turns`
(required) and `multiplier` (optional, default `2.5`) and emits `ceiling
= ceil(intended-turns * multiplier)`. Every one of the 19 sites computes
its `--max-turns` CLI value from this composite's output, never from a
literal.

**Rationale**: The spec's own Assumptions name 2.5x as the default
sizing "subject to the plan stage confirming it against the full
sample." The observed divergence in this repository's history is
1.0x-2.3x, always upward (Gate 11's docstring, `wing-commander-metrics-summary`'s
description). 2.5x leaves a 0.2x margin above the worst observed case
without inflating a genuinely runaway agent's maximum spend by more than
that same margin (SC-008) — smaller than option (1) in the issue's own
proposal (a flat 2.5x-everywhere edit with no shared source of truth,
which is exactly what already drifted once: `auto-update-spec-kit.yml`'s
one absorbed site used a *different*, hand-picked 2x before this
feature). Centralizing the multiplier in one composite's default means
changing it later (if a wider sample justifies a different number) is a
one-line change instead of a 19-site grep-and-edit — and Gate 23
(coverage-gate.md) can mechanically prove every site actually goes
through it, closing exactly the gap that let one site's fix
(`auto-update-spec-kit.yml:916`, 15→30) not generalize to `clarify.yml`
31 hours later.

**Alternatives considered**: A literal `--max-turns $(( intended * 25 /
10 ))` inline at each of the 19 sites — rejected: 19 copies of the same
arithmetic is the same shape of duplication that caused this issue
(one site fixed, eighteen not), and it gives Gate 23 nothing to check
structurally (a literal number looks identical whether it came from the
multiplier or was hand-edited back down, which is precisely User Story
3 Acceptance Scenario 3's "lowers a ceiling back to its intended
budget" case that must be caught). A fixed absolute ceiling (e.g. "add
50 turns") — rejected: it doesn't scale with budget size, so the
smallest budgets the issue calls out as "most exposed in relative
terms" (`auto-update-spec-kit.yml:2676` at 8, `implement.yml:1020` at
15) would still see the largest proportional inflation risk reduction,
while the largest budgets (`implement.yml` at 180) would gain far more
absolute ceiling than the divergence sample justifies.

## R2: Schema-shape validation stays call-site-owned; the shared verdict answers only "did the runtime say success"

**Decision**: The shared `wing-commander-agent-verdict` composite
computes a *generic* verdict from the transcript's terminal result
record alone (`subtype`, `is_error`, presence of a result record at all)
plus turn counts. It does not parse or validate any site's specific JSON
Schema. The 9 sites that already declare `--json-schema`
(`clarify.yml`, `intake.yml`, `pr-conversation.yml` ×2, `watchdog.yml`'s
`diagnose`, `auto-update-spec-kit.yml`'s `decide`/`interpret`) keep
their existing shape-check step, now gated on
`steps.<verdict>.outputs.verdict == 'healthy'` instead of a raw
`outcome == 'success'`, and that step is what actually enforces FR-004
("successful terminal result whose structured output is missing or does
not match the declared shape MUST be treated as a genuine failure") by
failing the job itself when the shape check fails.

**Rationale**: FR-013 asks for the verdict logic to be "defined once and
reused" — but the nine schemas are all *different* (clarify wants
`{answered, clarticulations}`, watchdog's is built dynamically from a
label registry at run time). A shared composite cannot know nine
different shapes without either (a) taking the literal schema as an
input and running a general JSON-Schema validator, which introduces a
new dependency (no `jsonschema`/`ajv` exists anywhere in this repository
today) for a check nine sites already do correctly in ~10 lines of `jq`
each, or (b) becoming a second thing this composite has to be right
about, widening its blast radius for no shared-logic benefit (each
site's shape check runs exactly once, so there is nothing to
de-duplicate). "Verdict logic" in FR-013's sense is the part that
*was* duplicated and drifting — the is_error/subtype read and the turn
count — not the shape check, which was already correctly scoped
per-site and never duplicated in the first place.

**Alternatives considered**: A generic JSON-Schema validator fed the
site's schema as an input — rejected for the dependency reason above,
and because it would not remove any existing code (each site would still
need to declare and pass its schema, so the composite would gain
complexity without shrinking any call site). Folding the shape check
into the verdict's own `reason` string as a second free-text field —
rejected: it conflates two different kinds of evidence (runtime-level
success vs. application-level output correctness) into one output,
making FR-012's "state the verdict, the evidence, and both turn totals"
harder to render distinctly.

## R3: Verdict categories — `healthy` / `exhausted` / `failed` / `unclassifiable`, mapped from spec edge cases

**Decision**: `wing-commander-agent-verdict` emits exactly one of four
`verdict` values:

| Transcript state | `verdict` | Spec basis |
|---|---|---|
| File missing, empty, or fails `jq -e .` | `unclassifiable` | Edge case 1: "cannot be established... fail closed" |
| Valid JSON, but no `.type=="result"` record anywhere | `failed` | Edge case 2: "no terminal result at all... genuine failure" |
| Result record present, `subtype=="error_max_turns"` | `exhausted` | Edge case 3: "reached the ceiling... a real outcome... surfaced as exhaustion" |
| Result record present, `is_error==true` (any subtype) | `failed` | Edge case 2: "`subtype: success` but `is_error: true`... genuine failure" |
| Result record present, `subtype` is neither `success` nor `error_max_turns` | `failed` | FR-001's own success indicators — anything else is not the documented healthy shape |
| Result record present, `subtype=="success"`, `is_error==false` | `healthy` | FR-001/FR-002 |

Only `healthy` means "continue as though the agent succeeded." The
generic "fail loud" step every call site gains checks
`verdict != 'healthy'` — a single condition, so `exhausted` is not
accidentally treated as success by a site that forgets to special-case
it, while still being distinguishable in `reason` for stages (like
`implement.yml`, see R13) that want to branch on exhaustion
specifically in the future.

**Rationale**: This table is a literal transcription of the spec's own
edge cases, chosen over inventing new categories so that FR-015's
required test set (healthy-but-rejected, genuinely errored, exhausted,
schema-violating, unreadable) maps one-to-one onto the composite's own
cases plus the call-site shape check from R2.

## R4: The verdict composite never fails its own step — same never-fail contract as metrics-summary

**Decision**: `wing-commander-agent-verdict`'s step always exits 0 and
degrades to `verdict: unclassifiable` on any internal read failure
(mirroring `wing-commander-metrics-summary`'s own "never fail the step"
contract, FR-009 in that action's original spec). The actual job-failing
action — `exit 1` after printing `::error::` — lives in each call site's
own "Fail loud on non-healthy verdict" step, gated on
`always() && steps.<verdict>.outputs.verdict != 'healthy'`.

**Rationale**: A composite that sometimes fails its own step and
sometimes doesn't would need `continue-on-error: true` at some sites and
not others depending on which verdict is expected — indistinguishable
from today's inconsistent per-site handling this feature is removing.
Keeping the composite itself unconditionally green and pushing the
single `if: ... != 'healthy'` decision into one small, identical step at
every site makes the actual failure point uniform and easy to audit from
the workflow YAML alone (FR-012/SC-007 — "a maintainer can determine...
from a single run's summary alone").

## R5: Turn-counting logic extracted to a shared script, called by both composites via `$GITHUB_ACTION_PATH`

**Decision**: The `jq` turn-counting block currently inlined in
`wing-commander-metrics-summary/action.yml` moves to
`.github/actions/_shared/count-turns.sh` (a plain script, not a
composite — nothing needs its own `action.yml`). Both
`wing-commander-metrics-summary` and the new `wing-commander-agent-verdict`
invoke it as `"$GITHUB_ACTION_PATH/../_shared/count-turns.sh"
"$TRANSCRIPT"` — `GITHUB_ACTION_PATH` is populated for every composite
`run:` step and points at that composite's own checked-out directory,
which sits alongside `_shared/` inside the same
`.wing-commander-pipeline/.github/actions/` self-checkout every stage
already performs (constitution VII), so this resolves correctly for any
adopter regardless of where their own repository's `.github/actions/`
lives. `verify-metrics-turn-accounting.py` (Gate 11) is updated to
extract and test `count-turns.sh` directly instead of the inline block
it tests today — same discipline, different extraction target.

**Rationale**: Without sharing, the verdict composite needs its own copy
of the exact counting rule (distinct `.message.id`, `parent_tool_use_id
== null` excluded) that Gate 11 exists specifically to keep correct —
introducing a *second* uninspected copy for Gate 11 to miss is the same
"one site fixed, the rest exposed" shape as this entire issue. Every
existing case of shared logic in this repository (Gate 5's collector
filter, Gate 11 itself) instead keeps one canonical copy and asserts a
second copy (a test fixture) matches it — but that pattern exists
*because* GitHub Actions composites could not previously call each other's
scripts; `GITHUB_ACTION_PATH` makes an actual shared script possible for
the first time in this codebase, and doing so removes a whole class of
gate (a second Gate-5-style diff check) that would otherwise be needed
to keep two copies honest.

**Alternatives considered**: Duplicate the block into the new composite
and add a Gate-5-style diff assertion between the two copies — rejected:
strictly more surface area (two copies plus a syncing gate) for no
behavioral difference from a single shared script, and this repository's
own commentary (Gate 5's header) already treats "two copies that can
drift" as the failure class to avoid, not a pattern to repeat when
avoidable.

## R6: `wing-commander-metrics-summary` gains two optional, display-only inputs

**Decision**: Add `verdict` and `verdict-reason` as optional string
inputs (default `""`). When both are non-empty, the rendered block gains
one line stating the verdict and reason, positioned directly under the
existing Model/Turns/Duration/Tokens/Cost table (FR-012). When empty (any
caller that hasn't been updated, or a future adopter who doesn't wire
the verdict composite), rendering is byte-for-byte identical to today.
No new decision logic is added to this action — it remains "never fails,
reads only what it's handed."

**Rationale**: FR-012 requires the run's own summary to state the
verdict and both turn totals in one place a maintainer reads without
opening the transcript (SC-007). `wing-commander-metrics-summary` is
already that place for turn totals at 14 of the 19 sites; extending it
avoids a second, competing summary block that would force a reader to
correlate two tables instead of reading one. Making the new inputs
optional and additive keeps the action's existing contract
non-breaking — the same reasoning constitution VII already applies to
this repository's *published* interfaces is applied here by analogy to
an internal one, because a silent behavior change to an action every
published stage already calls would be its own regression.

## R7: Uniform per-site rewire pattern — three added/changed steps, same shape at all 19 sites

**Decision**: Every call site gets the same four-step shape immediately
around its existing agent step:

1. Agent step gains `continue-on-error: true` if it doesn't already have
   it (8 of 19 sites are missing it — see R14), and its `--max-turns`
   argument changes from `${{ inputs.max-turns }}` (or a literal) to
   `${{ steps.<ceiling-id>.outputs.ceiling }}`.
2. NEW: a `wing-commander-turn-ceiling` step immediately before the
   agent step, `id: <name>-ceiling`, `intended-turns: ${{ inputs.max-turns }}`
   (or the literal budget for sites with no published input, e.g.
   `implement.yml`'s `progress` at a fixed 15).
3. NEW: a `wing-commander-agent-verdict` step immediately after the
   agent step, `if: always()`, `id: <name>-verdict`,
   `transcript-path`/`run-label` matching whatever
   `wing-commander-metrics-summary` already uses at that site (or, for
   the 5 sites with no metrics-summary invocation today — `pr-conversation.yml`
   ×2, `auto-update-spec-kit.yml` ×3 — the same default path
   `wing-commander-metrics-summary` itself defaults to).
4. Existing downstream gate(s) — the "Fail on agent API error"/shape
   check step, the "Verify..."/"Read back..." step, any metrics-summary
   invocation — change their `if:` from referencing
   `steps.<agent>.outcome` to referencing
   `steps.<verdict-id>.outputs.verdict == 'healthy'`, and the
   metrics-summary invocation (added where missing) gains the `verdict`/
   `verdict-reason` passthrough from R6.
5. NEW (uniform glue, ~5 lines, not centralized — see R4): a "Fail loud
   on non-healthy verdict" step, `if: always() && steps.<verdict-id>.outputs.verdict != 'healthy'`,
   printing `::error::` with the reason and exiting 1.
6. NEW, only at sites whose job already posts to the lifecycle issue
   (14 of 19 — see the call-site table below): a "Report over-budget"
   step, `if: steps.<verdict-id>.outputs.verdict == 'healthy' && steps.<verdict-id>.outputs.over-budget == 'true'`,
   calling `wing-commander-callout` with `kind: info` (FR-017).

**Rationale**: A uniform, mechanically-checkable shape is what makes
Gate 23's coverage enumeration (contracts/coverage-gate.md) possible at
all — a bespoke rewire per site would leave the same "correctly fixed
once, silently missed elsewhere" risk this issue already demonstrated.
Reusing each site's *existing* downstream step (rather than replacing
it wholesale) minimizes the diff and preserves every site's own
site-specific business logic (git-state checks, shape checks, PR
creation) exactly as-is — only the gating condition changes.

## R8: Coverage boundary — every `claude-code-action` step that declares `--max-turns`; `claude.yml`/`claude-code-review.yml` explicitly excluded (made without clarification)

**Decision**: Gate 23 enumerates every `uses: anthropics/claude-code-action`
step, across every `.github/workflows/*.yml` file, whose `claude_args`
block contains `--max-turns`. Re-enumerating (per spec.md's Assumptions,
"the plan stage re-enumerates rather than trusting the list") confirms
the issue's 19 sites are still 19 (line numbers have drifted; the set of
sites has not) and surfaces two *additional* `claude-code-action` steps
this feature does **not** bring into scope: `claude.yml:37` and
`claude-code-review.yml:37`, GitHub-App-triggered interactive
mention-response/PR-review bots, neither of which declares `--max-turns`
at all today.

**Rationale**: A site with no turn cap cannot experience this issue's
defect — the upstream throw this whole feature exists to work around
(`resultMessage.num_turns > sdkOptions.maxTurns`) is unreachable when
`maxTurns` is `undefined`. Bringing these two into scope would mean
*also* deciding what intended budget to assign them, which is a
different, pre-existing constitution II gap (every agent step should
declare a bounded cap) with no supporting evidence in this issue and no
mention in spec.md's Assumptions or Out of Scope. FR-010's "every agent
invocation site in the repository" is read here as bounded by what this
feature's own evidence and Key Entities describe — a call site with
"model, intended budget, ceiling, and verdict handling" (spec.md Key
Entities) presupposes an intended budget already exists to split.
Recommendation, not a deliverable of this feature: file a follow-up
issue proposing `claude.yml`/`claude-code-review.yml` gain an explicit
`--max-turns` under constitution II, independent of this feature's
ceiling/verdict machinery.

## R9: Gate 23 also catches a ceiling regressing back to its intended budget

**Decision**: Beyond presence/absence, Gate 23 resolves each site's
`--max-turns` expression and fails when it is anything other than
`steps.<id>.outputs.ceiling` referencing a `wing-commander-turn-ceiling`
step — a literal number, a raw `inputs.max-turns` passthrough, or a
ceiling step whose own `multiplier` input has been set to `1` (or
omitted with a *changed* action default of `1`) all fail the gate by
name.

**Rationale**: This is User Story 3 Acceptance Scenario 3 verbatim
("lowers an agent step's ceiling back to its intended budget... fail
rather than silently reintroducing the exposure") and SC-005. Checking
only "is the composite invoked somewhere in this job" would pass a site
that invokes it but doesn't actually wire its output into `--max-turns`
— the exact kind of gap Gate 7 (environment binding) was written to
close for a structurally similar problem (a binding present in the file
but not actually forwarding the right value).

## R10: New gate numbers — 22 (verdict self-test) and 23 (coverage enumeration + self-test)

**Decision**: The highest existing gate in `lint-workflows.yml` is Gate
21 (confirmed by direct read, not by trusting the issue). This feature
adds Gate 22 (`verify-agent-verdict.py`, same shipped-script-extraction
discipline as Gate 11) and Gate 23 (`verify-gate-23.py`, same
dynamic-enumeration-plus-self-test discipline as Gates 6/7/12). Gate 10
(the gate-wiring registry, `wc_gate_registry.py`) requires every new
`verify-*.py` to be invoked by some workflow step — both are added to
`lint-workflows.yml`'s existing `lint` job in the same PR that adds the
scripts, so Gate 10 never sees an orphaned gate script.

**Rationale**: Matches this repository's own numbering convention (gate
numbers are assigned in landing order, not reused, per the existing
1-21 sequence) and its "test the shipped artifact, not a hand-copied
description of it" discipline, which is exactly what FR-015 requires of
the verdict logic and what a bare "grep the file" coverage check would
not provide for Gate 23's regression case (R9).

## R11: Upstream report lives with this feature's own spec artifacts

**Decision**: `specs/037-agent-turn-budget-guard/upstream-report.md` —
not a new repository-wide `docs/upstream-reports/` directory.

**Rationale**: No precedent for cross-repository issue drafts exists
anywhere in this repository today (confirmed: no such directory, no
prior mention of `anthropics/claude-code-action#1607` outside this
feature's own spec). Inventing a new top-level documentation convention
for a single, possibly one-off artifact is more structure than the
current evidence justifies; if a second upstream report is ever drafted
by a future feature, promoting this into a shared `docs/` location at
that point is a small, well-motivated follow-up rather than a
speculative abstraction today (matches this repository's own "no
half-finished implementations, no hypothetical future requirements"
discipline). The report stays discoverable from the lifecycle issue
comment and from `specs/037-agent-turn-budget-guard/` itself, which is
sufficient for FR-018/SC-010's "present in the repository... whether or
not it is ever filed."

## R12: `docs/architecture.md` — extend the existing paragraph, no new gate catalog

**Decision**: Extend the existing turn-counter-divergence discussion at
`docs/architecture.md` lines ~172-197 (which already explains "`--max-turns`
caps main-loop model turns... `.num_turns`... 1.0x-2.3x... Gate 11") with
2-3 sentences describing the intended-budget/runaway-ceiling split, the
two new composites, and Gates 22/23 by name.

**Rationale**: `docs/architecture.md` has no consolidated gate
catalog/table anywhere — every existing gate is documented inline, next
to the subsystem it checks (confirmed by direct read: Gate 3 near
review-mode, Gate 5 near the watchdog collector, Gate 6 near wrapper
dispatch, Gate 11 already sits in exactly the paragraph this decision
extends). Introducing a table format for just this feature's two gates
would be a new, inconsistent documentation shape landing beside 21
gates documented the old way.

## R13: `implement.yml`'s convergence/stall loop is unchanged

**Decision**: This feature adds `budget-exhausted`/`over-budget` as new,
optional signals any stage may consume — it does not modify
`implement.yml`'s existing "Read back cycle/retry outcome" steps, which
already detect stalled progress from **git state** (whether a
`converge:` commit touching `tasks.md` is present on the pushed branch),
independent of turn counting.

**Rationale**: Direct inspection of `implement.yml`'s outcome-reading
steps found no `is_error`/`subtype`/`error_max_turns` check anywhere —
the "exhaustion signal `implement` already relies on" the issue
references is this git-state stall detection, which works empirically
regardless of *why* a cycle produced no progress (turn exhaustion is one
cause among several: a hard error, a converge loop that made no forward
motion, etc.). Rewiring that detection to key off the new `exhausted`
verdict specifically would narrow its coverage for no benefit this
feature's evidence asks for, and spec.md's own Assumptions state "the
`implement` stage's dependence on a budget-exhaustion signal is
preserved in whatever form the exhaustion outcome takes" — preserved,
not necessarily replaced. `implement.yml`'s three sites still gain the
verdict/ceiling wiring like every other site (a genuinely errored or
unclassifiable cycle now fails loud with a clear reason instead of
falling through to the stall-detection path with no explanation), but
its retry/stall *decision* logic itself is out of this feature's scope.

## R14: Uniform treatment regardless of today's `continue-on-error` count (made without clarification)

**Decision**: All 19 sites get `continue-on-error: true` on the agent
step as part of the standard rewire (R7 step 1) if they don't already
have it, with no distinction made based on the issue's estimate that
"six" sites lacked it. Direct enumeration found 8: `clarify.yml`,
`intake.yml`, `plan.yml` ×2, `pr-conversation.yml` ×2, `tasks.yml` ×2.

**Rationale**: FR-016 subsumes #193 "on every agent invocation site,"
which this plan reads as an outcome requirement (every site ends up
protected), not a literal count to reconcile against the issue's
estimate — the issue's number was written before this plan's own
re-enumeration and the spec's Assumptions already anticipate drift
("the plan stage re-enumerates rather than trusting the list"). Treating
all 19 uniformly is also simpler to implement and to verify via Gate 23
than special-casing 11 sites that already had `continue-on-error` versus
8 that didn't.
