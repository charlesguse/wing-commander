#!/usr/bin/env python3
"""The daily board status renders the board it read, and publishes to one
issue (wc_board_status.py, board-status.yml).

Two halves, both driven for real:

  render   classify()/render() against an inline board snapshot: every
           "waiting on" branch, the hidden tracking issues, the signal
           grouping, the switches and main's CI line, and an agent-written
           title that tries to break out of its code span.
  runtime  snapshot() and publish() against a `gh` stub on PATH that serves
           canned API pages through real `jq -r`, the way `gh --jq` prints.
           The shipped jq programs run, never a pre-filtered copy, and the
           publish call is checked to edit the existing status issue rather
           than open a second one.
"""
import json
import os
import re
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_board_status as bs  # noqa: E402
import board_eligibility as be  # noqa: E402

failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-board-status: {0} -- {1}".format(name, detail))


def issue(number, labels, title="t", created="2026-09-28T00:00:00Z", **extra):
    d = {"number": number, "title": title, "labels": labels, "created_at": created}
    d.update(extra)
    return d


SNAP = {
    "now": "2026-10-01T07:17:00Z",
    "roadmap_number": 890,
    "issues": [
        issue(889, ["disposition:tracking"], "Maintenance backlog"),
        issue(890, ["disposition:tracking"], "Roadmap"),
        issue(903, ["spec-proposal"], "Board loop merges its own fix-class PRs", "2026-10-01T02:45:00Z"),
        issue(560, ["spec-request", "stage:review", "rebase:blocked", "spec:074-serialized-fold-dispatch"]),
        issue(675, ["spec-request", "stage:review", "spec:090-stage-write-boundary"]),
        issue(737, ["spec-request", "stage:spec", "spec:095-agent-code-credential-containment"]),
        issue(739, ["spec-request", "stage:spec", "spec:096-no-pr-yet"]),
        issue(741, ["spec-request", "stage:clarify", "spec:098-a"], last_comment_by_bot=True),
        issue(742, ["spec-request", "stage:clarify", "spec:098-b"], last_comment_by_bot=False),
        issue(750, ["spec-request", "stage:implement", "spec:099-name-free-stage-identity"]),
        issue(717, ["spec-request", "stage:stalled", "spec:093-not-ready-board-release"]),
        issue(724, ["spec-request", "stage:review", "stage:stalled", "spec:097-recorded-stop-point"]),
        issue(723, ["spec-request", "stage:spec", "stage:implement", "spec:096-durable-prove-entry"]),
        issue(760, ["spec-request", "stage:tasks", "spec:101-read-only-gh-grants"]),
        issue(780, ["board:stalled"], "held fix"),
        issue(979, ["auto-release:failed"], "auto-release failed"),
        issue(902, ["found-by:implement"]),
        issue(911, ["found-by:finalize"]),
        issue(905, ["usage-limit"]),
        issue(912, []),
    ],
    "prs": [
        {"number": 821, "labels": ["spec-request", "stage:review", "spec:074-serialized-fold-dispatch"]},
        {"number": 836, "labels": ["spec-request", "stage:review", "spec:090-stage-write-boundary"]},
        {"number": 738, "labels": ["spec-request", "stage:clarify", "spec:095-agent-code-credential-containment"]},
        {"number": 909, "labels": []},
        {"number": 899, "labels": ["spec-request", "stage:review", "spec:097-recorded-stop-point"]},
        {"number": 761, "labels": ["spec-request", "stage:tasks", "spec:101-read-only-gh-grants"]},
    ],
    "maintenance": {"number": 889, "open": 30, "done": 1},
    "release": {"tag": "v2.7.3", "published_at": "2026-09-16T00:00:00Z"},
    "main_ci": {"status": "completed", "conclusion": "failure", "sha": "b554d1860eb2", "url": "https://example.invalid/run/1"},
    "switches": {"auto_release_paused": "true", "board_loop_paused": "", "lifecycle_auto_merge": "", "review_gate_paused": ""},
}


def rows_by_number(rows):
    out = {}
    for ref, what, age in rows:
        out[int(ref.split()[0].lstrip("#"))] = (ref, what, age)
    return out


def render_half():
    rows = bs.classify(SNAP)
    owner = rows_by_number(rows["owner"])
    pipeline = rows_by_number(rows["pipeline"])
    check("tracking issues are never listed", 889 not in owner and 889 not in pipeline and 890 not in owner)
    check("a spec-proposal waits on the owner", 903 in owner and "spec-request" in owner[903][1], owner.get(903))
    check("a final PR waits on the owner while lifecycle auto-merge is off, naming the PR",
          675 in owner and "#836" in owner[675][1], owner.get(675))
    check("rebase:blocked always waits on the owner and says so",
          560 in owner and "rebase blocked" in owner[560][1], owner.get(560))
    check("a spec stage with its PR open waits on the owner", 737 in owner and "#738" in owner[737][1], owner.get(737))
    check("a spec stage with no PR yet is the pipeline drafting", 739 in pipeline, pipeline.get(739))
    check("clarify whose last comment is the bot's waits on the owner", 741 in owner, owner.get(741))
    check("clarify whose last comment is a person's is the pipeline", 742 in pipeline, pipeline.get(742))
    check("implement is the pipeline", 750 in pipeline, pipeline.get(750))
    check("stage:stalled waits on the owner", 717 in owner, owner.get(717))
    check("stage:stalled beside a leftover stage:review is stalled, not a final PR to merge",
          724 in owner and "stalled" in owner[724][1], owner.get(724))
    check("two leftover stage labels read as the furthest one", 723 in pipeline
          and pipeline[723][1] == "implement", pipeline.get(723))
    check("a tasks PR in auto review mode is the pipeline's", 760 in pipeline, pipeline.get(760))
    check("a board:stalled hold waits on the owner", 780 in owner, owner.get(780))
    check("an auto-release failure waits on the owner (the board loop never acts on it)",
          979 in owner and "auto-release:failed" not in rows["signals"], owner.get(979))
    # #977: report closes the issue only when nothing stays outstanding --
    # a pass in one mode leaves a later-appended other-mode failure open.
    check("the auto-release wait says every recorded mode must pass, not just one",
          979 in owner and "every mode" in owner[979][1] and "that mode" not in owner[979][1], owner.get(979))
    # "the board loop never acts on it" holds only while the label is in
    # board_eligibility.SELF_MANAGED_LABELS, the loop's one exclusion home.
    check("the owner-only auto-release label is one the board loop excludes",
          bs.AUTO_RELEASE_FAILED_LABEL in be.SELF_MANAGED_LABELS
          and be.is_excluded({"state": "open", "labels": [{"name": bs.AUTO_RELEASE_FAILED_LABEL}]})[0],
          be.SELF_MANAGED_LABELS)
    # auto-release.yml's detect job is skipped while the pause switch is on
    # (SNAP has it on), so the row must not promise a self-close then.
    check("a paused auto-release is named on the auto-release wait",
          "auto-release is paused" in owner[979][1], owner[979][1])
    running = rows_by_number(bs.classify(dict(SNAP, switches=dict(SNAP["switches"], auto_release_paused="")))["owner"])
    check("an unpaused auto-release wait does not mention a pause",
          "paused" not in running[979][1], running[979][1])
    # The auto-release row outranks spec-proposal ("close it" would erase
    # the open failure) and board:stalled (the loop excludes it either way).
    mixed = rows_by_number(bs.classify(dict(SNAP, issues=[
        issue(985, ["auto-release:failed", "spec-proposal"]),
        issue(986, ["auto-release:failed", "board:stalled"]),
    ]))["owner"])
    for n in (985, 986):
        check("an auto-release failure with another owner label gets the auto-release wait (#{0})".format(n),
              n in mixed and mixed[n][1].startswith("fix the release failure"), mixed.get(n))
    check("a lifecycle row names its spec number", owner[675][0] == "#675 spec 090", owner[675][0])
    sig = rows["signals"]
    check("found-by:* issues group together", sig.get("found-by:*") == [902, 911], sig)
    check("an unlabelled issue is listed, not dropped", sig.get("unlabelled") == [912], sig)
    check("usage-limit is its own group", sig.get("usage-limit") == [905], sig)

    on = dict(SNAP, switches=dict(SNAP["switches"], lifecycle_auto_merge="true"))
    owner_on = rows_by_number(bs.classify(on)["owner"])
    pipe_on = rows_by_number(bs.classify(on)["pipeline"])
    check("with lifecycle auto-merge on, a final PR is the review gate's", 675 in pipe_on and 675 not in owner_on)
    check("rebase:blocked waits on the owner even when the review gate would merge",
          560 in owner_on and "rebase blocked" in owner_on[560][1], owner_on.get(560))
    check("a stalled issue stays the owner's when the review gate would merge", 724 in owner_on, owner_on.get(724))
    pr_mode = rows_by_number(bs.classify(dict(SNAP, switches=dict(SNAP["switches"], tasks_review="pr")))["owner"])
    check("a tasks PR in pr review mode waits on the owner, naming the PR",
          760 in pr_mode and "#761" in pr_mode[760][1], pr_mode.get(760))
    paused = dict(SNAP, switches=dict(on["switches"], review_gate_paused="true"))
    check("a paused review gate hands the final PR back to the owner",
          675 in rows_by_number(bs.classify(paused)["owner"]))

    body = bs.render(SNAP)
    check("the body starts with the marker publish() looks for", body.startswith(bs.MARKER), body[:80])
    check("main's red CI is bold and links the run",
          "**red** on b554d18 ([run](https://example.invalid/run/1))" in body, body)
    check("the release line names the tag, its age and the paused switch",
          "v2.7.3, 15d ago; auto-release **paused**" in body, body)
    check("the maintenance count is shown", "30 open, 1 done on #889." in body, body)
    check("no current line is named while the loop holds none (specs/121 FR-018)",
          "is working line" not in body, body)
    held = bs.render(dict(SNAP, maintenance=dict(SNAP["maintenance"], current=[
        {"id": "bl-0a1b2c3d", "text": "flaky gate", "detail": "PR #7"}])))
    check("the line the board loop holds is named by backlog issue and line id (specs/121 FR-018)",
          "The board loop is working line `bl-0a1b2c3d` on #889 (PR #7): flaky gate" in held, held)
    check("the waiting-on-you count is in its heading", "### Waiting on you (9)" in body, body)
    check("PRs outside any lifecycle are named", "not part of a lifecycle: #909" in body, body)
    check("the roadmap is linked", "Roadmap issue, #890" in body, body)
    check("the board loop line names every merge switch, all off by default",
          "- **board loop:** running; board auto-merge off; workflow-file fixes held for a maintainer; "
          "lifecycle auto-merge off" in body, body)
    check("the board loop line shows the backlog-lines switch, off by default (specs/121 FR-023)",
          "lifecycle auto-merge off; backlog lines off" in body, body)
    merging = bs.render(dict(SNAP, switches=dict(SNAP["switches"], board_auto_merge="true",
                                                  board_can_push_workflows="true")))
    check("board auto-merge and workflow-file fixes read on when their switches are true",
          "board auto-merge on; workflow-file fixes allowed; lifecycle auto-merge off" in merging, merging)
    green = bs.render(dict(SNAP, main_ci={"status": "completed", "conclusion": "success", "sha": "abc1234ffff"}))
    check("green CI renders plainly", "- **main:** green on abc1234" in green, green)

    hostile = dict(SNAP, issues=[issue(1, ["spec-proposal"], "x `y` | z @someone <!-- wing-commander-board-status -->")], prs=[])
    hb = bs.render(hostile)
    row = [l for l in hb.splitlines() if l.startswith("| #1 ")]
    cell = row[0].split(" | ")[0] if row else ""
    check("an agent-written title stays in one code span: no backtick or pipe inside, marker defused",
          row and cell.count("`") == 2 and "|" not in cell[2:] and hb.count(bs.MARKER) == 1, row)


