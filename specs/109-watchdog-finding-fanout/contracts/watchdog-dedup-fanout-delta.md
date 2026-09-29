# Contract Delta: Watchdog Job Contract (`watchdog.yml`, `implement.yml`)

This is a delta against `specs/015-pipeline-watchdog/contracts/
watchdog-workflow.md` as already amended by `specs/024-watchdog-precision-
hardening/contracts/watchdog-spec-amendments-delta.md`, which remains the
base contract. Only the clauses below change; the trigger contract, the
`collect` job's five-collector attribution invariant, and the `diagnose`
evidence-validity gate are unchanged.

## `collect` — one new collector, `Collect: cycle outcome`

**Current contract** (015/024): Five deterministic collector steps
(execution-output, branch-drift, spec-meta, step-summary, annotations),
each an empty-is-success attribution-guarded read.

**Amended contract**: A sixth collector, `Collect: cycle outcome`,
downloads the `wing-commander-cycle-outcome` artifact the inspected run's
`implement.yml` job uploaded (same `gh run download` mechanism, same
attribution guard, as `collect-execution-output`). Its two effects:

1. It records the run's `{converged, handoff, gate-suite-outcome,
   gate-suite-first-failure}` state for `triage`'s FR-009 condition
   (below) — not a `Signal`, never seen by `diagnose`.
2. When `gate-suite-outcome == "fail"`, it appends one `gate-suite-failure`
   signal to `signals.json` (data-model.md), visible to `diagnose` exactly
   like every other collector's signals, and citable in its structured
   output the same way.

A missing artifact (inspected run predates this feature, is not an
implement run, or the upload itself never happened) is a successful empty
contribution — no cycle-outcome state, no `gate-suite-failure` signal —
never a step failure.

## `implement.yml` — one new step, `Record cycle outcome for watchdog`

**New contract clause** (this feature introduces `implement.yml` into the
watchdog's contract surface for the first time — it was previously only a
*subject* the `spec-meta`/`branch-drift` collectors read state about, never
a producer of an artifact `watchdog.yml` consumes): immediately after
"Read back cycle outcome" (both the `(cycle)` and `(retry)` legs), a new
step uploads:

```json
{"converged": <bool>, "handoff": <bool>,
 "gate-suite-outcome": "pass"|"fail"|"skipped",
 "gate-suite-first-failure": <string|null>}
```
as artifact `wing-commander-cycle-outcome`. This step runs whenever "Read
back cycle outcome" ran (`always()`-adjacent to it, mirroring how
`Persist triage decision` in `watchdog.yml` already runs whenever its
sibling ran) — it never gates or fails the `implement` job; an upload
failure here is invisible to `implement.yml`'s own success/failure and is
simply a future `collect-cycle-outcome` empty contribution.

## `triage` — one new pre-fingerprint branch (FR-009); dedup search reads back accumulated ids; multi-match is named, not `data-integrity`

**Current contract** (015/024):
```
2. Evidence validity gate
3. Fingerprint: sha256(class + "|signals:" + sorted-joined(valid cited signal ids))
4. Dedup lookup: gh issue list ... --json number,state,body,
   local jq filter for the exact fingerprint marker.
   Outcomes: none | match-open | match-closed | unknown | data-integrity.
```

**Amended contract**:
```
2. Evidence validity gate (unchanged)
3. Fingerprint (unchanged: still the exact-citation-set hash — kept for
   the closed-issue exact-match path, FR-006/FR-015)
3a. NEW — gate-suite filing condition (FR-009/FR-010): if every one of
    this finding's valid cited ids has kind gate-suite-failure, AND the
    Collect: cycle outcome state is present with converged=false and
    handoff=false, AND neither spec-meta stage nor the stalled label say
    this cycle stalled: outcome=converging-gate-suite. Suppresses filing;
    does NOT run steps 4-5 below; reported under its own wording, never as
    data-integrity or unknown.
4. Dedup lookup: gh issue list --repo <repo> --label pipeline-defect
   --label "🐕 · <class>" --state all --limit 200
   --json number,state,body,comments   <- comments is NEW
   a. count == 200 -> outcome=unknown (NEW: truncation guard, FR-016)
   b. else: exact fingerprint marker match in .body -> match-open/match-closed
      (unchanged mechanism and priority: an exact hit is still checked
      first and still reopens a closed issue on its own, independent of
      overlap)
   c. else: compute each OPEN candidate's matchable id set (data-model.md:
      union of body + comment signal-ids= markers, capped at 30 most
      recent distinct ids) and intersect with this finding's cited ids
      -> outcome=overlap, issue-number=lowest-numbered intersecting
      candidate, other-matches=the rest (NEW)
   d. else -> outcome=none
```

## `act` — writes the new readable marker; multi-match names other issues; converging-gate-suite is report-only

**Current contract** (015/024):
```
none          -> create issue (fingerprint marker only)
match-open    -> comment on matched issue
match-closed  -> reopen + comment
unknown       -> suppress; report "dedup lookup failed..."
data-integrity -> report only, no auto action
```

**Amended contract**:
```
none               -> create issue: body carries BOTH the unchanged
                       fingerprint=<hash> marker AND a new
                       signal-ids=<cited ids> marker (data-model.md)
overlap            -> comment on the lowest-numbered matched issue only;
                       comment carries a signal-ids=<cited ids> marker,
                       states which ids matched and which are new
                       (FR-017), and names any other-matches by number
                       (FR-007) -- those issues are never written to
match-closed       -> unchanged (reopen + comment), comment gains the
                       same signal-ids= marker
converging-gate-suite (NEW) -> no write; reported to the lifecycle issue
                       under its own wording (FR-011), distinct from
                       "suppressed: invalid evidence" and "dedup lookup
                       failed"
unknown            -> unchanged
data-integrity     -> unchanged (still reserved for >1 EXACT-fingerprint
                       match, which stays an anomaly under overlap
                       matching too -- two issues should never carry the
                       identical hash)
```

No issue is ever closed, merged, or relabeled by any branch above — the
watchdog's remediation surface stays exactly the single
create/comment/reopen action spec 024's FR-014 established; this feature
widens *which* existing issue a comment lands on, never *what kind* of
write occurs.

## Removed entirely

Nothing. This feature is purely additive to the job contract (a new
collector, a new pre-fingerprint branch, a widened dedup read, a new
marker, a new outcome) — no existing step, outcome, or workflow input is
deleted.

## Unchanged

- `verify-image-prerequisites`, `report-unhandled-failure` jobs.
- The evidence-validity gate, the fingerprint formula itself, the
  exact-match closed-issue reopen path, `data-integrity`'s meaning (still
  reserved for >1 exact-fingerprint hit).
- Self-dispatch-depth check, pause switch, coexistence check
  (`alreadyHandledBy`) — all still gate the same single write path, now
  with two more outcome values (`overlap`, `converging-gate-suite`)
  flowing through it.
- Cross-class behavior: matching still never crosses the `🐕 · <class>`
  label filter (FR-001, FR-012); no finding of one class is ever compared
  against, or attached to, an issue of another class.
