#!/usr/bin/env python3
"""Gate (unnumbered) -- the proof list puts every entry in exactly one state,
decided by code (specs/124-merge-proof-list, FR-008 to FR-013).

Drives .github/scripts/fixtures/proof-list/states.json through the pure half of
wc_proof_list.py. Each case is built to land in one state; a gate that cannot
fail its subject is worthless, so a self-check at the end changes the code's
input and confirms the cases notice.
"""
import copy
import datetime
import inspect
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_proof_list as pl  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "proof-list")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def make_entry(base, override=None):
    entry = copy.deepcopy(base)
    entry.update(copy.deepcopy(override or {}))
    # the pair is unpacked, never used as a condition (data-model.md Entry)
    needs_run, needs_reason = pl.actions_only(entry["changed_paths"])
    entry["needs_run"], entry["needs_reason"] = needs_run, needs_reason
    if not needs_run:
        entry["reaching"] = []
    return entry


def run_case(fx, case):
    entry = make_entry(fx["base_entry"], case.get("entry"))
    runs = {}
    if case.get("runs"):
        run = dict(fx["base_run"], **(case.get("run") or {}))
        runs[".github/workflows/wrap.yml"] = [run]
    comments, named = {}, {}
    if "comment" in case:
        comments[entry["sha"]] = [dict(fx["base_comment"], **case["comment"])]
    if "named" in case:
        named["own/repo/500"] = dict(fx["base_named"], **case["named"])
    states, _aged = pl.classify_all([entry], runs, comments, named, fx["repository"],
                                    fx["window"]["start"], fx["window"]["end"])
    return states.get(entry["sha"])


def check(fx):
    problems = []
    for case in fx["cases"]:
        got = run_case(fx, case)
        if got != case["expect"]:
            problems.append("{0}: state {1}, expected {2}".format(case["label"], got, case["expect"]))
    # US2 scenario 3: classification is deterministic.
    for case in fx["cases"][:6]:
        if run_case(fx, case) != run_case(fx, case):
            problems.append("{0}: two classifications of the same input differ".format(case["label"]))

    for case in fx["shared_cases"]:
        e1 = make_entry(fx["base_entry"])
        e2 = make_entry(fx["base_entry"], {"sha": "e2", "pr": 11})
        comment = dict(fx["base_comment"], place={"kind": "issue", "number": 100}, body=case["body"])
        named = {"own/repo/500": dict(fx["base_named"], contains=["e1", "e2"])}
        by_sha = {"e1": [comment], "e2": [comment]}
        states, _ = pl.classify_all([e1, e2], {}, by_sha, named, fx["repository"],
                                    fx["window"]["start"], fx["window"]["end"])
        if states != case["expect"]:
            problems.append("{0}: {1}, expected {2}".format(case["label"], states, case["expect"]))

    for case in fx["set_apart_cases"]:
        e1 = make_entry(fx["base_entry"])
        runs = {".github/workflows/wrap.yml": [dict(fx["base_run"], **r) for r in case.get("runs", [])]}
        comments = {}
        if "comment" in case:
            comments["e1"] = [dict(fx["base_comment"], **case["comment"])]
        got = pl.set_apart([e1], runs, comments, {}, fx["repository"],
                           fx["window"]["start"], fx["window"]["end"])
        if got != case["expect"]:
            problems.append("{0}: set apart {1}, expected {2}".format(case["label"], got, case["expect"]))

    # FR-012: aged-out counts state 4 or 5 in the 24 hours before the window start.
    start, end = fx["window"]["start"], fx["window"]["end"]
    old4 = make_entry(fx["base_entry"], {"sha": "o4", "pr": 20, "merged_at": "2026-10-10T12:00:00Z"})
    old1 = make_entry(fx["base_entry"], {"sha": "o1", "pr": 21, "merged_at": "2026-10-10T13:00:00Z",
                                         "changed_paths": ["docs/a.md"]})
    older = make_entry(fx["base_entry"], {"sha": "o0", "pr": 22, "merged_at": "2026-10-09T12:00:00Z"})
    states, aged = pl.classify_all([old4, old1, older], {}, {}, {}, fx["repository"], start, end)
    if states or aged != 1:
        problems.append("aged-out: states {0}, count {1}; expected no window entries and 1".format(states, aged))

    # US2 scenarios 4 and 5: the window is end - 30 days and nothing else sets it.
    s, e = pl.window_for("2026-11-17T00:00:00Z")
    if (e - s) != datetime.timedelta(days=30) or e.isoformat() != "2026-11-17T00:00:00+00:00":
        problems.append("window_for() is not end - 30 days")
    if list(inspect.signature(pl.window_for).parameters) != ["end"]:
        problems.append("window_for() takes more than the build's own end time")
    # Round 2: capture reads the 33-day corpus window and drops what is later than as-of.
    cs, ce = pl.capture_window_for("2026-11-17T00:00:00Z")
    if (ce - cs) != datetime.timedelta(days=33):
        problems.append("capture window is not 33 days")
    cap = pl.capture({"built_at": "2026-11-17T00:00:00Z", "runs": {},
                      "comments": {"s": [{"posted_at": "2026-11-10T00:00:00Z", "body": "a"},
                                         {"posted_at": "2026-11-16T00:00:00Z", "body": "b"}]}},
                     "2026-11-12T00:00:00Z")
    if len(cap["comments"]["s"]) != 1 or cap["window"]["start"] != "2026-10-15T00:00:00Z":
        problems.append("capture did not use the corpus window or filter at as-of")
    # An entry exactly at `start` is outside (start < merged_at), exactly at `end` inside.
    edge = make_entry(fx["base_entry"], {"merged_at": start})
    last = make_entry(fx["base_entry"], {"sha": "e9", "pr": 30, "merged_at": end})
    states, _ = pl.classify_all([edge, last], {}, {}, {}, fx["repository"], start, end)
    if list(states) != ["e9"]:
        problems.append("window edges: {0}, expected only the commit at `end`".format(sorted(states)))
    return problems


