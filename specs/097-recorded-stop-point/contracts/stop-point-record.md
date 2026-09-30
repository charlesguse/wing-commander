# Contract: Stop Point Record content (FR-003, FR-004, FR-005, FR-010)

## Comment body template

```text
This item stopped because a maintainer posted a stop request.

Stop comment: <html_url> (from <login>, <created_at>)

<fenced reason block, omitted when the stop command carried no reason>

To resume this item, remove the `board:stalled` label.

<marker>
```

Where:

- `<html_url>` — the winning Stop Command Comment's own GitHub permalink
  (`https://github.com/<owner>/<repo>/issues/<n>#issuecomment-<id>`), added
  to the composite's existing comments fetch (contracts/stop-check-
  composite.md). A real GitHub URL, not user-authored text — rendered as a
  plain link, no fencing needed.
- `<login>` — the winning comment's author, rendered **without** a leading
  `@` (e.g. `alice`, not `@alice`) so posting this record never pings that
  maintainer. GitHub does not autolink a bare login.
- `<created_at>` — the winning comment's timestamp, as returned by the API
  (ISO 8601), rendered as-is.
- The reason block, when `stop_command_reason(body) != ""`:
  ```text
  <fenced_section("Reason given:", reason, 2000)>
  ```
  using `.github/scripts/board_spec_request_body.py`'s existing
  `fenced_section()` (imported from the trusted snapshot, the same way
  `board-loop.yml`'s fix job already does at its gate-failure rendering
  site) — never a second, hand-rolled quoting routine (FR-005: "the loop's
  existing fencing rule for quoted content"). When the stop command carried
  no reason (e.g. a bare `stop.`), this block is omitted entirely — no
  empty fence.
- `<marker>` — exactly `write_marker("stalled", 0, None, branch_or_none,
  base_sha_or_none)`'s own output, i.e. the `**Run:** <url>` line followed
  by the `<!-- wing-commander-board-item: {...} -->` HTML comment — this is
  what makes the record simultaneously human-legible (FR-004) and
  machine-readable (the existing marker-read contract, unchanged), and what
  gives this run's own stop-point record a `**Run:**` line that becomes the
  new stop-baseline going forward (research.md D10).

## Inert-reason guarantee (FR-005)

Only the reason text goes through `fenced_section()`. Everything else in
the template above is either a literal string this feature writes, or a
GitHub-generated URL/timestamp/login — never text the maintainer who posted
the *reason* controls outside the fence. A reason of
`` `@everyone` fixes #1 <script>alert(1)</script> `` renders, inside the
fence, as inert text: no mention fires, no cross-reference resolves, no
HTML executes, exactly as `fenced_section()` already guarantees for the fix
job's own gate-failure text today.

## Release condition (FR-004)

The single stated condition is always the same literal sentence: "remove
the `board:stalled` label." This is deliberately not phrased as "wait for
X" or "a maintainer will need to..." — spec 100 (in review) governs exactly
what happens *after* release (which step the item resumes at); this
record's own job is only to state the one act that makes the item eligible
for selection again, which is unaffected by spec 097/spec 100's landing
order.

## What is explicitly NOT in the record

- No PR number (FR-010: re-found via the existing `board:owned` fallback on
  release, never carried in the record).
- No review round (FR-010: dropped, matching `write_marker()`'s own
  `--round` default of `0`).
- No second label, no new marker step name (FR-003: the existing `stalled`
  step + `board:stalled` label is reused verbatim).
- No mention of which of the six jobs (triage/route/fix/review/readiness)
  happened to be the one that reached the stop check — a maintainer reading
  the issue does not need to know which stage was in flight, only that the
  loop stopped, why, and how to resume it.

## Acceptance mapping

- User Story 2, AS1 — cause, comment identity, and release condition are
  all literal, present text in the template above.
- User Story 2, AS2 — the reason (when present) is fenced; nothing outside
  the fence comes from the maintainer's own reason text.
- Edge case "item stopped while it had no branch or PR yet" vs "mid-fix or
  mid-review" — both produce this exact same template; only the marker's
  trailing `branch`/`base_sha` fields differ (null vs populated), per
  whichever `marker-branch`/`marker-base-sha` inputs the calling job passed.
