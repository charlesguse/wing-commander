# Phase 1 Data Model: The Lifecycle Review Gate

## §1 — `review_gate` state: the lifecycle issue's own marker

**Amended by T074 (maintainer review 5355876805, F3).** `review_gate`
does **not** live in `spec-meta.json` and is **not** committed to the
reviewed pull request's branch. The original design (a `spec-meta.json`
field, written by a commit `disposition` pushed to the lifecycle PR's own
branch) was fatal for auto-merge: that push necessarily advances the PR's
real head past the SHA the round just recorded, so `lint-workflows` never
runs on the bookkeeping commit, `gate_suite_green` is permanently false on
the real head, and `merge` can never see a clean round at the current tip.
It also stacked on F1/F2: a branch-authored commit deciding facts that
same branch is judged by, peeled back by commit *subject* alone, is a
forgeable trust boundary.

Instead, `review_gate` is recorded on the **lifecycle issue's own
comments**, the way `board_item_marker.py` (spec 057) records a board loop
item's state: an HTML comment `<!-- wing-commander-lifecycle-review-gate:
{...} -->` appended to `report`'s own human-legible round-outcome comment
(never the comment's only content). `wc_lifecycle_review_marker.py` is the
single home of this marker's read/write shape, reusing
`board_item_marker.py`'s own `find_latest_marker()`/
`is_loop_marker_author()` (the "latest bot-authored comment, last opener
wins" algorithm) rather than re-deriving it a second time.

```json
{
  "round": 0,
  "head_sha": null,
  "outcome": null,
  "findings_open": 0,
  "folded_fingerprints": [],
  "filed_fingerprints": [],
  "updated_at": null
}
```

A missing marker (no bot-authored comment on the lifecycle issue carries
one yet) means no round has ever completed — read exactly as the old
`null` `spec-meta.json.review_gate` was.

| Field | Type | Written by | Read by |
|---|---|---|---|
| `round` | integer, ≥ 0 | `report`, once per completed round (clean or not) | `select` (budget check via `disposition`), round-budget-exhaustion report |
| `head_sha` | string \| null | `report`, at round completion | `select`/`readiness` (D2/D5 — "not already reviewed at this head") |
| `outcome` | enum: `clean`\|`findings`\|`failed`\|`budget-exhausted`\|`paused`\|`null` | `report` | `lifecycle_merge_preconditions.py` (D6 — "round clean at this head") |
| `findings_open` | integer, ≥ 0 | `report`, at round completion | Lifecycle-issue status line (FR-015), merge preconditions |
| `folded_fingerprints` | array of string | `report`, from `disposition`'s fold step (D11), append-only | Same step, next round (FR-021 dedup) |
| `filed_fingerprints` | array of string | `report`, from `disposition`'s file step (D11), append-only | Same step, next round (FR-021 dedup) |
| `updated_at` | string (ISO 8601) \| null | `report`, every write | Diagnostic only; no gate reads it |

**Invariant**: `head_sha` and `outcome` are always written together, in
the same marker write — never a `head_sha` update with a stale `outcome`,
which is what would let a later reader believe a round covered a SHA it
did not (FR-005). This invariant is now trivially true: `report` is the
marker's *only* writer, and writes both fields in one call every time.

**Fingerprint values** reuse `wc_review_finding_fingerprint.py` (T028),
this repository's actual, currently-duplicable idiom — never a value the
reviewing agent supplies (constitution IX, FR-021). See T028's own module
docstring for why this is not spec 076's (unplanned) verbatim-anchor
scheme, which data-model.md originally (incorrectly) cited here.

## §2 — Review Round (ephemeral, one per workflow run)

Not persisted beyond `review_gate` above and the round's own PR/issue
comments; the concrete shape a run computes and threads between its own
jobs.

| Field | Type | Source |
|---|---|---|
| `pr_number` | integer | Selection step |
| `head_sha` | string | Fresh `gh pr view --json headRefOid` (D5) |
| `round_number` | integer | `review_gate.round + 1` |
| `findings` | array of Finding (§3) | Reviewer step's fenced block (D3), schema-validated |
| `outcome` | enum (§1) | Deterministic: `findings` empty → `clean`; reviewer step failed/timed-out/rate-limited → `failed`; else `findings` |

## §3 — Finding (reused schema, no new shape)

`.github/schemas/board-review-finding.schema.json`, unmodified (FR-010:
"the same shape the pipeline's existing review findings already use"):

```json
{
  "title": "string, ≤120 chars, no control chars",
  "what": "string",
  "evidence": {"file_paths": ["string", "..."], "detail": "string (optional)"},
  "in_scope": true,
  "fingerprint_basis": {"file_path": "string", "gate_or_artifact": "string"}
}
```

`in_scope: true` → folded (D11, into `wing-commander-fold-commit`'s
tasks.md section). `in_scope: false` → filed
(`wing-commander-durable-failure-issue`, body-prefixed `Found by the code
review of #<N>.`, FR-019). Neither disposition is decided by the
reviewing agent past this field — `in_scope` itself comes from the
reviewer's own diff-vs-file-touched comparison, and the *disposition* of
`in_scope` (fold vs. file, once/not-twice) is D11's deterministic step,
never the agent's further judgment (constitution IX).

