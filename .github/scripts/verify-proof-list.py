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
    cap = pl.capture({"built_at": "2026-11-17T00:00:00Z", "runs": {}, "repository": "own/repo",
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
    """A `gh` on PATH that answers by `case "$*"` arm, first match wins. Error
    arms come from wc_shell_harness.gh_error_stub_arm (Gate 127). Any other
    call is recorded in $STUB_UNEXPECTED and fails, so a case can never pass
    on a read it did not mean to make."""
    import wc_shell_harness as harness
    body = ['#!/bin/bash', 'case "$*" in']
    for glob, reply in arms:
        if isinstance(reply, tuple):
            body.append("  {0})\n{1}\n  ;;".format(glob, harness.gh_error_stub_arm(glob, *reply)))
        else:
            body.append("  {0})\n    echo '{1}'\n  ;;".format(glob, reply))
    body += ['  *) echo "$*" >> "$STUB_UNEXPECTED"; echo "unexpected gh $*" >&2; exit 2 ;;', 'esac']
    return "\n".join(body) + "\n"


# A paged read (paginated and slurped) is answered with a list of pages;
# its arm comes first, since `case` takes the first match.
_PAGES_OF_NONE = '[{"total_count": 2000, "workflow_runs": []}]'


def check_failed_reads():
    """FR-013 / SC-007: each failed read fails the build with its own message.
    The message is asserted, so a case cannot pass on an unrelated ReadError
    (the second review's N3: deleting a cap check left the gate green)."""
    import shutil
    import stat
    import tempfile
    problems = []
    runs = ".github/workflows/wrap.yml"
    cases = [
        ("a 500 on a comment thread", [("*issues/5/comments*", ("500", "Server Error"))],
         lambda c: c.thread("issue", 5), pl.ReadError, "(HTTP 500)"),
        ("a 403 primary rate limit", [("*issues/5/comments*", ("403", "API rate limit exceeded"))],
         lambda c: c.thread("issue", 5), pl.ReadError, "API rate limit exceeded"),
        ("a 404 on a named run is told apart", [("*actions/runs/7*", ("404", "Not Found"))],
         lambda c: pl.api("repos/own/repo/actions/runs/7"), pl.NotFound, "(HTTP 404)"),
        ("under 600 requests left", [("'api rate_limit --jq .resources.core.remaining'", "100")],
         lambda c: pl.check_rate_limit(), pl.ReadError, "only 100 API requests remain"),
        ("runs past the cap in one day",
         [("*--paginate*workflows/wrap.yml/runs*", _PAGES_OF_NONE),
          ("*workflows/wrap.yml/runs*", '{"total_count": 2000}')],
         lambda c: c.workflow_runs(runs), pl.ReadError, "more than 1000 runs in one day"),
        ("a deleted workflow's fallback list past the cap",
         [("*workflows/wrap.yml/runs*", ("404", "Not Found")),
          ("*--paginate*actions/runs?*", _PAGES_OF_NONE),
          ("*actions/runs?*", '{"total_count": 2000}')],
         lambda c: c.workflow_runs(runs), pl.ReadError,
         "wrap.yml (deleted; the repository's runs): more than 1000 runs in one day"),
    ]
    old_path, saved_gh = os.environ["PATH"], pl.gh_text
    for label, arms, act, want, text in cases:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gh")
            unexpected = os.path.join(tmp, "unexpected")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(_stub_gh(arms))
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
            os.environ["PATH"] = tmp + os.pathsep + old_path
            os.environ["STUB_UNEXPECTED"] = unexpected
            if os.name == "nt":
                # Windows cannot exec a bash script found as `gh`; run the same
                # stub through bash so the cases run on a maintainer's machine.
                bash = shutil.which("bash")
                pl.gh_text = lambda args, stub=path, bash=bash: pl._run([bash, stub] + list(args))
            try:
                act(pl.Collector("own/repo", "2026-11-10T12:00:00Z"))
                problems.append("{0}: the read did not fail".format(label))
            except Exception as exc:  # noqa: BLE001 - the type and message are the test
                if not isinstance(exc, want) or (want is pl.ReadError and isinstance(exc, pl.NotFound)):
                    problems.append("{0}: raised {1}, expected {2}".format(label, type(exc).__name__,
                                                                         want.__name__))
                elif text not in str(exc):
                    problems.append("{0}: failed with {1!r}, not {2!r}".format(label, str(exc)[:160], text))
            finally:
                os.environ["PATH"] = old_path
                os.environ.pop("STUB_UNEXPECTED", None)
                pl.gh_text = saved_gh
            if os.path.exists(unexpected):
                with open(unexpected, encoding="utf-8") as fh:
                    problems.append("{0}: the stub was asked for a read it does not answer: {1}".format(
                        label, fh.read().strip().splitlines()[:3]))
    return problems


def check_main_errors():
    """FR-013 (#889): a git, tar or file failure under `build` ends with the
    one `::error::wc_proof_list:` line and exit 1, never a traceback."""
    import contextlib
    import io
    import subprocess
    import tarfile
    problems = []
    raisers = [
        ("a failed git call", subprocess.CalledProcessError(128, ["git", "diff"], b"", b"fatal: bad object\n")),
        ("a missing file", FileNotFoundError(2, "No such file or directory", "x.yml")),
        ("an OS error", OSError(5, "Input/output error")),
        ("a bad tar archive", tarfile.ReadError("file could not be opened successfully")),
    ]
    saved = pl.collect
    try:
        for label, exc in raisers:
            def boom(*_a, exc=exc, **_k):
                raise exc
            pl.collect = boom
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    code = pl.main(["build", "--repository", "own/repo", "--out", os.devnull])
            except BaseException as raised:  # noqa: BLE001 - escaping at all is the failure
                problems.append("main: {0} escaped as {1}".format(label, type(raised).__name__))
                continue
            if code != 1 or not out.getvalue().startswith("::error::wc_proof_list: "):
                problems.append("main: {0} gave exit {1} and {2!r}".format(label, code, out.getvalue()[:160]))
            elif len(out.getvalue().splitlines()) != 1:
                problems.append("main: {0} printed more than the one error line: {1!r}".format(label, out.getvalue()[:160]))
            # diff_name_list captures git's stderr, so the line must carry it.
            elif isinstance(exc, subprocess.CalledProcessError) and "fatal: bad object" not in out.getvalue():
                problems.append("main: {0} dropped git's reason: {1!r}".format(label, out.getvalue()[:160]))
    finally:
        pl.collect = saved
    return problems


def check_section_file_home():
    """#889: the section file's name has one home, wc_board_status.PROOF_LIST_FILE;
    the writer uses it, and the workflow writes and uploads exactly that file."""
    import wc_board_status as bs
    problems = []
    if pl.SECTION_FILE is not bs.PROOF_LIST_FILE:
        problems.append("wc_proof_list.SECTION_FILE is not wc_board_status.PROOF_LIST_FILE")
    if hasattr(pl, "SECTION_ARTIFACT"):
        problems.append("wc_proof_list.SECTION_ARTIFACT is back; the artifact name is wc_board_status.PROOF_LIST_ARTIFACT")
    for name in ("wc_proof_list.py", "wc_board_status.py"):
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            count = fh.read().count('"{0}"'.format(bs.PROOF_LIST_FILE))
        if count != (1 if name == "wc_board_status.py" else 0):
            problems.append("{0}: the section file name is typed {1} time(s); it belongs once, "
                            "in wc_board_status.PROOF_LIST_FILE".format(name, count))
    with open(os.path.join(HERE, "..", "workflows", bs.PROOF_LIST_WORKFLOW), encoding="utf-8") as fh:
        text = fh.read()
    problems += section_file_problems(text, bs.PROOF_LIST_FILE)
    renamed = text.replace(bs.PROOF_LIST_FILE, "proof-list.json")
    if renamed == text or not section_file_problems(renamed, bs.PROOF_LIST_FILE):
        problems.append("section file fixture: a renamed file in the workflow was not noticed")
    upload_only = text.replace("path: " + bs.PROOF_LIST_FILE, "path: proof-list.json")
    if upload_only == text or not section_file_problems(upload_only, bs.PROOF_LIST_FILE):
        problems.append("section file fixture: a renamed upload path was not noticed")
    return problems


def section_file_problems(text, filename):
    """The build step writes `--out <filename>` and the upload's `path:` is it."""
    import shlex
    import yaml
    problems = []
    steps = [s for job in (yaml.safe_load(text).get("jobs") or {}).values() for s in job.get("steps") or []]
    builds = [s for s in steps if "wc_proof_list.py build" in str(s.get("run"))]
    if len(builds) != 1:
        return ["workflow: expected one `wc_proof_list.py build` step, found {0}".format(len(builds))]
    argv = shlex.split(builds[0]["run"])
    out = argv[argv.index("--out") + 1] if "--out" in argv[:-1] else None
    if out != filename:
        problems.append("workflow: the build writes {0!r}, not {1!r}".format(out, filename))
    uploads = [s for s in steps if "upload-artifact" in str(s.get("uses"))]
    if len(uploads) != 1 or (uploads[0].get("with") or {}).get("path") != filename:
        problems.append("workflow: the upload's path is not {0!r}".format(filename))
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
    "specs/001-other/notes.txt": "another spec this final PR edited\n",
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
                "closingIssuesReferences": [_closing_ref("own/repo", 7), _closing_ref("Other/Repo", 8)]}

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
        # R4: an issue the PR closes in another repository is not one of its places.
        if sorted(i["number"] for i in entry["named_issues"]) != [5, 7]:
            problems.append("entries: named issues {0}, expected #5 and #7 (not other/repo#8)".format(
                entry["named_issues"]))
        # R2: the commit's -05:00 time is written in UTC, so a comment posted
        # between the local and the UTC merge time is before the merge.
        if entry["merged_at"] != "2026-11-10T01:00:00Z":
            problems.append("entries: a -05:00 merge was written as {0}, expected 2026-11-10T01:00:00Z".format(
                entry["merged_at"]))
        early = {"comment_id": 1, "account": "owner", "account_type": "User", "marker_step": "none",
                 "posted_at": "2026-11-09T22:00:00Z", "place": {"kind": "pr", "number": 77},
                 "body": "Proven by https://github.com/own/repo/actions/runs/500 for #77"}
        named = {"own/repo/500": {"kind": "found", "run_id": 500, "run_started_at": "2026-11-10T02:00:00Z",
                                  "contains": [sha], "resolvable": True}}
        if pl.classify(entry, {}, [early], named, set(), "own/repo") == pl.STATE_ON_RECORD:
            problems.append("entries: a comment posted before the real (UTC) merge time counted")
    return problems



def check_closed_by_commit(fx):
    """R9 (FR-006): an issue the merge commit's message closes is read,
    confirmed by its own `closed` event; another repository's issue, and an
    issue closed by hand, are not."""
    problems = []
    message = ("Fix #12: the thing (#77)\n\nAlso closes Other/Repo#13 and fixes #14.\n"
               "It prefixes #15, which closes nothing.\n")
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        sha = _commit(repo.root, {".github/workflows/x.yml": "on: {push: {}}\njobs: {}\n"},
                      "2026-11-01T00:00:00 +0000", message=message)
        view = {"title": "Fix #12: the thing", "headRefName": "fix/12", "body": "",
                "closingIssuesReferences": []}
        events = {"12": [{"event": "referenced", "commit_id": sha},
                         {"event": "closed", "commit_id": sha}],
                  "14": [{"event": "closed", "commit_id": None}]}

        def api(path, paginate):
            if path.endswith("/commits/{0}/pulls".format(sha)):
                return [{"number": 77, "merge_commit_sha": sha}]
            for number, rows in events.items():
                if "/issues/{0}/events".format(number) in path:
                    return rows
            raise AssertionError("unexpected read " + path)
        reaching = [{"path": ".github/workflows/x.yml", "reached_via": "scan", "runs_of_its_own": True}]
        with _FakeReads(api=api, gh=lambda args: json.dumps(view), tree=lambda s, c: reaching) as fake:
            try:
                entries = pl.Collector("own/repo", "2026-11-10T12:00:00Z").entries()
            except (pl.ReadError, AssertionError) as exc:
                return ["closed by commit: the read failed: {0}".format(exc)]
    reads = [c[1] for c in fake.calls if c[0] == "api" and "/events" in c[1]]
    if any("/13/" in r or "other/repo" in r.lower() or "/15/" in r for r in reads):
        problems.append("closed by commit: read another repository's issue or a non-keyword one: {0}".format(reads))
    entry = entries[0] if entries else {}
    named = {i["number"]: i["how"] for i in entry.get("named_issues") or ()}
    if named != {12: "closes-commit"}:
        problems.append("closed by commit: named issues {0}, expected only #12 closes-commit "
                        "(#14 was closed by hand, #13 is another repository's)".format(named))
    proof = dict(fx["base_comment"], place={"kind": "issue", "number": 12}, posted_at="2026-11-03T00:00:00Z",
                 body="Proven by https://github.com/own/repo/actions/runs/500")
    run = dict(fx["base_named"], contains=[sha])
    if entry and pl.classify(entry, {}, [proof], {"own/repo/500": run}, set(), "own/repo") != pl.STATE_ON_RECORD:
        problems.append("closed by commit: a proof on the issue the merge message closed is not state 2")
    if pl.closing_targets("Resolves: GH-3, closes https://github.com/Own/Repo/issues/4 and "
                          "https://github.com/other/repo/issues/5", "own/repo") != [3, 4]:
        problems.append("closing_targets: {0}, expected [3, 4]".format(pl.closing_targets(
            "Resolves: GH-3, closes https://github.com/Own/Repo/issues/4 and "
            "https://github.com/other/repo/issues/5", "own/repo")))
    # #1314: the decoding is closing_keyword_refs(); an owner spelled like
    # `gh-` or `http` is another repository's slug, not a GH-N or a URL.
    if pl.closing_targets("Fixes gh-tools/x#6, fixes httpx/y#7, fixes #8", "own/repo") != [8]:
        problems.append("closing_targets: another repository's gh-/http-prefixed slug is not dropped")
    return problems


def check_loud_reads():
    """R4 (FR-013, research D6): a read that cannot be decoded, comes back
    empty or carries no time fails; it never reads as an empty thread."""
    problems = []
    bad = [sys.executable, "-c", r"import sys; sys.stdout.buffer.write(b'[\xff\xfe]')"]
    try:
        got = pl._run(bad)
        problems.append("_run: output that is not UTF-8 read as {0!r}, expected a failed read".format(got))
    except pl.ReadError:
        pass
    except Exception as exc:  # noqa: BLE001 - any other exception is the defect
        problems.append("_run: output that is not UTF-8 raised {0!r}, not a failed read".format(exc))
    good = [sys.executable, "-c", r"import sys; sys.stdout.buffer.write('caf\u00e9'.encode('utf-8'))"]
    if pl._run(good) != "café":
        problems.append("_run: UTF-8 output was not decoded as UTF-8: {0!r}".format(pl._run(good)))
    saved = pl.gh_text
    try:
        for reply in ("", "  " + chr(10)):
            pl.gh_text = lambda args, reply=reply: reply
            for paginate in (False, True):
                try:
                    got = pl.api("repos/own/repo/issues/5/comments", paginate)
                    problems.append("api(paginate={0}): an empty read gave {1!r}, expected a failed read".format(
                        paginate, got))
                except pl.ReadError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    problems.append("api(paginate={0}): an empty read raised {1!r}, not a failed read".format(
                        paginate, exc))
    finally:
        pl.gh_text = saved
    user = {"login": "owner", "type": "User"}
    reviews = [{"id": 1, "state": "PENDING", "submitted_at": None, "body": "draft", "user": user},
               {"id": 2, "state": "COMMENTED", "submitted_at": "2026-11-03T00:00:00Z", "body": "x", "user": user}]

    def api(path, paginate):
        return reviews if "/reviews" in path else []
    with _FakeReads(api=api):
        try:
            got = pl.Collector("own/repo", "2026-11-10T12:00:00Z").thread("pr", 10)
        except pl.ReadError as exc:
            got = None
            problems.append("thread: a pending review failed the read: {0}".format(exc))
    if got is not None and [c["comment_id"] for c in got] != [2]:
        problems.append("thread: a pending review was kept: {0}".format(
            [(c["comment_id"], c["posted_at"]) for c in got]))
    return problems


def check_read_cost(fx):
    """R5 (research D6, D15): each thread is read once, bounded by `since=`
    at the earliest merge among the entries that read it, at per_page=100;
    a run is looked up only for a comment that passes steps 1-4."""
    problems = []
    older = make_entry(fx["base_entry"])  # e1, PR 10, issue 100, merged 2026-11-01
    newer = make_entry(fx["base_entry"], {"sha": "e2", "pr": 11, "merged_at": "2026-11-05T00:00:00Z"})
    with _FakeReads(api=lambda path, paginate: []) as fake:
        col = pl.Collector("own/repo", "2026-11-10T12:00:00Z")
        col.bound_threads([newer, older])
        col.comments_for(newer)  # the build reads newest first
        col.comments_for(older)
    reads = sorted(c[1] for c in fake.calls)
    want = sorted([
        "repos/own/repo/issues/100/comments?per_page=100&since=2026-11-01T00:00:00Z",
        "repos/own/repo/issues/10/comments?per_page=100&since=2026-11-01T00:00:00Z",
        "repos/own/repo/pulls/10/comments?per_page=100&since=2026-11-01T00:00:00Z",
        "repos/own/repo/pulls/10/reviews?per_page=100",
        "repos/own/repo/issues/11/comments?per_page=100&since=2026-11-05T00:00:00Z",
        "repos/own/repo/pulls/11/comments?per_page=100&since=2026-11-05T00:00:00Z",
        "repos/own/repo/pulls/11/reviews?per_page=100",
    ])
    if reads != want:
        problems.append("thread reads: {0}, expected {1}".format(reads, want))
    base = fx["base_comment"]
    comments = {"e1": [dict(base, comment_id=1, posted_at="2026-10-31T00:00:00Z",
                            body="https://github.com/own/repo/actions/runs/7 #10"),
                       dict(base, comment_id=2, body="https://github.com/own/repo/actions/runs/8 #10"),
                       dict(base, comment_id=3, account_type="Bot",
                            body="https://github.com/own/repo/actions/runs/9 #10")]}

    def api(path, paginate):
        run_id = int(path.rsplit("/", 1)[-1])
        return {"id": run_id, "head_sha": "0" * 40, "run_started_at": "2026-11-02T00:00:00Z",
                "html_url": "https://github.com/own/repo/actions/runs/{0}".format(run_id)}
    with _FakeReads(api=api) as fake:
        pl.Collector("own/repo", "2026-11-10T12:00:00Z").named_runs(comments, [older])
    looked = [c[1] for c in fake.calls]
    if looked != ["repos/own/repo/actions/runs/8"]:
        problems.append("named runs: looked up {0}; expected only run 8 (run 7 is named before the "
                        "merge, run 9 by an unmarked bot)".format(looked))
    return problems


def check_classifier_corrections(fx):
    """R6: the shared set is the window's, a PR URL counts only for this
    repository, reduce_body keeps every line the classifier reads, and the
    replay flags a direct push in state 4 or 5."""
    problems = []
    start, end, repo = fx["window"]["start"], fx["window"]["end"], fx["repository"]
    # (a) FR-006: an aged-out PR naming the same issue does not make it shared
    # for the window ...
    e1 = make_entry(fx["base_entry"])  # PR 10, issue 100, merged 2026-11-01
    aged = make_entry(fx["base_entry"], {"sha": "a1", "pr": 20, "merged_at": "2026-10-10T12:00:00Z"})
    on_issue = dict(fx["base_comment"], place={"kind": "issue", "number": 100},
                    body="see https://github.com/own/repo/actions/runs/500")
    for_aged = dict(on_issue, posted_at="2026-10-10T13:00:00Z",
                    body="see https://github.com/own/repo/actions/runs/600")
    named = {"own/repo/500": dict(fx["base_named"], contains=["e1"]),
             "own/repo/600": dict(fx["base_named"], run_id=600, run_started_at="2026-10-10T12:30:00Z",
                                  contains=["a1"])}
    states, aged_out = pl.classify_all([e1, aged], {}, {"e1": [on_issue], "a1": [for_aged]}, named,
                                       repo, start, end)
    if states.get("e1") != pl.STATE_ON_RECORD:
        problems.append("shared issues: an aged-out PR on the same issue made a window entry need its "
                        "PR named (state {0}, expected 2)".format(states.get("e1")))
    # ... but the aged-out pass, classified as if the window began a day
    # earlier, has both PRs and treats the issue as shared.
    if aged_out != 1:
        problems.append("shared issues: aged-out count {0}, expected 1 (the issue is shared on the "
                        "aged-out pass, so the comment naming no PR does not count)".format(aged_out))
    # (b) a PR URL names the PR only for this repository.
    for body, want in (("https://github.com/other/repo/pull/10", False),
                       ("https://github.com/Own/Repo/pull/10", True),
                       ("https://github.com/own/repo/pull/101", False),
                       ("other/repo#10", False), ("for #10.", True)):
        if pl.pr_named(body, 10, repo) != want:
            problems.append("pr_named({0!r}, 10): {1}, expected {2}".format(body, not want, want))
    # (c) the corpus keeps every line the classifier reads, and only those.
    body = "\n".join(["Proven on https://github.com/own/repo/pull/10",
                      "<!-- wing-commander-board-item: {\"step\": \"proven\"} -->",
                      "run https://github.com/own/repo/actions/runs/500/job/7",
                      "a private line", "other/repo#10 is not a reference"])
    want = "\n".join(body.splitlines()[:3] + ["…", "…"])
    got = pl.reduce_body(body, repo)
    if got != want:
        problems.append("reduce_body: {0!r}, expected {1!r}".format(got, want))
    e2 = make_entry(fx["base_entry"], {"sha": "e2", "pr": 11})
    url_only = dict(on_issue, body="Proven on https://github.com/own/repo/pull/10\n"
                                   "https://github.com/own/repo/actions/runs/500")
    live, _ = pl.classify_all([e1, e2], {}, {"e1": [url_only], "e2": [url_only]}, named, repo, start, end)
    reduced = dict(url_only, body=pl.reduce_body(url_only["body"], repo))
    replay, _ = pl.classify_all([e1, e2], {}, {"e1": [reduced], "e2": [reduced]}, named, repo, start, end)
    if live != replay or live.get("e1") != pl.STATE_ON_RECORD:
        problems.append("reduce_body: the live build gave {0}, the replay of the reduced body {1}".format(
            live, replay))
    # (d) a direct push in state 4 or 5 is flagged by the replay, keyed by SHA.
    push = make_entry(fx["base_entry"], {"sha": "d4", "pr": None, "named_issues": []})
    corpus = {"repository": repo, "window": fx["window"], "entries": [push], "runs": {},
              "named_runs": {}, "comments": {}}
    key = {"proofs": [], "listed": [], "expected_differences": []}
    none = {"window": fx["window"], "sizes": {"proofs": 0, "listed": 0}}
    if not sc001_replay(corpus, key, **none):
        problems.append("SC-001: a direct push in state 4 was not flagged")
    listed = dict(key, expected_differences=[{"pr": None, "sha": "d4", "half": "listed", "expected_state": 4,
                                              "actual_state": 4, "reason": "own-tree", "note": "x"}])
    if sc001_replay(corpus, listed, **none):
        problems.append("SC-001: a direct push's listed difference was rejected: {0}".format(
            sc001_replay(corpus, listed, **none)))
    return problems


def check_utc():
    """R2: every time is read and written in UTC (FR-011, data-model Entry)."""
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    problems = []
    if pl.parse_time("2026-11-09T20:00:00-05:00").isoformat() != "2026-11-10T01:00:00+00:00":
        problems.append("parse_time keeps the offset instead of converting to UTC")
    start, end = pl.window_for("2026-11-17T00:00:00-05:00")
    if end.isoformat() != "2026-11-17T05:00:00+00:00":
        problems.append("window_for: an offset --end gave {0}".format(end.isoformat()))
    doc = pl.assemble_report([], {}, {}, {}, "own/repo", "2026-11-10T07:00:00-05:00", "h",
                             MAX_BODY_UNITS, utf16_len)
    if doc["built_at"] != "2026-11-10T12:00:00Z" or doc["window"]["end"] != "2026-11-10T12:00:00Z":
        problems.append("report: an offset build time was written as {0}, window {1}".format(
            doc["built_at"], doc["window"]))
    cap = pl.capture({"built_at": "2026-11-17T00:00:00-05:00", "runs": {}, "comments": {},
                      "repository": "own/repo"},
                     "2026-11-16T23:59:59-05:00")
    if cap["window"]["end"] != "2026-11-17T05:00:00Z" or cap["as_of"] != "2026-11-17T04:59:59Z":
        problems.append("capture: offset times written as window {0}, as-of {1}".format(
            cap["window"], cap["as_of"]))
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
            # #889: an unparseable stage array is fatal only on the current
            # tree; a historical tree carrying one gets no nightly edges.
            ar = os.path.join(wf, "auto-release.yml")
            with open(ar, "w", encoding="utf-8") as fh:
                fh.write("on: {workflow_dispatch: {}}\njobs: {}\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "break")
            broken = pl._run(["git", "rev-parse", "HEAD"], cwd=repo).strip()
            try:
                pl.tree_reaching(broken, [".github/workflows/implement.yml"])
                problems.append("trees: an unparseable stage array on the current tree did not fail")
            except ValueError:
                pass
            with open(ar, "w", encoding="utf-8") as fh:
                fh.write(AUTO_RELEASE_TEXT)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "restore")
            try:
                old = {w["path"]: w["reached_via"]
                       for w in pl.tree_reaching(broken, [".github/workflows/implement.yml"])}
                if old.get(".github/workflows/auto-release.yml") == "nightly-e2e":
                    problems.append("trees: a historical tree with no parseable stage array gained a nightly edge")
            except ValueError as exc:
                problems.append("trees: a historical tree's unparseable stage array failed the build: {0}".format(exc))
        finally:
            os.chdir(previous)
    return problems


def check_budget():
    """The build fails with its own one line before the job's timeout cancels
    it silently: every git/gh call waits at most CALL_TIMEOUT, never past the
    build's budget, and a build past its budget fails at its next call."""
    import time
    problems = []
    saved = pl.CALL_TIMEOUT
    slow = [sys.executable, "-c", "import time; time.sleep(10)"]
    try:
        pl.CALL_TIMEOUT = 1
        began = time.monotonic()
        try:
            pl._run(slow)
            problems.append("budget: a call that never answers was waited for to the end")
        except pl.ReadError as exc:
            if "gave no answer within 1 s" not in str(exc):
                problems.append("budget: a hung call failed with {0!r}".format(str(exc)[:160]))
        if time.monotonic() - began > 5:
            problems.append("budget: a hung call was not cut off at CALL_TIMEOUT")
    finally:
        pl.CALL_TIMEOUT = saved
    try:
        pl.start_budget(0)
        for label, act in (("_run", lambda: pl._run(["git", "--version"])),
                           ("is_ancestor", lambda: pl.is_ancestor("HEAD", "HEAD")),
                           ("commit_present", lambda: pl.commit_present("HEAD")),
                           ("tree_reaching", lambda: pl.tree_reaching("HEAD", []))):
            try:
                act()
                problems.append("budget: {0} ran after the build's budget was spent".format(label))
            except pl.ReadError as exc:
                if "ran past its 23-minute budget" not in str(exc):
                    problems.append("budget: {0} failed with {1!r}".format(label, str(exc)[:160]))
        pl.start_budget(2)
        began = time.monotonic()
        try:
            pl._run(slow)
            problems.append("budget: a call outlived the build's budget")
        except pl.ReadError as exc:
            if "ran past its 23-minute budget during" not in str(exc):
                problems.append("budget: a call cut short by the budget failed with {0!r}".format(str(exc)[:160]))
        if time.monotonic() - began > 5:
            problems.append("budget: a call was allowed CALL_TIMEOUT though the budget had less left")
    finally:
        pl.start_budget(None)
    import contextlib
    import io
    saved_collect, saved_start = pl.collect, pl.start_budget
    started = []
    try:
        pl.start_budget = lambda seconds=None: started.append(True)
        pl.collect = lambda *a, **k: (_ for _ in ()).throw(pl.ReadError("stop"))
        with contextlib.redirect_stdout(io.StringIO()):
            pl.main(["build", "--repository", "own/repo", "--out", os.devnull])
        if not started:
            problems.append("budget: `build` does not start the budget")
    finally:
        pl.collect, pl.start_budget = saved_collect, saved_start
    return problems


def _tree_snapshot(root, dest):
    """Copy the files `git archive` would carry for TREE_PATHSPECS -- tracked
    and untracked-but-not-ignored, so a local edit is still scanned -- from
    the working tree at `root` into `dest`. The tree-cost check scans this
    fixed copy, never the live tree: under `run-local-gates.py --jobs N` other
    gates write ignored files into it mid-scan (the byte cache Python writes
    in .github/actions/_shared/__pycache__ when a gate imports a shared
    script), which a composite directory's walk picked up between two scans.
    A file that vanishes while it is copied is left out of the copy."""
    import shutil
    from wc_repo_files import repo_files
    for rel in sorted(set(repo_files(root, untracked=True, pathspecs=pl.TREE_PATHSPECS))):
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            shutil.copy2(os.path.join(root, rel), target, follow_symlinks=False)
        except (FileNotFoundError, IsADirectoryError):
            continue


def check_tree_snapshot():
    """_tree_snapshot copies what the archive would carry, as it stood when
    copied: local edits and new files yes; ignored files and the scripts'
    test and fixture subdirectories no; a later write to the live tree
    never reaches the copy."""
    import subprocess
    import tempfile
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        root, dest = os.path.join(tmp, "repo"), os.path.join(tmp, "copy")
        files = {".gitignore": "__pycache__/\n",
                 ".github/workflows/a.yml": "on: push\n",
                 ".github/actions/x/action.yml": "runs: {}\n",
                 ".github/scripts/board_x.py": "import os\n",
                 ".github/scripts/tests/t.py": "x\n"}
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        subprocess.run(["git", "init", "-q", root], check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        for rel, text in ((".github/actions/x/new.sh", "echo\n"),
                          (".github/actions/x/__pycache__/m.pyc", "pyc"),
                          (".github/workflows/a.yml", "on: pull_request\n")):
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        _tree_snapshot(root, dest)
        with open(os.path.join(root, ".github/workflows/a.yml"), "w", encoding="utf-8") as fh:
            fh.write("on: written after the copy\n")
        got = sorted(os.path.relpath(os.path.join(d, n), dest).replace(os.sep, "/")
                     for d, _ds, ns in os.walk(dest) for n in ns)
        want = [".github/actions/x/action.yml", ".github/actions/x/new.sh",
                ".github/scripts/board_x.py", ".github/workflows/a.yml"]
        if got != want:
            problems.append("tree snapshot: copied {0}, expected {1}".format(got, want))
        elif open(os.path.join(dest, ".github/workflows/a.yml"), encoding="utf-8").read() != "on: pull_request\n":
            problems.append("tree snapshot: the copy does not hold the working tree as it stood when copied")
        # The copy is no git working tree: a pathspec listing there has no
        # walk to fall back on, so it raises instead of listing everything.
        from wc_repo_files import repo_files
        try:
            repo_files(dest, untracked=True, pathspecs=pl.TREE_PATHSPECS)
            problems.append("tree snapshot: a pathspec listing outside a git tree walked the disk")
        except RuntimeError:
            pass
    return problems


def check_tree_cost():
    """A merge's tree is scanned once per merge in the window (87 at the
    2026-11-26 timeouts), so its cost bounds the build: an unchanged
    workflow text is parsed once per build, a path absent from a text never
    reaches the mention regex, and the archive leaves out the tests and
    fixtures the scan never reads. The scans read a fixed copy of the tree
    (_tree_snapshot), so a gate writing to the live tree in parallel cannot
    make two scans differ, and nothing the scan reads is a file git ignores."""
    import board_prove as bp
    import subprocess
    import tempfile
    problems = []
    parses = []
    real = bp.yaml.safe_load
    repo = os.path.join(HERE, "..", "..")

    def counting(text, *a, **k):
        parses.append(1)
        return real(text, *a, **k)
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        _tree_snapshot(repo, tmp)
        bp.yaml.safe_load = counting
        try:
            os.chdir(tmp)
            first = bp.scan_dispatchable_and_uses_graph(bp.WORKFLOWS_DIR)
            before = len(parses)
            again = bp.scan_dispatchable_and_uses_graph(bp.WORKFLOWS_DIR)
            bp.workflow_triggers(".github/workflows/wing-commander-proof-list.yml")
            if len(parses) != before:
                problems.append("tree cost: {0} unchanged workflow texts were parsed again".format(
                    len(parses) - before))
            if first != again:
                problems.append("tree cost: a second scan of the same tree differs from the first")
        finally:
            bp.yaml.safe_load = real
            os.chdir(previous)
    scanned = sorted(set(first[1]) | set(p for refs in first[1].values() for p in refs))
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], input="\n".join(scanned),
                             capture_output=True, text=True, cwd=repo).stdout.split()
    if ignored:
        problems.append("tree cost: the scan read files git ignores, which the archive never carries: "
                        "{0}".format(", ".join(ignored[:5])))

    class Counting:
        def __init__(self):
            self.searches = 0

        def __getattr__(self, name):
            return getattr(real_re, name)

        def search(self, *a, **k):
            self.searches += 1
            return real_re.search(*a, **k)
    real_re, shim = bp.re, Counting()
    bp.re = shim
    try:
        absent = bp._mentions("x" * 1000, ".github/scripts/foo.py")
        present = bp._mentions("run: .github/scripts/foo.py\n", ".github/scripts/foo.py")
        longer = bp._mentions("run: .github/scripts/foo.py.bak\n", ".github/scripts/foo.py")
    finally:
        bp.re = real_re
    if absent or not present or longer:
        problems.append("tree cost: _mentions answers changed ({0}, {1}, {2})".format(absent, present, longer))
    if shim.searches != 2:
        problems.append("tree cost: _mentions ran {0} regex searches for 3 texts, 1 lacking the path; "
                        "expected 2".format(shim.searches))

    import subprocess
    import tarfile
    import io
    out = subprocess.run(["git", "archive", "HEAD", "--"] + list(pl.TREE_PATHSPECS), capture_output=True,
                         cwd=os.path.join(HERE, "..", ".."))
    if out.returncode != 0:
        problems.append("tree cost: the scan's pathspecs do not archive: {0}".format(out.stderr[:200]))
        return problems
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
        names = tar.getnames()
    if any(n.startswith(".github/scripts/") and n.count("/") > 2 for n in names):
        problems.append("tree cost: the archive carries .github/scripts subdirectories (tests, fixtures)")
    for want in (".github/workflows/auto-release.yml", ".github/scripts/board_prove.py",
                 ".github/actions/wing-commander-watch-guard/action.yml"):
        if want not in names:
            problems.append("tree cost: the archive lacks {0}, which the scan reads".format(want))
    return problems


