#!/usr/bin/env python3
"""Gate 135 -- an honoured stop records its stop point, and the kill switch
keeps writing nothing (specs/097-recorded-stop-point, FR-019,
specs/097-recorded-stop-point/contracts/gate-135-stop-point-recording.md).
Numbered 135, not the 128 this feature's own plan/tasks originally claimed
(maintainer review fold leg-3): 128 is spec 074/#821's, and 129-134 are
taken or allocated to specs 089/108/109 and others.

WHAT IT CHECKS
--------------
1. Structural: `.github/actions/wing-commander-board-stop-check/action.yml`
   has a step, gated on `stop-cause == 'stop-request'`, that invokes
   `board_item_marker.py --step stalled ... --add-label "board:stalled"`.
2. Provenance: that step's invocation, and the composite's own
   `board_stop_check.py` invocation, run from `$GITHUB_ACTION_PATH/../../
   scripts/...` (resolved relative to the composite's own trusted
   directory -- maintainer review fold leg-0), never a bare
   `.github/scripts/...` path (spec 095 FR-011/FR-012, research.md D8).
3. Cause-aware messaging: none of `.github/workflows/board-loop.yml`'s six
   stand-down messages hardcodes "kill switch" prose unconditionally --
   each reads `stop-cause` to pick its wording (FR-014).
4. Decision-function agreement: `find_stop_command_comment()`'s "did a
   comment win" answer agrees with `find_stop_request()`'s `stand_down` on
   every fixture under `.github/scripts/tests/board-stop-check/` (Gate 87's
   own corpus, reused, plus this feature's FR-016/FR-009 fixtures, plus the
   FR-006/FR-008 same-run-record fixture, maintainer review fold leg-1) --
   AND, for every fixture carrying its own `expected.stand_down`, both
   functions' answer agrees with that value too (maintainer review fold
   leg-0: the two functions agreeing with EACH OTHER is not enough, since a
   mutation that moves both functions' baseline computation the same wrong
   way would still agree with each other while being wrong).
5. Selection exclusion: a fixture issue carrying a `stalled` marker plus
   `board:stalled` is excluded by `is_excluded()` and never returned by
   `in_flight_candidate()`/`select()`, across ten simulated passes (SC-001).
6. No write on kill-switch-only/closed-issue: the record-write step's own
   `if:` is exactly `stop-cause == 'stop-request'` -- never a condition
   that would also admit `"kill-switch"`/`"closed-issue"` (FR-011/FR-013).
7. No caller-populated snapshot dependency: the composite's own script
   resolutions never reference `$RUNNER_TEMP/wc-pristine` -- every caller
   already invokes this composite from its own trusted `.wc-pristine-repo`
   checkout (spec 086 FR-003), so a second, composite-populated snapshot
   directory is unneeded trust surface (maintainer review fold leg-0).
8. Marker inputs wired: every `wing-commander-board-stop-check` call site in
   `.github/workflows/board-loop.yml` passes both `marker-branch` and
   `marker-base-sha` (maintainer review fold leg-1) -- explicit empty
   strings count as wired (e.g. triage/route before a branch exists, or
   prove, which tracks no branch at all).
9. Single home: `.github/workflows/board-loop.yml` never re-derives the
   stop-cause -> prose/run-label mapping -- no `case` on the cause (the
   STOP_CAUSE name quoted or not, braced or with an expansion operator; a
   variable bound to the composite's `stop-cause` output through env: or
   a shell assignment, with or without a default, or aliased from one; or
   that output's expression), no expression ternary picking prose by
   comparing the cause to a literal (either side, parenthesised or not,
   through the output, a bound env var or a bound job output), and none
   of the composite's own run-labels re-typed. An if/elif chain on the
   cause is not read. That mapping lives
   solely in wing-commander-board-stop-check's own `stop-cause-phrase`/
   `stop-cause-run-label` outputs (CLAUDE.md "Shared logic has exactly one
   home", maintainer review fold leg-2; code review of #899).

Each check's own mutation is applied under --self-test and must be caught
(Principle VIII, SC-009) -- see contracts/gate-135-stop-point-recording.md.
`selftest_registry_coverage()` additionally asserts `CHECKS` stays in sync
with `CHECK_SELFTEST_COVERAGE`/`SELFTESTS` themselves (maintainer review
fold leg-1): deleting a check's own registration from `CHECKS` used to
leave both `run()` and `--self-test` at 0 failures. It also asserts
`CHECKS` names exactly the checks the contract's table lists, so removing
a check from all three registries together still fails (code review of
#899).
"""
import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_eligibility  # noqa: E402
import board_stop_check  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSITE = os.path.join(
    REPO_ROOT, ".github", "actions", "wing-commander-board-stop-check", "action.yml")
BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")
FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-stop-check")
BOT_LOGIN = "wing-commander-bot[bot]"

RECORD_WRITE_IF_RE = re.compile(r"stop-cause\s*==\s*'stop-request'")
RECORD_WRITE_INVOCATION_RE = re.compile(
    r"board_item_marker\.py[\s\S]*?--step\s+stalled[\s\S]*?--add-label\s+\"board:stalled\"")
BARE_SCRIPT_PATH_RE = re.compile(
    r"(?<!GITHUB_ACTION_PATH/\.\./\.\./scripts/)\.github/scripts/"
    r"(board_stop_check|board_item_marker)\.py")
TRUSTED_BOARD_STOP_CHECK_RE = re.compile(
    r"GITHUB_ACTION_PATH/\.\./\.\./scripts/board_stop_check\.py")
# maintainer review fold leg-0: the composite must resolve its scripts
# relative to its own $GITHUB_ACTION_PATH, never a caller-populated
# $RUNNER_TEMP/wc-pristine snapshot -- matches both the shell
# ($RUNNER_TEMP/wc-pristine/scripts/...) and the python
# (os.environ["RUNNER_TEMP"], "wc-pristine") forms, but never the
# unrelated `.wc-pristine-repo` checkout directory every caller already
# uses to resolve this composite itself (spec 086 FR-003).
WC_PRISTINE_DEPENDENCY_RE = re.compile(
    r"\$RUNNER_TEMP/wc-pristine|RUNNER_TEMP[\"']\]\s*,\s*[\"']wc-pristine[\"']")


def _load_composite_steps(text=None):
    with open(COMPOSITE, encoding="utf-8") as fh:
        doc = yaml.safe_load(text if text is not None else fh.read())
    return doc["runs"]["steps"]


def _composite_text():
    with open(COMPOSITE, encoding="utf-8") as fh:
        return fh.read()


def _board_loop_text():
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        return fh.read()


def _find_step(steps, step_id):
    for step in steps:
        if (step or {}).get("id") == step_id:
            return step
    return None


