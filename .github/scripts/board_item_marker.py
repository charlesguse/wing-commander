#!/usr/bin/env python3
"""Board item marker read/write (specs/057-autonomous-board-loop,
contracts/board-item-marker.md, data-model.md "Board Item Marker",
research.md D21).

The marker is a fast path only: every field it supplies MUST be re-derived
from live GitHub state before any durable action is taken (FR-054). This
module only reads/writes the marker's own HTML-comment shape -- it never
decides whether a re-derivation contradicts it.

Only a marker on a comment the loop's own GitHub App posted is read
(is_loop_marker_author(), issue #555). Anyone can comment on a public
repository's issue, so a marker in any other comment is ignored.

Within one such comment only the LAST marker counts (last_marker_match(),
issue #580). The loop's comments embed agent text (a triage proposal, a
review finding title) and always end with write_marker()'s own output, so
a marker-shaped string in the agent text always comes before the real one.
"""
import argparse
import json
import os
import re
import subprocess
import sys

def marker_regexes(name):
    """Builds the (marker_re, open_re) pair for a marker named `name`,
    embedded as an HTML comment `<!-- <name>: {...} -->` in one of this
    App's own issue comments. This module's own MARKER_RE/MARKER_OPEN_RE
    (the board item marker) are `marker_regexes("wing-commander-board-item")`;
    a second marker shape (spec 062's lifecycle review gate state,
    wc_lifecycle_review_marker.py) is this function's second caller,
    reusing find_latest_marker() below rather than re-deriving the same
    "latest bot comment, last opener wins" algorithm a second time
    (CLAUDE.md's single-home rule)."""
    marker_re = re.compile(
        r"<!--\s*" + re.escape(name) + r":\s*(\{.*?\})\s*-->", re.DOTALL)
    open_re = re.compile(r"<!--\s*" + re.escape(name) + r":")
    return marker_re, open_re


MARKER_RE, MARKER_OPEN_RE = marker_regexes("wing-commander-board-item")


def last_marker_match(body, marker_re=MARKER_RE, open_re=MARKER_OPEN_RE):
    """The marker_re match that starts at the LAST marker opener in `body`,
    or None (issue #580). The one rule every marker reader uses.

    Not the first match: agent text earlier in the same bot comment could
    carry a marker of its own. Not simply the last of marker_re.finditer()
    either: an unclosed opener in the agent text would make the lazy match
    run on into the real marker and swallow it. write_marker()'s output is
    always the end of the loop's comment, so its opener is the last one."""
    body = body or ""
    start = None
    for opener in open_re.finditer(body):
        start = opener.start()
    if start is None:
        return None
    return marker_re.match(body, start)


def is_loop_marker_author(comment, bot_login):
    """True when `comment` was posted by the board loop's own GitHub App:
    `user.type == "Bot"` AND `user.login == bot_login` (the caller's
    `<app-slug>[bot]`, from wing-commander-context's `bot-slug` output).
    An empty/missing bot_login matches nothing. The one author predicate
    for what the loop reads back from its own comments: the board item
    marker (read_marker*, issue #555) and the stop check's `**Run:**`
    announcement (board_stop_check.find_stop_request(), issue #547)."""
    user = comment.get("user") or {}
    return bool(bot_login) and user.get("type") == "Bot" and user.get("login") == bot_login


def is_loop_branch(branch, issue_number):
    """True when `branch` is a name the fix job cuts for `issue_number`:
    `fix/<issue>-<slug>`, the slug being the title lowercased, reduced to
    [a-z0-9-] and cut to 40 characters (or `issue`). The resume step adopts
    a marker's branch only when this holds (issue #555)."""
    if not branch or not str(issue_number).isdigit():
        return False
    pattern = r"fix/{0}-[a-z0-9-]{{1,40}}".format(int(issue_number))
    return re.fullmatch(pattern, branch) is not None


