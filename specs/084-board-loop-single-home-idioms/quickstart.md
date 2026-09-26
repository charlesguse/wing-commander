# Quickstart: Single-home the remaining board-loop idioms

This feature only changes `.github/workflows/board-loop.yml`,
`.github/scripts/board_item_marker.py`,
`.github/actions/_shared/resolve-pr-branch/action.yml` (new), and
`.github/scripts/verify-single-home-idioms.py`. Its behavior only runs
inside GitHub Actions (a scheduled board-loop run), so full end-to-end
validation is a post-merge, in-Actions confirmation — this guide covers
what can be validated locally plus what to check after merge.

## Prerequisites

- A checkout of this branch.
- Python 3 with PyYAML available (same environment `verify-single-home-idioms.py`
  already requires).

## 1. Confirm the site counts before making changes (SC-001/SC-002 baseline)

```bash
grep -c "sys.path.insert" .github/workflows/board-loop.yml   # baseline: sites using the working-tree/pristine bootstrap
grep -c "write_marker(" .github/workflows/board-loop.yml     # baseline: marker-write call count (expect 17)
grep -n 'Resolve the PR under' .github/workflows/board-loop.yml  # baseline: expect exactly 2 (review, readiness)
```

## 2. Confirm the site counts after consolidation (SC-001/SC-002)

```bash
grep -c "sys.path.insert(0, '.github/scripts')" .github/workflows/board-loop.yml   # expect 0
grep -c "wc-pristine/scripts'" .github/workflows/board-loop.yml                    # expect 0 inline sys.path inserts (the CLI invocation string itself does not count as a re-paste of the bootstrap)
grep -c "board_item_marker.py" .github/workflows/board-loop.yml                    # expect 17 (one CLI invocation per former call site)
grep -c 'gh pr view .* --json headRefName --jq' .github/workflows/board-loop.yml   # expect 0
grep -c 'uses: ./.github/actions/_shared/resolve-pr-branch' .github/workflows/board-loop.yml  # expect 2
```

## 3. Run the full PR-time gate suite (FR-017, CLAUDE.md's own instruction)

```bash
python .github/scripts/run-local-gates.py
```

This must pass, including Gate 60 (`verify-single-home-idioms.py`, bare and
`--self-test`) and Gate 98 (`verify-board-loop-helper-provenance.py`) —
SC-007.

## 4. Prove the marker-write single home is byte-identical (SC-003/SC-006)

For each of the 17 argument combinations documented in `research.md`'s
precedent report (job, step, and exact `write_marker` args), compare the
inline call's rendered output against the new CLI's output for the same
arguments:

```bash
# Working-tree example (triage's handover marker):
python3 -c "import sys; sys.path.insert(0, '.github/scripts'); from board_item_marker import write_marker; print(write_marker('triage', 0, None, None, None))"
python3 .github/scripts/board_item_marker.py --step triage --round 0

# Pristine example (fix job's push-pr marker):
python3 -c "import sys; sys.path.insert(0, '.github/scripts'); from board_item_marker import write_marker; print(write_marker('review', 0, 123, 'impl/084-iter1', 'abc123'))"
python3 .github/scripts/board_item_marker.py --step review --round 0 --pr 123 --branch impl/084-iter1 --base-sha abc123
```

Each pair's stdout must be identical.

## 5. Prove the new gates can fail their own subject (FR-012/SC-004)

```bash
python3 .github/scripts/verify-single-home-idioms.py --self-test
```

This exercises, for `marker-write` and `pr-branch` (alongside every
existing check): a clean tree passes, a re-paste at a new site fails and
names the declared home, a waived copy passes, a stale waiver fails.

## 6. Post-merge: confirm no observable board-loop behavior changed (FR-016,
### SC-006, SC-007)

Re-drive one scheduled board-loop run
(`gh workflow run board-loop.yml` on the wrapper that dispatches it, per
CLAUDE.md's "a fix to behaviour that only runs in Actions is proven after
merge by re-driving one run") and confirm:

- The run's status comments carry markers in the same shape as before
  (same fields, same `**Run:**` line).
- The review/readiness jobs check out the same PR branch they would have.
- Gate 98's provenance check is green on that run's workflow file.

Record the run URL as evidence on the PR or lifecycle issue, per CLAUDE.md.
