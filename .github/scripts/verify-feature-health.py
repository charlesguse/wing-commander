#!/usr/bin/env python3
"""Gate (unnumbered) -- feature health puts every feature in exactly one state,
decided by code, and the registry cannot drift from docs/reference.md
(specs/126-feature-health, FR-001 to FR-018, SC-002/003/006/007).

Checks:
  registry   feature-health-registry.json against reference.md's three tables,
             the workflow files and the Kill switches table
  states     fixtures/feature-health/cases.json through the pure classifier
  render     fixtures/feature-health/render/render.json through render_section
  signals    fixtures/feature-health/signals/signals.json through read_signal
  unreadable fixtures/feature-health/unreadable/scenarios.json: collect/build
             against a `gh` stub on PATH built with wc_shell_harness
  workflow   wing-commander-feature-health.yml is read-only, agent-free and
             hands its artifact to wc_board_status.py
  sc001      the replay corpus, or the pending exemption
A self-check changes the code's input and confirms the fixtures notice.
"""
import copy
import datetime
import json
import os
import re
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import wc_feature_health as fh  # noqa: E402
import wc_shell_harness as harness  # noqa: E402
from board_prove import Exemption  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "feature-health")
WORKFLOW = "wing-commander-feature-health.yml"
REFERENCE_TABLES = ("At a glance", "Housekeeping and observability", "Schedules")
CADENCES = ("schedule", "event")  # data-model.md "Workflow ref"

# Reference rows that are not a feature of their own (Gate 124 reads `issue=`).
EXEMPT_UNREGISTERED = {
    "housekeeping": Exemption(reason="a group row; its members are registered one by one", issue=(889,)),
}
EXEMPT_SC001_PENDING = {
    "sc001": Exemption(reason="the corpus capture needs full history and an authenticated gh (T030)",
                       issue=(889,)),
}


