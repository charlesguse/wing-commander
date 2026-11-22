#!/usr/bin/env python3
"""Daily board status: one issue, rewritten in place (board reset of
2026-10-01).

WHY THIS EXISTS
---------------
At the reset the owner could not tell from the board how far along any
spec was: 80+ open issues, most of them the pipeline's own findings. The
Roadmap issue holds the plan, but it is edited by hand and drifts. This
renders the board as it actually is: what waits on the owner, what the
pipeline is working on, the maintenance backlog's size, the open signals,
main's CI and the last release. A daily job (board-status.yml) writes it
into ONE issue and rewrites that issue in place.

No agent. `snapshot()` reads the board with `gh api`. `render()` is a pure
function of that snapshot, which verify-board-status.py drives from
fixtures. `publish()` edits the one open issue that carries MARKER and was
opened by a bot, creating it on the first run.

    python3 wc_board_status.py publish        # the workflow's only call
    python3 wc_board_status.py render FILE    # print the body for a snapshot
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

MARKER = "<!-- wing-commander-board-status -->"
TITLE = "Board status"
TRACKING_LABEL = "disposition:tracking"
AUTO_RELEASE_FAILED_LABEL = "auto-release:failed"
LINT_WORKFLOW = "lint-workflows.yml"
TITLE_LIMIT = 80

# Lifecycle stages the pipeline works without the owner. The rest are
# decided per item in lifecycle_wait().
PIPELINE_STAGES = {"stage:tasks": "tasks", "stage:implement": "implement"}


def _labels(item):
    return set(item.get("labels") or [])


def _spec_label(labels):
    for name in sorted(labels):
        if name.startswith("spec:"):
            return name
    return ""


# Pipeline order. A stage label is added before the previous one is
# removed, and stage:stalled is added beside the stage it stopped in, so an
# issue can carry two: stalled wins, then the furthest stage.
STAGE_ORDER = ("stage:spec", "stage:clarify", "stage:plan", "stage:tasks",
               "stage:implement", "stage:review", "stage:done")


def _stage(labels):
    if "stage:stalled" in labels:
        return "stage:stalled"
    known = [name for name in STAGE_ORDER if name in labels]
    if known:
        return known[-1]
    for name in sorted(labels):
        if name.startswith("stage:"):
            return name
    return ""


def _days(now, stamp):
    if not stamp:
        return ""
    then = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    return "{0}d".format(max(0, (now - then).days))


def _title(text):
    # Titles are often agent-written. One code span with its backticks
    # removed renders no mention, link, HTML or table pipe, and a quoted
    # marker is broken so publish() can't mistake it for the status issue.
    text = " ".join(str(text).replace("`", "'").replace("<!--", "<! --").split())
    if len(text) > TITLE_LIMIT:
        text = text[:TITLE_LIMIT - 3].rstrip() + "..."
    return "`{0}`".format(text.replace("|", "/")) if text else "`(untitled)`"


def _switch_on(value):
    return str(value or "").strip().lower() == "true"


def lifecycle_wait(issue, prs, switches):
    """-> (who, what): who is "owner" or "pipeline"."""
    labels = _labels(issue)
    stage = _stage(labels)
    linked = [p for p in prs if _spec_label(labels) and _spec_label(labels) in _labels(p)]
    pr_ref = ", ".join("#{0}".format(p["number"]) for p in linked)
    notes = []
    if "rebase:blocked" in labels:
        notes.append("rebase blocked")
    if stage == "stage:stalled" or "board:stalled" in labels:
        who, what = "owner", "stalled: re-admit it or close it"
    elif stage == "stage:clarify":
        if issue.get("last_comment_by_bot"):
            who, what = "owner", "answer the clarify questions"
        else:
            who, what = "pipeline", "clarify is folding your answers"
    elif stage in ("stage:spec", "stage:plan"):
        kind = stage.split(":", 1)[1]
        if linked:
            who, what = "owner", "review and merge the {0} PR ({1})".format(kind, pr_ref)
        else:
            who, what = "pipeline", "drafting the {0}".format(kind)
    elif stage == "stage:tasks" and linked and switches.get("tasks_review") == "pr":
        who, what = "owner", "review and merge the tasks PR ({0})".format(pr_ref)
    elif stage in PIPELINE_STAGES:
        who, what = "pipeline", PIPELINE_STAGES[stage]
    elif stage == "stage:review":
        gate_merges = (_switch_on(switches.get("lifecycle_auto_merge"))
                       and not _switch_on(switches.get("review_gate_paused")))
        if gate_merges:
            who, what = "pipeline", "final PR {0} with the lifecycle review gate".format(pr_ref or "(none open)")
        else:
            who, what = "owner", "review and merge the final PR ({0})".format(pr_ref or "none open")
    elif stage == "":
        who, what = "pipeline", "intake"
    else:
        who, what = "pipeline", stage.split(":", 1)[1]
    if notes:
        who = "owner"
        what = "{0} ({1})".format(what, ", ".join(notes))
    return who, what


def classify(snap):
    """-> dict of the rendered sections' rows, so fixtures can assert on
    the decision separately from the markdown."""
    now = datetime.datetime.strptime(snap["now"], "%Y-%m-%dT%H:%M:%SZ")
    switches = snap.get("switches") or {}
    prs = snap.get("prs") or []
    owner, pipeline, signals = [], [], {}
    for issue in sorted(snap.get("issues") or [], key=lambda i: i["number"]):
        labels = _labels(issue)
        ref = "#{0} {1}".format(issue["number"], _title(issue.get("title", "")))
        age = _days(now, issue.get("created_at"))
        if TRACKING_LABEL in labels:
            continue
        if "spec-request" in labels:
            spec = _spec_label(labels)
            if spec:
                ref = "#{0} spec {1}".format(issue["number"], spec.split(":", 1)[1].split("-", 1)[0])
            who, what = lifecycle_wait(issue, prs, switches)
            (owner if who == "owner" else pipeline).append((ref, what, age))
        elif AUTO_RELEASE_FAILED_LABEL in labels:
            # The board loop never acts on it (board_eligibility.
            # SELF_MANAGED_LABELS; verify-board-status.py holds the label
            # there), so nothing but the owner fixes its cause. auto-release
            # closes it only once every mode its record names has passed
            # (_shared/auto-release-outstanding-modes.sh). Checked before
            # spec-proposal and board:stalled: "close it" would erase the
            # open failure, and releasing a board:stalled hold changes
            # nothing while the loop excludes the label anyway. While
            # WING_COMMANDER_AUTO_RELEASE_PAUSED is on auto-release.yml's
            # detect job never runs, so nothing closes it until unpaused.
            what = "fix the release failure; auto-release closes this once every mode it records has passed"
            if _switch_on(switches.get("auto_release_paused")):
                what += " -- but auto-release is paused, so it cannot close this until the pause is lifted"
            owner.append((ref, what, age))
        elif "spec-proposal" in labels:
            owner.append((ref, "promote it with `spec-request`, or close it", age))
        elif "board:stalled" in labels:
            owner.append((ref, "held for a maintainer (`board:stalled`)", age))
        else:
            names = sorted(labels)
            family = "unlabelled"
            if names:
                family = "found-by:*" if names[0].startswith("found-by:") else names[0]
            signals.setdefault(family, []).append(issue["number"])
    return {"owner": owner, "pipeline": pipeline, "signals": signals}


def render(snap):
    rows = classify(snap)
    now = datetime.datetime.strptime(snap["now"], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M UTC")
    switches = snap.get("switches") or {}
    lines = [MARKER, ""]
    roadmap = snap.get("roadmap_number")
    lines.append("Updated {0} by the daily `board-status` job, which rewrites this "
                 "issue in place; edits here are lost.{1}".format(
                     now, " The plan is the Roadmap issue, #{0}.".format(roadmap) if roadmap else ""))
    lines.append("")

    ci = snap.get("main_ci")
    if not ci:
        ci_text = "unknown (no `lint · workflows` run on main found)"
    elif ci.get("status") != "completed":
        ci_text = "running on {0}".format(ci.get("sha", "")[:7])
    elif ci.get("conclusion") == "success":
        ci_text = "green on {0}".format(ci.get("sha", "")[:7])
    else:
        ci_text = "**red** on {0} ([run]({1}))".format(ci.get("sha", "")[:7], ci.get("url", ""))
    release = snap.get("release")
    if release:
        rel_text = "{0}, {1} ago".format(release["tag"], _days(
            datetime.datetime.strptime(snap["now"], "%Y-%m-%dT%H:%M:%SZ"),
            release.get("published_at")))
    else:
        rel_text = "none"

    def state(key, on_text, off_text):
        return on_text if _switch_on(switches.get(key)) else off_text

    lines.append("- **main:** {0}".format(ci_text))
    lines.append("- **last release:** {0}; auto-release {1}".format(
        rel_text, state("auto_release_paused", "**paused**", "on")))
    # The switches as the owner set them, so the line says what the pipeline
    # may do on its own: the board loop's kill switch, its merge switch for
    # fix and Spec Kit bump PRs (constitution X), whether it may push a
    # workflow-file fix at all (docs/setup.md), and the lifecycle merge
    # switch. A paused loop merges nothing whatever its merge switch says.
    lines.append("- **board loop:** {0}; board auto-merge {1}; workflow-file fixes {2}; "
                 "lifecycle auto-merge {3}; backlog lines {4}".format(
                     state("board_loop_paused", "**paused**", "running"),
                     state("board_auto_merge", "on", "off"),
                     state("board_can_push_workflows", "allowed", "held for a maintainer"),
                     state("lifecycle_auto_merge", "on", "off"),
                     state("board_backlog_lines", "on", "off")))
    lines.append("")

    def table(title, header, items):
        lines.append("### {0} ({1})".format(title, len(items)))
        lines.append("")
        if not items:
            lines.append("Nothing.")
        else:
            lines.append("| Item | {0} | Open |".format(header))
            lines.append("|---|---|---|")
            for ref, what, age in items:
                lines.append("| {0} | {1} | {2} |".format(ref, what, age))
        lines.append("")

    table("Waiting on you", "What it needs", rows["owner"])
    table("In the pipeline", "Where it is", rows["pipeline"])

    maint = snap.get("maintenance")
    lines.append("### Maintenance backlog")
    lines.append("")
    if maint:
        lines.append("{0} open, {1} done on #{2}.".format(maint["open"], maint["done"], maint["number"]))
        # specs/121-board-backlog-line-items FR-018: the line the board loop
        # holds, named by the backlog issue and its line id.
        for line in maint.get("current") or []:
            lines.append("")
            lines.append("The board loop is working line `{0}` on #{1}{2}: {3}".format(
                line["id"], maint["number"],
                " ({0})".format(line["detail"]) if line.get("detail") else "", line["text"]))
    else:
        lines.append("No open Maintenance backlog issue.")
    lines.append("")

    signals = rows["signals"]
    total = sum(len(v) for v in signals.values())
    lines.append("### Other open issues ({0})".format(total))
    lines.append("")
    if signals:
        for family in sorted(signals):
            nums = ", ".join("#{0}".format(n) for n in signals[family])
            lines.append("- `{0}`: {1}".format(family, nums))
    else:
        lines.append("None.")
    lines.append("")
    prs = snap.get("prs") or []
    loose = sorted(p["number"] for p in prs if not _spec_label(_labels(p)))
    lines.append("**Open pull requests:** {0}{1}".format(
        len(prs), "; not part of a lifecycle: {0}".format(
            ", ".join("#{0}".format(n) for n in loose)) if loose else ""))
    body = "\n".join(lines) + "\n"
    if snap.get("proof_list"):
        body += "\n" + proof_list_block(snap["proof_list"], body)
    if snap.get("merge_evidence"):
        body += "\n" + merge_evidence_block(snap["merge_evidence"], body)
    return body


# --------------------------------------------------------------------------
# The proof list's section (specs/124-merge-proof-list, contracts/
# proof-list-report.md). wing-commander-proof-list.yml builds the content;
# this file is the only writer. The constants below are the one home of the
# names verify-board-status.py checks against the workflow file.
# --------------------------------------------------------------------------
PROOF_LIST_WORKFLOW = "wing-commander-proof-list.yml"
PROOF_LIST_ARTIFACT = "proof-list-section"
PROOF_LIST_BUILD_STEP = "Build the proof list"
PROOF_LIST_STALE_HOURS = 48
PROOF_LIST_NOTICES = {
    "paused": "The proof list is paused (`WING_COMMANDER_PROOF_LIST_PAUSED`).",
    "failed": "The proof list's latest build did not succeed, or is more than 48 hours old.",
    "never": "The proof list has never been built.",
    "unreadable": "The proof list's build history or artifact could not be read this time.",
}


def _pl_block(status, built, last_good, summary, content, tag="wc-proof-list"):
    return ('<!-- {5}:begin status="{0}" built="{1}" last-good="{2}" -->\n'
            "<details><summary>{3}</summary>\n\n{4}\n</details>\n"
            "<!-- {5}:end -->\n").format(status, built, last_good, summary, content.rstrip("\n"), tag)


def _section_block(pl, body, label, notices, tag):
    """The section for snapshot entry `pl`, placed after `body`: the full form
    if the whole body fits MAX_BODY_UNITS, else names-only, else the failed
    notice. Entries are never dropped for size (FR-020). The one renderer of
    every built-by-another-workflow section (proof list, merge evidence)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    status = pl.get("status", "unreadable")
    last_good = pl.get("last_good_at") or "never"
    used = utf16_len(body) + 1
    notice = None
    if status == "built":
        section = pl.get("section") or {}
        built = section.get("built_at", "none")
        summary = "{0}: built {1} (window 30 days)".format(label, built[:10])
        for key in ("full", "names_only"):
            block = _pl_block("built", built, last_good, summary, section.get(key, ""), tag)
            if used + utf16_len(block) <= MAX_BODY_UNITS:
                return block
        status, notice = "failed", "The {0} was too large for this issue's body.".format(label.lower())
    notice = notice or notices.get(status, notices["unreadable"])
    when = {"never": "there has never been a good build"}.get(
        last_good, "the last good build was {0}".format(last_good))
    if last_good == "unknown":
        when = "the last good build's date is unknown"
    return _pl_block(status, "none", last_good, "{0}: {1}".format(label, status),
                     "{0} {1}.".format(notice, when[0].upper() + when[1:]), tag)


