#!/usr/bin/env python3
"""Gate 46 -- actionlint over every workflow file, at PR time.

GitHub evaluates a ${{ }} reference to a not-yet-defined step id as
empty, silently, so an `if:` reading a step defined below it is
constant-false and the step never runs. GitHub's own parser cannot flag
that (expression semantics are outside its scope); actionlint type-checks
each expression against a steps context built from the steps ABOVE it, so
a use-before-definition is a hard diagnostic naming the line.

release.yml's Gate 1a has run actionlint since specs/031, but only on a
workflow_dispatch release. This is the PR-time (and, via
run-local-gates.py, pre-push) half, over EVERY workflow file rather than
the published stages alone -- lint-workflows.yml and release.yml carry
${{ }} expressions too. Gate 1a's pass 1 now invokes this same script, so
the two answers cannot drift (the Gate 31 arrangement), and its pass 2
reuses the pinned binary this one downloads (--ensure-binary).

THE TWO ALLOWANCES (actionlint 1.7.7 schema gaps, both verified real)
---------------------------------------------------------------------
- github.job_workflow_sha: a documented context property 1.7.7 does not
  know (specs/031 research.md D3). -ignore'd outright -- the message
  names the property, so nothing else can hide behind the pattern.
- environment.deployment: GitHub accepts and acts on the key
  (specs/031-stage-environment-binding/contracts/environment-binding.md);
  1.7.7's schema knows only name/url. NOT -ignore'd: counted instead,
  exactly one diagnostic per `deployment:` line, so the allowance goes
  loudly stale the day actionlint learns the key. See classify().

Shell/pyflakes lint of run: blocks stays release.yml pass 2's job (#149
tracks widening it): shellcheck is not on a maintainer's Windows machine,
and a gate needing it locally would fail on the environment rather than
the code. `-shellcheck= -pyflakes=` keeps this gate byte-identical
between CI and run-local-gates.py.
"""
import glob
import io
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ACTIONLINT_VERSION = "1.7.7"
KNOWN = 'unexpected key "deployment" for "environment" section'
IGNORED = 'property "job_workflow_sha" is not defined'
WORKFLOWS_DIR = ".github/workflows"
# The binding is a job-level environment sub-key: jobs(0) / <job>(2) /
# environment(4) / deployment(6). Matched on the key's own line rather
# than the full binding so this file never contains a literal GitHub
# expression (release.yml Gate 1a's original reasoning, kept verbatim).
BINDING_RE = re.compile(r"^ {6}deployment:")


def binary_name():
    return "actionlint.exe" if os.name == "nt" else "actionlint"