STUB = r"""#!/usr/bin/env bash
# gh stub: `gh api [--paginate] [-X M] PATH [--jq PROG] [--input FILE]`.
# A page file holds {"pages": [...]}: with --paginate each page is served in
# turn, as gh does; without it only the first, so a dropped --paginate
# loses whatever the later pages hold.
dir="$(dirname "$0")"
method=GET; path=""; prog=""; input=""; paginate=0
while [ $# -gt 0 ]; do
  case "$1" in
    api) ;;
    --paginate) paginate=1 ;;
    -X) method="$2"; shift ;;
    --jq) prog="$2"; shift ;;
    --input) input="$2"; shift ;;
    *) path="$1" ;;
  esac
  shift
done
if [ "$method" != GET ]; then
  printf '%s %s\n' "$method" "$path" >> "$dir/writes.log"
  cp "$input" "$dir/payload-$(wc -l < "$dir/writes.log" | tr -d ' ').json"
  echo '{}'
  exit 0
fi
key="$(printf '%s' "$path" | tr '/?&=:' '_____')"
page="$dir/pages/$key.json"
[ -f "$page" ] || { echo "HTTP 404: no stub page for $path" >&2; exit 1; }
count="$(jq '.pages | length' "$page")"
[ "$paginate" = 1 ] || count=1
i=0
while [ "$i" -lt "$count" ]; do
  if [ -n "$prog" ]; then jq -r ".pages[$i] | $prog" "$page"; else jq -c ".pages[$i]" "$page"; fi
  i=$((i + 1))
done
"""


def runtime_half():
    if not shutil.which("jq"):
        check("jq is available for the runtime half", False, "jq not on PATH")
        return
    tmp = tempfile.mkdtemp(prefix="wc-board-status-")
    pages = os.path.join(tmp, "pages")
    os.makedirs(pages)
    stub = os.path.join(tmp, "gh")
    with open(stub, "w") as fh:
        fh.write(STUB)
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
    repo = "o/r"

    def page(path, *data):
        key = path.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_").replace(":", "_")
        with open(os.path.join(pages, key + ".json"), "w") as fh:
            json.dump({"pages": list(data)}, fh)

    def gh_issue(number, labels, title="t", body="", user_type="User", pr=False, login="someone"):
        d = {"number": number, "title": title, "created_at": "2026-09-30T00:00:00Z",
             "labels": [{"name": n} for n in labels], "body": body,
             "user": {"type": user_type, "login": login}}
        if pr:
            d["pull_request"] = {"url": "x"}
        return d

    status_body = bs.MARKER + "\nold"
    page("repos/o/r/issues?state=open&per_page=100", [
        gh_issue(889, ["disposition:tracking"], "Maintenance backlog",
                 "- [ ] a\n- [x] b\n  - [ ] c\n- [ ] d [wc:bl-0a1b2c3d in-progress PR #7]\n"),
        gh_issue(890, ["disposition:tracking"], "Roadmap"),
        gh_issue(920, ["disposition:tracking"], "Board status", status_body, "Bot"),
    ], [
        gh_issue(741, ["spec-request", "stage:clarify", "spec:098-a"], login="the-author"),
        gh_issue(742, ["spec-request", "stage:clarify", "spec:098-b"], login="the-author"),
        gh_issue(743, ["spec-request", "stage:clarify", "spec:098-c"], login="the-author"),
        gh_issue(821, ["spec:074-x"], pr=True),
    ])

    def comment(user_type, association="NONE", login="x"):
        return {"user": {"type": user_type, "login": login}, "author_association": association}

    # 741: the bot asked last, then a passer-by commented -- still waiting.
    page("repos/o/r/issues/741/comments?per_page=100",
         [comment("User", "OWNER"), comment("Bot")], [comment("User", "NONE")])
    # 742: the issue's own author, not a maintainer, commented after the bot
    # -- clarify does not act on it (spec 134), so still waiting.
    page("repos/o/r/issues/742/comments?per_page=100",
         [comment("Bot")], [comment("User", "NONE", "the-author")])
    # 743: a maintainer answered after the bot.
    page("repos/o/r/issues/743/comments?per_page=100",
         [comment("Bot")], [comment("User", "MEMBER", "a-maintainer")])
    page("repos/o/r/actions/workflows/lint-workflows.yml/runs?branch=main&per_page=20",
         {"workflow_runs": [
             {"event": "pull_request_target", "status": "completed", "conclusion": "failure",
              "head_sha": "f0f0f0f", "html_url": "fork", "head_repository": {"full_name": "fork/r"}},
             {"event": "pull_request", "status": "completed", "conclusion": "action_required",
              "head_sha": "e0e0e0e", "html_url": "pr", "head_repository": {"full_name": "o/r"}},
             {"event": "push", "status": "completed", "conclusion": "success",
              "head_sha": "abc1234", "html_url": "u", "head_repository": {"full_name": "o/r"}}]})
    page("repos/o/r/releases/latest", {"tag_name": "v2.7.3", "published_at": "2026-09-16T00:00:00Z"})
    page("repos/o/r/issues?state=open&labels=disposition:tracking&per_page=100", [
        gh_issue(889, ["disposition:tracking"], "Maintenance backlog", "- [ ] a"),
        gh_issue(918, ["disposition:tracking"], "Board status", status_body, "User"),
        gh_issue(919, ["disposition:tracking"], "A bot issue quoting the marker", status_body, "Bot"),
    ], [
        gh_issue(925, ["disposition:tracking"], "Board status", status_body, "Bot"),
        gh_issue(920, ["disposition:tracking"], "Board status", status_body, "Bot"),
    ])

    old_path = os.environ["PATH"]
    os.environ["PATH"] = tmp + os.pathsep + old_path
    try:
        try:
            snap = bs.snapshot(repo, {})
        except Exception as exc:  # a broken jq program or parse is a finding, not a crash
            check("snapshot() completes against the stubbed API", False, repr(exc))
            return
        check("snapshot reads every page of issues, and issues and PRs apart",
              [i["number"] for i in snap["prs"]] == [821]
              and 741 in [i["number"] for i in snap["issues"]], snap)
        check("snapshot counts the maintenance checklist, nested lines included",
              {k: snap["maintenance"][k] for k in ("number", "open", "done")}
              == {"number": 889, "open": 3, "done": 1}, snap["maintenance"])
        check("snapshot names the line the board loop holds (specs/121 FR-018)",
              snap["maintenance"].get("current") == [
                  {"id": "bl-0a1b2c3d", "text": "d", "detail": "PR #7"}], snap["maintenance"])
        check("snapshot finds the roadmap", snap["roadmap_number"] == 890, snap["roadmap_number"])
        clar = {i["number"]: i for i in snap["issues"] if i["number"] in (741, 742, 743)}
        check("a passer-by's comment after the bot's questions answers nothing",
              clar.get(741, {}).get("last_comment_by_bot") is True, clar.get(741))
        check("the issue's own author who is not a maintainer answers nothing (spec 134)",
              clar.get(742, {}).get("last_comment_by_bot") is True, clar.get(742))
        check("a maintainer answering after the bot is an answer",
              clar.get(743, {}).get("last_comment_by_bot") is False, clar.get(743))
        check("main's CI is this repository's own run, never a fork PR's on a branch named main",
              (snap["main_ci"] or {}).get("conclusion") == "success"
              and snap["main_ci"]["sha"] == "abc1234", snap["main_ci"])
        check("snapshot reads the release", snap["release"]["tag"] == "v2.7.3", snap["release"])
        target = bs.publish(repo, "new body")
        writes = open(os.path.join(tmp, "writes.log")).read().splitlines()
        check("publish edits the bot's oldest status issue, never a person's or another issue quoting the marker",
              target == "repos/o/r/issues/920" and writes == ["PATCH repos/o/r/issues/920"], writes)
        payload = json.load(open(os.path.join(tmp, "payload-1.json")))
        check("publish sends only the body on an edit", payload == {"body": "new body"}, payload)

        page("repos/o/r/issues?state=open&labels=disposition:tracking&per_page=100", [])
        os.remove(os.path.join(tmp, "writes.log"))
        bs.publish(repo, "first body")
        writes = open(os.path.join(tmp, "writes.log")).read().splitlines()
        payload = json.load(open(os.path.join(tmp, "payload-1.json")))
        check("publish opens the status issue the first time, labelled so the board loop skips it",
              writes == ["POST repos/o/r/issues"] and payload.get("labels") == [bs.TRACKING_LABEL]
              and payload.get("title") == bs.TITLE, (writes, payload))
    finally:
        os.environ["PATH"] = old_path


