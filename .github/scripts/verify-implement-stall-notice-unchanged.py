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
Extracts the `run:` text of implement.yml's three exhausted-retry steps
("Mark lifecycle record stalled", "Report stalled on lifecycle issue",
"Announce the stall on the lifecycle issue") from BASE_REF (the commit
before this feature's implement.yml edits began) and from the current
working tree, and asserts each is byte-for-byte identical. Only the step's
`if:` guard was meant to change (User Story 1's own widening of the
`stalled` job) — this gate proves the wording did not move with it.

Usage: python3 .github/scripts/verify-implement-stall-notice-unchanged.py
Requires: git.
"""
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")

STAGE = ".github/workflows/implement.yml"
BASE_REF = "e877ac5"  # last commit before implement.yml gained T004-T006

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


def git_show(ref, path):
    proc = subprocess.run(["git", "show", f"{ref}:{path}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        sys.exit(f"::error::could not read {path!r} at {ref!r}: {proc.stderr}")
    return proc.stdout


def main():
    old_text = git_show(BASE_REF, STAGE)
    with open(STAGE, encoding="utf-8") as fh:
        new_text = fh.read()

    failures = []
    for name in STEP_NAMES:
        old_step = find_step_in_text(old_text, name)
        new_step = find_step_in_text(new_text, name)
        if old_step is None:
            failures.append(f"{name!r} not found at {BASE_REF} — update "
                            f"BASE_REF or the step name list together with "
                            f"this gate.")
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
                f"{name!r}'s `run:` text changed since {BASE_REF} — Out of "
                f"Scope / research.md D7 requires this step's wording stay "
                f"byte-for-byte unchanged. If the reword was intentional, "
                f"update BASE_REF here to the commit that made it, on "
                f"purpose, in its own reviewed change.")
        # uses:/with: shape (the "Announce" step calls a composite, no run:)
        for key in ("uses", "with"):
            if old_step.get(key) != new_step.get(key):
                failures.append(
                    f"{name!r}'s `{key}:` changed since {BASE_REF}: "
                    f"{old_step.get(key)!r} -> {new_step.get(key)!r}.")

    for f in failures:
        print(f"::error::{f}")
    print(f"implement.yml exhausted-retry notice: {len(STEP_NAMES)} step(s) "
          f"checked against {BASE_REF}; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
