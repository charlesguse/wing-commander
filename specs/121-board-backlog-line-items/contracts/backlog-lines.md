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
`env` carries `backlog_lines_switch`, `loop_paused`, `constitution_text`. Refuses with a one-line reason when the switch is not `true` (compared case-insensitively, never trimmed: the one switch rule, `wc_board_status._switch_on`), the loop is paused (the same rule), or Principle X (`### X.` section) lacks `Maintenance backlog line`; `constitution_text = None` refuses (FR-025).

### `mint_id(body) -> str`
`bl-` + 8 hex; never an id already in `body`.

### `branch_for(issue, line_id) -> str`
`fix/<issue>-<line_id>`; asserts `FIX_BRANCH_RE` full match.

### `title_for(text, prefix="Fix: ") -> str`
Strips annotation, collapses whitespace, truncates with `…` so `len(prefix + text) <= 200`; never contains a closing keyword (see below).

### `closing_keyword_hits(title, body, commit_messages) -> [Hit]`
Case-insensitive `close[sd]?|fix(e[sd])?|resolve[sd]?` followed by an issue reference (`#N`, `GH-N`, `owner/repo#N`, a full issue URL), anywhere in the three inputs. Any hit refuses (FR-017). `CLOSING_RE` is the one home of the pattern: `closing_keyword_refs(text, repository) -> [(N, match)]` reads the same hits, keeps those naming an issue of `repository` and gives its number, for Gate 182 (`verify-pr-closing-keywords.py`) and `wc_proof_list.closing_targets()`; no other script reads `CLOSING_RE` itself (Gate 191). `render_line_text_for_body(text)` returns the line text in a code span with `#` references defanged, so the body never carries a keyword.

### Annotation functions
`annotate(body, line_id, state, detail) -> body | None`, `tick(body, line_id, annotation) -> body | None`, `clear_note(...)`. `None` when the id is missing or duplicated, or the line is already ticked (stand down). `clear_note` clears only a `held` annotation, removing the id with it (the release).

### `line_context(body, issue, line_id, repository=None) -> str | None`
That line's text alone, fenced and framed as untrusted data (FR-007, FR-008). Triage's `find_cited_run()` skips fenced code, so each run link of `repository` (default `$GITHUB_REPOSITORY`) that the fenced text still carries after its 8000-character cut is listed again after the closing fence: the bare URL and nothing else of the line, matched by `board_triage.run_url_pattern()`, the one home of that pattern. Without it a line could never be ticked on run evidence (FR-012). No other repository's link leaves the fence.

### `release_attempt(issue, line_id, run=None, repository=None, sleep=None, close_attempts=3) -> str | None`
#1135 option (c): ends a released line's held attempt. `decide_line_item()` lists in `released` each line id whose newest line marker is `stalled` and that no line carries any more (released by the `release` op or by deleting the annotation by hand); board-loop's select line step calls `--release-attempt ISSUE LINE_ID` for each before it claims, and claims nothing while one returns no outcome. It closes every open PR whose head is `branch_for(issue, line_id)` in this repository and whose body cites the line (`pr_cites_line`), and never deletes the branch. Once a PR is closed it posts one comment on it saying the line was released: after the close, never with it, since `gh pr close --comment` posts its comment before it closes and a retried close would repeat it on a PR still open. A note that fails to post leaves the close final. It then posts one record on the backlog issue carrying a `stood-down` line marker, which ends the id's `stalled` state, so no later run repeats it. A close that fails is tried three times in all; a PR the token still cannot close is named in the record with the `gh pr close` command a maintainer runs. With no open PR only the record is posted. `None` (exit 1) when the PRs cannot be listed or the record cannot be posted; the next run retries.

### CLI subcommands
`select`, `claim`, `progress`, `hold`, `release`, `route-proposal`, `tick-evidence`, `tick-fixed`, `note-proof`, `check-closing-keywords`. Each edit subcommand goes through `board_backlog_edit.edit()`.

## `board_backlog_edit.py`

### `edit(issue, apply_fn, verify_fn, *, fetch, write, max_attempts=5) -> Result`
1. fetch body; 2. `new = apply_fn(body)`; `None` → `Result.stand_down`; 3. write; 4. fetch; `verify_fn(post_body)` true → `Result.ok`; false → loop. Exhausted → body left as last fetched (no forced write), `Result.failed`. `fetch` and `write` are injected so fixtures interleave concurrent writers.

### CLI
`board_backlog_edit.py --issue N --op <name> --line-id ID [--detail TEXT]`. This is the only sanctioned way for a local session to edit the backlog body (CLAUDE.md, "Working the issue board"). No other script or workflow runs `gh issue edit` with a body for the backlog (gate-enforced).

`--op release` releases a held line: it removes the `held` annotation and the id with it (`clear_note`). It is idempotent: on a body where no line carries the id (released already) it writes nothing and returns `applied`. It stands down on an id that names a line in any other state, or more than one line.

## PR body reference

A line-born PR body contains `Backlog line: #<backlog-issue> <line-id>` and the line text rendered by `render_line_text_for_body`. Paths that find a PR's item (prove entry, missed-proof detection, resume recovery) match this line, then read the keyed marker.
