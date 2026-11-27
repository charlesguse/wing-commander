#!/usr/bin/env python3
"""Feature health (specs/126-feature-health): one health state per feature,
decided by code from run history, kill switches and output signals.

Usage:
  wc_feature_health.py build --out feature-health-section.md
  wc_feature_health.py render READINGS.json     (pure: readings in, Markdown out)
  wc_feature_health.py capture --start T --now T --out corpus.json
                                                (maintainer only: the SC-001 corpus)

The pure half (classify_workflow, classify_feature, render_section) takes
already-read data and an injected `now` and does no I/O, so
verify-feature-health.py drives every branch from checked-in JSON. The runtime
half (collect, build) reads through `gh` and never writes: no comment, label,
close, edit or dispatch (FR-013).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
REGISTRY_PATH = os.path.join(HERE, "feature-health-registry.json")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import wc_board_status  # noqa: E402
from board_triage import (  # noqa: E402
    BACKLOG_TICK_COMMENT_PREFIX, BACKLOG_TICK_COMMENT_SUFFIX, TRIAGE_CLOSE_COMMENT_PREFIX, TRIAGE_CLOSE_GROUNDS)

# data-model.md "Health state": earliest wins.
STATE_ORDER = ["unreadable", "paused", "not configured", "failing", "not running",
               "quiet", "idle", "healthy"]
CALLED_OUT = ("unreadable", "paused", "failing", "not running", "quiet")
DEFAULT_QUIET_DAYS = 14
WINDOW_DAYS = 30
FAILING_WINDOW = 3
RUN_CAP = 1000
RATE_LIMIT_FLOOR = 300
COMMENT_READ_CAP = 150
SEARCH_PAGES = 3
# Comment pages read per issue by the triage_close and issue_or_comment
# readers: one issue with more than a page of comments must not make the
# whole signal unreadable.
COMMENT_PAGES = 10
# The not-running threshold never drops below this many hours, so an hourly
# workflow is not called out for an ordinary GitHub schedule delay.
NOT_RUNNING_FLOOR_HOURS = 6
MARKER_BEGIN = "<!-- wing-commander-feature-health -->"
MARKER_END = "<!-- /wing-commander-feature-health -->"
# The section's own built line: render_section writes it, section_built_at
# reads the build time back from it (#889).
BUILT_LINE = "**Feature health** — built "
BUILT_LINE_RE = re.compile(r"^" + re.escape(BUILT_LINE) + r"(\d{4}-\d\d-\d\d \d\d:\d\d)Z", re.M)
# The line wc_board_status.render opens the Board status issue with: the
# board-status job's own write time, which a hand edit of the issue does not
# move (#889). verify-feature-health.py reads it back from that renderer.
BOARD_STATUS_UPDATED_RE = re.compile(
    r"^Updated (\d{4}-\d\d-\d\d \d\d:\d\d) UTC by the daily `board-status` job", re.M)
SWITCH_PREFIX = "WING_COMMANDER_"
SIGNAL_KINDS = ("merged_pr", "release", "issue_or_comment", "triage_close",
                "branch_commit", "issue_updated", "issue_section")
NEVER = "never in window"
NOT_MEASURED = "not measured"
NOT_QUALIFYING = ("skipped", "cancelled", "neutral")


def parse_time(text):
    return datetime.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")


def fmt_time(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def day(text):
    return text[:10] if text else NEVER


def load_registry(path=REGISTRY_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def quiet_days(entry):
    return entry.get("quiet_days") or DEFAULT_QUIET_DAYS


def window_days(registry):
    return max([WINDOW_DAYS] + [quiet_days(e) for e in registry]) + 1


# --------------------------------------------------------------------------
# Pure half
# --------------------------------------------------------------------------
def _flag(value):
    """True / False / "unreadable" from a switch or variable reading."""
    return "unreadable" if value == "unreadable" else bool(value)


def classify_workflow(ref, entry, reading, ctx, now):
    """(state, detail) for one workflow of `entry`. `reading` is {"runs": [...],
    "interval_hours": number|None} or {"unreadable": reason}; `ctx` carries
    "switches" and "vars_set". The quiet rule (6) is a feature-level test, see
    classify_feature; stage rows never apply it."""
    detail = {"last_success": None, "last_failure": None, "last_run": None,
              "qualifying": 0, "reason": None}
    if "unreadable" in reading:
        detail["reason"] = "{0}: {1}".format(ref["file"], reading["unreadable"])
        return "unreadable", detail
    kill, var = entry.get("kill_switch"), entry.get("requires_var")
    switch = _flag((ctx.get("switches") or {}).get(kill)) if kill else False
    have_var = _flag((ctx.get("vars_set") or {}).get(var)) if var else True
    if switch == "unreadable" or have_var == "unreadable":
        detail["reason"] = "{0}: could not read {1}".format(
            ref["file"], kill if switch == "unreadable" else var)
        return "unreadable", detail
    interval = reading.get("interval_hours")
    if ref.get("cadence") == "schedule" and interval is None:
        # A schedule ref whose cron could not be found would otherwise skip
        # the not-running test silently and read as healthy or idle; it ranks
        # with the other unreadable reads, above paused.
        detail["reason"] = "{0}: no cron found".format(ref["file"])
        return "unreadable", detail
    runs = sorted(reading.get("runs") or [], key=lambda r: r["started_at"], reverse=True)
    # collect() may read a scheduled workflow back past the window, to the
    # not-running threshold (#1261); those earlier runs count only for the
    # not-running test and last_run. Every other rule reads in-window runs,
    # so a weekly or monthly cron whose only run predates the window is idle
    # (FR-017), not healthy (#889).
    window_start = reading.get("window_start")
    in_window = ([r for r in runs if parse_time(r["started_at"]) >= parse_time(window_start)]
                 if window_start else runs)
    qualifying = [r for r in in_window if r.get("conclusion") not in NOT_QUALIFYING]
    detail["qualifying"] = len(qualifying)
    for r in qualifying:
        if r["conclusion"] == "success" and not detail["last_success"]:
            detail["last_success"] = r["started_at"]
        if r["conclusion"] != "success" and not detail["last_failure"]:
            detail["last_failure"] = r["started_at"]
    detail["last_run"] = runs[0]["started_at"] if runs else None
    if switch:
        return "paused", detail
    if not have_var and in_window and all(r.get("conclusion") == "skipped" for r in in_window):
        return "not configured", detail
    last = qualifying[:FAILING_WINDOW]
    if last and all(r["conclusion"] != "success" for r in last):
        return "failing", detail
    if ref.get("cadence") == "schedule" and interval:
        cutoff = now - datetime.timedelta(hours=not_running_hours(interval))
        if not runs or parse_time(runs[0]["started_at"]) < cutoff:
            return "not running", detail
    if not qualifying:
        return "idle", detail
    return "healthy", detail


def not_running_hours(interval):
    """Hours without a run after which a scheduled workflow reads "not
    running": twice its cron interval, floored at NOT_RUNNING_FLOOR_HOURS."""
    return max(2 * interval, NOT_RUNNING_FLOOR_HOURS)