def switches_half():
    # board_now.py (the whats-on-me skill) reads the repository variables
    # straight from gh, as WING_COMMANDER_ + each env name in
    # bs.SWITCH_ENV, so that mapping must match what board-status.yml
    # actually passes -- one env line per switch, from that variable.
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, ".github", "workflows", "board-status.yml"), encoding="utf-8") as fh:
        text = fh.read()
    passed = dict(re.findall(r"^\s+([A-Z_]+): \$\{\{ vars\.WING_COMMANDER_([A-Z_]+) \}\}\s*$", text, re.M))
    check("board-status.yml passes each switch in bs.SWITCH_ENV, from WING_COMMANDER_<its env name>",
          passed == {env: env for env in bs.SWITCH_ENV.values()}, (passed, bs.SWITCH_ENV))
    got = bs.switches_from({"TASKS_REVIEW": " Required "}.get)
    check("switches_from fills every switch and normalises tasks_review",
          got == dict({k: "" for k in bs.SWITCH_ENV}, tasks_review="required"), got)

    # When gh can't list the variables (a Claude Code session's proxy
    # refuses them), board_now.py must stop rather than render every switch
    # as unset: that would report the board loop running and auto-merge off
    # whatever the real switches say.
    sys.path.insert(0, os.path.join(root, ".claude", "skills", "whats-on-me", "scripts"))
    import board_now
    import subprocess
    board_now.gh = lambda *a: subprocess.CompletedProcess(a, 1, "", "HTTP 403")
    try:
        board_now.switches_for("o/r")
        stopped = False
    except SystemExit as err:
        stopped = err.code not in (None, 0)
    check("board_now.py exits non-zero when it can't read the switches", stopped)


def proof_list_half():
    """specs/124-merge-proof-list: the section's notices (contracts/
    proof-list-report.md, research D17) and the constants shared with the
    proof-list workflow."""
    import datetime
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, ".github", "workflows", bs.PROOF_LIST_WORKFLOW), encoding="utf-8") as fh:
        wf = fh.read()
    check("the proof-list workflow's upload name is the writer's artifact constant",
          "name: {0}\n".format(bs.PROOF_LIST_ARTIFACT) in wf)
    check("the proof-list workflow's build step is the writer's build-step constant",
          "- name: {0}\n".format(bs.PROOF_LIST_BUILD_STEP) in wf)
    with open(os.path.join(root, ".github", "workflows", "board-status.yml"), encoding="utf-8") as fh:
        board_status_wf = fh.read()
    paused_line = re.compile(r"^\s+PROOF_LIST_PAUSED: \$\{\{ vars\.WING_COMMANDER_PROOF_LIST_PAUSED \}\}\s*$", re.M)
    check("proof_list_paused is in SWITCH_ENV and passed by board-status.yml",
          bs.SWITCH_ENV.get("proof_list_paused") == "PROOF_LIST_PAUSED" and paused_line.search(board_status_wf))
    # #889: the check above reads the workflow, so dropping the env line fails it.
    check("dropping board-status.yml's PROOF_LIST_PAUSED env line is noticed",
          not paused_line.search(paused_line.sub("", board_status_wf)))

    now = datetime.datetime(2026, 11, 20, 12, 0, 0)
    section = {"schema": 1, "built_at": "2026-11-20T06:19:00Z", "full": "FULLFORM\n", "names_only": "NAMESONLY\n"}

    def run(path_runs, ok, switches=None, download="ok", fail=None):
        def gh_obj(path):
            if fail and fail in path:
                raise subprocess.CalledProcessError(1, "gh", "", "boom")
            if path.endswith("/o/r") or path == "repos/o/r":
                return {"default_branch": "main"}
            return {"workflow_runs": path_runs}

        def dl(repo, rid, tmp):
            if download == "ok" or isinstance(download, dict):
                with open(os.path.join(tmp, bs.PROOF_LIST_FILE), "w", encoding="utf-8") as fh:
                    json.dump(section if download == "ok" else download, fh)
            elif download == "bad":
                with open(os.path.join(tmp, bs.PROOF_LIST_FILE), "w", encoding="utf-8") as fh:
                    fh.write("{")
        return bs.proof_list_snapshot("o/r", switches or {}, now, gh_obj, lambda rid: ok.get(rid, False), dl)

    def mk(rid, when, conclusion="success", event="schedule"):
        return {"id": rid, "run_started_at": when, "conclusion": conclusion, "event": event,
                "head_repository": {"full_name": "o/r"}}
    fresh, old = mk(3, "2026-11-20T06:19:00Z"), mk(2, "2026-11-19T06:19:00Z")
    got = run([fresh, old], {3: True})
    check("a fresh successful build is built, with its section", got["status"] == "built" and got["section"] == section, got)
    check("no run is never", run([], {})["status"] == "never")
    check("a failed latest build is failed, last good known",
          run([mk(4, "2026-11-20T06:19:00Z", "failure"), old], {2: True}) ==
          {"status": "failed", "last_good_at": "2026-11-19T06:19:00Z"})
    check("a cancelled latest build is failed", run([mk(4, "2026-11-20T06:19:00Z", "cancelled")], {})["status"] == "failed")
    check("a build older than 48 hours is failed", run([mk(5, "2026-11-17T06:19:00Z")], {5: True})["status"] == "failed")
    check("a successful run that stood down on the switch is paused", run([fresh], {3: False})["status"] == "paused")
    # #889: a run that succeeded but skipped its build, older than 48 hours,
    # reads "failed" (too old to stand for today), not "paused". The last
    # good build is older still: runs come newest first.
    skipped_old = run([mk(6, "2026-11-17T06:19:00Z"), mk(1, "2026-11-16T06:19:00Z")], {6: False, 1: True})
    check("a successful skipped-build run older than 48 hours is failed",
          skipped_old == {"status": "failed", "last_good_at": "2026-11-16T06:19:00Z"}, skipped_old)
    check("the switch set is paused whatever the history", run([fresh], {3: True}, {"proof_list_paused": "true"})["status"] == "paused")
    check("a refused run (another event or repository) is not read",
          run([dict(fresh, event="push")], {3: True})["status"] == "never"
          and run([dict(fresh, head_repository={"full_name": "x/y"})], {3: True})["status"] == "never")
    check("a missing artifact is unreadable", run([fresh], {3: True}, download="none")["status"] == "unreadable")
    check("a malformed artifact is unreadable", run([fresh], {3: True}, download="bad")["status"] == "unreadable")
    # #889: a non-string form or build time would make render() raise and stop
    # the whole Board status rewrite; the reader refuses it as unreadable.
    for key, bad in (("full", 123), ("names_only", ["x"]), ("built_at", 5), ("built_at", None)):
        typed = run([fresh], {3: True}, download=dict(section, **{key: bad}))
        check("a section whose {0} is {1!r}, not a string, is unreadable".format(key, bad),
              typed["status"] == "unreadable", typed)
    check("an unreadable history is unreadable with last good unknown",
          run([fresh], {3: True}, fail="workflows/") == {"status": "unreadable", "last_good_at": "unknown"})

    body = "board body\n"
    full = bs.proof_list_block({"status": "built", "last_good_at": "x", "section": section}, body)
    check("a build that fits embeds the full form between the contract's markers",
          "FULLFORM" in full and 'status="built"' in full and full.rstrip().endswith("<!-- wc-proof-list:end -->"), full)
    near = "x" * (60000 - len(body) - 700)
    names = bs.proof_list_block({"status": "built", "section": dict(section, full="F" * 5000)}, near)
    check("a body too full for the full form gets the names-only form", "NAMESONLY" in names and "FFFF" not in names, names[:200])
    over = bs.proof_list_block({"status": "built", "section": dict(section, full="F" * 5000, names_only="N" * 5000)}, "y" * 59000)
    # #889: the begin marker's last-good= attribute carries the snapshot's
    # last good build, on the built form and on every notice.
    check("the built form's begin marker carries last-good=",
          '<!-- wc-proof-list:begin status="built" built="2026-11-20T06:19:00Z" last-good="x" -->' in full, full[:200])
    for status, last in (("failed", "2026-11-19T06:19:00Z"), ("paused", "never"), ("unreadable", "unknown")):
        blk = bs.proof_list_block({"status": status, "last_good_at": last}, body)
        check("the {0} notice's begin marker carries last-good={1!r}".format(status, last),
              blk.startswith('<!-- wc-proof-list:begin status="{0}" built="none" last-good="{1}" -->'.format(status, last)),
              blk[:200])
    check("when neither form fits the failed notice shows, with no list",
          'status="failed"' in over and "NNNN" not in over and "too large" in over, over[:300])
    for status, last, text in (("paused", "never", "never been a good build"),
                               ("failed", "2026-11-19T06:19:00Z", "2026-11-19T06:19:00Z"),
                               ("never", "never", "never been built"),
                               ("unreadable", "unknown", "date is unknown")):
        blk = bs.proof_list_block({"status": status, "last_good_at": last}, body)
        check("the {0} notice shows no list and says when the last good build was".format(status),
              'status="{0}"'.format(status) in blk and text in blk and "FULLFORM" not in blk, blk)
    check("render places the section after the board and leaves the rest unchanged",
          bs.render(dict(SNAP, proof_list={"status": "never"})).startswith(bs.render(SNAP))
          and "wc-proof-list:begin" not in bs.render(SNAP))


def run_name_title_problems(wf_text):
    """Each of the writer's audit titles must appear whole, as a quoted
    literal, in the workflow's run-name (finding 9, #1173 round 3); a
    shared prefix or a format() template is not enough."""
    import yaml
    run_name = str((yaml.safe_load(wf_text) or {}).get("run-name") or "")
    problems = ["run-name has no literal '{0}'".format(t) for t in bs.MERGE_EVIDENCE_AUDIT_TITLES
                if "'{0}'".format(t) not in run_name]
    if "'merge-evidence verdicts'" not in run_name or "merge-evidence verdicts" in bs.MERGE_EVIDENCE_AUDIT_TITLES:
        problems.append("the hourly title 'merge-evidence verdicts' is missing, or counted as an audit")
    return problems