VERDICT_WORDS = ("proven", "not proven", "passed", "verified", "unproven")


def check_report(fx):
    """US1: the report lists every state-4/5 entry, collapses hundreds of runs
    to counts plus earliest/latest, shortens by names only, and fails when even
    that does not fit (FR-010, FR-020)."""
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    problems = []
    built_at = "2026-11-10T12:00:00Z"
    e4 = make_entry(fx["base_entry"], {"sha": "aaaaaaaaaaaa", "pr": 41})
    e5 = make_entry(fx["base_entry"], {"sha": "bbbbbbbbbbbb", "pr": 42,
                                       "reaching": [{"path": ".github/workflows/wrap.yml", "reached_via": "scan", "runs_of_its_own": True},
                                                    {"path": ".github/workflows/called.yml", "reached_via": "scan", "runs_of_its_own": False}]})
    e2 = make_entry(fx["base_entry"], {"sha": "cccccccccccc", "pr": 43, "changed_paths": ["docs/a.md"]})
    e4["reaching"] = [{"path": ".github/workflows/other.yml", "reached_via": "mention", "runs_of_its_own": True}]
    runs = {".github/workflows/wrap.yml": [
        {"run_id": 1000 + i, "event": "schedule" if i % 2 else "push", "conclusion": "success" if i % 3 else "failure",
         "run_started_at": "2026-11-0{0}T0{1}:00:00Z".format(2 + i % 7, i % 10),
         "html_url": "https://github.com/own/repo/actions/runs/{0}".format(1000 + i),
         "contains": ["bbbbbbbbbbbb"], "resolvable": True} for i in range(300)]}
    try:
        doc = pl.assemble_report([e4, e5, e2], runs, {}, {}, fx["repository"], built_at, "head1",
                                 MAX_BODY_UNITS, utf16_len)
    except ValueError as exc:
        return ["report assembly failed on a small fixture: {0}".format(exc)]
    if doc["schema"] != 1 or doc["window"]["start"] != "2026-10-11T12:00:00Z":
        problems.append("report schema/window wrong: {0}".format({k: doc[k] for k in ("schema", "window")}))
    if doc["counts"] != {"1": 1, "2": 0, "3": 0, "4": 1, "5": 1}:
        problems.append("report counts wrong: {0}".format(doc["counts"]))
    for form in ("full", "names_only"):
        for sha in ("aaaaaaaaaa", "bbbbbbbbbb"):
            if sha not in doc[form]:
                problems.append("{0} form drops entry {1}".format(form, sha))
        if "cccccccccc" in doc[form]:
            problems.append("{0} form lists a state-1 entry".format(form))
        if "no runs of its own" not in doc[form]:
            problems.append("{0} form lacks the 'no runs of its own' marking".format(form))
        if any(word in doc[form].lower() for word in VERDICT_WORDS):
            problems.append("{0} form carries verdict wording".format(form))
    if pl.STANDING_LINE not in doc["full"]:
        problems.append("the standing state-3 line is missing")
    if pl.SHORTENED_LINE in doc["full"] or pl.SHORTENED_LINE not in doc["names_only"]:
        problems.append("the shortened line must appear in the names-only form only")
    if doc["full"].count("actions/runs/") != 2:
        problems.append("300 runs did not collapse to an earliest and latest link: {0} links".format(
            doc["full"].count("actions/runs/")))
    if "schedule/success" not in doc["full"] or "push/failure" not in doc["full"]:
        problems.append("the per-event counts are missing from the full form")
    if "actions/runs/" in doc["names_only"]:
        problems.append("the names-only form carries run links")
    try:
        pl.assemble_report([e4, e5], runs, {}, {}, fx["repository"], built_at, "head1", 100, utf16_len)
        problems.append("a report over the size limit did not fail the build")
    except ValueError:
        pass
    return problems


