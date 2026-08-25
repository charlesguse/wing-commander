# Feature Specification: Durable Agent Run Metrics — Emit a Record, Persist It Beyond Artifact Retention, and Roll It Up per Specification

**Feature Branch**: `043-durable-metrics-record`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "Follow-up to #16: metrics are rendered but never stored — no per-feature rollup, no durable trend record. Spec 009 shipped tier 1 of #16 (per-run step-summary table, `wing-commander-metrics-summary`). Tiers 2 and 3 were deferred by the `Q1: A` clarification answer on #16 and no issue ever carried them forward. This is that issue. **Where cost data lives today**: the only durable copy of any agent run's cost is the raw transcript artifact — every agent step uploads `claude-execution-output.json`, and `wing-commander-metrics-summary` reads `.total_cost_usd`, `.num_turns`, `.duration_ms`, `.usage`, `.modelUsage` out of that file's terminal `result` record, formats one Markdown table row into `$GITHUB_STEP_SUMMARY`, and discards the values. Consequences: nothing is queryable (there is no API for step-summary content); the data expires (no upload site sets `retention-days`, so every transcript inherits the repo default of 90 days — as of 2026-07-28, 453 transcript artifacts, 0 expired, oldest 2026-07-05, first expiries 2026-10-03, and raising `retention-days` only affects future uploads); no aggregate exists at any level, so every tuning decision for model tiering (constitution II), the iteration cap, and `--max-turns` budgets has come from one or two remembered runs. **What I want**: Tier 2 — per-feature rollup, a specification's cumulative spend legible from its lifecycle issue alone (constitution III), requiring #16's Q2 (rolling table edited in place, a compact line appended to each stage's status comment, or both). Tier 3 — durable trend record, one structured entry per agent run (stage, spec, model, turns, tokens, cost, outcome) appended to a durable GitHub-native location, requiring #16's Q3. The two are independent and could ship separately; tier 3 is the one that fixes the retention bleed, so I'd rather it went first if only one gets built. **Store options for tier 3**: A — dedicated `metrics` branch, one JSON line per run: permanent, queryable via git/contents API, needs a write path that never disturbs stage branches, and 14 agent steps across concurrent specs means push contention and a retry-on-reject loop (cf. spec 013's serialization work); touches no branch the pipeline builds from and needs no constitutional carve-out. B — a `metrics.json` artifact per run alongside the existing transcript: retention-bound (90d default, 400d max), not queryable without one download + unzip per run, but the cheapest possible change since the composite action already extracts every field and just needs to normalize them into a record and upload. C — committed data file on `main` via PR: permanent and queryable, but conflicts with constitution V (humans merge every PR into `main`, the bot never merges to `main`) — at ~14 agent runs per feature that means either a human merging 14 data PRs per feature or an amendment to V, and every data commit to `main` makes every open spec branch stale, which the rebase stage then chases. Worth knowing for anyone evaluating B: GitHub artifacts have no metadata fields — `upload-artifact@v4` accepts only name, path, if-no-files-found, retention-days, compression-level, overwrite, include-hidden-files, and the list API returns only id, name, size_in_bytes, expired, created_at, expires_at, digest, and a workflow_run stub. There is nowhere to attach `{\"cost_usd\": 0.42}` that the API will index; the artifact name is the only queryable surface, so encoding headline numbers into it is the only zero-download query path — a stringly-typed schema with no versioning, and v4 rejects `\" : < > | * ? \\ /` in names. Why not C, given that a static page would be easier to build against it: Pages can be sourced from any branch, not just `main` or `main/docs`, so putting a future page on the metrics branch alongside the data gives the same same-origin fetch with no CORS, no 60/hr unauthenticated Contents API limit, no commit noise on `main`, and no conflict with constitution V. Pages is not enabled on this repository today. My leaning: B + A together, with any future Pages site sourced from the metrics branch. **Layer split (constitution VII)**: `.github/actions/**` is published-contract layer and is currently clean. 'Emit the record' and 'commit the record' fall on opposite sides, but the commit itself splits further — the decision and destination (persist at all? which branch, which path?) are consuming-instrument concerns, since a published stage that unconditionally pushes a `metrics` branch writes project content into every adopter's repository, which VI forbids as much as VII does; but the commit mechanism (fetch the run's artifacts, normalize, append, retry the push when concurrency rejects it) is identical for every adopter and genuinely fiddly, and pushing that into wrappers violates VII from the other direction since VII defines wrappers as triggers and gates only. Three pieces, not two: stage emits a normalized `metrics.json` artifact (published — always on, no configuration); collector fetch → normalize → append → push with destination taken as inputs (published — mechanism only, reads no ambient state); wrapper supplies the trigger (`workflow_run`) and the destination (consuming instrument). The stage never decides whether to persist. The collector never chooses where. The wrapper stays thin. One consequence worth stating plainly: the record's field names are the contract surface — once a page or any other consumer parses these records, the schema is a compatibility promise across a store that cannot be rewritten in place, so it needs a `schema_version` from the first record written, not retrofitted. Note that `.github/actions/**` is not covered by release.yml's Gate 1b, which greps eight workflow files and does not look at the actions directory at all (#149); nothing mechanical would catch a `vars.` appearing in the collector, and PR review is the only check until #149 lands. **Out of scope**: any dashboard or visualization, hosted or otherwise — this issue is about capturing and storing the data only; the store must not preclude a static page later, but no page is built here and Pages is not enabled as part of this work. Also out of scope: changing what `wing-commander-metrics-summary` renders to the step summary today. **Open decisions this issue needs answered**: (1) which tiers are committed — 2, 3, or both? (2) tier 2 rollup form (#16 Q2): rolling table, per-comment line, or both? (3) tier 3 store (#16 Q3): A, B, C, or a combination? (current leaning B + A; C would need constitution V amended first). (4) should the retention bleed be mitigated independently by setting `retention-days` on the 14 existing transcript uploads regardless of which tier ships? — this only affects future uploads, and rescuing the 453 artifacts that already exist is a one-time extraction script that needs no spec and should not wait on this issue's schedule; first expiries land 2026-10-03. (5) what is in the v1 record schema, and is `schema_version` in it from the first write?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every agent run emits a machine-readable record of what it cost (Priority: P1)

