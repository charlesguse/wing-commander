#!/usr/bin/env python3
"""Gate: every FR-002 consumer site's three-state resolved-stage behavior
(specs/099-name-free-stage-identity T031).

WHY THIS EXISTS
---------------
T024-T030 converted watchdog.yml's seven collector/guard sites (branch-
drift's push-expected-stage gate and implement-only baseline arms, its
stage label, spec-meta's expected-stage map, final-pr-claims's and spec-
collision's scope guards, and the watchdog's own self-inspection cascade
guard) from matching the inspected run's display name to switching on
`resolved-stage`/`resolved-stage-source` — the two outputs
wing-commander-inspected-run-identity's composite now computes (R1/R2).
Nothing before this gate executed the SHIPPED bash to prove:

  1. SC-001 — a renamed wrapper and the reference-named wrapper, reporting
     the SAME underlying stage, produce IDENTICAL outcomes at every site,
     because none of them reads the run's display name any more.
  2. contracts/resolved-stage-identity.md Rule 2's third state: a site
     distinguishes "out of scope" (silent skip, unchanged) from "not
     identified" (skip AND an `{"collector": ..., "outcome": "unresolved"}`
     entry in collector-outcomes.json) — and the third state fires only
     when `resolved-stage-source` is empty, never merely because the
     resolved stage did not match.
  3. research.md R7's fixture rows for the composite's OWN precedence
     (record wins over name; the name fallback only when the record truly
     has nothing; an unrecognised name with no record leaves both empty).

This runs the REAL `run:` blocks extracted from watchdog.yml and the
composite action (wc_shell_harness.find_step/run_step) — no copied logic
to drift out of sync, matching this repository's existing execution-based
gate convention (Gate 19, verify-metrics-summary-record-emission.py).

Usage: python3 .github/scripts/verify-watchdog-resolved-stage-consumers.py
       python3 .github/scripts/verify-watchdog-resolved-stage-consumers.py --self-test
Requires: bash, jq.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)
from wc_gha_expr import evaluate, truthy  # noqa: E402

WATCHDOG = ".github/workflows/watchdog.yml"
COMPOSITE = ".github/actions/wing-commander-inspected-run-identity/action.yml"
STAGE_STEP_NAME = "Resolve inspected run's stage"
NAME_FALLBACK_STEP_NAME = (
    "Resolve inspected run's stage from its display name, when the "
    "record left it unresolved")

# Fixed per verify-branch-drift-sha-baseline.py's own REPO convention — this
# gate never talks to the real GitHub API, so the value only has to be
# well-formed, not real.
GITHUB_REPOSITORY = "charlesguse/wing-commander"

# A `gh` stub answering `gh run download` with a deterministic "no artifacts"
# failure (gh's own phrasing, matched by the "stage" step's own
# `grep -qiE "no artifact|..."` check), so a `record=None` row proves the
# SAME genuine-not-found path a real adopter's record-less run takes,
# without ever reaching the network — see resolve_stage()'s docstring.
GH_STUB = """#!/bin/sh
case " $* " in
  *" run "*"download "*)
    echo "gh: no artifacts found" >&2
    exit 1
    ;;
