# Contract: FR-010 through FR-015 — Gate 60 gains two checks

Modeled directly on `specs/049-single-home-release-idioms/contracts/
single-home-gate.md`, the contract for Gate 60's original landing. This
feature extends the same script rather than writing a new one (FR-015).

## `.github/scripts/verify-single-home-idioms.py` (EXTENDED — Gate 60)

**Two new entries in `DECLARED_HOMES`**:

```python
"marker-write": ".github/scripts/board_item_marker.py",
"pr-branch": ".github/actions/_shared/resolve-pr-branch/action.yml",
```

Each gains the same kind of dated/issue-cited comment every existing entry
carries (see `board-stop-check`'s comment citing issue #462, for the
style).

**`marker-write` check** — file-wide co-occurrence (research.md D6):

Fragments: `"sys.path.insert"`, `"board_item_marker"`, `"write_marker"`,
all present in one subject file. Declared home excluded the same way
`check_stage_findings`/`check_board_stop_check` exclude theirs. Verified
against the current tree: only `board-loop.yml` (the 17 sites this
feature removes) and one comment in `wing-commander-board-stop-check/
action.yml` (mentions `board_item_marker` but neither `sys.path.insert`
nor `write_marker`) reference the module today — zero expected false
positives, zero new waivers (SC-008).

**`pr-branch` check** — per-step co-occurrence, via the existing
`_step_lists(doc)` helper (research.md D5 — the same per-step strategy
`check_failure_issue`/`check_token_mint` use, chosen specifically to avoid
two known false-positive sites):

Fragments, all required in one step's `run:` text: `"gh pr view"`,
`"headRefName"`, `'echo "pr-number='`, `'echo "branch='`. Verified this
does **not** match `pr-conversation.yml`'s two unrelated `headRefName`
reads (neither writes the `pr-number=`/`branch=` pair), nor any of the
other `headRefName` reads in `watchdog.yml`, `auto-release.yml`,
`wing-commander-7-cleanup.yml`, `intake.yml`, or
`auto-update-spec-kit.yml`.

**Failure message format** (matching every existing check):
`::error file=<path>::verify-single-home-idioms: <file>:<line>: <detail> -- see <declared home>`.

**`board-stop-check`**: already exists (research.md D1) — no change. This
feature's User Story 3 obligation for it is re-verification: confirm
`check_board_stop_check` and its `selftest_third_paste_fails` mutation
still pass, and cite that as the evidence for AS1/SC-004's third idiom.

## Waiver file — no changes expected

`.github/scripts/single-home-waivers.json` keeps its current 6 entries.
SC-008 expects 0 new waivers for this feature's own consolidation; the
pattern choices above (research.md D5/D6) are deliberately precise enough
that neither new check needs one.

## Self-test (`--self-test`, FR-012/Constitution VIII)

Two additions to the existing synthetic-tempdir harness, mechanically
identical to the 13 existing checks:

- `_clean_tree(tmp)` gains a minimal valid `board_item_marker.py` (a stub
  `write_marker` plus the new `main()`/CLI guard) and a minimal valid
  `resolve-pr-branch/action.yml`, so the synthetic "clean tree" continues
  to pass with only the declared homes present.
- `selftest_third_paste_fails("marker-write", <new path>, <old-bootstrap
  text>)` and `selftest_third_paste_fails("pr-branch", <new path>, <old
  gh-pr-view + GITHUB_OUTPUT text>)`, each asserting a `Finding` with that
  `check`/`path` appears when the old idiom is re-pasted at a synthetic
  new site.
- The existing generic waiver-interaction self-test cases
  (`selftest_waived_copy_passes`, `selftest_stale_waiver_fails`) already
  cover both new checks for free, since `apply_waivers`/`check_waiver_shape`
  are check-agnostic.

## Wiring (FR-013)

No new `lint-workflows.yml` step: Gate 60 is already registered there
(bare run + `--self-test`, both `if: "!cancelled()"`), and
`run-local-gates.py` re-derives both invocations automatically from
`lint-workflows.yml`'s own `run:` blocks (research.md D7). The existing
`pull_request.paths` filter already covers
`.github/workflows/**`/`.github/actions/**`/`.github/scripts/**`, so no
trigger-path change is needed.

## Gate 10 interaction

No new script is added (FR-015: everything extends the one already-wired
file), so Gate 10's "every `verify-*.py` must be invoked by a workflow"
convention check needs no new entry.
