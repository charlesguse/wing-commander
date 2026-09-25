#!/usr/bin/env python3
"""Single home for the body of every spec-request board-loop.yml files
(specs/057-autonomous-board-loop FR-021/FR-056).

WHY THIS EXISTS
---------------
Board-loop run 36044831201 routed issue #390 to spec, but route-propose
returned `category=spec` with no `pr-body`. The route job's spec step
built the body as `${pr_body:-No drafted body.}` plus a footer, so
spec-request #509's whole body was "No drafted body." and a link, and
intake started from an almost empty request. The fix job's post-push
breach and the readiness job's backstop breach had the same gap: their
spec-requests carried a breach notice and nothing about the work itself.

Every spec-request body board-loop.yml files is now built here, from the
same parts and in the same order:

    [notice]                      optional, e.g. a backstop-breach notice
    <body proper>                 see below
    ---
    [footer]                      optional, e.g. routing reason and link

The body proper is the first of these that is non-empty:

1. the drafted body (`--drafted-body-file`, route-propose's `pr-body`),
   under the heading "Drafted request (route agent output, shown as
   text):" -- model output derived from issue content, so it is data
   for intake to read, not markdown for GitHub to render (#548);
2. the originating issue's context, under the heading
   "Originating issue (trust-filtered context):" -- read ONLY from the
   file path given as `--context-file`, which Gate 93 requires to be the
   `context-file` output of wing-commander-issue-context (title, body,
   and comments that passed the author-association trust filter). This
   script cannot prove the file was not rewritten between that step and
   this one, so the heading claims only where the text came from;
3. the one-line fallback "No drafted body." when that composite never
   ran or its file is missing or empty.

Both the drafted body and the context go inside a fenced code block
whose fence is longer than the longest backtick run in the text, built by
one helper (fenced_section(), sized by fence_for()). GitHub does not
expand @mentions or #N references inside a code block, and renders no
link, image or HTML there, so the body neither notifies every commenter
(the context file carries a "## Comment by @login" line per comment, and
the draft can quote anyone) nor adds a "mentioned this" entry to every
issue or PR the text cites. No text inside can close the fence early:
GitHub's cmark-gfm caps a fence at 255 backticks (a longer one is read
as 255, so a lone line of 255 inside would close it), so before sizing,
fenced_section() splits every run of 255 or more backticks with a U+200B
zero-width space every 254 characters. The longest run left is 254 and
the fence is at most MAX_FENCE_LEN (255) backticks.
Intake reads the body as raw text (`gh issue view --json body`) and
treats it as an untrusted feature description, so the fence changes
nothing it relies on.

The fallback reads that file and nothing else. Never an unfiltered
`gh issue view --json body,comments`: FR-056 requires comment content to
be filtered in code before it reaches intake, and the spec-request body
feeds intake. Gate 93 (verify-issue-context-single-home.py) enforces both
halves: every spec-request creation in board-loop.yml goes through this
script, and its `--context-file` comes from that composite's
`context-file` output.

The body proper is truncated so the whole body stays under GitHub's
65536-character issue-body limit. When text is cut, a visible note (after
the closing fence, so it renders) says how much was omitted. Length is
counted in UTF-16 code units (the way GitHub's limit counts characters)
against a cap below 65536, which leaves room for newline normalisation.

USAGE
-----
    python3 .github/scripts/board_spec_request_body.py \\
      --context-file "$ISSUE_CONTEXT_FILE" \\
      [--drafted-body-file PATH] [--notice TEXT] [--footer TEXT] \\
      --out PATH
"""
import argparse
import os
import re
import sys

GITHUB_BODY_LIMIT = 65536
# Headroom under GitHub's limit for line-ending normalisation and the
# encoding differences a character count can hide.
MAX_BODY_UNITS = 60000

NO_BODY_FALLBACK = "No drafted body."
CONTEXT_HEADING = "Originating issue (trust-filtered context):"
DRAFTED_HEADING = "Drafted request (route agent output, shown as text):"
SEPARATOR = "\n\n---\n"
BACKTICK_RUN_RE = re.compile(r"`+")
# cmark-gfm (GitHub's renderer) reads a fence of more than 255 backticks
# as 255, so no run inside the text may reach 255.
MAX_FENCE_LEN = 255
LONG_BACKTICK_RUN_RE = re.compile(r"`{%d,}" % MAX_FENCE_LEN)
RUN_SPLITTER = "\u200b"


