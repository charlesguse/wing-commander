# Phase 0 Research: Durable Agent Run Metrics

spec.md carries no `[NEEDS CLARIFICATION]` markers — its own Assumptions
section already resolved the store choice (B+A), the tier scope (both,
tier 3 first), and the retention value (90 days, ships regardless of
tier). What remains for this phase is the mechanical design: how the
three published pieces spec.md's layer-split paragraph names (emission,
persistence mechanism, wrapper) are actually built against this
repository's existing composites, gates, and wrapper conventions, and
how the two tier-2 rollup surfaces attach to code that already exists.
Each item below is a plan-level decision, not a spec clarification —
flagged where a reasonable alternative existed and was rejected.

## R1: Emission extends `wing-commander-metrics-summary` in place, not a new composite

**Decision**: Add the record-emitting logic to the existing
`.github/actions/wing-commander-metrics-summary/action.yml` rather than
writing a second composite that re-parses the transcript.

**Rationale**: FR-004 requires the record and the rendered summary to
"derive every value they share from a single extraction, so the two
cannot disagree." The action already does the one extraction this
feature needs (`.total_cost_usd`, `.usage`, `.modelUsage`,
`count-turns.sh`'s counted/reported turns, the `error_max_turns`
subtype check). A second composite would need its own copy of that
extraction or a shared script two composites both call — exactly the
"drift risk a second copy would open" that spec 037 named and closed for
turn-counting by extracting `_shared/count-turns.sh`. Extending in place
means the fix for a future extraction bug (there have been several —
`.num_turns` divergence, the both-casing `modelUsage` defense) lands once.

**Alternatives considered**: A new `wing-commander-metrics-record`
composite calling the same `_shared/count-turns.sh` the summary action
already uses — rejected because the *rest* of the extraction
(`total_cost_usd`, `usage`, `modelUsage`, the `error_max_turns` check)
has no shared script today; pulling all of it out would be a larger,
riskier refactor than this feature needs, and the two composites would
still have to agree on field semantics (is a `null` `usage` "zero" or
"unavailable"?) via convention rather than by construction.

## R2: Record file, not just a step output

