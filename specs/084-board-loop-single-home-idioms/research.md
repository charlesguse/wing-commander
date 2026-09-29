# Research: Single-home the remaining board-loop idioms

All three `[NEEDS CLARIFICATION]` markers the spec originally carried were
already resolved in the clarify session recorded in spec.md's
Clarifications section (FR-005a, FR-009, FR-015). This document re-verifies
those decisions against the real tree — not just the counts the spec's own
checklist asked the plan stage to re-check (baseline commit `e170077`) —
and records the additional mechanical decisions the plan stage had to make
to turn each accepted decision into a concrete design.

## D1 — Board-stop-check already has a structural gate; FR-011/User Story 3
### AS1 are pre-satisfied on the base branch

**Finding**: `verify-single-home-idioms.py` already declares
`"board-stop-check": ".github/actions/wing-commander-board-stop-check/action.yml"`
in `DECLARED_HOMES`, with a working `check_board_stop_check()` wired into
`ALL_CHECKS`, a `--self-test` mutation
(`selftest_third_paste_fails("board-stop-check", ...)`), and waiver-eligibility
via the shared waiver mechanics. This landed in commit `98ee260`
("fix(board-loop): the kill-switch cancel uses github.token, and its
recheck is one composite (#465)"), which is an ancestor of `e170077` — the
commit the spec's own Context section cites as its triage baseline.

**Impact**: spec.md's Context item 1 ("What did not land alongside the
extraction is the structural single-home check CLAUDE.md asks for ...
nothing fails when a seventh site re-pastes") and FR-011 ("MUST gain such a
check in this feature even though its home already exists") describe a gap
that is already closed on the branch this feature starts from. User Story
3's Acceptance Scenario 1 ("Given the kill-switch/stop-request recheck
idiom, When its shell is re-pasted ... Then a gate fails") already passes
today with zero code changes.

**Decision**: this feature's tasks for the board-stop-check idiom are
**verification-only** — confirm `check_board_stop_check` still passes and
its self-test still exercises a re-paste, and record that confirmation as
evidence for AS1/FR-011/SC-004's third idiom — rather than adding a new
check. No new `DECLARED_HOMES` entry, no new check function. This is
reported separately as a stale-premise finding on the spec (not this plan's
file to fix); the plan proceeds on the corrected understanding.

**Alternatives considered**: re-deriving/replacing the existing check to
satisfy FR-011 "textually" — rejected as pure churn with no behavioral
gain and a needless risk of regressing `check_board_stop_check`'s already-
proven self-test coverage.

## D2 — Marker-write bootstrap: command-line entrypoint shape

FR-005a already decided the mechanism (a `python3 -I` command-line
entrypoint on `board_item_marker.py`, not a composite). The precedent named
in the clarification — `python3 -I
"$RUNNER_TEMP/wc-pristine/scripts/board_spec_request_body.py"` — was
verified at `board-loop.yml:2170`/`:3438` (pristine) and `:1648` (working
tree, no `-I`). `board_spec_request_body.py` is `argparse`-based and writes
its result to a `--out PATH` file; the 17 marker-write call sites instead
all capture stdout via `$(...)`, so the new entrypoint follows the
`print()`-to-stdout shape already used by every inline `python3 -c
"...; print(write_marker(...))"` call, not `board_spec_request_body.py`'s
`--out` shape.

**Decision**: add a `main()`/`if __name__ == "__main__":` block to
`board_item_marker.py` (which today has neither — `write_marker(step,
round, pr, branch, base_sha)` at line 110 is the only public surface) with
this CLI:

```
python3 [-I] <scripts_dir>/board_item_marker.py \
  --step STEP --round N [--pr NUM] [--branch REF] [--base-sha SHA]
```

- `--step` (required, string): the literal step name (`stalled`, `review`,
  `readiness`, `proven`, `prove`, ...), OR one of the two symbolic tokens
  `BREACH_STEP` / `AWAITING_MERGE_STEP` (see D3).
- `--round` (optional, `type=int`, default `0`): matches `write_marker`'s
  positional default use today (`0` everywhere except the review job's
  round-advance call, which passes `int(os.environ['NEXT_ROUND'])`).
- `--pr`, `--branch`, `--base-sha` (all optional, `argparse` default
  `None`): a flag that is never passed on the command line yields `None`
  (JSON `null`), preserving FR-004's null-vs-empty-string distinction
  without any sentinel value — argparse's own "flag absent" state already
  *is* `None`, and `--pr ""` (never used today, but available) would still
  produce `""`, distinct from omission.
- Output: `print(write_marker(...))` to stdout, unchanged from every
  existing inline call — callers keep capturing it with `$(...)`.

Working-tree call sites (triage, route, prove) invoke
`python3 .github/scripts/board_item_marker.py ...` (no `-I`, matching
`board_spec_request_body.py`'s own working-tree twin at `:1648`). Pristine
call sites (fix, review, readiness) invoke `python3 -I
"$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py" ...`.
`ALLOWED_PYTHON_ARGS_RE` in `verify-board-loop-helper-provenance.py`
already matches this exact spelling (`-I "$RUNNER_TEMP/wc-pristine/scripts/
[A-Za-z0-9_-]+\.py"` as a *prefix*, with unconstrained trailing args), and
the snapshot step (`board-loop.yml:1761-1770`, byte-identical across fix/
review/readiness) already `git archive`s the whole `.github/scripts`
directory, so `board_item_marker.py` needs no separate wiring into the
snapshot to satisfy the spec's own edge case ("must be part of what the
snapshot step copies"). Gate 98 requires no source change: `HELPER_IMPORT_RE`
(which gates a bare sys.path-insert-plus-import) never matches a direct
script invocation, since the caller line contains no `from`/`import` text
of its own — the import happens inside the entrypoint script, which Gate 98
does not scan (it scans `.github/workflows/*.yml`, not `.github/scripts/
*.py`).

**Alternatives considered**: a composite action — explicitly ruled out by
FR-005a itself (resolves from the checkout the fix/review/readiness agents
can write, defeating Gate 98's guarantee until #615).

## D3 — Resolving `BREACH_STEP`/`AWAITING_MERGE_STEP` without a second
### literal copy

**Finding**: both constants are plain strings —
`board_eligibility.py:77-78`: `AWAITING_MERGE_STEP = "awaiting-merge"`,
`BREACH_STEP = "breach"`. The two marker-write call sites that need them
(`fix`'s post-push-breach step, `readiness`'s ready-report step) currently
do `from board_eligibility import BREACH_STEP` /
`from board_eligibility import AWAITING_MERGE_STEP` inline alongside the
`write_marker` import, then pass the resolved constant positionally.

**Decision**: the CLI entrypoint accepts the symbolic token
(`--step BREACH_STEP` / `--step AWAITING_MERGE_STEP`) literally in the
caller's YAML, and `board_item_marker.py`'s own `main()` resolves it via a
small internal lookup that imports `board_eligibility` itself:

```python
_STEP_TOKENS = {}  # populated lazily to avoid a hard import at module load

def _resolve_step(value):
    if value in ("BREACH_STEP", "AWAITING_MERGE_STEP"):
        from board_eligibility import AWAITING_MERGE_STEP, BREACH_STEP
        return {"BREACH_STEP": BREACH_STEP,
                "AWAITING_MERGE_STEP": AWAITING_MERGE_STEP}[value]
    return value
```

This directly answers the spec's own edge case ("The two marker-write
sites that also import a constant from `board_eligibility`: the single
home must cover them, or they become the first drifted copy on day one") —
the *value* of `BREACH_STEP`/`AWAITING_MERGE_STEP` still has exactly one
home (`board_eligibility.py`), and the workflow YAML never hardcodes the
literal `"breach"`/`"awaiting-merge"` string, which would itself be a new,
second copy of that value one `board_eligibility.py` edit away from
drifting.

**Alternatives considered**: hardcoding the literal step string
(`--step breach`) at the two call sites — rejected because it reintroduces
exactly the two-copies-of-one-value risk `CLAUDE.md`'s rule exists to
avoid, one level down from where the spec found it.

## D4 — PR-branch resolution: internal composite shape, and the round
### pass-through

FR-009 already decided the location (`.github/actions/_shared/`, never
published). Both current call sites (`board-loop.yml:2233-2250` review job
id `pr`, `:3159-3170` readiness job id `pr`) are verified as the literal
first step of their job, before `actions/checkout@v5` — the composite
itself needs no checkout (it only calls `gh pr view`), so this ordering is
unaffected; the *step after* it consumes `steps.pr.outputs.branch` as the
checkout `ref:`, unchanged.

**Decision**: `.github/actions/_shared/resolve-pr-branch/action.yml`.

- Inputs: `pr-number` (required), `token` (required — callers pass
  `github.token`, matching both current sites), `round` (optional,
  default `""`).
- Outputs: `pr-number` (echoes the input, preserving
  `steps.pr.outputs.pr-number` for every downstream reference unchanged),
  `branch` (the resolved `headRefName`), `round` (echoes the `round`
  input verbatim — never derived, satisfying FR-007's "the round remains
  caller state").
- The composite's own step uses `env: REPO: ${{ github.repository }}`
  directly (no separate `repo` input needed — the composite runs in the
  same job/run context as its caller).
- Failure handling (FR-008, a **behavior change** from today — neither
  current site checks for a failed `gh pr view` or an empty
  `headRefName`; both currently flow an empty ref straight into
  `GITHUB_OUTPUT` and then into `actions/checkout@v5`'s `ref:`, which
  would silently resolve to the default branch): `set -euo pipefail`, so
  a nonzero `gh pr view` exit (assigned via `branch="$(...)"`) aborts the
  step under `-e`; an explicit `[ -z "$branch" ]` check after a
  successful-but-empty read emits `::error::` and `exit 1` rather than
  writing an empty `branch=` line.
- Both call sites are replaced by
  `uses: ./.github/actions/_shared/resolve-pr-branch` with `id: pr`
  (unchanged id), keeping every downstream `steps.pr.outputs.*` reference
  (18 call sites across the two jobs) untouched.

**Header/promotion-prevention convention**: modeled on
`orphan-branch-reset/action.yml` and `scoped-app-token/action.yml` — a
header comment naming this feature, its contract doc, and the standing
"internal, never resolved by a `workflow_call` stage or a published
composite; Gate 60's promotion-prevention check enforces this" sentence
common to every `_shared/` composite.

**Alternatives considered**: a published `wing-commander-*` composite —
explicitly ruled out by FR-009 (board-loop.yml is this idiom's only
caller; widening the adopter-pinned surface is a deliberate act, not a
convenience here).

## D5 — Single-home check patterns: avoiding two false-positive sites in
### `pr-conversation.yml`

**Finding**: `pr-conversation.yml` already contains two structurally
similar but conceptually distinct `gh pr view ... --json headRefName`
reads that are **not** the PR-branch-resolution idiom and must not trip
the new gate (this is exactly the case the spec's own edge cases section
names — "a structurally similar but conceptually distinct piece of shell
elsewhere in the fleet ... resolvable in the open, with a reason, not by
loosening the pattern" — the plan resolves it by pattern precision instead
of a waiver, since SC-008 expects zero new waivers):

- `pr-conversation.yml:492-493`: resolves `head_ref` *alongside*
  `base_ref` (`baseRefName`) and `default_branch`, as three-way input to a
  qualification-refusal check; writes `reason=`/`refused=true` to
  `GITHUB_OUTPUT` on failure, never `pr-number=`/`branch=`.
- `pr-conversation.yml:3136-3137`: resolves `head_ref` alone, to strip a
  spec-branch prefix and derive `slug=`/`spec-dir=`/`issue-number=` —
  again never `pr-number=`/`branch=`.

Neither site writes the `echo "pr-number=..."` / `echo "branch=..."` pair
that is the actual observable shape of the board-loop idiom (the read
alone, `gh pr view ... --json headRefName`, is common enough elsewhere —
`watchdog.yml`, `auto-release.yml`, `wing-commander-7-cleanup.yml` all read
`headRefName` for unrelated reasons — that keying on the read alone would
also hit those).

**Decision**: the new `pr-branch` check scans per-step (via the existing
`_step_lists(doc)` helper, the same pattern `check_failure_issue` and
`check_token_mint` already use for exactly this reason: file-wide
co-occurrence would risk cross-step false matches in a 3000+-line
workflow) for a step whose `run:` text contains **all** of: `"gh pr
view"`, `"headRefName"`, `'echo "pr-number='`, `'echo "branch='`. This
combination is unique to the two board-loop.yml call sites being
consolidated and to nothing else in the current tree — verified against
every other `headRefName` reference above.

## D6 — Single-home check pattern for marker-write

**Decision**: file-wide fragment co-occurrence (the same strategy
`check_stage_findings`/`check_dispatch_and_wait`/`check_board_stop_check`
already use), keyed on `"sys.path.insert"` + `"board_item_marker"` +
`"write_marker"` all appearing in one subject file. Verified against the
current tree: the only two files under `.github/workflows/` or
`.github/actions/` that reference `board_item_marker` at all are
`board-loop.yml` (all 17 sites, to be removed by this feature) and
`wing-commander-board-stop-check/action.yml` (one comment mentioning
`board_item_marker.is_loop_marker_author()`, which contains neither
`"sys.path.insert"` nor `"write_marker"` and so cannot false-positive).
The declared home (`.github/scripts/board_item_marker.py`) is a `.py`
file under `.github/scripts/`, which is outside `all_subject_files()`'s
scan universe (`.github/workflows/*.yml` plus `.github/actions/**`) by
construction — matching FR-010's own stated scope ("anywhere under
`.github/workflows/` or `.github/actions/`") — so the check needs no
explicit home-path exclusion to avoid self-matching, though one is kept
for defensive consistency with every other check in the file (in case a
`.py` file is ever relocated under `.github/actions/`).

## D7 — Extending `verify-single-home-idioms.py` (FR-015) rather than a
### new gate

Confirmed: the script is already wired as Gate 60 in `lint-workflows.yml`
(bare run + `--self-test`, both `if: "!cancelled()"`), and
`run-local-gates.py` derives its invocation list mechanically from
`lint-workflows.yml`'s own `run:` blocks — extending the script's
`DECLARED_HOMES`/`ALL_CHECKS`/self-test fixtures requires **no new
`lint-workflows.yml` step and no new registration**; FR-013's "reachable
through the gate registry" and "same subject same arguments locally as in
CI" are inherited for free by both new checks, matching how every prior
idiom added to this file (most recently `board-stop-check`,
`transcript-normalise`) landed with zero wiring changes. `lint-workflows.yml`'s
existing `pull_request.paths` filter already covers
`.github/workflows/**`, `.github/actions/**`, and `.github/scripts/**`, so
no trigger-path change is needed either.

**Self-test additions**: two more `_clean_tree` fixture entries (a minimal
valid `board_item_marker.py` CLI stub and a minimal valid
`resolve-pr-branch/action.yml`) and two more
`selftest_third_paste_fails(check_key, paste_path, paste_content)` calls —
mechanically identical to the pattern all 13 existing checks already use,
satisfying FR-012/Constitution VIII without new self-test infrastructure.

## D8 — Waivers: none expected (SC-008)

Cross-checked every existing entry in `.github/scripts/
single-home-waivers.json` (6 entries: `token-mint`, `failure-issue`,
`promotion`, `size-path-backstop`, `dispatch-and-wait`, `stage-findings`)
— none references `board-stop-check`, `marker-write`, or `pr-branch`, and
D5/D6's pattern choices are deliberately precise enough that no waiver is
expected to be needed for this feature's own consolidation, matching
SC-008.

## Decisions made without clarification (for the issue comment)

- **FR-011 / board-stop-check** (D1): treated as already satisfied by
  commit `98ee260` (an ancestor of the spec's own `e170077` triage
  baseline); this feature's work on it is verification, not new code.
  Reported separately as a stale-premise finding on the spec.
