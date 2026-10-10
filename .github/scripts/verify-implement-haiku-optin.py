#!/usr/bin/env python3
"""Gate: the `model:haiku` implement opt-in stays confined (spec 110, FR-014..016).

1. wing-commander-5-implement.yml's literal `max_turns=180` equals
   implement.yml's `max-turns` input default, so a non-Haiku cycle keeps the
   budget it has today.
2. In that wrapper the `model:opus` test is the `if` and the `model:haiku`
   test its very next `elif` (model:opus wins), and the Haiku branch itself
   escalates to claude-sonnet-5-5. Read from the executable lines only, in
   order: a comment that quotes either test cannot satisfy it (review gate
   rounds 4-5: a whole-file str.find could).
3. Only that wrapper reads the label: pr-conversation and the board loop
   never mention `model:haiku`.

Usage: verify-implement-haiku-optin.py [--root DIR]
       verify-implement-haiku-optin.py --self-test
"""
import argparse
import re
import shlex
import sys
from pathlib import Path

WRAPPER = ".github/workflows/wing-commander-5-implement.yml"
STAGE = ".github/workflows/implement.yml"
OTHERS = (".github/workflows/wing-commander-9-pr-conversation.yml",
          ".github/workflows/board-loop.yml",
          ".github/workflows/pr-conversation.yml")


def check(texts):
    """texts maps repo-relative path -> file text; returns failure strings."""
    failures = []
    wrapper, stage = texts.get(WRAPPER), texts.get(STAGE)
    if wrapper is None or stage is None:
        return [f"{WRAPPER} or {STAGE} missing"]
    lit = re.search(r"^[ ]*max_turns=(\d+)[ ]*$", wrapper, re.M)
    default = re.search(r"^[ ]{6}max-turns:\n(?:[ ]{8}.*\n)*?[ ]{8}default:[ ]*(\d+)",
                        stage, re.M)
    if not lit or not default:
        failures.append("cannot find the wrapper's max_turns literal or "
                        "implement.yml's max-turns default")
    elif lit.group(1) != default.group(1):
        failures.append(f"wrapper max_turns={lit.group(1)} != implement.yml "
                        f"max-turns default {default.group(1)}")
    failures += branch_failures(wrapper)
    for rel in OTHERS:
        if rel not in texts:
            failures.append(f"{rel} missing; the confinement check cannot run")
        elif "model:haiku" in texts[rel]:
            failures.append(f"{rel} must not read the model:haiku label")
    return failures


OPUS_IF = re.compile(r"^if grep -qx 'model:opus'")
HAIKU_ELIF = re.compile(r"^elif grep -qx 'model:haiku'")
BRANCH = re.compile(r"^(elif|else|fi)\b")


SEPARATORS = {";", "&&", "||", "&", "|", ";;"}
OPENS_COMMAND = {"if", "then", "else", "elif", "do", "!"}


