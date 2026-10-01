#!/usr/bin/env python3
"""Watchdog dedup survives partial signal overlap and gate-suite fan-out
(spec 109) -- the overlap-matching rule, the FR-009 converging-cycle
filing suppression, and the pre-existing #266 `{stage, tool}` denial
separation all keep holding once a finding's citation set can move.

WHY THIS EXISTS
---------------
Before this feature, `triage`'s `Dedup search` step matched an open issue
only on an EXACT, byte-identical citation set (the fingerprint marker).
Runs #729/#732/#765 showed three occurrences of one recurring defect whose
cited signal ids moved slightly each time, so each filed its own issue
instead of accumulating on one. Separately, run 36484099706 showed a
converging implement cycle's own red gate suite fanning out into six
`pipeline-defect` issues that the very next cycle was already going to
fix. Both defects are silent: nothing failed, the workflow just filed
more issues than the underlying problem warranted.

This harness EXECUTES the real shipped `triage` steps -- `Compute
fingerprint`, `Gate-suite filing condition`, and `Dedup search` -- against
stubbed `gh issue list`/artifact input (the same `wc_shell_harness`
convention `verify-act-dedup-guard.py` and Gate 19 use), plus, for the
`{stage, tool}` separation proof, the real `collect` job's `Collect:
execution-output artifacts` and `Stamp signal ids` steps chained
end-to-end so the signal ids it asserts on are the ones the shipped code
actually produces, not a hand-typed stand-in for them.

Four mutations (reverting overlap matching to exact-set equality,
disabling the 100-comment truncation guard, reverting the FR-009
condition to "always file", and reverting the `tool-denial` id
projection to a shared, coarser key) each must break at least one
assertion above, proving these are checks that can fail (Constitution
VIII) -- exercised under `--self-test`, mirroring Gate 120's two-step
shape (the plain invocation checks the real shipped files; the
self-test invocation checks the gate itself can fail).

Usage: python3 .github/scripts/verify-watchdog-overlap-fanout.py [--self-test]
Requires: bash, jq.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate  # noqa: E402
from wc_shell_harness import (ensure_jq, find_step, resolve_bash,  # noqa: E402
                              run_step, use_utf8_stdout)

WATCHDOG = ".github/workflows/watchdog.yml"
FINGERPRINT_STEP = "Compute fingerprint"
GATE_SUITE_STEP = "Gate-suite filing condition"
DEDUP_STEP = "Dedup search"
EXEC_STEP = "Collect: execution-output artifacts"
STAMP_STEP = "Stamp signal ids"

GITHUB_REPOSITORY = "charlesguse/wing-commander"
BASH = None


# --------------------------------------------------------------------------
# The subject: the real steps, lifted from the shipped workflow
# --------------------------------------------------------------------------
def load_step_scripts():
    scripts = {}
    for name in (FINGERPRINT_STEP, GATE_SUITE_STEP, DEDUP_STEP, EXEC_STEP, STAMP_STEP):
        scripts[name] = str(find_step(WATCHDOG, name).get("run") or "")
        if not scripts[name].strip():
            sys.exit(f"::error file={WATCHDOG}::{name!r} carries no run: text "
                     f"-- nothing to execute. If it was renamed, update this "
                     f"gate alongside the workflow.")
    dedup_if = str(find_step(WATCHDOG, DEDUP_STEP).get("if") or "")
    if not dedup_if.strip():
        sys.exit(f"::error file={WATCHDOG}::{DEDUP_STEP!r} carries no if: "
                 f"condition -- this gate's FR-009 check (dedup must never "
                 f"run on a converging-gate-suite finding) rests on it.")
    return scripts, dedup_if


# A single-purpose `gh` stub: `issue list` returns a caller-supplied fixture
# (or fails with a caller-supplied message); `run download` writes a
# caller-supplied artifact payload into whatever -D dir it was given (the
# same shape STUB_GH_SPECSLUG_TEMPLATE in verify-gate-19.py uses for the
# same purpose, kept local here rather than imported so this gate has no
# cross-gate coupling).
GH_STUB = r'''#!/usr/bin/env bash
if [ "$1 $2" = "issue list" ]; then
  if [ -n "${WC_GH_FAIL_MSG:-}" ]; then
    printf '%s\n' "$WC_GH_FAIL_MSG" >&2
    exit 1
  fi
  cat "$WC_GH_RESULTS_FILE"
  exit 0
fi
if [ "$1 $2" = "run download" ]; then
  dest=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-D" ]; then dest="$arg"; fi
    prev="$arg"
  done
  [ -n "$dest" ] || exit 1
  mkdir -p "$dest/artifact"
  printf '%s' "${WC_GH_ARTIFACT:-[]}" > "$dest/artifact/claude-execution-output.json"
  exit 0
fi
exit 0
'''


def make_gh_stub(tmproot):
    bindir = tempfile.mkdtemp(dir=tmproot)
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(path, 0o755)
    return bindir


def marker(ids):
    return "<!-- wing-commander-watchdog: signal-ids=" + ",".join(ids) + " -->"


def fp_marker(fp):
    return "<!-- wing-commander-watchdog: fingerprint=" + fp + " -->"


def run_fingerprint(scripts, class_, ids, tmproot, signals=None):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    signals = signals if signals is not None else [{"id": i} for i in ids]
    env = {"FINDING_CLASS": class_,
           "EVIDENCE": json.dumps([{"signalId": i} for i in ids]),
           "SIGNALS": json.dumps(signals)}
    rc, out, outputs, _ = run_step(BASH, scripts[FINGERPRINT_STEP], workdir, env, runner_temp)
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    return rc, out, outputs


def run_gate_suite_condition(scripts, cited_ids, signals, converged, handoff,
                              meta_stage, stalled_label, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    env = {"CITED_IDS": ",".join(cited_ids), "SIGNALS": json.dumps(signals),
           "CYCLE_CONVERGED": converged, "CYCLE_HANDOFF": handoff,
           "META_STAGE": meta_stage, "STALLED_LABEL": stalled_label}
    rc, out, outputs, _ = run_step(BASH, scripts[GATE_SUITE_STEP], workdir, env, runner_temp)
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    return rc, out, outputs


def run_dedup(scripts, fp, class_, cited_ids, results, tmproot, fail_msg=None):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = make_gh_stub(tmproot)
    results_file = os.path.join(workdir, "results.json")
    with open(results_file, "w", encoding="utf-8") as fh:
        json.dump(results, fh)
    env = {"GH_TOKEN": "dummy-token", "GITHUB_REPOSITORY": GITHUB_REPOSITORY,
           "FP": fp, "FINDING_CLASS": class_, "CITED_IDS": ",".join(cited_ids),
           "WC_GH_RESULTS_FILE": results_file.replace("\\", "/"),
           "PATH": bindir + os.pathsep + os.environ["PATH"]}
    if fail_msg:
        env["WC_GH_FAIL_MSG"] = fail_msg
    rc, out, outputs, _ = run_step(BASH, scripts[DEDUP_STEP], workdir, env, runner_temp)
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    shutil.rmtree(bindir, ignore_errors=True)
    return rc, out, outputs


def denial_artifact(tool, command):
    return json.dumps([{"type": "result", "num_turns": 1, "is_error": False,
                        "permission_denials": [{"tool_name": tool, "tool_use_id": "d0",
                                                "tool_input": {"command": command}}]}])


def run_collector_and_stamp(scripts, stage, tool, command, tmproot):
    """Collect: execution-output artifacts -> Stamp signal ids, chained
    through a real signals.json, exactly as `collect` runs them. Returns
    (id, error) -- the real stamped signal id for this {stage, tool} pair,
    or a diagnostic string."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = make_gh_stub(tmproot)
    try:
        for name in ("signals.json", "collector-outcomes.json"):
            with open(os.path.join(runner_temp, name), "w", encoding="utf-8") as fh:
                fh.write("[]")
        env = {"GH_TOKEN": "dummy-token", "ACTIONS_TOKEN": "dummy-token",
               "GITHUB_REPOSITORY": GITHUB_REPOSITORY, "RUN_ID": "1", "RUN_CONCLUSION": "success", "INSPECTED_STAGE": stage,
               "WC_GH_ARTIFACT": denial_artifact(tool, command),
               "PATH": bindir + os.pathsep + os.environ["PATH"]}
        rc, out, _, _ = run_step(BASH, scripts[EXEC_STEP], workdir, env, runner_temp)
        if rc != 0:
            return None, f"Collect: execution-output artifacts exited {rc}: {out.strip()}"
        rc, out, _, _ = run_step(BASH, scripts[STAMP_STEP], workdir, {}, runner_temp)
        if rc != 0:
            return None, f"Stamp signal ids exited {rc}: {out.strip()}"
        with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
            signals = json.load(fh)
        if not signals:
            return None, "the collector produced no denial signal"
        return signals[0]["id"], None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(runner_temp, ignore_errors=True)
        shutil.rmtree(bindir, ignore_errors=True)


