#!/usr/bin/env python3
"""Gate 110 - wing-commander-fold-commit's own `run:` step performs the
real append/flip/union/commit/push sequence against a real git repo, and
leaves the tree and the remote untouched when there is nothing to fold
(specs/062-lifecycle-review-gate T031/T032).

WHY THIS EXISTS
---------------
This composite is the single home CLAUDE.md's "Shared logic has exactly
one home" rule requires before pr-conversation.yml's `act` job (T033) and
lifecycle-review-gate.yml's `disposition` job (T038) can both fold a
tasks.md section without pasting the append/flip/commit/push sequence a
second time. Running the SHIPPED step (via wc_shell_harness.run_step
against a real git clone, not a copy of it and not a mock of git) is the
whole point: a copy could sit green for weeks while checking a sequence
that did not ship, and a mock could hide a real push failure.

    python3 .github/scripts/verify-fold-commit-composite.py
    python3 .github/scripts/verify-fold-commit-composite.py --self-test
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

ACTION = ".github/actions/wing-commander-fold-commit/action.yml"
STEP_NAME = "Append, flip, and commit the fold"
SPEC_DIR = "specs/999-fold-commit-harness"
BASH = None

GH_STUB = """#!/usr/bin/env bash
if [ "$1" = "api" ] && [ "$2" = "user" ]; then
  echo '{"login": "wing-commander-bot[bot]"}'
  exit 0