def load(*parts):
    with open(os.path.join(FIXTURES, *parts), encoding="utf-8") as fp:
        return json.load(fp)


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
def norm(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.replace("`", "").strip().lower()


def table_rows(ref_text, heading, key_col):
    """The key cell of each data row of the table under `## heading`."""
    out, inside, skip = [], False, 2
    for line in ref_text.splitlines():
        if line.startswith("## "):
            inside, skip = line[3:].strip() == heading, 2
            continue
        if inside and line.startswith("|"):
            if skip:
                skip -= 1
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append(cells[key_col])
    return out


def kill_switches(ref_text):
    return {c.replace("`", "") for c in table_rows(ref_text, "Kill switches", 0)}


def check_registry(registry, ref_text, workflow_files, exempt):
    problems = []
    names = {}
    for e in registry:
        names[e["name"]] = names.get(e["name"], 0) + 1
    problems += ["duplicate registry name: {0}".format(n) for n, c in sorted(names.items()) if c > 1]
    switches = kill_switches(ref_text)
    for e in registry:
        if not e.get("workflows"):
            problems.append("{0}: workflows must list at least one workflow".format(e["name"]))
        for ref in e.get("workflows") or []:
            if ref.get("cadence") not in CADENCES:
                problems.append("{0}: {1} has cadence {2!r}, not one of {3}".format(
                    e["name"], ref["file"], ref.get("cadence"), "/".join(CADENCES)))
            if ref["file"] not in workflow_files:
                problems.append("{0}: workflow file {1} does not exist".format(e["name"], ref["file"]))
        if e.get("kill_switch") and e["kill_switch"] not in switches:
            problems.append("{0}: kill switch {1} is not in reference.md's Kill switches table".format(
                e["name"], e["kill_switch"]))
        if "quiet_days" in e and not (isinstance(e["quiet_days"], int) and e["quiet_days"] >= 1):
            problems.append("{0}: quiet_days must be an integer of at least 1".format(e["name"]))
        sig = e.get("signal")
        if sig and sig.get("kind") not in fh.SIGNAL_KINDS:
            problems.append("{0}: unknown signal kind {1}".format(e["name"], sig.get("kind")))
    known = set()
    for e in registry:
        known.add(norm(e["name"]))
        known.update(norm(a) for a in e.get("reference_names", []))
    known.update(exempt)
    for heading, col in zip(REFERENCE_TABLES, (0, 0, 1)):
        for cell in table_rows(ref_text, heading, col):
            if norm(cell) not in known:
                problems.append("reference.md '{0}' lists '{1}' but the registry has no entry".format(
                    heading, norm(cell)))
    return problems


def check_registry_fixtures(registry, ref_text, files):
    problems = []
    for case in load("registry", "mutations.json"):
        reg, text, fl = copy.deepcopy(registry), ref_text, set(files)
        kind = case["kind"]
        if kind == "add_ref_row":
            text = ref_text.replace("| [Housekeeping](#housekeeping-and-observability)",
                                    "| [Invented feature](#x) | a | b | c | d | e |\n"
                                    "| [Housekeeping](#housekeeping-and-observability)", 1)
        elif kind == "missing_file":
            reg[0]["workflows"][0]["file"] = "no-such-workflow.yml"
        elif kind == "unknown_switch":
            reg[1]["kill_switch"] = "WING_COMMANDER_NO_SUCH_PAUSED"
        elif kind == "duplicate":
            reg[1]["name"] = reg[0]["name"]
        elif kind == "quiet_zero":
            reg[1]["quiet_days"] = 0
        elif kind == "empty_workflows":
            reg[1]["workflows"] = []
        elif kind == "bad_cadence":
            reg[1]["workflows"][0]["cadence"] = "schedul"
        got = check_registry(reg, text, fl, EXEMPT_UNREGISTERED)
        if not any(case["expect"] in p for p in got):
            problems.append("registry fixture '{0}': no problem containing '{1}' (got {2})".format(
                case["label"], case["expect"], got))
    return problems


# --------------------------------------------------------------------------
# states / render / signals
# --------------------------------------------------------------------------
def parse_now(fx):
    return fh.parse_time(fx["now"])


def make_inputs(fx, cases):
    """registry, readings, signals, ctx for a list of case dicts."""
    now = parse_now(fx)
    registry, readings, signals, ctx = [], {}, {}, {"switches": {}, "vars_set": {}}
    for i, case in enumerate(cases):
        entry = copy.deepcopy(fx["base_entry"])
        entry.update(copy.deepcopy(case.get("entry") or {}))
        entry["name"] = case.get("name") or "feature-{0}".format(i)
        for ref in entry["workflows"]:
            ref["file"] = "{0}-{1}".format(entry["name"], ref["file"])
        registry.append(entry)
        for ref in entry["workflows"]:
            base = ref["file"][len(entry["name"]) + 1:]
            runs = (case.get("runs") or {}).get(base, [])
            if isinstance(runs, dict):
                readings[ref["file"]] = {"unreadable": runs["unreadable"]}
                continue
            readings[ref["file"]] = {
                "runs": [{"id": n, "event": "schedule", "conclusion": c,
                          "started_at": fh.fmt_time(now - datetime.timedelta(hours=h))}
                         for n, (h, c) in enumerate(runs)],
                "interval_hours": case.get("interval", 24)}
        if entry.get("signal"):
            sig = case.get("signal_days_ago", "absent")
            if isinstance(sig, dict):
                signals[entry["name"]] = sig
            else:
                signals[entry["name"]] = {"signal_at": None if sig is None else fh.fmt_time(
                    now - datetime.timedelta(days=sig))}
        for key in ("switches", "vars_set"):
            ctx[key].update(case.get("ctx", {}).get(key, {}))
    return registry, readings, signals, ctx


def run_state_case(fx, case):
    reg, readings, signals, ctx = make_inputs(fx, [case])
    rows = fh.classify_all(reg, readings, signals, ctx, parse_now(fx))
    return rows


def check_states(fx):
    problems = []
    for case in fx["cases"]:
        rows = run_state_case(fx, case)
        if rows[0]["state"] != case["expect"]:
            problems.append("{0}: state {1}, expected {2}".format(case["label"], rows[0]["state"], case["expect"]))
        if case.get("expect_reason") and case["expect_reason"] not in (rows[0]["reason"] or ""):
            problems.append("{0}: reason {1!r} does not name {2!r}".format(
                case["label"], rows[0]["reason"], case["expect_reason"]))
        for stage, want in (case.get("expect_stages") or {}).items():
            got = next((r["state"] for r in rows if r["stage"] == stage), None)
            if got != want:
                problems.append("{0}: stage {1} is {2}, expected {3}".format(case["label"], stage, got, want))
        if rows != run_state_case(fx, case):
            problems.append("{0}: two classifications of the same input differ".format(case["label"]))
    return problems


def check_render(fx, rx):
    problems = []
    for case in rx["cases"]:
        reg, readings, signals, ctx = make_inputs(fx, case["features"])
        now = parse_now(fx)
        rows = fh.classify_all(reg, readings, signals, ctx, now)
        text = fh.render_section(rows, now, len(reg))
        if case.get("shorten"):
            text = fh.shorten_section(text)
        for want in case.get("contains", []):
            if want not in text:
                problems.append("{0}: output lacks {1!r}".format(case["label"], want))
        for bad in case.get("absent", []):
            if bad in text:
                problems.append("{0}: output has {1!r}".format(case["label"], bad))
        for e in reg:
            if not case.get("shorten") and text.count("| {0} |".format(e["name"])) != 1:
                problems.append("{0}: feature {1} is not in the table exactly once".format(case["label"], e["name"]))
        order = [text.find(x) for x in case.get("ordered", [])]
        if order != sorted(order) or -1 in order:
            problems.append("{0}: rows are not in the order {1}".format(case["label"], case.get("ordered")))
        again = fh.render_section(fh.classify_all(reg, readings, signals, ctx, now), now, len(reg))
        if case.get("shorten"):
            again = fh.shorten_section(again)
        if text != again:
            problems.append("{0}: two renders differ (SC-003)".format(case["label"]))
    return problems


class StubGh:
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, path):
        for key, body in self.responses:
            if key in path:
                return body
        return []


