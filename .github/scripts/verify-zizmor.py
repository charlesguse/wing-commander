#!/usr/bin/env python3
"""Gate - the pinned zizmor static analyser finds nothing unaccepted.

specs/132-workflow-trigger-security, contracts/zizmor-gate.md.

WHY THIS EXISTS
---------------
Every other gate here checks one named shape. None of them reads a workflow
the way an attacker does: an `${{ github.event.* }}` expanded inside a
`run:` script, a `pull_request_target` trigger, a persisted checkout
credential. zizmor does. This gate runs a version-pinned zizmor offline
over every workflow and composite action and fails on any finding that
`.github/scripts/zizmor-findings-waivers.json` does not record.

THE RULE
--------
1. `zizmor --version` equals the pin in .github/scripts/zizmor-pin.txt.
2. The file set is found by glob (workflows and composites, nested ones
   under `_shared/` included); an empty set fails, so a moved directory
   cannot turn the gate into a pass.
3. `zizmor --offline --format json --config .github/zizmor.yml <paths>`
   must print parsable JSON.
4. Each finding maps to (file, audit, location); a finding with no record
   fails, naming `file:line audit`. A record matching no finding is stale
   and fails; two records with one key fail.
5. `.github/zizmor.yml` must carry a non-empty `reason` for the disabled
   `self-repository` audit, and its `unpinned-uses` policy is the single
   home of the trusted-publisher list: a second copy of that list under
   .github/ fails.

Usage:
    python3 .github/scripts/verify-zizmor.py [--root DIR]
    python3 .github/scripts/verify-zizmor.py --self-test
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

PIN_PATH = ".github/scripts/zizmor-pin.txt"
CONFIG_PATH = ".github/zizmor.yml"
REGISTER_PATH = ".github/scripts/zizmor-findings-waivers.json"
TRUSTED_PATTERNS = ("actions/*", "github/*", "anthropics/*")
LOCATION_RE = re.compile(r"^(workflow|job:[^/]+(/step:.+)?)$")
REQUIRED_FIELDS = ("file", "audit", "location", "reason", "control", "issue")
# The only home of the trusted-publisher policy is CONFIG_PATH; these are
# the places a second copy would plausibly appear.
HOME_SCAN_GLOBS = (".github/**/*.yml", ".github/**/*.yaml", ".github/**/*.json",
                   ".github/**/*.txt")


def _read(root, rel):
    with io.open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def discover(root):
    files = sorted(
        glob.glob(os.path.join(root, ".github", "workflows", "*.yml"))
        + glob.glob(os.path.join(root, ".github", "workflows", "*.yaml"))
        + glob.glob(os.path.join(root, ".github", "actions", "**", "action.yml"),
                    recursive=True)
        + glob.glob(os.path.join(root, ".github", "actions", "**", "action.yaml"),
                    recursive=True))
    return [os.path.relpath(p, root).replace(os.sep, "/") for p in files]


def read_pin(root):
    try:
        text = _read(root, PIN_PATH)
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("version="):
            return line.split("=", 1)[1].strip() or None
    return None


def run_zizmor(root, files):
    """-> (version_text, json_text); version_text None when not installed."""
    try:
        v = subprocess.run(["zizmor", "--version"], capture_output=True,
                           text=True, cwd=root, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    ver = (v.stdout or "").strip()
    cfg = os.path.join(root, CONFIG_PATH)
    p = subprocess.run(
        ["zizmor", "--offline", "--format", "json", "--config", cfg] + files,
        capture_output=True, text=True, cwd=root, timeout=600)
    # zizmor exits non-zero when it has findings; the JSON is what counts.
    return ver, p.stdout


def _step_label(step, index):
    if isinstance(step, dict):
        if step.get("id"):
            return str(step["id"])
        if step.get("name"):
            return str(step["name"])
    return "#{0}".format(index)


def location_of(finding, doc):
    """Stable location for a finding: workflow, job:<id> or
    job:<id>/step:<id-or-name>; never a line."""
    locs = finding.get("locations") or []
    route = []
    for loc in locs:
        sym = loc.get("symbolic") or {}
        if sym.get("kind") in (None, "Primary") or not route:
            r = ((sym.get("route") or {}).get("route")) or []
            if r:
                route = r
                if sym.get("kind") == "Primary":
                    break
    keys = [c.get("Key") if "Key" in c else c.get("Index")
            for c in route if isinstance(c, dict)]
    job = step = None
    if len(keys) >= 2 and keys[0] == "jobs" and isinstance(keys[1], str):
        job = keys[1]
    elif len(keys) >= 3 and keys[0] == "runs" and keys[1] == "steps":
        job = None
    if job and len(keys) >= 4 and keys[2] == "steps" and isinstance(keys[3], int):
        steps = ((doc or {}).get("jobs") or {}).get(job, {}).get("steps") or []
        idx = keys[3]
        step = _step_label(steps[idx] if idx < len(steps) else None, idx)
    if job and step:
        return "job:{0}/step:{1}".format(job, step)
    if job:
        return "job:{0}".format(job)
    return "workflow"


def _finding_file(finding):
    for loc in finding.get("locations") or []:
        key = ((loc.get("symbolic") or {}).get("key") or {}).get("Local") or {}
        if key.get("given_path"):
            return str(key["given_path"]).replace(os.sep, "/")
    return None


def _finding_line(finding):
    for loc in finding.get("locations") or []:
        pt = (((loc.get("concrete") or {}).get("location") or {})
              .get("start_point") or {})
        if "row" in pt:
            return int(pt["row"]) + 1
    return 0


def map_findings(root, payload):
    """-> [(file, audit, location, line)]. Ignored findings are skipped."""
    out, docs = [], {}
    for f in payload:
        if not isinstance(f, dict) or f.get("ignored"):
            continue
        rel = _finding_file(f)
        if rel is None:
            rel = "<unknown>"
        if rel not in docs:
            try:
                docs[rel] = yaml.safe_load(_read(root, rel))
            except (OSError, yaml.YAMLError):
                docs[rel] = None
        out.append((rel, str(f.get("ident", "")), location_of(f, docs[rel]),
                    _finding_line(f)))
    return out


def load_register(root):
    """-> (entries, failures)."""
    try:
        data = json.loads(_read(root, REGISTER_PATH))
    except OSError:
        return [], ["{0}: cannot read the findings register.".format(REGISTER_PATH)]
    except ValueError as e:
        return [], ["{0}: not valid JSON ({1}).".format(REGISTER_PATH, e)]
    # `waivers` is the key gate 124 (verify-waiver-citations.py) reads in
    # every *-waivers.json register.
    if not isinstance(data, dict) or not isinstance(data.get("waivers"), list):
        return [], ["{0}: must be an object with a `waivers` array."
                    .format(REGISTER_PATH)]
    failures, entries = [], []
    for i, e in enumerate(data["waivers"]):
        where = "{0} waivers[{1}]".format(REGISTER_PATH, i)
        if not isinstance(e, dict):
            failures.append("{0}: not an object.".format(where))
            continue
        for k in REQUIRED_FIELDS:
            if k not in e:
                failures.append("{0}: missing `{1}`.".format(where, k))
        for k in ("reason", "control", "file", "audit"):
            if k in e and not (isinstance(e[k], str) and e[k].strip()):
                failures.append("{0}: `{1}` must be a non-empty string."
                                .format(where, k))
        loc = e.get("location")
        if isinstance(loc, str) and not LOCATION_RE.match(loc):
            failures.append("{0}: location `{1}` must be `workflow`, "
                            "`job:<id>` or `job:<id>/step:<id-or-name>`."
                            .format(where, loc))
        iss = e.get("issue")
        if iss is None:
            if not (e.get("permanent") is True
                    and str(e.get("permanent_reason", "")).strip()):
                failures.append("{0}: `issue` null needs `permanent: true` "
                                "and a `permanent_reason`.".format(where))
        elif not (isinstance(iss, str) and re.match(r"^#[0-9]+$", iss)):
            failures.append("{0}: `issue` must be \"#N\" or null.".format(where))
        if isinstance(e.get("file"), str) and not os.path.exists(
                os.path.join(root, e["file"])):
            failures.append("{0}: file `{1}` does not exist.".format(where, e["file"]))
        entries.append(e)
    return entries, failures


def check_config(root):
    failures = []
    try:
        cfg = yaml.safe_load(_read(root, CONFIG_PATH)) or {}
    except OSError:
        return ["{0}: missing.".format(CONFIG_PATH)]
    except yaml.YAMLError as e:
        return ["{0}: not valid YAML ({1}).".format(CONFIG_PATH, e)]
    sr = ((cfg.get("rules") or {}).get("self-repository")) or {}
    if sr.get("disable") is True and not (
            isinstance(sr.get("reason"), str) and sr["reason"].strip()):
        failures.append("{0}: the disabled `self-repository` audit needs a "
                        "non-empty `reason`.".format(CONFIG_PATH))
    if "self-repository" not in ((cfg.get("rules") or {})):
        failures.append("{0}: `rules.self-repository` is missing; its "
                        "disable and reason are the record of why that audit "
                        "is off.".format(CONFIG_PATH))
    pol = ((((cfg.get("rules") or {}).get("unpinned-uses")) or {})
           .get("config") or {}).get("policies")
    if not isinstance(pol, dict):
        failures.append("{0}: `rules.unpinned-uses.config.policies` is "
                        "missing.".format(CONFIG_PATH))
    else:
        for pat in TRUSTED_PATTERNS:
            if pol.get(pat) != "ref-pin":
                failures.append("{0}: policy `{1}` must be `ref-pin` (trusted "
                                "publisher).".format(CONFIG_PATH, pat))
        if pol.get("*") != "hash-pin":
            failures.append("{0}: policy `*` must be `hash-pin`.".format(CONFIG_PATH))
    return failures


def check_single_home(root):
    """A second copy of the trusted-publisher list under .github/ fails."""
    failures = []
    needle = re.compile(r"""["']?actions/\*["']?\s*:\s*["']?ref-pin""")
    for g in HOME_SCAN_GLOBS:
        for p in glob.glob(os.path.join(root, g), recursive=True):
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if rel == CONFIG_PATH or "/fixtures/" in rel:
                continue
            try:
                text = _read(root, rel)
            except OSError:
                continue
            if needle.search(text):
                failures.append("{0}: a second copy of the trusted-publisher "
                                "list; its one home is {1}.".format(rel, CONFIG_PATH))
    return failures


def evaluate(root, runner=run_zizmor):
    failures = []
    pin = read_pin(root)
    if pin is None:
        failures.append("{0}: no `version=` line; the analyser version is "
                        "unpinned.".format(PIN_PATH))
    files = discover(root)
    if not files:
        failures.append("no workflow or composite action files were found "
                        "under .github/; refusing to pass on an empty set.")
    failures += check_config(root)
    failures += check_single_home(root)
    entries, reg_failures = load_register(root)
    failures += reg_failures
    if files and pin is not None:
        ver, out = runner(root, files)
        if ver is None:
            failures.append("analyser missing or wrong version: zizmor is not "
                            "installed (need {0}).".format(pin))
        elif ver.split()[-1:] != [pin]:
            failures.append("analyser missing or wrong version: found `{0}`, "
                            "need {1}.".format(ver, pin))
        else:
            try:
                payload = json.loads(out)
                if not isinstance(payload, list):
                    raise ValueError("top level is not an array")
            except ValueError as e:
                failures.append("zizmor output is not parsable JSON ({0}); "
                                "refusing to read it as clean.".format(e))
                payload = None
            if payload is not None:
                findings = map_findings(root, payload)
                keys, seen = {}, set()
                for e in entries:
                    k = (e.get("file"), e.get("audit"), e.get("location"))
                    if k in keys:
                        failures.append("duplicate record for {0} {1} {2}."
                                        .format(*k))
                    keys[k] = e
                for f, audit, loc, line in findings:
                    k = (f, audit, loc)
                    if k in keys:
                        seen.add(k)
                    else:
                        failures.append("{0}:{1} {2} ({3}): unwaived finding."
                                        .format(f, line, audit, loc))
                for k in keys:
                    if k not in seen:
                        failures.append("stale record: {0} {1} {2} matches no "
                                        "current finding.".format(*k))
    return failures


# ---------------------------------------------------------------- self-test

def _finding(file, audit, route, row=3):
    return {"ident": audit, "ignored": False, "locations": [{
        "symbolic": {"kind": "Primary", "key": {"Local": {"given_path": file}},
                     "route": {"route": route}},
        "concrete": {"location": {"start_point": {"row": row, "column": 0}}}}]}


STEP_ROUTE = [{"Key": "jobs"}, {"Key": "j"}, {"Key": "steps"}, {"Index": 0}]
WF = ("on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
      "      - id: s\n        run: echo hi\n")
CFG = ("rules:\n  self-repository:\n    disable: true\n    reason: because\n"
       "  unpinned-uses:\n    config:\n      policies:\n"
       "        \"actions/*\": ref-pin\n        \"github/*\": ref-pin\n"
       "        \"anthropics/*\": ref-pin\n        \"*\": hash-pin\n")


def _tree(files):
    d = tempfile.mkdtemp(prefix="zizmor-selftest-")
    base = {".github/workflows/a.yml": WF, CONFIG_PATH: CFG,
            PIN_PATH: "version=1.33.1\n",
            REGISTER_PATH: json.dumps({"waivers": []})}
    base.update(files)
    for rel, text in base.items():
        if text is None:
            continue
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
    return d


def _runner(version="1.33.1", payload=None, raw=None):
    def run(root, files):
        if version is None:
            return None, ""
        return version, raw if raw is not None else json.dumps(payload or [])
    return run


def _entry(**kw):
    e = {"file": ".github/workflows/a.yml", "audit": "template-injection",
         "location": "job:j/step:s", "reason": "r", "control": "c",
         "issue": "#1"}
    e.update(kw)
    return e


def self_test():
    inj = [_finding(".github/workflows/a.yml", "template-injection", STEP_ROUTE)]
    cases = [
        ("clean", {}, _runner(payload=[]), None),
        ("unwaived finding", {}, _runner(payload=inj), "unwaived finding"),
        ("waived finding passes",
         {REGISTER_PATH: json.dumps({"waivers": [_entry()]})},
         _runner(payload=inj), None),
        ("stale record",
         {REGISTER_PATH: json.dumps({"waivers": [_entry()]})},
         _runner(payload=[]), "stale record"),
        ("duplicate record",
         {REGISTER_PATH: json.dumps({"waivers": [_entry(), _entry()]})},
         _runner(payload=inj), "duplicate record"),
        ("analyser missing", {}, _runner(version=None), "analyser missing"),
        ("wrong version", {}, _runner(version="zizmor 1.0.0"), "wrong version"),
        ("empty file set", {".github/workflows/a.yml": None},
         _runner(payload=[]), "empty set"),
        ("unparsable output", {}, _runner(raw="not json"), "not parsable"),
        ("self-repository reason removed",
         {CONFIG_PATH: CFG.replace("    reason: because\n", "")},
         _runner(payload=[]), "non-empty `reason`"),
        ("trusted list second copy",
         {".github/scripts/other.json": "{\"actions/*\": \"ref-pin\"}"},
         _runner(payload=[]), "second copy"),
        ("policy differing from home",
         {CONFIG_PATH: CFG.replace('"*": hash-pin', '"*": ref-pin')},
         _runner(payload=[]), "must be `hash-pin`"),
        ("record without control",
         {REGISTER_PATH: json.dumps({"waivers": [
             {k: v for k, v in _entry().items() if k != "control"}]})},
         _runner(payload=inj), "missing `control`"),
    ]
    bad = 0
    for name, files, runner, want in cases:
        d = _tree(files)
        try:
            got = evaluate(d, runner)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        ok = (not got) if want is None else any(want in g for g in got)
        if not ok:
            bad += 1
            print("SELF-TEST FAIL: {0}: wanted {1!r}, got {2}".format(
                name, want, got))
    if bad:
        return 1
    print("verify-zizmor self-test: {0} cases ok.".format(len(cases)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    failures = evaluate(args.root)
    for f in failures:
        print("::error::verify-zizmor: {0}".format(f))
    if failures:
        return 1
    print("verify-zizmor: no unwaived findings, no stale records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
