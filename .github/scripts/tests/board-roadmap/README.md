# board-roadmap fixtures

Read by `verify-board-duplicate-disposition.py` (the Roadmap cases, #1209).
`roadmap-body.md` is a cut-down copy of the Roadmap issue's body with the
same section layout: the "### Proposed" header, the owner's numbered
order (2026-11-25), the "Not specs:" list, the paragraphs after them and
the next heading. `roadmap-body-expected.md` is that
body after the board loop lists spec-proposal #4242 from backlog line
`bl-0123abcd` on 2026-11-25: a new "Not yet ordered" sub-list after the
numbered order, never inside it or in "Not specs:".
