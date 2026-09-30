#!/usr/bin/env python3
"""Shared: what counts as a covered `gh` capture, and whether its failure
path is safe.

WHY THIS EXISTS
---------------
On an HTTP error, `gh api ... --jq '<filter>'` still prints the raw JSON
error body to stdout while the human-readable line goes to stderr and the
filter is never applied -- so `x="$(gh api ...)"` leaves `x` holding
`{"message":"Not Found",...}` on failure, not an empty string (#497). A
capture site is safe only when its own failure path resets the captured
variable, exits the step, leaves the loop iteration before the variable is
next read, or carries a stated-reason `# wc-gh-api-error-exempt:` marker
(specs/091-gh-api-error-capture research.md D5).

Both `verify-gh-api-error-capture.py` (User Story 2) and
`verify-gh-error-stub-conformance.py`'s retrofit-set derivation (User Story
3, research.md D7) import `find_capture_sites`/`classify_failure_path` from
here rather than each defining their own notion of "is this line a covered
capture" -- CLAUDE.md's "shared logic has exactly one home" applied to a
detector rather than a shell fragment. `find_capture_sites` is called both
against a whole workflow/action file's text and against one extracted
`run:` block's text, so it must not assume `text` is a full YAML document.

SCOPE
-----
Only `gh api` (COVERED_GH_SUBCOMMANDS, FR-013) command-substitution
captures -- `gh issue view`, `gh pr list`, etc. are out of scope; widening
later is adding a tuple entry, not a rewrite.
"""
import dataclasses
import re

COVERED_GH_SUBCOMMANDS = ("api",)

_SUBCOMMAND_ALT = "|".join(re.escape(s) for s in COVERED_GH_SUBCOMMANDS)

# `VAR=$(gh api ...` or `VAR="$(gh api ...`. The lookbehind keeps this from
# matching in the middle of a longer identifier (`foo_VAR=`); `oparen` is
# captured so _matching_paren can walk from the exact `(` this substitution
# opens.
CAPTURE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<var>[A-Za-z_][A-Za-z0-9_]*)="
    r'(?P<q>"?)\$(?P<oparen>\()\s*gh\s+(?P<subcommand>' + _SUBCOMMAND_ALT +
    r")\b")

EXEMPT_RE = re.compile(r"wc-gh-api-error-exempt:\s*(\S.*)?")