def _record_write_step(steps):
    """The step this feature adds: gated on stop-cause == 'stop-request',
    invoking board_item_marker.py --step stalled ... --add-label
    "board:stalled". Found by shape, not by a hardcoded id, so a rename
    does not itself break this gate."""
    for step in steps:
        step = step or {}
        if_text = str(step.get("if") or "")
        run_text = str(step.get("run") or "")
        if RECORD_WRITE_IF_RE.search(if_text) and RECORD_WRITE_INVOCATION_RE.search(run_text):
            return step
    return None


# --- Check 1: the record-write step exists -----------------------------
def check_record_write_present(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    step = _record_write_step(steps)
    if step is None:
        if verbose:
            print("::error::verify-stop-point-recording: no step in {0} is gated on "
                  "stop-cause == 'stop-request' and invokes board_item_marker.py "
                  "--step stalled ... --add-label \"board:stalled\" (check 1)."
                  .format(COMPOSITE))
        return 1
    if verbose:
        print("[ok] check 1: the record-write step is present")
    return 0


# --- Check 2: provenance -------------------------------------------------
def check_provenance(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    check_step = _find_step(steps, "check")
    record_step = _record_write_step(steps)
    combined = str((check_step or {}).get("run") or "") + "\n" + str((record_step or {}).get("run") or "")
    failures = 0
    bare = BARE_SCRIPT_PATH_RE.search(combined)
    if bare:
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: {0!r} references a bare "
                  ".github/scripts/ path instead of $GITHUB_ACTION_PATH/../../scripts/ "
                  "(check 2).".format(bare.group(0)))
    if not TRUSTED_BOARD_STOP_CHECK_RE.search(str((check_step or {}).get("run") or "")):
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: the `check` step does not "
                  "invoke board_stop_check.py from $GITHUB_ACTION_PATH/../../scripts/ "
                  "(check 2).")
    if not failures and verbose:
        print("[ok] check 2: both invocations run from the composite's own trusted path")
    return failures


# --- Check 7: no caller-populated wc-pristine dependency -----------------
def check_no_wc_pristine_dependency(text=None, verbose=True):
    text = text if text is not None else _composite_text()
    match = WC_PRISTINE_DEPENDENCY_RE.search(text)
    if match:
        if verbose:
            print("::error::verify-stop-point-recording: {0!r} references a "
                  "caller-populated $RUNNER_TEMP/wc-pristine snapshot -- the composite "
                  "must resolve its scripts relative to its own $GITHUB_ACTION_PATH "
                  "instead (check 7).".format(match.group(0)))
        return 1
    if verbose:
        print("[ok] check 7: the composite depends on no caller-populated wc-pristine "
              "snapshot")
    return 0


# --- Check 3: cause-aware messaging -------------------------------------
KILL_SWITCH_TEXT_RE = re.compile(r"kill switch", re.IGNORECASE)
STOP_CAUSE_REF_RE = re.compile(r"stop-cause|STOP_CAUSE", re.IGNORECASE)


def _board_loop_jobs(doc):
    return (doc.get("jobs") or {}).items()


def check_cause_aware_messaging(board_loop_doc=None, verbose=True):
    if board_loop_doc is None:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            board_loop_doc = yaml.safe_load(fh)
    failures = 0
    for job_id, job in _board_loop_jobs(board_loop_doc):
        steps = (job or {}).get("steps") or []
        if not any((s or {}).get("id") == "killswitch-recheck" for s in steps):
            continue
        for step in steps:
            run_text = str((step or {}).get("run") or "")
            if not run_text:
                continue
            if KILL_SWITCH_TEXT_RE.search(run_text) and not STOP_CAUSE_REF_RE.search(run_text):
                failures += 1
                if verbose:
                    print("::error::verify-stop-point-recording: job {0!r} step {1!r} "
                          "hardcodes \"kill switch\" prose with no stop-cause reference "
                          "(check 3).".format(job_id, (step or {}).get("name")))
    if not failures and verbose:
        print("[ok] check 3: every stand-down message reads stop-cause")
    return failures


# --- Check 4: decision-function agreement -------------------------------
def _fixture_files():
    return sorted(
        p for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))
        if os.path.basename(p) != "stop-command-cases.json")


def check_decision_function_agreement(verbose=True):
    failures = 0
    files = _fixture_files()
    if not files:
        print("::error::verify-stop-point-recording: no fixtures found under {0} "
              "(check 4).".format(FIXTURES_DIR))
        return 1
    for path in files:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        comments = spec["comments"]
        bot_login = spec["bot_login"]
        current_run_id = spec.get("current_run_id", "999")
        stand_down = board_stop_check.find_stop_request(comments, current_run_id, bot_login).stand_down
        comment_won = board_stop_check.find_stop_command_comment(
            comments, current_run_id, bot_login) is not None
        if stand_down != comment_won:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: {0}: find_stop_request()."
                      "stand_down={1!r} but find_stop_command_comment() is not None "
                      "= {2!r} (check 4).".format(os.path.basename(path), stand_down, comment_won))
        elif verbose:
            print("[ok] check 4: {0}: both functions agree (stand_down={1!r})".format(
                os.path.basename(path), stand_down))
        # maintainer review fold leg-0: agreement between the two functions
        # is not by itself enough -- a mutation that moves both functions'
        # baseline computation the same wrong way would still agree with
        # each other while disagreeing with the fixture's own known-correct
        # answer. Compare against `expected.stand_down` too, for every
        # fixture that carries one (Gate 87's own corpus already does;
        # this feature's four new fixtures carry one for this reason).
        expected = spec.get("expected")
        if expected is not None and stand_down != expected.get("stand_down"):
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: {0}: find_stop_request()."
                      "stand_down={1!r} but the fixture's own expected stand_down={2!r} "
                      "(check 4).".format(os.path.basename(path), stand_down,
                                          expected.get("stand_down")))
    return failures


# --- Check 5: selection exclusion ---------------------------------------
STALLED_ISSUE = {
    "number": 402, "author": {"login": "someone"}, "authorAssociation": "NONE",
    "labels": [{"name": "board:stalled"}], "state": "OPEN",
    "createdAt": "2026-01-01T00:00:00Z",
}
STALLED_MARKER_BODY = (
    "**Run:** https://github.com/example/example/actions/runs/1\n\n"
    "<!-- wing-commander-board-item: "
    "{\"step\": \"stalled\", \"round\": 0, \"pr\": null, \"branch\": null, \"base_sha\": null} -->")


def _stalled_fixture():
    open_issues = [STALLED_ISSUE]
    comments_by_issue = {402: [{
        "created_at": "2026-01-02T00:00:00Z", "body": STALLED_MARKER_BODY,
        "user": {"login": BOT_LOGIN, "type": "Bot"},
    }]}
    pr_state_by_number = {}
    labeled_events_by_issue = {402: []}
    return open_issues, comments_by_issue, pr_state_by_number, labeled_events_by_issue


