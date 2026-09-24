"""Shared fenced-block JSON extractor for board-loop.yml's three agent
result parsers (triage-propose, route-propose, reviewer).

WHY THIS EXISTS
---------------
#499 code review (SF1): all three inline extractors used the same
non-greedy `re.search(r"```TAG\\s*\\n(.*?)```", text, re.S)`, which matches
the FIRST closing fence anywhere in the text -- including one nested
inside a quoted diff or code block the agent's own final message
contains before its real fenced answer. route-propose is the site most
exposed (its own proposal carries a diff, which can itself contain a
fence -- confirmed with a synthetic proposal whose diff embeds one), but
nothing stopped this from also truncating triage-propose or reviewer
output that quotes code. One extractor, used by all three, so a fix (or a
future regression) lands once instead of three times independently.

WHAT IT DOES
------------
`extract_fenced_json(text, tag)`:
  1. Normalizes CRLF to LF first -- a Windows-authored quote inside the
     agent's own message, or any \\r\\n line ending, must not make the
     line-start closing-fence match below miss.
  2. Finds the LAST "```<tag>" opening fence in the text, not the first --
     an agent's message occasionally shows an example or quotes another
     block before its real, final answer.
  3. Closes it on the next line that is ONLY a fence (`^```[ \\t]*$`,
     re.M) -- a fence embedded inside a diff or quoted code block is
     never bare on its own line the way a real closing fence is (a diff
     line always carries at least a leading +/-/space character), so this
     cannot be fooled by one. A model that omits the trailing fence
     entirely (no closing fence at all) is NOT treated as a failure here:
     the block is read to the end of the text instead, on the theory that
     an agent's fenced answer is normally its final content anyway, so
     whatever follows the opening fence is the best available payload.
  4. Parses the block as JSON.

Returns `(value, None)` on success, `(None, "<reason>")` on any failure
(no opening fence at all, or the matched block's text is not valid JSON)
-- the caller decides what "failure" means for its own output. Gate 94
(verify-fence-extract.py) asserts the missing-closing-fence case
specifically reads to end of text rather than failing. triage-propose
and route-propose
fall back to an already-safe default (close=False / category=spec) on
failure; the reviewer must NOT do the equivalent (silently reading as
"zero findings" would advance a possibly-unreviewed PR straight to
readiness) -- see board-loop.yml's "Extract and validate the review
findings" step, which fails the round CLOSED (outcome=stalled) instead.
"""
import json
import re


def extract_fenced_json(text, tag):
    """Extract and parse the last ```<tag> ... ``` fenced JSON block in
    `text`. Returns (value, None) on success, (None, reason) on failure."""
    text = (text or "").replace("\r\n", "\n")
    opens = list(re.finditer(r"```" + re.escape(tag) + r"\s*\n", text))
    if not opens:
        return None, "no ```{0}``` block found in the agent's result text".format(tag)
    start = opens[-1].end()
    close = re.search(r"^```[ \t]*$", text[start:], re.M)
    block = text[start:start + close.start()] if close else text[start:]
    try:
        return json.loads(block), None
    except ValueError as exc:
        return None, "```{0}``` block did not parse as JSON ({1})".format(tag, exc)
