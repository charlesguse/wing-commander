# Data Model: A Stall Holds Until a Maintainer Re-Admits It

This feature adds no persistent storage and no new marker fields (FR-019
keeps the board-item-marker schema unchanged). "Entities" here are the
values and determinations the resume step resolution and readiness's
stand-down gating compute and consume — restated from the spec's Key
Entities section at implementation altitude.

## Stall Site

An arm of a job that records a `stalled` board-item marker. Not new to this
feature (FR-001-005 are preserved invariants — research.md D1); restated
here because FR-004's derivation and FR-006/007's rule both range over the
same set.

| Field | Value | Source |
|---|---|---|
| job | one of `triage`, `route`, `fix`, `review`, `readiness` | the job that stalls |
| line | `board-loop.yml:1427`/`1906`/`2263`/`2467`/`3306`/`3311`/`3319`/`3913` | current `main` |
| stalls from | the marker step the job was executing when it stalled (`triage`'s handover has no prior step; `route`'s spec verdict; `fix`'s gate-red and post-push breach; `review`'s parse-failed/malformed-findings/budget-spent; `readiness`'s backstop breach) | derived, not hand-listed (FR-004) |
| reviewed-head resolvable? | `review`'s budget-spent arm and `readiness`'s breach arm: yes (a review converged into this state); every other arm: no (stalled before or during an inconclusive review) | governs FR-006b's default |

No new fields are added to this table by this feature; it is a restatement
for traceability between FR-004's enumeration and FR-006's rule.

## Re-admission Rule (FR-006/FR-006a/FR-006b)

The stated function resume's clause 2 (`pr_from_fallback`) now computes.

| Field | Type | Description |
|---|---|---|
| `marker_step` | string or null | the label-less `stalled` marker's own step field (always `"stalled"` once a marker exists at all — carried here for the `breach`-marker carve-out check, which reads the *pre-stall* marker only for the #530 case; a `stalled` marker never itself equals `BREACH_STEP`) |
| `pr_from_fallback` | bool | true when clause 1 found no marker-named PR but the FR-007 (spec 061) label fallback recovered an open `board:owned` PR citing the issue |
| `head_moved_since_last_review` | bool | D3's live-state determination; defaults `True` when unresolvable |
| resolved `step` | `"breach"` \| `"review"` \| `"readiness"` | `breach` marker → `"breach"` (unconditional, #530); else `head_moved_since_last_review` → `"review"`; else `"readiness"` |

Precondition (FR-007): only evaluated for an **open** issue (D7 — closed/
disposed issues never reach `select()`'s candidate set at all).

## Reviewed-Head Determination (FR-006b)

The one shared computation this feature builds and spec 093 later consumes
(research.md D3). Not a stored entity — computed fresh each time it is
needed.

| Input | Source |
|---|---|
| PR head commit timestamp | `gh pr view <pr> --json headRefOid,commits` (live) |
| last review-round verdict comment for this PR | `comments_by_issue` (already fetched by the `select` job for `read_marker`), filtered to the loop's own bot-authored comments matching the existing round-outcome wording (research.md D3 step 2) |
| output | `head_moved: bool` — `True` if no comparable comment is found, the PR lookup fails, or the comment is absent; `True` if the head commit postdates the comment; `False` only when a comment is found and postdates (or ties) the head commit |

Consumers: this feature's resume clause 2 (D2); spec 093 FR-007, when that
feature plans, reuses this same computation rather than deriving a second
one (CLAUDE.md "shared logic has exactly one home").

## Re-admission Budget (FR-009)

Not a new stored value — the existing `round` field on the marker, already
`0` for every `stalled` marker (research.md D4). Restated as a checked
invariant: a re-admitted item resuming at `review` starts with
`steps.select.outputs.round == "0"`, the same starting value a freshly
selected item gets.

## Run Summary Record (FR-011)

A `GITHUB_STEP_SUMMARY` line, written at three call sites, reusing the
summary-writing idiom readiness's stand-down already established (#782):

| Site | Line content names |
|---|---|
| resume (`select` job) | that the item was re-admitted from a stall, which clause resolved it (`review`/`readiness`/`triage`), and — for `review`/`readiness` — whether the head had moved |
| a stall site's retry (post FR-002 failure) | that this run is a retry of a previously failed label application, and the item, issue, and step it re-attempted |
| readiness stand-down | already exists (#782) — unchanged by this feature |

## Stand-down Answer (FR-012-015)

Unchanged by this feature (invariant, research.md D1) — restated for
completeness: the stop check's `paused` output, re-checked immediately
before readiness's own durable writes, already gates every one of them.