## §4 — Readiness Decision (`lifecycle_readiness.py`, ephemeral)

```python
@dataclass
class LifecycleReadinessDecision:
    ready: bool
    checks_green: bool
    gate_suite_green: bool
    mergeable: bool          # new relative to board_readiness.py (D5)
    not_yet_reviewed: bool   # new relative to board_readiness.py (D5)
    kill_switch_clear: bool
    unmet_reason: str | None  # the first False condition's name, or None
```

`ready` is the conjunction of all five. `unmet_reason` is never derived by
narrating which condition failed in prose from an agent — it is the first
failing field's own name, a plain deterministic lookup (constitution IX).

## §5 — Merge Precondition Decision (`lifecycle_merge_preconditions.py`, ephemeral)

```python
@dataclass
class LifecycleMergePreconditions:
    may_merge: bool
    readiness: LifecycleReadinessDecision   # §4, re-derived fresh
    round_clean: bool         # review_gate.outcome == "clean" at this head_sha
    zero_open_findings: bool  # review_gate.findings_open == 0
    no_unresolved_human_review: bool  # no CHANGES_REQUESTED from a non-bot author
    unmet_reason: str | None
```

`may_merge` is the conjunction of `readiness.ready` and the three
additional fields. FR-027's "state which condition failed" reads
`unmet_reason` directly — never re-derives it from `may_merge` alone,
which loses which specific condition tripped.

## §6 — Fold Commit (composite input/output shape, `wing-commander-fold-commit`)

| Input | Type | Notes |
|---|---|---|
| `token` | string | App-scoped push token |
| `spec-dir` | string | e.g. `specs/062-lifecycle-review-gate` |
| `section-file` | path | Pre-rendered Markdown, one tasks.md section |
| `fold-id` | string | Commit-message id — a leg id (pr-conversation caller) or `review-gate-round-<N>` (this gate) |
| `fold-summary` | string | One-line commit-message summary |
| `actor-login` | string | Unioned into `pending_re_review_from` |

| Output | Type | Notes |
|---|---|---|
| `folded` | boolean | `false` if `section-file` was empty — nothing committed |
| `commit-sha` | string \| empty | The fold commit, when `folded: true` |

This is the single home FR-017/FR-035 require: `pr-conversation.yml`'s
`act` job and this gate's own fold step are its only two callers, and
neither performs the append/flip/commit sequence any other way.

## §7 — Fold Dispatch (composite input/output shape, `wing-commander-fold-dispatch`)

| Input | Type | Notes |
|---|---|---|
| `token` | string | App-scoped dispatch token |
| `spec-dir` | string | |
| `issue` | integer | Lifecycle issue number |
| `base-sha` | string | The branch tip captured before folding began |

| Output | Type | Notes |
|---|---|---|
| `dispatched` | boolean | `false` if the tip did not move from `base-sha` |
| `new-iteration` | integer \| empty | `spec-meta.json.iteration + 1`, when dispatched |

## §8 — Repository variables (new)

| Variable | Family | Default | Effect |
|---|---|---|---|
| `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` | `WING_COMMANDER_*_PAUSED` kill switch | unset (`!= 'true'`, i.e. not paused) | Stops review *and* merge (FR-034) |
| `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` | Feature enable switch | unset (`!= 'true'`, i.e. off) | Authorizes the merge step alone (FR-024); review still runs and reports when off (FR-025) |
| `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL` | Model-tier override | `claude-sonnet-5` | The reviewer's declared model (constitution II, FR-009) |

## §9 — Entity relationships

```text
Lifecycle Issue (#N)
  ├─ review_gate marker (§1, T074) ──┐  (wc_lifecycle_review_marker.py; the
  │                                  │   issue's own comments, never a commit)
  └─ spec-meta.json
       ├─ iteration ──────────────┐  (unchanged field, read by §7)
       └─ pending_re_review_from  │  (unchanged field, written by §6)
                                   │
Lifecycle PR (final implementation PR, stage: review)
  └─ head_sha ── evaluated by ──> Readiness Decision (§4)
                                   │
                                   ├─ ready=true ──> Review Round (§2)
                                   │                   │
                                   │                   ├─ clean ──> pass status (FR-013) + optional merge (§5)
                                   │                   └─ findings ──> per Finding (§3):
                                   │                        in_scope=true  ──> §6 (fold) ──> §7 (dispatch)
                                   │                        in_scope=false ──> durable-failure-issue (file)
                                   └─ ready=false ─> unmet_reason stated, no round spent
```
