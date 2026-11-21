#!/usr/bin/env python3
"""Gate 148 - every stage's image probe enforces the git >= 2.38 floor
(specs/112-agent-startup-image-check, FR-013, User Story 4) and requires the
glibc dynamic loader the agent action's Bun needs.

.github/scripts/image-git-floor.sh is the canonical POSIX sh fragment. This
gate (a) runs it under `sh` against a stubbed `git --version` for each case in
image-git-floor-fixtures/ and asserts pass/fail and the exact failure message
(`git <found> is older than the 2.38 minimum` or `could not parse git version
from "<output>"`), and (b) asserts every published stage's
verify-image-prerequisites probe (found by its REQUIRED_TOOLS list) contains
the fragment byte for byte, and the host-side failure report (HOST_BRANCH)
too, so the pasted copies cannot drift; and (c) asserts Gate 62
(verify-gate-62.py) runs the fragment against the reference image and
classifies its result with FLOOR_MESSAGES, which must be the fragment's own
two messages.

The glibc loader check has its own canonical fragment,
.github/scripts/image-glibc-loader.sh, checked the same three ways: it is run
against image-glibc-loader-fixtures/ (a stubbed `uname -m` and a fake file
tree per case: glibc, gcompat, musl, a dangling loader link, an unknown
arch, no uname), every stage's probe must embed it byte for byte ahead of
the git floor along with its host-side report (LOADER_HOST_BRANCH), and
Gate 62 must run it against the reference image (LOADER_MESSAGES). Why the
check exists: anthropics/claude-code-action installs Bun with
oven-sh/setup-bun, which downloads bun-linux-<x64|aarch64>.zip -- a glibc
build whatever the image's libc (it has no musl variant). Its ELF
interpreter is /lib64/ld-linux-x86-64.so.2 on x86_64 and
/lib/ld-linux-aarch64.so.1 on aarch64, so on an image without that loader
(Alpine/musl, distroless) the probe used to pass and the agent's "Install
Bun" step died with `bun: cannot execute: required file not found`.
/lib/ld-linux-x86-64.so.2 is also accepted on x86_64: Alpine's gcompat
installs it (and the /lib64 link beside it). An unknown arch, or no uname,
is never failed by this check.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 142. It is
numbered 148, not 142: 141-146 were taken by spec 110's PR #982, which
claimed them first among the open lifecycle branches.

Usage: python3 .github/scripts/verify-image-git-floor.py [--self-test]
"""
import glob
import json
import re
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FRAGMENT = os.path.join(HERE, "image-git-floor.sh")
FIXTURES = os.path.join(HERE, "image-git-floor-fixtures")
LOADER_FRAGMENT = os.path.join(HERE, "image-glibc-loader.sh")
LOADER_FIXTURES = os.path.join(HERE, "image-glibc-loader-fixtures")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows", "*.yml")


# The host side of the probe: a floor failure is reported under its own
# name (not "could not run a POSIX shell"), and still lists any tools the
# presence loop found missing before the fragment exited. Pinned here so the
# pasted copies cannot drift (FR-013, T033).
HOST_BRANCH = (
    "if grep -qE 'is older than the 2\\.38 minimum|could not parse git version' docker-inspect-error.log; then\n"
    "              echo \"::error::wing-commander verify-image-prerequisites: $IMAGE failed the git version floor -- "
    "$(cat docker-inspect-error.log)${missing:+ (also missing required tool(s):$missing)}\"\n"
)


# The host side of the loader check: reported under its own message, ahead
# of (and chained to) the git-floor report, still listing missing tools.
LOADER_HOST_BRANCH = (
    "if grep -q 'no glibc dynamic loader' docker-inspect-error.log; then\n"
    "              echo \"::error::wing-commander verify-image-prerequisites: $IMAGE has "
    "$(cat docker-inspect-error.log) -- the agent action's Bun cannot run in it "
    "(Alpine/musl and distroless images need a glibc base)"
    "${missing:+ (also missing required tool(s):$missing)}\"\n"
    "            elif grep -qE 'is older than the 2\\.38 minimum|could not parse git version' docker-inspect-error.log; then\n"
)

# The probe's order: the tool loop, then the loader check, then the floor.
PROBE_HEAD = 'printf " %s" "$t"; done; '


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


