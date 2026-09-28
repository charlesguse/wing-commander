# Phase 0 Research: Run-Stamped Cost Attribution

spec.md carries no `[NEEDS CLARIFICATION]` markers — both clarification
sessions (2026-09-25, 2026-09-28) are already encoded. What remains for
this phase is mechanical design against the actual shape of
`.github/actions/wing-commander-metrics-summary/action.yml`,
`.github/actions/wing-commander-metrics-persist/action.yml`, and
`.github/workflows/watchdog.yml`'s `collect-cost-report` step, none of
which spec.md commits to (by design — it describes the observable
contract, not the implementation).

## R1: The metrics record key widens to `run_id:attempt:job_key:step_index`, attempt inserted second

**Decision**: `RECORD_KEY="${RUN_ID}:${RUN_ATTEMPT}:${JOB_KEY}:${STEP_INDEX}"`
in `wing-commander-metrics-summary/action.yml` (today:
`"${RUN_ID}:${JOB_KEY}:${STEP_INDEX}"`, action.yml:245).
`RUN_ATTEMPT` reads `github.run_attempt` — already ambient, no new lookup
(spec.md Assumptions). The `run` object in the emitted record gains a
sibling field, `run_attempt` (string, matching `workflow_run_id`'s own
`--arg`-sourced string type), alongside the unchanged
`workflow_run_id`/`job_key`/`job_id`/`step_index`/`record_key`.

**Rationale for inserting attempt second, not last**: FR-002 requires the
collector to match "on the run-identity portion of that key — the
workflow run id together with the attempt number." Placing `attempt`
immediately after `run_id` makes that portion a clean, order-independent
prefix (`run_id:attempt`) that a collector can split off with one
`cut -d: -f1-2` or one jq `split(":")[0:2]` — no dependency on `job_key`
or `step_index` never containing a colon. Appending attempt last would
make the run-identity portion depend on where `job_key` ends, which is
job-name-derived text, not a controlled token.

**Every composition site widens together (FR-014)**:
1. **Emission** — `wing-commander-metrics-summary/action.yml:245`
   (production).
2. **Persist-time rewrite** —
   `wing-commander-metrics-persist/action.yml`'s job-id resolution step
   (currently `.run.record_key = "\(.run.workflow_run_id):\($jid):\(.run.step_index)"`)
   must carry `run_attempt` through unchanged into the rewritten key:
   `.run.record_key = "\(.run.workflow_run_id):\(.run.run_attempt):\($jid):\(.run.step_index)"`.
   This rewrite only ever substitutes `job_key` → `job_id`; it must not
   touch or recompute the attempt segment.
3. **Test harness** — `.github/scripts/wc_metrics_harness.py`'s
   `metrics_record()`, `fixture_job_id()`/`resolved_key()`, and
   `persisted_record()` all build `record_key` literals and are consumed
   by `verify-metrics-persist-retry.py`, `verify-metrics-sweep-idempotence.py`,
   and `verify-metrics-expired-artifact-outcome.py` — each gains an
   `attempt` parameter (default `"1"`, matching `github.run_attempt`'s own
   default on a first attempt) threaded into the literal.
4. **Consumers keyed by `record_key`** — the per-run rollup line
   (`wing-commander-metrics-persist/action.yml`'s `history` jq, `.run.record_key`
   interpolation) and the idempotence/de-dup `existing_keys` diff (same
   action) need no logic change — they treat `record_key` as an opaque
   string already, so widening its shape is transparent to them. This is
   exactly what FR-014 asks for: the consumers are "widened with it in the
   same change" by construction, not by editing their own logic.

**Gates that pin the key's shape, and how each widens**:
- `verify-metrics-summary-record-emission.py`'s
  `case_repeated_invocation_in_one_job_gets_distinct_record_keys` needs no
  change (still asserts distinctness across step indices; attempt is
  constant within one run). Its file-level `mutate()`/`MUTATION_LABEL`
  pins `RECORD_KEY="${RUN_ID}:${JOB_KEY}:${STEP_INDEX}"` — updated to the
  new literal, and a **second** mutation is added
  (`MUTATION_LABEL_ATTEMPT = "record_key drops the attempt number
  (re-run attempts of one workflow run collide)"`) that strips `:${RUN_ATTEMPT}`
  instead, so the suite is proven to fail for FR-014's own stated reason,
  not just step_index's.