# --------------------------------------------------------------------------
# Scenario A (quickstart): partial overlap attaches to the same issue
# across three citation sets, the third citing an id recorded only in a
# COMMENT, never the original body.
# --------------------------------------------------------------------------
def scenario_a(scripts, tmproot):
    failures = []
    rc, out, fp1 = run_fingerprint(scripts, "denied-tool", ["A", "B"], tmproot)
    if rc != 0 or not fp1.get("fingerprint"):
        return [f"[Scenario A] Compute fingerprint (occurrence 1) exited {rc}: {out.strip()}"]
    if fp1.get("cited-ids") != "A,B":
        failures.append(f"[Scenario A] occurrence 1 cited-ids = {fp1.get('cited-ids')!r}, expected 'A,B'")
    rc, out, d1 = run_dedup(scripts, fp1["fingerprint"], "denied-tool", ["A", "B"], [], tmproot)
    if rc != 0:
        return failures + [f"[Scenario A] Dedup search (occurrence 1) exited {rc}: {out.strip()}"]
    if d1.get("outcome") != "none":
        failures.append(f"[Scenario A] occurrence 1 outcome = {d1.get('outcome')!r}, expected 'none'")

    issue_body = fp_marker(fp1["fingerprint"]) + " " + marker(["A", "B"])
    rc, out, fp2 = run_fingerprint(scripts, "denied-tool", ["A", "C", "D"], tmproot)
    if rc != 0:
        return failures + [f"[Scenario A] Compute fingerprint (occurrence 2) exited {rc}: {out.strip()}"]
    results = [{"number": 1, "state": "OPEN", "body": issue_body, "comments": []}]
    rc, out, d2 = run_dedup(scripts, fp2["fingerprint"], "denied-tool", ["A", "C", "D"], results, tmproot)
    if rc != 0:
        return failures + [f"[Scenario A] Dedup search (occurrence 2) exited {rc}: {out.strip()}"]
    if d2.get("outcome") != "overlap":
        failures.append(f"[Scenario A] occurrence 2 outcome = {d2.get('outcome')!r}, expected 'overlap'")
    if d2.get("issue-number") != "1":
        failures.append(f"[Scenario A] occurrence 2 issue-number = {d2.get('issue-number')!r}, expected '1'")
    if d2.get("matched-on") != "A":
        failures.append(f"[Scenario A] occurrence 2 matched-on = {d2.get('matched-on')!r}, expected 'A'")

    comment2_body = marker(["A", "C", "D"])
    results = [{"number": 1, "state": "OPEN", "body": issue_body,
                "comments": [{"body": comment2_body}]}]
    rc, out, fp3 = run_fingerprint(scripts, "denied-tool", ["D"], tmproot)
    if rc != 0:
        return failures + [f"[Scenario A] Compute fingerprint (occurrence 3) exited {rc}: {out.strip()}"]
    rc, out, d3 = run_dedup(scripts, fp3["fingerprint"], "denied-tool", ["D"], results, tmproot)
    if rc != 0:
        return failures + [f"[Scenario A] Dedup search (occurrence 3) exited {rc}: {out.strip()}"]
    if d3.get("outcome") != "overlap":
        failures.append(f"[Scenario A] occurrence 3 (citing only D, recorded only in a "
                         f"comment) outcome = {d3.get('outcome')!r}, expected 'overlap' -- "
                         f"the matchable-set union must read comments, not only the body")
    if d3.get("issue-number") != "1":
        failures.append(f"[Scenario A] occurrence 3 issue-number = {d3.get('issue-number')!r}, expected '1'")
    return failures