def run_loader_fragment(fragment, arch, files, links=None):
    """-> (exit code, stderr stripped) of the loader fragment under sh, with
    `uname -m` stubbed to print `arch` (absent when arch is None) and its
    absolute /lib paths rooted in a temp tree holding `files` and `links`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        os.makedirs(root)
        for f in files:
            dst = root + f
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "w").close()
        for f, target in (links or {}).items():
            dst = root + f
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(root + target, dst)
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        if arch is not None:
            stub = os.path.join(bindir, "uname")
            with open(stub, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\necho %s\n" % arch)
            os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
        rooted = fragment.replace("/lib", root + "/lib")
        sh = shutil.which("sh") or "/bin/sh"
        proc = subprocess.run([sh, "-c", rooted], env={"PATH": bindir},
                              capture_output=True, text=True)
        return proc.returncode, proc.stderr.strip().replace(root, "")


def check_loader_cases(fragment, fixtures=LOADER_FIXTURES):
    errors = []
    with open(os.path.join(fixtures, "expectations.json"), encoding="utf-8") as fh:
        expectations = json.load(fh)
    if "/lib" not in fragment:
        errors.append("image-glibc-loader.sh names no /lib path, so no fixture can root it")
    for name, exp in sorted(expectations.items()):
        rc, err = run_loader_fragment(fragment, exp["uname"], exp["files"], exp.get("links"))
        if (rc == 0) != exp["pass"]:
            errors.append("loader %s: expected pass=%s, exit code was %s (%s)" % (name, exp["pass"], rc, err))
        elif not exp["pass"] and err != exp["message"]:
            errors.append("loader %s: expected message %r, got %r" % (name, exp["message"], err))
    return errors


def check_loader_stages(loader, floor, stages):
    """Every probe embeds the loader fragment byte for byte, between the
    tool loop and the git floor, and the loader's host-side report."""
    errors = []
    for path, text in stages:
        name = os.path.basename(path)
        if loader not in text:
            errors.append("%s: the image probe lacks the glibc-loader fragment from image-glibc-loader.sh" % name)
        elif PROBE_HEAD + loader + "; " + floor not in text:
            errors.append("%s: the glibc-loader fragment is not between the tool loop and the git floor" % name)
        if LOADER_HOST_BRANCH not in text:
            errors.append("%s: the image probe lacks the canonical glibc-loader failure report (LOADER_HOST_BRANCH)" % name)
    return errors


def stage_files(pattern=WORKFLOWS):
    """Every workflow with a verify-image-prerequisites job -- found by the
    job, not by the probe's own wording, so a reworded probe cannot drop a
    stage out of the check."""
    out = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if re.search(r"(?m)^  verify-image-prerequisites:\s*$", text):
            out.append((path, text))
    return out


def stage_files_from(pairs):
    """stage_files()'s selection applied to in-memory (path, text) pairs."""
    return [(p, t) for p, t in pairs if re.search(r"(?m)^  verify-image-prerequisites:\s*$", t)]


def check_stages(fragment, stages):
    errors = []
    if not stages:
        errors.append("no stage with a verify-image-prerequisites probe was found")
    for path, text in stages:
        if fragment not in text:
            errors.append("%s: the image probe lacks the git-floor fragment from image-git-floor.sh" % os.path.basename(path))
        if HOST_BRANCH not in text:
            errors.append("%s: the image probe lacks the canonical git-floor failure report (HOST_BRANCH)" % os.path.basename(path))
    return errors


GATE_62 = os.path.join(HERE, "verify-gate-62.py")