def _rank(state):
    return STATE_ORDER.index(state)


def signal_state(entry, signal_reading, now):
    """None (no signal declared), "unreadable", "quiet" or "seen"."""
    if not entry.get("signal"):
        return None
    if "unreadable" in (signal_reading or {"unreadable": "no reading"}):
        return "unreadable"
    at = signal_reading.get("signal_at")
    if not at:
        return "quiet"
    age = now - parse_time(at)
    return "quiet" if age > datetime.timedelta(days=quiet_days(entry)) else "seen"


def classify_feature(entry, readings, signal_reading, ctx, now):
    """The feature's row set: [feature_row, stage_row...]. Worst-of across
    its workflows; idle workflows are ignored when a sibling has a qualifying
    run (FR-017); stage rows carry their own workflow's state (FR-018)."""
    results = [(ref, ) + classify_workflow(ref, entry, readings.get(ref["file"], {"unreadable": "not read"}), ctx, now)
               for ref in entry["workflows"]]
    any_qualifying = any(d["qualifying"] for _r, _s, d in results)
    counted = [(r, s, d) for r, s, d in results if not (s == "idle" and any_qualifying)]
    state = min((s for _r, s, _d in counted), key=_rank)
    reason = next((d["reason"] for _r, s, d in counted if s == "unreadable"), None)
    sig = signal_state(entry, signal_reading, now)
    if sig == "unreadable" and state != "unreadable":
        # A signal read failure must not hide a stronger call-out: keep
        # paused / not configured / failing / not running and note it.
        sig_reason = "signal: {0}".format((signal_reading or {}).get("unreadable", "no reading"))
        if _rank(state) > _rank("not running"):
            state, reason = "unreadable", sig_reason
        else:
            reason = "; ".join(r for r in (reason, sig_reason) if r)
    elif sig == "quiet" and _rank(state) > _rank("quiet"):
        state = "quiet"
    successes = [d["last_success"] for _r, _s, d in results if d["last_success"]]
    failures = [d["last_failure"] for _r, _s, d in results if d["last_failure"]]
    runs_at = [d["last_run"] for _r, _s, d in results if d["last_run"]]
    row = {"feature": entry["name"], "stage": None, "state": state,
           "last_success": max(successes) if successes else None,
           "last_failure": max(failures) if failures else None,
           "last_run": max(runs_at) if runs_at else None,
           "last_signal": NOT_MEASURED, "threshold_days": None,
           "signal_label": None, "kill_switch": entry.get("kill_switch"), "reason": reason}
    if entry.get("signal"):
        row["threshold_days"] = quiet_days(entry)
        row["signal_label"] = entry["signal"].get("label") or entry["signal"]["kind"]
        at = (signal_reading or {}).get("signal_at")
        row["last_signal"] = day(at) if "unreadable" not in (signal_reading or {"unreadable": 1}) else NOT_MEASURED
    # A failing or not-running call-out quotes the dates of the workflows in
    # that state, not a healthy sibling's (#889); the table keeps the
    # feature-wide dates.
    in_state = [d for _r, s, d in counted if s == state and s in ("failing", "not running")]
    if in_state:
        row["callout_dates"] = {k: max((d[k] for d in in_state if d[k]), default=None)
                                for k in ("last_success", "last_failure", "last_run")}
    rows = [row]
    for ref, s, d in results:
        if ref.get("stage"):
            rows.append({"feature": entry["name"], "stage": ref["stage"], "state": s,
                         "last_success": d["last_success"], "last_failure": d["last_failure"],
                         "last_run": d["last_run"], "last_signal": NOT_MEASURED,
                         "threshold_days": None, "signal_label": None,
                         "kill_switch": entry.get("kill_switch"), "reason": d["reason"]})
    return rows


