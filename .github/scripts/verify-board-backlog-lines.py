#!/usr/bin/env python3
"""Gate — board_backlog_lines.py parses, selects and annotates Maintenance
backlog lines exactly as the fixtures under
.github/scripts/tests/board-backlog-lines/ say (specs/121-board-backlog-line-items,
FR-019).

    python3 .github/scripts/verify-board-backlog-lines.py
    python3 .github/scripts/verify-board-backlog-lines.py --self-test
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_backlog_lines as bbl  # noqa: E402

FIXTURES = os.path.join(HERE, "tests", "board-backlog-lines", "*.json")
LINE_ENV = "BOARD_LINE_ID"  # board_item_marker.LINE_ENV

OPS = {
    "claim": bbl.claim,
    "annotate": bbl.annotate,
    "tick": bbl.tick,
    "clear": bbl.clear_note,
    "note_proof": bbl.note_proof,
}


def _subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _subset(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(expected) == len(actual)
                and all(_subset(e, a) for e, a in zip(expected, actual)))
    return expected == actual


def run_case(case):
    """Returns an error string or None."""
    op = case["op"]
    body = case.get("body", "")
    if op == "parse":
        actual = bbl.parse_lines(body)
        return None if _subset(case["expect"], actual) else "parse: got {0!r}".format(actual)
    if op == "select":
        actual = bbl.select_line(body)
        return None if _subset(case["expect"], actual) else "select: got {0!r}".format(actual)
    if op == "resolve":
        actual = list(bbl.resolve_backlog(case["issues"], case["bot"], case.get("maintainers", ())))
        return None if actual == case["expect"] else "resolve: got {0!r}".format(actual)
    if op == "gate":
        actual = list(bbl.selection_gate(case["env"]))
        return None if actual == case["expect"] else "gate: got {0!r}".format(actual)
    if op == "title":
        actual = bbl.title_for(case["text"])
        if len(actual) > 200 or ("max_len" in case and len(actual) > case["max_len"]):
            return "title too long: {0}".format(len(actual))
        if case.get("no_closing") and bbl.closing_keyword_hits(actual, "", []):
            return "title carries a closing keyword: {0!r}".format(actual)
        return None if actual.startswith(case["expect_prefix"]) else "title: got {0!r}".format(actual)
    if op == "branch":
        actual = bbl.branch_for(case["issue"], case["line_id"])
        return None if actual == case["expect"] else "branch: got {0!r}".format(actual)
    if op == "closing":
        actual = bbl.closing_keyword_hits(case["title"], case["body"], case["commits"])
        return None if bool(actual) == case["expect_hit"] else "closing: got {0!r}".format(actual)
    if op == "render":
        actual = bbl.render_line_text_for_body(case["text"])
        return None if not bbl.closing_keyword_hits("", actual, []) else "render: keyword survived {0!r}".format(actual)
    if op == "marker":
        import board_item_marker as bim
        text = bim.write_marker("fix", 1, None, case["branch"], "abc", line=case.get("line"))
        comments = [{"created_at": "2026-01-01T00:00:00Z", "body": text,
                     "user": {"login": case["bot"], "type": "Bot"}}]
        found = bim.find_latest_marker(comments, case["bot"])
        read_back = found[1].get("line") if found else None
        issue_path = bim.read_marker(comments, case["bot"])
        if read_back != case.get("line"):
            return "marker: line round trip got {0!r}".format(read_back)
        if (issue_path is None) != case["issue_path_ignores"]:
            return "marker: issue path read {0!r}".format(issue_path)
        matching = bim.find_latest_marker_matching(comments, case["bot"], lambda m: True)
        if (matching is None) != case["issue_path_ignores"]:
            return "marker: matching reader read {0!r}".format(matching)
        return None
    if op == "context":
        fn = getattr(bbl, "line_context", None)
        # The run list is this repository's ($GITHUB_REPOSITORY) alone: a
        # case names it, or runs with none (never CI's own value).
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        if case.get("repository"):
            os.environ["GITHUB_REPOSITORY"] = case["repository"]
        try:
            body = body.replace("{PAD}", "x" * case.get("pad", 0))
            actual = fn(body, case["issue"], case["line_id"]) if fn else "<no line_context()>"
        finally:
            os.environ.pop("GITHUB_REPOSITORY", None)
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved
        if case.get("expect_none"):
            return None if actual is None else "context: expected None, got {0!r}".format(actual)
        errors = ["context lacks {0!r}".format(n) for n in case["contains"] if n not in (actual or "")]
        errors += ["context carries {0!r}".format(n) for n in case.get("absent", []) if n in (actual or "")]
        if "cited_run" in case or "unfenced_absent" in case:
            # FR-012: triage's evidence read sees the line's run; FR-008:
            # none of the line's prose leaves the fence for it.
            import board_triage
            cited = case.get("cited_run")
            if cited:
                got = board_triage.find_cited_run(actual or "", cited["repository"])
                if got != cited["expect"]:
                    errors.append("triage's find_cited_run() read {0!r} from the line context, "
                                  "want {1!r}".format(got, cited["expect"]))
            unfenced = board_triage._unquoted_unfenced(actual or "")
            errors += ["line prose {0!r} is outside the fence".format(n)
                       for n in case.get("unfenced_absent", []) if n in unfenced]
        return "; ".join(errors) or None
    if op == "pr-ref":
        return run_pr_ref(case)
    if op == "pre-push":
        return run_pre_push(case)
    if op == "keyword-hold":
        return run_keyword_hold(case)
    if op == "route-line":
        return run_route_line(case)
    if op == "line-item":
        return run_line_item(case)
    if op == "stall":
        return run_stall(case)
    if op == "line-readers":
        return run_line_readers(case)
    if op == "chain":
        for number, step in enumerate(case["steps"]):
            new_body = OPS[step["op"]](body, *step["args"])
            if new_body != case["expect_after"][number]:
                return "step {0} ({1}): got {2!r}".format(number, step["op"], new_body)
            if new_body is not None:
                body = new_body
        return None
    return "unknown op {0!r}".format(op)


class _Env:
    """Sets BOARD_LINE_ID (board_item_marker.LINE_ENV) for one case."""

    def __init__(self, line_id):
        self.line_id = line_id

    def __enter__(self):
        self.saved = os.environ.get(LINE_ENV)
        if self.line_id is None:
            os.environ.pop(LINE_ENV, None)
        else:
            os.environ[LINE_ENV] = self.line_id

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop(LINE_ENV, None)
        else:
            os.environ[LINE_ENV] = self.saved


def run_stall(case):
    """The stall rule under BOARD_LINE_ID (specs/121 FR-014/FR-016/FR-017):
    a line is held by its annotation, the backlog issue is never labelled,
    and a line that is gone stands down with a report on the backlog."""
    import board_backlog_edit as bbe
    import board_item_marker as bim
    store = {"body": case["body"]}
    labelled, comments = [], []
    saved = (bbe.gh_fetch, bbe.gh_write, getattr(bbe, "gh_comment", None))
    bbe.gh_fetch = lambda _issue: store["body"]
    bbe.gh_write = lambda _issue, body: store.__setitem__("body", body)
    bbe.gh_comment = lambda issue, body: comments.append(body)

    class _Proc:
        returncode = 0

    def run_label(cmd, **_kw):
        labelled.append(cmd)
        return _Proc()

    # A per-run file, never a fixed path: the gate and its --self-test run
    # in parallel under run-local-gates.py --jobs, and a shared path let one
    # truncate the other's summary mid-case.
    import tempfile
    fd, summary = tempfile.mkstemp(prefix="bbl-stall-summary-", suffix=".txt")
    os.close(fd)
    saved_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    os.environ["GITHUB_STEP_SUMMARY"] = summary
    saved_repo = os.environ.get("GITHUB_REPOSITORY")
    os.environ["GITHUB_REPOSITORY"] = "o/r"
    open(summary, "w").close()
    import contextlib
    import io
    try:
        with _Env(case.get("line_id")), contextlib.redirect_stderr(io.StringIO()):
            ok = bim.add_stalled_label(889, "board:stalled", run=run_label)
            if ok:
                bim.record_stall_summary(889, case.get("from_step", "fix (gate suite red)"))
            marker = bim.write_marker("stalled", 0, None, None, None)
    finally:
        bbe.gh_fetch, bbe.gh_write, bbe.gh_comment = saved
        for key, value in (("GITHUB_STEP_SUMMARY", saved_summary), ("GITHUB_REPOSITORY", saved_repo)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    errors = []
    if ok != case["expect_ok"]:
        errors.append("add_stalled_label returned {0!r}".format(ok))
    if bool(labelled) != case["expect_labelled"]:
        errors.append("labelled the issue: {0!r}".format(labelled))
    if "expect_body" in case and store["body"] != case["expect_body"]:
        errors.append("body {0!r}".format(store["body"]))
    if bool(comments) != case.get("expect_report", False):
        errors.append("backlog report {0!r}".format(comments))
    line_key = '"line": "{0}"'.format(case["line_id"]) if case.get("line_id") else '"line"'
    if (line_key in marker) != bool(case.get("line_id")):
        errors.append("marker line key: {0!r}".format(marker))
    with open(summary, encoding="utf-8") as fh:
        text = fh.read()
    os.unlink(summary)
    for needle in case.get("summary_contains", []):
        if needle not in text:
            errors.append("summary lacks {0!r}: {1!r}".format(needle, text))
    return "; ".join(errors) or None


def run_pr_ref(case):
    """FR-017/FR-021: a line-born PR's body names its line by the
    non-closing reference; an issue-born `Fixes #N` body names none."""
    fn = getattr(bbl, "pr_line", None)
    if fn is None:
        return "no pr_line()"
    errors = []
    got = fn(case["pr_body"])
    want = tuple(case["expect"]) if case["expect"] else None
    if got != want:
        errors.append("pr_line: got {0!r}, want {1!r}".format(got, want))
    if "text" in case:
        body = bbl.pr_body(889, "bl-0a1b2c3d", case["text"], "fix/889-bl-0a1b2c3d", "abc")
        if bbl.closing_keyword_hits("", body, []):
            errors.append("pr_body carries a closing keyword: {0!r}".format(body))
        if bbl.pr_line(body) != (889, "bl-0a1b2c3d"):
            errors.append("pr_body does not name its line: {0!r}".format(body))
    return "; ".join(errors) or None


def run_pre_push(case):
    """FR-017 before a push: the line's PR title and the branch's commits."""
    fn = getattr(bbl, "pre_push_check", None)
    if fn is None:
        return "no pre_push_check()"
    got = fn(889, case["line_id"], case["body"], case["commits"])
    errors = []
    if bool(got["hits"]) != case["expect_hit"]:
        errors.append("hits {0!r}".format(got["hits"]))
    if "title_prefix" in case and not (got["title"] or "").startswith(case["title_prefix"]):
        errors.append("title {0!r}".format(got["title"]))
    return "; ".join(errors) or None


class _Proc:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def _stub_backlog(store, comments):
    import board_backlog_edit as bbe
    saved = (bbe.gh_fetch, bbe.gh_write, getattr(bbe, "gh_comment", None))
    bbe.gh_fetch = lambda _issue: store["body"]
    bbe.gh_write = lambda _issue, body: store.__setitem__("body", body)
    bbe.gh_comment = lambda issue, body: comments.append(body)
    return saved


def _unstub_backlog(saved):
    import board_backlog_edit as bbe
    bbe.gh_fetch, bbe.gh_write, bbe.gh_comment = saved


def run_keyword_hold(case):
    """FR-017 refusal: a hit holds the line through the stall rule (never a
    label on the backlog issue) and posts the refusal; a clean branch is
    "clear" with nothing written."""
    import contextlib
    import io
    fn = getattr(bbl, "keyword_hold", None)
    if fn is None:
        return "no keyword_hold()"
    store, notes, calls = {"body": case["body"]}, [], []

    def run(cmd, **_kw):
        calls.append(cmd)
        return _Proc()

    saved = _stub_backlog(store, notes)
    try:
        with _Env(case["line_id"]), contextlib.redirect_stderr(io.StringIO()):
            got = fn(889, case["line_id"], "fix", "fix/889-" + case["line_id"], "abc",
                     run=run, commits=case["commits"])
    finally:
        _unstub_backlog(saved)
    errors = []
    if got != case["expect"]:
        errors.append("result {0!r}".format(got))
    if any("--add-label" in cmd for cmd in calls):
        errors.append("labelled the backlog issue: {0!r}".format(calls))
    if "expect_body" in case and store["body"] != case["expect_body"]:
        errors.append("body {0!r}".format(store["body"]))
    posted = [cmd for cmd in calls if cmd[:3] == ["gh", "issue", "comment"]]
    if bool(posted) != (case["expect"] == "held"):
        errors.append("refusal comment {0!r}".format(posted))
    return "; ".join(errors) or None


def run_route_line(case):
    """FR-013: a spec-shaped line points at its proposal; the backlog issue
    is never closed or labelled, and a gone line refuses."""
    import contextlib
    import io
    import board_backlog_edit as bbe
    import board_duplicate_disposition as bdd
    if not hasattr(bdd, "route_line"):
        return "no board_duplicate_disposition.route_line()"
    store, notes, calls = {"body": case["body"]}, [], []

    def run(cmd, **_kw):
        calls.append(cmd)
        return _Proc()

    def edit(issue, apply_fn, verify):
        return bbe.edit(issue, apply_fn, verify, fetch=lambda _i: store["body"],
                        write=lambda _i, b: store.__setitem__("body", b))

    saved = _stub_backlog(store, notes)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ok = bdd.route_line(889, case["line_id"], 1210, "https://example.test/issues/1210",
                                "Routed", repository="o/r", run=run, edit=edit)
    finally:
        _unstub_backlog(saved)
    errors = []
    if ok != case["expect_ok"]:
        errors.append("route_line returned {0!r}".format(ok))
    if store["body"] != case["expect_body"]:
        errors.append("body {0!r}".format(store["body"]))
    if any("close" in cmd or "--add-label" in cmd or "PATCH" in cmd for cmd in calls):
        errors.append("touched the backlog issue's state or labels: {0!r}".format(calls))
    if ok and not any('"line": "{0}"'.format(case["line_id"]) in " ".join(cmd) for cmd in calls):
        errors.append("no line-keyed record comment: {0!r}".format(calls))
    if bool(notes) != (not case["expect_ok"]):
        errors.append("backlog report {0!r}".format(notes))
    return "; ".join(errors) or None


def run_line_item(case):
    """board_backlog_lines.decide_line_item() over a fixture request; the
    backlog comments are built from (step, line) pairs as loop markers."""
    import board_item_marker as bim
    fn = getattr(bbl, "decide_line_item", None)
    if fn is None:
        return "no decide_line_item()"
    base = {
        "tracking_issues": [{"number": 889, "title": "Maintenance backlog (one tracking issue)",
                             "labels": [{"name": "disposition:tracking"}], "state": "OPEN",
                             "author": {"login": "owner"}, "authorAssociation": "OWNER",
                             "body": case["body"]}],
        "bot_login": "bot[bot]", "issue_selected": False, "switch": "true", "paused": "false",
        "constitution_text": "### X. Bounded autonomy\nA Maintenance backlog line is an entry.\n### XI. Next\n",
    }
    base.update(case.get("request", {}))
    base["tracking_issues"] = base["tracking_issues"] + case.get("extra_issues", [])
    base["comments"] = [
        {"created_at": "2026-01-0{0}T00:00:00Z".format(n + 1),
         "body": bim.write_marker(entry[0], 0, entry[2] if len(entry) > 2 else None, None, None,
                                  line=entry[1]),
         "user": {"login": base["bot_login"], "type": "Bot"}}
        for n, entry in enumerate(case.get("markers", []))]
    actual = fn(base)
    want = dict(case["expect"])
    errors = []
    if want.pop("line_id_minted", False):
        if not re.fullmatch(r"bl-[0-9a-f]{8}", actual.get("line_id") or ""):
            errors.append("minted id {0!r}".format(actual.get("line_id")))
        actual = dict(actual, line_id=None)
    for key, value in want.items():
        if actual.get(key) != value:
            errors.append("{0}: got {1!r}, want {2!r}".format(key, actual.get(key), value))
    return "; ".join(errors) or None


def run_line_readers(case):
    """Issue-path marker readers under BOARD_LINE_ID read only that line's
    markers; with it unset they skip every line marker (specs/121 D5)."""
    import board_item_marker as bim
    comments = []
    for number, marker in enumerate(case["markers"]):
        line = marker.get("line")
        text = bim.write_marker(marker["step"], 0, None, None, None, line=line or None) if line else (
            "<!-- wing-commander-board-item: {0} -->".format(json.dumps(
                {"step": marker["step"], "round": 0, "pr": None, "branch": None, "base_sha": None})))
        comments.append({"created_at": "2026-01-0{0}T00:00:00Z".format(number + 1), "body": text,
                         "user": {"login": "bot[bot]", "type": "Bot"}})
    errors = []
    for line_id, expect in case["expect"].items():
        with _Env(None if line_id == "-" else line_id):
            got = bim.read_marker(comments, "bot[bot]")
            matching = bim.find_latest_marker_matching(comments, "bot[bot]", lambda m: True)
        step = got.get("step") if got else None
        mstep = matching[1].get("step") if matching else None
        if step != expect or mstep != expect:
            errors.append("{0}: read {1!r}/{2!r}, want {3!r}".format(line_id, step, mstep, expect))
    for branch, line_id, want in case.get("branches", []):
        if getattr(bim, "is_line_branch", lambda *a: None)(branch, 889, line_id) != want:
            errors.append("is_line_branch({0!r}, {1!r}) != {2}".format(branch, line_id, want))
    return "; ".join(errors) or None


ISSUE_CONTEXT = os.path.join(os.path.dirname(HERE), "actions", "wing-commander-issue-context", "action.yml")


def issue_context_wiring():
    """The issue-context composite stages a line only through its
    line-id-gated step, and its issue path is skipped only then (FR-007,
    FR-020: with line-id unset the composite is unchanged)."""
    with open(ISSUE_CONTEXT, encoding="utf-8") as fh:
        text = fh.read()
    errors = []
    if "      id: fetch\n      if: inputs.line-id == ''\n" not in text:
        errors.append("the trust-filter step is not gated on line-id being unset")
    if "      id: line\n      if: inputs.line-id != ''\n" not in text:
        errors.append("the line step is not gated on line-id being set")
    if 'board_backlog_lines.py" --line-context' not in text:
        errors.append("the line step does not stage board_backlog_lines.line_context()")
    return errors


BOARD_LOOP = os.path.join(os.path.dirname(HERE), "workflows", "board-loop.yml")
LINE_JOB_ENV = "${{ needs.select.outputs.line-id }}"
LINE_JOBS = ("triage", "route", "fix-agent", "fix", "review", "review-fixup-publish", "readiness", "merge")
LINE_GUARD = 'if [ -n "${BOARD_LINE_ID:-}" ]'


def unguarded_closes(run_text):
    """Lines of a run: block that close the item issue without a backlog
    line guard (FR-017, SC-005): a close must sit in the `else` arm of
    `if [ -n "${BOARD_LINE_ID:-}" ]`, after such a block that exits, or
    behind `[ -n "${BOARD_LINE_ID:-}" ] ||` on its own line."""
    lines = run_text.split("\n")
    bad = []
    for number, line in enumerate(lines):
        if "gh issue close" not in line or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith('[ -n "${BOARD_LINE_ID:-}" ] ||'):
            continue
        indent = len(line) - len(line.lstrip())
        guarded = False
        depth_else = None
        for back in range(number - 1, -1, -1):
            text = lines[back]
            stripped = text.strip()
            ind = len(text) - len(text.lstrip())
            if ind < indent and stripped == "else":
                depth_else = ind
            if stripped.startswith(LINE_GUARD):
                if depth_else is not None and ind == depth_else:
                    guarded = True
                    break
                block = "\n".join(lines[back:number])
                if ind <= indent and "exit 0" in block and "\n" + " " * ind + "fi" in block:
                    guarded = True
                    break
        if not guarded:
            bad.append(line.strip())
    return bad


def board_loop_wiring(path=BOARD_LOOP):
    """specs/121 T034 and FR-020's gating, over board-loop.yml itself."""
    import yaml
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    jobs = doc.get("jobs") or {}
    errors = []
    for name in LINE_JOBS:
        if (jobs.get(name, {}).get("env") or {}).get("BOARD_LINE_ID") != LINE_JOB_ENV:
            errors.append("job {0} does not carry BOARD_LINE_ID from select's line-id".format(name))
    if (jobs.get("prove", {}).get("env") or {}).get("BOARD_LINE_ID") != "${{ needs.prove-gate.outputs.line-id }}":
        errors.append("job prove does not carry BOARD_LINE_ID from prove-gate's line-id")
    if "line-id" not in (jobs.get("select", {}).get("outputs") or {}):
        errors.append("select has no line-id output")
    for job_name, job in jobs.items():
        for step in job.get("steps") or []:
            where = "{0}/{1}".format(job_name, step.get("name") or step.get("id"))
            run = step.get("run") or ""
            for line in unguarded_closes(run):
                errors.append("{0} closes the item issue with no backlog-line guard: {1}".format(where, line))
            for line in run.split("\n"):
                code = line.split(" #", 1)[0]
                if "gh issue edit" in code and not line.strip().startswith("#"):
                    errors.append("{0} edits an issue directly -- a line's backlog issue must never be "
                                  "labelled or retitled (FR-017): {1}".format(where, line.strip()))
                if '--add-label "board:stalled"' in code and not any(
                        helper in code for helper in ("board_item_marker.py", "board_workflow_scope_hold.py", "stall_args=")):
                    errors.append("{0} labels board:stalled outside the line-aware stall rule: {1}".format(
                        where, line.strip()))
                if '"Fix #$ISSUE_NUMBER: ' in code and LINE_GUARD not in run:
                    errors.append("{0} titles a PR from the item issue with no line branch".format(where))
            uses = step.get("uses") or ""
            with_ = step.get("with") or {}
            if (uses.endswith("wing-commander-issue-context")
                    and "needs.select.outputs.issue-number" in str(with_.get("issue-number"))
                    and with_.get("line-id") != LINE_JOB_ENV):
                errors.append("{0} reads the item through issue-context without its line-id".format(where))
            if step.get("id") == "keyword-hold" and "env.BOARD_LINE_ID != ''" not in str(step.get("if")):
                errors.append("{0} is not gated on a line item (FR-020)".format(where))
    decide = next((st for st in jobs.get("prove", {}).get("steps") or [] if st.get("id") == "decide"), {})
    if 'if target == "board-loop.yml" and not os.environ.get("BOARD_LINE_ID"):' not in (decide.get("run") or ""):
        errors.append("prove's decide step can aim a directed run at the backlog issue for a line")
    # FR-020/FR-023: the switch gates new claims only -- select's line step
    # is its one reader, so a merge's tick and prove entry never wait on it.
    for job_name, job in jobs.items():
        for step in job.get("steps") or []:
            if "WING_COMMANDER_BOARD_BACKLOG_LINES" in json.dumps(step) and not (
                    job_name == "select" and step.get("id") == "line"):
                errors.append("{0}/{1} reads the backlog-lines switch; only select's line step "
                              "may (FR-020)".format(job_name, step.get("name")))
    line_step = next((st for st in jobs.get("select", {}).get("steps") or [] if st.get("id") == "line"), None)
    if line_step is None:
        errors.append("select has no `line` step")
    elif line_step.get("continue-on-error") is not True:
        errors.append("select's line step can fail the select job while the feature is dark (FR-020)")
    return errors


