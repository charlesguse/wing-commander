# Research: Board Loop Works Maintenance Backlog Lines

Spec 121 carries no `[NEEDS CLARIFICATION]` markers (all questions were answered in its Clarifications sessions). The decisions below are the design choices the plan still had to make. Items marked **(plan decision)** were not settled by the spec and were decided here without clarification.

## D1. Where the logic lives

- **Decision**: One new pure-Python module, `.github/scripts/board_backlog_lines.py`, owns every line-specific rule: body parsing, candidate selection, id minting, annotation grammar, branch and title derivation, closing-keyword scan, backlog resolution, constitution phrase check, and the switch check. A second module, `.github/scripts/board_backlog_edit.py`, is the FR-024 shared edit helper (read, apply one change, write, read back). `board-loop.yml` calls them; it carries no line logic of its own.
- **Rationale**: Matches the existing `board_*.py` layout (eligibility, triage, merge). CLAUDE.md "Shared logic has exactly one home" and Principle IX (judgment that gates a durable action is deterministic code). The edit helper is separate because sessions call it too (FR-024).
- **Alternatives**: Inline `jq`/bash in `board-loop.yml` (rejected: untestable fixtures, repo rule). A composite action (rejected for the parser: no cross-workflow consumer; the edit helper is exposed as a CLI script under `.github/scripts/`, like the other board modules).

## D2. Line identity (FR-003) **(plan decision on format)**

- **Decision**: id = `bl-` + 8 lowercase hex characters from `secrets.token_hex(4)`, e.g. `bl-3f9a2c1d` (11 chars, inside `[a-z0-9-]`, well under the 40-char slug limit). Minted at claim, checked against ids already present in the body, re-minted on collision. The id is carried in the line's annotation token (D4).
- **Rationale**: Short, lossless in the branch name (no case folding), unique by construction within the body.
- **Alternatives**: content hash (rejected by the owner: breaks on edit, collides on identical lines); sequential counter (rejected: needs a stored counter, another write).

## D3. Branch and title derivation (FR-007)

- **Decision**: Branch `fix/<backlog-issue>-<line-id>`, e.g. `fix/889-bl-3f9a2c1d`; it matches `FIX_BRANCH_RE = fix/\d+-[a-z0-9-]{1,40}`. PR title is `Fix: <line text>` with no issue number; the line text has the id/annotation token stripped, is whitespace-collapsed, and is cut with an ellipsis so the whole title is at most 256 characters (cut to 200 to leave headroom for prefixes the other title sites add). Every title that the issue path copies from the issue title takes this function's output for a line.
- **Rationale**: The issue path's `Fix #<issue>: <title>` would carry a closing keyword for the backlog issue (FR-017). Dropping the `#N` removes the keyword shape entirely.
- **Alternatives**: `Refs #889:` prefix in the title (rejected: still invites a later edit to a keyword; plain `Fix:` is simplest to scan).

## D4. Annotation grammar (FR-010, FR-011, FR-013, FR-014) **(plan decision)**

