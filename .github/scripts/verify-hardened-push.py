#!/usr/bin/env python3
"""Gate 142 -- pushes after agent code ran use the one hardened idiom (spec
095 FR-015..FR-017, FR-022).

Static half:
  1. In every covered job (COVERED_JOBS: the jobs where an agent wrote the
     checkout, or that publish what one wrote), no `run:` line invokes
     `git push`: a push goes through ./.github/actions/
     wing-commander-hardened-push, or through a composite that hardens its
     own git environment (rule 2).
  2. Every composite reachable from a covered job whose `run:` body pushes
     sources _shared/git-push-hardening.sh and calls wc_harden_git_env
     before its first `git push` (publish-stranded-commits and
     fold-commit; hardened-push.sh does the same in _shared/).
  3. Single home (FR-022): the hardening idiom (core.hooksPath,
     GIT_CONFIG_NOSYSTEM) is spelled nowhere outside
     _shared/git-push-hardening.sh -- no workflow, composite or other
     shared script pastes it.

Behavioural half: the shared script is driven against a real local git
repository and a temp bare remote with (a) a planted `pre-push` hook and
(b) a planted `url.<base>.insteadOf` rewrite aimed at a decoy remote. The
hook must not run and the push must land on the real remote, not the decoy.
And (c) a GIT_CONFIG_KEY_0 the caller already set (a container job's
safe.directory) survives the hardening: its entries are appended, never
written over -- overwriting it makes every git call in a container job
refuse the workspace as dubious ownership.

Usage:
    python3 .github/scripts/verify-hardened-push.py
    python3 .github/scripts/verify-hardened-push.py --self-test
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures", "095-hardened-push")
SHARED = os.path.join(ROOT, ".github", "actions", "_shared")
SCRIPT = os.path.join(SHARED, "hardened-push.sh")
HARDENING = os.path.join(SHARED, "git-push-hardening.sh")
COMPOSITE = "wing-commander-hardened-push"
# Jobs where an agent wrote the checkout, or that publish what one wrote.
COVERED_JOBS = {
    "board-loop.yml": ("fix-agent", "fix", "review", "review-fixup-publish"),
    "implement.yml": ("implement",),
    "pr-conversation.yml": ("act",),
}

RAW_PUSH_RE = re.compile(r"(?<![\w-])git\s+(?:-\S+\s+)*push\b")
# The hardening's own spellings -- not every core.hooksPath (pr-conversation
# points it at its run-attribution hook on purpose).
IDIOM_RE = re.compile(r"GIT_CONFIG_NOSYSTEM|core\.hooksPath[\s=\"']+/dev/null"
                      r"|GIT_CONFIG_VALUE_\w*\s*[=:]\s*[\"']?/dev/null")
HARDEN_CALL = "wc_harden_git_env"
USES_RE = re.compile(r"\.github/actions/([\w-]+)/?$")
COMMENT_LINE_RE = re.compile(r"^[ \t]*#[^\n]*$", re.MULTILINE)


def _code(text):
    return COMMENT_LINE_RE.sub("", text)


def check_doc(name, doc, jobs):
    """Rule 1 over a parsed workflow's covered jobs."""
    errors = []
    all_jobs = (doc or {}).get("jobs") or {}
    for job_id in jobs:
        if job_id not in all_jobs:
            errors.append("{0}: covered job {1!r} is gone -- the push sites moved out of "
                          "view".format(name, job_id))
            continue
        for step in all_jobs[job_id].get("steps") or []:
            if not isinstance(step, dict):
                continue
            for line in _code(str(step.get("run", ""))).splitlines():
                if RAW_PUSH_RE.search(line):
                    errors.append("{0}: job {1!r} step {2!r}: raw `git push` at a covered "
                                  "site; use the {3} composite".format(
                                      name, job_id, step.get("name") or step.get("id"),
                                      COMPOSITE))
    return errors


