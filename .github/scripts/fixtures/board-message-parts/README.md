Fixtures for `.github/scripts/verify-board-message-parts.py` (spec 130).
Each `*.json` file is `{"mode", "id", "input", "expect"}`; the gate renders
it with `wc_message_parts.py` and checks the result. The gate also derives a
"one part missing" variant of every `*-full.json` fixture and an over-length
variant, so those need no file of their own.
`extract-explanation` fixtures hold the fixer's final message under
`input.result` and the exact parts the loop must keep under `expect`.