def check_gate_62(path=GATE_62):
    """Gate 62 builds the reference image and probes it like a stage does;
    it must run the same fragment, so a base image with old git fails
    there before any digest is pinned."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "image-git-floor.sh" not in text or "floor = check_git_floor(root, tag) if shell_ran else None" not in text:
        return ["verify-gate-62.py does not run image-git-floor.sh against the reference image"]
    m = re.search(r"^FLOOR_MESSAGES = \((.*?)\)$", text, re.M)
    fragment = read_fragment()
    copies = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if len(copies) != 2 or any(c not in fragment for c in copies):
        return ["verify-gate-62.py's FLOOR_MESSAGES %r are not image-git-floor.sh's own messages" % copies]
    body = re.search(r"^def check_git_floor\(.*?(?=^def |\Z)", text, re.M | re.S)
    if not body or not re.search(r"(?m)^\s+if any\(m in err for m in FLOOR_MESSAGES\):", body.group(0)):
        return ["verify-gate-62.py's check_git_floor does not classify with FLOOR_MESSAGES"]
    return []


def check_gate_62_loader(path=GATE_62):
    """Gate 62 must run image-glibc-loader.sh against the reference image
    too, and classify with the fragment's own message."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "image-glibc-loader.sh" not in text or "loader = check_glibc_loader(root, tag) if shell_ran else None" not in text:
        return ["verify-gate-62.py does not run image-glibc-loader.sh against the reference image"]
    m = re.search(r"^LOADER_MESSAGES = \((.*?)\)$", text, re.M)
    fragment = read_fragment(LOADER_FRAGMENT)
    copies = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if len(copies) != 1 or any(c not in fragment for c in copies):
        return ["verify-gate-62.py's LOADER_MESSAGES %r are not image-glibc-loader.sh's own message" % copies]
    body = re.search(r"^def check_glibc_loader\(.*?(?=^def |\Z)", text, re.M | re.S)
    if not body or not re.search(r"(?m)^\s+if any\(m in err for m in LOADER_MESSAGES\):", body.group(0)):
        return ["verify-gate-62.py's check_glibc_loader does not classify with LOADER_MESSAGES"]
    return []


def run_checks():
    fragment = read_fragment()
    loader = read_fragment(LOADER_FRAGMENT)
    stages = stage_files()
    return (check_cases(fragment) + check_stages(fragment, stages) + check_gate_62()
            + check_loader_cases(loader) + check_loader_stages(loader, fragment, stages)
            + check_gate_62_loader())


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
    if stages:
        path, text = stages[-1]
        drifted = stages[:-1] + [(path, text.replace("${missing:+ (also missing", "${missing:+ (missing"))]
        if not any("HOST_BRANCH" in e for e in check_stages(fragment, drifted)):
            failures.append("a drifted git-floor failure report was not caught")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "g62.py")
        with open(GATE_62, encoding="utf-8") as fh:
            src = fh.read()
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src.replace("floor = check_git_floor(root, tag) if shell_ran else None", "floor = None"))
        if not check_gate_62(p):
            failures.append("a Gate 62 that never runs the git floor was not caught")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src.replace("is older than the 2.38 minimum", "is too old"))
        if not check_gate_62(p):
            failures.append("a Gate 62 whose floor messages drifted from the fragment was not caught")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src.replace("if any(m in err for m in FLOOR_MESSAGES):",
                                 'if "is older than the 2.40 minimum" in err:'))
        if not check_gate_62(p):
            failures.append("a Gate 62 classifying with an inline literal was not caught")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src.replace("if any(m in err for m in FLOOR_MESSAGES):",
                                 'if "is older than the 2.40 minimum" in err:')
                     + "\n\ndef _elsewhere(err):\n    if any(m in err for m in FLOOR_MESSAGES):\n        return err\n")
        if not check_gate_62(p):
            failures.append("a FLOOR_MESSAGES test moved out of check_git_floor was not caught")
    if stages:
        path, text = stages[0]
        reworded = [(path, text.replace(fragment, "true").replace(
            'for t in $REQUIRED_TOOLS; do command -v "$t"', 'for t in $REQUIRED_TOOLS; do command -v -- "$t"'))] + stages[1:]
        if not any(os.path.basename(path) in e for e in check_stages(fragment, stage_files_from(reworded))):
            failures.append("a stage whose probe was reworded dropped out of the check")
    failures.extend(loader_self_test(fragment, stages))
    for f in failures:
        print("::error::Gate 148 self-test: " + f)
    if not failures:
        print("Gate 148 self-test: ok")
    return 1 if failures else 0


