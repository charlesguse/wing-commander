#!/usr/bin/env python3
"""The watchdog's own fix PRs must not carry the pipeline checkout as a gitlink.

WHY THIS EXISTS
---------------
Every job in every stage checks the pipeline repository out to
`.wing-commander-pipeline` INSIDE the consumer's working tree — it has to,
since actions/checkout refuses a path outside GITHUB_WORKSPACE — and that
directory carries its own `.git`. A bare `git add -A` therefore does not
recurse into it; it records a GITLINK, a submodule entry with no .gitmodules
behind it, pointing at a commit in another repository.

PR #201 shipped exactly that, from `prepare`. #202 fixed the two deterministic
sites in auto-update-spec-kit.yml and gave them fixtures (t9_prepare.sh,
t5_act.sh). It did not touch watchdog.yml, whose `act` job composes commits the
same way in the same working tree — so both rungs would have shipped the same
stray entry into the first fix PR the watchdog ever opened.

Nothing caught it for the same reason nothing caught #201: rungs 1 and 2 have
never fired in ~200 runs, and a path that has never executed cannot be observed
to be wrong. That is this repository's recurring failure shape (PR #158's
orphaned collector verifier, #169's unfailable harness dependencies), so the
fix ships with a harness that executes the shipped block rather than a copy of
it.

WHAT THIS CHECKS
----------------
Both `act` commit steps, EXTRACTED from watchdog.yml and executed against a
real git repository whose working tree contains a real nested git repository at
`.wing-commander-pipeline`, plus a real bare origin to push to and a `gh` stub:

  1. the step exits 0 and creates the commit;
  2. the resulting tree contains NO entry of git type `commit` (no gitlink) —
     the #201 defect stated directly;
  3. `.wing-commander-pipeline` is absent from the tree;
  4. the change the diff actually applied IS committed, so the exclusion did
     not become an over-exclusion (the #202 mutation that narrowed `-A` to an
     explicit pathspec list and silently stopped committing a real file);
  5. `.wing-commander-pipeline` is still untracked afterwards, i.e. it was
     excluded rather than deleted or ignored into the index.

MUTATION
--------
Reverting the pathspec to a bare `git add -A` must break this suite. Without
that check the suite would pass just as happily against the defect, which is
the only thing it exists to detect.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    find_step,
    resolve_bash,
    run_step,
    use_utf8_stdout,
)

WORKFLOW = ".github/workflows/watchdog.yml"

# The two shipped steps under test, by the name they carry in the workflow.
STEPS = [
    "Commit fix and open PR (rung 2)",
    "Commit fix and open PR (rung 1)",
]

# The env each step declares, rendered. Values are arbitrary but must be
# shell-safe: the point is the commit's CONTENT, not the message text.
STEP_ENV = {
    "GH_TOKEN": "stub-token",
    "BOT_SLUG": "wing-commander-bot",
    "SHORT_FP": "abc1234",
    "ISSUE_NUMBER": "140",
    "FINDING_CLASS": "missing-always-guard",
    "FINDING_DESCRIPTION": "A step lost its always() guard.",
    "RUN_URL": "https://github.com/o/r/actions/runs/1",
    "DB": "main",
    "GITHUB_REPOSITORY": "charlesguse/wing-commander",
}

MUTATIONS = [
    (
        "bare `git add -A` (the PR #201 defect)",
        "git add -A -- . ':(exclude).wing-commander-pipeline'",
        "git add -A",
    ),
]


def git(cwd, *args, check=True):
    proc = subprocess.run(("git",) + args, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n"
                           f"{proc.stdout}{proc.stderr}")
    return proc.stdout


def render(script, runner_temp):
    """Substitute the ${{ }} expressions these two steps carry."""
    return (script
            .replace("${{ runner.temp }}", runner_temp.replace("\\", "/"))
            .replace("${{ matrix.index }}", "0"))


def build_fixture(root):
    """A consumer checkout mid-run: tracked files, a bare origin, and the
    pipeline repository checked out into the working tree."""
    origin = os.path.join(root, "origin.git")
    repo = os.path.join(root, "repo")
    git(root, "init", "-q", "-b", "main", "--bare", origin)
    git(root, "clone", "-q", origin, repo)
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")

    os.makedirs(os.path.join(repo, ".github", "workflows"), exist_ok=True)
    with open(os.path.join(repo, ".github", "workflows", "target.yml"),
              "w", encoding="utf-8", newline="\n") as fh:
        fh.write("name: target\njobs:\n  a:\n    steps:\n      - run: echo before\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    git(repo, "push", "-q", "origin", "main")

    # The pipeline checkout. Its own .git is what turns `git add -A` into a
    # gitlink — a fixture without it stays green against the defect, which is
    # precisely how t5_act.sh passed with act's half of #202 reverted.
    pipe = os.path.join(repo, ".wing-commander-pipeline")
    os.makedirs(pipe)
    with open(os.path.join(pipe, "action.yml"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("name: shared composite\n")
    git(pipe, "init", "-q", "-b", "main")
    git(pipe, "config", "user.email", "t@t")
    git(pipe, "config", "user.name", "t")
    git(pipe, "add", "-A")
    git(pipe, "commit", "-qm", "pipeline")
    return repo


def write_diff(runner_temp):
    """The triage artifact the step applies. A one-line edit to a tracked
    file, so assertion 4 has something real to look for."""
    d = os.path.join(runner_temp, "triage-diff")
    os.makedirs(d, exist_ok=True)
    body = (
        "--- a/.github/workflows/target.yml\n"
        "+++ b/.github/workflows/target.yml\n"
        "@@ -1,5 +1,5 @@\n"
        " name: target\n"
        " jobs:\n"
        "   a:\n"
        "     steps:\n"
        "-      - run: echo before\n"
        "+      - run: echo after\n"
    )
    with open(os.path.join(d, "watchdog-fix-0.diff"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(body)


def install_gh_stub(root):
    """`gh pr create` must print a URL (the step captures it into
    $GITHUB_OUTPUT); `gh issue comment` just has to succeed."""
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir, exist_ok=True)
    stub = os.path.join(bindir, "gh")
    with open(stub, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/usr/bin/env bash\n"
                 'if [ "$1" = "pr" ] && [ "$2" = "create" ]; then\n'
                 '  echo "https://github.com/o/r/pull/1"\n'
                 "fi\n"
                 "exit 0\n")
    os.chmod(stub, 0o755)
    return bindir


def check(failures, label, got, want):
    if got != want:
        print(f"::error::{label}: got {got!r}, want {want!r}")
        failures.append(label)


def run_one(bash, script, root, label, failures):
    """Execute one rendered step against a fresh fixture and assert on the
    commit it produced. Returns True when every assertion held."""
    work = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(work, "runner-temp")
    os.makedirs(runner_temp)
    repo = build_fixture(work)
    write_diff(runner_temp)
    bindir = install_gh_stub(work)

    env = dict(STEP_ENV)
    env["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")

    before = len(failures)
    rc, out, outputs, _summary = run_step(
        bash, render(script, runner_temp), repo, env, runner_temp)

    check(failures, f"{label}: exit code", rc, 0)
    if rc != 0:
        print(out)
        return False

    branch = "watchdog-fix/" + STEP_ENV["SHORT_FP"]
    subjects = git(repo, "log", "--format=%s", "-1", branch).strip()
    check(failures, f"{label}: commit created",
          subjects.startswith("watchdog: fix "), True)

    # 2 — the defect itself. `git ls-tree -r` reports a gitlink with type
    # `commit`; every ordinary file is `blob`.
    tree = git(repo, "ls-tree", "-r", branch)
    gitlinks = [ln for ln in tree.splitlines() if ln.split()[1:2] == ["commit"]]
    check(failures, f"{label}: no gitlink in the tree", gitlinks, [])

    # 3 — stated by path as well as by type, so a future gitlink under some
    # other name is still caught by 2 and this one still names the culprit.
    named = git(repo, "ls-tree", "--name-only", branch, "--",
                ".wing-commander-pipeline").strip()
    check(failures, f"{label}: pipeline checkout absent from the tree",
          named, "")

    # 4 — the exclusion is not an over-exclusion.
    blob = git(repo, "show", f"{branch}:.github/workflows/target.yml")
    check(failures, f"{label}: the applied diff IS committed",
          "echo after" in blob, True)

    # 5 — excluded, not deleted or ignored into the index.
    status = git(repo, "status", "--porcelain", "--",
                 ".wing-commander-pipeline").strip()
    check(failures, f"{label}: pipeline checkout still untracked",
          status.split()[0:1], ["??"])

    return len(failures) == before


def suite(scripts, root, quiet=False):
    bash = resolve_bash()
    failures = []
    for name, script in scripts.items():
        label = name
        if quiet:
            # Mutation runs are expected to fail; their assertion noise is
            # not a finding, so swallow it and report only the verdict.
            with open(os.devnull, "w") as devnull:
                stdout, sys.stdout = sys.stdout, devnull
                try:
                    run_one(bash, script, root, label, failures)
                finally:
                    sys.stdout = stdout
        else:
            run_one(bash, script, root, label, failures)
    return failures


def main():
    use_utf8_stdout()
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    wf = os.path.join(repo_root, WORKFLOW)

    scripts = {}
    for name in STEPS:
        step = find_step(wf, name)
        if "run" not in step:
            sys.exit(f"::error file={WORKFLOW}::step {name!r} has no run: block.")
        scripts[name] = step["run"]

    root = tempfile.mkdtemp()
    failures = []
    try:
        failures.extend(suite(scripts, root))
        for label, original, mutant in MUTATIONS:
            mutated = {}
            changed = False
            for name, script in scripts.items():
                if original in script:
                    changed = True
                mutated[name] = script.replace(original, mutant)
            if not changed:
                print(f"::error::mutation {label!r} changed nothing — the code "
                      f"it edits was rewritten. Update the mutation so this "
                      f"harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if suite(mutated, root, quiet=True):
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"watchdog fix commit: {len(STEPS)} shipped step(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
