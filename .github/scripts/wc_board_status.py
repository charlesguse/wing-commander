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
        elif "spec-proposal" in labels:
            owner.append((ref, "promote it with `spec-request`, or close it", age))
        elif "board:stalled" in labels:
            owner.append((ref, "held for a maintainer (`board:stalled`)", age))
        elif "auto-release:failed" in labels:
            # The board loop never acts on it (board_eligibility.
            # SELF_MANAGED_LABELS), so nothing but the owner fixes its cause.
            owner.append((ref, "fix the release failure; auto-release closes this after a pass in that mode", age))
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
    lines.append("- **board loop:** {0}; lifecycle auto-merge {1}".format(
        state("board_loop_paused", "**paused**", "running"),
        state("lifecycle_auto_merge", "on", "off")))
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
    return "\n".join(lines) + "\n"


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
                           "done": sum(1 for l in body if l.lstrip().lower().startswith("- [x]"))}
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
            "switches": switches}


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


def main(argv):
    if len(argv) >= 3 and argv[1] == "render":
        with open(argv[2], encoding="utf-8") as fh:
            sys.stdout.write(render(json.load(fh)))
        return 0
    if len(argv) == 2 and argv[1] == "publish":
        repo = os.environ["GITHUB_REPOSITORY"]
        switches = {
            "auto_release_paused": os.environ.get("AUTO_RELEASE_PAUSED", ""),
            "board_loop_paused": os.environ.get("BOARD_LOOP_PAUSED", ""),
            "lifecycle_auto_merge": os.environ.get("LIFECYCLE_AUTO_MERGE", ""),
            "review_gate_paused": os.environ.get("LIFECYCLE_REVIEW_GATE_PAUSED", ""),
            "tasks_review": os.environ.get("TASKS_REVIEW", "").strip().lower(),
        }
        body = render(snapshot(repo, switches))
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