Every agent step in the pipeline — in this repository and in any repository that adopts the published stages — finishes by producing a normalized, structured record of that run: which stage it was, which specification it belonged to, which model it used, how many turns it took, how many tokens it consumed, what it cost, and how it ended. The record is produced whether or not anyone has arranged to keep it, and it is produced from the same values that already go into the run summary a maintainer reads.

**Why this priority**: This is the foundation both remaining tiers stand on, and it is the piece with no configuration and no destination to argue about. Today the numbers exist for the length of one `printf` and are then discarded; the only durable copy is a raw transcript nobody can query. Until a record exists in a defined shape, there is nothing for any store to store and nothing for any rollup to sum. It is also the cheapest slice: everything it needs is already extracted for the step summary.

**Independent Test**: Run any pipeline stage that invokes an agent and confirm a structured record is produced alongside the existing transcript, that it carries every field of the defined schema, that its values agree with what the run summary rendered for the same run, and that a run whose transcript is missing or unparseable still produces a record marked as such rather than producing nothing.

**Acceptance Scenarios**:

1. **Given** any agent step that renders a run summary today, **When** it completes, **Then** a structured metrics record for that run is produced, carrying the schema version, the stage, the specification identity, the model, the turns used and the budget they were measured against, the token counts, the cost, how the run ended, and a per-model breakdown of tokens and cost.
2. **Given** a run that used more than one model, **When** its record is read, **Then** the per-model breakdown carries one entry per model used, and its entries sum to the record's own token and cost totals; a single-model run carries a breakdown with one entry rather than none.
3. **Given** the same run, **When** the record and the rendered summary are compared, **Then** every value they share is the same value, derived once rather than twice.
4. **Given** a run whose transcript is missing, empty, or unparseable, **When** the step completes, **Then** a record is still produced, its unavailable fields are explicitly marked unavailable rather than guessed or omitted, and the step does not fail.
5. **Given** a job containing more than one agent step, **When** it completes, **Then** each agent step has its own distinct record, and no record overwrites another.
6. **Given** an adopting repository that has arranged no storage at all, **When** its stages run, **Then** records are still produced, nothing is pushed to any branch of that repository, and no configuration was required to get either behaviour.
7. **Given** the record's field names, **When** the first record is ever written, **Then** it already carries a schema version — the version is not added later to records that lack one.
8. **Given** a reader of the store and a record whose schema version it does not recognize, **When** it reads that record, **Then** it retains and skips the record rather than dropping, rewriting, or failing on it.

---

### User Story 2 - The record outlives the artifact that carried it (Priority: P1)

The pipeline's cost history accumulates somewhere permanent and queryable. A maintainer asking "what has this pipeline spent, per stage, over the last six months" reads it out of a durable store without downloading anything, and the answer does not get shorter every day as artifacts expire. The store is written by many concurrent runs without any of them losing a record or disturbing a branch the pipeline builds from.

