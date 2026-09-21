#!/usr/bin/env python3
"""Gate 80 - every job that pushes to a spec branch is in the per-spec group.

WHY THIS EXISTS
---------------
specs/013-serialize-rebase-stages put every stage that writes a
`spec/NNN-slug` branch into one concurrency group, `wing-commander-<spec-dir>`,
with `cancel-in-progress: false`, so GitHub runs one of them at a time per
specification. That is what stops the rebase stage's force-push from racing
a running implement cycle. The rule was written into the contract
(contracts/concurrency-groups.md: "Any future published stage that checks
out and publishes to a specification's working branch MUST declare ... in
this same form") and nothing enforced it.

`cleanup.yml`'s `mark-stalled` job rewrote `spec-meta.json` and pushed onto
the spec branch from a DIFFERENT group, keyed on the closed PR's head ref,
because spec 013's D5 assumed cleanup only runs after a spec's terminal
stage. Closing a plan or tasks PR mid-cycle is not terminal: the push was
unordered against a running implement or rebase on the same branch, and
either the marker or the cycle's push could lose (#397). A group name is
one line of YAML that reads correctly on its own; only a list of every
pusher, held against the rule, shows the one outside it.

WHAT IT CHECKS
--------------
For every job in `.github/workflows/*.yml` that can push, i.e. one that

  (a) runs `git push` in one of its own `run:` steps (comment, `echo` and
      `printf` lines stripped first, so a runbook that prints the command
      for a human is not a pusher),
  (b) grants its agent `Bash(git push:*)` through `wing-commander-tool-args`
      (the agent stages push through the agent, not a `run:` step), or
  (c) calls a local composite whose own `run:` steps push,

the job's `concurrency.group` must be the per-spec group in one of the three
shipped spellings:

    wing-commander-${{ inputs.spec-dir }}
    wing-commander-${{ needs.<job>.outputs.spec-dir }}
    wing-commander-${{ matrix.spec_dir }}

or the (file, job) pair must be waived in
`.github/scripts/spec-branch-push-waivers.json`, with `pushes` (what it
pushes) and `reason`. A waiver is stale-checked: one naming a job that no
longer exists, or no longer pushes, fails the gate, so a waiver cannot
outlive its reason.

WHAT IT DOES NOT CHECK
----------------------
Where a push goes. A `git push` target is a runtime string; this gate
holds every pusher to the group or to a written reason, and the reason is
where "not a spec branch" is stated and reviewed.

SELF-TEST
---------
`--self-test` builds a synthetic tree - a job pushing from a `run:` step,
one pushing through an agent grant, one pushing through a composite, each
in and out of the group, plus waivers that match, are stale, or are
malformed - and asserts each verdict, including the file and job named.

Usage:
    python3 .github/scripts/verify-spec-branch-push-concurrency.py
    python3 .github/scripts/verify-spec-branch-push-concurrency.py --self-test
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

WORKFLOW_DIR = ".github/workflows"
ACTIONS_DIR = ".github/actions"
WAIVERS_PATH = ".github/scripts/spec-branch-push-waivers.json"
TOOL_ARGS_COMPOSITE = "wing-commander-tool-args"

PUSH_RE = re.compile(r"(?<![\w-])git\s+push\b")
PUSH_GRANT_RE = re.compile(r"(?:^|,)\s*Bash\(git push:\*\)\s*(?:,|$)")
# The three spellings the shipped stages use (specs/013 contract). The
# group must be EXACTLY one of these: a prefix match would admit
# `wing-commander-${{ inputs.spec-dir }}-something`, a different group.
PER_SPEC_GROUP_RE = re.compile(
    r"^wing-commander-\$\{\{\s*"
    r"(?:inputs\.spec-dir|needs\.[\w-]+\.outputs\.spec-dir|matrix\.spec_dir)"
    r"\s*\}\}$")
LOCAL_COMPOSITE_RE = re.compile(r"(?:^|/)\.github/actions/([\w-]+)/?$")
NOISE_LINE_RE = re.compile(r"^\s*(?:#|echo\b|printf\b)")


def _rel(path):
    return path.replace(os.sep, "/")


def _run_text(step):
    """A step's `run:` with comment/echo/printf lines dropped."""
    run = (step or {}).get("run")
    if not isinstance(run, str):
        return ""
    return "\n".join(line for line in run.splitlines()
                     if not NOISE_LINE_RE.match(line))


