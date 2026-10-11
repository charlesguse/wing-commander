# Contract: Not-Ready Hold, Count, and Handover

This is this feature's own contract — no single existing contract spans
`board_eligibility.py`, `board_readiness.py` and `board_item_marker.py`
together. It extends
`specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`,
`specs/057-autonomous-board-loop/contracts/readiness-report.md` and
`specs/061-marker-owned-in-flight/contracts/in-flight-detection.md` — read
those first. FR-014 requires those documents (plus
`specs/061-marker-owned-in-flight/contracts/resume-recovery.md`) to be
corrected in place where they state the superseded behaviour; this
document is the canonical statement the corrections point at.

## `.github/scripts/board_readiness.py` (addition)

```python
def evaluate_from_snapshot(snapshot, open_in_scope_findings, backstop_holds,
                            kill_switch_paused):
    """... (unchanged conditions) ...
    Adds "unmet_class" to the returned dict: "self-clearing" when every
    rollup entry blocking checks_green is in a not-yet-concluded state
    (QUEUED, IN_PROGRESS, WAITING, REQUESTED, PENDING, EXPECTED -- a
    CheckRun's `status` when it has no `conclusion` yet), or every check
    is green and only the lint-workflows CheckRun has not registered yet;
    "durable" for any other
    unmet reason (a terminal failing check state, an empty rollup, an
    open finding, a backstop breach, or the kill switch), and null when
    ready. FR-005: derived only from the rollup's own per-entry states,
    never from an agent's reading of them."""
```

## `.github/scripts/board_eligibility.py` (additions)

```python
NOT_READY_THRESHOLD = 3  # spec.md Assumptions — a value, not a mechanism.

def not_ready_record(marker):
    """Returns {"pr": int, "head_sha": str, "class": "self-clearing"|"durable",
    "count": int} from `marker`'s nr_count/nr_head_sha/nr_class/pr fields,
    or None when marker is None, step != "readiness", or any of the three
    nr_* fields is missing/malformed (FR-011 fail-safe: degrade to "no
    record", never guess)."""

def _not_ready_holds(marker, pr_state_by_number, pr_head_sha_by_number,
                     number=None, passed_over=None):
    """FR-001/FR-004(b)/FR-005/FR-011. Both selection paths call it with
    the issue `number` and their `passed_over` dict, into which it records
    not_ready_hold_reason()'s reason for a held item (FR-011's record of
    why, made where the decision is). True (held) when not_ready_record(marker)
    is not None, its class is "durable", and pr_head_sha_by_number.get(pr)
    either is missing (unresolvable this run) or differs from... no --
    EQUALS head_sha (unchanged head holds; an unresolvable head_sha is the
    fail-safe and ALSO holds, per FR-011: "unreadable... MUST degrade to
    the fail-safe (pass the item over...), never to admitting"). False
    otherwise -- including a self-clearing record (never held, FR-005) and
    a durable record whose head has moved (re-admitted, not merely
    un-held -- resume's step resolution decides review vs. readiness, not
    this predicate). Also True for a readiness marker that names an
    nr_class but whose record does not parse (FR-011: passed over, never
    admitted). Never True for a PR known CLOSED or MERGED, or absent from
    a supplied pr_state_by_number (select's lookup 404'd: it can never
    close or move)."""

def not_ready_head_moved(marker, pr_head_sha):
    """FR-007/SC-010. True when marker carries a not-ready record of either
    class and the known live head differs from the record's: for a durable
    record, the end of the hold (re-admission); for a self-clearing one,
    new commits no review covered. Either way the item resumes at review.
    The resume step calls this instead of comparing head SHAs itself
    (FR-003)."""

def not_ready_handover_due(nr_count):
    """FR-004(a). True when nr_count >= NOT_READY_THRESHOLD."""

def is_not_ready_handover(marker): ...   # the D7 stalled marker naming a pr
def marker_names_live_pr(marker): ...    # FIX_OR_LATER step, or the above:
                                         # select looks that PR up, so an
                                         # unowned (taken-over) PR holds
```

`in_flight_candidate()` gains one more skip condition alongside its
existing `TERMINAL_STEPS`/`prove`/`AWAITING_MERGE_STEP` checks: a
`readiness` marker for which `_not_ready_holds()` is true is excluded from
the candidate list, exactly where `_awaiting_merge_holds()` is consulted
today for `select()`'s fallback (`in_flight_candidate()` itself does not
call `_awaiting_merge_holds()`/`_unowned_open_pr_holds()` because the
plain `pr_state_by_number.get(pr) == "OPEN"` test already excludes those
cases there — `_not_ready_holds()` cannot reuse that shortcut because an
open, durable, unmoved-head PR is exactly the case that must be excluded
despite `pr_state_by_number.get(pr) == "OPEN"` being true, so
`in_flight_candidate()` calls `_not_ready_holds()` explicitly). `select()`'s
oldest-first fallback calls the same predicate, mirroring its existing
`_awaiting_merge_holds()`/`_unowned_open_pr_holds()` calls — one decision,
both paths (FR-003/FR-004).