**Why this priority**: This is the tier that fixes the bleed. Every transcript this repository has ever produced inherits the repository's default retention; nothing has expired yet, but the first expiries are dated and close, and there is no API to extend an artifact's expiry once it is created. Equal priority to story 1 because story 1 without story 2 produces a better-shaped copy of the same disappearing data. The requester stated plainly that if only one tier gets built, this is the one.

**Independent Test**: Drive several concurrent pipeline runs, then read the store directly — without downloading any artifact — and confirm one entry exists per agent run, that entries from concurrent runs are all present, that no entry was overwritten or lost, and that no branch the pipeline builds from was modified.

**Acceptance Scenarios**:

1. **Given** a completed pipeline run containing agent steps, **When** persistence is arranged for that repository, **Then** one entry per agent run appears in the durable store, and each entry is readable without downloading or unpacking an artifact.
2. **Given** several pipeline runs for different specifications finishing at overlapping times, **When** they are all persisted, **Then** every record from every run is present in the store and none has been overwritten, reordered destructively, or dropped.
3. **Given** a write to the store that is rejected because another run wrote first, **When** the persistence step handles it, **Then** it retries against the updated state and the earlier run's records survive intact.
4. **Given** persistence running repeatedly for the same pipeline run, **When** it completes more than once, **Then** the store contains one entry per agent run, not duplicates.
5. **Given** persistence failing outright — the destination is unreachable, the retries are exhausted, the records cannot be fetched — **When** it fails, **Then** the pipeline run whose metrics were being persisted is unaffected, and the failure is visible rather than silent.
6. **Given** the store after any number of writes, **When** the branches the pipeline builds from are inspected, **Then** none of them has been modified by persistence, and nothing has been merged into the repository's default branch by the bot.
7. **Given** a repository that has never persisted before, **When** the first record is written, **Then** the destination is created and the write succeeds without a human preparing it by hand.
8. **Given** the store's contents, **When** a consumer reads them, **Then** the entries are in a form a later static page could fetch directly from where they live, without this feature building or enabling any page.

---

### User Story 3 - A specification's total spend is legible from its lifecycle issue (Priority: P2)

Someone reading a specification's lifecycle issue can see what that specification has cost so far — across intake, clarification, planning, task generation, every implementation cycle, convergence, finalization, and any rework — without opening a single workflow run. They see it in two places that agree: a compact cost line on each stage's own status comment, where that run's detail belongs, and one rolling cumulative summary that carries the running total so nobody sums a thread by eye.

**Why this priority**: This is what the constitution's "the lifecycle of a spec is legible from its original issue alone" asks for, and it is the tier a human actually reads. It is below the two P1 stories because it is a presentation of data that must first exist and first survive; building it on top of numbers that disappear in ninety days would mean building it twice.

**Independent Test**: Take one specification through several stages and confirm that each stage's status comment carries that run's cost line, that one rolling summary on the issue shows a cumulative figure covering every agent run that specification has had, that the two agree and the figure changes as stages complete, and that reading either requires opening no workflow run.

**Acceptance Scenarios**:

1. **Given** a specification that has completed several stages, **When** its lifecycle issue is read, **Then** the cumulative spend across all of that specification's agent runs is visible in one rolling summary, and each stage's status comment carries a compact cost line for its own run.
2. **Given** the same specification, **When** a further stage completes, **Then** the figure reflects the new run without a human asking for it.
3. **Given** both surfaces for the same run, **When** they are compared, **Then** they agree, because both are derived from the same records.
4. **Given** a rollup update that runs more than once for the same agent run, **When** the issue is read, **Then** that run's cost line appears once and exactly one rolling summary exists — no duplicate line, no second summary.
5. **Given** a rolling summary carrying human text around it, **When** it is updated, **Then** the machine-owned region is regenerated and its per-run history extended without rewriting earlier entries, and the human text outside the region is untouched.
6. **Given** a specification with several implementation cycles and a retry, **When** the rollup is read, **Then** every one of those runs is counted exactly once.
7. **Given** a specification whose runs include one with unavailable metrics, **When** the rollup is read, **Then** the rollup states that it is incomplete and why, rather than silently under-reporting.
8. **Given** a specification with many stages, **When** the rollup is read, **Then** it does not make the lifecycle issue harder to follow than it is today — no comment is added per agent run beyond the stage status comments the pipeline already posts.
9. **Given** the rollup, **When** it is produced, **Then** it is derived from the same records story 1 defines, not from a second, separately-maintained tally.

---

### User Story 4 - Future transcripts stop expiring on a ninety-day clock (Priority: P2)

The raw transcripts that every agent step uploads stop being the shortest-lived copy of the pipeline's history. Every transcript upload declares how long it is kept, rather than silently inheriting a repository default that nobody chose.