def check_selection_exclusion(verbose=True):
    open_issues, comments_by_issue, pr_state_by_number, labeled_events_by_issue = _stalled_fixture()
    failures = 0
    excluded, reason = board_eligibility.is_excluded(STALLED_ISSUE)
    if not (excluded and reason == "board:stalled"):
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: is_excluded() did not exclude "
                  "the stalled fixture (got {0!r}) (check 5).".format((excluded, reason)))
    for _ in range(10):
        candidate, _multiple = board_eligibility.in_flight_candidate(
            open_issues, comments_by_issue, pr_state_by_number, BOT_LOGIN)
        if candidate is not None:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: in_flight_candidate() "
                      "returned the stalled issue (check 5).")
            break
    for _ in range(10):
        selected = board_eligibility.select(
            open_issues, labeled_events_by_issue, comments_by_issue, pr_state_by_number, BOT_LOGIN)
        if selected is not None:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: select() returned the "
                      "stalled issue (check 5).")
            break
    if not failures and verbose:
        print("[ok] check 5: the stalled fixture is excluded across ten simulated passes")
    return failures


# --- Check 6: no write on kill-switch-only/closed-issue -----------------
def check_no_write_on_stand_down(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    step = _record_write_step(steps)
    if step is None:
        if verbose:
            print("::error::verify-stop-point-recording: no record-write step found "
                  "(check 6).")
        return 1
    if_text = str(step.get("if") or "")
    if not re.fullmatch(r"\s*steps\.check\.outputs\.stop-cause\s*==\s*'stop-request'\s*", if_text):
        print("::error::verify-stop-point-recording: the record-write step's `if:` "
              "is {0!r} -- it must be exactly `steps.check.outputs.stop-cause == "
              "'stop-request'`, never a broader condition that would also admit "
              "\"kill-switch\"/\"closed-issue\" (check 6).".format(if_text))
        return 1
    if verbose:
        print("[ok] check 6: the record-write step's `if:` admits only stop-request")
    return 0


# --- Check 8: marker-branch/marker-base-sha wired at every call site ----
STOP_CHECK_USES_RE = re.compile(r"wing-commander-board-stop-check$")


def check_marker_inputs_wired(board_loop_doc=None, verbose=True):
    """Every `wing-commander-board-stop-check` call site in board-loop.yml
    must wire BOTH `marker-branch` and `marker-base-sha` -- a site that
    omits either one silently loses the item's branch/base-sha on its
    stop-point record marker rather than failing anything (maintainer
    review: nothing previously asserted these call sites -- seven today,
    one per job from select to prove -- actually pass them through)."""
    if board_loop_doc is None:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            board_loop_doc = yaml.safe_load(fh)
    failures = 0
    found = 0
    for job_id, job in _board_loop_jobs(board_loop_doc):
        for step in (job or {}).get("steps") or []:
            uses = str((step or {}).get("uses") or "")
            if not STOP_CHECK_USES_RE.search(uses):
                continue
            found += 1
            with_block = (step or {}).get("with") or {}
            missing = [k for k in ("marker-branch", "marker-base-sha") if k not in with_block]
            if missing:
                failures += 1
                if verbose:
                    print("::error::verify-stop-point-recording: job {0!r} step {1!r} "
                          "does not wire {2} to the wing-commander-board-stop-check "
                          "composite (check 8).".format(
                              job_id, (step or {}).get("name"), " and ".join(missing)))
    if found == 0:
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: no wing-commander-board-stop-check "
                  "call site found in {0} (check 8).".format(BOARD_LOOP))
    if not failures and verbose:
        print("[ok] check 8: all {0} wing-commander-board-stop-check call site(s) wire "
              "marker-branch/marker-base-sha".format(found))
    return failures


# --- Check 9: the stop-cause case block has exactly one home -------------
# A `case` on the stop-cause: the STOP_CAUSE name itself, quoted or not,
# braced or not, with or without a parameter-expansion operator
# (`${STOP_CAUSE,,}`, `${STOP_CAUSE:-}`); a variable bound to the
# composite's own `stop-cause` output (env: at any level, or a shell
# assignment, with or without a `|| '...'` default, the cause either
# operand of the `||`), to a job output bound to it, or aliased from one
# (`c="$STOP_CAUSE"`); or the expression of the output or of such an env
# var directly (code review of #899, then of #940: the first form matched
# only `case "$STOP_CAUSE"`).
# A `|| '...'` default, its literal free to hold a `}`.
_DEFAULT = r"(?:\|\|(?:'[^']*'|[^}'])*)?"
# Operands ahead of the cause in a `||` chain (`x || <cause>`).
_LEAD = r"(?:(?:'[^']*'|[^}'])*?\|\|\s*)?"
_STOP_CAUSE = r"[\w.-]+\.outputs\.stop-cause(?![\w-])"


def _cause_expr_re(causes, prefix=r"", suffix=r"", flags=0):
    """`${{ <cause> }}` for any of `causes` (regex alternatives), a lead
    and a default allowed, wrapped in `prefix`/`suffix`."""
    return re.compile(prefix + r"\$\{\{\s*" + _LEAD + "(?:" + "|".join(causes) + r")\s*"
                      + _DEFAULT + r"\}\}" + suffix, flags)


STOP_CAUSE_OUTPUT_RE = _cause_expr_re([_STOP_CAUSE])
CASE_SUBJECT_RE = re.compile(r'\bcase\s+"?\$\{?(\w+)[^}"\s]*\}?"?\s+in\b')
# Where a shell assignment can start: the head of a command, never an
# argument (`--cause=$X`) -- see _blank_quoted_args for quoted text. Every
# word of a prefix list (`A=1 c="$X" cmd`), behind `env` and its options
# too, is an assignment (code review of #954). A case arm's `)` and an
# `if`/`while` condition head a command too (code review of #954, round 9:
# main's unanchored alias regex caught `a) c="$STOP_CAUSE" ;;`).
_CMD_POS_RE = re.compile(
    r"(?:^|[;&|({)!]|\b(?:if|elif|while|until|then|do|else|export|local|readonly"
    r"|declare|typeset)\b)[ \t]*"
    r"(?:env(?:[ \t]+-\S+)*[ \t]+)?", re.M)
_ASSIGN_WORD_RE = re.compile(
    r"""\w+=(?:"(?:\\.|[^"\\])*"|'[^']*'|\$\{\{.*?\}\}|\\.|[^\s"';&|)])*""")
SHELL_BINDING_RE = _cause_expr_re([_STOP_CAUSE], prefix=r"""^(\w+)=["']?""")
SHELL_ALIAS_RE = re.compile(r"""^(\w+)=["']?\$\{?(\w+)[^}"'\s]*\}?["']?$""")


def _prefix_assignments(run):
    """Every assignment word at a command's head in `run`, in order."""
    words = []
    for m in _CMD_POS_RE.finditer(run):
        i = m.end()
        while True:
            w = _ASSIGN_WORD_RE.match(run, i)
            if not w:
                break
            words.append(w.group(0))
            i = w.end()
            gap = re.match(r"[ \t]+", run[i:])
            if not gap:
                break
            i += gap.end()
    return words


