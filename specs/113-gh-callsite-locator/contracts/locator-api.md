# Contract: `wc_gh_callsites` module

Location: `.github/scripts/wc_gh_callsites.py`. Pure Python stdlib. Internal
(not part of the published adopter surface, Principle VII).

```python
def locate(script: str) -> list[Token]: ...
```

- Input: the text of one `run:` block (Actions `${{ … }}` expressions are
  left in place and treated as opaque words).
- Output: every `\bgh\b` command-position token, in source order, each a
  `Token` (see data-model.md) with `kind` `call` or `mention`.
- Guarantees:
  1. A token is `mention` only under FR-004 (a) quoted span without `$(` or
     backtick, (b) quoted-delimiter heredoc body, (c) shell comment.
  2. Every ambiguity yields `call`; calls outside the authoring rule have
     `position == "disallowed"` and a `reason`.
  3. Runs in time linear in `len(script)`.
  4. Never raises on malformed shell (unterminated quote or heredoc ⇒
     remaining `gh` tokens are `call`/`disallowed`).
- Consumers: Gate 12 (`verify-gate-12-token-permissions.py`), Gate 28
  (`verify-gh-api-explicit-method.py`). `verify-stop-point-recording.py`
  is waived until its own lifecycle.

Disallowed-form failure message (emitted by consumers):

`<file>:<line>: gh call in a form Gate 12 cannot verify (<reason>) — rewrite
it to the allowed form; see <authoring-rule heading>.`
