# Data Model: The Proof List

All structures are in memory (JSON in fixtures, the SC-001 corpus and the section artifact). The only durable output is the section of the "Board status" issue, which `wc_board_status.py publish` writes from the artifact (research D7).

## Entry
How each field is derived is in research D6's "Reused homes" table.

| Field | Type | Notes |
|---|---|---|
| `sha` | string | first-parent commit on the default branch |
| `merged_at` | UTC timestamp | committer time on the first-parent line (FR-001) |
| `pr` | int \| null | the PR from `commits/{sha}/pulls` whose `merge_commit_sha` equals `sha`; null for a direct push |
| `named_issues` | list of {`number`, `how`} | `how` ∈ `closes` (`closingIssuesReferences`), `closes-commit` (a closing keyword in the merge commit's message, confirmed by the issue's `closed` event for that commit; research D6), `board-item` (`pr_issue()`), `backlog-line` (`pr_line()`), `lifecycle`. Read for every entry with a PR, state 1 included, because shared-issue detection counts every entry's PR (research D6) |
| `lifecycle_issue` | int \| null | final PR only (title `Finalize: … (#N)`): `.issue` of the merge tree's `specs/<slug>/spec-meta.json`, cross-checked against the title |
| `changed_paths` | string[] | `diff_name_list(sha^1, sha)`; empty is allowed |
| `needs_run`, `needs_reason` | bool, string | `needs_run, needs_reason = actions_only(changed_paths)`; the function returns a pair, so the pair itself is never used as a condition |
| `reaching` | ReachingWorkflow[] | empty when `needs_run` is false |
| `state` | 1..5 | computed |

## ReachingWorkflow
`path`, `reached_via` (`scan` \| `mention` \| `nightly-e2e`), `runs_of_its_own` (bool), all computed from the entry's own tree (research D2, D3, D12). Reach is per workflow, not per job.

A workflow whose only trigger is `workflow_call` is dropped from `reaching` when an in-repository caller that reaches the same path is present. One with no such caller stays, marked `runs_of_its_own: false`, and the report shows it as "no runs of its own" (research D4).

## FinishedRun
`workflow`, `run_id`, `event`, `status` (always `completed`), `conclusion`, `head_sha`, `run_started_at`, `html_url`. A run of a reaching workflow counts for an entry when the entry's merge is an ancestor of `head_sha`. A run that does not count is simply not counted; it is set apart only under SetApartRun's two cases.

## NamedRun
A run a comment names, read by id (`actions/runs/{id}`), cached per build:

| Field | Notes |
|---|---|
| `url` | as written in the comment, job links included |
| `repository` | this repository, or another (then `kind` is `foreign`, and nothing is read) |
| `run_id` | |
| `kind` | `found` \| `not_found` (404) \| `foreign` |
| `run_started_at`, `head_sha`, `status`, `conclusion` | when `found` |

A `found` named run qualifies for an entry when `run_started_at` is after `merged_at` and the merge is an ancestor of `head_sha`. It need not have finished and need not belong to a reaching workflow. Any API error other than a 404 is a failed read.

## RecordComment
`where` (`pr-issue-comment` \| `pr-review-comment` \| `pr-review` \| `issue N`), `comment_id`, `account`, `account_type` (`User` \| `Bot`), `posted_at`, `body` (raw; the pure half parses run links and the PR reference from it), `marker_step` (`proven` \| `other` \| `none`; an unparseable marker is `other`).

