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
  sc001      the captured 2026-10-14..2026-11-12 corpus against its hand-written key
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
import types
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import wc_feature_health as fh  # noqa: E402
import wc_proof_list  # noqa: E402
import wc_shell_harness as harness  # noqa: E402
from board_prove import Exemption  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "feature-health")
WORKFLOW = "wing-commander-feature-health.yml"
REFERENCE_TABLES = ("At a glance", "Housekeeping and observability", "Schedules")
CADENCES = ("schedule", "event")  # data-model.md "Workflow ref"

# Reference rows that are not a feature of their own (Gate 124 reads `issue=`).
EXEMPT_UNREGISTERED = {
    "housekeeping": Exemption(reason="a group row; its members are registered one by one", issue=(889,)),
    ".github/dependabot.yml (dependabot, github-actions only)": Exemption(
        reason="Dependabot runs as GitHub's service, not as a workflow here, so "
               "there is no run history for a health state (specs/132 FR-009b)",
        issue=(), permanent=True,
        permanent_reason="Not a workflow of this repository; its bump PRs pass through the gate suite like any PR.",
        decided_by=(890,)),
}
# Emptied by T030: the corpus and its key are captured (fixtures/feature-health/sc001).
EXEMPT_SC001_PENDING = {}
# SC-001's window, "2026-10-14 to 2026-11-12", with `now` on the last day.
SC001_START = "2026-10-14T00:00:00Z"
SC001_NOW_DAY = "2026-11-12"


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
                                    read_text=lambda name: on_schedule('"17 6 * * *"'))
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
    return sc001_replay(corpus, expected), None


def sc001_replay(corpus, expected, registry=None):
    """Classify the corpus's readings, signals and switches at its own `now`
    (no gh, no clock) with the registry as it is now, not the copy the corpus
    recorded at capture, so a registry change that breaks SC-001 (a board
    loop threshold of 27 days or more) fails here; compare each expected row.
    A corpus outside SC-001's window, or a key with no rows, is itself a
    problem."""
    registry = fh.load_registry() if registry is None else registry
    problems = []
    window = corpus.get("window") or {}
    if window.get("start") != SC001_START or not (corpus.get("now") or "").startswith(SC001_NOW_DAY)             or window.get("now") != corpus.get("now"):
        problems.append("SC-001: the corpus window is {0}, not {1} to {2}".format(
            window, SC001_START, SC001_NOW_DAY))
    if not expected.get("rows"):
        problems.append("SC-001: expected.json has no rows")
    now = fh.parse_time(corpus["now"])
    rows = fh.classify_all(registry, corpus["readings"], corpus.get("signals", {}), corpus["ctx"], now)
    got = {(r["feature"], r["stage"] or ""): r["state"] for r in rows}
    want = {(e["feature"], e.get("stage") or ""): e["state"] for e in expected.get("rows") or []}
    problems += ["SC-001: {0} is {1}, expected {2}".format(k, got.get(k), v) for k, v in sorted(want.items())
                 if got.get(k) != v]
    return problems


def self_check_sc001(directory):
    """The replay must fail its subject: an always-healthy classifier, a
    flipped key row and a corpus from another window are each noticed."""
    paths = [os.path.join(directory, n) for n in ("corpus.json", "expected.json")]
    if not all(os.path.exists(p) for p in paths):
        return []
    with open(paths[0], encoding="utf-8") as fp:
        corpus = json.load(fp)
    with open(paths[1], encoding="utf-8") as fp:
        expected = json.load(fp)
    problems = []
    saved = fh.classify_all
    fh.classify_all = lambda registry, *_a: [{"feature": e["name"], "stage": None, "state": "healthy"}
                                             for e in registry]
    try:
        if not sc001_replay(corpus, expected):
            problems.append("self-check: the SC-001 replay did not notice an always-healthy classifier")
    finally:
        fh.classify_all = saved
    for i, row in enumerate(expected["rows"]):
        flipped = copy.deepcopy(expected)
        flipped["rows"][i]["state"] = "unreadable" if row["state"] != "unreadable" else "healthy"
        if not sc001_replay(corpus, flipped):
            problems.append("self-check: the SC-001 replay did not notice {0} flipped to {1}".format(
                row["feature"], flipped["rows"][i]["state"]))
    moved = copy.deepcopy(corpus)
    moved["window"]["start"] = "2026-10-12T00:00:00Z"
    if not sc001_replay(moved, expected):
        problems.append("self-check: the SC-001 replay did not notice a corpus from another window")
    if not sc001_replay(corpus, {"rows": []}):
        problems.append("self-check: the SC-001 replay did not notice an empty key")
    # The registry once declared a 30-day board loop threshold, which SC-001's
    # "shorter than 27 days" rules out; the replay must catch it coming back.
    thirty = copy.deepcopy(fh.load_registry())
    for e in thirty:
        if e["name"] == "board loop":
            e["quiet_days"] = 30
    if not any("board loop" in p for p in sc001_replay(corpus, expected, thirty)):
        problems.append("self-check: the SC-001 replay did not notice a 30-day board loop quiet threshold")
    return problems