# --------------------------------------------------------------------------
# Scenario B: a disjoint citation set files new.
# --------------------------------------------------------------------------
def scenario_b(scripts, tmproot):
    body = fp_marker("deadbeef00") + " " + marker(["A", "B"])
    results = [{"number": 1, "state": "OPEN", "body": body,
                "comments": [{"body": marker(["A", "C", "D"])}]}]
    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["E", "F"], tmproot)
    if rc != 0:
        return [f"[Scenario B] Compute fingerprint exited {rc}: {out.strip()}"]
    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["E", "F"], results, tmproot)
    if rc != 0:
        return [f"[Scenario B] Dedup search exited {rc}: {out.strip()}"]
    if d.get("outcome") != "none":
        return [f"[Scenario B] outcome = {d.get('outcome')!r}, expected 'none' "
                f"(a disjoint citation set must not attach)"]
    return []


# --------------------------------------------------------------------------
# Scenario F: chained multi-match attaches to the lowest-numbered issue,
# names the other, never data-integrity.
# --------------------------------------------------------------------------
def scenario_f(scripts, tmproot):
    body_x = fp_marker("fpx0000000") + " " + marker(["A", "B"])
    body_y = fp_marker("fpy0000000") + " " + marker(["B", "C"])
    results = [{"number": 9, "state": "OPEN", "body": body_y, "comments": []},
               {"number": 5, "state": "OPEN", "body": body_x, "comments": []}]
    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["A", "C"], tmproot)
    if rc != 0:
        return [f"[Scenario F] Compute fingerprint exited {rc}: {out.strip()}"]
    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["A", "C"], results, tmproot)
    if rc != 0:
        return [f"[Scenario F] Dedup search exited {rc}: {out.strip()}"]
    failures = []
    if d.get("outcome") != "overlap":
        failures.append(f"[Scenario F] outcome = {d.get('outcome')!r}, expected 'overlap' "
                         f"(a routine multi-match, never data-integrity)")
    if d.get("issue-number") != "5":
        failures.append(f"[Scenario F] issue-number = {d.get('issue-number')!r}, expected "
                         f"'5' (the lowest-numbered match)")
    if d.get("matched-on") != "A":
        failures.append(f"[Scenario F] matched-on = {d.get('matched-on')!r}, expected 'A'")
    if d.get("other-matches") != "9":
        failures.append(f"[Scenario F] other-matches = {d.get('other-matches')!r}, expected "
                         f"'9' (named, never written to)")
    return failures