def net_depth(line):
    """How many if-blocks this line opens minus how many it closes, reading
    `if` and `fi` only where the shell would: as the first word of a
    command (so `[ a = fi ]`, a quoted `#` and a trailing comment are
    data). A line shlex cannot split counts as neither."""
    try:
        lex = shlex.shlex(line, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return 0
    depth, command_start = 0, True
    for tok in tokens:
        if tok in SEPARATORS:
            command_start = True
            continue
        if command_start:
            if tok == "if":
                depth += 1
            elif tok == "fi":
                depth -= 1
            # `if`/`then`/`else`/... are followed by another command word;
            # any other first word is followed by its arguments.
            command_start = tok in OPENS_COMMAND
        # else: an argument, never a keyword
    return depth


def branch_lines(lines, start):
    """(index of the next elif/else/fi at the same nesting depth as the
    branch opened at `start`, the branch's own depth-0 body lines). A nested
    if ... fi inside the branch neither ends it nor counts as its body
    (review-gate round 7: a nested elif could hide a missing escalation)."""
    depth, body = 0, []
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if depth == 0 and BRANCH.match(ln):
            return i, body
        net = net_depth(ln)
        if depth == 0 and net == 0 and not ln.startswith("if "):
            body.append(ln)
        depth += net
    return len(lines), body


def branch_failures(wrapper):
    """model:opus is the if, model:haiku its next same-depth elif, and the
    Haiku branch's own (not a nested block's) body sets the Sonnet
    escalation."""
    lines = [ln.strip() for ln in wrapper.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    at = next((i for i, ln in enumerate(lines) if OPUS_IF.match(ln)), None)
    if at is None:
        return [f"{WRAPPER} has no `if grep -qx 'model:opus'` test"]
    nxt, _ = branch_lines(lines, at)
    if nxt >= len(lines) or not HAIKU_ELIF.match(lines[nxt]):
        return ["model:opus must be tested first and model:haiku in its very "
                f"next elif in {WRAPPER}, so model:opus wins"]
    _, body = branch_lines(lines, nxt)
    if 'escalation="claude-sonnet-5-5"' not in body:
        return ["the Haiku branch must escalate to claude-sonnet-5-5"]
    return []


GOOD_WRAPPER = """max_turns=180
if grep -qx 'model:opus' <<< "$labels"; then
  tier="claude-opus-5-5"
elif grep -qx 'model:haiku' <<< "$labels"; then
  escalation="claude-sonnet-5-5"
fi
"""
SWAPPED = """max_turns=180
# if grep -qx 'model:opus' runs first, model:opus wins
if grep -qx 'model:haiku' <<< "$labels"; then
  escalation="claude-sonnet-5-5"
elif grep -qx 'model:opus' <<< "$labels"; then
  tier="claude-opus-5-5"
fi
"""
GOOD_STAGE = "      max-turns:\n        type: number\n        default: 180\n"


def self_test():
    base = {WRAPPER: GOOD_WRAPPER, STAGE: GOOD_STAGE,
            OTHERS[0]: "model:opus\n", OTHERS[1]: "model:opus\n",
            OTHERS[2]: "model:opus\n"}
    ok = not check(base)
    # A nested if inside the Haiku branch, before the escalation, is fine.
    nested = dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
        '  escalation="claude-sonnet-5-5"\n',
        '  if [ -n "$x" ]; then\n    :\n  fi\n  escalation="claude-sonnet-5-5"\n')})
    for variant in ('if [ -n "$X" ]; then tier=x; fi',
                    'if [ -n "$X" ]; then tier=x; fi  # override',
                    'if [ -n "$X" ]; then tier=x; fi;',
                    'if [ "$x" = "a #b" ]; then y=1; fi'):
        one_line = dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  tier="claude-opus-5-5"\n',
            f'  tier="claude-opus-5-5"\n  {variant}\n')})
        if check(one_line):
            print(f"self-test: a one-line if ({variant!r}) in the opus branch "
                  f"must pass: {check(one_line)}", file=sys.stderr)
            ok = False
    if check(nested):
        print("self-test: a nested if in the Haiku branch must pass: "
              f"{check(nested)}", file=sys.stderr)
        ok = False
    bad = [
        dict(base, **{STAGE: GOOD_STAGE.replace("180", "100")}),
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace("model:opus", "model:zzz")}),
        dict(base, **{OTHERS[1]: "model:opus model:haiku\n"}),
        dict(base, **{OTHERS[2]: "model:haiku\n"}),
        {k: v for k, v in base.items() if k != OTHERS[1]},
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace("sonnet", "opus")}),
        # a comment quoting the opus test above swapped branches
        dict(base, **{WRAPPER: SWAPPED}),
        # the escalation set only inside a nested if within the Haiku branch
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  escalation="claude-sonnet-5-5"\n',
            '  if [ -n "$x" ]; then\n    escalation="claude-sonnet-5-5"\n'
            '  elif true; then\n    :\n  fi\n')}),
        # a one-line if in the Haiku branch, the escalation moved after the
        # chain where it applies to every tier
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  escalation="claude-sonnet-5-5"\nfi\n',
            '  if [ -n "$x" ]; then y=1; fi\n  tier=haiku\nfi\n'
            'escalation="claude-sonnet-5-5"\n')}),
        # a multi-line if whose condition ends in the word fi, the
        # escalation only inside it
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  escalation="claude-sonnet-5-5"\n',
            '  if test "$m" = fi\n  then\n    escalation="claude-sonnet-5-5"\n'
            '  fi\n')}),
        # an if still open after a nested one-line if, the escalation in it
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  escalation="claude-sonnet-5-5"\n',
            '  if a; then if b; then c; fi\n    escalation="claude-sonnet-5-5"\n'
            '  fi\n')}),
        # then/fi as test operands, the escalation in the still-open if
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  escalation="claude-sonnet-5-5"\n',
            '  if [ a = then ] && [ b = fi ]; then\n'
            '    escalation="claude-sonnet-5-5"\n  fi\n')}),
        # the Sonnet escalation set in the opus branch, not the Haiku one
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace(
            '  tier="claude-opus-5-5"', '  escalation="claude-sonnet-5-5"')
            .replace('then\n  escalation="claude-sonnet-5-5"\nfi',
                     'then\n  tier="claude-haiku-5-5"\nfi')}),
    ]
    for i, texts in enumerate(bad):
        if not check(texts):
            print(f"self-test: bad case {i} passed", file=sys.stderr)
            ok = False
    if not ok:
        print("self-test: the good layout must pass", file=sys.stderr)
        return 1
    print("self-test ok")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.root)
    texts = {rel: (root / rel).read_text(encoding="utf-8")
             for rel in (WRAPPER, STAGE) + OTHERS if (root / rel).is_file()}
    failures = check(texts)
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print("model:haiku opt-in is confined to the implement wrapper")
    return 0


if __name__ == "__main__":
    sys.exit(main())
