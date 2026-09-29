# Phase 1 Data Model: Pipeline Watchdog — Run Validation & Triage

This feature has no application database — it reads GitHub Actions run
data and repository files, and writes GitHub issues/comments/labels (no
PRs, per FR-014 of spec 024). The "entities" below are `spec.md`'s Key
Entities section, expressed as their concrete on-disk/on-GitHub
representation, plus the supporting shape research.md introduces
(`signals.json`).

## Run under inspection (`workflow_run` payload / `workflow_dispatch` input)

Not persisted by the watchdog — read once per invocation.

| Field | Source | Used for |
|---|---|---|
| `workflow_run.id` / dispatch `run-id` | event or input | The run being inspected; anchors every evidence collector |
| `workflow_run.name` | event | Which of the nine stages this is (including `"8 - Watchdog"` for self-inspection, FR-021) |
| `workflow_run.head_branch` | event | Deriving the spec slug (strip known prefixes: `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/*-iterN`); best-effort for runs on `main` (cleanup) |
| `workflow_run.head_sha`, `.conclusion` | event | Evidence-collector anchor points; `conclusion` covers both succeeded and failed per FR-001 |
| `workflow_run.html_url` | event | Cited verbatim in every Finding so a human can jump to the raw run (FR-002's "without opening raw artifacts" is about not *needing* to, not about hiding the link) |

## Signals (`signals.json`, ephemeral, produced by the collect job, consumed by diagnose)

Not committed anywhere — a job-scoped intermediate file, one array entry
per evidence source that produced anything:

```json
[
  {"source": "execution-output", "class-hint": "denied-tool", "facts": {"tool": "WebFetch", "denials": 4, "turns": [12, 15, 19, 22]}},
  {"source": "branch-drift", "class-hint": "lost-progress", "facts": {"branch": "spec/015-pipeline-watchdog", "before-sha": "…", "after-sha": "…", "commits": 0}},
  {"source": "spec-meta", "class-hint": "stage-mismatch", "facts": {"expected-stage": "plan", "actual-stage": "spec"}},
  {"source": "step-summary", "class-hint": null, "facts": {"job": "implement", "matched-sentinel": "turn-budget warning"}},
  {"source": "annotations", "class-hint": null, "facts": {"level": "warning", "message": "…"}}
]
```

> **Deviation (spec 022, FR-010):** the `denied-tool` signal's
> `facts.turns` field shown above (the first row) is renamed to
> `facts.record-index` by
> [`022-gate-closed-lifecycle`](../022-gate-closed-lifecycle/contracts/denied-tool-collector-delta.md).
> The value is unchanged — a zero-based position into the raw SDK message
> array — but `turns` mislabeled it as a conversation-turn count (a single
> turn spans several array entries, so the index can exceed the run's own
> `num_turns`; see issues #105/#106). This is a deliberate,
> spec-022-sanctioned deviation from this spec's original contract; see that
> delta for the full corrected `jq` filter and the `denials`-count fix that
> lands with it.

> **Deviation (PR #137):** the shape above, and spec 022's correction of it,
> both describe only the **fallback** log scan. The SDK's terminal result
> record does emit `permission_denials` — spec 022's research.md R4 recorded
> that it did not and guessed the shape as `{tool, count}`, and both halves
> were wrong — so the authoritative branch is the one actually taken, and it
> emitted `{tool: null, denials: null}` for every finding it ever produced.
> Its real per-signal shape is
> `{"source": "result-record", "class-hint": "denied-tool", "facts": {"tool": "Bash", "denials": 2, "denied-commands": ["…"]}}`:
> grouped by the SDK's `tool_name`, with up to five distinct denied commands
> carried as descriptive facts. There is no `record-index` on this path —
> the SDK gives commands, which are better evidence than array positions —
> so `record-index` is now specific to the fallback. The fallback also
> narrowed: `is_error` alone is no longer treated as a denial, because it is
> set for any failing call. Both paths are held to fixtures by
> `.github/scripts/verify-denied-tool-collector.sh`, which
> `lint-workflows.yml` gate 5 runs and diffs against the shipped filter.

`class-hint` is populated only for the two v1 pattern-matched classes
(FR-003a/b, computed directly by the collector, not the diagnose step);
`null` for sources whose interpretation genuinely needs the diagnose
step's judgment (step summaries, annotations, general
`spec-meta.json`/branch signals outside the two named classes). An empty
array means "no signal from any source" — the collect job still runs
diagnose (which then reports "passed inspection," FR-004), rather than
skipping it, so the "no problem" path is exercised through the same code
path as every other outcome, not a special early exit.

**Attribution invariant** (FR-026, spec 024 FR-004/FR-005): every
collector applies the same check before emitting a signal —

| Field | Rule |
|---|---|
| Attribution: executed | The inspected run's `conclusion` MUST NOT be `skipped`/`cancelled` at the point the collector's evidence source is read. |
| Attribution: owned | The evidence the collector reads MUST belong to a step/job/artifact the inspected run itself produced (already inherent for artifact-id-scoped and per-job-scoped reads; explicit for branch-drift's head-branch-ownership check). |

A collector whose inspected run fails either check emits **no signal**
for that condition — not a signal marked "unattributable," an absent
entry. Before spec 024, only 2 of the 5 collectors (`collect-branch-drift`,
`collect-spec-meta`) enforced this; after spec 024, all 5 do.

> **Addition (spec 109):** a sixth source, `"gate-suite"`, emitted by the
> `Collect: cycle outcome` collector only when the inspected run's most
> recent implement cycle's local gate suite (`run-local-gates.py`) exited
> non-zero: `{"source": "gate-suite", "class-hint": null, "facts":
> {"first-failure": "<the first FAIL line, normalized>"}}`. Stamped id
> (per-source projection, same convention as every other kind in this
> table): `{kind: "gate-suite-failure", ident: {"first-failure":
> <normalized first-failure text>}}` — two runs whose most recent cycle
> broke on the same first-failing check produce the same id. See "Cycle
> outcome" below for the companion, non-`Signal` state this same
> collector records for the FR-033 filing condition.

## Finding (diagnose step's structured output, one array entry per detected problem)

| Field | Type | Notes |
|---|---|---|
| `class` | enum | One of the FR-003 v1 classes (`denied-tool`, `lost-progress`) or a diagnose-assigned class for signals with `class-hint: null` |
| `description` | string | Human-readable, must quote/cite the specific evidence (FR-002) |
| `evidence` | array of {source, quote/locator} | What a human would need to confirm the diagnosis without opening raw artifacts |
| `normalizedFacts` | object | Descriptive, class-specific facts (e.g. `{tool: "webfetch"}`) checked for presence/non-emptiness by the evidence-validity gate (below) and surfaced in the filed issue for human context — never volatile fields like run IDs or turn numbers, and never the fingerprint's basis (that is signal ids alone, FR-006/FR-007 of spec 024) |
| `severityHint` | enum: `minor` \| `notable` \| `large` | Descriptive context only — retained in the lifecycle-issue report; never gates a write (FR-014 of spec 024 removed the rung it used to advise) |
| `alreadyHandledBy` | nullable string | Set when the coexistence check (research.md) finds this exact condition already reported by `implement.yml`'s stalled job or `cleanup.yml`'s `mark-stalled` — suppresses a duplicate new finding of this class for this run (FR-024) |

FR-004: zero Findings for a run ⇒ the watchdog records "passed
inspection" on the lifecycle issue and creates/comments/reopens nothing.
FR-005: if collection itself fails (evidence missing/expired/unreadable
for every source), the diagnose step is skipped entirely and the
watchdog records "could not inspect this run" instead of guessing.

### Evidence validity gate (FR-002/FR-027, spec 024 FR-008/FR-009)

A deterministic check, run once per Finding immediately after `diagnose`
and before fingerprinting:

```
valid  ⟺  evidence is non-empty
           AND every evidence[].signalId resolves to a signal this run's
               collectors actually emitted
           AND normalizedFacts carries every key required for finding.class
               (per-class key list, e.g. {tool} for denied-tool,
               {branch} for lost-progress, {expected,actual} for
               stage-mismatch)
           AND none of those required values is null, empty string, or
               empty array
```

`valid == false` ⇒ the Finding is **suppressed**, not filed, and is
recorded in the lifecycle-issue report as "suppressed: invalid evidence"
— distinct from both "passed inspection" (zero Findings) and "could not
inspect" (collection itself failed). A Finding shaped `{tool: null,
denials: null}` — the shape every historical `denied-tool` false
positive actually carried — now fails this gate.

## Fingerprint (computed, not model-generated)

```
fingerprint = sha256(finding.class + "|signals:" + sorted-joined(valid cited signal ids))
```

This is the single, unconditional basis (FR-016, spec 024 FR-006/FR-007)
— there is no fallback branch. `finding.class` and the cited signal ids
are both deterministic, collector/stamping-derived values, never
model-authored text, so the same defect recurring across independent
runs — independent `diagnose` invocations, independent English wording —
produces byte-identical fingerprints. This is possible only because the
evidence-validity gate (above) guarantees every Finding that reaches
this step already has at least one valid signal id — the precondition a
`normalizedFacts`-based fallback used to exist for can no longer occur.

## Cycle outcome (spec 109 — new artifact `implement.yml` uploads, `watchdog.yml` downloads)

Not a `Signal` (it never appears in `signals.json` and `diagnose` never
sees it directly) — triage-only state read by the `Collect: cycle
outcome` collector and consumed exclusively by the FR-033 filing
condition.

| Field | Type | Source |
|---|---|---|
| `converged` | boolean | `implement.yml`'s "Read back cycle outcome" step's own `converged` output (FR-010b of spec 059) |
| `handoff` | boolean | Same step's `handoff` output (FR-010 of spec 059) |
| `gate-suite-outcome` | `"pass"` \| `"fail"` \| `"skipped"` | Whichever of `gate-suite-cycle`/`gate-suite-retry` ran last in that attempt; `"skipped"` when the gate-suite preflight found a missing prerequisite |
| `gate-suite-first-failure` | string \| null | That step's own `first-failure` output; `null` when `gate-suite-outcome != "fail"` |

**Attribution guard**: identical shape to `collect-execution-output` — a
`skipped`/`cancelled` inspected run, or a download failure distinguishable
as "no artifact" (vs. a genuine API failure), is a successful *empty*
contribution: the fact is simply undetermined, not an error, and FR-033
requires the undetermined case to default to filing as normal, never to
guessing.

## Pipeline-defect issue (GitHub issue, repo-scoped, not spec-scoped)

The triage target for a filed or recurring finding — distinct from the
*lifecycle* issue below. One pipeline-defect issue tracks one fingerprint
across however many spec runs happen to trip it (e.g. a `WebFetch` denial
pattern could recur across many different specs' implement runs; they
all map to the same pipeline-defect issue, not one each).

| Field | Written by watchdog? | Notes |
|---|---|---|
| Body | On create: yes, includes `<!-- wing-commander-watchdog: fingerprint=<sha256> -->` marker (reused convention, research.md) plus the Finding's description/evidence | Never rewritten after creation — new occurrences are comments, not body edits |
| State (open/closed/reopened) | Yes — created open (FR-015); reopened on a closed-issue match (FR-014) | Humans may close it once genuinely fixed; the watchdog only reopens, never closes |
| Comments | Yes — every recurrence appends the fresh evidence (FR-013) | Comment body always includes the triggering run's `html_url` |

No PR is ever attached — the watchdog is a pure reporter with no fix-diff
path (FR-014 of spec 024); a human decides when the issue is actually
resolved and closes it themselves.

**Dedup resolution** (FR-012–FR-016, FR-028/FR-029 of spec 024, FR-030–FR-032 of spec 109, research.md):

Lookup mechanism (FR-029; `comments` added by spec 109): `gh issue list
--repo <repo> --label pipeline-defect --label "🐕 · <class>" --state all
--limit 200 --json number,state,body,comments` — a bounded,
strongly-consistent direct read scoped to the finding's own class,
replacing the eventually-consistent `gh search issues` full-text query.
The per-class label already exists on every filed pipeline-defect issue
(unchanged from spec 015); it becomes, retroactively, the durable,
queryable class attribute this bounded read needs. `comments` lets one
call read back every occurrence's matchable id set (below), with no
per-issue follow-up read. A local `jq` filter over that bounded result
set then checks, in order:

```
gh issue list --label pipeline-defect --label "🐕 · <class>" --state all --limit 200 --json number,state,body,comments
  lookup itself fails (network, rate limit, permissions)  → unknown
  candidate count == the read's own --limit ceiling (200) → unknown (spec 109, FR-016/FR-028: a truncated read is not a completed one)
  exact fingerprint=<sha256> marker, 1 OPEN match          → comment with fresh evidence, file nothing new
  exact fingerprint=<sha256> marker, 1 CLOSED match        → reopen + comment with fresh evidence
  exact fingerprint=<sha256> marker, >1 match              → data-integrity finding of its own; reported, no auto action
  no exact match; ≥1 OPEN candidate's matchable id set
    (spec 109, below) intersects the finding's cited ids   → overlap: comment on the lowest-numbered intersecting candidate;
                                                              other intersecting candidates named, never written to (FR-031)
  no exact match; no OPEN candidate's matchable set
    intersects, or the only intersecting candidate is
    CLOSED                                                 → create new pipeline-defect issue
```

**`unknown` (FR-028, amended by spec 109)**: the lookup itself could not
be completed, **or** it completed but returned a full page (candidate
count equals the `--limit` ceiling) and so may not be the whole candidate
set — distinct from `none`, which means the lookup completed, was not
truncated, and found nothing under either mechanism. `unknown` suppresses
filing entirely and reports "dedup lookup failed — finding suppressed,
needs a maintainer's manual check" (or the truncation-specific wording)
on the lifecycle issue. It shares no code path with `none`'s create-new
behavior — a broken or truncated lookup is never treated as "nothing
found."

**`overlap` (spec 109, new)**: at least one OPEN issue's matchable id set
(below) intersects the finding's cited signal ids, with no exact
`fingerprint=` match found first. Distinguished from `data-integrity`
(reserved for more than one *exact*-fingerprint hit, still an anomaly)
and from a routine multi-match under `overlap` (more than one candidate's
matchable set intersects — routine, resolved by FR-031, never reported as
an anomaly). A partial overlap against a **closed** issue is not a match
under this mechanism (FR-014) — only an exact fingerprint reopens a
closed issue.

## Occurrence record (spec 109 — the marker each filing/comment carries)

| Field | Type | Notes |
|---|---|---|
| `issue-number` | int | Which `pipeline-defect` issue this occurrence belongs to |
| `location` | `"body"` \| `"comment"` | Body only for the first (filing) occurrence; every later occurrence is a comment (FR-003 of spec 109: the watchdog never edits a body) |
| `cited-ids` | string[] | The validated signal ids *this occurrence* cited — sorted, comma-joined, same normalization the fingerprint step's `valid` basis already applies |
| `matched-on` | string[] | Subset of `cited-ids` that overlapped the matched issue's then-current matchable set (empty for the first/filing occurrence, which has nothing to match against; the full `cited-ids` set for an exact-fingerprint match, since the whole cited set matched) |
| `new-ids` | string[] | `cited-ids` minus `matched-on` — legible directly in the occurrence's own comment/body text (FR-034) |

Machine-readable form: `<!-- wing-commander-watchdog: signal-ids=<cited-ids, sorted, comma-joined> -->`,
one per occurrence, additive alongside the existing
`<!-- wing-commander-watchdog: fingerprint=<hash> -->` marker (unchanged:
still the exact-citation-set hash of *that one occurrence*, still the sole
mechanism the closed-issue exact-match path reads).

## Matchable id set (spec 109 — computed, not stored)

The set an open issue is matched against for a new finding. Computed at
dedup-search time as: the union of every occurrence record's `cited-ids`
for that issue (body + every comment carrying the marker, read back from
one `gh issue list --json number,state,body,comments` call — no per-issue
follow-up read), **capped at the 30 most-recently-added distinct ids**
(FR-032; oldest evicted first, in occurrence order). An id that ages out
of the cap remains visible in its own occurrence's historical record
(occurrence records are never edited) — it simply stops counting toward
future matches.

## Lifecycle issue (GitHub issue, one per spec, pre-existing — unchanged shape from stages 1–8)

Every watchdog run's report lands here (FR-022) — this is *always
written to*, unlike the pipeline-defect issue (created or commented on
only when a finding is filed). For self-inspection (US4), "the lifecycle issue"
resolves to whichever spec the *inspected* watchdog run was itself
invoked to check — no separate "watchdog's own issue" concept, so no
special case is needed for FR-021.

| Report shape | When |
|---|---|
| "Run passed inspection." | Zero findings (FR-004) |
| "Could not inspect this run: \<reason\>." | Evidence unreadable (FR-005) |
| "Suppressed: invalid evidence — \<reason\>. Not filed." | The evidence-validity gate rejected the Finding (FR-027) |
| One block per Finding: description + evidence + action taken + dedup outcome | One or more findings (FR-002, FR-022) |
| "Self-dispatch cap reached — reporting only, no write performed." | Self-inspection past the configured cap (FR-018) |
| "The watchdog's writes are paused (`WING_COMMANDER_WATCHDOG_PAUSED`) — reporting only." | FR-019 |

## Precision criterion (SC-008, new entity — spec 024 FR-001)

Not a runtime entity — a manual, maintainer-computed measure against the
filed-finding record. No component of the watchdog computes or reports
this itself (Constitution III forbids a new dashboard for it).

| Field | Value |
|---|---|
| Numerator | Count of distinct pipeline-defect issues, among the most recent 20, carrying label `disposition:confirmed`. |
| Denominator | Count of distinct pipeline-defect issues among the most recent 20 (post-dedup — one issue per fingerprint, regardless of how many runs recurred against it). |
| Target | ≥70%. |
| Not-yet-applicable state | Fewer than 10 distinct filed findings exist (including zero) — reported as "not applicable," never as a pass or a divide-by-zero failure. |
| Computation | Manual: `gh issue list --label pipeline-defect --state all --limit 20 --json number,labels,createdAt`, sorted most-recent-first, counting `disposition:confirmed` vs. `disposition:false-positive` labels among the result. |

The two disposition labels (`disposition:confirmed`, `disposition:false-positive`)
are maintainer-applied, not watchdog-written — only a human reviewing a
filed finding can know whether it was genuine.

## Triage decision (computed per Finding, not stored beyond the report above)

```
converging-cycle gate-suite finding (FR-033 of spec 109) → suppress; report under its own wording, never filed
dedup exact match found, open       → comment with fresh evidence
dedup exact match found, closed     → reopen + comment with fresh evidence
dedup overlap match found, open     → comment with fresh evidence on the lowest-numbered match (FR-030/FR-031 of spec 109); others named, not written to
no dedup match (neither mechanism)  → create new pipeline-defect issue
dedup lookup failed or truncated    → suppress; report the lookup failure (FR-028, amended by spec 109)
```

Selected purely by the dedup outcome — no fix diff is ever attempted, so
there is no rung/severity ambiguity left to resolve (FR-014 of spec 024
removes the ladder FR-010's tie-break used to apply to). Persisted shape
(per Finding, `triage`→`act` handoff artifact) gains four fields under
spec 109: `cited-ids` (the validated ids this finding cites, carried
forward so `act` can write the `signal-ids=` marker without recomputing
it), `matched-on`/`new-ids` (the Occurrence record fields above, computed
once here and reused by both the issue write and the lifecycle-issue
report), and `other-matches` (populated only for `overlap` with more than
one open candidate — the issue numbers FR-031 names but never writes to).

## Guardrail configuration — removed

`.specify/memory/watchdog-guardrails.json` and its allowlist/path/line-cap
schema are removed in full (FR-014 of spec 024) — the config existed
solely to gate rung 1, which no longer exists. No successor entity
replaces it.

| Companion knob | Home | FR |
|---|---|---|
| Pause/veto switch | `vars.WING_COMMANDER_WATCHDOG_PAUSED` | FR-019 |
| Self-dispatch cap | `vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`) | FR-018 |

Both still suppress the watchdog's one remaining write path (create/
comment/reopen a pipeline-defect issue) — collect/diagnose/triage still
run and are still reported; only the write itself is suppressed.

## State transition (the slice of pipeline state this stage reacts to and reports on)

```
(any stage's run completes, success or failure) ──workflow_run──▶ collect → diagnose
                                                                          │
                                          no signals ──────────────────▶ "passed inspection" on lifecycle issue
                                          collection failed ────────────▶ "could not inspect" on lifecycle issue
                                          ≥1 finding ──────────────────▶ evidence-validity gate
                                                                                │
                                                        invalid ─────────────▶ "suppressed: invalid evidence" on lifecycle issue
                                                        valid ────────────────▶ fingerprint (unchanged: exact citation-set hash)
                                                                                        │
                                                              every cited id gate-suite-failure-kind, AND
                                                              cycle-outcome converged=false/handoff=false, AND
                                                              NOT stalled (spec 109, FR-033)          ──▶ "converging implement cycle" on lifecycle issue; not filed
                                                                                        │ (otherwise)
                                                                                        ▼
                                                                        dedup lookup (bounded direct read, comments included)
                                                                                        │
                                                              candidate count == 200 (truncated, spec 109)  ──▶ suppress; report truncated lookup (unknown)
                                                              dedup lookup failed                            ──▶ suppress; report lookup failure (unknown)
                                                              exact fingerprint hit, open                    ──▶ comment on existing pipeline-defect issue
                                                              exact fingerprint hit, closed                  ──▶ reopen + comment on pipeline-defect issue
                                                              >1 exact fingerprint hit                       ──▶ report only, no auto action (data-integrity)
                                                              no exact hit; ≥1 OPEN matchable-set overlap
                                                                (spec 109, FR-030)                           ──▶ comment on the lowest-numbered match; others named (FR-031)
                                                              no exact hit; no overlap                       ──▶ create new pipeline-defect issue
                                                                                        │
                                                                        every non-suppressed path also appends to the lifecycle issue (FR-022)
```

This stage never writes `spec-meta.json` itself (unlike `cleanup.yml`'s
`mark-stalled` write) — its own writes are confined to GitHub
issues/comments/labels; no pull request, ever (FR-014 of spec 024).