def check_signals(sx):
    problems = []
    environ = sx.get("environ", {})
    since = fh.parse_time(sx["since"])
    for case in sx["cases"]:
        try:
            got = fh.read_signal(case["signal"], "own/repo", since, StubGh(case["responses"].items()
                                                                           if isinstance(case["responses"], dict)
                                                                           else case["responses"]), environ)
        except RuntimeError as exc:
            got = {"error": str(exc)}
        if got != case["expect"]:
            problems.append("signal {0}: got {1}, expected {2}".format(case["label"], got, case["expect"]))
    return problems


# --------------------------------------------------------------------------
# unreadable: a `gh` stub on PATH, built with the shared harness
# --------------------------------------------------------------------------
def stub_script(scenario):
    arms = []
    for fail in scenario.get("fail", []):
        if fail.get("overcap"):
            body = "    printf '%s\\n' '{\"total_count\":1000,\"workflow_runs\":[]}'\n"
        else:
            body = harness.gh_error_stub_arm("*{0}*".format(fail["match"]), fail.get("status", 500),
                                             fail.get("message", "Server Error"))
        arms.append("  *{0}*)\n{1}    ;;\n".format(fail["match"], body))
    for fresh in scenario.get("fresh_runs", []):
        arms.append("  *actions/workflows/{0}/*)\n    printf '%s\\n' '{{\"total_count\":1,\"workflow_runs\":"
                    "[{{\"id\":1,\"event\":\"schedule\",\"conclusion\":\"success\",\"run_started_at\":\"{1}\","
                    "\"created_at\":\"{1}\"}}]}}'\n    ;;\n".format(fresh, scenario["fresh_at"]))
    return ("#!/usr/bin/env bash\ncase \"$*\" in\n"
            "  *rate_limit*) printf '{\"resources\":{\"core\":{\"remaining\":%s}}}\\n' '" + str(
                scenario.get("rate_remaining", 5000)) + "' ;;\n"
            + "".join(arms)
            + "  *search/issues*) printf '{\"total_count\":0,\"incomplete_results\":false,\"items\":[]}\\n' ;;\n"
            + "  */commits/*) printf '{\"commit\":{\"committer\":{\"date\":\"2026-11-20T00:00:00Z\"}}}\\n' ;;\n"
            "  *actions/workflows/*) printf '{\"total_count\":0,\"workflow_runs\":[]}\\n' ;;\n"
            "  *) printf '[]\\n' ;;\nesac\n")


