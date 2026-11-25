# Contract: message parts renderer (live; fixed like code)

Module: `.github/scripts/wc_message_parts.py` (internal, not the published surface).

## API
- `render_explanation(parts: dict, identifier: str) -> str`
- `render_review(parts: dict, identifier: str, findings: list) -> str`
- `gap_text(part: str, kind: str) -> str`

## Guarantees
1. Every part of the set appears in the output, filled or as gap text, even when
   the input omits it, is empty, or is not a string.
2. Agent-written and backlog text is inside `fenced_section(...)`; labels and
   fixed text are outside. A fence/HTML/Markdown payload cannot close the fence.
3. The review output never equals or reduces to "No findings"; it names the identifier.
4. Lead section is labelled parts only; supplementary text goes in `<details>`.
5. Total output stays under 57000 UTF-16 units.
6. PR-body summary is rendered fenced and is refused if it contains a closing
   keyword (spec 121 rule), exiting non-zero with the keyword named.

## CLI
`python3 -I wc_message_parts.py render-explanation|render-review|summary --in FILE --id ID`
Exit 0 and body on stdout; exit 2 on refusal.

## Review result schema fragment
`report: {asked, checked, decided, not_decided, open}` each optional string.

## Gate
`verify-board-message-parts.py`: renders checked-in fixtures (one per part missing,
per part set, plus fence-injection, closing-keyword, over-length) and fails when a
rendered fixture lacks a part. Second mode enumerates `board-fixed-messages.json`
across auto-merge x kill switch x PR class and fails on a contradicted claim or an
unregistered fixed message.
