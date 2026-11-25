#!/usr/bin/env python3
"""Gate — board_duplicate_disposition.py's dispose_as_duplicate() resolves
contracts/duplicate-disposition.md's idempotency/failure-semantics table
correctly (specs/108-routed-original-disposition, FR-009/FR-010/FR-011).

WHY THIS EXISTS
---------------
The disposition is the one durable write that turns "one routed request,
two open issues" back into one -- a regression that re-closed, re-labelled,
or re-commented on every run (or that stopped resuming after a partial
failure) would look identical to correct behaviour on every fixture except
the one it broke. This gate pins every branch of the contract's
failure-semantics table against a stubbed `gh` (the same `run=` injection
seam `board_item_marker.add_stalled_label(issue_number, label, run=None)`
already demonstrates), never a real repository.

Cases R1-R15 (#1209) pin the Roadmap half of the same entry point: every
spec-proposal the loop files is listed under the Roadmap issue's
"### Proposed" header (board_roadmap.py), once, through
board_backlog_edit.edit(), and a Roadmap that cannot be found, has no
header or cannot be written never fails or undoes the routing. Fixtures:
.github/scripts/tests/board-roadmap/.

    python3 .github/scripts/verify-board-duplicate-disposition.py
    python3 .github/scripts/verify-board-duplicate-disposition.py --self-test
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_duplicate_disposition as bdd  # noqa: E402

ORIGINATING = 111
SPEC_REQUEST = 222
SPEC_REQUEST_URL = "https://github.com/example/example/issues/222"
REASON = "Routed to https://github.com/example/example/issues/222"
BOT_LOGIN = "wing-commander-bot[bot]"


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _own_comment(step=bdd.DUPLICATE_STEP, spec_request=SPEC_REQUEST):
    marker = bdd.write_marker(step, round=0, pr=None, branch=None, base_sha=None,
                               spec_request=spec_request)
    return {"body": "Closed as a duplicate -- {0}".format(marker),
            "user": {"login": BOT_LOGIN, "type": "Bot"}, "created_at": "2026-01-01T00:00:00Z"}


def _reciprocal_comment():
    return {"body": "- [ ] {0} — https://example/issues/{1}".format(
        bdd.RECIPROCAL_PHRASE, ORIGINATING),
        "user": {"login": BOT_LOGIN, "type": "Bot"}, "created_at": "2026-01-01T00:00:00Z"}


def _originating(state="OPEN", labelled=False, own_comment=False):
    labels = [{"name": bdd.DISPOSITION_LABEL}] if labelled else []
    comments = [_own_comment()] if own_comment else []
    return {"state": state, "labels": labels, "comments": comments}


def _spec_request(reciprocal=False):
    return {"comments": [_reciprocal_comment()] if reciprocal else []}


def _stub(fail_step=None):
    """A `run=` callable for dispose_as_duplicate()'s mutating gh calls
    (close/label/comment); every call succeeds except `fail_step`
    ("close", "label", or "comment"). Records every call it saw."""
    calls = []

    def run(args, **kwargs):
        calls.append(list(args))
        if args[1:3] == ["api", "-X"] and "PATCH" in args:
            step = "close"
        elif args[1:3] == ["issue", "edit"]:
            step = "label"
        elif args[1:3] == ["issue", "comment"]:
            step = "comment"
        else:
            raise AssertionError("unexpected gh call: {0!r}".format(args))
        if step == fail_step:
            return FakeProc(returncode=1, stderr="stub failure at " + step)
        return FakeProc(returncode=0, stdout="")
    return run, calls


def _call(originating, spec_request, fail_step=None):
    run, calls = _stub(fail_step)
    ok = bdd.dispose_as_duplicate(
        ORIGINATING, SPEC_REQUEST, SPEC_REQUEST_URL, REASON,
        repository="example/example", bot_login=BOT_LOGIN, run=run,
        originating=originating, spec_request=spec_request)
    steps_called = []
    for c in calls:
        if c[1:3] == ["api", "-X"]:
            steps_called.append("close")
        elif c[1:3] == ["issue", "edit"]:
            steps_called.append("label")
        elif c[1:3] == ["issue", "comment"]:
            steps_called.append("comment")
    return ok, steps_called


CASES = []


def _case(name, fn):
    CASES.append((name, fn))


def _case_1_already_disposed():
    """Closed + labelled + own comment present, spec-request already
    reciprocal-linked -> no-op True, zero gh calls."""
    ok, steps = _call(_originating("CLOSED", labelled=True, own_comment=True),
                       _spec_request(reciprocal=True))
    return ok is True and steps == []


_case("1: already disposed is a no-op with zero gh calls", _case_1_already_disposed)


def _case_2_label_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="label")
    second_ok, second_steps = _call(_originating("OPEN"), _spec_request(), fail_step=None)
    return (first_ok is False and first_steps == ["label"]
            and second_ok is True and second_steps == ["label", "comment", "close"])


_case("2: label fails -> False; a later attempt re-enters at label", _case_2_label_fails_then_resumes)


def _case_3_comment_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="comment")
    second_ok, second_steps = _call(_originating("OPEN", labelled=True), _spec_request(), fail_step=None)
    return (first_ok is False and first_steps == ["label", "comment"]
            and second_ok is True and second_steps == ["comment", "close"])


_case("3: label ok, comment fails -> False; a later attempt re-enters at comment, not a second label",
      _case_3_comment_fails_then_resumes)


def _case_4_close_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="close")
    second_ok, second_steps = _call(_originating("OPEN", labelled=True, own_comment=True), _spec_request(),
                                     fail_step=None)
    return (first_ok is False and first_steps == ["label", "comment", "close"]
            and second_ok is True and second_steps == ["close"])


_case("4: label+comment ok, close fails -> False; a later attempt closes only, posts no second comment",
      _case_4_close_fails_then_resumes)


def _case_5_idempotency_drill():
    """Everything already succeeded; called again -> no-op True, no second
    comment (FR-009)."""
    ok, steps = _call(_originating("CLOSED", labelled=True, own_comment=True), _spec_request())
    return ok is True and steps == []


_case("5: idempotency drill -- a repeated call posts no second comment", _case_5_idempotency_drill)


def _case_6_reciprocal_only_missing():
    ok, steps = _call(_originating("CLOSED", labelled=True, own_comment=True), _spec_request(reciprocal=False))
    needs = bdd.spec_request_needs_reciprocal_link(_spec_request(reciprocal=False)["comments"])
    return ok is True and steps == [] and needs is True


_case("6: reciprocal comment alone missing -> no-op True, needs-reciprocal-link=true",
      _case_6_reciprocal_only_missing)


def _case_7_reroute_new_spec_request_posts_new_comment():
    """An issue already fully disposed of an OLD spec-request (closed,
    labelled, marker present naming it) is routed again to a NEW,
    different spec-request: the stale marker must not be read as "already
    disposed of THIS spec-request" -- a new reason/marker comment naming
    the new spec-request is posted (maintainer review, fold leg-1;
    FR-003/FR-004/FR-009)."""
    old_spec_request = SPEC_REQUEST + 1000
    originating = {"state": "CLOSED", "labels": [{"name": bdd.DISPOSITION_LABEL}],
                   "comments": [_own_comment(spec_request=old_spec_request)]}
    ok, steps = _call(originating, _spec_request())
    return ok is True and steps == ["comment"]


_case("7: re-route to a new spec-request posts its own comment, not treated as already-disposed",
      _case_7_reroute_new_spec_request_posts_new_comment)


# ---------------------------------------------------------------------------
# #1209: every spec-proposal the loop files is listed under the Roadmap
# issue's "### Proposed" header, through board_backlog_edit.edit(), by
# board_roadmap.record_proposal() -- called from this script's main(),
# which all three spec-proposal sites run. Fixtures:
# .github/scripts/tests/board-roadmap/.
# ---------------------------------------------------------------------------
import board_roadmap as brm  # noqa: E402

ROADMAP_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "board-roadmap")
ROADMAP = 890
PROPOSAL = 4242
PROPOSAL_TITLE = "Roadmap Proposed lines for loop-filed proposals"
LINE_ID = "bl-0123abcd"
TODAY = "2026-11-25"


def _fixture(name):
    path = os.path.join(ROADMAP_FIXTURES, name)
    if not os.path.isfile(path):
        raise AssertionError("missing fixture {0}".format(path))
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _tracking(roadmap=True, extra=()):
    issues = [{"number": 889, "title": "Maintenance backlog", "state": "OPEN",
               "labels": [{"name": "disposition:tracking"}], "author": {"login": "owner"},
               "authorAssociation": "OWNER"}]
    if roadmap:
        issues.append({"number": ROADMAP, "title": "Roadmap: owner specs, in-flight lifecycles, and parked specs",
                       "state": "OPEN", "labels": [{"name": "disposition:tracking"}],
                       "author": {"login": "owner"}, "authorAssociation": "OWNER"})
    return issues + list(extra)


def _is_title_read(args):
    return args[:3] == ["gh", "issue", "view"] and "--json" in args \
        and "title" in args[args.index("--json") + 1].split(",")


class _RoadmapGh:
    """A fake GitHub for record_proposal(): `run` answers the tracking-issue
    list and the title read; fetch/write hold the Roadmap body.
    `drop_writes` writes that a concurrent editor overwrites."""

    def __init__(self, body, tracking=None, drop_writes=0, list_fails=False, title=PROPOSAL_TITLE,
                 state="OPEN", verify_fails=False):
        self.body = body
        self.state = state
        self.verify_fails = verify_fails
        self.tracking = _tracking() if tracking is None else tracking
        self.drop_writes = drop_writes
        self.list_fails = list_fails
        self.title = title
        self.writes = []
        self.fetches = 0
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        if args[:2] == ["gh", "api"] and "labels=disposition:tracking" in args:
            if self.list_fails:
                return FakeProc(returncode=1, stderr="HTTP 502")
            return FakeProc(stdout="".join(json.dumps(i) + "\n" for i in self.tracking))
        if _is_title_read(args):
            return FakeProc(stdout="{0}\t{1}\n".format(self.state, self.title))
        raise AssertionError("unexpected gh call: {0!r}".format(args))

    def fetch(self, issue):
        assert issue == ROADMAP, "fetched #{0}, not the Roadmap".format(issue)
        self.fetches += 1
        if self.verify_fails and self.writes:
            raise RuntimeError("gh api failed: HTTP 502")  # the read-back after a landed write
        return self.body

    def write(self, issue, body):
        assert issue == ROADMAP, "wrote #{0}, not the Roadmap".format(issue)
        self.writes.append(body)
        if self.drop_writes:
            self.drop_writes -= 1  # a concurrent writer's whole-body write wins
            return
        self.body = body

    def record(self, **kwargs):
        kwargs.setdefault("line_id", LINE_ID)
        return brm.record_proposal(PROPOSAL, repository="example/example", bot_login=BOT_LOGIN,
                                   run=self.run, fetch=self.fetch, write=self.write, today=TODAY,
                                   **kwargs)


def _case_r1_line_lands_under_proposed():
    gh = _RoadmapGh(_fixture("roadmap-body.md"))
    outcome, _msg = gh.record()
    return outcome == "applied" and gh.body == _fixture("roadmap-body-expected.md") and len(gh.writes) == 1


_case("R1: a line-routed proposal is appended to the Roadmap's Proposed list, nothing else changes",
      _case_r1_line_lands_under_proposed)


def _case_r2_idempotent():
    gh = _RoadmapGh(_fixture("roadmap-body-expected.md"))
    outcome, _msg = gh.record()
    return outcome == "applied" and gh.writes == [] and gh.body == _fixture("roadmap-body-expected.md")


_case("R2: a proposal already listed is not added twice (no write)", _case_r2_idempotent)


def _case_r3_issue_source():
    gh = _RoadmapGh(_fixture("roadmap-body.md"))
    outcome, _msg = gh.record(line_id=None, originating=1201)
    want = "- #4242: {0}. Filed by the board loop {1} from issue #1201.\n".format(PROPOSAL_TITLE, TODAY)
    return outcome == "applied" and want in gh.body and "bl-0123abcd" not in gh.body


_case("R3: an issue-routed proposal names its originating issue", _case_r3_issue_source)


def _case_r4_no_header():
    body = _fixture("roadmap-body.md").replace("### Proposed (waiting on the owner's `spec-request`)",
                                               "### Ideas")
    gh = _RoadmapGh(body)
    outcome, _msg = gh.record()
    return outcome == brm.NO_HEADER and gh.writes == []


_case("R4: no Proposed header -> reported, nothing written", _case_r4_no_header)


def _case_r5_no_roadmap():
    for tracking in (_tracking(roadmap=False),
                     _tracking(extra=[dict(_tracking()[1], number=891)])):
        gh = _RoadmapGh(_fixture("roadmap-body.md"), tracking=tracking)
        outcome, _msg = gh.record()
        if outcome != brm.NOT_FOUND or gh.fetches or gh.writes:
            return False
    return True


_case("R5: no Roadmap, or two of them -> reported, no fetch or write by number",
      _case_r5_no_roadmap)


def _case_r6_concurrent_write_retried():
    gh = _RoadmapGh(_fixture("roadmap-body.md"), drop_writes=1)
    outcome, _msg = gh.record()
    return (outcome == "applied" and len(gh.writes) == 2
            and gh.body == _fixture("roadmap-body-expected.md"))


_case("R6: a write a concurrent editor dropped is re-applied through edit()'s read-back loop",
      _case_r6_concurrent_write_retried)


def _case_r7_never_raises():
    gh = _RoadmapGh(_fixture("roadmap-body.md"), list_fails=True)
    outcome, _msg = gh.record()
    return outcome == "failed" and gh.writes == []


_case("R7: a gh failure is an outcome, never an exception", _case_r7_never_raises)


def _case_r8_shapes():
    """CRLF bodies keep CRLF; an empty section gets the line under its
    header; #42421 is not #4242; the title is one line with no doubled
    period."""
    crlf = _fixture("roadmap-body.md").replace("\n", "\r\n")
    out = brm.add_line(crlf, PROPOSAL, "- #4242: x.")
    if "- #4242: x.\r\n" not in out or "\n" in out.replace("\r\n", ""):
        return False
    empty = "### Proposed (waiting)\n\n### Parked\n- #4141: parked.\n"
    if brm.add_line(empty, PROPOSAL, "- #4242: x.") != ("### Proposed (waiting)\n" + brm.UNORDERED_LABEL
                                                       + "\n- #4242: x.\n\n### Parked\n- #4141: parked.\n"):
        return False
    lookalike = "### Proposed\n- #42421: other.\n"
    if brm.is_listed(lookalike, PROPOSAL) or not brm.is_listed(lookalike, 42421):
        return False
    line = brm.proposed_line(PROPOSAL, "Two\nlines <!-- x --> end.", TODAY, line_id="not-an-id", originating=7)
    return line == "- #4242: Two lines x end. Filed by the board loop 2026-11-25 from issue #7."


_case("R8: CRLF, empty section, number boundary and title cleaning",
      _case_r8_shapes)


def _run_main(env, roadmap_gh, disposition_fails=False):
    """Runs board_duplicate_disposition.main() on the issue path with every
    gh call stubbed, the Roadmap included. Returns (exit_code, outputs)."""
    import subprocess
    import tempfile
    repository = "example/example"

    def run_stub(args, **kwargs):
        if args[:2] == ["gh", "api"] and "labels=disposition:tracking" in args \
                or _is_title_read(args):
            return roadmap_gh.run(args)
        kind = _run_stub_call_kind(args, repository)
        if kind == "view {0}".format(ORIGINATING):
            return FakeProc(stdout='{"state": "OPEN", "labels": []}')
        if kind is not None:
            return FakeProc(stdout="")
        if disposition_fails and args[1:3] == ["issue", "edit"]:
            return FakeProc(returncode=1, stderr="stub failure at label")
        return FakeProc()

    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "out")
        summary_path = os.path.join(tmp, "summary")
        saved_env = dict(os.environ)
        saved = (subprocess.run, bdd.subprocess.run, brm.bbe.gh_fetch, brm.bbe.gh_write, sys.argv)
        os.environ.update({"GITHUB_REPOSITORY": repository, "BOT_LOGIN": BOT_LOGIN,
                           "GITHUB_OUTPUT": out_path, "GITHUB_STEP_SUMMARY": summary_path})
        os.environ.pop("BOARD_LINE_ID", None)
        os.environ.update(env)
        subprocess.run = run_stub
        brm.bbe.gh_fetch, brm.bbe.gh_write = roadmap_gh.fetch, roadmap_gh.write
        sys.argv = ["board_duplicate_disposition.py", "--originating", str(ORIGINATING),
                    "--spec-request-issue", str(PROPOSAL), "--spec-request-url",
                    "https://github.com/example/example/issues/{0}".format(PROPOSAL), "--reason", REASON]
        code = 0
        try:
            bdd.main()
        except SystemExit as exc:
            code = exc.code or 0
        finally:
            subprocess.run, bdd.subprocess.run, brm.bbe.gh_fetch, brm.bbe.gh_write, sys.argv = saved
            os.environ.clear()
            os.environ.update(saved_env)
        outputs = open(out_path, encoding="utf-8").read() if os.path.exists(out_path) else ""
        summary = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
    return code, outputs, summary


def _case_r9_main_lists_the_proposal():
    gh = _RoadmapGh(_fixture("roadmap-body.md"))
    code, outputs, summary = _run_main({}, gh)
    return (code == 0 and "disposed=true" in outputs and "from issue #{0}.".format(ORIGINATING) in gh.body
            and "#4242" in summary)


_case("R9: the disposition entry point every spec-proposal site runs lists the proposal",
      _case_r9_main_lists_the_proposal)


def _case_r10_roadmap_failure_never_fails_routing():
    gh = _RoadmapGh(_fixture("roadmap-body.md"), list_fails=True)
    code, outputs, summary = _run_main({}, gh)
    no_header = _RoadmapGh(_fixture("roadmap-body.md").replace("### Proposed", "### Ideas"))
    code2, outputs2, summary2 = _run_main({}, no_header)
    # ...and a failed disposition is still listed (the Roadmap goes first).
    listed = _RoadmapGh(_fixture("roadmap-body.md"))
    code3, _o, _s = _run_main({}, listed, disposition_fails=True)
    return (code == 0 and "disposed=true" in outputs and gh.writes == [] and "by hand" in summary
            and code2 == 0 and "disposed=true" in outputs2 and no_header.writes == []
            and 'has no "### Proposed" header' in summary2
            and code3 == 1 and "#4242:" in listed.body)


_case("R10: a Roadmap failure or missing header never fails or undoes the routing",
      _case_r10_roadmap_failure_never_fails_routing)


def _case_r11_owner_order_kept():
    """The owner numbers the Proposed list (2026-11-25): a numbered #N is
    already listed, a second proposal joins the existing "Not yet
    ordered" sub-list, and neither the numbered order nor "Not specs:"
    gains a line."""
    expected = _fixture("roadmap-body-expected.md")
    if not brm.is_listed(expected, 1188) or brm.add_line(expected, 1188, "- #1188: again.") != expected:
        return False
    out = brm.add_line(expected, 4343, "- #4343: next.")
    want = expected.replace(brm.UNORDERED_LABEL + "\n", brm.UNORDERED_LABEL + "\n- #4343: next.\n", 1)
    return out == want and out.count(brm.UNORDERED_LABEL) == 1


_case("R11: the owner's numbered order and 'Not specs:' are never written into; "
      "later proposals join 'Not yet ordered'", _case_r11_owner_order_kept)


def _case_r12_review_pass_1_shapes():
    """Code review of #1222, pass 1: a proposal the owner moved out of
    Proposed (In flight, Parked) is not listed again; with no numbered
    order the sub-list goes under the header, never after "Not specs:";
    an empty label never glues the text below onto the item; `**#N**`
    and `[#N](url)` items count as listed; an @name in a title is code,
    not a mention."""
    moved = "### Proposed\n1. #1.\n\n### In flight\n- #4242: promoted.\n"
    if brm.add_line(moved, PROPOSAL, "- #4242: x.") != moved:
        return False
    no_order = "### Proposed\nNone ordered yet.\n\nNot specs:\n- #1167 x\n\n### Parked\n"
    want = ("### Proposed\n" + brm.UNORDERED_LABEL + "\n- #4242: x.\n\nNone ordered yet.\n\n"
            "Not specs:\n- #1167 x\n\n### Parked\n")
    if brm.add_line(no_order, PROPOSAL, "- #4242: x.") != want:
        return False
    bare = "### Proposed\n" + brm.UNORDERED_LABEL + "\nNot specs:\n- #1167 x\n"
    if brm.add_line(bare, PROPOSAL, "- #4242: x.") != ("### Proposed\n" + brm.UNORDERED_LABEL
                                                       + "\n- #4242: x.\n\nNot specs:\n- #1167 x\n"):
        return False
    marked = "### Proposed\n1. **#77**: a\n2. [#78](https://example.invalid/78): b\n"
    if not (brm.is_listed(marked, 77) and brm.is_listed(marked, 78)):
        return False
    line = brm.proposed_line(PROPOSAL, "Bump @types/node for @octo-team", TODAY, originating=7)
    return line.startswith("- #4242: Bump `@types/node` for `@octo-team`. ")


_case("R12: moved proposals, no numbered order, an empty label, marked items and @-mentions",
      _case_r12_review_pass_1_shapes)


def _case_r13_review_pass_2_shapes():
    """Code review of #1222, pass 2: a loose numbered order (blank lines
    between items) is never split (since pass 4 the sub-list goes above
    it); an existing label with a blank line before its items gets the
    new line directly under it;
    the label never points "above" when it sits under the header; raw
    HTML in a title is shown as text; a title ending in ? or a truncation
    gets no doubled stop; truncation never reopens an @-mention; a
    proposal that is no longer open is not listed; a failure after a
    landed write never says the line is absent."""
    loose = "### Proposed\n1. #1: a\n\n2. #2: b\n   more\n\nNot specs:\n- #3\n"
    want = ("### Proposed\n" + brm.UNORDERED_LABEL + "\n- #4242: x.\n\n1. #1: a\n\n2. #2: b\n   more\n\n"
            "Not specs:\n- #3\n")
    if brm.add_line(loose, PROPOSAL, "- #4242: x.") != want:
        return False
    spaced = "### Proposed\n" + brm.UNORDERED_LABEL + "\n\n- #5: y\n"
    if brm.add_line(spaced, PROPOSAL, "- #4242: x.") != ("### Proposed\n" + brm.UNORDERED_LABEL
                                                        + "\n- #4242: x.\n\n- #5: y\n"):
        return False
    if "above" in brm.UNORDERED_LABEL:
        return False
    if "<details>" in brm.proposed_line(PROPOSAL, "Render <details> sections", TODAY, originating=7):
        return False
    if "?. " in brm.proposed_line(PROPOSAL, "Why does X fail?", TODAY, originating=7):
        return False
    long_line = brm.proposed_line(PROPOSAL, "a" * 190 + " @octocat", TODAY, originating=7)
    if "...." in long_line or "@octo" in long_line.replace("`@", ""):
        return False
    closed = _RoadmapGh(_fixture("roadmap-body.md"), state="CLOSED")
    outcome, _msg = closed.record()
    if outcome != brm.NOT_OPEN or closed.writes or closed.fetches:
        return False
    landed = _RoadmapGh(_fixture("roadmap-body.md"), verify_fails=True)
    outcome, msg = landed.record()
    return outcome == "failed" and len(landed.writes) == 1 and "did not finish" in msg \
        and "if it is missing" in brm.HAND_EDIT


_case("R13: loose order, spaced label, label wording, title HTML/stops/truncation, "
      "closed proposals and a failure after a landed write",
      _case_r13_review_pass_2_shapes)


def _case_r14_review_pass_3_shapes():
    """Code review of #1222, pass 3: a list that follows the loop's
    sub-list after a blank line is the owner's, so a second proposal is
    never appended into it; a backtick in a title can never pair with
    the code span round an @name and leave the name a live mention."""
    bulleted = "### Proposed\n- #1188: owner a\n- #1206: owner b\n\n### Parked\n"
    once = brm.add_line(bulleted, PROPOSAL, "- #4242: x.")
    twice = brm.add_line(once, 4343, "- #4343: y.")
    if twice != ("### Proposed\n" + brm.UNORDERED_LABEL + "\n- #4343: y.\n- #4242: x.\n\n"
                 "- #1188: owner a\n- #1206: owner b\n\n### Parked\n"):
        return False
    # Each title's own backslashes and backticks are escaped, so the only
    # live backticks are the pair round each @name.
    want = {
        "Fix `foo @bar baz": "Fix \\`foo `@bar` baz",
        "`a`@team": "\\`a\\``@team`",
        "a\\`@b": "a\\\\\\``@b`",
    }
    for title, cleaned in want.items():
        if brm.proposed_line(PROPOSAL, title, TODAY, originating=7) != \
                "- #4242: {0}. Filed by the board loop {1} from issue #7.".format(cleaned, TODAY):
            return False
    return True


_case("R14: a list below the loop's sub-list, and backticks round an @-mention",
      _case_r14_review_pass_3_shapes)


def _owner_lines(text):
    """The non-blank lines that are not the loop's: its label and its
    #4242/#4343 items."""
    return [line for line in text.splitlines()
            if line.strip() and line != brm.UNORDERED_LABEL and not line.startswith(("- #4242:", "- #4343:"))]


