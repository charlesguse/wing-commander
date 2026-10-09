#!/usr/bin/env python3
"""Gate: the `model:haiku` implement opt-in stays confined (spec 110, FR-014..016).

1. wing-commander-5-implement.yml's literal `max_turns=180` equals
   implement.yml's `max-turns` input default, so a non-Haiku cycle keeps the
   budget it has today.
2. In that wrapper the `model:opus` branch precedes the `model:haiku` branch
   (model:opus wins), and the Haiku branch escalates to claude-sonnet-5-5.
3. Only that wrapper reads the label: pr-conversation and the board loop
   never mention `model:haiku`.

Usage: verify-implement-haiku-optin.py [--root DIR]
       verify-implement-haiku-optin.py --self-test
"""
import argparse
import re
import sys
from pathlib import Path

WRAPPER = ".github/workflows/wing-commander-5-implement.yml"
STAGE = ".github/workflows/implement.yml"
OTHERS = (".github/workflows/wing-commander-9-pr-conversation.yml",
          ".github/workflows/board-loop.yml")


def check(texts):
    """texts maps repo-relative path -> file text; returns failure strings."""
    failures = []
    wrapper, stage = texts.get(WRAPPER), texts.get(STAGE)
    if wrapper is None or stage is None:
        return [f"{WRAPPER} or {STAGE} missing"]
    lit = re.search(r"^\s*max_turns=(\d+)\s*$", wrapper, re.M)
    default = re.search(r"^\s{6}max-turns:\n(?:\s{8}.*\n)*?\s{8}default:\s*(\d+)",
                        stage, re.M)
    if not lit or not default:
        failures.append("cannot find the wrapper's max_turns literal or "
                        "implement.yml's max-turns default")
    elif lit.group(1) != default.group(1):
        failures.append(f"wrapper max_turns={lit.group(1)} != implement.yml "
                        f"max-turns default {default.group(1)}")
    opus = wrapper.find("grep -qx 'model:opus'")
    haiku = wrapper.find("grep -qx 'model:haiku'")
    if opus < 0 or haiku < 0 or opus > haiku:
        failures.append("model:opus must be tested before model:haiku in "
                        f"{WRAPPER}")
    if 'escalation="claude-sonnet-5-5"' not in wrapper:
        failures.append("the Haiku branch must escalate to claude-sonnet-5-5")
    for rel in OTHERS:
        if "model:haiku" in texts.get(rel, ""):
            failures.append(f"{rel} must not read the model:haiku label")
    return failures


GOOD_WRAPPER = """max_turns=180
if grep -qx 'model:opus'; then x
elif grep -qx 'model:haiku'; then
escalation="claude-sonnet-5-5"
"""
GOOD_STAGE = "      max-turns:\n        type: number\n        default: 180\n"


def self_test():
    base = {WRAPPER: GOOD_WRAPPER, STAGE: GOOD_STAGE,
            OTHERS[0]: "model:opus\n", OTHERS[1]: "model:opus\n"}
    ok = not check(base)
    bad = [
        dict(base, **{STAGE: GOOD_STAGE.replace("180", "100")}),
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace("model:opus", "model:zzz")}),
        dict(base, **{OTHERS[1]: "model:opus model:haiku\n"}),
        dict(base, **{WRAPPER: GOOD_WRAPPER.replace("sonnet", "opus")}),
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
