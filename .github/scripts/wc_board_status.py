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
    """The wing-commander-watch-guard composite's pause test: "true" in any
    case, padding stripped. Board status reads a switch through
    switch_set(), which uses this only for the switches that guard reads."""
    return str(value or "").strip().lower() == "true"


# How each switch's own reader turns its value into on or off, so the status
# says what the pipeline will do (#889; owner decision 2026-11-27, on the
# Roadmap issue: mirror each switch's real reader). verify-board-status.py
# ties every entry to the reader it names and drives a fixture per switch.
#   exact       only the exact text "true": board-loop.yml's merge decision
#               (jq `$switch_on == "true"`) and board_backlog_lines.
#               selection_gate (`!= "true"`)
#   expression  "true" in any case, padding kept: a workflow's
#               `vars.WING_COMMANDER_* == 'true'` (or `!= 'true'`), which
#               GitHub compares case-insensitively and never trims
#   guard       _switch_on, the watch-guard composite's own test
SWITCH_READERS = {
    "auto_release_paused": "expression",
    "board_auto_merge": "exact",
    "board_backlog_lines": "exact",
    "board_can_push_workflows": "expression",
    "board_loop_paused": "expression",
    "lifecycle_auto_merge": "expression",
    "feature_health_paused": "guard",
    "merge_evidence_paused": "guard",
    "proof_list_paused": "guard",
    "review_gate_paused": "expression",
}
_READS = {
    "exact": lambda value: str(value or "") == "true",
    "expression": lambda value: str(value or "").lower() == "true",
    "guard": _switch_on,
}


def switch_set(switches, key):
    """Whether switch `key` is on, read the way its own reader reads it."""
    return _READS[SWITCH_READERS[key]]((switches or {}).get(key))


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
        gate_merges = (switch_set(switches, "lifecycle_auto_merge")
                       and not switch_set(switches, "review_gate_paused"))
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
            if switch_set(switches, "auto_release_paused"):
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
        return on_text if switch_set(switches, key) else off_text

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
        body = append_section(body, proof_list_block(snap["proof_list"], body))
    if snap.get("merge_evidence"):
        body = append_section(body, merge_evidence_block(snap["merge_evidence"], body))
    if snap.get("feature_health"):
        body = append_section(body, feature_health_block(snap["feature_health"], body))
    return body


def append_section(body, block):
    """`body` with section `block` after it: the one place render joins a
    section on, so the fit checks measure exactly this string. An empty block
    (a section left out for size) adds nothing, not even the separator."""
    return body + "\n" + block if block else body


