# Data Model: Single-home the remaining board-loop idioms

This feature moves call sites and adds structural checks; it defines no
new persistent entity or storage schema. The "entities" below are the
shapes that must stay stable across the move (spec.md's Key Entities
section), plus the two new interface shapes this plan introduces
(the marker CLI and the PR-branch composite).

## Board Item Marker (unchanged shape, relocated write path)

The HTML-comment payload a board-loop step appends to its own status
comments.

| Field | Type | Notes |
|---|---|---|
| `step` | string | e.g. `stalled`, `review`, `readiness`, `proven`, `prove`, `breach` (`BREACH_STEP`), `awaiting-merge` (`AWAITING_MERGE_STEP`) |
| `round` | int | Caller state; `0` unless the review job is advancing a follow-up round |
| `pr` | int \| null | `null` for markers with no associated PR (e.g. `stalled` before a PR exists) |
| `branch` | string \| null | `null` alongside `pr: null` |
| `base_sha` | string \| null | Only populated on `fix`/`review` sites that track a base commit |

Rendered as `**Run:** <url>\n\n` (when `GITHUB_SERVER_URL`/
`GITHUB_REPOSITORY`/`GITHUB_RUN_ID` are all set) followed by
`json.dumps({...}, sort_keys=True)`. `write_marker(step, round, pr, branch,
base_sha)` (`.github/scripts/board_item_marker.py:110`) owns this
rendering today and continues to; this feature adds a CLI wrapper around
it (see "Marker-Write CLI Contract" below), never changes its body.
`read_marker`/`read_marker_with_timestamp`/`last_marker_match` are the
read side and are untouched.

## Marker-Write CLI Contract (new)

The single home for every board-loop marker write, callable identically
from the working tree and the pristine snapshot.

| Flag | Required | Type | Absent-value semantics |
|---|---|---|---|
| `--step` | yes | string | literal step name, or `BREACH_STEP` / `AWAITING_MERGE_STEP` (resolved internally against `board_eligibility.py`) |
| `--round` | no | int, default `0` | n/a (always has a value) |
| `--pr` | no | int-parsed string | omitted flag → `None` → JSON `null` |
| `--branch` | no | string | omitted flag → `None` → JSON `null` |
| `--base-sha` | no | string | omitted flag → `None` → JSON `null` |

Output: the rendered marker text on stdout (`print(...)`), byte-identical
to today's `print(write_marker(...))` inline calls. See
`contracts/marker-write-entrypoint.md`.

## Provenance Context (unchanged; two call spellings, one script)

| Context | Scripts directory | Invocation |
|---|---|---|
| Working tree (triage, route, prove) | `.github/scripts` | `python3 .github/scripts/board_item_marker.py --step ...` |
| Pristine snapshot (fix, review, readiness) | `$RUNNER_TEMP/wc-pristine/scripts` | `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py" --step ...` |

The snapshot step (`board-loop.yml`, byte-identical across fix/review/
readiness) `git archive`s the whole `.github/scripts` directory, so no
separate wiring is needed for `board_item_marker.py` to appear in the
pristine copy.

## PR-Branch Resolution Contract (new)

`.github/actions/_shared/resolve-pr-branch/action.yml`.

| Input | Required | Default | Notes |
|---|---|---|---|
| `pr-number` | yes | — | the PR to resolve |
| `token` | yes | — | passed as `GH_TOKEN`; callers pass `github.token` |
| `round` | no | `""` | pass-through only; never derived from the PR (FR-007) |

| Output | Source |
|---|---|
| `pr-number` | echoes the `pr-number` input |
| `branch` | `gh pr view <pr-number> --json headRefName --jq .headRefName` |
| `round` | echoes the `round` input |

Failure mode (FR-008, new behavior): a failed `gh pr view` or an empty
resolved branch both abort the step non-zero with `::error::` — never a
silent empty `branch=` write. See
`contracts/pr-branch-resolution.md`.

## Declared Home (spec's Key Entity, applied)

| Idiom | Check name | Declared home | Status |
|---|---|---|---|
| Marker-write bootstrap | `marker-write` | `.github/scripts/board_item_marker.py` | New check, this feature |
| PR-branch resolution | `pr-branch` | `.github/actions/_shared/resolve-pr-branch/action.yml` | New check, this feature |
| Kill-switch/stop-request recheck | `board-stop-check` | `.github/actions/wing-commander-board-stop-check/action.yml` | **Already exists** (commit `98ee260`, predates this feature) — see research.md D1 |

## Idiom Detection Patterns (spec's Key Entity, applied)

| Check | Scan strategy | Fragments (all must co-occur) |
|---|---|---|
| `marker-write` | File-wide co-occurrence | `sys.path.insert`, `board_item_marker`, `write_marker` |
| `pr-branch` | Per-step (`_step_lists`) co-occurrence | `gh pr view`, `headRefName`, `echo "pr-number=`, `echo "branch=` |
| `board-stop-check` | File-wide co-occurrence (existing, unchanged) | `from board_stop_check import find_stop_request`, `gh run cancel`, `board-stop-check-comments.json` |

See research.md D5/D6 for why these exact fragments were chosen (avoiding
false positives against `pr-conversation.yml`'s two unrelated `headRefName`
reads and `wing-commander-board-stop-check`'s one comment mention of
`board_item_marker`).

## Waiver (spec's Key Entity, unchanged shape)

`.github/scripts/single-home-waivers.json`: `{file, check, pattern, count,
issue, reason}` per entry, `check` one of `CHECK_NAMES`. No new waiver
entries are expected for this feature's own consolidation (SC-008); the
existing 6 entries are untouched.