def merge_evidence_half():
    """specs/125-merge-evidence-audit: the section's statuses, its shortened
    form, and the constants shared with the merge evidence workflow."""
    import datetime
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, ".github", "workflows", bs.MERGE_EVIDENCE_WORKFLOW), encoding="utf-8") as fh:
        wf = fh.read()
    check("the merge-evidence workflow's upload name is the writer's artifact constant",
          "name: {0}\n".format(bs.MERGE_EVIDENCE_ARTIFACT) in wf)
    check("the merge-evidence workflow's build step is the writer's build-step constant",
          "- name: {0}\n".format(bs.MERGE_EVIDENCE_BUILD_STEP) in wf)
    missing = run_name_title_problems(wf)
    check("the merge-evidence workflow's run-name writes out each audit title the writer filters on",
          not missing, "; ".join(missing))
    for label, old_text, new_text in (("a renamed dispatch title", "'merge-evidence dispatch both'",
                                       "'merge-evidence dispatch all'"),
                                      ("a renamed scheduled audit title", "'merge-evidence audit'",
                                       "'merge-evidence audits'")):
        mutated = wf.replace(old_text, new_text)
        check("the run-name check notices {0}".format(label),
              mutated != wf and run_name_title_problems(mutated))
    check("merge_evidence_paused is in SWITCH_ENV and passed by board-status.yml",
          bs.SWITCH_ENV.get("merge_evidence_paused") == "MERGE_EVIDENCE_PAUSED")
    with open(os.path.join(root, ".github", "workflows", "board-status.yml"), encoding="utf-8") as fh:
        check("board-status.yml passes the pause variable",
              "MERGE_EVIDENCE_PAUSED: ${{ vars.WING_COMMANDER_MERGE_EVIDENCE_PAUSED }}" in fh.read())

    now = datetime.datetime(2026, 11, 20, 12, 0, 0)
    section = {"schema": 1, "built_at": "2026-11-20T05:41:00Z", "full": "MEFULL\n", "names_only": "MENAMES\n"}

    def run(runs, ok, switches=None, download="ok"):
        def gh_obj(path):
            if path == "repos/o/r":
                return {"default_branch": "main"}
            return {"workflow_runs": runs}

        def dl(repo, rid, tmp):
            if download == "ok":
                with open(os.path.join(tmp, bs.MERGE_EVIDENCE_FILE), "w", encoding="utf-8") as fh:
                    json.dump(section, fh)
        return bs.merge_evidence_snapshot("o/r", switches or {}, now, gh_obj, lambda rid: ok.get(rid, False), dl)

    def mk(rid, when, title="merge-evidence audit", conclusion="success"):
        return {"id": rid, "run_started_at": when, "conclusion": conclusion, "event": "schedule",
                "display_title": title, "head_repository": {"full_name": "o/r"}}
    audit = mk(3, "2026-11-20T05:41:00Z")
    hourly = mk(9, "2026-11-20T11:07:00Z", "merge-evidence verdicts")
    check("built: the hourly verdict runs are not the audit",
          run([hourly, audit], {3: True})["status"] == "built")
    check("never: only hourly runs exist", run([hourly], {9: True})["status"] == "never")
    check("failed: the latest audit failed",
          run([mk(4, "2026-11-20T05:41:00Z", conclusion="failure")], {})["status"] == "failed")
    check("paused: the switch is set, whatever the history",
          run([audit], {3: True}, {"merge_evidence_paused": "True"})["status"] == "paused")
    # The one switch rule never trims (#889): a padded value is not a pause.
    check("a padded pause switch is not a pause",
          run([audit], {3: True}, {"merge_evidence_paused": "True "})["status"] != "paused")
    check("unreadable: the artifact is missing", run([audit], {3: True}, download="none")["status"] == "unreadable")

    # #1173 review R3: ~25 runs a day, so the last good audit can sit past the
    # first 30 runs; the reader pages until it finds it.
    def paged(runs):
        def gh_obj(path):
            if path == "repos/o/r":
                return {"default_branch": "main"}
            per = int(re.search(r"per_page=(\d+)", path).group(1))
            page = int((re.search(r"[?&]page=(\d+)", path) or re.search(r"()", path)).group(1) or 1)
            return {"workflow_runs": runs[(page - 1) * per:page * per]}
        return gh_obj
    hourly_runs = [mk(100 + i, "2026-11-20T11:07:00Z", "merge-evidence verdicts") for i in range(140)]
    late_good = mk(7, "2026-11-19T05:41:00Z")
    failed_audit = mk(8, "2026-11-20T05:41:00Z", conclusion="failure")
    deep = hourly_runs[:20] + [failed_audit] + hourly_runs[20:130] + [late_good]
    snap = bs.merge_evidence_snapshot("o/r", {}, now, paged(deep), lambda rid: rid == 7, lambda *a: None)
    check("a failed audit keeps the last good build from past the first 100 runs",
          snap == {"status": "failed", "last_good_at": "2026-11-19T05:41:00Z"}, snap)
    fresh = hourly_runs[:35] + [audit]
    snap = bs.merge_evidence_snapshot("o/r", {}, now, paged(fresh), lambda rid: rid == 3,
                                      lambda repo, rid, tmp: json.dump(section, open(
                                          os.path.join(tmp, bs.MERGE_EVIDENCE_FILE), "w", encoding="utf-8")))
    check("a good audit past the 30th run is still found (not 'never')", snap.get("status") == "built", snap)
    # Round 5, finding 8: past three pages the reader keeps going, and a
    # bound it stops at is said as "not found within ...", never "never".
    mid = hourly_runs[:5] + [failed_audit] + [mk(200 + i, "2026-11-20T11:07:00Z", "merge-evidence verdicts")
                                              for i in range(440)] + [late_good]
    snap = bs.merge_evidence_snapshot("o/r", {}, now, paged(mid), lambda rid: rid == 7, lambda *a: None)
    check("the last good audit past three pages (the 447th run) is still found",
          snap == {"status": "failed", "last_good_at": "2026-11-19T05:41:00Z"}, snap)
    capped = [mk(1000 + i, "2026-11-20T11:07:00Z", "merge-evidence verdicts") for i in range(1050)] + [late_good]
    snap = bs.merge_evidence_snapshot("o/r", {}, now, paged(capped), lambda rid: True, lambda *a: None)
    check("no audit within the run cap is 'not found within N runs', not 'never'",
          snap.get("status") == "failed" and "not found within the newest" in str(snap.get("last_good_at")), snap)
    aged = [mk(3000 + i, "2026-09-01T11:07:00Z", "merge-evidence verdicts") for i in range(150)] + [late_good]
    snap = bs.merge_evidence_snapshot("o/r", {}, now, paged(aged), lambda rid: True, lambda *a: None)
    check("runs older than the lookback stop the reader with 'not found in the last N days'",
          snap.get("status") == "failed" and "not found in the last" in str(snap.get("last_good_at")), snap)
    check("the notice for a bound reads as a sentence",
          "The last good build was not found within the newest 1000 runs." in bs.merge_evidence_block(
              {"status": "failed", "last_good_at": "not found within the newest 1000 runs"}, "body\n"))
    forked = [dict(audit, id=21, event="pull_request"), dict(audit, id=22, head_repository={"full_name": "fork/r"})]
    check("a pull_request or fork run is never the audit",
          bs.merge_evidence_snapshot("o/r", {}, now, paged(forked), lambda rid: True, lambda *a: None)["status"] == "never")
    try:
        bs.merge_evidence_snapshot("o/r", {}, now, lambda path: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, "gh", "", "boom")), lambda rid: True)
        unreadable = True
    except subprocess.CalledProcessError:
        unreadable = False
    check("unreadable: a failed history read is a status, not a crash", unreadable)

    body = "board body\n"
    built = {"status": "built", "last_good_at": "x", "section": section}
    check("a section that fits shows the full form between its own markers",
          "MEFULL" in bs.merge_evidence_block(built, body)
          and "<!-- wc-merge-evidence:end -->" in bs.merge_evidence_block(built, body))
    near = "x" * (60000 - len(body) - 700)
    short = bs.merge_evidence_block({"status": "built", "section": dict(section, full="F" * 5000)}, near)
    check("over size, the names-only form shows", "MENAMES" in short and "FFFF" not in short)
    check("render places the section after the board and leaves the rest unchanged",
          bs.render(dict(SNAP, merge_evidence={"status": "never"})).startswith(bs.render(SNAP))
          and "wc-merge-evidence:begin" not in bs.render(SNAP))


