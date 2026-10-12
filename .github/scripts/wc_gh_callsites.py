#!/usr/bin/env python3
"""The one place that finds `gh` call sites in a shell `run:` block.

`locate(script)` returns every `gh` word in the script, in source order. A
token is a `mention` only where it can be proved to be inert text (FR-004 of
specs/113-gh-callsite-locator): inside a quoted span holding no `$(` or
backtick, inside a quoted-delimiter heredoc body no shell reads, or in a
comment. Everything else is a `call`, and a call outside the authoring rule
(CONTRIBUTING.md, "Authoring rule for `gh` call sites") is
`position == "disallowed"` with a `reason`.

The rule is strict so that this reader can stay small (the owner's option
(c) on #993, 2026-10-12): it never reads inside a string or stream a shell
or evaluator runs (`sh -c`, `eval`, `trap`, `ssh`, a backtick, a heredoc or
pipe fed to a shell); every `gh` in one is a disallowed call. A command word
that is a variable or expansion is a disallowed call wherever the script
holds a `gh` that is neither a located call nor a provable mention. The
scanner is one left-to-right pass with no re-slicing (linear in the script)
and never raises; once it meets a construct it cannot track exactly, every
`gh` after it is a disallowed call.

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


EXP = "\0"              # stands for one expansion in a word's _Word.pat
GH = re.compile(r"(?<![\w$@%-])gh(?![\w-])")          # the word gh, `/usr/bin/gh` too
# A `gh` anywhere in a word that also holds a `${...}` (`${X:-gh}`): what it
# expands to cannot be proved, so as a command word it is disallowed.
GH_IN_EXPANSION = re.compile(r"(?<![\w.$@%])gh(?![\w-])")
# In text a shell runs, gh as a word or spelled across quotes or an
# expansion: `g""h`, `g\\h`, `g$X`, `${X:-g}h`, `$(printf g)h`, `${X:-gh}`.
SPELLED = re.compile(r"(?<![\w$@%])g(?:[\"'\\]*h(?![\w-])|[\"'\\]*[$`])"
                     r"|(?:[})`]|\$\w+[\"'\\])[\"'\\]*h(?![\w-])")
BLANK_WORD = re.compile(r"[^ \t\n]+")
# `<<` or `<<-`, then the delimiter word; an unterminated quote ends it.
HEREDOC = re.compile(r"<<(-?)[ \t]*((?:'[^']*'|\"[^\"]*\"|\\.|[^\s;&|<>()`'\"\\])*)")
DELIM_PIECE = re.compile(r"'([^']*)'|\"([^\"]*)\"|\\(.)")
FUNCTION_NAME = re.compile(r"[ \t]+[^\s;&|()<>]")    # `function NAME`, not `function)`
TIME_GAP = re.compile(r"(?:[ \t]|\\\n)*")
ASSIGN = re.compile(r"[A-Za-z_]\w*(?:\[[^\]\n]*\])?\+?=")    # `a=`, `a+=`, `a[$k]=`
DECLARE = frozenset(("declare", "local", "typeset", "readonly", "export"))
GLOB = re.compile(r"\[(?:\[:[a-z]+:\]|[^\[\]/])+\]|[*?]")
SHELL_STRING = re.compile(r"-[A-Za-z]+")                  # with a c: a shell string
VAR = re.compile(r"\$(?:[A-Za-z_]\w*|[0-9@*#?!$-])")
NAMED_FD = re.compile(r"\{[A-Za-z_]\w*\}")
QUOTED_VAR = re.compile(r'"\$(?:\w+|\{\w+\})"')
NOT_ARITHMETIC = re.compile(r"[\"'`;\n]|\$\(")
MAX_DEPTH = 40          # of nested substitutions, well inside Python's recursion limit
RESERVED = frozenset(("if", "then", "elif", "else", "do", "while", "until", "!", "{",
                      "}", "time"))
# Programs that run another command given in their words; any of the words
# may be it. The list is closed, so the authoring rule says to call gh directly.
EVALUATORS = frozenset(("eval", "trap", "watch", "script", "ssh", "parallel", "source", "."))
WRAPPERS = frozenset(("env", "command", "exec", "sudo", "xargs", "nohup", "nice", "stdbuf",
                      "setsid", "timeout", "coproc", "builtin", "flock", "ionice", "taskset",
                      "chrt", "doas", "find", "docker", "podman", "kubectl", "chroot",
                      "nsenter", "unshare", "runuser", "sg", "strace", "busybox",
                      "time",                 # `X=1 time gh`: /usr/bin/time, not the keyword
                      )) | EVALUATORS
SHELLS = frozenset(("bash", "sh", "dash", "zsh", "ksh", "mksh", "ash", "yash", "posh",
                    "su"))                  # with `-c`, run a string


class _Word:
    __slots__ = ("raw", "lit", "off", "plain", "skel", "pre", "split", "pat")

    def __init__(self, raw, lit, off, plain, skel, pre, split, pat=""):
        self.raw, self.lit, self.off, self.plain = raw, lit, off, plain
        self.skel, self.pre, self.split = skel, pre, split
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
        # Where to look for gh: the text with each URL blanked (it names gh,
        # it never runs it).
        self.g = BLANK_WORD.sub(lambda m: " " * len(m.group()) if "://" in m.group()
                                else m.group(), text)
        self.by_off, self.pending, self.broken = {}, [], None
        self.nl = [i for i, c in enumerate(text) if c == "\n"]
        self.no_expr = None                   # offset of the first unclosed `${{`
        self.braces = 0                       # `${...}` levels open right now
        self.at = 0                           # where the command being ended stops
        self.bare = []                        # offsets of what runs a variable (locate())
        self.shell_stdin = False              # the heredocs now pending feed a shell
        self.fed = 0                          # text before it is condemned already

    # ---------------------------------------------------------------- tokens
    def _note(self, off, kind, **kw):
        """A token at `off`; a call replaces a mention there, and nothing
        replaces a disallowed call."""
        old = self.by_off.get(off)
        if old is None or kind == "call" and old.position != "disallowed":
            self.by_off[off] = Token(kind=kind, line=bisect.bisect_left(self.nl, off) + 1,
                                     offset=off, **kw)

    def _flag(self, off, why):
        """A disallowed call at `off` unless a comment or a located call is
        there. -> whether a disallowed call is there now."""
        old = self.by_off.get(off)
        if old is None or old.kind == "mention" and old.mention_clause != "comment":
            self._note(off, "call", position="disallowed", reason=why)
            return True
        return old.position == "disallowed"

    def _mark(self, a, b, why, call, spelled=False):
        """Each `gh` in t[a:b]: a disallowed call for reason `why` (with
        `spelled`, text a shell runs, also gh spelled across quotes or an
        expansion), or with call=False a mention in clause `why`."""
        for m in (SPELLED if spelled else GH).finditer(self.g, a, b):
            if call:
                self._flag(m.start(), why)
            else:
                self._note(m.start(), "mention", mention_clause=why)

    def _note_word(self, w, why):
        """Word `w` may run gh: each gh in it is a disallowed call, or the
        word itself is when it spells none."""
        hits = [self._flag(m.start(), why)
                for m in GH.finditer(self.g, w.off, w.off + len(w.raw))]
        if not any(hits):
            self._flag(w.off, why)

    def _condemn(self, start, why):
        """Text from `start` to the end of this command is a script a shell
        runs: every gh in it is a disallowed call, quoted or not."""
        self._mark(start, self.at, why, True, True)

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
        """A backtick is a string a shell runs: never read inside (the rule)."""
        j = self._close(i, True)
        self._mark(i + 1, j, "backtick" if j < self.n else "unterminated-quote", True, True)
        if "$" in self.t[i + 1:j]:
            self.bare.append(i)
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
            self._mark(i + 2, j, "ansi-c", True)
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
            self._mark(a, b, why, bad)
        if not dq:
            if j >= n:
                self._unsure(i, "unterminated-expansion")
            self.braces -= 1
        return "".join(buf), first, min(j + 1, n), "".join(pat)

    # ---------------------------------------------------------------- words
    def _word(self, i, ctx):
        t, n, s = self.t, self.n, i
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
                self._mark(i + 1, j, "unterminated-quote" if j >= n else "quoted", j >= n)
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
                i = self._backtick(i) if c == "`" else self._dollar(i, ctx)
                pat.append(EXP + EXP if ansi else EXP)      # `$'\x67h'`: never one word
            else:
                lit.append(c)
                pat.append(c)
                i += 1
        word = _Word(t[s:i], None if pre is not None else "".join(lit), s,
                     not quoted and pre is None, "".join(lit), pre or "", split, "".join(pat))
        return word, i

    # ------------------------------------------------------------- heredocs
    def _heredocs(self, i):
        """Consume the bodies of the heredocs opened on the line just ended."""
        t, n = self.t, self.n
        while self.pending and i < n:
            delim, quoted, strip = self.pending.pop(0)
            quoted = quoted and not self.shell_stdin      # a shell runs the body: not data
            body = i
            while i < n:
                e = t.find("\n", i)
                e = n if e < 0 else e
                line, i = t[i:e], min(e + 1, n)
                if (line.lstrip("\t") if strip else line) == delim:
                    end = e - len(line)
                    self._mark(body, end, "quoted-heredoc" if quoted else "unquoted-heredoc",
                               not quoted, not quoted)
                    if not quoted and "$" in t[body:end]:
                        self.bare.append(body)
                    break
            else:
                self._mark(body, n, "unterminated-heredoc", True)
                self.pending.clear()
                self.shell_stdin = False
                return n
        if i >= n:
            self.pending.clear()
        self.shell_stdin = bool(self.pending) and self.shell_stdin
        return i

    def _redirect(self, i, ctx):
        """-> (index after the operator, whether a target word follows)."""
        t = self.t
        if t.startswith("<<<", i):
            return i + 3, True
        m = HEREDOC.match(t, i)
        if m:
            # The delimiter may be quoted in part (`E"O"F`, `\EOF`): its text is
            # the pieces with quotes dropped, and any quoting makes the body data.
            word = m.group(2)
            if word:
                self.pending.append((DELIM_PIECE.sub(lambda p: "".join(p.groups("")), word),
                                     DELIM_PIECE.search(word) is not None, m.group(1) == "-"))
            return m.end(), False
        if t[i + 1:i + 2] == "(":                       # <( ) reads like $( )
            return self._nest(i, ctx), False
        return i + 1 + (t[i + 1:i + 2] in (">", "&", "|")), True

    # ------------------------------------------------------------- commands
    def _cmds(self, i, ctx):
        t, n = self.t, self.n
        words, drop, timed = [], False, None
        while i < n:
            c, self.at = t[i], i
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
                self._mark(i, j, "comment", False)
                i = j
            elif c == "&" and t[i + 1:i + 2] == ">" or c in "<>":
                i, drop = self._redirect(i + (c == "&"), ctx)
            elif (c == "(" and words and ASSIGN.fullmatch(words[-1].raw)
                  and words[-1].off + len(words[-1].raw) == i
                  and (words[0].lit in DECLARE or ASSIGN.match(words[0].raw))):
                w = words[-1]                                  # `a=(...)`: data, not commands
                i = self._data(i + 1, ctx, False)
                words[-1] = _Word(t[w.off:i], None, w.off, False, w.skel, w.pre, True,
                                  w.pat + EXP)
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
                words, i = [], j or i + 1 + t.startswith("|&", i)   # `|&` pipes too
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
                if (w.plain and (w.lit.isdigit() or NAMED_FD.fullmatch(w.lit))
                        and t[i:i + 1] in ("<", ">") and not ctx.pattern):
                    continue                                   # `2>file`, `{fd}>file`: a file descriptor
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
        self.at = i
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
                self._mark(i, j, "comment", False)
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
            if GH.search(self.g, w.off, w.off + len(w.raw)) or _may_be_gh(w):
                self._note_word(w, why)
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
        head, args = words[k], words[k + 1:]
        if _reads_stdin(words[k:]):    # its script arrives on stdin, from anything before it
            self._condemn(self.fed, "shell-stdin")
            self.fed = self.at
            self.shell_stdin = self.shell_stdin or bool(self.pending)
        if head.lit == "gh" or head.skel == "gh":      # `$(:)gh`, `""gh`, `\`\`gh`
            argv = [w.argv() for w in args]
            reason = (("unsupported-prefix" if odd_prefix else None)
                      or ("dynamic-command" if head.lit is None else None)
                      or ctx.forced
                      or ("case-arm" if ctx.depth and ctx.cases else None)
                      or ("nested-substitution" if ctx.depth > 1 else None)
                      or ("substitution-not-first" if ctx.depth and not was_first else None)
                      or _argv_reason(argv))
            m = GH.search(self.g, head.off, head.off + len(head.raw))
            self._note(m.start() if m else head.off, "call", reason=reason,
                       prefix_token=prefix, timeout=timeout, argv=argv,
                       position=("disallowed" if reason else
                                 "subst_first" if ctx.depth else "statement"))
            return
        base, dynamic = _base(head.lit), head.lit is None
        why = _may_be_gh(head)
        if why:
            self._note_word(head, why)
        elif head.pat == EXP:
            self.bare.append(head.off)                  # `$CMD`: see locate()
        if ((base == "command" and any(w.lit in ("-v", "-V") for w in args))
                or (base == "find" and not any((w.lit or "").startswith(("-exec", "-ok"))
                                               for w in args))
                or not (dynamic or base in WRAPPERS or base in SHELLS)):
            return
        if dynamic or any(_base(w.lit) in EVALUATORS or _shell_string(
                w.lit if w.lit is not None else w.pre) for w in [head] + args):
            self._condemn(head.off + len(head.raw),      # the head word is judged above
                          "dynamic-command" if dynamic else "unquoted-wrapper")
            self.bare.append(head.off)
            self.shell_stdin = self.shell_stdin or bool(self.pending)   # `eval "$(cat)" <<E`
        if base in SHELLS:
            return
        for w in args:                                  # any word may be the command
            if ASSIGN.match(w.raw) or (w.lit or "").startswith("-"):
                continue
            if "gh" in (w.lit, w.skel) or _may_be_gh(w, False):
                self._note_word(w, "dynamic-command" if dynamic else "unquoted-wrapper")
            elif w.lit is None:
                self.bare.append(w.off)


def _reads_stdin(words):
    """Whether the command in `words` runs a script it reads from stdin: a
    shell given no `-c` string and no script file (`bash`, `bash -o
    pipefail`, `sudo bash -s`, `bash /dev/stdin`, `bash <(...)`), `su`,
    `ssh` or `sudo -s`/`-i` given no `-c` string, a leading `source`/`.` of
    stdin or of a process substitution, or `xargs`/`parallel` handing what
    it reads to a shell or evaluator."""
    feeds = False
    for j, w in enumerate(words):               # stops at the first shell: linear
        rest, b = words[j + 1:], _base(w.lit)
        strings = any(_shell_string(r.lit if r.lit is not None else r.pre) for r in rest
                      ) if b in SHELLS or b in ("ssh", "sudo", "doas") else None
        if w.lit in ("source", ".") and (j == 0 or words[j - 1].lit in ("builtin", "command")):
            return not rest or _dev_file(rest[0])
        if b in ("xargs", "parallel"):
            feeds = True
        elif feeds and (b in SHELLS or b in EVALUATORS):
            return True
        elif b in SHELLS and b != "su":
            ops = [r for k, r in enumerate(rest) if (r.lit is None or r.lit[:1] not in "-+")
                   and (k == 0 or rest[k - 1].lit not in ("-o", "-O", "+o", "+O"))]
            return not strings and (not ops or _dev_file(ops[0]) or
                                    any(r.lit == "-s" for r in rest))
        elif b in ("su", "ssh") or b in ("sudo", "doas") and _login_shell(rest):
            return not strings
    return False


def _login_shell(rest):
    """Whether sudo's options `rest` ask for a shell (`-s`, `-i`, `-is`)."""
    for k, r in enumerate(rest):
        if (r.lit or "").startswith("-"):
            if r.lit != "--" and r.lit[1:2] != "-" and ("s" in r.lit or "i" in r.lit):
                return True
        elif k == 0 or rest[k - 1].lit not in ("-u", "-g", "-U", "-C", "-D", "-h", "-p", "-r",
                                                "-t", "-T"):
            return False
    return False


