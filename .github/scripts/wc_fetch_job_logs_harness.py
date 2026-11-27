#!/usr/bin/env python3
"""Run the wing-commander-fetch-job-logs composite's step the way the runner
does, for the harness gates whose subject reads what that composite stages.

WHY THIS EXISTS
---------------
Since specs/101-read-only-gh-grants, the watchdog's step-summary collector
and diagnose's staging step read job logs the composite fetched, so
verify-sentinel-collector.py and verify-gate-19.py each have to run the
composite's shipped step before the step under test. Both carried their own
copy of that runner -- the step lookup, its cache, the environment the
runner hands a composite step, the shell it runs under -- and the copies had
already drifted: verify-gate-19.py's never set $GITHUB_ACTION_PATH, so the
composite's `--allow-escape-sequences` probe resolved to
`/../../scripts/...` and silently never ran there (Maintenance backlog
#889, found by the code review of #991).

This module is the runner's one home. Gate 140
(verify-shell-harness-parity.py) fails if any other script under
.github/scripts/ names the composite's action.yml.
"""
import os

from wc_shell_harness import find_step, run_step, step_shell

FETCH_ACTION = ".github/actions/wing-commander-fetch-job-logs/action.yml"
FETCH_STEP = "Fetch job logs"

_FETCH = []


def shipped_fetch():
    """The shipped composite step's run: script, read once."""
    if not _FETCH:
        _FETCH.append(str(find_step(FETCH_ACTION, FETCH_STEP)["run"]))
    return _FETCH[0]


def run_fetch_step(bash, workdir, env, runner_temp, out_dir, script=None,
                   action_path=None):
    """Run the composite's step (`script`, else the shipped one) under the
    shell the runner gives it, staging into `out_dir`. `env` is the caller's
    environment (PATH with its stubs, CONCLUSIONS, ...); the inputs the
    composite's step always gets are set over it, and $GITHUB_ACTION_PATH is
    the composite's real directory unless `action_path` replaces it -- the
    step resolves ../../scripts/gh-allows-escape-sequences.sh from there.
    -> run_step's (rc, output, step outputs, step summary)."""
    env = dict(env, RUN_ID="1", GH_TOKEN="x", OUT_DIR=out_dir,
               GITHUB_REPOSITORY="charlesguse/wing-commander",
               GITHUB_ACTION_PATH=action_path or os.path.abspath(
                   os.path.dirname(FETCH_ACTION)))
    return run_step(bash, script or shipped_fetch(), workdir, env,
                    runner_temp, shell=step_shell(FETCH_ACTION, FETCH_STEP))