# --------------------------------------------------------------------------
# Scenario G: overlap with a CLOSED issue never reopens it; an exact
# fingerprint match against a closed issue still does (unchanged).
# --------------------------------------------------------------------------
def scenario_g(scripts, tmproot):
    failures = []
    body = fp_marker("fpclosed00") + " " + marker(["A", "B"])
    results = [{"number": 3, "state": "CLOSED", "body": body, "comments": []}]
    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["A", "C"], tmproot)
    if rc != 0:
        return [f"[Scenario G] Compute fingerprint exited {rc}: {out.strip()}"]
    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["A", "C"], results, tmproot)
    if rc != 0:
        return [f"[Scenario G] Dedup search exited {rc}: {out.strip()}"]
    if d.get("outcome") != "none":
        failures.append(f"[Scenario G] partial overlap against a CLOSED issue: outcome = "
                         f"{d.get('outcome')!r}, expected 'none' (never reopened by overlap alone)")

    rc, out, fp2 = run_fingerprint(scripts, "denied-tool", ["A", "B"], tmproot)
    if rc != 0:
        return failures + [f"[Scenario G] Compute fingerprint (exact) exited {rc}: {out.strip()}"]
    results2 = [{"number": 3, "state": "CLOSED",
                 "body": fp_marker(fp2["fingerprint"]) + " " + marker(["A", "B"]),
                 "comments": []}]
    rc, out, d2 = run_dedup(scripts, fp2["fingerprint"], "denied-tool", ["A", "B"], results2, tmproot)
    if rc != 0:
        return failures + [f"[Scenario G] Dedup search (exact/closed) exited {rc}: {out.strip()}"]
    if d2.get("outcome") != "match-closed":
        failures.append(f"[Scenario G] exact fingerprint match on a closed issue: outcome = "
                         f"{d2.get('outcome')!r}, expected 'match-closed' (unchanged behavior)")
    return failures