**Why this priority**: It is a small, independent mitigation that reduces the cost of any later gap in the durable store, and it is the only lever that touches transcripts rather than derived records. It is below the P1 stories because it cannot rescue anything that already exists and it does not make anything queryable — it only buys time. The requester asked for it regardless of which tier ships.

**Independent Test**: Inspect every transcript upload the pipeline performs and confirm each one declares a retention period, and that adding a new agent step without declaring one fails a check.

**Acceptance Scenarios**:

1. **Given** every agent step that uploads an execution transcript, **When** it uploads, **Then** the retention period is declared explicitly as 90 days rather than inherited from a repository default.
2. **Given** a new agent step added later that uploads a transcript without declaring a retention period, **When** the repository's checks run, **Then** they fail and name the site.
3. **Given** an adopting repository, **When** it takes this change, **Then** it receives the declared retention without editing a wrapper workflow.
4. **Given** transcripts uploaded before this change, **When** it ships, **Then** their expiry is unchanged — this feature does not claim to have rescued them.

---

### User Story 5 - The layer split and every failure branch are enforced by checks, not by review (Priority: P2)

Before this ships, checks assert that the emitting stage reads no ambient repository state, that the persistence mechanism decides nothing about destination, that the record's schema matches what is written, and that each failure path this feature adds has been driven against a checked-in fixture. Regressing any of them fails a check rather than waiting for a reviewer to notice.

**Why this priority**: Two standing rules make this non-optional. The published-contract directory this feature extends is not covered by the existing layer-split check — nothing mechanical would catch ambient state appearing in the new mechanism — and the repository's rule is that every shipped failure branch is exercised by a fixture rather than demonstrated once during development. Below the P1 stories because it protects the feature rather than being the feature.

**Independent Test**: Reintroduce each defect in turn — ambient state read by the published pieces, a destination decided by the mechanism instead of supplied to it, a record written that does not match the declared schema, a transcript upload with no declared retention — and confirm each one turns a check red; run the checks against the correct tree and confirm they pass.

**Acceptance Scenarios**:

1. **Given** the published emitting and persisting pieces, **When** the checks run, **Then** they fail if either reads repository-ambient state or event state rather than declared inputs.
2. **Given** a record written by the pipeline, **When** the checks run, **Then** they fail if it does not conform to the declared schema for its stated schema version.
3. **Given** a fixture where a write is rejected by contention, **When** the checks run, **Then** they assert the retry-and-preserve behaviour rather than relying on a live race having been observed once.
4. **Given** a fixture where the transcript is unparseable, **When** the checks run, **Then** they assert a record is still produced with its unavailable fields marked.
5. **Given** the new coverage disabled, removed, or made unreachable, **When** the checks run, **Then** a check fails — the coverage is wired into the same registry that proves every other gate is run.
6. **Given** the checks, **When** they are run locally, **Then** they run the same subject with the same arguments as they do in continuous integration.

---

### Edge Cases