def check_unreadable(ux):
    problems = []
    registry = fh.load_registry()
    now = fh.parse_time(ux["now"])
    old_path = os.environ["PATH"]
    with tempfile.TemporaryDirectory() as tmp:
        stub = os.path.join(tmp, "gh")
        os.environ["PATH"] = tmp + os.pathsep + old_path
        try:
            for sc in ux["scenarios"]:
                with open(stub, "w", encoding="utf-8") as out:
                    out.write(stub_script(sc))
                os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
                environ = {}
                for e in registry:
                    for name in (e.get("kill_switch"), e.get("requires_var")):
                        if name:
                            environ[name[len(fh.SWITCH_PREFIX):]] = ""
                for drop in sc.get("env_drop", []):
                    environ.pop(drop, None)
                try:
                    text = fh.build("own/repo", now=now, environ=environ, registry=registry,
                                    read_text=lambda name: 'cron: "17 6 * * *"')
                    outcome = "ok"
                except SystemExit as exc:
                    text, outcome = str(exc), "exit"
                if outcome != sc["expect_outcome"]:
                    problems.append("{0}: outcome {1}, expected {2} ({3})".format(
                        sc["label"], outcome, sc["expect_outcome"], text[:120]))
                for want in sc.get("contains", []):
                    if want not in text:
                        problems.append("{0}: output lacks {1!r}".format(sc["label"], want))
                for bad in sc.get("absent", []):
                    if bad in text:
                        problems.append("{0}: output has {1!r}".format(sc["label"], bad))
        finally:
            os.environ["PATH"] = old_path
    return problems


# --------------------------------------------------------------------------
# workflow file
# --------------------------------------------------------------------------
WRITE_VERBS = re.compile(r"gh\s+(issue|pr)\s+(comment|edit|close|create|review|merge|reopen)"
                         r"|gh\s+workflow\s+run|gh\s+label|gh\s+api\s+(-X|--method)\s*(POST|PATCH|PUT|DELETE)",
                         re.I)


def check_workflow_text(text, artifact):
    problems = []
    if re.search(r"^\s*[\w-]+:\s*write\s*$", text, re.M):
        problems.append("the workflow holds a write permission")
    if re.search(r"claude|anthropic|app-token|create-github-app-token", text, re.I):
        problems.append("the workflow runs an agent or mints an App token")
    if WRITE_VERBS.search(text):
        problems.append("the workflow uses a gh write verb")
    if re.search(r"always\(\)", text):
        problems.append("the workflow uses always() (success() only, T020)")
    if "name: {0}".format(artifact) not in text:
        problems.append("the upload step's artifact name is not {0}".format(artifact))
    if "workflow_dispatch" not in text or "cron:" not in text:
        problems.append("the workflow lacks its schedule or dispatch trigger")
    return problems


def check_workflow_fixtures(good, artifact):
    problems = []
    cases = [("issues: write", good.replace("issues: read", "issues: write"), "write permission"),
             ("agent step", good + "\n      - uses: anthropics/claude-code-action@v1\n", "agent"),
             ("gh write verb", good + "\n        run: gh issue comment 1 -b x\n", "write verb"),
             ("always()", good.replace("steps.pause.outputs.paused != 'true'", "always()", 1), "always()"),
             ("artifact name", good.replace("name: " + artifact, "name: other"), "artifact name")]
    for label, text, expect in cases:
        if not any(expect in p for p in check_workflow_text(text, artifact)):
            problems.append("workflow fixture '{0}' is not noticed".format(label))
    return problems


def check_workflow():
    import wc_board_status as bs
    path = os.path.join(REPO, ".github", "workflows", WORKFLOW)
    if not os.path.exists(path):
        return ["{0} does not exist".format(WORKFLOW)]
    with open(path, encoding="utf-8") as fp:
        text = fp.read()
    artifact = bs.FEATURE_HEALTH_ARTIFACT
    registry = fh.load_registry()
    problems = check_workflow_env(text, registry)
    if not check_workflow_env(re.sub(r"^\s*METRICS_BRANCH:.*$", "", text, flags=re.M), registry):
        problems.append("self-check: a workflow env missing a registry switch is not noticed")
    return problems + check_workflow_text(text, artifact) + check_workflow_fixtures(text, artifact)