# --------------------------------------------------------------------------
# Scenario H: a full 200-entry page reads as unknown, never none.
# --------------------------------------------------------------------------
def scenario_h(scripts, tmproot):
    results = [{"number": i, "state": "OPEN", "body": marker([f"z{i}"]), "comments": []}
               for i in range(1, 201)]
    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["nomatch"], tmproot)
    if rc != 0:
        return [f"[Scenario H] Compute fingerprint exited {rc}: {out.strip()}"]
    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["nomatch"], results, tmproot)
    if rc != 0:
        return [f"[Scenario H] Dedup search exited {rc}: {out.strip()}"]
    if d.get("outcome") != "unknown":
        return [f"[Scenario H] a full 200-entry page: outcome = {d.get('outcome')!r}, "
                f"expected 'unknown' (a truncated candidate set is never trustworthy "
                f"enough to call 'none')"]
    return []


# --------------------------------------------------------------------------
# FR-008: the 30-most-recently-added-distinct-id cap, oldest evicted first.
# --------------------------------------------------------------------------
def scenario_cap(scripts, tmproot):
    failures = []
    body_ids = [f"id{n:02d}" for n in range(1, 21)]
    comment_ids = [f"id{n:02d}" for n in range(21, 32)]
    body = fp_marker("fpcap00000") + " " + marker(body_ids)
    results = [{"number": 1, "state": "OPEN", "body": body,
                "comments": [{"body": marker(comment_ids)}]}]

    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["id01"], tmproot)
    if rc != 0:
        return [f"[30-cap] Compute fingerprint exited {rc}: {out.strip()}"]
    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["id01"], results, tmproot)
    if rc != 0:
        return [f"[30-cap] Dedup search (evicted id) exited {rc}: {out.strip()}"]
    if d.get("outcome") != "none":
        failures.append(f"[30-cap] citing only the 31st-oldest id (evicted by the 30-cap): "
                         f"outcome = {d.get('outcome')!r}, expected 'none'")

    rc, out, fp2 = run_fingerprint(scripts, "denied-tool", ["id31"], tmproot)
    if rc != 0:
        return failures + [f"[30-cap] Compute fingerprint (kept id) exited {rc}: {out.strip()}"]
    rc, out, d2 = run_dedup(scripts, fp2["fingerprint"], "denied-tool", ["id31"], results, tmproot)
    if rc != 0:
        return failures + [f"[30-cap] Dedup search (kept id) exited {rc}: {out.strip()}"]
    if d2.get("outcome") != "overlap":
        failures.append(f"[30-cap] citing the most-recently-added id (within the 30-cap): "
                         f"outcome = {d2.get('outcome')!r}, expected 'overlap'")
    return failures