def _dev_file(w):
    """A literal `/dev/...` or `/proc/.../fd/...` operand: stdin or a pipe."""
    return w.lit is not None and (w.lit.startswith("/dev/") or
                                  (w.lit.startswith("/proc/") and "/fd/" in w.lit))


def _base(s):
    """The last path segment of literal word text `s` ('' for None)."""
    return (s or "").rsplit("/", 1)[-1]


def _shell_string(s):
    """Whether literal word `s` hands a shell string over: `-c`, `-lc`,
    `-S...`, `--split-string`, `--command`."""
    s = s or ""
    return (s.startswith(("--split-string", "--command", "-S"))
            or (SHELL_STRING.fullmatch(s) is not None and "c" in s))


def _may_be_gh(w, split=True):
    """Why command word `w`, not the plain word gh, may still run gh, or
    None (FR-006): `gh-by-path` for a literal path ending in gh; else
    `dynamic-command` for a brace list or glob, a `${...}` naming gh, or an
    expansion whose neighbouring text could complete gh (`g$X`, `${X:-g}h`,
    `$HOME/bin/gh`, `$X$Y`, `$'\\x67h'`) and, with `split`, an unquoted
    expansion that may split off a gh word (`$X/x`). A lone `$CMD`, `"$@"`
    or `$(...)` is the gated rule's (locate())."""
    raw = w.raw.replace("\\\n", "")                # bash joins continuations first
    p = GLOB.sub(EXP + EXP, w.pat)
    if (w.lit is None and "${" in raw and GH_IN_EXPANSION.search(raw)
            or "{" in p and ("," in p or ".." in p)):      # a brace list
        return "dynamic-command"
    if EXP not in p:
        return "gh-by-path" if "/" in p and _base(p) == "gh" else None
    tail = p.rsplit(EXP, 1)[-1]
    if p != EXP and (split and w.split and "gh".startswith(_base(w.pre)) or (
            _base(tail) == "gh" if "/" in tail else tail in ("", "h", "gh"))):
        return "dynamic-command"
    return None