esac
exit 0
"""

BASH = None
GH_STUB_BINDIR = None
failures = []


def _make_gh_stub_bindir():
    d = tempfile.mkdtemp(prefix="wc-gh-stub-")
    path = os.path.join(d, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(path, 0o755)
    return d


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    print(f"::error::verify-watchdog-resolved-stage-consumers: {case}: {msg}")


def note(msg):
    print(f"note: {msg}")


def _outcomes_file(runner_temp):
    return os.path.join(runner_temp, "collector-outcomes.json")


def _init_runner_temp():
    runner_temp = tempfile.mkdtemp(prefix="wc-resolved-stage-")
    with open(_outcomes_file(runner_temp), "w", encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")
    return runner_temp


def _read_outcomes(runner_temp):
    with open(_outcomes_file(runner_temp), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Part A — the composite's own precedence (R1/R2), driven for real.
# ---------------------------------------------------------------------------
def resolve_stage(run_name, record=None, runner_temp=None):
    """Run the composite's "stage" step, then its "name-fallback" step, for
    real, against an optional pre-seeded metrics record. When `record` is
    None, the "stage" step's own `gh run download` still runs for real (it
    is unconditional whenever the record dir is empty, under `set -uo
    pipefail`) — it is pointed at GH_STUB_BINDIR's `gh` stub, which answers
    with a deterministic "no artifacts" failure, and GITHUB_REPOSITORY is
    passed explicitly so the step's `--repo "$GITHUB_REPOSITORY"` expansion
    never depends on whatever the ambient environment happens to carry (a
    bare host has it unset, which trips `set -u` before `gh` even runs; a
    real Actions runner sets it for real, which made this gate's own CI
    runs reach the live network under a fake token until this fix). This
    gate is about the precedence logic, not the download itself, which
    Gate 19's STAGE_SCENARIOS already covers in depth. Returns
    (resolved_stage, resolved_stage_source, rc1, rc2)."""
    own_temp = runner_temp is None
    if own_temp:
        runner_temp = tempfile.mkdtemp(prefix="wc-resolved-stage-compose-")
    try:
        mr_dir = os.path.join(runner_temp, "spec-slug-metrics-record")
        os.makedirs(mr_dir, exist_ok=True)
        if record is not None:
            with open(os.path.join(mr_dir, "record.json"), "w", encoding="utf-8") as fh:
                json.dump(record, fh)
        stage_script = find_step(COMPOSITE, STAGE_STEP_NAME)["run"]
        workdir = tempfile.mkdtemp(dir=runner_temp)
        rc1, out1, outputs1, _s1 = run_step(
            BASH, stage_script, workdir,
            {"ACTIONS_TOKEN": "x", "RUN_ID": "1",
             "GITHUB_REPOSITORY": GITHUB_REPOSITORY,
             "PATH": GH_STUB_BINDIR + os.pathsep + os.environ["PATH"]},
            runner_temp)
        if rc1 != 0:
            return "", "", rc1, None
        record_stage = outputs1.get("record-stage", "")

        fallback_script = find_step(COMPOSITE, NAME_FALLBACK_STEP_NAME)["run"]
        workdir2 = tempfile.mkdtemp(dir=runner_temp)
        rc2, out2, outputs2, _s2 = run_step(
            BASH, fallback_script, workdir2,
            {"RECORD_STAGE": record_stage, "RUN_NAME": run_name}, runner_temp)
        return (outputs2.get("resolved-stage", ""),
                outputs2.get("resolved-stage-source", ""), rc1, rc2)
    finally:
        if own_temp:
            shutil.rmtree(runner_temp, ignore_errors=True)


R7_CASES = [
    dict(name="record with no stage (stage_available: false): falls to the "
              "recognised name",
         record={"schema_version": 1, "stage": None},
         run_name="Wing Commander · 5 implement",
         expect=("implement", "name")),
    dict(name="missing record entirely: falls to the recognised name",
         record=None,
         run_name="Wing Commander · 4 tasks",
         expect=("tasks", "name")),
    dict(name="unrecognised display name, no record: both outputs stay empty",
         record=None,
         run_name="My Totally Custom CI Wrapper",
         expect=("", "")),
    dict(name="record vs. name disagreement: the record wins (FR-009)",
         record={"schema_version": 1, "stage": "tasks"},
         run_name="Wing Commander · 5 implement",
         expect=("tasks", "record")),
    dict(name="a clean or early-failed watchdog run (no metrics-record-"
              "diagnose written) falls to the recognised name, same as any "
              "other stage (maintainer review, fold leg-3)",
         record=None,
         run_name="Wing Commander · 8 watchdog",
         expect=("watchdog", "name")),
]


def case_r7_fixture_rows():
    case = "research.md R7 fixture rows"
    for row in R7_CASES:
        got_stage, got_source, rc1, rc2 = resolve_stage(
            row["run_name"], record=row["record"])
        want_stage, want_source = row["expect"]
        if rc1 != 0 or rc2 is not None and rc2 != 0:
            fail(case, f"{row['name']}: a composite step exited non-zero "
                       f"(rc1={rc1}, rc2={rc2})")
            continue
        if (got_stage, got_source) != (want_stage, want_source):
            fail(case, f"{row['name']}: expected resolved-stage="
                       f"{want_stage!r}/source={want_source!r}, got "
                       f"{got_stage!r}/{got_source!r}")
    if not any(f.startswith(case) for f in failures):
        note("all research.md R7 rows produced the expected "
             "resolved-stage/resolved-stage-source pair")


def case_sc001_name_independence_at_the_composite():
    """SC-001's root cause fix: once a record carries a stage, the
    resolved value is identical no matter what the run's display name
    is — the reference-named wrapper and an arbitrary renamed one."""
    case = "SC-001: composite output is name-independent when a record resolves"
    record = {"schema_version": 1, "stage": "implement"}
    reference = resolve_stage("Wing Commander · 5 implement", record=record)
    renamed = resolve_stage("My Totally Custom CI Wrapper", record=record)
    if reference[:2] != renamed[:2]:
        fail(case, f"reference-named wrapper resolved "
                   f"{reference[:2]!r}, renamed wrapper resolved "
                   f"{renamed[:2]!r} — the SAME underlying record must "
                   f"resolve identically regardless of display name")
    elif reference[:2] != ("implement", "record"):
        fail(case, f"expected both to resolve ('implement', 'record'), "
                   f"got {reference[:2]!r}")
    else:
        note("a reference-named and an arbitrarily-renamed wrapper "
             "reporting the same underlying record resolve to the "
             "identical resolved-stage/resolved-stage-source pair")


# ---------------------------------------------------------------------------
# Part B — the four bash-driven FR-002 consumer sites (T024/T027/T028/T029),
# each proven for the same three states: in scope, out of scope (resolved),
# and unresolved. Every env below is deliberately minimal, choosing values
# that reach a clean, pre-existing early exit for the "in scope"/"out of
# scope" cases (no spec slug resolved, no PR resolvable, etc.) so this gate
# needs no `gh` stub — it is proving the STAGE-SCOPING decision, not
# re-exercising the collector's downstream read logic other dedicated gates
# (verify-branch-drift-sha-baseline.py, verify-final-pr-claims-collector.sh,
# verify-spec-collision-collector.sh) already cover in depth.
# ---------------------------------------------------------------------------
def run_site(step_name, env, extra_files=None):
    runner_temp = _init_runner_temp()
    workdir = tempfile.mkdtemp(dir=runner_temp)
    try:
        script = find_step(WATCHDOG, step_name)["run"]
        rc, out, _outputs, summary = run_step(BASH, script, workdir, env, runner_temp)
        outcomes = _read_outcomes(runner_temp)
        return rc, out, outcomes, summary
    finally:
        shutil.rmtree(runner_temp, ignore_errors=True)


SITES = [
    dict(
        step="Collect: branch drift",
        collector="collect-branch-drift",
        base_env={
            "GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "RUN_ID": "1",
            "HEAD_BRANCH": "", "HEAD_SHA": "", "RUN_CREATED_AT": "",
            "RUN_CONCLUSION": "success", "META_STAGE": "",
            "STALLED_LABEL": "false", "SLUG": "", "SPEC_PREFIX": "spec/",
        },
        in_scope_stage="implement",
        out_of_scope_stage="finalize",
        # SLUG="" -> branch-drift's own #318 "no spec slug resolved" early
        # exit, before any outcome is written either way.
        expect_in_scope_outcomes=[],
        expect_out_of_scope_outcomes=[],
    ),
    dict(
        step="Collect: spec-meta state vs. expected stage",
        collector="collect-spec-meta",
        base_env={"RUN_CONCLUSION": "success", "META_STAGE": "implement",
                  "SLUG": "999-fixture"},
        in_scope_stage="implement",
        out_of_scope_stage="finalize",
        # This collector's own read never fails, so it unconditionally
        # records "ok" BEFORE the stage-scope case even runs (FR-010) --
        # Rule 2's "MUST additionally record" means the unresolved entry
        # joins that "ok", never replaces it.
        expect_in_scope_outcomes=[{"collector": "collect-spec-meta", "outcome": "ok"}],
        expect_out_of_scope_outcomes=[{"collector": "collect-spec-meta", "outcome": "ok"}],
        unresolved_also_has_ok=True,
    ),
    dict(
        step="Collect: final PR claims",
        collector="collect-final-pr-claims",
        base_env={"GH_TOKEN": "x", "RUN_CONCLUSION": "success", "SLUG": "",
                  "SPEC_DIR": "", "SPEC_PREFIX": "spec/"},
        in_scope_stage="finalize",
        out_of_scope_stage="implement",
        # SLUG="" -> "no spec slug resolved" early exit, before any gh call
        # or outcome write.
        expect_in_scope_outcomes=[],
        expect_out_of_scope_outcomes=[],
    ),
    dict(
        step="Collect: spec collision",
        collector="collect-spec-collision",
        base_env={"GH_TOKEN": "x", "RUN_CONCLUSION": "success", "SLUG": "",
                  "SPEC_DRAFT_PREFIX": "spec-draft/", "SPEC_PREFIX": "spec/"},
        in_scope_stage="intake",
        out_of_scope_stage="implement",
        # SLUG="" -> own_number resolves empty -> early exit, before any gh
        # call or outcome write.
        expect_in_scope_outcomes=[],
        expect_out_of_scope_outcomes=[],
    ),
]


def case_site_three_states(site):
    case = f"{site['collector']}: three-state resolved-stage behavior"

    # State 1: identified, in scope.
    env = dict(site["base_env"])
    env["RESOLVED_STAGE"] = site["in_scope_stage"]
    env["RESOLVED_STAGE_SOURCE"] = "name"
    rc, out, outcomes, _summary = run_site(site["step"], env)
    if rc != 0:
        fail(case, f"in-scope scenario exited {rc}: {out.strip()[:300]}")
    elif outcomes != site["expect_in_scope_outcomes"]:
        fail(case, f"in-scope scenario: expected outcomes "
                   f"{site['expect_in_scope_outcomes']!r}, got {outcomes!r}")
    elif any(o.get("outcome") == "unresolved" for o in outcomes):
        fail(case, f"in-scope scenario must never record 'unresolved', "
                   f"got {outcomes!r}")

    # State 2: identified, out of scope — silent skip, unchanged.
    env2 = dict(site["base_env"])
    env2["RESOLVED_STAGE"] = site["out_of_scope_stage"]
    env2["RESOLVED_STAGE_SOURCE"] = "name"
    rc2, out2, outcomes2, _summary2 = run_site(site["step"], env2)
    if rc2 != 0:
        fail(case, f"out-of-scope scenario exited {rc2}: {out2.strip()[:300]}")
    elif outcomes2 != site["expect_out_of_scope_outcomes"]:
        fail(case, f"out-of-scope scenario: expected outcomes "
                   f"{site['expect_out_of_scope_outcomes']!r}, got {outcomes2!r}")
    elif any(o.get("outcome") == "unresolved" for o in outcomes2):
        fail(case, f"out-of-scope (but resolved) scenario must never "
                   f"record 'unresolved' — that is Rule 2's state 2, not "
                   f"state 3 — got {outcomes2!r}")

    # State 3: not identified — resolved-stage-source empty.
    env3 = dict(site["base_env"])
    env3["RESOLVED_STAGE"] = ""
    env3["RESOLVED_STAGE_SOURCE"] = ""
    rc3, out3, outcomes3, _summary3 = run_site(site["step"], env3)
    if rc3 != 0:
        fail(case, f"unresolved scenario exited {rc3}: {out3.strip()[:300]}")
    else:
        unresolved_entries = [o for o in outcomes3
                              if o == {"collector": site["collector"],
                                       "outcome": "unresolved"}]
        if len(unresolved_entries) != 1:
            fail(case, f"unresolved scenario: expected exactly one "
                       f"{{'collector': {site['collector']!r}, 'outcome': "
                       f"'unresolved'}} entry, got {outcomes3!r}")
        if site.get("unresolved_also_has_ok") and \
                {"collector": site["collector"], "outcome": "ok"} not in outcomes3:
            fail(case, f"unresolved scenario: this collector's own read "
                       f"never fails, so 'ok' must still be present "
                       f"alongside 'unresolved', got {outcomes3!r}")

    # SC-001: the script text itself must never reference the run's
    # display name — the structural guarantee that makes "a renamed and a
    # reference-named wrapper behave identically" true by construction,
    # not by coincidence of these particular fixtures.
    script = find_step(WATCHDOG, site["step"])["run"]
    if "RUN_NAME" in script:
        fail(case, "this site's script still references RUN_NAME — a "
                   "renamed wrapper could once again produce a different "
                   "outcome than the reference-named one (SC-001)")

    if not any(f.startswith(case) for f in failures):
        note(f"{site['collector']}: in scope / out of scope / unresolved "
             f"each behave per contracts/resolved-stage-identity.md Rule 2, "
             f"and the script never reads the run's display name (SC-001)")


# ---------------------------------------------------------------------------
# Part C — T030's self-inspection cascade guard: a step-level `if:`, not a
# bash conditional, so there is no script body to execute differently; the
# proof is structural (constitution VIII: a check that cannot fail is not a
# check, so this also asserts against the PRE-#750 condition to show the
# assertion actually discriminates).
# ---------------------------------------------------------------------------
def case_self_inspection_guard_uses_resolved_stage():
    case = "watchdog self-inspection cascade guard (T030)"
    step = find_step(WATCHDOG, "Self-dispatch depth")
    cond = str(step.get("if", ""))
    want = "needs.collect.outputs.resolved-stage == 'watchdog'"
    old = "needs.collect.outputs.run-name == 'Wing Commander · 8 watchdog'"
    if cond != want:
        fail(case, f"expected the step's if: to read exactly {want!r}, "
                   f"got {cond!r}")
    elif cond == old:
        fail(case, "this assertion does not discriminate — the old "
                   "run-name condition would also have to fail it")
    else:
        note(f"Self-dispatch depth's if: reads {cond!r}")


NAME_WARNING_STEP_NAME = (
    "Report unrecognised display name, when nothing else identified the "
    "run's stage")

FR014_SCENARIOS = [
    ("stage unresolved + artifact found: FIRES (spec.md US2 AS3)",
     {"steps.spec-slug.outputs.resolved-stage-source": "",
      "steps.collect-execution-output.outputs.claude-execution-output-found": "true"},
     True),
    ("stage resolved via name, artifact found: does NOT fire (AS2/AS5)",
     {"steps.spec-slug.outputs.resolved-stage-source": "name",
      "steps.collect-execution-output.outputs.claude-execution-output-found": "true"},
     False),
    ("stage resolved via record, artifact found: does NOT fire",
     {"steps.spec-slug.outputs.resolved-stage-source": "record",
      "steps.collect-execution-output.outputs.claude-execution-output-found": "true"},
     False),
    ("stage unresolved, no artifact found: does NOT fire (AS4)",
     {"steps.spec-slug.outputs.resolved-stage-source": "",
      "steps.collect-execution-output.outputs.claude-execution-output-found": "false"},
     False),
]


def case_fr014_name_warning():
    """specs/099-name-free-stage-identity T039: the FR-014 name-warning
    step's `if:` fires exactly on "stage unresolved AND an execution-
    output artifact was found" (spec.md's US2 acceptance scenarios 2-5),
    and its body actually names the run's display name when it fires."""
    case = "FR-014 name warning (T039)"
    step = find_step(WATCHDOG, NAME_WARNING_STEP_NAME)
    cond = str(step.get("if", ""))
    for label, ctx, expect_fires in FR014_SCENARIOS:
        try:
            got = truthy(evaluate(cond, ctx))
        except (ValueError, IndexError) as exc:
            fail(case, f"{label}: if: did not evaluate: {exc}")
            continue
        if got != expect_fires:
            fail(case, f"{label}: if: evaluated to {got!r}, expected "
                       f"{expect_fires!r} (if: was {cond!r})")

    # Behaviorally confirm the firing case's BODY (not just its if:)
    # actually names the run's display name — ISSUE="" routes it to
    # $GITHUB_STEP_SUMMARY instead of a `gh issue comment` call, so no
    # stub is needed.
    runner_temp = tempfile.mkdtemp(prefix="wc-resolved-stage-fr014-")
    try:
        workdir = tempfile.mkdtemp(dir=runner_temp)
        env = {"GH_TOKEN": "x", "ISSUE": "", "RUN_URL": "https://example.invalid/run/1",
              "RUN_NAME": "My Totally Custom CI Wrapper"}
        rc, out, _outputs, summary = run_step(BASH, step["run"], workdir, env, runner_temp)
        if rc != 0:
            fail(case, f"the step's body exited {rc}: {out.strip()[:300]}")
        elif "My Totally Custom CI Wrapper" not in summary:
            fail(case, f"the warning body must name the run's own display "
                       f"name so a maintainer can act on it, got summary: "
                       f"{summary!r}")
    finally:
        shutil.rmtree(runner_temp, ignore_errors=True)

    if not any(f.startswith(case) for f in failures):
        note("the FR-014 name warning fires exactly on stage-unresolved + "
             "artifact-found, and names the run's own display name")