def feature_health_half():
    """specs/126-feature-health: the section's writer statuses (contracts/
    feature-health-report.md "Writer statuses") and the constants shared with
    the feature-health workflow."""
    import datetime
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, ".github", "workflows", bs.FEATURE_HEALTH_WORKFLOW), encoding="utf-8") as fh:
        wf = fh.read()
    check("the feature-health workflow's upload name is the writer's artifact constant",
          "name: {0}\n".format(bs.FEATURE_HEALTH_ARTIFACT) in wf)
    check("the feature-health workflow's build step is the writer's build-step constant",
          "- name: {0}\n".format(bs.FEATURE_HEALTH_BUILD_STEP) in wf)
    check("feature_health_paused is in SWITCH_ENV",
          bs.SWITCH_ENV.get("feature_health_paused") == "FEATURE_HEALTH_PAUSED")
    with open(os.path.join(root, ".github", "workflows", "board-status.yml"), encoding="utf-8") as fh:
        bs_text = fh.read()
    check("board-status.yml passes the feature-health switch",
          "FEATURE_HEALTH_PAUSED: ${{ vars.WING_COMMANDER_FEATURE_HEALTH_PAUSED }}" in bs_text)

    now = datetime.datetime(2026, 11, 20, 12, 0, 0)
    content = bs.FEATURE_HEALTH_MARKER + "\n**Feature health** — built 2026-11-20 06:29Z · 1 features · 0 unreadable\n"

    def run(path_runs, ok, switches=None, download="ok", fail=None):
        def gh_obj(path):
            if fail and fail in path:
                raise subprocess.CalledProcessError(1, "gh", "", "boom")
            if path == "repos/o/r":
                return {"default_branch": "main"}
            return {"workflow_runs": path_runs}

        def dl(repo, rid, tmp):
            if download in ("ok", "bad"):
                with open(os.path.join(tmp, bs.FEATURE_HEALTH_ARTIFACT + ".md"), "w", encoding="utf-8") as fh:
                    fh.write(content if download == "ok" else "garbage")
        return bs.feature_health_snapshot("o/r", switches or {}, now, gh_obj, lambda rid: ok.get(rid, False), dl)

    def mk(rid, when, conclusion="success"):
        return {"id": rid, "run_started_at": when, "conclusion": conclusion, "event": "schedule",
                "head_repository": {"full_name": "o/r"}}
    fresh, old = mk(3, "2026-11-20T06:29:00Z"), mk(2, "2026-11-19T06:29:00Z")
    got = run([fresh, old], {3: True})
    check("a fresh feature-health build is built, with its content", got["status"] == "built" and got["section"] == content, got)
    check("no feature-health run is never", run([], {})["status"] == "never")
    check("a failed latest feature-health build is failed, last good known",
          run([mk(4, "2026-11-20T06:29:00Z", "failure"), old], {2: True})
          == {"status": "failed", "last_good_at": "2026-11-19T06:29:00Z"})
    stale = run([mk(5, "2026-11-17T06:29:00Z")], {5: True})
    check("a build older than 48 hours keeps its content and is stale", stale["status"] == "stale" and stale["section"] == content, stale)
    check("a run that stood down on the switch is paused", run([fresh], {3: False})["status"] == "paused")
    check("the switch set is paused whatever the history",
          run([fresh], {3: True}, {"feature_health_paused": "true"})["status"] == "paused")
    check("a missing artifact is unreadable", run([fresh], {3: True}, download="none")["status"] == "unreadable")
    check("a malformed artifact is unreadable", run([fresh], {3: True}, download="bad")["status"] == "unreadable")
    check("an unreadable history is unreadable with last good unknown",
          run([fresh], {3: True}, fail="workflows/") == {"status": "unreadable", "last_good_at": "unknown"})

    body = "board body\n"
    built = bs.feature_health_block({"status": "built", "section": content}, body)
    check("a built section is embedded as the artifact content", built.startswith(bs.FEATURE_HEALTH_MARKER) and "Feature health" in built, built)
    st = bs.feature_health_block(dict(stale, built_at="2026-11-17T06:29:00Z"), body)
    check("a stale section says so and gives its build date", "Stale" in st and "2026-11-17" in st, st)
    table = content + "\n<details><summary>All features</summary>\n\n" + "| row |\n" * 20000 + "</details>\n"
    short = bs.feature_health_block({"status": "built", "section": table}, body)
    check("an over-size table is dropped and the call-outs stay", "Table shortened" in short and "| row |" not in short, short[:200])
    no_table = bs.FEATURE_HEALTH_MARKER + "\n**Feature health** — built x\n" + bs.FEATURE_HEALTH_MARKER_END + "\n"
    cut = bs.shorten_feature_health(no_table)
    check("shortening a section with no table keeps its end marker and adds no shortened line",
          cut.endswith(bs.FEATURE_HEALTH_MARKER_END) and "Table shortened" not in cut, cut)
    from board_spec_request_body import MAX_BODY_UNITS, utf16_len
    callouts = bs.FEATURE_HEALTH_MARKER + "\n" + "- `x` — failing\n" * 400 + bs.FEATURE_HEALTH_MARKER_END
    roomy = "b" * (MAX_BODY_UNITS - 1000)
    over = bs.feature_health_block({"status": "built", "section": callouts, "last_good_at": "2026-11-19"}, roomy)
    check("a section whose call-outs do not fit falls back to the too-large notice",
          "too large" in over and utf16_len(roomy) + 1 + utf16_len(over) <= MAX_BODY_UNITS, over[:200])
    full = "b" * (MAX_BODY_UNITS - 20)
    import contextlib
    import io
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        none = bs.feature_health_block({"status": "built", "section": callouts, "last_good_at": "2026-11-19"}, full)
    check("dropping the section when nothing fits is logged, not silent",
          none == "" and "left out" in err.getvalue(), err.getvalue())
    check("when not even the too-large notice fits, the body stays within the limit",
          utf16_len(full) + 1 + utf16_len(none) <= MAX_BODY_UNITS, utf16_len(none))
    for status, last, text in (("paused", "2026-11-19T06:29:00Z", "WING_COMMANDER_FEATURE_HEALTH_PAUSED"),
                               ("failed", "2026-11-19T06:29:00Z", "latest build failed"),
                               ("never", "never", "not yet built"),
                               ("unreadable", "2026-11-19T06:29:00Z", "could not read")):
        blk = bs.feature_health_block({"status": status, "last_good_at": last}, body)
        check("the {0} notice says {1}".format(status, text), text in blk and "Feature health —" not in blk, blk)
        if status != "never":
            check("the {0} notice gives the last good build date".format(status), "2026-11-19" in blk, blk)
    check("render places the feature-health section after the board",
          bs.render(dict(SNAP, feature_health={"status": "never"})).startswith(bs.render(SNAP))
          and bs.FEATURE_HEALTH_MARKER not in bs.render(SNAP))
    # #889: an unterminated <details> must not take the end marker with it.
    open_table = (bs.FEATURE_HEALTH_MARKER + "\n**Feature health** — built x\n\n<details><summary>All</summary>\n"
                  + "| row |\n" * 3 + bs.FEATURE_HEALTH_MARKER_END + "\n")
    cut = bs.shorten_feature_health(open_table)
    check("shortening a section whose <details> never closes keeps its end marker",
          cut.endswith(bs.FEATURE_HEALTH_MARKER_END) and "| row |" not in cut and "Table shortened" in cut, cut)


def path_half():
    """#889: the readers that import a sibling module put this directory on
    sys.path once, not once per call."""
    here = os.path.dirname(os.path.abspath(bs.__file__))
    before = sys.path.count(here)
    for _ in range(3):
        bs.current_lines("")
        bs.section_fits("body\n", "x\n")
    check("current_lines and section_fits do not grow sys.path on each call",
          sys.path.count(here) == max(before, 1), (before, sys.path.count(here)))


def fit_half():
    """#889: every section render appends keeps the whole body within
    MAX_BODY_UNITS, at and around the boundary, whatever the section's status.
    The limit is lowered for the sweep so a small board sits right at it."""
    import contextlib
    import io
    import board_spec_request_body as bsrb
    base = bs.render(SNAP)
    pl_section = {"schema": 1, "built_at": "2026-11-20T06:19:00Z", "full": "F" * 400 + "\n",
                  "names_only": "N" * 200 + "\n"}
    me_section = dict(pl_section, full="M" * 400 + "\n", names_only="m" * 200 + "\n")
    fh_section = (bs.FEATURE_HEALTH_MARKER + "\n**Feature health** — built x\n" + "- `x` — failing\n" * 10
                  + "\n<details><summary>All</summary>\n\n" + "| row |\n" * 40 + "</details>\n"
                  + bs.FEATURE_HEALTH_MARKER_END + "\n")
    cases = []
    for status in ("paused", "failed", "never", "unreadable"):
        cases.append(("proof list " + status, {"proof_list": {"status": status, "last_good_at": "2026-11-19"}}))
        cases.append(("merge evidence " + status, {"merge_evidence": {"status": status, "last_good_at": "2026-11-19"}}))
        cases.append(("feature health " + status, {"feature_health": {"status": status, "last_good_at": "2026-11-19"}}))
    cases.append(("proof list built", {"proof_list": {"status": "built", "last_good_at": "x", "section": pl_section}}))
    cases.append(("merge evidence built", {"merge_evidence": {"status": "built", "last_good_at": "x", "section": me_section}}))
    cases.append(("feature health built", {"feature_health": {"status": "built", "section": fh_section}}))
    cases.append(("feature health stale", {"feature_health": {"status": "stale", "section": fh_section,
                                                              "built_at": "2026-11-17T06:29:00Z"}}))
    cases.append(("all three built", {"proof_list": {"status": "built", "last_good_at": "x", "section": pl_section},
                                      "merge_evidence": {"status": "built", "last_good_at": "x", "section": me_section},
                                      "feature_health": {"status": "built", "section": fh_section}}))
    saved = bsrb.MAX_BODY_UNITS
    try:
        for name, extra in cases:
            snap = dict(SNAP, **extra)
            bsrb.MAX_BODY_UNITS = 10 ** 9
            top = bsrb.utf16_len(bs.render(snap))
            over, left_out, raised = [], 0, None
            for limit in range(bsrb.utf16_len(base), top + 2):
                bsrb.MAX_BODY_UNITS = limit
                err = io.StringIO()
                try:
                    with contextlib.redirect_stderr(err):
                        got = bs.render(snap)
                except Exception as exc:  # noqa: BLE001 -- any raise stops the rewrite
                    raised = "{0} at {1}: {2!r}".format(name, limit, exc)
                    break
                if bsrb.utf16_len(got) > limit:
                    over.append(limit)
                if "left out" in err.getvalue():
                    left_out += 1
            check("{0}: render stays within the body limit at every limit from the bare board up".format(name),
                  not over and not raised, raised or over[:5])
            check("{0}: a section with no room at all is left out and logged".format(name), left_out > 0, left_out)
    finally:
        bsrb.MAX_BODY_UNITS = saved
    check("append_section adds nothing for a section that was left out",
          bs.append_section("body\n", "") == "body\n" and bs.append_section("body\n", "x\n") == "body\n\nx\n")