def check_run_list_cost():
    """A run list's count is read as a one-run page, never a full page that
    the paged read then fetches again: six workflows pass the 1,000-run cap
    and are read by day, one count per day each (2026-11-26)."""
    problems = []

    def api(path, paginate):
        if paginate:
            return []
        # 1,500 runs over the window sends the read into day slices.
        return {"total_count": 1500 if "created=%3E%3D" in path else 40, "workflow_runs": []}
    with _FakeReads(api=api) as fake:
        col = pl.Collector("own/repo", "2026-11-10T12:00:00Z")
        col.workflow_runs(".github/workflows/wrap.yml")
    counts = [c[1] for c in fake.calls if not c[2]]
    paged = [c[1] for c in fake.calls if c[2]]
    if not counts or not paged:
        problems.append("run list cost: the sliced read made {0} counts and {1} paged reads".format(
            len(counts), len(paged)))
    wide = [q for q in counts if "per_page=1&" not in q or "per_page=100" in q]
    if wide:
        problems.append("run list cost: {0} of {1} counts read a full page, e.g. {2}".format(
            len(wide), len(counts), wide[0]))
    if any("per_page=100" not in q for q in paged):
        problems.append("run list cost: a paged read is not at per_page=100")
    return problems


def check_deleted_workflow_runs():
    """#889: a workflow gone from the default branch is read from the
    repository's run list, sliced by day as the main path is (the repository
    passes 1,000 runs in any window here), and a run whose `path` carries an
    `@refs/...` suffix is still that workflow's run."""
    problems = []
    gone = ".github/workflows/wrap.yml"

    def api(path, paginate):
        if "/workflows/wrap.yml/" in path:
            raise pl.NotFound("gh api {0}: (HTTP 404)".format(path))
        if not paginate:
            return {"total_count": 1500 if "created=%3E%3D" in path else 40, "workflow_runs": []}
        if "created=2026-10-10T12:00:00Z.." not in path:
            return []
        return [{"id": 1, "path": gone + "@refs/heads/main"}, {"id": 2, "path": gone},
                {"id": 3, "path": ".github/workflows/other.yml"},
                {"id": 4, "path": gone + ".bak"}]
    with _FakeReads(api=api) as fake:
        try:
            got = pl.Collector("own/repo", "2026-11-10T12:00:00Z").workflow_runs(gone)
        except pl.ReadError as exc:
            return ["deleted workflow: the repository's run list over the cap failed the read: {0}".format(exc)]
    ids = sorted(r["id"] for r in got)
    if ids != [1, 2]:
        problems.append("deleted workflow: kept runs {0}, expected [1, 2] (the @refs suffix "
                        "stripped, other paths dropped)".format(ids))
    days = [c[1] for c in fake.calls if c[2] and "/actions/runs?" in c[1]]
    if len(days) != 31:
        problems.append("deleted workflow: {0} day-sliced paged reads, expected 31".format(len(days)))
    return problems