def find_latest_marker(issue_comments, bot_login, marker_re=MARKER_RE, open_re=MARKER_OPEN_RE):
    """issue_comments: a list of {"created_at": "...", "body": "...",
    "user": {"login": "...", "type": "..."}} dicts (an issue's own
    comments, any order). bot_login: the loop's own App login
    (`<slug>[bot]`); required. Returns (created_at, marker) for the most
    recent well-formed marker of the (marker_re, open_re) shape
    (marker_regexes()) in a comment that is_loop_marker_author() accepts --
    each comment's last_marker_match(), never an earlier marker in the same
    comment -- or None when no such comment carries one, or the newest one
    is not valid JSON (missing/unparsable marker -- degrade to None, never
    raise; the caller falls back to live GitHub state per FR-054).

    read_marker_with_timestamp() below is this function specialized to
    this module's own MARKER_RE/MARKER_OPEN_RE (the board item marker);
    wc_lifecycle_review_marker.py calls this function directly with its
    own marker_regexes() pair (spec 062's review_gate state) rather than
    re-deriving the same "latest bot comment, last opener wins" loop."""
    dated_matches = []
    for comment in issue_comments or []:
        if not is_loop_marker_author(comment, bot_login):
            continue
        body = comment.get("body") or ""
        match = last_marker_match(body, marker_re, open_re)
        if not match:
            continue
        dated_matches.append((comment.get("created_at") or "", match.group(1)))
    if not dated_matches:
        return None
    dated_matches.sort(key=lambda pair: pair[0])
    created_at, raw = dated_matches[-1]
    try:
        marker = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(marker, dict):
        return None
    return created_at, marker


def read_marker_with_timestamp(issue_comments, bot_login):
    """As find_latest_marker(), specialized to this module's own board-item
    marker shape (MARKER_RE/MARKER_OPEN_RE)."""
    return find_latest_marker(issue_comments, bot_login)


def find_markers_matching(issue_comments, bot_login, predicate,
                          marker_re=MARKER_RE, open_re=MARKER_OPEN_RE):
    """Every loop-authored marker satisfying `predicate(marker_dict)`, as
    (created_at, marker) pairs, oldest first: each comment's own last
    marker, unparsable ones skipped. find_latest_marker_matching() is the
    newest of these; a caller that needs every match (an issue disposed as
    a duplicate, reopened and disposed again names two spec-requests,
    #874) reads the whole list."""
    dated_matches = []
    for comment in issue_comments or []:
        if not is_loop_marker_author(comment, bot_login):
            continue
        body = comment.get("body") or ""
        match = last_marker_match(body, marker_re, open_re)
        if not match:
            continue
        try:
            marker = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(marker, dict) or not predicate(marker):
            continue
        dated_matches.append((comment.get("created_at") or "", marker))
    dated_matches.sort(key=lambda pair: pair[0])
    return dated_matches


def find_latest_marker_matching(issue_comments, bot_login, predicate,
                                marker_re=MARKER_RE, open_re=MARKER_OPEN_RE):
    """As find_latest_marker(), but returns the newest loop-authored marker
    satisfying `predicate(marker_dict)`, scanning every comment rather than
    stopping at the single overall-newest one -- a later marker of a
    different shape must never hide an earlier one a caller still needs
    (spec 108 maintainer review, fold leg-0: board_eligibility's
    re-admission carve-out needs the newest step=="duplicate" marker even
    once a later route/fix marker becomes the issue's overall-newest).
    Comments whose own marker is unparsable are skipped rather than
    aborting the whole scan -- unlike find_latest_marker(), there is no
    "trust the single newest, even if unparsable" contract to preserve
    here. Returns (created_at, marker) or None."""
    dated_matches = find_markers_matching(issue_comments, bot_login, predicate,
                                          marker_re, open_re)
    return dated_matches[-1] if dated_matches else None


def read_marker(issue_comments, bot_login):
    """As read_marker_with_timestamp(), returning only the marker dict (or
    None)."""
    pair = read_marker_with_timestamp(issue_comments, bot_login)
    return pair[1] if pair else None