def classify_all(registry, readings, signals, ctx, now):
    rows = []
    for entry in registry:
        rows.extend(classify_feature(entry, readings, signals.get(entry["name"]), ctx, now))
    return rows


def _callout(row):
    line = _callout_line(row)
    reason = row.get("reason") or ""
    if row["state"] != "unreadable" and "signal: " in reason:
        line += " (signal unreadable: {0})".format(reason.split("signal: ", 1)[1])
    return line


def _callout_line(row):
    name, state = row["feature"], row["state"]
    dates = row.get("callout_dates") or row
    if state == "failing":
        return "- `{0}` — failing: last success {1}, last failure {2}".format(
            name, day(dates["last_success"]), day(dates["last_failure"]))
    if state == "quiet":
        if row["last_signal"] in (NOT_MEASURED, NEVER, None):
            return "- `{0}` — quiet: no {1} in the last {2} days".format(
                name, row["signal_label"], row["threshold_days"])
        return "- `{0}` — quiet: no {1} since {2} (threshold {3} days)".format(
            name, row["signal_label"], row["last_signal"], row["threshold_days"])
    if state == "not running":
        last = day(dates["last_run"])
        if last == NEVER:
            return "- `{0}` — not running: no run in the window".format(name)
        return "- `{0}` — not running: no run since {1}".format(name, last)
    if state == "paused":
        return "- `{0}` — paused: {1}".format(name, row["kill_switch"])
    return "- `{0}` — unreadable: {1}".format(name, row["reason"] or "no reason recorded")


def render_section(rows, now, registry_size=None):
    """The Markdown fragment (contracts/feature-health-report.md). Byte-
    deterministic for equal inputs."""
    features = [r for r in rows if not r["stage"]]
    unreadable = sum(1 for r in features if r["state"] == "unreadable")
    out = [MARKER_BEGIN,
           BUILT_LINE + "{0} · {1} features · {2} unreadable".format(
               now.strftime("%Y-%m-%d %H:%MZ"), registry_size or len(features), unreadable),
           "", "**Needs a look:**"]
    called = sorted((r for r in features if r["state"] in CALLED_OUT),
                    key=lambda r: (_rank(r["state"]), r["feature"]))
    out.extend(_callout(r) for r in called) if called else out.append("Nothing needs a look.")
    out += ["", "<details><summary>All features</summary>", "",
            "| Feature | State | Last success | Last failure | Last output signal |",
            "|---|---|---|---|---|"]
    for r in rows:
        label = ("&nbsp;&nbsp;" + r["stage"]) if r["stage"] else r["feature"]
        signal = r["last_signal"]
        if r["threshold_days"]:
            signal = "{0} (threshold {1}d)".format(signal, r["threshold_days"])
        out.append("| {0} | {1} | {2} | {3} | {4} |".format(
            label, r["state"], day(r["last_success"]), day(r["last_failure"]), signal))
    out += ["</details>", MARKER_END]
    return "\n".join(out) + "\n"


def shorten_section(text):
    """Drop the table, keep the call-outs (over-size body, research D8)."""
    return wc_board_status.shorten_feature_health(text) + "\n"


# --------------------------------------------------------------------------
# Runtime half: read through `gh`, never write.
# --------------------------------------------------------------------------
def gh_json(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                           else "gh api failed")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def check_rate_limit(gh=gh_json, floor=RATE_LIMIT_FLOOR):
    """FR-011: fail up front rather than classify from a truncated read."""
    remaining = gh("rate_limit")["resources"]["core"]["remaining"]
    if remaining < floor:
        raise SystemExit("feature-health: only {0} API calls left (floor {1}); not building".format(remaining, floor))
    return remaining