def check_capture_bounds():
    """T030: `until` caps every signal read for a past `now`, a current-state
    kind refuses to answer for a past day, and the build path (until=None)
    still keeps an occurrence after that day."""
    problems = []
    since, until = fh.parse_time("2026-10-14T00:00:00Z"), fh.parse_time("2026-11-12T23:59:59Z")
    pulls = [{"merged_at": "2026-11-20T00:00:00Z", "updated_at": "2026-11-20T00:00:00Z", "head": {"ref": "fix/a"}},
             {"merged_at": "2026-10-16T14:00:25Z", "updated_at": "2026-10-16T14:00:25Z", "head": {"ref": "fix/b"}}]
    releases = [{"published_at": "2026-11-15T00:00:00Z"}, {"published_at": "2026-11-11T00:00:00Z"}]
    calls = []
    # Issue 2 closed by triage after `now` and updated last; issue 1 closed in
    # the window and updated before that later close. The read must not stop
    # at issue 1 because of a close it will drop.
    close = fh.TRIAGE_CLOSE_COMMENT_PREFIX + fh.TRIAGE_CLOSE_GROUNDS[0] + ", see the run."
    closes = {2: "2026-11-20T00:00:00Z", 1: "2026-11-01T00:00:00Z"}

    def gh(path):
        calls.append(path)
        if path.startswith("search/issues?"):
            return {"incomplete_results": False,
                    "items": [{"number": 2, "updated_at": "2026-11-21T00:00:00Z"},
                              {"number": 1, "updated_at": "2026-11-02T00:00:00Z"}]}
        m = re.search(r"/issues/(\d+)/comments\?", path)
        if m:
            return [{"created_at": closes[int(m.group(1))], "body": close}]
        if "/pulls?" in path:
            return pulls if "page=1" in path else []
        if "/releases" in path:
            return releases
        if "/commits?sha=metrics&until=2026-11-12T23:59:59Z" in path:
            return [{"commit": {"committer": {"date": "2026-11-12T06:00:00Z"}}}]
        if "/commits/" in path:
            return {"commit": {"committer": {"date": "2026-11-23T06:00:00Z"}}}
        return []
    for signal, capped, live in (
            ({"kind": "merged_pr", "head_prefixes": ["fix/"]}, "2026-10-16T14:00:25Z", "2026-11-20T00:00:00Z"),
            ({"kind": "release"}, "2026-11-11T00:00:00Z", "2026-11-15T00:00:00Z"),
            ({"kind": "branch_commit", "branch": "metrics"}, "2026-11-12T06:00:00Z", "2026-11-23T06:00:00Z"),
            ({"kind": "triage_close"}, "2026-11-01T00:00:00Z", "2026-11-20T00:00:00Z")):
        for bound, want in ((until, capped), (None, live)):
            got = fh.read_signal(signal, "own/repo", since, gh, {}, until=bound)
            if got != want:
                problems.append("capture bound: {0} with until={1} gave {2}, expected {3}".format(
                    signal["kind"], bound, got, want))
    for kind in ("issue_updated", "issue_section"):
        try:
            fh.read_signal({"kind": kind, "title": "Board status", "marker": "x"}, "own/repo", since, gh, {},
                           until=until)
            problems.append("capture bound: {0} answered for a past day".format(kind))
        except RuntimeError:
            pass
    # A run re-run after `now` reports its later attempt; the capture refuses.
    now = until
    kept = {"a.yml": {"runs": [{"id": 1, "event": "push", "started_at": "2026-11-12T08:00:00Z",
                                "conclusion": "failure"}], "interval_hours": 24}}
    fh._runs_as_of(kept, now, None, "own/repo")
    if kept["a.yml"]["runs"] != [{"started_at": "2026-11-12T08:00:00Z", "conclusion": "failure"}]:
        problems.append("capture bound: runs kept {0}, not started_at and conclusion only".format(
            kept["a.yml"]["runs"]))
    rerun = {"a.yml": {"runs": [{"id": 1, "event": "push", "started_at": "2026-11-15T08:00:00Z",
                                 "conclusion": "success"}], "interval_hours": 24}}
    try:
        fh._runs_as_of(rerun, now, None, "own/repo")
        problems.append("capture bound: a run attempt started after now was recorded")
    except SystemExit:
        pass
    # A run started before `now` but finished after it was not completed at
    # `now`, so a build then could not have seen it; the capture drops it.
    inflight = {"a.yml": {"runs": [{"id": 1, "event": "push", "started_at": "2026-11-12T23:50:00Z",
                                    "updated_at": "2026-11-13T00:10:00Z", "conclusion": "failure"}],
                          "interval_hours": 24}}
    def jobs(done):
        def gh(path):
            if "/actions/runs/1/attempts/1/jobs?" not in path:
                raise RuntimeError("unexpected read {0}".format(path))
            return {"jobs": [{"completed_at": "2026-11-12T23:55:00Z"}, {"completed_at": done}]}
        return gh
    fh._runs_as_of(inflight, now, jobs("2026-11-13T00:10:00Z"), "own/repo")
    if inflight["a.yml"]["runs"]:
        problems.append("capture bound: a run still in progress at now was recorded as {0}".format(
            inflight["a.yml"]["runs"]))
    # A run finished before `now` whose `updated_at` GitHub moved later (a log
    # or artifact deletion) was complete at `now`: the capture keeps it, read
    # from its jobs' completion time, not dropped for its `updated_at` (#889).
    for label, done, want in (("finished before now, updated after", "2026-11-12T23:58:00Z", 1),
                              ("a job still running", None, 0)):
        bumped = {"a.yml": {"runs": [{"id": 1, "event": "push", "started_at": "2026-11-12T23:50:00Z",
                                      "updated_at": "2026-11-20T00:00:00Z", "run_attempt": 1,
                                      "conclusion": "failure"}], "interval_hours": 24}}
        fh._runs_as_of(bumped, now, jobs(done), "own/repo")
        if len(bumped["a.yml"]["runs"]) != want:
            problems.append("capture bound: a run {0} kept {1} runs, expected {2}".format(
                label, len(bumped["a.yml"]["runs"]), want))
    # `is:closed` is today's state: the search never asks for it (a backlog
    # tick sits on an open issue), and under `until` an issue open today with
    # a plain close in the window must raise.
    queries = []

    def reopened(path):
        if path.startswith("search/issues?"):
            queries.append(urllib.parse.unquote(path))
            return {"incomplete_results": False,
                    "items": [{"number": 3, "state": "open", "updated_at": "2026-11-21T00:00:00Z"}]}
        return [{"created_at": "2026-11-01T00:00:00Z", "body": close}]
    try:
        got = fh.read_signal({"kind": "triage_close"}, "own/repo", since, reopened, {}, until=until)
        problems.append("capture bound: a triage close on an issue reopened since gave {0}".format(got))
    except RuntimeError:
        pass
    if any("is:closed" in q for q in queries):
        problems.append("capture bound: the triage close search asked for today's is:closed under until")
    queries.clear()
    got = fh.read_signal({"kind": "triage_close"}, "own/repo", since, reopened, {})
    if got is not None:
        problems.append("triage close: a plain close on an issue open now counted in the build ({0})".format(got))
    if any("is:closed" in q for q in queries):
        problems.append("triage close: the build's search asks for is:closed, which hides the open "
                        "Maintenance backlog issue a line tick is posted on")
    problems += check_backlog_tick_closes(since, until)
    return problems