- **Decision**: The loop appends exactly one trailing token to a claimed line: `[wc:<id> <state>[ <detail>]]`, where state is one of `in-progress`, `held`, `proposal`, `fixed`, `evidence`, plus an optional `not-proven` note. Examples: `[wc:bl-3f9a2c1d in-progress PR #1201]`, `[wc:bl-3f9a2c1d held: red gate suite]`, `[wc:bl-3f9a2c1d proposal #1210]`, `[wc:bl-3f9a2c1d fixed by #1201]`. Ticking replaces `- [ ]` with `- [x]`. A maintainer clears a hold by deleting the token (or its `held` state); an unclaimed line carries no token. The token is visible in the rendered issue, parsed by one regex, and the rest of the line is never rewritten.
- **Rationale**: Visible where a maintainer reads the backlog (FR-011's owner decision); one regex gives FR-004's skip rule and FR-016's identity match. Reasons that contain `]` or newlines are sanitised by the writer.
- **Alternatives**: hidden HTML comment (rejected: invisible, contradicts FR-010); emoji prefixes (rejected: brittle matching).

## D5. Board state storage (FR-009)

- **Decision**: One loop-authored comment per claimed line on the backlog issue, carrying the existing `wing-commander-board-item` marker with an extra `line` field (the id). `board_item_marker` gains a keyed read: the marker readers that today read "the newest loop marker on issue N" take an optional `line` filter and, for a line item, read only markers whose `line` equals the id. Issue-path calls (no filter) ignore markers that carry a `line` field, so the backlog issue's markers never look like an issue-path item.
- **Rationale**: Reuses the marker writer/reader and its author check (#555) as the spec states; the filter is the single home for "which marker is this item's".
- **Alternatives**: one marker comment per backlog issue (rejected: two lines in sequence would shadow each other); state inside the line (rejected: long, user-editable).

## D6. How the select job takes a line (FR-001, FR-006, FR-020, FR-023, FR-025)

- **Decision**: `select` first runs today's issue selection unchanged. Only when it returns no issue and no line is already claimed does it call `board_backlog_lines.py select`, which applies in order: switch is exactly `true`, kill switch clear, constitution phrase present (read fresh from the default branch), backlog resolves unambiguously and was authored by a maintainer or the App, a candidate line exists. A claimed line (a loop marker keyed to a line id whose step is non-terminal and whose line is still in progress) is "the current item" and is resumed before any new claim. A refusal prints one reason line into the run summary. Outputs to downstream jobs: `item_kind` (`issue` or `line`), `item_number` (the backlog issue for a line), `line_id`, `line_text`.
- **Rationale**: Issues keep precedence by construction (SC-004). Resume of a claimed line is not gated by the switch (FR-023), so the order is: claimed line → eligible issue → new claim.
- **Alternatives**: interleaving (out of scope per FR-001).

## D7. Making downstream jobs line-aware without forking them (FR-007, FR-013, FR-014, FR-017, FR-021)

- **Decision**: Introduce a single "item sink" set of CLI subcommands in `board_backlog_lines.py` (`hold`, `route-proposal`, `tick-evidence`, `tick-fixed`, `progress`, `note-proof`) that every site which today does `gh issue edit --add-label board:stalled`, files a proposal and disposes of the issue, or closes the issue, calls when `item_kind == line`. The issue branch of each step stays as it is. The duplicate-disposition (spec 108) call is skipped for a line (FR-013). `fix`, `review-fixup-publish` and `merge` call `board_backlog_lines.py check-closing-keywords` before push/open/merge (FR-017); a refusal routes to `hold`. Resume's and the prove entry's lookup of "which item does this PR belong to" gains a second form: the PR body's non-closing reference `Backlog line: #<issue> <id>` (FR-021).
- **Rationale**: Keeps each existing step's structure; the line differences concentrate in one module that fixtures can exercise.
- **Alternatives**: duplicate jobs for lines (rejected: doubles ~5000 lines of workflow, and every divergent fix lands twice).

## D8. The edit helper (FR-015, FR-024)

- **Decision**: `board_backlog_edit.py` exposes `edit(apply_fn, issue, *, max_attempts=5)` and a CLI `--issue N --op <name> --line-id ID ...`. Each attempt: fetch the body, run the pure function `apply_fn(body) -> new_body | None`, write, fetch again, accept when the post-read still contains the change (idempotent predicate supplied per op), else retry up to the bound. `None` means the line is gone/ticked/mismatched → stand down (FR-016) and report on the backlog issue. After the bound it leaves the body untouched and reports. The write is `gh issue edit --body-file` (no conditional write exists, which FR-015 acknowledges). CLAUDE.md gets a rule pointing sessions at the CLI, and a gate (D10) fails if another file contains a direct whole-body write to the backlog.
- **Rationale**: Narrows the race window and makes read-back-and-reapply the one implementation.
- **Alternatives**: edit-history/ETag compare (rejected: not offered by the API for issues).

## D9. Constitution gate and amendment (FR-022, FR-025)

- **Decision**: Selection reads `.specify/memory/constitution.md` from the default branch via the contents API at selection time, extracts the `### X.` section, and requires the literal `Maintenance backlog line`. Unreadable → refuse. The amendment itself is a separate human-merged PR (#1115) and is not part of this feature's PRs; the plan only depends on it. The implementation PR does not edit `constitution.md`.
- **Rationale**: Owner precedent (spec 119) and the constraint that agents don't amend the constitution.

## D10. Gates (FR-019, FR-024)

- **Decision**: Add `verify-board-backlog-lines.py` (fixtures under `.github/scripts/tests/board-backlog-lines/`: selection order, skip rules, fenced/quoted/nested lines, identical lines, id format vs `FIX_BRANCH_RE`, long-title cut, closing-keyword scan including quoted line text, annotations, constitution phrase present/absent/unreadable, switch off with a claimed line, ambiguous backlog) and `verify-board-backlog-edit.py` (interleaved writer, dropped-change re-apply, deleted line stand-down, retry exhaustion, single-home scan: no other script or workflow writes the backlog body). Both register in the gate registry that `run-local-gates.py` reads and are wired into `lint-workflows.yml` per Principle VIII. Existing gates that enumerate board switches (Board status #914) get the new variable added.
- **Rationale**: Principle VIII; FR-019 demands a fixture for every branch.

## D11. Board status and reporting (FR-018, FR-023)

- **Decision**: `board-status.yml` lists `WING_COMMANDER_BOARD_BACKLOG_LINES` beside the other switches. Run summaries and the lifecycle-style "current item" line print `#889 line bl-xxxx` when `item_kind == line`.

## D12. Post-merge proof for lines (FR-011, FR-021)

- **Decision**: The prove job's close arms are replaced for a line by `note-proof`/`tick-fixed`: proven → no note; any non-success outcome → append `not proven: <reason>` (with run link when present) to the ticked line; a later proven run removes the note. The tick at merge is done by the `pull_request: closed` entry, never gated by the switch or claim state (FR-020).

## Open risk noted, not decided here

`board-loop.yml` is about 6,400 lines; the exact insertion points are found at tasks time by grepping for `board:stalled`, `Fixes #`, `gh issue close` and the spec-proposal filing sites. Tasks should list each site explicitly and have a gate assert none is left unconverted.
