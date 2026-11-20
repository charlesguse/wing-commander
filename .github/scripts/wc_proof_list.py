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
# The one need-a-run rule and the one reach computation (single home, Gate 89);
# reaching_workflows() is called per entry tree once `collect` lands (T018).
from board_prove import actions_only, reaching_workflows  # noqa: E402,F401
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


def workflow_summary(runs):
    """FR-020: one reaching workflow's counting runs as counts by event and
    conclusion plus the earliest and latest run link (never one row per run)."""
    by_kind = {}
    for run in runs:
        key = "{0}/{1}".format(run.get("event") or "unknown", run.get("conclusion") or "unknown")
        by_kind[key] = by_kind.get(key, 0) + 1
    ordered = sorted(runs, key=lambda r: (parse_time(r["run_started_at"]), str(r["run_id"])))
    return {"total": len(runs), "by_kind": dict(sorted(by_kind.items())),
            "earliest": ordered[0].get("html_url"), "latest": ordered[-1].get("html_url")}


STANDING_LINE = "State 3 means the scan found no edge, not that nothing runs the change."
SHORTENED_LINE = "This list was shortened to fit the issue: each entry shows only the names of its reaching workflows."
LABELS = {1: "needs no run", 2: "on record", 3: "no edge found", 4: "reached, no run counts",
          5: "run(s) count, nothing on record"}


def _wf_name(path):
    return path.rsplit("/", 1)[-1]


def _entry_cell(entry):
    pr = "#{0}".format(entry["pr"]) if entry.get("pr") is not None else "direct push"
    return "`{0}` | {1}".format(entry["sha"][:10], pr)


def render(entries, states, runs, counts_by_state, aged_out, set_apart_count,
           built_at, start, end, form="full"):
    """The section's Markdown body (inside the <details> block), `full` or
    `names_only` (contracts/proof-list-report.md "Content when built"). No
    wording of verdict (FR-010)."""
    lines = ["Window: {0} to {1}.".format(parse_time(start).date(), parse_time(end).date()), ""]
    lines.append("| State | Entries |")
    lines.append("|---|---|")
    for state in STATES:
        lines.append("| {0} {1} | {2} |".format(state, LABELS[state], counts_by_state.get(state, 0)))
    lines += ["", "Aged out in the 24 hours before the window start: {0}.".format(aged_out),
              "Runs set apart (could not be placed on this repository's history): {0}.".format(set_apart_count),
              "", STANDING_LINE, ""]
    if form == "names_only":
        lines += [SHORTENED_LINE, ""]
    listed = [e for e in entries if states.get(e["sha"]) in (STATE_NO_RUN, STATE_RUN_NO_RECORD)]
    if listed:
        lines += ["| Commit | PR | State | Reaching workflows |", "|---|---|---|---|"]
    for entry in listed:
        state = states[entry["sha"]]
        cells = []
        for workflow in entry.get("reaching") or ():
            name = _wf_name(workflow["path"])
            if not workflow.get("runs_of_its_own", True):
                name += " (no runs of its own)"
            elif form == "full" and state == STATE_RUN_NO_RECORD:
                found = counting_runs(entry, runs).get(workflow["path"])
                if found:
                    summary = workflow_summary(found)
                    kinds = ", ".join("{0} {1}".format(n, k) for k, n in summary["by_kind"].items())
                    name += " ({0}; [first]({1}), [last]({2}))".format(
                        kinds, summary["earliest"], summary["latest"])
            cells.append(name)
        lines.append("| {0} | {1} | {2} |".format(_entry_cell(entry), state, "; ".join(cells)))
    if not listed:
        lines.append("No entries in state 4 or 5.")
    return "\n".join(lines) + "\n"


def assemble_report(entries, runs, comments_by_sha, named_runs, repository, built_at, head_sha,
                    max_units, utf16_len):
    """The `proof-list-section.json` document (schema 1; data-model.md "Report").
    The window comes from `built_at` alone (FR-011). Raises ValueError when
    even the names-only form does not fit in `max_units` (FR-020); never drops
    an entry to fit."""
    start, end = window_for(built_at)
    states, aged_out = classify_all(entries, runs, comments_by_sha, named_runs, repository, start, end)
    apart = set_apart(entries, runs, comments_by_sha, named_runs, repository, start, end)
    in_win = [e for e in entries if e["sha"] in states]
    cts = counts(states)
    args = (in_win, states, runs, cts, aged_out, apart, built_at, start, end)
    full, names_only = render(*args, form="full"), render(*args, form="names_only")
    if utf16_len(names_only) > max_units:
        raise ValueError("the names-only form is {0} UTF-16 units, over the {1} limit".format(
            utf16_len(names_only), max_units))
    return {"schema": 1, "built_at": parse_time(built_at).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")},
            "head_sha": head_sha, "counts": {str(k): v for k, v in cts.items()},
            "aged_out": aged_out, "set_apart": apart, "full": full, "names_only": names_only}


def counts(states):
    """{1..5: n} for a {sha: state} map."""
    out = {s: 0 for s in STATES}
    for state in states.values():
        out[state] += 1
    return out
