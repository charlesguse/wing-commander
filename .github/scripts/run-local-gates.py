#!/usr/bin/env python3
"""Run the PR-time gate suite locally. One command, no arguments needed.

    python .github/scripts/run-local-gates.py
    python .github/scripts/run-local-gates.py sentinel gate-7   # filter

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
actually invokes (wc_gate_registry.pr_time_gates). Adding a gate to CI adds
it here, with nobody remembering to.

WHAT IT DOES NOT RUN
--------------------
Checks wired to other workflows — verify-watchdog-run.sh belongs to the
watchdog self-test and needs a live run id and a token, so it is not
something a local sweep can honestly report on. verify-gate-wiring.py knows
about those; this runner only claims to cover the PR-time suite.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import pr_time_gates  # noqa: E402
from wc_shell_harness import ensure_jq, resolve_bash, use_utf8_stdout  # noqa: E402


def command_for(script, bash):
    """How to invoke one gate.

    .py goes to THIS interpreter rather than to `python3`: on Windows the
    latter is usually the Microsoft Store stub, which exits 49 without
    running anything, and the resulting "gate failed" is about PATH rather
    than about the code.
    """
    if script.endswith(".py"):
        return [sys.executable, script]
    return [bash, script]


def main(argv):
    use_utf8_stdout()
    if not os.path.isdir(".github/workflows"):
        sys.exit("run this from the repository root.")
    ensure_jq()
    bash = resolve_bash()

    gates = pr_time_gates()
    if argv:
        gates = [g for g in gates if any(a in g for a in argv)]
    if not gates:
        sys.exit(f"no gates matched {argv!r}. Available:\n  "
                 + "\n  ".join(pr_time_gates()))

    print(f"Running {len(gates)} gate(s) with {sys.executable}\n"
          f"                and bash {bash}\n")

    results = []
    for script in gates:
        label = os.path.basename(script)
        print(f"--- {label} " + "-" * max(0, 60 - len(label)))
        start = time.time()
        proc = subprocess.run(command_for(script, bash),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        elapsed = time.time() - start
        out = (proc.stdout or "") + (proc.stderr or "")
        # Full output only for failures: a passing sweep should be readable
        # at a glance, and every one of these gates prints its own verdict
        # line, which is the part worth seeing when it passed.
        if proc.returncode == 0:
            tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
            print("\n".join(tail) or "(no output)")
        else:
            print(out.strip() or "(no output)")
        results.append((label, proc.returncode, elapsed))
        print()

    width = max(len(r[0]) for r in results)
    print("=" * (width + 22))
    for label, rc, elapsed in results:
        print(f"{label:<{width}}  {'PASS' if rc == 0 else 'FAIL'}  {elapsed:6.1f}s")
    failed = [r for r in results if r[1] != 0]
    print("=" * (width + 22))
    print(f"{len(results) - len(failed)}/{len(results)} passed, "
          f"{sum(r[2] for r in results):.1f}s total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
