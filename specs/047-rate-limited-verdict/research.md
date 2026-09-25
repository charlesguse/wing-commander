# Phase 0 Research: Rate-limited agent verdict

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers — the two
genuine ambiguities (where the uninspected-run fact is recorded and
whether stage-8b stays green; how the `rate-limited` exemption applies
outside the watchdog) were already resolved during the clarify stage and
are cited inline in the spec's Clarifications section (FR-012/FR-013,
FR-014/FR-015). What follows are the implementation-shape decisions this
plan makes to turn the spec's functional requirements into something
`tasks.md` can build against, grounded in a fresh read of
`wing-commander-agent-verdict/action.yml`, `watchdog.yml`,
`verify-watchdog-run.sh`, and `wing-commander-metrics-summary/action.yml`
as they exist on `main` today (not the issue's line numbers, which have
already drifted). Decisions not dictated by the spec text are marked
"(made without clarification)" and are repeated in the transmittal
comment on issue #306, per this pipeline's own convention.

## R1: The exact transcript shape the classifier keys on (made without clarification)

**Decision**: `rate-limited` is computed from the same `result_json`
variable the classifier already isolates (the last `.type=="result"`
record) plus a scan of the full transcript for `.type=="rate_limit_event"`
records. The condition, checked *before* the existing
`is_error`/`subtype` branch (same "order matters" precedent as
`exhausted`):

1. A terminal `result` record must exist (an empty transcript or one
   with no result record at all keeps its current `unclassifiable`/
   `failed` outcome — FR-005; this feature never rescues those shapes).