def check_backlog_tick_closes(since, until):
    """A triage close of a Maintenance-backlog line ticks the line and posts
    the close sentence on the backlog issue, which stays open, behind
    board-loop.yml's `Backlog line `X` ticked, not closed: ` opening (with or
    without a directed attribution between). It is a triage close in the
    build and in the capture alike (#889)."""
    problems = []
    tick = (fh.BACKLOG_TICK_COMMENT_PREFIX + "bl-0123abcd" + fh.BACKLOG_TICK_COMMENT_SUFFIX
            + fh.TRIAGE_CLOSE_COMMENT_PREFIX + fh.TRIAGE_CLOSE_GROUNDS[0] + ", with evidence")
    attributed = (fh.BACKLOG_TICK_COMMENT_PREFIX + "bl-4567cdef" + fh.BACKLOG_TICK_COMMENT_SUFFIX
                  + "Directed by a maintainer.\n\n" + fh.TRIAGE_CLOSE_COMMENT_PREFIX
                  + fh.TRIAGE_CLOSE_GROUNDS[-1] + ", with evidence")
    routed = fh.BACKLOG_TICK_COMMENT_PREFIX + "bl-89ab0123` routed to #5 -- not a close"
    for label, body, want in (("a backlog line tick", tick, "2026-11-01T00:00:00Z"),
                              ("an attributed backlog line tick", attributed, "2026-11-01T00:00:00Z"),
                              ("a backlog line routed, not closed", routed, None)):
        def backlog(path, body=body):
            if path.startswith("search/issues?"):
                if "is:closed" in urllib.parse.unquote(path):
                    return {"incomplete_results": False, "items": []}
                return {"incomplete_results": False,
                        "items": [{"number": 889, "state": "open", "updated_at": "2026-11-21T00:00:00Z"}]}
            return [{"created_at": "2026-11-01T00:00:00Z", "body": body}]
        for bound in (None, until):
            try:
                got = fh.read_signal({"kind": "triage_close"}, "own/repo", since, backlog, {}, until=bound)
            except RuntimeError as exc:
                got = "raised: {0}".format(exc)
            if got != want:
                problems.append("triage close: {0} on the open backlog issue (until={1}) gave {2}, "
                                "expected {3}".format(label, bound, got, want))
    with open(os.path.join(REPO, ".github", "workflows", "board-loop.yml"), encoding="utf-8") as fp:
        loop = fp.read()
    opening = "'{0}%s{1}%s'".format(fh.BACKLOG_TICK_COMMENT_PREFIX, fh.BACKLOG_TICK_COMMENT_SUFFIX)
    if opening not in loop:
        problems.append("board-loop.yml no longer ticks a backlog line with {0} "
                        "(BACKLOG_TICK_COMMENT_PREFIX/SUFFIX)".format(opening))
    return problems


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


