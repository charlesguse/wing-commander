#!/usr/bin/env python3
"""The chain-stop notice composite's shell, executed against real failure shapes.

WHY THIS EXISTS
----------------
`wing-commander-chain-stop-notice` is the one shared shape every gated
stage's survivor job calls to mark spec-meta.json stalled, flip the
stage:stalled label, and post the "stage did not start" notice
(specs/041-implement-stall-notice). Its own contract (FR-011) promises it
never fails the calling job even when the mark itself cannot be written —
that promise is only real if the SHIPPED shell degrades correctly, not a
copy of it (the repository's own gate 5 precedent: a copy sat green for
weeks checking a filter that never shipped).

WHAT THIS CHECKS
----------------
Drives the composite's "Mark spec-meta.json stalled", "Flip labels", and
"Post the notice" steps — extracted from the shipped action.yml, executed
with `wc_shell_harness.run_step` — against three shapes (quickstart.md §3):

  1. A normal mark: real git repo + bare remote, checkout already done
     (the harness plays that part directly, same as verify-stall-restart-
     runbook.py does for implement.yml's stalled job) — record-status must
     read "marked", the notice must use the "marked" wording, and exactly
     one gh label add / one label removal (when stage-label was given) must
     be recorded.
  2. A push that loses a race (remote unreachable) — record-status must
     read "unwritable", the notice must use the "could not be updated"
     wording, and nothing must raise.
  3. spec-dir empty (the intake case, research.md D5) — the mark step is
     never invoked at all (mirrors production: its own `if:` on
     inputs.spec-dir), and the notice still renders the "could not be
     updated" wording.
  4. A split call (specs/077-stalled-per-spec-group: mark-record/
     post-notice) — the notice-only half (mark-record: "false") renders
     neither the "marked" nor the "could not be updated" wording for a
     non-empty spec-dir, since the mark is merely queued by a separate
     job it never waited on; the mark-only half (post-notice: "false")
     still removes the stale stage:<name> label on a successful mark but
     never adds the stage:stalled label itself.
  5. An agent step whose action failed in its own setup (#889/#972:
     agent-ran 'true', agent-started 'false') — the notice must say the
     agent never started and pushed no commits and point at the runner
     environment, never "failed after running; its pushed commits are on
     the branch"; agent-started 'true' or empty keeps the agent-ran
     wording.

Also asserts (T019): restart-command is rendered byte-for-byte as the
caller supplied it — the composite treats it as an opaque, fully
caller-rendered string (data-model.md's composite input table) — covering
both implement's recorded_iteration+1-derived line and the plain
re-dispatch line the other five stages pass.

Usage: python3 .github/scripts/verify-chain-stop-notice-body.py
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import copy
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step as find_composite_step,
                              resolve_bash, run_step, use_utf8_stdout)

COMPOSITE = ".github/actions/wing-commander-chain-stop-notice/action.yml"

MARK_STEP = "Mark spec-meta.json stalled"
LABELS_STEP = "Flip labels"
NOTICE_STEP = "Post the notice"

SPEC_DIR = "specs/041-implement-stall-notice"
ISSUE = "231"

BASH = None

GH_STUB = """#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
exit 0
"""


def load_steps():
    return {name: find_composite_step(COMPOSITE, name)["run"]
            for name in (MARK_STEP, LABELS_STEP, NOTICE_STEP)}


def sh(script, cwd):
    path = os.path.join(cwd, "_helper.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def make_workspace(root, reachable_remote=True):
    """A git repo holding a pre-stall spec-meta.json.

    `reachable_remote=False` builds a clone whose origin points nowhere —
    the same shape as a synthetic repo with no bare remote configured
    (quickstart.md §3 step 4): commit succeeds, push fails.
    """
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
mkdir -p '{SPEC_DIR}'
printf '%s\\n' '{{"issue": {ISSUE}, "spec_dir": "{SPEC_DIR}", "stage": "implement", "iteration": 2}}' > '{SPEC_DIR}/spec-meta.json'
git add -A
git commit -q -m seed
git push -q origin main
"""
    if not reachable_remote:
        setup += f"\ngit remote set-url origin '{os.path.join(work, 'no-such-remote.git')}'\n"
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not build a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    return work, repo


