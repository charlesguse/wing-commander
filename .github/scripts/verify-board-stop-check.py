#!/usr/bin/env python3
"""Gate — board_stop_check.py's find_stop_request() resolves every
documented branch correctly (specs/057-autonomous-board-loop, research.md
D17, FR-052/FR-053).

WHY THIS EXISTS
---------------
The stop path is the one mechanism a maintainer relies on to halt an
in-flight item -- a regression that let a non-maintainer's "stop" cancel a
run (or that cancelled the run's own just-posted announcement) would look
identical to correct behavior on every fixture except the one it broke.

Fixtures, each a checked-in comments/expected-run-id pair under
.github/scripts/tests/board-stop-check/. Fails loudly, not vacuously, if
any fixture file is missing.

Issue #539 adds the stop-COMMAND rule (board_stop_check.py's module
docstring): stop-command-cases.json is an accept/reject table run through
is_stop_command() and, as a lone OWNER comment after a `**Run:**` marker,
through find_stop_request(); regression-402-prose-stop.json is #402's real
owner analysis ("it should stop retrying and finish"), which must not
stop. A mutation self-test then swaps the predicate back to the pre-#539
bare `\bstop\b` word search and requires the fixtures to FAIL -- a gate
that still passed would not be guarding the rule.

Issue #547 adds the marker-AUTHOR rule: a `**Run:**` line counts only at
the start of a line (MARKER_RUN_RE) in a comment the loop's own App posted
(is_loop_marker_author(): `user.type == "Bot"` and the caller's bot
login). The forged-marker-* fixtures post `**Run:**` lines as NONE,
CONTRIBUTOR and OWNER humans and as another App's bot, before a stop
(the cancel target) and after one (the baseline); run-line-in-prose-
ignored.json puts one mid-sentence and one in a `>` quote. Two more
mutations -- dropping the author check, un-anchoring MARKER_RUN_RE -- must
each be caught. Issue #580: only the LAST `**Run:**` line in the loop's
comment is its own (last_run_match()); forged-run-line-in-own-comment.json
puts a `**Run:**` line in the agent text of the loop's own comment, before
the real one, and a mutation restoring the first match must be caught. Finally the composite's own shell
(wing-commander-board-stop-check/action.yml, step `check`) is extracted and
run under bash -eo pipefail against a stub `gh`, proving its cancel guard:
a board-loop run of this repository is cancelled with the cancel-token; a
different workflow's run, an unreadable run and a completed run are not,
and none of them fails the step. A mutation that disables the workflow-
path guard must be caught there too.
"""
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_stop_check  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-stop-check")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSITE = os.path.join(
    REPO_ROOT, ".github", "actions", "wing-commander-board-stop-check", "action.yml")
BOT_LOGIN = "wing-commander-bot[bot]"
BOT_USER = {"login": BOT_LOGIN, "type": "Bot"}

EXPECTED_FILES = {
    "maintainer-stop.json", "non-maintainer-stop-ignored.json",
    "no-stop-mentioned.json", "skips-own-run.json",
    "stale-stop-predates-run.json", "first-pass-own-run-only.json",
    "evidence-link-not-a-marker.json", "regression-402-prose-stop.json",
    "forged-marker-outsider-target-ignored.json",
    "forged-marker-outsider-baseline-ignored.json",
    "forged-marker-owner-human-target-ignored.json",
    "forged-marker-owner-human-baseline-ignored.json",
    "bot-marker-honoured.json", "run-line-in-prose-ignored.json",
    "forged-run-line-in-own-comment.json",
}
COMMAND_CASES_FILE = "stop-command-cases.json"
MARKER_BODY = ("**Run:** https://github.com/example/example/actions/runs/111"
               "\n\n<!-- wing-commander-board-item: {} -->")


def run_fixtures(verbose=True):
    failures = 0
    for name in sorted(EXPECTED_FILES):
        with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as fh:
            spec = json.load(fh)
        got = board_stop_check.find_stop_request(
            spec["comments"], spec["current_run_id"], spec["bot_login"])
        expected = board_stop_check.StopDecision(**spec["expected"])
        if got != expected:
            failures += 1
            if verbose:
                print("::error::verify-board-stop-check: {0}: expected {1!r}, "
                      "got {2!r}.".format(name, expected, got))
        elif verbose:
            print("[ok] {0}: find_stop_request() == {1!r}".format(name, got))
    return failures


