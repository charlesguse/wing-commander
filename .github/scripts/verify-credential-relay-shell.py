#!/usr/bin/env python3
"""Gate 69 - behavioral proof for the credential relay's two shell mechanisms.

WHY THIS EXISTS
---------------
spec 052 (User Story 1's own "STOP and VALIDATE" step, quickstart.md
section 4): the credential relay (research.md D1) and the post-agent
remote refresh (research.md D2) are both plain shell, so their correctness
is a runtime fact, not a structural one -- exactly the class of thing
Gate 68 (verify-post-agent-credential-refresh.py, a static structural
check) deliberately does not exercise. This drives the SHIPPED `run:` text
of both mechanisms directly, the same way `verify-plan-tasks-cost-line.py`
and `verify-finalize-refresh.py` already do for their own subjects.

This gate exists because the mechanism it drives was WRONG the first time
it shipped, and a purely structural check would not have caught it: an
earlier version of the post-agent remote-refresh step only rewrote the
remote URL, and this feature's own T046 code review found that
`actions/checkout@v5` (default `persist-credentials: true`, unchanged by
this feature) authenticates via a local `http.https://github.com/
.extraheader` git config entry, not via any credential embedded in the
remote URL -- so a bare `git remote set-url` left every subsequent `git
fetch`/`push` authenticating with the OLD, possibly-expired extraheader,
silently reproducing the exact 401 this feature exists to eliminate. This
gate's second check reproduces that exact scenario (a stale extraheader
already configured, mirroring what `actions/checkout@v5` leaves behind)
and asserts the shipped step clears it.

WHAT THIS CHECKS
----------------
1. The relay step inside `wing-commander-context` (`.github/actions/
   wing-commander-context/action.yml`), run twice with different TOKEN
   values against the same simulated $GITHUB_ENV file: the file's LAST
   WC_BOT_TOKEN= line must carry the SECOND value (research.md D1 -- later
   $GITHUB_ENV writes win for every subsequent step in the job).
2. `wing-commander-refresh-remote`'s own "Refresh authenticated spec-branch
   remote (post-agent)" step, run inside a real git repository whose
   `origin` remote already carries BOTH a stale credential embedded in its
   URL AND a stale `http.https://github.com/.extraheader` config entry
   (research.md D2's corrected mechanism): afterward, the remote URL
   carries the fresh token, the stale extraheader is gone (not merely
   shadowed), and an untracked file present before the step ran is
   untouched (research.md D2's "cannot discard a commit or a staged
   change" claim, proven rather than merely asserted).

Every one of the 11 post-agent call sites across the 8 sweep-stage
workflows now calls the ONE shared composite below (CLAUDE.md's
single-home rule; Gate 68 check 5 enforces the call exists at every site)
-- driving the composite's own copy of the step exercises all of them, by
construction rather than by an unenforced claim of byte-identity
(maintainer review of PR #407: an earlier version of this docstring
claimed Gate 68 already enforced byte-identity across 8 pasted copies; it
did not).

Usage: python3 .github/scripts/verify-credential-relay-shell.py
Requires: bash, git (both present on ubuntu-latest runners).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

COMPOSITE = ".github/actions/wing-commander-context/action.yml"
RELAY_STEP = "Relay bot token to the job environment"

REFRESH_COMPOSITE = ".github/actions/wing-commander-refresh-remote/action.yml"
REFRESH_STEP = "Refresh authenticated spec-branch remote (post-agent)"

REPO = "acme/widgets"
EXTRAHEADER_KEY = "http.https://github.com/.extraheader"

BASH = None


def check_relay_env_precedence(root):
    """Check 1: two mints into the same $GITHUB_ENV, the second wins."""
    step = find_step(COMPOSITE, RELAY_STEP)
    script = str(step["run"])
    workdir = tempfile.mkdtemp(dir=root)
    env_file = os.path.join(workdir, "github_env")
    open(env_file, "w").close()
    runner_temp = os.path.join(workdir, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)

    failures = []
    for token in ("first-token", "second-token"):
        rc, out, _, _ = run_step(
            BASH, script, workdir,
            {"TOKEN": token, "GITHUB_ENV": env_file}, runner_temp)
        if rc != 0:
            failures.append(
                f"the relay step exited {rc} minting {token!r}:\n{out}")

    if failures:
        return failures

    with open(env_file, encoding="utf-8") as f:
        wc_lines = [l for l in f.read().splitlines()
                    if l.startswith("WC_BOT_TOKEN=")]
    if not wc_lines or wc_lines[-1] != "WC_BOT_TOKEN=second-token":
        failures.append(
            f"$GITHUB_ENV's WC_BOT_TOKEN lines after two mints: "
            f"{wc_lines!r} -- expected the LAST one to read "
            f"'WC_BOT_TOKEN=second-token' (research.md D1: later "
            f"$GITHUB_ENV writes win for every subsequent step in the job)")
    return failures


def _run_git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                    capture_output=True, text=True)


def check_remote_refresh_clears_stale_extraheader(root):
    """Check 2: the refresh step beats a stale actions/checkout extraheader
    without touching the working tree."""
    step = find_step(REFRESH_COMPOSITE, REFRESH_STEP)
    script = str(step["run"]).replace("${{ github.repository }}", REPO)

    workdir = tempfile.mkdtemp(dir=root)
    repo = os.path.join(workdir, "repo")
    os.makedirs(repo)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "harness@example.invalid")
    _run_git(repo, "config", "user.name", "harness")
    _run_git(repo, "remote", "add", "origin",
              f"https://x-access-token:STALE-TOKEN@github.com/{REPO}.git")
    # Mirrors what actions/checkout@v5 actually leaves behind (default
    # persist-credentials: true) -- a local extraheader, not a URL-embedded
    # credential, is what git's http transport authenticates with.
    _run_git(repo, "config", "--local", EXTRAHEADER_KEY,
              "AUTHORIZATION: basic U1RBTEUtQkFTRTY0Cg==")
    untracked = os.path.join(repo, "untracked.txt")
    with open(untracked, "w", encoding="utf-8") as f:
        f.write("uncommitted work the refresh step must not touch\n")

    runner_temp = os.path.join(workdir, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    # TOKEN, not WC_BOT_TOKEN -- the composite receives the token as its own
    # `inputs.token`, relayed to this step's env as TOKEN (action.yml), not
    # as the job-scoped env var the workflow-level call site reads from.
    rc, out, _, _ = run_step(
        BASH, script, repo, {"TOKEN": "fresh-token"}, runner_temp)

    failures = []
    if rc != 0:
        failures.append(f"the refresh step exited {rc}:\n{out}")

    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    if "fresh-token" not in url:
        failures.append(
            f"origin's remote URL after the refresh step does not carry "
            f"the fresh token: {url!r}")

    header_check = subprocess.run(
        ["git", "config", "--local", "--get", EXTRAHEADER_KEY], cwd=repo,
        capture_output=True, text=True)
    if header_check.returncode == 0:
        failures.append(
            f"the stale {EXTRAHEADER_KEY} survived the refresh step "
            f"({header_check.stdout.strip()!r}) -- actions/checkout's "
            f"extraheader takes precedence over a URL-embedded credential "
            f"for git's http auth, so this stale header would still "
            f"authenticate every subsequent git operation with the OLD "
            f"token regardless of the remote URL refresh (research.md D2's "
            f"correction)")

    if not os.path.isfile(untracked):
        failures.append(
            "the refresh step touched the working tree -- the untracked "
            "file placed before it ran is gone")
    else:
        with open(untracked, encoding="utf-8") as f:
            if "uncommitted work" not in f.read():
                failures.append(
                    "the refresh step modified the untracked file's "
                    "contents")

    return failures


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()

    tmproot = tempfile.mkdtemp(prefix="verify_credential_relay_shell_")
    try:
        failures = (check_relay_env_precedence(tmproot)
                    + check_remote_refresh_clears_stale_extraheader(tmproot))
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    for f in failures:
        print(f"::error::Gate 69: {f}")
    print(f"Gate 69: credential relay shell behavior; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
