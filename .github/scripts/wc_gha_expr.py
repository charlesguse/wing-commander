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
"Shared logic has exactly one home"). verify-write-boundary.py,
verify-act-dedup-guard.py, verify-clarification-gating.py,
verify-plan-tasks-cost-line.py, auto-update-spec-kit-tests/t7_gating.py and
wc_chain_stop_conditions.py each carried such a copy (Python `eval`s and
regex term parsers, all with case-sensitive `==`) until the code review of
#940; verify-single-home-idioms.py (Gate 60) now fails a script that
defines its own evaluator again.

WHAT IT COVERS
--------------
Literals, context references, `!`, `<`, `<=`, `>`, `>=`, `==`, `!=`, `&&`,
`||` with GitHub's precedence and loose-comparison rules, parentheses,
`fromJSON`, and the four string functions these guards can plausibly grow
into (format/startsWith/endsWith/contains). Status functions (`success()`, `cancelled()`, ...) are resolved
from the caller's context under the key `"<name>()"`, so a caller that models
them must say so explicitly.

Anything else is a hard ValueError. A guessed evaluation is precisely the
failure mode the gates built on this exist for, so an unmodelled construct
must stop the gate rather than quietly resolve to something plausible. A
caller that models only some contexts passes `known`, the reference
prefixes it models (`("steps.", "inputs.")`): a reference outside them is a
ValueError too, and one inside them that the context lacks is null, as an
unset step output is.
"""
import json
import math
import re

TOKEN = re.compile(r"""\s*(?:
    (?P<str>'(?:[^']|'')*')
  | (?P<num>-?\d+(?:\.\d+)?)
  | (?P<op>&&|\|\||==|!=|<=|>=|<|>|!|\(|\)|,)
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


def loose_order(a, b, op):
    """`<`/`<=`/`>`/`>=`: two strings compare case-insensitively, any
    other pair as numbers, and a NaN on either side is false."""
    if isinstance(a, str) and isinstance(b, str):
        x, y = a.lower(), b.lower()
    else:
        x, y = to_num(a), to_num(b)
        if math.isnan(x) or math.isnan(y):
            return False
    return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def fn_from_json(value):
    """fromJSON: a JSON number is a float, as every number here is."""
    try:
        out = json.loads(to_str(value))
    except ValueError as exc:
        raise ValueError(f"fromJSON({to_str(value)!r}): {exc}") from None
    if isinstance(out, int) and not isinstance(out, bool):
        return float(out)
    return out


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
    "contains": lambda s, x: (any(loose_eq(e, x) for e in s)
                              if isinstance(s, list)
                              else to_str(x).lower() in to_str(s).lower()),
    "fromjson": fn_from_json,
}


class Parser:
    def __init__(self, src, ctx, known=None):
        self.toks, self.i, self.ctx = tokenize(src), 0, ctx
        self.known = known
        # >0 while reading an `&&`/`||` right-hand side GitHub never
        # evaluates: a guarded `fromJSON('')` must not fail the expression
        # (code review of #954). Unmodelled names still raise -- a gate
        # must not pass on a construct it cannot read in any scenario.
        self.skip = 0

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

    def _rhs(self, read, skipped):
        """Read one `&&`/`||` operand, unevaluated when `skipped`."""
        self.skip += skipped
        try:
            return read()
        finally:
            self.skip -= skipped

    def or_(self):
        v = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            rhs = self._rhs(self.and_, truthy(v))
            v = v if truthy(v) else rhs
        return v

    def and_(self):
        v = self.cmp()
        while self.peek() == ("op", "&&"):
            self.take()
            rhs = self._rhs(self.cmp, not truthy(v))
            v = rhs if truthy(v) else v
        return v

    def cmp(self):
        # `!` binds tighter than `==`/`!=` in GitHub's grammar -- `!a == b`
        # is `(!a) == b`, not `!(a == b)` -- so unary() must be resolved
        # before an equality operator is looked for, not the other way
        # around (MF-08).
        v = self.order()
        if self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            eq = loose_eq(v, self.order())
            return eq if op == "==" else not eq
        return v

    def order(self):
        # `<`/`<=`/`>`/`>=` bind tighter than `==`/`!=`, and looser than `!`.
        v = self.unary()
        if self.peek() in (("op", "<"), ("op", "<="), ("op", ">"),
                           ("op", ">=")):
            op = self.take()[1]
            return loose_order(v, self.unary(), op)
        return v

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not truthy(self.unary())
        return self.primary()

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
            if self.skip:
                return None
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
            if (self.known is not None and val not in self.ctx
                    and not val.startswith(tuple(self.known))):
                raise ValueError(f"unmodelled context reference {val!r}")
            return self.ctx.get(val)
        raise ValueError(f"unexpected token {val!r}")


def evaluate(expr, ctx, known=None):
    """An `if:` value (bare or ${{ }}-wrapped) -> its GitHub result."""
    s = expr.strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", s, re.S)
    return Parser(m.group(1) if m else s, ctx, known).parse()


def evaluate_if(expr, ctx, known=None):
    """An `if:` -> whether the step runs (its result's truthiness)."""
    return truthy(evaluate(expr, ctx, known))


def interpolate(template, ctx):
    """A string field like run-name -> the string GitHub would render."""
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: to_str(Parser(m.group(1), ctx).parse()),
                  template, flags=re.S)


if __name__ == "__main__":
    # MF-08: `!` binds tighter than `==` -- `!a == b` is `(!a) == b`, never
    # `!(a == b)`. `!a` is `False`; `False == 'failure'` is `False`.
    assert evaluate("!a == b", {"a": "skipped", "b": "failure"}) is False
    # Code review of #940: fromJSON and the ordering operators, which bind
    # tighter than `==`; `==` on strings ignores case.
    assert evaluate("fromJSON(a) >= fromJSON(b)", {"a": "5", "b": "5"}) is True
    assert evaluate("fromJSON(a) < fromJSON(b)", {"a": "10", "b": "9"}) is False
    assert evaluate("a < b == true", {"a": "1", "b": "2"}) is True
    assert evaluate("fromJSON('[1]')", {}) == [1.0]
    assert evaluate("a == 'TRUE'", {"a": "true"}) is True
    # contains() on an array is element equality, not a substring of it.
    assert evaluate("contains(fromJSON('[\"ab\"]'), 'a')", {}) is False
    assert evaluate("contains(fromJSON('[\"ab\"]'), 'AB')", {}) is True
    # Code review of #954: `&&`/`||` stop as GitHub's do, so a guarded
    # fromJSON of an unset output does not fail the evaluation.
    assert evaluate("a == 'true' || fromJSON(b) >= 1", {"a": "true"}) is True
    assert evaluate("a == 'x' && fromJSON(b)", {"a": "y"}) is False
    assert evaluate("startsWith(a, '[') && fromJSON(a) || a",
                    {"a": "ubuntu-latest"}) == "ubuntu-latest"
    for bad, known in (("env.X == 'y'", ("steps.",)), ("fromJSON('[')", None),
                       ("true || env.X", ("steps.",)),
                       ("false && nope()", None)):
        try:
            evaluate(bad, {}, known)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} must be a ValueError")
    print("wc_gha_expr self-test: ok")