- **Two pipeline runs try to write to the store at the same moment.** This is the ordinary case, not the exception: concurrent specifications are supported and one feature produces on the order of a dozen agent runs. Neither write may be lost, and the loser of the race must retry against what the winner wrote rather than overwrite it.
- **The retry loop exhausts itself under sustained contention.** Persistence must give up rather than spin forever, and must say loudly that specific records were not persisted — a silent give-up is indistinguishable from a run that had no metrics.
- **Persistence runs twice for the same pipeline run** — a re-run, a retried job, a duplicated trigger. The store is append-only and cannot be rewritten in place, so the second pass must recognize what is already there rather than append a second copy.
- **Persistence runs for a pipeline run that contained no agent steps.** Nothing is appended and nothing fails.
- **The records a persistence run wants have already expired**, because the run being persisted is older than the retention window. It reports what it could not find rather than writing partial entries that look complete.
- **A pipeline run is cancelled mid-way.** The agent steps that completed still have records; the ones that never ran have none. The store must not imply the cancelled steps cost nothing — an absent record and a zero-cost record are different facts.
- **The transcript is missing, empty, or unparseable.** The existing behaviour for the rendered summary is to degrade to "metrics unavailable" and never fail the job; the record must degrade the same way, with unavailable fields marked as unavailable rather than defaulted to zero, because a zero is indistinguishable from a free run when it is later summed.
- **The turn count the record carries is the counted one, not the reported one.** The two diverge upward by a known factor in this repository's own history, and a store that mixes them is a store whose trend line means nothing.
- **A run's stage or specification identity cannot be determined** — a stage that is not attached to a specification, or a run triggered outside the normal lifecycle. The record still exists and states that the identity is absent rather than inventing one.
- **An adopter takes the published pieces but wants no persistence at all.** They must get the emitted records with no configuration and no writes to their repository, and must never find that adopting a stage created a branch in their repository they did not ask for.
- **An adopter wants persistence somewhere other than where this repository puts it.** The destination is supplied to the mechanism, so a different destination requires no change to any published piece.
- **The destination for the store does not exist yet.** The first write creates it; a human is not required to prepare it, and the creation path is exercised by coverage rather than by having happened once.
- **The store's destination is protected, unwritable, or has been deleted.** Persistence fails loudly and the pipeline run it was reporting on is unaffected — no stage may fail because its metrics could not be filed.
- **The schema needs a new field later.** The store cannot be rewritten in place, so readers will see both old and new records; the version each record carries is how a reader tells them apart. The rules are decided, not left to be discovered: additive within a version, a new version for anything else, and a reader that meets an unknown version retains and skips that record rather than dropping it.
- **A reader meets a record written by a newer version of the pipeline than it knows.** It keeps the record and skips it. Dropping it would silently shrink a history that the store exists to keep, and failing on it would let one future record break every reader.
- **A future consumer parses these records.** The field names become a compatibility surface at that moment. This feature is the only chance to choose them deliberately.
- **The count of transcript upload sites drifts.** The requester's inventory named fourteen; the measured count in this checkout is sixteen across twelve workflow files, including three sites in the auto-update stage and an implementation progress step the inventory omitted. Any requirement expressed as a hardcoded count is a requirement that will silently stop covering new sites — coverage must be expressed over "every site that uploads a transcript", discovered rather than enumerated.
- **Growth of the store.** One entry per agent run, on the order of a dozen or more per specification, forever. The store's form must remain readable and appendable as it grows, and must not require rewriting earlier content to add to it.

## Requirements *(mandatory)*

### Functional Requirements

#### Emitting the record (published, always on)

- **FR-001**: Every agent step that renders a run summary today MUST also emit a structured metrics record for that run.
- **FR-002**: The record MUST be emitted with no configuration by the consuming repository, and its emission MUST NOT depend on whether that repository has arranged any storage.
- **FR-003**: Emitting the record MUST NOT write to any branch, issue, or other durable location in the consuming repository. Emission produces the record; it does not decide its fate.
- **FR-004**: The record and the rendered run summary MUST derive every value they share from a single extraction, so the two cannot disagree about the same run.
- **FR-005**: The committed v1 record MUST carry: a schema version; the stage the run belongs to; the specification identity, where one exists; the model the caller declared; the turns used, counted the way the pipeline's turn budget counts them, together with the intended budget and the enforced ceiling they were measured against; token counts including cache reads and cache creation; the cost; the wall-clock duration; how the run ended; enough identity to tie the record back to the workflow run and job that produced it; and a nested per-model breakdown of tokens and cost. Nothing in this set is dropped and no name in it is changed within schema version 1.
- **FR-005a**: The per-model breakdown MUST be present on every record, carrying one entry per model the run actually used — a single entry when the run used one model — so that per-model trend analysis needs no second pass over the transcripts. It is the only nested part of the record; every other field is flat.
- **FR-006**: The record MUST carry its schema version from the first record ever written. Retrofitting a version onto records that lack one is not an acceptable outcome.
- **FR-007**: A field whose value is unavailable MUST be marked unavailable in the record. It MUST NOT be omitted silently, defaulted to zero, or guessed — an unavailable cost and a zero cost are different facts and are summed differently.
- **FR-008**: The turn figure the record carries MUST be the counted turn total the pipeline's budget is measured against, not the transcript's self-reported turn count. Where both are carried, the record MUST make clear which is which.
- **FR-009**: A missing, empty, or unparseable transcript MUST still produce a record, MUST NOT fail the emitting step, and MUST NOT fail the job — matching the degradation the rendered summary already guarantees.
- **FR-010**: A job containing more than one agent step MUST produce one distinct record per agent step, with none overwriting another.
- **FR-011**: What the run summary renders to the step summary today MUST NOT change. This feature adds a record; it does not restyle the existing table.

#### Persisting the record (published mechanism, consumer-chosen destination)