**Decision**: The action gains a `record-path` input (default
`${{ runner.temp }}/wing-commander-metrics-record.json`, mirroring
`transcript-path`'s existing default pattern) and always writes the
normalized JSON record there. It also exposes the same content as a
`record-json` action output for callers that want it without a file
read (small: one flat-ish JSON object, well under GitHub Actions' step
output size limit).

**Rationale**: FR-003 requires emission to produce the record without
deciding its fate — a file the call site can upload as an artifact (like
the transcript already is) is the natural unit for that hand-off, and
keeps the composite itself free of any `upload-artifact` call (uploading
is the call site's job, same separation the transcript already has:
the composite never uploads anything, callers do).

**Alternatives considered**: Output-only (no file) — rejected because
`upload-artifact`'s `path:` input needs a file, and callers would each
need to redundantly write the output back to disk before uploading it.

## R3: Record upload sites mirror the existing transcript upload sites, 1:1

**Decision**: Each of the ~14 existing `wing-commander-metrics-summary`
call sites (`intake.yml`, `clarify.yml`, `plan.yml` ×2, `tasks.yml` ×2,
`implement.yml` ×3, `finalize.yml`, `cleanup.yml`, `rebase.yml`,
`watchdog.yml` (diagnose), `pr-conversation.yml` ×2 — see data-model.md)
gains a sibling "Upload metrics record" step immediately after its
existing "Upload execution transcript" step, using the artifact name
`metrics-record[-<same suffix the transcript upload already uses>]`
(e.g. `metrics-record-diagnose` beside `claude-execution-output-diagnose`)
and `retention-days: 90` declared explicitly.

**Rationale**: FR-001 scopes emission to "every agent step that invokes
the run-summary action" — call site, not observed rendering (the FR's
own text warns against defining the population by whether a summary
happened to render, citing watchdog #261). The existing transcript
upload sites are already exactly this population, gated
`if: always() && steps.<agent-id>.outcome != 'skipped'` in the same
order (upload transcript, then render summary) — the record upload slots
into that same sequence without changing its gating.

**Alternatives considered**: One shared "upload metrics artifacts" composite
wrapping both `upload-artifact` calls — rejected as unnecessary
abstraction for a two-line mechanical addition repeated at each site;
these sites already tolerate this shape of near-duplication (the
transcript upload step itself is copy-pasted at all 16 sites) and a
wrapping composite would be one more moving part for no behavior gained.

## R4: Retention on the 16 existing transcript sites ships as its own mechanical pass

**Decision**: User Story 4 (declare `retention-days: 90` on all 16
existing transcript `upload-artifact` steps) is implemented as a
same-scope, independently-completable change alongside the record
upload sites from R3 — both touch the same 13-16 files, so they land
together, but User Story 4's fix does not depend on Tier 2 or Tier 3
existing.

**Rationale**: spec.md's Assumptions section states this explicitly
("ships with this feature... because the requester asked for it
independently and its first deadline is fixed"), and FR-032's declared
value (90 days) is what these sites already inherit by default — the
change is additive (an explicit `retention-days: 90` line), not a
behavior change.

## R5: Store layout — one orphan `metrics` branch, one append-only `records.jsonl`

**Decision**: The durable store is a dedicated branch (default name
`metrics`, wrapper-configurable via `WING_COMMANDER_METRICS_BRANCH`)
created as an orphan (no shared history with `main` or any spec branch)
containing a single file, `records.jsonl` (wrapper-configurable path via
`WING_COMMANDER_METRICS_PATH`), one JSON object per line, append-only.

**Rationale**: spec.md's Assumptions section already commits to "B + A
together" (records carried as an artifact per FR-024's fetchability
requirement, R3 above, *and* accumulated in a dedicated store). A single
flat JSONL file is the simplest shape that satisfies FR-023
("appendable without rewriting earlier content, remain readable as it
grows... indefinitely") — `git log`/`git show` on a growing text file is
cheap at the scale this feature describes ("a dozen or more" records per
spec, across dozens of specs is low thousands of lines over the
project's lifetime, not a scale where a flat file becomes a problem),
and FR-024's "directly fetchable... a future static page could fetch
directly from where they live" is satisfied by the raw-content URL of
one file on one branch with no server-side assembly step.

**Alternatives considered**: Sharding per spec (`records/<slug>.jsonl`)
— would make the rollup's per-spec read cheaper (fetch one small file
instead of grep-filtering the whole history) but adds a second thing
every writer must agree on (which shard a record belongs in) and a
directory-listing step the reader doesn't otherwise need; rejected as
premature for a growth rate the flat-file approach already tolerates
comfortably — nothing in spec.md asks for sharding, and the flat file
can still be split later without losing history, since git branches are
just commits. One file per pipeline run (many small files instead of one
growing one) — rejected: FR-023's "appendable" framing and FR-024's
"fetchable from where it lives" both read naturally as one location, and
many small files reintroduce exactly the "one download per run" cost
Tier 3 exists to remove.

## R6: Record key and idempotency

**Decision**: `record_key = "<workflow_run_id>:<job_id>:<step_index>"`,
where `step_index` is the ordinal position of that
`wing-commander-metrics-summary` invocation within its job (0 for the
13 of 14 sites with exactly one agent step per job; 0/1/2 for
`implement.yml`'s cycle/retry/progress sequence, which cannot all run in
the same job execution but are numbered for the general case). This key
is embedded in the record itself (`run.record_key`) and is what both the
persistence collector's de-dup and the rollup's per-run history-line
de-dup key on.

**Rationale**: FR-018 requires persistence to be idempotent per agent
run — running the collector twice for the same pipeline run must not
duplicate entries. `workflow_run_id` + `job_id` is stable for a given
job *execution* (GitHub assigns a new `job_id` only when the job itself
is re-run, which is correctly a new agent invocation with its own real
cost — spec.md's edge case for "a re-run, a retried job" is about the
*collector* being invoked twice against the same already-uploaded
artifacts, not about GitHub-level job reruns, which legitimately produce
new records). `step_index` disambiguates the one job (`implement.yml`)
whose id alone would collide across its own multiple agent steps.

**Alternatives considered**: `run-label` (the existing optional display
string, e.g. `"retry"`, `"progress comment"`) as (part of) the key —
rejected: it is caller-supplied prose meant for a step-summary heading,
not guaranteed unique or stable, and two sites already pass no
`run-label` at all (single-agent-step jobs), so it can't be relied on
uniformly.

## R7: Contention retry algorithm

**Decision**: The persistence composite's append-and-push step retries
up to 8 attempts. Each attempt: fetch the destination branch fresh,
parse its current `records.jsonl` for existing `record_key`s, compute
the subset of this run's records not already present, append only
those, commit, and `git push`. On non-fast-forward rejection, sleep
(`attempt` seconds, capped at 5) and retry from the fetch step. On the
8th consecutive rejection, the step fails, naming every `record_key`
still unwritten in its failure output.

**Rationale**: FR-016 requires a rejected write to retry against the
updated state rather than overwrite it; FR-017 requires the retry to be
bounded and to report exactly which records were not persisted, "naming
them specifically enough for a human to recover them while the artifacts
still exist." Recomputing "already present" from the freshly-fetched
file on every attempt (rather than blindly re-applying the same diff)
makes the loop safe against the case where a concurrent writer's push
included some of the same records this run might otherwise clash with —
though in practice two different pipeline runs never share a
`record_key` (it embeds `workflow_run_id`), so contention here is pure
git-level races between concurrent collector invocations, not logical
duplicate detection. 8 attempts follows this repository's existing
bounded-retry shape (`wing-commander-lifecycle-gate`'s 3 attempts for a
read-only `gh issue view`) scaled up for a write under higher expected
concurrency (spec.md: "14 agent steps across concurrent specs").

**Alternatives considered**: A single fetch-then-retry-forever loop with
no cap — rejected outright by FR-017 ("must give up rather than spin
forever"). Using GitHub's Contents API (`PUT
/repos/.../contents/{path}`) instead of a git push, which natively
returns a 409 on stale SHA — considered, but it round-trips the whole
file's content as a request body on every attempt and offers no
advantage over `git`, which this repository's runners already have
configured with the pipeline's own token; rejected in favor of the tool
already used elsewhere in this repo for branch writes (`rebase.yml`).

## R8: Destination branch creation

**Decision**: Before the first push, the composite runs
`git ls-remote --exit-code origin refs/heads/<destination-branch>`; if
it exits non-zero (branch does not exist), the composite creates an
orphan commit (`git checkout --orphan`, empty tree, one commit
containing the first batch of records) and pushes it as the branch's
first commit. If the branch already exists, the composite fetches it
normally and proceeds as in R7.

**Rationale**: FR-020 requires the destination to be created on first
write "without a human preparing it by hand." An orphan commit keeps the
metrics branch's history free of `main`'s history from the moment it
exists, matching "a dedicated location that no pipeline branch builds
from" (spec.md Assumptions).

## R9: Rollup — per-run line in-band, cumulative summary out-of-band

**Decision**: The two Tier-2 surfaces are produced by different pieces,
at different times:

- **Per-run cost line** (FR-031's first form): emitted synchronously,
  inside the *originating* stage workflow itself (e.g. `plan.yml`),
  immediately after its `wing-commander-metrics-summary` call, using
  that same call's outputs to build one line (e.g. `Cost: $0.42 · 38
  turns · claude-sonnet-5`) appended to the status comment that stage
  already posts. No new cross-run read is needed — the values are
  already in hand in the same job.
- **Rolling cumulative summary** (FR-031's second form): computed
  out-of-band, inside the published persistence workflow, immediately
  after a successful append (R7). The workflow re-reads the just-updated
  `records.jsonl`, filters to this run's `spec_dir`, sums every record
  (using each record's own `identity_available`/field-availability
  markers to decide completeness — FR-030), and writes the result into a
  machine-owned region on the spec's lifecycle issue (R10).

**Rationale**: FR-029 requires the rollup to be "derived from the same
records... never from a separately maintained tally" — recomputing the
cumulative sum fresh from the store on every update (rather than
incrementing a counter someone maintains elsewhere) is what makes that
true by construction, and it makes repeated runs of the same update
naturally idempotent in value (FR-031b) even before the comment-region
de-dup in R10 is applied. The per-run line, by contrast, needs no store
read at all — it is a fact about one run, known the moment that run's
extraction completes — so producing it in-band avoids paying persistence
(and its retry latency) as a dependency for something that doesn't need
cross-run data. This also means a repository that publishes the emission
and persistence layers but never enables persistence still gets correct
per-run cost lines (FR-031's first surface degrades independently of the
second, matching the "each stage's own status comment" half of the
Independent Test).

Posting the rolling summary to the *originating stage's spec's* lifecycle
issue is not a new destination decision requiring wrapper configuration:
the issue number is derived the same way `watchdog.yml` already derives
it for an arbitrary already-concluded run — branch name → strip the
configured spec-branch prefix → `spec_dir` → read the committed
`spec-meta.json` at that path for its `issue` field (R9 continued in
data-model.md). This is intrinsic to the run being persisted, not a
consumer-supplied destination, so it does not violate FR-013's "must not
choose... a destination" (that FR governs the *store's* destination,
which remains wrapper-supplied).

**Alternatives considered**: Computing the cumulative total in-band, at
each stage, by having every stage read the store itself before posting —
rejected: it would make every stage's status-comment step depend on the
store already existing and being reachable (contradicting FR-002 for
repositories with no persistence configured, and adding store-read
latency/failure modes to the critical path FR-037 says must "remain
quiet").

## R10: Machine-owned region on an issue comment (new; no existing precedent)

**Decision**: The rollup step searches the lifecycle issue's comments
(`gh api repos/{owner}/{repo}/issues/{issue}/comments`, paginated) for
one whose body contains the marker
`<!-- wing-commander-metrics-rollup:begin -->`. If found, it edits that
comment in place (`gh api --method PATCH
.../issues/comments/{id}`); if not found, it creates a new comment
containing the region. The region is regenerated in full on every
update (current cumulative totals, one line per stage), with a
per-run history list inside it that only appends an entry for a
`record_key` not already present in the existing region (parsed back out
of the previous body before regenerating) — the same
anchor-to-a-structured-field discipline `finalize.yml`'s fold-log
already uses (its own comment warns that anchoring dedup to free-text
instead of a structured field lets an unrelated string collision cause a
silent no-append).

**Rationale**: FR-031a requires the summary to live in a machine-owned
region whose ownership is evident, following "the pattern this
repository already established for machine-owned regions" — that
pattern (delimited region, regenerated fresh, human text outside
untouched) exists today only for a PR body (`finalize.yml`'s
state/fold-log/narrative regions), never for an issue comment, since
every existing stage-status post is a fresh append-only comment
(`wing-commander-callout`'s own description: "never edits or deletes a
prior comment"). This feature is the first to need find-and-edit
semantics for a comment, so the marker-search step is new, but the
region-splice logic that follows it is the same shape as `finalize.yml`.

**Alternatives considered**: Reusing `wing-commander-callout` and always
posting a fresh comment for the rollup, relying on "the last one" being
the current total — rejected: FR-031c ("no second rolling summary")
explicitly rules out a growing series of rollup comments, and FR-031b
requires "exactly one rolling summary exists" at any time, which
append-only cannot guarantee.

## R11: New published workflow and wrapper naming

**Decision**: The persistence mechanism is a new `workflow_call`-only
workflow, `metrics-persist.yml`, alongside the other published stages.
It is unnumbered, like `rebase.yml` and `auto-update-spec-kit.yml` (the
`wing-commander-N-*.yml` numbering is reserved for the intake → cleanup
lifecycle chain; event-driven stages outside that chain are unnumbered).
Its wrapper is `wing-commander-metrics-persist.yml`, triggered by
`workflow_run` on the set of stage workflows that call
`wing-commander-metrics-summary` (R3's list) plus a `workflow_dispatch`
`run-id` input for manual re-invocation, mirroring
`wing-commander-8-watchdog.yml`'s `resolve` job shape (branch on
`github.event_name`, no checkout in `resolve`, `permissions: actions:
read` only).

**Rationale**: `metrics-persist.yml` declaring only `on: workflow_call`
means `wc_published_stages.py`'s dynamic derivation (glob + YAML parse
for `workflow_call`) picks it up automatically — no manual list to edit,
which is the exact defect class issue #149 already named for a
hardcoded stage list. FR-019a requires persistence to run out of band
and be manually invocable for an arbitrary concluded run, "because its
live trigger wiring can only be exercised after it reaches the default
branch" — `workflow_run` triggers only fire for workflows on the default
branch, so the wrapper's first real dispatch cannot be its first test;
the `workflow_dispatch` escape hatch is what makes it testable pre-merge
and re-runnable for a historical run afterward.

## R12: Gate coverage — new checks, numbers assigned at implementation time

Five new deterministic gates are needed (User Story 5); each follows the
constitution VIII / gate-registry convention (a `verify-*.py`/`.sh`
script wired into exactly one `run:` line inside a PR-triggered job of
`lint-workflows.yml`; no second registration point). Concrete gate
numbers are assigned sequentially by convention at implementation time
(not reserved in this plan, to avoid colliding with numbers other
in-flight specs may claim first):

1. **Layer-split coverage extended to `.github/actions/**`** — the
   existing `verify-stage-invariants.py` (`Gate 31`'s script) only walks
   `.github/workflows`; this feature's two new/extended composites
   (`wing-commander-metrics-summary`'s additions, the new
   `wing-commander-metrics-persist` composite) live under
   `.github/actions/**`, exactly the gap issue #149 names and spec.md's
   own text calls out. FR-038 requires this coverage to exist before
   this feature ships, not deferred to #149.
2. **Schema conformance** — a fixture record for schema version 1 must
   validate against the field table in contracts/metrics-record-schema.md;
   a fixture with a missing/renamed/wrong-typed field must be rejected.
3. **Unknown schema version retained-and-skipped** — a fixture record
   carrying `schema_version: 2` (or any value the reader doesn't
   recognize) is read by the rollup/collector's schema-aware code path
   and asserted to be kept in the store and excluded from computation,
   never dropped or failed on.
4. **Contention-retry preserves both writers' records** — drives R7's
   retry loop against a fixture that simulates a rejected push (a second
   local branch tip pushed between fetch and push) and asserts both
   writers' records survive.
5. **Transcript/record retention-days declared at every discovered
   upload site** — discovers every `upload-artifact` step whose `path`
   matches the transcript or metrics-record pattern (not a hardcoded
   count — the existing inventory drifted from the requester's stated 14
   to the measured 16), and fails, naming the site, if `retention-days`
   is absent. Doubles as the check a new call site added later without
   declaring retention trips (FR-033).

A sixth check — "no agent invocation added by this feature" (FR-040a) —
is folded into gate 1 above rather than standing alone: the same script
that asserts no ambient-state read in `.github/actions/**` also asserts
no `uses: anthropics/claude-code-action` appears in the files this
feature adds or changes there, since both are the same "read the diff,
assert an absence" shape.

## R13: Decisions made without an explicit spec answer

Summarized for the lifecycle issue comment (none of these contradict
spec.md; each fills a gap spec.md left to plan-level judgment):

- Store layout: one orphan `metrics` branch, one flat `records.jsonl`
  (R5) — spec.md commits to "B + A" but not to file/branch naming or
  sharding.
- Record key formula: `run_id:job_id:step_index` (R6) — spec.md defines
  "one entry per agent run" but not the concrete de-dup key.
  Retry bound: 8 attempts (R7) — spec.md requires "bounded," not a number.
- Rollup split between in-band (per-run line) and out-of-band (rolling
  summary) (R9) — spec.md specifies both surfaces and that they agree,
  not which piece computes which.
- Gate numbers deferred to implementation time (R12) — sequential
  numbering is this repo's convention but not spec.md's concern.