def check_set_apart_report(fx):
    """US1 scenario 9: a run of a reaching workflow whose commit cannot be
    resolved, plus a comment naming a run of another repository, are counted
    as set apart and never as a state."""
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    entry = make_entry(fx["base_entry"])
    runs = {".github/workflows/wrap.yml": [dict(fx["base_run"], resolvable=False, contains=[])]}
    comment = dict(fx["base_comment"], body="Proven by https://github.com/other/repo/actions/runs/9 for #10")
    doc = pl.assemble_report([entry], runs, {"e1": [comment]}, {}, fx["repository"],
                             "2026-11-10T12:00:00Z", "head1", MAX_BODY_UNITS, utf16_len)
    problems = []
    if doc["set_apart"] != 2:
        problems.append("set-apart report: {0} runs set apart, expected 2".format(doc["set_apart"]))
    if doc["counts"]["4"] != 1:
        problems.append("set-apart report: the entry should stay in state 4, got {0}".format(doc["counts"]))
    return problems


# -- the I/O half: failed reads, fail loudly (FR-013, research D15) -----------
def _stub_gh(arms):
    """A `gh` on PATH that answers by `case "$*"` arm. Error arms come from
    wc_shell_harness.gh_error_stub_arm (Gate 127)."""
    import wc_shell_harness as harness
    body = ['#!/bin/bash', 'case "$*" in']
    for glob, reply in arms:
        if isinstance(reply, tuple):
            body.append("  {0})\n{1}\n  ;;".format(glob, harness.gh_error_stub_arm(glob, *reply)))
        else:
            body.append("  {0})\n    echo '{1}'\n  ;;".format(glob, reply))
    body += ['  *) echo "unexpected gh $*" >&2; exit 2 ;;', 'esac']
    return "\n".join(body) + "\n"


def check_failed_reads():
    import stat
    import tempfile
    problems = []
    cases = [
        ("a 500 on a comment thread", [("*issues/5/comments*", ("500", "Server Error"))],
         lambda c: c.thread("issue", 5), pl.ReadError),
        ("a 403 primary rate limit", [("*issues/5/comments*", ("403", "API rate limit exceeded"))],
         lambda c: c.thread("issue", 5), pl.ReadError),
        ("a 404 on a named run is told apart", [("*actions/runs/7*", ("404", "Not Found"))],
         lambda c: pl.api("repos/own/repo/actions/runs/7"), pl.NotFound),
        ("under 600 requests left", [("*rate_limit*", "100")], lambda c: pl.check_rate_limit(),
         pl.ReadError),
        ("runs past the cap in one day", [("*workflows/wrap.yml/runs*", '{"total_count": 2000}')],
         lambda c: c.workflow_runs(".github/workflows/wrap.yml"), pl.ReadError),
        ("a deleted workflow's fallback list past the cap",
         [("*workflows/wrap.yml/runs*", ("404", "Not Found")),
          ("*actions/runs?*", '{"total_count": 2000}')],
         lambda c: c.workflow_runs(".github/workflows/wrap.yml"), pl.ReadError),
    ]
    old_path = os.environ["PATH"]
    for label, arms, act, want in cases:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gh")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(_stub_gh(arms))
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
            os.environ["PATH"] = tmp + os.pathsep + old_path
            try:
                act(pl.Collector("own/repo", "2026-11-10T12:00:00Z"))
                problems.append("{0}: the read did not fail".format(label))
            except want as exc:
                if want is pl.ReadError and isinstance(exc, pl.NotFound):
                    problems.append("{0}: reported as a 404".format(label))
            finally:
                os.environ["PATH"] = old_path
    return problems


