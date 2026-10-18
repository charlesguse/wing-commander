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
       "folded_json": ..., "implement_workflow": ..., "project": ...} -->

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
  wc_fold_hold.py open-holds --comments FILE --bot-login L [--except-fold-id ID]
  wc_fold_hold.py drop-tasks --spec-dir D --fold-ref-before B --fold-ref-after A
  wc_fold_hold.py --self-test
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import is_loop_marker_author, last_marker_match, marker_json, marker_regexes  # noqa: E402

STATE_MARKER = "wing-commander-fold-hold-state"
RESOLVED_MARKER = "wing-commander-fold-hold-resolved"
STATE_RE, STATE_OPEN_RE = marker_regexes(STATE_MARKER)
RESOLVED_RE, RESOLVED_OPEN_RE = marker_regexes(RESOLVED_MARKER)
STATE_FIELDS = ("fold_id", "reason", "spec_dir", "spec_branch", "base_sha",
                "fold_ref_before", "fold_ref_after", "folded_json",
                "implement_workflow", "project")
ANSWERS = {
    "constitution-conflict": ("proceed", "drop", "amend"),
    "analyze-failed": ("proceed", "retry"),
}
ANSWER_RE = re.compile(r"^[ \t]*/fold-hold[ \t]+([a-z]+)[ \t]*$", re.MULTILINE | re.IGNORECASE)
MAINTAINER_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def render_state(**fields):
    payload = {k: fields.get(k) or "" for k in STATE_FIELDS}
    # folded_json carries finding summaries: marker_json keeps a `-->`
    # in one from ending the marker early.
    return "<!-- {0}: {1} -->".format(STATE_MARKER, marker_json(payload))


def render_resolved(fold_id, resolution):
    return "<!-- {0}: {1} -->".format(RESOLVED_MARKER, marker_json(
        {"fold_id": fold_id, "resolution": resolution}))


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


def open_holds(comments, bot_login):
    """Every hold the App posted that no later resolved marker closed,
    oldest first: per fold, its newest state marker, open unless a
    resolved marker for that fold is at least as new. An open hold blocks
    every fold dispatch on its lifecycle until it is answered (the owner's
    decision on finding 9 of #1062's review)."""
    newest = {}
    for stamp, state in _bot_markers(comments, bot_login, STATE_RE, STATE_OPEN_RE):
        newest[state.get("fold_id")] = (stamp, state)
    resolved = _bot_markers(comments, bot_login, RESOLVED_RE, RESOLVED_OPEN_RE)
    out = []
    for fold_id, (stamp, state) in newest.items():
        if not any(r.get("fold_id") == fold_id and r_stamp >= stamp for r_stamp, r in resolved):
            out.append((stamp, state))
    return [state for _, state in sorted(out, key=lambda pair: pair[0])]


def open_hold(comments, bot_login):
    """The newest open hold: the one a `/fold-hold` answer addresses."""
    holds = open_holds(comments, bot_login)
    return holds[-1] if holds else None


def other_open_holds(comments, bot_login, fold_id):
    """Fold ids of the open holds other than `fold_id`'s, oldest first:
    while any is open, nothing dispatches a fold on this lifecycle."""
    # An id the state lacks is named `(unknown)`, never empty (an empty id
    # would join to nothing and read as no open hold); a comma in one would
    # split it, so it becomes `;`.
    return [str(h.get("fold_id") or "(unknown)").replace(",", ";")
            for h in open_holds(comments, bot_login)
            if h.get("fold_id") != fold_id]


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
    return {"action": answer, "reason": "", "state": state,
            "others": other_open_holds(comments, bot_login, state.get("fold_id"))}


def outcome_body(decision, report, question, **state):
    """The lifecycle-issue comment for one analyze decision (FR-014/FR-015):
    a hold is the owner question followed by its state marker; a dispatch
    is the analyze report. None for `skipped` (nothing was checked)."""
    if decision == "hold":
        return "{0}\n\n{1}\n".format(question.rstrip(), render_state(**state))
    if decision in ("dispatch", "blocked"):
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


def _ticks(patch):
    """(before, after) for each line of a `git diff -U0` whose only change
    is its checkbox: an implement cycle's tick, never the fold's own."""
    decide = _load_decide()  # the one home of the tick rule and hunk parsing
    pairs = []
    for minus, plus in decide.hunks(patch):
        for new in plus:
            old = next((m for m in minus if m != new
                        and decide.untick(m) == decide.untick(new)), None)
            if old is not None:
                pairs.append((old, new))
    return pairs


