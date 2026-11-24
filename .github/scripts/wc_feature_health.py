#!/usr/bin/env python3
"""Feature health (specs/126-feature-health): one health state per feature,
decided by code from run history, kill switches and output signals.

Usage:
  wc_feature_health.py build --out feature-health-section.md
  wc_feature_health.py render READINGS.json     (pure: readings in, Markdown out)

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

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
REGISTRY_PATH = os.path.join(HERE, "feature-health-registry.json")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import wc_board_status  # noqa: E402
from board_triage import TRIAGE_CLOSE_COMMENT_PREFIX, TRIAGE_CLOSE_GROUNDS  # noqa: E402

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
MARKER_BEGIN = "<!-- wing-commander-feature-health -->"
MARKER_END = "<!-- /wing-commander-feature-health -->"
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
    qualifying = [r for r in runs if r.get("conclusion") not in NOT_QUALIFYING]
    detail["qualifying"] = len(qualifying)
    for r in qualifying:
        if r["conclusion"] == "success" and not detail["last_success"]:
            detail["last_success"] = r["started_at"]
        if r["conclusion"] != "success" and not detail["last_failure"]:
            detail["last_failure"] = r["started_at"]
    detail["last_run"] = runs[0]["started_at"] if runs else None
    if switch:
        return "paused", detail
    if not have_var and runs and all(r.get("conclusion") == "skipped" for r in runs):
        return "not configured", detail
    last = qualifying[:FAILING_WINDOW]
    if last and all(r["conclusion"] != "success" for r in last):
        return "failing", detail
    if ref.get("cadence") == "schedule" and interval:
        cutoff = now - datetime.timedelta(hours=2 * interval)
        if not runs or parse_time(runs[0]["started_at"]) < cutoff:
            return "not running", detail
    if not qualifying:
        return "idle", detail
    return "healthy", detail


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
    if state == "failing":
        return "- `{0}` — failing: last success {1}, last failure {2}".format(
            name, day(row["last_success"]), day(row["last_failure"]))
    if state == "quiet":
        if row["last_signal"] in (NOT_MEASURED, NEVER, None):
            return "- `{0}` — quiet: no {1} in the last {2} days".format(
                name, row["signal_label"], row["threshold_days"])
        return "- `{0}` — quiet: no {1} since {2} (threshold {3} days)".format(
            name, row["signal_label"], row["last_signal"], row["threshold_days"])
    if state == "not running":
        last = day(row["last_run"])
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
           "**Feature health** — built {0} · {1} features · {2} unreadable".format(
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
    """Smallest hours between scheduled runs across every uncommented `cron:`
    entry (double quoted, single quoted or plain); None if none; ValueError
    if one cannot be parsed, which makes the workflow unreadable."""
    crons = []
    for line in workflow_text.splitlines():
        m = re.match(r"""^\s*-?\s*cron:\s*(?:"([^"]+)"|'([^']+)'|([^"'#\s][^#]*?))\s*(?:#.*)?$""", line)
        if m:
            crons.append(m.group(1) or m.group(2) or m.group(3))
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
# that merely quotes a ground) is not a triage close (FR-003).
TRIAGE_CLOSE_RE = re.compile(r"^{0}({1}),".format(
    re.escape(TRIAGE_CLOSE_COMMENT_PREFIX), "|".join(re.escape(g) for g in TRIAGE_CLOSE_GROUNDS)), re.M)


def _triage_close_times(gh, repo, base, since):
    """Times of triage closes in the window. The search API names the closed
    issues whose comments carry the close sentence, newest update first, so
    the read does not grow with the number of closed issues; each candidate's
    comments are then matched exactly. A candidate updated before the newest
    match found so far cannot hold a newer one, so the read stops there; a
    search still unresolved after SEARCH_PAGES pages raises (FR-010/011)."""
    s = fmt_time(since)
    q = 'repo:{0} is:issue is:closed updated:>={1} "{2}"'.format(
        repo, s[:10], TRIAGE_CLOSE_COMMENT_PREFIX.strip())
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
            for c in _pages(gh, "{0}/issues/{1}/comments?since={2}&per_page=100".format(base, i["number"], s), 1):
                if TRIAGE_CLOSE_RE.search(c.get("body") or ""):
                    times.append(c["created_at"])
        if len(items) < 100:
            return times
    raise RuntimeError("triage close search not resolved in {0} pages".format(SEARCH_PAGES))