_FUNC_DEF_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:function\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*\(\)\s*\{")

_KEYWORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OPENERS = {"if", "for", "while", "until", "case"}
_CLOSERS = {"fi", "done", "esac"}


@dataclasses.dataclass
class CaptureSite:
    file: str
    line: int                    # 1-indexed
    variable: str
    subcommand: str
    guard_form: str              # if-negated | or-fallback | bare | pipeline
    # Internal offsets into the `text` this site was found in, reused by
    # classify_failure_path so it does not re-run the capture scan itself.
    var_start: int = 0
    after_stmt: int = 0          # index right after the assignment's RHS


@dataclasses.dataclass
class Classification:
    verdict: str                 # exits | reassigns | loop-exits | opted-in
                                  # | bare-marker | unsafe
    evidence: str


def _matching_paren(text, open_idx):
    """Index of the `)` matching the `(` at `open_idx`, quote-aware.

    Every `(`/`)` outside a quoted string changes depth, so a nested
    command substitution (`$(gh api ... $(...) ...)`) or a subshell group
    is walked correctly without special-casing it.
    """
    depth = 1
    i = open_idx + 1
    n = len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            if quote == '"' and c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _has_top_level_pipe(inner):
    """True if `inner` (a substitution's own content) pipes to another
    command at depth 0 -- `gh api ... | jq ...`, not `gh api ... $(...)`
    and not `a || b`."""
    depth = 0
    quote = None
    i, n = 0, len(inner)
    while i < n:
        c = inner[i]
        if quote:
            if quote == '"' and c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < n:
            i += 2
            continue
        elif c in "(":
            depth += 1
        elif c in ")":
            depth -= 1
        elif c == "|" and depth == 0:
            nxt = inner[i + 1] if i + 1 < n else ""
            prev = inner[i - 1] if i > 0 else ""
            if nxt != "|" and prev != "|":
                return True
        i += 1
    return False


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def find_capture_sites(text, file):
    """Every covered-`gh`-subcommand command-substitution capture in
    `text` (research.md D2's raw-text scan)."""
    sites = []
    for m in CAPTURE_RE.finditer(text):
        open_idx = m.start("oparen")
        close_idx = _matching_paren(text, open_idx)
        if close_idx == -1:
            continue          # unterminated -- not a shape this scans further
        after = close_idx + 1
        quoted = m.group("q") == '"'
        if quoted:
            if after < len(text) and text[after] == '"':
                after += 1
            else:
                continue      # opened quoted, never closed -- malformed, skip
        inner = text[open_idx + 1:close_idx]

        guard_form = _guard_form(text, m.start("var"), after, inner)

        sites.append(CaptureSite(
            file=file,
            line=_line_of(text, m.start("var")),
            variable=m.group("var"),
            subcommand=m.group("subcommand"),
            guard_form=guard_form,
            var_start=m.start("var"),
            after_stmt=after,
        ))
    return sites


def _guard_form(text, var_start, after, inner):
    prefix = text[max(0, var_start - 200):var_start]
    if prefix.rstrip().endswith("!") and re.search(r"\bif\b", prefix):
        return "if-negated"
    if re.match(r"[ \t]*\|\|(?!\|)", text[after:after + 40]):
        return "or-fallback"
    if _has_top_level_pipe(inner):
        return "pipeline"
    return "bare"


def _exit_helpers(text):
    """Locally-defined function names whose own body calls `exit`."""
    helpers = set()
    for m in _FUNC_DEF_RE.finditer(text):
        open_idx = text.find("{", m.end() - 1)
        if open_idx == -1:
            continue
        close_idx = _matching_brace(text, open_idx)
        if close_idx == -1:
            continue
        body = text[open_idx + 1:close_idx]
        if re.search(r"\bexit\b", body):
            helpers.add(m.group("name"))
    return helpers


def _matching_brace(text, open_idx):
    depth = 1
    i = open_idx + 1
    n = len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            if quote == '"' and c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < n:
            i += 2
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _bash_words(text, start, end):
    """(word, index) for every bare keyword-shaped word in text[start:end],
    skipping quoted strings and `#` comments -- a prose string containing
    "for" or "done" as an ordinary English word must not read as bash
    syntax (the #497-adjacent bug this module's own self-test caught:
    "reading the issue's label timeline **for** the pass-path..." inside a
    quoted `fail_infra_on_read` argument was mistaken for a `for` loop)."""
    i, n = start, end
    quote = None
    while i < n:
        c = text[i]
        if quote:
            if quote == '"' and c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "#":
            nl = text.find("\n", i, n)
            i = nl if nl != -1 else n
            continue
        if c.isalpha() or c == "_":
            m = _KEYWORD_RE.match(text, i, n)
            yield m.group(0), m.start()
            i = m.end()
            continue
        i += 1


def _block_end(text, start):
    """Index of the `fi`/`done`/`esac` closing the block that opened right
    before `start` (start is right after that block's own `then`/`do`)."""
    depth = 1
    for word, idx in _bash_words(text, start, len(text)):
        if word in _OPENERS:
            depth += 1
        elif word in _CLOSERS:
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _inside_loop(text, idx):
    depth = 0
    for word, _ in _bash_words(text, 0, idx):
        if word == "do":
            depth += 1
        elif word == "done":
            depth -= 1
    return depth > 0


def _classify_body(body, var, exit_helpers):
    m = re.search(r"(?<![\w.])" + re.escape(var) + r"\s*=(?!=)", body)
    if m:
        tail = re.match(r"[^\n;]*", body[m.end():]).group(0).strip()
        return Classification("reassigns", "{0}={1}".format(var, tail))
    exit_m = re.search(r"\bexit\b\s*\S*", body)
    if exit_m:
        return Classification("exits", exit_m.group(0).strip())
    for helper in exit_helpers:
        if re.search(r"\b" + re.escape(helper) + r"\b", body):
            return Classification("exits", helper)
    loop_m = re.search(r"\b(continue|break)\b", body)
    if loop_m:
        return Classification("loop-exits", loop_m.group(1))
    return None


def _exempt_marker(text, line):
    lines = text.split("\n")
    for idx in (line - 1, line - 2):
        if 0 <= idx < len(lines):
            m = EXEMPT_RE.search(lines[idx])
            if m:
                return (m.group(1) or "").strip()
    return None


def classify_failure_path(text, site):
    """research.md D5's four safe forms or `unsafe`, plus the `evidence`
    string surfaced in the gate's failure message."""
    exit_helpers = _exit_helpers(text)
    verdict = None

    if site.guard_form == "if-negated":
        then_m = re.match(r"\s*;?\s*then\b",
                          text[site.after_stmt:site.after_stmt + 200])
        if then_m:
            body_start = site.after_stmt + then_m.end()
            body_end = _block_end(text, body_start)
            if body_end != -1:
                body = text[body_start:body_end]
                verdict = _classify_body(body, site.variable, exit_helpers)
                if verdict and verdict.verdict == "loop-exits" and not \
                        _inside_loop(text, site.var_start):
                    verdict = None
    elif site.guard_form == "or-fallback":
        m = re.search(r"\|\|(?!\|)", text[site.after_stmt:site.after_stmt + 40])
        if m:
            fb_start = site.after_stmt + m.end()
            nl = text.find("\n", fb_start)
            fb_end = nl if nl != -1 else len(text)
            body = text[fb_start:fb_end]
            verdict = _classify_body(body, site.variable, exit_helpers)

    if verdict is not None:
        return verdict

    marker = _exempt_marker(text, site.line)
    if marker is not None:
        if marker:
            return Classification("opted-in", marker)
        return Classification("bare-marker", "")

    return Classification("unsafe", "")