def proof_list_block(pl, body):
    return _section_block(pl, body, "Proof list", PROOF_LIST_NOTICES, "wc-proof-list")


# --------------------------------------------------------------------------
# The merge evidence audit's section (specs/125-merge-evidence-audit,
# contracts/merge-evidence-report.md). wing-commander-merge-evidence.yml
# builds the content; this file only displays it. The artifact name is
# wc_merge_evidence.SECTION_ARTIFACT (its one home); verify-merge-evidence.py
# and verify-board-status.py check these constants against the workflow.
# --------------------------------------------------------------------------
MERGE_EVIDENCE_WORKFLOW = "wing-commander-merge-evidence.yml"
MERGE_EVIDENCE_ARTIFACT = "merge-evidence-section"
MERGE_EVIDENCE_FILE = "merge-evidence-section.json"
MERGE_EVIDENCE_BUILD_STEP = "Build the audit"
# The workflow's `run-name:` for the runs that carry the daily audit job;
# the hourly verdict runs have another title and are not the audit.
MERGE_EVIDENCE_AUDIT_TITLES = ("merge-evidence audit", "merge-evidence dispatch both",
                               "merge-evidence dispatch audit")
MERGE_EVIDENCE_NOTICES = {
    "paused": "The merge evidence audit is paused (`WING_COMMANDER_MERGE_EVIDENCE_PAUSED`).",
    "failed": "The merge evidence audit's latest build did not succeed, or is more than 48 hours old.",
    "never": "The merge evidence audit has never been built.",
    "unreadable": "The merge evidence audit's build history or artifact could not be read this time.",
}


