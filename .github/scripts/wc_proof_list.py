#!/usr/bin/env python3
"""The proof list: which merges to the default branch have a run that could
show them working and nothing on record (specs/124-merge-proof-list).

This file is the pure half first (no I/O): classification of each entry into
one of five states, comment qualification, set-apart and aged-out counting.
Every input is a plain dict/list (the shapes are in data-model.md), the window
(`start`, `end`) is a parameter, and the same inputs always give the same
states (FR-008, FR-011). Nothing here encodes a verdict (FR-010).
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import actions_only  # noqa: E402,F401  (the one need-a-run rule)
from board_triage import any_run_url_pattern  # noqa: E402

STATES = (1, 2, 3, 4, 5)
WINDOW_DAYS = 30
AGED_OUT_HOURS = 24
# data-model.md "State": 1 needs no run, 2 on record, 3 nothing reaches it,
# 4 reached but no finished run counts, 5 run(s) count but nothing on record.
STATE_NEEDS_NO_RUN, STATE_ON_RECORD, STATE_NOTHING_REACHES, STATE_NO_RUN, STATE_RUN_NO_RECORD = STATES

_RUN_URL_RE = re.compile(any_run_url_pattern())


def parse_time(value):
    """UTC datetime from an ISO string ending in Z or an offset, or a datetime."""
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def window_for(end):
    """`start = end - 30 days`; the only way a build's window is set (FR-011)."""
    end = parse_time(end)
    return end - datetime.timedelta(days=WINDOW_DAYS), end


def pr_named(body, pr, repository=None):
    """True when `body` names PR `pr`: `#N` with boundaries, or its URL."""
    if pr is None:
        return False
    if re.search(r"(?<![\w#/])#{0}(?!\w)".format(int(pr)), body or ""):
        return True
    return bool(re.search(r"/pull/{0}(?!\d)".format(int(pr)), body or ""))


def named_run_keys(body):
    """[(repository, run_id)] for every Actions run URL in `body`, in order."""
    return [(m.group(1), m.group(2)) for m in _RUN_URL_RE.finditer(body or "")]


def shared_issues(entries):
    """Issue numbers named by the PRs of more than one entry, any state."""
    named = {}
    for entry in entries:
        if entry.get("pr") is None:
            continue
        for issue in entry.get("named_issues") or ():
            named.setdefault(issue["number"], set()).add(entry["pr"])
    return {number for number, prs in named.items() if len(prs) > 1}


def _on_place(entry, comment):
    place = comment.get("place") or {}
    if place.get("kind") == "pr":
        return entry.get("pr") is not None and place.get("number") == entry["pr"]
    if place.get("kind") == "issue":
        return place.get("number") in {i["number"] for i in entry.get("named_issues") or ()}
    return False


def _named_run_for(entry, key, named_runs):
    """The NamedRun record for run URL key (repository, id), or None."""
    return named_runs.get("{0}/{1}".format(*key))


def comment_steps_1_to_4(entry, comment, shared, repository):
    """data-model.md "RecordComment" steps 1-4 (everything but the named run)."""
    if not _on_place(entry, comment):
        return False
    if parse_time(comment["posted_at"]) <= parse_time(entry["merged_at"]):
        return False
    marker = comment.get("marker_step", "none")
    if marker != "none":
        if marker != "proven":
            return False
    elif comment.get("account_type") == "Bot":
        return False
    place = comment.get("place") or {}
    if place.get("kind") == "issue" and place.get("number") in shared:
        if not pr_named(comment.get("body"), entry.get("pr"), repository):
            return False
    return True


def run_qualifies(entry, run):
    """A `found` named run: started after the merge, merge an ancestor of its head."""
    return (bool(run) and run.get("kind") == "found" and run.get("resolvable", True)
            and parse_time(run["run_started_at"]) > parse_time(entry["merged_at"])
            and entry["sha"] in (run.get("contains") or ()))