def check_workflow_env(text, registry):
    """Every kill switch and required variable the registry names must be
    supplied in the workflow's env as `KEY: ${{ vars.WING_COMMANDER_KEY }}`
    (the key is the name without its prefix, which is what collect reads)."""
    names = set()
    for e in registry:
        names.update(n for n in (e.get("kill_switch"), e.get("requires_var")) if n)
        sig = e.get("signal") or {}
        if sig.get("kind") == "branch_commit":
            names.add("WING_COMMANDER_METRICS_BRANCH")
    problems = []
    for name in sorted(names):
        key = name[len(fh.SWITCH_PREFIX):] if name.startswith(fh.SWITCH_PREFIX) else name
        if not re.search(r"^\s*{0}:\s*\$\{{\{{\s*vars\.{1}\s*\}}\}}".format(re.escape(key), re.escape(name)),
                         text, re.M):
            problems.append("the workflow env does not supply {0} as {1}".format(name, key))
    return problems


# --------------------------------------------------------------------------
# SC-001
# --------------------------------------------------------------------------
def check_sc001(directory, exempt):
    paths = [os.path.join(directory, n) for n in ("corpus.json", "expected.json")]
    present = [os.path.exists(p) for p in paths]
    if not any(present):
        if exempt:
            return [], "SC-001 not yet captured (EXEMPT_SC001_PENDING, #889)"
        return ["SC-001: the corpus and answer key are absent and the exemption was deleted without the capture"], None
    if not all(present):
        return ["SC-001: only one of corpus.json and expected.json is present"], None
    if exempt:
        return ["SC-001: both files are present but EXEMPT_SC001_PENDING is still there"], None
    with open(paths[0], encoding="utf-8") as fp:
        corpus = json.load(fp)
    with open(paths[1], encoding="utf-8") as fp:
        expected = json.load(fp)
    now = fh.parse_time(corpus["now"])
    rows = fh.classify_all(corpus["registry"], corpus["readings"], corpus.get("signals", {}), corpus["ctx"], now)
    got = {(r["feature"], r["stage"] or ""): r["state"] for r in rows}
    want = {(e["feature"], e.get("stage") or ""): e["state"] for e in expected["rows"]}
    return ["SC-001: {0} is {1}, expected {2}".format(k, got.get(k), v) for k, v in sorted(want.items())
            if got.get(k) != v], None


def self_check(fx):
    """A gate that cannot fail its subject is worthless: weaken the code and
    confirm the state fixtures notice."""
    saved = fh.DEFAULT_QUIET_DAYS
    fh.DEFAULT_QUIET_DAYS = 10 ** 6
    try:
        weakened = check_states(fx)
    finally:
        fh.DEFAULT_QUIET_DAYS = saved
    return [] if weakened else ["self-check: the state fixtures did not notice a disabled quiet rule"]