# --------------------------------------------------------------------------
# Review Gate Round 3: `gh issue list --json comments` is a single,
# un-paginated GraphQL page -- a candidate with 100+ comments may be
# missing ids recorded only in later ones, so a "none"/"overlap" computed
# against it isn't trustworthy until proven otherwise.
# --------------------------------------------------------------------------
def scenario_comment_truncation(scripts, tmproot):
    failures = []
    # Every comment repeats the SAME id (not a distinct one each time) so
    # the unrelated 30-most-recent-distinct-id cap (FR-008) never evicts
    # `bodyid` on its own — only the comment-count guard under test can
    # explain a "none"/"unknown" result here.
    body = fp_marker("fptrunc000") + " " + marker(["bodyid"])
    truncated = [{"number": 1, "state": "OPEN", "body": body,
                  "comments": [{"body": marker(["samecomment"])} for _ in range(100)]}]
    not_truncated = [{"number": 1, "state": "OPEN", "body": body,
                       "comments": [{"body": marker(["samecomment"])} for _ in range(99)]}]

    rc, out, fp = run_fingerprint(scripts, "denied-tool", ["bodyid"], tmproot)
    if rc != 0:
        return [f"[comment-truncation] Compute fingerprint exited {rc}: {out.strip()}"]

    rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["bodyid"], truncated, tmproot)
    if rc != 0:
        return [f"[comment-truncation] Dedup search (100 comments) exited {rc}: {out.strip()}"]
    if d.get("outcome") != "unknown":
        failures.append(f"[comment-truncation] a candidate with 100 comments, even one that "
                         f"would otherwise overlap-match on its body marker: outcome = "
                         f"{d.get('outcome')!r}, expected 'unknown' (a candidate at the "
                         f"un-paginated nested-read ceiling is never trustworthy enough to "
                         f"call 'none' or 'overlap')")

    rc, out, d2 = run_dedup(scripts, fp["fingerprint"], "denied-tool", ["bodyid"], not_truncated, tmproot)
    if rc != 0:
        return failures + [f"[comment-truncation] Dedup search (99 comments) exited {rc}: {out.strip()}"]
    if d2.get("outcome") != "overlap":
        failures.append(f"[comment-truncation] a candidate with 99 comments (below the "
                         f"ceiling) citing a real body match: outcome = {d2.get('outcome')!r}, "
                         f"expected 'overlap' — the guard must not fire below its own threshold")
    return failures


# --------------------------------------------------------------------------
# User Story 3 / #266: the {stage, tool} denial separation survives overlap
# matching -- proven against REAL stamped ids, not hand-typed stand-ins.
# --------------------------------------------------------------------------
def scenario_stage_tool_separation(scripts, tmproot):
    failures = []
    pairs = [("plan", "Bash", "rm -rf /a"),
             ("plan", "Read", "cat /etc/passwd"),
             ("tasks", "Bash", "rm -rf /b")]
    ids = []
    for stage, tool, cmd in pairs:
        id_, err = run_collector_and_stamp(scripts, stage, tool, cmd, tmproot)
        if err:
            failures.append(f"[stage/tool separation] {stage}/{tool}: {err}")
        ids.append(id_)
    if any(i is None for i in ids):
        return failures
    if len(set(ids)) != 3:
        failures.append(f"[stage/tool separation] expected three distinct signal ids for "
                         f"three distinct {{stage, tool}} pairs, got {ids}")
        return failures

    for i, (stage, tool, _cmd) in enumerate(pairs):
        results = [{"number": j + 1, "state": "OPEN",
                    "body": fp_marker(f"other{j}00") + " " + marker([ids[j]]), "comments": []}
                   for j in range(3) if j != i]
        rc, out, fp = run_fingerprint(scripts, "denied-tool", [ids[i]], tmproot,
                                       signals=[{"id": x} for x in ids])
        if rc != 0:
            failures.append(f"[stage/tool separation] {stage}/{tool}: Compute fingerprint "
                             f"exited {rc}: {out.strip()}")
            continue
        rc, out, d = run_dedup(scripts, fp["fingerprint"], "denied-tool", [ids[i]], results, tmproot)
        if rc != 0:
            failures.append(f"[stage/tool separation] {stage}/{tool}: Dedup search exited "
                             f"{rc}: {out.strip()}")
            continue
        if d.get("outcome") != "none":
            failures.append(f"[stage/tool separation] {stage}/{tool}'s id matched another "
                             f"{{stage, tool}} pair's issue (outcome={d.get('outcome')!r}) -- "
                             f"the per-pair keying (#266) must keep these disjoint")
    return failures