def _findall_assignments(pattern, run):
    return [m.groups() if pattern.groups > 1 else m.group(1)
            for w in _prefix_assignments(run) for m in [pattern.match(w)] if m]
# The run-label/phrase picked by comparing the cause to a non-empty literal
# in an expression -- the pre-leg-2 per-job ternary -- on either side of
# the comparison, parenthesised (once or more) or not, through the output
# itself, an env var bound to it, or a job output bound to it.
# `stop-cause != ''` ("did any stop win") is the comparison the callers
# legitimately make, and a boolean flag (`&& 'true' || 'false'`) picks no
# prose. The picked operand is a prose literal (not 'true'/'false', and
# not the left side of a further comparison, as in a compound if:) or a
# format().
_PICK = (r"(?:\s*\))*\s*&&\s*(?:\(\s*)*"
         r"(?:'(?!(?:true|false)')[^']*'(?!\s*(?:==|!=))|format\()")
COMPOSITE_RUN_LABEL_RE = re.compile(r'stop_cause_run_label="([^"]+)"')


def _blank_quoted_args(run):
    """`run` with every quoted string that is not an assignment's value
    emptied, so `echo "c=$STOP_CAUSE"` binds nothing while
    `c="$STOP_CAUSE"` still does (code review of #940). A trailing
    comment is dropped first, so its apostrophe (`# don't`) opens no
    quote that would blank the lines after it. Quotes start afresh inside
    `$( )`, in a double-quoted string or not, so
    `x="$(printf 'a'"'"'s' "$r")"` closes where bash closes it and the
    lines after it are still read (code review of #954)."""
    return _blank_from(run, 0, False)[0]


def _blank_from(run, i, nested):
    """-> (blanked text, end) from `run[i:]`; `nested` stops at the `)`
    closing a `$( )` and returns past it. A heredoc body is copied
    through as raw text, never read for quotes, so its apostrophe
    (`it's`) opens nothing; an arithmetic `<<` opens no heredoc (code
    review of #954)."""
    out, depth, pending = [], 0, []
    while i < len(run):
        ch = run[i]
        if ch == "\\":
            out.append(run[i:i + 2])
            i += 2
            continue
        if ch == "\n" and pending:
            i += 1
            out.append("\n")
            for delim in pending:
                while i < len(run):
                    end = run.find("\n", i)
                    end = len(run) if end < 0 else end
                    line = run[i:end]
                    out.append(run[i:end + 1])
                    i = end + 1
                    if line.strip() == delim:
                        break
            pending = []
            continue
        if run.startswith("$((", i) or (
                run.startswith("((", i) and (not i or run[i - 1] in " \t\n;&|(")):
            j, level = i + (3 if ch == "$" else 2), 2
            while j < len(run) and level:
                level += {"(": 1, ")": -1}.get(run[j], 0)
                j += 1
            out.append(run[i:j])
            i = j
            continue
        if run.startswith("<<<", i):
            out.append("<<<")
            i += 3
            continue
        m = re.match(r"<<-?[ \t]*\\?(['\"]?)([\w.+@%:,/-]+)\1", run[i:i + 80]) \
            if run.startswith("<<", i) else None
        if m:
            out.append(run[i:i + m.end()])
            pending.append(m.group(2))
            i += m.end()
            continue
        if ch == "#" and (not i or run[i - 1] in " \t\n;&|("):
            end = run.find("\n", i)
            i = len(run) if end < 0 else end
            continue
        if run.startswith("$(", i) and not run.startswith("$((", i):
            inner, i = _blank_from(run, i + 2, True)
            out.append("$(" + inner + ")")
            continue
        if nested and ch == "(":
            depth += 1
        elif nested and ch == ")":
            if not depth:
                return "".join(out), i + 1
            depth -= 1
        elif ch == "'":
            end = run.find("'", i + 1)
            end = len(run) if end < 0 else end
            keep = i and run[i - 1] == "="
            out.append(run[i:end + 1] if keep else "''")
            i = end + 1
            continue
        elif ch == '"':
            keep = i and run[i - 1] == "="
            body, j = [], i + 1
            while j < len(run) and run[j] != '"':
                if run[j] == "\\":
                    body.append(run[j:j + 2] if keep else "")
                    j += 2
                elif run.startswith("$(", j) and not run.startswith("$((", j):
                    inner, j = _blank_from(run, j + 2, True)
                    body.append("$(" + inner + ")")
                else:
                    if keep:
                        body.append(run[j])
                    j += 1
            # A blanked string keeps only its `$( )` commands, which run.
            out.append('"' + "".join(body) + '"')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), i


