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
# The owner-approved publisher names (spec 132 Q1). The patterns themselves
# live only in CONFIG_PATH; this is the closed set of names a policy key may
# use, so adding a publisher there is an owner decision this gate refuses.
APPROVED_PUBLISHERS = frozenset(("actions", "github", "anthropics"))
IGNORE_COMMENT_RE = re.compile(r"#\s*zizmor\s*:\s*ignore", re.IGNORECASE)
LOCATION_RE = re.compile(r"^(workflow|step:.+|job:[^/]+(/step:.+)?)$")
REQUIRED_FIELDS = ("file", "audit", "location", "reason", "control", "issue")
# The only home of the trusted-publisher policy is CONFIG_PATH; these are
# the places a second copy would plausibly appear.
HOME_SCAN_GLOBS = (".github/**/*.yml", ".github/**/*.yaml", ".github/**/*.json",
                   ".github/**/*.txt", ".github/scripts/*.py")


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
    try:
        p = subprocess.run(
            ["zizmor", "--offline", "--format", "json", "--config", cfg] + files,
            capture_output=True, text=True, cwd=root, timeout=600)
    except (OSError, subprocess.SubprocessError):
        # A timeout or a vanished binary mid-scan is the same failure as a
        # missing analyser, not a traceback.
        return None, ""
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
    """Stable location for a finding: workflow, job:<id>,
    job:<id>/step:<id-or-name>, or step:<id-or-name> inside a composite
    action; never a line."""
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
    elif len(keys) >= 3 and keys[0] == "runs" and keys[1] == "steps" \
            and isinstance(keys[2], int):
        # A composite action: its steps live under runs.steps.
        steps = ((doc or {}).get("runs") or {}).get("steps") or []
        idx = keys[2]
        return "step:{0}".format(_step_label(
            steps[idx] if idx < len(steps) else None, idx))
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
    # zizmor 1.33.1 names the input path `verbatim_path`; older releases
    # used `given_path`.
    for loc in finding.get("locations") or []:
        key = ((loc.get("symbolic") or {}).get("key") or {}).get("Local") or {}
        for field in ("verbatim_path", "given_path"):
            if key.get(field):
                path = str(key[field]).replace(os.sep, "/")
                return path[2:] if path.startswith("./") else path
    return None


def _primary_first(finding):
    """Locations with the Primary one first: zizmor lists Hidden and
    Related context locations too, and the line a finding names is its
    Primary location's."""
    locs = list(finding.get("locations") or [])
    return sorted(locs, key=lambda l: (
        (l.get("symbolic") or {}).get("kind") != "Primary"))


def _finding_line(finding):
    for loc in _primary_first(finding):
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


def self_repository_reason(text):
    """-> the non-empty reason recorded for the disabled self-repository
    audit, or None."""
    lines = text.splitlines()
    in_block = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*self-repository:\s*$", line):
            in_block, indent = True, len(line) - len(line.lstrip())
            continue
        if not in_block:
            continue
        if line.strip() and not line.lstrip().startswith("#") and (
                len(line) - len(line.lstrip())) <= indent:
            return None
        if re.match(r"^\s*disable:\s*true\s*$", line):
            m = re.match(r"^\s*#\s*reason:\s*(.*?)\s*$", lines[i - 1]) if i else None
            return m.group(1) if m and m.group(1) else None
    return None