def run_command_cases(verbose=True):
    with open(os.path.join(FIXTURES_DIR, COMMAND_CASES_FILE), encoding="utf-8") as fh:
        cases = json.load(fh)
    failures = 0
    for want, bodies in ((True, cases["accept"]), (False, cases["reject"])):
        for body in bodies:
            comments = [
                {"body": MARKER_BODY, "author_association": "NONE",
                 "created_at": "2026-01-01T00:00:00Z", "user": BOT_USER},
                {"body": body, "author_association": "OWNER",
                 "created_at": "2026-01-01T00:05:00Z",
                 "user": {"login": "maintainer", "type": "User"}},
            ]
            got_pred = board_stop_check.is_stop_command(body)
            got_decision = board_stop_check.find_stop_request(comments, "999", BOT_LOGIN)
            want_decision = board_stop_check.StopDecision(want, "111" if want else None)
            if got_pred != want or got_decision != want_decision:
                failures += 1
                if verbose:
                    print("::error::verify-board-stop-check: {0}: {1!r}: "
                          "expected is_stop_command()={2}/decision {3!r}, got "
                          "{4}/{5!r}.".format(COMMAND_CASES_FILE, body, want,
                                              want_decision, got_pred, got_decision))
            elif verbose:
                print("[ok] {0}: {1!r} -> {2}".format(
                    COMMAND_CASES_FILE, body, "stop" if want else "no stop"))
    return failures


MUTATIONS = (
    # (name, board_stop_check attribute, replacement factory)
    ("bare \\bstop\\b word match, pre-#539", "is_stop_command",
     lambda: (lambda body: bool(re.search(r"\bstop\b", body or "", re.IGNORECASE)))),
    ("marker author check dropped, pre-#547", "is_loop_marker_author",
     lambda: (lambda comment, bot_login: True)),
    ("MARKER_RUN_RE un-anchored, pre-#547", "MARKER_RUN_RE",
     lambda: re.compile(r"\*\*Run:\*\*\s*(https://\S+/actions/runs/(\d+))")),
    ("first `**Run:**` line in a comment read, pre-#580", "last_run_match",
     lambda: (lambda body: board_stop_check.MARKER_RUN_RE.search(body or ""))),
    ("self-run returned as cancel target, pre-085", "find_stop_request",
     lambda: _pre_085_find_stop_request),
)

_ORIGINAL_FIND_STOP_REQUEST = board_stop_check.find_stop_request


def _pre_085_find_stop_request(comments, current_run_id, bot_login):
    """Reintroduces the pre-085 fallback: cancel_run_id defaults to the
    current run's own id instead of None when no earlier run announced
    itself (today's line 218, before this feature replaced it)."""
    decision = _ORIGINAL_FIND_STOP_REQUEST(comments, current_run_id, bot_login)
    if decision.stand_down and decision.cancel_run_id is None:
        return board_stop_check.StopDecision(True, str(current_run_id))
    return decision


def mutation_check():
    """Each MUTATIONS entry, swapped into board_stop_check, must fail at
    least one fixture -- a gate that still passed would not be guarding
    that rule."""
    failures = 0
    for name, attr, make in MUTATIONS:
        original = getattr(board_stop_check, attr)
        setattr(board_stop_check, attr, make())
        try:
            caught = run_fixtures(verbose=False) + run_command_cases(verbose=False)
        finally:
            setattr(board_stop_check, attr, original)
        if not caught:
            failures += 1
            print("::error::verify-board-stop-check: mutation '{0}' was NOT "
                  "caught by any fixture.".format(name))
        else:
            print("note: mutation caught ({0}: fails {1} case(s)).".format(name, caught))
    return failures


# --- The composite's own cancel guard (issue #547) --------------------------