def _scripts_on_path():
    """Put this directory on sys.path once, however often a reader that
    imports a sibling module runs (#889)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def section_fits(body, block):
    """True when append_section(body, block) stays within MAX_BODY_UNITS."""
    _scripts_on_path()
    import board_spec_request_body as bsrb
    return bsrb.utf16_len(append_section(body, block)) <= bsrb.MAX_BODY_UNITS


def _fitting_or_left_out(body, block, what):
    """`block` when it fits after `body`, else "" with a log line: leaving the
    section out beats pushing the whole body past the limit and failing the
    publish."""
    if section_fits(body, block):
        return block
    print("board-status: the {0} section was left out; the body has no room even for its notice".format(what),
          file=sys.stderr)
    return ""


# --------------------------------------------------------------------------
# The proof list's section (specs/124-merge-proof-list, contracts/
# proof-list-report.md). wing-commander-proof-list.yml builds the content;
# this file is the only writer. The constants below are the one home of the
# names verify-board-status.py checks against the workflow file.
# --------------------------------------------------------------------------
PROOF_LIST_WORKFLOW = "wing-commander-proof-list.yml"
PROOF_LIST_ARTIFACT = "proof-list-section"
# The file inside that artifact: wc_proof_list.SECTION_FILE is this constant,
# and verify-proof-list.py checks the workflow's `--out` and `path:` (#889).
PROOF_LIST_FILE = "proof-list-section.json"
PROOF_LIST_BUILD_STEP = "Build the proof list"
PROOF_LIST_STALE_HOURS = 48
PROOF_LIST_NOTICES = {
    "paused": "The proof list is paused (`WING_COMMANDER_PROOF_LIST_PAUSED`).",
    "failed": "The proof list's latest build did not succeed, or is more than 48 hours old.",
    "never": "The proof list has never been built.",
    "unreadable": "The proof list's build history or artifact could not be read this time.",
}


# The feature-health section (specs/126-feature-health, contracts/
# feature-health-report.md). wing-commander-feature-health.yml builds the
# content; this file is the only writer.
FEATURE_HEALTH_WORKFLOW = "wing-commander-feature-health.yml"
FEATURE_HEALTH_ARTIFACT = "feature-health-section"
FEATURE_HEALTH_BUILD_STEP = "Build the feature health section"
FEATURE_HEALTH_STALE_HOURS = 48
FEATURE_HEALTH_MARKER = "<!-- wing-commander-feature-health -->"
FEATURE_HEALTH_MARKER_END = "<!-- /wing-commander-feature-health -->"
FEATURE_HEALTH_NOTICES = {
    "paused": "Feature health is paused (`WING_COMMANDER_FEATURE_HEALTH_PAUSED`).",
    "failed": "Feature health's latest build failed.",
    "never": "Feature health is not yet built.",
    "unreadable": "Feature health: could not read the latest build.",
}


def feature_health_block(fhs, body):
    """The section for snapshot entry `fhs`, placed after `body`. The table is
    dropped (call-outs kept) when the whole section would not fit."""
    status = fhs.get("status", "unreadable")
    last_good = (fhs.get("last_good_at") or "never")[:10]
    if status in ("built", "stale"):
        text = fhs["section"].rstrip("\n")
        stale = ""
        if status == "stale":
            stale = "\n\n_Stale: this build is from {0}, more than {1} hours old._".format(
                (fhs.get("built_at") or "an unknown date")[:10], FEATURE_HEALTH_STALE_HOURS)
        for candidate in (text, shorten_feature_health(text)):
            # The stale line goes inside the end marker so a consumer replacing
            # the marker-delimited block takes it along.
            block = _with_stale(candidate, stale) + "\n"
            if section_fits(body, block):
                return block
        block = "{0}\nFeature health's section was too large for this issue's body. The last good build was {1}.\n{2}\n".format(
            FEATURE_HEALTH_MARKER, last_good, FEATURE_HEALTH_MARKER_END)
        return _fitting_or_left_out(body, block, "feature-health")
    notice = FEATURE_HEALTH_NOTICES.get(status, FEATURE_HEALTH_NOTICES["unreadable"])
    if status != "never":
        notice += " The last good build was {0}.".format(last_good)
    return _fitting_or_left_out(
        body, "{0}\n{1}\n{2}\n".format(FEATURE_HEALTH_MARKER, notice, FEATURE_HEALTH_MARKER_END), "feature-health")


def _with_stale(text, stale):
    """`text` (a marker-delimited section) with `stale` placed before its end marker."""
    text = text.rstrip("\n")
    if not stale:
        return text
    if text.endswith(FEATURE_HEALTH_MARKER_END):
        return text[:-len(FEATURE_HEALTH_MARKER_END)].rstrip("\n") + stale + "\n" + FEATURE_HEALTH_MARKER_END
    return text + stale


def shorten_feature_health(text):
    """Drop the table, keep the call-outs (over-size body, research D8). The one
    home; wc_feature_health.shorten_section is this function. Text with no
    table is returned as it is, end marker included."""
    if "<details>" not in text:
        return text.rstrip("\n")
    head, _sep, tail = text.partition("<details>")
    end = tail.partition("</details>")[2]
    short = (head.rstrip("\n") + "\n\n_Table shortened: it did not fit this issue's body._\n"
             + end.lstrip("\n")).rstrip("\n")
    # An unterminated <details> takes the rest of the text with it, end marker
    # included; put the marker back so the next build reads a closed section.
    if FEATURE_HEALTH_MARKER_END in text and not short.endswith(FEATURE_HEALTH_MARKER_END):
        short += "\n" + FEATURE_HEALTH_MARKER_END
    return short


def _pl_block(status, built, last_good, summary, content, tag="wc-proof-list"):
    return ('<!-- {5}:begin status="{0}" built="{1}" last-good="{2}" -->\n'
            "<details><summary>{3}</summary>\n\n{4}\n</details>\n"
            "<!-- {5}:end -->\n").format(status, built, last_good, summary, content.rstrip("\n"), tag)


def _section_block(pl, body, label, notices, tag):
    """The section for snapshot entry `pl`, placed after `body`: the full form
    if the whole body fits MAX_BODY_UNITS, else names-only, else the failed
    notice, else nothing (logged; as feature_health_block). Entries are never
    dropped for size (FR-020). The one renderer of
    every built-by-another-workflow section (proof list, merge evidence)."""
    status = pl.get("status", "unreadable")
    last_good = pl.get("last_good_at") or "never"
    notice = None
    if status == "built":
        section = pl.get("section") or {}
        built = section.get("built_at", "none")
        summary = "{0}: built {1} (window 30 days)".format(label, built[:10])
        for key in ("full", "names_only"):
            block = _pl_block("built", built, last_good, summary, section.get(key, ""), tag)
            if section_fits(body, block):
                return block
        status, notice = "failed", "The {0} was too large for this issue's body.".format(label.lower())
    notice = notice or notices.get(status, notices["unreadable"])
    when = {"never": "there has never been a good build"}.get(
        last_good, "the last good build was {0}".format(last_good))
    if last_good == "unknown":
        when = "the last good build's date is unknown"
    return _fitting_or_left_out(
        body, _pl_block(status, "none", last_good, "{0}: {1}".format(label, status),
                        "{0} {1}.".format(notice, when[0].upper() + when[1:]), tag), label.lower())


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
    _scripts_on_path()
    import board_backlog_lines as bbl
    return [{"id": line["id"], "text": line["text"], "detail": line["detail"] or ""}
            for line in bbl.parse_lines(body)
            if not line["checked"] and line["state"] == "in-progress"]


def snapshot(repo, switches):
    item_jq = ('.[] | {number, title, created_at, pull_request: (.pull_request != null), '
               'labels: [.labels[].name], body: (.body // ""), user_type: .user.type}')
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
            # Who spoke last between the bot (its questions) and a
            # maintainer (the answers; spec 134: clarify acts on a maintainer's
            # reply only). Anyone else's comment answers nothing.
            speakers = _gh_lines("repos/{0}/issues/{1}/comments?per_page=100".format(
                repo, issue["number"]),
                '.[] | select(.user.type == "Bot" or '
                '(.author_association | IN("OWNER", "MEMBER", "COLLABORATOR"))) | .user.type')
            issue["last_comment_by_bot"] = bool(speakers) and speakers[-1] == "Bot"
        issue.pop("body", None)
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
            "merge_evidence": merge_evidence_snapshot(repo, switches),
            "feature_health": feature_health_snapshot(repo, switches)}


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
# section_snapshot pages 100 completed runs at a time looking for the latest
# good build, and stops at the end of the history, once a page's runs are all
# older than SECTION_LOOKBACK_DAYS, or at SECTION_RUN_PAGES pages (the merge
# evidence workflow has ~25 runs a day). Stopping early is said as "not found
# within ...", never as "never" (#1173 round 5, finding 8).
SECTION_RUN_PAGES = 10
SECTION_LOOKBACK_DAYS = 31


def trusted_watcher_run(run, repo):
    """The one home of "this run is the repository's own scheduled or
    dispatched run" (the section readers here and
    wc_merge_evidence.download_ledger): its event is a schedule or a
    dispatch and its head repository is `repo`, never a fork."""
    return ((run or {}).get("event") in TRUSTED_RUN_EVENTS
            and ((run or {}).get("head_repository") or {}).get("full_name") == repo)


def section_snapshot(repo, switches, workflow, artifact, switch_key, now, gh_obj, build_ok, download,
                     titles=None, filename=PROOF_LIST_FILE, stale_hours=PROOF_LIST_STALE_HOURS,
                     load=None, stale_keeps_section=False):
    """The section's status (research D17): paused, never, failed, built or
    unreadable, plus the last good build's time. The readers are parameters so
    verify-board-status.py drives every branch. `load` (default: the JSON
    section's reader) and `stale_keeps_section` serve feature health."""
    gh_obj = gh_obj or _gh_obj
    now = now or datetime.datetime.now(datetime.timezone.utc)
    paused = switch_set(switches, switch_key)
    last_good = "unknown"
    try:
        default = gh_obj("repos/{0}".format(repo))["default_branch"]
        # Pages of 100 until the latest good build is found (a page-count
        # bound, not a run count of one day: #1173 review R3).
        runs, found, good_ok, cut_short = [], "never", {}, None
        oldest_kept = (now.replace(tzinfo=None) - datetime.timedelta(days=SECTION_LOOKBACK_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%S")
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
            if max((r.get("run_started_at") or r.get("created_at") or "")[:19] for r in batch) < oldest_kept:
                cut_short = "not found in the last {0} days".format(SECTION_LOOKBACK_DAYS)
                break
            if page == SECTION_RUN_PAGES:
                cut_short = "not found within the newest {0} runs".format(SECTION_RUN_PAGES * 100)
        if found == "never" and cut_short:
            found = cut_short
        # Set only once the history was read: a failed read leaves "unknown".
        last_good = found
        if paused:
            return {"status": "paused", "last_good_at": last_good}
        if not runs:
            # No audit within the bound is not "never built": older runs exist.
            return {"status": "failed", "last_good_at": cut_short} if cut_short else \
                {"status": "never", "last_good_at": "never"}
        latest = runs[0]
        if latest.get("conclusion") != "success":
            return {"status": "failed", "last_good_at": last_good}
        started = datetime.datetime.strptime((latest.get("run_started_at") or "")[:19], "%Y-%m-%dT%H:%M:%S")
        stale = (now.replace(tzinfo=None) - started) > datetime.timedelta(hours=stale_hours)
        if stale and not stale_keeps_section:
            return {"status": "failed", "last_good_at": last_good}
        if not good_ok.get(latest["id"]):
            return {"status": "paused", "last_good_at": last_good}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                if download:
                    download(repo, latest["id"], tmp)
                else:
                    _download_section(repo, latest["id"], tmp, artifact)
                if load:
                    section = load(tmp)
                else:
                    with open(os.path.join(tmp, filename), encoding="utf-8") as fh:
                        section = json.load(fh)
                    # A non-string here would make render() raise and stop the
                    # whole Board status rewrite, so it is unreadable instead.
                    if section.get("schema") != 1 or not all(
                            isinstance(section.get(key), str) and section.get(key)
                            for key in ("full", "names_only", "built_at")):
                        raise ValueError("malformed section")
        except (OSError, ValueError, TypeError, AttributeError, subprocess.CalledProcessError):
            return {"status": "unreadable", "last_good_at": last_good}
        snap = {"status": "stale" if stale else "built", "last_good_at": last_good, "section": section}
        if stale_keeps_section:
            snap["built_at"] = latest.get("run_started_at")
        return snap
    except (subprocess.CalledProcessError, ValueError, KeyError, OSError, TypeError, AttributeError):
        return {"status": "paused" if paused else "unreadable", "last_good_at": last_good}


def _download_section(repo, run_id, directory, artifact=PROOF_LIST_ARTIFACT):
    _gh(["run", "download", str(run_id), "-R", repo, "-n", artifact, "-D", directory])


def feature_health_snapshot(repo, switches, now=None, gh_obj=None, build_ok=None, download=None):
    """The feature-health section's status: built, paused, failed, never,
    unreadable, or stale (older than 48h; the content is kept), plus the last
    good build (contracts/feature-health-report.md "Writer statuses")."""
    def load(directory):
        with open(os.path.join(directory, FEATURE_HEALTH_ARTIFACT + ".md"), encoding="utf-8") as fh:
            text = fh.read()
        if FEATURE_HEALTH_MARKER not in text or "Feature health" not in text:
            raise ValueError("malformed section")
        return text
    return section_snapshot(repo, switches, FEATURE_HEALTH_WORKFLOW, FEATURE_HEALTH_ARTIFACT,
                            "feature_health_paused", now, gh_obj,
                            build_ok or (lambda rid: _build_step_ok(repo, rid, FEATURE_HEALTH_BUILD_STEP)),
                            download, stale_hours=FEATURE_HEALTH_STALE_HOURS, load=load,
                            stale_keeps_section=True)


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
    "feature_health_paused": "FEATURE_HEALTH_PAUSED",
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
