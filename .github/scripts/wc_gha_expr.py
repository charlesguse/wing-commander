#!/usr/bin/env python3
"""A small GitHub-Actions expression evaluator, shared by the gates that need
to EVALUATE a shipped `if:` rather than pattern-match its text.

WHY THIS EXISTS
---------------
Two kinds of gate in this repository need the same thing: take the real
expression out of a shipped workflow and ask "what would GitHub do with it,
given this run state?". Matching the text instead (`'skipped' in if_text`) is
what these gates exist to catch -- a reordered clause, an `||` where an `&&`
was meant, or a `!` that moved one token left all keep every substring and
invert the answer.

It grew up inside verify-watchdog-self-skip-guard.py (Gate 70). It lives here
because verify-watchdog-clean-path.py (Gate 73) needs the identical semantics
for watchdog.yml's `diagnose` guard and its new collect-side step guards, and
a pasted second copy is invisible until the first divergent fix (CLAUDE.md,
"Shared logic has exactly one home").

WHAT IT COVERS
--------------
Literals, context references, `!`, `==`, `!=`, `&&`, `||` with GitHub's
precedence and loose-equality rules, parentheses, and the four string
functions these guards can plausibly grow into (format/startsWith/endsWith/
contains). Status functions (`success()`, `cancelled()`, ...) are resolved
from the caller's context under the key `"<name>()"`, so a caller that models
them must say so explicitly.

Anything else is a hard ValueError. A guessed evaluation is precisely the
failure mode the gates built on this exist for, so an unmodelled construct
must stop the gate rather than quietly resolve to something plausible.
"""
import math
import re

TOKEN = re.compile(r"""\s*(?:
    (?P<str>'(?:[^']|'')*')
  | (?P<num>-?\d+(?:\.\d+)?)
  | (?P<op>&&|\|\||==|!=|!|\(|\)|,)
  | (?P<name>[A-Za-z_][A-Za-z0-9_\-]*(?:\.(?:[A-Za-z_][A-Za-z0-9_\-]*|\*))*)
)""", re.X)


def tokenize(src):
    out, pos = [], 0
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot tokenize {src[pos:pos + 30]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def to_str(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def to_num(v):
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = v.strip()
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return math.nan


def truthy(v):
    if v is None or v is False or v == "":
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not math.isnan(v)
    return True


def loose_eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    if type(a) is type(b):
        return a == b
    x, y = to_num(a), to_num(b)
    return not (math.isnan(x) or math.isnan(y)) and x == y


def fn_format(fmt, *args):
    def sub(m):
        if m.group(0) == "{{":
            return "{"
        if m.group(0) == "}}":
            return "}"
        return to_str(args[int(m.group(1))])
    return re.sub(r"\{\{|\}\}|\{(\d+)\}", sub, to_str(fmt))


FUNCS = {
    "format": fn_format,
    "endswith": lambda s, x: to_str(s).lower().endswith(to_str(x).lower()),
    "startswith": lambda s, x: to_str(s).lower().startswith(to_str(x).lower()),
    "contains": lambda s, x: to_str(x).lower() in to_str(s).lower(),
}


class Parser:
    def __init__(self, src, ctx):
        self.toks, self.i, self.ctx = tokenize(src), 0, ctx

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise ValueError(f"expected {value!r}, found {tok[1]!r}")
        self.i += 1
        return tok

    def parse(self):
        v = self.or_()
        if self.i != len(self.toks):
            raise ValueError(f"trailing tokens from {self.peek()[1]!r}")
        return v

    def or_(self):
        v = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            rhs = self.and_()
            v = v if truthy(v) else rhs
        return v

    def and_(self):
        v = self.unary()
        while self.peek() == ("op", "&&"):
            self.take()
            rhs = self.unary()
            v = rhs if truthy(v) else v
        return v

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not truthy(self.unary())
        return self.cmp()

    def cmp(self):
        v = self.primary()
        if self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            eq = loose_eq(v, self.primary())
            return eq if op == "==" else not eq
        return v

    def call(self, name):
        """A `name(...)`: a string function, else a status function the
        caller modelled in its context under "<name>()". Never a guess."""
        self.take()
        args = []
        if self.peek() != ("op", ")"):
            args.append(self.or_())
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.or_())
        self.take(")")
        fn = FUNCS.get(name.lower())
        if fn is not None:
            return fn(*args)
        key = f"{name.lower()}()"
        if key in self.ctx:
            return self.ctx[key]
        raise ValueError(f"unsupported function {name}() -- model it in the "
                         f"context as {key!r} if this gate means to allow it")

    def primary(self):
        kind, val = self.take()
        if (kind, val) == ("op", "("):
            v = self.or_()
            self.take(")")
            return v
        if kind == "str":
            return val[1:-1].replace("''", "'")
        if kind == "num":
            return float(val)
        if kind == "name":
            if self.peek() == ("op", "("):
                return self.call(val)
            if val in ("true", "false"):
                return val == "true"
            if val == "null":
                return None
            return self.ctx.get(val)
        raise ValueError(f"unexpected token {val!r}")


def evaluate(expr, ctx):
    """An `if:` value (bare or ${{ }}-wrapped) -> its GitHub result."""
    s = expr.strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", s, re.S)
    return Parser(m.group(1) if m else s, ctx).parse()


def interpolate(template, ctx):
    """A string field like run-name -> the string GitHub would render."""
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: to_str(Parser(m.group(1), ctx).parse()),
                  template, flags=re.S)
