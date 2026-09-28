# Research: Classify the cancel call's own error instead of racing a pre-read status

**Feature**: `087-stop-cancel-error-classification` | **Issue**: #621

## Sources consulted

- `.github/actions/wing-commander-board-stop-check/action.yml` — the `check`
  step's current status-gated cancel branch (lines ~132-173).
- `.github/workflows/pr-conversation.yml` — the "Stop procedure" step
  (lines ~2446-2530), the canonical unconditional-attempt-then-classify
  idiom this feature ports into the board loop.
- `.github/scripts/board_stop_check.py`, `.github/scripts/verify-board-stop-check.py`
  — `find_stop_request()`'s own contract and the composite's existing
  shell-fixture harness (`STUB_GH`, `SHELL_CASES`, `MUTATIONS`).
- `.github/scripts/verify-single-home-idioms.py` — the `DECLARED_HOMES` /
  `check_*` pattern already used for `board-stop-check` and
  `transcript-normalise`; the model for the FR-009a addition.
- `.github/actions/_shared/normalise-transcript.sh`, `.github/actions/_shared/count-turns.sh`
  — the established shape of a `_shared/*.sh` script: a documented stdin/argv
  contract, invoked with `bash <path> ...` (never sourced, never relies on
  its executable bit), consumed both from a composite
  (`$GITHUB_ACTION_PATH/../_shared/...`) and, per
  `.github/actions/_shared/auto-release-verdict.sh`'s call sites in
  `auto-release.yml`, directly from a plain workflow job by repo-root-relative
  path (`bash .github/actions/_shared/....sh`). Confirms the same shape works
  for `pr-conversation.yml`, which is a plain workflow job, not a composite.
- `.github/actions/wing-commander-lifecycle-gate/action.yml`'s inline
  `sanitize()` helper (newline/tab flatten, `tr -s`, 300-char truncate, `%`
  escape) — the existing idiom for neutralising untrusted text before it
  reaches a `::warning::`/`::error::` workflow command.