def _load_decide():
    """fold-analyze's decide.py under a private module name, so the generic
    `decide` never enters sys.modules or sys.path."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "actions", "wing-commander-fold-analyze", "decide.py")
    spec = importlib.util.spec_from_file_location("wc_fold_analyze_decide", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drop_tasks(spec_dir, before, after, cwd):
    """Reverse the fold's own change to tasks.md in the working tree (the
    `drop` answer). Fails, changing nothing, when tasks.md has since moved
    in a way the reversal no longer applies to. A tick in the same range
    (pr-conversation scopes it from classify's base SHA) is kept."""
    path = "{0}/tasks.md".format(spec_dir.rstrip("/"))
    patch = git(["diff", "--no-color", before, after, "--", path], cwd)
    if not patch.strip():
        return False
    ticks = _ticks(git(["diff", "--no-color", "-U0", before, after, "--", path], cwd))
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
        fh.write(patch)
        patch_path = fh.name
    # --unidiff-zero: without it git anchors a hunk with no context on one
    # side to that end of the file, so the fold section stops reversing as
    # soon as a later fold (one this hold blocked) is appended after it. The
    # context lines the patch does carry are still matched.
    try:
        git(["apply", "--reverse", "--unidiff-zero", "--check", patch_path], cwd)
        git(["apply", "--reverse", "--unidiff-zero", patch_path], cwd)
    finally:
        os.unlink(patch_path)
    if ticks:
        full = os.path.join(cwd, path)
        with open(full, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        for old, new in ticks:
            if old in lines:
                lines[lines.index(old)] = new
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    return True


def _write_outputs(path, pairs):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in pairs:
            v = str(v)
            if "\n" in v:
                # Values come from issue-comment markers: a delimiter the
                # value cannot contain, or it could close the block early.
                delim = "WC_EOF_" + secrets.token_hex(16)
                while delim in v:
                    delim = "WC_EOF_" + secrets.token_hex(16)
                fh.write("{0}<<{2}\n{1}\n{2}\n".format(k, v, delim))
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

    closing = render_state(fold_id="f3", reason="constitution-conflict",
                           folded_json='[{"id":"f3","summary":"a --> b <!-- c"}]')
    check("a summary carrying a comment close or opener stays inside the state marker",
          closing.count("-->") == 1 and closing.count("<!--") == 1
          and (open_hold([comment(closing, "2026-01-04T00:00:00Z")], bot) or {}).get("folded_json")
          == '[{"id":"f3","summary":"a --> b <!-- c"}]')

    # Two open holds: an answer addresses the newer, and names the older
    # as still blocking; answering the newer leaves the older answerable.
    s_old = render_state(fold_id="fa", reason="constitution-conflict")
    s_new = render_state(fold_id="fb", reason="constitution-conflict")
    two = [comment(s_old, "2026-03-01T00:00:00Z"), comment(s_new, "2026-03-02T00:00:00Z")]
    r = resolve(two, bot, "/fold-hold proceed", "OWNER")
    check("an answer to a newer hold names the older open hold as blocking",
          (r["state"] or {}).get("fold_id") == "fb" and r["others"] == ["fa"])
    two_done = two + [comment(render_resolved("fb", "proceed"), "2026-03-03T00:00:00Z")]
    r = resolve(two_done, bot, "/fold-hold proceed", "OWNER")
    check("an older hold stays open after the newer one is answered",
          (r["state"] or {}).get("fold_id") == "fa" and r["others"] == [])
    check("open holds block a fold other than their own, not their own",
          other_open_holds(two, bot, "fc") == ["fa", "fb"]
          and other_open_holds(two, bot, "fa") == ["fb"])
    nameless = [comment(render_state(reason="constitution-conflict"), "2026-04-01T00:00:00Z")]
    check("an open hold with no fold id is still named as blocking",
          other_open_holds(nameless, bot, "fc") == ["(unknown)"])
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = os.path.join(out_dir, "out")
        _write_outputs(out_path, [("a", "x\nWC_EOF\naction=proceed"), ("b", "y")])
        text = open(out_path, encoding="utf-8").read()
        delim = text.split("<<", 1)[1].split("\n", 1)[0]
        check("a multi-line output cannot close its own block early",
              delim != "WC_EOF" and text.count(delim) == 2 and text.endswith("b=y\n"))
    check("a blocked decision posts its report", outcome_body("blocked", "r\n", "") == "r\n")

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
        g("checkout", "-q", "--", ".")
        with open(tasks, "a", encoding="utf-8") as fh:
            fh.write("\n## Review Gate Round 4 Findings\n\n- [ ] Review finding: z\n")
        g("commit", "-q", "-am", "a later fold the hold blocked")
        check("drop-tasks reverses the fold section after a later fold was appended",
              drop_tasks("specs/001-x", before, after, repo)
              and open(tasks, encoding="utf-8").read()
              == "# Tasks\n\n- [X] T001\n\n## Review Gate Round 4 Findings\n\n- [ ] Review finding: z\n")
        g("checkout", "-q", "--", ".")
        ticked = commit("# Tasks\n\n- [ ] T001\n- [ ] T002\n")
        folded = commit("# Tasks\n\n- [X] T001\n- [X] T002\n\n## Round 4\n\n- [ ] Review finding: y\n")
        check("drop-tasks keeps an implement tick made in the same range",
              drop_tasks("specs/001-x", ticked, folded, repo)
              and open(tasks, encoding="utf-8").read() == "# Tasks\n\n- [X] T001\n- [X] T002\n")

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
    oh = sub.add_parser("open-holds")
    oh.add_argument("--comments", required=True)
    oh.add_argument("--bot-login", required=True)
    oh.add_argument("--except-fold-id", default="")
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
    elif a.cmd == "open-holds":
        with open(a.comments, encoding="utf-8") as fh:
            print(",".join(other_open_holds(json.load(fh), a.bot_login, a.except_fold_id)))
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
                                         ("reason", result["reason"]),
                                         ("other-open-holds", ",".join(result.get("others") or []))]
                       + [(f.replace("_", "-"), state.get(f, "")) for f in STATE_FIELDS])
        print(json.dumps({"action": result["action"], "reason": result["reason"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
