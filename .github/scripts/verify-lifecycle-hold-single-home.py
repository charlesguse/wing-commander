#!/usr/bin/env python3
"""Gate: the lifecycle hold label has one home (specs/119, FR-019).

Fails when
  * the composite wing-commander-lifecycle-hold stops delegating to
    wc_lifecycle_hold.py or loses `shell: bash` on a run step;
  * a workflow or another composite reads or adds the hold label inline
    (`gh issue ... lifecycle:held` / the hold-label variable) instead of
    calling the composite.
Callers that exist are required to use `mode: set`/`check` only through the
composite; callers added by later tasks are covered by the inline-copy rule.

Usage: verify-lifecycle-hold-single-home.py [--self-test] [repo_root]
"""
import os
import re
import sys

HOME_COMPOSITE = ".github/actions/wing-commander-lifecycle-hold/action.yml"
HOME_SCRIPT = ".github/scripts/wc_lifecycle_hold.py"
INLINE_RE = re.compile(
    r"gh\s+issue\s+(?:edit|view)[^\n]*(?:lifecycle:held|HOLD_LABEL)"
    r"|--add-label[^\n]*(?:lifecycle:held|HOLD_LABEL)"
)


def check_composite(text):
    problems = []
    if "wc_lifecycle_hold.py" not in text:
        problems.append("composite no longer calls wc_lifecycle_hold.py")
    runs = len(re.findall(r"^\s+(?:-\s+)?run:", text, re.M))
    shells = len(re.findall(r"^\s+(?:-\s+)?shell:\s*bash\s*$", text, re.M))
    if runs != shells:
        problems.append("a run: step lacks `shell: bash`")
    return problems


def check_inline(path, text):
    if path == HOME_COMPOSITE:
        return []
    return [f"{path}: inline hold-label read/add ({m.group(0)[:60]!r}); "
            "use the wing-commander-lifecycle-hold composite"
            for m in INLINE_RE.finditer(text)]


def scan(root):
    problems = []
    comp = os.path.join(root, HOME_COMPOSITE)
    if not os.path.exists(comp) or not os.path.exists(os.path.join(root, HOME_SCRIPT)):
        return ["lifecycle hold composite or script is missing"]
    with open(comp, encoding="utf-8") as fh:
        problems += check_composite(fh.read())
    for base in (".github/workflows", ".github/actions"):
        for dirpath, _, files in os.walk(os.path.join(root, base)):
            for name in files:
                if not name.endswith((".yml", ".yaml", ".sh")):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                with open(full, encoding="utf-8") as fh:
                    problems += check_inline(rel, fh.read())
    return problems


def self_test():
    good = "runs:\n  steps:\n    - run: python3 wc_lifecycle_hold.py\n      shell: bash\n"
    assert not check_composite(good)
    assert check_composite("    - run: echo\n      shell: bash\n")
    assert check_composite("    - run: python3 wc_lifecycle_hold.py\n")
    assert check_inline("w.yml", "gh issue edit 1 --add-label lifecycle:held")
    assert check_inline("w.yml", 'gh issue view 1 --json labels # "$HOLD_LABEL"')
    assert not check_inline("w.yml", "uses: ./.github/actions/wing-commander-lifecycle-hold")
    assert not check_inline(HOME_COMPOSITE, "gh issue edit --add-label lifecycle:held")
    # The home module itself: fail-closed read and the canonical text.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wc_lifecycle_hold

    assert wc_lifecycle_hold.check(1, reader=lambda i, r: 1 / 0) == "unreadable"
    assert wc_lifecycle_hold.classify_labels(["lifecycle:held"]) == "held"
    assert wc_lifecycle_hold.classify_labels([]) == "clear"
    assert "labels could not be read" in wc_lifecycle_hold.UNREADABLE_MESSAGE
    print("self-test ok")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    args = [a for a in argv if not a.startswith("--")]
    root = args[0] if args else os.getcwd()
    problems = scan(root)
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        return 1
    print("lifecycle hold single home: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