def check_progress():
    """#889: a build logs each phase, and every PROGRESS_EVERY merges, with
    elapsed time and calls so far, so a slow build's log says where the time
    went; it is silent until main() turns it on, and main() turns it off."""
    import contextlib
    import io
    import re
    problems = []
    shape = re.compile(r"^wc_proof_list: .+ \(\d+\.\d s; \d+ gh and (\d+) git calls so far\)$")
    quiet = io.StringIO()
    with contextlib.redirect_stderr(quiet), contextlib.redirect_stdout(quiet):
        pl.progress("not started")
    if quiet.getvalue():
        problems.append("progress: printed before main() turned it on: {0!r}".format(quiet.getvalue()))
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        for n in range(12):
            _commit(repo.root, {".github/workflows/x.yml": "# {0}\n".format(n)},
                    "2026-11-0{0}T{1:02d}:00:00 +0000".format(1 + n % 9, n))

        def gh(args):
            if "rate_limit" in args:
                return "5000\n"
            raise AssertionError("unexpected gh " + " ".join(args))
        stream = io.StringIO()
        pl.start_progress(stream)
        try:
            with _FakeReads(api=lambda path, paginate: [], gh=gh, tree=lambda s, c: []):
                pl.collect("own/repo", "2026-11-10T12:00:00Z")
        except (pl.ReadError, AssertionError) as exc:
            return ["progress: the faked build failed: {0}".format(exc)]
        finally:
            pl._progress["stream"] = None
    lines = stream.getvalue().splitlines()
    for want in ("start: 5000 API requests remain", "entries: 10 of 12 merges read",
                 "entries: 12 merges read, 12 need a run", "comments: 0 threads read",
                 "runs: 0 runs of 0 reaching workflows read", "named runs: 0 read"):
        if not any(line.startswith("wc_proof_list: " + want + " (") for line in lines):
            problems.append("progress: no {0!r} line in {1}".format(want, lines))
    bad = [line for line in lines if not shape.match(line)]
    if bad or not lines:
        problems.append("progress: lines without elapsed time and call counts: {0}".format(bad or lines))
    elif int(shape.match(lines[-1]).group(1)) < 12:
        # At least one per merge: each merge's changed-path listing is a git
        # call, made by diff_name_list outside _subprocess.
        problems.append("progress: {0} git calls counted for 12 merges; each merge's "
                        "changed-path listing was not counted".format(shape.match(lines[-1]).group(1)))
    saved = pl.collect
    pl.collect = lambda *a, **k: (_ for _ in ()).throw(pl.ReadError("stop"))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pl.main(["build", "--repository", "own/repo", "--out", os.devnull])
    finally:
        pl.collect = saved
    if pl._progress["stream"] is not None:
        problems.append("progress: main() left the progress lines on")
    return problems