def run_link_single_home(path=os.path.join(HERE, "board_backlog_lines.py")):
    """CLAUDE.md "Shared logic has exactly one home": the run-link pattern
    lives in board_triage.run_url_pattern(); board_backlog_lines.py must
    not carry a copy of its own (found by the code review of #1131)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if re.search(r"actions/runs", text):
        return ["board_backlog_lines.py carries its own run-link pattern -- use "
                "board_triage.run_url_pattern()"]
    return []


def run(fixtures=None, verbose=True):
    failures = 0
    paths = sorted(glob.glob(FIXTURES)) if fixtures is None else fixtures
    if not paths:
        print("::error::verify-board-backlog-lines: no fixtures found")
        return 1
    if fixtures is None:
        for error in board_loop_wiring():
            failures += 1
            print("::error::verify-board-backlog-lines: board-loop.yml: {0}".format(error))
        for error in run_link_single_home():
            failures += 1
            print("::error::verify-board-backlog-lines: {0}".format(error))
        for error in issue_context_wiring():
            failures += 1
            print("::error::verify-board-backlog-lines: wing-commander-issue-context: {0}".format(error))
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            case = json.load(fh)
        error = run_case(case)
        name = os.path.basename(path)
        if error:
            failures += 1
            print("::error::verify-board-backlog-lines: {0}: {1}".format(name, error))
        elif verbose:
            print("[ok] {0}".format(name))
    return failures


def self_test():
    """A parser that ignores fences must fail the structure fixture, and the
    close-guard check must catch an unguarded close (T034)."""
    unguarded = 'set -uo pipefail\ngh issue comment "$N" --body x\ngh issue close "$N" -R "$R"\n'
    guarded = ('if [ -n "${BOARD_LINE_ID:-}" ]; then\n  echo line\nelse\n'
               '  gh issue close "$N" -R "$R"\nfi\n')
    exits = ('if [ -n "${BOARD_LINE_ID:-}" ]; then\n  echo line\n  exit 0\nfi\n'
             'gh issue close "$N" -R "$R"\n')
    if not unguarded_closes(unguarded) or unguarded_closes(guarded) or unguarded_closes(exits):
        print("::error::verify-board-backlog-lines --self-test: the close-guard check misreads a run block")
        return 1
    original = bbl.FENCE_RE
    try:
        import re
        bbl.FENCE_RE = re.compile(r"^never-matches$")
        broken = run(verbose=False)
    finally:
        bbl.FENCE_RE = original
    if not broken:
        print("::error::verify-board-backlog-lines --self-test: a parser ignoring fences passed")
        return 1
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("takes --self-test or nothing.")
    failures = run()
    print("verify-board-backlog-lines: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
