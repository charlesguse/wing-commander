# board-backlog-edit fixtures

JSON scenarios run by `verify-board-backlog-edit.py`. Each has
`initial` body, `op` + `line_id`, a list of `interference` bodies the fake
fetch returns in sequence after each write, and `expect` result (and
optionally `final_contains` / `final_equals_initial`).
