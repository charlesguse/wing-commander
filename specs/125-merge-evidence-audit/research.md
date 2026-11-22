# Research: The Merge Evidence Audit

Every decision below resolves a choice the spec left to the plan ("the store's form is a plan decision", FR-018) or fixes how the spec's "call it, never copy" rule (FR-008) is met. The spec carries no `[NEEDS CLARIFICATION]` marker: its three clarifications are recorded in spec.md.

## D1 — Verdict store: a cumulative ledger artifact, one writer

- **Decision**: The store is an Actions artifact named `merge-evidence-ledger` holding one JSON file, `ledger.json`: a map keyed `"<pr>@<head sha>"` to a verdict record (data-model.md). Each hourly run (1) downloads the ledger of the newest unexpired `merge-evidence-ledger` artifact that its own workflow uploaded on the default branch, found by name through the Actions artifacts API (audit and paused runs upload none, so the latest successful run may hold no ledger; #1173 round 3, finding 5), (2) computes a verdict for every open PR into `main`, (3) replaces the entry for each `(pr, head)` it computed, (4) prunes entries per D2, (5) uploads the result with `overwrite: true`, `retention-days: 90`. The hourly job runs under the concurrency group `wing-commander-merge-evidence-ledger` with `cancel-in-progress: false`, so there is exactly one writer at a time.
- **Rationale**: FR-018 needs a store the workflow's own runs read and write, not an issue and not the run summary (`gh` cannot read it). A `gh run download` of the run that uploaded the newest ledger artifact is how a session reads the current verdict (FR-018) and how the audit reads records. The artifact is re-uploaded hourly, so the 90-day maximum retention never expires a live record; `gh` and `actions: read` are all a reader needs. No write permission beyond the default artifact upload is needed, and nothing touches a commit's checks or statuses (FR-017).
- **Alternatives rejected**:
  - *One artifact per run, audit downloads all*: about 720 artifacts a window; 720 downloads a day against the API pool shared with board-status.
  - *An orphan branch or a file on a data branch*: a push, which FR-017 forbids, and it needs `contents: write`.
  - *A repository variable or a gist*: a variable needs a PAT-level write and the owner's scope; a gist is an outside service.
  - *An issue*: FR-018 forbids it, and a comment on some issues starts a pipeline run.
- **Failure mode, accepted and shown**: if an upload fails or a run is cancelled, the next run starts from the last good ledger and recomputes every open PR, so only a merge between the lost run and the next one loses its record, and the audit marks that merge *reconstructed* (FR-013, FR-016). If no ledger can be found (first run, expiry), the run starts an empty ledger and says so in its log; it never fails on a missing ledger, and it fails loudly on a ledger that is present but cannot be parsed.

## D2 — Retention of ledger entries

- **Decision**: An entry is kept while its PR is open, and for 31 days after the PR's merge (the window plus one day, so the day's audit never loses the entry it marks *recorded*). An entry for a PR closed without a merge is dropped after 7 days. An entry whose PR cannot be found is kept and listed in the run log.
- **Rationale**: FR-011 requires the record to survive as long as its merge is inside the 30-day window. The ledger stays small: tens of open PRs, about 50 merges, one record per head (at most a few KB each).
- **Alternative rejected**: keeping every head forever — unbounded growth, no reader.

## D3 — Triggers, workflow shape and gating

