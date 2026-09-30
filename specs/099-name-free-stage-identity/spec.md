# Feature Specification: Name-Free Stage Identity for Watchdog Collectors

**Feature Branch**: `099-name-free-stage-identity`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #750 — "watchdog collectors silently skip adopters whose wrapper names differ from the reference names"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An adopter with their own wrapper names gets the same watchdog coverage (Priority: P1)

An adopter installs the pipeline and names their wrapper workflows to fit
their own repository's conventions — `ai-spec-intake`, `Feature Pipeline:
Implement`, anything at all. The watchdog inspects their runs and produces
exactly the same findings it would produce for a repository that copied the
reference wrapper names verbatim: stage/spec-meta mismatches are detected,
lost progress on a plan/tasks/implement run is detected, finalize PR claims
and intake spec-number collisions are checked, and a dispatched run's spec
slug still resolves.

**Why this priority**: This is the defect. Today every one of those
collectors takes its "not my stage — skipping" branch for a renamed wrapper
and the watchdog reports "run passed inspection. No problems detected." A
green check that cannot fail its subject is precisely what constitution
VIII forbids, and hardcoded reference names in a published stage are
precisely what constitution VI forbids.

**Independent Test**: Drive one watchdog inspection against a run of a
wrapper whose display name shares no substring with the reference names,
where the underlying spec is in a state the spec-meta collector must flag.
The finding is filed. Repeat with the reference-named wrapper: the same
finding, same facts.

**Acceptance Scenarios**:

1. **Given** an inspected run from a wrapper named `Feature Pipeline:
   Implement` that calls the implement stage, and a spec whose recorded
   stage is earlier than `implement`, **When** the watchdog inspects that
   run, **Then** the spec-meta collector emits the stage-mismatch signal it
   would have emitted for a run named `Wing Commander · 5 implement`.
2. **Given** an inspected run from a renamed plan wrapper that pushed no
   commits to its spec branch and whose record carries branch-advance
   evidence, **When** the watchdog inspects it, **Then** branch-drift
   measures the spec branch and reports lost progress rather than skipping
   as "not a push-expected stage".
3. **Given** a dispatched run from a renamed tasks wrapper whose head is the
   default branch, and whose record declares the spec it names as the run's
   own, **When** the inspected-run-identity composite resolves the spec slug,
   **Then** the metrics-record fallback runs and the slug resolves, so
   collectors and the diagnose verdict file against the spec's lifecycle
   issue instead of the bare run URL.
4. **Given** an inspected watchdog, rebase, or cleanup run whose record
   names a spec it did not advance, **When** the composite resolves the spec
   slug, **Then** the record's own declaration that the spec is not the
   run's own suppresses the fallback, regardless of that run's display name.
5. **Given** an inspected run from a renamed finalize wrapper whose final PR
   body overstates its task count, **When** the watchdog inspects it,
   **Then** final-pr-claims runs and the narrative-drift signal is emitted.
6. **Given** an inspected run from a renamed intake wrapper that created a
   spec number already claimed, **When** the watchdog inspects it, **Then**
   spec-collision runs and the collision signal is emitted.

---

### User Story 2 - A maintainer can tell when stage identity was not resolved (Priority: P2)

When neither the inspected run's own evidence nor its display name yields a
stage, the watchdog says so — in the step summary and in whatever the
maintainer reads about that inspection — rather than emitting a silent
"skipping" line inside a collector nobody reads and a top-level "passed
inspection" verdict.

**Why this priority**: Without this, the fix is only as good as the new
identity source: the moment a run's record is missing or expired the
adopter is back in today's silent-skip world with no way to know. The P1
story delivers coverage; this story delivers the ability to trust it.
Constitution VIII: a collector that cannot reach its subject must say so
rather than report a pass it did not earn.

**Independent Test**: Inspect a run that emitted no metrics record and
carries an unrecognised display name. The inspection's own report names the
collectors that could not run, and the top-level verdict is not an
unqualified clean bill of health.

**Acceptance Scenarios**:

1. **Given** an inspected run with no resolvable stage identity from any
   source, **When** the watchdog finishes, **Then** its report distinguishes
   "inspected, no problems" from "some evidence classes were not examined
   because the stage could not be identified".
2. **Given** an inspected run whose display name is unrecognised but whose
   record names its stage, **When** the watchdog finishes, **Then** no
   warning about the name is emitted — the stage was identified.
3. **Given** an inspected run with no resolvable stage identity that
   uploaded a `claude-execution-output*` artifact, **When** the watchdog
   finishes, **Then** its report warns that the display name was not
   recognised and no name-free source supplied a stage.
4. **Given** an inspected run with no resolvable stage identity that
   uploaded no `claude-execution-output*` artifact — an adopter's unrelated
   workflow, or a pipeline run that failed before its agent step — **When**
   the watchdog finishes, **Then** no name warning is emitted, because
   "unrecognised" is the normal answer for such a run.
5. **Given** a run of one of this repository's reference-named wrappers
   (cleanup, rebase and pr-conversation included, which do upload
   `claude-execution-output*`) that left no metrics record, **When** the
   watchdog finishes, **Then** the name fallback resolves its stage and no
   name warning is emitted (FR-014a).

---

### User Story 3 - The adoption docs state exactly what still depends on a name (Priority: P3)

`docs/adoption.md` states, in one place, whether wrapper display names are
free-form and which pipeline behaviours (if any) still read them, so an
adopter choosing a name knows what they are choosing.

**Why this priority**: Documentation cannot substitute for the fix, but a
reader who has to infer a naming requirement from eight `case "$RUN_NAME"`
branches in a published stage is the reason this issue exists. Today the
reference names appear in the example wrappers with no statement either way.

**Independent Test**: Read `docs/adoption.md` alone and answer "may I rename
my wrappers, and what do I lose?" without opening `watchdog.yml`.

**Acceptance Scenarios**:

1. **Given** the shipped `docs/adoption.md`, **When** an adopter reads the
   wrapper section, **Then** it states whether the reference display names
   are required and lists any behaviour that still keys on them.

---

### Edge Cases

- **The record is gone.** Artifact retention expired, the artifact was
  never uploaded, or the download failed. The run's stage is then knowable
  only from its name — which is exactly the case the reference-name match
  handles today. Per FR-009 this does fall back to the name.
- **The run emitted no record at all.** A run that was skipped, cancelled,
  or failed before its metrics step never wrote one. Most collectors
  already exit early on `skipped`/`cancelled`, but a run that *failed* mid-
  stage is still inspected and is exactly the kind the watchdog exists for.
- **The record exists but carries no stage.** `stage_available: false` is a
  shape the metrics-summary composite explicitly supports. It must be
  treated as "no stage from this source", never as the empty-string stage.
- **The run is not a single-spec stage.** An adopter's unrelated workflow,
  or the pipeline's own cleanup, rebase, or pr-conversation runs. These have
  no single spec and no expected stage transition; the correct outcome is
  still "skip, on purpose". An adopter's unrelated workflow uploads no
  `claude-execution-output*` artifact, so per FR-014 no name warning fires —
  which is where most unrecognised names legitimately land. Cleanup, rebase
  and pr-conversation *do* upload one (`cleanup.yml:802`, `rebase.yml:807`,
  `pr-conversation.yml:1029`/`2259`). Their records name their stage, and a
  record-less run is resolved by the name fallback (FR-014a), so they reach
  the warning only under a renamed wrapper — the case the warning is for.
- **The record's stage and the name disagree.** A wrapper named
  `Wing Commander · 3 plan` that actually calls the tasks stage, or a single
  wrapper file that calls two stages. Per FR-009 the record's stage wins:
  the name is consulted only when the record yields no stage, so a
  disagreement is never even observed.
- **Several records, one run.** An implement run writes a cycle record and
  a progress record; a rebase run writes one per matrix slug. Each names the
  same stage, so first-record-wins is safe for the stage field even where it
  is unsafe for the spec field.
- **Self-inspection.** The watchdog's own record carries `stage: watchdog`
  *and* borrows the spec of the run it inspected. The stage field is
  therefore trustworthy for self-inspection even though the spec field is
  not. Per FR-008 the watchdog's record declares that its spec identity is
  not the run's own, so the borrowed spec is rejected without any list
  naming the watchdog.
- **A record borrowed from another run.** The existing allowlist exists to
  stop the watchdog's, rebase's, and cleanup's records from tying those runs
  to an arbitrary spec. Any change here must not reopen that; per FR-008
  each of those stages declares the borrowing in its own record, and per
  FR-008a a record predating the declaration is treated as borrowing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST resolve the inspected run's stage identity
  from evidence that does not depend on the run's workflow display name,
  for every stage that emits a metrics record.
- **FR-002**: Every site that today identifies the inspected stage by
  matching a reference display name MUST consume the resolved stage
  identity instead of matching a name — except the inspected-run-identity
  composite's metrics-record slug-fallback allowlist, which per FR-008
  consumes the record's own spec-identity declaration rather than the
  resolved stage. The known sites are: that slug-fallback allowlist; the
  branch-drift collector's push-expected-stage gate, its implement-only
  since-created baseline arms, and its stage label for the summary line; the
  spec-meta collector's expected-stage map; the final-pr-claims finalize
  scope guard; the spec-collision intake scope guard; and the watchdog's own
  self-inspection cascade guard.
- **FR-003**: The resolved stage identity MUST be derived once per
  inspection and shared by every consumer, rather than each collector
  deriving its own. (CLAUDE.md, "shared logic has exactly one home".)
- **FR-004**: Resolving the stage identity MUST NOT add a metrics-record
  download beyond the one the inspection already performs — the collectors
  that need the record today already share a single downloaded copy.
- **FR-005**: Every consumer MUST distinguish three states: stage
  identified and in scope, stage identified and out of scope (skip on
  purpose), and stage not identified. The third MUST NOT be reported as the
  second.
- **FR-006**: A stage identity that cannot be resolved MUST be surfaced in
  the inspection's report as an evidence class that was not examined, so
  the inspection is not reported as an unqualified clean pass.
- **FR-007**: The mapping from a resolved stage to its expected `spec-meta`
  lifecycle stage (intake→spec, plan→plan, tasks→tasks,
  implement→implement, finalize→review) MUST keep exactly one home, as the
  display-name map does today.
- **FR-008**: The rule that a watchdog, rebase, or cleanup run is never tied
  to a borrowed spec MUST remain enforced, and MUST be enforced by a
  property the metrics record itself carries: each record MUST declare
  whether the spec identity it names is the emitting run's own. The central
  allowlist of stages is removed, so no list can drift as stages are added.
  (Q2-A, which re-expressed the allowlist as resolved stage values, was
  rejected as circular — it would decide whether to trust a record's spec
  field using a stage read from that same record.)
- **FR-008a**: A metrics record that carries no such declaration — one
  written before the field existed — MUST be treated as NOT declaring the
  spec as the run's own, which is today's safe default.
- **FR-008b**: The declaration MUST be added to the durable record's
  documented shape (`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`)
  as an additive schema-version-1 field (that contract's rule 1), with the
  contract stating FR-008a's reading of a v1 record that predates it. It
  MUST be covered by `verify-metrics-record-schema.py`'s fixtures. No
  `schema_version` bump is made.
- **FR-009**: The precedence between the name-free stage identity and the
  display name MUST be fixed and documented in one place, and MUST be:
  the metrics record's stage first, and the display name only when the
  record yields no stage (no record, or `stage_available: false`). Runs that
  failed early, were cancelled, or whose artifacts expired leave no record
  and are the watchdog's core subject, so the name fallback is retained
  rather than dropped.
- **FR-009a**: Because the display name survives as a documented fallback,
  the FR-012 gate MUST permit a reference display name only in that fallback
  position and MUST fail it as a primary stage-identification condition.
- **FR-010**: The published stage workflows MUST NOT require an adopter's
  wrapper to carry any particular display name in order to receive the
  collector coverage FR-002 lists.
- **FR-011**: `docs/adoption.md` MUST state whether the reference wrapper
  display names are required, and MUST list any pipeline behaviour that
  still reads them.
- **FR-012**: A checked-in gate MUST fail if a reference display name
  reappears as a stage-identification condition at any of the FR-002 sites,
  the single FR-009 fallback excepted per FR-009a, so the consolidation
  survives the next edit. (CLAUDE.md: "a rule with no gate behind it lasts
  until the next session.")
- **FR-013**: Each failure and fallback branch this feature introduces MUST
  be exercised by a checked-in fixture — a record with no stage, a missing
  record, an unrecognised name, a record carrying no spec-identity
  declaration, and a disagreement between the two sources. (Constitution
  VIII.)
- **FR-014**: A warning about the inspected run's display name MUST be
  emitted only when no stage was resolved from any source AND the run meets
  a deterministic condition identifying it as a pipeline stage run. That
  condition MUST be a checkable property of the run rather than a judgment:
  the run uploaded a `claude-execution-output*` artifact. (Constitution IX.)
  A run whose stage resolved MUST NOT produce a name warning, and neither
  MUST a run that fails the condition — which is where most unrecognised
  names legitimately land.
- **FR-014a**: The FR-009 name fallback MUST recognise the reference display
  name of every stage whose runs can satisfy FR-014's condition — cleanup,
  rebase and pr-conversation included, not only the six single-spec stages
  the allowlist names today. A reference-named wrapper in this repository
  then never produces a name warning, so this repository's behaviour is
  unchanged (Assumptions).

### Key Entities

- **Inspected-run stage identity**: which pipeline stage the run under
  inspection executed, expressed as a stage value (`intake`, `clarify`,
  `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`,
  `pr-conversation`, `watchdog`, `board-loop`) or "unknown". One value per
  inspection, plus the source it came from.
- **Metrics record stage field**: the `stage` / `stage_available` pair each
  stage's metrics record already carries. The literal is set inside the
  published stage workflow, not by the wrapper, so it is adopter-
  independent by construction.
- **Record spec-identity declaration**: a property each metrics record
  carries stating whether the spec identity it names is the emitting run's
  own or borrowed from the run it was reporting on. Set inside the published
  stage workflow, like the stage field. Absent on records written before the
  field existed, which count as borrowed (FR-008a). This replaces the
  single-spec stage allowlist.
- **Wrapper display name**: adopter-owned, free-form. After this feature it
  is load-bearing only as the fallback stage source when the record yields
  no stage (FR-009), and as the subject of the narrow warning in FR-014.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the same underlying run, an inspection of a wrapper with
  an arbitrary display name and an inspection of a wrapper with the
  reference display name produce identical collector outcomes and identical
  findings — zero differences across all FR-002 sites.
- **SC-002**: Zero of the FR-002 sites decide stage scope by comparing
  against a reference display name, as measured by the FR-012 gate. Names
  survive at exactly one site — the single fallback FR-009 defines, reached
  only when the record yields no stage.
- **SC-003**: Zero inspections report an unqualified "passed inspection" for
  a run whose stage could not be identified.
- **SC-004**: The number of metrics-record downloads per inspection is
  unchanged from today.
- **SC-005**: An adopter can answer "may I rename my wrappers, and what do
  I lose?" from `docs/adoption.md` alone, with no reference to the stage
  workflow sources.
- **SC-006**: Every fallback and failure branch introduced has at least one
  checked-in fixture; zero branches are covered only by a manual
  demonstration.
- **SC-007**: Zero name warnings are emitted on inspections whose stage
  resolved, and zero on inspected runs that uploaded no
  `claude-execution-output*` artifact; an inspected run that uploaded one and
  resolved no stage yields exactly one.
- **SC-008**: Zero stages that emit a metrics record omit the spec-identity
  declaration, and zero lists of stage or wrapper names remain in the
  slug-resolution path.

## Clarifications

All three open questions were answered on lifecycle issue #750. No
[NEEDS CLARIFICATION] markers remain.

### Q1 — Precedence between the record's stage and the display name → **A**

**Resolved**: the metrics record's stage comes first; the display name is
consulted only when the record yields no stage (no record at all, or
`stage_available: false`). Encoded in FR-009 and FR-009a.

**Rationale given**: runs that failed early, were cancelled, or whose
artifacts expired leave no record, and they are the watchdog's core subject.
Dropping the name fallback (B) would regress them. C was not chosen: it
leaves the reference names as the primary contract.

**Consequence carried into the requirements**: the reference names stay in
the source as a fallback, so the FR-012 gate must permit them in that one
position while failing them as a primary condition (FR-009a), and the
record-vs-name disagreement edge case resolves in the record's favour
without ever being observed.

### Q2 — What the single-spec allowlist becomes → **B**

**Resolved**: each stage's metrics record declares whether the spec identity
it names is the emitting run's own, and the central allowlist is removed.
Encoded in FR-008 and FR-008a.

**Rationale given**: the knowledge lives in the stage that writes the
record, so no central list drifts as stages are added. A was rejected as
circular — it would decide whether to trust a record's spec field using a
stage read from that same record.

**Consequence carried into the requirements**: the record's shape widens and
every stage that emits one is touched; a record written before the field
existed carries no declaration and is treated as not the run's own, which is
today's safe default (FR-008a). The FR-002 slug-fallback site therefore
consumes the declaration rather than the resolved stage.

### Q3 — Whether an unrecognised display name is warned about → **A**

**Resolved**: warn only when no stage resolved from any source AND the run
otherwise looks like a pipeline stage. Encoded in FR-014 and SC-007.

**Rationale given**: signal where it matters, silence where "unrecognised"
is the normal answer. B fires on every non-stage run, which is routine noise
in this repository.

**Consequence carried into the requirements**: "looks like a pipeline stage"
is reduced to the deterministic condition constitution IX demands — the run
uploaded a `claude-execution-output*` artifact — rather than left as a
judgment.

### Status update 2026-09-30 — reconciled with current `main` (maintainer spec review)

- **#744 has merged** (`ae4caf20`, "key denied-tool findings by stage as
  well as tool"). `wing-commander-inspected-run-identity` now emits
  `record-stage` (`action.yml:151-156`), the first record in sorted order
  that names a stage (`action.yml:285-318`). FR-003's single home is that
  output: the resolved identity is record-stage, then the FR-009 name
  fallback, and it is derived in the composite, not per collector. The
  "#744 has not yet merged" Assumption is corrected.
- **Keep `record-stage` record-only (spec 109, merged).** Denial signal
  ids key on `record-stage` today, and spec 109 FR-013 requires the
  per-`{stage, tool}` separation to be preserved. The resolved identity is
  therefore exposed *beside* `record-stage`, not in place of it. Changing
  what the denial id keys on, for example keying a record-less run on a
  name-derived stage instead of `unknown`, would re-key existing
  `pipeline-defect` issues, and it is not part of this feature.
- **FR-002's sites are re-verified on `main`**, and no other site
  identifies the inspected stage by display name:
  - slug-fallback allowlist: `action.yml:207`;
  - branch-drift push-expected gate: `watchdog.yml:692-693`;
  - implement-only baseline arms: `watchdog.yml:795` and `852`;
  - stage label: `watchdog.yml:867-869`;
  - spec-meta map: `watchdog.yml:1024-1029`;
  - final-pr-claims: `watchdog.yml:1705`;
  - spec-collision: `watchdog.yml:1829`;
  - self-inspection guard: `watchdog.yml:3507`.

  `gh run list --workflow 'Wing Commander · 8 watchdog'` at
  `watchdog.yml:3524` is the run-discovery dependency that Assumptions
  already scope out.
- **Two record copies exist today, not one.** The composite downloads into
  `spec-slug-metrics-record` (`action.yml:213`, reused at `301`). The
  collectors share `metrics-record-shared` (`watchdog.yml:822-824`,
  `1393-1395`, `1603-1606`). FR-004/SC-004's baseline is that count. The
  plan may consolidate the two copies, but must not add a third.
- **FR-014's condition covers cleanup, rebase and pr-conversation.** Each
  of them uploads a `claude-execution-output*` artifact. US2 scenario 4 and
  the "not a pipeline stage" edge case said they did not; both are
  corrected. FR-014a keeps this repository's reference-named runs from
  warning.
- **The record's shape is a documented contract** (spec 043's schema,
  gated by `verify-metrics-record-schema.py`). FR-008b records the new
  declaration there as an additive v1 field.
- **Specs in flight on the same workflow.** Spec 101 (#759) adds a
  diagnose log-staging step to `watchdog.yml`, and spec 109 (merged)
  changes finding dedup. Neither identifies the inspected stage by display
  name, so neither adds an FR-002 site.
- US1's acceptance scenarios are renumbered into order (the Q2 scenario had
  been inserted as "6" between 3 and 4).

## Assumptions

- The metrics record's `stage` literal is set inside each published stage
  workflow rather than passed by the wrapper, so it is already adopter-
  independent and needs no new adopter action. Verified against the stage
  workflows, not assumed from the issue.
- #744's `record-stage` output is the carrier and has merged (`ae4caf20`;
  `wing-commander-inspected-run-identity/action.yml:151-156`, `285-318`).
  This feature consumes it as the record half of the resolved identity
  (FR-003) rather than establishing a second one.
- Reference display names remain in the example wrappers in
  `docs/adoption.md` — this feature stops them from being *required*, it
  does not rename anything.
- Scope is the watchdog's identification of the *inspected* stage. Two
  related name dependencies are deliberately out of scope and are recorded
  here so the plan does not have to rediscover them: the watchdog's
  discovery of its own prior runs by workflow name (`gh run list
  --workflow`), which is a run-discovery concern rather than an
  inspected-stage concern, and any adopter-facing trigger configuration,
  which is wrapper-owned per constitution VII.
- Behaviour for this repository's own reference-named wrappers must not
  change; every option above is evaluated against that.
- Because this behaviour only runs in Actions, it is proven after merge by
  re-driving one watchdog run and recording the evidence, per CLAUDE.md.
