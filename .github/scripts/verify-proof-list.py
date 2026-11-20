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


def _git(cwd, *args):
    import subprocess
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(args),
                   cwd=cwd, check=True, capture_output=True)


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


def main():
    fx = load("states.json")
    problems = (check(fx) + check_report(fx) + check_set_apart_report(fx)
                + check_failed_reads() + check_trees())
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
