# Phase 0 Research: Gate 59 resolves the dispatch idiom wherever it lives

Spec has no unresolved `[NEEDS CLARIFICATION]` markers — the three that
existed were resolved in clarification (issue #595) and are encoded
directly into FR-025–FR-028 and the Assumptions section. This document
records the design decisions a plan has to make that the spec leaves to
implementation judgment, each grounded in a fact gathered from the
current tree (not guessed), so tasks/implement can build against it
without re-deriving the same research.

## D1. Effective-shell corpus construction (FR-001, FR-002, FR-006)

**Decision**: Gate 59 builds its search corpus for checks 3 and 5 by
walking `auto-release.yml`'s `dispatch-release` job's steps in file
order. For each step:
- a `run:` step contributes its own shell text, tagged with source
  `auto-release.yml:<line>`;
- a `uses:` step whose value matches a local-composite reference
  (`./.github/actions/<name>` — the bare form `auto-release.yml` already
  uses for `board-loop.yml`'s own call to this composite at
  `board-loop.yml:3754`, confirmed as the consuming-instrument
  convention by specs/049 research.md D2) is resolved: its `action.yml`
  is loaded and its `runs.steps[*].run` shell is spliced in, in the
  composite's own step order, tagged with source
  `<composite-path>:<line>`, at the position the `uses:` step occupied;
- any other `uses:` (e.g. `actions/checkout@v5`) contributes nothing —
  it is not shell to search.

Checks 3 and 5 run against this spliced, ordered corpus exactly as they
run against `auto_lines` today (same substring/window logic), so a
relocation that changes *where* the shell lives but not *what order it
executes in relative to the job's own steps* passes unchanged (SC-001).

**Rationale**: This is the only construction that satisfies FR-002 (pass
when the shell moves entirely into a composite) without also satisfying
"pass when the shell is deleted" (FR-003) — resolving through the actual
`uses:` graph, rather than a global search over every file, is also what
makes FR-006 true by construction: a composite that happens to contain
the same fragment but that `dispatch-release` never calls is never part
of this corpus.

**Alternatives considered**: A global scan of every composite under
`.github/actions/**` for the checked fragments (à la Gate 60's structural
scan) was rejected — that shape can credit an invariant satisfied by a
composite the job doesn't call (violates FR-006), and it cannot express
"this composite is reached, so the invariant may live here" as opposed
to "this text exists somewhere in the repository."

## D2. Attribution (FR-005)

**Decision**: Each of checks 3 and 5's pass path records which tagged
source (`auto-release.yml` or the resolved composite's path) contained
the matching construct, and `run_gate()`'s pass-path output prints one
line per check naming that location (e.g. `Gate 59: check 3 (correlation)
satisfied in .github/actions/wing-commander-dispatch-and-wait/action.yml`).
Check 4 is always attributed to `auto-release.yml` itself, since FR-027
forbids it living anywhere else.

**Rationale**: FR-005 requires this explicitly ("so a maintainer reading
a pass can see whether the guarantee currently lives in the workflow or
in a composite"). This is a pure addition to the existing pass-path
`print()` in `run_gate()` — no existing failure-message shape changes.

## D3. Unresolvable references and the one-level-deep rule (FR-004, Edge Cases)

**Decision**: Three distinct outcomes, not two:
1. The job step's `uses:` names a local-composite path whose `action.yml`
   does not exist on disk → hard fail, `::error::` naming the exact
   unresolvable path. Never treated as a pass or as "the invariant was
   deleted."
2. The path resolves (the file exists) but neither its own shell nor a
   further local `uses:` inside it contains the checked construct →
   ordinary check-specific failure, the same clause-naming message
   checks 3/4/5 already produce for a same-file removal today. This is
   the Edge Cases distinction ("resolves but whose shell no longer
   contains the searched-for construct... distinguishable from 'the
   composite is missing', and both fail" — distinguishable by message,
   both are still failures).
3. The path resolves, the construct is absent, AND the resolved
   composite's own steps contain a further local `uses:` to a *second*
   composite (two levels deep) → hard fail, `::error::` naming that
   second-level reference as unresolved, per the Assumptions section
   ("treated as unresolvable and fails loudly... rather than being
   followed indefinitely or silently abandoned"). Gate 59 never opens a
   third file.

**Rationale**: Directly required by FR-004 and the spec's own Edge
Cases and Assumptions sections; distinguishing (2) from (3) is what lets
SC-004's "never a pass" bar hold for a genuinely broken reference while
still letting an ordinary in-place weakening (2) produce the same
clause-specific message checks 3/4/5 already ship (SC-003).

## D4. Check 4 stays job-only, including its forbidden-construct scan (FR-027)

**Decision**: `tag_state_outcome_errors` (check 4) is restricted to the
job's own `run:` step text only — it never inspects a resolved
composite's shell, for the positive check (`TAG_REV_PARSE` present) or
for the forbidden constructs (`gh run watch`, `.conclusion`). If the
tag-state shell is found only inside a composite the job calls, that is
itself the failure (User Story 1 scenario 7): the search that would find
it there simply never runs, so the positive check reports "not found in
the job's own text" — worded to name the tag-state clause, not to be
confused with a wholesale deletion.

**Rationale**: FR-027 is explicit that the composite "gains no
release-specific 'expected ref' input" and that the gate "MUST fail if
that shell is found only inside a composite" — scoping check 4's entire
search (not just its positive assertion) to the job's own text is what
makes a relocation of *this* check indistinguishable from a *deletion*
of it, which is the correct behavior per scenario 7 (unlike checks 3/5,
where that same indistinguishability was the defect this feature fixes).

## D5. Self-test fixture matrix (FR-007, SC-002, SC-003)

**Decision**: The existing `CLEAN_RELEASE`/`CLEAN_AUTO` two-fixture
self-test shape (release.yml + auto-release.yml text) grows a third
in-memory fixture, `CLEAN_COMPOSITE`, representing a resolved composite
whose shell carries checks 3 and 5's constructs, plus a `CLEAN_AUTO_VIA_COMPOSITE`
auto-release.yml fixture whose `dispatch-release` job calls it instead of
inlining the correlation/wait shell. `contract_errors` gains a
`resolve=None` parameter: when given, it stands in for filesystem
resolution of local `uses:` references against an in-memory
`{path: text}` map, so the self-test never touches real files (matching
every other gate's `--self-test` discipline of exercising branches
in-memory, e.g. Gate 50's `check(...)`/`fixture(...)` helper shape this
gate's docstring already cites as its model).

Required fixture cases, each asserted to fail naming only its own clause
(SC-003) except where noted:
- clean, fully inline (today's shape) — passes (existing).
- clean, checks 3 & 5 relocated into `CLEAN_COMPOSITE` — passes (**new**,
  proves SC-001's first half).
- check 3 weakened, inline — fails, recency clause only (existing).
- check 3 weakened, composite-resolved — fails, recency clause only
  (**new**).
- check 5 weakened, inline — fails, mid-flight-read clause only
  (existing).
- check 5 weakened, composite-resolved — fails, mid-flight-read clause
  only (**new**).
- check 4 weakened, inline (the only arrangement FR-027 allows) — fails,
  tag-state clause only (existing, unchanged).
- check 4's shell relocated into a composite, otherwise unweakened —
  fails, tag-state clause only (**new**, proves SC-001's second half /
  User Story 1 scenario 7).
- the job's `uses:` names a composite path that does not exist — fails
  loudly naming that path, not a pass and not "invariant deleted"
  (**new**, D3 case 1, SC-004).
- the job's composite resolves, but that composite itself defers to a
  second-level `uses:` with no construct in the first level — fails
  loudly naming the second-level reference (**new**, D3 case 3).

Checks 1 and 2 (`release.yml`) are untouched by this feature (FR-009) and
keep their existing single-arrangement fixtures.

**Rationale**: FR-007 requires "every branch that can occur in both the
inline-satisfied and composite-satisfied arrangements has a fixture in
each; the tag-state branches... are exercised in the one arrangement
they have, including the fixture that moves tag-state verification into
a composite." The list above is that requirement enumerated one-to-one.

## D6. Widened composite outputs and the caller-settable uncorrelated wait (FR-011–FR-014, FR-026, FR-028)

**Decision**: `wing-commander-dispatch-and-wait/action.yml` gains four
new outputs and one new input, additive only (FR-013, FR-016):

| New surface | Kind | Notes |
|---|---|---|
| `dispatch-rejected` | output, `"true"`/`"false"` | true iff `gh workflow run` itself failed; correlation search never runs in that case |
| `correlation` | output, `found` \| `ambiguous` \| `not-observed` | discrete, never collapsed into `run-url`'s existing empty-on-ambiguous-or-absent behavior (FR-012) |
| `correlated-run-id` | output, may be empty | the id half of what `run-url` already carries, exposed as its own fact per FR-026 ("no caller may be required to parse a structured value to read a single fact") |
| `request-time` | output, ISO-8601 string | the request time the correlation search searched forward from — reported even on `not-observed` (User Story 2 scenario 3) |
| `uncorrelated-wait-seconds` | input, default `"0"` | bounded wait applied only when `correlation` never reaches `found` (FR-014); default `0` preserves `board-loop.yml`'s prove job, which does not wait on this path today |

`run-url` and `conclusion` keep their existing names, meanings, and
empty/`timeout` conventions unchanged (FR-013) — `auto-release.yml`'s
call site is the reason two of these facts (`correlation`,
`correlated-run-id`) are being widened onto discrete outputs rather than
derived by the caller from `run-url` alone, exactly per FR-026's
no-structured-value rule.

**Rationale**: `auto-release.yml`'s `report` job distinguishes six facts
today (research.md's own read of `dispatch-release`'s current
`outputs:` block: `correlation`, `correlated-run-id`,
`correlated-run-url`, `tag-matches`, `request-time`,
`dispatch-rejected`). `tag-matches` is decided by the job's own
post-composite shell (D9) and never becomes a composite output — the
other five map onto the composite's existing (`run-url` →
`correlated-run-url`, `conclusion` — unused by `report` today but kept)
plus the four new outputs above. This is the minimum widening that lets
User Story 3's repoint reproduce every fact `report` reads today (FR-018)
without adding an output no caller uses.

**Alternatives considered**: A single structured JSON output
(`facts: '{"correlation": "found", ...}'`) was rejected outright by
FR-026. Renaming `run-url`/`conclusion` to match the new facts' naming
style was rejected by FR-013/FR-016 — existing callers (`board-loop.yml`)
read those two names today and must not need an edit (SC-009).

## D7. FR-028's deferred-hook record

**Decision**: The composite's own header comment (already documenting,
per its current text, that `auto-release.yml`'s call site is not yet
repointed — that sentence is deleted once User Story 3 lands) gains a
permanent paragraph stating that a generic post-wait verification hook
(a caller-supplied "does the state I expected to change actually show
it" check, run after the terminal-status wait and before the composite
returns) was considered and deliberately deferred: this composite stays
generic, `auto-release.yml`'s own tag-state check is the only consumer
of that shape today, and a second caller needing the same shape should
extend the composite's contract rather than paste a second verification
copy.

**Rationale**: FR-028 requires this recorded "on the composite's
contract" specifically so a future maintainer reaches for the deferred
decision instead of re-deriving it; the composite's own `action.yml`
header is where every other deliberate-scope-boundary note in this file
already lives (see its current T054-blocker paragraph, which this
feature's User Story 3 replaces with the resolution above).

## D8. A new runtime harness for the tag-state invariant (FR-025, third check)

**Decision**: A new gate, next available number **99** as of this plan
(re-check for a collision with any concurrently-landing spec before
claiming it, matching every prior gate's own numbering caveat — e.g.
`regression-gate.md`'s own text) — `.github/scripts/verify-auto-release-tag-state-runtime.py`,
following Gate 67's own shape (`verify-auto-release-credential-step.py`):
`find_step` extracts `dispatch-release`'s post-composite "decide
`released` from tag state" step (D9 names the step split), `run_step`
executes it with a stubbed `git` on `PATH` for the tag-matches/does-not-match
cases, and asserts `tag-matches` flips correctly — proving the invariant
at runtime, not just resolving its text. This harness is scoped to User
Story 3 (it needs the post-repoint job shape, where the tag-decision
step is isolable from the composite call) rather than User Story 1.

The correlation and wait-before-tag-read invariants' own runtime proof
(the other two-thirds of FR-025) is **already covered** by Gate 88's
existing `dispatch-and-wait-tests/run-tests.sh` (it already executes the
composite's own shipped shell against a stubbed `gh`, per its own header
comment) — that harness needs widening (User Story 2's new fixtures for
D6's new outputs) but not a new gate. Only the tag-state invariant, which
stays inline in the job per FR-027, has no existing runtime harness.

**Rationale**: FR-025 requires runtime proof of all three invariants,
executing "the shipped shell that satisfies each invariant." Gate 59
itself stays textual (matching Gate 50/51's established shape, restated
in `regression-gate.md`) — SC-010 is met by pairing it with Gate 88
(already existing, widened) for two invariants and this new gate for the
third, rather than rewriting Gate 59 into an execution harness, which
the spec's own Non-Goals-equivalent language ("a textual pass... MUST
NOT be treated as sufficient evidence... alone", FR-025) permits by not
requiring the *same* gate to do both jobs.

## D9. Repoint mapping — `dispatch-release`'s post-repoint step shape (FR-017–FR-019, FR-027)

**Decision**: `dispatch-release`'s single today's-shape step ("Dispatch
release.yml and correlate its run") splits into two job steps after User
Story 3 lands:
1. **"Dispatch and correlate release.yml"** — mints the token, calls
   `wing-commander-dispatch-and-wait` via `uses:` with
   `workflow-file: release.yml`, `workflow-inputs` carrying `version`,
   `breaking`, `breaking-notes`, `commit` (`VERIFIED_HEAD`),
   `attempt-token: <token>`, `uncorrelated-wait-seconds: "90"` (D6's new
   input, preserving today's fixed 90-second wait exactly).
2. **"Decide release outcome from tag state"** — a `run:` step reading
   only `VERSION`/`VERIFIED_HEAD` env and the prior step's
   `correlated-run-url`/`conclusion`/`correlation`/`correlated-run-id`/
   `request-time`/`dispatch-rejected` outputs (passed through, never
   recomputed) to build the job's own `outputs:` block, plus the
   independent `git fetch`/`rev-parse` tag comparison (FR-019, FR-027) —
   this is the step D8's new harness extracts.

**Rationale**: This is the shape that lets check 4 (D4) and the new
runtime harness (D8) address one isolable step, and it is the natural
seam FR-018 draws: everything the composite widened (D6) is data the
first step already produces; the tag-state decision the second step
makes never reads any of it as an input to the *decision*, only to the
*passthrough* — matching FR-019's "decided independently of the
correlated run's conclusion and of whether correlation succeeded at
all."

## D10. Single-home enforcement completes T056's second half (FR-020, FR-021)

**Decision**: `single-home-waivers.json`'s `dispatch-and-wait` /
`auto-release.yml` entry (issue #408) is deleted in the same PR that
lands User Story 3. `verify-single-home-idioms.py`'s existing
`check_dispatch_and_wait` (Gate 60) needs no new detection logic — it
already fails on a *third* paste of the fragment co-occurrence anywhere
outside the declared home; removing the waiver is what makes it start
failing `auto-release.yml`'s own current inline copy too, which is
exactly tasks.md T056's documented "second half," blocked on T054 until
now.

**Rationale**: Directly stated in both the waiver's own `reason` field
("Remove this waiver when T054 lands") and T056's own note ("removing
that waiver is the completion signal for both T054 and the rest of this
task"). No new Gate 60 code is needed — confirmed by reading
`check_dispatch_and_wait` (`.github/scripts/verify-single-home-idioms.py:501-518`),
which already scans every subject file outside the declared home
(`wing-commander-dispatch-and-wait/action.yml`) for the fragment
co-occurrence; `auto-release.yml`'s own inline copy already trips it
today and is only saved by the waiver.

## D11. Provenance updates (FR-023)

**Decision**: `specs/057-autonomous-board-loop/tasks.md` T054 and T056
(the second half) are marked done, each with a one-line pointer to this
feature (`specs/081-composite-aware-dispatch-gate`) rather than restating
the resolution inline — following this repository's canonical-pointer
convention. `specs/048-correlated-release-dispatch/contracts/regression-gate.md`
gains a note that its "five checks" table's checks 3 and 5 now resolve
through a called composite (pointing at this feature's
`contracts/resolving-gate.md`), and that its own self-test fixture shape
section is superseded by D5 above for those two checks.

**Rationale**: FR-023 requires updating "no task or contract may keep
describing a constraint that no longer holds" — T054/T056's blocker text
and `regression-gate.md`'s "textual, line-based... over the raw YAML
text of exactly two files" framing are exactly the constraints this
feature lifts for checks 3 and 5.

## D12. Post-merge proof (FR-022, SC-008)

**Decision**: After User Story 3 merges, re-drive `auto-release.yml`
once via `gh workflow run auto-release.yml` — confirmed a valid,
directly-dispatchable entry point: `auto-release.yml:15-17` already
declares `workflow_dispatch: {}` alongside its `schedule:` trigger, with
no required inputs — and record the resulting `run-url`/outcome on the
PR or lifecycle issue #595, per
CLAUDE.md's "prove" step and Constitution X's "a fix to behaviour that
only runs in Actions is proven after merge by re-driving one run."

**Rationale**: This behavior — a live release dispatch — cannot be
proven any other way (research.md D-nothing-else covers a live Actions
run); FR-022 requires it explicitly and SC-008 makes it measurable
(exactly one real run, recorded).
