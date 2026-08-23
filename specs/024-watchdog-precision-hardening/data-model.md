# Phase 1 Data Model: Watchdog Precision & Determinism Hardening

This feature has no application database of its own — it amends the
entities `specs/015-pipeline-watchdog/data-model.md` already defines.
Every entity below is a **delta**: what changes, what stays the same,
and why. Entities from 015 not listed here (Run under inspection,
Lifecycle issue) are unchanged.

## Signal (`signals.json` entry, produced by `collect`, consumed by `diagnose`)

**Unchanged shape.** What changes is which collectors are permitted to
emit one: per FR-004/FR-005, every collector now applies the same
attribution invariant before emitting a signal —

| Field | Rule |
|---|---|
| Attribution: executed | The inspected run's `conclusion` MUST NOT be `skipped`/`cancelled` at the point the collector's evidence source is read. |
| Attribution: owned | The evidence the collector reads MUST belong to a step/job/artifact the inspected run itself produced (already inherent for artifact-id-scoped and per-job-scoped reads; explicit for branch-drift's head-branch-ownership check). |

A collector whose inspected run fails either check emits **no signal**
for that condition — not a signal marked "unattributable," an absent
entry. This is a suppression at the source (FR-003), not a downstream
filter.

**Before this feature**: 2 of 5 collectors (`collect-branch-drift`,
`collect-spec-meta`) enforced this. **After**: all 5 do
(`collect-execution-output`, `collect-step-summary`,
`collect-annotations` gain the same check — research.md).

## Finding (`diagnose` step's structured output)

| Field | Type | Change |
|---|---|---|
| `class` | enum | Unchanged. |
| `description` | string | Unchanged. |
| `evidence` | array of `{signalId, source, locator}` | Unchanged shape; gains a new downstream **validity gate** (below) that did not exist before. |
| `normalizedFacts` | object | Unchanged shape; its presence/non-emptiness is now enforced, not merely requested. |
| `severityHint` | enum | Unchanged — advisory input to a rung decision that, after FR-014, no longer exists; retained only as descriptive context in the lifecycle-issue report, never gates a write. |
| `alreadyHandledBy` | nullable string | Unchanged (FR-021 of this feature's scope boundary — coexistence logic is untouched). |

### New: Evidence validity gate (FR-008/FR-009)

A deterministic check, run once per Finding immediately after
`diagnose` and before fingerprinting:

```
valid  ⟺  evidence is non-empty
           AND every evidence[].signalId resolves to a signal this run's
               collectors actually emitted (already checked pre-fingerprint,
               research.md)
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
inspect" (collection itself failed). A Finding with `{tool: null,
denials: null}` — the shape every historical `denied-tool` false
positive actually carried, per the retrospective — now fails this gate.

## Fingerprint (computed, `triage` job)

**Before this feature** (spec 015, as shipped — the research survey
found the *actual* code already ahead of spec 015's written contract):
two branches — a primary signal-id basis (`sha256(class + "|signals:" +
sorted-joined valid cited signal ids)`) and a fallback to
`sha256(class + "|" + canonicalized normalizedFacts)` "whenever the
Finding cites no usable signal id."

**After this feature** (FR-006/FR-007): the fallback branch is deleted.
Fingerprinting has exactly one basis:

```
fingerprint = sha256(finding.class + "|signals:" + sorted-joined(valid cited signal ids))
```

This is possible only because the evidence-validity gate (previous
entity) now guarantees every Finding that reaches this step already has
at least one valid signal id — the fallback's precondition can no longer
occur. `finding.class` and the signal ids are both deterministic,
collector/stamping-derived values (never model-authored text), so the
same defect recurring across independent runs — independent `diagnose`
invocations, independent English wording — produces byte-identical
fingerprints (US3, SC-004).

## Dedup outcome (computed, `triage` job)

**Before this feature**: three outcomes — `none`, `match-open`,
`match-closed` — plus the orthogonal `data-integrity` (>1 match). A
lookup that fails to execute (`gh search issues` non-zero exit) is
swallowed (`results='[]']`) and **collapses into `none`**, i.e. "file as
new."

**After this feature** (FR-018/FR-019/FR-020): four outcomes:

| Outcome | Meaning | Write behavior |
|---|---|---|
| `none` | The lookup completed and found no prior finding with this fingerprint. | Create a new pipeline-defect issue. |
| `match-open` | The lookup completed and found an open issue carrying this fingerprint. | Comment with fresh evidence; file nothing new. |
| `match-closed` | The lookup completed and found a closed issue carrying this fingerprint. | Reopen + comment. |
| `unknown` **(new)** | The lookup **could not be completed** (the `gh issue list` call itself errored — network, rate limit, permissions). | **Suppress filing entirely.** Report "dedup lookup failed — finding suppressed, needs manual check" on the lifecycle issue. Never falls through to `none`'s create-new behavior — `unknown` and `none` share no code path (FR-019). |
| `data-integrity` | >1 match for one fingerprint (marker-uniqueness violation). | Unchanged from spec 015 — reported, no auto action. |

**Lookup mechanism** (FR-020): replaces `gh search issues "<marker> in:body" --state all` (an eventually-consistent full-text index query) with `gh issue list --label pipeline-defect --label "🐕 · <class>" --state all` (a bounded, strongly-consistent direct read scoped to the finding's own class) followed by a local `jq` filter over that bounded result set's bodies for the exact fingerprint marker. The per-class label already exists on every filed pipeline-defect issue (unchanged from spec 015) — it becomes, retroactively, the "durable, queryable class attribute" FR-020 requires; no new label taxonomy is introduced for this purpose.

## Triage decision (computed per Finding)

**Before this feature**: a four-branch ladder (rung 1 auto-fix / rung 2
PR-referencing-issue / rung 3 issue-only / dedup-match comment-or-reopen)
gated by the FR-011 diff-based guardrail check against
`.specify/memory/watchdog-guardrails.json`.

**After this feature** (FR-014): collapses to exactly one branch —
"file, comment, or reopen a pipeline-defect issue," selected purely by
the dedup outcome above:

```
dedup outcome none          → create new pipeline-defect issue
dedup outcome match-open    → comment with fresh evidence
dedup outcome match-closed  → reopen + comment with fresh evidence
dedup outcome unknown       → suppress; surface the lookup failure
dedup outcome data-integrity → report only, no auto action (unchanged)
every non-suppressed path also appends to the lifecycle issue (FR-022 of spec 015, unchanged)
```

No diff is ever attempted; no PR is ever opened by the watchdog. The
`severityHint` field, the guardrail config, the self-dispatch cap's
write-suppression branch, and the pause switch's write-suppression
branch all still exist as *reporting* context (a capped/paused run still
reports it inspected and would-have-filed) but no longer gate a
richer-than-issue-filing action, because no richer action exists anymore.

## Precision criterion (new entity, FR-001)

| Field | Value |
|---|---|
| Numerator | Count of distinct pipeline-defect issues, among the most recent 20, carrying label `disposition:confirmed`. |
| Denominator | Count of distinct pipeline-defect issues among the most recent 20 (post-dedup — one issue per fingerprint, regardless of how many runs recurred against it). |
| Target | ≥70%. |
| Not-yet-applicable state | Fewer than 10 distinct filed findings exist (including zero) — reported as "not applicable," never as a pass or a divide-by-zero failure. |
| Computation | Manual: a maintainer runs `gh issue list --label pipeline-defect --state all --limit 20 --json number,labels,createdAt` (sorted, most recent 20) and counts `disposition:confirmed` vs. `disposition:false-positive` labels among them — no new automation (research.md, Constitution III). |

## Deterministic-judgment principle (new entity, FR-012/FR-013)

Not a runtime entity — a governance artifact. Recorded as Principle IX
of `.specify/memory/constitution.md` (research.md): judgment that gates
a durable action (a filed finding, a fingerprint, a dedup outcome, an
autonomous write) belongs in deterministic code, not an agent's prompt.
Citable by number (`Principle IX`) the same way Principle VIII already
is, per this repository's existing constitution-citation convention.

## Guardrail configuration — removed

`.specify/memory/watchdog-guardrails.json` and its schema (`maxDiffLines`,
`changeClasses[]`) are **deleted**, not amended — FR-014 removes rung 1
and the config existed solely to gate it. No successor entity replaces
it; there is no longer a guardrail concept because there is no longer an
autonomous-write rung to guard.

## State transition (updated)

```
(any stage's run completes, success or failure) ──workflow_run──▶ collect (all 5 collectors attribution-checked) → diagnose
                                                                          │
                                          no signals ──────────────────▶ "passed inspection" on lifecycle issue
                                          collection failed ────────────▶ "could not inspect" on lifecycle issue
                                          ≥1 finding ──────────────────▶ evidence-validity gate
                                                                                │
                                                        invalid ─────────────▶ "suppressed: invalid evidence" on lifecycle issue
                                                        valid ────────────────▶ fingerprint (signal-id basis only) → dedup lookup (bounded direct read)
                                                                                        │
                                                              none          ──▶ create pipeline-defect issue
                                                              match-open    ──▶ comment on existing issue
                                                              match-closed  ──▶ reopen + comment
                                                              unknown       ──▶ suppress; report lookup failure
                                                              data-integrity──▶ report only, no auto action
                                                                                        │
                                                                        every non-suppressed path also appends to the lifecycle issue
```

No rung branch remains in this diagram — the ladder from spec 015's
data-model.md is retired in full (FR-014, SC-009).
