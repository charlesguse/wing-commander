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
import codecs
import re
import warnings
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


EXP = "\0"              # stands for one expansion in a word's _Word.pat
GH_WORD = re.compile(r"(?<![\w./$@:%-])gh(?![\w-])")
# A `gh` anywhere in a word that also holds a `${...}`: what such a word
# expands to cannot be proved (`${X:-gh}`, `${GH:-${HOME}/bin/gh}`,
# `${X:-gh}${Y:-}`), so as a command word it is a disallowed call (FR-006),
# even where it could never be `gh` (`${X##*/gh}`).
GH_IN_EXPANSION = re.compile(r"(?<![\w.$@%])gh(?![\w-])")
FUNCTION_NAME = re.compile(r"[ \t]+[^\s;&|()<>]")    # `function NAME`, not `function)`
TIME_GAP = re.compile(r"(?:[ \t]|\\\n)*")
ASSIGN = re.compile(r"[A-Za-z_]\w*(?:\[[^\]\n]*\])?\+?=")    # `a=`, `a+=`, `a[$k]=`
DECLARE = frozenset(("declare", "local", "typeset", "readonly", "export"))
# Brace expansion and globbing in a word: either can complete `gh`.
BRACE = re.compile(r"\{[^{}\s]*\}")                     # linear: no class overlaps `{`/`}`
GLOB = re.compile(r"\[(?:\[:[a-z]+:\]|[^\[\]/])+\]|[*?]")
CMD_SPLIT = re.compile(r"[\s;&|()=]+")
SHELL_FLAG = re.compile(r"-[A-Za-z]*[cS]")                # `-c`, `-lc`, `-S'...'`
SHELL_STRING = re.compile(r"-[A-Za-z]+")                  # with a c or S: a shell string
EVAL_SUBST = re.compile(r"\$\(|`")
CASE_WORD = re.compile(r"\bcase\b")
CMD_SEP = re.compile(r"[;&|()\n]+")
HEREDOC_DELIM = re.compile(r"\\?([^\s;&|<>()'\"`\\]+)")
VAR = re.compile(r"\$(?:[A-Za-z_]\w*|[0-9@*#?!$-])")
QUOTED_VAR = re.compile(r'"\$(?:\w+|\{\w+\})"')
NOT_ARITHMETIC = re.compile(r"[\"'`;\n]|\$\(")
MAX_DEPTH = 40          # of nested substitutions, well inside Python's recursion limit
CLOSERS = frozenset(("fi", "done", "esac"))
RESERVED = frozenset(("if", "then", "elif", "else", "do", "while", "until", "!", "{",
                      "}", "time"))
WRAPPERS = frozenset(("env", "eval", "command", "exec", "sudo", "xargs", "nohup",
                      "nice", "stdbuf", "watch", "setsid", "timeout", "script",
                      "coproc", "builtin", "flock", "ionice", "taskset", "chrt", "doas",
                      "time"))                # `X=1 time gh`: /usr/bin/time, not the keyword
SHELL_RUNNERS = frozenset(("eval", "watch", "script"))     # run their words as a shell string
SHELLS = frozenset(("bash", "sh", "dash", "zsh", "ksh", "su"))  # with `-c`, run one
API_VALUED = frozenset(("-X", "--method", "-H", "--header", "-f", "--raw-field", "-F",
                        "--field", "-q", "--jq", "-t", "--template", "-p", "--preview",
                        "--hostname", "--input", "--cache"))
API_ATTACHED = re.compile(r"-(?:[HfFqtp]|-(?:header|raw-field|field|jq|template|"
                          r"preview|hostname|input|cache)=)")


class _Word:
    __slots__ = ("raw", "lit", "off", "plain", "skel", "pre", "split", "toks", "pat")

    def __init__(self, raw, lit, off, plain, skel, pre, split, toks=range(0), pat=""):
        self.raw, self.lit, self.off, self.plain = raw, lit, off, plain
        self.skel, self.pre, self.split = skel, pre, split
        self.toks = toks                # indexes of the tokens its own text holds
        self.pat = pat                  # its literal text with EXP for each expansion

    def argv(self):
        if self.lit is not None:
            return self.lit
        w = Dynamic(self.raw)
        w.pre, w.split = self.pre, self.split
        return w