def qualifying_comments(entry, comments, named_runs, shared, repository):
    """The comments that count as a record for `entry` (steps 1-5)."""
    out = []
    for comment in comments:
        if not comment_steps_1_to_4(entry, comment, shared, repository):
            continue
        for key in named_run_keys(comment.get("body")):
            if key[0] == repository and run_qualifies(
                    entry, _named_run_for(entry, key, named_runs)):
                out.append(comment)
                break
    return out


def counting_runs(entry, runs):
    """FinishedRuns of the entry's reaching workflows (with runs of their own)
    whose head contains the entry's merge, as {workflow: [run, ...]}."""
    counted = {}
    for workflow in entry.get("reaching") or ():
        if not workflow.get("runs_of_its_own", True):
            continue
        found = [r for r in runs.get(workflow["path"], ())
                 if r.get("resolvable", True) and entry["sha"] in (r.get("contains") or ())]
        if found:
            counted[workflow["path"]] = found
    return counted


def classify(entry, runs, comments, named_runs, shared, repository):
    """The first state that fits (data-model.md "State"); ints 1-5."""
    if not entry.get("needs_run"):
        return STATE_NEEDS_NO_RUN
    if qualifying_comments(entry, comments, named_runs, shared, repository):
        return STATE_ON_RECORD
    if not entry.get("reaching"):
        return STATE_NOTHING_REACHES
    if not counting_runs(entry, runs):
        return STATE_NO_RUN
    return STATE_RUN_NO_RECORD


def in_window(entry, start, end):
    """`start < merged_at <= end` (research D10)."""
    return parse_time(start) < parse_time(entry["merged_at"]) <= parse_time(end)


def classify_all(entries, runs, comments_by_sha, named_runs, repository, start, end):
    """({sha: state} for entries in the window, aged_out count).

    `shared` counts every entry's PR, so it reads all entries given, window or
    not. The aged-out count is state 4 or 5 among the commits in the 24 hours
    before `start`, classified as if the window began a day earlier (FR-012)."""
    shared = shared_issues(entries)
    day_before = parse_time(start) - datetime.timedelta(hours=AGED_OUT_HOURS)
    states, aged_out = {}, 0
    for entry in entries:
        state = classify(entry, runs, comments_by_sha.get(entry["sha"], ()),
                         named_runs, shared, repository)
        if in_window(entry, start, end):
            states[entry["sha"]] = state
        elif in_window(entry, day_before, start) and state in (STATE_NO_RUN, STATE_RUN_NO_RECORD):
            aged_out += 1
    return states, aged_out


def set_apart(entries, runs, comments_by_sha, named_runs, repository, start, end):
    """Count of runs set apart, exactly FR-013's two cases, de-duplicated by run
    id or URL (data-model.md "SetApartRun")."""
    shared = shared_issues(entries)
    apart = set()
    for entry in entries:
        merged = parse_time(entry["merged_at"])
        for workflow in entry.get("reaching") or ():
            for run in runs.get(workflow["path"], ()):
                if (not run.get("resolvable", True)
                        and parse_time(run["run_started_at"]) > merged):
                    apart.add(("run", str(run["run_id"])))
        for comment in comments_by_sha.get(entry["sha"], ()):
            if not comment_steps_1_to_4(entry, comment, shared, repository):
                continue
            for key in named_run_keys(comment.get("body")):
                record = None if key[0] != repository else _named_run_for(entry, key, named_runs)
                if key[0] != repository or (record or {}).get("kind") in ("foreign", "not_found") \
                        or record is None:
                    apart.add(("url", "{0}/{1}".format(*key)))
                elif (record.get("kind") == "found" and not record.get("resolvable", True)
                        and parse_time(record["run_started_at"]) > merged):
                    apart.add(("run", str(record["run_id"])))
    return len(apart)


def counts(states):
    """{1..5: n} for a {sha: state} map."""
    out = {s: 0 for s in STATES}
    for state in states.values():
        out[state] += 1
    return out