def reachable(docs, root=ROOT):
    """{composite name: action.yml text} reachable from the covered jobs."""
    pending = []
    for name, jobs in COVERED_JOBS.items():
        all_jobs = (docs.get(name) or {}).get("jobs") or {}
        for job_id in jobs:
            for step in (all_jobs.get(job_id) or {}).get("steps") or []:
                m = USES_RE.search(str((step or {}).get("uses", "")))
                if m:
                    pending.append(m.group(1))
    found = {}
    while pending:
        comp = pending.pop()
        if comp in found:
            continue
        path = os.path.join(root, ".github", "actions", comp, "action.yml")
        with open(path, encoding="utf-8") as fh:
            found[comp] = fh.read()
        for line in found[comp].splitlines():
            m = re.search(r"uses:\s*\S*\.github/actions/([\w-]+)", line)
            if m:
                pending.append(m.group(1))
    return found


def composite_errors(name, text):
    """Rule 2 over one composite's (or shared script's) text."""
    code = _code(text)
    push = RAW_PUSH_RE.search(code)
    if not push:
        return []
    harden = code.find(HARDEN_CALL + "\n")
    if harden < 0:
        harden = code.find(HARDEN_CALL)
    sourced = "git-push-hardening.sh" in code
    if not sourced or harden < 0 or harden > push.start():
        return ["{0}: pushes without calling {1} from _shared/git-push-hardening.sh first -- "
                "a planted hook or global config would run with the token".format(
                    name, HARDEN_CALL)]
    return []


def single_home_errors(paths):
    """Rule 3: the idiom is spelled only in git-push-hardening.sh."""
    errors = []
    for path in paths:
        if os.path.abspath(path) == os.path.abspath(HARDENING):
            continue
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(_code(fh.read()).splitlines(), 1):
                if IDIOM_RE.search(line):
                    errors.append("{0}:{1}: hardening idiom pasted instead of using the {2} "
                                  "composite / git-push-hardening.sh".format(
                                      os.path.relpath(path, ROOT), lineno, COMPOSITE))
    return errors


def idiom_paths(root=ROOT):
    paths = []
    for pattern_dir, exts in ((os.path.join(root, ".github", "workflows"), (".yml", ".yaml")),
                              (os.path.join(root, ".github", "actions"), (".yml", ".yaml", ".sh"))):
        for dirpath, _dirs, files in os.walk(pattern_dir):
            paths += [os.path.join(dirpath, f) for f in files if f.endswith(exts)]
    return sorted(paths)


def _git(args, cwd, env=None):
    full = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    full.update(env or {})
    return subprocess.run(["git"] + args, cwd=cwd, env=full, check=True,
                          capture_output=True, text=True)


def check_behaviour(push_cmd):
    """`push_cmd(workdir, env, head, branch)` runs a push; returns errors."""
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


def check_preserves_caller_config(hardening=HARDENING):
    """(c): a caller's GIT_CONFIG_KEY_0 survives wc_harden_git_env."""
    script = (". \"$1\"\nwc_harden_git_env\n"
              "printf '%s|%s\\n' \"$(git config --get user.name)\" "
              "\"$(git config --get core.hooksPath)\"\n")
    env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.name",
               GIT_CONFIG_VALUE_0="caller-entry")
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run(["bash", "-c", script, "harness", hardening], cwd=tmp, env=env,
                             capture_output=True, text=True).stdout.strip()
    if out != "caller-entry|/dev/null":
        return ["wc_harden_git_env does not keep the caller's GIT_CONFIG_KEY_0 and add "
                "core.hooksPath=/dev/null after it (got {0!r}) -- a container job's "
                "safe.directory entry would be lost".format(out)]
    return []


def hardened_push(work, env, head, branch, script=SCRIPT):
    full = dict(os.environ, **env)
    subprocess.run(["bash", script, branch, head], cwd=work, env=full,
                   capture_output=True, text=True)


def naive_push(work, env, head, branch):
    base = env["PUSH_SERVER_URL"] + "/" + env["GITHUB_REPOSITORY"] + ".git"
    subprocess.run(["git", "push", base, "HEAD:refs/heads/" + branch], cwd=work,
                   env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                            GIT_CONFIG_NOSYSTEM="1"),
                   capture_output=True, text=True)