def new_gh_stub(work):
    bindir = os.path.join(work, "bin")
    calls = os.path.join(work, "gh_calls")
    os.makedirs(bindir, exist_ok=True)
    open(calls, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    return bindir, calls


def read_calls(path):
    with open(path, encoding="utf-8") as fh:
        return [l for l in fh.read().splitlines() if l.strip()]


def run_mark(steps, repo, runner_temp, spec_dir, agent_ran=""):
    return run_step(BASH, steps[MARK_STEP], repo,
                    {"SPEC_DIR": spec_dir, "AGENT_RAN": agent_ran},
                    runner_temp)


def run_labels(steps, repo, runner_temp, bindir, calls, stage_label,
               record_status, mark_record="true", post_notice="true"):
    return run_step(
        BASH, steps[LABELS_STEP], repo,
        {"GH_TOKEN": "x", "ISSUE": ISSUE, "STAGE_LABEL": stage_label,
         "RECORD_STATUS": record_status, "GH_CALLS": calls,
         "MARK_RECORD": mark_record, "POST_NOTICE": post_notice,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)


def run_notice(steps, repo, runner_temp, bindir, calls, reason,
               restart_command, record_status, run_url="", agent_ran="",
               agent_conclusion="", commits_published="", push_ok="",
               mark_record="true", spec_dir=SPEC_DIR, agent_started=""):
    return run_step(
        BASH, steps[NOTICE_STEP], repo,
        {"GH_TOKEN": "x", "ISSUE": ISSUE, "REASON": reason,
         "RUN_URL_INPUT": run_url,
         "DEFAULT_RUN_URL": "https://example.invalid/actions/runs/1",
         "RESTART_COMMAND": restart_command, "RECORD_STATUS": record_status,
         "AGENT_RAN": agent_ran, "AGENT_CONCLUSION": agent_conclusion,
         # #889/#972: empty by default, as the composite's input default.
         "AGENT_STARTED": agent_started,
         # specs/071-agent-push-credential: always supplied, empty by
         # default, matching the composite's own input default -- `set -u`
         # inside the step under test would otherwise reject a truly unset
         # env var, a gap production never hits (the input always resolves
         # to at least "").
         "COMMITS_PUBLISHED": commits_published,
         "PUSH_OK": push_ok,
         # The step under test resolves _shared/published-commits-line.sh
         # relative to $GITHUB_ACTION_PATH, exactly as Actions sets it for
         # a real composite invocation of this file.
         "GITHUB_ACTION_PATH": os.path.abspath(os.path.dirname(COMPOSITE)),
         "MARK_RECORD": mark_record, "SPEC_DIR": spec_dir,
         "GH_CALLS": calls,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)


def read_notice_body(runner_temp):
    """The body the notice step wrote to its own $RUNNER_TEMP (#598: never a
    fixed /tmp path, which parallel gate runs raced on); "" if none."""
    try:
        with open(os.path.join(runner_temp, "wcsn-notice.md"),
                  encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def scenario_marked(steps, root):
    """The normal path: checkout already done, mark succeeds."""
    failures = []
    where = "scenario: normal mark (T017)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, outputs, _ = run_mark(steps, repo, runner_temp, SPEC_DIR)
    if rc != 0:
        failures.append(f"{where}: {MARK_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if outputs.get("record-status") != "marked":
        failures.append(f"{where}: record-status={outputs.get('record-status')!r}, "
                        f"expected 'marked'.")
        return failures
    with open(os.path.join(repo, SPEC_DIR, "spec-meta.json"),
              encoding="utf-8") as fh:
        meta_text = fh.read()
    if '"stalled"' not in meta_text:
        failures.append(f"{where}: spec-meta.json was not marked stalled: {meta_text}")

    rc, out, _, _ = run_labels(steps, repo, runner_temp, bindir, calls,
                               "stage:implement", "marked")
    if rc != 0:
        failures.append(f"{where}: {LABELS_STEP!r} exited {rc}: {out.strip()}")
        return failures
    calls_text = read_calls(calls)
    adds = [c for c in calls_text if "--add-label stage:stalled" in c]
    removes = [c for c in calls_text if "--remove-label stage:implement" in c]
    if len(adds) != 1:
        failures.append(f"{where}: expected exactly one stage:stalled label add, "
                        f"got {len(adds)}: {calls_text}")
    if len(removes) != 1:
        failures.append(f"{where}: expected exactly one stage:implement label "
                        f"removal (mark succeeded, stage-label given), got "
                        f"{len(removes)}: {calls_text}")

    rc, out, _, _ = run_notice(steps, repo, runner_temp, bindir, calls,
                               "the implement stage never started",
                               "gh workflow run wing-commander-5-implement.yml "
                               "-f spec_dir=specs/041-implement-stall-notice "
                               "-f issue=231 -f iteration=3", "marked")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    comments = [c for c in read_calls(calls) if c.startswith("gh issue comment")]
    if len(comments) != 1:
        failures.append(f"{where}: expected exactly one gh issue comment call, "
                        f"got {len(comments)}: {read_calls(calls)}")
    body = read_notice_body(runner_temp)
    if "stage did not start" not in body:
        failures.append(f"{where}: notice body missing 'stage did not start' "
                        f"template text: {body!r}")
    if "marked stalled" not in body:
        failures.append(f"{where}: notice body missing the 'marked' wording "
                        f"(data-model.md 'record-status: marked' template): "
                        f"{body!r}")
    if "could not be updated" in body:
        failures.append(f"{where}: notice body used the unwritable wording on "
                        f"a successful mark: {body!r}")
    if "-f iteration=3" not in body:
        failures.append(f"{where}: notice body did not reproduce the caller's "
                        f"restart-command byte-for-byte (T019 — implement's "
                        f"recorded_iteration+1-derived line): {body!r}")
    return failures


def scenario_unwritable_push(steps, root):
    """T018 step 4: remote unreachable — commit succeeds, push fails."""
    failures = []
    where = "scenario: unreachable remote (T018)"
    work, repo = make_workspace(root, reachable_remote=False)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, outputs, _ = run_mark(steps, repo, runner_temp, SPEC_DIR)
    if rc != 0:
        failures.append(f"{where}: {MARK_STEP!r} exited {rc} — should degrade, "
                        f"not fail (FR-011): {out.strip()}")
        return failures
    if outputs.get("record-status") != "unwritable":
        failures.append(f"{where}: record-status={outputs.get('record-status')!r}, "
                        f"expected 'unwritable' when the push cannot land.")
        return failures

    rc, out, _, _ = run_labels(steps, repo, runner_temp, bindir, calls,
                               "stage:implement", outputs.get("record-status"))
    if rc != 0:
        failures.append(f"{where}: {LABELS_STEP!r} exited {rc}: {out.strip()}")
        return failures
    removes = [c for c in read_calls(calls)
              if "--remove-label stage:implement" in c]
    if removes:
        failures.append(f"{where}: stage-label was removed even though the "
                        f"mark never landed — implies a hand-off that never "
                        f"happened: {removes}")

    rc, out, _, _ = run_notice(steps, repo, runner_temp, bindir, calls,
                               "the implement stage never started",
                               "", "unwritable")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    comments = [c for c in read_calls(calls) if c.startswith("gh issue comment")]
    if len(comments) != 1:
        failures.append(f"{where}: expected exactly one gh issue comment call "
                        f"even when the record could not be written, got "
                        f"{len(comments)}: {read_calls(calls)}")
    body = read_notice_body(runner_temp)
    if "could not be updated" not in body:
        failures.append(f"{where}: notice body missing the 'could not be "
                        f"updated' wording: {body!r}")
    if "marked stalled" in body:
        failures.append(f"{where}: notice body used the 'marked' wording on "
                        f"a push that never landed: {body!r}")
    return failures


def scenario_empty_spec_dir(steps, root):
    """T018 step 5 / research.md D5: spec-dir empty (intake's case)."""
    failures = []
    where = "scenario: spec-dir empty (T018, intake)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    # Production never invokes the mark step at all when spec-dir is empty
    # (the composite's own `if:` on that step) — the harness mirrors that by
    # simply not calling run_mark, feeding the notice step an empty
    # record-status exactly as `steps.mark.outputs.record-status` resolves
    # for a step that never ran.
    rc, out, _, _ = run_notice(steps, repo, runner_temp, bindir, calls,
                               "no specification exists yet for this run",
                               "Re-dispatch the intake stage for this "
                               "specification once the cause above is "
                               "resolved.", "", spec_dir="")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    if "could not be updated" not in body:
        failures.append(f"{where}: notice body missing the 'could not be "
                        f"updated' wording when spec-dir is empty: {body!r}")
    if "Re-dispatch the intake stage" not in body:
        failures.append(f"{where}: notice body did not reproduce intake's "
                        f"plain re-dispatch restart-command byte-for-byte "
                        f"(T019): {body!r}")
    return failures


def scenario_split_notice_only(steps, root):
    """specs/077-stalled-per-spec-group: a caller that splits its notice
    from its stall-mark write (mark-record: "false") gets neither the
    'marked' nor the 'could not be updated' wording — the mark is being
    written by a separate job this call never waited on, and the notice
    must say so rather than implying the write failed."""
    failures = []
    where = "scenario: split call, notice-only (specs/077)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    # Production never invokes the mark step at all on the notice-only call
    # (mark-record: "false") -- mirrored here the same way as the
    # empty-spec-dir scenario above: no run_mark call, empty record-status.
    rc, out, _, _ = run_notice(steps, repo, runner_temp, bindir, calls,
                               "the pr-conversation stage never started",
                               "Re-dispatch the pr-conversation stage for "
                               "this pull request once the cause above is "
                               "resolved.", "", mark_record="false",
                               spec_dir=SPEC_DIR)
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    if "could not be updated" in body:
        failures.append(f"{where}: notice body used the 'could not be "
                        f"updated' wording for a mark that is merely queued "
                        f"elsewhere, not one that actually failed: {body!r}")
    if "marked stalled" in body:
        failures.append(f"{where}: notice body claimed the record was "
                        f"marked, but this call never ran the mark step: "
                        f"{body!r}")
    if "separate job" not in body:
        failures.append(f"{where}: notice body does not say the stall-mark "
                        f"is being written by a separate job: {body!r}")
    return failures


def scenario_split_mark_only_labels(steps, root):
    """specs/077-stalled-per-spec-group: the mark-only call (post-notice:
    "false") still removes the stale stage:<name> label once its own mark
    succeeds, but never adds the stage:stalled label -- that is the
    notice-only call's job, and adding it twice would just be redundant,
    not wrong, but a survivor that never posts a notice at all (a caller
    that only ever makes the mark-only call) must not silently also flip
    that label as a side effect of the split."""
    failures = []
    where = "scenario: split call, mark-only labels (specs/077)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, outputs, _ = run_mark(steps, repo, runner_temp, SPEC_DIR)
    if rc != 0:
        failures.append(f"{where}: {MARK_STEP!r} exited {rc}: {out.strip()}")
        return failures

    rc, out, _, _ = run_labels(steps, repo, runner_temp, bindir, calls,
                               "stage:implement", outputs.get("record-status"),
                               mark_record="true", post_notice="false")
    if rc != 0:
        failures.append(f"{where}: {LABELS_STEP!r} exited {rc}: {out.strip()}")
        return failures
    calls_text = read_calls(calls)
    adds = [c for c in calls_text if "--add-label stage:stalled" in c]
    removes = [c for c in calls_text if "--remove-label stage:implement" in c]
    if adds:
        failures.append(f"{where}: the mark-only call (post-notice: "
                        f"'false') added the stage:stalled label -- that is "
                        f"the notice-only call's job: {calls_text}")
    if len(removes) != 1:
        failures.append(f"{where}: expected exactly one stage:implement "
                        f"label removal (the mark succeeded), got "
                        f"{len(removes)}: {calls_text}")
    return failures


def scenario_agent_ran(steps, root):
    """spec 052 FR-011/FR-015: agent-ran=true drops the "did not start" /
    "no work was lost" wording, in both the marked and unwritable shapes."""
    failures = []
    where = "scenario: agent ran but a post-agent step failed (spec 052)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, _, _ = run_notice(
        steps, repo, runner_temp, bindir, calls,
        "the agent step ran (concluded: failure) and the 'push' step after "
        "it did not complete",
        "Re-dispatch the clarify stage for this specification once the "
        "cause above is resolved.", "marked",
        agent_ran="true", agent_conclusion="failure")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    if "the stage did not start" in body:
        failures.append(f"{where}: notice still claims the stage did not "
                        f"start even though agent-ran=true: {body!r}")
    if "no work was lost" in body:
        failures.append(f"{where}: notice still claims no work was lost "
                        f"even though agent-ran=true: {body!r}")
    if "concluded: failure" not in body:
        failures.append(f"{where}: notice does not name the agent's own "
                        f"conclusion: {body!r}")
    if "the agent completed its work" in body:
        failures.append(f"{where}: notice claims the agent completed its "
                        f"work even though it concluded failure (second "
                        f"maintainer review of PR #407, FR-011): {body!r}")
    if "failed after running" not in body:
        failures.append(f"{where}: notice does not say the agent step "
                        f"failed after running when agent-conclusion is "
                        f"'failure': {body!r}")
    return failures


def scenario_agent_ran_success(steps, root):
    """spec 052 second maintainer review of PR #407 (FR-011): a stall caused
    by a step *after* a successfully-concluded agent step must say the agent
    completed its work, not the generic (and previously unconditional)
    "ran to completion" claim that also applied when the agent had failed."""
    failures = []
    where = "scenario: agent ran and succeeded, a later step stalled (spec 052)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, _, _ = run_notice(
        steps, repo, runner_temp, bindir, calls,
        "the agent step ran (concluded: success) and the 'push' step after "
        "it did not complete",
        "Re-dispatch the clarify stage for this specification once the "
        "cause above is resolved.", "marked",
        agent_ran="true", agent_conclusion="success")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    if "the agent completed its work" not in body:
        failures.append(f"{where}: notice does not say the agent completed "
                        f"its work when agent-conclusion is 'success': "
                        f"{body!r}")
    if "failed after running" in body:
        failures.append(f"{where}: notice claims the agent failed after "
                        f"running even though it concluded success: {body!r}")
    return failures


def scenario_agent_never_started(steps, root):
    """#889/#972: the agent step's action failed in its own setup (run
    37866026318: its runtime install failed on an image without unzip), so
    agent-ran is 'true' and agent-conclusion 'failure', but agent-started
    is 'false'. The notice must not claim the agent ran or that it pushed
    commits, and must send the reader to the runner environment rather
    than straight to a re-dispatch that fails identically."""
    failures = []
    where = "scenario: agent action failed before the agent started (#889)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, _, _ = run_notice(
        steps, repo, runner_temp, bindir, calls,
        "the agent step's action failed in its own setup before the agent "
        "started",
        "Re-dispatch the intake stage for this specification once the "
        "cause above is resolved.", "marked",
        agent_ran="true", agent_conclusion="failure", agent_started="false")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    for bad in ("pushed commits are on the branch", "failed after running",
                "the agent ran but"):
        if bad in body:
            failures.append(f"{where}: notice says {bad!r} for an agent "
                            f"that never started: {body!r}")
    for good in ("the agent never started", "pushed no commits",
                 "runner environment"):
        if good not in body:
            failures.append(f"{where}: notice does not say {good!r}: "
                            f"{body!r}")
    if "no work was lost" in body:
        failures.append(f"{where}: notice uses the stage-did-not-start "
                        f"wording although the agent step itself ran: "
                        f"{body!r}")

    # agent-started 'true' or empty (a caller predating the input) keeps
    # the agent-ran wording unchanged.
    for started in ("true", ""):
        rc, out, _, _ = run_notice(
            steps, repo, runner_temp, bindir, calls,
            "the agent step ran (concluded: failure) and a step after it "
            "did not complete",
            "Re-dispatch the intake stage for this specification once the "
            "cause above is resolved.", "marked",
            agent_ran="true", agent_conclusion="failure",
            agent_started=started)
        body = read_notice_body(runner_temp)
        if rc != 0 or "failed after running" not in body:
            failures.append(f"{where}: agent-started={started!r} no longer "
                            f"renders the agent-ran wording: {body!r}")
    return failures


def scenario_commits_published(steps, root):
    """specs/071-agent-push-credential FR-016/FR-017: a nonzero
    commits-published count names it; zero/empty renders no such line.
    push-ok=false (code review of that PR) renders the honest "could not
    be published either" wording instead of claiming success."""
    failures = []
    where = "scenario: commits-published line (071)"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    cases = [
        ("", "", False, False),
        ("0", "", False, False),
        ("3", "true", True, False),
        ("3", "", True, False),
        ("3", "false", False, True),
    ]
    for commits, push_ok, expect_published, expect_failed in cases:
        rc, out, _, _ = run_notice(
            steps, repo, runner_temp, bindir, calls,
            "the clarify stage never started",
            "Re-dispatch the clarify stage for this specification once "
            "the cause above is resolved.", "marked",
            commits_published=commits, push_ok=push_ok)
        if rc != 0:
            failures.append(f"{where} (commits-published={commits!r}, "
                            f"push-ok={push_ok!r}): {NOTICE_STEP!r} exited "
                            f"{rc}: {out.strip()}")
            continue
        body = read_notice_body(runner_temp)
        has_published = "were published after it" in body
        has_failed = "could not be published either" in body
        if expect_published and not has_published:
            failures.append(f"{where}: commits-published={commits!r} "
                            f"push-ok={push_ok!r} did not render the "
                            f"published-commits line: {body!r}")
        if expect_failed and not has_failed:
            failures.append(f"{where}: commits-published={commits!r} "
                            f"push-ok={push_ok!r} did not render the "
                            f"rescue-push-failed line: {body!r}")
        if (expect_published or expect_failed) and "3 commit(s)" not in body:
            failures.append(f"{where}: commits-published={commits!r} "
                            f"push-ok={push_ok!r} did not name the count: "
                            f"{body!r}")
        if not expect_published and has_published:
            failures.append(f"{where}: commits-published={commits!r} "
                            f"push-ok={push_ok!r} rendered the published-"
                            f"commits line when it should not have: {body!r}")
        if not expect_failed and has_failed:
            failures.append(f"{where}: commits-published={commits!r} "
                            f"push-ok={push_ok!r} rendered the rescue-push-"
                            f"failed line when it should not have: {body!r}")
    return failures


def scenario_restart_command_verbatim(steps, root, stage, restart_command,
                                       forbid_substrings=()):
    """T019: restart-command is opaque to the composite — echoed verbatim."""
    failures = []
    where = f"scenario: restart-command verbatim ({stage})"
    work, repo = make_workspace(root, reachable_remote=True)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_gh_stub(work)

    rc, out, _, _ = run_notice(steps, repo, runner_temp, bindir, calls,
                               f"the {stage} stage never started",
                               restart_command, "marked")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(runner_temp)
    if restart_command not in body:
        failures.append(f"{where}: notice body did not contain {stage}'s "
                        f"restart-command byte-for-byte: {body!r}")
    for bad in forbid_substrings:
        if bad in body and bad not in restart_command:
            failures.append(f"{where}: notice body contains {bad!r}, which "
                            f"{stage}'s restart-command never supplied — the "
                            f"composite invented text instead of staying "
                            f"caller-rendered: {body!r}")
    return failures


# One fixture per non-implement stage (T008/T010/T012/T014/T016): a plain
# re-dispatch line, no recorded_iteration + 1 arithmetic. Implement's own
# fixture (which DOES compute recorded_iteration + 1) is covered by
# scenario_marked above.
PLAIN_RESTART_FIXTURES = [
    ("clarify", "Re-dispatch the clarify stage for this specification once "
                "the cause above is resolved."),
    ("finalize", "Re-dispatch the finalize stage for this specification "
                 "once the cause above is resolved."),
    ("intake", "Re-dispatch the intake stage for this specification once "
               "the cause above is resolved."),
    ("pr-conversation", "Re-dispatch the pr-conversation stage for this "
                        "pull request once the cause above is resolved."),
    ("tasks", "Re-dispatch the tasks stage for this specification once the "
              "cause above is resolved."),
]


def suite(steps, root):
    failures = []
    failures += scenario_marked(steps, root)
    failures += scenario_unwritable_push(steps, root)
    failures += scenario_empty_spec_dir(steps, root)
    failures += scenario_split_notice_only(steps, root)
    failures += scenario_split_mark_only_labels(steps, root)
    failures += scenario_agent_ran(steps, root)
    failures += scenario_agent_ran_success(steps, root)
    failures += scenario_agent_never_started(steps, root)
    failures += scenario_commits_published(steps, root)
    for stage, cmd in PLAIN_RESTART_FIXTURES:
        failures += scenario_restart_command_verbatim(
            steps, root, stage, cmd,
            forbid_substrings=("recorded", "iteration + 1", "restart_iteration"))
    return failures


def _mut_notice_ignores_record_status(steps):
    """Both branches render the same wording — the maintainer cannot tell
    whether the record was actually marked."""
    steps[NOTICE_STEP] = steps[NOTICE_STEP].replace(
        'if [ "$RECORD_STATUS" = "marked" ]; then',
        'if true; then')


def _mut_labels_removes_regardless_of_status(steps):
    """The stage-label is removed even when the mark never landed — implies
    a successful hand-off that never happened."""
    steps[LABELS_STEP] = steps[LABELS_STEP].replace(
        '[ -n "$STAGE_LABEL" ] && [ "$RECORD_STATUS" = "marked" ]',
        '[ -n "$STAGE_LABEL" ]')


def _mut_notice_ignores_restart_command(steps):
    """The composite starts inventing its own restart text instead of
    staying caller-rendered (FR-008 — each stage owns its own math)."""
    steps[NOTICE_STEP] = steps[NOTICE_STEP].replace(
        'restart="$RESTART_COMMAND"',
        'restart=""')


def _mut_notice_ignores_agent_ran(steps):
    """spec 052 FR-011/FR-015 regression: the notice claims the stage never
    started even though the entry job's agent step ran."""
    steps[NOTICE_STEP] = steps[NOTICE_STEP].replace(
        'if [ "$AGENT_RAN" = "true" ]; then',
        'if false; then')


def _mut_notice_ignores_agent_conclusion(steps):
    """Second maintainer review of PR #407 (FR-011) regression: the notice
    claims the agent "completed its work" regardless of whether it actually
    concluded success or failure."""
    steps[NOTICE_STEP] = steps[NOTICE_STEP].replace(
        'case "$AGENT_CONCLUSION" in\n'
        '    success) agent_clause="the agent completed its work" ;;\n'
        '    failure) agent_clause="the agent step failed after '
        'running; its pushed commits are on the branch" ;;\n'
        '    *) agent_clause="the agent step ran" ;;\n'
        '  esac',
        'agent_clause="the agent completed its work"')


def _mut_notice_ignores_agent_started(steps):
    """#889/#972 regression: an agent step whose action failed in its own
    setup is reported as "the agent step failed after running; its pushed
    commits are on the branch"."""
    steps[NOTICE_STEP] = steps[NOTICE_STEP].replace(
        'if [ "$AGENT_RAN" = "true" ] && [ "$AGENT_STARTED" = "false" ]; then',
        'if false; then')


def _mut_notice_ignores_commits_published(steps):
    """specs/071-agent-push-credential regression: the notice stops naming
    a nonzero commits-published count (the eval of the single-homed
    _shared/published-commits-line.sh short-circuited to always-empty)."""
    original = steps[NOTICE_STEP]
    mutated = original.replace(
        'eval "$(bash "$GITHUB_ACTION_PATH/../_shared/published-commits-line.sh" "$COMMITS_PUBLISHED" "$PUSH_OK")"',
        'published_line=""')
    if mutated == original:
        sys.exit("::error::self-test setup: "
                 "_mut_notice_ignores_commits_published's target text was "
                 "not found in the shipped step -- update the mutation "
                 "together with the step.")
    steps[NOTICE_STEP] = mutated


MUTATIONS = [
    ("notice renders the same wording regardless of record-status",
     _mut_notice_ignores_record_status),
    ("notice ignores commits-published and never names a nonzero count",
     _mut_notice_ignores_commits_published),
    ("labels step removes stage-label even when the mark never landed",
     _mut_labels_removes_regardless_of_status),
    ("notice ignores the caller's restart-command",
     _mut_notice_ignores_restart_command),
    ("notice ignores agent-ran and always claims the stage never started",
     _mut_notice_ignores_agent_ran),
    ("notice ignores agent-conclusion and always claims the agent completed "
     "its work",
     _mut_notice_ignores_agent_conclusion),
    ("notice ignores agent-started and claims an agent that never started "
     "ran and pushed commits",
     _mut_notice_ignores_agent_started),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped step under test "
                 "commits and pushes, so nothing here can run without it.")
    if not os.path.isfile(COMPOSITE):
        sys.exit(f"::error::run this from the repository root; {COMPOSITE} "
                 f"not found.")

    base_steps = load_steps()
    root = tempfile.mkdtemp()
    try:
        failures = suite(base_steps, root)
        for f in failures:
            print(f"::error::{f}")

        for label, apply_mutation in MUTATIONS:
            mutated = copy.deepcopy(base_steps)
            apply_mutation(mutated)
            if mutated == base_steps:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation so "
                      f"this harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if suite(mutated, root):
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing in this suite.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"chain-stop-notice composite body: 9 base scenario(s), "
          f"{len(PLAIN_RESTART_FIXTURES)} restart-command fixture(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
