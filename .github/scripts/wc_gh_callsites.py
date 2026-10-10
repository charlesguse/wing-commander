#!/usr/bin/env python3
"""The one place that finds `gh` call sites in a shell `run:` block.

`locate(script)` returns every `gh` word the shell could run or that merely
mentions it, in source order. A token is a `mention` only where it can be
proved to be inert text (FR-004 of specs/113-gh-callsite-locator): inside a
quoted span holding no `$(` or backtick, inside a quoted-delimiter heredoc
body, or in a comment. Everything else is a `call`, and a call outside the
authoring rule (CONTRIBUTING.md, "Authoring rule for `gh` call sites") is
`position == "disallowed"` with a `reason`. The scanner is one left-to-right
pass with no re-slicing (linear in the script), never raises, and models only
what it must to fail closed: it notices case arms, ANSI-C strings, backticks
and complex `${...}` rather than parsing them, and once it meets a construct
it cannot track exactly, every `gh` after it is a disallowed call.

`api_parts(argv)` reads a `gh api` call's path word and method flags from the
located argv, so no consumer needs a tokeniser of its own (contracts/
locator-api.md).
"""
import bisect
import re
from dataclasses import dataclass, field


class Dynamic(str):
    """An argv word holding an expansion; the str value is its raw source."""
    pre = ""            # the literal text before its first expansion
    split = False       # an unquoted expansion: the shell may split it into words


@dataclass
class Token:
    kind: str                       # "call" | "mention"
    line: int                       # 1-based within the run: block
    offset: int
    position: str = None            # call: "statement" | "subst_first" | "disallowed"
    reason: str = None
    mention_clause: str = None      # "quoted" | "quoted-heredoc" | "comment"
    prefix_token: str = None        # raw value of a GH_TOKEN=<word> prefix
    timeout: bool = False
    argv: list = field(default_factory=list)


GH_WORD = re.compile(r"(?<![\w./$@:%-])gh(?![\w-])")
# A `gh` anywhere in a word that also holds a `${...}`: what such a word
# expands to cannot be proved (`${X:-gh}`, `${GH:-${HOME}/bin/gh}`,
# `${X:-gh}${Y:-}`), so as a command word it is a disallowed call (FR-006),
# even where it could never be `gh` (`${X##*/gh}`).
GH_IN_EXPANSION = re.compile(r"(?<![\w.$@%])gh(?![\w-])")
TIME_GAP = re.compile(r"(?:[ \t]|\\\n)*")
ASSIGN = re.compile(r"[A-Za-z_]\w*=")
HEREDOC_DELIM = re.compile(r"\\?([^\s;&|<>()'\"`\\]+)")
VAR = re.compile(r"\$(?:[A-Za-z_]\w*|[0-9@*#?!$-])")
QUOTED_VAR = re.compile(r'"\$(?:\w+|\{\w+\})"')
NOT_ARITHMETIC = re.compile(r"[\"'`;\n]|\$\(")
MAX_DEPTH = 40          # of nested substitutions, well inside Python's recursion limit
RESERVED = frozenset(("if", "then", "elif", "else", "do", "while", "until", "!", "{",
                      "}", "time"))
WRAPPERS = frozenset(("env", "eval", "command", "exec", "sudo", "xargs", "nohup",
                      "nice", "stdbuf", "watch", "setsid", "timeout", "script",
                      "coproc"))
API_VALUED = frozenset(("-X", "--method", "-H", "--header", "-f", "--raw-field", "-F",
                        "--field", "-q", "--jq", "-t", "--template", "-p", "--preview",
                        "--hostname", "--input", "--cache"))
API_ATTACHED = re.compile(r"-(?:[HfFqtp]|-(?:header|raw-field|field|jq|template|"
                          r"preview|hostname|input|cache)=)")


class _Word:
    __slots__ = ("raw", "lit", "off", "plain", "skel", "pre", "split", "toks")

    def __init__(self, raw, lit, off, plain, skel, pre, split, toks=range(0)):
        self.raw, self.lit, self.off, self.plain = raw, lit, off, plain
        self.skel, self.pre, self.split = skel, pre, split
        self.toks = toks                # indexes of the tokens its own text holds

    def argv(self):
        if self.lit is not None:
            return self.lit
        w = Dynamic(self.raw)
        w.pre, w.split = self.pre, self.split
        return w