def locate(script):
    """Every `gh` word in `script`, in source order (see the module doc)."""
    sc = _Scan(script)
    sc._cmds(0, _Ctx(0, 0))
    # What runs a variable (`$CMD`, `eval`, a backtick or unquoted heredoc
    # holding an expansion) may run a gh the script holds outside a located
    # call or a provable mention (`GH=gh`, `set -- gh api x`): unprovable.
    if any(m.start() not in sc.by_off for m in GH.finditer(sc.g)):
        for off in sc.bare:
            sc._flag(off, "dynamic-command")
    toks = sorted(sc.by_off.values(), key=lambda x: x.offset)
    if sc.broken is not None:
        for tok in toks:
            if tok.offset >= sc.broken[0] and tok.position != "disallowed":
                tok.kind, tok.position, tok.reason, tok.mention_clause = (
                    "call", "disallowed", sc.broken[1], None)
    return toks


# ------------------------------------------------- a located call's own words

API_VALUED = frozenset(("-X", "--method", "-H", "--header", "-f", "--raw-field", "-F",
                        "--field", "-q", "--jq", "-t", "--template", "-p", "--preview",
                        "--hostname", "--input", "--cache"))
API_ATTACHED = re.compile(r"-(?:[HfFqtpX]|-(?:header|raw-field|field|jq|template|"
                          r"preview|hostname|input|cache|method)=)")


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
            methods.append(_like(w, m.group(1)))
        elif s.startswith("--method="):
            methods.append(_like(w, s[9:]))
    return path, methods, stray, flags