# Research D6 "Reused homes": wc_proof_list.py keeps no copy of these. Each
# seed is a copy the scan must catch when appended to the real source.
FORBIDDEN_HOME_SEEDS = (
    ("a `Board item:` pattern", 'BOARD_ITEM_RE = re.compile(r"Board item: #(\\d+)")\n'),
    ("a closing-keyword pattern",
     'CLOSES_RE = re.compile(r"(?i)\\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\\s+#(\\d+)")\n'),
    ("a run-link pattern", 'RUN_RE = re.compile(r"https://github\\.com/([^/]+/[^/]+)/actions/runs/(\\d+)")\n'),
    ("the board item marker's name", 'MARKER = "<!-- wing-commander-board-item: "\n'),
    ("a UTF-16 counter", 'def units(text):\n    return len(text.encode("utf-16-le")) // 2\n'),
    ("a UTF-16 counter", 'def units(text):\n    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)\n'),
    ("a `git diff --name-only` call", 'def changed(a, b):\n    return git("diff", "--name-only", a, b)\n'),
    ("a `git diff --name-only` call", 'CHANGED = "git diff --name-only {0} {1}"\n'),
    ("a call to `_gh_json`", 'def read(path):\n    return wc_board_status._gh_json(path)\n'),
    ("a call to `_gh_json`", 'from wc_board_status import _gh_json\n'),
)
_REGEX_CHARS = set("\\([|+*^$")