def _non_comment_lines(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _bound_env_names(env, bound_re=STOP_CAUSE_OUTPUT_RE):
    return {name for name, value in (env or {}).items()
            if bound_re.search(str(value))}


def _strings(obj):
    """Every string value in a parsed YAML node, depth first."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _ternary_hits(strings, causes):
    cause = "(?:" + "|".join(causes) + ")"
    found = []
    for pattern in (re.compile(cause + r"\s*(?:==|!=)\s*'[^']+'" + _PICK),
                    re.compile(r"'[^']+'\s*(?:==|!=)\s*" + cause + _PICK)):
        for value in strings:
            for m in pattern.finditer(_non_comment_lines(value)):
                found.append("an expression picking prose by cause: `{0}`".format(m.group(0)))
    return found


def _pasted_stop_cause_mappings(text, composite_text):
    """-> [description] for every place `text` (board-loop.yml) re-derives
    the stop-cause -> phrase/run-label mapping."""
    found = []
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return ["board-loop.yml does not parse ({0}), so check 9 cannot read its "
                "steps".format(str(exc).splitlines()[0])]
    if not isinstance(doc, dict):
        return ["board-loop.yml is not a mapping, so check 9 cannot read its steps"]
    jobs = doc.get("jobs") or {}
    workflow_env = _bound_env_names(doc.get("env"))
    # A job output bound to the cause the way an env var is (the
    # expression itself, a default allowed) -- never a boolean derived
    # from it, such as `stop-cause != ''`.
    job_outputs = {(job_id, name) for job_id, job in jobs.items()
                   for name, value in ((job or {}).get("outputs") or {}).items()
                   if STOP_CAUSE_OUTPUT_RE.search(str(value))}
    base_causes = [_STOP_CAUSE]
    base_causes += [r"needs\." + re.escape(j) + r"\.outputs\." + re.escape(o) + r"(?![\w-])"
                    for j, o in sorted(job_outputs)]
    # An env var bound to a job output that is itself bound to the cause
    # is bound to the cause too (code review of #940).
    bound_re = _cause_expr_re(base_causes)
    found += _ternary_hits(
        [v for k, v in doc.items() if k != "jobs" for v in _strings(v)],
        base_causes + [r"env\." + re.escape(n) + r"\b" for n in sorted(workflow_env)])
    for job_id, job in jobs.items():
        job = job or {}
        job_env = workflow_env | _bound_env_names(job.get("env"), bound_re)
        # Env names bound anywhere in THIS job; another job's binding of the
        # same name says nothing about this one (code review of #940).
        env_names = set(job_env)
        for step in job.get("steps") or []:
            step = step or {}
            raw_run = _non_comment_lines(str(step.get("run") or ""))
            run = _blank_quoted_args(raw_run)
            step_env = _bound_env_names(step.get("env"), bound_re)
            env_names |= step_env
            bound = {"STOP_CAUSE"} | job_env | step_env
            bound |= set(_findall_assignments(SHELL_BINDING_RE, run))
            while True:
                more = {lhs for lhs, rhs in _findall_assignments(SHELL_ALIAS_RE, run)
                        if rhs.upper() in {b.upper() for b in bound}} - bound
                if not more:
                    break
                bound |= more
            bound_upper = {b.upper() for b in bound}
            for m in CASE_SUBJECT_RE.finditer(raw_run):
                if m.group(1).upper() in bound_upper:
                    found.append("job {0!r} step {1!r}: `{2}`".format(
                        job_id, step.get("name"), m.group(0)))
            # A `case` on the cause's expression, or on a bound env var's
            # (`case "${{ env.C }}"`).
            case_on_expr = _cause_expr_re(
                base_causes + [r"env\." + re.escape(n) + r"\b"
                               for n in sorted(job_env | step_env)],
                prefix=r'\bcase\s+"?', suffix=r'"?\s+in\b')
            for m in case_on_expr.finditer(raw_run):
                found.append("job {0!r} step {1!r}: `{2}`".format(
                    job_id, step.get("name"), m.group(0)))
        found += _ternary_hits(
            list(_strings(job)),
            base_causes + [r"env\." + re.escape(n) + r"\b" for n in sorted(env_names)])
    code = _non_comment_lines(text)
    for label in sorted(set(COMPOSITE_RUN_LABEL_RE.findall(composite_text))):
        if label in code:
            found.append("the composite's own run-label {0!r}, re-typed".format(label))
    return found


def check_no_pasted_stop_cause_case(text=None, verbose=True, composite_text=None):
    """CLAUDE.md "Shared logic has exactly one home" (maintainer review fold
    leg-2): the stop-cause -> prose/run-label mapping lives solely in
    wing-commander-board-stop-check/action.yml's own `stop-cause-phrase`/
    `stop-cause-run-label` outputs; a `case` on the cause, an expression
    ternary picking prose by cause, or one of the composite's run-labels
    re-typed into board-loop.yml is this same logic re-derived a second
    time."""
    text = text if text is not None else _board_loop_text()
    composite_text = composite_text if composite_text is not None else _composite_text()
    found = _pasted_stop_cause_mappings(text, composite_text)
    if found:
        if verbose:
            for where in found:
                print("::error::verify-stop-point-recording: {0} re-derives the stop-cause "
                      "mapping ({1}) -- read wing-commander-board-stop-check's own "
                      "`stop-cause-phrase`/`stop-cause-run-label` outputs instead "
                      "(check 9).".format(BOARD_LOOP, where))
        return len(found)
    if verbose:
        print("[ok] check 9: board-loop.yml never re-derives the stop-cause mapping")
    return 0


CHECKS = (
    ("check 1", check_record_write_present),
    ("check 2", check_provenance),
    ("check 3", check_cause_aware_messaging),
    ("check 4", check_decision_function_agreement),
    ("check 5", check_selection_exclusion),
    ("check 6", check_no_write_on_stand_down),
    ("check 7", check_no_wc_pristine_dependency),
    ("check 8", check_marker_inputs_wired),
    ("check 9", check_no_pasted_stop_cause_case),
)


def run(verbose=True):
    failures = 0
    for _name, fn in CHECKS:
        failures += fn(verbose=verbose)
    return failures


# --- Self-test -----------------------------------------------------------
def _mutate_composite_text(pattern, replacement, count=1):
    text = _composite_text()
    mutated, n = re.subn(pattern, replacement, text, count=count)
    if n != count:
        raise AssertionError("mutation pattern {0!r} matched {1} time(s), expected {2}"
                              .format(pattern, n, count))
    return yaml.safe_load(mutated)["runs"]["steps"]


def selftest_check1():
    case = "record-write step's if: removed -> check 1 fails"
    mutated_steps = _mutate_composite_text(
        r"(id: record-stop-point\n) {6}if: steps\.check\.outputs\.stop-cause == 'stop-request'\n",
        r"\1", count=1)
    failures = check_record_write_present(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check2():
    case = "board_item_marker.py invocation rewritten to a bare .github/scripts/ path -> check 2 fails"
    mutated_steps = _mutate_composite_text(
        r'\$GITHUB_ACTION_PATH/\.\./\.\./scripts/board_item_marker\.py',
        r'.github/scripts/board_item_marker.py', count=1)
    failures = check_provenance(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check7():
    case = "board_stop_check.py invocation reverted to $RUNNER_TEMP/wc-pristine -> check 7 fails"
    text = _composite_text()
    mutated, n = re.subn(
        r'\$GITHUB_ACTION_PATH/\.\./\.\./scripts/board_stop_check\.py"\)"',
        r'$RUNNER_TEMP/wc-pristine/scripts/board_stop_check.py")"',
        text, count=1)
    if n != 1:
        raise AssertionError("selftest_check7: mutation pattern matched {0} time(s), "
                              "expected 1".format(n))
    failures = check_no_wc_pristine_dependency(text=mutated, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check3():
    case = "a hardcoded \"kill switch\" stand-down message -> check 3 fails"
    doc = {
        "jobs": {
            "triage": {
                "steps": [
                    {"id": "killswitch-recheck"},
                    {"name": "Act", "run": 'echo "board-loop: kill switch set -- standing down."'},
                ]
            }
        }
    }
    failures = check_cause_aware_messaging(board_loop_doc=doc, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check4():
    case = "find_stop_command_comment() baseline forced empty -> check 4 fails"
    original = board_stop_check.find_stop_command_comment

    def _no_baseline(comments, current_run_id, bot_login):
        ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
        winner = None
        for comment in ordered:
            if (comment.get("author_association") in board_stop_check.MAINTAINER_ASSOCIATIONS
                    and board_stop_check.is_stop_command(comment.get("body"))):
                winner = comment
        return winner

    board_stop_check.find_stop_command_comment = _no_baseline
    try:
        failures = check_decision_function_agreement(verbose=False)
    finally:
        board_stop_check.find_stop_command_comment = original
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}: {1} fixture(s) disagreed).".format(case, failures))
    return 0


def _pre_fix_find_stop_request(comments, current_run_id, bot_login):
    """The pre-FR-006/FR-008 shape of `find_stop_request()`: every marker
    advances the baseline, including one carrying `current_run_id` -- shared
    by `selftest_check4_samerun_record` (reverts this function alone) and
    `selftest_check4_samerun_record_both` (reverts this and
    `_pre_fix_find_stop_command_comment` together)."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
    current_run_id = str(current_run_id)
    baseline = ""
    last_other_run_id = None
    for comment in ordered:
        if not board_stop_check.is_loop_marker_author(comment, bot_login):
            continue
        match = board_stop_check.last_run_match(comment.get("body"))
        if not match:
            continue
        baseline = comment.get("created_at") or baseline
        run_id = match.group(2)
        if run_id != current_run_id:
            last_other_run_id = run_id
    stop_seen = False
    for comment in ordered:
        if (comment.get("created_at") or "") < baseline:
            continue
        if (comment.get("author_association") in board_stop_check.MAINTAINER_ASSOCIATIONS
                and board_stop_check.is_stop_command(comment.get("body"))):
            stop_seen = True
    if not stop_seen:
        return board_stop_check.StopDecision(False, None)
    return board_stop_check.StopDecision(True, last_other_run_id)


def selftest_check4_samerun_record():
    case = ("own-run-record-does-not-undo-stand-down.json: pre-fix "
            "find_stop_request() (baseline advanced by every marker, "
            "including same-run ones) -> check 4 fails")

    original = board_stop_check.find_stop_request
    board_stop_check.find_stop_request = _pre_fix_find_stop_request
    try:
        failures = check_decision_function_agreement(verbose=False)
    finally:
        board_stop_check.find_stop_request = original
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}: {1} fixture(s) disagreed).".format(case, failures))
    return 0


