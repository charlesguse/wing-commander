# Phase 0 Research: Name-Free Stage Identity for Watchdog Collectors

spec.md's own Clarifications section already resolved the three open
questions raised during intake/clarify (Q1 precedence, Q2 spec-identity
declaration shape, Q3 warning condition) and its "Status update
2026-09-30" section re-verified every FR-002 site's line citation against
current `main`. No `[NEEDS CLARIFICATION]` marker remains in spec.md, so
this phase covers only the technical decisions the spec leaves to the
plan: where the new logic lives, what it is named, and how it is proven.

## R1 — Where the resolved stage identity is computed and exposed

**Decision**: Add the computation to the existing single home,
`wing-commander-inspected-run-identity`'s composite action, as a third
step following the existing `resolve` and `stage` steps. It consumes the
composite's own `record-stage` output (already computed) and, only when
that is empty, falls back to a `case "$RUN_NAME"` mapping covering every
stage FR-014a names (`intake`, `clarify`, `plan`, `tasks`, `implement`,
`finalize`, `cleanup`, `rebase`, `pr-conversation`). It exposes two new
composite outputs:

- `resolved-stage`: `record-stage` if non-empty, else the name-derived
  value, else empty.
- `resolved-stage-source`: `record`, `name`, or empty (none resolved).

