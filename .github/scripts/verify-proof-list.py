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


def main():
    fx = load("states.json")
    problems = check(fx) + check_report(fx)
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