def write_marker(step, round, pr, branch, base_sha, spec_request=None,
                  outcome_reason=None, recovery_attempted=False):
    """Renders the run announcement plus the HTML-comment marker line.
    Appended to the loop's own human-legible status comment -- never the
    comment's only content (FR-044) -- by the caller.

    Every call carries a `**Run:** <url>` line (research.md D17,
    contracts/board-loop-workflow.md's stop procedure, spec 057 T051): the
    same shape pr-conversation.yml's own announcements already use, so the
    stop procedure's scan (`test("\\*\\*Run:\\*\\*")`, newest-first,
    skipping this run's own announcement by GITHUB_RUN_ID) finds this
    comment without a second announcement convention. GITHUB_SERVER_URL/
    GITHUB_REPOSITORY/GITHUB_RUN_ID are ambient in every Actions step, so
    every existing write_marker() call site gets this for free.

    `spec_request` (spec 108, data-model.md "Board Item Marker"): the
    linked spec-request issue number, included only when not None -- the
    one caller is the duplicate-disposition write (`step="duplicate"`);
    every other existing call site omits it.

    `outcome_reason`/`recovery_attempted` (spec 096, research.md D4) are
    included unconditionally so every pre-feature positional call site
    keeps working and its marker simply carries
    `"outcome_reason": null, "recovery_attempted": false` alongside the
    five existing keys."""
    payload_dict = {"step": step, "round": round, "pr": pr, "branch": branch,
                     "base_sha": base_sha, "outcome_reason": outcome_reason,
                     "recovery_attempted": recovery_attempted}
    if spec_request is not None:
        payload_dict["spec_request"] = spec_request
    payload = json.dumps(payload_dict, sort_keys=True)
    marker = "<!-- wing-commander-board-item: {0} -->".format(payload)

    server_url = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server_url and repository and run_id:
        run_url = "{0}/{1}/actions/runs/{2}".format(server_url, repository, run_id)
        return "**Run:** {0}\n\n{1}".format(run_url, marker)
    return marker


STALLED_STEP = "stalled"


# Any review-round verdict line naming a PR: converged, budget-spent,
# inconclusive, or a pushed follow-up. Only the newest of these for a PR
# decides clause 2b, so a later inconclusive or budget-spent verdict on a
# head an earlier round converged on is never read as "reviewed clean".
_REVIEW_VERDICT_RE = re.compile(r"Review round[^\n]*?PR #(\d+)")

_REVIEW_CONVERGED_RE = re.compile(r"Review round \d+ converged -- .*?PR #(\d+) \(head ([0-9a-f]{7,40})\)")


def _converged_review_head(body, pr_number):
    """The head commit SHA a review round's *converged* verdict comment
    recorded for `pr_number` in `body`, or None (contracts/resume-
    recovery.md clause 2b, FR-006b). Deliberately matches ONLY the
    converged wording the review job's "Post the converged/stalled
    outcome and marker" step posts -- never the inconclusive parse-failed
    or malformed-findings wording (which shares the same generic "Review
    round N on PR #P" prefix but names no verdict), and never the
    budget-spent wording either: a spent budget means review never
    finished clearing the PR's findings, so it must not be treated as a
    baseline a later, unmoved head could satisfy (maintainer review of
    #885: that bug reported a budget-spent stall READY once its head
    stopped moving, with in-scope findings still open, breaking FR-006b/
    SC-004). Both of those inconclusive verdicts fall through to
    head_moved_since_last_review()'s own "no converged head resolvable"
    default of True, exactly like finding no resolved comment at all."""
    match = _REVIEW_CONVERGED_RE.search(body or "")
    if match and match.group(1) == str(pr_number):
        return match.group(2)
    return None