fi
exit 1
"""


def _sh(script, cwd):
    global BASH
    if BASH is None:
        BASH = resolve_bash()
    path = os.path.join(cwd, "_setup.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def make_repo(root, initial_re_review=("alice",)):
    """A real git repo (bare remote + clone) seeded with tasks.md and
    spec-meta.json on `main`. Returns (repo_path, remote_path, base_sha)."""
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    meta = json.dumps({"stage": "review",
                       "pending_re_review_from": list(initial_re_review)})
    setup = """
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
mkdir -p '{spec_dir}'
printf '%s\\n' '# Tasks' > '{spec_dir}/tasks.md'
printf '%s\\n' '{meta}' > '{spec_dir}/spec-meta.json'
git add -A
git commit -q -m seed
git push -q origin main
git rev-parse HEAD
""".format(remote=remote, repo=repo, spec_dir=SPEC_DIR, meta=meta)
    proc = _sh(setup, work)
    if proc.returncode != 0:
        sys.exit("::error::verify-fold-commit-composite: harness could not "
                 "seed a git workspace: {0}{1}".format(proc.stdout, proc.stderr))
    base_sha = proc.stdout.strip().splitlines()[-1]
    return repo, remote, base_sha


def _stub_gh(root):
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(path, 0o755)
    return bindir


def remote_head_sha(remote):
    proc = subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip()


def remote_head_subject(remote):
    proc = subprocess.run(
        ["git", "--git-dir", remote, "log", "-1", "--format=%s", "main"],
        capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip()


def run_fold(root, step_script, section_content, fold_id="leg-a",
            summary="a summary", actor="bob", initial_re_review=("alice",)):
    """Seeds a fresh repo, runs `step_script` (the shipped step unless the
    caller mutated it) against it, and returns (repo, remote, base_sha, rc,
    out, outputs)."""
    repo, remote, base_sha = make_repo(root, initial_re_review)
    bindir = _stub_gh(root)
    if section_content is None:
        section_path = os.path.join(root, "missing-section.md")
    else:
        fd, section_path = tempfile.mkstemp(dir=root, suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(section_content)
    env = {
        "GH_TOKEN": "x",
        "SPEC_DIR": SPEC_DIR,
        "SECTION_FILE": section_path,
        "FOLD_ID": fold_id,
        "FOLD_SUMMARY": summary,
        "ACTOR_LOGIN": actor,
        "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
        # spec 095: the step sources _shared/git-push-hardening.sh beside
        # the shipped composite.
        "GITHUB_ACTION_PATH": os.path.dirname(os.path.abspath(ACTION)),
        "PUSH_TOKEN": "",
    }
    rc, out, outputs, _summary = run_step(resolve_bash(), step_script, repo,
                                          env, root)
    return repo, remote, base_sha, rc, out, outputs


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return fh.read()


def run():
    failures = []
    root = tempfile.mkdtemp(prefix="wc-fold-commit-")
    try:
        step = find_step(ACTION, STEP_NAME)
        script = step.get("run") or ""
        if not script:
            sys.exit("::error::verify-fold-commit-composite: step {0!r} in "
                     "{1} has no run: body.".format(STEP_NAME, ACTION))

        # Case 1: a non-empty section-file folds for real.
        before1 = len(failures)
        section = "## A new section\n\n- [ ] T999 do the thing\n"
        repo, remote, base_sha, rc, out, outputs = run_fold(
            root, script, section, fold_id="leg-a", summary="fold it",
            actor="bob", initial_re_review=("alice",))
        if rc != 0:
            failures.append("the shipped step exited {0}: {1}".format(rc, out))
        else:
            if outputs.get("folded") != "true":
                failures.append("expected folded=true for a non-empty "
                                "section-file, got {0!r}".format(outputs.get("folded")))
            commit_sha = outputs.get("commit-sha", "")
            if len(commit_sha) != 40:
                failures.append("expected a 40-character commit-sha, got "
                                "{0!r}".format(commit_sha))
            tasks_md = read(repo, os.path.join(SPEC_DIR, "tasks.md"))
            if "# Tasks" not in tasks_md or section.strip() not in tasks_md:
                failures.append("tasks.md does not carry both the original "
                                "content and the appended section: "
                                "{0!r}".format(tasks_md))
            meta = json.loads(read(repo, os.path.join(SPEC_DIR, "spec-meta.json")))
            if meta.get("stage") != "implement":
                failures.append("expected spec-meta.json stage=implement, "
                                "got {0!r}".format(meta.get("stage")))
            if sorted(meta.get("pending_re_review_from") or []) != ["alice", "bob"]:
                failures.append("expected pending_re_review_from to union "
                                "to [alice, bob], got {0!r}".format(
                                    meta.get("pending_re_review_from")))
            if remote_head_sha(remote) != commit_sha:
                failures.append("the remote's main did not advance to the "
                                "reported commit-sha -- the composite "
                                "committed locally but the push did not "
                                "land.")
            if remote_head_subject(remote) != "fold(leg-a): fold it":
                failures.append("expected the remote's commit subject to be "
                                "'fold(leg-a): fold it', got {0!r}".format(
                                    remote_head_subject(remote)))
            if len(failures) == before1:
                print("[ok] a non-empty section-file appends, flips, "
                     "unions, commits, and pushes for real")

        # Case 2: an empty section-file folds nothing.
        before = len(failures)
        repo2, remote2, base_sha2, rc2, out2, outputs2 = run_fold(
            root, script, "", fold_id="leg-b", summary="nothing here")
        if rc2 != 0:
            failures.append("the shipped step exited {0} on an empty "
                            "section-file: {1}".format(rc2, out2))
        else:
            if outputs2.get("folded") != "false":
                failures.append("expected folded=false for an empty "
                                "section-file, got {0!r}".format(outputs2.get("folded")))
            if outputs2.get("commit-sha", "") != "":
                failures.append("expected an empty commit-sha for an empty "
                                "section-file, got {0!r}".format(outputs2.get("commit-sha")))
            if remote_head_sha(remote2) != base_sha2:
                failures.append("the remote advanced past base_sha even "
                                "though section-file was empty -- something "
                                "was committed and pushed with nothing to "
                                "fold.")
        if len(failures) == before:
            print("[ok] an empty section-file commits and pushes nothing, "
                 "reporting folded=false")

        # Case 3: a missing section-file is treated the same as empty.
        repo3, remote3, base_sha3, rc3, out3, outputs3 = run_fold(
            root, script, None, fold_id="leg-c", summary="never written")
        if rc3 != 0:
            failures.append("the shipped step exited {0} on a missing "
                            "section-file: {1}".format(rc3, out3))
        elif outputs3.get("folded") != "false":
            failures.append("expected folded=false for a missing "
                            "section-file, got {0!r}".format(outputs3.get("folded")))
        elif remote_head_sha(remote3) != base_sha3:
            failures.append("the remote advanced past base_sha even though "
                            "section-file did not exist.")
        else:
            print("[ok] a missing section-file is treated the same as an "
                 "empty one")

        # Case 4 (specs/062-lifecycle-review-gate T038): an empty
        # actor-login (an automated round's own fold -- no human actor)
        # must add nothing to pending_re_review_from, not an empty string.
        before4 = len(failures)
        repo4, remote4, base_sha4, rc4, out4, outputs4 = run_fold(
            root, script, "## s\n", fold_id="leg-d", summary="s",
            actor="", initial_re_review=("alice",))
        if rc4 != 0:
            failures.append("the shipped step exited {0} with an empty "
                            "actor-login: {1}".format(rc4, out4))
        else:
            if outputs4.get("folded") != "true":
                failures.append("expected folded=true with an empty "
                                "actor-login, got {0!r}".format(outputs4.get("folded")))
            meta4 = json.loads(read(repo4, os.path.join(SPEC_DIR, "spec-meta.json")))
            if meta4.get("pending_re_review_from") != ["alice"]:
                failures.append("expected pending_re_review_from to stay "
                                "[alice] with an empty actor-login, got "
                                "{0!r}".format(meta4.get("pending_re_review_from")))
        if len(failures) == before4:
            print("[ok] an empty actor-login adds nothing to "
                 "pending_re_review_from")
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        print("::error::verify-fold-commit-composite: {0}".format(f))
    print("verify-fold-commit-composite: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def _mutate_always_folds(script):
    """A regression that reports folded=true even when section-file is
    empty -- must be caught by Case 2 above."""
    needle = 'if [ ! -s "$SECTION_FILE" ]; then'
    if script.count(needle) != 1:
        sys.exit("::error::verify-fold-commit-composite --self-test: "
                 "expected one empty-check guard; update this harness.")
    return script.replace(
        needle, 'if false; then', 1)


def _mutate_overwrites_re_review(script):
    """A regression that OVERWRITES pending_re_review_from instead of
    unioning into it -- must be caught by Case 1's union assertion."""
    needle = ('.pending_re_review_from = (((.pending_re_review_from // []) '
              '+ (if $actor == "" then [] else [$actor] end)) | unique)')
    if script.count(needle) != 1:
        sys.exit("::error::verify-fold-commit-composite --self-test: "
                 "expected one pending_re_review_from assignment; update "
                 "this harness.")
    return script.replace(needle, '.pending_re_review_from = [$actor]', 1)