def merge_evidence_block(me, body):
    return _section_block(me, body, "Merge evidence audit", MERGE_EVIDENCE_NOTICES, "wc-merge-evidence")


# --------------------------------------------------------------------------
# Runtime half: read the board, write the issue. Never run by the fixtures.
# --------------------------------------------------------------------------
def _gh(args):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("board-status: gh {0} failed: {1}\n".format(args[1] if len(args) > 1 else "", r.stderr.strip()))
        raise subprocess.CalledProcessError(r.returncode, ["gh"] + args, r.stdout, r.stderr)
    return r.stdout


def _gh_lines(path, jq):
    # `gh --jq` prints a string result raw rather than JSON-encoded, so
    # every program is wrapped in `tojson`: one JSON value per line.
    out = _gh(["api", "--paginate", path, "--jq", "{0} | tojson".format(jq)])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _gh_json(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def current_lines(body):
    """The backlog lines the board loop has claimed (annotation state
    `in-progress`), parsed by board_backlog_lines -- the single home of the
    line grammar (specs/121-board-backlog-line-items FR-018)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_backlog_lines as bbl
    return [{"id": line["id"], "text": line["text"], "detail": line["detail"] or ""}
            for line in bbl.parse_lines(body)
            if not line["checked"] and line["state"] == "in-progress"]


def snapshot(repo, switches):
    item_jq = ('.[] | {number, title, created_at, pull_request: (.pull_request != null), '
               'labels: [.labels[].name], body: (.body // ""), user_type: .user.type, '
               'author: .user.login}')
    items = _gh_lines("repos/{0}/issues?state=open&per_page=100".format(repo), item_jq)
    issues = [i for i in items if not i["pull_request"]]
    prs = [i for i in items if i["pull_request"]]
    maintenance = None
    roadmap = None
    for issue in issues:
        if TRACKING_LABEL not in issue["labels"]:
            continue
        if issue["title"].startswith("Maintenance backlog") and maintenance is None:
            body = issue["body"].splitlines()
            maintenance = {"number": issue["number"],
                           "open": sum(1 for l in body if l.lstrip().startswith("- [ ]")),
                           "done": sum(1 for l in body if l.lstrip().lower().startswith("- [x]")),
                           "current": current_lines(issue["body"])}
        elif issue["title"].startswith("Roadmap") and roadmap is None:
            roadmap = issue["number"]
    for issue in issues:
        if "stage:clarify" in issue["labels"]:
            # Who spoke last among the bot (its questions), a maintainer
            # and the issue's own author (the answers). A passer-by's
            # comment on this public repository answers nothing.
            speakers = _gh_lines("repos/{0}/issues/{1}/comments?per_page=100".format(
                repo, issue["number"]),
                '.[] | select(.user.type == "Bot" or .user.login == "{0}" or '
                '(.author_association | IN("OWNER", "MEMBER", "COLLABORATOR"))) | .user.type'.format(
                    issue.get("author", "")))
            issue["last_comment_by_bot"] = bool(speakers) and speakers[-1] == "Bot"
        issue.pop("body", None)
        issue.pop("author", None)
    # branch=main also matches a fork PR whose head branch is its own main,
    # so the first run on this repository's main that is not a PR run.
    runs = _gh_json("repos/{0}/actions/workflows/{1}/runs?branch=main&per_page=20".format(
        repo, LINT_WORKFLOW)) or {}
    run = next((r for r in runs.get("workflow_runs") or []
                if r.get("event") != "pull_request"
                and (r.get("head_repository") or {}).get("full_name") == repo), None)
    main_ci = None
    if run:
        main_ci = {"status": run.get("status"), "conclusion": run.get("conclusion"),
                   "sha": run.get("head_sha", ""), "url": run.get("html_url", "")}
    rel = _gh_json("repos/{0}/releases/latest".format(repo))
    release = {"tag": rel["tag_name"], "published_at": rel.get("published_at")} if rel else None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"now": now, "issues": issues, "prs": prs, "maintenance": maintenance,
            "roadmap_number": roadmap, "release": release, "main_ci": main_ci,
            "switches": switches, "proof_list": proof_list_snapshot(repo, switches),
            "merge_evidence": merge_evidence_snapshot(repo, switches)}


def _gh_obj(path):
    return json.loads(_gh(["api", path]))


def _build_step_ok(repo, run_id, step_name=None):
    step_name = step_name or PROOF_LIST_BUILD_STEP
    jobs = _gh_obj("repos/{0}/actions/runs/{1}/jobs?per_page=100".format(repo, run_id)).get("jobs") or []
    return any(step.get("name") == step_name and step.get("conclusion") == "success"
               for job in jobs for step in job.get("steps") or [])


def proof_list_snapshot(repo, switches, now=None, gh_obj=None, build_ok=None, download=None):
    """The proof list's section status; see section_snapshot()."""
    return section_snapshot(repo, switches, PROOF_LIST_WORKFLOW, PROOF_LIST_ARTIFACT, "proof_list_paused",
                            now, gh_obj, build_ok or (lambda rid: _build_step_ok(repo, rid)), download)


def merge_evidence_snapshot(repo, switches, now=None, gh_obj=None, build_ok=None, download=None):
    """The merge evidence audit's section status; only the daily audit's runs
    count (the hourly verdict runs never build the section)."""
    return section_snapshot(repo, switches, MERGE_EVIDENCE_WORKFLOW, MERGE_EVIDENCE_ARTIFACT,
                            "merge_evidence_paused", now, gh_obj,
                            build_ok or (lambda rid: _build_step_ok(repo, rid, MERGE_EVIDENCE_BUILD_STEP)),
                            download, titles=MERGE_EVIDENCE_AUDIT_TITLES, filename=MERGE_EVIDENCE_FILE)


# The events a read-only watcher's own runs come from. A pull_request run
# executes the PR's copy of the workflow (a fork's, with a head branch it
# can name `main`), so its artifacts are never this repository's output.
TRUSTED_RUN_EVENTS = ("schedule", "workflow_dispatch")
# section_snapshot reads up to this many pages of 100 completed runs looking
# for the latest good build: the merge evidence workflow has ~25 runs a day.
SECTION_RUN_PAGES = 3


def trusted_watcher_run(run, repo):
    """The one home of "this run is the repository's own scheduled or
    dispatched run" (the section readers here and
    wc_merge_evidence.download_ledger): its event is a schedule or a
    dispatch and its head repository is `repo`, never a fork."""
    return ((run or {}).get("event") in TRUSTED_RUN_EVENTS
            and ((run or {}).get("head_repository") or {}).get("full_name") == repo)


def section_snapshot(repo, switches, workflow, artifact, switch_key, now, gh_obj, build_ok, download,
                     titles=None, filename="proof-list-section.json"):
    """The section's status (research D17): paused, never, failed, built or
    unreadable, plus the last good build's time. The readers are parameters so
    verify-board-status.py drives every branch."""
    gh_obj = gh_obj or _gh_obj
    now = now or datetime.datetime.now(datetime.timezone.utc)
    paused = _switch_on(switches.get(switch_key))
    last_good = "unknown"
    try:
        default = gh_obj("repos/{0}".format(repo))["default_branch"]
        # Pages of 100 until the latest good build is found (a page-count
        # bound, not a run count of one day: #1173 review R3).
        runs, found, good_ok = [], "never", {}
        for page in range(1, SECTION_RUN_PAGES + 1):
            try:
                batch = gh_obj("repos/{0}/actions/workflows/{1}/runs?status=completed&branch={2}"
                               "&per_page=100&page={3}".format(repo, workflow, default, page)).get("workflow_runs") or []
            except subprocess.CalledProcessError as exc:
                if "HTTP 404" not in (exc.stderr or ""):
                    raise
                batch = []
            for run in batch:
                if not trusted_watcher_run(run, repo) or (titles is not None and run.get("display_title") not in titles):
                    continue
                runs.append(run)
                if found == "never":
                    good_ok[run["id"]] = build_ok(run["id"]) if run.get("conclusion") == "success" else False
                    if good_ok[run["id"]]:
                        found = run.get("run_started_at") or run.get("created_at") or "unknown"
            if found != "never" or len(batch) < 100:
                break
        # Set only once the history was read: a failed read leaves "unknown".
        last_good = found
        if paused:
            return {"status": "paused", "last_good_at": last_good}
        if not runs:
            return {"status": "never", "last_good_at": "never"}
        latest = runs[0]
        if latest.get("conclusion") != "success":
            return {"status": "failed", "last_good_at": last_good}
        started = datetime.datetime.strptime((latest.get("run_started_at") or "")[:19], "%Y-%m-%dT%H:%M:%S")
        if (now.replace(tzinfo=None) - started) > datetime.timedelta(hours=PROOF_LIST_STALE_HOURS):
            return {"status": "failed", "last_good_at": last_good}
        if not good_ok.get(latest["id"]):
            return {"status": "paused", "last_good_at": last_good}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                if download:
                    download(repo, latest["id"], tmp)
                else:
                    _download_section(repo, latest["id"], tmp, artifact)
                with open(os.path.join(tmp, filename), encoding="utf-8") as fh:
                    section = json.load(fh)
            if section.get("schema") != 1 or not section.get("full") or not section.get("names_only"):
                raise ValueError("malformed section")
        except (OSError, ValueError, TypeError, AttributeError, subprocess.CalledProcessError):
            return {"status": "unreadable", "last_good_at": last_good}
        return {"status": "built", "last_good_at": last_good, "section": section}
    except (subprocess.CalledProcessError, ValueError, KeyError, OSError, TypeError, AttributeError):
        return {"status": "paused" if paused else "unreadable", "last_good_at": last_good}


def _download_section(repo, run_id, directory, artifact=PROOF_LIST_ARTIFACT):
    _gh(["run", "download", str(run_id), "-R", repo, "-n", artifact, "-D", directory])


def publish(repo, body):
    mine = _gh_lines("repos/{0}/issues?state=open&labels={1}&per_page=100".format(
        repo, TRACKING_LABEL),
        '.[] | select(.user.type == "Bot" and .title == "{0}") | select((.body // "") | contains("{1}")) | .number'.format(
            TITLE, MARKER))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        if mine:
            json.dump({"body": body}, fh)
            path = "repos/{0}/issues/{1}".format(repo, min(mine))
            method = "PATCH"
        else:
            json.dump({"title": TITLE, "body": body, "labels": [TRACKING_LABEL]}, fh)
            path = "repos/{0}/issues".format(repo)
            method = "POST"
        payload = fh.name
    _gh(["api", "-X", method, path, "--input", payload])
    return path


# Each switch and the env name board-status.yml passes it under; the
# repository variable is that name prefixed with WING_COMMANDER_. The one
# home of this mapping: the whats-on-me skill's board_now.py reads it too.
SWITCH_ENV = {
    "auto_release_paused": "AUTO_RELEASE_PAUSED",
    "board_auto_merge": "BOARD_AUTO_MERGE",
    "board_backlog_lines": "BOARD_BACKLOG_LINES",
    "board_can_push_workflows": "BOARD_CAN_PUSH_WORKFLOWS",
    "board_loop_paused": "BOARD_LOOP_PAUSED",
    "lifecycle_auto_merge": "LIFECYCLE_AUTO_MERGE",
    "merge_evidence_paused": "MERGE_EVIDENCE_PAUSED",
    "proof_list_paused": "PROOF_LIST_PAUSED",
    "review_gate_paused": "LIFECYCLE_REVIEW_GATE_PAUSED",
    "tasks_review": "TASKS_REVIEW",
}


def switches_from(get):
    """The switches dict snapshot() takes, with get(env_name) -> raw value."""
    switches = {key: get(env) or "" for key, env in SWITCH_ENV.items()}
    switches["tasks_review"] = switches["tasks_review"].strip().lower()
    return switches


def main(argv):
    if len(argv) >= 3 and argv[1] == "render":
        with open(argv[2], encoding="utf-8") as fh:
            sys.stdout.write(render(json.load(fh)))
        return 0
    if len(argv) == 2 and argv[1] == "publish":
        repo = os.environ["GITHUB_REPOSITORY"]
        body = render(snapshot(repo, switches_from(lambda env: os.environ.get(env, ""))))
        target = publish(repo, body)
        print("board-status: wrote {0}".format(target))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(body)
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