Qualification, for one entry, in order (FR-006, FR-007, FR-009; research D6):
1. `posted_at` is after `merged_at`, and the comment is on a place FR-006 names for that entry.
2. A marker is present: continue only if `marker_step == proven`. Otherwise it never counts.
3. No marker and `account_type == Bot`: it never counts.
4. On a shared issue (named by more than one entry's PR, any entry, state 1 included), the body names that entry's PR (`#N` with boundaries, or the PR URL).
5. At least one NamedRun in the body qualifies for that entry.

## SetApartRun
Exactly FR-013's two cases (research D5):
- `unresolvable`: a run of a reaching workflow, or a `found` named run, whose `head_sha` is absent from a complete history, and whose `run_started_at` is after the `merged_at` of an entry whose `reaching` includes its workflow (for a named run, of the entry whose comment names it). An unresolvable run that started before every such merge is not set apart (research D5);
- `not-this-repository`: a named run of `kind` `foreign` or `not_found`, named by a comment that passes steps 1-4 above.

Each is counted once across the window, de-duplicated by run id or URL, never per entry.

## State (first that fits)
1. `needs_run` is false: needs no run (`needs_reason` is kept for the fixtures).
2. At least one qualifying RecordComment, with or without a reaching workflow.
3. `reaching` is empty.
4. `reaching` is not empty, and no FinishedRun counts for the entry.
5. FinishedRuns count, and no comment qualifies.

Invariants: exactly one state per entry; the same inputs give the same state; no field encodes a verdict (FR-010). A run's conclusion never changes a state.

## Report (`proof-list-section.json`, the artifact)
| Field | Notes |
|---|---|
| `schema` | `1` |
| `built_at` | UTC ISO; the build's own time, which sets the window (FR-011) |
| `window` | {`start`, `end`}, `start < merged_at ≤ end` (research D10) |
| `head_sha` | the default-branch commit the build ran on |
| `counts` | {`1`..`5`} |
| `aged_out` | count of commits in state 4 or 5 in the 24 hours before the window start |
| `set_apart` | SetApartRun count |
| `full` | the section's Markdown with full detail |
| `names_only` | the section's Markdown with each entry and only its reaching workflows' names, plus the shortened line |

`wc_proof_list.py` renders both forms (the renderer's one home). The writer picks one, or shows a notice (research D8, D17).

## Section status (decided by the writer, `wc_board_status.proof_list_snapshot()`)
`status` ∈ `built` \| `paused` \| `failed` \| `never` \| `unreadable`, `built_at` (when `built`), `last_good_at` (UTC ISO, `never`, or `unknown` when the history could not be read), `form` (`full` \| `names-only` \| none). The rules are in research D17.

## SC-001 corpus (`.github/scripts/fixtures/proof-list/sc001/corpus.json`)
The pure half's input, written by `wc_proof_list.py capture` (research D13):
- `window` {`start`: `2026-10-15T00:00:00Z`, `end`: `2026-11-17T00:00:00Z`} as UTC instants (SC-001's "2026-10-15 to 2026-11-16", last day included), `as_of`, `repository`. The replay passes `start` and `end` to the pure half as they are (research D10);
- `entries`: every first-parent commit in the window and in the aged-out day before it (`start − 24h < merge ≤ start`), with the Entry fields and `reaching` computed at capture time from each entry's own tree;
- `runs`: per reaching workflow with runs of its own, the FinishedRun fields of every completed run created at or after the aged-out day's start (`start − 24h`, research D4), plus `contains` (the entry SHAs that are ancestors of its `head_sha`) and `resolvable` (bool);
- `named_runs`: NamedRun records keyed by URL, with `contains` and `resolvable` as above;
- `comments`: RecordComment records per place read, posted no later than `as_of`, with each body reduced to its lines carrying a run link, a PR reference or the board item marker (other lines become `…`) and then scrubbed of any private project name.

The replay needs neither git nor `gh`.

## SC-001 expected file (`.github/scripts/fixtures/proof-list/sc001/expected.json`)
Built by the `[maintainer]` session from the saved 2026-11-16 lookup, held by the owner's sessions (research D13):
- `source`: "the saved 2026-11-16 lookup, held by the owner's sessions";
- `proofs`: the PR numbers of the lookup's 10 hand-written proofs (expected in state 2);
- `listed`: the PR numbers of the lookup's 21 merges with nothing found (expected in state 4 or 5): the 14 with nothing found, the 4 Spec Kit bumps, #1051, #1081 and #1082;
- `expected_differences`: a list of {`pr`, `sha`, `half` (`proofs` \| `listed`), `expected_state`, `actual_state`, `reason`, `note`}, where `reason` ∈ `own-tree` \| `FR-005` \| `FR-006-shared-issue` \| `FR-013-set-apart`.

The replay fails on any entry of `proofs` not in state 2, any entry of `listed` not in state 4 or 5, and any other entry in state 4 or 5, unless that exact difference is on the list. An entry on the list that no longer differs also fails, so the list cannot go stale.