- `specs/088-stop-check-closed-read/spec.md` (issue #623, sibling in-flight
  spec) — explicitly defers the neutralisation of this exact
  `echo "::warning::gh run cancel ... $cancel_error"` line to this feature
  ("Spec 087 (#621) replaces this same line, so the fix is sequenced there
  rather than here"), confirming FR-011's ownership and that no double edit
  is at risk.
- `.github/scripts/verify-gate-12.py` — confirms the token-permission gate
  asserts *which token* runs `gh run cancel`/`gh run list`, never the text of
  the outcome-classification grep, so repointing that grep at the shared
  script does not touch Gate 12's assertions.
- Issue #621 comment thread — the clarify stage's two resolved questions
  (vocabulary-only consolidation; a non-warning informational line on the
  already-terminal path), both Option A, already folded into spec.md's
  FR-009/FR-010 and requiring no further decision here.

## Decisions

### D1: Shared vocabulary lives in a new `_shared/*.sh` predicate script
**Decision**: Add `.github/actions/_shared/cancel-already-terminal.sh`. Contract:
invoke as `bash <path> "$ERROR_TEXT"` with the cancellation call's captured
stderr/error text as `$1`; exit 0 when that text identifies the target as
already-terminal (no stdout needed — it is a predicate, not a transform),
exit 1 otherwise. Never sourced, never relies on its executable bit — same
invocation discipline `normalise-transcript.sh` documents for itself.
**Rationale**: `normalise-transcript.sh` is the one precedent in this
repository for "a shared script two independent call sites (a composite via
`$GITHUB_ACTION_PATH/../_shared/...` and a plain workflow job by
repo-relative path) both consume for one decision." An exit-code predicate
is the smallest contract that fits both call sites' needs: the composite
only needs a branch (warn or don't), and `pr-conversation.yml` only needs
the same branch (`outcome="already-completed"` or not) — neither needs a
parsed value back.
**Alternatives considered**: A jq/Python helper — rejected, both sites are
already bash and stdlib `grep -qiE` is the pattern already in the codebase
at both call sites (FR-009's own framing: consolidate the vocabulary, not
the mechanism). Sourcing the file to expose a shell function — rejected,
`normalise-transcript.sh`'s own comment records why this repository invokes
`_shared/*.sh` as a subprocess rather than sourcing it (the executable bit
is never load-bearing, and a workflow step's `set -e` semantics stay
predictable across a subprocess boundary).

### D2: Vocabulary anchoring
**Decision**: The script's internal pattern matches, case-insensitively:
`HTTP 409` (not bare `409`), `already completed`, `cannot cancel`. This is
the existing pr-conversation.yml phrase set with its status-code term
re-anchored per FR-005.
**Rationale**: Spec Edge Cases and FR-005 are explicit and already resolved
(clarify stage, Question 1 answered before this plan): the anchor prevents a
permission-error message that merely quotes `409` in a run id or URL from
being misclassified as already-terminal (SC-002's third checked-in case).
**Alternatives considered**: none — this is spec text, not a design choice.

### D3: `board-stop-check/action.yml` restructure
**Decision**: In the `check` step's `run:` block:
- Delete the `cancel_target_status` extraction
  (`jq -r '.status // empty'`) — FR-002/SC-006.
- Collapse the `elif [ "$cancel_target_status" != "completed" ]` branch: once
  the ownership guard (`cancel_target_path`/`cancel_target_repo`) passes, the
  cancellation is now attempted unconditionally in that `else` branch —
  FR-001.
- On `gh run cancel` failure, call `cancel-already-terminal.sh` with the
  captured error text (`$GITHUB_ACTION_PATH/../_shared/cancel-already-terminal.sh`).
  - Match (exit 0): emit a plain `echo` line (no `::...::` prefix) recording
    that the target had already finished — FR-003/FR-010.
  - No match (exit 1): emit `::warning::` with the *neutralised* error text —
    FR-004/FR-011.
- The surrounding header comments that currently justify the status-gated
  branch (the "already be terminal... `gh run cancel` on a completed run
  always 409s" block, and its cross-reference to "peer review of #465,
  round 2") describe removed behaviour and must be rewritten to describe the
  unconditional-attempt-then-classify replacement, per CLAUDE.md's "workflow
  comments are load-bearing" rule — a stale comment here is exactly the
  failure mode `specs/088-stop-check-closed-read` was opened over.
**Rationale**: Directly implements FR-001/FR-002/FR-003/FR-004/FR-010;
mirrors `pr-conversation.yml`'s already-accepted shape (the Input
description's own framing).
**Alternatives considered**: Keep the status read for the ownership check's
diagnostic value but branch on it too — rejected, FR-002 is explicit that
the execution-state field must not be consulted anywhere, not merely not be
the sole gate.

### D4: Error-text neutralisation (FR-011) stays a local, inline helper
**Decision**: Add a small inline `sanitize()` function to the `check` step's
own script, matching `wing-commander-lifecycle-gate`'s existing idiom
(flatten newlines/tabs, collapse repeated spaces, truncate at 300 chars,
escape `%`). Apply it only to the FR-004 warning path's error text before
interpolation.
**Rationale**: Spec's own Assumptions section bounds this feature's edit
surface to "one composite action's stop-check step, the gate that covers
it, the single-home gate extended by FR-009a, the new shared vocabulary
script, and the one line in the other stop procedure that switches to
consuming it" — it does not list a new shared sanitiser. `sanitize()` is
four lines and has exactly one prior instance in the repository
(`wing-commander-lifecycle-gate`); CLAUDE.md's "shared logic has exactly
one home" section is triggered by a *second* paste, and the spec's own
scope statement is the deliberate call that this feature's copy is not
that trigger. Revisit only if a third site needs the same neutralisation.
**Alternatives considered**: Promote `sanitize()` to `_shared/` now —
rejected as scope creep against the spec's explicit boundary; noted here so
a future feature that adds a third caller has the cross-reference.

### D5: Informational line format (FR-010)
**Decision**: A bare `echo "run $stop_run_id had already finished; nothing to cancel"`
(exact wording is an implementation choice for `/speckit-tasks`), carrying
no `::notice::`/`::warning::`/`::error::` GitHub Actions workflow-command
prefix.
**Rationale**: `watchdog.yml`'s "Collect: annotations" step (named in
`specs/088-stop-check-closed-read/spec.md`'s own observed facts) fetches
check-run *annotations* — which only `::notice::`/`::warning::`/`::error::`
produce — for every non-skipped/non-cancelled job. A bare log line is
invisible to that collector by construction, which is what FR-010 requires
("the annotation collector that gathers only warnings and failures does not
pick it up").
**Alternatives considered**: `::notice::` — rejected, `::notice::` is still
an annotation and the collector's own filter (job conclusion, not
annotation level) does not exclude notices; using it would risk exactly the
"is this noise" ambiguity the clarify stage's Question 2 was asked to
settle (Option B, not "silent" Option A, was chosen — a visible but
non-annotation line).

### D6: `pr-conversation.yml`'s Stop procedure repointed at the shared script
**Decision**: Replace the inline
`grep -qiE '409|already completed|cannot cancel' "$RUNNER_TEMP/cancel-err.txt"`
with `bash .github/actions/_shared/cancel-already-terminal.sh "$(cat "$RUNNER_TEMP/cancel-err.txt")"`.
This is the "one line in the other stop procedure that switches to
consuming it" the spec's Assumptions name. Everything downstream of that
`if` (the `outcome` variable, the three PR-comment bodies) is unchanged.
**Rationale**: FR-005/FR-009 require both sites to read the same vocabulary
and both get the anchored `HTTP 409` form; this is the minimal edit that
achieves it without touching this site's reporting (out of scope per FR-009
and the spec's Assumptions).
**Behaviour change accepted knowingly**: a failure whose text is not an
already-terminal refusal but happens to contain the bare digits `409` (e.g.
in a run id) now reports `cancel-failed` instead of `already-completed` at
this site too — narrower, and moves this site toward its own governing
requirement (contracts/autonomy-and-confirmation.md: a permission failure
must never be reported as a completion), per the spec's own Assumptions
section.
**Alternatives considered**: Leave `pr-conversation.yml`'s own grep as-is
and only anchor the new shared copy — rejected, FR-005's last two sentences
are explicit that "the other stop procedure's present unanchored form is
corrected by this change rather than preserved."

### D7: FR-009a gate extension
**Decision**: Extend `.github/scripts/verify-single-home-idioms.py`:
- Add `"cancel-already-terminal": ".github/actions/_shared/cancel-already-terminal.sh"`
  to `DECLARED_HOMES`.
- Add a regex-based structural check (modeled on `check_transcript_normalise`,
  the closest existing precedent for "one small recognition pattern, not a
  multi-line procedure") that flags any file outside the declared home whose
  text re-implements the vocabulary — co-occurrence of the three phrase
  fragments (`HTTP 409`, `already completed`, `cannot cancel`) in one
  `grep`/regex-shaped construct, the same co-occurrence style
  `check_board_stop_check` and `check_dispatch_and_wait` already use to avoid
  false-positiving on an unrelated, single ordinary mention of one phrase.
- Register the new check in `CHECK_NAMES`/the dispatch table alongside
  `"board-stop-check"` and `"transcript-normalise"`, per FR-009a's "alongside
  the check that already covers this stop check."
**Rationale**: FR-009a requires this gate specifically, not a new one, and
requires it be structural (catches a re-implementation of the vocabulary,
not merely a literal copy of `cancel-already-terminal.sh`'s exact text) so a
third site cannot reintroduce the pre-anchoring bug by writing its own
similar-looking grep.
**Alternatives considered**: A literal substring check (the sha256/
fingerprint style of `check_stage_findings`) — rejected, the vocabulary is
three short common English phrases; a literal-text check would both
false-positive on prose review discussion of this very feature and
false-negative on a rephrased but behaviourally identical re-implementation.

### D8: Fixture and mutation coverage (FR-007/FR-008/SC-001–SC-003/SC-008)
**Decision**:
- Extend `verify-board-stop-check.py`'s `STUB_GH` so `gh run cancel` can be
  told, per test case, to fail with a given stderr string (today it always
  exits 0). Extend `RUNS`/`SHELL_CASES` (or an adjacent table) with: a
  successful cancellation (already covered), an already-terminal refusal
  (asserts no `::warning::`, one informational line, `paused=true`, exit 0),
  a non-terminal failure (asserts a `::warning::` naming the run and the
  error text, `paused=true`, exit 0), an empty-stderr failure (asserts the
  same warning path, per FR-004's "including a failure with empty or
  unrecognised error output"), a failure whose text contains bare `409`
  without `HTTP` (asserts warning, not silence — SC-002's third case), and a
  failure whose text contains a newline / `::`-shaped workflow-command
  fragment (asserts exactly one warning annotation survives neutralised,
  per SC-008).
- Add a `MUTATIONS`-style entry (or a dedicated mutation in
  `composite_shell_check()`, matching its existing "disable the cancel
  guard" mutation) that inverts the already-terminal classification (e.g.
  swaps `cancel-already-terminal.sh`'s exit code) and asserts at least one
  new fixture catches it — FR-008/SC-003.
- The existing `EXPECTED_FILES` fixture set (ownership, unreadable-target,
  forged-marker, self-run) is unchanged and must keep passing — SC-004.
**Rationale**: These are the concrete mechanics `/speckit-tasks` needs to
turn FR-007/FR-008 into tasks against the actual test harness; the harness
already has every piece (`STUB_GH`, `SHELL_CASES`, `MUTATIONS`,
`composite_shell_check`'s own working mutation for the cancel guard) this
feature's coverage extends rather than replaces.
**Alternatives considered**: A brand-new gate script — rejected,
`verify-board-stop-check.py`'s own docstring already states it is *the*
gate for this composite's cancel guard, and CLAUDE.md's single-home rule
applies to gates as much as to shell.

## Decisions made without clarification

None. `spec.md` carries no `[NEEDS CLARIFICATION]` markers — both questions
the clarify stage raised (vocabulary-only consolidation; a non-warning
informational line) were answered on issue #621 before this plan ran, and
are already encoded in FR-009/FR-010.