def _cron_hour_set(hour, expr):
    """The hours (0-23) a cron hour field fires on: `*`, `N`, `A-B`, and a
    `/step` on `*` or a range, comma-joined. ValueError otherwise."""
    hours = set()
    for part in hour.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
        if not m or (m.group(2) is not None and int(m.group(2)) < 1):
            raise ValueError("unparseable cron: {0}".format(expr))
        span, step = m.group(1), int(m.group(2) or 1)
        lo, _sep, hi = ("0-23" if span == "*" else span).partition("-")
        lo, hi = int(lo), int(hi or lo)
        if m.group(2) is not None and span != "*" and "-" not in span:
            hi = 23
        if not 0 <= lo <= hi <= 23:
            raise ValueError("unparseable cron: {0}".format(expr))
        hours.update(range(lo, hi + 1, step))
    return hours


def _cron_hours(expr):
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("unparseable cron: {0}".format(expr))
    unrestricted = fields[2:] == ["*", "*", "*"]
    if fields[1] == "*" and unrestricted:
        return 1
    hours = sorted(_cron_hour_set(fields[1], expr))
    if unrestricted:
        # Largest gap between consecutive firings, counting the wrap past midnight.
        gaps = [b - a for a, b in zip(hours, hours[1:])] + [hours[0] + 24 - hours[-1]]
        return max(gaps)
    month = fields[3]
    if month != "*":
        step = re.fullmatch(r"\*/(\d+)", month)
        return 24 * 31 * int(step.group(1)) if step and int(step.group(1)) >= 1 else 24 * 366
    return 24 * 7 if fields[4] != "*" else 24 * 31


def schedule_interval_hours(workflow_text):
    """Smallest hours between scheduled runs across the workflow's
    `on.schedule` cron entries; a `cron:` line anywhere else (a `run:` block,
    a heredoc, a comment) is not a schedule. None if there is none;
    ValueError if the workflow or a cron cannot be parsed, which makes the
    workflow unreadable."""
    try:
        doc = yaml.safe_load(workflow_text)
    except yaml.YAMLError as exc:
        raise ValueError("workflow does not parse as YAML: {0}".format(str(exc).splitlines()[0]))
    # PyYAML reads the bare key `on` as the boolean True.
    on = (doc.get("on", doc.get(True)) if isinstance(doc, dict) else None)
    schedule = on.get("schedule") if isinstance(on, dict) else None
    if schedule is not None and not isinstance(schedule, list):
        raise ValueError("on.schedule is not a list")
    crons = []
    for item in schedule or []:
        if not isinstance(item, dict) or not isinstance(item.get("cron"), str):
            raise ValueError("on.schedule entry has no cron string: {0!r}".format(item))
        crons.append(item["cron"].strip())
    if not crons:
        return None
    return min(_cron_hours(c) for c in crons)


def fetch_runs(gh, repo, filename, start, end, events=None):
    """Finished runs of one workflow in [start, end], sliced by halving the
    window while a slice reports RUN_CAP or more (D4). A slice under an hour
    that is still capped raises."""
    path = ("repos/{0}/actions/workflows/{1}/runs?status=completed&created={2}..{3}&per_page=100"
            .format(repo, filename, fmt_time(start), fmt_time(end)))
    first = gh(path)
    if first.get("total_count", 0) >= RUN_CAP:
        if end - start <= datetime.timedelta(hours=1):
            raise RuntimeError("more than {0} runs in one hour".format(RUN_CAP))
        mid = start + (end - start) / 2
        return (fetch_runs(gh, repo, filename, start, mid, events)
                + fetch_runs(gh, repo, filename, mid + datetime.timedelta(seconds=1), end, events))
    runs, page, body = [], 1, first
    while True:
        runs.extend(body.get("workflow_runs") or [])
        if len(body.get("workflow_runs") or []) < 100:
            break
        page += 1
        body = gh(path + "&page={0}".format(page))
    out = []
    for r in runs:
        if events and r.get("event") not in events:
            continue
        out.append({"id": r["id"], "event": r.get("event"),
                    "started_at": r.get("run_started_at") or r["created_at"],
                    "updated_at": r.get("updated_at"), "run_attempt": r.get("run_attempt") or 1,
                    "conclusion": r.get("conclusion") or "other"})
    return out


def _pages(gh, path, max_pages=10):
    """Every item of a list endpoint, page by page. Raises when the last
    allowed page is still full: a cut-off read must not classify (FR-010/011)."""
    items = []
    for page in range(1, max_pages + 1):
        got = gh(path + "&page={0}".format(page))
        items.extend(got)
        if len(got) < 100:
            return items
    raise RuntimeError("more than {0} items: read truncated".format(max_pages * 100))


