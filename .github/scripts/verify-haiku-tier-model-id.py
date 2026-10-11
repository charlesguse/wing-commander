#!/usr/bin/env python3
"""Gate: no pipeline-chosen `claude-haiku-4-5` remains (spec 110, FR-006).

The Haiku tier names `claude-haiku-5-5`. This gate fails when the retired
4.5 ID (any suffix, e.g. a dated snapshot) reappears in a place the pipeline
chooses a model or documents the tier: .github/workflows/, .github/actions/,
.specify/memory/constitution.md and docs/. Fixtures under .github/scripts/,
the amendment history (constitution-history.md) and specs/ are historical or
test data and are not scanned. An empty or missing scan root fails loudly, so
a moved directory cannot turn the gate into a no-op.

Usage:
    verify-haiku-tier-model-id.py [--root DIR]
    verify-haiku-tier-model-id.py --self-test
"""
import argparse
import re
import sys
from pathlib import Path

RETIRED = re.compile(r"claude-haiku-4-5")
SCAN_ROOTS = (
    ".github/workflows",
    ".github/actions",
    ".specify/memory/constitution.md",
    "docs",
)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "haiku-tier-model-id"


def scan(root):
    """Return a list of failure strings for the repo layout under root."""
    failures = []
    for rel in SCAN_ROOTS:
        base = root / rel
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = sorted(p for p in base.rglob("*") if p.is_file())
        else:
            files = []
        if not files:
            failures.append(f"scan root {rel} is missing or empty")
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if RETIRED.search(line):
                    failures.append(
                        f"{path.relative_to(root)}:{n}: retired Haiku ID "
                        f"claude-haiku-4-5 (use claude-haiku-5-5)")
    return failures


def self_test():
    ok = True
    expectations = {
        "clean": 0,
        "workflow-hit": 1,
        "docs-hit": 1,
        "constitution-hit": 1,
        "empty-root": 1,
    }
    for name, want in expectations.items():
        case = FIXTURES / name
        if not case.is_dir():
            print(f"self-test: fixture {case} missing", file=sys.stderr)
            ok = False
            continue
        got = scan(case)
        if bool(got) != bool(want):
            print(f"self-test: {name}: expected "
                  f"{'failure' if want else 'pass'}, got {got}",
                  file=sys.stderr)
            ok = False
    if ok:
        print("self-test ok")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    failures = scan(Path(args.root).resolve())
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print("no retired Haiku model ID found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