def forbidden_home_problems(source):
    """What `source` defines that research D6 puts in another home: a
    `Board item:`, closing-keyword or run-link pattern, the board item
    marker's name, a UTF-16 counter, a `git diff --name-only` call or a
    `_gh_json` call. Docstrings are prose and are not read."""
    import ast
    import re
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    closing = re.compile(r"(?i)\b(?:fix|close|resolve)")
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and id(node) not in docstrings:
            value = node.value
            if isinstance(value, str):
                regexy = bool(_REGEX_CHARS & set(value)) or "#" in value
                if "board item" in value.lower():
                    found.add("a `Board item:` pattern")
                if closing.search(value) and regexy:
                    found.add("a closing-keyword pattern")
                if "actions/runs" in value and bool(_REGEX_CHARS & set(value)):
                    found.add("a run-link pattern")
                if "wing-commander-board-item" in value:
                    found.add("the board item marker's name")
                if re.search(r"\bdiff\s+--name-only\b", value):
                    found.add("a `git diff --name-only` call")
            elif isinstance(value, int) and not isinstance(value, bool) and value in (0xFFFF, 0x10000):
                found.add("a UTF-16 counter")
        elif isinstance(node, (ast.Call, ast.List, ast.Tuple)):
            items = node.args if isinstance(node, ast.Call) else node.elts
            consts = {a.value for a in items if isinstance(a, ast.Constant) and isinstance(a.value, str)}
            if "diff" in consts and "--name-only" in consts:
                found.add("a `git diff --name-only` call")
            # An encoding to UTF-16 (a message naming "UTF-16 units" is prose).
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("encode", "decode")
                    and any(re.search(r"(?i)utf[-_]?16", c) for c in consts)):
                found.add("a UTF-16 counter")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.search(r"(?i)utf_?16", node.name):
            found.add("a UTF-16 counter")
        elif isinstance(node, ast.Name) and node.id == "_gh_json":
            found.add("a call to `_gh_json`")
        elif isinstance(node, ast.Attribute) and node.attr == "_gh_json":
            found.add("a call to `_gh_json`")
        elif isinstance(node, ast.alias) and node.name == "_gh_json":
            found.add("a call to `_gh_json`")
    return sorted(found)


def check_forbidden_homes():
    """Research D6: wc_proof_list.py defines none of the patterns, counters or
    calls that have a home elsewhere; one seeded copy of each is caught."""
    with open(os.path.join(HERE, "wc_proof_list.py"), encoding="utf-8") as fh:
        source = fh.read()
    problems = ["wc_proof_list.py defines {0}; D6 puts it in its one home".format(what)
                for what in forbidden_home_problems(source)]
    for what, seed in FORBIDDEN_HOME_SEEDS:
        if what not in forbidden_home_problems(source + "\n\n" + seed):
            problems.append("forbidden-home fixture: a seeded copy of {0} was not caught: {1!r}".format(
                what, seed.strip()))
    return problems


# -- review coverage (#889, found by the code review of #1154) ----------------
# Each check below drives one branch of wc_proof_list.py that no case reached;
# each fails when that branch is removed or its boundary moved.
def check_rebase_merge():
    """Collector.entries: a rebase merge leaves only its last commit as the
    PR's merge_commit_sha, so an earlier commit takes the one merged PR the
    commit lists; two merged PRs, or none merged, leave it a direct push."""
    problems = []
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        sha = _commit(repo.root, {"docs/a.md": "a\n"}, "2026-11-01T00:00:00 +0000")
        merged = {"number": 77, "merge_commit_sha": "f" * 40, "merged_at": "2026-11-01T00:05:00Z"}
        cases = [
            ("the one merged PR of a rebase-merged commit", [merged, {"number": 78, "merged_at": None}], 77),
            ("two merged PRs listing the commit", [merged, dict(merged, number=79)], None),
            ("no merged PR listing the commit", [dict(merged, merged_at=None)], None),
            ("the PR whose merge commit it is wins", [merged, dict(merged, number=80, merge_commit_sha=sha)], 80),
        ]
        view = {"title": "x", "headRefName": "fix/x", "body": "", "closingIssuesReferences": []}
        for label, pulls, want in cases:
            def api(path, paginate, pulls=pulls):
                if path.endswith("/commits/{0}/pulls".format(sha)):
                    return pulls
                raise AssertionError("unexpected read " + path)
            with _FakeReads(api=api, gh=lambda args: json.dumps(view), tree=lambda s, c: []):
                try:
                    entries = pl.Collector("own/repo", "2026-11-10T12:00:00Z").entries()
                except (pl.ReadError, AssertionError) as exc:
                    problems.append("rebase merge: {0}: the read failed: {1}".format(label, exc))
                    continue
            got = entries[0]["pr"] if len(entries) == 1 else entries
            if got != want:
                problems.append("rebase merge: {0}: PR {1!r}, expected {2!r}".format(label, got, want))
    return problems


