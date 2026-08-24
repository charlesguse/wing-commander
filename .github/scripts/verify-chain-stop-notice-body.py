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


def run_mark(steps, repo, runner_temp, spec_dir):
    return run_step(BASH, steps[MARK_STEP], repo, {"SPEC_DIR": spec_dir},
                    runner_temp)


def run_labels(steps, repo, runner_temp, bindir, calls, stage_label,
               record_status):
    return run_step(
        BASH, steps[LABELS_STEP], repo,
        {"GH_TOKEN": "x", "ISSUE": ISSUE, "STAGE_LABEL": stage_label,
         "RECORD_STATUS": record_status, "GH_CALLS": calls,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)


def run_notice(steps, repo, runner_temp, bindir, calls, reason,
               restart_command, record_status, run_url=""):
    return run_step(
        BASH, steps[NOTICE_STEP], repo,
        {"GH_TOKEN": "x", "ISSUE": ISSUE, "REASON": reason,
         "RUN_URL_INPUT": run_url,
         "DEFAULT_RUN_URL": "https://example.invalid/actions/runs/1",
         "RESTART_COMMAND": restart_command, "RECORD_STATUS": record_status,
         "GH_CALLS": calls,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)


def read_notice_body(work):
    proc = sh("cat /tmp/wcsn-notice.md 2>/dev/null || true", work)
    return proc.stdout


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
    body = read_notice_body(work)
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
    body = read_notice_body(work)
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
                               "resolved.", "")
    if rc != 0:
        failures.append(f"{where}: {NOTICE_STEP!r} exited {rc}: {out.strip()}")
        return failures
    body = read_notice_body(work)
    if "could not be updated" not in body:
        failures.append(f"{where}: notice body missing the 'could not be "
                        f"updated' wording when spec-dir is empty: {body!r}")
    if "Re-dispatch the intake stage" not in body:
        failures.append(f"{where}: notice body did not reproduce intake's "
                        f"plain re-dispatch restart-command byte-for-byte "
                        f"(T019): {body!r}")
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
    body = read_notice_body(work)
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


MUTATIONS = [
    ("notice renders the same wording regardless of record-status",
     _mut_notice_ignores_record_status),
    ("labels step removes stage-label even when the mark never landed",
     _mut_labels_removes_regardless_of_status),
    ("notice ignores the caller's restart-command",
     _mut_notice_ignores_restart_command),
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

    print(f"chain-stop-notice composite body: 3 base scenario(s), "
          f"{len(PLAIN_RESTART_FIXTURES)} restart-command fixture(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