- **FR-012**: The pipeline MUST be able to accumulate emitted records into a durable store that is not bound by artifact retention and that is readable without downloading or unpacking an artifact.
- **FR-013**: The persistence mechanism MUST take its destination as a declared input. It MUST NOT choose, default to, or infer a destination, and MUST NOT read repository-ambient state or event state to determine one.
- **FR-014**: The decision to persist at all, the trigger that starts persistence, and the destination MUST live in the consuming repository's own configuration, not in any published piece.
- **FR-015**: Persistence MUST NOT modify any branch the pipeline builds from, MUST NOT commit to the repository's default branch, and MUST NOT approve or merge anything.
- **FR-016**: Concurrent persistence MUST NOT lose records. A write rejected because another writer went first MUST be retried against the updated state, preserving the other writer's records.
- **FR-017**: The retry MUST be bounded. On exhaustion, persistence MUST report which records were not persisted, naming them specifically enough for a human to recover them while the artifacts still exist.
- **FR-018**: Persistence MUST be idempotent per agent run: running it more than once for the same pipeline run MUST leave one entry per agent run, not duplicates.
- **FR-019**: A persistence failure of any kind MUST NOT fail, retry, or otherwise disturb the pipeline run whose metrics it was persisting, and MUST NOT be silent.
- **FR-020**: Persistence MUST create the destination when it does not yet exist, without a human preparing it by hand.
- **FR-021**: A pipeline run with no agent steps MUST result in no entries and no failure.
- **FR-022**: Records that cannot be retrieved — expired, deleted, never uploaded — MUST be reported as not retrieved rather than persisted as partial entries indistinguishable from complete ones.
- **FR-023**: The store MUST be appendable without rewriting earlier content, and MUST remain readable as it grows at a rate of one entry per agent run indefinitely.
- **FR-024**: The store's contents MUST be directly fetchable from where they live, so that a static page could later be added alongside them without moving the data. No page is built, enabled, or configured by this feature.
- **FR-025**: The schema's compatibility rules are settled, and MUST be stated alongside the schema itself rather than left to a reader to infer: (a) **within a schema version, changes are additive only** — a field may be added, but no field of that version may be removed, renamed, or have its meaning or units changed; (b) a reader of a record may therefore assume every field of that record's declared version is present, with any unavailable value explicitly marked as unavailable per FR-007 rather than absent; (c) any change that is not purely additive requires a new schema version; (d) **a reader encountering a schema version it does not know MUST retain and skip that record** — it MUST NOT drop it, rewrite it, or fail on it. The store cannot be rewritten in place, so both old and new records will be read together.

#### Rolling up per specification

- **FR-026**: Both tiers are committed by this specification — the durable trend record and the per-specification rollup — with the durable store sequenced first, so the rollup is built on records that already exist and already survive rather than on data that expires. A specification's cumulative spend across all of its agent runs MUST be legible from its lifecycle issue without opening any workflow run.
- **FR-027**: The rollup MUST update as further stages complete, without a human requesting it.
- **FR-028**: The rollup MUST count every agent run of that specification exactly once, including every implementation cycle, retry, convergence pass, and rework run.
- **FR-029**: The rollup MUST be derived from the same records FR-001 defines, never from a separately maintained tally.
- **FR-030**: A rollup that is incomplete — because a run's metrics were unavailable or unretrievable — MUST say so rather than present an under-reported figure as complete.
- **FR-031**: The rollup MUST take both forms: a compact cost line for that run appended to the status comment the stage already posts, and one rolling cumulative summary for the specification kept current in place. Per-run detail sits where the run happened; the running total sits in one place a reader does not have to sum by eye.
- **FR-031a**: The rolling cumulative summary MUST live in a machine-owned region whose ownership is evident to a reader, following the pattern this repository already established for machine-owned regions: the region is regenerated on each update, the per-run history inside it is appended without rewriting earlier entries, and human text outside the region is preserved untouched across every update.
- **FR-031b**: The two surfaces MUST be derived from the same records and MUST NOT disagree about any run they both describe. Updating the rollup MUST be idempotent: however many times it runs for the same agent run, the per-stage line appears once and exactly one rolling summary exists for the specification.
- **FR-031c**: The rollup MUST NOT make the lifecycle issue materially harder to read than it is today: it adds no comment per agent run beyond the stage status comments the pipeline already posts, and no second rolling summary.

#### Stopping the retention bleed for future transcripts

- **FR-032**: Every site that uploads an execution transcript MUST declare its retention period explicitly rather than inheriting a repository default. The declared value is **90 days** — today's inherited default, made explicit and chosen rather than assumed. It is deliberately not the platform maximum: the durable store, not the transcript artifact, is the long-lived copy, and holding sixteen transcripts per run for 400 days is a storage cost this feature exists to make unnecessary.
- **FR-033**: A transcript upload site added later without a declared retention period MUST fail a check that names the site. The check MUST discover the sites rather than compare against a hardcoded count, because the inventory drifts.
- **FR-034**: The declared retention MUST reach adopters without any wrapper edit.
- **FR-035**: This feature MUST NOT claim to have preserved transcripts uploaded before it shipped; their expiry is unchanged and rescuing them is separate work.