class _Ctx:
    """One command list: the script itself, or a substitution inside it.
    `forced` is the reason every call here is disallowed (inside `${...}`);
    `pattern` is 1 where a case pattern may start and 2 inside one; its
    words run nothing."""
    __slots__ = ("depth", "first", "cases", "parens", "start", "forced", "pattern")

    def __init__(self, depth, start, forced=None):
        self.depth, self.first, self.cases, self.parens, self.start, self.forced = (
            depth, depth > 0, 0, 0, start, forced)
        self.pattern = 0


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
        why = "backtick" if j < self.n else "unterminated-quote"
        self._mark(self.t[i + 1:j], i + 1, why)
        self._commands_in(self.t[i + 1:j], i + 1, why, False)
        return min(j + 1, self.n)

    def _commands_in(self, text, base, why, data):
        """Note a disallowed call at `base` when a command word in `text`,
        which this scanner does not parse (a backtick body, or with `data`
        the `$(...)`/backtick spans of an unquoted heredoc body), could be
        `gh` without being the word `gh` (`${X:-g}h`, `g$X`)."""
        if GH_WORD.search(text) is None and _text_may_run_gh(
                text, False, braced="${" in text, spans=data):
            self._note(base, "call", position="disallowed", reason=why)

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
        prefix before the first expansion or None, index after, the literal
        text with EXP in place of each expansion).

        A double-quoted span's text is a mention unless it holds a command
        substitution. A `${...}` span's text is data and a substitution in it
        a disallowed form (the authoring rule); a lone `'` there could be a
        quote or text depending on the quoting around the expansion, so it
        makes everything after unprovable."""
        t, n, dq = self.t, self.n, close == '"'
        if not dq:
            if self.braces >= MAX_DEPTH:
                self._unsure(i, "nested-expansion")
                return "", None, n, ""
            self.braces += 1
            ctx = _Ctx(ctx.depth, i, "param-expansion")
        j = start = i + 2 - dq
        segs, buf, first, sub, pat = [], [], None, False, []
        while j < n and t[j] != close:
            c, nx = t[j], t[j + 1:j + 2]
            if c == "\\" and dq and t.startswith("${{", j + 1):
                j += 1
            elif c == "\\":
                buf.append(nx if nx in ("$", "`", '"', "\\") else c + nx)
                pat.append(buf[-1])
                j += 2
            elif c == "'" and not dq:
                self._unsure(j, "unparsed-expansion")
                j += 1
            elif c in '`"' or (c == "$" and (nx in ("(", "{") or dq and VAR.match(t, j))):
                first = "".join(buf) if first is None else first
                segs.append((start, j))
                sub |= c == "`" or (nx == "(" and not t.startswith("((", j + 1))
                pat.append(EXP)
                j = (self._backtick(j) if c == "`" else self._span(j, ctx, c)[2]
                     if c == '"' else self._dollar(j, ctx))
                start = j
            else:
                buf.append(c)
                pat.append(c)
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
        return "".join(buf), first, min(j + 1, n), "".join(pat)

    # ---------------------------------------------------------------- words
    def _word(self, i, ctx):
        t, n, s, tok0 = self.t, self.n, i, len(self.toks)
        lit, pre, split, quoted, pat = [], None, False, False, []
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
                pat.append(lit[-1])
                i, quoted = i + 2, True
            elif c == "'":
                j = self._close(i, False)
                self._mark(t[i + 1:j], i + 1, "unterminated-quote" if j >= n else "quoted",
                           call=j >= n)
                lit.append(t[i + 1:j])
                pat.append(lit[-1])
                i, quoted = min(j + 1, n), True
            elif c == '"':
                text, p, i, qpat = self._span(i, ctx, '"')
                if p is not None and pre is None:
                    pre = "".join(lit) + p
                lit.append(text)
                pat.append(qpat)
                quoted = True
            elif c == "$" and t[i + 1:i + 2] == '"':          # `$"..."`: a locale string
                i += 1
            elif c == "`" or (c == "$" and (t[i + 1:i + 2] in ("(", "'", "{")
                                            or VAR.match(t, i))):
                pre = "".join(lit) if pre is None else pre
                ansi = c == "$" and t[i + 1:i + 2] == "'"
                split |= not ansi
                j = self._backtick(i) if c == "`" else self._dollar(i, ctx)
                pat.append(_ansi_c(t[i + 2:j - 1]) if ansi else EXP)
                i = j
            else:
                lit.append(c)
                pat.append(c)
                i += 1
        word = _Word(t[s:i], None if pre is not None else "".join(lit), s,
                     not quoted and pre is None, "".join(lit), pre or "", split,
                     range(tok0, len(self.toks)), "".join(pat))
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
                    if not quoted:
                        self._commands_in(t[body:e - len(line)], body, "unquoted-heredoc", True)
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
            elif ctx.pattern and (c in ";&" or c == "\n" and ctx.pattern == 2):
                self._unsure(i, "case-pattern")                # a pattern cut short
                ctx.pattern = 0
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
            elif (c == "(" and words and ASSIGN.fullmatch(words[-1].raw)
                  and words[-1].off + len(words[-1].raw) == i
                  and (words[0].lit in DECLARE or ASSIGN.match(words[0].raw))):
                w = words[-1]                                  # `a=(...)`: data, not commands
                i = self._data(i + 1, ctx, False)
                words[-1] = _Word(t[w.off:i], None, w.off, False, w.skel, w.pre, True,
                                  w.toks, w.pat + EXP)
            elif ctx.pattern and c in "|(":                   # `a|b)`, `(a)`
                ctx.pattern, i = 2, i + 1
            elif c == ";" and ctx.cases and t[i:i + 2] in (";;", ";&"):
                self._end(words, ctx)                          # an arm ends: a pattern next
                words, ctx.pattern = [], 1
                i += 2 + (t[i:i + 3] == ";;&")
            elif c in ";&|(":                                  # `((` may be arithmetic
                j = c == "(" and not words and t.startswith("((", i) and self._arithmetic(i, 2)
                if not j:
                    self._end(words, ctx)
                    ctx.parens += c == "("
                words, i = [], j or i + 1
            elif c == ")" and ctx.pattern:                     # a case pattern's `)`
                ctx.pattern, words, i = 0, [], i + 1
            elif c == ")":
                if ctx.parens or not ctx.cases:                # else a case pattern's `)`
                    self._end(words, ctx)
                    if ctx.depth and not ctx.parens:
                        return i + 1
                    ctx.parens = max(ctx.parens - 1, 0)
                words, i = [], i + 1
            else:
                w, i = self._word(i, ctx)
                if ctx.pattern or (w.plain and w.lit == "in" and len(words) > 1
                                   and words[0].plain and words[0].lit == "case"):
                    if not ctx.pattern or ctx.pattern == 1 and w.plain and w.lit == "esac":
                        ctx.first = False                      # the case is a command
                    if ctx.pattern == 1 and w.plain and w.lit == "esac":
                        ctx.cases, ctx.pattern = max(0, ctx.cases - 1), 0
                    else:
                        ctx.pattern = 2 if ctx.pattern else 1
                    continue
                lead = not words and w.plain and w.lit
                if lead == "[[" and not drop:                  # a test: data, not commands
                    self._end([w], ctx)
                    i = self._data(i, ctx, True)
                    continue
                if drop or (lead == "function" and FUNCTION_NAME.match(t, i)):
                    drop = not drop                            # `function NAME`: drop NAME
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

    def _data(self, i, ctx, test):
        """Index after the list of operand words at i that closes with `]]`
        (`test`, a `[[` test, whose `(`, `|` and `<` are operands too) or
        with `)` (an array assignment's list). Only expansions in its words
        are read. A list this cannot read to its close (unterminated, or cut
        by an operator, where reading goes on as commands) is unprovable:
        each `gh` in its words, and every one after it, is a disallowed call.
        Nothing is read twice, so this stays linear."""
        t, n, start, words = self.t, self.n, i, []
        while i < n and (test or t[i] != ")"):
            c = t[i]
            if c == "\n":
                i = self._heredocs(i + 1)               # a `$(cat <<E)` word opened one
            elif c in " \t" or (c == "\\" and t[i + 1:i + 2] == "\n"):
                i += 1 + (c == "\\")
            elif test and c in "<>" and t[i + 1:i + 2] == "(":
                i = self._nest(i, ctx)                  # `<(...)` runs even in a test
            elif test and c in "()|&<>!":
                i += 1
            elif not test and c == "#" and t[i - 1] in " \t\n(":
                j = t.find("\n", i)
                j = n if j < 0 else j
                self._mark(t[i:j], i, "comment", call=False)
                i = j
            else:
                w, j = self._word(i, ctx)
                if j == i:                              # an operator: no list after all
                    break
                i = j
                if test and w.plain and w.lit == "]]":
                    return i
                words.append(w)
        else:
            if i < n:
                return i + 1                            # the array's `)`
        why = "unterminated-test" if test else "unparsed-array"
        for w in words:
            noted = {self.toks[k].offset for k in w.toks}
            for m in GH_WORD.finditer(w.raw):
                if w.off + m.start() not in noted:
                    noted.add(w.off + m.start())
                    self._note(w.off + m.start(), "call", position="disallowed", reason=why)
            if not noted and (_gh_in_expansion(w) or _may_run_gh(w, True)):
                self._note(w.off, "call", position="disallowed", reason=why)
        self._unsure(start, why)
        return i

    def _end(self, words, ctx):
        """A simple command ended: is it a `gh` call, and in what position?"""
        if not words:
            return
        was_first, ctx.first = ctx.first, False
        k = 0
        while k < len(words) and ASSIGN.match(words[k].raw):
            k += 1
        tokens = [w.raw[9:] for w in words[:k] if w.raw.startswith("GH_TOKEN=")]
        prefix = (tokens or [None])[-1]
        odd_prefix = len(tokens) < k or any("=(" in w.raw for w in words[:k])
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
        elif _may_run_gh(head, True, True) and self._note_once(
                head, "gh-by-path" if head.lit is not None and
                EXP not in GLOB.sub(EXP, BRACE.sub(_unknown_braces, head.lit))
                else "dynamic-command"):
            pass                                        # else its arguments are read below
        elif (head.lit is None                         # `$SUDO gh`: may expand to nothing
              or _base(head.lit) in WRAPPERS and not (
                  head.lit == "command" and any(w.lit in ("-v", "-V") for w in words[k + 1:]))):
            why = "dynamic-command" if head.lit is None else "unquoted-wrapper"
            args = words[k + 1:]
            run = _wrapped_commands(args)
            # A literal wrapper may take operands before the command (`flock
            # FILE`, `timeout 5s`), so any of its words may be the command; a
            # dynamic command word's own arguments are not. eval, and a
            # wrapper or shell given a shell string, re-read their words.
            every = head.lit is not None
            evals = any(_base(w.lit) in SHELL_RUNNERS
                        or _shell_string(w.lit if w.lit is not None else w.pre)
                        for w in [head] + args)
            for w in args:
                if ("gh" in (w.lit, w.skel)
                        or (((every or w.off in run) and not ASSIGN.match(w.raw))
                            and _may_run_gh(w, True, w.off in run))
                        or _gh_in_expansion(w)
                        or (evals and _eval_may_run_gh(w))) and self._note_once(w, why):
                    break

        elif _base(head.lit) in SHELLS and any(
                _shell_string(w.lit if w.lit is not None else w.pre) for w in words[k + 1:]):
            for w in words[k + 1:]:                     # `bash -c '...'` re-reads it
                if _eval_may_run_gh(w) and self._note_once(w, "unquoted-wrapper"):
                    break

    def _note_once(self, w, reason):
        """A disallowed call at word `w`, unless its own text already holds one
        (`${X:+gh}` is marked inside the expansion). -> whether it noted one."""
        if any(self.toks[k].kind == "call" for k in w.toks):
            return False
        self._note(w.off, "call", position="disallowed", reason=reason)
        return True


def _base(s):
    """The last path segment of literal word text `s` ('' for None)."""
    return (s or "").rsplit("/", 1)[-1]


def _shell_string(s):
    """Whether literal word `s` hands a shell string over: `-c`, `-lc`,
    `-S...`, `--split-string`, `--command`."""
    s = s or ""
    return (s.startswith(("--split-string", "--command", "-S"))
            or (SHELL_STRING.fullmatch(s) is not None and "c" in s))


def _gh_in_expansion(w):
    """A word whose `${...}` text holds `gh` (`${X:-gh}`, `${D:-${H}/bin/gh}`)."""
    raw = w.raw.replace("\\\n", "")                  # bash joins continuations first
    return w.lit is None and "${" in raw and GH_IN_EXPANSION.search(raw) is not None


def _ansi_c(body):
    """The value of `$'body'`, or two EXPs (an unknown that may be a whole
    command word) when it cannot be decoded here."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return codecs.decode(body.encode("latin-1", "backslashreplace"),
                                 "unicode_escape").split(EXP, 1)[0]   # bash stops at NUL
    except Exception:                               # never raise (contract 4)
        return EXP + EXP


