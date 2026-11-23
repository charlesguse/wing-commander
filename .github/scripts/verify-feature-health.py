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
        for ref in e["workflows"]:
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
        got = fh.read_signal(case["signal"], "own/repo", since, StubGh(case["responses"].items()
                                                                       if isinstance(case["responses"], dict)
                                                                       else case["responses"]), environ)
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
    return ("#!/usr/bin/env bash\ncase \"$*\" in\n"
            "  *rate_limit*) printf '{\"resources\":{\"core\":{\"remaining\":%s}}}\\n' '" + str(
                scenario.get("rate_remaining", 5000)) + "' ;;\n"
            + "".join(arms)
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