def check_review_fixes(fx):
    """Round 1 review findings, each with a case that fails without its fix."""
    import tempfile
    import wc_board_status as bs
    problems = []
    # Run URLs compare case-insensitively with the repository.
    mixed = dict(fx["base_comment"], body="Proven by https://github.com/Own/Repo/actions/runs/500 for #10")
    entry = make_entry(fx["base_entry"])
    named = {"own/repo/500": dict(fx["base_named"])}
    states, _ = pl.classify_all([entry], {}, {entry["sha"]: [mixed]}, named, "own/repo",
                                fx["window"]["start"], fx["window"]["end"])
    if states.get("e1") != pl.STATE_ON_RECORD:
        problems.append("a differently capitalised run URL did not count: {0}".format(states))
    if pl.set_apart([entry], {}, {entry["sha"]: [mixed]}, named, "Own/Repo",
                    fx["window"]["start"], fx["window"]["end"]) != 0:
        problems.append("a differently capitalised own-repo run URL was set apart")
    # Decided: a run's conclusion never changes a state (data-model.md), so a
    # cancelled run counts like any finished run.
    cancelled = {".github/workflows/wrap.yml": [dict(fx["base_run"], conclusion="cancelled")]}
    if pl.classify(entry, cancelled, [], {}, set(), "own/repo") != pl.STATE_RUN_NO_RECORD:
        problems.append("a cancelled run changed the state")
    # One ancestry check per (merge, head), however many runs share a head.
    calls = []
    saved = (pl.is_ancestor, pl.commit_present)
    pl.is_ancestor = lambda a, d: calls.append((a, d)) or True
    pl.commit_present = lambda sha: True
    try:
        col = pl.Collector("own/repo", "2026-11-10T12:00:00Z")
        raw = {"id": 1, "head_sha": "h1", "path": "p", "run_started_at": "2026-11-02T00:00:00Z"}
        col.run_record(raw, [entry])
        col.run_record(dict(raw, id=2), [entry])
    finally:
        pl.is_ancestor, pl.commit_present = saved
    if len(calls) != 1:
        problems.append("{0} ancestry checks for two runs of one head, expected 1".format(len(calls)))
    # A malformed section shape is `unreadable`, never an exception.
    def gh_obj(path):
        return []
    snap = bs.proof_list_snapshot("o/r", {}, None, gh_obj, lambda rid: True, lambda *a: None)
    if snap.get("status") != "unreadable":
        problems.append("a malformed API shape gave {0}, expected unreadable".format(snap.get("status")))
    return problems


def _git(cwd, *args, **env):
    import subprocess
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(args),
                   cwd=cwd, check=True, capture_output=True, env=dict(os.environ, **env))


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _commit(root, files, when, message="c"):
    """Writes `files` ({relpath: text}), commits them with committer and
    author time `when` (git's own date form, offset included), returns the SHA."""
    for rel, text in files.items():
        _write(root, rel, text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message, GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)
    return pl._run(["git", "rev-parse", "HEAD"], cwd=root).strip()


