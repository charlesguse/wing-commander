# Phase 0 Research: Deterministic Watchdog Collectors for the Supervision Gap

spec.md carries no `[NEEDS CLARIFICATION]` markers. What remains for this
phase is the mechanical design: how four new signal-emitting steps fit
inside `watchdog.yml`'s existing `collect` job without touching anything
FR-030–FR-033 protects, and — the harder problem — how a trend that must
"accumulate at one severity band, then only refile on escalation"
(FR-012/FR-015) and a claim-mismatch class that must never open an issue
(FR-025) can both be built as pure additions rather than special cases
threaded through the shared diagnose/evidence-gate/fingerprint/dedup
path. Each item below is a plan-level decision; several fill a gap
spec.md deliberately left open (its Assumptions section says the default
thresholds "are starting values a maintainer is expected to tune, not
derived constants" — it does not commit to file layout, signal shapes, or
the mechanism behind the accumulate/escalate behavior).

## R1: Every new collector is one more `collect-*` step, not a new job

**Decision**: `collect-turn-budget`, `collect-cost-report`,
`collect-final-pr-claims`, `collect-spec-collision` are added as four more
steps inside `watchdog.yml`'s existing `collect` job, in the same
bash+jq, `id: collect-<name>`, `continue-on-error: true` shape the five
existing collectors already use, each writing into the same
`signals.json`/`collector-outcomes.json` pair.

**Rationale**: FR-001 forbids a new agent invocation, and FR-003 forbids
modifying the downstream path to special-case new signals — the only way
to satisfy both is for the new collectors to be indistinguishable, from
`diagnose` onward, from the five that already exist. A new job would also
need its own `needs:` wiring into `diagnose`, multiplying the surface
FR-032 protects for no benefit.

**Alternatives considered**: A second job (`collect-supervision`) running
in parallel with `collect`, merging its output before `diagnose` — rejected:
it would need its own signals-aggregation step duplicating `Aggregate
signals`' `evidence-available`/`collectors-failed`/`untrusted-collectors`
logic, which is exactly the kind of pasted-and-drifting logic
CLAUDE.md's "shared logic has exactly one home" section warns against,
for a job split that buys nothing (both jobs would still need to finish
before `diagnose` starts).

## R2: New threshold vars follow the one documented exception `watchdog.yml` already has

**Decision**: `vars.WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` (default
`10`), `vars.WING_COMMANDER_TURN_BUDGET_CONSECUTIVE_TRIGGER` (default
`3`), and `vars.WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION` (default
`0.6`) are read directly inside `watchdog.yml`'s `collect` job, matching
the exact defaults spec.md's Assumptions section commits to.

**Rationale**: Constitution VII normally requires every `vars.*` read to
live in the wrapper, not the reusable stage — but `watchdog.yml` already
carries a documented, named exception for its branch-prefix reads
(release.yml Gate 1b), because the watchdog's own inspection logic needs
those values regardless of which wrapper invoked it. The three new
thresholds are the same shape of value (a collector-internal tuning knob,
not an event fact), so they extend the existing exception rather than
opening a second one — opening a second exception is exactly the kind of
proliferation constitution VII's "a deliberate act rather than a
convenience" language guards against.

**Alternatives considered**: New `workflow_call` inputs on `watchdog.yml`,
threaded through by the wrapper (the pattern `diagnose-model`/
`diagnose-max-turns` already use) — rejected only because it would be the
*second* mechanism for the same class of knob inside one workflow file,
which is more surface for an adopter to learn than reusing the one that
already exists for this exact purpose.

## R3: Turn-budget cross-run history read — the spec-043 metrics branch, filtered client-side