def triage_close_grounds_reached(module):
    """The grounds `module.triage()` returns with outcome "closed", found by
    calling it with each evidence check stubbed to fire in turn (and none, to
    check the no-evidence path closes nothing). The module's own evidence
    checks are restored afterwards."""
    saved = (module.check_rate_limit, module.check_action_bump)
    grounds = set()
    with tempfile.TemporaryDirectory() as tmp:
        transcript = os.path.join(tmp, "transcript.jsonl")
        with open(transcript, "w", encoding="utf-8") as out:
            out.write("{}\n")
        issue = {"cited_run_url": "https://example.invalid/run/1", "cited_run_commit_sha": "0" * 40,
                 "cited_run_transcript_path": transcript, "cited_run_workflow_path": "x.yml",
                 "workflow_files": ["x.yml"], "agent_proposal": {}}
        try:
            for rate, bump in ((None, None), ({"stub": 1}, None), (None, {"stub": 1})):
                module.check_rate_limit = lambda _path, r=rate: r
                module.check_action_bump = lambda *_a, b=bump: b
                got = module.triage(dict(issue), issue["cited_run_url"])
                if got.get("outcome") == "closed":
                    grounds.add(got.get("ground"))
        finally:
            module.check_rate_limit, module.check_action_bump = saved
    return grounds


def check_board_status_updated_line():
    """issue_updated reads the board-status job's own Updated line; read it
    back from the renderer that writes it, so a change to that line's format
    fails here instead of making the board status feature read quiet."""
    import wc_board_status as bs
    body = bs.render({"now": "2026-11-20T06:31:00Z"})
    got = fh.board_status_updated_at(body)
    if got != "2026-11-20T06:31:00Z":
        return ["issue_updated: wc_board_status.render's Updated line reads back as {0}, "
                "expected 2026-11-20T06:31:00Z".format(got)]
    return []


