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

Usage: python3 .github/scripts/verify-auto-release-mode.py
Requires: bash. See wc_shell_harness.py for running this on Windows.
"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    find_step, parse_github_output, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = ".github/workflows/auto-release.yml"
STEP = "Derive this run's execution mode (container vs default-runner)"

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


def main():
    global BASH
    use_utf8_stdout()
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
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"auto-release mode derivation: {len(SCENARIOS)} scenario(s) plus "
          f"the pause-control checks; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