def check_config(root):
    failures = []
    try:
        cfg = yaml.safe_load(_read(root, CONFIG_PATH)) or {}
    except OSError:
        return ["{0}: missing.".format(CONFIG_PATH)]
    except yaml.YAMLError as e:
        return ["{0}: not valid YAML ({1}).".format(CONFIG_PATH, e)]
    sr = ((cfg.get("rules") or {}).get("self-repository")) or {}
    # zizmor rejects unknown keys in its config, so the reason lives in a
    # `# reason: <text>` comment on the line directly above `disable: true`
    # inside the `self-repository:` block (research D5).
    if sr.get("disable") is True and not self_repository_reason(
            _read(root, CONFIG_PATH)):
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
        # The trusted list is read from its one home; each key must be an
        # approved publisher's `<name>/*` or the `*` catch-all.
        trusted = set()
        for pat, mode in pol.items():
            m = re.match(r"^([^/*]+)/\*$", str(pat))
            if str(pat) == "*":
                continue
            if not m or m.group(1) not in APPROVED_PUBLISHERS:
                failures.append("{0}: policy key `{1}` is outside the "
                                "owner-approved trusted publishers."
                                .format(CONFIG_PATH, pat))
            elif mode != "ref-pin":
                failures.append("{0}: policy `{1}` must be `ref-pin` (trusted "
                                "publisher).".format(CONFIG_PATH, pat))
            else:
                trusted.add(m.group(1))
        for name in sorted(APPROVED_PUBLISHERS - trusted):
            failures.append("{0}: trusted publisher `{1}/*` is missing from "
                            "the policies.".format(CONFIG_PATH, name))
        if pol.get("*") != "hash-pin":
            failures.append("{0}: policy `*` must be `hash-pin`.".format(CONFIG_PATH))
    for name, rule in sorted(((cfg.get("rules") or {}).items())):
        if name != "self-repository" and isinstance(rule, dict) \
                and rule.get("disable"):
            failures.append("{0}: audit `{1}` is disabled; only "
                            "`self-repository` may be.".format(CONFIG_PATH, name))
    return failures


def check_inline_ignores(root, files):
    """A `# zizmor: ignore` comment would hide a finding from the register."""
    failures = []
    for rel in files:
        try:
            text = _read(root, rel)
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if IGNORE_COMMENT_RE.search(line):
                failures.append("{0}:{1}: inline `zizmor: ignore` comment; "
                                "record the finding in {2} instead."
                                .format(rel, n, REGISTER_PATH))
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


DEPENDABOT_PATH = ".github/dependabot.yml"


def _dir_glob_re(pattern):
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def check_dependabot_coverage(root):
    """Every composite action directory must match a Dependabot
    `directories` glob, or its SHA pins are never bumped."""
    try:
        cfg = yaml.safe_load(_read(root, DEPENDABOT_PATH)) or {}
    except OSError:
        return ["{0}: missing; the SHA pins are never bumped.".format(DEPENDABOT_PATH)]
    except yaml.YAMLError as e:
        return ["{0}: not valid YAML ({1}).".format(DEPENDABOT_PATH, e)]
    pats = []
    for u in cfg.get("updates") or []:
        if isinstance(u, dict) and u.get("package-ecosystem") == "github-actions":
            pats += [str(d) for d in (u.get("directories") or [])]
            if u.get("directory"):
                pats.append(str(u["directory"]))
    res = [_dir_glob_re(p) for p in pats]
    failures = []
    for f in discover(root):
        if not f.startswith(".github/actions/"):
            continue
        d = "/" + os.path.dirname(f)
        if not any(r.match(d) for r in res):
            failures.append("{0}: composite directory `{1}` matches no "
                            "github-actions `directories` entry, so Dependabot "
                            "never bumps its pins.".format(DEPENDABOT_PATH, d))
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
    failures += check_inline_ignores(root, files)
    failures += check_single_home(root)
    failures += check_dependabot_coverage(root)
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
                counts = {}
                for f, audit, loc, line in findings:
                    k = (f, audit, loc)
                    counts[k] = counts.get(k, 0) + 1
                    if k in keys and counts[k] > 1:
                        failures.append("{0}:{1} {2} ({3}): a second finding "
                                        "under one waiver record; each "
                                        "finding needs its own record."
                                        .format(f, line, audit, loc))
                    elif k in keys:
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
        "symbolic": {"kind": "Primary", "key": {"Local": {"verbatim_path": file}},
                     "route": {"route": route}},
        "concrete": {"location": {"start_point": {"row": row, "column": 0}}}}]}


STEP_ROUTE = [{"Key": "jobs"}, {"Key": "j"}, {"Key": "steps"}, {"Index": 0}]
WF = ("on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
      "      - id: s\n        run: echo hi\n")
CFG = ("rules:\n  self-repository:\n    # reason: because\n    disable: true\n"
       "  unpinned-uses:\n    config:\n      policies:\n"
       "        \"actions/*\": ref-pin\n        \"github/*\": ref-pin\n"
       "        \"anthropics/*\": ref-pin\n        \"*\": hash-pin\n")