def check_paged_signal_reads():
    """merged_pr and release page until the window cutoff, not a fixed page
    count (#889): a match past the old 3-page / 30-release limit is found, and
    the read stops at the first page that ends before the window."""
    problems = []
    since = fh.parse_time("2026-10-20T00:00:00Z")

    def busy(path):
        found = re.search(r"&page=(\d+)", path)
        page = int(found.group(1)) if found else 1
        if "/pulls?" in path:
            if page < 6:
                return [{"merged_at": None, "updated_at": "2026-11-15T00:00:00Z", "head": {"ref": "fix/x"}}] * 100
            if page == 6:
                return ([{"merged_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z",
                          "head": {"ref": "fix/late"}}]
                        + [{"merged_at": None, "updated_at": "2026-10-01T00:00:00Z", "head": {"ref": "fix/y"}}] * 99)
            problems.append("merged_pr: read page {0} after a page that ended before the window".format(page))
            return []
        if "/releases?" in path:
            if page == 1:
                return [{"published_at": "2026-11-10T00:00:00Z"}] * 100
            if page == 2:
                # A draft has no published_at and must not end the read.
                return ([{"published_at": None}, {"published_at": "2026-10-25T00:00:00Z"}]
                        + [{"published_at": "2026-10-01T00:00:00Z"}] * 98)
            problems.append("release: read page {0} after a page that reached before the window".format(page))
            return []
        return []
    for signal, want in (({"kind": "merged_pr", "head_prefixes": ["fix/"]}, "2026-11-01T00:00:00Z"),
                         ({"kind": "release"}, "2026-11-10T00:00:00Z")):
        try:
            got = fh.read_signal(signal, "own/repo", since, busy, {})
        except RuntimeError as exc:
            got = "raised: {0}".format(exc)
        if got != want:
            problems.append("{0}: a busy repository read {1}, expected {2}".format(signal["kind"], got, want))
    return problems


def check_shared_sources():
    """FR-003/FR-004 single home: triage grounds come from board_triage.py and
    switch values from wc_board_status._switch_on."""
    import board_triage
    import wc_board_status as bs
    problems = []
    if fh.TRIAGE_CLOSE_GROUNDS is not board_triage.TRIAGE_CLOSE_GROUNDS:
        problems.append("triage grounds are not imported from board_triage.py")
    # Drive board_triage.triage() itself down each close path rather than
    # match its source text (#889): the grounds it closes on are the grounds
    # the triage_close reader counts.
    closed = triage_close_grounds_reached(board_triage)
    if set(closed) != set(board_triage.TRIAGE_CLOSE_GROUNDS):
        problems.append("board_triage.triage() closes on grounds {0}, but TRIAGE_CLOSE_GROUNDS is {1}".format(
            sorted(closed), list(board_triage.TRIAGE_CLOSE_GROUNDS)))
    fake = types.SimpleNamespace(check_rate_limit=None, check_action_bump=None,
                                 triage=lambda issue, run: {"outcome": "closed", "ground": "new_ground"})
    if triage_close_grounds_reached(fake) != {"new_ground"}:
        problems.append("self-check: a triage() that closes on a new ground is not noticed")
    if re.search(r'"grounds"\s*:', json.dumps(fh.load_registry())):
        problems.append("registry holds a literal triage grounds list")
    if fh.TRIAGE_CLOSE_COMMENT_PREFIX is not board_triage.TRIAGE_CLOSE_COMMENT_PREFIX:
        problems.append("the triage close sentence is not imported from board_triage.py")
    if (fh.BACKLOG_TICK_COMMENT_PREFIX is not board_triage.BACKLOG_TICK_COMMENT_PREFIX
            or fh.BACKLOG_TICK_COMMENT_SUFFIX is not board_triage.BACKLOG_TICK_COMMENT_SUFFIX):
        problems.append("the backlog line tick opening is not imported from board_triage.py")
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


def on_schedule(*crons):
    """A minimal workflow whose on.schedule lists `crons` (as written, quoted or not)."""
    return "on:\n  schedule:\n" + "".join("    - cron: {0}\n".format(c) for c in crons)