# The comment board-loop.yml's triage step closes an issue with starts a line
# with board_triage.TRIAGE_CLOSE_COMMENT_PREFIX and the ground, then a comma.
# Anything else (a duplicate close at the route step, a deferral, a comment
# that merely quotes a ground) is not a triage close (FR-003). On a
# Maintenance-backlog line the loop ticks the line instead and posts the same
# sentence on the backlog issue, which stays open, behind BACKLOG_TICK_RE's
# opening; that comment is a triage close too (#889).
TRIAGE_CLOSE_RE = re.compile(r"^(?:{0}[^`\n]+{1})?{2}({3}),".format(
    re.escape(BACKLOG_TICK_COMMENT_PREFIX), re.escape(BACKLOG_TICK_COMMENT_SUFFIX),
    re.escape(TRIAGE_CLOSE_COMMENT_PREFIX), "|".join(re.escape(g) for g in TRIAGE_CLOSE_GROUNDS)), re.M)
BACKLOG_TICK_RE = re.compile(r"\A{0}[^`\n]+{1}".format(
    re.escape(BACKLOG_TICK_COMMENT_PREFIX), re.escape(BACKLOG_TICK_COMMENT_SUFFIX)))


def _triage_close_times(gh, repo, base, since, until=None):
    """Times of triage closes in the window. The search API names the issues
    whose comments carry the close sentence, newest update first, so the
    read does not grow with the number of closed issues; each candidate's
    comments are then matched exactly. A candidate updated before the newest
    match found so far cannot hold a newer one, so the read stops there; a
    search still unresolved after SEARCH_PAGES pages raises (FR-010/011).
    `until` (the capture only) drops a close after it before the stop rule
    sees it, so a later close cannot end the read early and hide one in the
    window. The search does not ask for `is:closed`: a backlog-line tick
    (BACKLOG_TICK_RE) is posted on the backlog issue, which stays open, and
    counts whatever its state (#889). Any other close counts only on an issue
    closed today; under `until`, an issue open today with such a close in the
    window raises: whether it was still closed at `until` cannot be read
    back."""
    s = fmt_time(since)
    u = fmt_time(until) if until else None
    q = 'repo:{0} is:issue updated:>={1} "{2}"'.format(repo, s[:10], TRIAGE_CLOSE_COMMENT_PREFIX.strip())
    path = "search/issues?q={0}&sort=updated&order=desc&per_page=100".format(urllib.parse.quote(q))
    times = []
    for page in range(1, SEARCH_PAGES + 1):
        try:
            got = gh(path + "&page={0}".format(page))
        except RuntimeError as exc:
            # The search API has its own, much smaller quota; say so rather than
            # report a generic failure while core calls are plentiful.
            if re.search(r"\b(403|429)\b|rate limit|abuse", str(exc), re.I):
                raise RuntimeError("triage close search is rate limited (the search quota is separate "
                                   "from the core quota): {0}".format(exc))
            raise
        if not isinstance(got, dict) or got.get("incomplete_results"):
            raise RuntimeError("triage close search returned an incomplete result")
        items = got.get("items") or []
        for i in items:
            if times and i.get("updated_at", "") < max(times):
                return times
            for c in _pages(gh, "{0}/issues/{1}/comments?since={2}&per_page=100".format(base, i["number"], s),
                            COMMENT_PAGES):
                body = c.get("body") or ""
                if TRIAGE_CLOSE_RE.search(body) and (u is None or c["created_at"] <= u):
                    if i.get("state") == "open" and not BACKLOG_TICK_RE.match(body):
                        if u is None:
                            continue
                        raise RuntimeError("issue {0} was triage closed at {1} and is open now; its state "
                                           "at {2} cannot be read".format(i["number"], c["created_at"], u))
                    times.append(c["created_at"])
        if len(items) < 100:
            return times
    raise RuntimeError("triage close search not resolved in {0} pages".format(SEARCH_PAGES))


def section_built_at(body, marker):
    """The build time (ISO) of the section `marker` opens when it carries
    built content, else None: a paused/failed/never/stale notice carries the
    marker too, so the marker alone would let a broken section read as seen.
    The time is the section's own (its opener's `built="..."`, or the feature
    health built line), never the issue's `updated_at`, which any edit moves
    (#889)."""
    # Anchor on the opener comment: a bare mention of the marker text earlier
    # in the body is not the section.
    lead = "" if marker.startswith("<!--") else r"<!--\s*"
    opener_match = re.search(lead + re.escape(marker), body)
    if not opener_match:
        return None
    idx = opener_match.start()
    line_end = body.find("-->", idx)
    opener = body[idx:line_end if line_end >= 0 else len(body)]
    if 'status="' in opener:
        built = re.search(r'\bbuilt="([^"]*)"', opener)
        if 'status="built"' not in opener or not built:
            return None
        try:
            return fmt_time(parse_time(built.group(1)))
        except ValueError:
            return None
    nxt = body.find("<!-- /", idx)
    block = body[idx:nxt if nxt >= 0 else len(body)]
    if "_Stale:" in block:
        return None
    # A section with no status attribute is built only when it carries its
    # own built line; a stray <details> block after the marker is not one.
    line = BUILT_LINE_RE.search(block)
    return line.group(1).replace(" ", "T") + ":00Z" if line else None


