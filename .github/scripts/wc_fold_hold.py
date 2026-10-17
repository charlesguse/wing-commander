#!/usr/bin/env python3
"""Fold hold state and its release (specs/116-review-convergence-analyze,
contracts/fold-analyze.md "Hold protocol", research.md D9, T025).

When the fold-time analyze check holds a fold (a constitution conflict, or
a check that failed), the caller posts the owner question on the lifecycle
issue -- it already carries `<!-- wing-commander-fold-hold: fold=<id> -->`
-- followed by a hold-state marker this module renders, holding what a
later release needs to dispatch the fold without re-deriving anything:

  <!-- wing-commander-fold-hold-state: {"fold_id": ..., "reason": ...,
       "spec_dir": ..., "spec_branch": ..., "base_sha": ...,
       "fold_ref_before": ..., "fold_ref_after": ...,
       "folded_json": ..., "implement_workflow": ...} -->

A maintainer releases it with an ordinary comment on the issue (constitution
III): a line reading `/fold-hold <answer>`. Which answers a hold accepts
depends on why it held (FR-013, FR-014):

  constitution-conflict   proceed | drop | amend
  analyze-failed          proceed | retry

The release job (wing-commander-fold-hold.yml) resolves the answer through
`resolve` -- deterministic code, never an agent (constitution IX) -- and
records the outcome with a resolved marker so a hold is released once:

  <!-- wing-commander-fold-hold-resolved: {"fold_id": ..., "resolution": ...} -->

`amend` is recorded but dispatches nothing: the lifecycle waits for the
spec amendment, and the owner answers `proceed` once it has landed. `retry`
re-runs the analyze check, which posts a fresh outcome (and, on another
hold, a fresh question with its own state marker).

CLI:
  wc_fold_hold.py state --fold-id ... --reason ... (one flag per field)
  wc_fold_hold.py resolve --comments FILE --bot-login L --body-file F
                          --association A [--github-output PATH]
  wc_fold_hold.py resolved-marker --fold-id ID --resolution R
  wc_fold_hold.py post-outcome --issue N --decision D --report-file F
                               --question-file F [state flags]
  wc_fold_hold.py drop-tasks --spec-dir D --fold-ref-before B --fold-ref-after A
  wc_fold_hold.py --self-test
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import is_loop_marker_author, last_marker_match, marker_regexes  # noqa: E402

STATE_MARKER = "wing-commander-fold-hold-state"
RESOLVED_MARKER = "wing-commander-fold-hold-resolved"
STATE_RE, STATE_OPEN_RE = marker_regexes(STATE_MARKER)
RESOLVED_RE, RESOLVED_OPEN_RE = marker_regexes(RESOLVED_MARKER)
STATE_FIELDS = ("fold_id", "reason", "spec_dir", "spec_branch", "base_sha",
                "fold_ref_before", "fold_ref_after", "folded_json",
                "implement_workflow")
ANSWERS = {
    "constitution-conflict": ("proceed", "drop", "amend"),
    "analyze-failed": ("proceed", "retry"),
}
ANSWER_RE = re.compile(r"^[ \t]*/fold-hold[ \t]+([a-z]+)[ \t]*$", re.MULTILINE | re.IGNORECASE)
MAINTAINER_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def render_state(**fields):
    payload = {k: fields.get(k) or "" for k in STATE_FIELDS}
    return "<!-- {0}: {1} -->".format(STATE_MARKER, json.dumps(payload, sort_keys=True))


def render_resolved(fold_id, resolution):
    return "<!-- {0}: {1} -->".format(RESOLVED_MARKER, json.dumps(
        {"fold_id": fold_id, "resolution": resolution}, sort_keys=True))


def _bot_markers(comments, bot_login, marker_re, open_re):
    """(created_at, payload) for every App-authored marker of one shape."""
    out = []
    for c in comments or []:
        if not isinstance(c, dict) or not is_loop_marker_author(c, bot_login):
            continue
        match = last_marker_match(c.get("body") or "", marker_re, open_re)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(payload, dict):
            out.append((c.get("created_at") or "", payload))
    return sorted(out, key=lambda pair: pair[0])


def open_hold(comments, bot_login):
    """The newest hold the App posted that no later resolved marker closed."""
    states = _bot_markers(comments, bot_login, STATE_RE, STATE_OPEN_RE)
    if not states:
        return None
    stamp, state = states[-1]
    for r_stamp, resolved in _bot_markers(comments, bot_login, RESOLVED_RE, RESOLVED_OPEN_RE):
        if resolved.get("fold_id") == state.get("fold_id") and r_stamp >= stamp:
            return None
    return state


def parse_answer(body):
    """The last `/fold-hold <answer>` line in a comment body, lowercased."""
    found = ANSWER_RE.findall(body or "")
    return found[-1].lower() if found else None


def resolve(comments, bot_login, body, association):
    """-> {action, reason, state}. action is one of the hold's accepted
    answers, or `ignore` (not an answer, no open hold, or not a maintainer)
    or `reject` (an answer this hold does not accept)."""
    answer = parse_answer(body)
    if answer is None:
        return {"action": "ignore", "reason": "no /fold-hold answer line", "state": None}
    if association not in MAINTAINER_ASSOCIATIONS:
        return {"action": "ignore", "reason": "the commenter is not a maintainer", "state": None}
    state = open_hold(comments, bot_login)
    if state is None:
        return {"action": "ignore", "reason": "no open fold hold on this issue", "state": None}
    accepted = ANSWERS.get(state.get("reason"), ())
    if answer not in accepted:
        return {"action": "reject", "state": state,
                "reason": "`{0}` is not an answer to a {1} hold; it accepts {2}".format(
                    answer, state.get("reason") or "(unknown)",
                    ", ".join("`/fold-hold {0}`".format(a) for a in accepted) or "nothing")}
    return {"action": answer, "reason": "", "state": state}


def outcome_body(decision, report, question, **state):
    """The lifecycle-issue comment for one analyze decision (FR-014/FR-015):
    a hold is the owner question followed by its state marker; a dispatch
    is the analyze report. None for `skipped` (nothing was checked)."""
    if decision == "hold":
        return "{0}\n\n{1}\n".format(question.rstrip(), render_state(**state))
    if decision == "dispatch":
        return report.rstrip() + "\n"
    return None


def post_outcome(issue, decision, report_file, question_file, **state):
    """Posts outcome_body() on the lifecycle issue with `gh` (GH_TOKEN from
    the caller's environment: the App token). The one home of the posting
    the fold-analyze callers and the hold-release job share."""
    def read(path):
        if not path or not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    body = outcome_body(decision, read(report_file), read(question_file), **state)
    if body is None:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        body_path = fh.name
    try:
        subprocess.run(["gh", "issue", "comment", str(issue), "-R",
                        os.environ["GITHUB_REPOSITORY"], "--body-file", body_path], check=True)
    finally:
        os.unlink(body_path)
    return True


def git(args, cwd):
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("wc_fold_hold: git {0} failed: {1}".format(" ".join(args), out.stderr.strip()))
    return out.stdout


def drop_tasks(spec_dir, before, after, cwd):
    """Reverse the fold's own change to tasks.md in the working tree (the
    `drop` answer). Fails, changing nothing, when tasks.md has since moved
    in a way the reversal no longer applies to."""
    path = "{0}/tasks.md".format(spec_dir.rstrip("/"))
    patch = git(["diff", "--no-color", before, after, "--", path], cwd)
    if not patch.strip():
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
        fh.write(patch)
        patch_path = fh.name
    try:
        git(["apply", "--reverse", "--check", patch_path], cwd)
        git(["apply", "--reverse", patch_path], cwd)
    finally:
        os.unlink(patch_path)
    return True


def _write_outputs(path, pairs):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in pairs:
            v = str(v)
            if "\n" in v:
                fh.write("{0}<<WC_EOF\n{1}\nWC_EOF\n".format(k, v))
            else:
                fh.write("{0}={1}\n".format(k, v))


def self_test():
    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)
        print(("PASS " if cond else "FAIL ") + name)

    bot = "wing-commander-bot[bot]"

    def comment(body, stamp, login=bot, kind="Bot"):
        return {"body": body, "created_at": stamp, "user": {"login": login, "type": kind}}

    state = render_state(fold_id="f1", reason="constitution-conflict", spec_dir="specs/001-x",
                         spec_branch="spec/001-x", base_sha="a", fold_ref_before="b",
                         fold_ref_after="c", folded_json='[{"id":"f1","summary":"s"}]',
                         implement_workflow="wing-commander-5-implement.yml")
    held = [comment("question\n\n" + state, "2026-01-01T00:00:00Z")]
    check("proceed releases a constitution-conflict hold",
          resolve(held, bot, "/fold-hold proceed", "OWNER")["action"] == "proceed")
    check("drop and amend are accepted for a constitution-conflict hold",
          [resolve(held, bot, "/fold-hold " + a, "MEMBER")["action"] for a in ("drop", "amend")]
          == ["drop", "amend"])
    check("retry is rejected for a constitution-conflict hold",
          resolve(held, bot, "/fold-hold retry", "OWNER")["action"] == "reject")
    check("a non-maintainer's answer is ignored",
          resolve(held, bot, "/fold-hold proceed", "NONE")["action"] == "ignore")
    check("a comment with no answer line is ignored",
          resolve(held, bot, "please proceed", "OWNER")["action"] == "ignore")
    check("the answer must be on its own line",
          resolve(held, bot, "do not /fold-hold proceed yet", "OWNER")["action"] == "ignore")
    forged = [comment("question\n\n" + state, "2026-01-01T00:00:00Z", login="someone", kind="User")]
    check("a hold-state marker a human posted is not a hold",
          resolve(forged, bot, "/fold-hold proceed", "OWNER")["action"] == "ignore")
    resolved = held + [comment(render_resolved("f1", "proceed"), "2026-01-02T00:00:00Z")]
    check("a resolved hold is released once",
          resolve(resolved, bot, "/fold-hold proceed", "OWNER")["action"] == "ignore")
    failed_state = state.replace("constitution-conflict", "analyze-failed")
    rehold = resolved + [comment("q2\n\n" + failed_state.replace('"f1"', '"f2"'), "2026-01-03T00:00:00Z")]
    check("a later hold is open again, and an analyze-failed hold takes retry",
          resolve(rehold, bot, "/fold-hold retry", "OWNER")["action"] == "retry")
    check("an analyze-failed hold rejects drop",
          resolve(rehold, bot, "/fold-hold drop", "OWNER")["action"] == "reject")

    body = outcome_body("hold", "", "<!-- wing-commander-fold-hold: fold=f1 -->\nq", fold_id="f1",
                        reason="constitution-conflict", spec_dir="specs/001-x")
    check("a hold body is the question followed by a state marker open_hold() reads back",
          body.startswith("<!-- wing-commander-fold-hold: fold=f1 -->")
          and (open_hold([comment(body, "2026-02-01T00:00:00Z")], bot) or {}).get("spec_dir")
          == "specs/001-x")
    check("a dispatch body is the report alone",
          outcome_body("dispatch", "report\n", "q") == "report\n")
    check("a skipped decision posts nothing", outcome_body("skipped", "r", "q") is None)

    with tempfile.TemporaryDirectory() as repo:
        def g(*args):
            return git(["-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false"] + list(args), repo).strip()

        os.makedirs(os.path.join(repo, "specs", "001-x"))
        tasks = os.path.join(repo, "specs", "001-x", "tasks.md")

        def commit(text):
            with open(tasks, "w", encoding="utf-8") as fh:
                fh.write(text)
            g("add", "-A")
            g("commit", "-q", "-m", "c")
            return g("rev-parse", "HEAD")

        g("init", "-q", "-b", "main")
        before = commit("# Tasks\n\n- [X] T001\n")
        after = commit("# Tasks\n\n- [X] T001\n\n## Review Gate Round 3 Findings\n\n- [ ] Review finding: x\n")
        check("drop-tasks reverses the fold section", drop_tasks("specs/001-x", before, after, repo)
              and open(tasks, encoding="utf-8").read() == "# Tasks\n\n- [X] T001\n")
        check("drop-tasks with no fold change reports nothing to drop",
              drop_tasks("specs/001-x", after, after, repo) is False)

    print("{0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--self-test"]:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("state")
    for field in STATE_FIELDS:
        st.add_argument("--" + field.replace("_", "-"), default="")
    rs = sub.add_parser("resolve")
    rs.add_argument("--comments", required=True)
    rs.add_argument("--bot-login", required=True)
    rs.add_argument("--body-file", required=True)
    rs.add_argument("--association", required=True)
    rs.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    rm = sub.add_parser("resolved-marker")
    rm.add_argument("--fold-id", required=True)
    rm.add_argument("--resolution", required=True)
    po = sub.add_parser("post-outcome")
    po.add_argument("--issue", required=True)
    po.add_argument("--decision", required=True)
    po.add_argument("--report-file", default="")
    po.add_argument("--question-file", default="")
    for field in STATE_FIELDS:
        if field != "reason":
            po.add_argument("--" + field.replace("_", "-"), default="")
    po.add_argument("--hold-reason", default="")
    dt = sub.add_parser("drop-tasks")
    dt.add_argument("--spec-dir", required=True)
    dt.add_argument("--fold-ref-before", required=True)
    dt.add_argument("--fold-ref-after", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "state":
        print(render_state(**dict((f, getattr(a, f)) for f in STATE_FIELDS)))
    elif a.cmd == "resolved-marker":
        print(render_resolved(a.fold_id, a.resolution))
    elif a.cmd == "post-outcome":
        state = dict((f, getattr(a, f)) for f in STATE_FIELDS if f != "reason")
        posted = post_outcome(a.issue, a.decision, a.report_file, a.question_file,
                              reason=a.hold_reason, **state)
        print("posted" if posted else "nothing-to-post")
    elif a.cmd == "drop-tasks":
        changed = drop_tasks(a.spec_dir, a.fold_ref_before, a.fold_ref_after, os.getcwd())
        print("dropped" if changed else "nothing-to-drop")
    else:
        with open(a.comments, encoding="utf-8") as fh:
            comments = json.load(fh)
        with open(a.body_file, encoding="utf-8") as fh:
            body = fh.read()
        result = resolve(comments, a.bot_login, body, a.association)
        state = result["state"] or {}
        _write_outputs(a.github_output, [("action", result["action"]),
                                         ("reason", result["reason"])]
                       + [(f.replace("_", "-"), state.get(f, "")) for f in STATE_FIELDS])
        print(json.dumps({"action": result["action"], "reason": result["reason"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