def check_cron_forms_and_bounded_reads():
    """Unquoted and ranged cron, bounded triage and comment reads."""
    problems = []
    for text, want in ((on_schedule("0 */4 * * *"), 4),
                       (on_schedule("17 6 * * *   # daily"), 24),
                       (on_schedule('"0 9-17 * * *"'), 16),
                       (on_schedule('"0 0-23/6 * * *"'), 6),
                       (on_schedule('"0 1,9-11 * * *"'), 14),
                       (on_schedule('"0 5-5/2 * * *"'), 24),
                       (on_schedule('"0 5/6 * * *"'), 6)):
        try:
            got = fh.schedule_interval_hours(text)
        except ValueError as exc:
            got = "ValueError: {0}".format(exc)
        if got != want:
            problems.append("cron parsing: {0!r} gave {1}, expected {2}".format(text.strip(), got, want))
    for bad in (on_schedule('"0 25 * * *"'), on_schedule('"0 5-2 * * *"'), on_schedule('"0 */0 * * *"'),
                on_schedule('"0 5-2/2 * * *"')):
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
         "interval_hours": fh.schedule_interval_hours(on_schedule('"0 9-17 * * *"'))},
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


def check_schedule_and_comment_reads():
    """The schedule read takes only on.schedule, the not-running threshold has
    a floor and is never longer than the run read, and a long comment thread
    on one triage-close candidate is paged rather than raised on."""
    problems = []
    # A `cron:` line in a run: block or heredoc is not a schedule.
    wf = (on_schedule('"29 6 * * *"') + "jobs:\n  a:\n    steps:\n      - run: |\n"
          "          cat > w.yml <<'EOF'\n          - cron: \"0 * * * *\"\n          EOF\n")
    if fh.schedule_interval_hours(wf) != 24:
        problems.append("cron parsing: a cron line inside a run: block set the interval to {0}h".format(
            fh.schedule_interval_hours(wf)))
    if fh.schedule_interval_hours("on: push\njobs:\n  a:\n    steps:\n      - run: |\n"
                                  "          - cron: \"0 * * * *\"\n") is not None:
        problems.append("cron parsing: a workflow with no on.schedule read a cron from a run: step")
    # An hourly workflow is not "not running" after an ordinary schedule delay.
    now = fh.parse_time("2026-11-20T12:00:00Z")
    for hours_ago, want in ((3, "healthy"), (7, "not running")):
        state, _d = fh.classify_workflow(
            {"file": "x.yml", "cadence": "schedule"}, {"name": "f"},
            {"runs": [{"started_at": fh.fmt_time(now - datetime.timedelta(hours=hours_ago)),
                       "conclusion": "success"}], "interval_hours": 1}, {}, now)
        if state != want:
            problems.append("an hourly cron with a run {0} h ago classed {1!r}, expected {2}".format(
                hours_ago, state, want))
    # A monthly cron whose last run is older than the 31-day window but inside
    # twice its interval: the run read must reach back to the threshold, so it
    # is not "not running", and the run before the window counts for nothing
    # else, so it is idle (FR-017, spec 126 scenario 6), not healthy and not
    # failing (#889). Past the threshold it is "not running".
    def monthly_at(days_ago, conclusion="success"):
        last = fh.fmt_time(now - datetime.timedelta(days=days_ago))

        def monthly(path):
            m = re.search(r"created=([0-9TZ:-]+)\.\.", path)
            if m:
                runs = ([{"id": 1, "event": "schedule", "conclusion": conclusion, "run_started_at": last,
                          "created_at": last}] if m.group(1) <= last else [])
                return {"total_count": len(runs), "workflow_runs": runs}
            return []
        return monthly
    entry = [{"name": "f", "workflows": [{"file": "m.yml", "cadence": "schedule"}]}]
    for days_ago, conclusion, want in ((45, "success", "idle"), (45, "failure", "idle"),
                                       (70, "success", "not running")):
        readings, signals, ctx = fh.collect(entry, "own/repo", now, gh=monthly_at(days_ago, conclusion),
                                            environ={}, read_text=lambda _n: on_schedule('"0 6 1 * *"'))
        rows = fh.classify_all(entry, readings, signals, ctx, now)
        if rows[0]["state"] != want:
            problems.append("a monthly cron whose only run ({0}) was {1} days ago classed {2!r}, expected "
                            "{3}".format(conclusion, days_ago, rows[0]["state"], want))
    readings, signals, ctx = fh.collect(entry, "own/repo", now, gh=monthly_at(45), environ={},
                                        read_text=lambda _n: on_schedule('"0 6 1 * *"'))
    if not fh.classify_all(entry, readings, signals, ctx, now)[0]["last_run"]:
        problems.append("a monthly cron that ran 45 days ago lost its last run date")
    # One triage-close candidate with a full page of other comments: the close
    # on its second page is found, not a truncation error.
    close = fh.TRIAGE_CLOSE_COMMENT_PREFIX + fh.TRIAGE_CLOSE_GROUNDS[0] + ", see the run."

    def long_thread(path):
        if path.startswith("search/issues"):
            return {"incomplete_results": False, "items": [{"number": 7, "updated_at": "2026-11-19T00:00:00Z"}]}
        if "/issues/7/comments" in path:
            if path.endswith("&page=1"):
                return [{"body": "chatter", "created_at": "2026-11-10T00:00:00Z"}] * 100
            if path.endswith("&page=2"):
                return [{"body": close, "created_at": "2026-11-18T00:00:00Z"}]
        return []
    try:
        got = fh.read_signal({"kind": "triage_close"}, "own/repo", fh.parse_time("2026-10-20T00:00:00Z"),
                             long_thread, {})
    except RuntimeError as exc:
        got = "RuntimeError: {0}".format(exc)
    if got != "2026-11-18T00:00:00Z":
        problems.append("triage_close on a candidate with 100+ comments: got {0}, expected "
                        "2026-11-18T00:00:00Z".format(got))
    # The same for issue_or_comment: a labeled issue with a full page of
    # comments is paged, and the newest comment on its second page counts.

    def long_labeled(path):
        if "/issues?state=all" in path:
            return [{"number": 8, "created_at": "2026-11-01T00:00:00Z"}]
        if "/issues/8/comments" in path:
            if path.endswith("&page=1"):
                return [{"created_at": "2026-11-10T00:00:00Z"}] * 100
            if path.endswith("&page=2"):
                return [{"created_at": "2026-11-19T00:00:00Z"}]
        return []
    try:
        got = fh.read_signal({"kind": "issue_or_comment", "label_name": "x"}, "own/repo",
                             fh.parse_time("2026-10-20T00:00:00Z"), long_labeled, {})
    except RuntimeError as exc:
        got = "RuntimeError: {0}".format(exc)
    if got != "2026-11-19T00:00:00Z":
        problems.append("issue_or_comment on a labeled issue with 100+ comments: got {0}, expected "
                        "2026-11-19T00:00:00Z".format(got))
    return problems