def _case_r15_fixed_anchor():
    """Code review of #1222, pass 4: the line goes at a fixed anchor --
    directly under the "Not yet ordered" label, which sits directly under
    the header -- so the loop never works out where the owner's list
    ends. For every shape of the owner's Proposed section (tight, loose,
    bulleted, a lazy continuation, prose only, an existing label), two
    filings leave every owner line in place and in order, put the newest
    line directly under the label, and keep the label unique."""
    shapes = [
        "### Proposed\n1. #1: a\n2. #2: b\nNot specs:\n- #3\n\n### Parked\n",
        "### Proposed\n1. #1: a\n\n2. #2: b\n\n- #3\n",
        "### Proposed\n- #1: a\n- #2: b\n\n- #3: c\n",
        "### Proposed\nOrder agreed.\n1. #1: a\n   more\n\nNot specs:\n* #3\n",
        "### Proposed\n" + brm.UNORDERED_LABEL + "\n- #9: older.\n\n1. #1: a\n",
        "### Proposed\n" + brm.UNORDERED_LABEL,
        "### Proposed",
        _fixture("roadmap-body.md"),
    ]
    for body in shapes:
        out = brm.add_line(brm.add_line(body, PROPOSAL, "- #4242: x."), 4343, "- #4343: y.")
        lines = out.splitlines()
        label = lines.index(brm.UNORDERED_LABEL)
        if _owner_lines(out) != _owner_lines(body) or out.count(brm.UNORDERED_LABEL) != 1 \
                or lines[label + 1:label + 3] != ["- #4343: y.", "- #4242: x."] \
                or not brm.HEADER_RE.match(lines[label - 1]):
            return False
        # The owner's first line under the header is set apart from the
        # loop's list unless it is the loop's own older item.
        after = lines[label + 3] if label + 3 < len(lines) else ""
        if after and not after.startswith("- #9:") and after.strip():
            return False
    return True


