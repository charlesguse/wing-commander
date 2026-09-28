# Phase 0 Research: An Honest Read-Failure Policy for board-stop-check's Closed Check

spec.md carries no `[NEEDS CLARIFICATION]` markers — the owner already
resolved every open trade-off on issue #623 and recorded the resolutions
inline under "Clarifications" (fail-loud policy, FR-005 mootness, Gate 24
scope, sequencing with spec 087). This research phase resolves the *design*
unknowns those answers leave open, by reading the current shipped
implementation (`wing-commander-board-stop-check/action.yml`,
`wing-commander-lifecycle-gate/action.yml`, `board-loop.yml`'s `prove` job,
`verify-board-stop-check.py`, `verify-comment-canonical-pointers.py`,
`verify-gate-24.py`) and choosing among the options each leaves open.

## D1: Reorder the composite's two steps so FR-002 and FR-003 both hold

**Decision**: Move the "kill-switch/stop-request re-check" step (`id:
check`) to run **first**, unconditionally, with no dependency on
`closed-check`'s output. Move `closed-check` to run **second**, still gated
`if: inputs.check-issue-closed == 'true'`, with `continue-on-error: true`
removed entirely (FR-002's literal text). `check` drops its `ISSUE_IS_OPEN`
env var and the `if [ "$ISSUE_IS_OPEN" = "false" ]` block; the CLOSED
signal moves out of `check`'s own `paused` computation and into the
composite's own `outputs.paused` expression (D2).

**Rationale**: FR-002 requires `continue-on-error: true` gone from
`closed-check`; FR-003 requires the kill-switch re-check and stop-request
scan to still run, and to still be able to report `paused=true`, even when
`closed-check` fails totally — and its own parenthetical names the
constraint directly: "as shipped, `closed-check` precedes the step that
performs those two checks, so satisfying FR-002 without violating this
requirement constrains where the failure surfaces." As shipped, `check`
runs *after* `closed-check` and is gated by the composite's default
step-sequencing (an earlier unguarded failure skips every later step with
no `always()`/`!cancelled()`/`failure()`). Simply deleting
`continue-on-error: true` in place, with no reorder, would make a failed
`closed-check` skip `check` entirely — silently dropping the kill-switch
re-check and, concretely, the `gh run cancel` side effect that stands down
a genuinely still-running earlier run (edge case: "the kill switch is
already on and the state read fails... a failed closed-check can never
*un*-pause"). Reordering so `check` runs first and unconditionally makes
that impossible by construction: the kill-switch/stop-request logic (and
its cancel side effect) always executes before `closed-check` gets a
chance to fail loud.

**Consequence for the calling job**: `board-loop.yml`'s `prove` job already
gates both durable-action steps ("Close the issue on the merge evidence
alone" and "Re-drive the changed behaviour to prove the fix") on
`steps.killswitch-recheck.outputs.paused != 'true'` with no `if:` status
function of their own — GitHub Actions implicitly ANDs a bare `if:` with
`success()`. When the composite's own `closed-check` step fails (no
`continue-on-error`), the calling `uses: ./.github/actions/
wing-commander-board-stop-check` step is marked failed, and both
downstream steps are skipped on that implicit `success()` check alone —
satisfying Acceptance Scenario 4 ("the job stops before its next durable
action... the close-or-redrive step does not run") with **no change
needed in `board-loop.yml` itself**.

**Alternatives considered**:
- Keep `closed-check` first, give it `continue-on-error: true` locally so
  `check` still runs, and add a new terminal step after `check` that hard-
  fails the job by reading `steps.closed-check.outcome` — rejected: FR-002's
  text is explicit that `continue-on-error: true` "MUST be removed from
  the `closed-check` step," not merely neutralized by a later gate; keeping
  it (even paired with a hard-fail step) would also leave a real window
  where the annotation looks tolerated to a reader who has not traced the
  later step, which is exactly the kind of misleading-comment risk FR-001
  exists to remove.
- Have `check` read `closed-check`'s output via a job-level (not step-level)
  mechanism that survives step failure — rejected: no such mechanism exists
  for composite-internal steps; `steps.<id>.outputs` is populated from
  whatever the step wrote to `$GITHUB_OUTPUT` before it exited, which is
  exactly what D2's OR-of-two-outputs design already uses, with no need for
  `check` to read anything from `closed-check` at all.

## D2: The composite's `paused` output becomes an OR of two independent step outputs

**Decision**: Change

```yaml
outputs:
  paused:
    value: ${{ steps.check.outputs.paused }}
```

to

```yaml
outputs:
  paused:
    value: >-
      ${{ steps.check.outputs.paused == 'true' ||
          (inputs.check-issue-closed == 'true' &&
           steps.closed-check.outputs.is-open == 'false') }}
```

**Rationale**: With `check` no longer reading `closed-check`'s output (D1),
something still has to combine "kill switch or stop request fired" with
"the issue is closed" into one `paused` boolean for the composite's callers
— all seven, not just `prove`. Composite `outputs:` expressions are
evaluated against whatever `steps.*.outputs` and `steps.*.outcome` values
exist at composite-completion time, independent of which step is doing the
combining, so this is the natural place: it needs no new step, and it
reads correctly on every caller (the other six pass no
`check-issue-closed`, so `inputs.check-issue-closed == 'true'` is false and
the whole second clause short-circuits to `false`, leaving `paused` exactly
`steps.check.outputs.paused` as it always was for them).

**Alternatives considered**:
- Add a third step whose sole job is to combine the two outputs into a
  single `paused` — rejected as an unneeded extra process fork for a
  boolean OR that GitHub Actions expression syntax already computes
  correctly in the `outputs:` mapping itself; every existing composite in
  this repository (e.g. `wing-commander-lifecycle-gate`'s own `is-open`)
  computes its output as a plain expression over a single step, not a
  combining step.

## D3: Failure visibility is a trailing `if: failure()`-scoped note, not a rewritten lifecycle-gate

**Decision**: Add a third composite step, positioned after `closed-check`,
gated `if: steps.closed-check.outcome == 'failure'`, that echoes one
`::error::` line naming the issue number and the policy's consequence —
e.g. "closed-check for issue #N did not resolve; wing-commander-board-
stop-check's fail-loud policy stops this job before its next durable
action (see this file's own header comment)." It exits `0`.

**Rationale**: FR-004 requires the read failure be visible "naming which
issue could not be read and what the policy did about it — rather than
only inferable from the absence of an output." `lifecycle-gate` already
emits `::error::wing-commander-lifecycle-gate: could not determine state
of issue #N after N retried attempts...` (satisfies "which issue"), but it
has no knowledge of the *calling* composite's policy, so it cannot state
"what the policy did about it." A step scoped to `steps.closed-check.
outcome == 'failure'` runs exactly once, exactly when needed, and its own
`exit 0` does not "heal" the job back to success — GitHub Actions rolls a
job's conclusion up from every step's individual conclusion, and one
earlier unguarded failure (`closed-check`) already fixed that roll-up
before this step runs. This keeps the fail-loud outcome and the added
visibility fully independent: removing the note step (a hypothetical
future regression) would not change whether the job fails, only how
legible the reason is.

**Alternatives considered**:
- Fold the extra context into `lifecycle-gate`'s own error message via a
  new input (e.g. `caller-policy-note`) — rejected: `lifecycle-gate` is
  called from seven sites with no tolerance-policy concept of its own
  (FR-006 forbids adding one for this feature's sake), and its own
  docstring already states its contract is narrow ("does not check who
  commented or what labels the issue carries — those who/what gates are
  unchanged and stay where they are"); adding a caller-specific message
  parameter would widen that contract for one caller's convenience.

## D4: The canonical errexit statement lives in the new gate script's own docstring

**Decision**: FR-008's "exactly one canonical statement" is the new gate
script's (D5) module docstring — a "WHY THIS EXISTS" section stating: a
`shell: bash` step runs as `bash --noprofile --norc -eo pipefail {0}`, so
errexit is active from the outer invocation before the script's first line
runs; `set -uo pipefail` only touches `-u` and `-o pipefail`, leaving
`-e`'s existing value untouched; a failing command inside a plain `var="$(
...)"` assignment therefore still aborts the step. Every one of the five
corrected comments (the `board-stop-check` rewrite under FR-001, plus the
four `board-loop.yml`/`metrics-persist.yml`/`implement.yml`/
`lint-workflows.yml` sites under FR-007) states its own site-specific
consequence briefly and points at the gate script with a `-- see
verify-errexit-claim-comments.py.` pointer rather than restating the
mechanism.

**Rationale**: This repository already uses a gate script's own docstring
as the canonical statement of the fact the gate defends — Gate 19's
docstring states the pagination-loss fact its `lint-workflows.yml` comment
then only summarizes and points back to ("under `set -uo pipefail` with no
`-e`" — ironically itself one of the four sites this feature corrects, at
its NARRATIVE description of the *pre-fix* bug, which the edge case
"historical narrative... must not erase the record of what actually
happened" says to preserve, correcting only the *tense/framing* so it
reads as "the fix removed a step that would have silently dropped
annotations under the mistaken belief errexit was off," not as a live
claim). A gate's docstring is also where Gate 47's pointer-resolution rule
(`resolve_target_path`) already treats a bare `NAME.py` target as
resolving under `.github/scripts/` "the canonical home for that script's
own self-test regression list" (verify-comment-canonical-pointers.py's own
docstring, part (a)) — i.e. this repository has already decided gate
docstrings are valid canonical-fact homes, not just workflow comments.

**Gate 47 coverage note**: `check_pointers`/`check_canonical_markers` only
scan `.github/workflows/*.yml` as pointer *sources* (`workflow_files()`).
The four workflow-file corrections (`board-loop.yml`, `metrics-persist.yml`,
`implement.yml`, `lint-workflows.yml`) are real Gate 47 pointer sources and
get validated (target exists, topic words overlap). The `board-stop-check`
composite's own corrected comment is **not** a Gate 47 source (action files
aren't scanned), so a `-- see verify-errexit-claim-comments.py.` pointer
placed there is not mechanically validated by Gate 47 — it is still written
for a human reader, matching FR-008's spirit, but its correctness is
enforced by FR-009's own gate (which scans the composite directly, D5)
rather than by Gate 47.

**Alternatives considered**:
- Put the canonical statement in `wing-commander-board-stop-check/
  action.yml`'s own header comment (the "site that matters most," per
  spec.md's Overview) — rejected: that file is not a Gate 47 pointer
  source, and it is also not naturally where a contributor lands when
  writing a *new* comment about a different step in a different file; the
  new gate's own docstring is read exactly when someone is told their PR
  failed FR-009's gate, which is the moment the canonical fact is most
  useful.
- A new standalone doc, e.g. `docs/shell-conventions.md` — rejected: this
  repository's established idiom for a defended fact is a gate's own
  docstring (Gate 19, Gate 24, Gate 47 itself), not a separate prose file
  with no enforcement tied to it; a new doc nothing points at mechanically
  is the same "restated per feature, trusted nowhere" problem Principle
  VIII's motivation paragraph names for the checklist theme generally.

## D5: The new gate scans both `.github/workflows/*.yml` and `.github/actions/**/action.yml`

**Decision**: `verify-errexit-claim-comments.py` (FR-009's gate, numbered
`Gate <N>` — the next sequential number after the highest shipped at
tasks-generation time, currently 100; this repository renumbers on a rebase
collision rather than reserving a number in advance, per Gate 99/100's own
comments) globs comment blocks from `.github/workflows/*.yml` **and**
`.github/actions/**/action.yml` (recursive, matching
`verify-actions-layer-invariants.py`'s existing
`glob.glob(os.path.join(base, "*", pattern))` +
`glob.glob(os.path.join(base, "**", pattern), recursive=True)` shape, which
already covers both directly-nested composites and `_shared/`-nested ones).

**Rationale**: FR-001's own violation — the comment this feature exists to
fix — lives in `.github/actions/wing-commander-board-stop-check/action.yml`,
not in a workflow file. FR-012 exists precisely because Gate 24's
`WORKFLOWS_GLOB = ".github/workflows/*.yml"` never saw that same file's
`continue-on-error:` pairing, so "Gate 24: 0 findings" was vacuous evidence
for it. A new gate that repeats that exact glob would be unable to see the
one file most likely to carry a future recurrence of this feature's own
mistake — the "next one cannot ship" framing in spec.md's Overview would be
false on day one for the action-file half of the fleet. SC-008 requires
that no gate cited as evidence for this feature's changed files is vacuous
for them; scanning actions is what makes that true for `board-stop-check`
specifically.

**Alternatives considered**:
- Match Gate 24's `.github/workflows/*.yml`-only scope for consistency —
  rejected for the reason above; consistency with a documented blind spot
  is not a virtue FR-012 asks for, and nothing in FR-009 requires matching
  Gate 24's scope.

## D6: False-claim detection — phrase patterns with a negation-window and a quoted-span exclusion

**Decision**: The gate matches a small set of phrase patterns against the
comment text of each block (reusing
`verify-comment-canonical-pointers.py`'s `comment_blocks()`/`_joined()`
line-joining, imported rather than re-implemented):

- `\brun(?:s)?\s+without\s+(?:-e\b|errexit\b)`
- `\bwithout\s+errexit\b`
- `\bwith\s+no\s+`-e`\b` (backtick-quoted `-e`, this repo's own comment
  style for the flag)
- `\bno\s+`-e`\b` where the token immediately preceding "no" is not itself
  part of a larger negation (see below)
- `\bclears?\s+`-e`\b`

A candidate match is **excluded** (not a violation) when either:

1. **Negation window**: one of the three words immediately preceding the
   match is `not`, `never`, `n't`-suffixed, `doesn't`, `does`, or `cannot`
   (covering "does not clear `-e`", "never runs without errexit") — the
   corrected canonical phrasing this feature ships (D4) is written to use
   exactly this shape ("does not clear `-e`", never "clears `-e`" bare), so
   the true statement and the false one are lexically distinguishable by
   polarity, not just by which gate script happens to be reading them.
2. **Quoted span**: the match falls inside a `"..."`, `'...'`, or
   `` `...` `` delimited span that itself spans more than just the flag
   token (i.e., a longer quotation, not merely `` `-e` `` on its own) —
   covering the edge case "a comment that... quotes the wrong claim in
   order to correct it," e.g. `Previously this said "runs without -e" —
   wrong; errexit is already active.`

**Rationale**: The edge case is explicit that a correctly-discussing or
correction-quoting comment must not trip the gate, and the corrected
canonical text (D4) necessarily has to describe the false claim's
*mechanism* ("does not clear `-e`") using vocabulary that overlaps the
false claim's own words — a bare substring match would flag the cure along
with the disease. Anchoring on tense/polarity (bare "clears" vs. negated
"does not clear") and on quotation is deterministic, requires no NLP, and
is exactly how the four corrected sites and the gate's own docstring are
written under this plan — self-consistent by construction, not by
convention alone.

**Alternatives considered**:
- Match on exact phrase strings only (the four+one strings actually
  observed) rather than patterns — rejected: SC-002 requires that "zero
  comments remain... asserting" the claim and that a *newly introduced*
  one fails (FR-009), which means the gate must generalize past the exact
  four phrasings already fixed, or the next contributor's fifth rephrasing
  ships uncaught — the precise failure mode #465's review already
  demonstrated once.
- A stricter rule requiring every false-claim mention be wrapped in an
  explicit sentinel comment (e.g. `# HISTORICAL:`) — rejected: this would
  require rewriting every historical-narrative sentence in the four
  corrected sites to add a marker with no functional benefit over the
  negation/quotation heuristics, and would still need the same phrase-match
  step underneath to know what counts as "the claim" in the first place.

## D7: `verify-board-stop-check.py`'s extension — structural assertions plus extended shell cases

**Decision**: Extend `verify-board-stop-check.py` (not a new parallel
harness, per FR-013) with:

1. **Structural checks** against the parsed `action.yml`: the step with
   `id: closed-check` has no `continue-on-error` key (or it is falsy); the
   step with `id: check` appears at a lower step index than `closed-check`
   in `runs.steps` (proving the reorder, not just the flag removal); the
   `check` step's `run:` text contains no reference to
   `steps.closed-check` (proving it truly no longer depends on
   `closed-check`'s output, D1).
2. **Extended shell cases**: the existing `SHELL_CASES` table already
   drives the `check` step's script under a stub `gh`; extend it to run
   with `check-issue-closed` both unset and `"true"`, and add cases
   covering the composite's new `outputs.paused` expression evaluated
   against each `(check.outputs.paused, closed-check.outcome,
   closed-check.outputs.is-open)` combination named in SC-007: read
   succeeds OPEN (`is-open=true`), succeeds CLOSED (`is-open=false`),
   fails transiently then succeeds (same as succeeds,
   `lifecycle-gate`'s own retry is unchanged and untested here — Gate 25
   already covers it), fails all attempts (`closed-check.outcome=failure`,
   composite step fails), and an unrecognized value (`lifecycle-gate`
   itself exits 1 on this, so it is the same code path as "fails all
   attempts" from this composite's point of view — `verify-lifecycle-
   gate-retry.py`, Gate 25, is where the unrecognized-value branch inside
   `lifecycle-gate` itself is fixture-tested; this harness tests the
   composite's *reaction* to that failure, not `lifecycle-gate`'s own
   internal classification).
3. **A new mutation**: reintroduce `continue-on-error: true` on
   `closed-check` (the pre-fix shape) and assert at least one structural
   check or shell case catches it — following the existing
   `composite_shell_check()`'s `GUARD_LINE_RE`-based mutation pattern, but
   as a structural YAML mutation (toggle the key) rather than a regex
   substitution on the `run:` string, since the fix here is a YAML-level
   property, not a shell-level one.

**Rationale**: FR-013 requires every behavioural requirement concerning the
composite's own shell be covered by this existing harness "rather than by a
new parallel harness." SC-007 requires every read-failure-policy branch be
exercised and a mutation of the policy caught. Because the actual
step-skipping-on-failure semantics (D1's real payoff) is a GitHub Actions
runtime behavior this harness's direct-subprocess execution of one step's
`run:` text cannot reproduce (it invokes one script, not the composite's
full multi-step engine), the harness proves the *ingredients* of the fix
deterministically instead: `closed-check` cannot re-strand `check` because
`check` no longer reads its output and runs first (structural + "no
`steps.closed-check` reference" checks), and the two independent booleans
combine correctly in the output expression (parsed and evaluated against
each SC-007 combination) — together these are sufficient to prove the fix
without needing to fake GitHub's own step orchestrator.

**Alternatives considered**:
- Evaluate the composite's `outputs.paused` GHA expression string with a
  full expression-language interpreter — rejected as unnecessary; the
  expression this plan produces (D2) is a simple boolean OR/AND of literal
  comparisons, which can be evaluated with a small hand-written parser (this
  repository already has `wc_gha_expr.py` for exactly this shape of task —
  reuse it rather than writing a second one, per CLAUDE.md's "Shared logic
  has exactly one home").
- Spin up an actual `act`-style local GitHub Actions runner to exercise the
  full composite end-to-end — rejected: no such tool is part of this
  repository's existing gate infrastructure (`wc_shell_harness.py` runs
  real bash against synthetic git repos, deliberately not a full Actions
  emulator), and introducing one for a single feature would violate
  CLAUDE.md's existing-harness-first instruction and Principle VIII's
  "same subject and arguments locally as in CI" (an emulator is not the
  same execution engine CI actually uses either).

## D8: Gate 24's boundary is recorded in its own docstring, with a follow-up issue filed at implementation time

**Decision**: Add a short paragraph to `verify-gate-24.py`'s module
docstring, near `WORKFLOWS_GLOB`, stating plainly that this gate inspects
only `.github/workflows/*.yml` and not `.github/actions/**` — composite
actions, including `wing-commander-board-stop-check`, are out of its
scope — and naming the follow-up issue that tracks widening it. The issue
itself does not exist yet; per FR-012 and CLAUDE.md's issue-routing
convention ("File the issue first and apply the label as a separate
action"), it is filed as one of the tasks/implement stage's own actions
(a plain bug/enhancement issue, not a `spec-request` — the widening itself
is deterministic and gate-shaped per Principle X's own routing rule), and
its number is substituted into the docstring paragraph once known.

**Rationale**: FR-012's Acceptance Scenario 2 requires the recorded
boundary "point at the follow-up issue for widening Gate 24... rather than
leaving the gap undocumented" — a placeholder with no eventual issue number
would not satisfy that. Filing happens during implementation (not this
plan stage, which has no tool access to create issues and is scoped to
`specs/088-stop-check-closed-read` only) so the docstring's pointer is real
on the PR that ships it, not a promise to be filled in later.

**Alternatives considered**:
- Point at issue #465 (the PR whose vacuous "Gate 24: 0 findings" motivated
  this whole feature) instead of a new issue — rejected: #465 is closed
  history describing the mistake, not an open tracker for the widening
  work; FR-012 asks for a pointer a reader can act on today, which needs an
  open issue.

## D9: A stale line citation in spec.md's own evidence, noted but not corrected here

spec.md's Observed Facts section cites `implement.yml:2785` for the fourth
"no `-e`" comment. Against the current checkout, line 2785 is a different,
already-correct comment ("Record truncated-cycle count" is continue-on-error
*under* `bash -e`" — a true statement); the actual "No `-e`: an unreadable
file degrades to empty fields..." comment is at line 3013 today (confirmed
by content search, not by the cited line number). This is intervening-commit
line drift against the commit spec.md was verified at (53b7450), not a
defect in the spec's reasoning — the content, not the line number, is what
FR-007 needs corrected, and tasks/implement will locate it by content
search rather than by the stale line number. Not fixed here: spec.md is
this plan stage's input data, not a file this run edits (see this run's own
constraints). Reported separately as a `wing-commander-findings` entry per
this run's instructions.