def _unknown_braces(m):
    """A `{...}` holding `,` or `..` is a brace expansion: an unknown."""
    body = m.group(0)
    return EXP if "," in body or ".." in body else body


def _collapse_braces(p):
    """`p` with each outermost `{...}` that holds a `,` or `..` as one EXP."""
    out, depth, start = [], 0, 0
    for i, c in enumerate(p):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth:
            depth -= 1
            if depth == 0:
                body = p[start:i + 1]
                out.append(EXP if "," in body or ".." in body else body)
        elif depth == 0:
            out.append(c)
    if depth:                                       # unclosed: an unknown if a list
        body = p[start:]
        out.append(EXP if "," in body or ".." in body else body)
    return "".join(out)


def _variants(pat, limit=16):
    """`pat` with its `{a,b}` brace lists spelled out (at most `limit`
    variants; lists past that, and sequence braces, are EXP), then glob
    characters as EXP."""
    out, todo = [], [BRACE.sub(lambda m: EXP if ".." in m.group(0) or
                               m.group(0).count(",") >= limit else m.group(0), pat)]
    while todo:
        p = todo.pop()
        m = next((b for b in BRACE.finditer(p) if "," in b.group(0)), None)
        if m is None:
            out.append(GLOB.sub(EXP, p))
            continue
        alts = m.group(0)[1:-1].split(",")
        if len(out) + len(todo) + len(alts) > limit:     # the rest at once: linear
            out.append(GLOB.sub(EXP, BRACE.sub(_unknown_braces, _collapse_braces(p))))
            continue
        todo += [p[:m.start()] + alt + p[m.end():] for alt in alts]
    return out


