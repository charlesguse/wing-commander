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

Self-test (--self-test): runs both checks clean against the real shipped
scripts, then reintroduces the two regressions this gate exists to catch
and asserts each one fails its check -- check 1 against a relay script
where an already-set WC_BOT_TOKEN short-circuits the write (the FIRST
mint sticks instead of the LAST), and check 2 against the pre-T046
remote-refresh form (`git remote set-url` alone, the extraheader-clearing
line removed) that this feature's own T046 code review found shipped as
a no-op (FR-023, tasks.md T048).

Usage: python3 .github/scripts/verify-credential-relay-shell.py [--self-test]
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


def relay_script():
    return str(find_step(COMPOSITE, RELAY_STEP)["run"])


def refresh_script():
    return str(find_step(REFRESH_COMPOSITE, REFRESH_STEP)["run"])


def check_relay_env_precedence(root, script=None):
    """Check 1: two mints into the same $GITHUB_ENV, the second wins."""
    if script is None:
        script = relay_script()
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


def check_remote_refresh_clears_stale_extraheader(root, script=None):
    """Check 2: the refresh step beats a stale actions/checkout extraheader
    without touching the working tree."""
    if script is None:
        script = refresh_script()
    script = script.replace("${{ github.repository }}", REPO)

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


def mut_relay_first_write_wins():
    """Regression: skip the $GITHUB_ENV write once WC_BOT_TOKEN is already
    set, so the FIRST mint sticks for the rest of the job instead of the
    LAST (the exact inversion of research.md D1)."""
    script = relay_script()
    mutated = script.replace(
        'echo "WC_BOT_TOKEN=$TOKEN" >> "$GITHUB_ENV"',
        'grep -q "^WC_BOT_TOKEN=" "$GITHUB_ENV" || '
        'echo "WC_BOT_TOKEN=$TOKEN" >> "$GITHUB_ENV"')
    if mutated == script:
        sys.exit("::error::Gate 69 self-test: mut_relay_first_write_wins "
                 "changed nothing -- the relay step's shipped text was "
                 "rewritten; update the mutation to match.")
    return mutated


def mut_refresh_remote_no_extraheader_clear():
    """Regression: the pre-T046 form -- `git remote set-url` alone, with
    the extraheader-clearing line removed. This is the exact bug this
    feature's own T046 code review found shipping as a silent no-op."""
    script = refresh_script()
    mutated_lines = [line for line in script.splitlines()
                      if "unset-all" not in line]
    mutated = "\n".join(mutated_lines)
    if script.endswith("\n"):
        mutated += "\n"
    if mutated == script:
        sys.exit("::error::Gate 69 self-test: "
                 "mut_refresh_remote_no_extraheader_clear changed nothing "
                 "-- the refresh step's shipped text was rewritten; update "
                 "the mutation to match.")
    return mutated


def self_test():
    problems = []
    tmproot = tempfile.mkdtemp(prefix="verify_credential_relay_shell_selftest_")
    try:
        clean = (check_relay_env_precedence(tmproot)
                 + check_remote_refresh_clears_stale_extraheader(tmproot))
        if clean:
            problems.append(
                "the clean shipped scripts FAILED their own checks: "
                + "; ".join(clean))

        broke = check_relay_env_precedence(tmproot, mut_relay_first_write_wins())
        if not broke:
            problems.append(
                "MUTATION SURVIVED -- reintroducing 'first $GITHUB_ENV "
                "write wins instead of last' broke nothing in check 1.")
        else:
            print(f"Mutation OK -- relay first-write-wins: "
                  f"{len(broke)} assertion(s) fail.")

        broke = check_remote_refresh_clears_stale_extraheader(
            tmproot, mut_refresh_remote_no_extraheader_clear())
        if not broke:
            problems.append(
                "MUTATION SURVIVED -- reintroducing the pre-T046 "
                "remote-refresh form (no extraheader clear) broke nothing "
                "in check 2.")
        else:
            print(f"Mutation OK -- pre-T046 remote refresh (no extraheader "
                  f"clear): {len(broke)} assertion(s) fail.")
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 69 self-test: {p}")
    if problems:
        return 1
    print("Gate 69 self-test: clean shipped scripts pass; each mutation fails.")
    return 0


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()

    if "--self-test" in sys.argv[1:]:
        return self_test()

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