def _like(w, text):
    """`text`, a slice of the argv word `w`, as the same kind of word: a
    Dynamic keeps its literal prefix and its splitting."""
    if not isinstance(w, Dynamic):
        return type(w)(text)
    out = Dynamic(text)
    cut = len(w) - len(text)            # the flag's own characters
    out.pre, out.split = w.pre[cut:], w.split
    return out


def api_parts(args):
    """-> (path word or None, [method words]) for the words after `gh api`."""
    return _api_scan(args)[:2]


def call_words(script, tok):
    """-> (offset, argv) of the `gh` call a disallowed token with no argv
    stands for (a backtick body, `sudo gh`, `eval "gh ..."`, a heredoc fed to
    a shell), read from the first `gh` at or after it to the end of its line;
    (None, []) when there is none. Gate 28 reads a call's flags even where
    Gate 12 rejects its form."""
    end = script.find("\n", tok.offset)
    while end > 0 and script[end - 1] == "\\":      # a continued line goes on
        end = script.find("\n", end + 1)
    end = len(script) if end < 0 else end
    m = GH.search(script, tok.offset, end)
    if m is None:
        return None, []
    for t in locate(script[m.start():end]):
        if t.offset == 0 and t.kind == "call":
            return m.start(), t.argv
    return None, []