## `.github/scripts/board_item_marker.py` (additions)

```python
def write_marker(step, round, pr, branch, base_sha,
                  nr_count=None, nr_head_sha=None, nr_class=None, nr_reason=None):
    """Unchanged shape, four new optional trailing fields serialized only
    when not None (an absent field, not a null-valued one, keeps old
    markers and new no-not-ready-record markers byte-identical in every
    field that already existed)."""
```

Two readers join it: `same_not_ready_comment_id(comments, bot_login, pr,
head_sha, unmet_reason)` (FR-009's match, below) and `directed_carry(comments,
bot_login)` (the pr and not-ready count a directed review carries).

`main()`'s CLI gains `--nr-count`, `--nr-head-sha`, `--nr-class`,
`--nr-reason` (the unmet condition, FR-002), each
optional and independent of `--step`. `add_stalled_label()`'s own
docstring is NOT changed by this feature (research.md D7, D10) — that
canonical statement is spec 100's (#752) to update when it generalizes
the review/readiness split to every stall site; this feature's own
handover call site instead documents its own `--pr`/`--nr-head-sha` usage
inline, pointing at this contract rather than restating the rule
(CLAUDE.md).

## `.github/workflows/board-loop.yml` (deltas)

### `select` job — PR lookup

The existing per-PR `gh api repos/:owner/:repo/pulls/:number` call (the
one `pr_numbers_to_check` loop already makes for every `FIX_OR_LATER_STEPS`
marker) additionally extracts `.head.sha` into a parallel
`board-pr-head-sha-by-number.json`, folded into the `board_eligibility.py`
stdin payload as `pr_head_sha_by_number` (research.md D4) — no new `gh`
call.

### `select` job — resume step

The resume step's clauses for this feature are canonical in
`specs/061-marker-owned-in-flight/contracts/resume-recovery.md`, clauses
0.5a (this feature's own stalled handover marker, its PR open: readiness on
a head unmoved since the last converged review, else review with the round
advanced by one) and 0.5b (a readiness marker with a not-ready record of
either class whose head moved: review, round + 1). A handover whose PR was
merged or closed since falls to a fresh triage. The round a re-admission
resumes at is `board_eligibility.readmission_round()`. The not-ready count
belongs to one PR: resume carries it only while the item stays on the PR
the marker names (a fallback-recovered other PR, or a fix that cuts a new
one, starts it at 0). See that file; this one does not restate it.

The PR lookup above covers a handover marker's PR too
(`board_eligibility.marker_names_live_pr()`), so a PR a human took over
(board:owned removed) holds as unowned.

### `review` job — three marker-writing sites

1. "Post the converged/stalled outcome and marker" (`OUTCOME = converged`):
   adds `--round "$ROUND"` (research.md D6) and `--nr-count
   "$NR_COUNT"` (carried through unchanged from `needs.select.outputs.nr-count`
   or this run's own prior value on a same-run handoff).
2. review-fixup-publish's "Advance the round" (`continue`; spec 095 moved
   the push and round advance out of the review job): adds
   `--nr-count "$NR_COUNT"`, carried through unchanged (the round already
   advances here; the not-ready count does not — only readiness's own
   not-ready outcome advances it, research.md D5).
3. "Post the converged/stalled outcome and marker" (`stall-reason` != "");
   these markers are `step=stalled` with no `pr` (unchanged — this
   feature's own handover is the one exception, and it is written by
   readiness, not review).

### `readiness` job — not-ready-report step

Reads the incoming `nr_count`/`nr_head_sha`/`nr_class` context (from
`needs.select.outputs.*` or `needs.review.outputs.*`, whichever produced
this run's readiness entry), computes `unmet_class` from `board_readiness`'s
extended decision (research.md D2), and:

- **`ready == 'true'`**: unchanged (`awaiting-merge` marker, no `nr_*`
  fields — moot once handed to a human, data-model.md).
- **backstop breach**: unchanged (FR-012 — this feature's hold/count/
  handover never applies to the backstop-breach path, which keeps its own
  terminal `spec-request` + `board:stalled` + `stalled` marker).
- **otherwise (the plain not-ready branch, today's bare "Not ready on PR
  #%s: %s" comment)**:
  1. `new_count = (carried-in nr_count or 0) + 1`.
  2. If `not_ready_handover_due(new_count)` (`new_count >=
     NOT_READY_THRESHOLD`, FR-004(a); the step asks board_eligibility.py
     and fails on no answer rather than re-deriving the comparison): apply
     `board:stalled` first (`add_stalled_label()`), then write a `stalled`
     marker carrying `--pr` and `--nr-head-sha` (research.md D7) — never a
     `readiness` marker in this branch. Post the FR-008 handover notice
     naming the unmet condition, the PR, the head SHA, and that removing
     the label is the sole re-eligibility condition. Fail the step loudly
     if the label add fails (unchanged pattern, `add_stalled_label()`).
  3. Otherwise: write a `readiness` marker carrying `--nr-count
     "$new_count"`, `--nr-head-sha` (this run's head), `--nr-class`
     (`unmet_class`), `--nr-reason` (the unmet condition), plus the
     unchanged `--pr`/`--branch`. Before posting the comment, compare
     `(pr, head_sha, unmet_reason)` against the newest loop marker's own
     `pr`/`nr_head_sha`/`nr_reason` (FR-009, never the comment's prose --
     `board_item_marker.same_not_ready_comment_id()`); on
     an exact match, edit THAT comment by its id
     (`PATCH /repos/:owner/:repo/issues/comments/:id`), updating its
     embedded marker to the new count, instead of appending a new one
     (research.md D8); otherwise post a new comment as today. The count
     and round reach this step from select or, on a same-run handoff, from
     review. (A directed review carries the marker's count into the
     converged marker it writes, which a later ordinary run reads.)
     A directed proof run (`directed-stage`) selects no board item: its
     not-ready outcome is reported, as before this feature, with no record,
     no count and no handover.
     The comment says what happens next: a durable outcome is held until
     the PR's head moves (a push re-admits it at review), a self-clearing
     one is picked up again on a later run.

`select` names every item a not-ready hold passed over, and why, in its
step summary, from `board_eligibility.py`'s own `not_ready_held` output
(FR-011). A PR known to be CLOSED or MERGED, or one select's lookup found
gone (404, no state), is never held; resume routes it
(a fresh triage, for a merged handover too: nothing in the job graph
consumes a bare prove resolution, `_merged_fix_holds()`, #532).

Every durable action above stays behind
`steps.killswitch-recheck.outputs.paused == 'false'`, unchanged (research.md
D9 — FR-006 needs no new gating, only a fixture proving it).

## Gate: `verify-board-eligibility.py` (Gate 81, extended — no new gate)

New fixture directories under
`.github/scripts/tests/board-eligibility/in-flight/`, each the same
four/five-file shape as the existing `awaiting-merge-*`/`breach-*` cases
(FR-013):

1. `not-ready-durable-unmoved-held` — a `readiness` marker with a durable
   not-ready record, `pr_state_by_number` OPEN, `pr_head_sha_by_number`
   equal to `nr_head_sha` → `(null, false)` from `in_flight_candidate()`;
   `select()` returns a second, newer eligible issue (mirrors
   `awaiting-merge-pr-open`'s two-file shape).
2. `not-ready-durable-moved-admitted` — same marker, but
   `pr_head_sha_by_number` differs from `nr_head_sha` → that issue, `false`
   (admitted, back in flight).
3. `not-ready-self-clearing-not-held` — a `readiness` marker with
   `nr_class: "self-clearing"`, head unchanged → that issue is still the
   in-flight candidate (never held, FR-005).
4. `not-ready-head-unresolvable` — durable record, PR absent from
   `pr_head_sha_by_number` (lookup failed) → held (fail-safe, FR-011), same
   shape as case 1.
5. `not-ready-two-held-one-eligible` — two separate held items plus a
   third eligible issue → the third is selected; neither held item
   blocks the other (US1 AS4).
6. `stalled-own-handover-unmoved` / `stalled-own-handover-moved` —
   resume-recovery cases (exercised by Gate 97, not Gate 81, since
   resume's step resolution lives in the workflow, not `board_eligibility.py`
   — listed here for cross-reference only).

## Gate: `verify-board-loop-resume-gating.py` (Gate 97, extended — no new gate)

New `RESUME_CASES` entries (FR-013):

- A `readiness` marker with a durable, unmoved-head not-ready record →
  `step = "readiness"` (unchanged from today, but now exercised with the
  new fields present rather than absent).
- The same marker with a moved head → `step = "review"`, `round` one past
  the marker's own `round` (research.md D6 continues the budget; each
  re-admission spends one round, SC-009), never `0`. A self-clearing
  record's moved head resolves the same way (SC-010).
- This feature's own `stalled` handover marker (`pr` + `nr_head_sha` set),
  its PR resolved OPEN by number and head unmoved since the last converged
  review → `step = "readiness"`.
- The same handover marker, head moved → `step = "review"`, round + 1.
- The same handover marker, its PR merged or closed since → `step =
  "triage"`, PR cleared.
- A `stalled` marker from any other stall site (`pr` absent) → `step =
  "review"`, unchanged (regression case, FR-015).

A self-test mutation (FR-013's "resume-gating gate's self-test... the
not-ready site's record write is dropped from the workflow") asserts Gate
97 fails when the not-ready-report step's marker write (or its
`board:stalled` handover branch) is removed from `board-loop.yml`.
