# Phase 1 Data Model: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

Entities not listed here (`Signal` in general, `Finding`, `Fingerprint`,
`Precision criterion`) are unchanged from `specs/015-pipeline-watchdog/
data-model.md` as amended by `specs/024-watchdog-precision-hardening/
data-model.md`; only the additions and modifications this feature makes
are documented below. This file is itself amended, in the same shape, into
`specs/015-pipeline-watchdog/data-model.md` at implementation time
(FR-023) — see `contracts/watchdog-dedup-fanout-delta.md`.

## Signal — one new kind (`gate-suite-failure`)

| Field | Type | Notes |
|---|---|---|
| `source` | string | New value: `"gate-suite"`, emitted by a new `Collect: cycle outcome` collector step (below), only when the inspected run's most recent implement cycle's local gate suite (`run-local-gates.py`) exited non-zero |
| `class-hint` | string \| null | `null`, as with every other collector — the finding's class remains diagnose's own choice (FR-009: "whatever class the diagnose agent assigned it") |
| `facts` | object | `{"first-failure": <string>}` — the first `FAIL` line `implement.yml`'s gate-suite step captured, truncated/normalized the same way other collectors truncate free text |

**Stamped id** (`Stamp signal ids`, per-source projection, unchanged
convention): `{kind: "gate-suite-failure", ident: {"first-failure":
<normalized first-failure text>}}`. Two runs whose most recent cycle broke
on the *same* first-failing check produce the *same* id, matching the
stability guarantee every other `kind` in this table already provides.

## Cycle outcome (new: artifact `implement.yml` uploads, `watchdog.yml` downloads)

Not a `Signal` (it never appears in `signals.json` and diagnose never sees
it directly) — it is triage-only state read by the new `Collect: cycle
outcome` collector and consumed exclusively by the FR-009 condition.

| Field | Type | Source |
|---|---|---|
| `converged` | boolean | `implement.yml`'s "Read back cycle outcome" step's own `converged` output (FR-010b of spec 059) |
| `handoff` | boolean | Same step's `handoff` output (FR-010 of spec 059) |
| `gate-suite-outcome` | `"pass"` \| `"fail"` \| `"skipped"` | Whichever of `gate-suite-cycle`/`gate-suite-retry` ran last in that attempt; `"skipped"` when the gate-suite preflight found a missing prerequisite |
| `gate-suite-first-failure` | string \| null | That step's own `first-failure` output; `null` when `gate-suite-outcome != "fail"` |

**Attribution guard**: identical shape to `collect-execution-output`
(`watchdog.yml:534-539`) — a `skipped`/`cancelled` inspected run, or a
download failure distinguishable as "no artifact" (vs. a genuine API
failure), is a successful *empty* contribution: the fact is simply
undetermined, not an error, and FR-010 requires the undetermined case to
default to filing as normal, never to guessing.

## Occurrence record (new — the marker each filing/comment carries)

| Field | Type | Notes |
|---|---|---|
| `issue-number` | int | Which `pipeline-defect` issue this occurrence belongs to |
| `location` | `"body"` \| `"comment"` | Body only for the first (filing) occurrence; every later occurrence is a comment (FR-003: the watchdog never edits a body) |
| `cited-ids` | string[] | The validated signal ids *this occurrence* cited — sorted, comma-joined, same normalization `Compute fingerprint`'s `valid` basis already applies |
| `matched-on` | string[] | Subset of `cited-ids` that overlapped the matched issue's then-current matchable set (empty for the first/filing occurrence, which has nothing to match against) |
| `new-ids` | string[] | `cited-ids` minus `matched-on` — legible directly in the occurrence's own comment/body text (FR-017) |

Machine-readable form: `<!-- wing-commander-watchdog: signal-ids=<cited-ids, sorted, comma-joined> -->`,
one per occurrence, additive alongside the existing
`<!-- wing-commander-watchdog: fingerprint=<hash> -->` marker (unchanged:
still the exact-citation-set hash of *that one occurrence*, still the sole
mechanism the closed-issue exact-match path reads).

## Matchable id set (new — computed, not stored)