STUB_GH = r"""#!/usr/bin/env bash
# Stub gh for verify-board-stop-check.py: logs every call with the token it
# ran under, serves the issue comments and per-run JSON from files.
printf '%s|%s\n' "$GH_TOKEN" "$*" >> "$STUB_LOG"
if [ "$1" = "api" ] && [[ "$2" == */comments ]]; then
  shift 2
  while [ $# -gt 0 ]; do
    if [ "$1" = "--jq" ]; then jq -c "$2" "$STUB_COMMENTS"; exit $?; fi
    shift
  done
  exit 1
fi
if [ "$1" = "api" ] && [[ "$2" == */actions/runs/* ]]; then
  f="$STUB_RUNS_DIR/${2##*/}.json"
  if [ -f "$f" ]; then cat "$f"; exit 0; fi
  echo "HTTP 404: Not Found" >&2
  exit 1
fi
if [ "$1" = "run" ] && [ "$2" = "cancel" ]; then
  exit 0
fi
echo "stub gh: unexpected call: $*" >&2
exit 1
"""

REPO = "example/example"
OWN_PATH = ".github/workflows/board-loop.yml"


def _marker(run_id, **overrides):
    comment = {"body": "**Run:** https://github.com/{0}/actions/runs/{1}\n\n"
                       "<!-- wing-commander-board-item: {{}} -->".format(REPO, run_id),
               "author_association": "NONE", "created_at": "2026-01-01T00:00:00Z",
               "user": BOT_USER}
    comment.update(overrides)
    return comment


STOP = {"body": "stop", "author_association": "OWNER",
        "created_at": "2026-01-01T00:05:00Z",
        "user": {"login": "maintainer", "type": "User"}}
RUNS = {
    "222": {"status": "in_progress", "path": OWN_PATH, "repository": {"full_name": REPO}},
    "333": {"status": "in_progress", "path": ".github/workflows/release.yml",
            "repository": {"full_name": REPO}},
    "555": {"status": "completed", "path": OWN_PATH, "repository": {"full_name": REPO}},
    "666": {"status": "in_progress", "path": OWN_PATH, "repository": {"full_name": REPO}},
}
# (name, comments, expected `paused` output, expected cancelled run id or None)
SHELL_CASES = (
    ("an earlier board-loop run is cancelled", [_marker(222), STOP], "true", "222"),
    ("a different workflow's run is not cancelled", [_marker(333), STOP], "true", None),
    ("an unreadable run is not cancelled", [_marker(444), STOP], "true", None),
    ("a completed run is not cancelled", [_marker(555), STOP], "true", None),
    ("an OWNER human's forged marker never reaches gh run cancel",
     [_marker(999),
      _marker(666, created_at="2026-01-01T00:01:00Z", author_association="OWNER",
              user={"login": "maintainer", "type": "User"}),
      STOP], "true", None),
    ("no stop request, nothing cancelled", [_marker(222)], "false", None),
)
GUARD_LINE_RE = re.compile(r'^(\s*)if \[ -z "\$cancel_target_path" \].*; then$', re.MULTILINE)


def composite_check_script():
    with open(COMPOSITE, encoding="utf-8") as fh:
        action = yaml.safe_load(fh)
    for step in action["runs"]["steps"]:
        if step.get("id") == "check":
            return step.get("run")
    return None


def _run_shell_case(script_path, bindir, runs_dir, work, comments):
    case_dir = tempfile.mkdtemp(dir=work)
    comments_path = os.path.join(case_dir, "comments.json")
    with open(comments_path, "w", encoding="utf-8") as fh:
        json.dump(comments, fh)
    log = os.path.join(case_dir, "gh.log")
    out = os.path.join(case_dir, "output")
    for path in (log, out):
        open(path, "w", encoding="utf-8").close()
    env = dict(os.environ)
    env.update({
        "PATH": bindir + os.pathsep + env.get("PATH", ""),
        "GH_TOKEN": "app-token", "CANCEL_TOKEN": "cancel-token",
        "ISSUE_NUMBER": "1", "BOT_LOGIN": BOT_LOGIN,
        "INITIAL_PAUSED": "false", "ISSUE_IS_OPEN": "",
        "GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "999",
        "GITHUB_WORKFLOW_REF": "{0}/{1}@refs/heads/main".format(REPO, OWN_PATH),
        "RUNNER_TEMP": case_dir, "GITHUB_OUTPUT": out,
        "STUB_LOG": log, "STUB_COMMENTS": comments_path, "STUB_RUNS_DIR": runs_dir,
    })
    # Actions runs a `shell: bash` step as `bash --noprofile --norc -eo
    # pipefail {0}`: errexit is on whatever the script's own `set` says.
    proc = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", script_path],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    with open(out, encoding="utf-8") as fh:
        outputs = dict(line.split("=", 1) for line in fh.read().splitlines() if "=" in line)
    with open(log, encoding="utf-8") as fh:
        calls = [line.split("|", 1) for line in fh.read().splitlines()]
    return proc, outputs, calls


