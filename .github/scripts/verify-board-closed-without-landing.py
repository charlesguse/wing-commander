#!/usr/bin/env python3
"""Gate — board_closed_without_landing.py's closed_without_landing() and
post_notice() resolve contracts/closed-without-landing-notice.md correctly
(specs/108-routed-original-disposition, research.md D8, FR-017).

WHY THIS EXISTS
---------------
A spec-request that closes with its work never landed is the one case
where a maintainer's only path back onto the board (reopening the
originating issue) is never reported unless this scan says so
(Principle IV: no manual step survives unreported). A regression that
skipped a short-of-terminal spec-meta.json, that mistook "no
spec-meta.json at all" for "landed", or that re-posted the notice on
every run, would look identical to correct behaviour on every fixture
except the one it broke.

    python3 .github/scripts/verify-board-closed-without-landing.py
    python3 .github/scripts/verify-board-closed-without-landing.py --self-test
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_closed_without_landing as bcwl  # noqa: E402


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub(fail=False):
    calls = []

    def run(args, **kwargs):
        calls.append(list(args))
        if fail:
            return FakeProc(returncode=1, stderr="stub failure")
        return FakeProc(returncode=0)
    return run, calls


CASES = []


def _case(name, fn):
    CASES.append((name, fn))


def _case_a_short_of_terminal():
    """(a) A closed spec-request whose spec-meta.json's stage is short of
    the finalize terminal value -- both notices posted."""
    entry = {"number": 701, "spec_meta": {"stage": "implement"}, "comments": [],
             "originating_issue": 700, "originating_comments": []}
    selected = bcwl.closed_without_landing([entry])
    if selected != [entry]:
        return False
    run, calls = _stub()
    ok_spec_request = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(),
                                        entry["comments"], 701, run=run)
    ok_originating = bcwl.post_notice(700, "example/example", bcwl._originating_notice_body(701),
                                       entry["originating_comments"], 701, run=run)
    return (ok_spec_request and ok_originating and len(calls) == 2
            and all(bcwl.notice_marker(701) in call[-1] for call in calls))


_case("a: short-of-terminal stage -> both notices posted", _case_a_short_of_terminal)


def _case_b_idempotent_repeat():
    """(b) The same run repeated -- no second notice on either issue."""
    marker_comment = {"body": "already notified\n\n" + bcwl.notice_marker(701)}
    run, calls = _stub()
    ok = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(),
                           [marker_comment], 701, run=run)
    ok_originating = bcwl.post_notice(700, "example/example", bcwl._originating_notice_body(701),
                                       [marker_comment], 701, run=run)
    return ok is True and ok_originating is True and calls == []


_case("b: a repeated run posts no second notice (idempotency, FR-017)", _case_b_idempotent_repeat)


def _case_c_no_spec_meta_at_all():
    """(c) A spec-request with no spec-meta.json naming it at all -- still
    counted as closed without landing."""
    entry = {"number": 702, "spec_meta": None, "comments": [],
              "originating_issue": None, "originating_comments": None}
    return bcwl.closed_without_landing([entry]) == [entry]


_case("c: no spec-meta.json at all is still counted", _case_c_no_spec_meta_at_all)


def _case_d_reached_terminal():
    """(d) A spec-request whose spec-meta.json DID reach the terminal
    stage -- no notice."""
    entry = {"number": 703, "spec_meta": {"stage": bcwl.FINALIZE_TERMINAL_STAGE},
              "comments": [], "originating_issue": 700, "originating_comments": []}
    return bcwl.closed_without_landing([entry]) == []


_case("d: a spec-request that reached the terminal stage is not selected", _case_d_reached_terminal)


def _case_e_gh_failure_propagates():
    """A `gh` failure while posting is reported (False), not swallowed."""
    run, calls = _stub(fail=True)
    ok = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(), [], 701, run=run)
    return ok is False and len(calls) == 1


_case("e: a gh failure while posting returns False, not swallowed", _case_e_gh_failure_propagates)


def _case_f_second_closure_keyed():
    """(f) The originating issue already carries the notice for its first
    spec-request's closure (#701); reopened and re-routed, its second
    spec-request (#705) also closes without landing. That second notice is
    posted, whether the first left a keyed marker or a legacy bare one
    (found by the code review of #937)."""
    posted = []
    for first in (bcwl.notice_marker(701), bcwl.NOTICE_MARKER):
        prior = {"body": bcwl._originating_notice_body(701) + "\n\n" + first}
        run, calls = _stub()
        ok = bcwl.post_notice(700, "example/example", bcwl._originating_notice_body(705),
                               [prior], 705, run=run)
        posted.append(ok is True and len(calls) == 1 and bcwl.notice_marker(705) in calls[0][-1])
    return all(posted)


_case("f: a second spec-request's closure is noticed on an already-noticed originating issue",
      _case_f_second_closure_keyed)


def _case_g_legacy_marker_still_counts():
    """(g) A legacy bare marker still suppresses a repeat of the notice it
    was posted for: on the spec-request itself, and on an originating issue
    whose notice names that spec-request."""
    bare = "\n\n" + bcwl.NOTICE_MARKER
    run, calls = _stub()
    ok_own = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(),
                               [{"body": bcwl._spec_request_notice_body() + bare}], 701, run=run)
    ok_originating = bcwl.post_notice(700, "example/example", bcwl._originating_notice_body(701),
                                       [{"body": bcwl._originating_notice_body(701) + bare}], 701,
                                       run=run)
    return ok_own is True and ok_originating is True and calls == []


_case("g: a legacy bare marker still counts for the closure it names", _case_g_legacy_marker_still_counts)


def run(verbose=True):
    failures = 0
    for name, fn in CASES:
        passed = fn()
        if passed:
            if verbose:
                print("[ok] {0}".format(name))
        else:
            failures += 1
            if verbose:
                print("::error::verify-board-closed-without-landing: {0}: FAILED".format(name))
    return failures


def self_test():
    """A mutation proving case (b) is not vacuous: disabling the notice
    marker's presence check must make the idempotent-repeat case re-post."""
    failures = 0

    def check(name, cond):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0}".format(name))

    original = bcwl._has_notice
    bcwl._has_notice = lambda comments, issue_number, spec_request_number: False
    try:
        mutated_reposts = not _case_b_idempotent_repeat()
    finally:
        bcwl._has_notice = original
    check("mutation: dropping the notice-presence check makes the "
          "idempotent-repeat case (b) re-post", mutated_reposts)

    # The pre-fix check: any closed-without-landing marker suppresses every
    # later notice on the issue, whichever spec-request it was about.
    bcwl._has_notice = lambda comments, issue_number, spec_request_number: any(
        "<!-- wing-commander-closed-without-landing" in (c.get("body") or "") for c in comments or [])
    try:
        unkeyed_caught = not _case_f_second_closure_keyed()
    finally:
        bcwl._has_notice = original
    check("mutation: an unkeyed presence check suppresses the second closure's "
          "notice (case f)", unkeyed_caught)

    # Legacy acceptance dropped: only the keyed marker counts.
    bcwl._has_notice = lambda comments, issue_number, spec_request_number: any(
        bcwl.notice_marker(spec_request_number) in (c.get("body") or "") for c in comments or [])
    try:
        legacy_caught = not _case_g_legacy_marker_still_counts()
    finally:
        bcwl._has_notice = original
    check("mutation: ignoring the legacy bare marker re-posts a notice it already "
          "covers (case g)", legacy_caught)

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    failures = run()
    print("verify-board-closed-without-landing: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
