# Data Model: Board Backlog Lines

## Maintenance backlog (resolved, not stored)

Resolved each run by `board_backlog_lines.resolve_backlog(open_issues, bot_login)`: exactly one open issue with label `disposition:tracking` and a title beginning "Maintenance backlog", authored by a maintainer association or the App. Zero or more than one → no line is taken; the reason is returned.

## Backlog line (parsed from the body)

| Field | Source | Notes |
|---|---|---|
| `index` | position among top-level checklist lines in the body as read | Order key (FR-004). |
| `checked` | `- [x]` vs `- [ ]` | Ticked lines are never candidates. |
| `text` | line text without the checkbox and without the annotation token | Untrusted data (FR-008). |
| `annotation` | optional trailing token `[wc:<id> <state> ...]` | See below. |
| `id` | from the token, else none | Unclaimed lines have none. |

Parsing rules (FR-005): only lines matching `^- \[( |x)\] ` at column 0 outside fenced blocks, outside blockquotes, and not indented (nested) are lines. Comments are never read.

### Candidate predicate

A line is a candidate iff unchecked and its annotation is absent. A line with any annotation (`in-progress`, `held`, `proposal`) is skipped; a maintainer clears a hold by deleting the token.

## Line annotation

Grammar: `[wc:<id> <state>( <detail>)?]` appended once at the end of the line.

| State | Meaning | Detail | Line checked? |
|---|---|---|---|
| `in-progress` | claimed; board holds it | `PR #N` once a fix PR exists | no |
| `held` | stalled with the `board:stalled` reason | reason text, sanitised, one line | no |
| `proposal` | routed spec-shaped | `#N` of the `spec-proposal` | no |
| `fixed` | fix PR merged | `by #PR` | yes |
| `evidence` | closed on deterministic triage evidence | quoted evidence | yes |

An optional suffix ` not-proven: <reason> [run](url)` follows `fixed` (FR-011).

Transitions (loop-authored): none → `in-progress` (claim) → `in-progress PR #N` (PR opened) → `fixed` | `held` | `proposal` | `evidence`. `held` → none (maintainer deletes). `fixed` + `not-proven` → `fixed` (later proof succeeds). A maintainer tick or deletion at any time → stand down (FR-016).

## Line id

`bl-` + 8 hex characters. Unique within the body. Matches `[a-z0-9-]{1,40}`.

## Line board state (comment on the backlog issue)

The existing board item marker, plus `line: <id>`. Existing fields (step, pr, branch, round, etc.) are unchanged; `issue` holds the backlog issue number. Readers filter by `line`; issue-path readers ignore markers that carry `line`. Only markers authored by the App are read (#555).

## Item descriptor (select job output)

`item_kind` (`issue`|`line`), `item_number` (issue number; the backlog issue for a line), `line_id`, `line_text`, `branch`, `pr_title`. For `item_kind == issue` the last three are the issue path's own values.

## Edit operation (helper input)

`{op: claim|progress|hold|proposal|tick-fixed|tick-evidence|note-proof, line_id, detail}` → pure `apply(body)` returning the new body or `None` (line missing, ticked, or id duplicated → stand down). Duplicate id present twice → stand down, write neither (spec Edge Cases).

## Switch and gate inputs

- `WING_COMMANDER_BOARD_BACKLOG_LINES`: exactly `true` to allow new claims.
- `WING_COMMANDER_BOARD_LOOP_PAUSED`: hard stop.
- Constitution Principle X text on the default branch must contain `Maintenance backlog line`.