# --------------------------------------------------------------------------
# FR-009/FR-010: the gate-suite filing condition, and Dedup search's own
# skip when it fires.
# --------------------------------------------------------------------------
GATE_SUITE_ID = "gsf1000000"
TOOL_DENIAL_ID = "td1000000"


def gs_signals():
    return [{"id": GATE_SUITE_ID, "signal-kind": "gate-suite-failure"},
            {"id": TOOL_DENIAL_ID, "signal-kind": "tool-denial"}]


def scenario_gate_suite_condition(scripts, dedup_if_expr, tmproot):
    failures = []
    signals = gs_signals()

    def check(label, cited, converged, handoff, meta_stage, stalled_label, expect_suppress):
        rc, out, o = run_gate_suite_condition(scripts, cited, signals, converged, handoff,
                                               meta_stage, stalled_label, tmproot)
        if rc != 0:
            failures.append(f"[Gate-suite condition] {label}: exited {rc}: {out.strip()}")
            return
        got_outcome = o.get("outcome", "")
        got_suppress = got_outcome == "converging-gate-suite"
        if got_suppress != expect_suppress:
            failures.append(
                f"[Gate-suite condition] {label}: outcome={got_outcome!r}, expected "
                f"{'converging-gate-suite' if expect_suppress else 'normal filing (empty outcome)'}")
        ctx = {"steps.suppress.outputs.suppressed": "false",
               "steps.evidence-gate.outputs.valid": "true",
               "steps.gate-suite-condition.outputs.outcome": got_outcome}
        dedup_would_run = bool(evaluate(dedup_if_expr, ctx))
        if dedup_would_run == expect_suppress:
            failures.append(
                f"[Gate-suite condition] {label}: Dedup search's own if: "
                f"{'still runs' if dedup_would_run else 'is skipped'} -- contract requires it "
                f"{'be skipped' if expect_suppress else 'still run'} here")

    check("(a) converging, not stalled", [GATE_SUITE_ID], "false", "false", "", "", True)
    check("(b) stalled via meta-stage", [GATE_SUITE_ID], "false", "false", "stalled", "", False)
    check("(b) stalled via label", [GATE_SUITE_ID], "false", "false", "", "true", False)
    check("(c) handoff reached", [GATE_SUITE_ID], "false", "true", "", "", False)
    check("(d) no cycle-outcome artifact (undeterminable)", [GATE_SUITE_ID], "", "", "", "", False)
    check("(e) mixed citation (not purely gate-suite)", [GATE_SUITE_ID, TOOL_DENIAL_ID],
          "false", "false", "", "", False)
    check("(e) unrelated finding under a converging cycle", [TOOL_DENIAL_ID],
          "false", "false", "", "", False)
    return failures


def all_scenarios(scripts, dedup_if_expr, tmproot):
    failures = []
    failures += scenario_a(scripts, tmproot)
    failures += scenario_b(scripts, tmproot)
    failures += scenario_f(scripts, tmproot)
    failures += scenario_g(scripts, tmproot)
    failures += scenario_h(scripts, tmproot)
    failures += scenario_cap(scripts, tmproot)
    failures += scenario_comment_truncation(scripts, tmproot)
    failures += scenario_stage_tool_separation(scripts, tmproot)
    failures += scenario_gate_suite_condition(scripts, dedup_if_expr, tmproot)
    return failures


