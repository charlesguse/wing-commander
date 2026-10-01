#!/usr/bin/env python3
"""Gate 134 -- the re-admission rule FR-006 states is the one board-loop.yml's
resume step actually runs (specs/100-stalled-item-re-admission,
contracts/resume-recovery-readmission.md, folded into specs/061's
contracts/resume-recovery.md clause 2).

WHY THIS EXISTS
---------------
Every stall site (#604) posts a `stalled` marker with no
`pr`, so a maintainer who removes `board:stalled` always sends the item
through resume clause 2's `board:owned` fallback. Before this feature that
clause resolved unconditionally to `review` (except the `#530` breach
carve-out), so a label-removed item whose PR had already been reviewed to a
spent budget on an unmoved head was re-reviewed from scratch for no reason.
FR-006/FR-006b's `head_moved_since_last_review()` (board_item_marker.py)
decides `review` vs `readiness` instead; this gate pins both halves: the
function's own decision branches, and that clause 2 actually calls it
rather than quietly reverting to the old unconditional form.

Maintainer review of #885 (PR for this feature) found that the original
shape treated a budget-spent review verdict the same as a converged one,
so a budget-spent stall could resolve to `readiness` once its head stopped
moving -- reporting READY with in-scope findings still open (FR-006b/
SC-004). Only a *converged* verdict comment now establishes a reviewed
head; a budget-spent (or any inconclusive) verdict always resolves to
`review` with a fresh round budget. The comparison itself also moved from
a commit-timestamp heuristic to a direct head-SHA comparison against the
SHA the converged comment recorded, which a rebase or a push authored
before, but landed after, the verdict could fool.

WHAT IT CHECKS (direct, fixture-driven)
----------------------------------------
head_moved_since_last_review() is imported and called directly against each
fixture case under .github/scripts/tests/board-loop-readmission/<case>/ (a
comments.json array, a pr-view.json stub for the injected `run`, and an
expected.json): a converged verdict comment whose recorded head SHA differs
from the live head resolves True; one whose recorded head SHA matches the
live head resolves False; no resolved verdict at all (including when only
the inconclusive parse-failed/malformed-findings wording matches, or only
the budget-spent wording matches) resolves True without ever calling `run`
(the live lookup is skipped, not merely tolerated); and a failing live PR
lookup (reached only once a converged verdict was actually found) resolves
True.

WHAT IT CHECKS (static)
------------------------
The resume step's `step_resolution_json` heredoc is extracted out of
board-loop.yml and its clause 2 (`elif pr_from_fallback:`) text must still
call `head_moved_since_last_review(` -- reverting clause 2 to the old
unconditional `step = BREACH_STEP if marker_step == BREACH_STEP else
"review"` form drops that call and fails this check by name. Clause 2a's
unconditional breach carve-out (`if marker_step == BREACH_STEP:`) must
still be present and un-conditioned on head movement (#530).

WHAT IT CHECKS (executed, heredoc-driven)
-------------------------------------------
The same heredoc is run for real (as Gate 97's own resume_findings() runs
it) against fixture cases under board-loop-readmission/<case>/resume-env.json
+ expected.json: a `breach` marker recovered via the fallback resolves
`breach` regardless of a head-moved or head-unmoved sub-case (clause 2a is
never reached by clause 2b's split); no PR recovered by either the marker
or the fallback never reaches clause 2 at all, falling to clause 4's
`triage`; a `stalled` marker (round 0, every stall site's marker call
omits --round) recovered via the fallback with no resolved verdict resolves
`review` with `round` still `"0"` -- the same starting value a freshly
selected item gets (FR-009/SC-006); and one case drives the heredoc's own
live `gh pr view` call (via a throwaway stub `gh` prepended to PATH) to
actually resolve `readiness`, so this gate cannot pass vacuously by never
exercising that branch at all. This resume step never re-simulates the
unrelated, unchanged round-budget decision review's own job makes each
round; round == 0 at resume is the one new fact this feature's clause 2b
could disturb, and the gate confirms it does not.

WHAT IT CHECKS (FR-009/SC-006 -- a re-stall after a fresh budget)
----------------------------------------------------------------------
The review job's own "Decide the round outcome" step (unmodified by this
feature) is run for real against a round==ROUND_BUDGET, findings-still-open
environment: the fresh budget a re-admitted item started at round 0
eventually spends out exactly like a freshly selected item's would,
stalling again on the same terms (outcome=stalled, stall-reason=
budget-spent).

WHAT IT CHECKS (FR-010 -- no extra agent invocation, FR-011 -- run summary)
----------------------------------------------------------------------------
Stall sites are derived from the workflow itself (`--add-label
"board:stalled"`, the one phrase every stall-marker render carries, per
board_item_marker.add_stalled_label()'s own refusal to run without it) --
never a hand-kept list a new stall site could silently escape. None of
those steps carries `continue-on-error: true` (FR-010): every one already
fails loudly on a failed `add_stalled_label()` call (#604, Gate 97);
without this, that failure would not fail the job, and a later step in the
same job -- including an agent step -- could still run this same run. Each
stall-marker render is matched by at least one
`--record-stall-summary` call in the same step's text (FR-011,
board_item_marker.record_stall_summary() -- CLAUDE.md single-home rule):
review's one step carries three of each (one per stall arm), so a mutation
dropping any single arm's call is caught by name, not masked by the other
two arms' calls satisfying a step-wide "any at all" check.

Fails loudly, not vacuously, when any fixture file under the direct,
heredoc, or round-outcome cases is missing, matching
verify-board-eligibility.py's own rule.

--self-test mutates the shipped workflow text (drops the call to
head_moved_since_last_review() from clause 2) and asserts the static check
detects it.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "board-loop.yml")
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "board-loop-readmission")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import head_moved_since_last_review  # noqa: E402
import wc_shell_harness  # noqa: E402


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _find_step(doc, job, predicate):
    for s in ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []:
        if isinstance(s, dict) and predicate(s):
            return s
    return None


def _step_run(doc, job, predicate):
    step = _find_step(doc, job, predicate)
    return str((step or {}).get("run", ""))


def _resume_heredoc(doc):
    run = _step_run(doc, "select", lambda s: s.get("id") == "resume")
    m = re.search(r"step_resolution_json=.*?<<'PYEOF'\n(.*?)\nPYEOF", run, re.S)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Direct, fixture-driven tests of head_moved_since_last_review() itself.
# ---------------------------------------------------------------------------

DIRECT_CASES = (
    "head-moved-resolves-review",
    "head-unmoved-resolves-readiness",
    "no-reviewed-head-defaults-review",
    "pr-lookup-fails-defaults-review",
    "budget-spent-unmoved-resolves-review",
    "converged-then-budget-spent-resolves-review",
)


def _fake_run(pr_view, calls):
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, pr_view["returncode"],
                                           stdout=pr_view.get("stdout", ""), stderr="")
    return run


def direct_call_findings():
    findings = []
    for case in DIRECT_CASES:
        case_dir = os.path.join(FIXTURES_DIR, case)
        missing = [name for name in ("comments.json", "pr-view.json", "expected.json")
                   if not os.path.exists(os.path.join(case_dir, name))]
        if missing:
            findings.append("{0}: missing fixture file(s) {1}".format(case, missing))
            continue
        comments = _load_json(os.path.join(case_dir, "comments.json"))
        pr_view = _load_json(os.path.join(case_dir, "pr-view.json"))
        expected = _load_json(os.path.join(case_dir, "expected.json"))
        calls = []
        got = head_moved_since_last_review(
            expected["pr_number"], comments, expected["bot_login"], run=_fake_run(pr_view, calls))
        if got != expected["moved"]:
            findings.append("{0}: head_moved_since_last_review() returned {1!r}, expected {2!r}".format(
                case, got, expected["moved"]))
        if "expect_run_called" in expected:
            called = bool(calls)
            if called != expected["expect_run_called"]:
                findings.append(
                    "{0}: gh pr view called={1}, expected {2} -- the live lookup must be skipped "
                    "when no converged review verdict names this PR".format(
                        case, called, expected["expect_run_called"]))
    return findings


# ---------------------------------------------------------------------------
# Static: clause 2 of the resume step's step_resolution_json heredoc still
# calls head_moved_since_last_review(), and the breach carve-out (clause 2a)
# is unconditional.
# ---------------------------------------------------------------------------

def clause2_structural_findings(doc):
    code = _resume_heredoc(doc)
    if code is None:
        return ["resume: no `step_resolution_json` heredoc found in select's resume step"]
    m = re.search(r"elif pr_from_fallback:\n(.*?)\nelif branch:", code, re.S)
    if not m:
        return ["resume: clause 2 (`elif pr_from_fallback:`) not found, or its boundary with "
                 "clause 3 (`elif branch:`) moved"]
    clause2_body = m.group(1)
    findings = []
    if "if marker_step == BREACH_STEP:" not in clause2_body:
        findings.append(
            "resume: clause 2 no longer carries the unconditional breach carve-out "
            "(`if marker_step == BREACH_STEP:`) -- a breach marker could be reviewed (#530)")
    if "head_moved_since_last_review(" not in clause2_body:
        findings.append(
            "resume: clause 2 does not call head_moved_since_last_review() -- it may have "
            "reverted to resolving unconditionally to \"review\" again (FR-006)")
    return findings


# ---------------------------------------------------------------------------
# Executed: the real heredoc, run against fixture environments (as Gate 97's
# own resume_findings() runs the same heredoc).
# ---------------------------------------------------------------------------

HEREDOC_CASES = (
    "breach-marker-ignores-head-movement/head-moved",
    "breach-marker-ignores-head-movement/head-unmoved",
    "no-open-pr-falls-to-triage",
    "fresh-budget-after-readmission",
    "head-unmoved-resolves-readiness-live",
)


def _stub_gh_dir(head_ref_oid):
    """A throwaway bin dir whose `gh` answers `gh pr view ... --json
    headRefOid` with a fixed SHA, so a heredoc case can drive
    head_moved_since_last_review()'s own live lookup branch (T030: this
    gate must not pass vacuously by never exercising that branch at all).
    Left for the OS to reclaim, matching this repository's other
    throwaway-stub-dir harnesses (wc_shell_harness._shim_jq_cr)."""
    d = tempfile.mkdtemp(prefix="wc-gh-stub-")
    path = os.path.join(d, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/bin/sh\n")
        fh.write('printf \'{{"headRefOid": "{0}"}}\'\n'.format(head_ref_oid))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return d


def _exec_heredoc(code, env, scripts_root, path_prepend=None):
    full_env = dict(os.environ)
    full_env.update(env)
    if path_prepend:
        full_env["PATH"] = path_prepend + os.pathsep + full_env.get("PATH", "")
    proc = subprocess.run([sys.executable, "-"], input=code, text=True,
                          capture_output=True, env=full_env, cwd=scripts_root)
    return proc.returncode, proc.stdout, proc.stderr


def heredoc_findings(doc, scripts_root=ROOT):
    code = _resume_heredoc(doc)
    if code is None:
        return ["resume: no `step_resolution_json` heredoc found in select's resume step"]
    findings = []
    for case in HEREDOC_CASES:
        case_dir = os.path.join(FIXTURES_DIR, case)
        env_path = os.path.join(case_dir, "resume-env.json")
        expected_path = os.path.join(case_dir, "expected.json")
        missing = [p for p in (env_path, expected_path) if not os.path.exists(p)]
        if missing:
            findings.append("{0}: missing fixture file(s) {1}".format(case, missing))
            continue
        env = dict(_load_json(env_path))
        expected = _load_json(expected_path)
        stub_oid = env.pop("GH_STUB_HEAD_REF_OID", None)
        path_prepend = _stub_gh_dir(stub_oid) if stub_oid else None
        rc, out, err = _exec_heredoc(code, env, scripts_root, path_prepend)
        if rc != 0:
            findings.append("{0}: step resolution crashed: {1}".format(
                case, (err.strip().splitlines() or [err])[-1]))
            continue
        try:
            got = json.loads(out)
        except ValueError:
            findings.append("{0}: output is not JSON: {1!r}".format(case, out))
            continue
        diff = {k: got.get(k) for k, v in expected.items() if got.get(k) != v}
        if diff:
            findings.append("{0}: expected {1}, got (diff) {2}".format(case, expected, diff))
    return findings


# ---------------------------------------------------------------------------
# Executed: review's own, unmodified "Decide the round outcome" step, driven
# at round==budget with findings still open -- a re-admitted item's fresh
# round-0 restart (T020) eventually re-stalls on the same terms (FR-009/
# SC-006).
# ---------------------------------------------------------------------------

def round_outcome_restall_findings():
    case_dir = os.path.join(FIXTURES_DIR, "fresh-budget-after-readmission",
                            "re-stall-after-fresh-budget-spent")
    env_path = os.path.join(case_dir, "round-outcome-env.json")
    expected_path = os.path.join(case_dir, "expected.json")
    missing = [p for p in (env_path, expected_path) if not os.path.exists(p)]
    if missing:
        return ["re-stall-after-fresh-budget-spent: missing fixture file(s) {0}".format(missing)]
    env = _load_json(env_path)
    expected = _load_json(expected_path)
    step = wc_shell_harness.find_step(WORKFLOW, "Decide the round outcome")
    bash = wc_shell_harness.resolve_bash()
    workdir = tempfile.mkdtemp(prefix="wc-round-outcome-")
    try:
        rc, output, outputs, summary = wc_shell_harness.run_step(bash, step["run"], workdir, env, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    findings = []
    for key, value in expected.items():
        if outputs.get(key) != value:
            findings.append(
                "re-stall-after-fresh-budget-spent: expected {0}={1!r}, got {2!r} (rc={3}, output={4!r})".format(
                    key, value, outputs.get(key), rc, output))
    return findings


# ---------------------------------------------------------------------------
# FR-010 (no extra agent invocation) and FR-011 (run summary records): both
# read every stall site, derived from the workflow itself rather than a
# hand-kept list (T030) -- every stall-marker render carries
# `--add-label "board:stalled"` (add_stalled_label()'s own refusal to run
# without it), including triage's, whose `--step` value is a shell variable
# rather than the literal word "stalled".
# ---------------------------------------------------------------------------

STALL_MARKER_PHRASE = '--add-label "board:stalled"'


def _stall_sites(doc):
    sites = []
    for job_key, job in (doc.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            if isinstance(step, dict) and STALL_MARKER_PHRASE in str(step.get("run", "")):
                sites.append((job_key, step))
    return sites


def no_extra_invocation_findings(doc):
    findings = []
    for job_key, step in _stall_sites(doc):
        if step.get("continue-on-error"):
            findings.append(
                "{0}/{1}: stall-site step carries continue-on-error: true -- a failed "
                "add_stalled_label() would not fail the job, so a later step in the same job "
                "(including an agent step) could still run this same run (FR-010)".format(
                    job_key, step.get("name") or step.get("id")))
    return findings


def run_summary_findings(doc):
    findings = []
    for job_key, step in _stall_sites(doc):
        run_text = str(step.get("run", ""))
        stall_count = run_text.count(STALL_MARKER_PHRASE)
        summary_count = run_text.count("--record-stall-summary")
        if summary_count < stall_count:
            findings.append(
                "{0}/{1}: {2} stalled-marker render(s) but only {3} --record-stall-summary call(s) "
                "-- a stall here can be invisible without log archaeology (FR-011)".format(
                    job_key, step.get("name") or step.get("id"), stall_count, summary_count))
    return findings


def all_findings(doc, scripts_root=ROOT):
    return (clause2_structural_findings(doc) + direct_call_findings()
            + heredoc_findings(doc, scripts_root) + round_outcome_restall_findings()
            + no_extra_invocation_findings(doc) + run_summary_findings(doc))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_HEAD_MOVED_CALL = 'moved = head_moved_since_last_review(pr_number, comments, os.environ.get("BOT_LOGIN") or "")'


def run_selftest(text):
    failures = []
    base_doc = yaml.safe_load(text)
    base = all_findings(base_doc)
    if base:
        failures.append("unmutated board-loop.yml is not clean: {0}".format(base))
    if _HEAD_MOVED_CALL not in text:
        failures.append("self-test: fixture text not found for `clause 2 reverted to unconditional "
                        "review`: {0!r}".format(_HEAD_MOVED_CALL))
    else:
        mutated_text = text.replace(
            _HEAD_MOVED_CALL, 'moved = True  # mutated: no longer calls head_moved_since_last_review')
        mutated_doc = yaml.safe_load(mutated_text)
        found = clause2_structural_findings(mutated_doc)
        if not found:
            failures.append("mutation `clause 2 reverted to unconditional review` was NOT detected")
        else:
            print("  detected: clause 2 reverted to unconditional review -> {0}".format(found[0]))

    # T030: dropping one of review's three --record-stall-summary calls
    # must be caught by name, not masked by the other two arms' calls
    # satisfying a step-wide "any at all" check.
    review_call = 'python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py" --record-stall-summary --issue "$ISSUE_NUMBER" --from-step "review ($STALL_REASON)"'
    if review_call not in text:
        failures.append("self-test: fixture text not found for `review drops one stall arm's "
                        "--record-stall-summary call`: {0!r}".format(review_call))
    else:
        mutated_text = text.replace(review_call, "", 1)
        mutated_doc = yaml.safe_load(mutated_text)
        found = run_summary_findings(mutated_doc)
        if not found:
            failures.append("mutation `review drops one stall arm's --record-stall-summary call` was NOT detected")
        else:
            print("  detected: review drops one stall arm's summary call -> {0}".format(found[0]))

    for f in failures:
        print("FAIL: " + f)
    print("verify-board-loop-readmission --self-test: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--workflow", default=WORKFLOW)
    args = parser.parse_args()
    with open(args.workflow, encoding="utf-8") as fh:
        text = fh.read()
    if args.self_test:
        return run_selftest(text)
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print("FAIL: board-loop.yml does not parse: {0}".format(exc))
        return 1
    findings = all_findings(doc)
    for f in findings:
        print("FAIL: " + f)
    print("verify-board-loop-readmission: {0} finding(s).".format(len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