def section_built(body, marker):
    """True when `marker` opens a section carrying built content, not a
    paused/failed/never/stale notice (those carry the marker too, so the marker
    alone would let a broken section read as seen)."""
    # Anchor on the opener comment: a bare mention of the marker text earlier
    # in the body is not the section.
    lead = "" if marker.startswith("<!--") else r"<!--\s*"
    opener_match = re.search(lead + re.escape(marker), body)
    if not opener_match:
        return False
    idx = opener_match.start()
    line_end = body.find("-->", idx)
    opener = body[idx:line_end if line_end >= 0 else len(body)]
    if 'status="' in opener:
        return 'status="built"' in opener
    nxt = body.find("<!-- /", idx)
    block = body[idx:nxt if nxt >= 0 else len(body)]
    if "_Stale:" in block:
        return False
    return ("<details>" in block or "_Table shortened" in block
            or "**Feature health** — built" in block)


def read_signal(signal, repo, since, gh, environ):
    """The newest occurrence time (ISO) of a declared signal in the window, or
    None (FR-003). Marker and selector strings live in the registry or in the
    script that owns them; nothing is inferred from green runs."""
    kind = signal["kind"]
    base = "repos/{0}".format(repo)
    s = fmt_time(since)
    times = []
    if kind == "merged_pr":
        for page in (1, 2, 3):
            got = gh("{0}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={1}".format(base, page))
            for p in got:
                if p.get("merged_at") and p["merged_at"] >= s and any(
                        p["head"]["ref"].startswith(x) for x in signal.get("head_prefixes", [])):
                    times.append(p["merged_at"])
            if len(got) < 100 or got[-1].get("updated_at", "") < s:
                break
        else:
            raise RuntimeError("merged PR read truncated at 300 PRs")
    elif kind == "release":
        got = gh("{0}/releases?per_page=30".format(base))
        if len(got) >= 30 and all((r.get("published_at") or "") >= s for r in got):
            raise RuntimeError("release read truncated at 30 releases")
        times = [r["published_at"] for r in got if r.get("published_at")]
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
                gh, "{0}/issues/{1}/comments?since={2}&per_page=100".format(base, i["number"], s), 1))
    elif kind == "triage_close":
        times = _triage_close_times(gh, repo, base, since)
    elif kind == "branch_commit":
        branch = environ.get("METRICS_BRANCH") or signal["branch"]
        times = [gh("{0}/commits/{1}".format(base, branch))["commit"]["committer"]["date"]]
    elif kind in ("issue_updated", "issue_section"):
        for i in gh("{0}/issues?state=open&labels=disposition:tracking&per_page=100".format(base)):
            if not i["title"].startswith(signal["title"]):
                continue
            if kind == "issue_section" and not section_built(i.get("body") or "", signal["marker"]):
                continue
            times.append(i["updated_at"])
    else:
        raise RuntimeError("unknown signal kind {0}".format(kind))
    times = [t for t in times if t >= s]
    return max(times) if times else None


def collect(registry, repo, now, gh=gh_json, environ=None, read_text=None):
    """The readings, signals and ctx classify_all takes. A failed read makes
    only the thing it belongs to unreadable (FR-010)."""
    environ = os.environ if environ is None else environ
    read_text = read_text or (lambda name: open(os.path.join(REPO_ROOT, ".github", "workflows", name),
                                                 encoding="utf-8").read())
    start = now - datetime.timedelta(days=window_days(registry))
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
                runs = fetch_runs(gh, repo, ref["file"], start, now, ref.get("events"))
                interval = schedule_interval_hours(read_text(ref["file"]))
                readings[ref["file"]] = {"runs": runs, "interval_hours": interval}
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                readings[ref["file"]] = {"unreadable": str(exc) or "read failed"}
        if entry.get("signal"):
            try:
                # A signal may list `also` readers; the newest occurrence of any counts.
                found = [read_signal(s, repo, start, gh, environ)
                         for s in [entry["signal"]] + list(entry["signal"].get("also") or [])]
                found = [t for t in found if t]
                signals[entry["name"]] = {"signal_at": max(found) if found else None}
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                signals[entry["name"]] = {"unreadable": str(exc) or "read failed"}
    return readings, signals, ctx


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
