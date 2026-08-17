# Phase 0 Research: Multi-Page `gh api` Reads Return What They Claim

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — its own Clarifications
session (2026-08-16) already resolved the three open questions (watchdog-wide
read-outcome scope, flagging the two accidentally-safe reads, and
all-three-sites test coverage). The decisions below are plan-level design
choices needed to turn those resolved requirements into concrete edits; each
follows the format Decision / Rationale / Alternatives considered.

## D1: The fix shape for all five call sites

**Decision**: Every one of the five sites (`watchdog.yml:665`, `:740`,
`:743`; `auto-update-spec-kit.yml:425`, `:835`) is rewritten to
`gh api "<path>" --paginate --jq '<per-item filter>' | jq -s '.'` —
stream one JSON value per line under pagination, collect once. For
`watchdog.yml:665`/`:740` the per-item filter becomes `--jq '.jobs[]'`
(the endpoint is `{"jobs":[...]}`; streaming the array's elements turns
`{"jobs":[...]}` per page into `{...}\n{...}\n...` across all pages), so
the collected value changes shape from `{"jobs":[...]}` to a flat JSON
array of job objects — every downstream `.jobs[]?.id` reference at those
two sites becomes `.[]?.id` (FR-018: same ids for a single-page run,
every page's ids for a multi-page run). For `watchdog.yml:743` the filter
becomes `--jq '.[] | select(.annotation_level=="warning" or
.annotation_level=="failure") | {source:"annotations",...}'`, replacing
the current two-step `gh api --paginate` (no `--jq`) + separate `jq -c
'[...]'` pass. For `auto-update-spec-kit.yml:425` and `:835`, the
per-item filter becomes `--jq '.[] | select(.prerelease == false)'`
(pushing the existing `select` into the `--jq` itself, since it commutes
with per-page filtering — dropping prereleases page-by-page and slurping
is identical to slurping and dropping prereleases once, because
"prerelease" is a per-item property, not one that depends on page
position), and the existing `sort_by(...) | last` (detect) /
`select($vv > $pp and $vv <= $cc)` (notes) run unchanged on the slurped
array.

**Rationale**: This is exactly the form spec 033 T067 already proved
correct and shipped in `pr-conversation.yml` (`--jq '.[] | select(...) |
{...}'` piped through `jq -s '.'`), and it's the form `intake.yml:399`
independently arrived at. Reusing a proven shape rather than inventing a
new one satisfies the spec's own Assumptions section ("this feature
applies that form rather than inventing one") and keeps the new Gate 18
(D2) checkable with one shape rule instead of two.

**Alternatives considered**:
- `--slurp` instead of streaming + `jq -s`: rejected per spec's own
  Suggested-fix note — `--slurp` changes the shape to an array *of pages*
  (`[[...],[...]]`), which would require every downstream filter to gain
  a flattening step; the streaming form is the smaller, and now
  precedented, edit.
- Leaving `:665`/`:740` as `{"jobs":[...]}`-per-page and declaring them
  gate-exempt because their consumer happens to tolerate it: rejected —
  this is precisely the shape FR-011 requires flagged and rewritten
  ("a read whose correctness depends on an unstated property of its
  consumer MUST NOT pass"), and Out of Scope explicitly names these two
  reads as being rewritten, not grandfathered.

## D2: Gate numbering and where the static check lives

**Decision**: The pagination-shape gate is **Gate 18** — the next free
number in `lint-workflows.yml`'s existing sequence (grep confirms gates 1,
2, 3, 4 (the auto-update-spec-kit job, separately named), 5-17 are all
used; nothing is numbered 18+ today). It is a single `python3 - <<'PYEOF'`
step in the `lint` job's existing numbered sequence, immediately followed
by a `Gate 18 self-test — the detector actually detects` step running
`.github/scripts/verify-gate-18.py` — the same two-step shape Gates 15,
16, and 17 already use, because Gate 18 is a pure static-shape detector
(scans text, flags a shape) rather than a step-execution harness. Its
self-test extracts Gate 18's own source out of the shipped
`lint-workflows.yml` at run time (the same `extract_gate()` pattern
`verify-gate-16.py` already implements against the `HEREDOC_OPEN`/
`HEREDOC_CLOSE` markers) and runs it against a table of synthetic
fixtures, per FR-009's "a detector that has stopped detecting MUST NOT be
able to pass as a healthy one."

**Rationale**: `verify-gate-wiring.py` (Gate 10) enforces exactly one
convention: any `.github/scripts/verify-*.py` must be named in some
workflow's `run:` block. Adding Gate 18 as a step (not a standalone script
invoked elsewhere) means its *detection logic* lives inline in
`lint-workflows.yml` and its *self-test* is the `verify-*.py` script that
gets wired — matching every one of Gates 6-8 and 15-17's shape. This is
also what makes Gate 18 automatically appear in `run-local-gates.py`'s
output with zero registration work (`wc_gate_registry.pr_time_gates()`
derives the list from what `lint-workflows.yml` actually runs).