class _Ctx:
    """One command list: the script itself, or a substitution inside it.
    `forced` is the reason every call here is disallowed (inside `${...}`)."""
    __slots__ = ("depth", "first", "cases", "parens", "start", "forced")

    def __init__(self, depth, start, forced=None):
        self.depth, self.first, self.cases, self.parens, self.start, self.forced = (
            depth, depth > 0, 0, 0, start, forced)


class _Scan:
    def __init__(self, text):
        self.t, self.n = text, len(text)
        self.toks, self.pending, self.broken = [], [], None
        self.nl = [i for i, c in enumerate(text) if c == "\n"]
        self.no_expr = None                   # offset of the first unclosed `${{`
        self.braces = 0                       # `${...}` levels open right now

    # ---------------------------------------------------------------- tokens
    def _note(self, off, kind, **kw):
        self.toks.append(Token(kind=kind, line=bisect.bisect_left(self.nl, off) + 1,
                               offset=off, **kw))

    def _mark(self, text, base, why, call=True):
        """Note each `gh` in `text` (at `base`): a disallowed call for reason
        `why`, or with call=False a mention in clause `why`."""
        kw = {"position": "disallowed", "reason": why} if call else {"mention_clause": why}
        for m in GH_WORD.finditer(text):
            self._note(base + m.start(), "call" if call else "mention", **kw)

    def _unsure(self, off, reason):
        """A construct this scanner cannot track exactly: nothing after it is
        provable, so every later `gh` is a disallowed call."""
        if self.broken is None or off < self.broken[0]:
            self.broken = (off, reason)

    # ----------------------------------------------------------- span helpers
    def _close(self, i, esc):
        """Index of the character closing the quote t[i] opens, or n when
        unterminated; with `esc`, a backslash escapes the next character."""
        t, n, j = self.t, self.n, i + 1
        while j < n and t[j] != t[i]:
            j += 2 if esc and t[j] == "\\" else 1
        return min(j, n)

    def _group(self, i, op, cl):
        """Index after the bracket matching the `op` at i, quotes skipped."""
        t, n, d = self.t, self.n, 0
        while i < n:
            c = t[i]
            if c in "\\'\"":
                i = (i + 2 if c == "\\" else
                     self._close(i, c == '"' or t[i - 1:i] == "$") + 1)
                continue
            d += (c == op) - (c == cl)
            i += 1
            if d == 0:
                return i
        return n

    def _backtick(self, i):
        j = self._close(i, True)
        self._mark(self.t[i + 1:j], i + 1, "backtick" if j < self.n else "unterminated-quote")
        return min(j + 1, self.n)

    def _expr_end(self, i):
        """Index after the Actions expression opening at i (`${{`), else None."""
        t, n, j = self.t, self.n, i + 3
        while self.no_expr is None and j < n:
            if t[j] == "'":                             # a string; '' escapes a quote
                j += 1
                while j < n and not (t[j] == "'" and t[j + 1:j + 2] != "'"):
                    j += 2 if t[j] == "'" else 1
            elif t.startswith("}}", j):
                return j + 2
            j += 1
        self.no_expr = i                                # no closer: later ones have none
        return None

    def _arithmetic(self, i, extra):
        """Index after `((...))` opening at i when it is plain arithmetic."""
        j = self._group(i, "(", ")")
        ok = self.t[j - 2:j] == "))" and not NOT_ARITHMETIC.search(self.t[i + extra:j - 2])
        return j if ok else None

    def _nest(self, i, ctx):
        """Index after the substitution opening at i, parsed one level deeper;
        nesting this deep is never real shell, so the rest is unprovable."""
        if ctx.depth >= MAX_DEPTH:
            self._unsure(i, "nested-substitution")
            return self.n
        return self._cmds(i + 2, _Ctx(ctx.depth + 1, i, ctx.forced))

    def _dollar(self, i, ctx):
        """Index after the `$` expansion at i."""
        t = self.t
        nxt = t[i + 1:i + 2]
        if nxt == "'":                                  # $'...' ANSI-C
            j = self._close(i + 1, True)            # unterminated: to the end
            self._mark(t[i + 2:j], i + 2, "ansi-c")
            return min(j + 1, self.n)
        if nxt == "(":
            j = self._arithmetic(i + 1, 2) if t.startswith("((", i + 1) else None
            return j or self._nest(i, ctx)
        if nxt == "{":
            end = self._expr_end(i) if t.startswith("{{", i + 1) else None
            return end or self._span(i, ctx, "}")[2]
        m = VAR.match(t, i)
        return m.end() if m else i + 1

    def _span(self, i, ctx, close):
        """Walk the `"..."` (close '"') or `${...}` (close '}') span at i,
        handing each expansion in it to its reader. -> (literal text, literal
        prefix before the first expansion or None, index after).

        A double-quoted span's text is a mention unless it holds a command
        substitution. A `${...}` span's text is data and a substitution in it
        a disallowed form (the authoring rule); a lone `'` there could be a
        quote or text depending on the quoting around the expansion, so it
        makes everything after unprovable."""
        t, n, dq = self.t, self.n, close == '"'
        if not dq:
            if self.braces >= MAX_DEPTH:
                self._unsure(i, "nested-expansion")
                return "", None, n
            self.braces += 1
            ctx = _Ctx(ctx.depth, i, "param-expansion")
        j = start = i + 2 - dq
        segs, buf, first, sub = [], [], None, False
        while j < n and t[j] != close:
            c, nx = t[j], t[j + 1:j + 2]
            if c == "\\" and dq and t.startswith("${{", j + 1):
                j += 1
            elif c == "\\":
                buf.append(nx if nx in ("$", "`", '"', "\\") else c + nx)
                j += 2
            elif c == "'" and not dq:
                self._unsure(j, "unparsed-expansion")
                j += 1
            elif c in '`"' or (c == "$" and (nx in ("(", "{") or dq and VAR.match(t, j))):
                first = "".join(buf) if first is None else first
                segs.append((start, j))
                sub |= c == "`" or (nx == "(" and not t.startswith("((", j + 1))
                j = (self._backtick(j) if c == "`" else self._span(j, ctx, c)[2]
                     if c == '"' else self._dollar(j, ctx))
                start = j
            else:
                buf.append(c)
                j += 1
        segs.append((start, min(j, n)))
        bad = not dq or j >= n or sub
        why = ("param-expansion" if not dq else "unterminated-quote" if j >= n
               else "quoted-substitution" if sub else "quoted")
        for a, b in segs:
            self._mark(t[a:b], a, why, call=bad)
        if not dq:
            if j >= n:
                self._unsure(i, "unterminated-expansion")
            self.braces -= 1
        return "".join(buf), first, min(j + 1, n)

    # ---------------------------------------------------------------- words
    def _word(self, i, ctx):
        t, n, s, tok0 = self.t, self.n, i, len(self.toks)
        lit, pre, split, quoted = [], None, False, False
        while i < n:
            c = t[i]
            if c in " \t\n;&|()<>":
                break
            if c == "\\":
                # A line continuation, or `\${{` escaping the value GitHub puts there.
                if t[i + 1:i + 2] == "\n" or t.startswith("${{", i + 1):
                    i += 1 + (t[i + 1:i + 2] == "\n")
                    continue
                lit.append(t[i + 1:i + 2])
                i, quoted = i + 2, True
            elif c == "'":
                j = self._close(i, False)
                self._mark(t[i + 1:j], i + 1, "unterminated-quote" if j >= n else "quoted",
                           call=j >= n)
                lit.append(t[i + 1:j])
                i, quoted = min(j + 1, n), True
            elif c == '"':
                text, p, i = self._span(i, ctx, '"')
                if p is not None and pre is None:
                    pre = "".join(lit) + p
                lit.append(text)
                quoted = True
            elif c == "`" or (c == "$" and (t[i + 1:i + 2] in ("(", "'", "{")
                                            or VAR.match(t, i))):
                pre = "".join(lit) if pre is None else pre
                split |= not (c == "$" and t[i + 1:i + 2] == "'")
                i = self._backtick(i) if c == "`" else self._dollar(i, ctx)
            else:
                lit.append(c)
                i += 1
        word = _Word(t[s:i], None if pre is not None else "".join(lit), s,
                     not quoted and pre is None, "".join(lit), pre or "", split,
                     range(tok0, len(self.toks)))
        return word, i

    # ------------------------------------------------------------- heredocs
    def _heredocs(self, i):
        """Consume the bodies of the heredocs opened on the line just ended."""
        t, n = self.t, self.n
        while self.pending and i < n:
            delim, quoted, strip = self.pending.pop(0)
            body = i
            while i < n:
                e = t.find("\n", i)
                e = n if e < 0 else e
                line, i = t[i:e], min(e + 1, n)
                if (line.lstrip("\t") if strip else line) == delim:
                    self._mark(t[body:e - len(line)], body, ("quoted-heredoc" if quoted
                                                             else "unquoted-heredoc"), call=not quoted)
                    break
            else:
                self._mark(t[body:n], body, "unterminated-heredoc")
                return n
        if i >= n:
            self.pending.clear()
        return i

    def _redirect(self, i, ctx):
        """-> (index after the operator, whether a target word follows)."""
        t = self.t
        if t.startswith("<<<", i):
            return i + 3, True
        if t.startswith("<<", i):
            j = i + 2
            strip = t[j:j + 1] == "-"
            j += strip
            while t[j:j + 1] in (" ", "\t"):
                j += 1
            if t[j:j + 1] in ("'", '"'):
                k = self._close(j, False)
                self.pending.append((t[j + 1:k], True, strip))
                return k + 1, False
            m = HEREDOC_DELIM.match(t, j)
            if m:
                self.pending.append((m.group(1), t[j] == "\\", strip))
                return m.end(), False
            return j, False
        if t[i + 1:i + 2] == "(":                       # <( ) reads like $( )
            return self._nest(i, ctx), False
        return i + 1 + (t[i + 1:i + 2] in (">", "&", "|")), True

    # ------------------------------------------------------------- commands
    def _cmds(self, i, ctx):
        t, n = self.t, self.n
        words, drop, timed = [], False, None
        while i < n:
            c = t[i]
            if c in " \t" or (c == "\\" and t[i + 1:i + 2] == "\n"):
                i += 1 + (c == "\\")
            elif c == "\n":
                self._end(words, ctx)
                words, i = [], self._heredocs(i + 1)
            elif c == "#":
                j = t.find("\n", i)
                j = n if j < 0 else j
                self._mark(t[i:j], i, "comment", call=False)
                i = j
            elif c == "&" and t[i + 1:i + 2] == ">" or c in "<>":
                i, drop = self._redirect(i + (c == "&"), ctx)
            elif c in ";&|(":                                  # `((` may be arithmetic
                j = c == "(" and not words and t.startswith("((", i) and self._arithmetic(i, 2)
                if not j:
                    self._end(words, ctx)
                    ctx.parens += c == "("
                words, i = [], j or i + 1
            elif c == ")":
                if ctx.parens or not ctx.cases:                # else a case pattern's `)`
                    self._end(words, ctx)
                    if ctx.depth and not ctx.parens:
                        return i + 1
                    ctx.parens = max(ctx.parens - 1, 0)
                words, i = [], i + 1
            else:
                w, i = self._word(i, ctx)
                lead = not words and w.plain and w.lit
                if drop or lead == "function":                 # `function NAME`: drop NAME
                    drop = not drop
                    continue
                if lead in ("case", "esac"):
                    ctx.cases = max(0, ctx.cases + (1 if lead == "case" else -1))
                if (lead and lead[0] == "-" and timed is not None   # `time -p gh`
                        and TIME_GAP.fullmatch(t, timed, w.off)):
                    timed = i
                    continue
                timed = i if lead == "time" else None
                if lead not in RESERVED:
                    words.append(w)
        self._end(words, ctx)
        if ctx.depth:
            self._unsure(ctx.start, "unterminated-substitution")
        return n

    def _end(self, words, ctx):
        """A simple command ended: is it a `gh` call, and in what position?"""
        if not words:
            return
        was_first, ctx.first = ctx.first, False
        k = 0
        while k < len(words) and ASSIGN.match(words[k].raw):
            k += 1
        tokens = [w.raw[9:] for w in words[:k] if w.raw.startswith("GH_TOKEN=")]
        prefix, odd_prefix = (tokens or [None])[-1], len(tokens) < k
        timeout = (k + 1 < len(words) and words[k].lit == "timeout"
                   and not words[k + 1].raw.startswith("-"))
        k += 2 * timeout
        if k >= len(words):
            return
        head = words[k]
        if head.lit == "gh" or head.skel == "gh":      # `$(:)gh`, `""gh`, `\`\`gh`
            argv = [w.argv() for w in words[k + 1:]]
            reason = (("unsupported-prefix" if odd_prefix else None)
                      or ("dynamic-command" if head.lit is None else None)
                      or ctx.forced
                      or ("case-arm" if ctx.depth and ctx.cases else None)
                      or ("nested-substitution" if ctx.depth > 1 else None)
                      or ("substitution-not-first" if ctx.depth and not was_first else None)
                      or _argv_reason(argv))
            self._note(head.off, "call", reason=reason, prefix_token=prefix,
                       timeout=timeout, argv=argv,
                       position=("disallowed" if reason else
                                 "subst_first" if ctx.depth else "statement"))
        elif _expands_to_gh(head):
            self._note_once(head, "dynamic-command")
        elif head.lit in WRAPPERS and not (head.lit == "command" and any(
                w.lit in ("-v", "-V") for w in words[k + 1:])):
            w = next((w for w in words[k + 1:]
                      if "gh" in (w.lit, w.skel) or _expands_to_gh(w)), None)
            if w:
                self._note_once(w, "unquoted-wrapper")

    def _note_once(self, w, reason):
        """A disallowed call at word `w`, unless its own text already holds one
        (`${X:+gh}` is marked inside the expansion)."""
        if not any(self.toks[k].kind == "call" for k in w.toks):
            self._note(w.off, "call", position="disallowed", reason=reason)