_case("R15: the line goes directly under the label, the label directly under the header, "
      "and no owner line moves", _case_r15_fixed_anchor)


def run(verbose=True):
    failures = 0
    for name, fn in CASES:
        try:
            passed = fn()
        except AssertionError as exc:
            passed = False
            if verbose:
                print("::error::verify-board-duplicate-disposition: {0}: {1}".format(name, exc))
        if passed:
            if verbose:
                print("[ok] {0}".format(name))
        else:
            failures += 1
            if verbose:
                print("::error::verify-board-duplicate-disposition: {0}: FAILED".format(name))
    return failures


def _run_stub_call_kind(args, repository):
    """Classifies a `run()` call made by the real (non-injected) fetch
    path: "view" (`gh issue view <n> -R repo --json state,labels`),
    "comments <n>" (the `gh api repos/repo/issues/<n>/comments` call,
    `--paginate --jq '.[]'`), or None for anything else (the three
    mutating calls `_stub()` already classifies)."""
    if args[:3] == ["gh", "issue", "view"]:
        return "view {0}".format(args[3])
    prefix = "repos/{0}/issues/".format(repository)
    if args[:2] == ["gh", "api"] and len(args) > 2 and args[2].startswith(prefix) \
            and args[2].endswith("/comments"):
        number = args[2][len(prefix):-len("/comments")]
        return "comments {0}".format(number)
    return None


