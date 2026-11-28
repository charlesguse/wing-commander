#!/usr/bin/env python3
"""Gate 170 - no external action pin targets a deprecated Node.js runtime,
and none keeps an Actions cache.

WHY THIS EXISTS
---------------
GitHub's runners now force an action that declares `runs.using: node20`
onto Node.js 24 and annotate the run "Node.js 20 is deprecated". The step
still passes, so nothing fails until the runners drop that fallback. The
watchdog saw the annotation and filed #1127 (`deprecated-action-runtime`)
against actions/download-artifact@v4. The fix PR, #1128, bumped it to @v6
on the belief that v6 ran on Node.js 24. It did not: v6's action.yml still
says node20, and v7 is the first node24 tag. The review caught it. Nothing
in the gate suite could have, because no gate read an action's runtime.

THE RULE
--------
Every external action a step `uses:` in .github/workflows/*.yml or
.github/actions/**/action.yml (local `./` actions, `docker://` images and
reusable-workflow calls are not action pins) is looked up in
.github/scripts/action-runtime-pins.json, the committed record of what
`runs.using` that action's own action.yml declares at that ref:

  * a pin with no row fails: read its action.yml and add the row;
  * a pin whose runtime is deprecated (node12, node16, node20) fails unless
    .github/scripts/action-runtime-waivers.json waives it, with the open
    issue that tracks the bump (Gate 124 checks the citation);
  * a row or a waiver for a pin nothing uses fails as stale, and so does a
    waiver for a pin whose runtime is not deprecated;
  * a runtime outside the known set fails, so a typo cannot read as clean.

THE SECOND RULE: NO ACTIONS CACHE
---------------------------------
No workflow or composite in this repository restores or saves an Actions
cache (owner decision, 2026-11-27). Over the same external steps:

  * a step that uses actions/cache, or its restore or save sub-action,
    fails;
  * a setup action (an action named setup-*) fails unless SETUP_CACHE_INPUTS
    names it. A row names the input that turns its cache off, or None for
    a setup action that keeps no Actions cache;
  * a step whose setup action has such an input fails unless the step sets
    that input to false. A missing input counts as caching on, because
    astral-sh/setup-uv's enable-cache defaults to auto, which restores and
    saves one; so does an expression, which this gate cannot evaluate.

WHY A COMMITTED TABLE, NOT A LIVE READ
--------------------------------------
The PR-time lint job runs offline, and a gate whose answer depends on the
network is a gate that flakes. The table makes the claim reviewable in the
diff: a bump has to change a row, and the row says what the bump buys.
`--check-remote` re-reads every row from GitHub with `gh api` and fails on
a wrong one; run it when you add or change a row.

Usage:
    python3 .github/scripts/verify-action-runtime-pins.py
    python3 .github/scripts/verify-action-runtime-pins.py --self-test
    python3 .github/scripts/verify-action-runtime-pins.py --check-remote
"""
import argparse
import base64
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

PINS_PATH = ".github/scripts/action-runtime-pins.json"
WAIVERS_PATH = ".github/scripts/action-runtime-waivers.json"
DEPRECATED = ("node12", "node16", "node20")
KNOWN = DEPRECATED + ("node24", "composite", "docker")
# The second rule (see the docstring). owner/repo of each setup action this
# repository may use -> the input that turns its Actions cache off, or None
# when the action keeps no Actions cache at all.
CACHE_ACTION = "actions/cache"
SETUP_CACHE_INPUTS = {"astral-sh/setup-uv": "enable-cache"}


def cache_problem(uses, with_):
    """-> why this step restores or saves an Actions cache, or None."""
    path = uses.split("@", 1)[0].strip()
    owner_repo = "/".join(path.split("/")[:2])
    if owner_repo == CACHE_ACTION:
        return "restores or saves an Actions cache"
    if owner_repo in SETUP_CACHE_INPUTS:
        key = SETUP_CACHE_INPUTS[owner_repo]
    elif path.split("/")[1].startswith("setup-"):
        return ("is a setup action with no row in SETUP_CACHE_INPUTS; read "
                "how it caches and add the input that turns caching off")
    else:
        return None
    if key is None:
        return None
    value = with_.get(key) if isinstance(with_, dict) else None
    if value is False or (isinstance(value, str)
                          and value.strip().lower() == "false"):
        return None
    return ("leaves {0} at {1}, so it restores and saves an Actions cache; "
            "set {0}: false".format(
                key, "its default" if value is None else repr(value)))


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def is_action_pin(uses):
    """True for owner/repo[/path]@ref; False for a local action, a docker
    image or a reusable-workflow call."""
    if not isinstance(uses, str) or "@" not in uses:
        return False
    if uses.startswith(("./", "docker://")):
        return False
    if "/.github/workflows/" in uses:
        return False
    return uses.split("@", 1)[0].count("/") >= 1


