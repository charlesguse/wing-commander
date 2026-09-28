# Phase 0 Research: The Stop Decision Answers Both Questions

No `[NEEDS CLARIFICATION]` markers remain in `spec.md` — the three questions
raised during specification were carried to lifecycle issue #612 and answered
there (spec.md "Clarifications" section: FR-013's combined scope, FR-004's
kept redundant check, FR-009's structural-check strategy). This document
records the plan-level design decisions those answers still leave open: the
concrete shape of the two-fact contract, the CLI/stdin wiring, the composite's
new invocation, and the structural rework of Gate 60 and the mutation-proof
gap in Gate 87. None of these decisions changes the spec's requirements; each
picks one concrete way to satisfy an already-fixed FR.

## D1: The two-fact return type

**Decision**: `board_stop_check.py` gains a `StopDecision` named tuple with
two fields — `stand_down` (bool) and `cancel_run_id` (`str | None`) — and
`find_stop_request()` returns one.

**Rationale**: A named tuple is immutable, structurally comparable (`==`
against a literal `StopDecision(True, None)` in a fixture-driven test, no
custom `__eq__`), and matches this file's own established idiom elsewhere in
the gate suite (`Finding = namedtuple(...)` in `verify-single-home-idioms.py`).
It also serializes trivially to the JSON object `main()` prints
(`{"stand_down": ..., "cancel_run_id": ...}` via `_asdict()`), which is the
CLI contract D3 below defines.

**Alternatives considered**:
- A plain `dict` — rejected: no field-name typo protection, and every
  existing fixture/gate helper in this module already prefers named,
  attribute-accessed structures over dict indexing.
- A `dataclass` — equivalent in effect to a named tuple here (two fields, no
  behaviour); a named tuple is chosen only because it is the pattern already
  in the file this module sits beside, not for any dataclass shortcoming.
- Two separate return values (a bool and a nullable string, unpacked by every
  caller) — rejected: `find_stop_request()` has exactly one production
  caller and several test callers; a single named return value is what lets
  `main()` and every fixture compare "the decision" as one unit rather than
  two positionally-ordered values that could be swapped by a call-site typo.

## D2: Keep the function's name

**Decision**: The decision function keeps the name `find_stop_request`; only
its return type and docstring change.

**Rationale**: The name is already the one every governing comment points
at — `board_stop_check.py`'s own module docstring, Gate 60's
`DECLARED_HOMES["board-stop-check"]` comment, and issue #612's own quoted
snippet all call it `find_stop_request()`. Renaming it would touch strictly
more surface for no requirement in scope (FR-001/FR-003 ask for a contract
change, not a rename) and would cost a second round of "why did this name
change" review for no behavioural benefit.

**Alternatives considered**: A verb that reads more accurately against the
new two-fact contract (e.g. `decide_stop`) — rejected per the rationale
above; the fix here is what the function *returns*, not what it is called.

## D3: The CLI/stdin contract

**Decision**: `main()`'s stdin contract is unchanged — it still reads one
JSON object `{"comments": [...], "current_run_id": "...", "bot_login": "..."}`
from stdin. Its stdout contract changes: on success it prints exactly one
line, the JSON object `{"stand_down": <bool>, "cancel_run_id": <string or
null>}`, always — including the `stand_down: false` case (today's `main()`
prints nothing at all when there is no stop request). On any failure
(malformed payload, an uncaught exception) it prints nothing to stdout,
writes Python's normal traceback to stderr, and exits non-zero — behaviour
`main()` already has for free via `json.load(sys.stdin)` raising on bad
input, so no new error-handling code is required in the module itself.

**Rationale**: Changing only one side of the interface (output) keeps this
plan's diff to the one contract FR-001/FR-003 actually redefine. Printing a
JSON object unconditionally on success (rather than an empty line for
"false") gives the composite one unambiguous parse rather than two shapes to
distinguish, and lets a `jq -e` read of `.stand_down`/`.cancel_run_id` fail
loudly (FR-007) if `main()` ever printed something that is not valid JSON —
which, combined with the process's own non-zero exit on a genuine crash, is
the layered "fail loud" behaviour D5 below wires into the composite.

**Alternatives considered**:
- Encode `stand_down` in the process exit code and `cancel_run_id` (or
  nothing) on stdout — rejected: it overloads the exit code with domain data
  and collides with the exit code's other job under FR-007, which is
  exclusively "did the decision compute at all."
- Two lines of plain text (`stand_down\ncancel_run_id`) — rejected: a JSON
  object is one `jq` call away from either field and is the shape `main()`'s
  own docstring can describe unambiguously (FR-005), where two positional
  text lines invite a caller to swap them.

## D4: The composite's new invocation

**Decision**: `wing-commander-board-stop-check/action.yml`'s `check` step
keeps its existing `gh api ... --paginate --jq '...' | jq -s '.' >
"$RUNNER_TEMP/board-stop-check-comments.json"` read (FR-008's App-token read
is unchanged), then builds the same stdin payload `main()` already expects
with `jq` (folding in `$GITHUB_RUN_ID` and `$BOT_LOGIN` alongside the comments
array already on disk) and pipes it directly into
`python3 .github/scripts/board_stop_check.py` — no `sys.path.insert`, no
`from board_stop_check import find_stop_request`, no inline `python3 -c`
block. The script's own working directory is already the repository root
(the composite runs after this repository's self-checkout), so the relative
path resolves the same way every other `python3 .github/scripts/*.py`
invocation in this repository's workflows already does.

**Rationale**: This is the direct reading of FR-006 ("obtain the decision by
invoking `board_stop_check.py` through its own documented stdin/stdout
interface... MUST NOT contain an inline re-implementation of that call
convention") and User Story 2's independent test ("no inline Python module
import of `board_stop_check` and no `sys.path` manipulation"). Reusing `jq`
(already a dependency of this same step) to assemble the payload, rather than
introducing a second templating mechanism, keeps the diff to the one
`run:` block FR-006 names.

**Alternatives considered**: Passing `current_run_id`/`bot_login` as CLI
arguments instead of folding them into the stdin JSON — rejected: it would
change `main()`'s documented stdin contract (D3 deliberately leaves it
alone) for no requirement in scope, and would require the module's docstring
to describe two different invocation shapes (stdin-only vs. stdin+argv)
where one already suffices.

## D5: Fail-loud wiring in the composite

**Decision**: After capturing `board_stop_check.py`'s stdout into a shell
variable, the `check` step validates it with `jq -e '.stand_down |
type == "boolean"' >/dev/null` (or equivalent) before reading
`.cancel_run_id`, printing an explicit `::error::` and failing the step if
that validation does not hold. This is in addition to, not instead of,
`bash`'s own `set -e`/`pipefail` already failing the step when the `python3`
process itself exits non-zero.

**Rationale**: FR-007 requires the step to "fail loudly... and MUST NOT treat
an unreadable answer as 'no stop request'." A crashing `python3` process
already satisfies this for free (empty stdout, non-zero exit, `set -e`
propagates). The extra `jq -e` validation covers the residual case Edge
Cases names explicitly — "a malformed or empty comments payload" reaching
`main()` in a way that does not raise inside `json.load` (e.g. valid JSON
that is not an object) — and gives Gate 87's new composite-shell fixture
(contracts/gate-87-coverage.md) something concrete to drive: a stub `gh` that
serves a payload `board_stop_check.py` cannot answer, asserting the step
fails rather than resolving to `paused=false`.

**Alternatives considered**: Relying solely on `set -e`/`pipefail` and the
process exit code, with no explicit `jq -e` check — rejected: it leaves the
"valid JSON, wrong shape" edge case unproven and untestable by name, where
Constitution VIII asks every failure branch a gate ships to be exercised by a
checked-in fixture.

## D6: The composite's redundant "not this run" check (FR-004)

**Decision**: The composite keeps exactly one shell comparison of the
decision's `cancel_run_id` against `$GITHUB_RUN_ID` before `gh run cancel`,
now reading `cancel_run_id` (parsed from `board_stop_check.py`'s JSON output)
in place of today's `stop_run_id`. Its guarding comment is rewritten to say,
in place, that this check is deliberately redundant with
`find_stop_request()`'s own contract (D1/D9: the function never returns the
current run as `cancel_run_id`), that the function's contract is the primary
guard, and that the check is kept anyway because cancelling a run is not
recoverable by retry — matching the belt-and-braces framing the existing
workflow-path and repository-target guards already carry in the same step.

**Rationale**: This is FR-004 verbatim, resolved by the spec's own
Clarifications session; no design choice remains except naming exactly which
variable the comparison now reads (`cancel_run_id`, since `stop_run_id` no
longer exists as a name once D1–D4 land).

## D7: Gate 60's `check_board_stop_check` — structural rework (FR-009)

**Decision**: `check_board_stop_check()` stops scanning whole-file text for
literal co-occurrence of `BOARD_STOP_CHECK_FRAGMENTS` (`"from board_stop_check
import find_stop_request"`, `"gh run cancel"`,
`"board-stop-check-comments.json"`). It instead follows `check_token_mint()`'s
existing pattern: YAML-parse the subject (`load_yaml`, never grep the raw
file), resolve each job's (or composite's own `runs.steps`) step list via the
already-shared `_step_lists(doc)` helper, and — per step list, excluding the
declared home's own directory exactly as today — test for co-occurrence of
two structural facts across that step list's concatenated `run:` text:

1. **Obtains a stop decision from the stop-check module** — a regex matching
   either calling convention: `board_stop_check\.py` (the post-change CLI
   invocation this feature introduces) or `from board_stop_check import
   find_stop_request` (the pre-change import style, kept in the pattern so a
   contributor who copies the *old* idiom from git history, or from another
   repository's fork of this one, is still caught — FR-009's "regardless of
   the style it is written in").
2. **Performs a run cancellation** — `gh run cancel`, unchanged from today
   (this fragment is not the one the fix deletes, and remains unique enough
   in this codebase's shell that `check_dispatch_and_wait`'s own precedent —
   co-occurrence, not a bare fragment — already documents why `gh run cancel`
   alone is safe to key on when paired with fact 1).

A step list is only a finding when *both* facts are present somewhere in its
own steps, matching FR-009's "a site is the idiom when its resolved steps
both obtain a stop decision... and perform a run cancellation" and Acceptance
Scenario 3 ("a subject file whose steps reference the stop-check module but
orchestrate no run cancellation... MUST NOT be flagged").

**Rationale**: This satisfies FR-009's two explicit requirements at once —
"MUST NOT depend on a literal fragment that this change itself deletes"
(the check no longer keys on the import line at all; it is one of two
alternatives, not the sole trigger) and "MUST do so structurally... parse
each job's step list and reason about the resolved steps rather than about
literal text anywhere in the file" (mirrors `check_token_mint`'s per-step-list
resolution instead of `check_orphan_reset`'s file-wide literal scan). Scoping
to a step list (a job, or a composite's own `runs.steps`) rather than the
whole file is what makes fact 1 and fact 2 have to appear *together* in one
orchestration, not merely somewhere in a large file that also happens to
mention `gh run cancel` for an unrelated reason elsewhere (the same
false-positive concern `check_failure_issue`'s docstring already measured
empirically for its own per-step scoping).

**Alternatives considered**:
- Keep file-wide scope (like `check_orphan_reset`) instead of per-step-list —
  rejected: `gh run cancel` alone already appears in `pr-conversation.yml`'s
  own, unrelated stop procedure (noted in the existing
  `BOARD_STOP_CHECK_FRAGMENTS` comment); file-wide co-occurrence with a bare
  module-name mention would risk flagging that file the moment it also
  imports or references `board_stop_check` for legitimate, unrelated reasons.
  Per-step-list scoping is strictly narrower and was not shown to
  false-positive against the real tree in the way `check_failure_issue`'s
  docstring already found for a different check.
- Match only the CLI style, dropping the import-style alternative entirely —
  rejected: FR-009 explicitly says "regardless of the style it is written
  in, including one written against the module's CLI" — "including" implies
  the CLI style is one of at least two the check must catch, not the only
  one.

## D8: Updating Gate 60's fixtures and self-test (FR-010)

**Decision**: Three artifacts move together, in the same change as D7:

- `DECLARED_HOMES["board-stop-check"]`'s comment is rewritten to describe the
  post-change idiom (obtain a decision from `board_stop_check.py`'s CLI, then
  `gh run cancel` whatever it names) rather than the pre-change import.
- `_clean_tree()`'s planted fixture at the declared home is rewritten to the
  post-change shape — piping a payload to `board_stop_check.py` and calling
  `gh run cancel` — so the clean-tree self-test exercises the real shape Gate
  60 must stay silent on, not a shape that no longer resembles the shipped
  composite.
- `run_selftest()`'s existing `selftest_third_paste_fails("board-stop-check",
  ...)` call plants the *post-change* style (piping to `board_stop_check.py`)
  in a second workflow and asserts a finding, per FR-010's "a finding on a
  planted paste written in the post-change style." A second, new self-test
  case plants a file whose steps reference `board_stop_check.py` (fact 1)
  without any `gh run cancel` (no fact 2) and asserts **no** finding — the
  direct self-test analogue of Acceptance Scenario 3 and FR-010's third
  named direction ("silent on a planted file that references the module
  without orchestrating a cancel").

**Rationale**: FR-010 names all three obligations explicitly ("Gate 60's
declared-home comment, clean-tree fixture and third-paste self-test MUST be
updated in the same change") plus the third self-test direction; this is a
transcription of that requirement into the three concrete artifacts that
already exist in `verify-single-home-idioms.py` today.

## D9: Proving the no-self-cancel invariant is load-bearing (FR-011)

**Decision**: Two independent mutation proofs, at two different layers,
because the invariant now exists at two different layers (D1's function
contract, and D6's redundant shell comparison):

1. **Decision-function layer** (closes the literal gap the spec's "gate gap"
   section names). `verify-board-stop-check.py`'s existing `MUTATIONS` tuple
   gains one entry that reintroduces the pre-fix bug directly in
   `find_stop_request()`'s own logic: when no earlier run's marker exists,
   return the current run's id as `cancel_run_id` instead of `None` (i.e.
   revert FR-003's rule). `mutation_check()` already runs every `MUTATIONS`
   entry through `run_fixtures()`/`run_command_cases()` and requires at least
   one checked-in fixture to fail; the existing `first-pass-own-run-only.json`
   fixture (current-run-only announcement, a stop present, expecting
   `cancel_run_id: null` under the new shape) already fails under this
   mutation with no change needed beyond updating its expected shape (D1).
   This proof runs entirely inside the Python process — no shell, no stub
   `gh`, no `RUNS` table — so its failure is mechanically not attributable to
   the unreadable-run or workflow-path guards (they do not exist at this
   layer at all), which is exactly what FR-011 requires ("that failure MUST
   NOT be attributable to the unreadable-run or workflow-path guards
   suppressing the cancel for an unrelated reason").
2. **Composite-shell layer** (closes the specific case the spec's "gate gap"
   section traces through the existing harness: `GITHUB_RUN_ID` is always
   `"999"` in `_run_shell_case`'s environment, and `999` is absent from
   `RUNS`, so the *existing* forged-marker shell case is saved by the
   unreadable-run guard regardless of whether the redundant `!=
   $GITHUB_RUN_ID` comparison is present). `RUNS` gains a `"999"` entry
   (`in_progress`, `path: OWN_PATH`, matching repository) so a run
   announcing itself as the current run is, for the first time in this
   fixture set, readable, same-workflow, and non-completed — every *other*
   guard's reason to suppress a cancel is removed. `SHELL_CASES` gains a case
   with only `_marker(999)` (no earlier run) plus `STOP`, asserting
   `want_cancel=None` under the shipped (correct) `board_stop_check.py`. A
   second run of `composite_shell_check()`'s existing `GUARD_LINE_RE`-style
   mutation is extended to also disable the redundant comparison line (in
   addition to the existing workflow-path guard mutation, unchanged) and
   re-run against a copy of `board_stop_check.py` that carries mutation 1
   above (the function-level self-cancel bug) — the combination the
   redundant check exists to catch per FR-004's own stated reason ("a cancel
   is not recoverable by retry"). With the corrected function on its own, the
   new `999`-only case already proves the *function's* contract holds
   end-to-end through the real composite shell (no mutation needed for that
   half); the combined mutation proves the *shell comparison* is
   independently load-bearing as a backstop against a future regression in
   the function, which is what "defence in depth" (FR-004) is for.

**Rationale**: The spec's own "gate gap" section traces the exact mechanism
by which the current single shell case is saved by an unrelated guard
(`999` absent from `RUNS`) rather than by the self-cancel comparison it was
supposed to be testing — Constitution VIII's "not suppressible by an
unrelated gate/guard that merely shares its job" applies here to guards
within one gate's own fixture, not only to whole gates. Splitting the proof
into a pure-function mutation (fast, unambiguous, and structurally incapable
of being saved by a shell-only guard) plus a shell-level mutation that
specifically needs the new `999`-readable fixture to be meaningful is the
only way to satisfy FR-011's "not attributable to ... an unrelated reason"
clause for both layers the invariant now lives in.

**Alternatives considered**: Proving the invariant only at the shell layer
(mutate the composite's own guard line, as `composite_shell_check()` already
does for the workflow-path guard) — rejected on its own: it would still
leave the *function's* FR-003 contract itself unproven by mutation (the
literal thing FR-001/FR-003 introduce), and would require every shell case
to route through a mutated `board_stop_check.py` on disk merely to exercise
a bug that is far cheaper and far more precisely located at the Python-object
level `MUTATIONS` already operates at.
