#!/usr/bin/env python3
"""implement.yml's exhausted-retry stall notice reads exactly as it did before.

WHY THIS EXISTS
----------------
specs/041-implement-stall-notice's Out of Scope is explicit: "Rewording the
existing exhausted-retry stall notice ... This feature adds a case; the
current wording for the current case stays" (research.md D7). The safest way
to guarantee that is to never touch the code that renders it — but "we did
not mean to touch it" is not the same claim as "we did not touch it". This
gate makes the second claim mechanically, not by re-reading five hundred
lines of surrounding YAML on every future change.

WHAT THIS CHECKS
----------------
Compares implement.yml's three exhausted-retry steps ("Mark lifecycle record
stalled", "Report stalled on lifecycle issue", "Announce the stall on the
lifecycle issue") in the working tree against
fixtures/implement-stall-notice-baseline.json — their wording pinned from
main at the 2026-08-24 merge (6f04355; spec 040 had already reworded the
pre-041 text, and a git-ref baseline is unreadable in CI's shallow
checkout). Each step's `run:`, `uses:`, and `with:` must match the pin
byte-for-byte; only `if:` guards were 041's to change.

Usage: python3 .github/scripts/verify-implement-stall-notice-unchanged.py
"""
import json
import os
import sys

STAGE = ".github/workflows/implement.yml"
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "implement-stall-notice-baseline.json")

STEP_NAMES = [
    "Mark lifecycle record stalled",
    "Report stalled on lifecycle issue",
    "Announce the stall on the lifecycle issue",
]


def find_step_in_text(text, name):
    import yaml
    wf = yaml.safe_load(text) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == name:
                return step
    return None


def load_baseline():
    try:
        with open(FIXTURE, encoding="utf-8") as fh:
            return json.load(fh)["steps"]
    except (OSError, KeyError, ValueError) as e:
        sys.exit(f"::error file={FIXTURE}::could not load the pinned "
                 f"baseline: {e}")


def main():
    baseline = load_baseline()
    with open(STAGE, encoding="utf-8") as fh:
        new_text = fh.read()

    failures = []
    for name in STEP_NAMES:
        old_step = baseline.get(name)
        new_step = find_step_in_text(new_text, name)
        if old_step is None:
            failures.append(f"{name!r} not pinned in {FIXTURE} — update "
                            f"the fixture or the step name list together "
                            f"with this gate.")
            continue
        if new_step is None:
            failures.append(f"{name!r} no longer exists in {STAGE} — the "
                            f"exhausted-retry notice path was removed, not "
                            f"just left untouched.")
            continue
        old_run = old_step.get("run")
        new_run = new_step.get("run")
        if old_run is not None and new_run != old_run:
            failures.append(
                f"{name!r}'s `run:` text changed since the pinned baseline "
                f"— Out of Scope / research.md D7 requires this step's "
                f"wording stay byte-for-byte unchanged. If the reword was "
                f"intentional, regenerate the fixture on purpose, in its "
                f"own reviewed change.")
        # uses:/with: shape (the "Announce" step calls a composite, no run:)
        for key in ("uses", "with"):
            if old_step.get(key) != new_step.get(key):
                failures.append(
                    f"{name!r}'s `{key}:` changed since the pinned baseline: "
                    f"{old_step.get(key)!r} -> {new_step.get(key)!r}.")

    for f in failures:
        print(f"::error::{f}")
    print(f"implement.yml exhausted-retry notice: {len(STEP_NAMES)} step(s) "
          f"checked against the pinned baseline; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
