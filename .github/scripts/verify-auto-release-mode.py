#!/usr/bin/env python3
"""Gate 64 -- auto-release.yml's mode derivation never repeats a mode across
a year boundary (specs/054-e2e-container-coverage, SC-009).

WHY THIS EXISTS
---------------
The `mode` step used to derive the container/default-runner alternation from
day-of-year parity (`date -u +%j`). Day-of-year resets to 1 every January
1st, and in a non-leap year day 365 (December 31st) and day 1 (January 1st)
are both odd -- so a scheduled run landing on either side of that boundary
got the SAME mode twice in a row instead of alternating, silently skipping
the default-runner leg for one rotation. A monotonic day count (days since
the Unix epoch) has no such seam: consecutive calendar days always increment
it by exactly one, in any year.

This harness EXECUTES the shipped "Derive this run's execution mode
(container vs default-runner)" step (read out of auto-release.yml at run
time, so there is no second copy to drift) against a stubbed `date`, and
ends with a MUTATION that puts the day-of-year parity check back to prove
the year-boundary scenario actually fails on that defect.

#966 extended this gate to the step right after it in `detect`, "Decide
whether this run verifies (unreleased head, or an open failure in this
run's mode)": a container-mode failure was closed by a default-runner pass
and then never re-checked, because every later quiet day skipped
verification. The step is executed, verbatim, under a stubbed `gh issue
list`, for each recorded mode an open auto-release:failed issue can carry;
static checks then pin the job conditions that consume its output
(e2e-pin and verify-e2e on run-verification, decide-version still on
has-new-work), and mutations put the mode-blind shapes back.

Usage: python3 .github/scripts/verify-auto-release-mode.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_job, find_step, parse_github_output, resolve_bash,
    run_step, use_utf8_stdout)

WORKFLOW = ".github/workflows/auto-release.yml"
STEP = "Derive this run's execution mode (container vs default-runner)"
VERIFY_STEP = ("Decide whether this run verifies (unreleased head, or an "
               "open failure in this run's mode)")

BASH = None

# Answers both the shipped `date -u +%s` call and the pre-fix `date -u +%j`
# call a mutation puts back, so one stub serves both the real script and its
# mutated form.
STUB_DATE = r'''#!/usr/bin/env bash
if [ "$1 $2" = "-u +%s" ]; then
  printf '%s\n' "${FAKE_EPOCH_SECONDS:?FAKE_EPOCH_SECONDS not set}"
  exit 0
fi
if [ "$1 $2" = "-u +%j" ]; then
  printf '%s\n' "${FAKE_DOY:?FAKE_DOY not set}"
  exit 0
fi
echo "unexpected date invocation: $*" >&2
exit 1
'''


def _epoch(year, month, day):
    return int(datetime.datetime(year, month, day, 12, 0, 0,
                                  tzinfo=datetime.timezone.utc).timestamp())


def _doy(year, month, day):
    return f"{datetime.date(year, month, day).timetuple().tm_yday:03d}"


# Two ordinary, non-boundary consecutive days -- picked far from any year
# seam so a correct implementation of EITHER scheme (day-of-year or
# monotonic count) agrees on "these two must differ".
ORDINARY_A = dict(epoch=_epoch(2026, 6, 14), doy=_doy(2026, 6, 14))
ORDINARY_B = dict(epoch=_epoch(2026, 6, 15), doy=_doy(2026, 6, 15))

# The regression this gate exists to catch: December 31st of a non-leap year
# (day-of-year 365, odd) followed by January 1st the next year (day-of-year
# 001, also odd) -- day-of-year parity reads both as the same mode; the
# monotonic day count, being one apart, never does.
BOUNDARY_A = dict(epoch=_epoch(2025, 12, 31), doy=_doy(2025, 12, 31))
BOUNDARY_B = dict(epoch=_epoch(2026, 1, 1), doy=_doy(2026, 1, 1))

assert BOUNDARY_A["doy"] == "365" and BOUNDARY_B["doy"] == "001", (
    "fixture dates drifted off the intended day-of-year values -- update "
    "them alongside this assertion")

# Fixed days, independent of the calendar, used to test the pause control in
# isolation: a day whose derived mode is default-runner (even count) and one
# whose derived mode is container (odd count), both far from any seam.
DAY_COUNT_DEFAULT_RUNNER = 20000   # even
DAY_COUNT_CONTAINER = 20001        # odd


def _epoch_for_day_count(n):
    return n * 86400 + 43200   # noon UTC that day


def run_mode_step(script, epoch_seconds, doy, container_paused, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    date_path = os.path.join(bindir, "date")
    with open(date_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_DATE)
    os.chmod(date_path, 0o755)

    env = {
        "CONTAINER_PAUSED": container_paused,
        "FAKE_EPOCH_SECONDS": str(epoch_seconds),
        "FAKE_DOY": doy,
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    rc, out, outputs, _summary = run_step(BASH, script, workdir, env,
                                          runner_temp, path_prepend=bindir)
    for d in (workdir, runner_temp, bindir):
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    if rc != 0:
        sys.exit(f"::error::the mode step exited {rc}:\n{out}")
    return outputs.get("mode"), outputs.get("paused")


SCENARIOS = [
    dict(
        name="two ordinary consecutive days flip mode",
        a=ORDINARY_A, b=ORDINARY_B, must_differ=True,
    ),
    dict(
        name="year boundary (SC-009): Dec 31 of a non-leap year and the "
             "following Jan 1st still flip mode, not repeat it",
        a=BOUNDARY_A, b=BOUNDARY_B, must_differ=True,
    ),
]


def suite(script, tmproot):
    failures = []
    for sc in SCENARIOS:
        mode_a, _ = run_mode_step(script, sc["a"]["epoch"], sc["a"]["doy"],
                                  "false", tmproot)
        mode_b, _ = run_mode_step(script, sc["b"]["epoch"], sc["b"]["doy"],
                                  "false", tmproot)
        tag = f"[{sc['name']}]"
        if mode_a not in ("container", "default-runner"):
            failures.append(f"{tag} day A produced an unrecognised mode {mode_a!r}")
        if mode_b not in ("container", "default-runner"):
            failures.append(f"{tag} day B produced an unrecognised mode {mode_b!r}")
        if sc["must_differ"] and mode_a == mode_b:
            failures.append(f"{tag} both days derived mode={mode_a!r} -- the "
                            f"alternation repeated instead of flipping")

    # Pause control: forces default-runner + paused=true on an otherwise-
    # container day, never overrides an already-default-runner day.
    mode, paused = run_mode_step(
        script, _epoch_for_day_count(DAY_COUNT_CONTAINER), "999", "true", tmproot)
    if mode != "default-runner" or paused != "true":
        failures.append(
            "[pause control on a container-turn day] expected "
            f"mode=default-runner paused=true, got mode={mode!r} paused={paused!r}")

    mode, paused = run_mode_step(
        script, _epoch_for_day_count(DAY_COUNT_DEFAULT_RUNNER), "999", "true", tmproot)
    if mode != "default-runner" or paused != "false":
        failures.append(
            "[pause control on an already-default-runner day] expected "
            f"mode=default-runner paused=false (never marked paused when "
            f"that leg was never due), got mode={mode!r} paused={paused!r}")

    return failures


def mut_day_of_year_parity(script):
    """Put the pre-fix day-of-year parity check back."""
    old = ('days_since_epoch="$(( $(date -u +%s) / 86400 ))"\n'
          'if [ $(( days_since_epoch % 2 )) -eq 0 ]; then')
    new = ('doy="$(date -u +%j)"\n'
          'if [ $(( 10#$doy % 2 )) -eq 0 ]; then')
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-mode: could not locate the "
                 "monotonic day-count derivation to mutate -- the step text "
                 "may have changed shape; update this harness alongside it.")
    return script.replace(old, new, 1)


# --------------------------------------------------------------------------
# #966: detect's "does this run verify" decision.
# --------------------------------------------------------------------------
# Answers the step's one `gh issue list` with GH_STUB_ISSUE (already the
# `.[0] // empty` the step's --jq would print), or fails it when
# GH_STUB_FAIL is set. Anything else is a regression the stub refuses.
STUB_GH = r'''#!/usr/bin/env bash
if [ "$1 $2" = "issue list" ]; then
  if [ -n "${GH_STUB_FAIL:-}" ]; then
    echo "HTTP 502: Bad Gateway" >&2
    exit 1
  fi
  printf '%s' "${GH_STUB_ISSUE:-}"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''


def _issue(body):
    return json.dumps({"number": 966, "body": body})


CONTAINER_FAILURE = _issue(
    "**Classification**: pipeline defect (fail-wrong-output)\n\n"
    "**Verified head**: abc\n\n**Mode**: container\n\n"
    "**Failing check**: verify-image-prerequisites\n")
DEFAULT_RUNNER_FAILURE = _issue(
    "**Classification**: infrastructure (fail-infra)\r\n\r\n"
    "**Mode**: default-runner\r\n\r\n**Failing check**: reset\r\n")
PAUSED_FAILURE = _issue(
    "**Mode**: default-runner (container mode not exercised: paused)\n")
UNKNOWN_MODE_FAILURE = _issue(
    "**Classification**: infrastructure (job failure)\n\n"
    "**Mode**: unknown (this run did not reach verify-e2e, or its mode "
    "could not be read)\n")
COLLISION_FAILURE = _issue(
    "**Classification**: version collision\n\n**Verified head**: abc\n")

# (name, HAS_NEW_WORK, MODE, issue JSON -- "" for none open, None for "the
#  lookup fails" -- expected run-verification, expected failure-issue-mode)
VERIFY_SCENARIOS = [
    ("no unreleased head, open container failure, container turn: the "
     "failing mode is re-verified (#966)",
     "false", "container", CONTAINER_FAILURE, "true", "container"),
    ("no unreleased head, open container failure, default-runner turn: "
     "nothing to verify -- the container failure waits for its own turn",
     "false", "default-runner", CONTAINER_FAILURE, "false", "container"),
    ("no unreleased head, open default-runner failure (CRLF body), "
     "default-runner turn: re-verified",
     "false", "default-runner", DEFAULT_RUNNER_FAILURE, "true", "default-runner"),
    ("a failure filed on a paused container turn records the default-runner "
     "mode that actually ran",
     "false", "default-runner", PAUSED_FAILURE, "true", "default-runner"),
    ("an open failure no single mode owns is unrecorded and triggers nothing",
     "false", "container", UNKNOWN_MODE_FAILURE, "false", "unrecorded"),
    ("a collision body carries no Mode line: unrecorded",
     "false", "default-runner", COLLISION_FAILURE, "false", "unrecorded"),
    ("no open failure issue, nothing unreleased: a quiet day",
     "false", "container", "", "false", ""),
    ("unreleased head, no open failure: verified, as before",
     "true", "default-runner", "", "true", ""),
    ("unreleased head, open failure in the other mode: still verified",
     "true", "default-runner", CONTAINER_FAILURE, "true", "container"),
    ("the issue lookup fails: unreadable, and only unreleased work verifies",
     "false", "container", None, "false", "unreadable"),
    ("the issue lookup fails on a day with unreleased work: still verified",
     "true", "container", None, "true", "unreadable"),
]


def run_verify_step(script, has_new_work, mode, issue, tmproot):
    import shutil
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH)
    os.chmod(gh_path, 0o755)
    env = {
        "GH_TOKEN": "dummy-token",
        "GITHUB_REPOSITORY": "charlesguse/wing-commander",
        "HAS_NEW_WORK": has_new_work,
        "MODE": mode,
        "GH_STUB_ISSUE": issue or "",
        "GH_STUB_FAIL": "1" if issue is None else "",
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    rc, out, outputs, _summary = run_step(BASH, script, workdir, env,
                                          runner_temp, path_prepend=bindir)
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outputs


def verify_suite(script, tmproot):
    failures = []
    for name, new_work, mode, issue, want_run, want_mode in VERIFY_SCENARIOS:
        tag = f"[{name}]"
        rc, out, o = run_verify_step(script, new_work, mode, issue, tmproot)
        if rc != 0:
            failures.append(f"{tag} the step exited {rc} -- it must never fail "
                            f"detect:\n{out}")
            continue
        if o.get("run-verification") != want_run:
            failures.append(f"{tag} run-verification={o.get('run-verification')!r}, "
                            f"expected {want_run!r}; outputs {o}")
        if (o.get("failure-issue-mode") or "") != want_mode:
            failures.append(f"{tag} failure-issue-mode={o.get('failure-issue-mode')!r}, "
                            f"expected {want_mode!r}")
        if issue and o.get("failure-issue") != "966":
            failures.append(f"{tag} failure-issue={o.get('failure-issue')!r}, expected '966'")
    return failures


def job_conditions():
    """The `if:` strings that consume detect's decision."""
    return {job: str(find_job(WORKFLOW, job).get("if", ""))
            for job in ("e2e-pin", "verify-e2e", "decide-version")}