def api_flags(args):
    """The dashed words in flag position among the words after `gh api`."""
    return _api_scan(args)[3]


class Run(str):
    """The text of one `run:` scalar, knowing where it sits in its file. This
    is the one home of the line arithmetic: `line(n)` is the file line of
    line `n` of the text, as the locator counts it (by `\\n`). Only a literal
    (`|`) scalar keeps its lines one to one; a folded, plain or quoted scalar
    has no such mapping, so its tokens report the line the text starts on."""
    first = 1
    literal = False

    def line(self, n):
        return self.first + (n - 1 if self.literal else 0)


def _run(node):
    run = Run(node.value)
    run.literal = node.style == "|"
    run.first = node.start_mark.line + 1 + (node.style in ("|", ">"))
    return run


def _compose(path):
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.compose(fh)


def _map_get(node, key):
    import yaml
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if getattr(k, "value", None) == key:
                return v
    return None


def run_blocks(path):
    """[Run] for every `run:` scalar in the workflow or composite-action YAML
    at `path`."""
    import yaml
    out, active = [], set()

    def walk(node, step):
        if id(node) in active:               # an alias cycle; a shared node
            return                           # is read at each of its uses
        active.add(id(node))
        try:
            walk_node(node, step)
        finally:
            active.discard(id(node))

    def walk_node(node, step):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                key = getattr(k, "value", None)
                # `run:` is shell only in a step; `with: {run: ...}` is an input.
                if key == "run" and step and isinstance(v, yaml.ScalarNode):
                    out.append(_run(v))
                else:
                    walk(v, key == "steps")
        elif isinstance(node, yaml.SequenceNode):
            for v in node.value:
                walk(v, step)

    walk(_compose(path), False)
    return out


def step_runs(path, in_jobs):
    """{(job name or None, step index): Run} for the step `run:` scalars of
    the workflow (`in_jobs`) or composite action at `path`. Raises when the
    file cannot be composed or its job keys cannot be built: the caller says
    so, rather than report every call at line 1."""
    import yaml
    out = {}
    root = _compose(path)
    if in_jobs:
        jobs = _map_get(root, "jobs")
        # Keyed as yaml.safe_load keys the job (a job named `on` is True there).
        loader = yaml.SafeLoader("")
        try:
            groups = [(loader.construct_object(k), _map_get(v, "steps"))
                      for k, v in jobs.value
                      ] if isinstance(jobs, yaml.MappingNode) else []
        finally:
            loader.dispose()
    else:
        groups = [(None, _map_get(_map_get(root, "runs"), "steps"))]
    for jname, steps in groups:
        if isinstance(steps, yaml.SequenceNode):
            for idx, st in enumerate(steps.value):
                run = _map_get(st, "run")
                if isinstance(run, yaml.ScalarNode):
                    out[(jname, idx)] = _run(run)
    return out
