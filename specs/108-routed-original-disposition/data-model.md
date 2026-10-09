# Data Model: Routed-Original Disposition

This feature adds no new persistent store — GitHub issues, labels, and
comments remain the sole durable state (per research.md's Storage: N/A).
It extends three existing entities and adds one new label value.

## Originating Issue (extended)

Defined in spec.md's Key Entities. Fields relevant to this feature, as
tracked by GitHub itself:

| Field | Before this feature | After this feature |
|---|---|---|
| `state` | stays `OPEN`, gains `board:stalled` | closed (`state_reason: duplicate`) at disposition time (FR-001) |
| `labels` | gains `board:stalled` | gains `disposition:duplicate` (D1); does **not** gain `board:stalled` at these three sites |
| newest board-item marker | `{"step": "stalled", ...}` | `{"step": "duplicate", "spec_request": <int>, ...}` (see Board Item Marker below) |
| cross-link comment | none pointing back from this issue | unchanged: still receives the `wing-commander-outstanding-task-item` "Routed to spec-request" checklist item (D5) |
| disposition comment | none | one comment stating the reason ("Closed as a duplicate of #<spec-request>") and linking the counterpart (FR-003) |

Re-admission (FR-006): an issue in this state that a maintainer reopens
re-enters GitHub's `OPEN` set with `disposition:duplicate` and its
`step: "duplicate"` marker still present. See Eligibility contract changes
below for how `board_eligibility.is_excluded()` treats that combination.

## Spec-Request (extended)

Defined in spec.md's Key Entities. New field:

| Field | Before | After |
|---|---|---|
| reciprocal link | none (only the prose footer "Originating issue: <url>" inside its body) | one `wing-commander-outstanding-task-item` checklist-item comment linking back to the originating issue (D5, FR-004) |
| closure notice (FR-017) | n/a | when this issue closes without its linked `spec-meta.json` reaching the finalize stage's terminal value, one idempotent notice comment is posted on it stating the same fact the originating issue's notice states |

## Disposition (new entity, per spec.md's Key Entities)

Not a GitHub object of its own — the durable state it produces IS the
Originating Issue's `state`/`labels`/marker/comment fields above, plus the
Spec-Request's reciprocal link. Modelled here only to name its inputs and
the idempotency contract:

- **Inputs**: originating issue number, spec-request issue number/URL, a
  human-readable reason string.
- **Invariant (FR-009)**: applying a Disposition whose originating issue
  already carries `disposition:duplicate` AND is already `CLOSED` is a
  no-op success — no second close call, no second label-add, no second
  comment on either issue.
- **Partial-failure invariant (FR-010/FR-011)**: a Disposition MUST NOT run
  at all unless its spec-request was filed successfully (the existing
  create-guard at each site already enforces this — D3 does not change it).
  If the Disposition itself fails after the spec-request exists, the
  originating issue is left in whatever state the failed attempt reached
  (open, or closed-but-not-yet-labelled/commented) — never with the
  spec-request as its only record and no trace on the originating issue.
  The next run's own idempotency pre-check (D4) picks up wherever the
  previous attempt stopped, rather than re-filing a second spec-request.

## Board Item Marker (extended)

`board_item_marker.py`'s marker JSON gains one new key, written only by the
disposition operation:

```json
{"step": "duplicate", "round": 0, "pr": null, "branch": null,
 "base_sha": null, "spec_request": 1234}
```

- **`step: "duplicate"`**: a new terminal step name, added to
  `board_eligibility.TERMINAL_STEPS` alongside `"closed"`/`"stalled"`/
  `"proven"` — defence in depth so `in_flight_candidate()` never treats a
  disposed issue as in-flight even if it were ever queried while still
  technically open (it never is, in the steady state, since `state ==
  CLOSED` already excludes it first).
- **`spec_request`**: the linked spec-request's issue number. The one new
  field the re-admission carve-out (research.md D6) reads: on an OPEN issue
  carrying `disposition:duplicate` whose newest marker has `step ==
  "duplicate"`, the carve-out resolves this number's current `state` live
  (never trusts a cached value, matching `write_marker()`'s own documented
  "fast path only, re-derived from live GitHub state" rule) and re-admits
  only when it resolves `CLOSED`.
- All five existing keys (`step`, `round`, `pr`, `branch`, `base_sha`) keep
  their current meaning and callers; `spec_request` is additive and only
  ever populated by the disposition write, so every existing
  `read_marker`/`read_marker_with_timestamp` caller that does not look for
  it is unaffected (`json.loads` tolerates the extra key; no caller
  validates the key set is exact).

## New label

| Label | Applied to | Applied when | Cleared by |
|---|---|---|---|
| `disposition:duplicate` | the originating issue | disposition (FR-001), at all three spec-request sites (FR-002) | never programmatically — GitHub does not clear labels on reopen; a disposed-and-reopened issue keeps this label, and the eligibility carve-out (D6) is what lets it become selectable again despite that |

This is a new row in `docs/setup.md`'s manual label table (the same table
`board:stalled`'s row lives in), created the same way that table already
documents labels — no `.github/labels.yml` or other machine-readable label
config is introduced (matching spec 057's own decision on this point,
carried forward rather than revisited).
