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
                                        entry["comments"], run=run)
    ok_originating = bcwl.post_notice(700, "example/example", bcwl._originating_notice_body(701),
                                       entry["originating_comments"], run=run)
    return ok_spec_request and ok_originating and len(calls) == 2


_case("a: short-of-terminal stage -> both notices posted", _case_a_short_of_terminal)


def _case_b_idempotent_repeat():
    """(b) The same run repeated -- no second notice on either issue."""
    marker_comment = {"body": "already notified\n\n" + bcwl.NOTICE_MARKER}
    run, calls = _stub()
    ok = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(),
                           [marker_comment], run=run)
    return ok is True and calls == []


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
    ok = bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(), [], run=run)
    return ok is False and len(calls) == 1


_case("e: a gh failure while posting returns False, not swallowed", _case_e_gh_failure_propagates)


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
    bcwl._has_notice = lambda comments: False
    try:
        marker_comment = {"body": "already notified\n\n" + bcwl.NOTICE_MARKER}
        run_stub, calls = _stub()
        bcwl.post_notice(701, "example/example", bcwl._spec_request_notice_body(),
                          [marker_comment], run=run_stub)
        mutated_reposts = len(calls) == 1
    finally:
        bcwl._has_notice = original
    check("mutation: dropping the notice-presence check makes the "
          "idempotent-repeat case (b) re-post", mutated_reposts)

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