- `verify-metrics-record-schema.py` (Gate 39) currently only type-checks
  `record_key: str` with no shape assertion — this plan adds a positive
  regex assertion, `^[0-9]+:[0-9]+:[^:]+:[0-9]+$`, applied to every
  ingested record's `record_key` and to the new `run_attempt: str` field's
  presence. This is the check FR-014 needs most: it fails on ANY
  composition site that ships a key missing the attempt segment, not only
  the ones this plan remembers to add a mutation for — see R8.
- `verify-metrics-persist-retry.py`'s literal `want_key = f"{run_id}:{diagnose_job_id}:0"`
  and the ambiguous-job-key case's `f"{run_id}:collect:0"` both gain the
  attempt segment (`f"{run_id}:1:{diagnose_job_id}:0"` etc., using the
  harness's new default attempt).
- `verify-metrics-schema-version-tolerance.py`, `verify-turn-budget-collector.sh`,
  `verify-watchdog-no-record-on-clean-path.py`, and every fixture under
  `.github/scripts/fixtures/metrics-record-schema/*.json` carry literal
  `record_key`/`run` shapes that need the attempt segment added so they
  keep validating against the widened schema regex above.

**Alternatives considered**: A stamp-only "superset" identity — the stamp
carries `{run_id, attempt, job_key, step_index}` while `record_key` itself
stays `run_id:job_key:step_index` — was the 2026-09-25 session's working
assumption and is exactly what the 2026-09-28 clarification overturned:
two identities for one run (the record's own and the stamp's) would let
the per-run rollup line and the stamp disagree about which attempt a
record belongs to, the opposite of "one run identity everywhere." Rejected
per that clarification.

## R2: The stamp is the widened record key, wrapped invisibly, embedded once inside `cost-line`'s own text

**Decision**: `wing-commander-metrics-summary/action.yml` gains a new,
unconditional **first** step (`id: run-stamp`, no `continue-on-error`
needed because nothing in it can fail):

```bash
STAMP="<!-- wing-commander-cost-stamp:${RUN_ID}:${RUN_ATTEMPT}:${JOB_KEY}:${STEP_INDEX} -->"
echo "value=$STAMP" >> "$GITHUB_OUTPUT"
```

computed from the same four ambient inputs `RECORD_KEY` is built from
(`github.run_id`, `github.run_attempt`, `github.job`, the `step-index`
input), before any step that reads a transcript, calls `jq` against a
record file, or can otherwise degrade. The composite declares a new
output, `stamp`, sourced from this step. The existing `cost-line`
computation (action.yml:379-391) appends `" " + $stamp` as its last
concatenation term — one edit to the existing jq pipeline's final line,
passing the stamp in via `--arg stamp "$STAMP"` — so every one of the 12
call sites that already appends `steps.metrics-summary.outputs.cost-line`
verbatim inherits the stamp with **zero call-site edits** for the normal
and internally-degraded ("cost unavailable" / "turns unavailable" /
"model unavailable") paths alike (FR-003: "so that every consumer of that
line inherits it").

**Rationale for HTML-comment shape**: this mirrors the one existing
precedent for an invisible, machine-readable marker on a pipeline-authored
comment — `wing-commander-metrics-persist`'s rollup begin/end markers
(`<!-- wing-commander-metrics-rollup:begin -->`) — and GitHub already
renders HTML comments invisibly in every surface these comments reach
(issue comments, PR comments, step summaries), satisfying FR-004/SC-004
without a new rendering assumption to validate.

**Why the stamp step runs before anything that can degrade, not after**:
`emit_record()`'s own record-building jq already degrades gracefully
(`> "$RECORD_PATH" 2>/dev/null || printf '{}' > "$RECORD_PATH"` — action.yml,
before the cost-line jq), so `cost_line` itself is essentially never
empty for a composite step that actually executes: the `"**Cost**: " +`
prefix and `" · "` separators are literal jq string concatenation, present
regardless of which part degrades. Placing the stamp step first, using
only inputs that cannot themselves fail to resolve, means the stamp is
available for every scenario except the composite step not executing at
all — R3 shows that residual case does not, in practice, reach the
call-site fallback text either.

## R3: The call-site literal fallback reuses the composite's `stamp` output — it does not reconstruct it

**Finding, not a decision**: auditing every one of the 12 call sites
(`clarify.yml:739/768`, `intake.yml:922/951`, `implement.yml:1093/1123`
and its `-retry`/`-progress` siblings, and the rest) confirms the
"Compute cost line" step's `if:` is **always textually identical** to its
paired "Agent run metrics summary" step's `if:` — both gated on the same
`steps.agent.outcome != 'skipped'` (or `steps.cycle.outcome`, etc.)
condition. This means the literal `"**Cost**: metrics unavailable"`
fallback (triggered when `$COST_LINE` is empty) can only be reached when
the metrics-summary step *did* run; it is never reached because the step
was skipped. Combined with R2's finding that `cost_line` is essentially
always non-empty once the composite step executes at all, the empty-string
branch is a defensive backstop for a scenario the codebase has never
actually needed to rely on, not a routinely-hit path — but FR-001
Acceptance Scenario 2 is an explicit, mandatory requirement regardless of
how rarely it fires, so it is honored structurally rather than left as an
edge case someone must remember.

**Decision**: each of the 12 call sites' `env:` block gains one more line,
`RUN_STAMP: ${{ steps.metrics-summary.outputs.stamp }}` (or the
per-call-site-suffixed step id, e.g. `steps.metrics-summary-cycle.outputs.stamp`),
and the fallback line changes from

```bash
[ -n "$line" ] || line="**Cost**: metrics unavailable"
```

to

```bash
[ -n "$line" ] || line="**Cost**: metrics unavailable $RUN_STAMP"
```

This stays "at most a one-line fallback" (CLAUDE.md's own phrase for the
carve-out) — it is still one line, and it does not recompute the stamp's
template; it concatenates a value the single-home composite already
produced. `steps.metrics-summary.outputs.stamp` is set by the composite's
first, unconditional step (R2), so it survives independently of whatever
degraded `cost-line` — the only scenario in which `$RUN_STAMP` would
itself be empty is the composite step not running at all, which per this
research is the same condition under which the *entire* "Compute cost
line" step is skipped too, so no unstamped fallback comment is ever
actually posted.

**Why this is not "a second formatter" (FR-003)**: the stamp's *shape* — a
colon-joined key wrapped in an HTML comment — is written in exactly one
place, `wing-commander-metrics-summary/action.yml`'s `run-stamp` step. No
call site constructs, re-derives, or reformats that string; each one only
threads an already-computed output through one more line, the same
relationship every call site already has with `cost-line` itself.

**Alternatives considered**: having each call site rebuild the stamp from
its own ambient `github.run_id`/`github.run_attempt`/`github.job`/literal
step-index — rejected even though the values are locally available,
because it would mean the marker's literal template text (`<!--
wing-commander-cost-stamp:...`) exists as source at 13 places (the
composite plus 12 call sites) rather than 1, and any future change to the
marker's shape would need a coordinated 13-site edit with nothing failing
on a drifted copy — exactly the CLAUDE.md "Shared logic has exactly one
home" failure mode this plan is required to avoid, for a case (R3's
finding) that turns out not to need it: reusing the already-computed
output costs one more `env:` line and closes the same requirement.

## R4: The collector's three-way split — stamped-own, stamped-foreign, unstamped

**Decision**: `collect-cost-report`'s `COST_ATTRIBUTION_FILTER` (currently
one `select`/`select`/`select` pipeline keyed on author login and
`createdAt` window alone) becomes, conceptually:

```text
authored := comments authored by one of the pipeline's own identities (unchanged, FR-007)
parsed   := authored comments, each with its stamp parsed out (or null if absent/malformed)
stamped_own     := parsed comments whose stamp's run-identity portion (run_id:attempt,
                    or run_id alone under R6's degraded match) equals the inspected run
stamped_foreign := parsed comments whose stamp names a run-identity portion that does NOT
                    equal the inspected run (excluded unconditionally, FR-006)
unstamped       := parsed comments with no stamp, or a stamp that fails to parse (degrades
                    to "no stamp", per the malformed-stamp edge case)
own := stamped_own ∪ (unstamped ∩ window)   -- window applies ONLY to the unstamped set (FR-008)
```

then the existing "first cost line wins, ordered by creation time" rule
(FR's own words) runs over `own` exactly as it does today — unchanged
sort, unchanged first-match extraction. `stamped_own` membership is never
bounded by `since`/`until` (FR-006's "regardless of whether it falls
inside the inspected run's time window", and the edge case "a run posts
its cost line after its recorded `updatedAt`").

**Rationale**: this is the literal shape of FR-005 through FR-009 read
together — stamp preference (FR-005), foreign-stamp exclusion regardless
of window (FR-006), continued author-identity gating (FR-007), and the
conservative unstamped fallback that a stamp *elsewhere* in the window
must not disqualify (FR-008). Building it as a three-way partition rather
than a single modified predicate keeps each requirement a visibly separate
jq clause, which is what makes FR-012's mutation checks (removing the
stamp preference, or inverting it to prefer a foreign stamp) each
correspond to deleting or flipping exactly one clause — the shape a
mutation test needs to prove the suite would actually catch the regression.

**Alternatives considered**: computing `own` as "authored ∩ window, plus
stamped_own" (i.e., keep the window as a base filter and only *add*
stamped comments outside it) — equivalent in outcome to the decision
above stated differently, but the decision's phrasing keeps "which
comments enter `own` and why" legible as three named sets rather than an
additive patch to the existing filter, which matters for FR-012's gate
readability (contracts/cost-attribution.md documents the sets by name).

## R5: `comments_checked` no longer requires a resolvable window — it requires the issue and the author identity

**Decision**: the collector's existing gate — `comments_checked` stays
`"false"` unless `ISSUE`, `CREATED_AT`, `UPDATED_AT`, and `BOT_SLUG` are
all non-empty — relaxes to: `comments_checked` requires `ISSUE` and
`BOT_SLUG` (author identity is what makes a stamp believable at all, FR-007,
and the issue is what tells the collector where to read comments from).
`CREATED_AT`/`UPDATED_AT` become optional bounds threaded into the filter
as empty strings when unresolved, exactly like the filter already treats
an open-ended `since`/`until` today (`($in.since // "") == "" or ...`) —
the difference is only that this state is now reachable even when the
*run's own* `createdAt`/`updatedAt` lookup failed, not only when one side
of the window was intentionally left open.

**Why this does not reopen #376 ("not checked" silently becoming "checked
and absent")**: R4's partition means an unresolvable window empties the
`unstamped ∩ window` term (nothing is in-window when there is no window),
but `stamped_own` is computed independently of the window entirely — so a
genuinely stamp-attributable comment is still found, while an unstamped
comment is never credited to a run whose window the collector could not
resolve (the previous behavior for that half is unchanged: no window, no
unstamped attribution). If *neither* a stamp match nor a window is
available — the inspected run's own workflow-run identity itself cannot
be resolved, which R6 shows only happens when `gh run view` itself fails
— the collector still declines to report anything, preserving FR-009's
guarantee exactly.

**Alternatives considered**: leaving `comments_checked` gated on all four
values as today, and treating an unresolvable window as "checked: false"
even when a stamp match exists — rejected because it directly contradicts
FR-009's own text ("the collector MUST NOT abandon the check merely
because the run's time window is unresolvable") and would mean a stamp
that is present and matching is thrown away for a reason the stamp exists
specifically to make irrelevant.

## R6: Attempt-number resolution and the FR-002a degraded match

**Decision**: `run-meta`'s `gh run view --json` call
(watchdog.yml:447) gains `attempt` to its field list (`gh run view --json
headBranch,headSha,conclusion,url,event,createdAt,updatedAt,databaseId,workflowName,attempt`),
exposed as a new `run-meta` output, `attempt-number`, read by
`collect-cost-report` alongside the existing `CREATED_AT`/`UPDATED_AT`.
`gh run view --json` already supports this field (unlike a lookup this
plan would need to add a second API call for), so this is a one-field
widening of an existing, already-invoked command — no new network call.

Per FR-002a, when `attempt-number` is empty (the `gh run view` call itself
failed or the field came back empty — the only way this plan's own
Assumptions section says it can be unresolvable): the collector still
excludes any comment whose stamp names a **different workflow run id**
outright (FR-006 does not need the attempt to apply — a foreign run id is
foreign regardless). Among comments whose stamp names the **same**
workflow run id, the collector cannot tell attempts apart, so — per
FR-002a's explicit instruction not to "credit one attempt with another's
line on a run-id match alone while presenting the result as stamp-backed"
— those comments are **reclassified into the `unstamped` set** for this
run's inspection (not `stamped_own`), so they are only attributed if they
also fall in the window, and if attributed, FR-010 records the attribution
as `window`, never `stamp`. This is a precise, deliberate demotion: the
comment still carries a real stamp, but this run's own missing attempt
number means the collector cannot use it as proof, so the finding must
not claim stamp-backed certainty it does not have.

**Alternatives considered**: treating a same-run-id, unresolvable-attempt
match as `stamped_own` outright (ignore attempt when it can't be checked)
— rejected outright by FR-002a's literal text; this is exactly the
"presenting the result as stamp-backed" failure the requirement names.

## R7: A malformed stamp degrades to "no stamp" — never a collector error

**Decision**: the stamp is parsed with one jq regex,
`<!-- wing-commander-cost-stamp:([^:]+):([^:]+):([^:]+):([^:]+) -->`
(four non-colon capture groups matching `run_id:attempt:job_key:step_index`
— `job_key` is a GitHub Actions job id/name, which cannot itself contain a
literal `:`, so the four-group split is unambiguous). A comment whose body
contains no match, or a `<!-- wing-commander-cost-stamp:...` prefix that
doesn't complete the pattern (truncated, extra fields, non-numeric run id
or attempt), is treated identically to a comment with no stamp at all —
folded into R4's `unstamped` set, never raising, never partially trusting
a malformed capture (spec.md edge case: "degrades to 'no stamp' — the
collector never raises and never guesses a run id").

**Rationale**: this is the same posture the existing `COST_REPORT_FILTER`
already takes toward a malformed cost figure (a `cost_token` that fails
the currency regex becomes `cost-line-malformed`, never a script error) —
consistent error handling for "well-formed marker, wrong content" across
both of the collector's programs.

## R8: `normalizedFacts` and signal-facts gain `attribution`, not a new signal class

**Decision**: FR-010 is satisfied by adding one field to the existing
`cost-line-missing`/`cost-line-malformed` signal facts (spec 046's
`cost-line-claim` signal kind, `ident: {run, stage, claim-type}`,
unchanged) — `attribution: "stamp" | "window"` — set from which branch of
R4's partition produced the comment the verdict was decided from (for
`cost-line-missing`, whether any `stamped_own` comment existed at all, even
one without a cost line, per the spec's existing "a comment of its own was
found" distinction). This is additive to the fixed `normalizedFacts`
vocabulary's existing `stage`/`expected`/`actual` triple (constitution IX
does not apply here — this is a descriptive fact added to signal facts a
gate already asserts shape-of, not a new judgment call the model makes;
`diagnose`'s own `normalizedFacts` mapping for this class can fold
`attribution` into `actual`'s text, e.g. `"no cost line found for this
run (window-attributed)"`, needing no schema widening at all).

**Alternatives considered**: a new signal source/kind
(`cost-report-attribution`) — rejected: FR-010 asks the *existing* signal
to record how it decided, not a second signal describing the decision
process; a second signal would need its own identity, its own dedup
behavior, and its own place in `Stamp signal ids`' source→kind map for no
benefit over one more fact on the signal that already exists.

## R9: Gate coverage — extend the two existing harnesses, widen one existing single-home gate, add no new gate number

Per spec.md's own Dependencies section ("FR-012's scenarios extend these
rather than adding a third harness"):

- **`verify-gate-19.py`** — `COST_SCENARIOS` gains the fixtures FR-012
  names: overlapping pair (one posts, one doesn't) attributed
  independently; overlapping pair where both post; a foreign-stamped
  comment inside the window; an unstamped comment inside the window
  (pre-stamp behavior preserved); a mixed-era window (foreign stamp +
  unstamped both present, unstamped stays eligible); several stamps from
  one run in one window; two attempts of one workflow run, each owing a
  line, asserted independently; an inspected run with an unresolvable
  attempt number (R6); a malformed stamp (R7); a stamp in a comment from a
  non-pipeline author (still excluded, FR-007 unchanged). `COST_MUTATIONS`
  gains: drop the stamp preference entirely (falls back to window-only —
  reproduces the reported #369/#370 defect); invert it (prefer a foreign
  stamp); drop the attempt number from the matched run-identity portion
  (collapses R1's widened key back to run-id-only matching, reproducing
  FR-002's re-run defect).
- **`verify-cost-report-collector.sh`** — extended with fixtures pinning
  the two jq programs' new branches directly (the three-way partition in
  `COST_ATTRIBUTION_FILTER`, the `attribution` field in
  `COST_REPORT_FILTER`'s output), mirroring its existing role of pinning
  the *programs* while `verify-gate-19.py` pins the *whole bash step*.
- **`verify-metrics-summary-record-emission.py`** gains one new case
  function, `case_run_stamp_has_exactly_one_home`, sibling to the existing
  `case_cost_line_formatter_has_exactly_one_home` (same file, same
  `_workflow_texts()`/actions-walk scan, different detection string: the
  literal marker prefix `wing-commander-cost-stamp:` combined with a scan
  for the *construction* of that prefix — i.e. any file outside the
  canonical action that contains a **shell string-building** occurrence of
  the prefix, as opposed to a **plain reference/consumption** of an
  already-computed `steps.*.outputs.stamp` value. Concretely: the gate
  flags a file outside the canonical action if it contains the marker
  prefix text *not* immediately preceded by `outputs.stamp` or `$RUN_STAMP`
  on the same or an adjacent line — i.e., it fails a literal
  reconstruction (`STAMP="<!-- wing-commander-cost-stamp:...`) while
  passing a consumption (`RUN_STAMP: ${{ steps.metrics-summary.outputs.stamp }}`,
  `"$RUN_STAMP"`). This is the concrete mechanism FR-003's "a second
  formatter MUST fail the existing single-home gate" cashes out to, and it
  is exercised by a fixture per constitution VIII: one fixture proving a
  reconstructed marker at a workflow file fails, one proving the 12
  call-sites' actual `$RUN_STAMP` consumption passes.
- Gate 39 (`verify-metrics-record-schema.py`) gains the `record_key` shape
  regex from R1 — this is new coverage, not an extension of the two named
  collector harnesses, but it is the single check that makes FR-014's "a
  composition site left emitting a key without the attempt number" fail
  for *any* future site, not just ones this plan remembers to mutate-test
  by name.

No new gate number is registered; every change above lands inside a gate
script this repository already runs, following this repository's own
"single home" convention for the gates themselves (CLAUDE.md).

## R10: Decisions made without an explicit spec answer

Summarized for the lifecycle issue comment — none contradicts spec.md;
each fills an implementation-shaped gap spec.md deliberately left open:

- Attempt number is inserted as the **second** segment of the widened
  record key (`run_id:attempt:job_key:step_index`), so the run-identity
  portion FR-002 names is a clean two-field prefix (R1).
- The stamp is an HTML comment wrapping the widened record key, appended
  as the last term of the `cost-line` output's own jq concatenation, and
  additionally exposed as a standalone `stamp` output (R2).
- The degraded one-line fallback at all 12 call sites reuses that
  standalone `stamp` output via one added `env:` line, rather than
  reconstructing the marker locally (R3) — the audited `if:` conditions
  show this fallback text is, in practice, never reached with a genuinely
  unstamped result once R2's first-step placement ships.
- The collector's attribution logic is a three-way partition
  (stamped-own / stamped-foreign / unstamped-in-window), with the window
  applying only to the unstamped set (R4).
- `comments_checked` relaxes from requiring all of
  issue/createdAt/updatedAt/bot-login to requiring only issue/bot-login,
  with the window becoming an optional bound rather than a hard
  precondition (R5) — needed for FR-009 to hold once a stamp can decide
  attribution without a window at all.
- An inspected run with an unresolvable attempt number demotes
  same-run-id stamped comments to the unstamped/window-fallback set rather
  than trusting them as stamp-backed (R6), per FR-002a's literal
  instruction.
- A malformed stamp is parsed by one fixed regex and folds into
  "unstamped" on any non-match, never a partial/guessed match (R7).
- FR-010's attribution record is one new fact
  (`attribution: "stamp"|"window"`) on the existing signal, not a new
  signal class (R8).
- Gate numbers are not reserved; every change lands inside an existing
  gate script, with one new sibling case function in
  `verify-metrics-summary-record-emission.py` for the stamp's single-home
  check (R9).