def _pattern_may_be_gh(pat, head, braced):
    """Whether a word with literal text and EXP markers `pat` could be `gh`,
    or a path ending in `gh` (see _may_run_gh)."""
    if EXP not in pat:
        return pat == "gh" or ("/" in pat and pat.rsplit("/", 1)[-1] == "gh")
    tail = pat.rsplit(EXP, 1)[-1]
    if "/" in tail:
        return tail.rsplit("/", 1)[-1] == "gh"
    if tail not in ("", "h", "gh"):
        return False
    if pat.replace(EXP, ""):
        return True
    return head and (braced or pat.count(EXP) > 1)


def _may_run_gh(w, head, split=False):
    """Whether word `w` in command position could run `gh` though it is not
    the plain word `gh` (FR-006). Expansions, brace expansions and globs are
    unknowns (a brace list is spelled out, a `$'...'` decoded); the literal
    text after the last unknown decides. After a `/` it must be `gh`
    (`/usr/bin/gh`, `$HOME/bin/gh`); with no `/` it must be a suffix of `gh`
    that the unknown before it could complete (`${X:-g}h`, `g$X`,
    `$(printf g)h`, `{g,}h`, and `h$X`, which is `h/gh` when X is `/gh`). A
    word made only of unknowns counts at a command word (`head`) when it
    holds a `${...}` or more than one of them (`${CMD}`,
    `$(printf g)$(printf h)`), but not as a lone bare `$CMD`/`$(...)`: the
    scanner reads the `$(...)` inside `$(( $(...) ))` as a command word.
    With `split` (the word that runs), an unquoted expansion may also split
    into words whose first is `gh` (`${X}g` with X='gh '), so any literal
    text after it does not matter. Unprovable either way, so a disallowed
    call."""
    if _gh_in_expansion(w):
        return True
    if w.lit == "gh":                               # plain `gh`: a call, decided elsewhere
        return False
    if split and w.split and w.pat != EXP and "gh".startswith(_base(w.pre)):
        return True
    braced = "${" in w.raw or ("{" in w.pat and "," in w.pat)   # or a long brace list
    return any(_pattern_may_be_gh(p, head, braced) for p in _variants(w.pat))