def ensure_binary():
    """Path to the pinned actionlint, downloading into a temp cache once.

    Cached under the OS temp dir (RUNNER_TEMP in CI) rather than the
    checkout: a lint gate has no business leaving a file in the tree it
    lints, and the version in the directory name makes a bump a fresh
    download rather than a stale hit.
    """
    cache = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(),
                         f"wc-actionlint-{ACTIONLINT_VERSION}")
    target = os.path.join(cache, binary_name())
    if os.path.exists(target):
        return target
    os.makedirs(cache, exist_ok=True)

    machine = os.environ.get("PROCESSOR_ARCHITECTURE", "") \
        if os.name == "nt" else os.uname().machine
    arch = "arm64" if machine.lower() in ("arm64", "aarch64") else "amd64"
    if sys.platform.startswith("win"):
        osname, ext = "windows", "zip"
    elif sys.platform == "darwin":
        osname, ext = "darwin", "tar.gz"
    else:
        osname, ext = "linux", "tar.gz"
    url = (f"https://github.com/rhysd/actionlint/releases/download/"
           f"v{ACTIONLINT_VERSION}/actionlint_{ACTIONLINT_VERSION}_"
           f"{osname}_{arch}.{ext}")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = resp.read()
    except OSError as e:
        sys.exit(f"could not download actionlint {ACTIONLINT_VERSION} "
                 f"({url}): {e}. If this machine is offline, note that CI "
                 f"runs this gate regardless -- it is not skippable by "
                 f"being unreachable.")
    # Extracted next to the target and renamed into place, so a second
    # runner racing this one sees either nothing or a whole binary.
    part = target + ".part"
    if ext == "zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as z, \
                open(part, "wb") as out:
            out.write(z.read(binary_name()))
    else:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as t:
            member = t.extractfile(binary_name())
            with open(part, "wb") as out:
                out.write(member.read())
        os.chmod(part, os.stat(part).st_mode
                 | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(part, target)
    return target


def workflow_files(root="."):
    base = os.path.join(root, WORKFLOWS_DIR)
    return sorted(glob.glob(os.path.join(base, "*.yml"))
                  + glob.glob(os.path.join(base, "*.yaml")))


def count_bindings(files):
    total = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            total += sum(1 for line in fh if BINDING_RE.match(line))
    return total


def run_actionlint(binary, files, extra_ignores=()):
    """Diagnostic lines from the schema/expression pass, one per line."""
    cmd = [binary, "-no-color", "-oneline", "-shellcheck=", "-pyflakes=",
           "-ignore", IGNORED]
    for pat in extra_ignores:
        cmd += ["-ignore", pat]
    proc = subprocess.run(cmd + list(files), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    return [l for l in out.splitlines() if l.strip()]


def classify(diag_lines, bindings):
    """The allowance accounting, as a pure function so --self-test can
    drive its failure branches without faking a linter run.

    Returns (errors, other_lines): errors non-empty means the gate
    fails; other_lines are the diagnostics beyond the accounted
    environment.deployment allowance, for printing.
    """
    seen = sum(1 for l in diag_lines if KNOWN in l)
    other = [l for l in diag_lines if KNOWN not in l]
    errors = []
    if other:
        errors.append(f"actionlint reported {len(other)} diagnostic(s) "
                      f"beyond the known environment.deployment schema gap.")
    if bindings > 0 and seen == 0:
        errors.append(f"actionlint no longer flags environment.deployment "
                      f"({bindings} binding(s), 0 diagnostics) -- its schema "
                      f"has learned the key. Delete this allowance and the "
                      f"counting around it.")
    elif seen != bindings:
        errors.append(f"expected one environment.deployment diagnostic per "
                      f"binding ({bindings}), saw {seen} -- either a binding "
                      f"is going unlinted or an unrelated diagnostic is "
                      f"being counted as known.")
    return errors, other


def run_gate():
    files = workflow_files()
    # A derived-empty set must not read as a clean pass -- the same
    # reasoning as Gate 7's stages == 0 guard.
    if not files:
        sys.exit(f"no workflow files found under {WORKFLOWS_DIR} -- "
                 f"this gate linted nothing. Run from the repository root.")
    binary = ensure_binary()
    diags = run_actionlint(binary, files)
    bindings = count_bindings(files)
    errors, other = classify(diags, bindings)
    for line in other:
        print(line)
    for e in errors:
        print(f"::error::{e}")
    print(f"Gate 46: {len(files)} workflow file(s), {bindings} binding(s), "
          f"{len(diags) - len(other)} accounted diagnostic(s), "
          f"{len(other)} other.")
    return 1 if errors else 0


def self_test():
    """The linter flags what this gate exists to catch, and the
    accounting's failure branches actually fire.

    The forward-reference fixture is the PR #277 shape itself: an `if:`
    reading a step id defined below it. If a future actionlint bump
    stops flagging that, this gate is no longer checking the thing it
    was built for, and this is what says so.
    """
    binary = ensure_binary()
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        fwd = os.path.join(td, "forward-ref.yml")
        with open(fwd, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on: push\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - name: reads an id defined below\n"
                "        if: steps.later.outputs.x != ''\n"
                "        run: echo unreachable\n"
                "      - id: later\n"
                "        run: echo \"x=1\" >> \"$GITHUB_OUTPUT\"\n")
        diags = run_actionlint(binary, [fwd])
        check("use-before-definition is a diagnostic",
              any('"later" is not defined' in l for l in diags),
              f"got {diags!r}")
        errors, _ = classify(diags, 0)
        check("and the accounting fails the gate on it", bool(errors))

        binding = os.path.join(td, "binding.yml")
        with open(binding, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on: push\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    environment:\n"
                "      name: pipeline\n"
                "      deployment: wc-test\n"
                "    steps:\n"
                "      - run: echo ok\n")
        diags = run_actionlint(binary, [binding])
        bindings = count_bindings([binding])
        check("a deployment binding is counted, not ignored",
              bindings == 1 and sum(1 for l in diags if KNOWN in l) == 1,
              f"bindings={bindings} diags={diags!r}")
        errors, _ = classify(diags, bindings)
        check("and balances to a clean pass", not errors, f"got {errors!r}")

    # The accounting's failure branches, driven directly (pure function).
    errors, _ = classify([], 3)
    check("stale allowance fires when bindings exist but nothing is flagged",
          any("has learned the key" in e for e in errors))
    errors, _ = classify([f"a.yml:1:1: {KNOWN} [syntax-check]"], 2)
    check("an unlinted binding fires the imbalance branch",
          any("going unlinted" in e for e in errors))
    errors, _ = classify(["a.yml:1:1: something real [expression]"], 0)
    check("a real diagnostic is never absorbed by the allowance",
          any("beyond the known" in e for e in errors))

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    if argv == ["--ensure-binary"]:
        print(ensure_binary())
        return 0
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test, "
                 f"--ensure-binary, or nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
