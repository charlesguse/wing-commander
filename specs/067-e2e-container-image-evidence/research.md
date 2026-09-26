# Phase 0 Research: Container-Mode Evidence in End-to-End Release Verification

No `[NEEDS CLARIFICATION]` markers remain in spec.md. One decision below (D4)
resolves a question spec.md's own Assumptions section explicitly defers to
planning ("Which job-data signal reliably marks a job as having run inside a
container is a planning question, to be confirmed against real run data
before the detection is built on it rather than assumed"); this plan cannot
drive a real container-mode run from a headless planning session, so D4 is
recorded as a decision made without clarification, with its confirmation
step pushed into quickstart.md and a documented fallback if the chosen
signal proves unreliable.

## D1: Reuse the existing maintainer-credential validation; add no new step for it

**Decision**: Both new evidence reads use
`WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`, whose validity (Write
collaborator on the test repository) and containment (reaches exactly the
test repository, nothing else) are already confirmed by the `maintainer-
credential` step in `auto-release.yml` (`id: maintainer-credential`, ~lines
300–413, introduced by `specs/055-unattended-e2e-gates`). The new evidence
steps gate on `steps.maintainer-credential.outputs.ok == 'true'` the same
way the existing `cleanup` step already does; they perform no independent
credential check.

**Rationale**: FR-003/FR-014 require exactly this reuse — "No new App
installation permission is required" and containment "MUST be confined...
the way the credential's reach is already checked today." Re-deriving a
second validity/containment check would duplicate `specs/055`'s work and
violate CLAUDE.md's single-home rule for shared logic.

**Alternatives considered**: A dedicated validity check scoped to the new
evidence reads' exact permissions (e.g., confirming `Actions: read` and
variable-read access specifically) — rejected because the existing check
already proves Write-collaborator access, which is a superset of what
reading a variable and the run's job data needs; a narrower check would
duplicate the broader one for no additional safety.

## D2: Where the two evidence reads run

**Decision**: Two separate points, matching the spec's own two-source-of-
truth structure (FR-006):

1. **Configuration evidence** (FR-002, FR-007, cases (i)/(ii)/(v)/rate-
   limited): a new step `container-evidence-config`, gated
   `if: steps.mode.outputs.mode == 'container' && steps.maintainer-
   credential.outputs.ok == 'true'`, placed immediately after `maintainer-
   credential` and before `cleanup`/`reset`/`speckit-version`/`scaffold`.
   This is earlier than FR-011 strictly requires (only "before kickoff," at
   line ~687) but cheaper: it also skips the `scaffold` step's fixture
   push on an unconfigured turn, which is wasted work if the turn is going
   to fail anyway. `scaffold` starts at line ~587; `kickoff` at line ~687.
2. **Execution evidence** (FR-006, case (iv)): read inside the existing
   `poll` step, immediately before its one `pass`-writing `write_verdict`
   call (currently `"pass" "" "" "" "$ISSUE_URL" "true"` at line ~1338),
   after the poll loop has observed the chain reach its terminal
   `CLOSED`+`stage:done` state and before that call is permitted to run.

**Rationale**: FR-011/SC-003 require the configuration failure to be cheap
(no kickoff issue, no stage agent turn); the execution evidence can only
exist after the chain has run (spec Assumptions), so it belongs at the one
place a `pass` is ever written, matching the Assumptions' acceptance that
"a passthrough regression still costs a full chain to detect."

**Alternatives considered**: A single evidence step run once at verdict
time — rejected, since it would spend a full stage chain's turns on every
unconfigured turn, violating FR-011/SC-003 outright.

## D3: Reuse the provisioning script's pin-comparison logic instead of re-deriving it

**Decision**: `container-evidence-config` calls into
`.github/scripts/e2e-provisioning/checks.sh`'s existing
`this_repo_container_image()` (reads this repository's own
`WING_COMMANDER_CONTAINER_IMAGE` pin via `gh variable list`) for the
"expected" side of the FR-007 comparison, rather than re-implementing that
read. If `check_container_image_pin()`'s existing signature (built for
`provision-e2e-target.sh`'s mutation context) does not cleanly fit a read-
only comparison call from `auto-release.yml`, the implement stage factors
the shared two-line "read this repo's own pin" logic out of both call
sites into one function in `checks.sh`, rather than leaving
`provision-e2e-target.sh` and the new evidence step each holding a copy.
The exact refactor shape (call the existing function vs. extract a
narrower one) is an implementation-stage decision; the constraint is that
no second copy of the "read this repository's own pin" read is created.

