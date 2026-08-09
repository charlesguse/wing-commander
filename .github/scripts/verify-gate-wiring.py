#!/usr/bin/env python3
"""Assert every check in .github/scripts is actually run, and vice versa.

WHY THIS EXISTS
---------------
verify-denied-tool-collector.sh was orphaned for weeks: no workflow invoked
it, and while nothing was running it, it drifted out of sync with the filter
it claimed to verify. It still printed "all assertions passed" whenever
someone ran it by hand, so it read as evidence while proving nothing about
the code that shipped. PR #158 wired that script up. It did nothing to stop
the next one from landing the same way, and by then this repository had four
verifiers and was adding more.

This closes it generally, in both directions:

  forward   every .github/scripts/verify-*.{py,sh} and every subdirectory
            harness entrypoint is invoked by at least one workflow. A check
            nobody runs is dead weight that looks like coverage.
  reverse   every .github/scripts/... path a workflow tries to run exists on
            disk. A gate step pointing at a moved or renamed file fails at
            the worst possible moment, and until it does, the gate's name in
            the job list implies a check that is not happening.
  modules   every wc_*.py shared module is imported by something. These are
            exempt from the wiring rule (nothing invokes them directly), so
            without this they are the one place an orphan could still hide.

The rule is a naming convention read off the directory, not a list of gate
names — see wc_gate_registry.py for why a list would recreate issue #149.

Usage: python3 .github/scripts/verify-gate-wiring.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import (  # noqa: E402
    SCRIPTS_DIR, _self_check, invocations, referenced_script_paths,
    shared_modules)


def main():
    failures = []
    _self_check()

    # --- forward: every check is invoked -----------------------------------
    wiring = invocations()
    if not wiring:
        print("::error::found no verify-* scripts at all. Either they moved "
              "or this gate's discovery has broken; either way it is about "
              "to check nothing.")
        return 1
    for script, workflows in wiring.items():
        if workflows:
            print(f"ok    {script} <- {', '.join(workflows)}")
        else:
            failures.append(
                f"{script} is not invoked by any workflow. A verifier nothing "
                f"runs is not a verifier: it will drift out of sync with the "
                f"code it checks and keep reporting success (this is exactly "
                f"what happened to verify-denied-tool-collector.sh). Wire it "
                f"into a gate, or delete it.")

    # --- reverse: every invoked path exists --------------------------------
    for path, workflows in referenced_script_paths().items():
        if not os.path.exists(path):
            failures.append(
                f"{path} is run by {', '.join(workflows)} but does not exist. "
                f"That step will fail the moment it is reached, and until "
                f"then its name in the job list implies a check that is not "
                f"happening.")

    # --- modules: every shared module has an importer ----------------------
    sources = {}
    for name in os.listdir(SCRIPTS_DIR):
        if name.endswith(".py"):
            sources[name] = open(os.path.join(SCRIPTS_DIR, name),
                                 encoding="utf-8").read()
    for module in shared_modules():
        stem = module[:-3]
        importers = sorted(
            n for n, src in sources.items()
            if n != module
            and re.search(rf"^\s*(from {stem} import|import {stem})\b",
                          src, re.M))
        if importers:
            print(f"ok    {module} <- imported by {', '.join(importers)}")
        else:
            failures.append(
                f"{SCRIPTS_DIR}/{module} is a shared module that nothing "
                f"imports. It is exempt from the invocation rule because "
                f"nothing runs it directly, which makes an unused one "
                f"invisible. Use it or delete it.")

    print()
    for f in failures:
        print(f"::error::{f}")
    # ASCII only in this line: it also runs on a maintainer's Windows shell,
    # where a cp1252 stdout cannot encode a dash and the gate would die in
    # the print instead of reporting its verdict.
    print(f"Gate wiring: {len(wiring)} check(s), "
          f"{len(shared_modules())} shared module(s); {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
