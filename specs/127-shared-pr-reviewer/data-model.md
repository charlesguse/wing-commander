# Data Model: Shared PR Reviewer (127)

Layer: consuming instrument. All structures are JSON; the record lives in an HTML-comment marker (research D1).

## ReviewRequest (workflow input)
| Field | Type | Rule |
|---|---|---|
| pr | int | required; PR must exist and be open or closed/merged |
| kind | enum `fix` (accepted values: `fix`,`spec`,`plan`,`final`,`board-fix`) | only `fix`/`board-fix`-shaped session fix PRs run; other kinds refused (FR-001). Derived by code from the PR's head branch/labels, never from agent output |
| purpose_source | `{type: issue\|backlog\|run, ref}` or null | resolved by code (research D10) |
| requested_by | string | dispatching actor |
| dismissals | list of `{id, reason}` | each id must be open at round start, else dropped and noted |

## Finding (checked)
| Field | Type | Rule |
|---|---|---|
| id | `F<round>-<n>` | assigned by code; kept from a cited, existing earlier id (FR-016) |
| fingerprint | string | from `wc_review_finding_fingerprint.py`; not an identity input |
| title, claim | string | agent text, untrusted |
| file, line, line_end | string, int, int | anchor |
| failing_case | `{state, wrong_result}` | required for breakage claims; absent → dismissed |
| cites | id or null | agent-proposed |
| possible_repeat_of | id or null | code-set on overlap without cite |
| status | `upheld`/`dismissed`/`reopened`/`resolved` | FR-015 table |
| reason | string | required for dismissed/reopened/resolved |
| note | string or null | e.g. `not re-checked: code-run results missing` |
| in_scope, reachable | bool | reported by checking job |
| blocking | bool | code: open ∧ in_scope ∧ reachable (FR-013); `non_blocking_rule` names why not |

Transitions (code-enforced): new→upheld/dismissed; dismissed|resolved→reopened (checker upholds a showing); upheld|reopened→resolved/unchanged (re-check; missing code-run → unchanged); upheld|reopened→dismissed (requester, via confirmed record). Anything else is rejected and logged.

## PurposeAnswers
`problem_real`, `change_fixes`, `check_fails_without_fix`: each `positive`/`negative`/`not_determinable`, with a short basis. A reserved `requirements_unmet` slot (FR-009) is allowed and null.

## CodeRunResults (staged data)
`{status: staged|missing, named_check: {exit, output_tail}|null, gate_suite: {exit, output_tail}|null}`. Non-zero exits are data. `missing` only when nothing could be staged.

## RoundRecord (marker `wing-commander-shared-review-round`)
| Field | Rule |
|---|---|
| schema | 1 |
| reviewer | `shared-pr-reviewer` (keeps spec-116 readers out; the marker name already does) |
| pr_kind | `fix` |
| round | int ≥ 1, counting confirmed records |
| head_sha | commit actually reviewed |
| verdict | `clean`/`findings`/`undetermined`/`incomplete` (FR-014) |
| pr_state | open/closed/merged at posting |
| purpose | `{source, version_used}` and PurposeAnswers |
| open_set | findings open after the round, full |
| findings | every other finding evaluated or dismissed this round |
| dismissals | requester dismissals carried |
| reviewer_commit | default-branch commit the run executed from |
| run_id | Actions run id |
Size: capped like `MAX_RECORD_CHARS`; the open set is never truncated, other findings are truncated first, with a count.

## HandoffRecord (marker kind `handoff`)
`{schema, reviewer, pr, rounds_used, budget, open_set, run_id, reviewer_commit}`; no `verdict`.

## Derived (code, not stored)
- ConfirmedRecords: records whose `run_id` passes `confirm_record` (research D5).
- OpenSet: fold of confirmed records in round order.
- Verdict: `compute_verdict(agent_ok, open_set, answers, code_run)`.
- Budget used: count of confirmed round records.
