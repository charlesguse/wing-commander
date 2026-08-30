#!/usr/bin/env python3
"""Run the PR-time gate suite locally. One command, no arguments needed.

    python .github/scripts/run-local-gates.py
    python .github/scripts/run-local-gates.py sentinel gate-7   # filter
    python .github/scripts/run-local-gates.py --jobs 1          # serial

WHY THIS EXISTS
---------------
The checks in this directory are the repository's real safety net, and until
now the only way to run them was to read lint-workflows.yml, copy each `run:`
line out by hand, and discover one at a time that `python3` on Windows is the
Microsoft Store stub and `bash` is the WSL launcher. A gate suite that is
awkward to run before pushing gets run after pushing, which is how a verifier
ends up merged in a state where it cannot fail.

It is also the single command for spec artifacts to point at. A quickstart
that enumerates script paths goes stale the first time one is renamed; this
one does not, because the gate list is DERIVED from what lint-workflows.yml
actually invokes (wc_gate_registry.pr_time_invocations). Adding a gate to CI
adds it here, with nobody remembering to.

Arguments are derived too, and that part is load-bearing rather than tidy.
This runner used to invoke every gate bare, which for most of them merely
selected a default mode - but for `verify-versioning-refs.py` it changed the
SUBJECT. CI runs that one `--self-test`; bare, it defaults to
`--remote origin` and reaches across the network, so a maintainer running
the sweep offline or in a restricted sandbox got a confident FAIL on a check
the pull request never performs. A local suite that runs a different check
than CI is not a rehearsal of CI, and the discrepancy hides well because
both ends look green on a good day. A gate CI invokes twice with different
flags now runs twice here too.

WHAT IT DOES NOT RUN
--------------------
Checks wired to other workflows — verify-watchdog-run.sh belongs to the
watchdog self-test and needs a live run id and a token, so it is not
something a local sweep can honestly report on. verify-gate-wiring.py knows
about those; this runner only claims to cover the PR-time suite.

PARALLELISM (--jobs)
---------------------
Serial, the suite measured 1599s: one ~300s harness (run-tests.sh) and a
handful of 40-120s verify-*.py self-tests dominate, while most gates finish
in under 5s. Every gate here is already a subprocess.run of a SEPARATE
process, so a thread pool submitting those calls parallelises real wall
time with no GIL concern — the Python interpreter running this file is
never doing the CPU-bound work, it is just waiting on children.

Threads are safe to interleave here because a targeted audit (2026-08,
alongside this flag's introduction) found nothing that shares mutable state
across gates:

  * Every gate that needs a scratch directory gets it from
    `tempfile.mkdtemp()`/`mktemp -d`, which mints a fresh random-suffixed
    path per call — two gates, or two invocations of the SAME gate (a
    script CI invokes twice with different flags, see above), never
    collide on a fixed name the way a hard-coded `RUNNER_TEMP/foo` would.
  * `ensure_jq()` (wc_shell_harness.py) does not download anything — it
    only probes PATH and a fixed list of known local install directories
    and, at most, prepends one of them to THIS process's PATH. It runs
    once, before any gate is dispatched, so there is no concurrent-write
    window at all.
  * No gate mutates this repository's working tree. Every gate that runs
    `git init`/`add`/`commit`/`push` does so inside a throwaway repo it
    just created under its own temp dir (verify-stall-restart-runbook.py,
    the auto-update-spec-kit-tests harness, etc.) — the real checkout is
    read from, at most (e.g. `cp "$REPO"/.specify ...`), never written to.
  * Neither this runner nor any gate calls `os.chdir`. Gates that `cd`
    do so inside a bash subprocess of their own, which cannot change this
    process's (or a sibling thread's) working directory.

`--jobs 1` does not go through the pool at all — it keeps running the
original sequential loop verbatim, so its output and behavior stay
byte-for-byte what this script always produced. `--jobs N>1` prints one
PASS/FAIL line per gate as it COMPLETES (not in the list order above,
since faster gates finish out of order), with that gate's full output
inlined immediately below a FAIL. The final table and totals line are
still printed for both modes, so a parallel run and a serial run report
the same pass/fail facts even though the second column of a live run is
compressed to wall-clock time rather than the historical CI-style body.

SCHEDULING (the timing cache)
------------------------------
Submission order matters for a bounded pool: the registry orders gates
however wc_gate_registry happened to walk lint-workflows.yml, which is not
correlated with cost. Left as-is, the three ~300s gates can land late in
that order, so they start only after several worker-seconds have already
gone by and the run's tail becomes one worker grinding alone through a
gate that could have started at t=0 — the classic bin-packing mistake of
scheduling the heaviest items last.

The fix is a self-maintaining timing cache rather than a hard-coded list
of "the slow gates": a literal list is exactly the anti-pattern this
repository keeps re-discovering the expensive way (see the module-level
WHY THIS EXISTS above, and wc_gate_registry's own docstring on why gate
membership is a mechanical convention rather than a manifest) — it would
drift the moment a gate's cost changed materially, and nothing would ever
notice, because a stale schedule still finishes correctly, just slower.
A cache keyed by the same label this script already prints requires no
maintenance: every run records what it measured, so the schedule tracks
reality automatically.

  * Storage: `<tempdir>/wing-commander-gate-timings.json`, one JSON object
    of `{label: seconds}`. Machine-local scratch on purpose — it is a
    performance hint, not a fact about the repository, and committing it
    would make every maintainer's local hardware speed part of the diff.
    Written atomically (temp file in the same directory + os.replace) so
    a run killed mid-write cannot leave the next run reading a torn file,
    and merged with whatever was already there so a filtered run (three
    gates) does not evict the timings of the other fifty-four.
  * Loading is wrapped in a bare try/except returning {}: missing (first
    run ever), corrupt (killed mid-write on some OTHER machine sharing
    the temp dir, hand-edited, OS-cleaned mid-run), or simply absent for
    a label that never ran locally before are all the same case from the
    scheduler's point of view — proceed with no hint rather than fail the
    whole suite over a cache that only ever exists to make things faster.
  * Sort key: known durations descending, UNKNOWN LABELS FIRST (treated
    as heaviest). This is the safe default in both directions: a gate
    that turns out to be cheap merely starts a little early and finishes
    fast, costing nothing; a gate that turns out to be the next 300s
    outlier is never starved to the end of the queue by having no data
    yet. It also means a bare `--jobs N` with no cache present degrades
    to exactly today's registry-order behavior (every label ties at
    "unknown," so the stable sort leaves the original order untouched),
    and the very next run — cache now populated — self-heals into
    longest-first without anyone invoking a separate warm-up step.
  * `--jobs 1` records timings too (folded into the same cache the
    parallel path reads), so alternating between `--jobs 1` for a
    one-off debug run and the parallel default does not leave the cache
    stale — but it does not print anything about doing so, because its
    whole contract above is byte-identical output to the pre-cache
    script.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import pr_time_invocations  # noqa: E402
from wc_shell_harness import ensure_jq, resolve_bash, use_utf8_stdout  # noqa: E402


TIMING_CACHE_PATH = os.path.join(tempfile.gettempdir(),
                                 "wing-commander-gate-timings.json")


def _load_timing_cache():
    """{label: last-measured seconds}, or {} on any reason it isn't usable.

    Deliberately a blanket except: every failure mode here (file absent,
    truncated by a killed run, hand-edited, a stale schema from some future
    version of this script) means the same thing to the caller — no hint
    available, fall back to registry order — and none of them should turn
    a scheduling nicety into a suite failure. See the SCHEDULING section of
    this module's docstring for why this lives in the OS temp dir rather
    than the repo.
    """
    try:
        with open(TIMING_CACHE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_timing_cache(measured):
    """Merge `measured` ({label: seconds}) into the cache, written atomically.

    Merge, not overwrite: a filtered run (`run-local-gates.py gate-7`) only
    measured one label and must not blank out the other fifty-six the next
    parallel run would otherwise get a scheduling hint for. Atomic via
    temp-file-then-os.replace in the SAME directory (so the replace is a
    same-filesystem rename, not a cross-device copy) — a run killed mid-write
    must never leave a half-written JSON file for the next run to trip over,
    which is exactly the failure `_load_timing_cache` above is written to
    shrug off, but there is no reason to manufacture it when os.replace
    makes the write instantaneous from any reader's point of view.

    Best-effort: an OSError here (read-only temp dir, out of space) must not
    fail the gate suite over a file that only ever exists to make the next
    run schedule slightly better.
    """
    cache = _load_timing_cache()
    cache.update(measured)
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(TIMING_CACHE_PATH),
            prefix=".wing-commander-gate-timings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
            os.replace(tmp_path, TIMING_CACHE_PATH)
        except OSError:
            os.remove(tmp_path)
            raise
    except OSError:
        pass


def command_for(script, bash, args=()):
    """How to invoke one gate, with the arguments CI gives it.

    .py goes to THIS interpreter rather than to `python3`: on Windows the
    latter is usually the Microsoft Store stub, which exits 49 without
    running anything, and the resulting "gate failed" is about PATH rather
    than about the code.
    """
    if script.endswith(".py"):
        return [sys.executable, script] + list(args)
    return [bash, script] + list(args)


def _parse_jobs_flag(argv):
    """Pull `--jobs N` / `--jobs=N` out of argv; everything else is a filter.

    Not argparse: this script has never had a flag before, every other
    token is a free-text filter substring (see label_of matching below),
    and argparse's positional/optional mixing would have to special-case
    that anyway. A tiny hand-rolled scan keeps `--jobs 4 sentinel gate-7`
    and `sentinel --jobs=4 gate-7` both working, which is the level of
    tolerance the existing filter argument already gets.
    """
    jobs = None
    filters = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--jobs":
            if i + 1 >= len(argv):
                sys.exit("--jobs requires a value, e.g. --jobs 4")
            jobs = argv[i + 1]
            i += 2
            continue
        if tok.startswith("--jobs="):
            jobs = tok[len("--jobs="):]
            i += 1
            continue
        filters.append(tok)
        i += 1
    if jobs is None:
        jobs = os.cpu_count() or 4
    else:
        try:
            jobs = int(jobs)
        except ValueError:
            sys.exit(f"--jobs expects an integer, got {jobs!r}")
        if jobs < 1:
            sys.exit("--jobs must be >= 1")
    return jobs, filters


def _run_one(script, args, bash, label):
    """Invoke one gate and collect its result. Runs on a pool thread.

    Each call is its own OS process (subprocess.run), so nothing here
    touches state another thread's call could also be touching — see the
    PARALLELISM section of this module's docstring for the audit that
    established that.
    """
    start = time.time()
    proc = subprocess.run(command_for(script, bash, args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    elapsed = time.time() - start
    out = (proc.stdout or "") + (proc.stderr or "")
    return label, proc.returncode, elapsed, out


def main(argv):
    use_utf8_stdout()
    if not os.path.isdir(".github/workflows"):
        sys.exit("run this from the repository root.")
    ensure_jq()
    bash = resolve_bash()

    all_gates = pr_time_invocations()

    def label_of(script, args):
        base = os.path.basename(script)
        return (base + " " + " ".join(args)).strip()

    jobs, argv = _parse_jobs_flag(argv)

    gates = all_gates
    if argv:
        gates = [(sc, ar) for sc, ar in gates
                 if any(t in label_of(sc, ar) or t in sc for t in argv)]
    if not gates:
        sys.exit(f"no gates matched {argv!r}. Available:\n  "
                 + "\n  ".join(label_of(sc, ar)
                                  for sc, ar in all_gates))

    results = []
    wall_start = time.time()

    if jobs == 1:
        # The original sequential loop, untouched, so `--jobs 1` is not a
        # 1-worker pool that HAPPENS to behave the same — it is the exact
        # code path this script ran before parallelism existed. Anything
        # that ever depended on that (a maintainer's muscle memory, a spec
        # quickstart quoting this output) keeps working unconditionally.
        print(f"Running {len(gates)} gate(s) with {sys.executable}\n"
              f"                and bash {bash}\n")
        for script, args in gates:
            label = label_of(script, args)
            print(f"--- {label} " + "-" * max(0, 60 - len(label)))
            start = time.time()
            proc = subprocess.run(command_for(script, bash, args),
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            elapsed = time.time() - start
            out = (proc.stdout or "") + (proc.stderr or "")
            # Full output only for failures: a passing sweep should be
            # readable at a glance, and every one of these gates prints its
            # own verdict line, which is the part worth seeing when it
            # passed.
            if proc.returncode == 0:
                tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
                print("\n".join(tail) or "(no output)")
            else:
                print(out.strip() or "(no output)")
            results.append((label, proc.returncode, elapsed))
            print()
    else:
        print(f"Running {len(gates)} gate(s) with {sys.executable}\n"
              f"                and bash {bash}\n"
              f"                across {jobs} worker(s) in parallel — lines "
              f"below print in COMPLETION order.\n")
        # Longest-known-first submission: a bounded pool finishes soonest
        # when the biggest items go in first, so the tail isn't one worker
        # alone on a 300s gate the other N-1 workers could have been
        # helping shorten from the start. `timing_cache.get(label, inf)`
        # makes an unmeasured gate sort as heaviest — see SCHEDULING in
        # this module's docstring for why that default, and why the cache
        # lives outside the repo.
        timing_cache = _load_timing_cache()
        gates = sorted(
            gates,
            key=lambda sa: -timing_cache.get(label_of(*sa), float("inf")))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_run_one, script, args, bash,
                                   label_of(script, args))
                       for script, args in gates]
            for fut in concurrent.futures.as_completed(futures):
                label, rc, elapsed, out = fut.result()
                status = "PASS" if rc == 0 else "FAIL"
                print(f"{status}  {elapsed:6.1f}s  {label}")
                if rc != 0:
                    # Delimited and printed right away rather than held for
                    # the final table: in a live run a maintainer is
                    # watching this stream, and the failure's own output is
                    # the part worth seeing the moment it is known, same as
                    # the serial path already does.
                    print(f"----- {label} output " + "-" * 40)
                    print(out.strip() or "(no output)")
                    print("-" * 70)
                results.append((label, rc, elapsed))

    wall_elapsed = time.time() - wall_start

    # Record what this run measured for next time, regardless of --jobs.
    # This is silent by design (--jobs 1's contract above is byte-identical
    # output to the pre-cache script) and best-effort (see
    # _save_timing_cache) — a maintainer offline or on a read-only temp dir
    # still gets a correct, merely unscheduled, run.
    _save_timing_cache({label: elapsed for label, _, elapsed in results})

    width = max(len(r[0]) for r in results)
    print("=" * (width + 22))
    for label, rc, elapsed in results:
        print(f"{label:<{width}}  {'PASS' if rc == 0 else 'FAIL'}  {elapsed:6.1f}s")
    failed = [r for r in results if r[1] != 0]
    print("=" * (width + 22))
    if jobs == 1:
        print(f"{len(results) - len(failed)}/{len(results)} passed, "
              f"{sum(r[2] for r in results):.1f}s total")
    else:
        # Wall-clock is what a maintainer waiting on this run experiences;
        # the summed per-gate time is also printed since it is what the
        # 1599s serial baseline is comparable to, and the gap between the
        # two numbers is the parallelism's whole point.
        print(f"{len(results) - len(failed)}/{len(results)} passed, "
              f"{wall_elapsed:.1f}s wall-clock total "
              f"({sum(r[2] for r in results):.1f}s summed across gates)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