**Rationale**: FR-003 requires exactly one derivation shared by every
consumer; the composite is already that home for `record-stage` and the
slug (per the action's own header comment, `#266`/`#322`). Adding a step
here costs no new metrics-record download (FR-004) — it reuses
`record-stage`'s already-downloaded copy at `$RUNNER_TEMP/spec-slug-
metrics-record`, consulting `$RUN_NAME` only as a string already passed
into the composite as `inputs.run-name`.

**Alternatives considered**: Computing the fallback inside each collector
in `watchdog.yml` (rejected — recreates exactly the per-collector
duplication FR-003 and CLAUDE.md's "shared logic has exactly one home"
forbid, and is why the FR-012 gate would then have to check N call sites
instead of one). Replacing `record-stage` itself with the resolved value
(rejected — spec 109 FR-013 keys `tool-denial` signal identity on
`record-stage` specifically; spec.md's status update already settled this
as "expose beside, never replace").

## R2 — Name-derived fallback coverage and the FR-012 gate's one permitted site

**Decision**: The name-derived `case "$RUN_NAME"` step is the single
step the FR-009 fallback, and therefore the FR-012 gate's one permitted
exception, occupies. It carries a fixed step id (`id: name-fallback`) so
the gate can name it precisely rather than match on line numbers, which
drift.

**FR-012 gate design**: a new Python gate script
(`verify-no-reference-name-stage-match.py`) that:

1. Parses `watchdog.yml` and
   `wing-commander-inspected-run-identity/action.yml` for any `run:` block
   containing one of the nine reference display-name literals
   (`"Wing Commander · 1 intake"` … `"Wing Commander · 9 pr conversation"`,
   plus `"Wing Commander · 8 watchdog"` for the self-inspection guard)
   used inside a shell conditional (`case`/`if`/`[`) that gates behavior.
2. Fails if any such match is found outside the `id: name-fallback` step
   this feature introduces.
3. Passes today (pre-implementation) only in the sense that it does not
   yet exist; the gate ships together with the sites it checks, in the
   same PR, so it is red-then-green within one change rather than landing
   toothless.

**Rationale**: constitution VIII forbids a gate that cannot fail its
subject; grepping for the literal strings themselves (rather than
line-number ranges) means the gate keeps checking after the next
unrelated edit reflows the file, which spec.md's own re-verification of
stale line citations shows is a real risk in this file.

**Alternatives considered**: An allowlist of line ranges (rejected — the
exact failure mode CLAUDE.md's Gate 47 pointer mechanism exists to avoid:
a line-range allowlist silently stops checking anything once lines shift).

## R3 — The spec-identity declaration's shape and call-site enforcement

**Decision**: A new optional boolean field nested under the existing
`spec` group in the metrics-record schema: `spec.identity_is_own`.
Absent on any record (including every record written before this feature
ships) is read as `false` (FR-008a) — never as a validation failure, so
old records stay schema-valid. `wing-commander-metrics-summary` gains a
new input, `spec-identity-is-own` (`'true'`/`'false'`, **no default**),
written straight into `spec.identity_is_own` as a JSON boolean. Every
existing call site of the composite (the ~30 sites research found across
12 workflows) is updated in the same PR to pass it explicitly: `'true'`
for the six single-spec stages the current allowlist names (intake,
clarify, plan, tasks, implement, finalize), `'false'` for every other
stage that emits a record (watchdog, cleanup, rebase, pr-conversation,
board-loop, lifecycle-review-gate).

**Enforcing SC-008 ("zero stages ... omit the declaration")**: giving the
input no default does not by itself make GitHub fail an omitted `with:`
key on a composite action (composite inputs are not enforced the way
`workflow_call` inputs are). The real enforcement is a static check added
to the existing call-site-completeness family of gates (the pattern Gate
72 and Gate 100 already use for other "every call site carries X"
properties): the new gate script from R2 also scans every `uses: ./
.github/actions/wing-commander-metrics-summary` (and its local
equivalents) block for a `spec-identity-is-own:` key, failing on any
call site missing one. This keeps FR-012 and SC-008 behind the same gate
rather than opening a second one for a closely related property.

**Rationale**: FR-008b requires the field to land in `specs/043-durable-
metrics-record/contracts/metrics-record-schema.md` as an additive
schema-version-1 field; nesting under `spec` groups it with the slug and
lifecycle-issue fields it semantically qualifies, matching the schema's
existing grouping (`REQUIRED_SPEC` in `verify-metrics-record-schema.py`).
A plain boolean (not a `*_available` pair) is correct because there is no
"unavailable but distinguishable from false" state here — FR-008a
collapses "absent" and "false" on purpose.

**Alternatives considered**: Q2-A (deriving trust from the resolved
stage) was already rejected in spec.md as circular. A top-level field
(`spec_identity_is_own`) instead of nesting under `spec` (rejected only
for consistency with the schema's existing grouping — no functional
difference; nesting keeps `REQUIRED_SPEC`'s dict the single place new
spec-scoped fields are added).

## R4 — Consumption at the seven FR-002 sites (excluding the slug-fallback allowlist)

**Decision**: Each site's existing `case "$RUN_NAME" in ... esac` or
`[ "$RUN_NAME" = ... ]` is rewritten to switch on
`needs.collect.outputs.resolved-stage` (the composite output already
computed once in the `collect` job and available to every job/step that
already reads `steps.spec-slug.outputs.*`), with a third arm added
everywhere the existing code only distinguished two:

| State | `resolved-stage` / `-source` | Existing two-arm code | New three-arm code |
|---|---|---|---|
| Identified, in scope | non-empty, matches expected stage | matched arm runs | unchanged |
| Identified, out of scope | non-empty, does not match | `*)` skip arm runs | unchanged (still a silent, on-purpose skip — FR-005) |
| Not identified | empty, `-source` empty | today: `*)` skip arm runs (wrongly, per spec.md's motivating defect) | a NEW arm: skip, but write `{"collector": "<name>", "outcome": "unresolved"}` to `collector-outcomes.json` (R5) |

**Rationale**: FR-005 forbids reporting "not identified" as "out of
scope"; distinguishing the third arm from the `*)` default is the only
way a collector that used to silently skip can now say which of the two
reasons applied.

**Slug-fallback allowlist (excepted by FR-002/FR-009a)**: this one site
does not switch to `resolved-stage` — per FR-008 it consumes the
record's own `spec.identity_is_own` declaration (R3) instead. Concretely,
`action.yml:207`'s `case "$RUN_NAME" in <six names>) record_fallback=true
;; esac` is replaced by reading `spec.identity_is_own` off the record
this step already has open (the same downloaded copy the `stage` step
scans), evaluated only for runs where a record exists at all — a run
with no record still has no slug to resolve regardless.

## R5 — Surfacing "not identified" in the inspection's report (FR-006, SC-003)

**Decision**: Reuse the existing `collector-outcomes.json` mechanism
(`RUNNER_TEMP/collector-outcomes.json`, already populated by every
collector with `{"collector": ..., "outcome": "ok"|"failed"}` and
consumed by the `aggregate` step at `watchdog.yml:2033` to compute
`untrusted-collectors`) rather than inventing a parallel channel. Add a
third outcome value, `"unresolved"`, written by any FR-002-site collector
that hits the new third arm from R4. Extend the `aggregate` step to also
count `outcome=="unresolved"` entries into a new output,
`stage-unresolved-collectors` (name and count, mirroring
`collectors-failed`/`untrusted-collectors`), and extend both of the
existing deterministic report strings at `watchdog.yml:2076`+ ("Report
'passed inspection'"/"could not inspect") to name it when non-zero — e.g.
appending "; N evidence class(es) not examined because the inspected
run's stage could not be identified" — so SC-003's "unqualified pass"
never reaches the lifecycle issue.

**Rationale**: constitution IX and CLAUDE.md both push toward reusing an
existing deterministic accounting structure rather than adding a second
one that could drift from it; `collector-outcomes.json` already exists
for exactly this class of problem ("a collector's read outcome, distinct
from its shell exit code") and its one consumer (`aggregate`) is already
the single home for turning collector outcomes into verdict wording.
Keeping `unresolved` a distinct value from `failed` also preserves
FR-005: an unresolved stage is never folded into `untrusted-collectors`,
which the diagnose step's own prompt currently reads to mean "this
collector's read genuinely errored," a different claim.

**Alternatives considered**: A brand-new `stage-identity.json` side file
(rejected — a second book-keeping structure for the same kind of fact
`collector-outcomes.json` already tracks is the pasted-copy failure mode
CLAUDE.md warns about, one level up). Folding `unresolved` into the
existing `failed` bucket (rejected — FR-005 explicitly forbids collapsing
the third state into either of the other two, and `failed` specifically
means "this collector's own read errored," which is not what happened
here).

## R6 — The FR-014 name-warning condition

**Decision**: A new step in the `collect` job, gated on
`resolved-stage-source == ''` (nothing resolved from any source) AND the
existing `collect-execution-output` step's own already-computed
artifact-presence fact (it already distinguishes "no
`claude-execution-output*` artifact found" from "found and processed" at
`watchdog.yml:546`/`650`). Rather than re-downloading or re-checking for
the artifact a second time (which would cost an extra `gh run download`
FR-004 does not budget for this collector but does forbid growing), the
existing step is extended to also emit a
`claude-execution-output-found` output, and the new warning step reads
that plus `resolved-stage-source`.

**Rationale**: FR-014 requires the condition to be "a checkable property
of the run" — the artifact's presence is exactly that, and
`collect-execution-output` already computes it as a side effect of doing
its own job; exposing it as an output is cheaper than a second check and
keeps the single-download budget FR-004 sets for the *metrics record*
(a separate artifact class) from becoming a precedent for re-downloading
the execution-output artifact too.

## R7 — Fixture coverage (FR-013, SC-006)

**Decision**: Each of the following gets at least one checked-in fixture,
added to the existing fixture families rather than a new ad hoc set:

| Branch | Fixture home |
|---|---|
| Record with no stage (`stage_available: false`) | `verify-metrics-record-schema.py` fixtures (already has healthy/degraded shapes) |
| Missing record entirely | `verify-metrics-summary-record-emission.py`'s existing "missing artifact" case, extended to assert `resolved-stage-source` falls through to name |
| Unrecognised display name, no record | new case in the R2 gate script's own self-test, plus a `wing-commander-inspected-run-identity` fixture-style test if one exists (else a small bats/bash-under-test harness matching the composite's own conventions) |
| Record with no `spec.identity_is_own` (pre-feature record) | `verify-metrics-record-schema.py` fixture asserting FR-008a's read as `false`, not a schema failure |
| Record stage vs. name disagreement | fixture proving precedence (record wins) — belongs beside the resolved-stage composite's own test, since FR-009 says this is "never even observed" downstream, i.e. it is a property of R1's derivation alone |

**Rationale**: SC-006 requires zero branches covered only by manual
demonstration; anchoring each new branch to an existing fixture family
(rather than a new one per branch) keeps the count of "homes for this
kind of test" from growing past what CLAUDE.md's single-home rule would
tolerate.

## R8 — `docs/adoption.md` update (FR-011, SC-005)

**Decision**: Add a new subsection directly after "A wrapper-owned
feature needs a wrapper change too" (the closest existing precedent for
"what still depends on wrapper content"), titled to directly answer
US3's independent test question ("may I rename my wrappers, and what do
I lose?"). It states: display names are free-form for all ten stages;
the sole behavior that still reads one is the FR-009 fallback, active
only when a run leaves no metrics record (expired/missing artifact,
early failure, cancellation); every reference-named example wrapper in
this document works unchanged either way.

**Rationale**: directly answers SC-005's readability bar without
requiring the reader to open `watchdog.yml`; placed next to the existing
wrapper-diff section because both are about "what in this document is
load-bearing beyond the pinned stage version."

## R9 — Gate number

**Decision**: The new gate is the next unclaimed number in
`lint-workflows.yml` at the time tasks/implement lands it (125 is the
highest claimed as of this plan; the implement stage re-checks before
claiming a number, since other specs land concurrently on this
repository's own board).

**Rationale**: hardcoding a number here risks collision with another
spec merged in the interim; `run-local-gates.py` derives its gate list
from `lint-workflows.yml` itself (per the research agent's finding), so
no separate registry needs the number in advance.