#### Not regressing

- **FR-036**: The declared inputs, outputs, and secrets of every affected published piece MUST NOT be removed or renamed. Any addition MUST be optional with a default that preserves current behaviour, and no adopter may need to edit a wrapper workflow to receive any part of this feature.
- **FR-037**: Every path that is quiet today MUST remain quiet. A stage that renders a summary and does nothing else MUST continue to look the same to a maintainer reading its run.
- **FR-038**: No published piece this feature adds or changes may read repository-ambient state or event state, and a check MUST fail if one does. The existing layer-split check does not cover the directory these pieces live in, so this coverage MUST be made to reach them rather than assumed.
- **FR-039**: Executable coverage MUST exercise, against checked-in fixtures: a record emitted from a healthy transcript; a record emitted from a missing, empty, and unparseable transcript; a job with several agent steps producing several distinct records; a write rejected by contention and retried without loss; a retry loop exhausted, reporting unpersisted records; a repeated persistence pass producing no duplicates; a persistence failure leaving the reported-on pipeline run unaffected; a first write creating a destination that did not exist; a pipeline run with no agent steps; a record that does not conform to its declared schema version being rejected; a record carrying a schema version the reader does not know being retained and skipped rather than dropped; a multi-model run whose per-model breakdown sums to its own totals; and a rollup update repeated for the same agent run leaving one cost line and one rolling summary.
- **FR-040**: The new coverage MUST be wired into the repository's existing gate registry, so coverage that stops being run is itself a failure, and MUST run the same subject with the same arguments locally as it does in continuous integration.
- **FR-041**: Whether a record is well-formed enough to be written MUST be decided by deterministic code, not by an agent's judgement — a durable, un-rewritable store is exactly the kind of write that cannot rely on a prompt having been followed.

### Key Entities

- **Agent run metrics record**: the structured, versioned account of one agent invocation — stage, specification, model, turns against budget and ceiling, tokens, cost, duration, outcome, the per-model breakdown of tokens and cost, and the run and job identity that produced it. The unit of everything else here. Its field names are its contract.
- **Schema version**: the number every record carries from the first write, and the only thing a reader has to distinguish records written under different field sets in a store that cannot be rewritten in place. Version 1 is additive-only; an unknown version is retained and skipped.
- **Emission**: the always-on, unconfigured production of a record by the stage that ran the agent. It produces; it does not decide where the record goes or whether it is kept.
- **Persistence mechanism**: the fetch, normalize, append, and retry-on-contention machinery. Identical for every adopter, and therefore published — but it takes its destination as an input and chooses nothing about it.
- **Destination**: where a consuming repository has decided its records accumulate. It belongs to the consuming repository, is supplied to the mechanism, and is never inferred.
- **Durable store**: the accumulated records at that destination. Append-only, permanent, readable without unpacking anything, and not a branch the pipeline builds from.
- **Rollup**: the per-specification presentation on the lifecycle issue, derived from the records rather than tallied separately, in two surfaces — a per-run cost line on each stage's existing status comment, and one rolling cumulative summary in a machine-owned region.
- **Transcript**: the raw execution output every agent step already uploads. It remains retention-bound; the record is what outlives it.

## Out of Scope

