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
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The one need-a-run rule and the one reach computation (single home, Gate 89);
# reaching_workflows() is called per entry tree once `collect` lands (T018).
from board_prove import actions_only, reaching_workflows  # noqa: E402,F401
from board_triage import any_run_url_pattern  # noqa: E402
import wc_board_status  # noqa: E402

STATES = (1, 2, 3, 4, 5)
WINDOW_DAYS = 30
CAPTURE_DAYS = 33  # the SC-001 corpus window, 2026-10-15..2026-11-17 (research D13)
AGED_OUT_HOURS = 24
# data-model.md "State": 1 needs no run, 2 on record, 3 nothing reaches it,
# 4 reached but no finished run counts, 5 run(s) count but nothing on record.
STATE_NEEDS_NO_RUN, STATE_ON_RECORD, STATE_NOTHING_REACHES, STATE_NO_RUN, STATE_RUN_NO_RECORD = STATES

_RUN_URL_RE = re.compile(any_run_url_pattern())


def parse_time(value):
    """UTC datetime from an ISO string ending in Z or an offset, or a datetime.
    An offset is converted, never dropped: git's `%cI` keeps each commit's
    own `-04:00`/`-05:00`, and every time this module writes is UTC."""
    if not isinstance(value, datetime.datetime):
        value = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def utc_text(value):
    """The one serialised form of a time: `YYYY-MM-DDTHH:MM:SSZ`, in UTC."""
    return parse_time(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def window_for(end):
    """`start = end - 30 days`; the only way a build's window is set (FR-011)."""
    end = parse_time(end)
    return end - datetime.timedelta(days=WINDOW_DAYS), end


def capture_window_for(end):
    """The SC-001 corpus window, used by `capture` only, never by `build`."""
    end = parse_time(end)
    return end - datetime.timedelta(days=CAPTURE_DAYS), end


def pr_reference_pattern(repository, pr=None):
    """The one PR-reference rule (research D6): `#N` not preceded by a word
    character, `/` or `#` and not followed by a word character, or this
    repository's PR URL `github.com/<repository>/pull/N` not followed by a
    digit (case-insensitive). `pr` None matches any number. Another
    repository's PR URL is never a reference to this one's."""
    num = str(int(pr)) if pr is not None else r"\d+"
    alternatives = [r"(?<![\w#/])#{0}(?!\w)".format(num)]
    if repository:
        alternatives.append(r"github\.com/{0}/pull/{1}(?!\d)".format(re.escape(repository), num))
    return re.compile("|".join(alternatives), re.I)


def pr_named(body, pr, repository):
    """True when `body` names PR `pr` of `repository`."""
    if pr is None:
        return False
    return bool(pr_reference_pattern(repository, pr).search(body or ""))


def named_run_keys(body):
    """[(repository, run_id)] for every Actions run URL in `body`, in order."""
    return [(m.group(1).lower(), m.group(2)) for m in _RUN_URL_RE.finditer(body or "")]


def shared_issues(entries):
    """Issue numbers named by the PRs of more than one entry, any state."""
    named = {}
    for entry in entries:
        if entry.get("pr") is None:
            continue
        for issue in entry.get("named_issues") or ():
            named.setdefault(issue["number"], set()).add(entry["pr"])
    return {number for number, prs in named.items() if len(prs) > 1}


def shared_by_pass(entries, start, end):
    """(window, aged) shared-issue sets. FR-006: an issue is shared when more
    than one PR among the entries IN THE WINDOW names it; the aged-out pass,
    classified as if the window began a day earlier, adds the aged-out day's
    entries. `window` is the smaller set, so the more permissive one."""
    day_before = parse_time(start) - datetime.timedelta(hours=AGED_OUT_HOURS)
    return (shared_issues([e for e in entries if in_window(e, start, end)]),
            shared_issues([e for e in entries if in_window(e, day_before, end)]))


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


def comments_that_can_count(entries, comments_by_sha, repository, start, end):
    """[[comment, ...] per entry]: each entry's comments that pass steps 1-4
    for it. The named runs of any other comment are never needed. Uses the
    window's shared set, the more permissive one, so no comment that
    classify_all or set_apart could pass is left out."""
    shared, _aged = shared_by_pass(entries, start, end)
    return [[c for c in comments_by_sha.get(e["sha"], ())
             if comment_steps_1_to_4(e, c, shared, repository)] for e in entries]


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
            if key[0] == repository.lower() and run_qualifies(
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

    A window entry is classified with the window's shared issues (FR-006: the
    PRs among the entries in the window). The aged-out count is state 4 or 5
    among the commits in the 24 hours before `start`, classified as if the
    window began a day earlier, so with that day's PRs added (FR-012)."""
    shared_window, shared_aged = shared_by_pass(entries, start, end)
    day_before = parse_time(start) - datetime.timedelta(hours=AGED_OUT_HOURS)
    states, aged_out = {}, 0
    for entry in entries:
        comments = comments_by_sha.get(entry["sha"], ())
        if in_window(entry, start, end):
            states[entry["sha"]] = classify(entry, runs, comments, named_runs, shared_window, repository)
        elif in_window(entry, day_before, start):
            state = classify(entry, runs, comments, named_runs, shared_aged, repository)
            if state in (STATE_NO_RUN, STATE_RUN_NO_RECORD):
                aged_out += 1
    return states, aged_out


def set_apart(entries, runs, comments_by_sha, named_runs, repository, start, end):
    """Count of runs set apart, exactly FR-013's two cases, de-duplicated by run
    id or URL (data-model.md "SetApartRun")."""
    shared_window, shared_aged = shared_by_pass(entries, start, end)
    apart = set()
    for entry in entries:
        shared = shared_window if in_window(entry, start, end) else shared_aged
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
                own = key[0] == repository.lower()
                record = _named_run_for(entry, key, named_runs) if own else None
                if not own or (record or {}).get("kind") in ("foreign", "not_found") \
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
    return {"schema": 1, "built_at": utc_text(built_at),
            "window": {"start": utc_text(start), "end": utc_text(end)},
            "head_sha": head_sha, "counts": {str(k): v for k, v in cts.items()},
            "aged_out": aged_out, "set_apart": apart, "full": full, "names_only": names_only}


def counts(states):
    """{1..5: n} for a {sha: state} map."""
    out = {s: 0 for s in STATES}
    for state in states.values():
        out[state] += 1
    return out


# ---------------------------------------------------------------------------
# The I/O half: reads git and the GitHub API, then hands plain dicts to the
# pure half above. Every read raises ReadError on failure: an incomplete read
# fails the build loudly instead of shrinking the list (FR-013, research D15).
# ---------------------------------------------------------------------------
class ReadError(RuntimeError):
    """A read that failed or came back incomplete."""


class NotFound(ReadError):
    """`gh` reported `(HTTP 404)` on stderr."""


RATE_LIMIT_FLOOR = 600
RUN_CAP = 1000
SECONDARY_RE = re.compile(r"secondary rate limit", re.I)
SECONDARY_DEFAULT_WAIT = 30
RETRY_AFTER_RE = re.compile(r"retry-after:?\s*(\d+)", re.I)
# The section file's one home is the reader's constant (#889).
SECTION_FILE = wc_board_status.PROOF_LIST_FILE
FINALIZE_RE = re.compile(r"^Finalize:.*\(#(\d+)\)\s*$")
SPEC_BRANCH_RE = re.compile(r"^spec/([^/]+)$")
# The build fails with its own one-line reason before the job's
# `timeout-minutes: 25` cancels it, which would leave no line at all. The
# budget leaves two minutes for checkout and the guard; no single `git` or
# `gh` call may wait longer than CALL_TIMEOUT, or past the budget.
BUILD_BUDGET_SECONDS = 23 * 60
CALL_TIMEOUT = 120
_deadline = [None]  # monotonic seconds, set by start_budget()


# Progress lines (#889): a build logs each phase, and every PROGRESS_EVERY
# merges read, with the time since it started and the `gh` and `git` calls
# made so far, so a slow build's log says where the time went. Silent unless
# main() turns it on; they go to stderr, so stdout keeps its one line.
PROGRESS_EVERY = 10
_progress = {"stream": None, "started": 0.0, "gh": 0, "git": 0}


def start_progress(stream):
    import time
    _progress.update(stream=stream, started=time.monotonic(), gh=0, git=0)


def progress(what):
    import time
    if _progress["stream"] is None:
        return
    print("wc_proof_list: {0} ({1:.1f} s; {2} gh and {3} git calls so far)".format(
        what, time.monotonic() - _progress["started"], _progress["gh"], _progress["git"]),
        file=_progress["stream"], flush=True)


def start_budget(seconds=BUILD_BUDGET_SECONDS):
    import time
    _deadline[0] = None if seconds is None else time.monotonic() + seconds


def call_timeout(argv):
    """Seconds this call may wait: CALL_TIMEOUT, cut to what is left of the
    build's budget. A build already past its budget fails here, naming the
    call it was about to make."""
    import time
    if _deadline[0] is None:
        return CALL_TIMEOUT
    left = _deadline[0] - time.monotonic()
    if left <= 0:
        raise ReadError("the build ran past its {0}-minute budget before `{1}`".format(
            BUILD_BUDGET_SECONDS // 60, " ".join(argv[:4])))
    return min(CALL_TIMEOUT, left)


def _subprocess(argv, **kwargs):
    """subprocess.run under call_timeout(); a call that outlives it is a failed read."""
    import subprocess
    timeout = call_timeout(argv)
    tool = os.path.basename(argv[0]) if argv else ""
    if tool in ("gh", "git"):
        _progress[tool] += 1
    try:
        return subprocess.run(argv, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        if timeout < CALL_TIMEOUT:
            raise ReadError("the build ran past its {0}-minute budget during `{1}`".format(
                BUILD_BUDGET_SECONDS // 60, " ".join(argv[:4])))
        raise ReadError("`{0}` gave no answer within {1:.0f} s".format(" ".join(argv[:4]), timeout))


def _run(argv, cwd=None, sleep=None):
    import time
    # Bytes, decoded here as strict UTF-8: with text=True a failed decode
    # leaves stdout None on Windows (the reader thread dies), which read as an
    # empty thread (FR-013).
    proc = _subprocess(argv, capture_output=True, cwd=cwd)
    try:
        out = proc.stdout.decode("utf-8", errors="strict").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ReadError("{0}: output is not UTF-8 ({1})".format(" ".join(argv[:4]), exc))
    if proc.returncode == 0:
        return out
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if "(HTTP 404)" in err:
        raise NotFound("{0}: {1}".format(" ".join(argv[:4]), err))
    if argv[0] == "gh" and SECONDARY_RE.search(err):
        # A secondary limit only: wait what the server said, once. A primary
        # limit (403/429 without that text) is a failed read, no back-off.
        # `gh api` seldom prints Retry-After: without it wait a fixed, bounded time.
        match = RETRY_AFTER_RE.search(err)
        if sleep is not False:
            wait = min(int(match.group(1)), 60) if match else SECONDARY_DEFAULT_WAIT
            # The wait counts against the budget too: wait no longer than it has left.
            (sleep or time.sleep)(min(wait, max(call_timeout(argv) - 1, 0)))
            return _run(argv, cwd, sleep=False)
    raise ReadError("{0}: {1}".format(" ".join(argv[:4]), err or "exit {0}".format(proc.returncode)))


def gh_text(args):
    return _run(["gh"] + list(args))


def api(path, paginate=False):
    """JSON from `gh api path`; a paginated list is flattened (an object page
    contributes its one list value). An empty or unparseable read is a
    failed read, never an empty list (FR-013)."""
    args = ["api", path] if not paginate else ["api", "--paginate", "--slurp", path]
    text = gh_text(args)
    if not (text or "").strip():
        raise ReadError("gh api {0}: empty read".format(path))
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ReadError("gh api {0}: not JSON ({1})".format(path, exc))
    if not paginate:
        return doc
    if not isinstance(doc, list):
        raise ReadError("gh api {0} (paged): not a list of pages".format(path))
    pages, out = doc, []
    for page in pages:
        if isinstance(page, dict):
            lists = [v for v in page.values() if isinstance(v, list)]
            out.extend(lists[0] if lists else [])
        else:
            out.extend(page)
    return out


def check_rate_limit(floor=RATE_LIMIT_FLOOR):
    remaining = int(gh_text(["api", "rate_limit", "--jq", ".resources.core.remaining"]).strip() or 0)
    if remaining < floor:
        raise ReadError("only {0} API requests remain (below {1})".format(remaining, floor))
    return remaining


def git(*args):
    return _run(["git"] + list(args))


def first_parent_commits(since=None):
    """[(sha, committer time)] newest first on the checked-out default branch.
    A shallow clone is an incomplete history (FR-013)."""
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise ReadError("the checkout is shallow: main history is incomplete")
    out = []
    for line in git("log", "--first-parent", "--format=%H %cI").splitlines():
        sha, when = line.split(" ", 1)
        if since is None or parse_time(when) > parse_time(since):
            out.append((sha, parse_time(when)))
    return out


def is_ancestor(ancestor, descendant):
    proc = _subprocess(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                       capture_output=True, text=True)
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise ReadError("git merge-base failed: {0}".format(proc.stderr.strip()))


def commit_present(sha):
    return _subprocess(["git", "cat-file", "-e", "{0}^{{commit}}".format(sha)],
                       capture_output=True).returncode == 0


def marker_step(body):
    """`proven` | `other` | `none` for the board item marker in `body`."""
    from board_item_marker import MARKER_OPEN_RE, last_marker_match
    if not MARKER_OPEN_RE.search(body or ""):
        return "none"
    match = last_marker_match(body)
    if match is None:
        return "other"
    try:
        step = json.loads(match.group(1)).get("step")
    except (ValueError, AttributeError):
        return "other"
    return "proven" if step == "proven" else "other"


def closing_targets(text, repository):
    """[N] for this repository's issues that a GitHub closing keyword in
    `text` names (`Fixes #N`, `closes owner/repo#N`, `resolved: GH-N`, an
    issue URL), in order. Another repository's issue is dropped, as R4 drops
    its closingIssuesReferences."""
    from board_backlog_lines import CLOSING_RE
    own, out = repository.lower(), []
    for match in CLOSING_RE.finditer(text or ""):
        target = re.split(r"[:\s]+", match.group(0), maxsplit=1)[1]
        if target.lower().startswith("http"):
            parts = target.split("/")  # https: '' github.com owner repo issues N
            repo, number = "/".join(parts[3:5]), parts[6]
        elif target.upper().startswith("GH-"):
            repo, number = own, target[3:]
        else:
            repo, _hash, number = target.rpartition("#")
            repo = repo or own
        if repo.lower() == own and int(number) not in out:
            out.append(int(number))
    return out


def ref_repository(ref):
    """`owner/name`, lower case, of a `closingIssuesReferences` item. A
    reference that says neither fails the read: guessing this repository
    would read another repository's issue of the same number."""
    repo = ref.get("repository") or {}
    owner, name = (repo.get("owner") or {}).get("login"), repo.get("name")
    if owner and name:
        return "{0}/{1}".format(owner, name).lower()
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/issues/\d+$", ref.get("url") or "")
    if match:
        return match.group(1).lower()
    raise ReadError("closingIssuesReferences item #{0} names no repository".format(ref.get("number")))


def is_pending_review(raw):
    """A review not yet submitted: no `submitted_at`, nothing posted (only the
    reading token's own pending reviews are visible)."""
    return raw.get("state") == "PENDING" or not raw.get("submitted_at")


def comment_record(place, raw, kind):
    user = raw.get("user") or {}
    posted = raw.get("submitted_at") or raw.get("created_at")
    if not posted:
        raise ReadError("{0} {1} on {2} #{3} has no time".format(
            kind, raw.get("id"), place.get("kind"), place.get("number")))
    return {"place": place, "where": kind, "comment_id": raw.get("id"),
            "account": user.get("login"), "account_type": user.get("type", "User"),
            "posted_at": posted,
            "body": raw.get("body") or "", "marker_step": marker_step(raw.get("body"))}


def run_total(query):
    """`total_count` of a run-list query, read as one run: the count is the
    same at any page size, and a full first page of runs is ~1.5 MB and ~2 s
    (2026-11-26), while the day-sliced lists ask for a count once per day per
    workflow over 1,000 runs."""
    probe = query.replace("per_page=100", "per_page=1", 1)
    if probe == query:
        raise ValueError("run_total: {0} has no per_page=100".format(query))
    return int(api(probe + "&page=1").get("total_count", 0))


class Collector:
    """One build's reads, with per-build caches (commits' trees, issue threads,
    named runs, workflow run lists)."""

    def __init__(self, repository, built_at, window=window_for):
        self.repository = repository
        self.built_at = parse_time(built_at)
        self.start, self.end = window(self.built_at)
        self.since = self.start - datetime.timedelta(hours=AGED_OUT_HOURS)
        self.threads, self.named, self.run_lists, self.trees = {}, {}, {}, {}
        self.present, self.ancestry, self.thread_since = {}, {}, {}

    # -- entries -----------------------------------------------------------
    def entries(self):
        from board_backlog_lines import pr_issue, pr_line
        from board_route_backstop import diff_name_list
        out = []
        commits = [(sha, when) for sha, when in first_parent_commits(self.since) if when <= self.end]
        for sha, when in commits:
            if out and len(out) % PROGRESS_EVERY == 0:
                progress("entries: {0} of {1} merges read".format(len(out), len(commits)))
            pulls = api("repos/{0}/commits/{1}/pulls".format(self.repository, sha), paginate=True)
            pr = next((p for p in pulls if p.get("merge_commit_sha") == sha), None)
            if pr is None:
                # A rebase merge leaves only the last commit as merge_commit_sha;
                # earlier commits of the same merged PR belong to it too.
                merged = [p for p in pulls if p.get("merged_at")]
                pr = merged[0] if len(merged) == 1 else None
            changed = diff_name_list(sha + "^1", sha)
            needs_run, reason = actions_only(changed)
            entry = {"sha": sha, "merged_at": utc_text(when),
                     "pr": pr["number"] if pr else None, "named_issues": [],
                     "lifecycle_issue": None, "changed_paths": changed,
                     "needs_run": needs_run, "needs_reason": reason, "reaching": []}
            if pr:
                view = json.loads(gh_text(["pr", "view", str(pr["number"]), "-R", self.repository,
                                           "--json", "closingIssuesReferences,body,title,headRefName"]))
                seen = {}
                for ref in view.get("closingIssuesReferences") or ():
                    # A PR can close another repository's issue; only this
                    # repository's issues are places of this entry.
                    if ref_repository(ref) == self.repository.lower():
                        seen.setdefault(ref["number"], "closes")
                body = view.get("body") or ""
                if pr_issue(body):
                    seen.setdefault(pr_issue(body), "board-item")
                if pr_line(body):
                    seen.setdefault(pr_line(body)[0], "backlog-line")
                life = self.lifecycle_issue(sha, view.get("title") or "", view.get("headRefName"))
                if life:
                    seen.setdefault(life, "lifecycle")
                    entry["lifecycle_issue"] = life
                for number in self.closed_by_commit(sha, seen):
                    seen.setdefault(number, "closes-commit")
                entry["named_issues"] = [{"number": n, "how": h} for n, h in sorted(seen.items())]
            if needs_run:
                entry["reaching"] = self.reaching(sha, changed)
            out.append(entry)
        return out

    def lifecycle_issue(self, sha, title, head_ref):
        """research D6: a final PR's lifecycle issue is `.issue` in
        `specs/<slug>/spec-meta.json` in the merge commit's tree, `<slug>`
        from the PR's head branch `spec/<slug>`, cross-checked against the
        title's `(#N)`. Other spec directories the PR touched are never read
        (final PRs edit other specs' live contracts). Not a final PR, a head
        branch that is not `spec/<slug>`, or no spec-meta.json at that commit:
        None."""
        match = FINALIZE_RE.match(title)
        slug = SPEC_BRANCH_RE.match(head_ref or "")
        if not match or not slug:
            return None
        path = "specs/{0}/spec-meta.json".format(slug.group(1))
        # `ls-tree` prints nothing for a path absent at that commit and fails
        # only when the commit itself cannot be read.
        if not git("ls-tree", "--name-only", sha, "--", path).strip():
            return None
        try:
            meta = json.loads(git("show", "{0}:{1}".format(sha, path)))
            issue = int(meta.get("issue"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ReadError("{0} unreadable at {1}: {2}".format(path, sha[:10], exc))
        if issue != int(match.group(1)):
            raise ReadError("{0}: spec-meta issue {1} disagrees with the title's #{2}".format(
                path, meta.get("issue"), match.group(1)))
        return issue

    def closed_by_commit(self, sha, already):
        """FR-006 "each issue the pull request closes": a squash merge's
        message (the PR title, `Fix #N: ...`) closes issue N from the default
        branch while `closingIssuesReferences` stays empty. Candidates are
        this repository's issues named after a closing keyword in the merge
        commit's message (board_backlog_lines.CLOSING_RE, the one home of
        GitHub's keyword grammar); each is kept only when its
        `issues/{N}/events` has a `closed` event whose `commit_id` is this
        merge. One read per candidate not already named. A number that is
        no issue (404) is no candidate."""
        message = git("log", "-1", "--format=%B", sha)
        out = []
        for number in closing_targets(message, self.repository):
            if number in already or number in out:
                continue
            try:
                events = api("repos/{0}/issues/{1}/events?per_page=100".format(self.repository, number), True)
            except NotFound:
                continue
            if any(e.get("event") == "closed" and e.get("commit_id") == sha for e in events):
                out.append(number)
        return out

    def reaching(self, sha, changed):
        if sha not in self.trees:
            self.trees[sha] = tree_reaching(sha, changed)
        return self.trees[sha]

    # -- comments ----------------------------------------------------------
    @staticmethod
    def thread_keys(entry):
        """The (kind, number) threads an entry's comments are read from (D6)."""
        keys = [("pr", entry["pr"])] if entry.get("pr") is not None else []
        return keys + [("issue", i["number"]) for i in entry.get("named_issues") or ()]

    def bound_threads(self, entries):
        """research D6: each thread is read once, with `?since=` set to the
        earliest merge among ALL the entries that read it. Done before any
        read: a bound taken from the first (newest) reader would drop the
        comments an older entry on the same shared issue needs."""
        for entry in entries:
            for key in self.thread_keys(entry):
                when = parse_time(entry["merged_at"])
                if key not in self.thread_since or when < self.thread_since[key]:
                    self.thread_since[key] = when

    def thread(self, kind, number):
        key = (kind, number)
        if key not in self.threads:
            base = "repos/{0}".format(self.repository)
            # `since` filters by update time, so it only bounds the read; the
            # classifier still keeps a comment only when it was posted after
            # its entry's merge. Review bodies take no `since` (D6).
            since = self.thread_since.get(key)
            bound = "per_page=100" + ("&since={0}".format(utc_text(since)) if since else "")
            if kind == "pr":
                items = [(c, "pr-issue-comment")
                         for c in api("{0}/issues/{1}/comments?{2}".format(base, number, bound), True)]
                items += [(c, "pr-review-comment")
                          for c in api("{0}/pulls/{1}/comments?{2}".format(base, number, bound), True)]
                items += [(c, "pr-review")
                          for c in api("{0}/pulls/{1}/reviews?per_page=100".format(base, number), True)
                          if not is_pending_review(c)]
            else:
                items = [(c, "issue {0}".format(number))
                         for c in api("{0}/issues/{1}/comments?{2}".format(base, number, bound), True)]
            place = {"kind": kind, "number": number}
            self.threads[key] = [comment_record(place, c, w) for c, w in items]
        return self.threads[key]

    def comments_for(self, entry):
        out = []
        for kind, number in self.thread_keys(entry):
            out += self.thread(kind, number)
        return out

    # -- runs --------------------------------------------------------------
    def completed_runs(self, list_path, label):
        """Every completed run in `list_path` (a run-list endpoint) created
        since the aged-out day began: one paged read, or one per day when the
        window holds more than RUN_CAP, since the API lists no further."""
        query = "{0}?status=completed&per_page=100&created=%3E%3D{1}".format(list_path, utc_text(self.since))
        if run_total(query) <= RUN_CAP:
            return api(query, paginate=True)
        runs, day = [], self.since
        while day < self.end:
            nxt = day + datetime.timedelta(days=1)
            # The range is inclusive at both ends: stop one second early.
            span = "created={0}..{1}".format(
                utc_text(day),
                utc_text(nxt - datetime.timedelta(seconds=1)))
            q = "{0}?status=completed&per_page=100&{1}".format(list_path, span)
            if run_total(q) > RUN_CAP:
                raise ReadError("{0}: more than {1} runs in one day".format(label, RUN_CAP))
            runs += api(q, paginate=True)
            day = nxt
        return runs

    def workflow_runs(self, path):
        if path in self.run_lists:
            return self.run_lists[path]
        base = "repos/{0}/actions".format(self.repository)
        name = path.rsplit("/", 1)[-1]
        try:
            runs = self.completed_runs("{0}/workflows/{1}/runs".format(base, name), name)
        except NotFound:
            # The file is gone from the default branch: read the repository's
            # runs, sliced by day the same way (the whole repository passes
            # the cap in any window), and keep the ones of that path. A run's
            # `path` can carry an `@refs/...` suffix (#889). A later-deleted
            # workflow is still credited (FR-013).
            runs = [r for r in self.completed_runs(
                        "{0}/runs".format(base), "{0} (deleted; the repository's runs)".format(name))
                    if (r.get("path") or "").split("@")[0] == path]
        self.run_lists[path] = runs
        return runs

    def run_record(self, raw, entries):
        head = raw.get("head_sha")
        if head not in self.present:
            self.present[head] = bool(head) and commit_present(head)
        resolvable = self.present[head]
        contains = []
        started = raw.get("run_started_at") or raw.get("created_at")
        for e in entries:
            if not resolvable:
                break
            # A head cannot contain a merge made after the run started.
            if started and parse_time(started) <= parse_time(e["merged_at"]):
                continue
            if (e["sha"], head) not in self.ancestry:
                self.ancestry[(e["sha"], head)] = is_ancestor(e["sha"], head)
            if self.ancestry[(e["sha"], head)]:
                contains.append(e["sha"])
        return {"workflow": raw.get("path"), "run_id": raw["id"], "event": raw.get("event"),
                "status": raw.get("status"), "conclusion": raw.get("conclusion"), "head_sha": head,
                "run_started_at": raw.get("run_started_at") or raw.get("created_at"),
                "html_url": raw.get("html_url"), "contains": contains, "resolvable": resolvable}

    def runs(self, entries):
        paths = sorted({w["path"] for e in entries for w in e.get("reaching") or ()
                        if w.get("runs_of_its_own", True)})
        out = {}
        for path in paths:
            relevant = [e for e in entries if any(w["path"] == path for w in e.get("reaching") or ())]
            out[path] = [self.run_record(r, relevant) for r in self.workflow_runs(path)]
            progress("runs: {0} runs of {1}".format(len(out[path]), path))
        return out

    def named_runs(self, comments_by_sha, entries):
        """Reads each run named by a comment that passes steps 1-4 for at
        least one entry; a comment that fails them can never count or be set
        apart, so its runs are never read (research D15)."""
        out = {}
        for comments in comments_that_can_count(entries, comments_by_sha, self.repository,
                                                self.start, self.end):
            for comment in comments:
                for repo, run_id in named_run_keys(comment.get("body")):
                    key = "{0}/{1}".format(repo, run_id)
                    if repo != self.repository.lower() or key in out:
                        continue
                    if key not in self.named:
                        try:
                            raw = api("repos/{0}/actions/runs/{1}".format(repo, run_id))
                            rec = self.run_record(raw, entries)
                            rec.update(kind="found", url=raw.get("html_url"))
                        except NotFound:
                            rec = {"kind": "not_found", "run_id": run_id}
                        self.named[key] = rec
                    out[key] = self.named[key]
        return out


def collect(repository, built_at, window=window_for):
    """Every input of the pure half, read from git and the API."""
    progress("start: {0} API requests remain".format(check_rate_limit()))
    col = Collector(repository, built_at, window)
    entries = col.entries()
    progress("entries: {0} merges read, {1} need a run".format(
        len(entries), sum(1 for e in entries if e["needs_run"])))
    col.bound_threads([e for e in entries if e["needs_run"]])
    comments_by_sha = {e["sha"]: col.comments_for(e) for e in entries if e["needs_run"]}
    progress("comments: {0} threads read".format(len(col.threads)))
    runs = col.runs(entries)
    progress("runs: {0} runs of {1} reaching workflows read".format(
        sum(len(v) for v in runs.values()), len(runs)))
    named = col.named_runs(comments_by_sha, entries)
    progress("named runs: {0} read".format(len(named)))
    return {"repository": repository, "built_at": utc_text(col.built_at),
            "head_sha": git("rev-parse", "HEAD").strip(), "entries": entries, "runs": runs,
            "comments": comments_by_sha, "named_runs": named}


# -- per-entry trees (US3) ---------------------------------------------------
# What the reach scan reads of a merge's tree: `.github` less the
# subdirectories of `.github/scripts`. The scan resolves imports only against
# top-level helper scripts (board_prove.py); the subdirectories (tests,
# fixtures) were ~15 MB of a 27 MB archive, extracted and deleted once per
# merge in the window. An exclude that matches nothing is no error.
TREE_PATHSPECS = (".github", ":(exclude,glob).github/scripts/*/**")


def tree_reaching(sha, changed_paths):
    """[ReachingWorkflow] from the `.github` tree at `sha` (not today's): the
    shared reach computation plus the nightly end-to-end edges, merged here only
    (FR-005; the hand procedure never merges them)."""
    import contextlib
    import io
    import tarfile
    import tempfile
    from board_prove import (AUTO_RELEASE, WORKFLOWS_DIR, reach,
                             reaching_workflows as _reaching, nightly_e2e_edges,
                             runs_of_its_own as _own, scan_dispatchable_and_uses_graph)
    current = git("rev-parse", "HEAD").strip() == git("rev-parse", sha).strip()
    archive = _subprocess(["git", "archive", sha, "--"] + list(TREE_PATHSPECS), capture_output=True)
    if archive.returncode != 0:
        raise ReadError("git archive {0} failed: {1}".format(sha[:10], archive.stderr.decode(errors="replace")))
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            _disp, graph = scan_dispatchable_and_uses_graph(WORKFLOWS_DIR)
            base = _reaching(changed_paths, graph)
            # An unparseable stage array is fatal only on the current tree;
            # a historical merge's tree carrying one gets no nightly edges,
            # or that one tree would fail every daily build until it left
            # the window (#889).
            try:
                extra, stages = nightly_e2e_edges(".", with_stages=True)
            except ValueError:
                if not current:
                    extra, stages = {}, []
                else:
                    raise
            extended = {k: set(v) for k, v in graph.items()}
            if extra:
                extended.setdefault(AUTO_RELEASE, set()).update(extra[AUTO_RELEASE], stages)
                for wrapper in extra[AUTO_RELEASE]:
                    extended.setdefault(wrapper, set(graph.get(wrapper, ())))
            hits = _reaching(changed_paths, extended)
            found = []
            for path in sorted(hits):
                if path not in graph and not os.path.isfile(path):
                    continue
                if path in base:
                    via = "mention" if set(base[path].values()) == {"mention"} else "scan"
                else:
                    via = "nightly-e2e"
                found.append({"path": path, "reached_via": via,
                              "runs_of_its_own": _own(path) if os.path.isfile(path) else True})
            reaches = {w["path"]: reach(w["path"], extended) for w in found}
            # A workflow_call-only workflow with an in-repository caller that
            # reaches the same path is dropped (research D4).
            return [w for w in found
                    if w["runs_of_its_own"]
                    or not any(w["path"] in reaches[o["path"]] for o in found if o["path"] != w["path"])]
        finally:
            os.chdir(previous)


# -- capture, build, render ---------------------------------------------------
def reduce_body(body, repository):
    """Keep lines carrying a run link, a PR reference or the board item
    marker (data-model.md "SC-001 corpus"); every other line becomes an
    ellipsis. The keep-test is built from the patterns the classifier itself
    reads with (research D6 reused homes), so a replay of the reduced body
    classifies as the live build did."""
    from board_item_marker import MARKER_OPEN_RE
    keeps = (_RUN_URL_RE, MARKER_OPEN_RE, pr_reference_pattern(repository))
    return "\n".join(line if any(k.search(line) for k in keeps) else "…"
                     for line in (body or "").splitlines())


def capture(bundle, as_of):
    """The SC-001 corpus document (data-model.md "SC-001 corpus")."""
    start, end = capture_window_for(bundle["built_at"])
    cutoff = parse_time(as_of)

    def known(when):
        return not when or parse_time(when) <= cutoff

    out = dict(bundle, as_of=utc_text(as_of), window={"start": utc_text(start), "end": utc_text(end)})
    out["entries"] = [e for e in bundle.get("entries", []) if known(e.get("merged_at"))]
    out["named_runs"] = {k: r for k, r in (bundle.get("named_runs") or {}).items()
                         if known(r.get("run_started_at"))}
    repository = bundle["repository"]
    out["comments"] = {sha: [dict(c, body=reduce_body(c.get("body"), repository)) for c in cs
                             if known(c.get("posted_at"))]
                       for sha, cs in bundle["comments"].items()}
    out["runs"] = {path: [r for r in rs if known(r.get("run_started_at"))]
                   for path, rs in bundle["runs"].items()} if isinstance(bundle["runs"], dict) else bundle["runs"]
    return out


def report_from_bundle(bundle):
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    return assemble_report(bundle["entries"], bundle["runs"], bundle["comments"], bundle["named_runs"],
                           bundle["repository"], bundle["built_at"], bundle["head_sha"],
                           MAX_BODY_UNITS, utf16_len)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="read, classify and write the section file ({0})".format(SECTION_FILE))
    build.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    build.add_argument("--out", default=SECTION_FILE)
    cap = sub.add_parser("capture", help="write the SC-001 corpus (maintainer only)")
    cap.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    cap.add_argument("--end", required=True)
    cap.add_argument("--as-of", required=True)
    cap.add_argument("--out", required=True)
    rend = sub.add_parser("render", help="print one form of a built section")
    rend.add_argument("--in", dest="src", default=SECTION_FILE)
    rend.add_argument("--form", choices=("full", "names_only"), default="full")
    args = parser.parse_args(argv)
    import subprocess
    import tarfile
    try:
        if args.cmd == "render":
            with open(args.src, encoding="utf-8") as fh:
                sys.stdout.write(json.load(fh)[args.form])
            return 0
        if not args.repository:
            parser.error("--repository (or GITHUB_REPOSITORY) is required")
        start_progress(sys.stderr)
        if args.cmd == "build":
            start_budget()
            now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            doc = report_from_bundle(collect(args.repository, now))
        else:
            doc = capture(collect(args.repository, args.end, capture_window_for), args.as_of)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
        print("wrote {0}".format(args.out))
        return 0
    except (ReadError, ValueError, subprocess.CalledProcessError, OSError, tarfile.TarError) as exc:
        # FR-013: a failed git, tar or file read ends the build with this one
        # line, never a traceback (#889). OSError covers FileNotFoundError.
        # A failed git call's own reason is in its captured stderr.
        err = getattr(exc, "stderr", None)
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        why = " ".join(err.split()) if isinstance(err, str) else ""
        print("::error::wc_proof_list: {0}{1}".format(exc, ": " + why if why else ""))
        return 1
    finally:
        _progress["stream"] = None


if __name__ == "__main__":
    sys.exit(main())
