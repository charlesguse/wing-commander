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
    check("the waiting-on-you count is in its heading", "### Waiting on you (9)" in body, body)
    check("PRs outside any lifecycle are named", "not part of a lifecycle: #909" in body, body)
    check("the roadmap is linked", "Roadmap issue, #890" in body, body)
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
        gh_issue(889, ["disposition:tracking"], "Maintenance backlog", "- [ ] a\n- [x] b\n  - [ ] c\n"),
        gh_issue(890, ["disposition:tracking"], "Roadmap"),
        gh_issue(920, ["disposition:tracking"], "Board status", status_body, "Bot"),
    ], [
        gh_issue(741, ["spec-request", "stage:clarify", "spec:098-a"], login="the-author"),
        gh_issue(742, ["spec-request", "stage:clarify", "spec:098-b"], login="the-author"),
        gh_issue(821, ["spec:074-x"], pr=True),
    ])

    def comment(user_type, association="NONE", login="x"):
        return {"user": {"type": user_type, "login": login}, "author_association": association}

    # 741: the bot asked last, then a passer-by commented -- still waiting.
    page("repos/o/r/issues/741/comments?per_page=100",
         [comment("User", "OWNER"), comment("Bot")], [comment("User", "NONE")])
    # 742: the issue's own author answered after the bot.
    page("repos/o/r/issues/742/comments?per_page=100",
         [comment("Bot")], [comment("User", "NONE", "the-author")])
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
              snap["maintenance"] == {"number": 889, "open": 2, "done": 1}, snap["maintenance"])
        check("snapshot finds the roadmap", snap["roadmap_number"] == 890, snap["roadmap_number"])
        clar = {i["number"]: i for i in snap["issues"] if i["number"] in (741, 742)}
        check("a passer-by's comment after the bot's questions answers nothing",
              clar.get(741, {}).get("last_comment_by_bot") is True, clar.get(741))
        check("the issue's own author answering after the bot is an answer",
              clar.get(742, {}).get("last_comment_by_bot") is False, clar.get(742))
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


def main():
    render_half()
    runtime_half()
    print("verify-board-status: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