def section_built(body, marker):
    """True when `marker` opens a section carrying built content."""
    return section_built_at(body, marker) is not None


def board_status_updated_at(body):
    """The board-status job's own write time (ISO) from the issue body, or
    None when the body does not carry the job's Updated line."""
    line = BOARD_STATUS_UPDATED_RE.search(body)
    return line.group(1).replace(" ", "T") + ":00Z" if line else None


def read_signal(signal, repo, since, gh, environ, until=None):
    """The newest occurrence time (ISO) of a declared signal in the window, or
    None (FR-003). Marker and selector strings live in the registry or in the
    script that owns them; nothing is inferred from green runs. `until` caps
    the window for a past `now` (the SC-001 capture only; the build leaves it
    None): an occurrence after it is dropped, and a kind that can only read
    today's state raises rather than answer for a past day."""
    kind = signal["kind"]
    base = "repos/{0}".format(repo)
    s = fmt_time(since)
    u = fmt_time(until) if until else None
    if u and kind in ("issue_updated", "issue_section"):
        raise RuntimeError("{0} reads only the issue's current state; no read as of {1}".format(kind, u))
    times = []
    if kind == "merged_pr":
        # Closed PRs newest update first, paged until a page ends before the
        # window: a PR merged in the window was updated in it, so nothing
        # older can hold one (#889). No page count cuts the read short.
        # `title_prefixes`, when declared, narrows the head-prefix match to
        # PRs whose title also starts with one of them: every `spec/` PR is
        # not a final PR, only the one finalize.yml titles `Finalize: ` (#889).
        titles = signal.get("title_prefixes")
        page = 0
        while True:
            page += 1
            got = gh("{0}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={1}".format(base, page))
            for p in got:
                if p.get("merged_at") and p["merged_at"] >= s and any(
                        p["head"]["ref"].startswith(x) for x in signal.get("head_prefixes", [])) and (
                        not titles or any((p.get("title") or "").startswith(t) for t in titles)):
                    times.append(p["merged_at"])
            if len(got) < 100 or got[-1].get("updated_at", "") < s:
                break
    elif kind == "release":
        # Releases are listed newest first: page until one published before
        # the window (#889). A draft has no published_at and does not stop it.
        page = 0
        while True:
            page += 1
            got = gh("{0}/releases?per_page=100&page={1}".format(base, page))
            times.extend(r["published_at"] for r in got if r.get("published_at"))
            if len(got) < 100 or any((r.get("created_at") or r.get("published_at") or s) < s for r in got):
                break
    elif kind == "issue_or_comment":
        # Labeled issues and comments on them both count (the registry text).
        issues = _pages(gh, "{0}/issues?state=all&labels={1}&since={2}&per_page=100".format(
            base, signal["label_name"], s))
        if len(issues) > COMMENT_READ_CAP:
            raise RuntimeError("more than {0} labeled issues in window; comment read bounded".format(
                COMMENT_READ_CAP))
        for i in issues:
            times.append(i["created_at"])
        for i in issues:
            times.extend(c["created_at"] for c in _pages(
                gh, "{0}/issues/{1}/comments?since={2}&per_page=100".format(base, i["number"], s), COMMENT_PAGES))
    elif kind == "triage_close":
        times = _triage_close_times(gh, repo, base, since, until)
    elif kind == "branch_commit":
        branch = environ.get("METRICS_BRANCH") or signal["branch"]
        if u:
            got = gh("{0}/commits?sha={1}&until={2}&per_page=1".format(base, branch, u))
            times = [got[0]["commit"]["committer"]["date"]] if got else []
        else:
            times = [gh("{0}/commits/{1}".format(base, branch))["commit"]["committer"]["date"]]
    elif kind in ("issue_updated", "issue_section"):
        # The issue's updated_at moves on any edit, so the time is read from
        # the body: the section's own build time, or the board-status job's
        # Updated line (#889).
        for i in gh("{0}/issues?state=open&labels=disposition:tracking&per_page=100".format(base)):
            if not i["title"].startswith(signal["title"]):
                continue
            body = i.get("body") or ""
            at = (section_built_at(body, signal["marker"]) if kind == "issue_section"
                  else board_status_updated_at(body))
            if at:
                times.append(at)
    else:
        raise RuntimeError("unknown signal kind {0}".format(kind))
    times = [t for t in times if t >= s and (u is None or t <= u)]
    return max(times) if times else None