def check_multi_workflow_callouts():
    """A feature with several workflows: its failing or not-running call-out
    quotes the dates of the workflow in that state, not a healthy sibling's
    (#889)."""
    problems = []
    now = fh.parse_time("2026-11-20T12:00:00Z")
    ago = lambda hours: fh.fmt_time(now - datetime.timedelta(hours=hours))  # noqa: E731
    entry = {"name": "f", "workflows": [{"file": "a.yml", "cadence": "schedule"},
                                        {"file": "b.yml", "cadence": "schedule"}]}
    ok = {"runs": [{"started_at": ago(1), "conclusion": "success"},
                   {"started_at": ago(2), "conclusion": "failure"}], "interval_hours": 1}
    stopped = {"runs": [{"started_at": ago(30), "conclusion": "success"}], "interval_hours": 1}
    failing = {"runs": [{"started_at": ago(h), "conclusion": "failure"} for h in (3, 4, 5)]
               + [{"started_at": ago(50), "conclusion": "success"}], "interval_hours": 1}
    for b, want in ((stopped, "- `f` — not running: no run since {0}".format(fh.day(ago(30)))),
                    (failing, "- `f` — failing: last success {0}, last failure {1}".format(
                        fh.day(ago(50)), fh.day(ago(3))))):
        rows = fh.classify_feature(entry, {"a.yml": ok, "b.yml": b}, None, {}, now)
        got = fh._callout(rows[0])
        if got != want:
            problems.append("multi-workflow call-out: got {0!r}, expected {1!r}".format(got, want))
    return problems


