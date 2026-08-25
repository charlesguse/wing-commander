#!/usr/bin/env python3
"""Gate 37 - no template expressions in action-manifest descriptions.

WHY THIS EXISTS
---------------
Watchdog issue #261 (2026-08-25, its first live spec-cycle inspection): the
wing-commander-metrics-summary composite carried `${{ steps.<x>.outputs.y }}`
as PROSE EXAMPLES inside three input descriptions. The runner template-
validates every `${{ }}` in a manifest - including descriptions - and
`steps` is not a named-value there, so the whole action FAILED TO LOAD on
every call, silently (callers are non-fatal), for as long as the watchdog
was paused. actionlint covers workflows, not composite-action manifests, so
nothing red ever said so.

THE RULE
--------
No `${{` anywhere in an `inputs.*.description` or `outputs.*.description`
of any `.github/actions/*/action.yml`. An example belongs in backticks;
even a template that happens to validate today (a `github.*` read) is prose
pretending to be code, one edit away from #261's shape.

Self-test: --self-test runs two inline fixtures (one clean, one carrying
the exact #261 shape) through the same scan, proving the detector detects
(constitution VIII).

Usage: python3 .github/scripts/verify-action-manifest-descriptions.py [--self-test]
Exit: 0 clean; 1 any templated description (or a self-test failure).
"""
import glob
import io
import os
import sys
import tempfile

import yaml

ACTIONS_GLOB = ".github/actions/*/action.yml"


def scan(root="."):
    """-> (failures, manifests_seen)."""
    failures = []
    paths = sorted(glob.glob(os.path.join(root, *ACTIONS_GLOB.split("/"))))
    for path in paths:
        rel = path.replace(os.sep, "/")
        try:
            doc = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            failures.append(f"{rel}: does not parse as YAML ({exc}) - the "
                            f"runner will refuse to load it")
            continue
        for section in ("inputs", "outputs"):
            for name, spec in (doc.get(section) or {}).items():
                desc = (spec or {}).get("description") or ""
                if "${{" in desc:
                    failures.append(
                        f"{rel}: {section}.{name}'s description contains a "
                        f"template expression - the runner validates it and "
                        f"an unrecognized named-value (like `steps`) makes "
                        f"the WHOLE action fail to load, silently at every "
                        f"non-fatal call site (#261). Quote the example in "
                        f"backticks instead.")
    return failures, len(paths)


CLEAN = """\
name: clean
description: fine
inputs:
  ceiling:
    description: >
      `steps.x.outputs.ceiling` from the ceiling step - prose, in backticks.
    required: false
runs:
  using: composite
  steps:
    - run: echo ok
      shell: bash
"""

TEMPLATED = """\
name: broken
description: carries the #261 shape
inputs:
  ceiling:
    description: >
      ${{ steps.x.outputs.ceiling }} from the ceiling step.
    required: false
runs:
  using: composite
  steps:
    - run: echo ok
      shell: bash
"""


def self_test():
    bad = 0
    for label, source, expect_failure in (
            ("clean manifest passes", CLEAN, False),
            ("the #261 shape is caught", TEMPLATED, True)):
        root = tempfile.mkdtemp(prefix="wc-gate37-")
        adir = os.path.join(root, ".github", "actions", "fixture")
        os.makedirs(adir)
        with io.open(os.path.join(adir, "action.yml"), "w",
                     encoding="utf-8", newline="\n") as fh:
            fh.write(source)
        failures, seen = scan(root)
        if seen != 1:
            bad += 1
            print(f"[FAIL] {label}: scanned {seen} manifests, expected 1 - "
                  f"discovery broke and the fixture was never read")
        elif bool(failures) != expect_failure:
            bad += 1
            print(f"[FAIL] {label}: expected "
                  f"{'a failure' if expect_failure else 'a clean pass'}, "
                  f"got: {failures}")
        else:
            print(f"[ok] {label}")
    print(f"Gate 37 self-test: {2 - bad}/2 fixtures behaved as specified.")
    return 1 if bad else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    failures, seen = scan()
    for f in failures:
        print(f"::error::Gate 37: {f}")
    if seen == 0:
        # A gate whose subject vanished must not read as a pass.
        print("::error::Gate 37: no action manifests found under "
              ".github/actions - discovery broke or the actions moved.")
        return 1
    print(f"Gate 37: {seen} action manifest(s) scanned, "
          f"{len(failures)} templated description(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