def collect(registry, repo, now, gh=gh_json, environ=None, read_text=None, start=None, until=None):
    """The readings, signals and ctx classify_all takes. A failed read makes
    only the thing it belongs to unreadable (FR-010). `start` and `until` pin
    a past window (capture_corpus only); the build passes neither."""
    environ = os.environ if environ is None else environ
    read_text = read_text or (lambda name: open(os.path.join(REPO_ROOT, ".github", "workflows", name),
                                                 encoding="utf-8").read())
    start = start or now - datetime.timedelta(days=window_days(registry))
    readings, signals = {}, {}
    ctx = {"switches": {}, "vars_set": {}}
    for entry in registry:
        for name, kind in ((entry.get("kill_switch"), "switches"), (entry.get("requires_var"), "vars_set")):
            if name:
                env = name[len(SWITCH_PREFIX):] if name.startswith(SWITCH_PREFIX) else name
                if env not in environ:
                    ctx[kind][name] = "unreadable"
                elif kind == "switches":
                    ctx[kind][name] = wc_board_status._switch_on(environ[env])
                else:
                    ctx[kind][name] = bool(environ[env].strip())
        for ref in entry["workflows"]:
            if ref["file"] in readings:
                continue
            try:
                interval = schedule_interval_hours(read_text(ref["file"]))
                # Read back at least as far as the not-running threshold, so a
                # weekly or monthly cron's last run before the window still counts.
                since = start
                if ref.get("cadence") == "schedule" and interval:
                    since = min(start, now - datetime.timedelta(hours=not_running_hours(interval)))
                runs = fetch_runs(gh, repo, ref["file"], since, now, ref.get("events"))
                readings[ref["file"]] = {"runs": runs, "interval_hours": interval}
                if since < start:
                    readings[ref["file"]]["window_start"] = fmt_time(start)
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                readings[ref["file"]] = {"unreadable": str(exc) or "read failed"}
        if entry.get("signal"):
            try:
                # A signal may list `also` readers; the newest occurrence of any counts.
                found = [read_signal(s, repo, start, gh, environ, until=until)
                         for s in [entry["signal"]] + list(entry["signal"].get("also") or [])]
                found = [t for t in found if t]
                signals[entry["name"]] = {"signal_at": max(found) if found else None}
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                signals[entry["name"]] = {"unreadable": str(exc) or "read failed"}
    return readings, signals, ctx


def _environ_as_of(registry, repo, now, gh):
    """The environ the workflow would have had at `now`: every registry switch
    and variable (and the metrics branch), from the repository variable, or ""
    when it is unset, as `${{ vars.X }}` gives. A variable changed after `now`
    has no readable past value, so the capture refuses rather than guess; one
    deleted since `now` leaves no trace and reads as unset."""
    names = {n for e in registry for n in (e.get("kill_switch"), e.get("requires_var")) if n}
    names.add(SWITCH_PREFIX + "METRICS_BRANCH")
    have = {}
    for page in range(1, 11):
        got = gh("repos/{0}/actions/variables?per_page=30&page={1}".format(repo, page))
        have.update({v["name"]: v for v in got.get("variables") or []})
        if len(got.get("variables") or []) < 30:
            break
    else:
        raise SystemExit("feature-health capture: more than 300 repository variables; read truncated")
    environ = {}
    for name in sorted(names):
        var = have.get(name)
        if var and parse_time(var["updated_at"]) > now:
            raise SystemExit("feature-health capture: {0} changed at {1}, after {2}; its value then "
                             "cannot be read".format(name, var["updated_at"], fmt_time(now)))
        environ[name[len(SWITCH_PREFIX):]] = var["value"] if var else ""
    return environ


def _workflow_text_at(commit):
    """read_text for a past `now`: the workflow file as committed at `commit`.
    A file that did not exist then raises OSError, which collect records as
    that workflow's unreadable reading."""
    def read(name):
        r = subprocess.run(["git", "show", "{0}:.github/workflows/{1}".format(commit, name)],
                           capture_output=True, cwd=REPO_ROOT)
        if r.returncode != 0:
            raise OSError("{0} does not exist at {1}".format(name, commit[:12]))
        return r.stdout.decode("utf-8")
    return read


def _completed_at(gh, repo, run):
    """When the attempt `run` reports finished (ISO), from its jobs: the
    latest job `completed_at`, or None while any job has none (still in
    flight) or the attempt has no jobs. A run's `updated_at` is not that
    time: GitHub moves it on later edits too (a log or artifact deletion,
    #889)."""
    path = "repos/{0}/actions/runs/{1}/attempts/{2}/jobs?per_page=100".format(
        repo, run["id"], run.get("run_attempt") or 1)
    jobs, page = [], 0
    while True:
        page += 1
        got = (gh(path + "&page={0}".format(page)) or {}).get("jobs") or []
        jobs.extend(got)
        if len(got) < 100:
            break
    done = [j.get("completed_at") for j in jobs]
    return max(done) if done and all(done) else None


