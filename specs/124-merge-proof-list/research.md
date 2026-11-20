# Research: The Proof List

No `[NEEDS CLARIFICATION]` markers remained in spec.md. The decisions below were made without owner input; each is reversible and listed in the plan PR.

## D1. Where the classifier lives
- **Decision**: one new module `.github/scripts/wc_proof_list.py`, pure functions plus a thin `gh`/`git` collector, mirroring `wc_board_status.py` (pure `render`, runtime half never run by fixtures).
- **Rationale**: Principle VIII/IX — every branch drivable from fixtures; precedent in this repo.
- **Alternatives**: inline jq/bash in the workflow (rejected: CLAUDE.md single-home rule, untestable); an agent (rejected: FR-016).

## D2. One home for the reach rule
- **Decision**: move `reach()` from `.claude/skills/prove-after-merge/scripts/redrive_candidates.py` into `board_prove.py` (next to `scan_dispatchable_and_uses_graph`), add the FR-005 nightly rule there, and have both consumers import it. A gate asserts no second definition.
- **Rationale**: FR-003/SC-006. `board_prove.py` is already the single home of `actions_only` and the scan.
- **Risk**: stage agents may not write under `.claude/`. If the implement stage cannot edit the skill script, it leaves a documented `[maintainer]` task; the proof list still imports from `board_prove`.
- **Alternatives**: proof list imports from the skill script (rejected: scripts shared with a skill dir are an odd dependency direction); copy (rejected by FR-003).

## D3. Reading each entry's own tree
- **Decision**: `git archive <sha> .github | tar -x` into a fresh temp dir per entry needing a run, run the existing scan with that cwd, cache per sha.
- **Rationale**: the scan uses cwd-relative paths; this needs no signature change and matches the board `prove` job's "merge commit's own tree".
- **Alternatives**: `git worktree add` (heavier, leaves state); rewriting the scan to take a tree reader (larger change, risks drift).

## D4. Complete reads of runs
- **Decision**: per reaching workflow, query `/actions/workflows/{id}/runs` with `created=>=<oldest merge date>` sliced by day when a slice's `total_count` exceeds 1,000; any slice still over the cap fails the build. Deleted workflows are read by their path/id from the entry's tree. `board-loop.yml` (hourly) is the case that motivates slicing.
- **Rationale**: FR-013 forbids a silent partial list.
- **Alternatives**: read all repo runs once (rejected: far over the cap); sample (rejected).

## D5. "Run on a commit that contains the merge"
- **Decision**: `git merge-base --is-ancestor <merge> <head_sha>` on a `fetch-depth: 0` checkout; `main` history completeness verified first (shallow check, first-parent walk reaches beyond the window start). A `head_sha` absent locally while history is complete is set apart and counted (FR-013).
- **Alternatives**: compare by run `created_at` only (rejected: a run on an older branch commit created after merge would qualify).

## D6. Comment sources and qualification
- **Decision**: read comments on the PR, each issue it closes (`closingIssuesReferences`) or names as board item (via `board_item_marker`'s parsing in the PR body), and the lifecycle issue for a final PR. Qualify per FR-006/007/009: posted after merge; names a run URL of this repository whose run started after merge on a containing commit; bot accounts (`user.type == "Bot"`, covering the App and `github-actions[bot]`) only with marker step `proven`; step `prove` never; shared issues require the entry's PR number in the body. A thread that cannot be paged fully fails the build.
- **Alternatives**: trusting `author_association` to detect "people" (rejected: bot test is `user.type`).

## D7. Report publication and persistence across board-status rewrites
- **Decision**: `wc_board_status.py` remains sole writer. `publish` gains an optional proof section; `render()` places a `<details>` block between `<!-- wc-proof-list:begin -->`/`end` markers with a `<!-- built=… last-good=… -->` comment. The daily board-status run reads the current body, carries the block forward verbatim, and the proof-list workflow shares the board-status concurrency group.
- **Rationale**: FR-021 — a second writer would be overwritten; carry-forward keeps the section alive between builds.
- **Failed/paused build**: the block is replaced by a notice and last-good date; the stale list is dropped (simplest way to satisfy "no older list without notice").
- **Alternatives**: store the list as an artifact and have board-status download it (rejected: `gh` cannot read it, adds an auth path); a separate issue (rejected: spec says collapsed section of Board status).

## D8. Size handling
- **Decision**: three renderings in order — full (per-workflow counts by event/conclusion, earliest/latest), per-entry reaching-workflow names only, then fail. Shortening is announced in the section. Budget is the issue body limit minus the rest of the board-status body, computed at render time.
- **Rationale**: FR-020 forbids dropping entries.

## D9. Kill switch name
- **Decision**: `WING_COMMANDER_PROOF_LIST_PAUSED`. Creating the variable is the owner's (FR-018); the workflow treats unset as running.

## D10. Aged-out count
- **Decision**: classify commits in the day before the window start with the same classifier (window shifted one day), count those in states 4/5; never read a prior report (FR-012).
- **Cost note**: this adds one day of commits; tree extraction cached.

## D11. Schedule
- **Decision**: cron `37 7 * * *` (after `board-status` at 07:17), sharing its concurrency group so ordering is serialized not assumed.
