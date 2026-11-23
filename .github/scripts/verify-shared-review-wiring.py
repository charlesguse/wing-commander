#!/usr/bin/env python3
"""Gate: the shared reviewer is wired as specified (specs/127-shared-pr-reviewer,
FR-003, FR-005, FR-024, FR-026, FR-027, FR-028).

  * `record` is the only job that posts or mints a write token;
  * every downstream job depends on `prepare` (which depends on `guard`);
  * both agents carry explicit models and turn budgets from inputs;
  * the wrapper has the per-PR concurrency group (no cancel) and the kill
    switch is passed through;
  * nothing else in the repository reads the shared verdict (report-only use).

`--self-test` proves each check fails on a mutated workflow.
"""
import copy
import glob
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CALLABLE = os.path.join(ROOT, ".github", "workflows", "shared-pr-reviewer.yml")
WRAPPER = os.path.join(ROOT, ".github", "workflows", "wing-commander-shared-pr-reviewer.yml")
OWN = {"shared-pr-reviewer.yml", "wing-commander-shared-pr-reviewer.yml"}


def callable_problems(wf):
    problems = []
    jobs = wf.get("jobs") or {}
    for name in ("guard", "prepare", "code-run", "find", "check", "record"):
        if name not in jobs:
            problems.append("missing job " + name)
    if problems:
        return problems
    for name, job in jobs.items():
        text = yaml.safe_dump(job)
        if name != "record" and ("issues: write" in text or "permission-issues: write" in text
                                 or "-X POST" in text):
            problems.append("{0} writes or posts; only record may".format(name))
        if name not in ("prepare", "record") and "create-github-app-token" in text:
            problems.append("{0} mints an App token".format(name))
    if "record" not in jobs or "-X POST" not in yaml.safe_dump(jobs["record"]):
        problems.append("record no longer posts the comment")
    for name in ("find", "check", "code-run", "record"):
        needs = jobs[name].get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        if "prepare" not in needs:
            problems.append("{0} does not depend on prepare".format(name))
    if "guard" not in ([jobs["prepare"].get("needs")] if isinstance(jobs["prepare"].get("needs"), str)
                       else jobs["prepare"].get("needs") or []):
        problems.append("prepare does not depend on guard")
    if "needs.guard.outputs.proceed" not in str(jobs["prepare"].get("if", "")):
        problems.append("prepare is not gated on guard's output")
    for name, model, turns in (("find", "find-model", "find-max-turns"),
                               ("check", "check-model", "check-max-turns")):
        text = yaml.safe_dump(jobs[name])
        if "inputs." + model not in text or "inputs." + turns not in text:
            problems.append("{0} lacks an explicit model or turn budget input".format(name))
    return problems


def diff_read_problems(wf):
    """R3-F5: the PR's diff, added files and commits are read with no
    `|| true` to swallow a failure, and an empty diff stops the round."""
    problems = []
    steps = ((wf.get("jobs") or {}).get("prepare") or {}).get("steps") or []
    runs = [str((s or {}).get("run") or "") for s in steps]
    reader = [r for r in runs if "pr.diff" in r]
    if not reader:
        return ["prepare no longer writes the PR's diff"]
    for line in reader[0].splitlines():
        if re.search(r"\bgit (diff|log)\b", line) and re.search(r"\|\|\s*(true|:)\b", line):
            problems.append("prepare swallows a failed git read: " + line.strip())
    if not re.search(r"\[ -s [^\]]*pr\.diff \]", reader[0]):
        problems.append("prepare does not stop the round on an empty diff")
    return problems


def wrapper_problems(wf):
    problems = []
    conc = wf.get("concurrency") or {}
    if "shared-pr-reviewer-" not in str(conc.get("group", "")) or conc.get("cancel-in-progress") is not False:
        problems.append("the wrapper lacks the per-PR concurrency group with cancel-in-progress: false")
    if "WING_COMMANDER_SHARED_REVIEWER_PAUSED" not in yaml.safe_dump(wf):
        problems.append("the wrapper does not pass the kill switch")
    return problems


def readers_problems(root=ROOT):
    """No existing workflow or skill reads the shared verdict (FR-005, FR-028)."""
    problems = []
    needles = ("wing-commander-shared-review-round", "wc_shared_review", "shared-review-")
    paths = glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml"))
    paths += glob.glob(os.path.join(root, ".claude", "skills", "**", "*.md"), recursive=True)
    for path in sorted(paths):
        if os.path.basename(path) in OWN:
            continue
        if os.path.basename(path) == "lint-workflows.yml":
            continue  # the gate registry names the gates, it reads no verdict
        text = open(path, encoding="utf-8", errors="replace").read()
        if any(n in text for n in needles):
            problems.append("{0} reads the shared reviewer's output".format(os.path.relpath(path, root)))
    return problems


def _prepare_diff_step(wf):
    return next(s for s in wf["jobs"]["prepare"]["steps"] if "pr.diff" in str(s.get("run") or ""))


def _swallow_diff(wf):
    step = _prepare_diff_step(wf)
    step["run"] = step["run"].replace("> ../input/pr.diff", "> ../input/pr.diff || true", 1)


def _drop_empty_diff_stop(wf):
    step = _prepare_diff_step(wf)
    step["run"] = "\n".join(l for l in step["run"].splitlines() if "[ -s " not in l)


def main():
    cal = yaml.safe_load(open(CALLABLE, encoding="utf-8")) or {}
    wrap = yaml.safe_load(open(WRAPPER, encoding="utf-8")) or {}
    problems = callable_problems(cal) + diff_read_problems(cal) + wrapper_problems(wrap) + readers_problems()
    if "--self-test" in sys.argv:
        bad = 0
        muts = {
            "find posts": lambda c: c["jobs"]["find"].update({"permissions": {"issues": "write"}}),
            "check loses its model": lambda c: c["jobs"]["check"]["steps"].clear(),
            "prepare loses the guard": lambda c: c["jobs"]["prepare"].update({"needs": []}),
        }
        for label, mutate in muts.items():
            clone = copy.deepcopy(cal)
            mutate(clone)
            if not callable_problems(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        for label, mutate, check in (
                ("a git read swallowed with || true", _swallow_diff, diff_read_problems),
                ("the empty-diff stop removed", _drop_empty_diff_stop, diff_read_problems)):
            clone = copy.deepcopy(cal)
            mutate(clone)
            if not check(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        wclone = copy.deepcopy(wrap)
        wclone["concurrency"] = {}
        if not wrapper_problems(wclone):
            print("::error::self-test: dropped concurrency not caught")
            bad += 1
        return 1 if bad or problems else 0
    for p in problems:
        print("::error::verify-shared-review-wiring: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