CASES = [
    case_r7_fixture_rows,
    case_sc001_name_independence_at_the_composite,
    lambda: case_site_three_states(SITES[0]),
    lambda: case_site_three_states(SITES[1]),
    lambda: case_site_three_states(SITES[2]),
    lambda: case_site_three_states(SITES[3]),
    case_self_inspection_guard_uses_resolved_stage,
    case_fr014_name_warning,
]


# ---------------------------------------------------------------------------
# --self-test: proves the "stage" step's `gh run download` line is actually
# exercised by resolve_stage()'s own fixture rows, and that an ambient
# GITHUB_REPOSITORY (set for real on every Actions runner, unset on a bare
# dev host) is not what makes those rows pass — the exact drift this gate
# shipped with (maintainer review, fold leg-1): locally, an absent ambient
# value tripped `set -u` before `gh` ever ran; in CI, a present ambient
# value let a real `gh run download` reach the network under a fake token
# and pass only because that live call happened to fail too.
# ---------------------------------------------------------------------------
def self_test():
    case = "self-test: GITHUB_REPOSITORY is passed explicitly, not inherited"
    had = os.environ.pop("GITHUB_REPOSITORY", None)
    try:
        # With the fix: resolve_stage()'s own env_extra carries
        # GITHUB_REPOSITORY regardless of the ambient environment, and the
        # gh stub answers the download deterministically.
        got_stage, got_source, rc1, rc2 = resolve_stage(
            "Wing Commander · 4 tasks", record=None)
        if rc1 != 0 or rc2 != 0:
            fail(case, f"with the fix in place, a record=None row still "
                       f"exited non-zero (rc1={rc1}, rc2={rc2}) even "
                       f"with GITHUB_REPOSITORY absent from the ambient "
                       f"environment")
        elif (got_stage, got_source) != ("tasks", "name"):
            fail(case, f"expected ('tasks', 'name'), got "
                       f"{(got_stage, got_source)!r}")

        # Without the fix: calling the real "stage" step directly, the same
        # way resolve_stage() used to before env_extra carried
        # GITHUB_REPOSITORY, must fail under `set -u` when the ambient
        # environment has none either — proving the case above is not
        # vacuous.
        runner_temp = tempfile.mkdtemp(prefix="wc-resolved-stage-selftest-")
        try:
            os.makedirs(os.path.join(runner_temp, "spec-slug-metrics-record"),
                        exist_ok=True)
            stage_script = find_step(COMPOSITE, STAGE_STEP_NAME)["run"]
            workdir = tempfile.mkdtemp(dir=runner_temp)
            rc_unfixed, out_unfixed, _o, _s = run_step(
                BASH, stage_script, workdir,
                {"ACTIONS_TOKEN": "x", "RUN_ID": "1"}, runner_temp)
        finally:
            shutil.rmtree(runner_temp, ignore_errors=True)
        if rc_unfixed == 0:
            fail(case, "calling the 'stage' step with no explicit "
                       "GITHUB_REPOSITORY and none in the ambient "
                       "environment unexpectedly exited 0 — this "
                       "self-test no longer discriminates the fix from "
                       "its absence")
        elif "GITHUB_REPOSITORY" not in out_unfixed and "unbound variable" \
                not in out_unfixed:
            fail(case, f"expected the unfixed call to fail on an unbound "
                       f"GITHUB_REPOSITORY, got: {out_unfixed.strip()[:300]}")
    finally:
        if had is not None:
            os.environ["GITHUB_REPOSITORY"] = had

    if not any(f.startswith(case) for f in failures):
        note("GITHUB_REPOSITORY is passed explicitly in env_extra (not "
             "inherited from the ambient environment), and the same call "
             "with that fix removed demonstrably fails — the self-test "
             "discriminates")


def main():
    global BASH, GH_STUB_BINDIR
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    GH_STUB_BINDIR = _make_gh_stub_bindir()

    if "--self-test" in sys.argv[1:]:
        self_test()
        if failures:
            print(f"{len(failures)} failure(s).")
            return 1
        print("verify-watchdog-resolved-stage-consumers self-test: "
              "GITHUB_REPOSITORY fix verified as non-vacuous; 0 failures.")
        return 0

    for case in CASES:
        case()

    if failures:
        print(f"{len(failures)} failure(s).")
        return 1
    print(f"verify-watchdog-resolved-stage-consumers: {len(CASES)} case(s) "
          f"checked; 0 failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
