#!/usr/bin/env python3
"""The lifecycle review gate's own bookkeeping commits, peeled off
(specs/062-lifecycle-review-gate T069).

WHY THIS EXISTS
---------------
`disposition`'s round-recording commit ("review-gate: round N clean at
...", "review-gate: round N findings/budget-exhausted, nothing new to
fold") writes `review_gate.head_sha` equal to the SHA it reviewed, then
pushes -- which necessarily advances the PR's actual branch tip PAST that
recorded value (a commit cannot name its own resulting SHA inside its own
content). Comparing the PR's raw current head against the recorded
`review_gate.head_sha` after that push always reads "not yet reviewed",
which would make `select` pick the PR back up, and `merge`'s
`reviewed_at_this_head` condition never hold, on every run forever.

`settled_head()` walks a ref/SHA backward past this gate's own trailing
recording commits (their subject always starts with "review-gate: round
") to the most recent commit that is NOT one of them -- the SHA that was
actually reviewed. Both `select` (bash, via this script's CLI) and
`lifecycle_merge_preconditions.evaluate()` (Python, via direct import) use
it so a PR is recognised as "still fully reviewed" once the only thing
that changed on top of the reviewed head is this gate's own bookkeeping.

A real new commit (an implement/finalize push, or a second round's own
fold) always has a different subject and stops the walk immediately, so
genuine new content is never mistaken for this gate's own trailing
commit.
"""
import re
import subprocess
import sys

BOOKKEEPING_SUBJECT_RE = re.compile(r"^review-gate: round \d+ ")


def settled_head(ref, cwd=None):
    """Returns the SHA `ref` resolves to, peeled backward past any run of
    this gate's own trailing "review-gate: round ..." commits. Stops (and
    returns the SHA reached so far) the first time a commit's subject does
    not match, the object cannot be resolved, or there is no parent."""
    proc = subprocess.run(["git", "rev-parse", ref], cwd=cwd,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return ref
    sha = proc.stdout.strip()

    while True:
        proc = subprocess.run(["git", "log", "-1", "--format=%s", sha],
                              cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0 or not BOOKKEEPING_SUBJECT_RE.match(proc.stdout.strip()):
            return sha
        proc = subprocess.run(["git", "rev-parse", sha + "^"], cwd=cwd,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            return sha
        sha = proc.stdout.strip()


def self_test():
    """Exercised both standalone (`--self-test` below) and imported directly
    by `verify-lifecycle-readiness.py`'s own `self_test()` (Gate 107) --
    this repository's gate suite is discovered from `verify-*.py`/`.sh`
    invocations in lint-workflows.yml (wc_gate_registry.py), so a bare
    `wc_review_gate_settled_head.py --self-test` step would never actually
    run at PR time; folding the call into Gate 107's own self-test is what
    makes it real, matching this file's WHY docstring's cross-reference."""
    import shutil
    import tempfile

    failures = []

    def check(name, cond, detail=""):
        if not cond:
            failures.append("{0} {1}".format(name, detail))

    def run(*args, cwd):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)

    def commit(cwd, message, filename="f.txt", content="x"):
        with open("{0}/{1}".format(cwd, filename), "w", encoding="utf-8") as fh:
            fh.write(content)
        run("git", "add", filename, cwd=cwd)
        run("git", "commit", "-m", message, "--allow-empty", cwd=cwd)

    tmp = tempfile.mkdtemp()
    try:
        run("git", "init", "-q", cwd=tmp)
        run("git", "config", "user.email", "t@example.com", cwd=tmp)
        run("git", "config", "user.name", "t", cwd=tmp)

        commit(tmp, "real work")
        real_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp,
                                  capture_output=True, text=True).stdout.strip()
        check("no-bookkeeping-on-top", settled_head("HEAD", cwd=tmp) == real_sha,
              "expected {0}, an unpeeled tip".format(real_sha))

        commit(tmp, "review-gate: round 1 clean at abc123")
        check("one-bookkeeping-commit-peeled",
              settled_head("HEAD", cwd=tmp) == real_sha,
              "expected the peel to reach {0}".format(real_sha))

        commit(tmp, "review-gate: round 2 findings, nothing new to fold")
        check("two-stacked-bookkeeping-commits-peeled",
              settled_head("HEAD", cwd=tmp) == real_sha,
              "expected the peel to reach {0} through two commits".format(real_sha))

        commit(tmp, "implement: fix the finding")
        real_sha2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp,
                                   capture_output=True, text=True).stdout.strip()
        check("real-commit-on-top-of-bookkeeping-stops-the-peel",
              settled_head("HEAD", cwd=tmp) == real_sha2,
              "a genuine new commit must never be peeled away")

        check("unresolvable-ref-returns-itself",
              settled_head("not-a-real-ref", cwd=tmp) == "not-a-real-ref")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in failures:
        print("::error::wc_review_gate_settled_head --self-test: {0}".format(f))
    if failures:
        print("{0} failure(s).".format(len(failures)))
        return 1
    print("wc_review_gate_settled_head --self-test: ok.")
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) != 1:
        sys.exit("usage: wc_review_gate_settled_head.py <ref-or-sha> | --self-test")
    print(settled_head(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