def utf16_len(text):
    """Length in UTF-16 code units: a character outside the BMP counts
    twice, the way a JavaScript-side length check counts it."""
    return len(text.encode("utf-16-le")) // 2


def truncation_note(omitted):
    return ("\n\n_[Truncated: {0} characters omitted to stay under "
            "GitHub's {1}-character issue body limit. The full text is on "
            "the originating issue.]_").format(omitted, GITHUB_BODY_LIMIT)


def _cut_to_units(text, budget):
    """The longest prefix of `text` whose UTF-16 length is <= budget."""
    if budget <= 0:
        return ""
    used = 0
    for index, char in enumerate(text):
        width = 2 if ord(char) > 0xFFFF else 1
        if used + width > budget:
            return text[:index]
        used += width
    return text


def truncate(text, budget):
    """(kept, note): `text` and "" when it fits `budget` UTF-16 units;
    otherwise its longest prefix that leaves room for the truncation
    note, and that note. utf16_len(kept) + utf16_len(note) <= budget."""
    if utf16_len(text) <= budget:
        return text, ""
    # The note's own length depends on the omitted count's digit count;
    # sizing it with the largest possible count keeps the result in
    # budget whatever the final count is.
    note_budget = utf16_len(truncation_note(len(text)))
    kept = _cut_to_units(text, budget - note_budget).rstrip()
    return kept, truncation_note(len(text) - len(kept))


def split_long_backtick_runs(text):
    """`text` with every run of MAX_FENCE_LEN or more backticks broken
    into chunks of MAX_FENCE_LEN - 1 joined by RUN_SPLITTER, so no run can
    close a fence of at most MAX_FENCE_LEN."""
    chunk = MAX_FENCE_LEN - 1

    def _split(match):
        run = match.group(0)
        return RUN_SPLITTER.join(run[i:i + chunk]
                                 for i in range(0, len(run), chunk))
    return LONG_BACKTICK_RUN_RE.sub(_split, text)


def fence_for(text):
    """A backtick fence longer than any backtick run in `text` (at least
    three), so nothing inside can close it."""
    longest = max((len(m.group(0)) for m in BACKTICK_RUN_RE.finditer(text)),
                  default=0)
    return "`" * max(3, longest + 1)


def fenced_section(heading, text, budget):
    """`heading`, then `text` in a fenced code block, inside `budget`
    UTF-16 units -- the one home for fencing any part of the body. The
    fence is sized from the full text; cutting only shortens backtick
    runs, so the same fence still holds after truncation. The truncation
    note goes after the closing fence, where it renders. Long backtick
    runs are split first (split_long_backtick_runs()), so the fence stays
    within cmark-gfm's 255 cap and still no line inside can close it.
    Every CR is normalised to LF first (#580 review): GitHub ends a line
    at a lone CR too, so after this the fenced text's lines are exactly
    the lines GitHub renders."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = split_long_backtick_runs(text)
    fence = fence_for(text)
    opening = heading + "\n\n" + fence + "\n"
    closing = "\n" + fence
    kept, note = truncate(
        text, budget - utf16_len(opening) - utf16_len(closing))
    return opening + kept + closing + note


def read_text(path):
    """The file's text, or "" when `path` is empty, missing or
    unreadable (the composite never ran, or its step failed)."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def build_body(drafted="", context="", notice="", footer="",
               max_units=MAX_BODY_UNITS):
    """Assemble one spec-request body. See the module docstring for the
    layout and the order the body proper is chosen in."""
    drafted = (drafted or "").strip()
    context = (context or "").strip("\n").rstrip()
    notice = (notice or "").strip()
    footer = (footer or "").strip()

    head = notice + "\n\n" if notice else ""
    tail = SEPARATOR + footer if footer else ""
    # Notice and footer are short, deterministic text built by the
    # workflow; they are never cut. Whatever room is left goes to the
    # body proper.
    budget = max_units - utf16_len(head) - utf16_len(tail)

    if drafted:
        proper = fenced_section(DRAFTED_HEADING, drafted, budget)
    elif context.strip():
        proper = fenced_section(CONTEXT_HEADING, context, budget)
    else:
        proper = NO_BODY_FALLBACK

    return head + proper + tail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--context-file", default="",
                        help="wing-commander-issue-context's context-file "
                             "output (empty when that step never ran)")
    parser.add_argument("--drafted-body-file", default="")
    parser.add_argument("--notice", default="")
    parser.add_argument("--footer", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    body = build_body(
        drafted=read_text(args.drafted_body_file),
        context=read_text(args.context_file),
        notice=args.notice,
        footer=args.footer,
    )
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