def head_moved_since_last_review(pr_number, comments, bot_login, run=None):
    """FR-006/FR-006b, contracts/resume-recovery.md clause 2b: whether
    `pr_number`'s live head commit differs from the SHA the loop's own
    most recent *converged* review-round verdict comment recorded for
    that PR -- never a budget-spent or inconclusive verdict, neither of
    which establishes a head reviewed clean (see _converged_review_head()
    above). `comments` is the resume step's own already-fetched flat
    per-issue comments array (read_marker()'s own argument shape), not the
    earlier select step's comments_by_issue map -- a different step's own
    file.

    Returns True (moved -- the safe default, forcing a fresh `review`)
    when no converged verdict comment names this PR, or when the live
    `gh pr view` lookup fails or its output cannot be read (both failures
    are reported to stderr -- distinct from the silent "no converged
    verdict" case above, so a run's log does not read the same for "never
    reviewed" and "the live lookup broke"); False only when the PR's live
    head SHA is exactly the SHA the converged comment recorded (nothing
    reviewed has changed).

    The single shared computation this rule needs (CLAUDE.md "shared logic
    has exactly one home") -- spec 093's own FR-007, when it reaches its
    plan stage, calls this function rather than deriving a second one."""
    run = run or subprocess.run
    newest_body = None
    latest_created_at = None
    for comment in comments or []:
        if not is_loop_marker_author(comment, bot_login):
            continue
        body = comment.get("body") or ""
        verdict = _REVIEW_VERDICT_RE.search(body)
        if verdict is None or verdict.group(1) != str(pr_number):
            continue
        created_at = comment.get("created_at") or ""
        if latest_created_at is None or created_at > latest_created_at:
            latest_created_at = created_at
            newest_body = body
    # Only the newest review verdict for this PR counts: a converged round
    # followed by a budget-spent or inconclusive one is not reviewed clean.
    reviewed_sha = _converged_review_head(newest_body, pr_number)
    if reviewed_sha is None:
        return True
    repository = os.environ.get("GITHUB_REPOSITORY")
    cmd = ["gh", "pr", "view", str(pr_number)]
    if repository:
        cmd += ["-R", repository]
    cmd += ["--json", "headRefOid"]
    try:
        proc = run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print("::warning::head_moved_since_last_review: gh pr view #{0} raised {1} -- "
              "treating the head as moved (FR-006b safe default).".format(pr_number, exc),
              file=sys.stderr)
        return True
    if proc.returncode != 0:
        print("::warning::head_moved_since_last_review: gh pr view #{0} failed (rc={1}): {2} -- "
              "treating the head as moved (FR-006b safe default).".format(
                  pr_number, proc.returncode, (proc.stderr or "").strip()),
              file=sys.stderr)
        return True
    try:
        head_sha = json.loads(proc.stdout).get("headRefOid")
    except ValueError:
        print("::warning::head_moved_since_last_review: gh pr view #{0} returned unparsable JSON -- "
              "treating the head as moved (FR-006b safe default).".format(pr_number),
              file=sys.stderr)
        return True
    if not head_sha:
        return True
    return head_sha != reviewed_sha


