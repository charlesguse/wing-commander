#!/usr/bin/env python3
"""Gate 62 - the e2e reference image's tool set agrees with required-tools.txt.

Gate 23's existing drift check is purely textual: it compares the
`REQUIRED_TOOLS=` string literal embedded in each stage's
verify-image-prerequisites job against .github/scripts/required-tools.txt.
That check cannot fail if .github/docker/e2e-reference-image/Dockerfile
silently stops installing a tool the text still claims to install --
Constitution VIII ("a green check means what it says") is violated the
moment a check like that is trusted to guard a real artifact it never
inspects.

This gate is the version of the check that CAN fail on its own subject: it
`docker build`s the reference image locally (no push) and runs the exact
same one-container-start-checks-everything probe every stage's
verify-image-prerequisites job already runs against an adopter's image
(research.md D6):

    docker run --rm --entrypoint sh "$IMAGE" -c \
      'for t in $REQUIRED_TOOLS; do command -v "$t" || echo "missing:$t"; done'

against .github/scripts/required-tools.txt, naming every missing tool at
once rather than stopping at the first.

Self-test (--self-test): copies the Dockerfile and required-tools.txt into
an isolated temp tree, then (a) builds the real, unmodified pair and expects
a clean pass, and (b) removes one real tool's install from a copy of the
Dockerfile and expects the failure to name that tool -- proving this gate's
failure branch actually fails on its own subject (Constitution VIII), the
exact gap Gate 23's textual-only check leaves open.

Usage: python3 .github/scripts/verify-gate-62.py [--self-test]
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOCKERFILE_DIR = ".github/docker/e2e-reference-image"
REQUIRED_TOOLS_FILE = ".github/scripts/required-tools.txt"
IMAGE_TAG = "wing-commander-gate-62-reference-image:local"


def read_required_tools(root="."):
    tools = []
    with io.open(os.path.join(root, REQUIRED_TOOLS_FILE), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tools.append(line)
    return tools


def build_image(root, tag):
    proc = subprocess.run(
        ["docker", "build", "-t", tag, os.path.join(root, DOCKERFILE_DIR)],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)


def check_tools(tag, tools):
    """-> (missing tools or None if no shell could be started, log tail)."""
    proc = subprocess.run(
        ["docker", "run", "--rm", "-e", "REQUIRED_TOOLS=" + " ".join(tools),
         "--entrypoint", "sh", tag, "-c",
         'for t in $REQUIRED_TOOLS; do command -v "$t" >/dev/null 2>&1 || '
         'echo "missing:$t"; done'],
        capture_output=True, text=True,
    )
    missing = [line.split("missing:", 1)[1]
               for line in proc.stdout.splitlines() if line.startswith("missing:")]
    if proc.returncode != 0 and not proc.stdout.strip():
        return None, (proc.stdout + proc.stderr)
    return missing, (proc.stdout + proc.stderr)


def scan(root=".", tag=IMAGE_TAG):
    failures = []
    tools = read_required_tools(root)
    ok, log = build_image(root, tag)
    if not ok:
        failures.append(
            f"docker build of {DOCKERFILE_DIR}/Dockerfile failed -- {log[-2000:]}")
        return failures
    try:
        missing, log = check_tools(tag, tools)
        if missing is None:
            failures.append(
                f"could not run a POSIX shell inside the built image to check its "
                f"prerequisites -- {log[-1000:]}")
        elif missing:
            failures.append(
                f"the reference image built from {DOCKERFILE_DIR}/Dockerfile is "
                f"missing required tool(s) named in {REQUIRED_TOOLS_FILE}: "
                + ", ".join(missing))
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, text=True)
    return failures


def _copy_subject(dst):
    shutil.copytree(DOCKERFILE_DIR, os.path.join(dst, DOCKERFILE_DIR))
    os.makedirs(os.path.dirname(os.path.join(dst, REQUIRED_TOOLS_FILE)), exist_ok=True)
    shutil.copy(REQUIRED_TOOLS_FILE, os.path.join(dst, REQUIRED_TOOLS_FILE))


def self_test():
    problems = []
    root = tempfile.mkdtemp(prefix="verify_gate_62_")
    try:
        # (a) the real Dockerfile and required-tools.txt, unmodified
        clean = os.path.join(root, "clean")
        _copy_subject(clean)
        got = scan(clean, tag=IMAGE_TAG + "-clean")
        if got:
            problems.append("clean copy of the real image FAILED: " + "; ".join(got))

        # (b) the Dockerfile silently drops one real tool's install -- the
        # exact gap Gate 23's textual-only check cannot see, since the
        # embedded REQUIRED_TOOLS= literal and required-tools.txt both stay
        # untouched here.
        drifted = os.path.join(root, "drifted")
        _copy_subject(drifted)
        dockerfile_path = os.path.join(drifted, DOCKERFILE_DIR, "Dockerfile")
        with io.open(dockerfile_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        kept = [ln for ln in lines if ln.strip().rstrip("\\").strip() != "jq"]
        if len(kept) == len(lines):
            problems.append("fixture setup: expected the reference Dockerfile to "
                             "install jq on its own continuation line -- self-test "
                             "can no longer construct its drift fixture, update it "
                             "to drop a different tool")
        else:
            with io.open(dockerfile_path, "w", encoding="utf-8") as fh:
                fh.writelines(kept)
            got = scan(drifted, tag=IMAGE_TAG + "-drifted")
            if not any("jq" in g for g in got):
                problems.append(f"a Dockerfile that stopped installing jq was NOT "
                                 f"detected as missing jq; got: {got}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 62 self-test: {p}")
    if problems:
        return 1
    print("Gate 62 self-test: a clean build of the real image passes; a Dockerfile "
          "that silently stops installing a required tool fails, naming it.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::Gate 62: {f}")
    print(f"Gate 62: the e2e reference image's tool set agrees with "
          f"{REQUIRED_TOOLS_FILE}; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
