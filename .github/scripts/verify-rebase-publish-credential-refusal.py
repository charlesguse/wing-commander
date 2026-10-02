#!/usr/bin/env python3
"""rebase.yml's "Publish rebased branch" tells a credential refusal from a
branch race.

WHY THIS EXISTS
---------------
The publish step force-pushes the rebased spec branch with
--force-with-lease and treated every refusal as "the branch moved since
checkout": a warning, a summary line, and a green job. When the agent had
run and the post-agent wing-commander-bot credential could not be
re-established, the refusal was most likely authentication, and the run
still ended green with a message that blamed a race (#661, against spec
073 FR-003/FR-004: name the credential as the cause).

So "Determine post-agent credential status" now runs ahead of the publish
step, and the publish step reads its `ok` output:
  - a refusal with `ok == false` fails the step, naming the credential;
  - a refusal with `ok == true`, or empty because the agent never ran
    (a clean rebase), stays the tolerated branch-moved warning;
  - a push that succeeds is unaffected whatever `ok` says.

This harness EXECUTES the shipped publish step (wc_shell_harness.run_step)
inside a real clone of a real local bare remote, with the branch moved
underneath it by a second clone for the refusal cases, so the lease is
git's own. Static checks pin the step order and the env wiring. Each
MUTATION reverts one rule and asserts the suite then fails.

Usage: python3 .github/scripts/verify-rebase-publish-credential-refusal.py
Requires: bash, git.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_job, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

WORKFLOW = ".github/workflows/rebase.yml"
JOB = "rebase"
PUBLISH = "Publish rebased branch"
CREDENTIAL = "Determine post-agent credential status"
BRANCH = "spec/001-demo"

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-rebase-publish-credential-refusal: {0} -- {1}".format(name, detail))


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git"] + list(args), cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(cwd, name):
    with open(os.path.join(cwd, name), "w") as fh:
        fh.write(name + "\n")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", name)
    return git(cwd, "rev-parse", "HEAD")


def run(script, moved, credential_ok):
    """-> (rc, output, summary, origin tip, local rebased sha, mover's sha)."""
    root = tempfile.mkdtemp(prefix="wc-rebase-publish-")
    try:
        origin = os.path.join(root, "origin.git")
        git(root, "init", "-q", "--bare", origin)
        seed = os.path.join(root, "seed")
        git(root, "init", "-q", "-b", "main", seed)
        commit(seed, "base")
        git(seed, "checkout", "-q", "-b", BRANCH)
        commit(seed, "spec")
        git(seed, "remote", "add", "origin", "file://" + origin)
        git(seed, "push", "-q", "origin", "main", BRANCH)
        work = os.path.join(root, "work")
        git(root, "clone", "-q", "file://" + origin, work)
        git(work, "checkout", "-q", BRANCH)
        rebased = commit(work, "rebased")
        mover_sha = ""
        if moved:
            mover = os.path.join(root, "mover")
            git(root, "clone", "-q", "file://" + origin, mover)
            git(mover, "checkout", "-q", BRANCH)
            mover_sha = commit(mover, "moved")
            git(mover, "push", "-q", "origin", BRANCH)
        runner_temp = os.path.join(root, "runner-temp")
        os.makedirs(runner_temp)
        env = {"SLUG": BRANCH.split("/", 1)[1], "ISSUE": "", "GH_TOKEN": "t",
               "SPEC_PREFIX": "spec/", "CREDENTIAL_OK": credential_ok,
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        rc, out, _outputs, summary = run_step(BASH, script, work, env, runner_temp)
        tip = git(origin, "rev-parse", BRANCH)
        return rc, out, summary, tip, rebased, mover_sha
    finally:
        shutil.rmtree(root, ignore_errors=True)


def suite(script, quiet=False):
    failed = []

    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    rc, out, summary, tip, rebased, _ = run(script, moved=False, credential_ok="true")
    ck("an unrefused push publishes the rebased result",
       rc == 0 and tip == rebased and "pushed rebased result" in summary,
       "rc={0} tip={1} rebased={2}\n{3}".format(rc, tip, rebased, out))
    rc, out, summary, tip, rebased, _ = run(script, moved=False, credential_ok="false")
    ck("a push that succeeds is unaffected by a failed credential status",
       rc == 0 and tip == rebased, "rc={0}\n{1}".format(rc, out))
    rc, out, summary, tip, rebased, mover = run(script, moved=True, credential_ok="true")
    ck("a refusal with a good credential stays the tolerated branch-moved warning",
       rc == 0 and tip == mover and "branch moved since checkout" in out and "::error::" not in out,
       "rc={0} tip={1}\n{2}".format(rc, tip, out))
    rc, out, summary, tip, rebased, mover = run(script, moved=True, credential_ok="")
    ck("a refusal after a clean rebase (agent never ran) is tolerated the same way",
       rc == 0 and tip == mover and "branch moved since checkout" in out,
       "rc={0}\n{1}".format(rc, out))
    rc, out, summary, tip, rebased, mover = run(script, moved=True, credential_ok="false")
    ck("a refusal after a failed post-agent credential fails, naming the credential (#661)",
       rc != 0 and tip == mover and "::error::" in out and "credential" in out
       and "not a branch race" in out and "branch moved since checkout" not in out,
       "rc={0}\n{1}".format(rc, out))
    return failed


MUTATIONS = (
    ("the credential arm removed", 'elif [ "$CREDENTIAL_OK" = "false" ]; then', "elif false; then"),
    ("the credential arm left non-fatal",
     '  } >> "$GITHUB_STEP_SUMMARY"\n  exit 1\nelse\n', '  } >> "$GITHUB_STEP_SUMMARY"\nelse\n'),
)


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    steps = find_job(WORKFLOW, JOB).get("steps") or []
    names = [(s or {}).get("name") for s in steps]
    for need in (PUBLISH, CREDENTIAL):
        if need not in names:
            sys.exit("::error file={0}::no step named {1!r} in job {2!r}. If it was renamed, "
                     "update the workflow and this harness together.".format(WORKFLOW, need, JOB))
    publish = steps[names.index(PUBLISH)]
    check("the credential status is determined before the publish step reads it",
          names.index(CREDENTIAL) < names.index(PUBLISH),
          "order: {0} at {1}, {2} at {3}".format(CREDENTIAL, names.index(CREDENTIAL),
                                                  PUBLISH, names.index(PUBLISH)))
    check("the publish step reads the credential status's ok output",
          (publish.get("env") or {}).get("CREDENTIAL_OK") == "${{ steps.credential-status.outputs.ok }}",
          "env={0}".format(publish.get("env")))
    script = str(publish["run"])
    for name, old, _new in MUTATIONS:
        if script.count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the publish step exactly "
                     "once. Update the mutation with the step.".format(WORKFLOW, name))
    suite(script)
    for name, old, new in MUTATIONS:
        check("mutation caught: " + name, bool(suite(script.replace(old, new), quiet=True)),
              "the suite stayed green with this rule reverted")
    if failures:
        print("verify-rebase-publish-credential-refusal: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-rebase-publish-credential-refusal: ok")


if __name__ == "__main__":
    main()
