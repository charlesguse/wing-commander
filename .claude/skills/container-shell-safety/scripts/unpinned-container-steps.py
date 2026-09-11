#!/usr/bin/env python3
"""`run:` steps in a caller-supplied-container job with no effective
`shell:` -- and, of those, which ones already carry a bash-only construct.

THE DEFECT CLASS
-----------------
A job's `container: image:` can be an adopter's own image (PR #293:
`container: image: ${{ inputs.container-image }}`), never one this repo
controls. A `run:` step with no effective `shell:` (its own, or a job- or
workflow-level `defaults: run: shell:`) has its shell resolved by Actions
from whatever that image offers. On an image without bash reachable the
way Actions expects, that can be `sh` -- and a step whose body uses a
bash-only construct then fails outright (`set -o pipefail` -> "Illegal
option -o pipefail"; an array assignment -> a syntax error; and so on),
not on some steps, on every run against that image.

PR #293 fixed every step its own gate could prove used `set ... pipefail`
-- 38 sites, found only after two review passes missed the first 26 and
a regex-precedent bug in the gate itself. `pipefail` is one bash-only
construct out of several; a step using arrays, `[[ ]]`, `local`, process
substitution, or `read -d` is exactly as exposed and none of those trip
the gate, because a plain substring/regex check that flags EVERY such
construct false-positives constantly on ordinary POSIX-safe shell that
merely mentions those characters in a string or comment. Machine-checking
"is this step actually unsafe" is the wrong tool for that judgment; this
script instead enumerates every CANDIDATE -- unpinned steps in a
caller-supplied-container job -- and leaves "is this one actually at
risk" to whoever is reviewing the change, the same split
`verify-gate-24.py` (exact, auto-fail) and `stranded-steps.py` (broad,
judgment-required) use for step-gating.

WHAT THIS REPORTS
------------------
Every `run:` step in a job `wc_shell_pin.is_container_bound` calls
caller-supplied whose `wc_shell_pin.effective_shell` does not
`wc_shell_pin.pins_bash` it. Findings whose body matches a known
bash-only construct are listed first and labelled with which construct
matched -- these are close to certain defects. Findings with no match are
listed after, unlabelled -- most of these are fine (nothing in a POSIX
`sh` breaks them today), a few are one edit away from not being; judge by
what the step does, the way `stranded-steps.py`'s own "ask:" line leaves
the four-way classification to the reader rather than guessing it.

Usage:
    python3 unpinned-container-steps.py                       # every .github/workflows/*.yml
    python3 unpinned-container-steps.py path/to/workflow.yml  # one or more explicit files
    python3 unpinned-container-steps.py --quiet                # findings only, no notes

Exit status is always 0. This is a review aid, not a gate -- the exact,
auto-failing subset of this same defect class is
`case_container_pipefail_steps_pin_shell_bash` in
verify-metrics-summary-record-emission.py; run that first.
"""
import os
import re
import sys

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, ".github", "scripts"))
from wc_gate_registry import workflow_files  # noqa: E402
from wc_shell_pin import effective_shell, is_container_bound, pins_bash  # noqa: E402
# workflow_files() (not a plain glob) so the default file list gets the same
# forward-slash normalization every gate's findings use -- glob.glob() fills
# the wildcard with the OS's native separator, so a bare glob on Windows
# prints ".github/workflows\x.yml", the exact drift wc_gate_registry._rel()
# exists to prevent.

# Construct -> (regex, human label). Deliberately conservative: each one
# is a real bash-only feature `sh`/dash rejects or silently mishandles,
# not a heuristic guess. A step matching none of these is not proven
# safe -- it is merely not proven unsafe by this list.
BASHISMS = {
    "pipefail": (re.compile(r"\bpipefail\b"),
                 "set -o pipefail (any spelling, incl. split flags)"),
    "array": (re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\+?=\s*\("),
              "array assignment (arr=(...) / arr+=(...))"),
    "assoc-array": (re.compile(r"\bdeclare\s+-[Aa]\b"),
                    "declare -A (associative array)"),
    "double-bracket": (re.compile(r"\[\[.*\]\]"),
                       "[[ ... ]] conditional"),
    "local": (re.compile(r"(?:^|[;&|]|\bthen\b|\bdo\b)\s*local\s+\w",
                          re.MULTILINE),
              "local (function-scoped variable)"),
    "process-sub": (re.compile(r"<\(|\$\(<"),
                    "process substitution (<(...) or $(<file))"),
    "read-d": (re.compile(r"\bread\s+(?:-\w+\s+)*-d\b"),
              "read -d (delimiter option)"),
}


class LineLoader(yaml.SafeLoader):
    """SafeLoader that records each mapping's source line as `__line__`
    (mirrors review-step-gating/scripts/stranded-steps.py's loader) so a
    finding here is a place to jump to, not just a name to grep for."""


def _construct_mapping(loader, node, deep=False):
    mapping = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def step_label(step, index):
    name = step.get("name") or step.get("id") or step.get("uses")
    return str(name) if name else f"step[{index}]"


def matched_bashisms(run_text):
    return [label for _key, (rx, label) in BASHISMS.items()
            if rx.search(run_text)]


def scan_job(path, job_name, job, workflow_doc, findings):
    if not is_container_bound(job):
        return
    for i, step in enumerate(job.get("steps") or []):
        if not isinstance(step, dict) or not step.get("run"):
            continue
        if pins_bash(effective_shell(step, job, workflow_doc)):
            continue
        run_text = str(step.get("run") or "")
        hits = matched_bashisms(run_text)
        where = f"{path}:{step.get('__line__', '?')}"
        findings.append((bool(hits), where, job_name, step_label(step, i), hits))


def main(argv):
    quiet = "--quiet" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        paths = workflow_files()

    findings = []
    scanned = 0
    for path in paths:
        try:
            wf = yaml.load(open(path, encoding="utf-8"), Loader=LineLoader) or {}
        except yaml.YAMLError as exc:
            print(f"{path}: could not parse as YAML ({exc}) -- skipped.")
            continue
        scanned += 1
        for job_name, job in (wf.get("jobs") or {}).items():
            if job_name == "__line__" or not isinstance(job, dict):
                continue
            scan_job(path, job_name, job, wf, findings)

    # Bug-shaped findings (a known construct matched) sort first -- same
    # reasoning as stranded-steps.py's signal-reading sort: a reviewer
    # working top-down should meet the near-certain defects before the
    # "nothing detected, use judgment" tail.
    findings.sort(key=lambda f: (0 if f[0] else 1, f[1]))

    likely = sum(1 for f in findings if f[0])
    for has_bashism, where, job_name, label, hits in findings:
        print(f"\n{where}: job {job_name!r}: {label!r} has no effective "
              f"shell: and runs inside a caller-supplied container.")
        if hits:
            print(f"  matched: {', '.join(hits)}")
            print("  ask: does this actually need bash, or is it already "
                  "POSIX sh-safe despite the match?")
        else:
            print("  matched: (no known bash-only construct detected)")
            print("  ask: is this step genuinely sh-safe today, or does "
                  "what it does (loops over arrays of files, jq + bash "
                  "arithmetic, anything copy-pasted from a bash-pinned "
                  "sibling) make a future edit likely to add one?")

    if not quiet and findings:
        print()
    print(f"{scanned} workflow(s) scanned: {len(findings)} unpinned "
          f"step(s) in caller-supplied-container jobs "
          f"({likely} with a detected bash-only construct, "
          f"{len(findings) - likely} with none detected).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
