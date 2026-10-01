# Data Model: An Honoured Stop Records Its Stop Point

This feature adds no new storage and no new marker schema field — the
"data model" is: one new derived value (`stop-cause`), one new pure-function
return shape, and the existing entities it reuses unchanged. See research.md
D1–D12 for the reasoning behind each choice below.

## Entities

### Stand-down cause (new)

A derived enum, computed once per `wing-commander-board-stop-check`
invocation from live state. Not persisted anywhere as its own field — it
exists only as the composite's `stop-cause` output for the duration of one
job.

| Value | Meaning | Durable write? |
|---|---|---|
| `""` | Neither the kill switch, a closed issue, nor an authorized stop request applies. | none (`paused=false`) |
| `"closed-issue"` | `check-issue-closed=="true"` and the issue reads closed (the `prove` job's own extra pre-check, FR-053). Takes priority over a stop request that may also be present. | none (FR-013) |
| `"kill-switch"` | The repository-wide kill switch is set, and neither of the above applies. | none (FR-011) |
| `"stop-request"` | `find_stop_request()` returns `stand_down=true` (an authorized, unactioned stop command exists after baseline). Takes priority over the kill switch (FR-012: honoured even when both are set). | the Stop Point Record (below) |

Priority order (closed-issue > stop-request > kill-switch > none) is fixed
and computed as a single ordered check — see research.md D3.

### Stop Command Comment (new derived fact, not a new stored entity)

The specific issue comment `find_stop_command_comment(comments,
current_run_id, bot_login)` identifies as the one that makes `stand_down`
true: the newest comment at or after the existing baseline whose author's
`author_association` is in `{OWNER, MEMBER, COLLABORATOR}` and whose body
satisfies `is_stop_command()`. `current_run_id` is required (maintainer
review fold leg-1, FR-006/FR-008 — see research.md D1's addendum): no
`**Run:**` marker carrying the SAME run id may advance the baseline, since
this run's own stop-point record is exactly such a marker, and letting it
advance the baseline would undo an already-honoured stop for the rest of
the run.

Fields consumed from it (all already present in, or newly added to, the
composite's existing `gh api .../comments` fetch):

| Field | Source | New? |
|---|---|---|
| `body` | existing `--jq` projection | no |
| `author_association` | existing `--jq` projection | no |
| `created_at` | existing `--jq` projection | no |
| `user.login`, `user.type` | existing `--jq` projection | no |
| `html_url` | added to the `--jq` projection (research.md D9) | **yes** |

Derived from `body` via the new `stop_command_reason(body)`: the free text
the maintainer wrote after the stop command token on its own line (empty
string when the stop command carried no reason, e.g. a bare `stop.`).

This is never stored — it is recomputed from the same comments fetch every
time a job reaches its stop check, exactly as `find_stop_request()` itself
is recomputed every time (no caching, no separate record of "which comment
won" persists independently of the Stop Point Record's own comment body).

### Stop Point Record (new durable artifact)

The durable consequence of an honoured stop request. Composed of exactly
the same two primitives every other board-loop stall site already uses —
no new primitive, no new marker field:

1. **The `board:stalled` label** (`board_eligibility.STALLED_LABEL`),
   applied via `add_stalled_label()` before anything else durable is
   written (existing `#604` ordering rule, reused verbatim).
2. **A `stalled`-step Board Item Marker** (unchanged shape — see below),
   carrying the item's branch and base commit (when known) and dropping
   `pr` and `round` — via the existing `write_marker()`/`board_item_
   marker.py --step stalled` CLI, called with `--branch`/`--base-sha` set
   from the caller-supplied `marker-branch`/`marker-base-sha` composite
   inputs (empty for triage/route, populated for fix/review/readiness).
3. **A human-legible comment** (research.md D9) naming the cause ("a
   maintainer stop request"), linking the Stop Command Comment via its
   `html_url`, reproducing its reason (if any) inertly via
   `fenced_section()`, and stating the release condition ("remove
   `board:stalled`"). This comment's body ends with the marker from (2), so
   it is simultaneously the human-legible record and the machine-readable
   one (FR-044's existing "never marker-only" rule, unchanged).

No new label namespace, no new marker step name, no new JSON field. "The
reason: stopped by maintainer request" (FR-003) is prose in (3), never a
machine field — mirroring how every existing stall site's reason lives in
its comment text, not in the marker JSON.

**Validity / uniqueness**: at most one Stop Point Record is written per
honoured stop, enforced by a fresh label read immediately before writing
(research.md D5/D6) — if `board:stalled` is already present, no write
happens (whatever caused it — this run's own earlier write, or an
unrelated existing stall — is left as is).

**Lifecycle**: created when `stop-cause == "stop-request"` and no
`board:stalled` label yet exists; released when a maintainer removes
`board:stalled` (unchanged existing act, per FR-003 and spec 100); which
step a released item resumes at is decided by spec 100's FR-006/FR-006b,
out of scope for this feature (spec 097 only has to leave the marker in the
shape spec 100's resume rule already expects: `stalled`, no `pr`, no
`round`, present or absent `branch`/`base_sha`).

### Board Item Marker (existing, unchanged schema)

```json
{"step": "stalled", "round": 0, "pr": null,
 "branch": "<name>" | null, "base_sha": "<sha>" | null}
```

(`.github/scripts/board_item_marker.py:139-155`, `write_marker()`.) This
feature writes this exact existing shape via the exact existing CLI
(`board_item_marker.py --step stalled ...`) — it adds no field. The `round`
value is always `0` for a stop-point record (the CLI's own default when
`--round` is omitted), matching FR-010's "the review round MUST NOT be
preserved."

### Board item marker → JSON test fixture correspondence (Gate 135)

Gate 135's eligibility-level check (research.md D7 item 3) constructs an
issue fixture of this shape and feeds it through the existing, unmodified
`board_eligibility.is_excluded()` / `in_flight_candidate()` / `select()`:

```json
{
  "number": 402,
  "state": "OPEN",
  "labels": [{"name": "board:stalled"}],
  "createdAt": "2026-01-01T00:00:00Z"
}
```

with a companion bot comment whose marker is
`{"step":"stalled","round":0,"pr":null,"branch":null,"base_sha":null}` (or
with `branch`/`base_sha` populated, for the mid-fix variant) — proving
SC-001 ("selected by zero of the next ten runs") from the real selection
code rather than by inspection.

## Relationships

```text
wing-commander-board-stop-check (composite)
  ├─ inputs: token, cancel-token, issue-number, bot-login,
  │          initial-paused, check-issue-closed (unchanged),
  │          marker-branch, marker-base-sha (NEW, optional)
  ├─ calls board_stop_check.find_stop_request()        (unchanged)
  ├─ calls board_stop_check.find_stop_command_comment() (NEW)
  ├─ calls board_stop_check.stop_command_reason()       (NEW)
  ├─ on stop-cause == "stop-request":
  │     calls board_item_marker.add_stalled_label()     (existing, reused)
  │     calls board_item_marker.write_marker()          (existing, reused)
  │     posts a comment (fenced via board_spec_request_body.fenced_section, existing, reused)
  └─ outputs: paused (unchanged), stop-cause (NEW)

board-loop.yml (6 call sites: triage, route, fix, review, readiness, prove)
  ├─ passes marker-branch/marker-base-sha from needs.select.outputs.branch/base-sha
  ├─ reads stop-cause to word its own stand-down message (FR-014)
  └─ emits one always() "Record run outcome" metrics-summary step per job,
     whose run-label reflects stop-cause when non-empty
```

No change to `board_eligibility.py` (is_excluded/in_flight_candidate/
select already correctly exclude any `board:stalled` item — that is the
existing behaviour this feature relies on, not new behaviour it adds).