def check_shared_sources():
    """FR-003/FR-004 single home: triage grounds come from board_triage.py and
    switch values from wc_board_status._switch_on."""
    import board_triage
    import wc_board_status as bs
    problems = []
    if fh.TRIAGE_CLOSE_GROUNDS is not board_triage.TRIAGE_CLOSE_GROUNDS:
        problems.append("triage grounds are not imported from board_triage.py")
    with open(os.path.join(HERE, "board_triage.py"), encoding="utf-8") as fp:
        src = fp.read()
    for g in board_triage.TRIAGE_CLOSE_GROUNDS:
        if '"outcome": "closed", "ground": "{0}"'.format(g) not in src:
            problems.append("board_triage.py no longer closes on ground {0}".format(g))
    if re.search(r'"grounds"\s*:', json.dumps(fh.load_registry())):
        problems.append("registry holds a literal triage grounds list")
    if fh.TRIAGE_CLOSE_COMMENT_PREFIX is not board_triage.TRIAGE_CLOSE_COMMENT_PREFIX:
        problems.append("the triage close sentence is not imported from board_triage.py")
    with open(os.path.join(REPO, ".github", "workflows", "board-loop.yml"), encoding="utf-8") as fp:
        loop = fp.read()
    if "'{0}%s,".format(board_triage.TRIAGE_CLOSE_COMMENT_PREFIX) not in loop:
        problems.append("board-loop.yml no longer closes with '{0}<ground>,' (TRIAGE_CLOSE_COMMENT_PREFIX)".format(
            board_triage.TRIAGE_CLOSE_COMMENT_PREFIX))
    with open(os.path.join(HERE, "wc_feature_health.py"), encoding="utf-8") as fp:
        fh_src = fp.read()
    problems += check_switch_source(fh_src)
    copied = fh_src.replace("ctx[kind][name] = wc_board_status._switch_on(environ[env])",
                            'ctx[kind][name] = environ[env].strip().lower() == "true"', 1)
    if copied == fh_src or not check_switch_source(copied):
        problems.append("self-check: a switch reader reimplemented inside collect is not noticed")
    base = ("import wc_board_status\n"
            "def collect(env):\n    {body}\n")
    helper = ("def _parse(v):\n    return v.strip().lower() in ('true', '1')\n"
              "def collect(env):\n    wc_board_status._switch_on(env)\n    return _parse(env)\n")
    for label, src, want in (
            ("a module-level helper called from collect", helper, True),
            ("an unrelated '1' constant", base.format(body="wc_board_status._switch_on(env)\n    return env.get('n', '1')"), False),
            ("a version string compared elsewhere", base.format(body="wc_board_status._switch_on(env)\n    return env == 'v2'"), False)):
        if bool(check_switch_source(src)) != want:
            problems.append("self-check: check_switch_source on {0} gave {1}".format(label, check_switch_source(src)))
    # A switch value must read the same through both modules.
    for value in ("true", " TRUE ", "false", "", "1", "yes"):
        env = {"BOARD_X": value}
        entry = [{"name": "f", "workflows": [], "kill_switch": "WING_COMMANDER_BOARD_X"}]
        got = fh.collect(entry, "own/repo", fh.parse_time("2026-11-20T00:00:00"),
                         gh=lambda *_a, **_k: [], environ=env)
        ctx = got[2] if isinstance(got, tuple) else got
        if ctx["switches"]["WING_COMMANDER_BOARD_X"] != bs._switch_on(value):
            problems.append("switch value {0!r} reads differently from wc_board_status".format(value))
    return problems


def check_switch_source(src):
    """FR-004 single home, read from the source: collect reads switches only
    through wc_board_status._switch_on, and wc_feature_health defines no switch
    parser of its own. The value-parity loop above cannot see a copy that
    happens to agree on its sample values."""
    import ast
    tree = ast.parse(src)
    problems = []
    defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if "_switch_on" in defs:
        problems.append("wc_feature_health.py defines its own _switch_on")
    coll = defs.get("collect")
    calls = [n for n in ast.walk(coll) if isinstance(n, ast.Call)] if coll else []
    shared = [c for c in calls if isinstance(c.func, ast.Attribute) and c.func.attr == "_switch_on"
              and isinstance(c.func.value, ast.Name) and c.func.value.id == "wc_board_status"]
    if not shared:
        problems.append("collect does not read switches through wc_board_status._switch_on")
    truthy = ("true", "1", "yes", "on")

    def is_truthy_const(n):
        return isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip().lower() in truthy

    def parses_switch(node):
        """A comparison (==, !=, in) against a truthy string or a collection of them."""
        if not isinstance(node, ast.Compare):
            return None
        for comp in node.comparators:
            if is_truthy_const(comp):
                return comp.value
            if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) and any(is_truthy_const(e) for e in comp.elts):
                return next(e.value for e in comp.elts if is_truthy_const(e))
        return None

    # collect plus every module-level helper it reaches by name.
    seen, todo = set(), ["collect"] if coll else []
    while todo:
        fn = todo.pop()
        if fn in seen or fn not in defs:
            continue
        seen.add(fn)
        for node in ast.walk(defs[fn]):
            lit = parses_switch(node)
            if lit is not None:
                problems.append("{0} compares a switch against the literal {1!r}".format(fn, lit))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id != "_switch_on":
                todo.append(node.func.id)
    return problems