def _baseline_end_to_end():
    """No-fixture baseline (T007): a bare gh stub that succeeds at every
    call -- including the pre-check's own `gh issue view --json
    state,labels` and `gh api .../comments --paginate --jq '.[]'` reads
    (the real REST shape, fold leg-1 -- never `gh issue view --json
    comments`'s GraphQL `author`-shaped payload, which hid that bug),
    since originating/spec_request are omitted here -- produces
    disposed=true, needs-reciprocal-link=true end to end. An empty stdout
    (no lines) is what `--jq '.[]'` emits for a zero-comment page (Gate
    18: never a bare `[]` array literal, which `--paginate` without a
    per-item filter would NOT actually produce past the first page)."""
    repository = "example/example"
    calls = []

    def run_stub(args, **kwargs):
        calls.append(list(args))
        kind = _run_stub_call_kind(args, repository)
        if kind == "view {0}".format(ORIGINATING):
            return FakeProc(returncode=0, stdout='{"state": "OPEN", "labels": []}')
        if kind in ("comments {0}".format(ORIGINATING), "comments {0}".format(SPEC_REQUEST)):
            return FakeProc(returncode=0, stdout="")
        return FakeProc(returncode=0, stdout="")

    ok = bdd.dispose_as_duplicate(
        ORIGINATING, SPEC_REQUEST, SPEC_REQUEST_URL, REASON,
        repository=repository, bot_login=BOT_LOGIN, run=run_stub)
    needs = bdd.spec_request_needs_reciprocal_link([])
    return ok is True and needs is True


