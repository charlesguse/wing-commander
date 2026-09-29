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

    python3 .github/scripts/verify-board-duplicate-disposition.py
    python3 .github/scripts/verify-board-duplicate-disposition.py --self-test
"""
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


def _case_2_close_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="close")
    second_ok, second_steps = _call(_originating("OPEN"), _spec_request(), fail_step=None)
    return (first_ok is False and first_steps == ["close"]
            and second_ok is True and second_steps == ["close", "label", "comment"])


_case("2: close fails -> False; a later attempt re-enters at close", _case_2_close_fails_then_resumes)


def _case_3_label_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="label")
    second_ok, second_steps = _call(_originating("CLOSED", labelled=False), _spec_request(), fail_step=None)
    return (first_ok is False and first_steps == ["close", "label"]
            and second_ok is True and second_steps == ["label", "comment"])


_case("3: close ok, label fails -> False; a later attempt re-enters at label, not a second close",
      _case_3_label_fails_then_resumes)


def _case_4_comment_fails_then_resumes():
    first_ok, first_steps = _call(_originating("OPEN"), _spec_request(), fail_step="comment")
    second_ok, second_steps = _call(_originating("CLOSED", labelled=True), _spec_request(), fail_step=None)
    return (first_ok is False and first_steps == ["close", "label", "comment"]
            and second_ok is True and second_steps == ["comment"])


_case("4: close+label ok, comment fails -> False; a later attempt posts only the missing comment",
      _case_4_comment_fails_then_resumes)


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


def _baseline_end_to_end():
    """No-fixture baseline (T007): a bare gh stub that succeeds at every
    call -- including the pre-check's own `gh issue view` reads, since
    originating/spec_request are omitted here -- produces disposed=true,
    needs-reciprocal-link=true end to end."""
    calls = []

    def run_stub(args, **kwargs):
        calls.append(list(args))
        if args[:3] == ["gh", "issue", "view"] and str(ORIGINATING) in args:
            return FakeProc(returncode=0, stdout='{"state": "OPEN", "labels": [], "comments": []}')
        if args[:3] == ["gh", "issue", "view"] and str(SPEC_REQUEST) in args:
            return FakeProc(returncode=0, stdout='{"comments": []}')
        return FakeProc(returncode=0, stdout="")

    ok = bdd.dispose_as_duplicate(
        ORIGINATING, SPEC_REQUEST, SPEC_REQUEST_URL, REASON,
        repository="example/example", bot_login=BOT_LOGIN, run=run_stub)
    needs = bdd.spec_request_needs_reciprocal_link([])
    return ok is True and needs is True


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

    original = bdd._has_own_duplicate_comment
    bdd._has_own_duplicate_comment = lambda comments, bot_login: False
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