def _expands_to_gh(w):
    raw = w.raw.replace("\\\n", "")                  # bash joins continuations first
    return w.lit is None and "${" in raw and GH_IN_EXPANSION.search(raw) is not None


def _argv_reason(argv):
    """Why this call's subcommand, method or flags are not all literal, or None."""
    if not argv or isinstance(argv[0], Dynamic):
        return "variable-subcommand"
    if argv[0] == "api":
        _, methods, stray, _ = _api_scan(argv[1:])
        if stray is not None:
            return "dynamic-flag"
        if any(isinstance(m, Dynamic) for m in methods):
            return "variable-method"
    elif len(argv) > 1 and isinstance(argv[1], Dynamic) and not argv[1].startswith("-"):
        return "variable-subcommand"
    return None


def _api_scan(args):
    """-> (path word or None, [method words], first stray word or None,
    [flag words]).

    Every spelling gh accepts: `-X POST`, `-XPOST`, `-iX POST`, `--method POST`,
    `--method=POST`. A flag gh documents as taking a value consumes the next
    word, `--` makes the rest positional, any other dashed word is a switch.
    The flag words are the dashed words in flag position, so a flag-looking
    value (`-H -f`) is never one. A stray word is one holding an expansion
    the shell may split into several words, or one that may expand to a
    flag: either could hide a method."""
    path, methods, stray, flags = None, [], None, []
    i, n, rest = 0, len(args), False

    def strays(w, is_value):
        if not isinstance(w, Dynamic):
            return False
        if path is None and QUOTED_VAR.fullmatch(str(w)):
            return False            # a quoted variable as the PATH: the gate resolves it
        flag_proof = w.pre and (not w.pre.startswith("-") or API_ATTACHED.match(w.pre))
        return w.split or not (is_value or flag_proof)

    while i < n:
        w = args[i]
        s = str(w)
        i += 1
        if strays(w, False):
            stray = stray if stray is not None else w
            continue
        if rest or not s.startswith("-") or s == "-":
            path = path if path is not None else w
            continue
        if s == "--":
            rest = True
            continue
        flags.append(s)
        m = re.fullmatch(r"-i*X(.*)", s)
        if s in API_VALUED or (m and not m.group(1)) or re.fullmatch(r"-i+[HfFqtp]", s):
            if i < n:
                if strays(args[i], True):
                    stray = stray if stray is not None else args[i]
                if s in ("-X", "--method") or m:
                    methods.append(args[i])
            i += 1
        elif m:
            methods.append(type(w)(m.group(1)))
        elif s.startswith("--method="):
            methods.append(type(w)(s[9:]))
    return path, methods, stray, flags