def _composite_name(uses):
    m = LOCAL_COMPOSITE_RE.search(str(uses or "").strip())
    return m.group(1) if m else None


def pushing_composites(root="."):
    """-> {composite-name} whose action.yml runs `git push` itself."""
    out = set()
    for path in sorted(glob.glob(os.path.join(root, ACTIONS_DIR, "*", "action.yml"))):
        with io.open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        steps = ((doc.get("runs") or {}).get("steps")) or []
        if any(PUSH_RE.search(_run_text(s)) for s in steps if isinstance(s, dict)):
            out.add(os.path.basename(os.path.dirname(path)))
    return out


def push_reasons(job, composites):
    """-> ["run step 'X'", "agent grant on 'Y'", "composite Z via 'W'"]."""
    reasons = []
    for step in (job or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = step.get("name") or step.get("id") or "<unnamed step>"
        if PUSH_RE.search(_run_text(step)):
            reasons.append("run step {0!r}".format(name))
        uses = str(step.get("uses") or "")
        with_ = step.get("with") or {}
        if TOOL_ARGS_COMPOSITE in uses and PUSH_GRANT_RE.search(
                str(with_.get("default-allowed-tools", ""))):
            reasons.append("agent grant Bash(git push:*) on {0!r}".format(name))
        comp = _composite_name(uses)
        if comp and comp in composites:
            reasons.append("composite {0} via {1!r}".format(comp, name))
    return reasons


def discover(root="."):
    """-> [(file, job, group, reasons)] for every job that can push."""
    composites = pushing_composites(root)
    found = []
    for path in sorted(glob.glob(os.path.join(root, WORKFLOW_DIR, "*.yml"))):
        with io.open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        rel = _rel(os.path.relpath(path, root))
        for job_name, job in ((doc.get("jobs") or {}).items()):
            reasons = push_reasons(job, composites)
            if not reasons:
                continue
            conc = (job or {}).get("concurrency")
            group = conc.get("group") if isinstance(conc, dict) else conc
            found.append((rel, job_name, group, reasons))
    return found


def load_waivers(root="."):
    """-> (waivers, failures). A missing file is no waivers, not an error."""
    path = os.path.join(root, WAIVERS_PATH)
    if not os.path.exists(path):
        return [], []
    try:
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return [], ["{0} could not be read ({1}); a waiver file that does not "
                    "parse would silence every waiver check.".format(WAIVERS_PATH, e)]
    waivers = data.get("waivers") if isinstance(data, dict) else None
    if not isinstance(waivers, list):
        return [], ["{0} must contain a \"waivers\" list.".format(WAIVERS_PATH)]
    failures = []
    good = []
    for i, w in enumerate(waivers):
        missing = [k for k in ("file", "job", "pushes", "reason")
                   if not isinstance(w, dict) or not str(w.get(k, "")).strip()]
        if missing:
            # A malformed waiver waives nothing: the job it half-names is
            # reported as unwaived as well, so the fix is to complete it.
            failures.append("{0} waiver #{1} is missing {2}: every waiver names "
                            "the file, the job, what it pushes, and why that is "
                            "not a spec branch write.".format(
                                WAIVERS_PATH, i, ", ".join(missing)))
        else:
            good.append(w)
    return good, failures


def evaluate(found, waivers):
    """-> list of failure strings."""
    failures = []
    waived = {(w.get("file"), w.get("job")) for w in waivers}
    seen = set()
    for rel, job_name, group, reasons in found:
        seen.add((rel, job_name))
        if (rel, job_name) in waived:
            continue
        if isinstance(group, str) and PER_SPEC_GROUP_RE.match(group.strip()):
            continue
        failures.append(
            "{0} [{1}] can push ({2}) but its concurrency group is {3!r}, not "
            "the per-spec group `wing-commander-<spec-dir>` every spec-branch "
            "writer shares (specs/013 contract, #397). Join the group, or "
            "waive the job in {4} with what it pushes and why.".format(
                rel, job_name, "; ".join(reasons),
                group, WAIVERS_PATH))
    for w in waivers:
        key = (w.get("file"), w.get("job"))
        if key not in seen:
            failures.append(
                "{0} waives {1} [{2}], which does not exist or no longer pushes; "
                "a waiver cannot outlive its reason - remove it.".format(
                    WAIVERS_PATH, key[0], key[1]))
    return failures


def run(root="."):
    waivers, failures = load_waivers(root)
    found = discover(root)
    return found, failures + evaluate(found, waivers)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
_NL = chr(10)


def _job(name, group, steps):
    text = "  {0}:{1}    runs-on: ubuntu-latest{1}".format(name, _NL)
    if group is not None:
        text += "    concurrency:{0}      group: \"{1}\"{0}".format(_NL, group)
    text += "    steps:" + _NL + steps
    return text


RUN_PUSH = ("      - name: Publish" + _NL +
            "        run: |" + _NL +
            "          git commit -am x" + _NL +
            "          git push origin HEAD" + _NL)
RUN_ECHO_ONLY = ("      - name: Runbook" + _NL +
                 "        run: |" + _NL +
                 "          # git push origin --delete x" + _NL +
                 "          echo \"git push origin --delete x\"" + _NL)
AGENT_GRANT = ("      - uses: ./.github/actions/wing-commander-tool-args" + _NL +
               "        with:" + _NL +
               "          step-label: \"x\"" + _NL +
               "          default-allowed-tools: \"Read,Bash(git push:*),Bash(ls:*)\"" + _NL)
COMPOSITE_CALL = ("      - uses: ./.wing-commander-pipeline/.github/actions/pusher" + _NL)
COMPOSITE_ACTION = ("name: pusher" + _NL + "runs:" + _NL +
                    "  using: composite" + _NL + "  steps:" + _NL +
                    "    - shell: bash" + _NL +
                    "      run: git push origin HEAD:refs/heads/x" + _NL)
GOOD_GROUP = "wing-commander-${{ inputs.spec-dir }}"
MATRIX_GROUP = "wing-commander-${{ matrix.spec_dir }}"
NEEDS_GROUP = "wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}"
BAD_GROUP = "wing-commander-cleanup-${{ inputs.head-ref }}"
NEAR_GROUP = "wing-commander-${{ inputs.spec-dir }}-extra"


def _tree(jobs_text, waivers=None, composite=True):
    tmp = tempfile.mkdtemp(prefix="gate80-")
    os.makedirs(os.path.join(tmp, WORKFLOW_DIR))
    with io.open(os.path.join(tmp, WORKFLOW_DIR, "stage.yml"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write("name: stage" + _NL + "on: [push]" + _NL + "jobs:" + _NL + jobs_text)
    if composite:
        os.makedirs(os.path.join(tmp, ACTIONS_DIR, "pusher"))
        with io.open(os.path.join(tmp, ACTIONS_DIR, "pusher", "action.yml"),
                     "w", encoding="utf-8", newline="") as fh:
            fh.write(COMPOSITE_ACTION)
    if waivers is not None:
        os.makedirs(os.path.join(tmp, ".github/scripts"), exist_ok=True)
        with io.open(os.path.join(tmp, WAIVERS_PATH), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write(waivers if isinstance(waivers, str)
                     else json.dumps({"waivers": waivers}))
    return tmp


def self_test():
    bad = 0

    def case(label, jobs_text, expect_failing_jobs, waivers=None,
             expect_substrings=(), composite=True):
        nonlocal bad
        tmp = _tree(jobs_text, waivers, composite)
        try:
            _found, failures = run(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        joined = " | ".join(failures)
        named = sorted({m for m in re.findall(r"\[([\w-]+)\]", joined)})
        ok = named == sorted(expect_failing_jobs) and all(
            s in joined for s in expect_substrings)
        if expect_failing_jobs == [] and expect_substrings:
            ok = all(s in joined for s in expect_substrings)
        if ok:
            print("[ok] {0}".format(label))
        else:
            bad += 1
            print("[FAIL] {0}: expected jobs {1} and {2}, got: {3}".format(
                label, expect_failing_jobs, list(expect_substrings), failures or "clean"))

    case("a run-step pusher in the per-spec group passes (all three spellings)",
         _job("a", GOOD_GROUP, RUN_PUSH) + _job("b", MATRIX_GROUP, RUN_PUSH)
         + _job("c", NEEDS_GROUP, RUN_PUSH), [])
    case("a run-step pusher outside the group fails, naming the job and the group",
         _job("a", BAD_GROUP, RUN_PUSH), ["a"],
         expect_substrings=[BAD_GROUP, "run step 'Publish'"])
    case("a run-step pusher with no concurrency at all fails",
         _job("a", None, RUN_PUSH), ["a"], expect_substrings=["None"])
    case("a group that merely starts with the per-spec spelling is not the group",
         _job("a", NEAR_GROUP, RUN_PUSH), ["a"])
    case("an agent grant of Bash(git push:*) outside the group fails",
         _job("a", "wing-commander-intake", AGENT_GRANT), ["a"],
         expect_substrings=["agent grant Bash(git push:*)"])
    case("a composite that pushes, called from outside the group, fails",
         _job("a", None, COMPOSITE_CALL), ["a"],
         expect_substrings=["composite pusher"])
    case("the same composite call inside the group passes",
         _job("a", GOOD_GROUP, COMPOSITE_CALL), [])
    case("a runbook that only echoes or comments `git push` is not a pusher",
         _job("a", None, RUN_ECHO_ONLY), [])
    case("a waiver naming the job suppresses exactly that job",
         _job("a", None, RUN_PUSH) + _job("b", None, RUN_PUSH), ["b"],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "a tag", "reason": "not a spec branch"}])
    case("a stale waiver (job gone) fails",
         _job("a", GOOD_GROUP, RUN_PUSH), [],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "ghost",
                   "pushes": "x", "reason": "y"}],
         expect_substrings=["does not exist or no longer pushes"])
    case("a stale waiver (job no longer pushes) fails",
         _job("a", None, RUN_ECHO_ONLY), [],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "x", "reason": "y"}],
         expect_substrings=["does not exist or no longer pushes"])
    case("a waiver missing its reason fails",
         _job("a", None, RUN_PUSH), ["a"],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "x"}],
         expect_substrings=["missing reason"])
    case("an unparseable waiver file fails rather than silencing the check",
         _job("a", GOOD_GROUP, RUN_PUSH), [], waivers="{not json",
         expect_substrings=["could not be read"])

    # The shipped defect, replayed against the real tree: cleanup.yml's
    # mark-stalled back in its own head-ref group must fail (#397).
    found = discover(".")
    waivers, _ = load_waivers(".")
    mutated = [(f, j, BAD_GROUP if (f, j) == (".github/workflows/cleanup.yml", "mark-stalled") else g, r)
               for f, j, g, r in found]
    if any(j == "mark-stalled" for _, j, _, _ in found) and any(
            "cleanup.yml [mark-stalled]" in x for x in evaluate(mutated, waivers)):
        print("[ok] the shipped defect replayed: cleanup.yml mark-stalled in its "
              "old head-ref group fails")
    else:
        bad += 1
        print("[FAIL] cleanup.yml mark-stalled back in its old group was not caught")

    print("Gate 80 self-test: {0} failure(s).".format(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="Gate 80 - spec-branch pushers share the per-spec group")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    found, failures = run(args.root)
    for f in failures:
        print("::error::Gate 80: {0}".format(f))
    print("Gate 80: {0} pushing job(s) checked against the per-spec concurrency "
          "group and {1}; {2} failure(s).".format(len(found), WAIVERS_PATH, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