def _pre_fix_find_stop_command_comment(comments, current_run_id, bot_login):
    """Mirrors `_pre_fix_find_stop_request` above, but for
    `find_stop_command_comment()` -- drops the same-run-id exclusion
    (FR-006/FR-008) from its baseline computation too, so a self-test can
    revert the fix in BOTH functions at once (maintainer review: reverting
    only one function makes them disagree with each other, which check 4's
    agreement half already catches; reverting both keeps them agreeing with
    each other while both disagree with a fixture's own `expected`)."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
    baseline = ""
    for comment in ordered:
        if not board_stop_check.is_loop_marker_author(comment, bot_login):
            continue
        match = board_stop_check.last_run_match(comment.get("body"))
        if not match:
            continue
        baseline = comment.get("created_at") or baseline
    winner = None
    for comment in ordered:
        if (comment.get("created_at") or "") < baseline:
            continue
        if (comment.get("author_association") in board_stop_check.MAINTAINER_ASSOCIATIONS
                and board_stop_check.is_stop_command(comment.get("body"))):
            winner = comment
    return winner


def selftest_check4_samerun_record_both():
    case = ("own-run-record-does-not-undo-stand-down.json: pre-fix "
            "find_stop_request() AND find_stop_command_comment() reverted "
            "together (both lose the same-run baseline exclusion, so they "
            "still agree with each other) -> check 4 fails against the "
            "fixture's own expected stand_down")
    original_request = board_stop_check.find_stop_request
    original_comment = board_stop_check.find_stop_command_comment
    board_stop_check.find_stop_request = _pre_fix_find_stop_request
    board_stop_check.find_stop_command_comment = _pre_fix_find_stop_command_comment
    try:
        failures = check_decision_function_agreement(verbose=False)
    finally:
        board_stop_check.find_stop_request = original_request
        board_stop_check.find_stop_command_comment = original_comment
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}: {1} fixture(s) disagreed).".format(case, failures))
    return 0


def selftest_check5():
    case = "board:stalled label omitted from the fixture -> check 5's exclusion assertion no longer holds"
    unlabeled_issue = dict(STALLED_ISSUE)
    unlabeled_issue["labels"] = []
    excluded, _reason = board_eligibility.is_excluded(unlabeled_issue)
    if excluded:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught "
              "(still excluded with no label).".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check6():
    case = "record-write step's if: broadened to stop-cause != '' -> check 6 fails"
    mutated_steps = _mutate_composite_text(
        r"(id: record-stop-point\n {6}if: steps\.check\.outputs\.stop-cause) == 'stop-request'\n",
        r"\1 != ''\n", count=1)
    failures = check_no_write_on_stand_down(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check8():
    case = "one wing-commander-board-stop-check call site drops marker-branch -> check 8 fails"
    doc = {
        "jobs": {
            "triage": {
                "steps": [
                    {"uses": "./.wc-pristine-repo/.github/actions/wing-commander-board-stop-check",
                     "with": {"marker-branch": "x", "marker-base-sha": "y"}},
                ]
            },
            "route": {
                "steps": [
                    {"uses": "./.wc-pristine-repo/.github/actions/wing-commander-board-stop-check",
                     "with": {"marker-base-sha": "y"}},
                ]
            },
        }
    }
    failures = check_marker_inputs_wired(board_loop_doc=doc, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


# Each is a job appended under board-loop.yml's `jobs:` (its last top-level
# key), so the mutated text still parses and the env-binding forms are read
# the same way the real file is.
_CHECK9_JOB = (
    "\n  zz-check9-mutation:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - name: re-pasted mapping\n{env}        run: |\n{run}")
CHECK9_MUTATIONS = (
    ('the original `case "$STOP_CAUSE"` form', "",
     '          case "$STOP_CAUSE" in\n          esac\n'),
    ("an unquoted, braced `case ${STOP_CAUSE}`", "",
     "          case ${STOP_CAUSE} in\n          esac\n"),
    ("a renamed env var bound to the stop-cause output",
     "        env:\n          CAUSE: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n",
     '          case "$CAUSE" in\n          esac\n'),
    ("a shell variable assigned from the stop-cause output", "",
     '          why="${{ steps.killswitch-recheck.outputs.stop-cause }}"\n'
     "          case $why in\n          esac\n"),
    ("a `case` directly on the stop-cause expression", "",
     '          case "${{ steps.killswitch-recheck.outputs.stop-cause }}" in\n          esac\n'),
    ("a re-pasted run-label ternary", "",
     "          echo \"${{ steps.killswitch-recheck.outputs.stop-cause == 'stop-request' "
     "&& 'paused' || 'halted' }}\"\n"),
    ("one of the composite's run-labels re-typed", "",
     '          label="triage: stopped (stop-request)"\n'),
    ("a parameter-expansion `case ${STOP_CAUSE,,}`", "",
     "          case \"${STOP_CAUSE,,}\" in\n          esac\n"),
    ("an env var bound to the output with a default",
     "        env:\n          C: ${{ steps.killswitch-recheck.outputs.stop-cause || 'none' }}\n",
     '          case "$C" in\n          esac\n'),
    ("a two-hop shell alias of STOP_CAUSE", "",
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    ("a parenthesised ternary", "",
     "          echo \"${{ (steps.killswitch-recheck.outputs.stop-cause == 'stop-request') "
     "&& 'paused' || 'halted' }}\"\n"),
    ("a literal-first ternary", "",
     "          echo \"${{ 'kill-switch' == steps.killswitch-recheck.outputs.stop-cause "
     "&& 'halted' || 'paused' }}\"\n"),
    ("a ternary on an env var bound to the output",
     "        env:\n          CAUSE_ENV: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n",
     "          echo \"${{ env.CAUSE_ENV == 'kill-switch' && 'halted' || 'paused' }}\"\n"),
    # Code review of #940: the forms the first two rounds still missed.
    ("a `case` on a bound env var's expression",
     "        env:\n          C: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n",
     '          case "${{ env.C }}" in\n          esac\n'),
    ("an env var bound with a default holding a `}`",
     "        env:\n          C: ${{ steps.killswitch-recheck.outputs.stop-cause || '}' }}\n",
     '          case "$C" in\n          esac\n'),
    ("an env var bound with the cause as the second `||` operand",
     "        env:\n          C: ${{ steps.other.outputs.x || steps.killswitch-recheck.outputs.stop-cause }}\n",
     '          case "$C" in\n          esac\n'),
    ("a doubly parenthesised ternary", "",
     "          echo \"${{ ((steps.killswitch-recheck.outputs.stop-cause == 'stop-request')) "
     "&& 'paused' || 'halted' }}\"\n"),
    # Code review of #954: a trailing comment's apostrophe opened a quote.
    ("a shell alias after a trailing comment with an apostrophe", "",
     "          echo start # don't worry\n"
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    # Code review of #954, round 2: quotes restart inside `$( )`, and a
    # prefix list or `env` assigns every word ahead of the command.
    ("a shell alias after a `$( )` whose quotes nest", "",
     "          x=\"$(printf 'a'\"'\"'s %s' \"$r\")\"\n"
     "          echo \"issue #1, it's\"\n"
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    ("a shell alias second in a prefix list", "",
     '          A=1 c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    ("a shell alias behind env", "",
     '          env -i c="$STOP_CAUSE" true\n          case "$c" in\n          esac\n'),
    # Code review of #954, round 3: a heredoc body's apostrophe, and an
    # arithmetic `<<`, opened nothing that hides the lines after them.
    ("a shell alias after a heredoc body with an apostrophe", "",
     "          cat <<EOF\n          it's done\n          EOF\n"
     "          n=$(( 1 << k ))\n"
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    # Round 6: a delimiter bash accepts with a `-` in it.
    ("a shell alias after a `-` delimited heredoc with an apostrophe", "",
     "          cat <<'PY-EOF'\n          it's done\n          PY-EOF\n"
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    # Round 7: a backslash-quoted delimiter (`<<\EOF`) hides its body too.
    ("a shell alias after a backslash-quoted heredoc with an apostrophe", "",
     "          cat <<\\EOF\n          it's done\n          EOF\n"
     '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n'),
    # Round 9: a case arm's `)` and an `if` condition head a command.
    ("a shell alias in a case arm", "",
     '          case "$m" in\n          a) c="$STOP_CAUSE" ;;\n          esac\n'
     '          case "$c" in\n          esac\n'),
    ("a shell alias as an if condition", "",
     '          if c="$STOP_CAUSE"; then :; fi\n          case "$c" in\n          esac\n'),
)
# Legitimate shapes check 9 must leave alone: gating on the cause, and a
# boolean flag that picks no prose.
CHECK9_ALLOWED = (
    ("an if: gated on the cause", "",
     "          echo gated\n",
     "        if: steps.killswitch-recheck.outputs.stop-cause == 'stop-request'\n"),
    ("a boolean flag derived from the cause", "",
     "          echo \"${{ steps.killswitch-recheck.outputs.stop-cause == 'stop-request' "
     "&& 'true' || 'false' }}\"\n", ""),
    ("a compound if: comparing the cause and then a second operand", "",
     "          echo gated\n",
     "        if: steps.killswitch-recheck.outputs.stop-cause == 'stop-request' && "
     "'yes' == env.ALWAYS\n"),
    # Code review of #940: SHELL_ALIAS_RE read these as assignments.
    ("an assignment-shaped string inside quotes", "",
     '          echo "c=$STOP_CAUSE"\n          case "$c" in\n          esac\n', ""),
    ("an assignment-shaped flag argument", "",
     '          tool --c=$STOP_CAUSE\n          case "$c" in\n          esac\n', ""),
)


def _mut_workflow_env_binding(text):
    """A top-level env: binding of the cause, then a `case` on it."""
    anchor = "\nenv:\n"
    if text.count(anchor) != 1:
        raise AssertionError("board-loop.yml's top-level env: block moved")
    text = text.replace(anchor, anchor + "  WF_CAUSE: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n", 1)
    return text.rstrip("\n") + "\n" + _CHECK9_JOB.format(
        env="", run='          case "$WF_CAUSE" in\n          esac\n')


def _mut_job_output_ternary(text):
    """A job output bound to the cause, and a ternary on it downstream."""
    return (text.rstrip("\n") + "\n"
            + "\n  zz-cause-out:\n    runs-on: ubuntu-latest\n    outputs:\n"
              "      why: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n"
              "    steps:\n      - run: echo hi\n"
            + _CHECK9_JOB.format(
                env="", run="          echo \"${{ needs.zz-cause-out.outputs.why == "
                            "'kill-switch' && 'halted' || 'paused' }}\"\n"))


def _mut_job_output_env_case(text):
    """A job output bound to the cause, bound to an env var downstream,
    then `case`d (code review of #940)."""
    return (text.rstrip("\n") + "\n"
            + "\n  zz-cause-out:\n    runs-on: ubuntu-latest\n    outputs:\n"
              "      why: ${{ steps.killswitch-recheck.outputs.stop-cause }}\n"
              "    steps:\n      - run: echo hi\n"
            + _CHECK9_JOB.format(
                env="        env:\n          W: ${{ needs.zz-cause-out.outputs.why }}\n",
                run='          case "$W" in\n          esac\n'))


def _mut_alias_in_route_step(text):
    """An aliased `case` pasted into route's real spec-request step, after
    its `"$(jq -r '...' "...")"` line (code review of #954)."""
    anchor = "          agent_proposal=\"$(jq -r '.decision.agent_proposal' "
    if text.count(anchor) != 1:
        raise AssertionError("board-loop.yml's agent_proposal= line moved")
    head, tail = text.split(anchor, 1)
    line, rest = tail.split("\n", 1)
    return (head + anchor + line + "\n"
            + '          c="$STOP_CAUSE"\n          case "$c" in\n          esac\n' + rest)


def _mut_unparseable(text):
    """board-loop.yml that no longer parses."""
    return text.rstrip("\n") + "\n  zz-broken: [unclosed\n"


CHECK9_TEXT_MUTATIONS = (
    ("a top-level env: binding of the cause, then a case on it", _mut_workflow_env_binding),
    ("a ternary on a job output bound to the cause", _mut_job_output_ternary),
    ("an env var bound to a job output bound to the cause, then a case on it",
     _mut_job_output_env_case),
    ("an aliased case pasted into route's real spec-request step",
     _mut_alias_in_route_step),
    ("an unparseable board-loop.yml (a finding, not a silent pass)", _mut_unparseable),
)


def selftest_check9():
    failures = 0
    base = _board_loop_text()
    for name, mutate in CHECK9_TEXT_MUTATIONS:
        case = "{0} -> check 9 fails".format(name)
        if not check_no_pasted_stop_cause_case(text=mutate(base), verbose=False):
            print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
            failures += 1
        else:
            print("note: mutation caught ({0}).".format(case))
    for name, env, run in CHECK9_MUTATIONS:
        case = "{0} re-pasted into board-loop.yml -> check 9 fails".format(name)
        mutated = base.rstrip("\n") + "\n" + _CHECK9_JOB.format(env=env, run=run)
        yaml.safe_load(mutated)  # a mutation that no longer parses tests nothing
        if not check_no_pasted_stop_cause_case(text=mutated, verbose=False):
            print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
            failures += 1
        else:
            print("note: mutation caught ({0}).".format(case))
    for name, env, run, step_if in CHECK9_ALLOWED:
        case = "{0} -> check 9 leaves it alone".format(name)
        job = _CHECK9_JOB.format(env=env, run=run)
        if step_if:
            marker = "      - name: re-pasted mapping\n"
            if job.count(marker) != 1:
                raise AssertionError("_CHECK9_JOB's step header moved")
            job = job.replace(marker, marker + step_if, 1)
        mutated = base.rstrip("\n") + "\n" + job
        yaml.safe_load(mutated)
        if check_no_pasted_stop_cause_case(text=mutated, verbose=False):
            print("::error::verify-stop-point-recording self-test: {0}: wrongly "
                  "flagged.".format(case))
            failures += 1
        else:
            print("note: negative control held ({0}).".format(case))
    return failures


# maintainer review: a check deleted from CHECKS previously left both the
# gate's own `run()` and `--self-test` at 0 failures -- nothing compared
# CHECKS against what the self-tests actually exercise. This table is the
# one place that comparison is declared; selftest_registry_coverage() below
# asserts it stays in sync with both CHECKS and SELFTESTS.
CHECK_SELFTEST_COVERAGE = {
    check_record_write_present: (selftest_check1,),
    check_provenance: (selftest_check2,),
    check_cause_aware_messaging: (selftest_check3,),
    check_decision_function_agreement: (
        selftest_check4, selftest_check4_samerun_record, selftest_check4_samerun_record_both),
    check_selection_exclusion: (selftest_check5,),
    check_no_write_on_stand_down: (selftest_check6,),
    check_no_wc_pristine_dependency: (selftest_check7,),
    check_marker_inputs_wired: (selftest_check8,),
    check_no_pasted_stop_cause_case: (selftest_check9,),
}


# One literal path, not os.path.join pieces: verify-gate-wiring.py finds a
# gate's subject documents by their path text, and requires lint-workflows'
# pull_request paths: filter to name each one.
CONTRACT = os.path.join(
    REPO_ROOT, "specs/097-recorded-stop-point/contracts/gate-135-stop-point-recording.md")
CONTRACT_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|", re.M)


def contract_check_names():
    """{"check N"} for every row of the contract's "What it must fail on"
    table -- the list of checks declared outside this file, so removing a
    check takes an edit someone reviews there too."""
    with open(CONTRACT, encoding="utf-8") as fh:
        return {"check {0}".format(n) for n in CONTRACT_ROW_RE.findall(fh.read())}


def registry_problems(checks, coverage, selftests, contract_names):
    """-> [problem] for a CHECKS/CHECK_SELFTEST_COVERAGE/SELFTESTS triple
    that has drifted from itself or from the contract's own check list."""
    registered = {fn for _, fn in checks}
    covered = set(coverage)
    problems = []
    names = {name for name, _ in checks}
    if names != contract_names:
        problems.append("CHECKS names {0} but the contract's table names {1} -- a check "
                        "removed from CHECKS, its coverage and SELFTESTS together still "
                        "leaves the contract row".format(
                            sorted(names), sorted(contract_names)))
    missing_coverage = registered - covered
    stale_coverage = covered - registered
    if missing_coverage:
        problems.append("check(s) registered in CHECKS with no self-test coverage: {0}".format(
            ", ".join(sorted(fn.__name__ for fn in missing_coverage))))
    if stale_coverage:
        problems.append("self-test coverage references check(s) no longer in CHECKS: {0}".format(
            ", ".join(sorted(fn.__name__ for fn in stale_coverage))))
    referenced_selftests = {st for sts in coverage.values() for st in sts}
    unregistered_selftests = referenced_selftests - set(selftests)
    if unregistered_selftests:
        problems.append("coverage references self-test(s) not in SELFTESTS: {0}".format(
            ", ".join(sorted(fn.__name__ for fn in unregistered_selftests))))
    return problems


def selftest_registry_coverage():
    case = "CHECKS registry stays in sync with CHECK_SELFTEST_COVERAGE and SELFTESTS"
    contract_names = contract_check_names()
    problems = registry_problems(CHECKS, CHECK_SELFTEST_COVERAGE, SELFTESTS, contract_names)
    # The coordinated removal (code review of #899): check 9 dropped from
    # CHECKS, its coverage entry and SELFTESTS in one edit is still caught.
    dropped_check = CHECKS[-1][1]
    dropped_selftests = set(CHECK_SELFTEST_COVERAGE[dropped_check])
    if not registry_problems(
            CHECKS[:-1],
            {fn: sts for fn, sts in CHECK_SELFTEST_COVERAGE.items() if fn is not dropped_check},
            tuple(st for st in SELFTESTS if st not in dropped_selftests),
            contract_names):
        problems.append("a coordinated removal of {0} from CHECKS, its coverage and "
                        "SELFTESTS is NOT caught".format(CHECKS[-1][0]))
    if problems:
        print("::error::verify-stop-point-recording self-test: {0}: {1}.".format(
            case, "; ".join(problems)))
        return 1
    print("note: registry coverage verified ({0}).".format(case))
    return 0


SELFTESTS = (
    selftest_check1, selftest_check2, selftest_check3,
    selftest_check4, selftest_check4_samerun_record, selftest_check4_samerun_record_both,
    selftest_check5, selftest_check6, selftest_check7, selftest_check8, selftest_check9,
    selftest_registry_coverage,
)


def self_test():
    failures = 0
    for fn in SELFTESTS:
        failures += fn()
    return failures


def main():
    if "--self-test" in sys.argv:
        failures = self_test()
    else:
        failures = run()
    print("verify-stop-point-recording: {0} failure(s).".format(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