class _InRepo:
    """chdir into a temporary git repository; the collector's git reads are real."""

    def __enter__(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root, self._previous = self._tmp.name, os.getcwd()
        _git(self.root, "init", "-q")
        os.chdir(self.root)
        return self

    def __exit__(self, *exc):
        os.chdir(self._previous)
        self._tmp.cleanup()
        return False


class _FakeReads:
    """Replaces the collector's GitHub readers in-process, so a fixture runs
    with no `gh` on PATH, on any OS. `api` and `gh` are callables; every call
    is recorded in `calls`."""

    def __init__(self, api=None, gh=None, tree=None):
        self.api, self.gh, self.tree, self.calls = api, gh, tree, []

    def __enter__(self):
        self._saved = (pl.api, pl.gh_text, pl.tree_reaching)

        def api(path, paginate=False):
            self.calls.append(("api", path, paginate))
            return self.api(path, paginate)

        def gh(args):
            self.calls.append(("gh",) + tuple(args))
            return self.gh(list(args))
        pl.api, pl.gh_text = api, gh
        if self.tree is not None:
            pl.tree_reaching = self.tree
        return self

    def __exit__(self, *exc):
        pl.api, pl.gh_text, pl.tree_reaching = self._saved
        return False


FINAL_SHA_FILES = {
    ".github/workflows/x.yml": "on: {push: {}}\njobs: {}\n",
    "specs/001-other/spec-meta.json": '{"issue": 148}\n',
    "specs/001-other/contracts/c.md": "edited by a later final PR\n",
    "specs/124-own/spec-meta.json": '{"issue": 5}\n',
}


def check_lifecycle_issue():
    """R1 (research D6): the lifecycle issue comes from the head branch's own
    spec directory only, cross-checked against the title."""
    problems = []
    with _InRepo() as repo:
        sha = _commit(repo.root, FINAL_SHA_FILES, "2026-11-09T20:00:00 -0500")
        col = pl.Collector("own/repo", "2026-11-10T12:00:00Z")
        cases = [
            ("a final PR touching two spec directories uses only its own",
             "Finalize: own (#5)", "spec/124-own", 5),
            ("a final PR whose spec has no spec-meta.json at that commit",
             "Finalize: gone (#9)", "spec/999-gone", None),
            ("a head branch that is not spec/<slug>", "Finalize: own (#5)", "claude/x", None),
            ("a PR that is not a final PR", "Fix things (#5)", "spec/124-own", None),
        ]
        for label, title, head, want in cases:
            try:
                got = col.lifecycle_issue(sha, title, head)
            except pl.ReadError as exc:
                got = "ReadError: {0}".format(exc)
            if got != want:
                problems.append("lifecycle issue: {0}: got {1!r}, expected {2!r}".format(label, got, want))
        try:
            got = col.lifecycle_issue(sha, "Finalize: own (#6)", "spec/124-own")
            problems.append("lifecycle issue: its own spec-meta disagreeing with the title gave "
                            "{0!r}, expected a failed read".format(got))
        except pl.ReadError:
            pass
    return problems


def _closing_ref(repo, number):
    owner, name = repo.split("/")
    return {"number": number, "repository": {"name": name, "owner": {"login": owner}},
            "url": "https://github.com/{0}/issues/{1}".format(repo, number)}


def check_entries():
    """`Collector.entries` end to end on a real repository, with the GitHub
    reads faked: the head branch reaches lifecycle_issue (R1)."""
    problems = []
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        sha = _commit(repo.root, FINAL_SHA_FILES, "2026-11-09T20:00:00 -0500")
        view = {"title": "Finalize: own (#5)", "headRefName": "spec/124-own", "body": "",
                "closingIssuesReferences": []}

        def api(path, paginate):
            if path.endswith("/commits/{0}/pulls".format(sha)):
                return [{"number": 77, "merge_commit_sha": sha}]
            raise AssertionError("unexpected read " + path)
        reaching = [{"path": ".github/workflows/x.yml", "reached_via": "scan", "runs_of_its_own": True}]
        with _FakeReads(api=api, gh=lambda args: json.dumps(view), tree=lambda s, c: reaching) as fake:
            try:
                entries = pl.Collector("own/repo", "2026-11-10T12:00:00Z").entries()
            except pl.ReadError as exc:
                return ["entries: a final PR touching two spec directories failed the read: {0}".format(exc)]
        views = [c for c in fake.calls if c[:2] == ("gh", "pr")]
        if not views or "headRefName" not in views[0][-1]:
            problems.append("entries: gh pr view does not read headRefName: {0}".format(views))
        if len(entries) != 1:
            return problems + ["entries: {0} entries, expected the one merge in the window".format(len(entries))]
        entry = entries[0]
        if entry["lifecycle_issue"] != 5 or {"number": 5, "how": "lifecycle"} not in entry["named_issues"]:
            problems.append("entries: lifecycle issue {0}, named {1}; expected #5 from spec/124-own".format(
                entry["lifecycle_issue"], entry["named_issues"]))
    return problems


AUTO_RELEASE_TEXT = ("on: {workflow_dispatch: {}}\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
                     "      - run: |\n          declare -A stage_file=(\n"
                     "            [wing-commander-5-implement.yml]=implement.yml\n          )\n")


def check_trees():
    """US3: reach is read from the tree at the entry's merge; a later-deleted
    workflow is still credited; the nightly end-to-end edge reaches a stage
    workflow change (FR-005)."""
    import tempfile
    problems = []
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as repo:
        wf = os.path.join(repo, ".github", "workflows")
        os.makedirs(wf)
        _git(repo, "init", "-q")
        files = {"new.yml": "on: {push: {}}\njobs: {}\n", "implement.yml": "on: {workflow_call: {}}\njobs: {}\n",
                 "wing-commander-5-implement.yml": "on: {workflow_dispatch: {}}\njobs: {}\n",
                 "auto-release.yml": AUTO_RELEASE_TEXT}
        for name, text in files.items():
            with open(os.path.join(wf, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "add")
        sha = pl._run(["git", "rev-parse", "HEAD"], cwd=repo).strip()
        os.remove(os.path.join(wf, "new.yml"))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "delete")
        os.chdir(repo)
        try:
            added = pl.tree_reaching(sha, [".github/workflows/new.yml"])
            names = {w["path"]: w for w in added}
            if ".github/workflows/new.yml" not in names:
                problems.append("trees: a workflow deleted later is no longer credited: {0}".format(sorted(names)))
            elif names[".github/workflows/new.yml"]["reached_via"] != "scan":
                problems.append("trees: the added workflow was not reached by the scan")
            nightly = pl.tree_reaching(sha, [".github/workflows/implement.yml"])
            via = {w["path"]: w["reached_via"] for w in nightly}
            if via.get(".github/workflows/auto-release.yml") != "nightly-e2e":
                problems.append("trees: the nightly end-to-end run does not reach a stage workflow: {0}".format(via))
            if pl.tree_reaching(sha, [".github/workflows/nothing.yml"]):
                problems.append("trees: a path no workflow reaches was listed")
        finally:
            os.chdir(previous)
    return problems


WRITE_CALLS = ("gh workflow run", "gh issue comment", "gh issue close", "gh issue edit", "gh pr comment",
               "gh label", "createWorkflowDispatch", "-X POST", "-X PATCH", "-X PUT", "-X DELETE",
               "--method POST", "--method PATCH", "claude-code-action", "create-github-app-token")


def check_workflow_text(text):
    """FR-014 to FR-019, SC-004, SC-007: the workflow file's own shape."""
    import yaml
    problems = []
    doc = yaml.safe_load(text)
    on = doc.get("on", doc.get(True)) or {}
    if on.get("schedule") != [{"cron": "19 6 * * *"}]:
        problems.append("workflow: the schedule is not 19 6 * * *")
    if on.get("workflow_dispatch") not in ({}, None) or "inputs" in (on.get("workflow_dispatch") or {}):
        problems.append("workflow: workflow_dispatch takes inputs")
    if doc.get("permissions") != {"contents": "read", "actions": "read", "issues": "read",
                                  "pull-requests": "read"}:
        problems.append("workflow: permissions are not the four read scopes")
    if doc.get("concurrency", {}).get("group") != "wing-commander-proof-list":
        problems.append("workflow: concurrency group is not wing-commander-proof-list")
    jobs = doc.get("jobs") or {}
    if len(jobs) != 1:
        problems.append("workflow: expected exactly one job")
    job = next(iter(jobs.values()), {})
    if job.get("timeout-minutes") != 15:
        problems.append("workflow: timeout-minutes is not 15")
    steps = job.get("steps") or []
    names = [s.get("name") for s in steps]
    if len(steps) != 5 or "refuse" not in (names[0] or "").lower() or "pause" not in (names[1] or "").lower():
        problems.append("workflow: the refusal and the pause check are not the first two steps: {0}".format(names))
    elif "default_branch" not in steps[0].get("env", {}).get("DEFAULT_BRANCH", "") or \
            "exit 1" not in steps[0].get("run", ""):
        problems.append("workflow: the refusal does not exit 1 on the default branch comparison")
    if "if" in (steps[0] if steps else {}):
        problems.append("workflow: the refusal step is conditional")
    for step in steps[2:]:
        if step.get("if") != "steps.pause.outputs.paused != 'true'":
            problems.append("workflow: step {0!r} is not gated on the pause output".format(step.get("name")))
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    text = code
    for token in ("always()", "!cancelled()"):
        if token in text:
            problems.append("workflow: {0} appears".format(token))
    uploads = [s for s in steps if "upload-artifact" in str(s.get("uses"))]
    if len(uploads) != 1 or uploads[0]["with"].get("name") != "proof-list-section" \
            or uploads[0]["with"].get("retention-days") != 7:
        problems.append("workflow: the upload is not proof-list-section for 7 days")
    for call in WRITE_CALLS:
        if call in text:
            problems.append("workflow: contains a write or agent call ({0})".format(call))
    return problems


def check_workflow():
    with open(os.path.join(HERE, "..", "workflows", "wing-commander-proof-list.yml"), encoding="utf-8") as fh:
        text = fh.read()
    problems = check_workflow_text(text)
    with open(os.path.join(HERE, "wc_proof_list.py"), encoding="utf-8") as fh:
        source = fh.read()
    for call in ("gh_text([\"api\", \"-X", "\"issue\", \"comment\"", "\"issue\", \"edit\"", "\"workflow\", \"run\"", "\"pr\", \"comment\""):
        if call in source:
            problems.append("wc_proof_list.py: contains a write call ({0})".format(call))
    # Fixtures: each mutation of the shipped file must be noticed.
    mutations = [
        ("a refusal that no longer exits", text.replace("exit 1", "exit 0", 1)),
        ("a permission widened", text.replace("issues: read", "issues: write")),
        ("an always() on the build", text.replace("- name: Build the proof list\n        if:",
                                                   "- name: Build the proof list\n        if: always() &&")),
        ("an input on dispatch", text.replace("workflow_dispatch: {}", "workflow_dispatch:\n    inputs:\n      x: {}")),
        ("a dropped gate on checkout", text.replace("if: steps.pause.outputs.paused != 'true'\n        uses: actions/checkout",
                                                     "uses: actions/checkout")),
        ("a write call", text + "      - run: gh issue comment 1 -b x\n"),
    ]
    for label, mutated in mutations:
        if mutated == text or not check_workflow_text(mutated):
            problems.append("workflow fixture: {0} was not noticed".format(label))
    return problems


# -- SC-001: replay of the captured corpus (research D13) ---------------------
from board_prove import Exemption  # noqa: E402
# Interim: the corpus and its answer key are captured by a maintainer session
# (T029), which deletes this entry in the same commit. Passed to the check as a
# parameter; never written here (Gate 124).
EXEMPT_SC001_PENDING = {
    "sc001": Exemption(
        reason=("sc001/corpus.json and expected.json are captured by a maintainer "
                "session with full history and `gh` (T029); until then the replay "
                "reports 'not yet captured' instead of failing"),
        issue=(889,)),
}
SC001_REASONS = ("own-tree", "FR-005", "FR-006-shared-issue", "FR-013-set-apart")


def sc001_replay(corpus, expected):
    """The replay: needs neither git nor `gh`. Returns problems."""
    problems = []
    states, _aged = pl.classify_all(corpus["entries"], corpus["runs"], corpus["comments"],
                                    corpus["named_runs"], corpus["repository"],
                                    corpus["window"]["start"], corpus["window"]["end"])
    by_pr = {e["pr"]: states.get(e["sha"]) for e in corpus["entries"] if e.get("pr") is not None}
    diffs = []
    for pr in expected["proofs"]:
        if by_pr.get(pr) != pl.STATE_ON_RECORD:
            diffs.append((pr, "proofs", by_pr.get(pr)))
    for pr in expected["listed"]:
        if by_pr.get(pr) not in (pl.STATE_NO_RUN, pl.STATE_RUN_NO_RECORD):
            diffs.append((pr, "listed", by_pr.get(pr)))
    named = set(expected["proofs"]) | set(expected["listed"])
    for pr, state in sorted(by_pr.items()):
        if pr not in named and state in (pl.STATE_NO_RUN, pl.STATE_RUN_NO_RECORD):
            diffs.append((pr, "listed", state))
    allowed = {}
    for item in expected.get("expected_differences", ()):
        if item.get("reason") not in SC001_REASONS:
            problems.append("SC-001: #{0} has reason {1!r}, outside SC-001's four".format(
                item.get("pr"), item.get("reason")))
        allowed[(item.get("pr"), item.get("half"), item.get("actual_state"))] = item
    for key in diffs:
        if key not in allowed:
            problems.append("SC-001: #{0} ({1}) is in state {2}, a difference that is not on the list".format(*key))
    for key, item in sorted(allowed.items(), key=lambda kv: str(kv[0])):
        if key not in diffs:
            problems.append("SC-001: the expected difference for #{0} ({1}, state {2}) no longer differs; "
                            "delete it".format(*key))
    return problems


def check_sc001(directory, exempt):
    """-> (problems, note). The five cases of research D13."""
    paths = [os.path.join(directory, n) for n in ("corpus.json", "expected.json")]
    present = [os.path.isfile(p) for p in paths]
    if sum(present) == 1:
        return ["SC-001: exactly one of corpus.json and expected.json is present"], None
    if sum(present) == 0:
        if exempt:
            return [], "SC-001 not yet captured (EXEMPT_SC001_PENDING, #889)"
        return ["SC-001: the corpus and answer key are absent and the exemption was deleted "
                "without the capture"], None
    if exempt:
        return ["SC-001: both files are present but EXEMPT_SC001_PENDING is still there; "
                "the capture commit deletes the entry"], None
    with open(paths[0], encoding="utf-8") as fh:
        corpus = json.load(fh)
    with open(paths[1], encoding="utf-8") as fh:
        expected = json.load(fh)
    return sc001_replay(corpus, expected), "SC-001 replayed {0} entries".format(len(corpus["entries"]))


def check_sc001_fixtures(fx):
    import tempfile
    problems = []
    base = fx["base_entry"]
    entries = [make_entry(base, {"sha": "p1", "pr": 1}),
               make_entry(base, {"sha": "l2", "pr": 2}),
               make_entry(base, {"sha": "x3", "pr": 3, "changed_paths": ["docs/a.md"]})]
    comment = dict(fx["base_comment"], place={"kind": "pr", "number": 1})
    corpus = {"repository": fx["repository"], "window": fx["window"], "entries": entries,
              "runs": {}, "named_runs": {"own/repo/500": dict(fx["base_named"], contains=["p1"])},
              "comments": {"p1": [comment]}}
    good = {"proofs": [1], "listed": [2], "expected_differences": []}
    if sc001_replay(corpus, good):
        problems.append("SC-001 fixture: the matching corpus failed: {0}".format(sc001_replay(corpus, good)))
    diff = {"pr": 2, "sha": "l2", "half": "listed", "expected_state": 5, "actual_state": 3,
            "reason": "own-tree", "note": "x"}
    mismatches = [
        ("a proof not in state 2", dict(good, proofs=[2], listed=[1])),
        ("a listed entry outside 4 or 5", dict(good, listed=[3])),
        ("an extra entry in 4 or 5", dict(good, listed=[])),
        ("a stale expected difference", dict(good, expected_differences=[dict(diff, pr=1, half="proofs", actual_state=4)])),
        ("a reason outside SC-001's four", dict(good, expected_differences=[dict(diff, reason="other")])),
    ]
    for label, expected in mismatches:
        if not sc001_replay(corpus, expected):
            problems.append("SC-001 fixture: {0} was not noticed".format(label))
    # an expected difference that matches an actual one is accepted
    moved = dict(corpus, entries=[make_entry(base, {"sha": "l2", "pr": 2, "reaching": []})] + entries[:1] + entries[2:])
    if sc001_replay(moved, dict(good, expected_differences=[dict(diff, actual_state=3)])):
        problems.append("SC-001 fixture: a listed difference was rejected: {0}".format(
            sc001_replay(moved, dict(good, expected_differences=[dict(diff, actual_state=3)]))))
    # the five exemption cases
    exempt = EXEMPT_SC001_PENDING
    with tempfile.TemporaryDirectory() as tmp:
        def write(name):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                json.dump(corpus if name == "corpus.json" else good, fh)
        for label, files, table, want_fail in (
                ("both absent, entry present", (), exempt, False),
                ("both absent, no entry", (), {}, True),
                ("exactly one file", ("corpus.json",), {}, True),
                ("both present, entry still there", ("corpus.json", "expected.json"), exempt, True),
                ("both present, no entry, replay passes", ("corpus.json", "expected.json"), {}, False)):
            for name in ("corpus.json", "expected.json"):
                path = os.path.join(tmp, name)
                if os.path.exists(path):
                    os.remove(path)
            for name in files:
                write(name)
            got, _note = check_sc001(tmp, table)
            if bool(got) != want_fail:
                problems.append("SC-001 fixture: {0}: {1}".format(label, got or "did not fail"))
    return problems


def main():
    fx = load("states.json")
    real, note = check_sc001(os.path.join(FIXTURES, "sc001"), EXEMPT_SC001_PENDING)
    if note:
        print("[ok] verify-proof-list: {0}".format(note))
    problems = (check(fx) + check_report(fx) + check_set_apart_report(fx)
                + check_failed_reads() + check_review_fixes(fx) + check_lifecycle_issue()
                + check_entries() + check_trees() + check_workflow()
                + real + check_sc001_fixtures(fx))
    # Self-check: a classifier that ignores the merge time must be caught.
    original = pl.comment_steps_1_to_4
    pl.comment_steps_1_to_4 = lambda entry, comment, shared, repository: True
    try:
        if not check(fx):
            problems.append("self-check: a classifier that qualifies every comment passed the cases")
    finally:
        pl.comment_steps_1_to_4 = original
    for problem in problems:
        print("::error::verify-proof-list: {0}".format(problem))
    if not problems:
        print("[ok] verify-proof-list: {0} state cases, {1} shared-issue cases, {2} set-apart cases, "
              "aged-out and window edges".format(len(fx["cases"]), len(fx["shared_cases"]),
                                                 len(fx["set_apart_cases"])))
    print("verify-proof-list: {0} failure(s).".format(len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
