# Quickstart: validating the proof list

Prerequisites: a checkout with full history; `python3`, PyYAML.

1. **Gate suite**: `python .github/scripts/run-local-gates.py`. Each fixture below must fail when the code it tests is removed.
   - **`verify-proof-list.py`** (new, an unnumbered `lint-workflows.yml` step), driving `wc_proof_list.py`'s pure half, its `collect` half with a stub `gh` on `PATH` (as `verify-board-status.py` drives `publish`), and the workflow file:
     - **States**: one fixture for each of the five states; the ties (Story 2 AS3: a qualifying comment and no reach gives state 2); AS1's docs-only, verify-only, mixed and empty changed paths.
     - **Comments**:
       - a person's `prove` marker, and a person's `merged` marker (both stay in state 5);
       - an unmarked App comment, and an unmarked `github-actions[bot]` notice (both stay in state 5);
       - a line `proven` marker on the shared Maintenance backlog issue that names the PR (state 2);
       - a comment naming a failed run (still state 2, FR-010);
       - a comment posted before the merge, and a comment naming a run that started before the merge or on a commit without it (neither counts);
       - a PR review body and a review comment carrying a proof (both read).
     - **Shared issue (AS8)**: the named run qualifies for both entries, and the comment names only the first PR. The fixture fails if the names-the-PR check is removed. Also `#12` against PR #123.
     - **Named runs**: state 2 for an entry no workflow reaches; a named run still in progress (qualifies); a 404 (set apart); another repository's run (set apart, AS9); a job link; one recorded `actions/runs/{id}` JSON response mapped through `collect` to its NamedRun record.
     - **Set apart (AS9)**: an unresolvable run plus a foreign named run give a count of 2. A pre-merge run and a run on a non-containing commit leave it unchanged. A run named twice counts once.
     - **Reach**: own tree, from a throwaway git repository built by the gate (Story 3: a workflow added, then deleted later); nightly reach (AS4), with eight wrappers, a wrapper missing from the array, no `auto-release.yml`, and an unparseable array; a reusable-only change listing `wing-commander-5-implement.yml`, not `implement.yml`; an orphan reusable shown as "no runs of its own".
     - **Entries**: a direct push; a final PR whose `closingIssuesReferences` is empty, with its lifecycle issue from `spec-meta.json`, and a title that disagrees with it (fails); a commit whose title names an issue before the PR number.
     - **Aged out**: one commit on each side of each of the three boundaries (`start - 24h`, `start`, `end`), and a supplied window that is not 30 days long (research D10).
     - **Failed reads (FR-013)**, each failing the build: runs past the cap after slicing; shallow or short history; an unreadable comment thread; an unresolvable tree. Also a 403/429 primary limit, and a rate-limit floor below 600.
     - **Size**: the full and names-only renderings; a names-only form over `MAX_BODY_UNITS` fails the build.
     - **Determinism (SC-003)**: the same inputs built twice give the same states.
     - **Workflow file**:
       - the refusal is the first step, before checkout, and compares against `github.event.repository.default_branch`;
       - the pause is a step, not a job `if:`;
       - steps 3-5 are gated on it with no `always()` or `!cancelled()`;
       - no write permission;
       - `build` is the only subcommand invoked, and it has no window option;
       - no `gh workflow run`, `gh issue`/`gh pr` comment, edit, close or label call, and no `gh api -X POST|PATCH|PUT|DELETE` in the workflow or the script;
       - no agent action.
     - **Reused homes**: a seeded copy of each pattern or reader listed in research D6 fails.
     - **SC-001 replay** (step 2).
   - **`verify-board-status.py`** (existing), driving `proof_list_snapshot()` and `render()`:
     - built (full form); built (names-only fallback); too large for either (failed notice);
     - paused by the switch; paused by a latest run that stood down; the day after the switch is cleared (still paused until the next build);
     - failed (failure, cancelled, timed out); failed for no build in 48 hours; never built;
     - a refused run on another branch, ignored;
     - an unreadable history or artifact (notice, with the rest of the body still rendered);
     - the last-good date found by paging past runs that stood down;
     - the build step's name constant matching the workflow file;
     - the new `SWITCH_ENV` entry's env line in `board-status.yml` (the existing `switches_half()` check).
   - **`verify-board-prove.py`** (Gate 89, existing): the single-home check and its fixtures (research D2); `EXEMPT_REACH_COPIES` excusing only the skill script; a stale entry (a thinned skill script that still has its entry) failing.
   - **`verify-waiver-citations.py`** (Gate 124, existing) reads `EXEMPT_REACH_COPIES` and `EXEMPT_SC001_PENDING`.
2. **SC-001 replay**: `python .github/scripts/verify-proof-list.py` replays `.github/scripts/fixtures/proof-list/sc001/corpus.json` over its window (`2026-10-15T00:00:00Z` to `2026-11-17T00:00:00Z`, the corpus's own `start` and `end`) and compares against `expected.json`. Any difference not on its list, and any listed difference that no longer occurs, fails. While both files are absent the check reports "SC-001 not yet captured" under `EXEMPT_SC001_PENDING` (research D13); the `[maintainer]` capture task adds the files and deletes the exemption in the same commit. A fixture for each of D13's five cases: both files absent with the entry (not yet captured); either file present with the entry (fails as stale); exactly one file present (fails); both present with no entry (the replay runs); both absent with no entry (fails).
3. **Dry render**: `python .github/scripts/wc_proof_list.py render .github/scripts/fixtures/proof-list/<case>.json` prints a section. Confirm it has no verdict wording.
4. **After merge** (`[maintainer]`, `prove-after-merge`):
   1. Dispatch `wing-commander-proof-list.yml` on the default branch and wait for it.
   2. Dispatch `board-status.yml`, then run `gh issue view <Board status #>`. Confirm the collapsed section shows its build time and the counts.
   3. Dispatch the proof list from another branch and confirm it refused before checkout. Dispatch `board-status.yml` again and confirm the section is unchanged.
   4. The owner sets `WING_COMMANDER_PROOF_LIST_PAUSED=true`. Dispatch the proof list (it stands down, with no artifact), then `board-status.yml`. Confirm the paused notice with the last good build's date.
   5. The owner clears the switch.

See [contracts/proof-list-report.md](contracts/proof-list-report.md) and [data-model.md](data-model.md).