# --------------------------------------------------------------------------
# Mutations -- each guard must be load-bearing (Constitution VIII)
# --------------------------------------------------------------------------
def mut_overlap_to_exact_equality(scripts):
    old = ("([ $matchable[] | select(. as $x | ($cited_ids | index($x)) != null) ] | unique) "
           "as $matched")
    text = scripts[DEDUP_STEP]
    if text.count(old) != 1:
        sys.exit(f"::error file={WATCHDOG}::verify-watchdog-overlap-fanout: could not find "
                 f"the overlap intersection expression in {DEDUP_STEP!r} to mutate -- the "
                 f"step text changed shape; update this gate alongside it.")
    new = "(if ($matchable | sort) == ($cited_ids | sort) then $matchable else [] end) as $matched"
    mutated = dict(scripts)
    mutated[DEDUP_STEP] = text.replace(old, new, 1)
    return mutated


def mut_comment_truncation_guard_removed(scripts):
    old = 'select((.comments // []) | length >= 100) | .number'
    text = scripts[DEDUP_STEP]
    if text.count(old) != 1:
        sys.exit(f"::error file={WATCHDOG}::verify-watchdog-overlap-fanout: could not find "
                 f"the comment-truncation guard's length check in {DEDUP_STEP!r} to mutate -- "
                 f"the step text changed shape; update this gate alongside it.")
    new = old.replace("length >= 100", "length >= 999999999")
    mutated = dict(scripts)
    mutated[DEDUP_STEP] = text.replace(old, new, 1)
    return mutated


def mut_fr009_always_file(scripts):
    old = "outcome=converging-gate-suite"
    text = scripts[GATE_SUITE_STEP]
    if text.count(old) != 1:
        sys.exit(f"::error file={WATCHDOG}::verify-watchdog-overlap-fanout: could not find "
                 f"{old!r} in {GATE_SUITE_STEP!r} to mutate.")
    mutated = dict(scripts)
    mutated[GATE_SUITE_STEP] = text.replace(old, "outcome=", 1)
    return mutated


TOOL_DENIAL_IDENT_RE = re.compile(
    r'ident: \{stage: \(\$fx\.stage // "" \| ascii_downcase \| '
    r'if \. == "" then "unknown" else \. end\),\s*tool:')


def mut_tool_denial_coarser_key(scripts):
    text = scripts[STAMP_STEP]
    new_text, n = TOOL_DENIAL_IDENT_RE.subn("ident: {tool:", text, count=1)
    if n != 1:
        sys.exit(f"::error file={WATCHDOG}::verify-watchdog-overlap-fanout: could not find "
                 f"the tool-denial ident: {{stage:..., tool:...}} shape in {STAMP_STEP!r} to "
                 f"mutate -- the step text changed shape; update this gate alongside it.")
    mutated = dict(scripts)
    mutated[STAMP_STEP] = new_text
    return mutated


MUTATIONS = [
    ("overlap matching reverted to exact-set equality", mut_overlap_to_exact_equality),
    ("the 100-comment truncation guard disabled", mut_comment_truncation_guard_removed),
    ("the FR-009 gate-suite filing condition reverted to \"always file\"", mut_fr009_always_file),
    ("the tool-denial id projection reverted to a shared, coarser key (drops #266's stage)",
     mut_tool_denial_coarser_key),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()
    ensure_jq()
    global BASH
    BASH = resolve_bash()

    scripts, dedup_if_expr = load_step_scripts()
    root = tempfile.mkdtemp()
    try:
        if args.self_test:
            failures = []
            for label, mutate in MUTATIONS:
                mutated = mutate(scripts)
                broke = all_scenarios(mutated, dedup_if_expr, root)
                if broke:
                    print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
                else:
                    print(f"::error::MUTATION SURVIVED - reintroducing '{label}' broke "
                          f"nothing in this suite, so the suite is not testing that defect.")
                    failures.append(f"mutation survived: {label}")
            print(f"verify-watchdog-overlap-fanout --self-test: {len(MUTATIONS)} "
                  f"mutation(s), {len(failures)} failure(s).")
            sys.exit(1 if failures else 0)

        failures = all_scenarios(scripts, dedup_if_expr, root)
        for f in failures:
            print(f"::error::{f}")
        print(f"verify-watchdog-overlap-fanout: {len(failures)} failure(s).")
        sys.exit(1 if failures else 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
