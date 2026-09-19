#!/usr/bin/env python3
"""Gate 70 -- 8b stands down on a skipped stage-8 run only when the run that
stage 8 was asked to inspect was itself skipped.

Stage 8 (wing-commander-8-watchdog.yml) declines a source run whose
conclusion is 'skipped': it executed nothing, so FR-026 leaves the watchdog
nothing to say about it. Every such decline makes the stage-8 run itself
conclude 'skipped', and 8b (wing-commander-8b-watchdog-self.yml) must not
file a pipeline-defect issue for it. But a stage-8 run can also conclude
'skipped' because a regression in its own `if:` gated off a source run that
DID execute -- and 8b's check 1 is the only thing that would ever notice. If
8b keyed on stage 8's conclusion alone, both cases would look the same and
the regression would pass as a healthy silence.

8b's workflow_run payload describes the stage-8 run, not its source, and a
run whose jobs were all gated off leaves no output behind. So stage 8 writes
the source's conclusion at the end of its `run-name:` and 8b reads it back
from `display_title`. The two files share a string convention with nothing
else holding them together; this gate is that thing. It evaluates the REAL
expressions from both files -- stage 8's run-name and job guards, 8b's job
guard -- for every source conclusion, paused and unpaused, event-driven and
dispatched, and asserts:

  * stage 8 runs exactly when unpaused and the source was not skipped;
  * 8b stands down when paused, or when stage 8 skipped a skipped source;
  * 8b still runs (so check 1 fires) when stage 8 concluded 'skipped' for a
    source that executed, or on a dispatch -- the regression case.

Three mutations -- 8b keyed on stage 8's conclusion alone, the run-name
suffix changed in one file only, stage 8's skipped-source guard dropped --
must each break an assertion, so the gate proves it can see the drift it
exists for. It reads the two workflow files only; it makes no network call.
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_job, use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

STAGE8 = os.path.join(".github", "workflows", "wing-commander-8-watchdog.yml")
SELF = os.path.join(".github", "workflows", "wing-commander-8b-watchdog-self.yml")
STAGE8_JOBS = ("resolve", "watchdog")
SELF_JOB = "verify"
PAUSE_VAR = "vars.WING_COMMANDER_WATCHDOG_PAUSED"
SOURCE_CONCLUSIONS = ("success", "failure", "cancelled", "timed_out", "skipped")


# --------------------------------------------------------------------------
# A small GitHub-expression evaluator: literals, context references, ! == !=
# && || with GitHub's precedence and loose-equality rules, and the four
# string functions these guards can plausibly grow into. Anything else is a
# hard error -- a guessed evaluation is the failure mode this gate exists for.
# --------------------------------------------------------------------------
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
                fn = FUNCS.get(val.lower())
                if fn is None:
                    raise ValueError(f"unsupported function {val}()")
                self.take()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_())
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.or_())
                self.take(")")
                return fn(*args)
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


# --------------------------------------------------------------------------
# The subject expressions and the scenarios
# --------------------------------------------------------------------------
def load_subject():
    with open(STAGE8, encoding="utf-8") as fh:
        run_name = (yaml.safe_load(fh) or {}).get("run-name")
    if not isinstance(run_name, str) or not run_name.strip():
        sys.exit(f"::error file={STAGE8}::no `run-name:` -- 8b cannot tell a "
                 f"declined skipped source from a gating regression without it.")
    subject = {"run-name": run_name}
    for job in STAGE8_JOBS:
        subject[f"stage8:{job}"] = str(find_job(STAGE8, job).get("if") or "")
    subject["8b"] = str(find_job(SELF, SELF_JOB).get("if") or "")
    for key, val in subject.items():
        if not val.strip():
            sys.exit(f"::error::{key} has no `if:` -- nothing to evaluate. "
                     f"Removing a guard is the regression this gate exists for.")
    return subject


def source_ctx(paused, conclusion):
    """Stage 8's context: event-driven (conclusion set) or dispatch (None)."""
    ctx = {PAUSE_VAR: "true" if paused else ""}
    if conclusion is None:
        ctx.update({"github.event_name": "workflow_dispatch", "inputs.run-id": "17712345678"})
    else:
        ctx.update({"github.event_name": "workflow_run",
                    "github.event.workflow_run.id": 17712345678.0,
                    "github.event.workflow_run.name": "Wing Commander · 2 clarify",
                    "github.event.workflow_run.conclusion": conclusion})
    return ctx


