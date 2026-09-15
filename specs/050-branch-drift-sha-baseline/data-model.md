# Phase 1 Data Model: Exact-SHA Branch-Drift Baseline

No application database. Every entity below is either an addition to the
JSON record specs/043 already defines, or the shape of a signal the
watchdog already emits. This is spec.md's Key Entities section made
concrete against research.md's decisions.

## `branch_advance` (new group on the agent run metrics record, schema version 1)

Added to the existing record shape (`contracts/metrics-record-schema.md`,
data-model.md's "Agent run metrics record" table) as one new top-level
nested object. Present on every record this feature's version of
`wing-commander-metrics-summary` emits (research.md R3); populated only
by the fourth, new call site (`implement.yml`'s "Record branch advance
(cycle)"), `available: false` and every value `null`/`false` on the
three pre-existing per-step records and on any record emitted by a
caller predating this feature (which simply omits the new group entirely
— see "Compatibility" below).

| Field | Type | Notes |
|---|---|---|
| `branch_advance.available` | boolean | `true` only when the call site passed `branch` and at least one of `before-sha-available`/`after-sha-available` as `'true'` (research.md R3). `false` for every call site that does not opt in — the three existing implement.yml call sites, and every other stage's call site today. |
| `branch_advance.branch` | string or null | The branch this pair describes, e.g. `"spec/050-branch-drift-sha-baseline"` — recorded literally by the call site (`${{ inputs.spec-prefix }}${{ slug }}`), never derived by a reader from a slug or prefix default (FR-003). `null` when `available` is `false`. |
| `branch_advance.before_sha` | string or null | The branch's tip as observed at cycle start. `null` when `before_available` is `false`. |
| `branch_advance.before_available` | boolean | `false` only for the not-yet-created-branch case (FR-004) — not currently reachable from `implement.yml`'s own cycle (research.md R1) but required by the schema/gate for the stage-neutral case a future `plan`/`tasks` populator will hit. |
| `branch_advance.after_sha` | string or null | The branch's tip as observed after every push the cycle made (the agent's own push(es), the retry's, and the deterministic bookkeeping push) — never the tip after only the first of several pushes (spec.md Edge Case). A rejected push yields `after_sha == before_sha`, not `after_available:false` (research.md R4). |
| `branch_advance.after_available` | boolean | `false` only when the stage's own read of the branch tip itself failed (a transient fetch failure) — best-effort, degrades rather than failing the cycle (spec.md Assumption). |
| `branch_advance.commits` | integer or null | `git rev-list --count before_sha..after_sha`, computed once by the stage while it holds both SHAs locally (research.md R5). `0` both when the two points are equal (no progress) and when `after_sha` is a strict ancestor of `before_sha` (a backwards reset) — the two are distinguished by whether `before_sha == after_sha`, not by `commits` alone (spec.md Edge Case). |
| `branch_advance.commits_available` | boolean | `false` only when either SHA itself is unavailable, or the range fails to resolve for a reason other than "zero commits". |

**Compatibility**: Additive only (FR-006). A record from a pipeline
version predating this feature simply has no `branch_advance` key at
all — a reader (the watchdog, or any future consumer) MUST treat a
missing key the same as `available: false`, never as a validation
failure (spec.md Edge Case "a record carrying the new fields reaches a
consumer that does not know them" — this is the mirror case, an old
record reaching a new consumer, and both directions degrade rather than
error).

**Invariant**: `before_available` and `after_available` are each
independent of the other and of `commits_available` — a fixture proving
"before unavailable, after available" (and the reverse) is required by
FR-008 and is not implied by any other field on the record.

## New composite inputs (`.github/actions/wing-commander-metrics-summary`)

Not a runtime entity — the call-site surface that populates
`branch_advance`. All seven are optional, all default to the
group's `available: false` state when omitted (research.md R3):

| Input | Maps to |
|---|---|
| `branch` | `branch_advance.branch` |
| `before-sha` | `branch_advance.before_sha` |
| `before-sha-available` (`'true'`\|`'false'`) | `branch_advance.before_available` |
| `after-sha` | `branch_advance.after_sha` |
| `after-sha-available` (`'true'`\|`'false'`) | `branch_advance.after_available` |
| `commits` | `branch_advance.commits` |
| `commits-available` (`'true'`\|`'false'`) | `branch_advance.commits_available` |

`branch_advance.available` is computed by `emit_record()`, not passed
directly — `true` iff `branch` is non-empty AND (`before-sha-available`
== `'true'` OR `after-sha-available` == `'true'`).

## The fourth implement.yml call site's own inputs

Not part of the published contract — the literal values `implement.yml`'s
new "Record branch advance (cycle)" step passes:

| Composite input | Source in `implement.yml` |
|---|---|
| `transcript-path` | A path that does not exist for this call (e.g. `${{ runner.temp }}/wing-commander-no-transcript.json`) — deliberately drives the existing degraded-record path so this record's transcript-derived fields (`turns`, `tokens`, `cost_usd`, `outcome`, `per_model`) read `unavailable`/`null` rather than duplicating the progress-comment step's still-resident transcript file. |
| `model` | `steps.effective-model.outputs.model` (required input; reused for consistency, not read for anything branch-specific). |
| `stage` | `implement` |
| `spec-dir` / `spec-issue` | `inputs.spec-dir` / `inputs.issue-number` (same as the other three call sites — this is how `spec.identity_available` stays `true`, and how the watchdog's existing spec-identity resolution keeps working unchanged). |
| `run-label` | `branch advance` (display label, matches the `cycle`/`retry`/`progress comment` convention). |
| `step-index` | `'3'` |
| `branch` | `${{ inputs.spec-prefix }}${{ steps.spec.outputs.slug }}` |
| `before-sha` / `before-sha-available` | `steps.base.outputs.base-sha` (research.md R1); available unless empty. |
| `after-sha` / `after-sha-available` | Freshly fetched `origin/<branch>` tip (research.md R4); available unless the fetch/rev-parse failed. |
| `commits` / `commits-available` | `git rev-list --count before..after` (research.md R5); available unless either SHA is unavailable. |
| `record-path` | A distinct temp path (mirroring the other three, e.g. `${{ runner.temp }}/wing-commander-metrics-record-branch-advance.json`), immediately uploaded by a new "Upload metrics record (branch advance)" step as artifact `metrics-record-branch-advance`. |

## Branch-drift signal (watchdog's emitted finding — changed fact shape)

**Before this feature** (dispatched-implement, `since-created` arm —
unchanged for a record with no usable `branch_advance`):
```json
{"branch": "...", "before-sha": null, "since": "<RUN_CREATED_AT>", "after-sha": "...", "commits": 0}
```
(the `commits: 0` here is today's fixed placeholder — the since-created
arm never actually counts, it only fires when the count came back `0`,
so recording anything other than `0` would be meaningless; FR-019
explicitly does not require the fallback arm to carry a real count.)

**This feature adds** — dispatched-implement, `exact-sha` arm (new):
```json
{"branch": "...", "before-sha": "<before_sha>", "since": null, "after-sha": "<after_sha>", "commits": <recorded commits>}
```
`commits` here is the value `branch_advance.commits` recorded, verbatim
— never recomputed by the watchdog (FR-019). The spec-branch-head arm
(`plan`/`tasks` pushing to their own head, `baseline="head-sha"`) is
**unchanged** — it already compares `HEAD_SHA..after_sha` exactly, so it
already has the shape the dispatched-implement arm is gaining.

**Baseline selection, restated as a table** (replaces the prose the two
miss-case comments carried — research.md R8):

| Condition | Baseline | Verdict rule |
|---|---|---|
| Run's head branch == the branch the stage pushes to (`plan`/`tasks`) | `head-sha` (unchanged) | `HEAD_SHA..after_sha` commit count == 0 |
| Dispatched implement run, inspected record's `branch_advance.available == true` | `exact-sha` (**new**) | `before_sha == after_sha` |
| Dispatched implement run, no record with `branch_advance.available == true` | `since-created` (unchanged fallback) | `git rev-list --count --since=<createdAt> after_sha` == 0 |
| Not a push-expected stage / no spec slug resolved | (skipped) | no signal |

**Step summary addition (FR-013)**: whichever row's baseline fired is
named in `$GITHUB_STEP_SUMMARY`, e.g. "measuring `spec/050-...` via the
implement run's own recorded before/after SHAs" vs. "...via commits
since the run was created at `<timestamp>` (no recorded branch-advance
evidence on this run)".

## Gate fixtures (not runtime entities, but checked-in test data)

| Fixture | Used by |
|---|---|
| `branch_advance`: both points present, different, `commits` > 0 | Gate 39 (positive) |
| `branch_advance`: both points present, equal, `commits: 0` | Gate 39 (positive) |
| `branch_advance`: `before_available: false` | Gate 39 (positive) |
| `branch_advance`: `after_available: false` | Gate 39 (positive) |
| `branch_advance`: `commits: 0` with `before_sha != after_sha` (backwards reset) | Gate 39 (positive) |
| `branch_advance`: `commits_available: false` with both SHAs present | Gate 39 (positive) |
| `branch_advance` with a wrong-typed field (e.g. `commits` as a string) | Gate 39 (negative) |
| A record predating this feature (no `branch_advance` key at all) | Gate 39 (positive — must still validate) |
| A batch containing one record with a populated `branch_advance` group, appended/deduped/retried alongside plain records | Gate 41 |
| The real composite invoked a fourth time with populated branch/SHA inputs and an absent transcript path | Gate 43 |
| A local git repo + synthetic run/record JSON: `branch_advance.available` true, SHAs equal | Gate 53 (US1 AS1) |
| Same, SHAs differ | Gate 53 (US1 AS3) |
| Same, equal SHAs but the spec's lifecycle already reads `stalled` | Gate 53 (US1 AS4 / FR-014) |
| A record with no `branch_advance` (or `available: false`) | Gate 53 (US3 / FR-018) |
| A non-dispatched-implement run (spec-branch-head, non-push-expected stage, skipped/cancelled run) | Gate 53 (FR-012, regression) |