def check_run_ancestry_skip():
    """Collector.run_record: a run that started at or before a merge cannot
    contain it, so no ancestry check is made and the run does not count;
    a run started after it is checked."""
    problems = []
    entry = {"sha": "e1", "merged_at": "2026-11-01T00:00:00Z"}
    saved = (pl.is_ancestor, pl.commit_present)
    for started, want_calls in (("2026-10-31T23:59:59Z", 0), ("2026-11-01T00:00:00Z", 0),
                                ("2026-11-01T00:00:01Z", 1)):
        calls = []
        pl.is_ancestor = lambda a, d, calls=calls: calls.append((a, d)) or True
        pl.commit_present = lambda sha: True
        try:
            rec = pl.Collector("own/repo", "2026-11-10T12:00:00Z").run_record(
                {"id": 1, "head_sha": "h1", "path": "p", "run_started_at": started}, [entry])
        finally:
            pl.is_ancestor, pl.commit_present = saved
        if len(calls) != want_calls or (rec["contains"] == ["e1"]) != bool(want_calls):
            problems.append("run ancestry: a run started {0} for a merge at {1} made {2} ancestry "
                            "check(s) and contains {3}; expected {4}".format(
                                started, entry["merged_at"], len(calls), rec["contains"], want_calls))
    return problems


def check_capture_clip():
    """capture(): the corpus keeps what was known at `as_of` -- a merge, a
    comment, a run or a named run at or before it, or with no time -- and
    drops what came after."""
    problems = []
    as_of = "2026-11-16T12:00:00Z"
    at, after = as_of, "2026-11-16T12:00:01Z"
    bundle = {"repository": "own/repo", "built_at": "2026-11-17T00:00:00Z",
              "entries": [{"sha": "k1", "merged_at": at}, {"sha": "d1", "merged_at": after}, {"sha": "k2"}],
              "named_runs": {"own/repo/1": {"run_started_at": at}, "own/repo/2": {"run_started_at": after}},
              "comments": {"k1": [{"comment_id": 1, "posted_at": at, "body": "x"},
                                  {"comment_id": 2, "posted_at": after, "body": "x"}]},
              "runs": {"w.yml": [{"run_id": 1, "run_started_at": at}, {"run_id": 2, "run_started_at": after}]}}
    cap = pl.capture(bundle, as_of)
    got = ([e["sha"] for e in cap["entries"]], sorted(cap["named_runs"]),
           [c["comment_id"] for c in cap["comments"]["k1"]], [r["run_id"] for r in cap["runs"]["w.yml"]])
    want = (["k1", "k2"], ["own/repo/1"], [1], [1])
    if got != want:
        problems.append("capture: kept {0} (entries, named runs, comments, runs), expected {1}".format(got, want))
    return problems


def check_git_failed_reads():
    """FR-013: a shallow checkout, a `git archive` that fails, a
    `git merge-base` that fails and a lifecycle spec-meta.json that does not
    read each fail the build with their own ReadError, never an empty list."""
    import subprocess
    import tempfile
    problems = []
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        sha = _commit(repo.root, {"b.txt": "b\n", "specs/124-own/spec-meta.json": "not json\n",
                                  "specs/125-null/spec-meta.json": '{"issue": null}\n'},
                      "2026-11-01T00:00:00 +0000")
        missing = "0123456789" * 4
        col = pl.Collector("own/repo", "2026-11-10T12:00:00Z")
        cases = [
            ("a git archive of a missing commit", lambda: pl.tree_reaching(missing, ["b.txt"]), "git archive"),
            ("a merge-base of a missing commit", lambda: pl.is_ancestor(missing, sha), "git merge-base failed"),
            ("a spec-meta.json that is not JSON",
             lambda: col.lifecycle_issue(sha, "Finalize: own (#5)", "spec/124-own"), "unreadable at"),
            ("a spec-meta.json with no issue",
             lambda: col.lifecycle_issue(sha, "Finalize: own (#5)", "spec/125-null"), "unreadable at"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            shallow = os.path.join(tmp, "shallow")
            subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + repo.root.replace(os.sep, "/"),
                            shallow], check=True, capture_output=True)
            previous = os.getcwd()

            def in_shallow():
                os.chdir(shallow)
                try:
                    return pl.first_parent_commits()
                finally:
                    os.chdir(previous)
            cases.append(("a shallow checkout", in_shallow, "the checkout is shallow"))
            for label, act, text in cases:
                try:
                    got = act()
                    problems.append("git reads: {0} gave {1!r}, expected a failed read".format(label, got))
                except Exception as exc:  # noqa: BLE001 - the type and message are the test
                    if not isinstance(exc, pl.ReadError) or text not in str(exc):
                        problems.append("git reads: {0} failed with {1}: {2!r}, not a failed read "
                                        "saying {3!r}".format(label, type(exc).__name__, str(exc)[:160], text))
    return problems


def check_reusable_only_filter():
    """tree_reaching (research D4): a workflow_call-only workflow is dropped
    when an in-repository caller that reaches the same path is listed, and
    kept, marked as having no runs of its own, when none is."""
    problems = []
    with _InRepo() as repo:
        sha = _commit(repo.root, {
            ".github/workflows/caller.yml": ("on: {push: {}}\njobs:\n  j:\n"
                                             "    uses: ./.github/workflows/called.yml\n"),
            ".github/workflows/called.yml": "on: {workflow_call: {}}\njobs: {}\n",
            ".github/workflows/orphan.yml": "on: {workflow_call: {}}\njobs: {}\n"},
            "2026-11-01T00:00:00 +0000")
        try:
            called = {w["path"]: w for w in pl.tree_reaching(sha, [".github/workflows/called.yml"])}
            orphan = {w["path"]: w for w in pl.tree_reaching(sha, [".github/workflows/orphan.yml"])}
        except (pl.ReadError, ValueError) as exc:
            return ["reusable-only: the tree read failed: {0}".format(exc)]
    if sorted(called) != [".github/workflows/caller.yml"]:
        problems.append("reusable-only: a called workflow with a listed caller gave {0}, expected the "
                        "caller only".format(sorted(called)))
    got = orphan.get(".github/workflows/orphan.yml") or {}
    if sorted(orphan) != [".github/workflows/orphan.yml"] or got.get("runs_of_its_own") is not False:
        problems.append("reusable-only: a workflow_call-only workflow with no caller gave {0}, expected it "
                        "kept with no runs of its own".format(orphan))
    return problems


def check_window_edges(fx):
    """research D10 and FR-012 at their boundaries: a merge exactly at the
    window start is aged out, not in the window; one exactly AGED_OUT_HOURS
    before it is neither; one at the end is in. A comment posted, a named
    run started or an unresolvable run started exactly at the merge does
    not count and is not set apart."""
    problems = []
    start, end, repo = fx["window"]["start"], fx["window"]["end"], fx["repository"]
    day = pl.parse_time(start) - pl.datetime.timedelta(hours=pl.AGED_OUT_HOURS)
    edges = [("s_at_start", start), ("s_day_before", pl.utc_text(day)),
             ("s_in_day", pl.utc_text(day + pl.datetime.timedelta(seconds=1))), ("s_at_end", end)]
    entries = [make_entry(fx["base_entry"], {"sha": sha, "pr": 60 + i, "merged_at": when, "named_issues": []})
               for i, (sha, when) in enumerate(edges)]
    states, aged = pl.classify_all(entries, {}, {}, {}, repo, start, end)
    if sorted(states) != ["s_at_end"] or aged != 2:
        problems.append("window edges: in the window {0}, aged out {1}; expected only the merge at the end, "
                        "and the merges at the start and one second into the aged-out day".format(sorted(states), aged))
    entry = make_entry(fx["base_entry"])
    merged = entry["merged_at"]
    at_merge = dict(fx["base_comment"], posted_at=merged)
    if pl.classify(entry, {}, [at_merge], {"own/repo/500": dict(fx["base_named"])}, set(), repo) == pl.STATE_ON_RECORD:
        problems.append("window edges: a comment posted exactly at the merge counted")
    named = {"own/repo/500": dict(fx["base_named"], run_started_at=merged)}
    if pl.classify(entry, {}, [dict(fx["base_comment"])], named, set(), repo) == pl.STATE_ON_RECORD:
        problems.append("window edges: a named run started exactly at the merge counted")
    runs = {".github/workflows/wrap.yml": [dict(fx["base_run"], run_started_at=merged, resolvable=False,
                                                contains=[])]}
    if pl.set_apart([entry], runs, {}, {}, repo, start, end) != 0:
        problems.append("window edges: an unresolvable run started exactly at the merge was set apart")
    return problems