def suite(subject):
    """Every broken assertion, as a message. Empty = the pair is consistent."""
    broke = []
    for paused in (False, True):
        for source in SOURCE_CONCLUSIONS + (None,):
            where = f"paused={paused} source={source or 'dispatch'}"
            ctx = source_ctx(paused, source)
            try:
                title = interpolate(subject["run-name"], ctx)
                ran = [truthy(evaluate(subject[f"stage8:{j}"], ctx)) for j in STAGE8_JOBS]
            except (ValueError, IndexError) as exc:
                broke.append(f"{where}: stage 8 expression did not evaluate: {exc}")
                continue
            want = not paused and source != "skipped"
            for job, got in zip(STAGE8_JOBS, ran):
                if got != want:
                    broke.append(f"{where}: stage 8 job {job!r} runs={got}, expected {want}")

            # What 8b hears. A stage-8 run that executed concludes success or
            # failure; one whose jobs were all gated off concludes skipped --
            # whether by design (paused, skipped source) or by regression,
            # which is modelled by forcing 'skipped' whatever its guards said.
            outcomes = [("executed", "success"), ("executed", "failure"),
                        ("gated off", "skipped")]
            for how, stage8_conclusion in outcomes:
                deliberate = paused or source == "skipped"
                if how == "gated off":
                    want8b = not deliberate
                else:
                    want8b = not paused
                ctx8b = {PAUSE_VAR: ctx[PAUSE_VAR], "github.event_name": "workflow_run",
                         "github.event.workflow_run.conclusion": stage8_conclusion,
                         "github.event.workflow_run.display_title": title}
                try:
                    got8b = truthy(evaluate(subject["8b"], ctx8b))
                except (ValueError, IndexError) as exc:
                    broke.append(f"{where}: 8b's if: did not evaluate: {exc}")
                    break
                if got8b != want8b:
                    broke.append(f"{where}, stage 8 {how} ({stage8_conclusion}), title "
                                 f"{title!r}: 8b runs={got8b}, expected {want8b}")
    return broke


def mut_self_keys_on_stage8_alone(subject):
    s = dict(subject)
    s["8b"] = re.sub(r"\(\s*(github\.event\.workflow_run\.conclusion != 'skipped')\s*\|\|.*\)\s*$",
                     r"\1", subject["8b"], flags=re.S)
    return s


def mut_suffix_drifts(subject):
    s = dict(subject)
    s["run-name"] = subject["run-name"].replace("({2})", "[{2}]")
    return s


def mut_stage8_guard_dropped(subject):
    s = dict(subject)
    for job in STAGE8_JOBS:
        s[f"stage8:{job}"] = re.sub(r"&&\s*github\.event\.workflow_run\.conclusion != 'skipped'",
                                    "", subject[f"stage8:{job}"])
    return s


MUTATIONS = [
    ("8b keys on stage 8's conclusion alone", mut_self_keys_on_stage8_alone),
    ("run-name suffix changed in stage 8 only", mut_suffix_drifts),
    ("stage 8's skipped-source guard dropped", mut_stage8_guard_dropped),
]


def main():
    use_utf8_stdout()
    subject = load_subject()
    failures = suite(subject)
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        mutated = mutate(subject)
        if mutated == subject:
            print(f"::error::mutation {label!r} changed nothing -- the expression it "
                  f"targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        broke = suite(mutated)
        if broke:
            print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 70: {len(SOURCE_CONCLUSIONS) + 1} source shape(s) x paused/unpaused, "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