def _steps_of(doc, is_composite):
    if not isinstance(doc, dict):
        return []
    if is_composite:
        runs = doc.get("runs")
        steps = runs.get("steps") if isinstance(runs, dict) else None
        return [("runs", s) for s in steps or [] if isinstance(s, dict)]
    out = []
    jobs = doc.get("jobs")
    for name, job in (jobs or {}).items() if isinstance(jobs, dict) else ():
        if isinstance(job, dict):
            for s in job.get("steps") or []:
                if isinstance(s, dict):
                    out.append((name, s))
    return out


def discover(root="."):
    """-> ({pin: [file:job, ...]}, failures)."""
    found, failures = {}, []
    files = [(p, False) for p in sorted(
        glob.glob(os.path.join(root, ".github", "workflows", "*.yml"))
        + glob.glob(os.path.join(root, ".github", "workflows", "*.yaml")))]
    # Recursive: composites shared between composites live one level
    # deeper, under .github/actions/_shared/ (CLAUDE.md).
    files += [(p, True) for p in sorted(
        glob.glob(os.path.join(root, ".github", "actions", "**", "action.yml"),
                  recursive=True)
        + glob.glob(os.path.join(root, ".github", "actions", "**",
                                 "action.yaml"), recursive=True))]
    for path, is_composite in files:
        rel = _rel(root, path)
        try:
            with io.open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as e:
            failures.append("{0}: cannot parse ({1}); its pins would go "
                            "unchecked.".format(rel, e))
            continue
        for job, step in _steps_of(doc, is_composite):
            uses = step.get("uses")
            if is_action_pin(uses):
                found.setdefault(uses.strip(), []).append(
                    "{0}:{1}".format(rel, job))
                why = cache_problem(uses, step.get("with"))
                if why:
                    failures.append(
                        "{0} (used at {1}:{2}) {3}. No workflow or "
                        "composite here keeps an Actions cache.".format(
                            uses.strip(), rel, job, why))
    return found, failures


def _load(root, rel, key, kind):
    path = os.path.join(root, rel)
    try:
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        return None, ["{0} is missing.".format(rel)]
    except ValueError as e:
        return None, ["{0} does not parse ({1}).".format(rel, e)]
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, kind):
        return None, ["{0} must contain a \"{1}\" {2}.".format(
            rel, key, "object" if kind is dict else "list")]
    return value, []


def evaluate(found, pins, waivers):
    failures = []
    waived = {}
    for i, w in enumerate(waivers):
        if not isinstance(w, dict):
            failures.append("{0}: waiver #{1} is not an object.".format(
                WAIVERS_PATH, i))
            continue
        missing = [k for k in ("uses", "issue", "reason") if not w.get(k)]
        if missing:
            failures.append("{0}: waiver #{1} lacks {2}.".format(
                WAIVERS_PATH, i, ", ".join(missing)))
            continue
        if w["uses"] in waived:
            failures.append("{0}: {1} is waived twice.".format(
                WAIVERS_PATH, w["uses"]))
        waived[w["uses"]] = w

    for pin, runtime in sorted(pins.items()):
        if runtime not in KNOWN:
            failures.append(
                "{0}: {1} has runtime {2!r}, not one of {3}.".format(
                    PINS_PATH, pin, runtime, ", ".join(KNOWN)))
        if pin not in found:
            failures.append(
                "{0}: {1} is not used by any workflow or composite action; "
                "remove the stale row.".format(PINS_PATH, pin))

    for pin, sites in sorted(found.items()):
        sites = sorted(set(sites))
        runtime = pins.get(pin)
        if runtime is None:
            failures.append(
                "{0} (used at {1}) has no row in {2}. Read runs.using from "
                "the action's own action.yml at that ref and add it.".format(
                    pin, ", ".join(sites), PINS_PATH))
        elif runtime in DEPRECATED and pin not in waived:
            failures.append(
                "{0} (used at {1}) targets {2}, a deprecated runtime: the "
                "runner forces it onto Node.js 24 and annotates the run "
                "(#1127). Bump it to a release that declares node24, or "
                "waive it in {3} with the issue tracking the bump.".format(
                    pin, ", ".join(sites), runtime, WAIVERS_PATH))

    for pin in sorted(waived):
        if pin not in found:
            failures.append(
                "{0}: the waiver for {1} matches no pin in use; remove "
                "it.".format(WAIVERS_PATH, pin))
        elif pins.get(pin) not in DEPRECATED:
            failures.append(
                "{0}: the waiver for {1} is stale; its runtime is {2!r}, "
                "not deprecated.".format(WAIVERS_PATH, pin, pins.get(pin)))
    return failures