# The one switch rule (#889; owner decision 2026-11-27, on the Roadmap
# issue: all switches work the same way, with exceptions only where the
# technology forces one): a switch is on when its value equals "true"
# compared case-insensitively, with no trimming. That is GitHub's own
# `vars.X == 'true'`, which most switches are read by and which nothing here
# can change, so it is the answer every other reader must give.
def one_rule(value):
    return str(value or "").lower() == "true"


# Values a person could type into a variable. None is an unset variable.
READER_VALUES = ("true", "True", "TRUE", "tRuE", "true ", " true", "\ttrue\n", "false", "False",
                 "", None, "yes", "1", "truee")
BOARD_LOOP = ".github/workflows/board-loop.yml"
GUARD_ACTION = ".github/actions/wing-commander-watch-guard/action.yml"
# The one temporary exception: a reader that may still disagree with the
# rule, the tracker that holds its fix, and the exact line (stripped) it is
# registered against. When that line changes the exception fails, so it is
# dropped with the fix rather than left to excuse a later drift.
READER_EXCEPTIONS = {
    "board-loop.yml merge decision (jq)": {
        "tracker": "#889",
        "path": BOARD_LOOP,
        "line": "'{class: $class, switch_on: ($switch_on == \"true\"),",
    },
}
# Shell pause checks that do not follow the rule yet, tracked on #889
# ("One rule for all switches"): (workflow file that relays the raw value,
# switch, workflow file whose check reads it). Not run by
# one_rule_problems(); docs_half() requires docs/reference.md to name each,
# and relay_problems() fails on a raw relay of a switch that is neither here
# nor in ONE_RULE_RELAYS, and on an entry whose relay is gone.
PENDING_SHELL_READERS = (
    ("lifecycle-review-gate.yml", "WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED", "lifecycle-review-gate.yml"),
    ("auto-release.yml", "WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED", "auto-release.yml"),
)
# Raw relays of a switch to a reader one_rule_problems() runs (or to the
# registered exception): workflow file -> the switches it relays that way
# (None: every switch). A `switch-value:` hand-off to the watch-guard
# composite is checked by READER_SITES' guard shape instead.
ONE_RULE_RELAYS = {
    "board-status.yml": None,  # wc_board_status
    "wing-commander-feature-health.yml": None,  # wc_feature_health.collect
    "board-loop.yml": {"WING_COMMANDER_BOARD_BACKLOG_LINES", "WING_COMMANDER_BOARD_LOOP_PAUSED",
                       "WING_COMMANDER_BOARD_AUTO_MERGE"},  # selection_gate; the exception
    # shared-pr-reviewer.yml's `paused` input, which its guard and prepare
    # jobs read as `inputs.paused == 'true'` (shell_pause_readers()).
    "wing-commander-shared-pr-reviewer.yml": {"WING_COMMANDER_SHARED_REVIEWER_PAUSED"},
}
# A value handed out of GitHub's expression untouched (with or without an
# empty-string default), for some later reader to compare.
RAW_RELAY_RE = re.compile(r"\$\{\{\s*vars\.(WING_COMMANDER_[A-Z0-9_]+)\s*(?:\|\|\s*''\s*)?\}\}")


