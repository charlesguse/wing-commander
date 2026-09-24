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

1. the drafted body (`--drafted-body-file`, route-propose's `pr-body`);
2. the originating issue's trust-filtered context, under the heading
   "Originating issue (trust-filtered, verbatim):" -- read ONLY from the
   `context-file` output of wing-commander-issue-context (title, body,
   and comments that passed the author-association trust filter);
3. the one-line fallback "No drafted body." when that composite never
   ran or its file is missing or empty.

The fallback reads the composite's file and nothing else. Never an
unfiltered `gh issue view --json body,comments`: FR-056 requires comment
content to be filtered in code before it reaches intake, and the
spec-request body feeds intake. Gate 93
(verify-issue-context-single-home.py) enforces both halves: every
spec-request creation in board-loop.yml goes through this script, and
its `--context-file` comes from that composite's `context-file` output.

The body proper is truncated so the whole body stays under GitHub's
65536-character issue-body limit. When text is cut, a visible note says
how much was omitted. Length is counted in UTF-16 code units (the way
GitHub's limit counts characters) against a cap below 65536, which leaves
room for newline normalisation.

USAGE
-----
    python3 .github/scripts/board_spec_request_body.py \\
      --context-file "$ISSUE_CONTEXT_FILE" \\
      [--drafted-body-file PATH] [--notice TEXT] [--footer TEXT] \\
      --out PATH
"""
import argparse
import os
import sys

GITHUB_BODY_LIMIT = 65536
# Headroom under GitHub's limit for line-ending normalisation and the
# encoding differences a character count can hide.
MAX_BODY_UNITS = 60000

NO_BODY_FALLBACK = "No drafted body."
CONTEXT_HEADING = "Originating issue (trust-filtered, verbatim):"
SEPARATOR = "\n\n---\n"


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


def fit(text, budget):
    """`text` unchanged when it fits `budget` UTF-16 units; otherwise its
    longest fitting prefix plus a truncation note, the whole still inside
    `budget`."""
    if utf16_len(text) <= budget:
        return text
    # The note's own length depends on the omitted count's digit count;
    # sizing it with the largest possible count keeps the result in
    # budget whatever the final count is.
    note_budget = utf16_len(truncation_note(len(text)))
    kept = _cut_to_units(text, budget - note_budget).rstrip()
    return kept + truncation_note(len(text) - len(kept))


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
    context = (context or "").strip()
    notice = (notice or "").strip()
    footer = (footer or "").strip()

    head = notice + "\n\n" if notice else ""
    tail = SEPARATOR + footer if footer else ""
    # Notice and footer are short, deterministic text built by the
    # workflow; they are never cut. Whatever room is left goes to the
    # body proper.
    budget = max_units - utf16_len(head) - utf16_len(tail)

    if drafted:
        proper = fit(drafted, budget)
    elif context:
        label = CONTEXT_HEADING + "\n\n"
        proper = label + fit(context, budget - utf16_len(label))
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