def _load_workflows(root=ROOT):
    docs = {}
    for name in COVERED_JOBS:
        with open(os.path.join(root, ".github", "workflows", name), encoding="utf-8") as fh:
            docs[name] = yaml.safe_load(fh)
    return docs


def static_errors(docs, root=ROOT):
    errors = []
    for name, jobs in COVERED_JOBS.items():
        errors += check_doc(name, docs[name], jobs)
    for comp, text in sorted(reachable(docs, root).items()):
        errors += composite_errors(comp + "/action.yml", text)
    with open(SCRIPT, encoding="utf-8") as fh:
        errors += composite_errors("_shared/hardened-push.sh", fh.read())
    errors += single_home_errors(idiom_paths(root))
    return errors


def run():
    errors = (static_errors(_load_workflows()) + check_behaviour(hardened_push)
              + check_preserves_caller_config())
    for err in errors:
        print("::error::Gate 142: " + err)
    if not errors:
        print("verify-hardened-push: ok")
    return 1 if errors else 0


def self_test():
    failures = []

    def fixture(name):
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    if not check_doc("raw-push.yml", fixture("raw-push.yml"), ("publish",)):
        failures.append("raw push not detected")
    if not single_home_errors([os.path.join(FIXTURES, "pasted-idiom.yml")]):
        failures.append("pasted idiom not detected")
    if check_doc("composite-use.yml", fixture("composite-use.yml"), ("publish",)):
        failures.append("composite use rejected")
    for name, want in (("unhardened-composite.yml", True), ("hardened-composite.yml", False)):
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
            if bool(composite_errors(name, fh.read())) != want:
                failures.append("{0}: composite rule said {1}".format(name, not want))
    naive = check_behaviour(naive_push)
    if not any("hook ran" in e for e in naive):
        failures.append("planted hook not detected on a naive push")
    if not any("insteadOf" in e for e in naive):
        failures.append("planted insteadOf not detected on a naive push")
    # Mutations of the shipped files, each of which must fail.
    docs = _load_workflows()
    if static_errors(docs):
        failures.append("the shipped workflows already fail: {0}".format(static_errors(docs)))
    # T031: a raw push put back at each real covered site is caught there.
    for name, jobs in COVERED_JOBS.items():
        for job_id in jobs:
            mutated = _load_workflows()
            mutated[name]["jobs"][job_id]["steps"].append(
                {"name": "x", "run": "if ! git push origin \"HEAD:refs/heads/$BRANCH\"; then "
                                     "exit 1; fi\n"})
            if not any("raw `git push`" in e and "{0!r}".format(job_id) in e
                       for e in static_errors(mutated)):
                failures.append("a raw `if ! git push` in {0} {1} not detected".format(
                    name, job_id))
    with tempfile.TemporaryDirectory() as tmp:
        with open(HARDENING, encoding="utf-8") as fh:
            text = fh.read()
        overwrite = os.path.join(tmp, "git-push-hardening.sh")
        old = 'n="${GIT_CONFIG_COUNT:-0}"'
        if old not in text:
            sys.exit("::error::Gate 142 self-test: {0!r} not in git-push-hardening.sh".format(old))
        with open(overwrite, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, "n=0"))
        if not check_preserves_caller_config(overwrite):
            failures.append("a hardening that overwrites GIT_CONFIG_KEY_0 not detected")
        shim_less = os.path.join(tmp, "hardened-push.sh")
        with open(SCRIPT, encoding="utf-8") as fh:
            ptext = fh.read()
        tail = ptext.index("shim=\"$(mktemp -d)\"")
        with open(shim_less, "w", encoding="utf-8") as fh:
            fh.write(ptext[:tail] + 'git push --no-verify "$url" "HEAD:refs/heads/${branch}"\n')
        shutil.copy(HARDENING, overwrite)
        got = check_behaviour(lambda w, e, h, b: hardened_push(w, e, h, b, shim_less))
        if not any("insteadOf" in e for e in got):
            failures.append("a push from the workspace (no shim) not caught by the planted "
                            "insteadOf")
    for failure in failures:
        print("SELF-TEST FAIL: " + failure, file=sys.stderr)
    if failures:
        return 1
    print("verify-hardened-push self-test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