def run(root="."):
    found, failures = discover(root)
    pins, f1 = _load(root, PINS_PATH, "pins", dict)
    waivers, f2 = _load(root, WAIVERS_PATH, "waivers", list)
    failures += f1 + f2
    if pins is None or waivers is None:
        return found, failures
    return found, failures + evaluate(found, pins, waivers)


def remote_runtime(pin):
    """runs.using of the action at that ref, read with gh api."""
    target, ref = pin.split("@", 1)
    parts = target.split("/")
    repo, sub = "/".join(parts[:2]), "/".join(parts[2:])
    for name in ("action.yml", "action.yaml"):
        path = (sub + "/" + name) if sub else name
        proc = subprocess.run(
            ["gh", "api", "repos/{0}/contents/{1}?ref={2}".format(
                repo, path, ref), "--jq", ".content"],
            capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            text = base64.b64decode(proc.stdout.strip()).decode("utf-8")
            runs = (yaml.safe_load(text) or {}).get("runs") or {}
            return str(runs.get("using", "")).strip()
    return None


def check_remote(root="."):
    pins, failures = _load(root, PINS_PATH, "pins", dict)
    if pins is None:
        return failures
    for pin, runtime in sorted(pins.items()):
        actual = remote_runtime(pin)
        if actual is None:
            failures.append("{0}: could not read its action.yml.".format(pin))
        elif actual != runtime:
            failures.append("{0}: {1} says {2!r}; the action declares "
                            "{3!r}.".format(pin, PINS_PATH, runtime, actual))
        else:
            print("ok  {0}: {1}".format(pin, actual))
    return failures


# --------------------------------------------------------------- self-test

WORKFLOW = """name: stage
on: workflow_call
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
{steps}
  reuse:
    uses: owner/repo/.github/workflows/x.yml@v1
"""
COMPOSITE = """name: c
runs:
  using: composite
  steps:
    - uses: {pin}
"""


def _tree(steps, pins, waivers, composite_pin=None, composite_dir="c"):
    tmp = tempfile.mkdtemp(prefix="wc-action-runtime-")
    os.makedirs(os.path.join(tmp, ".github", "workflows"))
    os.makedirs(os.path.join(tmp, ".github", "scripts"))
    body = "\n".join("      - uses: " + s for s in steps)
    with io.open(os.path.join(tmp, ".github", "workflows", "stage.yml"),
                 "w", encoding="utf-8") as fh:
        fh.write(WORKFLOW.format(steps=body))
    if composite_pin:
        d = os.path.join(tmp, ".github", "actions", *composite_dir.split("/"))
        os.makedirs(d)
        with io.open(os.path.join(d, "action.yml"), "w",
                     encoding="utf-8") as fh:
            fh.write(COMPOSITE.format(pin=composite_pin))
    for rel, data in ((PINS_PATH, pins), (WAIVERS_PATH, waivers)):
        if data is None:
            continue
        with io.open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
    return tmp


def self_test():
    results = []

    def case(label, steps, pins, waivers, expect, composite_pin=None,
             composite_dir="c"):
        tmp = _tree(steps, {"pins": pins} if isinstance(pins, dict) else pins,
                    {"waivers": waivers} if isinstance(waivers, list)
                    else waivers, composite_pin, composite_dir)
        try:
            _, failures = run(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        text = "\n".join(failures)
        if expect is None:
            ok = not failures
        else:
            ok = bool(failures) and all(e in text for e in expect)
        results.append(ok)
        print("[{0}] {1}{2}".format("ok" if ok else "FAIL", label,
                                    "" if ok else " -- got: " + repr(text)))

    good = {"actions/checkout@v5": "node24",
            "actions/download-artifact@v7": "node24"}
    case("node24 pins with rows pass; local, docker and reusable-workflow "
         "uses are not pins",
         ["actions/checkout@v5", "actions/download-artifact@v7",
          "./.github/actions/x", "docker://alpine:3"], good, [], None)
    case("#1127's regression: download-artifact@v6 declares node20 and "
         "fails unwaived",
         ["actions/checkout@v5", "actions/download-artifact@v6"],
         {"actions/checkout@v5": "node24",
          "actions/download-artifact@v6": "node20"}, [],
         ["actions/download-artifact@v6", "targets node20"])
    case("a deprecated pin inside a composite action is found too",
         ["actions/checkout@v5"],
         {"actions/checkout@v5": "node24",
          "actions/download-artifact@v4": "node20"}, [],
         ["actions/download-artifact@v4", ".github/actions/c/action.yml"],
         composite_pin="actions/download-artifact@v4")
    case("a deprecated pin in a composite under .github/actions/_shared/ "
         "is found too",
         ["actions/checkout@v5"],
         {"actions/checkout@v5": "node24",
          "actions/download-artifact@v4": "node20"}, [],
         ["actions/download-artifact@v4",
          ".github/actions/_shared/c/action.yml"],
         composite_pin="actions/download-artifact@v4",
         composite_dir="_shared/c")
    case("a waived deprecated pin passes",
         ["actions/checkout@v4"], {"actions/checkout@v4": "node20"},
         [{"uses": "actions/checkout@v4", "issue": "#889", "reason": "r"}],
         None)
    case("a pin with no row fails",
         ["actions/checkout@v5", "docker/login-action@v3"], good,
         [], ["docker/login-action@v3", "has no row"])
    case("a row nothing uses fails as stale",
         ["actions/checkout@v5"], good, [],
         ["actions/download-artifact@v7", "remove the stale row"])
    case("a waiver for an unused pin fails",
         ["actions/checkout@v5", "actions/download-artifact@v7"], good,
         [{"uses": "actions/checkout@v4", "issue": "#889", "reason": "r"}],
         ["waiver for actions/checkout@v4 matches no pin"])
    case("a waiver for a node24 pin fails as stale",
         ["actions/checkout@v5", "actions/download-artifact@v7"], good,
         [{"uses": "actions/checkout@v5", "issue": "#889", "reason": "r"}],
         ["waiver for actions/checkout@v5 is stale"])
    case("a waiver without an issue fails",
         ["actions/checkout@v4"], {"actions/checkout@v4": "node20"},
         [{"uses": "actions/checkout@v4", "reason": "r"}],
         ["lacks issue"])
    case("an unknown runtime string fails",
         ["actions/checkout@v5"], {"actions/checkout@v5": "node 24"}, [],
         ["runtime 'node 24'"])
    case("a missing table fails loudly",
         ["actions/checkout@v5"], None, [], [PINS_PATH + " is missing"])
    case("an unparseable waivers file fails loudly",
         ["actions/checkout@v5"], {"actions/checkout@v5": "node24"},
         "{not json", [WAIVERS_PATH + " does not parse"])

    # The second rule: no Actions cache.
    uv = "astral-sh/setup-uv@v10.0.0"
    uv_pins = {"actions/checkout@v5": "node24", uv: "node24"}

    def uv_with(value):
        return uv + "\n        with:\n          enable-cache: " + value

    case("setup-uv with enable-cache: false passes",
         ["actions/checkout@v5", uv_with("false")], uv_pins, [], None)
    case("setup-uv with enable-cache: 'false' (a string) passes",
         ["actions/checkout@v5", uv_with("'false'")], uv_pins, [], None)
    case("setup-uv with no enable-cache fails: its default, auto, caches",
         ["actions/checkout@v5", uv], uv_pins, [],
         [uv, "enable-cache at its default"])
    case("setup-uv with enable-cache: true fails",
         ["actions/checkout@v5", uv_with("true")], uv_pins, [],
         ["enable-cache at True"])
    case("setup-uv with enable-cache from an expression fails",
         ["actions/checkout@v5", uv_with("${{ inputs.cache }}")], uv_pins,
         [], ["enable-cache at '${{ inputs.cache }}'"])
    case("actions/cache fails",
         ["actions/checkout@v5", "actions/cache@v4"],
         {"actions/checkout@v5": "node24", "actions/cache@v4": "node24"}, [],
         ["actions/cache@v4", "restores or saves an Actions cache"])
    case("actions/cache/restore inside a composite fails",
         ["actions/checkout@v5"],
         {"actions/checkout@v5": "node24",
          "actions/cache/restore@v4": "node24"}, [],
         ["actions/cache/restore@v4", ".github/actions/c/action.yml",
          "restores or saves an Actions cache"],
         composite_pin="actions/cache/restore@v4")
    case("a setup action with no row in SETUP_CACHE_INPUTS fails",
         ["actions/checkout@v5", "actions/setup-go@v5"],
         {"actions/checkout@v5": "node24", "actions/setup-go@v5": "node24"},
         [], ["actions/setup-go@v5", "no row in SETUP_CACHE_INPUTS"])

    passed = sum(results)
    print("verify-action-runtime-pins self-test: {0}/{1} passed".format(
        passed, len(results)))
    return passed == len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check-remote", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    if args.self_test:
        return 0 if self_test() else 1
    if args.check_remote:
        failures = check_remote(args.root)
    else:
        found, failures = run(args.root)
        if not failures:
            print("Gate 170: {0} external action pin(s), each with a "
                  "recorded runtime, none deprecated unwaived, and none "
                  "keeping an Actions cache.".format(
                      len(found)))
    for f in failures:
        print("::error::Gate 170: " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
