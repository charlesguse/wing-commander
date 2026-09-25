#!/usr/bin/env python3
"""Write step outputs whose values may carry agent or issue text (#583).

$GITHUB_OUTPUT is line-oriented: a CR or LF inside a `key=value` line ends
that value and starts a new `key=value` line, so a value can set other
outputs of the same step. clean_output_value() removes every control
character (Unicode category Cc, which covers CR, LF, NUL, ESC and the C1
range including NEL) plus the Unicode line and paragraph separators, so a
value always stays on its own line. write_outputs() is the one place
board-loop.yml writes such values from Python; the CLI form is for shell:

    python3 wc_step_output.py KEY VALUE >> "$GITHUB_OUTPUT"
"""
import re
import sys
import unicodedata

_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_LINE_SEPARATORS = (" ", " ")


def clean_output_value(value):
    """`value` as a str with every control character and line/paragraph
    separator removed."""
    text = "" if value is None else str(value)
    return "".join(ch for ch in text
                   if unicodedata.category(ch) != "Cc" and ch not in _LINE_SEPARATORS)


def output_line(key, value):
    """One `key=value` line (no trailing newline). The key is fixed by the
    caller and must be a plain output name."""
    if not _KEY_RE.fullmatch(key or ""):
        raise ValueError("invalid step output name: {0!r}".format(key))
    return "{0}={1}".format(key, clean_output_value(value))


def write_outputs(path, pairs):
    """Append each (key, value) in `pairs` to the $GITHUB_OUTPUT file at
    `path`, one cleaned line per pair."""
    lines = [output_line(k, v) for k, v in pairs]
    if not lines:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv):
    if len(argv) != 3:
        print("usage: wc_step_output.py KEY VALUE", file=sys.stderr)
        return 2
    try:
        print(output_line(argv[1], argv[2]))
    except ValueError as exc:
        print("::error::{0}".format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