**Alternatives considered**:
- A standalone `verify-pagination-shape.py` that both detects AND
  self-tests in one file, matching Gate 9/19's behavioral-harness shape:
  rejected for the *static* check specifically — Gate 9's shape fits a
  harness that executes shipped shell against a stub, which the
  pagination-shape check does not do (it never runs any workflow code, it
  reads text). Forcing it into that mold would make the detection logic
  live only inside a script nothing else references for drift-proofing,
  losing the "extracted from the shipped workflow" guarantee Gates 15-17
  rely on.

## D3: The declared-exemption escape hatch (FR-013)

**Decision**: A read that must legitimately produce one array per page
(no such use exists today — spec's Edge Cases) declares itself with a
same-line or immediately-preceding-line shell comment carrying the
literal token `wc-pagination-exempt:` followed by a non-empty reason,
e.g. `# wc-pagination-exempt: intentionally one array per page because
<reason>` directly above (or on) the `gh api ... --paginate` line. Gate 18
skips a call site only when this exact token is present within one line
of the call; a bare `wc-pagination-exempt` with no reason text still
fails, so the exemption cannot be used as a silent bypass.

**Rationale**: FR-013 requires the exemption be "declared at that read,
visible in the diff that introduces it" and explicitly forbids a
hand-maintained list — a list is what issue #149 already was for a
different gate, and `wc_gate_registry.py`'s own docstring names that
exact failure mode. An inline, grep-adjacent marker is visible in the
same diff hunk as the call it exempts, requires no second file to keep in
sync, and follows the repository's existing convention for inline
directive comments (`WC-SENTINEL: <token>`, documented in
`docs/agent-friendly-workflows.md`).

**Alternatives considered**:
- A YAML front-matter/step-level `exempt-pagination-shape: true` flag on
  the step: rejected — a step can contain more than one `gh api
  --paginate` call (as `watchdog.yml`'s annotation collector already
  does, two per step), so a step-level flag would exempt the whole step
  rather than the one call site that needs it, silently widening the
  exemption's blast radius.
- No exemption mechanism at all (flag everything, no escape hatch):
  rejected — spec's own Edge Cases section requires one to exist for the
  hypothetical future "legitimately needs one array per page" read, and
  FR-013's wording ("any exemption a genuinely unusual read requires
  MUST be declared") presupposes the mechanism exists.

## D4: Making the auto-update harness's `gh` stub page-aware

**Decision**: `auto-update-spec-kit-tests/gh_stub.py`'s `spec-kit/releases`
branch (currently: load the fixture array, call `emit(data, argv)` once)
is changed to, when `--paginate` is present in `argv`: split the fixture
array into chunks of `PAGE_SIZE = 30` items (matching the spec's own
"thirty items by default" page-boundary assumption and GitHub's real
default), and for each chunk call the same `--jq`-or-raw-dump logic
`emit()` already implements, writing each chunk's output directly to
stdout with no added separator — reproducing exactly the byte shape real
`gh --paginate --jq` produces (N concatenated JSON documents) rather than
gh's actual HTTP pagination mechanics, which the stub has no need to
simulate. `t1_detect.sh` gains a fixture builder variant that produces
more than 30 releases so its existing `detect()` helper can assert
against a multi-page read without any change to `detect()` itself — the
stub, not the test helper, is where pagination realism belongs, so every
present and future suite that reads `spec-kit/releases` through this stub
gets faithful multi-page behavior for free.

**Rationale**: This is the one real gap the research surfaced (the stub
currently answers `--paginate` identically to a non-paginated call,
because none of the nine existing suites needed pagination realism until
now). Generalizing the stub, rather than adding a one-off
"return-two-documents" special case just for this feature's fixtures,
matches the stub's existing design principle (`jq()`'s docstring: "delegate
to the real jq binary so filter semantics are authentic") — the point of
this harness is that nothing in it should need to re-derive `gh`'s actual
behavior by hand.

**Alternatives considered**:
- A fixture-level boolean (`"paginate_pages": 2`) that only the new
  scenarios set, leaving `--paginate` handling otherwise unchanged:
  rejected — this would make "faithful to real `gh --paginate`" an opt-in
  property of individual fixtures rather than the stub's actual behavior,
  which is backwards: real `gh --paginate` always pages once a response
  exceeds one page, regardless of what the caller "wants."
- Testing against the real GitHub API instead of the stub: rejected —
  every existing suite in this harness stubs `gh` specifically so tests
  are deterministic and offline (README.md); `spec-kit/releases` already
  has 30+ releases in production, so a live-API test would also be
  flaky against exactly the boundary this feature cares about (upstream
  gaining a release mid-test-run changes which page a given release
  lands on).

## D5: A behavioral harness for the annotation collector (Gate 19)

**Decision**: `.github/scripts/verify-gate-19.py` extracts `watchdog.yml`'s
`Collect: annotations` step (`id: collect-annotations`) via
`wc_shell_harness.find_step`/`run_step`, the same mechanism
`verify-sentinel-collector.py` (Gate 9) already uses for the neighboring
`Collect: step summaries` step, and stubs `gh` to answer the two API
paths that step calls (`*/jobs`, `*/check-runs/*/annotations`) from
fixture files — with the annotations fixture, when a scenario asks for
it, containing more than one concatenated JSON array document (the same
"N concatenated documents" shape D4 teaches the other harness to
produce), so the shipped step is driven against the actual byte shape
`gh --paginate` emits past page 1. Scenarios assert every warning/failure
annotation from every page reaches `signals.json`, that annotations from
one job don't displace another's (spec's Acceptance Scenario 3), and that
a job with zero matching annotations leaves the evidence set unchanged
(Acceptance Scenario 5). Per FR-009/Acceptance Scenario 7, it ends with a
mutation check that reintroduces the broken array-collecting `--jq
'[...]'` form and asserts the suite then fails to collect page-2
annotations — proving the harness can actually detect the regression it
exists to catch, the same discipline Gate 9's suite already applies to
itself.

**Rationale**: FR-012 requires "equivalent coverage stood up for it,
since no such harness exists there today" for the annotation collector —
confirmed by the research phase (`verify-sentinel-collector.py` covers the
step-summary collector; nothing today drives the annotation collector
against any fixture, stubbed or live-dispatched). Gate 9 is the nearest
precedent for "extract and execute one of watchdog's collector steps
against a `gh` stub," so reusing its exact plumbing (`wc_shell_harness.py`)
means Gate 19 inherits the same Windows-safety and drift-proofing
properties for free rather than re-solving them.

**Alternatives considered**:
- Extending `verify-sentinel-collector.py` itself to also cover the
  annotations step: rejected — that file's own docstring frames it as
  specifically about the step-summary collector's sentinel-matching
  defect; folding in an unrelated collector's pagination defect would
  make one file's mutation-testing section prove two unrelated things
  are fixed, weakening the "a test that cannot fail is not a test"
  discipline by making it harder to tell which mutation exercises which
  claim.
- Relying solely on `wing-commander-watchdog-test.yml`'s live dispatch
  for this coverage: rejected — that harness needs a real run with a
  real >30-annotation job to exercise the multi-page path, which is not
  reliably producible on demand (spec's own Independent Test for User
  Story 1 asks for a *driven* response spanning more than one page, not
  an opportunistic one).

## D6: Surfacing read outcomes to `diagnose` (FR-010/FR-016/FR-017)

**Decision**: Each of the five `collect` job collectors is changed to
track, alongside the entries it already appends to `signals.json`, whether
every `gh api` read it performed this run succeeded (`ok`) or any one of
them failed outright (`failed`) — determined from the `gh api` invocation's
own exit status captured before the existing `2>/dev/null || echo
'<empty>'` fallback discards it (today the fallback makes every read look
like "succeeded with an empty result," which is exactly the property
FR-010 requires removed), never from the step's overall shell exit code
(the step already runs under `set -uo pipefail`, no `-e`, deliberately, so
one job's read failure doesn't abort the loop over the rest — FR-017).
Each collector writes one `{"collector": "<name>", "outcome":
"ok"|"failed"}` line to a new `$RUNNER_TEMP/collector-outcomes.json`
(same accumulate-and-`jq`-merge pattern `signals.json` already uses), and
the `collect` job's existing `aggregate` step (`watchdog.yml:837`) folds
that file into a new job output —
`untrusted-collectors: ${{ steps.aggregate.outputs.untrusted-collectors }}`
— a JSON array of collector names, alongside the unchanged `signals`
output. The `diagnose` job writes this array to a second file next to
`watchdog-signals.json` and its prompt is told to name any collectors
listed there as untrusted evidence sources — Out of Scope explicitly
excludes changing what `diagnose` *concludes* from this; only that the
information reaches it.

**Rationale**: This is FR-010/016/017's whole requirement, restated
mechanically: a failed read must be distinguishable from an empty one
(today, both look identical: `|| echo '[]'`), the run must still reach a
verdict (already true — collectors are `continue-on-error: true` and the
job only halts entirely if all five fail, `watchdog.yml:854`), and
`diagnose` must be told which collectors it can't trust. Capturing exit
status *before* the `|| echo` fallback is the only point in each
collector where "failed" and "empty" are still distinguishable — after
the fallback runs, the shell has already thrown that information away.

**Alternatives considered**:
- Folding read outcomes into the existing `signals` array as a new
  signal `source` kind (e.g. `source: "collector-error"`): rejected —
  recorded in plan.md's Complexity Tracking; a failed read is evidence
  about the watchdog's own instrument, not about the inspected run, and
  the spec's Out of Scope explicitly protects `diagnose`'s per-signal
  reasoning from having to change, which conflating the two would force.
- Failing the `collect` job outright when any one collector's read
  fails: rejected — this is exactly what FR-017 forbids ("MUST NOT abort
  the watchdog run or discard the evidence that other collectors
  gathered successfully") and what the existing `continue-on-error: true`
  / 5-of-5-failed threshold already gets right; this feature only adds
  visibility, not a new failure mode.

## D7: Where the workflow-author guidance lives (FR-014)

**Decision**: `docs/agent-friendly-workflows.md`'s existing "Mechanics
that bite agents specifically" bullet (currently: "`gh api --paginate`
breaks on `/jobs`: it concatenates JSON documents and jq chokes
downstream. Use `?per_page=100`.", lines 194-195) is replaced with the
correct, general rule: `--paginate` applies `--jq` per page and
concatenates the outputs, so any filter must emit one JSON value per line
(`--jq '.[] | ...'`) and the caller slurps once with `jq -s '.'` if it
needs a single array — never a filter that itself wraps results in `[...]`,
and never no `--jq` at all on an array/object endpoint. This sits in the
same list a maintainer already reads before writing a new agent-bearing
(or any) workflow step, immediately above the "Checklist for a new
agent-bearing workflow" the same document already ends with.

**Rationale**: FR-014 requires the rule to exist "somewhere a maintainer
looks before writing the call, not only in the failure message
afterwards" — this bullet is the closest existing candidate and is
presently wrong (`?per_page=100` only raises the boundary, which the
spec's own Edge Cases section calls out as "one edit away from being
raised" rather than a fix), so replacing it serves both FR-014 and basic
correctness of the document. `docs/architecture.md` was considered and
rejected (per the research phase: it is stage-by-stage narrative, not
workflow-authoring mechanics — no comparable "bite" list exists there).

**Alternatives considered**:
- A new standalone doc section/file just for this rule: rejected as
  unnecessary — one corrected bullet in an existing, already-read list
  fully satisfies FR-014 without adding a second place a maintainer would
  need to know to check.