def record_stall_summary(issue_number, from_step):
    """FR-011's one canonical $GITHUB_STEP_SUMMARY line for a successful
    stall (CLAUDE.md "shared logic has exactly one home"): every stall
    site calls this -- `--record-stall-summary --issue N --from-step
    <name>` -- right after its own `gh issue comment`/`gh issue close`
    posting the stalled marker actually succeeds, never before. Before
    this, each stall call site pasted its own copy of this
    line BEFORE that post, so a failed post still left the line's claim
    standing (maintainer review of #885)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(
            "board-loop: issue #{0} -- stalled from {1} with board:stalled applied "
            "and a stalled marker recorded.\n".format(issue_number, from_step))


def add_stalled_label(issue_number, label, run=None):
    """Adds `label` (board_eligibility.STALLED_LABEL) to `issue_number`
    BEFORE a stalled marker is rendered (issue #604). Returns True on
    success; on any failure prints `::error::` to stderr and returns False,
    and main() then renders no marker at all.

    Canonical statement of the stall rule, for every board-loop.yml stall
    site (triage's hand-over, fix's gate-red, review's three stalls):
    board:stalled goes on first and a failed add fails the step, so a
    stalled marker is never posted without the label. A stalled marker
    with no board:stalled label can then only mean a maintainer removed
    the label on purpose -- the re-admission spec 057 data-model.md
    defines. Re-admission keeps the resume step's ordinary re-derivation
    from live state: review when an open board:owned PR cites the issue AND
    its head has moved since the loop's own last *converged* review
    verdict (or none is resolvable -- a budget-spent or inconclusive
    verdict never counts), readiness when it has not, otherwise a fresh
    triage (FR-006/FR-006a/FR-006b, contracts/resume-recovery-readmission.md
    folded into specs/061-marker-owned-in-flight/contracts/resume-recovery.md)
    -- head_moved_since_last_review() above is the one shared determination
    of "moved", consumed by board-loop.yml's resume step so the rule lives
    in one canonical place. Before #604 a failed add after the marker
    had already been posted looked identical to that re-admission, and
    resume walked a stalled PR straight back into review (#530 fixed the
    two breach sites; #604 moved every site here).

    `--step stalled` is refused without `--issue` and `--add-label`, so
    no site can render the marker without the add. The label is named at
    the call site (`--add-label "board:stalled"`), not only here, so the
    label-creation gate (verify-board-label-creation.py) still sees each
    job's apply. gh's own stdout (the issue URL) goes to stderr: stdout
    carries the marker alone."""
    run = run or subprocess.run
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        print("::error::board_item_marker: GITHUB_REPOSITORY is unset -- cannot add {0} to issue #{1}, "
              "so no stalled marker is rendered (#604).".format(label, issue_number), file=sys.stderr)
        return False
    try:
        proc = run(["gh", "issue", "edit", str(issue_number), "-R", repository, "--add-label", label],
                   stdout=sys.stderr)
        ok = proc.returncode == 0
    except OSError as exc:
        print(exc, file=sys.stderr)
        ok = False
    if not ok:
        print("::error::board_item_marker: could not add {0} to issue #{1} -- no stalled marker is "
              "rendered, so the item is never left stalled without its label (#604).".format(
                  label, issue_number), file=sys.stderr)
    return ok


def _resolve_step(value):
    """Resolves the symbolic tokens `BREACH_STEP`/`AWAITING_MERGE_STEP` to
    their `board_eligibility` values; any other value passes through
    unchanged. The one place a caller's YAML names these steps -- never a
    second hardcoded copy of the literal "breach"/"awaiting-merge" string
    (contracts/marker-write-entrypoint.md, research.md D3)."""
    if value in ("BREACH_STEP", "AWAITING_MERGE_STEP"):
        from board_eligibility import AWAITING_MERGE_STEP, BREACH_STEP
        return {"BREACH_STEP": BREACH_STEP, "AWAITING_MERGE_STEP": AWAITING_MERGE_STEP}[value]
    return value


def main():
    # `python3 -I` (the board-loop.yml pristine-snapshot invocation shape)
    # excludes the script's own directory from sys.path, so _resolve_step's
    # `from board_eligibility import ...` would otherwise raise
    # ModuleNotFoundError (maintainer review of #607, fold leg-1). The
    # snapshot directory is trusted (Gate 98), so adding it back is safe.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", default=None)
    parser.add_argument("--round", type=int, default=0)
    parser.add_argument("--pr", type=int, default=None)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--base-sha", default=None)
    parser.add_argument("--issue", type=int, default=None,
                        help="with --step stalled: the issue --add-label is applied to first (#604); "
                             "with --record-stall-summary: the issue the summary line names")
    parser.add_argument("--add-label", default=None,
                        help="with --step stalled: must be board_eligibility.STALLED_LABEL (#604)")
    parser.add_argument("--record-stall-summary", action="store_true",
                        help="append FR-011's run-summary line for --issue N, naming --from-step, "
                             "instead of rendering a marker -- call this AFTER the stall site's own "
                             "stalled-marker comment has actually posted (see record_stall_summary())")
    parser.add_argument("--from-step", default=None,
                        help="with --record-stall-summary: the step name the summary line names, "
                             "e.g. 'review (round budget spent)'")
    parser.add_argument("--outcome-reason", default=None)
    parser.add_argument("--recovery-attempted", action="store_true")
    args = parser.parse_args()
    if args.record_stall_summary:
        if args.issue is None or not args.from_step:
            parser.error("--record-stall-summary needs --issue N --from-step <name>")
        record_stall_summary(args.issue, args.from_step)
        return
    if args.step is None:
        parser.error("--step is required (unless --record-stall-summary)")
    step = _resolve_step(args.step)
    if step == STALLED_STEP or args.issue is not None or args.add_label is not None:
        from board_eligibility import STALLED_LABEL
        if step != STALLED_STEP or args.issue is None or args.add_label != STALLED_LABEL:
            parser.error("--step {0} needs --issue N --add-label {1}, and those two only go with "
                         "--step {0} -- see add_stalled_label() (#604)".format(STALLED_STEP, STALLED_LABEL))
        if not add_stalled_label(args.issue, args.add_label):
            sys.exit(1)
    print(write_marker(step, args.round, args.pr, args.branch, args.base_sha,
                       outcome_reason=args.outcome_reason,
                       recovery_attempted=args.recovery_attempted))


if __name__ == "__main__":
    main()