def check_report_edges(fx):
    """FR-020: the earliest and latest links are the first and last run by
    start time, whatever order the runs were read in; the size limit is
    applied to the names-only form, so a report whose full form is over it
    still builds when the names-only form fits."""
    from board_spec_request_body import utf16_len
    problems = []
    entry = make_entry(fx["base_entry"])
    url = "https://github.com/own/repo/actions/runs/{0}".format
    order = [("2026-11-05T00:00:00Z", 2), ("2026-11-02T00:00:00Z", 1), ("2026-11-09T00:00:00Z", 3),
             ("2026-11-04T00:00:00Z", 4)]
    runs = {".github/workflows/wrap.yml": [dict(fx["base_run"], run_id=n, run_started_at=when, html_url=url(n),
                                                event="push", conclusion="success") for when, n in order]}
    args = ([entry], runs, {}, {}, fx["repository"], "2026-11-10T12:00:00Z", "h")
    huge = 10 ** 6
    doc = pl.assemble_report(*args, huge, utf16_len)
    if "[first]({0}), [last]({1})".format(url(1), url(3)) not in doc["full"]:
        problems.append("report: the earliest and latest links are not runs 1 and 3: {0!r}".format(
            [line for line in doc["full"].splitlines() if "first" in line]))
    fits = utf16_len(doc["names_only"])
    if utf16_len(doc["full"]) <= fits:
        return problems + ["report fixture: the full form is not longer than the names-only form"]
    try:
        pl.assemble_report(*args, fits, utf16_len)
    except ValueError as exc:
        problems.append("report: a names-only form that fits failed the build: {0}".format(exc))
    try:
        pl.assemble_report(*args, fits - 1, utf16_len)
        problems.append("report: a names-only form one unit over the limit did not fail the build")
    except ValueError:
        pass
    return problems


def check_closed_by_commit_edges():
    """Collector.closed_by_commit: an issue the message names but another
    commit closed is not this merge's, and a number that is no issue (404)
    is no candidate, not a failed read."""
    problems = []
    with _InRepo() as repo:
        _commit(repo.root, {"a.txt": "a\n"}, "2026-10-01T00:00:00 +0000")
        sha = _commit(repo.root, {"b.txt": "b\n"}, "2026-11-01T00:00:00 +0000",
                      message="Fix #21, closes #22 and fixes #23\n")
        events = {"21": [{"event": "closed", "commit_id": "f" * 40}],
                  "23": [{"event": "closed", "commit_id": sha}]}

        def api(path, paginate):
            for number, rows in events.items():
                if "/issues/{0}/events".format(number) in path:
                    return rows
            if "/issues/22/events" in path:
                raise pl.NotFound("gh api {0}: (HTTP 404)".format(path))
            raise AssertionError("unexpected read " + path)
        with _FakeReads(api=api):
            try:
                got = pl.Collector("own/repo", "2026-11-10T12:00:00Z").closed_by_commit(sha, {})
            except (pl.ReadError, AssertionError) as exc:
                return ["closed by commit: a 404 or another commit's close failed the read: {0}".format(exc)]
    if got != [23]:
        problems.append("closed by commit: {0}, expected [23] (#21 closed by another commit, #22 a 404)".format(got))
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
    if job.get("timeout-minutes") != 25:
        problems.append("workflow: timeout-minutes is not 25")
    elif pl.BUILD_BUDGET_SECONDS > (job["timeout-minutes"] - 1) * 60:
        problems.append("workflow: the build's {0} s budget leaves under a minute of the {1}-minute "
                        "timeout, so a cancel can still beat the build's own error line".format(
                            pl.BUILD_BUDGET_SECONDS, job["timeout-minutes"]))
    steps = job.get("steps") or []
    names = [s.get("name") for s in steps]
    # #1173 round 5: checkout (pinned to the default branch), then the
    # wing-commander-watch-guard composite, the refusal's and the pause
    # test's one home, with its dispatch-only refusal.
    guard = (steps[1] if len(steps) > 1 else {}) or {}
    if len(steps) != 4 or "actions/checkout@" not in str(steps[0].get("uses")) \
            or guard.get("uses") != "./.github/actions/wing-commander-watch-guard" or guard.get("id") != "pause":
        problems.append("workflow: the steps are not checkout, the watch guard, build, upload: {0}".format(names))
    elif (guard.get("with") or {}).get("refuse-on") != "dispatch" \
            or "default_branch" not in str((guard.get("with") or {}).get("default-branch")):
        problems.append("workflow: the guard does not refuse a dispatch off the default branch")
    elif (steps[0].get("with") or {}).get("ref") != "${{ github.event.repository.default_branch }}":
        problems.append("workflow: the checkout is not pinned to the default branch")
    for step in steps[:2]:
        if "if" in step:
            problems.append("workflow: step {0!r} is conditional".format(step.get("name")))
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
    elif uploads[0]["with"].get("overwrite") is not True:
        # A re-run keeps the run id; without overwrite the second upload of
        # the same name fails (-- see pr-conversation.yml).
        problems.append("workflow: the upload does not set overwrite: true")
    for call in WRITE_CALLS:
        if call in text:
            problems.append("workflow: contains a write or agent call ({0})".format(call))
    return problems


def check_pause_agreement(text):
    """The pause test the workflow runs (the watch guard's pause step) agrees
    with wc_board_status._switch_on on padded and mixed-case values."""
    import subprocess
    import tempfile
    import yaml
    import wc_board_status as bs
    uses = next((s.get("uses") for job in yaml.safe_load(text)["jobs"].values() for s in job["steps"]
                 if s.get("id") == "pause"), None)
    if not uses or not uses.startswith("./"):
        return ["workflow: no step with id pause runs a local composite"]
    with open(os.path.join(HERE, "..", "..", uses[2:], "action.yml"), encoding="utf-8") as fh:
        step = next((s for s in yaml.safe_load(fh)["runs"]["steps"] if s.get("id") == "pause"), None)
    if step is None:
        return ["workflow: the guard has no step with id pause"]
    problems = []
    for value in ("true", "TRUE", "  True  ", "\ttrue\n", "false", "", "yes", "truee", "1"):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "output")
            open(out, "w").close()
            subprocess.run(["bash", "-c", step["run"]], check=True, capture_output=True,
                           env=dict(os.environ, SWITCH_VALUE=value, SWITCH_NAME="X", GITHUB_OUTPUT=out, SCRIPTS=HERE))
            with open(out, encoding="utf-8") as fh:
                got = "paused=true" in fh.read().split()
        if got != bs._switch_on(value):
            problems.append("workflow pause step disagrees with _switch_on on {0!r}: step={1}".format(value, got))
    return problems