def loader_self_test(floor, stages):
    """Each drift of the glibc-loader check must fail the gate."""
    failures = []
    loader = read_fragment(LOADER_FRAGMENT)

    def caught(mutated, case):
        return any(("loader %s:" % case) in e for e in check_loader_cases(mutated))

    # (fragment, the fixture that must catch it, what the mutation is)
    mutations = [
        (loader.replace(" /lib/ld-linux-x86-64.so.2", ""), "gcompat-x86_64",
         "a fragment that dropped gcompat's /lib loader"),
        (loader.replace("/lib64/ld-linux-x86-64.so.2 ", ""), "glibc-x86_64",
         "a fragment that dropped the /lib64 loader"),
        (loader.replace("*) gl_want=;;", '*) gl_want="/lib64/ld-linux-x86-64.so.2";;'), "unknown-arch",
         "a fragment that fails an unknown arch"),
        (loader.replace("*) gl_want=;;", '*) gl_want="/lib64/ld-linux-x86-64.so.2";;'), "no-uname",
         "a fragment that fails when uname is missing"),
        (loader.replace('"/lib/ld-linux-aarch64.so.1"', '"/lib/ld-linux-aarch64.so.1 /lib64/ld-linux-x86-64.so.2"'),
         "aarch64-with-x86_64-loader", "a fragment that accepts the other arch's loader"),
        (loader.replace('if [ -e "$gl_p" ]', 'if [ -L "$gl_p" ] || [ -e "$gl_p" ]'),
         "x86_64-dangling-loader-link", "a fragment that accepts a dangling loader link"),
        (loader.replace("exit 1; fi", "fi"), "musl-x86_64",
         "a fragment that reports a missing loader but does not fail"),
        (loader.replace("no glibc dynamic loader", "glibc loader missing"), "musl-aarch64",
         "a fragment whose message drifted"),
        ("true", "musl-x86_64", "a fragment that checks nothing"),
    ]
    for mutated, case, what in mutations:
        if mutated == loader:
            failures.append("fixture setup: %s -- the mutation no longer applies to image-glibc-loader.sh" % what)
        elif not caught(mutated, case):
            failures.append("%s was not caught by the %s case" % (what, case))
    if stages:
        path, text = stages[0]
        dropped = [(path, text.replace(loader + "; ", ""))] + stages[1:]
        if not any(os.path.basename(path) in e and "glibc-loader fragment" in e
                   for e in check_loader_stages(loader, floor, dropped)):
            failures.append("a probe missing the glibc-loader fragment was not caught")
        path, text = stages[-1]
        drifted = stages[:-1] + [(path, text.replace(loader, loader.replace("x86_64)", "x86_64|amd64)")))]
        if not any(os.path.basename(path) in e for e in check_loader_stages(loader, floor, drifted)):
            failures.append("a drifted copy of the glibc-loader fragment was not caught")
        path, text = stages[0]
        moved = [(path, text.replace(PROBE_HEAD + loader + "; ", PROBE_HEAD).replace(
            "exit 1; fi; fi'", "exit 1; fi; fi; " + loader + "'"))] + stages[1:]
        if moved[0][1] == text or not any("between the tool loop" in e for e in check_loader_stages(loader, floor, moved)):
            failures.append("a glibc-loader fragment moved after the git floor was not caught")
        path, text = stages[-1]
        report = [(path, text.replace("need a glibc base)", "need glibc)"))] + stages[:-1]
        if not any("LOADER_HOST_BRANCH" in e for e in check_loader_stages(loader, floor, report)):
            failures.append("a drifted glibc-loader failure report was not caught")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "g62.py")
        with open(GATE_62, encoding="utf-8") as fh:
            src = fh.read()
        g62 = [
            (src.replace("loader = check_glibc_loader(root, tag) if shell_ran else None", "loader = None"),
             "a Gate 62 that never runs the glibc loader check"),
            (src.replace('LOADER_MESSAGES = ("no glibc dynamic loader",)', 'LOADER_MESSAGES = ("no loader",)'),
             "a Gate 62 whose loader message drifted from the fragment"),
            (src.replace("if any(m in err for m in LOADER_MESSAGES):", 'if "no glibc" in err:'),
             "a Gate 62 classifying the loader with an inline literal"),
        ]
        for mutated, what in g62:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(mutated)
            if mutated == src:
                failures.append("fixture setup: %s -- the mutation no longer applies to verify-gate-62.py" % what)
            elif not check_gate_62_loader(p):
                failures.append("%s was not caught" % what)
    return failures


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
