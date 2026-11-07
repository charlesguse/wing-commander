# Contract: `board_backlog_lines.py` and `board_backlog_edit.py`

Live contract: fixed like code, read by the gates `verify-board-backlog-lines.py` and `verify-board-backlog-edit.py`.

## `board_backlog_lines.py`

Pure functions (importable) plus a CLI that reads JSON on stdin and prints JSON on stdout. Exit 0 on a decision (including "refuse"), exit 2 on malformed input.

### `parse_lines(body) -> [Line]`
Returns candidate-shaped lines per data-model.md. Fenced blocks, blockquotes, indented and nested checkboxes are ignored.

### `select_line(body, *, claimed_ids) -> Line | None`
Topmost unchecked line with no annotation. `claimed_ids` is informational; an annotated line is skipped regardless.

### `resolve_backlog(open_issues, bot_login) -> (number | None, reason | None)`
FR-002. Ambiguity or an unmaintained author returns `(None, reason)`.

### `selection_gate(env) -> (ok, reason)`
`env` carries `backlog_lines_switch`, `loop_paused`, `constitution_text`. Refuses with a one-line reason when the switch is not exactly `true`, the loop is paused, or Principle X (`### X.` section) lacks `Maintenance backlog line`; `constitution_text = None` refuses (FR-025).

### `mint_id(body) -> str`
`bl-` + 8 hex; never an id already in `body`.

### `branch_for(issue, line_id) -> str`
`fix/<issue>-<line_id>`; asserts `FIX_BRANCH_RE` full match.

### `title_for(text, prefix="Fix: ") -> str`
Strips annotation, collapses whitespace, truncates with `…` so `len(prefix + text) <= 200`; never contains a closing keyword (see below).

### `closing_keyword_hits(title, body, commit_messages) -> [Hit]`
Case-insensitive `close[sd]?|fix(e[sd])?|resolve[sd]?` followed by an issue reference (`#N`, `owner/repo#N`, a full issue URL), anywhere in the three inputs. Any hit refuses (FR-017). `render_line_text_for_body(text)` returns the line text in a code span with `#` references defanged, so the body never carries a keyword.

### Annotation functions
`annotate(body, line_id, state, detail) -> body | None`, `tick(body, line_id, annotation) -> body | None`, `clear_note(...)`. `None` when the id is missing or duplicated, or the line is already ticked (stand down).

### CLI subcommands
`select`, `claim`, `progress`, `hold`, `route-proposal`, `tick-evidence`, `tick-fixed`, `note-proof`, `check-closing-keywords`. Each edit subcommand goes through `board_backlog_edit.edit()`.

## `board_backlog_edit.py`

### `edit(issue, apply_fn, verify_fn, *, fetch, write, max_attempts=5) -> Result`
1. fetch body; 2. `new = apply_fn(body)`; `None` → `Result.stand_down`; 3. write; 4. fetch; `verify_fn(post_body)` true → `Result.ok`; false → loop. Exhausted → body left as last fetched (no forced write), `Result.failed`. `fetch` and `write` are injected so fixtures interleave concurrent writers.

### CLI
`board_backlog_edit.py --issue N --op <name> --line-id ID [--detail TEXT]`. This is the only sanctioned way for a local session to edit the backlog body (CLAUDE.md, "Working the issue board"). No other script or workflow runs `gh issue edit` with a body for the backlog (gate-enforced).

## PR body reference

A line-born PR body contains `Backlog line: #<backlog-issue> <line-id>` and the line text rendered by `render_line_text_for_body`. Paths that find a PR's item (prove entry, missed-proof detection, resume recovery) match this line, then read the keyed marker.