**Decision**: `collect-turn-budget`'s per-run half reads the inspected
run's own metrics record — preferring the durable store (spec 043's
`records.jsonl` on the `metrics` branch, filtered to this run's
`record_key`) and falling back to the run's own uploaded
`metrics-record[-<label>]` artifact when the durable store has no entry
for this run yet (persistence is out-of-band and may not have completed,
or the adopter has not wired it — spec.md's own Assumption). The
cross-run half additionally reads the same `records.jsonl`, filtered to
records whose `stage` matches the inspected run's stage, ordered by
append position (the file's own natural order — spec 043's data-model.md
states it is never re-sorted), and takes the most recent
`WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` of them.

**Rationale**: This is the only durable, cross-run history the pipeline
already produces (spec.md's Assumptions section names it explicitly: "the
persisted history of those records is readable by the watchdog at
inspection time. This feature reads that data; it does not add fields to
it."). Reading `records.jsonl` directly via `git show
origin/<branch>:<path>` mirrors `verify-metrics-rollup-idempotent.py`'s
existing read shape — no new fetch mechanism.

**Interpretation decision** (FR-014's "execution-output artifact"
fallback): FR-014 predates the metrics-record/execution-output split spec
043 introduced — this plan reads "falling back to the run's execution-output
artifact" as "falling back to the run's own normalized `metrics-record`
artifact," the spec-043-normalized source, not the raw transcript. This
mirrors `collect-execution-output`'s own two-tier precedent (an
authoritative result-record read, with a labeled "not authoritative"
log-scan fallback only when the primary is unavailable) — reading the raw
transcript directly here would mean re-implementing `count-turns.sh`'s
extraction a second time, exactly the drift CLAUDE.md's "shared logic has
exactly one home" section warns against. If neither the store nor the
per-run artifact yields turn values, `collect-turn-budget` emits no
turn-budget signal for that run (FR-014's own fallback-of-fallback: "no
signal").

**Alternatives considered**: Reading `records.jsonl` unfiltered and doing
the stage/window filtering inside `diagnose`'s prompt — rejected outright
by constitution IX: which runs belong to the trend window is exactly the
kind of judgment that must be deterministic, not a model's read of a raw
file.

## R4: The trend's accumulate-then-escalate behavior is a collector-side pre-check, not a dedup-rule change

This is the plan's central design problem. FR-012 requires successive
runs at the same severity band to map to one accumulating finding; FR-015
requires a maintainer's closure of that finding to be treated as an
acceptance — no reopening, no new finding — until the trend escalates
into a strictly higher band, at which point exactly one new finding
files. FR-032 forbids changing the dedup rules to add a bespoke "don't
reopen this class" branch (today, `match-closed` unconditionally reopens
— watchdog.yml:2613-2615 — for every class, with no per-class exception).

**Decision**: Three sub-decisions, each additive:

1. **Severity band is a three-value ordinal, not a magnitude**: `watch`
   (the consecutive-run trigger alone is met), `elevated` (the
   climb-fraction trigger alone is met), `critical` (both are met in the
   same window). This uses exactly the two thresholds spec.md's
   Assumptions section already commits to — no third invented number —
   and gives every trend exactly one band label per run: the strongest
   condition its current window satisfies.
2. **The cross-run signal's identity is the (stage, band) pair, not the
   run's own turn counts.** `collect-turn-budget` computes the signal's
   `class-hint: "turn-budget-trend"` and `facts` normally (carrying the
   window's actual counted-turns/headroom numbers, per FR-009), but the
   *identity* the `Stamp signal ids` step hashes for this signal kind is
   `{stage, band}` alone (a new row in that step's existing source→kind
   map — see data-model.md). This is what makes every run that extends
   the same trend at the same band produce the *same* signal id, hence
   the same fingerprint (`sha256("turn-budget-trend|signals:" +
   that-one-id)`), hence a dedup match against the same issue every
   time — FR-012 falls out of the existing, unmodified fingerprint/dedup
   mechanism for free, exactly because nothing about it changes.
3. **Before emitting the cross-run signal, `collect-turn-budget`
   replicates the fingerprint formula for the band it is about to
   report and checks whether a *closed* `pipeline-defect` issue already
   carries that exact fingerprint** (`gh issue list --label
   pipeline-defect --label "🐕 · turn-budget-trend" --state closed --json
   body`, the same bounded direct-read shape the existing dedup-search
   step already uses, done here at collect time instead of triage time).
   If a closed match exists, `collect-turn-budget` emits no cross-run
   signal for this run — the collector suppresses its own signal rather
   than asking `diagnose` or `triage` to decide not to file. If no closed
   match exists (never filed, or filed and still open), it emits
   normally; an open match is left to the existing, unmodified
   `match-open` → comment path.

**Why this satisfies FR-015 without touching dedup**: a closed `watch`
finding stays closed while the trend keeps computing `watch` (same
fingerprint, found closed, suppressed every time). The moment the trend
computes `elevated` instead, that is a *different* signal identity, a
*different*, never-before-seen fingerprint — no closed match exists for
it, so `collect-turn-budget` emits, and the existing `none` → create-issue
path files it fresh. This is one new, narrowly-scoped read *inside a
single collector*, not a modification of `triage`'s dedup-search step,
its outcome vocabulary, or its reopen behavior — those remain exactly as
spec 024 left them.

**Rationale for band-as-identity over magnitude-as-identity**: the
rejected alternative (hashing the literal counted-turns/headroom numbers
into the signal identity) would make every run's signal a distinct
fingerprint, defeating FR-012 outright (one finding per run, not one
accumulating finding) — this is precisely the failure mode FR-012's
Independent Test calls out by name.

**Alternatives considered**: Teaching `triage`'s dedup-search step a
per-class "closed means accepted, do not reopen" exception table —
rejected: this is a direct, literal change to "the dedup rules," which
FR-032 names explicitly; every future class needing this behavior would
then also modify the shared step, the opposite of keeping new signals
flowing through the existing path "without that path being modified to
special-case" them (FR-003). Encoding the suppression as a prompt
instruction to `diagnose` ("if you see this pattern, don't file") —
rejected outright by constitution IX: this is exactly the durable-write
gate the principle requires deterministic code for, and a prompt that
silently isn't followed produces no error, no test failure, and no
signal that the gate was skipped.

## R5: The per-run turn-budget signal is `class-hint: null`, matching the existing evidence-only convention

**Decision**: FR-010's per-run signal (counted turns, intended budget,
enforced ceiling, consumed fraction) is emitted with `class-hint: null`,
`source: "turn-budget"` — the same convention `step-summary` and
`annotations` already use for signals that exist purely as potential
supporting evidence, never as a class a Finding should be built from in
isolation.

**Rationale**: `diagnose`'s existing (unmodified) prompt already
instructs: "a signal whose class-hint is already set... should normally
become a Finding of that class... a signal with class-hint: null...
needs your own judgment to decide whether it describes a genuine problem
worth a Finding" (watchdog.yml:1504-1510). FR-010 requires the per-run
signal to "serve only as evidence attached to a cross-run trend finding
and MUST NOT produce a filed finding on its own." Reusing the existing
null-hint convention gets this behavior from the *existing, unmodified*
prompt text — no prompt change, no new judgment rule for the model to
follow, satisfying FR-032 and constitution IX simultaneously: the
distinction that actually prevents a lone per-run signal from filing is
which one of the two existing, already-shipped prompt branches it falls
into, decided by a field the collector sets deterministically.

**Alternatives considered**: A new prompt paragraph specifically telling
`diagnose` "never file from a turn-budget signal alone" — rejected: a
direct edit to the prompt, forbidden by FR-032, and unnecessary once R5's
null-hint choice makes the existing paragraph already say the right
thing.

## R6: Final-PR-claims parsing treats the PR body as untrusted data to compare, never to execute

**Decision**: `collect-final-pr-claims` regex-parses the final PR body
for the three claim shapes finalize's narrative section is known to
produce today (a task count, a commit count, a test count — spec.md's
Assumptions section names these as "the ones the finalize stage reliably
emits today"), and independently re-derives each ground truth without
trusting anything the PR body says about how to derive it:

- **Task count**: `grep -c '^- \[[ xX]\]'` / `grep -c '^- \[[xX]\]'` over
  `tasks.md` on the PR's head ref — the exact idiom `finalize.yml`'s own
  state block already uses (finalize.yml:896-898), read independently by
  the collector rather than trusted from the PR's rendered state block
  (the state block is deterministic and always correct today, but this
  collector's job is to catch the *narrative* prose drifting from it, not
  to assume the state block itself is what drifted).
- **Commit count**: `git rev-list --count <base>..<head>` (or the
  paginated `gh api .../pulls/{number}/commits` count for a PR whose
  local clone doesn't have both refs) between the PR's recorded base and
  head SHAs — computed by the collector itself, not read from anything
  the finalize agent's own `git log` output claimed.
- **Test count**: research.md R7 below — this is the one claim shape with
  no pre-existing ground-truth source in this repository.

**Rationale**: FR-006/edge case ("a final PR body contains text that
looks like an instruction to an agent... treated as untrusted data to be
compared against ground truth, never as an instruction") is satisfied
structurally: the collector is a `jq`/`grep`/`git` pipeline with no agent
step in the loop at all — there is no execution context for an injected
instruction to reach, matching FR-005's "the collector owns its own
false-positive duty" and FR-023's "an unparseable claim is an absence of
evidence, never a finding" (a regex that fails to match is empty output,
not an error).

## R7: Test-count ground truth — new/changed fixture files, not a project-wide test framework

This repository has no project-wide unit-test framework (spec 024's own
plan.md: "no automated test suite exists for any pipeline stage in this
repository") — its test surface is the gate-registry convention itself:
one `verify-*.{py,sh}` script per gate, each carrying its own inline or
`fixtures/`-directory test cases (constitution VIII: "every failure
branch a gate ships MUST be exercised by a checked-in fixture"). There is
no existing artifact anywhere that states "N tests" for an arbitrary PR.

**Decision**: The ground truth for a test-count claim is the number of
files added under any `fixtures/` directory between the PR's base and
head (`git diff --name-only --diff-filter=A <base>..<head> | grep -c
'/fixtures/'`) — the file-level unit this repository already treats as
"one test case" by its own stated convention.

**Rationale**: This is a plan-level decision filling a genuine gap
spec.md leaves open (it names the ground truth abstractly as "the
test-run summary the run itself produced" without specifying what that
summary is, because none existed to name concretely). Anchoring to
fixture files rather than, say, counting assertion calls inside gate
scripts keeps the check generic across both this repository's testing
idioms (inline-heredoc fixtures in bash gates, `fixtures/`-directory
files for Python gates per spec 043's own data-model.md) without needing
to parse gate-script internals, and it directly targets the spec's own
motivating incident ("a 'new test cases' figure that was really a line
count") — a claim that conflates a line count with a test-case count is
exactly the kind of drift a file-level, not line-level, ground truth
catches.

**Limitation, stated rather than hidden**: a PR whose narrative claims a
test count in a different unit (e.g., "12 new assertions" in a gate with
no separate fixture file, only inline heredocs) is not verifiable against
this ground truth. Per FR-023/FR-005, that is an absence of evidence, not
a mismatch — the collector must not fabricate a finding it cannot
substantiate, so a claim in an unrecognized unit produces no signal.

**Alternatives considered**: Counting occurrences of the `note()`/
`reason()` assertion-helper calls `verify-denied-tool-collector.sh`'s
convention uses — rejected as gate-script-shape-specific (Python gates
don't use this helper) and therefore not generic enough to serve as one
check's ground truth across every gate style in the repository.

## R8: Cost-line malformation check must validate against the renderer's actual dual-precision format, not a single fixed precision

**Decision**: The "expected presentation" FR-018 requires is defined
against `wing-commander-metrics-summary`'s own existing `cost-line`
renderer (action.yml:293-305), which already uses two precisions by
design: two decimal places for amounts ≥ $1.00, four decimal places for
amounts < $1.00 (so a $0.0042 run doesn't round to a misleading
"$0.00"). The malformed-line check extracts the dollar-amount substring
from a stage's posted cost line and validates it against
magnitude-appropriate precision — `^\$[1-9][0-9]*\.[0-9]{2}$` for amounts
≥ 1, `^\$0\.[0-9]{4}$` for amounts < 1 — rather than one universal decimal
count.

**Rationale**: FR-018's literal text ("rounded to a fixed number of
decimal places") reads as one universal precision, but the renderer this
repository already ships (the one FR-020 says this check exists to guard
against *regressing*) deliberately varies precision by magnitude. Adopting
a single-precision rule that contradicts the renderer's own correct
output would make every sub-$1 run's well-formed line report as a false
positive malformed-cost-line finding — a direct violation of FR-019 ("no
signal when a well-formed cost figure is present, regardless of the
amount"). "Fixed" is read here as "fixed given the amount's own
magnitude, matching the one renderer this repository ships," not as
"fixed at a single global decimal count."

**Alternatives considered**: A single `^\$[0-9]+\.[0-9]{2}$` pattern
(literal reading of "fixed number of decimal places") — rejected for the
false-positive reason above; this repository's real formatting defect
class (#272's literal-`$COST_LINE`-string leak from an interpolation
choice, per implement.yml's own comment) is caught equally well by either
pattern, so the stricter, magnitude-aware pattern loses nothing while
avoiding a whole class of false positives on legitimately small-cost runs.

## R9: Narrative-drift findings never open an issue — one new, narrowly-scoped routing step

**Decision**: `triage` gains one new step, `Determine issue-filing
eligibility`, placed immediately alongside (not inside) the existing
`Coexistence suppression check`. It checks a fixed, hard-coded constant —
`class == "narrative-drift"` — and, if true, sets an `issueless: true`
flag on the triage decision artifact. `act`'s `Ensure pipeline-defect
issue` step gains one additional skip condition (`steps.decision.outputs.issueless
!= 'true'`, alongside its existing `dedup-outcome` and write-suppression
skip conditions); the always-on `Report finding to lifecycle issue` step
is untouched and still runs unconditionally, so the maintainer still sees
the mismatch exactly where FR-025 requires it — "at the moment they read"
the final PR, on the lifecycle issue, at no tracker cost.

**Rationale**: FR-025 needs a class that is fully diagnosed, fingerprinted
(so repeat mismatches on the same PR revision don't spam the lifecycle
issue either — dedup's `none`/`match-open` distinction still applies to
whether the report step says "new" or "recurrence"), yet never becomes a
tracked `pipeline-defect` issue. The only precedent for "this Finding
skips the tracked-issue path" is the existing coexistence-suppression
flag (`alreadyHandledBy`) — reusing that field's *mechanism shape*
(short-circuit before `Ensure pipeline-defect issue`) without reusing its
*meaning* (coexistence means "someone else already reported this exact
problem"; narrative-drift's exemption means "this class of problem is
permanently cosmetic-severity by design") keeps the two concepts
distinct, which the report step's rendered text also needs to (a
coexistence-suppressed Finding says "already reported by existing
automation"; an issue-exempt Finding needs its own wording, e.g. "cosmetic
narrative mismatch — reported here only").

**Why this doesn't touch the evidence-validity gate, fingerprint, or
dedup**: those three steps still run exactly as before for a
narrative-drift Finding — it is still fingerprinted, still dedup-searched
(so a second run citing the same evidence signal correctly reports
"recurrence," not "new," on the lifecycle issue) — only the one
downstream decision "does this open a `pipeline-defect` issue" gains a
class-based early exit, evaluated by a step that sits beside, not inside,
the protected ones.

**Alternatives considered**: Giving narrative-drift Findings a dedup
outcome of `unknown` (already an existing outcome that skips issue
creation, per FR-018/FR-019 of spec 024) — rejected: `unknown` means
"the dedup lookup itself failed," a data-integrity signal that should
alarm a maintainer differently from "this is cosmetic by design"; reusing
it would make a permanently-quiet class indistinguishable from a broken
lookup, and SC-007's precision measurement excludes `unknown` findings
for the *lookup-failed* reason, not the *by-design* reason narrative-drift
needs.

## R10: One class per collector concern, using the fixed ten-key `normalizedFacts` vocabulary

**Decision**: Five new classes, each mapped through the existing
`stage`/`expected`/`actual` (plus `spec` or `file` for artifact identity)
keys `diagnose`'s unmodified output schema already allows:

| Class | `stage` | `expected` | `actual` | Issue-filing |
|---|---|---|---|---|
| `turn-budget-trend` | inspected stage | e.g. `"budget 180, ceiling 450"` | e.g. `"226/180 turns, 3 consecutive runs, 60% of ceiling"` | Normal |
| `cost-line-missing` | inspected stage | `"cost line present"` | `"no cost line found for this run"` | Normal |
| `cost-line-malformed` | inspected stage | the expected pattern (R8) | the observed text (FR-018) | Normal |
| `narrative-drift` | `"finalize"` | the branch-derived ground truth | the PR body's claimed value | **Issue-exempt (R9)** |
| `spec-number-collision` | `"intake"` | n/a — uses `spec` for the contested number, `file`/`expected`/`actual` for the two claimant identities | | Normal |

**Rationale**: FR-032 forbids widening the output schema, so
`normalizedFacts`' fixed key vocabulary (`tool, branch, spec, file, job,
step, workflow, stage, expected, actual`) is a hard constraint, not a
starting point to extend. Every one of the four new detection classes is,
at its core, a comparison between two values — this is exactly what
`expected`/`actual` already exist to express (the existing `stage-mismatch`
class already uses this same pair for `expected-stage`/`actual-stage`).
This table is descriptive-only guidance for `diagnose` (per
`normalizedFacts`' own documented purpose: "DESCRIPTIVE ONLY... identity
now comes from the signal ids you cite") — the signals themselves (R11,
data-model.md) carry the full, unconstrained fact set FR-009 requires;
`normalizedFacts` only needs to be non-empty and well-shaped enough for
the evidence-validity gate's per-class required-key check, which gains
one row per new class (an additive registration, not a rule change — see
plan.md's Summary).

**Alternatives considered**: A single catch-all `stage`/`expected`/`actual`
triple with the specific claim-shape (task/commit/test) folded into free
text inside `expected`/`actual`'s own values for narrative-drift, rather
than three implied sub-shapes — this is in fact the decision made:
`narrative-drift` is one class, not three, because FR-022 requires "each
mismatch... its own signal," not its own class, and one class keeps the
issue-exemption check (R9) a single constant rather than a list to
maintain.

## R11: Signal-id source→kind map — four additive rows

**Decision**: `Stamp signal ids`' existing hard-coded source→kind map
gains four rows (data-model.md has the full ident shape per row):

| `source` | `kind` | Identity (`ident`) fields |
|---|---|---|
| `"turn-budget"` (per-run, `class-hint: null`) | `turn-budget-observation` | `{stage, run}` — distinct per run, never expected to be cited alone into a Finding (R5) |
| `"turn-budget-trend"` | `turn-budget-trend` | `{stage, band}` — **not** the run, per R4 |
| `"cost-report"` | `cost-line-claim` | `{run, stage, claim-type}` (`claim-type` ∈ `missing`\|`malformed`) |
| `"final-pr-claims"` | `narrative-claim` | `{pr, claim-type}` (`claim-type` ∈ `tasks`\|`commits`\|`tests`) |
| `"spec-collision"` | `spec-number-claim` | `{number, sorted-claimants}` |

**Rationale**: The map is what makes signal identity — and therefore
fingerprint identity — deterministic and collector-derived rather than
model-authored, the exact property spec 024 introduced this mechanism to
guarantee. Adding rows for new sources is the same shape of change every
future collector will always need (the map's `else` branch is explicitly
the failure path — "unmapped" plus a warning — never intended as a
permanent home for a real signal), so this is additive registration, not
a modification of the map's existing behavior for the five sources
already in it.

## R12: Gate coverage — numbers assigned at implementation time

Following spec 043's own precedent (its research.md R12): six new gates,
each fixture-backed, each wired the standard single-registration way into
`lint-workflows.yml`. Concrete gate numbers are assigned sequentially at
implementation time, not reserved here, to avoid colliding with numbers
other in-flight specs may claim first. Full fixture inventory in
data-model.md; contract in `contracts/gate-coverage-046.md`.

## R13: Decisions made without an explicit spec answer

Summarized for the lifecycle issue comment (none contradicts spec.md;
each fills a gap spec.md left to plan-level judgment):

- Severity-band ladder: `watch`/`elevated`/`critical`, derived from
  exactly the two existing thresholds, no third invented number (R4).
- The trend's accumulate/escalate mechanism: a collector-side, pre-emptive
  closed-fingerprint read, not a dedup-rule change (R4) — the single
  largest design decision in this plan.
- Turn-budget per-run signal uses the existing `class-hint: null`
  convention rather than a prompt change to prevent lone-signal filing (R5).
- Test-count ground truth: new/changed fixture files between the PR's
  base and head, with an explicit, stated limitation for claims in other
  units (R7) — no comparable "test-run summary" artifact exists in this
  repository today.
- Cost-line "expected presentation" matches the existing renderer's real
  dual-precision format (2 decimals ≥ $1, 4 decimals < $1), not a single
  universal decimal count, to avoid false positives on legitimately
  small-cost runs (R8).
- Narrative-drift's issue-exemption is a new, narrowly-scoped routing
  step beside (not inside) the existing coexistence check, distinct from
  reusing the `unknown` dedup outcome (R9).
- `normalizedFacts` for all four new classes fits inside the existing
  fixed ten-key vocabulary using `stage`/`expected`/`actual` as the
  general comparison slots (R10) — FR-032 forbids widening that schema.
- New threshold vars are read directly in `watchdog.yml`, extending its
  one documented `vars.*` exception rather than adding `workflow_call`
  inputs (R2).
- Gate numbers deferred to implementation time (R12).