2. That record must be a failure by the classifier's existing test
   (`is_error=="true"`, or a non-`success` subtype) — a `rate_limit_event`
   earlier in the transcript with an eventual `subtype=="success"`
   terminal record is `healthy`, unchanged (spec.md edge case "a 429 the
   runtime recovered from").
3. Given a failing terminal record, `rate-limited` fires when *either*:
   (a) the terminal record itself carries `.terminal_reason=="api_error"`
   and `.api_error_status=="429"`, or (b) those fields are absent but the
   transcript carries at least one `rate_limit_event` record whose
   status is `"rejected"` (read from `.rate_limit_info.status`, falling
   back to a top-level `.status`); a bare `rate_limit_event` record with
   no status in either place still counts — FR-002's "tolerates their
   absence" applies to every field, not just `resetsAt`. An event with
   any other status (the runtime's informational `"allowed"` /
   `"allowed_warning"`, emitted during ordinary runs) is not evidence:
   the first implementation counted every event whatever its status, and
   so classified unrelated failures as `rate-limited` (#544).
   Otherwise the existing `is_error`/`subtype` → `failed` logic applies
   unchanged.

**Rationale**: spec.md's own Assumptions state the issue's cited field
names (`rate_limit_event.status`/`rateLimitType`/`resetsAt`,
`result.terminal_reason`/`api_error_status`) are "the observed shape of
today's runtime" and that "the classifier tolerates their absence rather
than requiring all of them" — this plan reads that as license to key
primarily on the *presence* of a `rate_limit_event` record alongside a
failing terminal result, using the terminal record's own
`terminal_reason`/`api_error_status` fields as corroboration when
present rather than as a hard requirement. This keeps the detector
robust to the runtime shipping the two record types in either
combination the assumption anticipates, without inventing a third,
undocumented signal. **Risk carried forward to tasks/implement**: the
three replay fixtures SC-004 requires (the three 2026-09-12 runs, the
2026-08-28 run) are the ground truth for this shape, not this document —
`tasks.md` must pull the real `execution-output` artifacts from those
runs (linked in issue #306/#300) before writing Gate 22's synthetic
cases, and this decision's condition (2)/(3) must be re-checked against
what they actually contain.

**Alternatives considered**: Requiring all five documented fields
verbatim — rejected, directly contradicted by spec.md's own Assumptions
sentence. Keying only on `rate_limit_event` presence with no terminal-
record corroboration at all — rejected: a `rate_limit_event` can appear
mid-run on a recovered call (edge case), so terminal-record failure is
load-bearing, not optional; dropping it would misclassify some non-
terminal 429 blips whose transcript retries and finishes as another
call's `is_error`/`subtype` failure.

## R2: Reset time is a structured output, not just reason-text prose

**Decision**: `wing-commander-agent-verdict` gains a new output,
`rate-limit-reset`: the `rate_limit_event` record's `resetsAt` value
verbatim when present and non-empty, else the literal string `unknown`.
`reason` (free text) also names it and the window type
(`rateLimitType`, when present) for humans reading the step summary or
an `::error::` line, but `rate-limit-reset` is the field every
*programmatic* consumer (the watchdog's new report step, the
`usage-limit` issue body, `wing-commander-metrics-summary`'s display
line) reads — never a `reason`-string regex.

**Rationale**: FR-003 says the classifier "MUST expose the window's
reset time to its callers" — plural callers, at least one of which
(the watchdog report, FR-007) needs the value to compose its own
sentence rather than re-parse another field's prose. This mirrors how
`counted-turns`/`over-budget` are already separate structured outputs
rather than folded into `reason` alone (data-model.md of spec 037).
Emitting the raw ISO-8601 string (not a pre-formatted "human-readable"
rendering) keeps the composite's contract simple and lets each caller
decide its own presentation — the same division of labor R2 of spec 037
already drew between the classifier (generic truth) and each call site
(its own presentation/validation).

**Alternatives considered**: Folding the reset time only into `reason`
and having callers regex it out — rejected: fragile, and the composite's
own contract already promises structured outputs for everything a
caller needs programmatically. A separate `rate-limit-window` output for
the window type — not added: no functional requirement reads the window
identity programmatically (FR-013 requires naming the run and the reset
time on the `usage-limit` issue, not the window type), and
spec.md's Assumptions explicitly say the window's identity is "reported,
not used to gate the classification" — reported in `reason` prose
satisfies that without a second structured output nothing consumes.

## R3: `wing-commander-metrics-summary` gains the allow-list value only, not a second copy of the detection

**Decision**: The outcome-resolution `case` statement
(`healthy|exhausted|failed|unclassifiable`) gains `rate-limited` as a
fifth accepted literal, passed through from the `verdict` input exactly
like the other four. The action's *standalone fallback* branch — the
one that classifies from the raw transcript when no `verdict` input was
supplied at all — is **not** taught to detect rate-limiting.

**Rationale**: FR-006 requires the rate-limited determination to "live
in exactly one place consumed by all stages... no per-workflow copy of
the detection." The fallback branch is a second, pre-existing copy of
the *original four-way* classification (predating this feature, kept
for callers that never wired `wing-commander-agent-verdict`) — teaching
it the `rate_limit_event`/429 shape as well would create exactly the
second home FR-006 forbids, for a code path every current call site
already bypasses by passing `verdict` explicitly (spec 037 wired all 19
sites). A transcript that would classify `rate-limited` through the real
composite instead falls through the fallback's existing `else`
(`is_error=="true"` → `failed`) when no verdict is supplied — a pre-
existing, unrelated gap in the fallback's four-way coverage that this
feature does not widen.

**Alternatives considered**: Duplicating the detection into the
fallback for completeness — rejected per FR-006 above. Removing the
fallback entirely now that every site wires `verdict` — out of scope:
no functional requirement asks for it, and removing an unrelated
duplication is exactly the kind of drive-by cleanup CLAUDE.md's
"don't add features... beyond what the task requires" instructs against.

## R4: Verifier suppression is two narrow `if`-wraps keyed on one new step-conclusion read, not a rewritten script

**Decision**: `verify-watchdog-run.sh` gains one new evidence read —
whether the diagnose job's `'Report "rate-limited" to lifecycle issue'`
step ran (not skipped), the same "conditional reporting step as
evidence" pattern the script already uses for `"diagnose failed"`,
`"could not inspect"`, and the two `report-unhandled-failure` steps.
When that step ran:
- Check 7 ("successful terminal result" on the diagnose execution-output
  artifact) is suppressed — a rate-limited run's terminal record is,
  by definition, a failure, so this check would otherwise always fire
  and is exactly the "absent successful terminal result" reason FR-010
  names.
- The duration-band **floor** breach only (too-fast) inside check 2 is
  suppressed — a one-turn, zero-cost rejection is the "short-duration
  band breach that a one-turn death produces" FR-010 names. The
  duration **ceiling** breach (too-slow — a stall) is never suppressed:
  nothing about rate-limiting explains a slow run, and a stall alongside
  a rate-limited diagnose step is exactly US1 Acceptance Scenario 4's
  "unrelated check" that must still fire and still file.

Check 3 ("the diagnose agent FAILED, its 'diagnose failed' reporter
ran") needs **no new suppression code**: it already reads that specific
step's own conclusion, and a rate-limited run's "Read back diagnose
outcome" step takes the new `outcome=rate-limited` branch instead of
`outcome=diagnose-failed` (contracts/watchdog-reporting.md), so the
"diagnose failed" reporter is skipped by construction and check 3
already produces no reason — the mutual exclusion between the two
`outcome` branches is what does the work, not a script-side special
case.

**Rationale**: This is the smallest change that satisfies FR-010/FR-011/
FR-012a together: suppress exactly the reasons rate-limiting explains,
leave every other check (conclusion, duration ceiling, the unhandled-
failure safety net, the crash-signature backstop, the read-back step's
own success) fully live, so a rate-limited run with an *additional*,
independent defect still fails stage-8b for that defect alone
(FR-011). Reading a step's conclusion as the source of truth (rather
than re-deriving rate-limited-ness from the artifact a second time)
keeps the judgment in exactly one deterministic place — the same
"conditional reporting steps encode the true outcome" design the whole
script's header comment already documents, extended by one more step
name rather than a parallel code path (constitution IX).

**Alternatives considered**: Re-reading the diagnose execution-output
artifact inside the verifier script to re-derive rate-limited-ness
independently — rejected: this is the second-copy shape FR-006
explicitly forbids for the classifier's own logic; the verifier should
trust the one place that already computed the verdict (the workflow's
own step outcome), not recompute it. Suppressing the *entire* duration-
band check rather than just its floor arm — rejected: it would also
blind check 2 to a genuinely stalled rate-limited-and-also-hung run, a
combination the spec does not ask this feature to special-case away.

## R5: `usage-limit` issue dedup — one open issue at a time, not a per-window fingerprint

**Decision**: The new "Ensure usage-limit issue" step searches for **any
OPEN issue labelled `usage-limit`** (`gh issue list --label usage-limit
--state open`) — no fingerprint, no per-window matching key. If one
exists, append a bullet (`- run <URL>, usage window resets at <time>`) via
`gh issue comment`; if none exists, `gh issue create` with that first
bullet as the body, labelled `usage-limit` (created with `gh label
create ... --force` first, mirroring the existing `pipeline-defect`
label bootstrap).

**Rationale**: FR-012/FR-013 ask for "one issue per exhausted window,"
but also (spec.md Assumptions) accept that closing/sweeping those issues
"stays a human action" — i.e., the system already tolerates a
maintainer leaving a window's issue open indefinitely, which means a
strict per-window fingerprint (keying dedup on `resetsAt` or
`rateLimitType`) would, on that same tolerated path, produce a *second*
open `usage-limit` issue the moment a later window exhausts before the
first is closed — the exact "board grows by one item per run, not per
window" outcome the label and this whole feature exist to prevent. The
simpler "fold into whatever `usage-limit` issue is currently open" rule
keeps the board's accepted cost at "one issue per *unclosed* window
episode," which is what SC-003 actually measures ("one issue per
exhausted window... discoverable... from a single label filter") and
is far simpler to implement and to verify than a fingerprint match
(no marker comment to embed/parse, unlike the existing `pipeline-defect`
dedup's `<!-- fingerprint=... -->` convention).

**Alternatives considered**: Fingerprinting by `resetsAt` (one issue per
reset timestamp) — rejected: two runs rejected by the *same* window
exhaustion can observe slightly different `resetsAt` values if the
runtime rounds or the window boundary is recomputed between calls,
which would silently defeat the "fold into one issue" requirement for
exactly the runs FR-012 most wants folded. Reusing the existing
fingerprint/dedup step verbatim with a different label — rejected: that
mechanism's fingerprint is built from finding-class-specific fields
(triage's `Compute fingerprint` step) that don't exist for this simpler,
unclassed record; forcing the shape to fit would add complexity with no
requirement asking for per-window precision.

## R6: FR-015b's gate — dynamic enumeration plus a small registered-exempt list, not a hand-maintained catalog

**Decision**: A new gate, `.github/scripts/verify-rate-limited-exemption.py`,
following `verify-gate-23.py`'s existing template (YAML-parsed, never
grepped, so unusual indentation or flow style is never silently missed):
it walks every step in every `.github/workflows/*.yml` job, finds every
step whose `run:` body contains a `gh issue create`, `gh issue comment`,
or `gh pr comment` invocation *and* whose own `if:` (or an enclosing
job-level `if:`) references a `steps.<id>.outputs.verdict` or
`needs.<job>.outputs.verdict`-shaped expression, and asserts that for
each such site, either (a) the `if:` condition already excludes
`rate-limited` (e.g. `verdict != 'healthy' && verdict != 'rate-limited'`,
or an equivalent allow-list form), or (b) the site's `(file, step name)`
pair is in this gate's own small `EXEMPT_SITES` constant — the two new
watchdog steps this feature adds (`'Report "rate-limited" to lifecycle
issue'`, `'Ensure usage-limit issue'`), which are themselves the
sanctioned rate-limited-handling issue writers FR-015a carves out. Any
other verdict-gated issue/comment-writing step that is neither excluded
nor registered fails the gate, by file and step name.

**Rationale**: FR-015b explicitly asks for the enumeration to live "in
one place" and for a gate to fail when a new site "silently
reintroduce[s] the filing" — a plan-time hand-count (the shape spec 037
used for its 19 turn-budget call sites) would itself be exactly the
kind of list this requirement distrusts, since it goes stale the moment
a new agent-bearing stage adds an issue-writing step after this feature
lands. Parsing the YAML dynamically (Gate 23's own justification,
research.md R9 of spec 037) means the gate's coverage grows
automatically with the workflow files themselves, and the small
`EXEMPT_SITES` constant is the "one place" the requirement asks for —
auditable in a single diff, not scattered across per-workflow comments.

**Alternatives considered**: A single fleet-wide rule (e.g., make every
"fail loud" step's downstream issue-writer automatically skip on
`rate-limited` with no per-site registration) — this is literally the
option the spec's own clarify session rejected (spec.md Clarifications,
second entry: "The exemption is per-call-site rather than one fleet-wide
rule"), because the fail-loud step itself must stay red for
`rate-limited` while only the narrower issue-writing step beneath it
is exempted — collapsing the two into one condition would either exempt
too much (silencing the fail-loud gate) or too little (leaving the
issue-writer unexempted). A hand-maintained Markdown/JSON list of sites
consumed by the gate — rejected in favor of parsing the workflows
directly, for the same "detector should read the shipped artifact, not
a description of it" reason `verify-agent-verdict.py` and `verify-gate-23.py`
already establish for this repository.

## R7: Known non-watchdog exemption candidates (context, not a final list)

Two candidates surfaced directly during this plan's research (not an
exhaustive enumeration — R6's gate is the actual, authoritative
enumeration mechanism, re-run by `tasks.md`/implementation, not by this
document):

- `finalize.yml`'s "Fail loudly rather than opening a PR with incomplete
  content" step, which posts a failure-describing comment gated on a
  non-healthy verdict.
- `cleanup.yml`'s completion-summary fallback, which renders a
  failure-shaped summary line gated on `verdict != 'healthy'`.

Both need their `if:` (or the summary branch they feed) to stop treating
`rate-limited` as the generic failure case, consistent with FR-015a. This
plan does not resolve their exact final wording — that is
implementation work the new gate (R6) will hold to account, not a
design decision this plan needs to pre-commit.

## R8: Gate numbering

**Decision**: The highest existing gate in `lint-workflows.yml` is Gate
50 (`verify-release-contract.py`, confirmed by direct read, not by
trusting any prior document). This feature's new gate (R6) is the next
number, Gate 51. Gate 22 and Gate 36 are *extended* in place (new cases
in the same script, same gate number) — this feature adds exactly one
new gate number, not two.

**Rationale**: Matches this repository's own numbering convention (gate
numbers assigned in landing order, never reused) and Gate 10's
requirement that every new `verify-*.py`/`.sh` be wired into
`lint-workflows.yml`'s `run:` blocks in the same PR that adds it, so
Gate 10 never observes an orphaned script.