**Rationale**: CLAUDE.md: "Before pasting a `run:` block, jq program, or
shell helper into a second workflow, move it instead." `checks.sh` already
implements and fails closed on exactly this read
(`check_container_image_pin()`, lines ~173–188, matching the spec's Edge
Case "this repository's own pinned reference image cannot be read at
comparison time"). Reusing it also means the fail-closed behavior for an
unreadable pin (FR-007's last sentence) is inherited rather than
re-derived and possibly drifting from the provisioning script's version.

**Alternatives considered**: An independent read in `auto-release.yml`
duplicating the `gh variable list` call — rejected as exactly the pasted-
copy pattern CLAUDE.md's "Shared logic has exactly one home" section
warns against; a rounding or field-name fix to the pin read would then
need to land in two places with nothing failing on a drifted copy.

## D4: The execution-evidence signal (decision made without clarification)

**Decision**: Treat the presence of an `Initialize containers` step in a
stage job's `steps[]` array — returned by the GitHub Actions REST Jobs API
(`GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`, the same
paginated `gh api .../jobs --jq` idiom `watchdog.yml` already uses for its
own job-data reads, ~lines 1020–1110) — as the signal that a job executed
inside a container. GitHub's runner injects `Initialize containers` /
`Stop containers` as synthetic steps around a job's own steps precisely
when that job's workflow YAML declares a `container:` key; a job with no
container carries neither step. This keeps the read to the Jobs API's
existing `steps[]` field with no job-log fetch, matching the spec
Assumptions' "small, constant number of API calls."

**Why this is unconfirmed**: Spec.md's Assumptions section states this
exact question is "a planning question, to be confirmed against real run
data before the detection is built on it rather than assumed." A headless
planning session has no way to drive a real container-mode `auto-release.yml`
run and inspect its actual Jobs API response — that requires a live
Actions run against the test repository, which is implement/validation
work, not plan-stage research. This decision is therefore recorded here as
made without clarification, per this run's instructions, and is called out
in the issue #509 comment.

**Confirmation required before this reaches the pass path**: quickstart.md
Scenario 6 requires inspecting one real container-mode run's Jobs API
response (and one default-runner run's, for contrast) before the execution-
evidence check is allowed to gate a `pass`. If `Initialize containers` is
absent, misnamed, or inconsistent across runner/runs-on combinations, the
documented fallback is scanning the job's log output (the same
`gh api .../jobs/{job_id}/logs` + `##[group]`/`##[endgroup]` idiom
`watchdog.yml` already uses at ~lines 1063–1088) for the runner's own
container-initialization log line, which is a strictly more expensive but
strictly more certain signal.

**Alternatives considered**: Reading `runner_name` or `labels` on the job
— rejected on inspection of the Jobs API shape, since neither field
reflects a job-level `container:` declaration (they describe the runner
the job was dispatched to, not what ran on it); parsing the full job log
unconditionally — rejected as the default because it costs materially more
than a `steps[]` read and the spec's own Assumptions call for a "small,
constant number of API calls," reserved here as the fallback if the
cheaper signal is unconfirmed or wrong.

## D5: No new verdict schema fields; new outcomes carried as `failing_check` text under the existing `fail-infra` outcome

**Decision**: All of FR-005's cases (i) not configured, (ii) drift, (iv)
stage jobs not containerized, and (v) evidence unreadable — plus the
rate-limited variant of (v) — map to the verdict's existing `outcome:
fail-infra` value (`.github/actions/_shared/auto-release-verdict.sh`'s
8-field shape is unchanged: `outcome, verified_head, failing_check,
expected, observed, evidence_url, mode, container_image_configured`).
They are distinguished by new `failing_check` string values (e.g.
`"container image not configured on the test repository"`, `"container
image drift"`, `"stage jobs did not execute inside a container"`,
`"container-mode evidence unreadable"`, `"container-mode evidence
rate-limited"`), consumed by `report`'s existing classification logic.
Case (iii) (configured but unpullable/unauthorized) keeps its current
`failing_check` text verbatim, per FR-005's explicit requirement.
`container_image_configured` is `false` on every one of these outcomes
and `true` only on case (vi), preserving `auto-release-verdict.sh`'s
existing default (its header comment already documents this default,
fixed by `specs/054`'s MF1).

**Rationale**: Matches the precedent `specs/055-unattended-e2e-gates`'
`contracts/verdict-extension.md` set for `fail-gate-stall`: a new outcome
is added as a value within an existing string-typed field, not a JSON
schema change, keeping every existing consumer (the `report` step, the
issue-comment renderer) working unmodified. It also matches spec.md's own
Assumptions ("the reporting shape... [is] unchanged; this feature
constrains only what a container-mode run may conclude and when").

**Alternatives considered**: A dedicated new `outcome` value per FR-005
case (e.g. `fail-container-not-configured`) — rejected because every case
is already "infrastructure-class" in the spec's own vocabulary (FR-002,
FR-004), and a proliferation of near-synonymous outcome values would make
`report`'s classification switch harder to keep in sync with SC-005's
"tell apart" requirement than one outcome with descriptive
`failing_check` text.

## D6: Fail-closed vs. rate-limited distinguished in a pure decision script, not inline

**Decision**: A new pure script,
`.github/actions/_shared/auto-release-container-evidence-decision.sh`,
receives the raw outcome of each evidence fetch (the `gh api`/`gh
variable` exit status and, where available, the HTTP status it reported)
and returns the FR-005 classification plus the `failing_check`/
`expected`/`observed` text to feed `auto-release-verdict.sh`. The fetch
(the `gh api`/`gh variable` calls themselves, in the workflow step's
shell) and the decision (this script) are split the same way
`specs/055`'s `contracts/gate-decision-scripts.md` documents for
`auto-release-e2e-clarify-decision.sh`/`auto-release-e2e-merge-decision.sh`
(research.md D5 there): fetch in the step, decide in a testable,
argument-driven `_shared/` script.

**Rationale**: US2 AC2 requires the rate-limited case to be a verdict
"distinct from the 'not configured' verdict," and IX requires that
distinction to be deterministic code a test can drive directly rather
than inline shell embedded in a 1900-line workflow file. A pure script
taking captured exit/HTTP status as arguments is unit-testable by the new
gate's fixtures (SC-006) without invoking `gh` at all.

**Alternatives considered**: Inline `if`/`case` logic directly in the
workflow step — rejected because it cannot be exercised by a fixture
independently of running the actual workflow step (Constitution VIII's
"every failure branch... exercised by a checked-in fixture" is far cheaper
to satisfy against a standalone script than against inline YAML shell).

## D7: The FR-015 gate — hybrid of an executed-step fixture gate and a structural scan

**Decision**: The new gate combines two techniques already in this
repository, one per half of what FR-015 must prove:

- **Executed-step half** (modeled on `verify-auto-release-report.py`,
  Gate 52): uses `wc_shell_harness.py` to extract and run the shipped
  `container-evidence-config` step's shell and the shipped `poll` step's
  execution-evidence check verbatim, under stubbed `gh`/`date`, against
  one fixture per FR-005 branch (not configured, empty value, drift,
  unreadable, rate-limited, stage jobs not containerized, and the
  passing case) — satisfying SC-006's "every failure branch... exercised
  by a checked-in fixture."
- **Structural half** (modeled on `verify-single-home-idioms.py`, Gate
  60): scans `auto-release.yml` to prove the `poll` step's one
  `pass`-writing `write_verdict` call site is reachable only when both
  evidence steps' `ok`/decision outputs are consulted in its guarding
  condition — so a future edit that adds a second `pass` call site, or
  loosens the existing one's guard, fails the gate rather than silently
  reopening the gap this feature closes. This is the literal target of
  FR-015 ("fails when a container-mode pass path can be reached without
  consulting the evidence").

**Gate number**: `lint-workflows.yml` currently registers through Gate
98 (`verify-gate-wiring.py`'s completeness check covers every
`verify-*.py`/`.sh` file, not just numbered ones). This plan reserves the
next available number, Gate 99, as of this writing; the implement stage
MUST re-check `lint-workflows.yml` immediately before registering, since
another in-flight spec may claim 99 first.

**Rationale**: Constitution VIII requires the gate run "the same subject
with the same arguments locally as it does in CI" — extracting and
running the shipped step's actual shell, rather than a reimplementation
of its logic, is the only way to satisfy that for the executed-step half;
the structural scan is the only technique in this repository's toolkit
that can prove a *reachability* property (no unguarded second pass path)
rather than a per-input behavior property.

**Alternatives considered**: A purely structural gate with no executed-
step fixtures — rejected, since it could confirm the guard's presence
syntactically while missing a logic bug in the decision script itself
(exactly the class of defect VIII's prior-art list describes); a purely
executed-step gate with no structural scan — rejected, since it cannot
prove the negative ("no other pass path exists") that FR-015 asks for.

## D8: Documentation and prior-spec updates are one-site corrections, not a new shared idiom

**Decision**: FR-016's five sites (`docs/setup.md:128`,
`docs/architecture.md`'s container-mode-leg "Reporting" bullet,
`specs/054-e2e-container-coverage/spec.md`'s FR-004/FR-006, and its
`contracts/e2e-container-coverage.md` §1) are each corrected once, in
place, pointing at this feature's contract for the current behavior. None
of this prose is currently pasted more than once (each site independently
narrates the same gap in its own words, not a shared canonical comment),
so CLAUDE.md's canonical-pointer / Gate 47 mechanism does not apply here
— there is no second copy for it to guard.

**Rationale**: Gate 47 (`verify-comment-canonical-pointers.py`) exists to
catch a *second* copy of prose that should point at a canonical source;
none of these five sites is a second copy of another — they are five
independent statements of the same now-stale fact, and FR-016 asks that
each independently state the new fact.

**Alternatives considered**: Introducing one canonical "container-mode
evidence" doc paragraph and making all five sites point at it via
Gate 47 — considered and rejected as disproportionate: `docs/setup.md`
and `docs/architecture.md` describe the behavior for two different
audiences (setup prerequisite vs. architectural narrative) and
legitimately need different wording, and the two `specs/054` sites are
historical spec text whose job is now to point forward, not to restate
current behavior at all.
