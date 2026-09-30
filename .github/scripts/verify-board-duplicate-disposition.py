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
