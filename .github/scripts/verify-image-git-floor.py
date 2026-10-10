#!/usr/bin/env python3
"""Gate 148 - every stage's image probe enforces the git >= 2.38 floor
(specs/112-agent-startup-image-check, FR-013, User Story 4).

.github/scripts/image-git-floor.sh is the canonical POSIX sh fragment. This
gate (a) runs it under `sh` against a stubbed `git --version` for each case in
image-git-floor-fixtures/ and asserts pass/fail and the exact failure message
(`git <found> is older than the 2.38 minimum` or `could not parse git version
from "<output>"`), and (b) asserts every published stage's
verify-image-prerequisites probe (found by its REQUIRED_TOOLS list) contains
the fragment byte for byte, so the 14 pasted copies cannot drift.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 142. It is
numbered 148, not 142: 141-146 were taken by spec 110's PR #982, which
claimed them first among the open lifecycle branches.

Usage: python3 .github/scripts/verify-image-git-floor.py [--self-test]
"""
import glob
import json
import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FRAGMENT = os.path.join(HERE, "image-git-floor.sh")
FIXTURES = os.path.join(HERE, "image-git-floor-fixtures")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows", "*.yml")


def read_fragment(path=FRAGMENT):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def run_fragment(fragment, git_output):
    """-> (exit code, stderr stripped) of the fragment under sh with a stub git."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.txt")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(git_output)
        stub = os.path.join(tmp, "git")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\ncat "%s"\n' % out)
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
        env = {"PATH": tmp + ":/usr/bin:/bin"}
        proc = subprocess.run(["sh", "-c", fragment], env=env, capture_output=True, text=True)
        return proc.returncode, proc.stderr.strip()


def check_cases(fragment, fixtures=FIXTURES):
    errors = []
    with open(os.path.join(fixtures, "expectations.json"), encoding="utf-8") as fh:
        expectations = json.load(fh)
    for name, exp in sorted(expectations.items()):
        path = os.path.join(fixtures, name + ".txt")
        if not os.path.exists(path):
            errors.append("fixture %s.txt is missing" % name)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        rc, err = run_fragment(fragment, text)
        if (rc == 0) != exp["pass"]:
            errors.append("%s: expected pass=%s, exit code was %s" % (name, exp["pass"], rc))
        elif not exp["pass"] and err != exp["message"]:
            errors.append("%s: expected message %r, got %r" % (name, exp["message"], err))
    for f in os.listdir(fixtures):
        if f.endswith(".txt") and f[:-4] not in expectations:
            errors.append("fixture %s has no expectation" % f)
    return errors


def stage_files(pattern=WORKFLOWS):
    out = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "REQUIRED_TOOLS=" in text and 'for t in $REQUIRED_TOOLS; do command -v "$t"' in text:
            out.append((path, text))
    return out


def check_stages(fragment, stages):
    errors = []
    if not stages:
        errors.append("no stage with a verify-image-prerequisites probe was found")
    for path, text in stages:
        if fragment not in text:
            errors.append("%s: the image probe lacks the git-floor fragment from image-git-floor.sh" % os.path.basename(path))
    return errors


def run_checks():
    fragment = read_fragment()
    return check_cases(fragment) + check_stages(fragment, stage_files())


def self_test():
    failures = []
    fragment = read_fragment()
    base = run_checks()
    if base:
        failures.append("baseline is not clean: %r" % base)
    lowered = fragment.replace('"$min" -lt 38', '"$min" -lt 30')
    if lowered == fragment or not any("2.34.1" in e for e in check_cases(lowered)):
        failures.append("a lowered floor was not caught by the 2.34.1 case")
    stages = stage_files()
    if stages:
        path, text = stages[0]
        broken = [(path, text.replace(fragment, "true"))] + stages[1:]
        if not any(os.path.basename(path) in e for e in check_stages(fragment, broken)):
            failures.append("a probe missing the fragment was not caught")
    for f in failures:
        print("::error::Gate 148 self-test: " + f)
    if not failures:
        print("Gate 148 self-test: ok")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    errors = run_checks()
    for e in errors:
        print("::error::Gate 148: " + e)
    if not errors:
        print("Gate 148: ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