def _eval_unknowns(text):
    """`text` with each `$name`, `${...}`, `$(...)` and backticked span (nested
    ones whole) as EXP, then the quotes and backslashes a second read drops
    removed. One pass: each closer is found by counting its own brackets."""
    out, i, n = [], 0, len(text)
    while i < n:
        c, nx = text[i], text[i + 1:i + 2]
        if c == "$" and nx == "'":                   # `$'...'`: its decoded value
            j = text.find("'", i + 2)
            j = n if j < 0 else j
            out.append(_ansi_c(text[i + 2:j]))
            i = j + 1
        elif c == "$" and nx == '"':                 # `$"..."`: a quoted string
            i += 1
        elif c == "$" and nx in ("{", "("):
            d, j = 0, i + 1
            while j < n:
                d += (text[j] == nx) - (text[j] == ("}" if nx == "{" else ")"))
                j += 1
                if d == 0:
                    break
            out.append(EXP)
            i = j
        elif c == "$" and nx and (nx.isalnum() or nx in "_@*#?!$-"):
            j = i + 2
            if nx.isalpha() or nx == "_":
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
            out.append(EXP)
            i = j
        elif c == "`":
            j = text.find("`", i + 1)
            out.append(EXP)
            i = n if j < 0 else j + 1
        else:
            out.append("" if c in "\\'\"" else c)
            i += 1
    return "".join(out)