def run_shell_cases(script, verbose=True):
    failures = 0
    work = tempfile.mkdtemp(prefix="board-stop-check-")
    try:
        bindir = os.path.join(work, "bin")
        runs_dir = os.path.join(work, "runs")
        os.makedirs(bindir)
        os.makedirs(runs_dir)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8") as fh:
            fh.write(STUB_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        for run_id, run_json in RUNS.items():
            with open(os.path.join(runs_dir, run_id + ".json"), "w", encoding="utf-8") as fh:
                json.dump(run_json, fh)
        script_path = os.path.join(work, "check.sh")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        for name, comments, want_paused, want_cancel in SHELL_CASES:
            proc, outputs, calls = _run_shell_case(script_path, bindir, runs_dir, work, comments)
            problems = []
            if proc.returncode != 0:
                problems.append("exit {0}: {1}".format(proc.returncode, proc.stderr.strip()))
            if outputs.get("paused") != want_paused:
                problems.append("paused={0!r}, expected {1!r}".format(
                    outputs.get("paused"), want_paused))
            cancels = [c for c in calls if c[1].startswith("run cancel ")]
            got_cancel = [c[1].split()[2] for c in cancels]
            if got_cancel != ([want_cancel] if want_cancel else []):
                problems.append("cancelled {0}, expected {1}".format(got_cancel, want_cancel))
            if any(c[0] != "cancel-token" for c in cancels):
                problems.append("gh run cancel ran without the cancel-token")
            if any(c[0] != "app-token" for c in calls if "/comments" in c[1]):
                problems.append("the issue-comment read did not use the App token")
            if problems:
                failures += 1
                if verbose:
                    print("::error::verify-board-stop-check: composite shell: {0}: {1}".format(
                        name, "; ".join(problems)))
            elif verbose:
                print("[ok] composite shell: {0}".format(name))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return failures


def composite_shell_check():
    """Runs the composite's `check` step shell against a stub gh, then again
    with its workflow-path cancel guard disabled -- which must fail."""
    script = composite_check_script()
    if not script:
        print("::error::verify-board-stop-check: no step `id: check` with a run: "
              "block in {0}.".format(COMPOSITE))
        return 1
    if "${{" in script:
        print("::error::verify-board-stop-check: the composite's check step "
              "interpolates an expression into its run: block; pass it through env.")
        return 1
    if shutil.which("jq") is None or shutil.which("bash") is None:
        print("::error::verify-board-stop-check: bash and jq are required.")
        return 1
    failures = run_shell_cases(script)
    mutated, count = GUARD_LINE_RE.subn(r"\1if false; then", script)
    if count != 1:
        print("::error::verify-board-stop-check: could not locate the composite's "
              "workflow-path cancel guard (`if [ -z \"$cancel_target_path\" ] ...`) "
              "to mutate.")
        return failures + 1
    caught = run_shell_cases(mutated, verbose=False)
    if not caught:
        print("::error::verify-board-stop-check: mutation 'cancel guard disabled' "
              "was NOT caught by any composite shell case.")
        return failures + 1
    print("note: mutation caught (cancel guard disabled: fails {0} composite "
          "shell case(s)).".format(caught))
    return failures


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-stop-check: fixtures directory {0} "
              "does not exist.".format(FIXTURES_DIR))
        return 1

    found = {os.path.basename(p) for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))}
    missing = sorted((EXPECTED_FILES | {COMMAND_CASES_FILE}) - found)
    if missing:
        print("::error::verify-board-stop-check: missing fixture(s): "
              "{0}".format(", ".join(missing)))
        return 1

    failures += run_fixtures()
    failures += run_command_cases()
    failures += mutation_check()
    failures += composite_shell_check()

    print("verify-board-stop-check: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