DEPENDABOT = ("version: 2\nupdates:\n  - package-ecosystem: github-actions\n"
              "    directories:\n      - \"/\"\n      - \"/.github/actions/**/*\"\n")
COMPOSITE = ("name: c\ndescription: d\nruns:\n  using: composite\n  steps:\n"
             "    - id: first\n      run: echo a\n      shell: bash\n"
             "    - id: relay\n      run: echo b\n      shell: bash\n")


def _scan_timeout_case():
    """run_zizmor must turn a scan-time failure into 'analyser missing'."""
    real = subprocess.run
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "zizmor 1.33.1\n", "")
        raise subprocess.TimeoutExpired(cmd, 600)
    subprocess.run = fake
    try:
        ver, _ = run_zizmor(".", ["x"])
    finally:
        subprocess.run = real
    if ver is None and len(calls) == 2:
        return 0
    print("SELF-TEST FAIL: a scan timeout must report the analyser missing.")
    return 1


def _tree(files):
    d = tempfile.mkdtemp(prefix="zizmor-selftest-")
    base = {".github/workflows/a.yml": WF, CONFIG_PATH: CFG,
            PIN_PATH: "version=1.33.1\n",
            DEPENDABOT_PATH: DEPENDABOT,
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


def _real_analyser_policy_case():
    """FR-006/FR-009: with the shipped .github/zizmor.yml, the real analyser
    fails a tag-pinned action outside the trusted set and accepts a tag on a
    trusted publisher. Runs only when the pinned zizmor is installed; without
    it the gate itself already fails with "analyser missing"."""
    pin = read_pin(".")
    try:
        ver = subprocess.run(["zizmor", "--version"], capture_output=True,
                             text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        ver = ""
    if not pin or ver.split()[-1:] != [pin]:
        print("note: real-analyser policy case skipped: zizmor {0} is not "
              "installed.".format(pin))
        return 0
    wf = ("on: push\npermissions: {}\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
          "    steps:\n      - uses: actions/checkout@v5\n"
          "        with:\n          persist-credentials: false\n"
          "      - uses: docker/login-action@v3\n")
    d = _tree({".github/workflows/a.yml": wf,
               CONFIG_PATH: _read(".", CONFIG_PATH)})
    try:
        got = evaluate(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    unpinned = [g for g in got if "unpinned-uses" in g]
    if len(unpinned) == 1 and "a.yml:10 " in unpinned[0]:
        return 0
    print("SELF-TEST FAIL: tag-pinned action outside the trusted set: wanted "
          "one unpinned-uses finding on a.yml:10 only, got {0}".format(got))
    return 1


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
        # US1 acceptance 2: an inline `${{ github.event.* }}` in `run:` is a
        # finding that fails naming file, line and audit; the same value
        # moved to `env:` yields no finding and passes.
        ("inline expansion names file line audit",
         {".github/workflows/a.yml": WF.replace(
             "echo hi", "echo ${{ github.event.issue.title }}")},
         _runner(payload=[_finding(".github/workflows/a.yml",
                                   "template-injection", STEP_ROUTE, row=6)]),
         "a.yml:7 template-injection"),
        # zizmor lists Hidden/Related context locations before the Primary
        # one; the line named must be the Primary location's.
        ("primary location names the line",
         {}, _runner(payload=[{"ident": "template-injection", "ignored": False,
                               "locations": [
             {"symbolic": {"kind": "Hidden",
                           "key": {"Local": {"verbatim_path": ".github/workflows/a.yml"}},
                           "route": {"route": STEP_ROUTE}},
              "concrete": {"location": {"start_point": {"row": 1, "column": 0}}}}]
             + _finding(".github/workflows/a.yml", "template-injection",
                        STEP_ROUTE, row=6)["locations"]}]),
         "a.yml:7 template-injection (job:j/step:s)"),
        ("self-repository reason left empty",
         {CONFIG_PATH: CFG.replace("# reason: because", "# reason:")},
         _runner(payload=[]), "non-empty `reason`"),
        ("env form passes",
         {".github/workflows/a.yml": WF.replace(
             "        run: echo hi\n",
             "        env:\n          T: ${{ github.event.issue.title }}\n"
             "        run: echo \"$T\"\n")},
         _runner(payload=[]), None),
        ("tag-pinned action outside the trusted set",
         {}, _runner(payload=[_finding(".github/workflows/a.yml",
                                       "unpinned-uses", STEP_ROUTE)]),
         "unpinned-uses (job:j/step:s): unwaived finding"),
        ("analyser missing", {}, _runner(version=None), "analyser missing"),
        ("wrong version", {}, _runner(version="zizmor 1.0.0"), "wrong version"),
        ("empty file set", {".github/workflows/a.yml": None},
         _runner(payload=[]), "empty set"),
        ("unparsable output", {}, _runner(raw="not json"), "not parsable"),
        ("self-repository reason removed",
         {CONFIG_PATH: CFG.replace("    # reason: because\n", "")},
         _runner(payload=[]), "non-empty `reason`"),
        ("trusted list second copy",
         {".github/scripts/other.json": "{\"actions/*\": \"ref-pin\"}"},
         _runner(payload=[]), "second copy"),
        ("policy differing from home",
         {CONFIG_PATH: CFG.replace('"*": hash-pin', '"*": ref-pin')},
         _runner(payload=[]), "must be `hash-pin`"),
        ("composite finding names its step",
         {".github/actions/c/action.yml": COMPOSITE},
         _runner(payload=[_finding(".github/actions/c/action.yml", "github-env",
                                   [{"Key": "runs"}, {"Key": "steps"},
                                    {"Index": 1}])]),
         "github-env (step:relay): unwaived finding"),
        ("composite waiver does not cover another step",
         {".github/actions/c/action.yml": COMPOSITE,
          REGISTER_PATH: json.dumps({"waivers": [_entry(
              file=".github/actions/c/action.yml", audit="github-env",
              location="step:relay")]})},
         _runner(payload=[_finding(".github/actions/c/action.yml", "github-env",
                                   [{"Key": "runs"}, {"Key": "steps"},
                                    {"Index": 0}])]),
         "github-env (step:first): unwaived finding"),
        ("deeply nested composite is covered by Dependabot",
         {".github/actions/_shared/a/b/c/action.yml": COMPOSITE},
         _runner(payload=[]), None),
        ("composite outside Dependabot's directories",
         {".github/actions/_shared/a/b/action.yml": COMPOSITE,
          DEPENDABOT_PATH: DEPENDABOT.replace("/.github/actions/**/*",
                                              "/.github/actions/*")},
         _runner(payload=[]), "matches no github-actions `directories`"),
        ("scan timeout is analyser missing", {},
         _runner(version=None), "analyser missing"),
        ("two findings under one record",
         {REGISTER_PATH: json.dumps({"waivers": [_entry(
             audit="dangerous-triggers", location="workflow")]})},
         _runner(payload=[
             _finding(".github/workflows/a.yml", "dangerous-triggers",
                      [{"Key": "on"}]),
             _finding(".github/workflows/a.yml", "dangerous-triggers",
                      [{"Key": "on"}], row=4)]),
         "a second finding under one waiver record"),
        ("inline zizmor ignore",
         {".github/workflows/a.yml": WF.replace(
             "echo hi", "echo hi  # zizmor: ignore[template-injection]")},
         _runner(payload=[]), "inline `zizmor: ignore`"),
        ("another audit disabled",
         {CONFIG_PATH: CFG + "  template-injection:\n    disable: true\n"},
         _runner(payload=[]), "audit `template-injection` is disabled"),
        ("policy for an unapproved publisher",
         {CONFIG_PATH: CFG.replace('        "*": hash-pin',
                                   '        "docker/*": ref-pin\n'
                                   '        "*": hash-pin')},
         _runner(payload=[]), "outside the owner-approved"),
        ("trusted list copy in a gate script",
         {".github/scripts/other.py": "X = {'actions/*': 'ref-pin'}\n"},
         _runner(payload=[]), "second copy"),
        ("record without control",
         {REGISTER_PATH: json.dumps({"waivers": [
             {k: v for k, v in _entry().items() if k != "control"}]})},
         _runner(payload=inj), "missing `control`"),
    ]
    bad = _real_analyser_policy_case() + _scan_timeout_case()
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