- **Decision**: One repository-only workflow, `.github/workflows/wing-commander-merge-evidence.yml`, with `schedule` entries `7 * * * *` (hourly verdicts, FR-016) and `41 5 * * *` (daily audit, before proof-list's 06:19 and board-status's 07:17) and `workflow_dispatch` with one input `job` (`verdicts` | `audit` | `both`, default `both`). Two jobs, `verdicts` and `audit`, selected by a first-step condition on the schedule string or the input; the audit job has its own concurrency group `wing-commander-merge-evidence-audit`.
- **Steps (both jobs)**: (1) checkout of the default branch (`ref: ${{ github.event.repository.default_branch }}`), `persist-credentials: false`, so a refused dispatch from another branch runs only the default branch's code; (2) the `wing-commander-watch-guard` composite, which refuses a run whose ref is not the default branch before anything reads a pull request, check or artifact (FR-021), then reads `vars.WING_COMMANDER_MERGE_EVIDENCE_PAUSED` by calling `wc_board_status._switch_on` (trimmed, case-folded `true`) (FR-022); (3) run the script; (4) upload. The checkout comes first because a local composite and the Python switch test both run from it (#1173 round 3, finding 8: one home for the refusal and the pause test). Steps 3-4 are gated on the pause output and the job-select output under the default `success()`, with no `always()` and no `!cancelled()`, exactly as `wing-commander-proof-list.yml` is — so a failed read stops the upload and the ledger keeps its last good state.
- **Permissions**: `contents: read`, `actions: read`, `issues: read`, `pull-requests: read`, `checks: read`, `statuses: read`. No App token, no agent, no dispatch, no write (FR-017, FR-020).
- **Rationale**: Same proven shape as spec 124's workflow. The hourly cron is not chained to CI finishing (FR-016); a PR merged within the hour is reconstructed.
- **Cost**: an hourly job of about one minute: about 720 Actions minutes a month for the verdicts plus about 30 for the audit; this is the cost the spec's clarification accepted.
- **Alternative rejected**: `pull_request_target` / `check_suite` triggers — an Actions-token event starts no run and `check_suite` does not fire for Actions-created suites (spec Assumptions).

## D4 — Reuse, not copy (FR-008)

- **Decision**: A new `.github/scripts/wc_merge_evidence.py` holds the pure half (kind assignment, condition list, as-of-merge filter, audit and report renderers) and the runtime half (`collect`, `verdicts`, `audit`). It imports, and does not re-implement:
  - `board_merge.snapshot_complete`, `eligible_fix_class`, `_attributed_to_auto_update`, `bump_records`, `latest_record_at_head`, `verification_run_confirms`, `fetch_snapshot`, `_fetch_verification_run`, `MERGE_OUTCOME_MARKER`, `BUMP_BRANCH_RE`, `FIX_BRANCH_RE` for the board-loop fix PR and Spec Kit bump kinds;
  - `board_readiness._checks_green` and `_gate_suite_green` for the board-loop "every status counts" rule;
  - `lifecycle_merge_preconditions` for the final-PR rule (which leaves the gate's own status out) and its unresolved-human-review test.
  Underscore-prefixed names are promoted to public aliases in the same change (a rename plus an alias, no behaviour change) so a gate can fail a copy by name; the existing gates (`verify-board-merge.py`, `verify-lifecycle-merge-preconditions.py`) keep passing unchanged.
- **Single-home gate**: a new unnumbered gate `verify-merge-evidence.py` (D9) parses `wc_merge_evidence.py` and fails when it defines a function whose name matches one of the reused homes, when it contains the literal terminal-state sets those homes own (`GREEN_STATES` members used as a membership test), or when it re-implements the `lint` / `workflow` name test of `_gate_suite_green`. The table of exempt names is a parameter, not a module-level mutable (Gate 124 forbids writes to `EXEMPT_*` names).
- **Where a rule cannot be called**: the condition of the nine-condition list that has no code today is the hold label of spec 119 (parked). It is a verdict-only condition, `no_hold_label`, reading the labels of the lifecycle issue from the snapshot; it is `met` when the label cannot be present because nothing applies it, and `not read` when the labels were not fetched. The spec's "call it once such code exists" is a task-level follow-up: the gate carries an `EXEMPT` entry naming spec 119's parked state and goes stale when merge-time code for the hold label exists.
- **Alternatives rejected**: copying the conditions into the new script (FR-008 forbids; this is the exact drift CLAUDE.md names); moving the conditions into a new shared module (a larger change to two live merge paths whose decisions FR-019 says must not change).

## D5 — "As of the merge" without changing the reused code

- **Decision**: The audit builds a *time-cut snapshot* and feeds it to the same reused functions. `cut_snapshot(snapshot, merged_at)` drops every `statusCheckRollup` entry whose `completedAt` (CheckRun) or `startedAt`/creation time (StatusContext) is later than `merged_at`, drops comments, reviews, and review-gate rounds created after it, and drops labels whose last `labeled` event is later. It is a pure function over the same fields `fetch_snapshot` already reads, so the reused evaluators need no change. A record whose timestamp cannot be read is treated as *after* the merge (left out), and the entry says so.
- **Rationale**: FR-012: "anything dated after it is left out"; stages started by the merge (the finalize/cleanup runs) must not turn a merge's checks red or green retroactively. The cut lives in one function with one fixture per kind of timestamp.
- **Check-run time source**: the PR's rollup carries `completedAt`; the audit reads the head commit's check runs and statuses with the REST `commits/{sha}/check-runs` and `/status`, paginating fully (an incomplete page makes the entry incomplete, FR-005).

## D6 — Reading the merge facts and unpaired commits

- **Decision**: The audit lists merged PRs into `main` by `gh api` search of closed PRs, `merged_at` within the window (paginated, any short page fails the run loudly). For each, `merge_commit_sha`, the PR's last head before merge (the `head.sha` of the PR at merge time, from `merged` event data: the `pull_request` object's `head.sha` after merge, which GitHub freezes at the last head), and `merged_by.login`. It then lists first-parent commits on `main` in the window (`git log --first-parent --since`, from a full-depth checkout, `fetch-depth: 0`) and removes each that is some merged PR's `merge_commit_sha`. The rest are unpaired (FR-014), with author and committer from the commit object. Squash commits are therefore not listed as unpaired (Edge Cases). A revert-and-reapply produces two merged PRs or two commits and so two entries.
- **Rationale**: The same first-parent window as spec 124's proof list; no new reading pattern.
- **Alternative rejected**: `commits/{sha}/pulls` per commit — about 50 extra calls and it misses PRs closed and reopened.

