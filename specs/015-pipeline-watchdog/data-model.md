# Phase 1 Data Model: Pipeline Watchdog — Run Validation & Triage

This feature has no application database — it reads GitHub Actions run
data and repository files, and writes GitHub issues/comments/labels/PRs.
The "entities" below are `spec.md`'s Key Entities section, expressed as
their concrete on-disk/on-GitHub representation, plus the two supporting
shapes research.md introduces (`signals.json` and the guardrail config).

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

## Finding (diagnose step's structured output, one array entry per detected problem)

| Field | Type | Notes |
|---|---|---|
| `class` | enum | One of the FR-003 v1 classes (`denied-tool`, `lost-progress`) or a diagnose-assigned class for signals with `class-hint: null` |
| `description` | string | Human-readable, must quote/cite the specific evidence (FR-002) |
| `evidence` | array of {source, quote/locator} | What a human would need to confirm the diagnosis without opening raw artifacts |
| `normalizedFacts` | object | Stable, class-specific facts the deterministic fingerprint step hashes (research.md) — e.g. `{tool: "webfetch"}`, never volatile fields like run IDs or turn numbers |
| `severityHint` | enum: `minor` \| `notable` \| `large` | Descriptive context only — retained in the lifecycle-issue report; never gates a write (FR-014 of spec 024 removed the rung it used to advise) |
| `alreadyHandledBy` | nullable string | Set when the coexistence check (research.md) finds this exact condition already reported by `implement.yml`'s stalled job or `cleanup.yml`'s `mark-stalled` — suppresses a duplicate new finding of this class for this run (FR-024) |

FR-004: zero Findings for a run ⇒ the watchdog records "passed
inspection" on the lifecycle issue and creates/comments/reopens nothing.
FR-005: if collection itself fails (evidence missing/expired/unreadable
for every source), the diagnose step is skipped entirely and the
watchdog records "could not inspect this run" instead of guessing.

## Fingerprint (computed, not model-generated)

```
fingerprint = sha256(finding.class + "|" + canonical(finding.normalizedFacts))
```

`canonical()`: sort object keys, lowercase string values, drop any field
a per-class schema marks volatile. Deterministic and reproducible across
independent watchdog runs inspecting recurrences of the same defect
(research.md) — this is what makes FR-016's "same defect → one issue,
distinct defects → distinct issues" guarantee hold even though two
diagnose invocations never see each other's output.

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

**Dedup resolution** (FR-012–FR-016, research.md):

```
gh search issues "wing-commander-watchdog: fingerprint=<sha256> in:body" --state all
  0 results            → create new pipeline-defect issue
  1 OPEN result         → comment with fresh evidence, file nothing new
  1 CLOSED result        → reopen + comment with fresh evidence
  >1 result              → data-integrity finding of its own; reported, no auto action
```

## Lifecycle issue (GitHub issue, one per spec, pre-existing — unchanged shape from stages 1–8)

Every watchdog run's report lands here (FR-022), regardless of rung —
this is *always written to*, unlike the pipeline-defect issue (created
only for rung 2/3). For self-inspection (US4), "the lifecycle issue"
resolves to whichever spec the *inspected* watchdog run was itself
invoked to check — no separate "watchdog's own issue" concept, so no
special case is needed for FR-021.

| Report shape | When |
|---|---|
| "Run passed inspection." | Zero findings (FR-004) |
| "Could not inspect this run: \<reason\>." | Evidence unreadable (FR-005) |
| One block per Finding: description + evidence + action taken + dedup outcome | One or more findings (FR-002, FR-022) |
| "Self-dispatch cap reached — reporting only, no write performed." | Self-inspection past the configured cap (FR-018) |
| "The watchdog's writes are paused (`WING_COMMANDER_WATCHDOG_PAUSED`) — reporting only." | FR-019 |

## Triage decision (computed per Finding, not stored beyond the report above)

```
dedup match found, open    → comment with fresh evidence
dedup match found, closed  → reopen + comment with fresh evidence
no dedup match              → create new pipeline-defect issue
```

Selected purely by the dedup outcome — no fix diff is ever attempted, so
there is no rung/severity ambiguity left to resolve (FR-014 of spec 024
removes the ladder FR-010's tie-break used to apply to).

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
                                          ≥1 finding ──────────────────▶ fingerprint → dedup search
                                                                                │
                                                    dedup miss             ──▶ create new pipeline-defect issue
                                                    dedup hit, open        ──▶ comment on existing pipeline-defect issue
                                                    dedup hit, closed      ──▶ reopen + comment on pipeline-defect issue
                                                                                │
                                                                        every path also appends to the lifecycle issue (FR-022)
```

This stage never writes `spec-meta.json` itself (unlike `cleanup.yml`'s
`mark-stalled` write) — its own writes are confined to GitHub
issues/comments/labels; no pull request, ever (FR-014 of spec 024).
