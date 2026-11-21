# Research: The Proof List

No `[NEEDS CLARIFICATION]` markers remained in spec.md. The decisions below were made without owner input except D13's answer-key source, which the owner chose (2026-11-20). Each is reversible and listed in the plan PR. Round 1 of the plan PR's review (#1150) is folded in here: the tasks stage reads only this directory, so nothing below may be left as "see the review".

## D1. Where the classifier lives
- **Decision**: one new module `.github/scripts/wc_proof_list.py`, mirroring `wc_board_status.py` (a pure half that fixtures drive, a runtime half they never run).
  - **Pure half**: `classify`, comment qualification (FR-006/007/009), shared-issue detection, set-apart counting, aged-out counting, and the two renderings of the section (D8). It takes the window's `start` and `end` as parameters, both UTC instants (FR-011, Story 2 AS5, SC-001), so a test can supply a window. `build` sets `end` to its own time and `start = end − 30 days`; the SC-001 replay passes the corpus's `window` values. Nothing in the pure half ties `end − start` to 30 days (D10).
  - **Runtime half**: `collect` reads git and `gh` and produces the pure half's input, failing loudly on any incomplete read (FR-013).
  - **Subcommands**: `build` (what the workflow runs) takes no window option: it sets the window from its own clock and writes the section artifact (D7). `capture --since --until --as-of --out` writes the pure half's input as a corpus file for SC-001 (D13); `--since` and `--until` are UTC instants that become the corpus window's `start` and `end`; it renders nothing and publishes nothing, and the workflow never runs it. `render FILE` prints a section from a fixture.
- **Rationale**: Principle VIII/IX; every branch is drivable from a fixture.
- **Alternatives**: inline jq/bash in the workflow (rejected: CLAUDE.md single-home rule, untestable); an agent (rejected: FR-016).
- **Later reuse (plan note)**: `collect`'s reading of the first-parent commits and their PRs is the one reading of "what reached `main`". If #1143's daily audit is built, it reads entries from here rather than keeping a second reader (spec Assumptions). Nothing is built for #1143 now.

## D2. One home for the reach computation (FR-003, SC-006)
- **Decision**: move the whole "which workflows reach these changed paths" computation out of `.claude/skills/prove-after-merge/scripts/redrive_candidates.py` into `.github/scripts/board_prove.py`, next to `scan_dispatchable_and_uses_graph()`. Both the hand procedure and the proof list call it. The moved pieces:
  - `reach(workflow, uses_graph)`: the transitive closure, today at `redrive_candidates.py` L72-81;
  - `mention_edges(changed_paths)`: the literal-mention edge, today inline in that script's `main()` (L109-133, #976). It reads workflow and composite files relative to the working directory, skips full-line comments and counts only `.github/` paths;
  - `reaching_workflows(changed_paths, uses_graph)`: the closure plus the mention edge, combined as `main()` combines them today (L135-140). It returns, per workflow, the changed paths it reaches and how (`scan`, `mention`);
  - `workflow_triggers(path)`: the trigger reader, today `triggers()` in the skill script;
  - `runs_of_its_own(path)`: false when a workflow's only trigger is `workflow_call` (D4).
- **What does not change**: `actions_only()` stays where it is. The hand procedure's output stays as it is (spec Assumptions): it calls `reaching_workflows()` and applies neither the reusable-only filter nor FR-005's nightly edges (D12).
- **The `.claude/` edit**: the implement stage cannot write under `.claude/` (`implement.yml`'s `no-write-paths` input defaults to `.claude/,.git/`, Constitution V), so it can never thin the skill script. The split:
  1. Implement moves the code into `board_prove.py` and builds the single-home check (below) with one interim exemption for the skill script. The exemption is a Gate-124-shaped table, `EXEMPT_REACH_COPIES` in `verify-board-prove.py`: a dict whose value is a call carrying `issue=(1144,)`, which `verify-waiver-citations.py` reads. #1144 is the lifecycle issue, open while the feature is built, so Gate 124's open-issue check turns `main` red if the entry outlives it.
  2. A `[maintainer]` task in the final "Maintainer follow-up" phase thins the skill script to import from `board_prove` and deletes the exemption entry. A human session commits it on the lifecycle branch before the final PR merges. Spec 116 had the same shape (implement built Gate 165, then a maintainer commit edited the skill script and dropped the exemption).
- **The single-home check (one home: Gate 89, `verify-board-prove.py`)**, the nearest existing gate, which already tests `actions_only()`:
  - **End-state rule, two parts**. Only an entry in `EXEMPT_REACH_COPIES` excuses a file from either part. An entry whose file no longer breaks either part (it defines none of the listed names and no longer lists, walks or opens files under `.github/workflows` or `.github/actions`) is stale and fails the gate, as `verify-action-runtime-pins.py` fails a stale entry. So a forgotten deletion fails the final PR's own CI once the skill script is thinned.
    1. **Names**: no Python file under `.github/` or `.claude/` other than `board_prove.py` defines `actions_only`, `reach`, `mention_edges`, `reaching_workflows`, `workflow_triggers`, `runs_of_its_own` or `nightly_e2e_edges` (D12). Today the only hits are the skill script's `reach()` and `triggers()`, which the exemption covers. `verify-metrics-wrapper-trigger-drops-watchdog.py`'s own `triggers(doc)` is not on the list.
    2. **Consumers**: the two consumers, the skill script and `wc_proof_list.py`, each import `reaching_workflows` and `actions_only` from `board_prove`. Neither lists, walks or opens files under `.github/workflows` or `.github/actions` itself. This part catches an inline copy of the mention loop, which has no function name to find.
  - **Fixtures, each failing without the code it tests**:
    - a copy of `reach` in another file; a copy of `actions_only`;
    - the skill script with `def reach` removed but the inline mention loop left in `main()` (fails by the consumer part);
    - the skill script passing only while its exemption entry exists;
    - a stale entry: a thinned skill script that still has its entry (fails);
    - a shell script reached only by a mention (fails if the mention edge is removed);
    - a composite reached only through a reusable workflow (fails if the closure is removed).
  - Gate 89 now reads the skill script. `lint-workflows.yml`'s `pull_request` paths already include `.claude/skills/*/scripts/**`, so a change to it triggers the suite with no wiring change.
  - **What holds the order**: a deletion forgotten after the thinning fails Gate 89 on the final PR (the stale rule above), but nothing mechanical blocks a final PR whose `[maintainer]` line was never done, since the exemption is then still live. Gate 124's open-issue check runs only on `main` (pushes and the daily schedule) and only fails once #1144 is closed. The unticked `[maintainer]` line and the owner's review of the final PR hold it, so that line says "before the final PR merges".
- **Alternatives**: a small owner-merged PR on `main` before implement, which needs no exemption but waits for the owner (CLAUDE.md "Deciding without the owner", item 1); the proof list importing from the skill script (rejected: a pipeline script depending on a skill directory); a copy (rejected by FR-003).

## D3. Reading each entry's own tree (FR-004)
- **Decision**: `git archive <sha> .github | tar -x` into a fresh temp directory per entry that needs a run; run the scan, `reaching_workflows()` and `nightly_e2e_edges()` with that directory as the working directory; cache per SHA within a build. Everything the scan reads is under `.github/`, including the `.github/scripts/board_*.py` files its script-import closure reads.
- **Rationale**: the scan uses cwd-relative paths, so no signature changes; this matches the board `prove` job's "merge commit's own tree".
- **Fixture**: the gate builds a small throwaway git repository in a temp directory (three commits: add a workflow, change a path it reaches, delete the workflow) and checks that both entries are credited from their own trees (Story 3 AS1, AS2). It needs no history of this repository.
- **Alternatives**: `git worktree add` (heavier, leaves state); rewriting the scan to take a tree reader (larger change, risks drift).

## D4. Complete reads of runs (FR-006, FR-013)
- **Decision**:
  - Reaching workflows are those `reaching_workflows()` returns (with D12's nightly edges merged in) **minus each workflow with no runs of its own** (`runs_of_its_own()` false: only `workflow_call`) **whose in-repository caller is also listed**. `reach()` returns the workflow itself whatever its triggers, so without the filter `implement.yml` and other reusable-only stages are listed with zero runs beside the wrapper that calls them. A reusable-only workflow that reaches a change but has no in-repository caller is listed as "no runs of its own" and leaves the entry in state 4.
  - Runs are read per remaining workflow from `/actions/workflows/{file}/runs?created=>=<aged-out day's start>&status=completed&per_page=100`, paged. The aged-out day's start is `start − 24h` (D10), not the oldest entry's merge, so runs that only an aged-out commit needs are read too. When a query's `total_count` exceeds 1,000, the read is sliced by day, and a day slice still over 1,000 fails the build. `board-loop.yml` (hourly) is the case that motivates slicing: it had 790 runs in the 30 days to 2026-11-19, under the cap but close to it.
  - "Finished" means `status == completed`. A run qualifies as a finished run of an entry when the merge is an ancestor of its `head_sha` (D5), which also means it started after the merge.
  - A workflow a later commit deleted is read by its file name like any other. A read of its runs that cannot be completed (including a file name the API no longer resolves) is a failed read (FR-013).
- **Rationale**: FR-013 forbids a silent partial list; the filter keeps "0 runs" lines out of the report and saves about a third of FR-020's size budget.
- **Alternatives**: read all repository runs once (rejected: far over the cap); sample (rejected).

## D5. "A commit that contains the merge", and what is set apart (FR-013)
- **Decision**:
  - Containment is `git merge-base --is-ancestor <merge> <head_sha>` on a `fetch-depth: 0` checkout.
  - History completeness is checked first: the checkout is not shallow (`git rev-parse --is-shallow-repository` is `false`), and the first-parent walk reaches past the aged-out day (D10). Otherwise the build fails.
  - A run before the merge, or on a commit that does not contain it, simply does not count. It is not set apart (spec Edge Cases).
  - **Set apart** is exactly FR-013's two cases and nothing else:
    1. a run whose `head_sha` is not in the checkout (`git cat-file -e <sha>^{commit}` fails) while history is complete, and only when it could otherwise have counted: for a run of a reaching workflow, its `run_started_at` is after the `merged_at` of an entry whose `reaching` includes that workflow; for a named run, after the `merged_at` of the entry whose comment names it. An unresolvable run that started before every such merge is not set apart. Where this case and the bullet above ("a run before the merge … is not set apart") meet, the bullet above wins: it is the reading closest to FR-006's runs "finished since the merge";
    2. a run a comment names that is not a run of this repository (D6).
  - The set-apart count is counted once across the window, de-duplicated by run id (case 1) or by the named URL (case 2), never per entry. A run named only by a comment that would not have counted anyway (posted before the merge, refused by FR-007, or failing the shared-issue condition) is not counted.
- **Alternatives**: compare by run `created_at` only (rejected: a run on an older branch commit created after the merge would qualify).

## D6. Comment sources, named runs and qualification (FR-006, FR-007, FR-009)
- **Where comments are read.** The places below are found for **every entry with a PR**, state 1 included: shared-issue detection counts every entry's PR (FR-006, "Shared issues" below), so a docs-only PR that names an issue still makes it shared. The comment threads on those places are read only for entries that need a run; a state-1 entry reads no thread.
  - **The PR**: all three surfaces, its issue comments (`issues/{pr}/comments`), its review comments (`pulls/{pr}/comments`) and its review bodies (`pulls/{pr}/reviews`). A proof written in a review is a comment on the PR.
  - **Each issue the PR closes**: `closingIssuesReferences`, read through `gh pr view N --json closingIssuesReferences` (GraphQL; REST has no such field), keeping only this repository's issues. An issue closed before the merge is still read.
  - **Each issue the merge commit's message closes**: a squash merge's message is the PR title, so `Fix #N: …` closes issue N from the default branch while `closingIssuesReferences` stays empty (#1073 closed #1072, #1077 closed #1071). The message (`git log -1 --format=%B <sha>`) is read for GitHub's closing keywords with `board_backlog_lines.CLOSING_RE`, the one home of that grammar, keeping this repository's issues only. Each candidate is kept only when `issues/{N}/events` has a `closed` event whose `commit_id` is the merge SHA: one REST read per candidate not already named, about 4 in a window. A number that is no issue (404) is no candidate.
  - **The PR's board item**: `board_backlog_lines.pr_issue(body)` (`Board item: #N`, or the legacy `Fixes #N`) and `board_backlog_lines.pr_line(body)` (a backlog line, which names the Maintenance backlog issue: the shared case).
  - **A final PR's lifecycle issue**: a final PR is one whose title starts `Finalize: ` (`finalize.yml` L1426 writes `Finalize: <title> (#N)`). Its lifecycle issue is `.issue` in `specs/<slug>/spec-meta.json` in the merge commit's own tree, where `<slug>` comes from the PR's head branch `spec/<slug>`. It is cross-checked against the `(#N)` in the title, and a disagreement fails the build. `closingIssuesReferences` is empty on merged final PRs (#1100, #1119, #1121), so it cannot be used here.
  - Issue comments and PR review comments are read with `?since=<merge time>` to bound the read (it filters by update time), then kept only when `created_at` is after the merge. Review bodies have no `since` parameter, so they are read in full and kept only when `submitted_at` is after the merge. Every read is paged to the end; a thread that cannot be read fully fails the build.
- **Named runs**:
  - A comment names a run by a run link. Links to this repository are matched with `board_triage.run_url_pattern(repo)`, the one home of the run-link pattern; a job link (`…/actions/runs/<id>/job/<id>`) matches through its run prefix. Links to another repository's runs are matched by a sibling, `board_triage.any_run_url_pattern()`, added next to it. Bare text such as "run 123" names no run (plan decision).
  - Every run a comment names is read by its own id, `gh api repos/{repo}/actions/runs/{id}` (as `board_merge.py` L579 does), whatever the entry's reach, and cached by id within a build. It qualifies when its `run_started_at` is after the merge and the merge is an ancestor of its `head_sha`. It need not have finished and need not belong to a reaching workflow, so an entry no workflow reaches can still be in state 2 (Story 2 AS3).
  - Set apart and counted (D5): a link to another repository's run; a 404 on this repository's id (run ids are global, so a 404 is how "not a run of this repository" shows, and a typo must not block the list for 30 days); a `head_sha` absent while history is complete. Any other API error is a failed read.
- **The board item marker**: each comment's marker is read with `board_item_marker.last_marker_match(body)` and `json.loads`, for any author and with no line filter. The module's other readers (`find_markers_matching`, `find_latest_marker*`, `read_marker`, `read_marker_with_timestamp`) are not used: they keep only comments that pass `is_loop_marker_author()`, which needs the App's login (only an App token can learn it), and `_keep_marker()` drops line markers when `BOARD_LINE_ID` is unset. A `proven` marker on a backlog line lands on the shared Maintenance backlog issue. `marker_step` is `proven`, `other` or `none`; an unparseable marker is `other`.
- **The predicate, in order** (FR-007, FR-009):
  1. A marker is present: the comment counts only at step `proven`, whoever posted it (Story 1 AS7: a `prove` marker by anyone stays in state 5).
  2. Otherwise, `user.type == "Bot"`: it never counts. The test is the account type, not the two named accounts. Exact App identity needs an App token or a new repository variable (the owner's), and no other bot posts proofs here. Comments by people and sessions are `User` accounts.
  3. Otherwise it counts, subject to the run, time and shared-issue conditions.
  - A `proven` comment names two runs, since every `write_marker()` output carries a `**Run:** <board-loop run>` line. Any qualifying named run counts.
- **Shared issues**: an issue is shared when more than one PR among the window's entries names it in any of the three ways above. On a shared issue a comment counts toward an entry only when its raw body names that entry's PR. The pure half parses this from the body: `#N` not preceded by a word character, `/` or `#` and not followed by a digit (so `#12` does not match `#123`), or the PR's URL `https://github.com/<repo>/pull/N` not followed by a digit.
  - **Known limit (plan note)**: since #1146 a session's proof form names the merge SHA, not the PR. On a shared issue such a proof counts only if it also names the PR. FR-006's wording is kept as merged, and this goes in reference.md's Known limits.
- **Reused homes**. `wc_proof_list.py` uses these and keeps no copy:

  | What | Home |
  |---|---|
  | commit → PR | `gh api repos/{repo}/commits/{sha}/pulls`, keeping the PR whose `merge_commit_sha` equals the SHA; when none does, the single merged PR in the list (a rebase merge's earlier commits); none means a direct push. Never the commit title: `5fccc8c8`'s title names the issue first |
  | changed paths | `board_route_backstop.diff_name_list(sha^1, sha)` |
  | closed issues | `gh pr view N --json closingIssuesReferences` |
  | board item | `board_backlog_lines.pr_issue()` / `pr_line()` |
  | run links | `board_triage.run_url_pattern(repo)` and its new sibling |
  | marker | `board_item_marker.last_marker_match()` |
  | need a run | `board_prove.actions_only()` (D2) |
  | reach | `board_prove.reaching_workflows()`, `runs_of_its_own()`, `nightly_e2e_edges()` (D2, D12) |
  | body size | `board_spec_request_body.utf16_len()` and `MAX_BODY_UNITS` (GitHub counts UTF-16 units) |
  | `gh` reads | a reader that raises on failure, like `wc_board_status._gh_lines`; never one that returns `None`, like `_gh_json` |

  The existing single-home gates each scan one file (for example `verify-board-backlog-lines.py` scans only `board_backlog_lines.py`), so `verify-proof-list.py` checks `wc_proof_list.py` itself. It may not define its own `Board item:` / `Fixes #` / `/actions/runs/` / `wing-commander-board-item` pattern, a UTF-16 counter, a `git diff --name-only` call or a call to `_gh_json`. A seeded copy of each in a fixture fails.
- **Alternatives**: trusting `author_association` to tell people from bots (rejected: the bot test is `user.type`); counting only App-authored markers (rejected: Story 1 AS7 applies the marker rule to anyone).

## D7. Publication: an artifact hand-off read by `board-status.yml` (FR-015, FR-021)
- **Decision**:
  - `wing-commander-proof-list.yml` holds no `issues: write`. A build uploads one artifact, `proof-list-section` (the file `proof-list-section.json`, schema in data-model.md), with `actions/upload-artifact@v6` and `retention-days: 7`. The artifact is how the section's content is handed to the issue's one writer, not a second durable output. The workflow writes nothing else: no step summary, comment, label or issue edit.
  - `wc_board_status.py` stays the issue's only writer. `snapshot()` gains a `proof_list` entry from a new reader, `proof_list_snapshot(repo, switches, now)`. It decides the section's status from the proof-list workflow's run history and downloads the latest build's artifact with `gh run download <id> -n proof-list-section`, using the `actions: read` that `board-status.yml` already grants. `render()` places the block between stable markers (contract).
  - The new switch joins `SWITCH_ENV` as `"proof_list_paused": "PROOF_LIST_PAUSED"`, and `board-status.yml` gains the matching env line, `PROOF_LIST_PAUSED: ${{ vars.WING_COMMANDER_PROOF_LIST_PAUSED }}`. `verify-board-status.py`'s existing `switches_half()` check then requires exactly that line.
  - `proof_list_snapshot()` never raises. Any failed read (run history, artifact download, a malformed artifact) gives status `unreadable`, and the rest of the Board status body renders as before.
  - The whats-on-me skill's `board_now.py` already calls `snapshot()`, `render()` and `switches_from()`, so it shows the section and the switch with no `.claude/` edit. Where its token cannot read Actions, it shows the `unreadable` notice.
  - While `WING_COMMANDER_BOARD_STATUS_PAUSED` is set, nothing rewrites the issue, the section included. That is what that switch already means.
- **Rationale**: this meets FR-021 (one writer; the proof list never writes the issue), the Layer line (one repository-only scheduled workflow of its own) and Story 4 AS1 (the workflow itself refuses).
- **Rejected**:
  - The earlier draft had the proof-list workflow call `publish`. `publish` renders the whole body from `snapshot()` with switch values that only `board-status.yml` passes, so every switch would render as off. It would ignore `WING_COMMANDER_BOARD_STATUS_PAUSED`, and the proof list would write the issue itself, against FR-015 and FR-021.
  - A `proof-list` job inside `board-status.yml`: it strains the Layer line and Story 4 AS1.
  - A splice-only subcommand the proof-list workflow calls: it breaks FR-021.
  - The earlier reason for rejecting artifacts ("`gh` cannot read it") was wrong: `gh run download` reads artifacts with `actions: read`.
  - Carrying the old block forward from the issue body: a timed-out, cancelled or paused build left the old list with no notice (finding 2 of the review). Run history replaces it.

## D8. Size (FR-020)
- **Decision**:
  - The section's renderer has one home, `wc_proof_list.py`'s pure half. A build renders two forms into the artifact: `full` (per state-5 entry and reaching workflow, finished-run counts by event and conclusion and the earliest and latest run link) and `names_only` (each entry with only its reaching workflows' names, plus a line saying the list was shortened). Both carry every state-4 and state-5 entry and the counts.
  - The build fails if `names_only` alone exceeds `MAX_BODY_UNITS` (60,000 UTF-16 units, under GitHub's 65,536), since it could never fit.
  - The writer renders the rest of the Board status body, then embeds `full` if the whole body is at most `MAX_BODY_UNITS` by `utf16_len()`. Otherwise it embeds `names_only`. If neither fits, it shows the failed notice saying the list was too large. There is no partly shortened form.
- **Rationale**: FR-020 forbids dropping entries; the budget depends on the rest of the body, which only the writer knows.

## D9. Kill switch (FR-018)
- **Decision**: `WING_COMMANDER_PROOF_LIST_PAUSED`. Only the exact value `true` pauses (`wc_board_status._switch_on`); unset means running. Creating the variable is the owner's.
  - It is read in two places. The proof-list workflow reads it as a step, its second, after the refusal: the job stands down, builds nothing and uploads nothing, and the run ends successfully, as `board-loop.yml`'s `select` job reads its switch as a step rather than a job-level `if:`. The writer reads it through `SWITCH_ENV` to show the paused notice.

## D10. Aged-out count (FR-012)
- **Decision**: the pure half is given the window's `start` and `end` (D1). An entry is a commit with `start < merge time ≤ end`. The aged-out day is `start − 24h < merge time ≤ start`. `build`, with build time T, passes `end = T` and `start = T − 30 days`, so a commit exactly 30 days old has aged out. The SC-001 replay passes the corpus's own `start` and `end` (data-model.md), which are 33 days apart; nothing checks the span. Commits in the aged-out day are classified with the same classifier, as if the window began one day earlier, and those in state 4 or 5 are counted. They are not entries. No earlier report is read. The report's label is "aged out in the 24 hours before the window start".
- **Fixtures**: one commit on each side of each of the three boundaries (`start − 24h`, `start`, `end`), and a supplied window that is not 30 days long.

## D11. Schedule
- **Decision**: cron `19 6 * * *` (06:19 UTC), 58 minutes before `board-status.yml` at 07:17, with `timeout-minutes: 15`. It avoids 06:37 (metrics sweep), 06:53 (cleanup), 07:13 (Spec Kit updater) and the hourly :13, :27 and :41. The workflow has its own concurrency group, `wing-commander-proof-list` (`cancel-in-progress: false`). It no longer shares board-status's group, because it writes nothing the writer writes.
  - If a scheduled build runs late, the writer shows the previous build, which carries its own build time. The 48-hour staleness rule in D17 covers a schedule that stops.

## D12. FR-005: the nightly end-to-end run's edges
- **Decision**: a separate `board_prove.nightly_e2e_edges()` reads the keys of the `declare -A stage_file=(…)` array from the tree's `.github/workflows/auto-release.yml` (today L1139-1148, eight wrapper files), relative to the working directory, so it works in D3's extracted tree. It returns edges from `auto-release.yml` to each `.github/workflows/<wrapper>`; the scan's existing wrapper → stage edges then reach the stages and whatever they reach.
  - Only the proof list merges these edges into the reach computation. `reach()`, `reaching_workflows()` and the hand procedure stay unchanged, so the hand procedure never suggests dispatching `auto-release.yml`, which can cut a release.
  - A tree with no `auto-release.yml` gives no edges. A tree that has the file but whose array cannot be parsed fails the build. Every tree since 1201a4a7 (2026-09-13) has the array.
  - `reached_via` is `nightly-e2e` when `auto-release.yml` reaches the change only through these edges.
- **Fixtures**: eight wrappers; a wrapper missing from the array; no `auto-release.yml`; an unparseable array.
- **Rationale**: the array is bash, which the scan cannot see; that is why the scan links the nightly run to only the two wrappers its `sed` lines name. A hard-coded list would drift and would ignore FR-004.

## D13. SC-001: the corpus, the answer key and who captures them
- **The corpus** is the serialized input of the pure half, so the replay calls neither git nor `gh` and runs in the depth-1 `lint` job of `lint-workflows.yml` (its checkout sets no `fetch-depth`). Its shape is in data-model.md. Reach is computed at capture time from each entry's own tree.
- **The producer** is `wc_proof_list.py capture`, run with `--since 2026-10-15T00:00:00Z --until 2026-11-17T00:00:00Z --as-of <the lookup's time>`: SC-001's "2026-10-15 to 2026-11-16" read as UTC instants, with the last day included, so `end` is the next midnight. Comments and runs after `--as-of` are dropped, so a proof posted after the lookup cannot move an entry. The capture also includes the day before `--since`, so the replay exercises the aged-out pass; SC-001 asserts nothing about that count. Comment bodies are reduced to the lines the pure half reads (a run link, a PR reference or the board item marker). Every other line becomes `…`.
- **The answer key**: the owner chose option A of the review's Q1 (2026-11-20). The per-PR results of the 2026-11-16 lookup survive in the saved 2026-11-16 lookup, held by the owner's sessions, outside the repository. Neither the tasks stage nor implement can read them, and the implement agent has no `gh run`/`gh api` in its tool allowlist and no Actions access on its token. So capturing the corpus and building the expected file is one `[maintainer]` task for a local session with full history and `gh` authentication. It runs once the collector exists on the lifecycle branch, and commits on that branch before the final PR merges. That session:
  1. runs `capture` and writes `.github/scripts/fixtures/proof-list/sc001/corpus.json`;
  2. builds `.github/scripts/fixtures/proof-list/sc001/expected.json` (schema in data-model.md) from the saved lookup;
  3. rechecks each merge against the merged spec's rules, which the lookup predates: FR-007's App and `github-actions[bot]` rule, FR-006's shared-issue condition and FR-013's set-apart runs. The lookup's 10/21 split may shift, and each shift goes on the expected-differences list with its reason;
  4. checks in only what SC-001 needs;
  5. scrubs anything that names a private project;
  6. deletes the interim SC-001 exemption entry (below).
- **Reasons** are SC-001's four: `own-tree`, `FR-005`, `FR-006-shared-issue`, `FR-013-set-apart`. A shift with any other cause (for example an entry the FR-007 bot-account rule moves) is not on SC-001's list. The session stops and raises it with the owner rather than adding a fifth reason, because SC-001 is merged spec.
- **The interval before the capture**: implement builds the replay check and drives it with small synthetic corpora. While the two SC-001 files are absent, the check reports SC-001 as "not yet captured" through a Gate-124-shaped exemption, `EXEMPT_SC001_PENDING` in `verify-proof-list.py` (`issue=(1144,)`), rather than as a red gate.
  - Why not a red gate: implement's cycle-start gate verdict (`implement.yml`'s `gate-suite-implement-cycle` job) is its agent's input every cycle, and a red SC-001 check would invite the agent to invent a corpus, so SC-001 would go green with nothing real behind it.
  - The exemption applies only while both files are absent, and a stale entry fails the gate. The five cases, each with a fixture:
    1. both files absent, entry present: "not yet captured", not red;
    2. either file present, entry present: fails as stale (the capture commit must delete the entry);
    3. exactly one file present: fails;
    4. both files present, no entry: the replay runs in full, and any difference not on the list fails;
    5. both files absent, no entry: fails (the exemption was deleted without the capture).

    The implement stage must not create, edit or weaken either file, or the check that reads them.
  - The trade-off: a deletion forgotten in the capture commit fails the final PR's own CI (case 2), but, as with D2's exemption, nothing mechanical blocks a final PR whose capture was never done. Gate 124 fails only on `main` and only once #1144 is closed. The unticked `[maintainer]` line and the owner's review of the final PR hold the order. `EXEMPT_SC001_PENDING` therefore holds only while lifecycle auto-merge (`WING_COMMANDER_LIFECYCLE_AUTO_MERGE`) is off, so that a human merges every final PR.
- **Alternatives**: a red check until the capture (rejected above); a pipeline capture (needs a wider tool allowlist or an Actions-read token, which is the owner's); deriving the key by running the new classifier (rejected: SC-001 would check the classifier against itself).

## D14. The scan's known under-reads (FR-022)
- **Decision**: keep the scan as it is (spec Assumptions), and say what it misses:
  - the mention edge counts only `.github/` paths in non-comment text (`mention_edges`, D2);
  - the script-import closure reads only `.github/scripts/board_*.py` (`board_prove._script_import_graph`);
  - no composite-calls-composite edge exists.
  - Example: a change only to `.claude/skills/speckit-implement/SKILL.md` lands in state 3, although `implement.yml` hands that file to its agent and `actions_only()` says it needs a run.
- The report carries one standing line: "State 3 means the scan found no edge, not that nothing runs the change." reference.md's Known limits gains the same bullet. Widening the scan is the owner's call.

## D15. API budget
- **Decision**:
  - **Estimate**: a build makes about 300-450 `GITHUB_TOKEN` REST calls (about 41 entries × 6-8 reads, plus 25-40 run pages), plus about 11 GraphQL `closingIssuesReferences` reads for the state-1 entries with a PR, whose namings shared-issue detection needs (D6). GraphQL is metered apart from the REST pool, so those reads do not touch the 600-call floor below. The `GITHUB_TOKEN` REST pool is 1,000 an hour per repository (GitHub's stated figure, not re-checked for this plan), shared with `board-status.yml` (07:17), `lifecycle-review-gate.yml` (:27), `spec-pr-review.yml` (:41) and PR CI. The board loop reads with the App token and mostly does not share it.
  - **Rules**: list runs at `per_page=100`; read comment threads only for entries that need a run (the namings are read for every entry with a PR, D6). Check `gh api rate_limit` first (it costs nothing) and fail before reading anything when fewer than 600 core calls remain. Treat a primary-limit 403/429 as a failed read with no back-off: the limit resets up to an hour later and the job times out at 15 minutes. Honour `Retry-After` only for secondary limits, within the timeout.

## D16. The refusal (FR-017)
- **Decision**: the workflow's first step, before checkout and before any read, refuses a `workflow_dispatch` whose `github.ref` is not `format('refs/heads/{0}', github.event.repository.default_branch)`, or whose default-branch value is empty. It exits non-zero. `wing-commander-e2e-reference-image.yml` L160 is the precedent (`push` and `workflow_dispatch`). A scheduled run always runs on the default branch and is not checked. There is no literal `main`.
  - A refused run is on another branch, so the writer, which reads only default-branch runs, never sees it. The section is unchanged (FR-021, SC-007).

## D17. Which notice the section shows, and the workflow's step gating
- **The writer decides every notice**, so the proof-list workflow has no notice step. In `proof_list_snapshot()`, in order:
  1. The switch is set (`SWITCH_ENV`): `paused`.
  2. Read the proof-list workflow's finished runs on the default branch (`status=completed`, `branch=<default>`, events `schedule` and `workflow_dispatch`, `head_repository` this repository), newest first. The default branch name comes from `gh api repos/{repo} --jq .default_branch`.
     - No such run: `never`.
     - The latest one did not succeed (failure, cancelled, timed out, or anything else): `failed`. That covers a timeout and a lost runner, with no step in the failed run.
     - It succeeded but its build step was skipped (it stood down on the switch): `paused`. This is the case the day after the switch is cleared, until the next build.
     - It succeeded, built, and started more than 48 hours before the writer runs: `failed` ("no build in the last 48 hours").
     - It succeeded and built: `built`. Download its artifact; a missing or malformed artifact gives `unreadable`.
  3. Last good build: the newest of those runs whose build step succeeded (read from `actions/runs/{id}/jobs`), paging until one is found, or `never`.
  4. Any read failure in this function: `unreadable`, and the rest of the body renders. The last good build is then `unknown` when the history itself could not be read.
- **The workflow's steps**, in order, with no `always()` or `!cancelled()` anywhere:
  1. **Refuse** (D16).
  2. **Pause check**: sets an output from `vars.WING_COMMANDER_PROOF_LIST_PAUSED`.
  3. **Checkout** with `fetch-depth: 0` and `persist-credentials: false`.
  4. **Build the proof list**.
  5. **Upload**.

  Steps 3-5 are gated on the pause output, under the default `success()`. A failed refusal stops every later step, and a failed build stops the upload. The build step's name is a constant `wc_board_status.py` reads; `verify-board-status.py` checks it against the workflow file.
- A `review-step-gating` pass covers this workflow and the `board-status.yml` change (a task, see plan.md).