def _baseline_idempotent_via_real_fetch():
    """Regression drill for fold leg-1: an issue already fully disposed
    (closed, labelled, own marker comment present) is read through the
    REAL `gh api .../comments --paginate --jq '.[]'` fetch path -- not
    injected as a pre-built Python dict the way CASES 1-7 do -- and
    correctly recognized as already disposed: zero mutating gh calls.
    Before the fix, board_duplicate_disposition.py read comments via `gh
    issue view --json comments` (GraphQL `author`, no `user.type`), so
    is_loop_marker_author() never matched and this same drill made a
    spurious "comment" call on every run. Each stub reply is ONE JSON
    object per line (what `--jq '.[]'` actually emits, Gate 18), never a
    `[...]`-wrapped array."""
    repository = "example/example"
    own_comment = _own_comment()
    reciprocal_comment = _reciprocal_comment()
    calls = []

    def run_stub(args, **kwargs):
        calls.append(list(args))
        kind = _run_stub_call_kind(args, repository)
        if kind == "view {0}".format(ORIGINATING):
            return FakeProc(returncode=0, stdout=json.dumps(
                {"state": "CLOSED", "labels": [{"name": bdd.DISPOSITION_LABEL}]}))
        if kind == "comments {0}".format(ORIGINATING):
            return FakeProc(returncode=0, stdout=json.dumps(own_comment))
        if kind == "comments {0}".format(SPEC_REQUEST):
            return FakeProc(returncode=0, stdout=json.dumps(reciprocal_comment))
        raise AssertionError("unexpected gh call: {0!r}".format(args))

    ok = bdd.dispose_as_duplicate(
        ORIGINATING, SPEC_REQUEST, SPEC_REQUEST_URL, REASON,
        repository=repository, bot_login=BOT_LOGIN, run=run_stub)
    mutating = [c for c in calls if _run_stub_call_kind(c, repository) is None]
    return ok is True and mutating == []


def self_test():
    """The baseline end-to-end drill, plus a mutation proving case 1 is not
    vacuous: disabling the marker-presence check must make the idempotency
    drill (case 5) re-post a comment."""
    failures = 0

    def check(name, cond):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0}".format(name))

    check("baseline: bare gh stub succeeding at every call yields "
          "disposed=true, needs-reciprocal-link=true end to end", _baseline_end_to_end())

    check("baseline: an already-disposed issue read through the real "
          "gh api .../comments fetch path (--paginate --jq '.[]') is "
          "recognized as already disposed (fold leg-1 regression)",
          _baseline_idempotent_via_real_fetch())

    original = bdd._has_own_duplicate_comment
    bdd._has_own_duplicate_comment = lambda comments, bot_login, spec_request_issue: False
    try:
        ok, steps = _call(_originating("CLOSED", labelled=True, own_comment=True), _spec_request())
    finally:
        bdd._has_own_duplicate_comment = original
    check("mutation: dropping the own-comment presence check makes the "
          "idempotency drill (case 5) re-post a comment", steps == ["comment"] and ok is True)

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    failures = run()
    print("verify-board-duplicate-disposition: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