def check_review_round_three():
    """Unquoted and ranged cron, bounded triage and comment reads."""
    problems = []
    for text, want in (("    - cron: 0 */4 * * *\n", 4),
                       ("    - cron: 17 6 * * *   # daily\n", 24),
                       ('    - cron: "0 9-17 * * *"\n', 16),
                       ('    - cron: "0 0-23/6 * * *"\n', 6),
                       ('    - cron: "0 1,9-11 * * *"\n', 14),
                       ('    - cron: "0 5-5/2 * * *"\n', 24),
                       ('    - cron: "0 5/6 * * *"\n', 6)):
        try:
            got = fh.schedule_interval_hours(text)
        except ValueError as exc:
            got = "ValueError: {0}".format(exc)
        if got != want:
            problems.append("cron parsing: {0!r} gave {1}, expected {2}".format(text.strip(), got, want))
    for bad in ('    - cron: "0 25 * * *"\n', '    - cron: "0 5-2 * * *"\n', '    - cron: "0 */0 * * *"\n',
                '    - cron: "0 5-2/2 * * *"\n'):
        try:
            fh.schedule_interval_hours(bad)
            problems.append("cron parsing: {0!r} did not raise".format(bad.strip()))
        except ValueError:
            pass
    # A daily 9-17 cron whose last run was 13.5 h ago is not "not running".
    now = fh.parse_time("2026-11-20T23:30:00Z")
    state, _d = fh.classify_workflow(
        {"file": "x.yml", "cadence": "schedule"}, {"name": "f"},
        {"runs": [{"started_at": "2026-11-20T10:00:00Z", "conclusion": "success"}],
         "interval_hours": fh.schedule_interval_hours('    - cron: "0 9-17 * * *"\n')},
        {}, now)
    if state != "healthy":
        problems.append("a 9-17 daily cron with a run 13.5 h ago classed {0!r}, expected healthy".format(state))

    since = fh.parse_time("2026-10-20T00:00:00Z")
    calls = []

    def busy(path):
        """A repository with 300+ closed issues and two triage closes."""
        calls.append(path)
        if path.startswith("search/issues"):
            return {"total_count": 2, "incomplete_results": False,
                    "items": [{"number": 1, "updated_at": "2026-11-09T00:00:00Z"},
                              {"number": 2, "updated_at": "2026-11-01T00:00:00Z"}]}
        if "/issues/1/comments" in path:
            return [{"body": "Triage closed this issue on ground rate_limit, x", "created_at": "2026-11-08T00:00:00Z"}]
        if "/issues/2/comments" in path:
            return [{"body": "Triage closed this issue on ground action_bump, x", "created_at": "2026-10-30T00:00:00Z"}]
        if "issues?state=closed" in path:
            return [{"number": n} for n in range(100)]
        return []
    try:
        got = fh.read_signal({"kind": "triage_close"}, "own/repo", since, busy, {})
    except RuntimeError as exc:
        got = "RuntimeError: {0}".format(exc)
    if got != "2026-11-08T00:00:00Z":
        problems.append("triage_close on a busy repository: got {0}, expected 2026-11-08T00:00:00Z".format(got))
    if any("/issues/2/comments" in c for c in calls):
        problems.append("triage_close read an issue updated before the newest close already found")

    def limited(path):
        if path.startswith("search/issues"):
            raise RuntimeError("gh: API rate limit exceeded (HTTP 403)")
        return []
    try:
        fh.read_signal({"kind": "triage_close"}, "own/repo", since, limited, {})
        problems.append("triage_close: a search 403 did not raise")
    except RuntimeError as exc:
        if "search quota is separate" not in str(exc):
            problems.append("triage_close: a search 403 reads as a generic failure: {0}".format(exc))

    def unresolved(path):
        if path.startswith("search/issues"):
            return {"total_count": 900, "incomplete_results": False,
                    "items": [{"number": n, "updated_at": "2026-11-09T00:00:00Z"} for n in range(100)]}
        return []
    for label, stub in (("a search that never resolves", unresolved),
                        ("an incomplete search", lambda p: {"incomplete_results": True, "items": []}
                         if p.startswith("search/") else [])):
        try:
            fh.read_signal({"kind": "triage_close"}, "own/repo", since, stub, {})
            problems.append("triage_close: {0} did not raise".format(label))
        except RuntimeError:
            pass

    def many_labeled(path):
        if "labels=" in path:
            page = int(re.search(r"&page=(\d+)", path).group(1))
            return [{"number": n, "created_at": "2026-11-01T00:00:00Z"}
                    for n in range(100 if page == 1 else 51 if page == 2 else 0)]
        return []
    try:
        fh.read_signal({"kind": "issue_or_comment", "label_name": "x"}, "own/repo", since, many_labeled, {})
        problems.append("issue_or_comment: {0} labeled issues read without raising".format(151))
    except RuntimeError:
        pass
    return problems


