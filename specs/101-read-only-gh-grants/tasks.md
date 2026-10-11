# Tasks: Read-Only Agents Hold No Write-Capable `gh` Grant

**Input**: Design documents from `/specs/101-read-only-gh-grants/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/gate-93-check-4c.md, contracts/diagnose-staged-logs.md, quickstart.md

**Tests**: The spec requires fixtures and a mutation self-test for the gate (FR-012, SC-003); those are tasks in US3. No other test tasks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 diagnose, US2 auto-update, US3 gate, US4 docs and contracts

Workflow comments are load-bearing (gates byte-compare them): after any edit under `.github/workflows/`, run `python .github/scripts/run-local-gates.py`.

## Phase 1: Setup

**Purpose**: Establish the baseline before editing.

- [X] T001 Run `python .github/scripts/run-local-gates.py` on the branch and record the baseline result, so later failures are attributable to this feature.
- [X] T002 [P] Read the current `collect-step-summary` step in `.github/workflows/watchdog.yml` (job-log fetch near lines 1262-1309), the `diagnose` job's tool-args site (`Bash(gh:*)` near line 2585) and prompt, and the "Decide upgrade path" step in `.github/workflows/auto-update-spec-kit.yml` (lines ~1092-1131), so every later edit is made against the current text.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared fetch helper both the collector and the new staging step use (FR-018: one home, no second copy).

**⚠️ CRITICAL**: US1 depends on this.

- [X] T003 Create `.github/actions/_shared/fetch-job-logs.sh` per `contracts/diagnose-staged-logs.md`. Inputs are env `GH_TOKEN`, `GITHUB_REPOSITORY`, `RUN_ID` and an output-directory argument. List jobs with `--paginate`, capture through a direct pipeline with `|| rc=` (never a bare command substitution), and skip `skipped`/`cancelled` jobs. Do one bounded retry after `sleep 10` per failed read. Never write an error message or an empty body as log content. Write `jobs.json` and per-job log files. Print `ok` or `failed` on the final line and always return 0.
- [X] T004 Rewrite `collect-step-summary` in `.github/workflows/watchdog.yml` (~1262-1309) to call `.github/actions/_shared/fetch-job-logs.sh` instead of its inline per-job fetch. Keep the sentinel-scanning logic inline and keep `ACTIONS_TOKEN: ${{ github.token }}`. Verify its behaviour is unchanged on the success and failure paths.

**Checkpoint**: One fetch helper exists and is used by the collector.

---

## Phase 3: User Story 1 - Diagnose cannot touch the repository (Priority: P1) 🎯 MVP

**Goal**: `watchdog.diagnose` holds zero `gh` grants and reads failed-job logs staged by a deterministic step.

**Independent Test**: The composed allowed list for `watchdog.diagnose` has no `gh`. After the staging step, logs sit at the literal paths the prompt names. A failed fetch produces `outcome:"failed"` and a verdict stating that job logs could not be gathered.

- [X] T005 [US1] Add a `Stage failed-job logs` step to the `diagnose` job in `.github/workflows/watchdog.yml`, before the agent step, with `continue-on-error: true` and `ACTIONS_TOKEN: ${{ github.token }}` (the workflow already grants `actions: read`). Call `.github/actions/_shared/fetch-job-logs.sh`, keep jobs whose conclusion is `failure`, and write `${{ steps.ctx.outputs.runner-temp }}/watchdog-job-logs/<job_id>.log` and `watchdog-job-logs-status.json` with the shape in `data-model.md`. Write the status file on every path. On a listing failure, a log read failure or an empty body, set `outcome:"failed"`, write no log file for that job (`file: null`), and append `"job-logs"` to `watchdog-untrusted-collectors.json`. Add the `container-shell-safety` and `review-step-gating` checks to the PR review notes.
- [X] T006 [US1] Remove `Bash(gh:*)` from the `watchdog.diagnose` tool-args `default-allowed-tools` in `.github/workflows/watchdog.yml` (~line 2585). Keep `Read,Grep` and the `python3 -I …/git_read.py` wrapper grant.
- [X] T007 [US1] Rewrite the diagnose prompt in `.github/workflows/watchdog.yml`. Name the log directory and status file by literal path. Frame the logs as untrusted DATA like the signals file. Remove every sentence that names `gh` or a fetch the agent would perform. State that when the status is `failed`, the status file is missing, or `job-logs` is in the untrusted collectors file, the verdict says job logs could not be gathered and no signal is dropped silently.
- [X] T008 [US1] Run `python .github/scripts/run-local-gates.py` and fix any workflow-comment or gate fallout from T004-T007.

**Checkpoint**: US1 is complete and is the MVP.

---

## Phase 4: User Story 2 - Upgrade agent held to the same rule (Priority: P1)

**Goal**: The "Decide upgrade path" agent holds no `gh` grant.

**Independent Test**: The inline `--allowedTools` has no `gh`, and the prompt names only the staged `release-notes.json`.

- [X] T009 [P] [US2] In `.github/workflows/auto-update-spec-kit.yml`, remove `Bash(gh api:*)` from the "Decide upgrade path" inline `--allowedTools` (~line 1131).
- [X] T010 [US2] In the same step's prompt (~lines 1092-1094), rewrite the sentence that describes `gh api` as an evidence tool. It should say Bash is restricted to the git wrapper and that the only evidence is the staged `release-notes.json`. Then run `python .github/scripts/run-local-gates.py`.

**Checkpoint**: Both named agents are at zero `gh` grants.

---

## Phase 5: User Story 3 - The rule is mechanical (Priority: P1)

**Goal**: Gate 93 check 4b fails on any `gh` grant on a read-only agent step in any workflow, with fixtures and a mutation self-test.

**Independent Test**: `python .github/scripts/verify-issue-context-single-home.py` and `--self-test` pass on the real tree. Each fixture fails or passes as `contracts/gate-93-check-4c.md` lists.

**Depends on**: US1 and US2 (otherwise the gate fails the clean tree).

- [X] T011 [US3] In `.github/scripts/verify-issue-context-single-home.py`, extend `_bash_grant_problems` and `check_read_only_git(strict=False)` so a `Bash` grant whose first token's basename is `gh` (any wildcard spelling or path-qualified) is a problem. Match by whitespace-split token, not substring. Reword the message to name the workflow, step and grant, say `gh` reaches remote writes, local file writes and alias/extension execution, point at the staged-file route, and point at `docs/agent-friendly-workflows.md` rather than restating the rationale. Update the check 4b docstring to drop "Other Bash grants (`gh ...`) are not this check's business" and to state the shipped-defaults-only scope (FR-014).
- [X] T012 [US3] Add an exemption table in the same script for `pr-conversation.classify` (`.github/workflows/pr-conversation.yml`), scoped to exactly `gh pr view`, `gh issue view` and `gh search issues`, per research D4 and `data-model.md`. The gate fails if the site holds any other `gh` grant or holds none (stale). Cite the open "Maintenance backlog" issue (#889) as tracker. Before closing out, run `grep -rnE '"#889"|issue *= *\([^)]*\b889\b' .github/scripts/` and follow the waiver-register shape that Gate 124 (`verify-waiver-citations.py`) expects.
- [X] T013 [US3] Make the loud-failure cases fail: a `FLEET_READ_ONLY_STEP_LABELS` label with no matching site, and zero read-only sites across the fleet.
- [X] T014 [US3] Add the nine fixtures from `contracts/gate-93-check-4c.md` to the self-test, one per failure branch. Update the existing `_inline_fixture` default (`Bash(gh api:*)`) and the 4b "gh left alone" case, which encode the old behaviour.
- [X] T015 [US3] Add mutations to the self-test that restore `Bash(gh:*)` in `watchdog.yml`'s `watchdog.diagnose` site and `Bash(gh api:*)` in `auto-update-spec-kit.yml`'s inline list, on copies of the real files. The gate must fail on each.
- [X] T016 [US3] Run `python .github/scripts/verify-issue-context-single-home.py --self-test`, then `python .github/scripts/run-local-gates.py`. Confirm the gate is invoked the same way locally as in `lint-workflows.yml`.

**Checkpoint**: A regression of either grant fails the PR-time suite.

---

## Phase 6: User Story 4 - The record stops teaching the old grant (Priority: P2)

**Goal**: Docs and live contracts match the shipped lists, with one canonical rationale home.

**Independent Test**: Grep for `Bash(gh:*)` and `Bash(gh api:*)` in docs and contracts. Each survivor is labelled historical.

- [X] T017 [US4] In `docs/agent-friendly-workflows.md`, replace the `--allowedTools "Read,Grep,Bash(gh:*)"` read-only example with a list that cannot write. Make this section the single canonical rationale (FR-017): `gh` reaches remote writes, local file writes, and arbitrary execution via `gh alias set` / `gh extension install`, and the rule is total rather than per-subcommand.
- [X] T018 [P] [US4] Update `specs/010-reusable-pipeline/contracts/stage-interfaces.md`: the per-stage table (~line 339) and the `gh api` disposition paragraph (~line 293). State the new lists and point at the canonical home instead of restating the rationale.
- [X] T019 [P] [US4] Update the diagnose `--allowedTools` record in `specs/015-pipeline-watchdog/contracts/watchdog-workflow.md` (~line 81) to match the shipped list, and add the staged job-log files.
- [X] T020 [P] [US4] Update the evaluate-path `--allowedTools` record in `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md` (~line 104).
- [X] T021 [P] [US4] Rewrite the "pre-existing, wider `Bash(gh:*)` grant … untouched by this policy" paragraph in `specs/051-read-only-inspection-policy/contracts/inspection-policy.md` in the past tense, with a pointer to the canonical home.
- [X] T022 [US4] Add a "single home" assertion for the rationale (per research D6) to the nearest existing gate: the rationale's distinguishing sentence must occur in exactly one file. If no cheap deterministic form exists, record why in the PR description instead.

**Checkpoint**: SC-006 and SC-007 hold.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T023 Grep `.github/` and `docs/` for remaining `Bash(gh:*)`, `Bash(gh api:*)`, and prompt text that coaches `gh` on read-only agents (SC-001, SC-006).
- [X] T024 Run `python .github/scripts/run-local-gates.py` clean, then walk `quickstart.md`.
- [ ] T025 Post-merge proof (hand to the maintainer, since the merge needs the `workflow` scope): re-drive one watchdog run with `gh workflow run` and record the schema-valid verdict with no denied-tool event (SC-004). Record one auto-update evaluation returning an outcome from the staged release notes (SC-005). Record a simulated fetch failure ending in `outcome:"failed"` and a verdict naming job logs (SC-008).

---

## Dependencies & Execution Order

- Setup → Foundational (T003, T004) → US1.
- US1 and US2 are independent of each other. Both must land before US3, whose gate would otherwise fail the clean tree.
- US4 is independent of US1 and US2, but T018-T021 should state the final lists, so run it after them.
- T004 and T005-T007 all edit `watchdog.yml`, so keep them sequential. T009 can run in parallel with US1 work (a different file).

### Parallel Opportunities

- T002 alongside T001.
- T009 alongside T005-T008.
- T018-T021 together (different files).

## Implementation Strategy

- **MVP**: Phases 1-3 (US1). This removes the exposure the issue was filed for.
- **Then** US2, then US3 (the guard that keeps both from regressing), then US4.
- Keep concurrent local agents to two (CLAUDE.md usage-window rule). Every fix PR gets a code review. Run `spec-cross-reference` on the review, since the changed files are referenced by specs.
- Out-of-scope findings go on the Maintenance backlog issue, not new issues.

## Maintainer Feedback

- [X] T001 (PR #991 comment by charlesguse) Run `python .github/scripts/run-local-gates.py` on the branch and record the baseline result. The rebuilt implement image (#996) now includes PyYAML (#989).
- [X] T008 (PR #991 comment) Run `python .github/scripts/run-local-gates.py` and fix any workflow-comment or gate fallout from T004-T007.
- [X] T016 (PR #991 comment) Run `python .github/scripts/verify-issue-context-single-home.py --self-test`, then `python .github/scripts/run-local-gates.py`. Confirm the gate is invoked the same way locally as in `lint-workflows.yml`.
- [X] T022 (PR #991 comment) Add a single-home assertion for the rationale (research D6) to the nearest existing gate. The rationale's distinguishing sentence must occur in exactly one file. If no cheap deterministic form exists, record why in the PR description.
- [X] T024 (PR #991 comment) Run `python .github/scripts/run-local-gates.py` clean, then walk `quickstart.md`.
- T025 stays a post-merge maintainer step and is not part of this change.

## Phase 8: Convergence

- [X] T026 Update the live contract `specs/101-read-only-gh-grants/contracts/diagnose-staged-logs.md` (its "Helper" heading, line 6): the fetch now lives in the published composite `.github/actions/wing-commander-fetch-job-logs/action.yml` (its own step, because Gate 12 forbids `gh` calls in `_shared/` scripts and Gate 60 forbids a published stage resolving `_shared/`), and the callers read its `result` output instead of the helper's last stdout line, per FR-018 (contracts are live) (partial)

## Phase 9: Review Fixes

- [X] T027 (code review of PR #991) Make an unreadable job listing a gather failure (FR-019). `Stage failed-job logs` in `.github/workflows/watchdog.yml` now checks the `jq` read that picks the failed jobs, and records `outcome:"failed"` with reason `jobs-unreadable` when a non-empty `jobs.json` is truncated or is not an array of objects (`{}`, `[null]`). The helper stays the one place that decides what a readable listing is. Before, that read failed silently inside the loop header and left the status at `ok`. `.github/actions/wing-commander-fetch-job-logs/action.yml` no longer turns a body `jq` cannot parse (exit status 0 from `gh`) into `[]` and `ok`; it reports `failed`/`jobs-list`, and it writes `jobs.json` through a temp file so no caller reads a half-written one. A failed move into place is also `failed`, and a `jobs.json` from an earlier run is removed first. The reason is written before the `[]`, so a helper that dies between the two still reads as failed. Each job log is also read into a temp file and moved into place. A helper that failed without naming a log-read failure (it died, or could not write its reason) makes the staging status `failed` with reason `fetch-incomplete`, unless a more specific reason applies. The collector's reads of `jobs.json` and a job log now reassign on failure, so under the runner's `bash -e` a missing file is recorded as a failed read instead of ending the step. `verify-gate-19.py`'s step-summary scenarios now plant the skipped or cancelled sibling's log, so the collector's own per-job guard is still proven. Covered by the staging and collector scenarios and the staging mutations in `.github/scripts/verify-sentinel-collector.py`, and recorded in the live contract's failure table.
- [X] T028 (code review of PR #991) Check whether `collect-step-summary` reads a different directory than the helper writes in `container:` jobs. It does not. The helper receives `${{ runner.temp }}/cs-job-logs` as a leading `with:` value and reads it only through its step's `env:` (`OUT_DIR`), where the runner translates a leading host path to the container mount. That is the rule from #965 that Gate 43's `case_container_jobs_use_in_job_paths` enforces, and it is the same path as the collector's `$RUNNER_TEMP/cs-job-logs`. No change.
- [X] T029 (code review of PR #991) Check whether FR-020 requires staging logs for `cancelled` and `timed_out` jobs. It does not, so the `failure` filter stays. FR-018 scopes staging to "the failed jobs' logs". FR-020 requires diagnose to say which evidence it could not gather, not to gather more of it, and the prompt already requires that through the status file and the untrusted-collectors file. Fetching `cancelled` jobs would also go against spec 024 FR-004/FR-005, which the shared helper follows by skipping them. A job cancelled before it started has no log, so fetching it would turn a legitimate absence into a `log-read` gather failure on every cancelled run.

## Review Gate Round 1 Findings

- [X] Review finding: gh-grant gate misses wrapper spellings such as env gh or GH_TOKEN=x gh

  Check 4b only inspects the first whitespace token of a Bash grant, so Bash(env gh api:*), Bash(command gh:*) and similar grants for a read-only agent pass the gate.

  - .github/scripts/verify-issue-context-single-home.py

  Detail: Around line 456.

- [X] Review finding: Live contract still says the token comes from ACTIONS_TOKEN

  The diagnose-staged-logs contract says the token is passed from ACTIONS_TOKEN, but this PR removed ACTIONS_TOKEN from collect-step-summary and the callers now pass github.token as the token: input. Live contracts are fixed like code.

  - specs/101-read-only-gh-grants/contracts/diagnose-staged-logs.md

  Detail: Around line 2357 of the diff.

## Review Gate Round 2 Findings

- [X] Review finding: Fetch helper downloads logs for every job, not just failed ones

  wing-commander-fetch-job-logs fetches every non-skipped, non-cancelled job's log, though diagnose only uses failure jobs; this wastes time, can spend the single retry on an irrelevant job, and lets an irrelevant 404 mark the whole read failed.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: Needs a caller-supplied job filter or conclusion list; all logs also remain readable under RUNNER_TEMP/dj-fetch.

- [X] Review finding: Empty log body now treated as failed read

  The helper treats an empty log (! -s) as log-read failure, so timed_out/neutral/never-started jobs returning HTTP 200 with an empty body set result=failed and produce spurious untrusted-collector caveats.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: The old collector treated an rc=0 empty log as nothing to scan.

- [X] Review finding: gh-grant detector is overbroad

  The detector flags any whitespace token whose basename is gh, not just the command word, so grants like Bash(ls docs/gh:*) or Bash(echo gh:*) are false positives.

  - .github/scripts/verify-issue-context-single-home.py

  Detail: It should match the command word after skipping env, command and VAR=x prefixes.

- [X] Review finding: Shadow gate no-gh rule only matches Bash(gh prefix

  The shadow gate misses Bash(/usr/bin/gh ...), Bash(env gh ...) and Bash(GH_TOKEN=x gh ...) because it requires gh immediately after Bash(.

  - .github/scripts/verify-diagnose-shadow-acts-on-nothing.py

  Detail: Spec 101's total rule then rests entirely on Gate 93's detector.

- [X] Review finding: repo_files silently falls back to os.walk

  When git fails (for example dubious ownership), repo_files falls back to os.walk with no report, which includes the untracked pipeline checkout the module exists to exclude.

  - .github/scripts/wc_repo_files.py

  Detail: This brings back the gate failures behind #808, #822 and #823.

- [X] Review finding: _glob_has_match re-lists repo on every call and changes root semantics

  Each call spawns two git subprocesses with no cache, and a root that is not the repo top now yields every on-disk file instead of tracked files relative to root.

  - .github/scripts/verify-stage-tool-lists.py

- [X] Review finding: verify-gate-19 runs the fetch helper without step_shell

  run_stepsum_one calls run_step without shell=step_shell(...), so the helper is not run under the real composite's bash -e, and it re-imports yaml and re-parses action.yml for every scenario.

  - .github/scripts/verify-gate-19.py

  Detail: verify-sentinel-collector.py passes step_shell(FETCH_ACTION, FETCH_STEP).

- [X] Review finding: run_collector env lacks GITHUB_REPOSITORY and PATH setup

  run_collector no longer sets the GITHUB_REPOSITORY and PATH stubs that run_one added, so the test environment differs from the real step's, which runs under set -u.

  - .github/scripts/verify-sentinel-collector.py

  Detail: A mutation can read as caught for the wrong reason.

- [X] Review finding: Collector and diagnose disagree on the same helper result

  If the helper returns failed/log-read because of a non-failure job and all failure jobs are staged, diagnose reports ok and does not add job-logs to the untrusted collectors, while the collector records the read as failed.

  - .github/workflows/watchdog.yml

- [X] Review finding: Check 6 paths filter too narrow for repo-wide scan (no change: check 6's docstring records the choice -- listing every live file would run the whole suite on every PR, and a copy outside the filter is caught by the push to main and the daily schedule; the owner may overrule)

  Check 6 scans every live tracked text file, but the pull_request paths filter lists only docs/agent-friendly-workflows.md, so a pasted duplicate elsewhere does not fail the PR and turns main red later.

  - .github/workflows/lint-workflows.yml

  Detail: This is the Gate 124 failure mode CLAUDE.md warns about.

## Review Gate Round 3 Findings

- [X] Review finding: Empty-but-successful job log reported as log-read failure

  The fetch helper writes no file for an empty log body, but the staging loop in watchdog.yml treats a missing or empty log as outcome=failed/log-read and marks job-logs untrusted, so timed-out or runner-lost jobs are misreported as unreadable.

  - .github/workflows/watchdog.yml
  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: watchdog.yml ~line 2275

- [X] Review finding: Single retry budget shared across all jobs in fetch-job-logs

  `retried` is set once by the first failing job, so later jobs hitting the same log-lag get no retry and the whole result is marked failed.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: ~line 108

- [X] Review finding: Stale <id>.log files in out-dir are not cleared

  Only jobs.json and reason.txt are removed up front, so a pre-existing <id>.log can be read as current evidence by callers that test only for file existence, contradicting the header's 'a log file that exists is always real evidence'.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: ~line 81

- [X] Review finding: _grants_gh detector bypassed by option-taking wrappers and other launchers

  Tokens starting with '-' are skipped and the next token is taken as the command word, so `env -u X gh` or `sudo -u root gh` miss the gh grant, and launchers such as xargs, timeout and bash -c are not in _GH_WRAPPERS, so the shadow gate can pass while holding a gh grant.

  - .github/scripts/verify-diagnose-shadow-acts-on-nothing.py

  Detail: ~line 256

- [X] Review finding: Command-word/wrapper detection duplicated across two gates

  verify-issue-context-single-home.py re-implements _command_word and GRANT_WRAPPER_WORDS separately from _grants_gh and _GH_WRAPPERS in verify-diagnose-shadow-acts-on-nothing.py, against the 'shared logic has exactly one home' rule.

  - .github/scripts/verify-issue-context-single-home.py
  - .github/scripts/verify-diagnose-shadow-acts-on-nothing.py

  Detail: ~line 520

- [X] Review finding: repo_files now raises where callers used to fall back to disk walk

  When git cannot answer in a root with a .git (dubious ownership or git missing), repo_files raises RuntimeError, and verify-agent-push-credential-helper.py and verify-stage-tool-lists.py do not catch it, so they crash with a traceback instead of giving a gate verdict.

  - .github/scripts/wc_repo_files.py

  Detail: ~line 2057

- [X] Review finding: gate-19 harness runs the fetch helper without a sleep stub

  run_stepsum_one runs the real helper under a stub gh without stubbing sleep, so each scenario with a failing log read waits 10 seconds on the retry and slows the PR gate suite.

  - .github/scripts/verify-gate-19.py

  Detail: ~line 376

- [X] Review finding: Unfiltered fetch includes in-progress/queued jobs whose logs 404

  With empty `conclusions`, only skipped and cancelled are excluded, so a job with a null conclusion has its log fetched, the fetch 404s and the whole result is marked failed, which the shared helper's contract now makes look intended.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

  Detail: ~line 133

- [X] Review finding: Diagnose log fetch limited to conclusion=failure drops timed_out/startup_failure jobs

  The diagnose staging uses `conclusions: failure`, so timed-out or startup-failure jobs get no staged log yet the status reports outcome=ok, silently removing log access the agent previously had.

  - .github/workflows/watchdog.yml

  Detail: ~line 2232

## Review Gate Round 4 Findings

- [X] Review finding: Per-job log retry sleep multiplies on systematic failure

  The fetch-job-logs helper retries with a 10s sleep per job, so a token that gets a 403 on every log costs N x 10s and can hit the collect job timeout; the removed collector comment said the retry was once per step for this reason.

  - .github/actions/wing-commander-fetch-job-logs/action.yml

- [X] Review finding: Gate 93 check 6 does not catch RuntimeError from repo_files

  check_gh_rationale_home reaches repo_files through _live_text_files without catching RuntimeError, so an unreadable git root produces a traceback instead of a FAIL verdict. The other two callers do catch it.

  - .github/scripts/verify-issue-context-single-home.py

- [X] Review finding: gh-grant detector misses launcher and interpreter grants that can run gh

  grants_gh only flags grants that name gh as a token, so Bash(env:*), Bash(xargs:*), Bash(bash:*), Bash(python3 -c:*) and 'echo x; gh api' pass, and LAUNCHER_WORDS omits su, runuser, nsenter, systemd-run, taskset, numactl, tmux, ssh and perl.

  - .github/scripts/wc_gh_grant.py

- [X] Review finding: grants_gh splits on first colon and misses env assignments containing a colon

  Bash(PATH=/a:/b gh api:*) is cut to the command PATH=/a, whose tokens are only an assignment, so command_word returns an empty string and the gh grant is not flagged.

  - .github/scripts/wc_gh_grant.py

- [X] Review finding: _listing cache contradicts its docstring for git-init fixtures

  _listing caches the tracked-file list per real working tree, but the docstring says a fixture directory is listed afresh. A git-init fixture takes the cached path and returns a stale listing after git add.

  - .github/scripts/verify-stage-tool-lists.py

- [X] Review finding: _glob_has_match no longer limited to tracked files for a subdirectory root

  When root is not the repo top and has no .git, repo_files falls back to os.walk, so untracked leftovers can satisfy a stale wildcard grant. The old code ran git ls-files and returned tracked files only.

  - .github/scripts/verify-stage-tool-lists.py

- [X] Review finding: Watchdog log status is ok with file null for a failed job whose log is empty

  Diagnose stages logs only for failed jobs. A timed_out or startup_failure job with an empty 200 body records outcome ok and file null, and job-logs is not marked untrusted, so the agent cannot tell a missing log from an unneeded one.

  - .github/workflows/watchdog.yml

- [X] Review finding: Shadow denies Bash(gh:*) but the Diagnose agent does not, and no gate checks the deny side

  Only the shadow's disallowed list includes Bash(gh:*). A gh grant added to Diagnose through extra-allowed-tools or a later edit is not denied, and Gate 93 4b reads only shipped defaults.

  - .github/workflows/watchdog.yml

- [X] Review finding: Check 6 of Gate 93 is outside the PR path filter, so it can turn main red after merge

  Check 6 scans every live tracked text file but only the home document is in the PR paths filter, so a pasted duplicate elsewhere passes the PR and fails on the push to main or the daily run.

  - .github/scripts/verify-issue-context-single-home.py

- [X] Review finding: Jobs-list failure discards gh stderr, so the failure is not attributable

  The gh api --paginate jobs listing sends stderr to /dev/null, so a 403, 404 or rate limit is recorded only as reason jobs-list with no diagnostic. That undercuts the loud, attributable failure that FR-019 and FR-020 promise.

  - .github/actions/wing-commander-fetch-job-logs/action.yml
