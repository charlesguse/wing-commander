#!/usr/bin/env python3
"""Pushes after agent code ran use the one hardened idiom (spec 095
FR-015..FR-017, FR-022).

Static half: at every covered workflow, a push step must go through
./.github/actions/wing-commander-hardened-push -- a raw `git push` is a
failure, and so is the hardening idiom (core.hooksPath / GIT_CONFIG_NOSYSTEM)
pasted into a workflow instead of used from the composite. The idiom's one
home is .github/actions/_shared/hardened-push.sh.

Behavioural half: the shared script is driven against a real local git
repository and a temp bare remote with (a) a planted `pre-push` hook and
(b) a planted `url.<base>.insteadOf` rewrite aimed at a decoy remote. The
hook must not run and the push must land on the real remote, not the decoy.

COVERED_WORKFLOWS grows as T025-T027/T031 convert each real push site.

Usage:
    python3 .github/scripts/verify-hardened-push.py
    python3 .github/scripts/verify-hardened-push.py --self-test
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures", "095-hardened-push")
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "hardened-push.sh")
COMPOSITE = "wing-commander-hardened-push"
# Workflows whose push sites are already converted; each is held to the rule.
COVERED_WORKFLOWS = ()

RAW_PUSH_RE = re.compile(r"^\s*(?:run:\s*)?git\s+push\b", re.M)
IDIOM_RE = re.compile(r"core\.hooksPath|GIT_CONFIG_NOSYSTEM")


def check_text(name, text):
    errors = []
    if COMPOSITE not in text and RAW_PUSH_RE.search(text):
        errors.append("{0}: raw `git push` at a covered site; use the {1} "
                      "composite".format(name, COMPOSITE))
    if IDIOM_RE.search(text):
        errors.append("{0}: hardening idiom pasted instead of using the {1} "
                      "composite".format(name, COMPOSITE))
    return errors


def check_static(paths):
    errors = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            errors += check_text(os.path.basename(path), fh.read())
    return errors


def _git(args, cwd, env=None):
    full = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    full.update(env or {})
    return subprocess.run(["git"] + args, cwd=cwd, env=full, check=True,
                          capture_output=True, text=True)


def check_behaviour(push_cmd):
    """`push_cmd(workdir, env, head)` runs a push; returns a list of errors."""
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        real = os.path.join(tmp, "owner", "repo.git")
        decoy = os.path.join(tmp, "decoy.git")
        work = os.path.join(tmp, "work")
        marker = os.path.join(tmp, "hook-ran")
        for bare in (real, decoy):
            os.makedirs(bare)
            _git(["init", "--quiet", "--bare"], bare)
        os.makedirs(work)
        _git(["init", "--quiet"], work)
        _git(["config", "user.email", "t@example.invalid"], work)
        _git(["config", "user.name", "t"], work)
        with open(os.path.join(work, "f"), "w") as fh:
            fh.write("x")
        _git(["add", "f"], work)
        _git(["commit", "--quiet", "-m", "c"], work)
        head = _git(["rev-parse", "HEAD"], work).stdout.strip()
        hook = os.path.join(work, ".git", "hooks", "pre-push")
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\ntouch '{0}'\n".format(marker))
        os.chmod(hook, 0o755)
        base = "file://" + tmp
        # Rewrite the real remote URL to the decoy bare repository.
        _git(["config", "url.{0}/decoy.git.insteadOf".format(base),
              base + "/owner/repo.git"], work)
        env = {"GITHUB_REPOSITORY": "owner/repo", "PUSH_SERVER_URL": base}
        push_cmd(work, env, head, "main")
        if os.path.exists(marker):
            errors.append("planted pre-push hook ran")
        landed = subprocess.run(["git", "rev-parse", "--verify", "refs/heads/main"],
                                cwd=real, capture_output=True, text=True)
        if landed.returncode != 0 or landed.stdout.strip() != head:
            errors.append("push did not land on the real remote "
                          "(planted insteadOf redirected it)")
    return errors


def hardened_push(work, env, head, branch):
    full = dict(os.environ, **env)
    subprocess.run(["bash", SCRIPT, branch, head], cwd=work, env=full,
                   capture_output=True, text=True)


def naive_push(work, env, head, branch):
    base = env["PUSH_SERVER_URL"] + "/" + env["GITHUB_REPOSITORY"] + ".git"
    subprocess.run(["git", "push", base, "HEAD:refs/heads/" + branch], cwd=work,
                   env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                            GIT_CONFIG_NOSYSTEM="1"),
                   capture_output=True, text=True)


def covered_paths():
    return [os.path.join(ROOT, ".github", "workflows", name)
            for name in COVERED_WORKFLOWS]


def run():
    errors = check_static(covered_paths()) + check_behaviour(hardened_push)
    for err in errors:
        print("::error::" + err)
    if not errors:
        print("verify-hardened-push: ok")
    return 1 if errors else 0


def self_test():
    failures = []

    def fixture(name):
        return os.path.join(FIXTURES, name)

    if not check_static([fixture("raw-push.yml")]):
        failures.append("raw push not detected")
    if not check_static([fixture("pasted-idiom.yml")]):
        failures.append("pasted idiom not detected")
    if check_static([fixture("composite-use.yml")]):
        failures.append("composite use rejected")
    naive = check_behaviour(naive_push)
    if not any("hook ran" in e for e in naive):
        failures.append("planted hook not detected on a naive push")
    if not any("insteadOf" in e for e in naive):
        failures.append("planted insteadOf not detected on a naive push")
    for failure in failures:
        print("SELF-TEST FAIL: " + failure, file=sys.stderr)
    if failures:
        return 1
    print("verify-hardened-push self-test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