def check_review_round_two():
    """Cron parsing, truncated reads, shortened-section detection."""
    problems = []
    wf = "on:\n  schedule:\n    - cron: '0 */6 * * *'\n    # - cron: \"0 1 * * *\"\n    - cron: \"0 3,15 * * *\"\n"
    if fh.schedule_interval_hours(wf) != 6:
        problems.append("cron parsing: expected the smallest interval 6, got {0}".format(
            fh.schedule_interval_hours(wf)))
    if fh.schedule_interval_hours('on:\n  schedule:\n    - cron: "0 1 * * *"\n') != 24:
        problems.append("cron parsing: a daily cron is not 24 hours")
    try:
        fh.schedule_interval_hours('    - cron: "bad"\n')
        problems.append("cron parsing: an unparseable cron did not raise")
    except ValueError:
        pass
    try:
        fh._pages(lambda _p: [{}] * 100, "x?a=1", 2)
        problems.append("_pages: a full last page did not raise")
    except RuntimeError:
        pass
    shortened = ("<!-- wing-commander-feature-health -->\n**Feature health** — built x\n\n"
                 "_Table shortened: it did not fit._\n<!-- /wing-commander-feature-health -->")
    if not fh.section_built(shortened, fh.MARKER_BEGIN):
        problems.append("section_built: a shortened section reads as not built")
    if fh.section_built("see wing-commander-feature-health here\n_Stale: x_\n<details>x</details>\n",
                        "wing-commander-feature-health"):
        problems.append("section_built: a bare earlier mention read as the section")
    for expr, want in (("0 * * * 1", 168), ("0 6 1 */3 *", 24 * 31 * 3), ("0 * * * *", 1)):
        got = fh.schedule_interval_hours('on:\n  schedule:\n    - cron: "{0}"\n'.format(expr))
        if got < want if want > 1 else got != want:
            problems.append("cron {0}: interval {1}h, want >= {2}h".format(expr, got, want))
    snap_src = open(os.path.join(REPO, ".github", "scripts", "wc_board_status.py"), encoding="utf-8").read()
    if 'if stale_keeps_section:\n            snap["built_at"]' not in snap_src:
        problems.append("section_snapshot: built_at must be gated on stale_keeps_section")
    return problems


def check_review_round_five(registry):
    """section_built with the registry's own marker: a title mentioning the
    workflow file must not stand in for the section's opener."""
    problems = []
    marker = next(e["signal"]["marker"] for e in registry
                  if (e.get("signal") or {}).get("label") == "feature health section")
    body = ("| #1 | Fix wing-commander-feature-health.yml paused check | open |\n\n"
            "<!-- wc-proof-list:begin status=\"built\" built=\"2026-11-22\" -->\nproofs\n"
            "<!-- wc-proof-list:end -->\n"
            "<!-- wing-commander-feature-health -->\nFeature health's latest build failed.\n"
            "<!-- /wing-commander-feature-health -->\n")
    if fh.section_built(body, marker):
        problems.append("section_built: a failed feature-health notice reads as built when a "
                        "title mentions the workflow file")
    return problems


def main():
    with open(os.path.join(REPO, "docs", "reference.md"), encoding="utf-8") as fp:
        ref_text = fp.read()
    files = set(os.listdir(os.path.join(REPO, ".github", "workflows")))
    registry = fh.load_registry()
    fx = load("cases.json")
    problems = check_registry(registry, ref_text, files, EXEMPT_UNREGISTERED)
    problems += check_registry_fixtures(registry, ref_text, files)
    problems += check_states(fx)
    problems += check_render(fx, load("render", "render.json"))
    problems += check_signals(load("signals", "signals.json"))
    problems += check_unreadable(load("unreadable", "scenarios.json"))
    problems += check_workflow()
    problems += check_shared_sources()
    problems += check_review_round_two()
    problems += check_review_round_three()
    problems += check_review_round_five(registry)
    real, note = check_sc001(os.path.join(FIXTURES, "sc001"), EXEMPT_SC001_PENDING)
    problems += real + self_check(fx)
    if note:
        print("[ok] verify-feature-health: {0}".format(note))
    if problems:
        for p in problems:
            print("[FAIL] verify-feature-health: {0}".format(p))
        return 1
    print("[ok] verify-feature-health: {0} features, {1} state cases".format(len(registry), len(fx["cases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