def self_test():
    use_utf8_stdout()
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    step = find_step(ACTION, STEP_NAME)
    script = step.get("run") or ""

    root = tempfile.mkdtemp(prefix="wc-fold-commit-selftest-")
    try:
        # A mutation that always reports folded=true must be caught: an
        # empty section-file must never advance the remote.
        mutated = _mutate_always_folds(script)
        repo, remote, base_sha, rc, out, outputs = run_fold(
            root, mutated, "", fold_id="leg-x", summary="s")
        caught = (rc != 0 or outputs.get("folded") != "false" or
                 remote_head_sha(remote) != base_sha)
        check("a mutation that always folds is caught", caught,
             "outputs={0!r} rc={1}".format(outputs, rc))

        # A mutation that overwrites pending_re_review_from instead of
        # unioning must be caught.
        mutated2 = _mutate_overwrites_re_review(script)
        repo2, remote2, base_sha2, rc2, out2, outputs2 = run_fold(
            root, mutated2, "## s\n", fold_id="leg-y", summary="s",
            actor="carol", initial_re_review=("alice",))
        if rc2 == 0 and outputs2.get("folded") == "true":
            meta = json.loads(read(repo2, os.path.join(SPEC_DIR, "spec-meta.json")))
            caught2 = sorted(meta.get("pending_re_review_from") or []) != ["alice", "carol"]
        else:
            caught2 = True
        check("a mutation that overwrites pending_re_review_from is caught",
             caught2)

        # Control: the unmutated step still folds correctly (proves these
        # mutations actually exercise real behavior, not a harness bug).
        repo3, remote3, base_sha3, rc3, out3, outputs3 = run_fold(
            root, script, "## s\n", fold_id="leg-z", summary="s",
            actor="dave", initial_re_review=("alice",))
        control_ok = (rc3 == 0 and outputs3.get("folded") == "true" and
                     remote_head_sha(remote3) != base_sha3)
        check("the unmutated step still folds correctly (control)",
             control_ok, "outputs={0!r} rc={1}".format(outputs3, rc3))
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