def kill_switch_vars(reference):
    """The switches docs/reference.md's Kill switches table lists."""
    kill = reference.split("## Kill switches", 1)[-1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `(WING_COMMANDER_[A-Z0-9_]+)` \|", kill, re.M))


NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def pending_docs_problems(kill_flat, pending):
    """docs/reference.md's "N readers do not follow it yet" sentence states
    how many readers are pending and names only their workflow files."""
    m = re.search(r"(\w+) readers? do(?:es)? not follow it yet(.*?)\| Switch \|", kill_flat)
    if not m:
        return ["docs/reference.md's Kill switches section has no \"do not follow it yet\" list"]
    problems = []
    want = NUMBER_WORDS[len(pending)] if len(pending) < len(NUMBER_WORDS) else str(len(pending))
    if m.group(1).lower() != want:
        problems.append("the list says {0!r} readers; {1} are pending".format(m.group(1), len(pending)))
    named = set(re.findall(r"`([\w.-]+\.yml)`", m.group(2)))
    extra = sorted(named - {path for path, _var in pending})
    if extra:
        problems.append("the list names {0}, which no longer has a pending reader".format(extra))
    return problems


def relay_problems(root, switch_vars, pending, conforming):
    """Every raw relay of a switch in .github/workflows goes to a reader the
    one-rule check runs, or is a registered pending reader; every pending
    reader still has its relay, so it is dropped with its fix."""
    wf_dir = os.path.join(root, ".github", "workflows")
    found = set()
    for name in sorted(os.listdir(wf_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        for line in _file_lines(root, os.path.join(".github", "workflows", name)):
            if line.startswith("#") or line.startswith("switch-value:"):
                continue
            for var in RAW_RELAY_RE.findall(line):
                if var in switch_vars:
                    found.add((name, var))
    problems = []
    registered = {(relay, var) for relay, var, _reader in pending}
    for name, var in sorted(found):
        allowed = conforming.get(name, set())
        if (allowed is None or var in allowed) or (name, var) in registered:
            continue
        problems.append("{0} relays {1} raw to a reader this check does not run; bring it under "
                        "the one switch rule or register it in PENDING_SHELL_READERS".format(name, var))
    for relay, var in sorted(registered - found):
        problems.append("{0} no longer relays {1} raw; drop its PENDING_SHELL_READERS entry and "
                        "its docs/reference.md mention".format(relay, var))
    return problems
# Where each switch Board status reports is read, as the literal statement
# in its file. Every statement must have one of SITE_SHAPES' shapes (or be
# an exception's line), so a switch cannot pick up a reader of its own that
# this check never runs.
READER_SITES = {
    "auto_release_paused": [(".github/workflows/auto-release.yml",
                             "if: vars.WING_COMMANDER_AUTO_RELEASE_PAUSED != 'true'")],
    "board_auto_merge": [(BOARD_LOOP, "SWITCH_ON: ${{ vars.WING_COMMANDER_BOARD_AUTO_MERGE }}"),
                         (BOARD_LOOP, "'{class: $class, switch_on: ($switch_on == \"true\"),")],
    "board_backlog_lines": [(BOARD_LOOP, "BACKLOG_LINES_SWITCH: ${{ vars.WING_COMMANDER_BOARD_BACKLOG_LINES }}"),
                            (BOARD_LOOP, "\"switch\": os.environ.get(\"BACKLOG_LINES_SWITCH\") or \"\","),
                            (".github/scripts/board_backlog_lines.py",
                             "if not wc_board_status._switch_on(env.get(\"backlog_lines_switch\")):")],
    "board_can_push_workflows": [(BOARD_LOOP,
                                  "CAN_PUSH_WORKFLOWS: ${{ vars.WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS == 'true' }}")],
    "board_loop_paused": [(BOARD_LOOP,
                           "if [ \"${{ vars.WING_COMMANDER_BOARD_LOOP_PAUSED == 'true' }}\" = \"true\" ]; then")],
    "lifecycle_auto_merge": [(".github/workflows/lifecycle-review-gate.yml",
                              "!cancelled() && vars.WING_COMMANDER_LIFECYCLE_AUTO_MERGE == 'true'")],
    "review_gate_paused": [(".github/workflows/lifecycle-review-gate.yml",
                            "if: vars.WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED != 'true'")],
    "feature_health_paused": [(".github/workflows/wing-commander-feature-health.yml",
                               "switch-value: ${{ vars.WING_COMMANDER_FEATURE_HEALTH_PAUSED }}")],
    "merge_evidence_paused": [(".github/workflows/wing-commander-merge-evidence.yml",
                               "switch-value: ${{ vars.WING_COMMANDER_MERGE_EVIDENCE_PAUSED }}")],
    "proof_list_paused": [(".github/workflows/wing-commander-proof-list.yml",
                           "switch-value: ${{ vars.WING_COMMANDER_PROOF_LIST_PAUSED }}")],
}
# The shapes a reader site may have: GitHub's comparison, a hand-off to the
# watch-guard composite, a raw relay to a reader one_rule_problems() runs,
# or a call to the rule's one home.
SITE_SHAPES = {
    "expression": re.compile(r"vars\.WING_COMMANDER_[A-Z_]+ [!=]= 'true'"),
    "guard": re.compile(r"^switch-value: \$\{\{ vars\.WING_COMMANDER_[A-Z_]+ \}\}$"),
    "relay": re.compile(r"^[A-Z_]+: \$\{\{ vars\.WING_COMMANDER_[A-Z_]+ \}\}$|os\.environ\.get\(\"[A-Z_]+\"\)"),
    "rule": re.compile(r"\bwc_board_status\._switch_on\("),
}


def _file_lines(root, path):
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return [line.strip() for line in fh.read().splitlines()]


def reader_sites_problems(root, sites, exceptions):
    """Every switch has a site; every site's statement is a line of its file,
    names its own variable and has one of SITE_SHAPES' shapes or is an
    exception's line; a guard site hands the value to the watch-guard
    composite."""
    problems = []
    excused = {(ex["path"], ex["line"]) for ex in exceptions.values()}
    for key in sorted(set(bs.SWITCH_ENV) - {"tasks_review"}):
        if not sites.get(key):
            problems.append("{0}: no reader site".format(key))
        var = "WING_COMMANDER_" + bs.SWITCH_ENV[key]
        for path, statement in sites.get(key, []):
            try:
                lines = _file_lines(root, path)
            except OSError as err:
                problems.append("{0}: {1} unreadable ({2})".format(key, path, err))
                continue
            at = [i for i, line in enumerate(lines) if statement in line]
            if not at:
                problems.append("{0}: {1} no longer has the line {2!r}".format(key, path, statement))
            shapes = [name for name, rx in SITE_SHAPES.items() if rx.search(statement)]
            if not shapes and (path, statement) not in excused:
                problems.append("{0}: {1!r} reads the switch some way other than the one rule".format(key, statement))
            if "WING_COMMANDER_" in statement and var not in statement:
                problems.append("{0}: {1!r} reads another variable".format(key, statement))
            if "guard" in shapes:
                near = lines[max(0, at[0] - 10):at[0] + 1] if at else []
                if not any(line.startswith("uses:") and "wing-commander-watch-guard" in line for line in near) \
                        or "switch-name: " + var not in near:
                    problems.append("{0}: {1} does not hand {2} to wing-commander-watch-guard".format(key, path, var))
    for key in sorted(set(sites) - set(bs.SWITCH_ENV)):
        problems.append("{0}: a reader site for a switch SWITCH_ENV does not have".format(key))
    return problems


def one_rule_problems(root, readers, exceptions, values=READER_VALUES):
    """Every reader gives one_rule()'s answer on every value. A reader that
    disagrees fails unless it is the registered exception; the exception
    fails once its line has changed or once its reader agrees, so it is
    dropped with the fix."""
    problems = []
    if len(exceptions) > 1:
        problems.append("more than one reader exception: {0}".format(sorted(exceptions)))
    for name, read in readers.items():
        try:
            wrong = [(v, read(v)) for v in values if read(v) != one_rule(v)]
        except Exception as err:  # a reader that cannot run is not shown to agree
            problems.append("{0}: could not run ({1})".format(name, err))
            continue
        ex = exceptions.get(name)
        if ex is None:
            if wrong:
                problems.append("{0} disagrees with the one switch rule on {1}".format(name, wrong))
            continue
        try:
            present = ex["line"] in _file_lines(root, ex["path"])
        except OSError:
            present = False
        if not present:
            problems.append("{0}: the exception's line {1!r} is gone from {2}; drop the exception "
                            "(tracker {3})".format(name, ex["line"], ex["path"], ex["tracker"]))
        elif not wrong:
            problems.append("{0} now follows the one switch rule; drop its exception (tracker {1})".format(
                name, ex["tracker"]))
    for name in sorted(set(exceptions) - set(readers)):
        problems.append("{0}: an exception for a reader this check does not run".format(name))
    return problems


def real_readers(root):
    """Every real reader of a switch Board status reports, each run on the
    raw value the way the pipeline hands it over."""
    import subprocess
    import yaml
    import board_backlog_lines as bbl
    import wc_feature_health as fh

    def board_status(value):
        answers = {bs.switch_set({key: value}, key) for key in bs.SWITCH_ENV if key != "tasks_review"}
        if len(answers) != 1:
            raise ValueError("Board status reads its switches differently on {0!r}".format(value))
        return answers.pop()

    with open(os.path.join(root, GUARD_ACTION), encoding="utf-8") as fh_:
        pause = next(st for st in yaml.safe_load(fh_)["runs"]["steps"] if st.get("id") == "pause")

    def guard(value):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "output")
            open(out, "w").close()
            env = dict(os.environ, SWITCH_VALUE=str(value or ""), SWITCH_NAME="X", GITHUB_OUTPUT=out,
                       SCRIPTS=os.path.join(root, ".github", "scripts"))
            subprocess.run(["bash", "-c", pause["run"]], check=True, capture_output=True, env=env)
            with open(out, encoding="utf-8") as fh_:
                got = fh_.read().split()
        if got not in (["paused=true"], ["paused=false"]):
            raise ValueError("pause step wrote {0!r}".format(got))
        return got == ["paused=true"]

    def feature_health(value):
        entry = [{"name": "f", "workflows": [], "kill_switch": "WING_COMMANDER_BOARD_X"}]
        got = fh.collect(entry, "own/repo", fh.parse_time("2026-11-20T00:00:00"),
                         gh=lambda *_a, **_k: [], environ={"BOARD_X": str(value or "")})
        ctx = got[2] if isinstance(got, tuple) else got
        return ctx["switches"]["WING_COMMANDER_BOARD_X"] is True

    def backlog(value):
        ok, reason = bbl.selection_gate({"backlog_lines_switch": str(value or ""), "loop_paused": False,
                                         "constitution_text": None})
        return reason != "backlog lines switch is not true"

    def backlog_paused(value):
        ok, reason = bbl.selection_gate({"backlog_lines_switch": "true", "loop_paused": str(value or ""),
                                         "constitution_text": None})
        return reason == "board loop is paused"

    # board-loop.yml's merge decision: the comparison is read from the
    # workflow line and run through real jq, so a fixed line is run as fixed.
    lines = _file_lines(root, BOARD_LOOP)
    merge_line = next((line for line in lines if "switch_on: (" in line and "$switch_on" in line), "")
    match = re.search(r"switch_on: (\(\$switch_on.*?\)),", merge_line)

    def jq_merge(value):
        if not match:
            raise ValueError("no merge-decision switch_on comparison in {0}".format(BOARD_LOOP))
        out = subprocess.run(["jq", "-n", "--arg", "switch_on", str(value or ""), match.group(1)],
                             capture_output=True, text=True, check=True).stdout.strip()
        return out == "true"

    return {
        "wc_board_status._switch_on": bs._switch_on,
        "Board status (switch_set, every reported switch)": board_status,
        "wing-commander-watch-guard pause step": guard,
        "wc_feature_health.collect": feature_health,
        "board_backlog_lines.selection_gate": backlog,
        "board_backlog_lines.selection_gate (loop paused)": backlog_paused,
        "board-loop.yml merge decision (jq)": jq_merge,
    }


def _workflow_step(root, path, job, step_id):
    import yaml
    with open(os.path.join(root, path), encoding="utf-8") as fh_:
        steps = yaml.safe_load(fh_)["jobs"][job]["steps"]
    found = [st for st in steps if st.get("id") == step_id]
    if len(found) != 1:
        raise ValueError("{0}: job {1} has {2} step(s) with id {3}".format(path, job, len(found), step_id))
    return found[0]


def _run_step(script, env):
    """Run a step's shell with only `env` (plus PATH) and GitHub's two
    output files; return (exit code, outputs, summary)."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        out, summary = os.path.join(tmp, "output"), os.path.join(tmp, "summary")
        for f in (out, summary):
            open(f, "w").close()
        full = dict(env, PATH=os.environ.get("PATH", ""), GITHUB_OUTPUT=out, GITHUB_STEP_SUMMARY=summary)
        code = subprocess.run(["bash", "-c", script], capture_output=True, env=full).returncode
        with open(out, encoding="utf-8") as fh_:
            outputs = dict(line.split("=", 1) for line in fh_.read().splitlines() if "=" in line)
        with open(summary, encoding="utf-8") as fh_:
            return code, outputs, fh_.read()


def shell_pause_readers(root):
    """#889 ("One rule for all switches"): the shell pause checks that were
    PENDING_SHELL_READERS until they followed the rule, each run as shipped:
    the step's env expression evaluated by wc_gha_expr from the variable's
    raw value, then the step's own shell (or wc_shared_review.guard) on the
    result."""
    import wc_gha_expr as gx
    import wc_shared_review as sr
    known = ("vars.", "inputs.")

    def env_of(step, key, var, value):
        ctx = {} if value is None else {"vars." + var: value}
        return gx.interpolate(step["env"][key], ctx, known)

    spec = ".github/workflows/spec-pr-review.yml"
    sel = _workflow_step(root, spec, "select", "pause")
    elig = _workflow_step(root, spec, "review", "eligible")
    elig_lines = [ln for ln in elig["run"].splitlines() if "PAUSED" in ln]
    wd = _workflow_step(root, ".github/workflows/watchdog.yml", "act", "write-suppression")
    shared = ".github/workflows/shared-pr-reviewer.yml"
    decide = _workflow_step(root, shared, "guard", "decide")
    state = _workflow_step(root, shared, "prepare", "state")
    import yaml
    with open(os.path.join(root, ".github", "workflows", "wing-commander-shared-pr-reviewer.yml"),
              encoding="utf-8") as fh_:
        relay = yaml.safe_load(fh_)["jobs"]["review"]["with"]["paused"]

    def shared_input(value):
        """The wrapper's `paused:` input as the reusable workflow receives it."""
        ctx = {} if value is None else {"vars.WING_COMMANDER_SHARED_REVIEWER_PAUSED": value}
        return {"inputs.paused": gx.interpolate(relay, ctx, known)}

    def spec_select(value):
        code, outputs, _ = _run_step(sel["run"], {"PAUSED": env_of(sel, "PAUSED", "WING_COMMANDER_SPEC_REVIEW_PAUSED",
                                                                    value)})
        if code or outputs.get("paused") not in ("true", "false"):
            raise ValueError("spec-pr-review pause step exited {0} with {1!r}".format(code, outputs))
        return outputs["paused"] == "true"

    def spec_eligible(value):
        if len(elig_lines) != 1:
            raise ValueError("spec-pr-review eligible step has {0} PAUSED line(s)".format(len(elig_lines)))
        code, _, _ = _run_step("set -uo pipefail\n" + elig_lines[0],
                               {"PAUSED": env_of(elig, "PAUSED", "WING_COMMANDER_SPEC_REVIEW_PAUSED", value)})
        return code != 0

    def watchdog(value):
        code, outputs, _ = _run_step(wd["run"], {"CAPPED": "false", "PAUSED": env_of(
            wd, "PAUSED", "WING_COMMANDER_WATCHDOG_PAUSED", value)})
        if code or outputs.get("suppressed") not in ("true", "false"):
            raise ValueError("watchdog write-suppression exited {0} with {1!r}".format(code, outputs))
        return outputs.get("reason") == "paused"

    def shared_guard(value):
        env = {"CALLER_REF": "refs/heads/main", "DEFAULT_BRANCH": "main",
               "PAUSED": gx.interpolate(decide["env"]["PAUSED"], shared_input(value), known)}
        code, outputs, _ = _run_step(decide["run"], env)
        if code or outputs.get("proceed") not in ("true", "false"):
            raise ValueError("shared-pr-reviewer guard exited {0} with {1!r}".format(code, outputs))
        return outputs["proceed"] == "false"

    def shared_prepare(value):
        paused = gx.interpolate(state["env"]["PAUSED"], shared_input(value), known)
        return sr.guard("refs/heads/main", "main", "pr", paused)[1] == "paused"

    return {
        "spec-pr-review.yml select pause step": spec_select,
        "spec-pr-review.yml review eligibility re-check": spec_eligible,
        "watchdog.yml write suppression": watchdog,
        "shared-pr-reviewer.yml guard (via the wrapper's input)": shared_guard,
        "shared-pr-reviewer.yml prepare's wc_shared_review.guard (via the wrapper's input)": shared_prepare,
    }


def reader_half():
    """#889: every switch follows the one rule (owner decision 2026-11-27).
    Each real reader runs on the same values and must give one_rule()'s
    answers; the only reader allowed to disagree is the registered
    exception, and it fails once its line changes."""
    import ast
    import inspect
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    check("jq is available to run board-loop.yml's merge comparison", shutil.which("jq") is not None)
    readers = dict(real_readers(root), **shell_pause_readers(root))
    problems = one_rule_problems(root, readers, READER_EXCEPTIONS)
    check("every switch reader follows the one switch rule, but the one registered exception",
          not problems, problems)
    check("the one exception is board-loop.yml's merge decision, tracked on #889",
          {k: v["tracker"] for k, v in READER_EXCEPTIONS.items()} == {"board-loop.yml merge decision (jq)": "#889"},
          READER_EXCEPTIONS)

    # Shown to fail: a reader that trims, one that reads only exact "true",
    # an exception whose line changed, an exception whose reader agrees, and
    # a second exception.
    trims = lambda v: str(v or "").strip().lower() == "true"  # noqa: E731
    exact = lambda v: str(v or "") == "true"  # noqa: E731
    check("a reader that trims fails the one rule",
          one_rule_problems(root, dict(readers, trimmed=trims), READER_EXCEPTIONS))
    check("a reader that reads only the exact text 'true' fails the one rule",
          one_rule_problems(root, dict(readers, exact=exact), READER_EXCEPTIONS))
    moved = {k: dict(v, line=v["line"].replace('== "true"', '| ascii_downcase == "true"'))
             for k, v in READER_EXCEPTIONS.items()}
    check("an exception whose line has changed fails", one_rule_problems(root, readers, moved))
    fixed = dict(readers, **{"board-loop.yml merge decision (jq)": one_rule})
    check("an exception whose reader now follows the rule fails",
          one_rule_problems(root, fixed, READER_EXCEPTIONS))
    check("a second exception fails",
          one_rule_problems(root, dict(readers, exact=exact),
                            dict(READER_EXCEPTIONS, exact=dict(tracker="#889", path=BOARD_LOOP, line="x"))))
    check("with no exception registered, the merge decision's disagreement fails",
          one_rule_problems(root, readers, {}))

    problems = reader_sites_problems(root, READER_SITES, READER_EXCEPTIONS)
    check("every switch's reader site still reads it by the one rule", not problems, problems)

    # Code review of #1318 (pass 2): the readers that do not follow the rule
    # yet are all registered, found from the workflows' raw relays rather
    # than from memory.
    with open(os.path.join(root, "docs", "reference.md"), encoding="utf-8") as fh:
        switch_vars = kill_switch_vars(fh.read())
    switch_vars |= {"WING_COMMANDER_" + v for k, v in bs.SWITCH_ENV.items() if k != "tasks_review"}
    check("docs/reference.md's Kill switches table is read", len(switch_vars) > len(bs.SWITCH_ENV), switch_vars)
    problems = relay_problems(root, switch_vars, PENDING_SHELL_READERS, ONE_RULE_RELAYS)
    check("every raw relay of a switch reaches a one-rule reader or a registered pending reader",
          not problems, problems)
    check("an unregistered exact shell reader fails the relay check",
          relay_problems(root, switch_vars, PENDING_SHELL_READERS[:-1], ONE_RULE_RELAYS))
    check("a pending reader whose relay is gone fails the relay check",
          relay_problems(root, switch_vars, PENDING_SHELL_READERS
                         + (("board-status.yml", "WING_COMMANDER_NO_SUCH_SWITCH", "board-status.yml"),),
                         ONE_RULE_RELAYS))
    drifted = dict(READER_SITES, board_auto_merge=[(BOARD_LOOP, "switch_on: ($switch_on | ascii_downcase == \"true\")")])
    check("a drifted reader site fails the tie", reader_sites_problems(root, drifted, READER_EXCEPTIONS))
    check("an exact comparison that is not the exception's line fails the tie",
          reader_sites_problems(root, READER_SITES, {}))
    check("a switch with no reader site fails the tie",
          reader_sites_problems(root, {k: v for k, v in READER_SITES.items() if k != "proof_list_paused"},
                                READER_EXCEPTIONS))

    # Everything in wc_board_status reads a switch through switch_set().
    tree = ast.parse(inspect.getsource(bs))
    direct = sorted({node.lineno for top in tree.body if getattr(top, "name", None) != "switch_set"
                     for node in ast.walk(top) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == "_switch_on"})
    check("wc_board_status reads no switch with _switch_on but through switch_set", not direct, direct)

    # The rule as Board status shows it.
    shown = bs.render(dict(SNAP, switches=dict(SNAP["switches"], board_can_push_workflows="True")))
    check("board can-push-workflows set to 'True' renders on, as GitHub's comparison reads it",
          "workflow-file fixes allowed" in shown, shown)
    padded = rows_by_number(bs.classify(dict(SNAP, switches=dict(SNAP["switches"], lifecycle_auto_merge="true ")))
                            ["owner"])
    check("a padded lifecycle auto-merge leaves the final PR with the owner, as the gate's if: reads it",
          675 in padded, padded.get(675))
    cased = rows_by_number(bs.classify(dict(SNAP, switches=dict(SNAP["switches"], lifecycle_auto_merge="TRUE")))
                           ["pipeline"])
    check("lifecycle auto-merge set to 'TRUE' hands the final PR to the review gate", 675 in cased, cased.get(675))


def docs_half():
    """#889: docs/setup.md says where Board status reports each switch. The
    switches render() states are read from its own state() calls, so a
    switch added to the status lines without a setup.md mention fails here:
    the Board status row must name every one, and each switch's own row must
    say the issue reports it."""
    import inspect
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, "docs", "setup.md"), encoding="utf-8") as fh:
        rows = {m.group(1): m.group(0) for m in
                re.finditer(r"^\| `(WING_COMMANDER_[A-Z_]+)` \|.*$", fh.read(), re.M)}
    keys = re.findall(r'\bstate\("([a-z_]+)"', inspect.getsource(bs.render))
    check("render() states at least the board-loop and auto-release switches",
          {"board_loop_paused", "board_auto_merge", "auto_release_paused"} <= set(keys), keys)
    status_row = rows.get("WING_COMMANDER_BOARD_STATUS_PAUSED", "")
    for key in keys:
        var = "WING_COMMANDER_" + bs.SWITCH_ENV[key]
        check("docs/setup.md's Board status row names {0}".format(var),
              "`{0}`".format(var) in status_row, status_row[:120])
        check("docs/setup.md's {0} row says Board status reports it".format(var),
              'The "Board status" issue reports this switch' in rows.get(var, ""), rows.get(var, "")[-160:])

    # #889 (code review of #1301): docs/reference.md names the switches
    # Board status reports, in its board-status.yml row and its Known
    # limits line, rather than calling them "the merge switches".
    with open(os.path.join(root, "docs", "reference.md"), encoding="utf-8") as fh:
        reference = fh.read()
    check("docs/reference.md no longer calls Board status's switch lines the merge switches",
          "merge switches" not in reference)
    ref_row = next((line for line in reference.splitlines() if line.startswith("| `board-status.yml` |")), "")
    limits = reference.split("## Known limits", 1)[-1]
    limit = next((item for item in re.split(r"\n- ", limits) if '"Board status" issue shows' in item), "")
    for key in keys:
        var = "`WING_COMMANDER_{0}`".format(bs.SWITCH_ENV[key])
        check("docs/reference.md's board-status.yml row names {0}".format(var), var in ref_row, ref_row[:160])
        check("docs/reference.md's Known limits line names {0}".format(var), var in limit, limit[:200])

    # Code review of #1318: the Kill switches section names every reader that
    # does not follow the one switch rule yet -- the registered exception and
    # the shell pause re-checks the #889 line "One rule for all switches"
    # tracks -- rather than claiming a single one. Drop an entry here with
    # its fix.
    kill = reference.split("## Kill switches", 1)[-1].split("\n## ", 1)[0]
    kill_flat = " ".join(kill.split())
    pending = [(ex["path"].rsplit("/", 1)[-1], "WING_COMMANDER_BOARD_AUTO_MERGE")
               for ex in READER_EXCEPTIONS.values()] + [(reader, var) for _r, var, reader in PENDING_SHELL_READERS]
    for path, var in pending:
        check("docs/reference.md's Kill switches section names {0}'s reader of {1}".format(path, var),
              "`{0}`".format(path) in kill_flat and "`{0}`".format(var) in kill_flat, kill_flat[:400])
    # Code review of #1329: and names no other, so a reader brought under
    # the rule leaves that list with its PENDING_SHELL_READERS entry.
    problems = pending_docs_problems(kill_flat, pending)
    check("docs/reference.md's not-yet list names only the readers still pending", not problems, problems)
    check("a reader the not-yet list still names after its fix fails",
          pending_docs_problems(kill_flat, pending[:-1]))

    # Code review of #1329 (pass 2): shared-pr-reviewer.yml's `paused` input
    # now follows the rule (owner decision on #890 accepting the narrowed
    # input), and the contract that names the input says which values pause.
    with open(os.path.join(root, "specs", "127-shared-pr-reviewer", "contracts", "round-record.md"),
              encoding="utf-8") as fh:
        contract = " ".join(fh.read().split())
    check("specs/127's round-record.md says the paused flag follows the one switch rule",
          re.search(r"paused flag \([^)]*one switch rule", contract) is not None,
          contract[contract.find("paused flag"):][:200])


def main():
    render_half()
    runtime_half()
    switches_half()
    reader_half()
    docs_half()
    proof_list_half()
    merge_evidence_half()
    feature_health_half()
    fit_half()
    path_half()
    print("verify-board-status: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