def _eval_may_run_gh(w):
    """eval (and a wrapper or shell handed a shell string) re-reads its words
    as shell, so each command-like piece of one is judged as a command word
    (`eval "gh api x"`, `eval "g$X api"`, `eval "${GH} api"`)."""
    return _text_may_run_gh(w.pat, True, "${" in w.raw)


def _text_may_run_gh(text, every, braced=False, spans=False):
    """Whether shell `text`, read again, could run `gh` through a word that
    is not plainly `gh`: an expansion in it is an unknown, quotes and
    backslashes are dropped as a second read drops them, and a substitution
    is read both as an unknown and as the commands inside it. With `every`,
    each piece of it is judged as a command word (an eval string, where
    wrappers may hide the command); else the first word of each command, and
    every word after a wrapper, of `text` and of its substitutions (with
    `spans`, `text` is data and only its substitutions run)."""
    if every:
        texts = (text, EVAL_SUBST.sub(" ", text))
    else:
        texts = SUBST_SPANS(text) + ([] if spans else [text])
    for t in texts:
        pat = _eval_unknowns(t)
        if every:
            pieces = CMD_SPLIT.split(pat)
        else:
            pieces = []
            for seg in CMD_SEP.split(pat):
                ws = [q for q in seg.split() if not ASSIGN.match(q)]
                while ws and ws[0] in RESERVED | CLOSERS:
                    ws.pop(0)
                pieces += ws if ws and _base(ws[0]) in WRAPPERS else ws[:1]
        pieces = [q for piece in pieces if piece
                  for q in (piece, SHELL_FLAG.sub("", piece, count=1)) if q]
        if any(_pattern_may_be_gh(p, True, braced or "{" in piece)
               for piece in pieces for p in _variants(piece)):
            return True
    return False


def SUBST_SPANS(text):
    """The bodies of the `$(...)` and backticked spans in `text`, nested ones
    included (to MAX_DEPTH levels)."""
    out, stack, tick, n, rest = [], [], None, len(text), False
    for i, c in enumerate(text):
        if c == "`":
            if tick is None:
                tick = i
            else:
                out.append(text[tick + 1:i])
                tick = None
        elif c == "(":
            stack.append(i if text[i - 1:i] == "$" and len(stack) < MAX_DEPTH else None)
        elif c == ")" and stack:
            start = stack.pop()
            if start is not None:                       # a case pattern's `)` may end
                body = text[start + 1:i]                # it early: then take the rest,
                if not rest and CASE_WORD.search(body):  # once (it holds every later one)
                    body, rest = text[start + 1:], True
                out.append(body)
    out += [text[s + 1:] for s in stack if s is not None]
    if tick is not None:
        out.append(text[tick + 1:])
    return out


def _wrapped_commands(args):
    """Offsets of the words a wrapper or a dynamic command word may run: the
    first word that is not an option, an assignment, a number or another
    wrapper, and before it any word straight after an option, which may be
    that option's value or, after a flag that takes none, the command."""
    out, after_opt = set(), False
    for w in args:
        s = w.lit
        if ASSIGN.match(w.raw) or (s is not None and (
                s.isdigit() or _base(s) in WRAPPERS)):
            after_opt = False
            continue
        if s is not None and s.startswith("-"):
            after_opt = True
            continue
        out.add(w.off)
        if not after_opt:
            break
        after_opt = False
    return out


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