The set an open issue is matched against for a new finding. Computed at
dedup-search time as: the union of every occurrence record's `cited-ids`
for that issue (body + every comment carrying the marker, read back from
one `gh issue list --json number,state,body,comments` call — no per-issue
follow-up read), **capped at the 30 most-recently-added distinct ids**
(FR-008; oldest evicted first, in occurrence order). An id that ages out
of the cap remains visible in its own occurrence's historical record
(occurrence records are never edited) — it simply stops counting toward
future matches.

## Dedup outcome — one new value (`converging-gate-suite`)

Extends spec 024's four-outcome set (`none` / `match-open` / `match-closed`
/ `data-integrity` / `unknown`) with:

| Outcome | Meaning | Write? | Distinguished from |
|---|---|---|---|
| `overlap` | ≥1 open issue's matchable set intersects the finding's cited ids (replaces bare `match-open` as the general open-match case; an *exact*-citation-set match is still reported as such via the unchanged `fingerprint=` marker check, but both are `act`ed on identically — comment on the match) | Yes — comment on the lowest-numbered match | `data-integrity` (>1 result carries the *same exact* fingerprint — still an unexplained anomaly, never expected) and multi-match-under-overlap (routine, not an anomaly — see `other-matches` below) |
| `converging-gate-suite` | FR-009's filing condition: every cited id is `gate-suite-failure`-kind, the run's cycle outcome says `converged=false, handoff=false`, and neither `spec-meta` stage nor the `stalled` label say this cycle stalled | No — reported under its own wording (FR-011), never as `data-integrity` or `unknown` | `unknown` (undecidable) and `data-integrity` (an anomaly) — this is a *decided* "not a defect" |

`overlap`'s per-instance detail carries an `other-matches` list (issue
numbers of every *other* open candidate whose set also intersected,
sorted ascending, excluding the lowest-numbered one already selected) —
named in the occurrence comment (FR-007) but never written to.

## Triage decision (computed per Finding) — updated shape

| Field | Type | Notes |
|---|---|---|
| `suppressed` | boolean | Unchanged (coexistence with existing stalled/cleanup automation, spec 024) |
| `evidence-valid` | boolean | Unchanged |
| `fingerprint` | string | Unchanged — still the exact-citation-set hash |
| `cited-ids` | string[] | New — the validated ids this finding cites, carried forward so `act` can write the new `signal-ids=` marker without recomputing it |
| `dedup` | enum | `none` \| `overlap` \| `match-closed` \| `data-integrity` \| `unknown` \| `converging-gate-suite` |
| `dedup-issue` | int \| "" | The (lowest-numbered, for `overlap`) matched issue, when applicable |
| `other-matches` | int[] | New — populated only for `overlap` with more than one open candidate |
| `matched-on` / `new-ids` | string[] | New — the occurrence record fields above, computed once here and reused by both the issue-body/comment write and the lifecycle-issue report |

## State transition (updated slice)

```text
finding → evidence-valid? → fingerprint (unchanged: exact citation-set hash)
                                   │
                                   ▼
                    is every cited id gate-suite-failure-kind?
                     │yes                              │no
                     ▼                                  │
     cycle-outcome artifact present                     │
     AND converged=false AND handoff=false               │
     AND NOT stalled?                                    │
        │yes                    │no                      │
        ▼                       └──────────┬─────────────┘
converging-gate-suite                       ▼
 (report only, no write)      dedup search: gh issue list
                                --json number,state,body,comments
                                       │
                                       ▼
                       1. count == 200 (truncated)? ──yes──▶ unknown
                                       │no
                                       ▼
                       2. exact fingerprint match found? ──yes──▶ match-open/match-closed
                                       │no
                                       ▼
                       3. any OPEN candidate's comments.length
                          >= 100 (comment-read ceiling,
                          Review Gate Round 3)? ──yes──▶ unknown
                                       │no
                                       ▼
                       4. matchable-set intersects? ──yes──▶ overlap
                                       │no                   (lowest-numbered open
                                       ▼                      match wins; others
                                     none                     named, not written)
```