- **Any dashboard, page, or visualization**, hosted or otherwise. The store must not preclude one later — that is the only reason the store's readability is a requirement — but none is built, and no hosting is enabled or configured by this feature.
- **Changing what the existing run summary renders** to the step summary. The rendered table is unchanged.
- **Rescuing the transcripts that already exist.** Extracting the artifacts uploaded before this feature ships is a one-time exercise that does not depend on this specification and must not wait for it.
- **Amending the constitution** to permit the bot to commit data to the default branch. The store is chosen so that no amendment is needed.
- **Cost accounting for anything that is not an agent run** — runner minutes, storage, non-agent steps.
- **Budget enforcement, alerting, or throttling** based on the stored data. This feature captures and stores; acting on the numbers is a separate decision informed by having them.
- **Retroactively changing the schema of records already written.** The store cannot be rewritten in place; that constraint is why the version exists.
- **Choosing a destination for adopting repositories.** Each adopter decides its own, or decides not to persist at all.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of agent runs that render a run summary today also produce a structured record — up from none.
- **SC-002**: Every value the record and the rendered summary share agrees for 100% of runs, verified against fixtures rather than by inspection.
- **SC-003**: A maintainer can answer "what has this pipeline spent, by stage, over an arbitrary date range" by reading the store directly, downloading zero artifacts — down from one download and unpack per run, and from no answer at all once artifacts expire.
- **SC-004**: Across concurrent pipeline runs, zero records are lost to write contention, demonstrated against a fixture that drives the rejected-write path rather than by observing a live race.
- **SC-005**: Repeated persistence for the same pipeline run produces zero duplicate entries.
- **SC-006**: Zero pipeline runs fail, stall, or change behaviour because persistence failed; zero persistence failures are silent.
- **SC-007**: Zero branches the pipeline builds from are modified by persistence, and zero commits are made by the bot to the default branch.
- **SC-008**: An adopting repository that arranges no storage receives records with zero configuration and zero writes to its repository.
- **SC-009**: A specification's cumulative spend is readable from its lifecycle issue in one place, with zero workflow runs opened — down from one run opened per stage today — while each stage's own run cost is readable from the status comment that stage already posts. The two surfaces disagree on zero runs, and repeated updates produce zero duplicate cost lines and zero second summaries.
- **SC-010**: Every transcript upload site declares a retention period of 90 days — measured over the sites discovered in the tree, not a fixed list — up from zero of the sixteen sites in this checkout.
- **SC-011**: Adding a transcript upload site without a declared retention period, or a published piece that reads ambient state, or a record that does not match its declared schema, each fails a check; disabling the new coverage fails a check.
- **SC-012**: Every failure branch this feature ships is exercised by a checked-in fixture, with zero branches whose only evidence is a manual demonstration during development.
- **SC-013**: The change reaches adopters with zero wrapper edits, and zero declared inputs, outputs, or secrets of affected published pieces are removed or renamed.
- **SC-014**: 100% of records carry a schema version, including the first one ever written, and 100% carry a per-model breakdown, including single-model runs.
- **SC-015**: A reader given a record of an unknown schema version retains it and skips it in 100% of cases — zero records dropped, zero rewritten, zero reader failures.

## Assumptions

- **The store is a dedicated location that no pipeline branch builds from, and records are also carried as an artifact alongside each run's transcript** — the requester's stated leaning of "B + A together". The artifact makes the data machine-readable immediately at negligible cost since every field is already extracted; the dedicated store is what survives retention and is queryable. Committing data to the default branch is excluded outright: it conflicts with the principle that humans merge every pull request into the default branch and the bot never does, and every data commit would make every open specification branch stale for the rebase stage to chase.
- **A future static page, if one is ever built, is served from wherever the store lives**, which is why the store's direct fetchability is a requirement here even though no page is in scope. This costs nothing now and removes the only argument for committing data to the default branch later.
- **The retention declaration on transcript uploads ships with this feature** rather than waiting for a tier decision, because the requester asked for it independently and its first deadline is fixed. The declared value is 90 days: today's inherited default, made explicit and chosen. The point is not to keep transcripts longer — the durable store is what carries the history now — but to stop the value being a repository default nobody set, and to avoid paying to hold sixteen transcripts per run for 400 days for data the store already keeps.
- **The one-time extraction of already-uploaded transcripts is separate work** on its own schedule, as the requester stated. Nothing in this feature depends on it and nothing in it should be delayed by this feature's review cycle.
- **The three-piece layer split is settled**: the stage emits with no configuration, the mechanism persists with its destination supplied, and the consuming repository's own configuration supplies the trigger and the destination. This is a consequence of the standing two-interfaces and portability rules rather than an open choice.
- **The emitted record's fields are drawn from what is already extracted for the rendered summary**, plus the run and job identity needed to trace a record back. Nothing new needs to be measured; the fields exist and are discarded.
- **The counted turn total, not the transcript's self-reported one, is the figure the record carries.** The two are known to diverge upward in this repository's history, and a trend line built on the wrong counter is worse than no trend line.
- **"One entry per agent run" means per agent invocation, not per workflow run.** A job with several agent steps produces several records, and an implementation cycle plus its retry plus its convergence pass are three runs, not one.
- **The measured inventory of transcript upload sites in this checkout is sixteen sites across twelve workflow files**, not the fourteen the request names; the difference is three sites in the auto-update stage and an implementation progress step. The specification therefore requires coverage that discovers sites rather than counts them.
- **Persistence is triggered after the pipeline run it reports on has finished**, so it can collect that run's records together and never blocks or slows the run itself.
- **The retention bleed's deadline is real but not immediate.** As of the request, nothing had expired and the first expiries were roughly ten weeks out. This feature is urgent enough to sequence the durable store first, and not so urgent that it should ship without the checks that keep it honest.