def api_parts(args):
    """-> (path word or None, [method words]) for the words after `gh api`."""
    return _api_scan(args)[:2]


def api_flags(args):
    """The dashed words in flag position among the words after `gh api`."""
    return _api_scan(args)[3]


def run_blocks(path):
    """[(1-based line the run: text starts on, text)] for every `run:` scalar
    in the workflow or composite-action YAML at `path`."""
    import yaml
    out = []

    def walk(node):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                if getattr(k, "value", None) == "run" and isinstance(v, yaml.ScalarNode):
                    out.append((v.start_mark.line + 1 + (v.style in ("|", ">")), v.value))
                else:
                    walk(v)
        elif isinstance(node, yaml.SequenceNode):
            for v in node.value:
                walk(v)

    with open(path, encoding="utf-8") as fh:
        walk(yaml.compose(fh))
    return out


def locate(script):
    """Every `gh` word in `script`, in source order (see the module doc)."""
    sc = _Scan(script)
    sc._cmds(0, _Ctx(0, 0))
    toks = sorted(sc.toks, key=lambda x: x.offset)
    if sc.broken is not None:
        for tok in toks:
            if tok.offset >= sc.broken[0] and tok.position != "disallowed":
                tok.kind, tok.position, tok.reason, tok.mention_clause = (
                    "call", "disallowed", sc.broken[1], None)
    return toks
