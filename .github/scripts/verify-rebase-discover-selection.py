#!/usr/bin/env python3
"""rebase.yml's discover step selects only spec branches that are still in
flight, and reads its dedup marker only from the App's own comments.

WHY THIS EXISTS
---------------
`Select in-flight branches` decides which spec branches the rebase matrix
spends agent turns on. Two defects lived in it with nothing executing it:

  #916  A branch whose lifecycle issue was closed (parked, not planned,
        abandoned) and that had no open pull request was still selected,
        so it was rebased on every push to the default branch and nightly,
        for nobody.
  #831  The `rebase:blocked` dedup marker was matched on comment body only
        (anyone can comment on a public issue, so a quoted marker with the
        current SHAs silenced the re-escalation), read through `--json
        comments` (no user.type, one page), and every failed read was
        swallowed into a default with no trace.

This harness EXECUTES the shipped step through wc_shell_harness.run_step
against a real local git origin (so `git fetch` and `git ls-remote` are the
real thing) and a `gh` stub that applies the step's own `--jq` programs to
fixture JSON with real `jq -r`, the way `gh --jq` prints. Nothing is
pre-filtered (#766). Each MUTATION reverts one fix in the step text and
asserts the suite then fails.

Usage: python3 .github/scripts/verify-rebase-discover-selection.py
Requires: bash, git, jq.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,  # noqa: E402
                              use_utf8_stdout)

REBASE = ".github/workflows/rebase.yml"
STEP = "Select in-flight branches"
BOT = "wc-bot[bot]"
REPO = "o/r"

# The stub: argument dispatch in bash, fixture lookup and `--jq` in python
# so the step's own jq program runs against the fixture, never a copy.
STUB_PY = r'''
import json, os, subprocess, sys
fx = json.load(open(os.environ["STUB_FIXTURE"]))
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")

def opt(name):
    return args[args.index(name) + 1] if name in args else None

def emit(doc):
    prog = opt("--jq")
    if prog is None:
        sys.stdout.write(json.dumps(doc))
        return
    out = subprocess.run(["jq", "-r", prog], input=json.dumps(doc),
                         capture_output=True, text=True)
    sys.stdout.write(out.stdout)
    sys.stderr.write(out.stderr)
    sys.exit(out.returncode)

def fail(what):
    sys.stderr.write("gh: HTTP 502: Bad Gateway (%s)\n" % what)
    sys.exit(1)

if args[:1] == ["api"]:
    path = args[1].split("?")[0]
    prefix = "repos/%s/issues/" % fx["repo"]
    rest = path[len(prefix):]
    if rest in fx.get("fail", []):
        fail(path)
    if rest.endswith("/comments"):
        pages = fx["comments"].get(rest.split("/")[0], [[]])
        if "--paginate" not in args:
            pages = pages[:1]
        # gh applies --jq to each page in turn and prints each result.
        for page in pages:
            out = subprocess.run(["jq", "-c", opt("--jq") or "."], input=json.dumps(page),
                                 capture_output=True, text=True)
            sys.stdout.write(out.stdout)
            if out.returncode:
                sys.stderr.write(out.stderr)
                sys.exit(out.returncode)
        sys.exit(0)
    emit(fx["issues"][rest])
elif args[:2] == ["pr", "list"]:
    head, state = opt("--head"), opt("--state")
    key = "%s@%s" % (head, state)
    if key in fx.get("fail", []):
        fail(key)
    emit(fx.get("prs", {}).get(key, []))
else:
    sys.stderr.write("stub gh: unexpected call: %s\n" % " ".join(args))
    sys.exit(97)
'''

STUB_SH = '#!/usr/bin/env bash\nexec python3 "$STUB_PY" "$@"\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-rebase-discover-selection: {0} -- {1}".format(name, detail))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def meta(slug, issue, stage="implement"):
    return json.dumps({"spec_dir": "specs/" + slug, "issue": issue, "stage": stage})


# slug -> lifecycle issue number. Every branch carries a valid spec-meta.
BRANCHES = {
    "001-open": 1,             # open issue, nothing else: selected
    "002-parked": 2,           # #916: closed, no open PR: excluded
    "003-closed-open-pr": 3,   # closed but an open PR: selected
    "004-merged": 4,           # merged PR (#95): excluded
    "005-forged-marker": 5,    # #831: a human's marker with current SHAs: selected
    "006-bot-marker": 6,       # the App's marker with current SHAs: excluded (dedup)
    "007-issue-read-fails": 7, # failed issue read: selected, annotated
    "008-pr-read-fails": 8,    # closed, failed open-PR read: selected, annotated
    "009-marker-page-2": 9,    # current marker on page 2 of the comments: excluded
    "010-stale-last": 10,      # current marker, then a newer stale one: selected
    "011-comments-fail": 11,   # blocked, failed comments read: selected, annotated
    "012-other-bot": 12,       # #831: another App's marker with current SHAs: selected
    "013-fork-pr-only": 13,    # #916: closed, only a fork's same-named PR open: excluded
    "014-login-not-bot": 14,   # #831: the App's login on a non-Bot user (synthetic): selected
}


def build(tmp):
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "work")
    git(tmp, "init", "-q", "--bare", origin)
    git(tmp, "init", "-q", "-b", "main", work)
    for k, v in (("user.email", "h@example.invalid"), ("user.name", "harness"),
                 ("commit.gpgsign", "false")):
        git(work, "config", k, v)
    open(os.path.join(work, "README"), "w").write("main\n")
    git(work, "add", "README")
    git(work, "commit", "-q", "-m", "main")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-q", "origin", "main")
    tips = {}
    for slug, number in BRANCHES.items():
        git(work, "checkout", "-q", "-b", "spec/" + slug, "main")
        d = os.path.join(work, "specs", slug)
        os.makedirs(d)
        open(os.path.join(d, "spec-meta.json"), "w").write(meta(slug, number))
        git(work, "add", "specs")
        git(work, "commit", "-q", "-m", slug)
        git(work, "push", "-q", "origin", "spec/" + slug)
        tips[slug] = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "-q", "main")
    shutil.rmtree(os.path.join(work, "specs"), ignore_errors=True)
    return work, tips, git(work, "rev-parse", "main")


def comment(body, login=BOT, kind="Bot"):
    return {"user": {"login": login, "type": kind}, "body": body}


def marker(branch, main):
    return ("🛠️ **Auto-rebase needs a human**\n\n"
            "<!-- wing-commander-rebase: blocked branch-sha={0} main-sha={1} -->\n\n"
            "cost line".format(branch, main))


def fixture(tips, main):
    def issue(state, blocked=False):
        labels = [{"name": "spec:x"}] + ([{"name": "rebase:blocked"}] if blocked else [])
        return {"state": state, "labels": labels}

    issues = {str(n): issue("open") for n in BRANCHES.values()}
    issues["2"] = issue("closed")
    issues["3"] = issue("closed")
    issues["8"] = issue("closed")
    issues["13"] = issue("closed")
    for n in (5, 6, 9, 10, 11, 12, 14):
        issues[str(n)] = issue("open", blocked=True)
    t = tips
    return {
        "repo": REPO,
        "issues": issues,
        "fail": ["7", "11/comments", "spec/008-pr-read-fails@open"],
        "prs": {
            "spec/003-closed-open-pr@open": [{"number": 31, "isCrossRepository": True},
                                             {"number": 30, "isCrossRepository": False}],
            "spec/013-fork-pr-only@open": [{"number": 130, "isCrossRepository": True}],
            "spec/004-merged@merged": [{"number": 40}],
        },
        "comments": {
            "5": [[comment(marker(t["005-forged-marker"], main), login="someone", kind="User")]],
            "6": [[comment("unrelated"), comment(marker(t["006-bot-marker"], main))]],
            "9": [[comment(marker("0" * 40, main))],
                  [comment(marker(t["009-marker-page-2"], main))]],
            "10": [[comment(marker(t["010-stale-last"], main))],
                   [comment(marker("0" * 40, main))]],
            "12": [[comment(marker(t["012-other-bot"], main), login="github-actions[bot]")]],
            "14": [[comment(marker(t["014-login-not-bot"], main), kind="User")]],
        },
    }


def run(script, tmp, work, fx):
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    stub_py = os.path.join(tmp, "stub_gh.py")
    open(stub_py, "w").write(STUB_PY)
    gh = os.path.join(bindir, "gh")
    open(gh, "w").write(STUB_SH)
    os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
    fx_path = os.path.join(tmp, "fixture.json")
    json.dump(fx, open(fx_path, "w"))
    log = os.path.join(tmp, "gh.log")
    open(log, "w").close()
    runner_temp = os.path.join(tmp, "runner-temp")
    os.makedirs(runner_temp, exist_ok=True)
    env = {
        "PATH": bindir + os.pathsep + os.environ["PATH"],
        "GH_TOKEN": "x", "DB": "main", "SPEC_PREFIX": "spec/", "BOT_LOGIN": BOT,
        "GITHUB_REPOSITORY": REPO, "STUB_PY": stub_py, "STUB_FIXTURE": fx_path,
        "STUB_LOG": log,
    }
    rc, output, outputs, summary = run_step(BASH, script, work, env, runner_temp)
    return rc, output, outputs, summary


def suite(script, quiet=False):
    """Run every scenario once against `script`; return the failed names.
    `quiet` is for a mutation run, whose failures are the expected outcome
    and must not print as ::error:: annotations."""
    failed = []

    def ck(name, cond, detail=""):
        if quiet:
            if not cond:
                failed.append(name)
            return
        check(name, cond, detail)
        if not cond:
            failed.append(name)

    tmp = tempfile.mkdtemp(prefix="wc-rebase-discover-")
    try:
        work, tips, main = build(tmp)
        rc, output, outputs, summary = run(script, tmp, work, fixture(tips, main))
        ck("the step exits 0", rc == 0, "rc={0}\n{1}".format(rc, output))
        try:
            chosen = sorted(b["slug"] for b in json.loads(outputs.get("branches", "null")))
        except (TypeError, ValueError):
            chosen = None
        want = ["001-open", "003-closed-open-pr", "005-forged-marker",
                "007-issue-read-fails", "008-pr-read-fails", "010-stale-last",
                "011-comments-fail", "012-other-bot", "014-login-not-bot"]
        ck("selects exactly the in-flight branches", chosen == want,
           "selected {0}, want {1}".format(chosen, want))
        ck("#916: a closed issue with no open PR is noted, not warned",
           "spec/002-parked` excluded from auto-rebase: its lifecycle issue (#2) is closed" in summary
           and "spec/002-parked excluded" not in output,
           "summary:\n{0}\noutput:\n{1}".format(summary, output))
        ck("#831: the App's current marker dedups the branch",
           "spec/006-bot-marker` unchanged since it was reported blocked" in summary, summary)
        ck("#831: a marker on the second comments page still counts",
           "spec/009-marker-page-2` unchanged since" in summary, summary)
        for slug, what in (("007-issue-read-fails", "lifecycle issue #7"),
                           ("008-pr-read-fails", "its open pull requests"),
                           ("011-comments-fail", "lifecycle issue #11's comments")):
            line = ("::warning::wing-commander rebase discover: spec/{0} kept — "
                    "could not read {1}: gh: HTTP 502").format(slug, what)
            ck("#831: a failed read of {0} is annotated".format(what), line in output, output)
        return failed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Each mutation reverts one fix; the suite must then fail.
MUTATIONS = (
    ("#916 closed-issue exclusion removed",
     'if [ "$issue_state" = "closed" ]; then', 'if false; then'),
    ("#831 author test removed",
     'select(.user.type == "Bot" and .user.login == $bot)', '.'),
    ("#831 author test keeps only the type half",
     'select(.user.type == "Bot" and .user.login == $bot)', 'select(.user.type == "Bot")'),
    ("#831 author test keeps only the login half",
     'select(.user.type == "Bot" and .user.login == $bot)', 'select(.user.login == $bot)'),
    ("#916 a fork's same-named PR counted",
     "[.[] | select(.isCrossRepository | not)] | .[0].number", ".[0].number"),
    ("#831 only the first comments page read",
     "--paginate --jq '.[]'", "--jq '.[]'"),
    ("#831 failed reads swallowed again",
     'echo "::warning::wing-commander rebase discover: ${SPEC_PREFIX}$1 kept', 'true "'),
    ("#831 first marker read instead of the last",
     "| last // empty')", "| first // empty')"),
)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    script = find_step(REBASE, STEP)["run"]
    for name, old, _new in MUTATIONS:
        if script.count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the step text "
                     "exactly once. Update the mutation with the step.".format(REBASE, name))
    suite(script)
    for name, old, new in MUTATIONS:
        check("mutation caught: " + name, bool(suite(script.replace(old, new), quiet=True)),
              "the suite stayed green with this fix reverted")
    if failures:
        print("verify-rebase-discover-selection: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-rebase-discover-selection: ok")


BASH = None

if __name__ == "__main__":
    main()