## D7 — Kind assignment (FR-002, FR-003)

- **Decision**: Order of tests, first match wins, with the deciding facts stored in the record: (1) bump: `board_merge` bump-shaped test (branch `BUMP_BRANCH_RE`, bump body marker, author attributed to the auto-update stage); (2) board loop fix PR: `board_merge.eligible_fix_class` facts (branch `FIX_BRANCH_RE` plus App authorship); (3) final PR: head branch matches `spec/[<P>/]<NNN-slug>` built from the repository's configured prefix variable defaults, with the base `main`; (4) spec PR: `spec-draft/[<P>/]<NNN-slug>`; (5) otherwise maintainer PR. The branch prefixes come from the same defaults the finalize and intake stages use (`WING_COMMANDER_*_BRANCH_PREFIX` variables, defaulting to the literals in the constitution); the script takes them as arguments from `vars.*` in the workflow, never hard-coded.
- **Rationale**: A fork PR whose head branch is named `spec/…` must not be judged a final PR: the final-PR test also requires the head repository to be this repository (the fork case in Edge Cases). A PR that fails that test falls through to maintainer PR.

## D8 — Records that count (FR-009, FR-010)

- **Decision**: One function, `counted_origin(record_source)`, returns `counted` only for: a comment authored by the pipeline's App login (`board_merge._is_app_user`), a `wc-bump-verification` record whose run `verification_run_confirms` accepts, a `lifecycle-review-gate` round written by an Actions run the API confirms, and (once #1142 exists) its round record under the same run-confirmation. Everything authored under a maintainer login is listed as `reported`. A record naming a commit other than the head is dropped by `latest_record_at_head` (the reused function), and the verdict names the commit it saw.
- **Maintainer PR / spec PR evidence**: until #1142 exists, the condition `review_round_record` is `unmet` with reason "no counted round record exists for this kind (#1142 not built)". The condition's reader is a stub that returns "none" and a gate fixture proves a maintainer-posted comment never flips it.

## D9 — Gates, wiring, replay