def static_failures(conds):
    failures = []
    for job in ("e2e-pin", "verify-e2e"):
        if "needs.detect.outputs.run-verification == 'true'" not in conds[job]:
            failures.append(
                f"[{job} runs on run-verification] a no-unreleased-head run with an "
                f"open failure in its mode would never re-verify (#966): if={conds[job]!r}")
    if "needs.detect.outputs.has-new-work == 'true'" not in conds["decide-version"]:
        failures.append(
            "[decide-version still gated on has-new-work] a re-verification of an "
            "already-released head would compute and dispatch a release: "
            f"if={conds['decide-version']!r}")
    return failures


SAME_MODE_ARM = 'elif [ -n "$MODE" ] && [ "$failure_mode" = "$MODE" ]; then'


def mut_mode_blind_verification(script):
    """Put back "verify only unreleased work" -- the pre-#966 shape."""
    if script.count(SAME_MODE_ARM) != 1:
        sys.exit("::error::verify-auto-release-mode: could not locate the "
                 "same-mode re-verification arm to mutate -- update this "
                 "harness alongside the step.")
    return script.replace(SAME_MODE_ARM, "elif false; then", 1)


def mut_any_failure_verifies(script):
    """Re-verify on any open failure, whatever mode it records."""
    return script.replace(SAME_MODE_ARM, 'elif [ -n "$failure_mode" ]; then', 1)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")

    step = find_step(WORKFLOW, STEP)
    script = str(step["run"])
    if "${{" in script:
        sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")

    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        failures = suite(script, tmproot)
        for f in failures:
            print(f"::error::{f}")

        mutated = mut_day_of_year_parity(script)
        broke = suite(mutated, tmproot)
        if broke:
            print(f"Mutation OK -- day-of-year parity reinstated: "
                  f"{len(broke)} assertion(s) fail.")
        else:
            print("::error::MUTATION SURVIVED -- reinstating day-of-year "
                  "parity broke nothing in this suite, so the suite is not "
                  "testing the year-boundary regression.")
            failures.append("mutation survived: day-of-year parity")

        verify_script = str(find_step(WORKFLOW, VERIFY_STEP)["run"])
        if "${{" in verify_script:
            sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                     f"${{{{ }}}} expression this harness does not resolve.")
        vf = verify_suite(verify_script, tmproot)
        conds = job_conditions()
        vf += static_failures(conds)
        for f in vf:
            print(f"::error::{f}")
        failures += vf
        for label, mutate in (
                ("re-verification blind to the open failure's mode (#966)",
                 mut_mode_blind_verification),
                ("any open failure re-verifies, whatever its mode",
                 mut_any_failure_verifies)):
            mutated = mutate(verify_script)
            if mutated == verify_script or not verify_suite(mutated, tmproot):
                print(f"::error::MUTATION SURVIVED -- {label}")
                failures.append(f"mutation survived: {label}")
            else:
                print(f"Mutation OK -- {label}.")
        for label, job, old, new in (
                ("e2e-pin back on has-new-work", "e2e-pin",
                 "run-verification", "has-new-work"),
                ("verify-e2e back on has-new-work", "verify-e2e",
                 "run-verification", "has-new-work"),
                ("decide-version no longer gated on has-new-work", "decide-version",
                 "needs.detect.outputs.has-new-work == 'true' && ", "")):
            mutated_conds = dict(conds)
            mutated_conds[job] = conds[job].replace(old, new)
            if mutated_conds[job] == conds[job] or not static_failures(mutated_conds):
                print(f"::error::MUTATION SURVIVED -- {label}")
                failures.append(f"mutation survived: {label}")
            else:
                print(f"Mutation OK -- {label}.")
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"auto-release mode derivation: {len(SCENARIOS)} scenario(s) plus "
          f"the pause-control checks, {len(VERIFY_SCENARIOS)} verification-"
          f"decision scenario(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