def check_workflow():
    with open(os.path.join(HERE, "..", "workflows", "wing-commander-proof-list.yml"), encoding="utf-8") as fh:
        text = fh.read()
    problems = check_workflow_text(text) + check_pause_agreement(text)
    with open(os.path.join(HERE, "wc_proof_list.py"), encoding="utf-8") as fh:
        source = fh.read()
    for call in ("gh_text([\"api\", \"-X", "\"issue\", \"comment\"", "\"issue\", \"edit\"", "\"workflow\", \"run\"", "\"pr\", \"comment\""):
        if call in source:
            problems.append("wc_proof_list.py: contains a write call ({0})".format(call))
    # Fixtures: each mutation of the shipped file must be noticed.
    mutations = [
        ("a refusal made every-run", text.replace("          refuse-on: dispatch\n", "          refuse-on: every-run\n", 1)),
        ("a permission widened", text.replace("issues: read", "issues: write")),
        ("an always() on the build", text.replace("- name: Build the proof list\n        if:",
                                                   "- name: Build the proof list\n        if: always() &&")),
        ("an input on dispatch", text.replace("workflow_dispatch: {}", "workflow_dispatch:\n    inputs:\n      x: {}")),
        ("a dropped gate on the build", text.replace("- name: Build the proof list\n        if: steps.pause.outputs.paused != 'true'\n",
                                                      "- name: Build the proof list\n", 1)),
        ("an unpinned checkout", text.replace("          ref: ${{ github.event.repository.default_branch }}\n", "", 1)),
        ("a write call", text + "      - run: gh issue comment 1 -b x\n"),
        ("the upload's overwrite dropped", text.replace("          overwrite: true\n", "")),
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
EXEMPT_SC001_PENDING = {}
SC001_REASONS = ("own-tree", "FR-005", "FR-006-shared-issue", "FR-013-set-apart")
# SC-001 and data-model.md "SC-001 expected file": the fixed corpus window and
# the answer key's size (the lookup's 10 hand-written proofs, its 21 merges
# with nothing found). Fixtures pass their own; the real replay never does.
SC001_WINDOW = {"start": "2026-10-15T00:00:00Z", "end": "2026-11-17T00:00:00Z"}
SC001_SIZES = {"proofs": 10, "listed": 21}
SC001_HALF_STATES = {"proofs": (2,), "listed": (4, 5)}


def sc001_shape(corpus, expected, window, sizes):
    """Problems with the corpus window or the answer key's shape: the replay
    alone passes `proofs: []`, a dropped proof or two colliding differences."""
    problems = []
    got = corpus.get("window") or {}
    if (got.get("start"), got.get("end")) != (window["start"], window["end"]):
        problems.append("SC-001: the corpus window is {0}..{1}, not {2}..{3}".format(
            got.get("start"), got.get("end"), window["start"], window["end"]))
    halves = {}
    for half in ("proofs", "listed"):
        items = expected.get(half)
        if not isinstance(items, list) or not all(isinstance(n, int) and not isinstance(n, bool)
                                                  for n in items):
            problems.append("SC-001: `{0}` is not a list of PR numbers".format(half))
            items = []
        if len(items) != sizes[half]:
            problems.append("SC-001: `{0}` has {1} PRs, expected {2}".format(half, len(items), sizes[half]))
        if len(set(items)) != len(items):
            problems.append("SC-001: `{0}` repeats a PR".format(half))
        halves[half] = set(items)
    if halves["proofs"] & halves["listed"]:
        problems.append("SC-001: #{0} is in both `proofs` and `listed`".format(
            ", #".join(str(n) for n in sorted(halves["proofs"] & halves["listed"]))))
    seen = set()
    for item in expected.get("expected_differences", ()):
        who = item.get("pr") if item.get("pr") is not None else item.get("sha")
        key = (who, item.get("half"), item.get("actual_state"))
        if key in seen:
            problems.append("SC-001: two expected differences for {0} ({1}, state {2})".format(
                _who(who), key[1], key[2]))
        seen.add(key)
        if item.get("expected_state") not in SC001_HALF_STATES.get(item.get("half"), ()):
            problems.append("SC-001: the expected difference for {0} has half {1!r} and expected_state "
                            "{2!r}; proofs expect 2, listed 4 or 5".format(
                                _who(who), item.get("half"), item.get("expected_state")))
    return problems


def sc001_replay(corpus, expected, window=SC001_WINDOW, sizes=SC001_SIZES):
    """The replay: needs neither git nor `gh`. Returns problems."""
    problems = sc001_shape(corpus, expected, window, sizes)
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
    # A direct push has no PR for the answer key to name, so it is keyed by
    # its SHA: in state 4 or 5 it is "any other entry" (data-model.md).
    for entry in corpus["entries"]:
        state = states.get(entry["sha"])
        if entry.get("pr") is None and state in (pl.STATE_NO_RUN, pl.STATE_RUN_NO_RECORD):
            diffs.append((entry["sha"], "listed", state))
    allowed = {}
    for item in expected.get("expected_differences", ()):
        who = item.get("pr") if item.get("pr") is not None else item.get("sha")
        if item.get("reason") not in SC001_REASONS:
            problems.append("SC-001: {0} has reason {1!r}, outside SC-001's four".format(
                _who(who), item.get("reason")))
        allowed[(who, item.get("half"), item.get("actual_state"))] = item
    for key in diffs:
        if key not in allowed:
            problems.append("SC-001: {0} ({1}) is in state {2}, a difference that is not on the list".format(
                _who(key[0]), key[1], key[2]))
    for key, item in sorted(allowed.items(), key=lambda kv: str(kv[0])):
        if key not in diffs:
            problems.append("SC-001: the expected difference for {0} ({1}, state {2}) no longer differs; "
                            "delete it".format(_who(key[0]), key[1], key[2]))
    return problems


def _who(key):
    """`#N` for a PR, `direct push <sha>` for an entry with none."""
    return "#{0}".format(key) if isinstance(key, int) else "direct push {0}".format(str(key)[:10])


def check_sc001(directory, exempt, window=SC001_WINDOW, sizes=SC001_SIZES):
    """-> (problems, note). The five cases of research D13."""
    paths = [os.path.join(directory, n) for n in ("corpus.json", "expected.json")]
    present = [os.path.isfile(p) for p in paths]
    if sum(present) == 1:
        return ["SC-001: exactly one of corpus.json and expected.json is present"], None
    if sum(present) == 0:
        if exempt:
            issues = sorted({n for e in exempt.values() for n in e.issue})
            return [], "SC-001 not yet captured (EXEMPT_SC001_PENDING, {0})".format(
                ", ".join("#{0}".format(n) for n in issues))
        return ["SC-001: the corpus and answer key are absent and the exemption was deleted "
                "without the capture"], None
    if exempt:
        return ["SC-001: both files are present but EXEMPT_SC001_PENDING is still there; "
                "the capture commit deletes the entry"], None
    with open(paths[0], encoding="utf-8") as fh:
        corpus = json.load(fh)
    with open(paths[1], encoding="utf-8") as fh:
        expected = json.load(fh)
    return (sc001_replay(corpus, expected, window, sizes),
            "SC-001 replayed {0} entries".format(len(corpus["entries"])))


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
    shape = {"window": fx["window"], "sizes": {"proofs": 1, "listed": 1}}
    if sc001_replay(corpus, good, **shape):
        problems.append("SC-001 fixture: the matching corpus failed: {0}".format(sc001_replay(corpus, good, **shape)))
    diff = {"pr": 2, "sha": "l2", "half": "listed", "expected_state": 5, "actual_state": 3,
            "reason": "own-tree", "note": "x"}
    mismatches = [
        ("a proof not in state 2", dict(good, proofs=[2], listed=[1])),
        ("a listed entry outside 4 or 5", dict(good, listed=[3])),
        ("an extra entry in 4 or 5", dict(good, listed=[])),
        ("a stale expected difference", dict(good, expected_differences=[dict(diff, pr=1, half="proofs", expected_state=2, actual_state=4)])),
        ("a reason outside SC-001's four", dict(good, expected_differences=[dict(diff, reason="other")])),
    ]
    for label, expected in mismatches:
        if not sc001_replay(corpus, expected, **shape):
            problems.append("SC-001 fixture: {0} was not noticed".format(label))
    # R10: the answer key's shape and the corpus window, which the replay
    # alone never checked (each passed before sc001_shape).
    # `moved`: #2 really differs (state 3), so a difference item for it is live.
    moved = dict(corpus, entries=[make_entry(base, {"sha": "l2", "pr": 2, "reaching": []})] + entries[:1] + entries[2:])
    two = {"window": fx["window"], "sizes": {"proofs": 2, "listed": 1}}
    shaped = [
        ("an empty proofs half", corpus, dict(good, proofs=[]), shape),
        ("a proof dropped from the answer key", corpus, dict(good, proofs=[1]), two),
        ("a proof repeated", corpus, dict(good, proofs=[1, 1]), two),
        ("a PR in both halves", corpus, dict(good, proofs=[1, 2], listed=[2]), two),
        ("another corpus window", corpus, good, {"window": {"start": fx["window"]["start"],
                                                           "end": "2026-11-11T00:00:00Z"},
                                                "sizes": shape["sizes"]}),
        ("two differences with one key", moved, dict(good, expected_differences=[
            dict(diff), dict(diff, reason="FR-005")]), shape),
        ("a listed difference expecting state 2", moved, dict(good, expected_differences=[
            dict(diff, expected_state=2)]), shape),
        # SC001_HALF_STATES each way: a listed half expects only 4 or 5, a
        # proofs half only 2 (#889).
        ("a listed difference expecting state 3", moved, dict(good, expected_differences=[
            dict(diff, expected_state=3)]), shape),
        ("a listed difference expecting state 1", moved, dict(good, expected_differences=[
            dict(diff, expected_state=1)]), shape),
        ("a proofs difference expecting state 4", dict(corpus, comments={}), dict(good, expected_differences=[
            dict(diff, pr=1, sha="p1", half="proofs", expected_state=4, actual_state=4)]), shape),
    ]
    for label, case_corpus, expected, own in shaped:
        if not sc001_replay(case_corpus, expected, **own):
            problems.append("SC-001 fixture: {0} was not noticed".format(label))
    if (SC001_WINDOW, SC001_SIZES) != ({"start": "2026-10-15T00:00:00Z", "end": "2026-11-17T00:00:00Z"},
                                       {"proofs": 10, "listed": 21}) \
            or inspect.signature(sc001_replay).parameters["sizes"].default is not SC001_SIZES \
            or inspect.signature(check_sc001).parameters["window"].default is not SC001_WINDOW:
        problems.append("SC-001: the real replay does not default to the fixed window and the 10/21 key")
    # an expected difference that matches an actual one is accepted
    moved = dict(corpus, entries=[make_entry(base, {"sha": "l2", "pr": 2, "reaching": []})] + entries[:1] + entries[2:])
    if sc001_replay(moved, dict(good, expected_differences=[dict(diff, actual_state=3)]), **shape):
        problems.append("SC-001 fixture: a listed difference was rejected: {0}".format(
            sc001_replay(moved, dict(good, expected_differences=[dict(diff, actual_state=3)]), **shape)))
    # the five exemption cases, with their own table: never EXEMPT_SC001_PENDING,
    # which T029 deletes (plan.md "Build details")
    exempt = {"sc001": Exemption(reason="fixture: the capture is pending", issue=(889,))}
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
            got, _note = check_sc001(tmp, table, **shape)
            if bool(got) != want_fail:
                problems.append("SC-001 fixture: {0}: {1}".format(label, got or "did not fail"))
    return problems



from board_prove import fixtures_name_no_live_table  # noqa: E402,F401  (single home)


def main():
    fx = load("states.json")
    real, note = check_sc001(os.path.join(FIXTURES, "sc001"), EXEMPT_SC001_PENDING)
    if note:
        print("[ok] verify-proof-list: {0}".format(note))
    problems = (check(fx) + check_report(fx) + check_set_apart_report(fx)
                + check_failed_reads() + check_main_errors() + check_section_file_home() + check_review_fixes(fx) + check_lifecycle_issue()
                + check_entries() + check_closed_by_commit(fx) + check_loud_reads() + check_read_cost(fx) + check_classifier_corrections(fx) + check_utc() + check_trees() + check_budget() + check_tree_snapshot() + check_tree_cost() + check_run_list_cost() + check_deleted_workflow_runs() + check_progress() + check_forbidden_homes() + check_workflow()
                + check_rebase_merge() + check_run_ancestry_skip() + check_capture_clip() + check_git_failed_reads()
                + check_reusable_only_filter() + check_window_edges(fx) + check_report_edges(fx)
                + check_closed_by_commit_edges()
                + real + check_sc001_fixtures(fx) + fixtures_name_no_live_table(check_sc001_fixtures))
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