def _runs_as_of(readings, now, gh, repo):
    """Keep only what classify_workflow reads of each run, in place. A run
    created before `now` but re-run after it reports its later attempt's
    start and conclusion, and what it showed at `now` cannot be read back, so
    the capture refuses rather than record a later result as the window's.
    A run still in progress at `now` (finished after it) is dropped: a build
    at `now` reads only completed runs, so it could not have seen it. A run
    whose `updated_at` is after `now` is judged by its attempt's completion
    time (_completed_at), not by `updated_at`, which a later edit moves; one
    updated by `now` was already finished then."""
    for name, reading in readings.items():
        late = [r["started_at"] for r in reading.get("runs") or [] if parse_time(r["started_at"]) > now]
        if late:
            raise SystemExit("feature-health capture: {0} has a run attempt started at {1}, after {2}; "
                             "its state then cannot be read".format(name, max(late), fmt_time(now)))
        if "runs" in reading:
            kept = []
            for r in reading["runs"]:
                if r.get("updated_at") and parse_time(r["updated_at"]) > now:
                    done = _completed_at(gh, repo, r)
                    if done is None or parse_time(done) > now:
                        continue
                kept.append({"started_at": r["started_at"], "conclusion": r["conclusion"]})
            reading["runs"] = sorted(kept, key=lambda r: r["started_at"])


def capture_corpus(repo, now, start, ref="origin/main", gh=gh_json, registry=None):
    """The SC-001 replay corpus (maintainer only, specs/126 tasks.md T030):
    collect() over [start, now] with `now` pinned in the past, the registry
    as merged, workflow files (for cron intervals) as committed on `ref`'s
    first-parent line at `now`, and switches as the repository variables held
    them then. Runs keep only what classify_workflow reads. Never run by the
    workflow (FR-013 still holds: it only reads)."""
    registry = registry or load_registry()
    check_rate_limit(gh)
    commit = subprocess.run(["git", "rev-list", "-1", "--first-parent", "--before=" + fmt_time(now), ref],
                            capture_output=True, text=True, cwd=REPO_ROOT, check=True).stdout.strip()
    if not commit:
        raise SystemExit("feature-health capture: no commit on {0} before {1}".format(ref, fmt_time(now)))
    environ = _environ_as_of(registry, repo, now, gh)
    readings, signals, ctx = collect(registry, repo, now, gh, environ, _workflow_text_at(commit),
                                     start=start, until=now)
    _runs_as_of(readings, now, gh, repo)
    return {"schema": 1, "repository": repo, "window": {"start": fmt_time(start), "now": fmt_time(now)},
            "now": fmt_time(now), "workflow_commit": commit,
            "captured_at": fmt_time(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)),
            "registry": registry, "readings": readings, "signals": signals, "ctx": ctx}


def build(repo, now=None, gh=gh_json, environ=None, read_text=None, registry=None):
    """Collect, classify, render. Exits non-zero when every feature's run
    history is unreadable (FR-010)."""
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    registry = registry or load_registry()
    check_rate_limit(gh)
    readings, signals, ctx = collect(registry, repo, now, gh, environ, read_text)
    if readings and all("unreadable" in r for r in readings.values()):
        raise SystemExit("feature-health: every workflow's run history is unreadable; not building")
    rows = classify_all(registry, readings, signals, ctx, now)
    return render_section(rows, now, len(registry))


def main(argv):
    if len(argv) >= 3 and argv[1] == "render":
        with open(argv[2], encoding="utf-8") as fh:
            data = json.load(fh)
        now = parse_time(data["now"])
        rows = classify_all(data["registry"], data["readings"], data.get("signals", {}), data["ctx"], now)
        sys.stdout.write(render_section(rows, now, len(data["registry"])))
        return 0
    if len(argv) == 8 and argv[1] == "capture" and argv[2::2] == ["--start", "--now", "--out"]:
        corpus = capture_corpus(os.environ["GITHUB_REPOSITORY"], parse_time(argv[5]), parse_time(argv[3]))
        with open(argv[7], "w", encoding="utf-8", newline="\n") as fh:
            json.dump(corpus, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print("feature-health: wrote {0}".format(argv[7]))
        return 0
    if len(argv) == 4 and argv[1] == "build" and argv[2] == "--out":
        text = build(os.environ["GITHUB_REPOSITORY"])
        with open(argv[3], "w", encoding="utf-8") as fh:
            fh.write(text)
        print("feature-health: wrote {0}".format(argv[3]))
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