def check_cron_truncation_and_shortening():
    """Cron parsing, truncated reads, shortened-section detection."""
    problems = []
    wf = "on:\n  schedule:\n    - cron: '0 */6 * * *'\n    # - cron: \"0 1 * * *\"\n    - cron: \"0 3,15 * * *\"\n"
    if fh.schedule_interval_hours(wf) != 6:
        problems.append("cron parsing: expected the smallest interval 6, got {0}".format(
            fh.schedule_interval_hours(wf)))
    if fh.schedule_interval_hours('on:\n  schedule:\n    - cron: "0 1 * * *"\n') != 24:
        problems.append("cron parsing: a daily cron is not 24 hours")
    try:
        fh.schedule_interval_hours(on_schedule('"bad"'))
        problems.append("cron parsing: an unparseable cron did not raise")
    except ValueError:
        pass
    try:
        fh._pages(lambda _p: [{}] * 100, "x?a=1", 2)
        problems.append("_pages: a full last page did not raise")
    except RuntimeError:
        pass
    shortened = ("<!-- wing-commander-feature-health -->\n**Feature health** — built 2026-11-20 06:38Z\n\n"
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


def check_section_built_own_marker(registry):
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


def check_final_pr_selector(registry, finalize_text, finalize_re=None):
    """The lifecycle signal counts only final PRs: its `spec/` head match is
    narrowed by a title prefix finalize.yml itself writes, so a `spec/` PR
    that is not final cannot make a stalled lifecycle read healthy (#889).
    The proof list reads the same title (wc_proof_list.FINALIZE_RE), so each
    prefix must also be one that reader accepts: a prefix moved with a new
    finalize.yml title cannot leave the proof list reading the old one."""
    if finalize_re is None:
        finalize_re = wc_proof_list.FINALIZE_RE
    problems = []
    sig = next((e.get("signal") or {}) for e in registry if e["name"] == "lifecycle")
    titles = sig.get("title_prefixes") or []
    if sig.get("kind") != "merged_pr" or not titles:
        problems.append("lifecycle signal: a merged_pr with title_prefixes is required; any merged "
                        "`spec/` PR would count as a final PR")
    for t in titles:
        if '--title "{0}'.format(t) not in finalize_text:
            problems.append("lifecycle signal: title prefix {0!r} is not the title finalize.yml opens the "
                            "final PR with".format(t))
        if not finalize_re.match("{0}A feature (#1)".format(t)):
            problems.append("lifecycle signal: title prefix {0!r} is not a final PR title the proof list's "
                            "wc_proof_list.FINALIZE_RE reads".format(t))
    return problems


def check_check_names(source):
    """This gate's checks are named for what they check, never for the review
    round that added them (#889)."""
    return ["check {0}() is named for a review round; name it by subject".format(m)
            for m in re.findall(r"^def (check_\w*round\w*)\(", source, re.M)]


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
    problems += check_cron_truncation_and_shortening()
    problems += check_cron_forms_and_bounded_reads()
    problems += check_section_built_own_marker(registry)
    problems += check_board_status_updated_line()
    problems += check_paged_signal_reads()
    problems += check_schedule_and_comment_reads()
    problems += check_multi_workflow_callouts()
    with open(os.path.join(REPO, ".github", "workflows", "finalize.yml"), encoding="utf-8") as fp:
        finalize_text = fp.read()
    problems += check_final_pr_selector(registry, finalize_text)
    unnarrowed = copy.deepcopy(registry)
    for e in unnarrowed:
        if e["name"] == "lifecycle":
            e["signal"].pop("title_prefixes", None)
    if not check_final_pr_selector(unnarrowed, finalize_text):
        problems.append("self-check: a lifecycle signal with no title_prefixes is not noticed")
    if not check_final_pr_selector(registry, finalize_text.replace('--title "Finalize: ', '--title "Final: ')):
        problems.append("self-check: a finalize.yml title that drifted from title_prefixes is not noticed")
    if not check_final_pr_selector(registry, finalize_text, re.compile(r"^Final:.*\(#(\d+)\)\s*$")):
        problems.append("self-check: a title prefix the proof list's FINALIZE_RE does not read is not noticed")
    with open(os.path.abspath(__file__), encoding="utf-8") as fp:
        problems += check_check_names(fp.read())
    if check_check_names("def check_review_round_two():\n") == []:
        problems.append("check_check_names self-test: a round-named check was not noticed")
    problems += check_capture_bounds()
    real, note = check_sc001(os.path.join(FIXTURES, "sc001"), EXEMPT_SC001_PENDING)
    problems += real + self_check(fx) + self_check_sc001(os.path.join(FIXTURES, "sc001"))
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