- **Decision**: One new gate `verify-merge-evidence.py`, wired as an unnumbered `lint-workflows.yml` step (as `verify-proof-list.py` and `verify-board-status.py` are; `wc_gate_registry.pr_time_gates()` derives the set and `verify-gate-wiring.py` fails an unwired one). It checks: every fixture case (kinds, each condition, incomplete snapshot, wrong-author record, stale-head record, no-checks, spec PR, as-of-merge cut, recorded vs reconstructed, unpaired commit, decision-record link, ledger replace, ledger prune), the single-home rule of D4, the workflow file's shape (checkout pinned to the default branch, then the `wing-commander-watch-guard` composite refusing a non-default ref and reading the pause switch, no `always()`/`!cancelled()`, permissions, schedules, no agent, no `gh pr merge|review|edit`, no `gh api -X POST|PUT|PATCH|DELETE`), the no-merge-job-reads-it rule (FR-019: neither `board-loop.yml` nor the review gate's merge job nor `board_merge.py`/`lifecycle_merge_preconditions.py` mentions the artifact name or the module), and the SC-003 replay.
- **SC-003 replay**: runs from a checked-in corpus and expected file with no `gh` or `git`, supplying the 2026-10-15 to 2026-11-16 window as a parameter (FR-012: the report never does). As in spec 124, the corpus comes from a `[maintainer]` capture against the saved lookup; until it lands the check reports "not yet captured" under an `EXEMPT_SC003_PENDING` entry citing #1143 (Gate 124: a cited issue must be open and the entry fails when stale).
- **Alternative rejected**: a numbered gate — numbers are allocated by hand and collide (#773).

## D10 — Publication in Board status (FR-018)

- **Decision**: The audit job uploads the artifact `merge-evidence-section` (7-day retention) holding the rendered section content (the audit of the window, and each open PR's latest verdict naming its head). `wc_board_status.py` gains `merge_evidence_snapshot()` beside `proof_list_snapshot()`, the same statuses (`built`, `paused`, `failed`, `never`, `unreadable`), a collapsed `<details>` section, a names-only shortened form when over `MAX_BODY_UNITS`, and a `SWITCH_ENV` entry for `WING_COMMANDER_MERGE_EVIDENCE_PAUSED`; `board-status.yml` gains that env line. The artifact name is one constant shared by the writer and checked by `verify-board-status.py` against the upload step.
- **Rationale**: Board status stays the issue's one writer; the workflow holds no write permission.
- **Open-PR verdicts in the daily section** are the ledger's entries as of the audit's own run, which reads the ledger artifact (read-only) and says when it was last written.

## D11 — Reading the current verdict with `gh` (FR-018, User Story 1)

- **Decision**: The `verdicts` job uploads the ledger only; there is no second artifact. The contract (contracts/merge-evidence-report.md) gives the two commands (`gh api .../actions/artifacts?name=merge-evidence-ledger` for the newest ledger's run, then `gh run download <id> -n merge-evidence-ledger`) and a `jq` filter. A reader must compare `head` with the PR's current `headRefOid`; the record names its head so a stale one is visible.
- **Rationale**: One reader recipe with no Board status dependency.

## D12 — Dispatch input and kill switch

- **Decision**: The dispatch has the one `job` input of D3 and no window, repository or date input (FR-012: "the report never supplies the window"). Switch: `WING_COMMANDER_MERGE_EVIDENCE_PAUSED`, added to `docs/setup.md` §3 and to the kill-switch tables of `docs/reference.md`; while set, the jobs write nothing, including no ledger upload.

## D13 — Documentation (FR-025)

- **Decision**: `docs/reference.md`: a row under "Housekeeping and observability"; "Schedules" (hourly :07, daily 05:41); "Kill switches"; the `board-status.yml` row; "Merge classes" (what the audit now records, per kind); "Known limits" (the session-merge limit now has a recorded-after-the-fact audit, and what stays unrecorded: a maintainer-account merge cannot be told from a session's, spec PRs show unmet while they have no checks, maintainer PRs are unmet until #1142). `docs/setup.md` §3 gets the variable row and README the repository-only workflow list.

## D14 — Limits carried openly

- A verdict is only as current as the last hourly run: the head it names is shown, never assumed current.
- The audit cannot tell a session's merge from the owner's (FR-003) and says so in the report header.
- The 30-day watching period (FR-024) is stated in the report header with its end date, computed from the day the workflow first writes a ledger entry (the ledger's oldest `computed_at`), not from a hard-coded date.
