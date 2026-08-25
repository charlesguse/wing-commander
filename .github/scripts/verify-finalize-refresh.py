#!/usr/bin/env python3
"""Gate 35: finalize refreshes an open final PR, and only an open one.

WHY THIS EXISTS
---------------
Before specs/042-post-review-fold-loop, `finalize.yml`'s existing-PR guard
was a boolean `skip` — any existing PR (open, merged, or closed) meant
"nothing to do", so a folded change never got a second look and a
maintainer's review feedback silently went unanswered. research.md D7-D10
widen the guard to a tri-state `pr-state` (none/open/merged/closed): `none`
creates exactly as today, `open` refreshes the PR body/label/metadata/
re-review instead of skipping, and `merged`/`closed` report and change
nothing.

This gate drives the SHIPPED `run:` text of the guard, diff, body-assembly,
PR-open-or-update, re-review-request, and metadata-commit steps against a
REAL local git repository with a bare remote (mirroring Gate 14's
`verify-stall-restart-runbook.py` shape) — needed because the idempotent
fold-log append (D9a) and the preserve/regenerate PR-body split (D9) have
real commit/push and real existing-body-read/write side effects a
transcript-only harness cannot honestly exercise. `gh` is a stub executable
on PATH recording every invocation's arguments and serving canned
responses.

Adaptation note: "Report the final pull request is already merged/closed"
delegate to the `wing-commander-callout` composite action (a `uses:` step,
not inline `run:` text) — not something this harness can execute directly.
Their reachability is instead confirmed structurally (their `if:` names the
exact `pr-state` value gate-coverage-042.md's scenarios 2/3 require), which
is the same class of static check Gate 15 itself already uses for
job-suppression conditions.

Usage: python3 .github/scripts/verify-finalize-refresh.py [-v]
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import copy
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,
                              use_utf8_stdout)

STAGE = ".github/workflows/finalize.yml"

GUARD_STEP = "Check for an existing final pull request"
DIFF_STEP = 'Check for a diff and compute "how to see it"'
BODY_STEP = "Assemble PR body"
PR_STEP = "Open or update the final pull request"
REREVIEW_STEP = "Request re-review from the answered reviewer(s)"
METADATA_STEP = "Commit metadata (stage -> review)"
REPORT_MERGED_STEP = "Report the final pull request is already merged"
REPORT_CLOSED_STEP = "Report the final pull request is closed"

REPO = "charlesguse/wing-commander"
SPEC_DIR = "specs/042-post-review-fold-loop"
SLUG = "042-post-review-fold-loop"
ISSUE = "250"
DB = "main"
PR_NUMBER = "260"

BASH = None
VERBOSE = "-v" in sys.argv[1:]

STATE_BEGIN = "<!-- wing-commander-finalize:state:begin -->"
STATE_END = "<!-- wing-commander-finalize:state:end -->"
FOLDLOG_BEGIN = "<!-- wing-commander-finalize:fold-log:begin -->"
FOLDLOG_END = "<!-- wing-commander-finalize:fold-log:end -->"
NARRATIVE_BEGIN = "<!-- wing-commander-finalize:narrative:begin -->"
NARRATIVE_END = "<!-- wing-commander-finalize:narrative:end -->"


def extract_between(text, start_marker, end_marker):
    """The text strictly between the FIRST start_marker and the following
    end_marker — never a naive substring split, which breaks the moment one
    marker's text is itself a substring of the other (both markers here
    share the "wing-commander-finalize:" prefix).
    """
    try:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return text[start:end]
    except ValueError:
        return None


GH_STUB = r"""#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
case " $* " in
  *" pr "*"view "*"--json body"*)
    # gh's --jq '.body // ""' already extracts the raw body text server-
    # side; the stub replicates that shape rather than wrapping in JSON.
    if [ -n "${GH_PR_BODY_FILE:-}" ] && [ -f "$GH_PR_BODY_FILE" ]; then
      cat "$GH_PR_BODY_FILE"
    fi
    exit 0
    ;;
  *" pr "*"view "*"--json reviews"*)
    printf '%s' "${GH_REVIEWS_JSON:-[]}"
    exit 0
    ;;
  *" pr "*"view "*)
    printf '{"url": "https://example.invalid/pull/%s"}' "${GH_PR_NUMBER:-1}"
    exit 0
    ;;
  *" pr "*"list "*)
    # gh's --jq '.[0] // empty' already reduces the array server-side.
    printf '%s' "${GH_PR_LIST_JSON:-[]}" | jq -c '.[0] // empty'
    exit 0
    ;;
  *" pr "*"edit "*"--add-reviewer"*)
    exit "${GH_ADD_REVIEWER_EXIT:-0}"
    ;;
  *" pr "*"edit "*)
    exit "${GH_PR_EDIT_EXIT:-0}"
    ;;
  *" pr "*"create "*)
    exit "${GH_PR_CREATE_EXIT:-0}"
    ;;
  *" issue "*"view "*)
    printf '{"labels": []}'
    exit 0
    ;;
esac
exit 0
"""


def sh(script, cwd):
    path = os.path.join(cwd, "_helper.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def resolve_gh_expressions(text, runner_temp):
    """finalize.yml's own established style uses `${{ runner.temp }}`
    (and, in one step, `${{ steps.body.outputs.body-file }}`) directly
    inside `run:` text — GitHub substitutes these before bash ever sees the
    script; this harness must do the same before handing the text to bash.
    """
    text = text.replace("${{ runner.temp }}", runner_temp)
    text = text.replace("${{ steps.body.outputs.body-file }}",
                        os.path.join(runner_temp, "finalize-pr-body.md"))
    return text


SPEC_BRANCH = f"spec/{SLUG}"


def make_repo(root, iteration, tasks_checked, tasks_total,
             pending_re_review_from=None):
    """A real git repo (bare remote + clone) with `main` (DB) holding only a
    root README, and a separate spec branch — checked out in `repo` — that
    diverges from it with spec.md/tasks.md/spec-meta.json. Keeping the spec
    branch distinct from DB is what makes `git diff --stat origin/$DB...HEAD`
    a genuine, non-empty comparison, matching production where the spec
    branch is always ahead of the default branch.
    """
    import json
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    tasks_lines = "\n".join(
        [f"- [X] T{i:03d} done" for i in range(tasks_checked)]
        + [f"- [ ] T{i:03d} todo" for i in range(tasks_total - tasks_checked)])
    meta = {"issue": int(ISSUE), "spec_dir": SPEC_DIR, "stage": "implement",
           "iteration": iteration,
           "pending_re_review_from": pending_re_review_from or []}
    setup = f"""
git init --bare -q -b {DB} '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
echo 'root' > README.md
git add -A
git commit -q -m 'seed main'
git push -q origin {DB}
git checkout -q -b '{SPEC_BRANCH}'
mkdir -p '{SPEC_DIR}'
echo '# Feature Specification: The Post-Review Fold Loop' > '{SPEC_DIR}/spec.md'
cat > '{SPEC_DIR}/spec-meta.json' <<'META_EOF'
{json.dumps(meta)}
META_EOF
cat > '{SPEC_DIR}/tasks.md' <<'TASKS_EOF'
{tasks_lines}
TASKS_EOF
git add -A
git commit -q -m seed
git push -q -u origin '{SPEC_BRANCH}'
git rev-parse HEAD
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not seed a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    base_sha = proc.stdout.strip().splitlines()[-1]
    return repo, base_sha


def add_fold_commit(repo, work, leg_id, summary):
    commit_script = f"""
cd '{repo}'
echo 'fold change' >> '{SPEC_DIR}/tasks.md'
git add -A
git commit -q -m 'fold({leg_id}): {summary}'
git push -q origin '{SPEC_BRANCH}'
git rev-parse HEAD
git rev-parse --short HEAD
"""
    proc = sh(commit_script, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not seed a fold commit: "
                 f"{proc.stdout}{proc.stderr}")
    lines = proc.stdout.strip().splitlines()
    return lines[-2], lines[-1]  # (full sha, short sha)


def new_stub_dir(work):
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    calls = os.path.join(work, "gh_calls")
    open(calls, "w").close()
    return bindir, calls


def gh_call_count(calls_path, *substrings):
    with open(calls_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return sum(1 for line in lines if all(s in line for s in substrings))


def load_steps():
    names = (GUARD_STEP, DIFF_STEP, BODY_STEP, PR_STEP, REREVIEW_STEP,
            METADATA_STEP)
    return {name: find_step(STAGE, name)["run"] for name in names}


def base_env(work, bindir, calls, runner_temp, extra=None):
    env = {"GH_TOKEN": "x", "GITHUB_REPOSITORY": REPO,
          "SLUG": SLUG, "DB": DB, "SPEC_PREFIX": "spec/",
          "ISSUE": ISSUE, "SPEC_DIR": SPEC_DIR,
          "GH_CALLS": calls, "PATH": bindir + os.pathsep + os.environ["PATH"]}
    if extra:
        env.update(extra)
    return env


def run_guard(steps, work, bindir, calls, runner_temp, pr_list_json):
    return run_step(BASH, steps[GUARD_STEP], work,
                    base_env(work, bindir, calls, runner_temp,
                             {"GH_PR_LIST_JSON": pr_list_json}),
                    runner_temp)


def run_diff(steps, repo, work, bindir, calls, runner_temp, guard_pr_state):
    return run_step(BASH, steps[DIFF_STEP], repo,
                    base_env(work, bindir, calls, runner_temp,
                             {"GUARD_PR_STATE": guard_pr_state}),
                    runner_temp)


# --------------------------------------------------------------- scenarios

def scenario_guard_tri_state(steps, root):
    """D7: the guard reports none/open/merged/closed correctly."""
    failures = []
    cases = [
        ("[]", "none"),
        ('[{"number": 260, "state": "OPEN", "url": "https://x/260"}]', "open"),
        ('[{"number": 260, "state": "MERGED", "url": "https://x/260"}]', "merged"),
        ('[{"number": 260, "state": "CLOSED", "url": "https://x/260"}]', "closed"),
    ]
    for pr_list_json, expected in cases:
        work = tempfile.mkdtemp(dir=root)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls = new_stub_dir(work)
        rc, out, outputs, _ = run_guard(steps, work, bindir, calls,
                                        runner_temp, pr_list_json)
        if rc != 0:
            failures.append(f"guard({expected}): exited {rc}: {out.strip()}")
            continue
        if outputs.get("pr-state") != expected:
            failures.append(f"guard({pr_list_json}): expected pr-state="
                            f"{expected!r}, got {outputs.get('pr-state')!r}")
    return failures


def scenario_diff_propagation(steps, root):
    """merged/closed short-circuit diff to skip=true immediately; open/none
    with a real diff propagate pr-state and skip=false.
    """
    failures = []
    for guard_state in ("merged", "closed"):
        repo, base_sha = make_repo(root, 1, 0, 1)
        work = os.path.dirname(repo)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls = new_stub_dir(work)
        rc, out, outputs, _ = run_diff(steps, repo, work, bindir, calls,
                                       runner_temp, guard_state)
        if rc != 0:
            failures.append(f"diff({guard_state}): exited {rc}: {out.strip()}")
            continue
        if outputs.get("skip") != "true":
            failures.append(f"diff({guard_state}): expected skip=true, got "
                            f"{outputs.get('skip')!r} — a merged/closed PR "
                            f"must never reach the refresh/create steps.")
        if outputs.get("pr-state") != guard_state:
            failures.append(f"diff({guard_state}): pr-state not passed "
                            f"through: {outputs.get('pr-state')!r}")

    for guard_state in ("none", "open"):
        repo, base_sha = make_repo(root, 1, 0, 1)
        work = os.path.dirname(repo)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls = new_stub_dir(work)
        # Make a real diff against DB by adding a commit on a branch ahead
        # of it — DB itself (main) already differs from HEAD? No: they're
        # the same commit right after seeding, so add one more commit.
        add_fold_commit(repo, work, "leg-0", "a change")
        rc, out, outputs, _ = run_diff(steps, repo, work, bindir, calls,
                                       runner_temp, guard_state)
        if rc != 0:
            failures.append(f"diff({guard_state}): exited {rc}: {out.strip()}")
            continue
        if outputs.get("skip") != "false":
            failures.append(f"diff({guard_state}): expected skip=false "
                            f"given a real diff, got {outputs.get('skip')!r}")
        if outputs.get("pr-state") != guard_state:
            failures.append(f"diff({guard_state}): pr-state not passed "
                            f"through: {outputs.get('pr-state')!r}")
    return failures


def _run_assemble_body(steps, repo, work, bindir, calls, runner_temp,
                       pr_state, prior_body_file=None, reviews_json="[]"):
    env = base_env(work, bindir, calls, runner_temp, {
        "CONVERGED": "true", "COMPARE_LINK": "https://example.invalid/compare",
        "CHANGED_FILES": "tasks.md", "PR_STATE": pr_state,
        "EXISTING_PR": PR_NUMBER, "GH_REVIEWS_JSON": reviews_json,
    })
    if prior_body_file:
        env["GH_PR_BODY_FILE"] = prior_body_file
    with open(os.path.join(runner_temp, "finalize-remaining.md"), "w") as fh:
        fh.write("")
    with open(os.path.join(runner_temp, "finalize-summary.md"), "w") as fh:
        fh.write("This spec closed the fold loop.")
    text = resolve_gh_expressions(steps[BODY_STEP], runner_temp)
    rc, out, outputs, _ = run_step(BASH, text, repo, env, runner_temp)
    body_path = os.path.join(runner_temp, "finalize-pr-body.md")
    body = ""
    if os.path.exists(body_path):
        with open(body_path, encoding="utf-8") as fh:
            body = fh.read()
    return rc, out, body


def scenario_create_path_seeds_region(steps, root):
    """`none`: the region is written fresh with zero fold-log entries."""
    failures = []
    repo, base_sha = make_repo(root, 1, 2, 5)
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_stub_dir(work)
    rc, out, body = _run_assemble_body(steps, repo, work, bindir, calls,
                                       runner_temp, "none")
    if rc != 0:
        failures.append(f"create-path body assembly exited {rc}: {out.strip()}")
        return failures
    if STATE_BEGIN not in body:
        failures.append("create-path body has no machine-owned state region.")
    if "2/5 checked" not in body:
        failures.append(f"create-path body does not state the task count: {body!r}")
    fold_log_span = extract_between(body, FOLDLOG_BEGIN, FOLDLOG_END) or ""
    if fold_log_span.strip():
        failures.append(f"create-path fold log is not empty: {fold_log_span!r}")
    return failures


def scenario_refresh_preserves_and_appends(steps, root):
    """gate-coverage-042.md scenario 1: open PR, one prior fold-log entry, a
    new fold since -> state block regenerated, prose preserved, exactly one
    new entry appended, the prior entry unchanged.
    """
    failures = []
    repo, base_sha = make_repo(root, 2, 3, 5, pending_re_review_from=["alice"])
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_stub_dir(work)

    _, old_short = add_fold_commit(repo, work, "leg-0", "first fold")
    prior_body = (
        "Some human wrote this note before the region.\n\n"
        f"{STATE_BEGIN}\n**Branch**: `x`\n{STATE_END}\n\n"
        f"{FOLDLOG_BEGIN}\n"
        f"- Fold (2026-08-20, review by @alice, #250) {old_short}: 1 item(s) folded — first fold.\n"
        f"{FOLDLOG_END}\n\n"
        f"{NARRATIVE_BEGIN}\nA stale narrative from the prior run.\n{NARRATIVE_END}\n\n"
        "Some human wrote this note after the region.\n"
    )
    prior_body_file = os.path.join(work, "prior-body.md")
    with open(prior_body_file, "w", encoding="utf-8") as fh:
        fh.write(prior_body)

    _, new_short = add_fold_commit(repo, work, "leg-1", "second fold")
    rc, out, body = _run_assemble_body(steps, repo, work, bindir, calls,
                                       runner_temp, "open",
                                       prior_body_file=prior_body_file)
    if rc != 0:
        failures.append(f"refresh body assembly exited {rc}: {out.strip()}")
        return failures
    for needle in ("Some human wrote this note before the region.",
                  "Some human wrote this note after the region."):
        if needle not in body:
            failures.append(f"refresh dropped preserved prose: {needle!r} "
                            f"not found in {body!r}")
    # PR #253 review: the narrative lives INSIDE the region (narrative:begin
    # ... narrative:end), so a refresh must discard the prior run's own
    # narrative, not preserve it alongside a freshly generated one.
    if "A stale narrative from the prior run." in body:
        failures.append("refresh preserved the PRIOR run's narrative instead "
                        f"of discarding it — this is the duplicate-narrative "
                        f"defect PR #253's review caught: {body!r}")
    narrative_span = extract_between(body, NARRATIVE_BEGIN, NARRATIVE_END) or ""
    if not narrative_span.strip():
        failures.append(f"refresh produced an empty narrative region: {body!r}")
    if "3/5 checked" not in body:
        failures.append(f"refresh did not regenerate the state block's task "
                        f"count: {body!r}")
    if f"{old_short}: 1 item(s) folded — first fold." not in body:
        failures.append(f"refresh dropped or altered the prior fold-log "
                        f"entry: {body!r}")
    if f"{new_short}:" not in body:
        failures.append(f"refresh did not append a new fold-log entry for "
                        f"the new fold: {body!r}")
    if "alice" not in body:
        failures.append(f"refresh's new fold-log entry does not name the "
                        f"reviewer from pending_re_review_from: {body!r}")
    fold_log_span = extract_between(body, FOLDLOG_BEGIN, FOLDLOG_END) or ""
    if fold_log_span.count("- Fold (") != 2:
        failures.append(f"expected exactly 2 fold-log entries (1 prior + 1 "
                        f"new), found {fold_log_span.count('- Fold (')}: "
                        f"{fold_log_span!r}")
    return failures


def scenario_idempotent_repeat_refresh(steps, root):
    """gate-coverage-042.md scenario 5: repeat refresh, no intervening fold
    -> no new fold-log entry.
    """
    failures = []
    repo, base_sha = make_repo(root, 2, 3, 5, pending_re_review_from=[])
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_stub_dir(work)

    _, short_sha = add_fold_commit(repo, work, "leg-0", "the only fold")
    rc, out1, body1 = _run_assemble_body(steps, repo, work, bindir, calls,
                                      runner_temp, "none")
    if rc != 0:
        failures.append(f"first assembly exited {rc}: {out1.strip()}")
        return failures
    body1_file = os.path.join(work, "body1.md")
    with open(body1_file, "w", encoding="utf-8") as fh:
        fh.write(body1)

    # Repeat: refresh again with body1 as the prior body, tip unchanged.
    rc, out, body2 = _run_assemble_body(steps, repo, work, bindir, calls,
                                        runner_temp, "open",
                                        prior_body_file=body1_file)
    if rc != 0:
        failures.append(f"repeat assembly exited {rc}: {out.strip()}")
        return failures

    # PR #253 review: assert the narrative appears exactly once, not once
    # per refresh — the exact shape of the duplicate-narrative defect
    # (narrative sat outside the region, so "preserve everything outside"
    # kept the prior run's copy and a fresh one was appended below it).
    body2_file = os.path.join(work, "body2.md")
    with open(body2_file, "w", encoding="utf-8") as fh:
        fh.write(body2)
    rc, out, body3 = _run_assemble_body(steps, repo, work, bindir, calls,
                                        runner_temp, "open",
                                        prior_body_file=body2_file)
    if rc != 0:
        failures.append(f"second repeat assembly exited {rc}: {out.strip()}")
        return failures
    for label, body in (("first refresh", body2), ("second refresh", body3)):
        how_count = body.count("## How to see it")
        if how_count != 1:
            failures.append(f"{label}: narrative appears {how_count} time(s) "
                            f"(expected exactly 1) — {body!r}")
        narrative_count = body.count(NARRATIVE_BEGIN)
        if narrative_count != 1:
            failures.append(f"{label}: {narrative_count} narrative:begin "
                            f"marker(s) found (expected exactly 1) — {body!r}")

    fold_log_span = extract_between(body2, FOLDLOG_BEGIN, FOLDLOG_END) or ""
    count = fold_log_span.count("- Fold (")
    if count != 1:
        failures.append(f"repeat refresh with no intervening fold produced "
                        f"{count} fold-log entries, expected 1 (no "
                        f"duplicate): {fold_log_span!r}")
    return failures


def scenario_pr_open_or_update(steps, root):
    """T023: `none` creates, `open` edits — never both."""
    failures = []
    for pr_state, expect_call in (("none", "create"), ("open", "edit")):
        repo, base_sha = make_repo(root, 1, 0, 1)
        work = os.path.dirname(repo)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls = new_stub_dir(work)
        with open(os.path.join(runner_temp, "finalize-pr-body.md"), "w") as fh:
            fh.write("body")
        text = resolve_gh_expressions(steps[PR_STEP], runner_temp)
        env = base_env(work, bindir, calls, runner_temp, {
            "TITLE": "Test", "PR_STATE": pr_state, "EXISTING_PR": PR_NUMBER})
        rc, out, _, _ = run_step(BASH, text, repo, env, runner_temp)
        if rc != 0:
            failures.append(f"pr-step({pr_state}) exited {rc}: {out.strip()}")
            continue
        if gh_call_count(calls, f"pr {expect_call}") != 1:
            failures.append(f"pr-step({pr_state}): expected exactly one "
                            f"'gh pr {expect_call}' call.")
        other = "create" if expect_call == "edit" else "edit"
        if gh_call_count(calls, f"pr {other}") != 0:
            failures.append(f"pr-step({pr_state}): unexpectedly called "
                            f"'gh pr {other}' too — FR-010's one-PR-per-spec "
                            f"guard depends on only `none` ever creating.")
    return failures


def scenario_re_review_request(steps, root):
    """FR-010b: a failed re-review request is stated, not swallowed, and
    does not fail the job; a successful one issues exactly one call.
    """
    failures = []
    for add_reviewer_exit, expect_failed in ((0, False), (1, True)):
        repo, base_sha = make_repo(root, 1, 0, 1,
                                   pending_re_review_from=["bob", "carol"])
        work = os.path.dirname(repo)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls = new_stub_dir(work)
        env = base_env(work, bindir, calls, runner_temp, {
            "EXISTING_PR": PR_NUMBER,
            "GH_ADD_REVIEWER_EXIT": str(add_reviewer_exit)})
        rc, out, outputs, _ = run_step(BASH, steps[REREVIEW_STEP], repo, env,
                                       runner_temp)
        if rc != 0:
            failures.append(f"re-review(exit={add_reviewer_exit}) exited "
                            f"{rc}: {out.strip()}")
            continue
        if (outputs.get("failed") == "true") != expect_failed:
            failures.append(f"re-review(exit={add_reviewer_exit}): expected "
                            f"failed={expect_failed}, got "
                            f"{outputs.get('failed')!r}")
        if "bob" not in (outputs.get("logins") or "") or \
                "carol" not in (outputs.get("logins") or ""):
            failures.append(f"re-review(exit={add_reviewer_exit}): logins "
                            f"output does not name both reviewers: "
                            f"{outputs.get('logins')!r}")
        if gh_call_count(calls, "pr", "edit", "--add-reviewer") != 1:
            failures.append(f"re-review(exit={add_reviewer_exit}): expected "
                            f"exactly one add-reviewer call.")
    return failures


def scenario_metadata_commit_idempotent(steps, root):
    """The metadata commit clears pending_re_review_from and never fails on
    a repeat run where there is nothing left to commit (FR-010a).
    """
    failures = []
    repo, base_sha = make_repo(root, 1, 0, 1,
                               pending_re_review_from=["dave"])
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_stub_dir(work)
    env = base_env(work, bindir, calls, runner_temp,
                   {"BOT_SLUG": "wing-commander-bot"})
    rc, out, _, _ = run_step(BASH, steps[METADATA_STEP], repo, env, runner_temp)
    if rc != 0:
        failures.append(f"metadata commit (first run) exited {rc}: {out.strip()}")
        return failures
    proc = sh(f"cd '{repo}' && git log -1 --format=%s", work)
    if "review" not in proc.stdout:
        failures.append(f"metadata commit message does not mention the "
                        f"stage transition: {proc.stdout!r}")

    # Repeat: nothing changed (stage already review, field already []).
    rc, out, _, _ = run_step(BASH, steps[METADATA_STEP], repo, env, runner_temp)
    if rc != 0:
        failures.append(f"metadata commit (repeat, nothing to commit) "
                        f"exited {rc}: {out.strip()} — FR-010a requires this "
                        f"to be a safe no-op, not a failure.")
    return failures


def scenario_foldlog_sha_extraction_ignores_prose_hex(steps, root):
    """PR #253 review: last_recorded_sha must be read from the last entry's
    own structured field, not a free-text scan of the whole fold log — an
    agent-authored summary can embed an unrelated hex-looking token, which a
    naive `grep -oE '[0-9a-f]{7,40}'` picks up as "last" and derives the
    wrong range_start, silently dropping the next cycle's fold-log entry.
    """
    failures = []
    repo, base_sha = make_repo(root, 2, 3, 5, pending_re_review_from=[])
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = new_stub_dir(work)

    _, old_short = add_fold_commit(repo, work, "leg-0", "first fold")
    # The summary embeds a spurious hex-looking token AFTER the real
    # short-sha on the same line — exactly the shape a free-text grep over
    # the whole file cannot tell apart from the real one.
    prior_body = (
        f"{STATE_BEGIN}\n**Branch**: `x`\n{STATE_END}\n\n"
        f"{FOLDLOG_BEGIN}\n"
        f"- Fold (2026-08-20, review by @alice, #250) {old_short}: 1 item(s) "
        f"folded — merged into deadbeef1 for compatibility.\n"
        f"{FOLDLOG_END}\n\n"
        f"{NARRATIVE_BEGIN}\nprior narrative\n{NARRATIVE_END}\n"
    )
    prior_body_file = os.path.join(work, "prior-body.md")
    with open(prior_body_file, "w", encoding="utf-8") as fh:
        fh.write(prior_body)

    _, new_short = add_fold_commit(repo, work, "leg-1", "second fold")
    rc, out, body = _run_assemble_body(steps, repo, work, bindir, calls,
                                       runner_temp, "open",
                                       prior_body_file=prior_body_file)
    if rc != 0:
        failures.append(f"refresh body assembly exited {rc}: {out.strip()}")
        return failures
    fold_log_span = extract_between(body, FOLDLOG_BEGIN, FOLDLOG_END) or ""
    count = fold_log_span.count("- Fold (")
    if count != 2:
        failures.append(f"a spurious hex token in the prior entry's own "
                        f"summary caused the new fold to go unrecorded: "
                        f"expected 2 fold-log entries (1 prior + 1 new), "
                        f"found {count}: {fold_log_span!r}")
    if f"{new_short}:" not in body:
        failures.append(f"no fold-log entry for the new fold "
                        f"({new_short}) — the spurious hex token "
                        f"'deadbeef1' in the prior entry's summary was "
                        f"picked as last_recorded_sha instead of the real "
                        f"{old_short!r}: {body!r}")
    return failures


def test_structural():
    """Reachability of the merged/closed report steps, which delegate to a
    composite action this harness cannot execute directly (see module
    docstring) — the same class of static check Gate 15 uses.
    """
    failures = []
    merged_step = find_step(STAGE, REPORT_MERGED_STEP)
    if "pr-state == 'merged'" not in (merged_step.get("if") or ""):
        failures.append(f"structural: {REPORT_MERGED_STEP!r}'s `if:` does "
                        f"not gate on pr-state == 'merged'.")
    closed_step = find_step(STAGE, REPORT_CLOSED_STEP)
    if "pr-state == 'closed'" not in (closed_step.get("if") or ""):
        failures.append(f"structural: {REPORT_CLOSED_STEP!r}'s `if:` does "
                        f"not gate on pr-state == 'closed'.")

    doc = yaml.safe_load(open(STAGE, encoding="utf-8")) or {}
    finalize_job = (doc.get("jobs") or {}).get("finalize") or {}
    refresh_steps = ("Assemble PR body", PR_STEP, "Flip stage label",
                     METADATA_STEP, "Announce the implementation PR for review",
                     "Check for remaining manual work")
    for step in finalize_job.get("steps") or []:
        if step.get("name") in refresh_steps:
            cond = step.get("if") or ""
            if "steps.diff.outputs.skip" not in cond:
                failures.append(f"structural: {step.get('name')!r} no "
                                f"longer gates on steps.diff.outputs.skip — "
                                f"a merged/closed PR could now reach it.")
    return failures


SCENARIOS = [
    scenario_guard_tri_state,
    scenario_diff_propagation,
    scenario_create_path_seeds_region,
    scenario_refresh_preserves_and_appends,
    scenario_idempotent_repeat_refresh,
    scenario_foldlog_sha_extraction_ignores_prose_hex,
    scenario_pr_open_or_update,
    scenario_re_review_request,
    scenario_metadata_commit_idempotent,
]


def suite(steps, root):
    return [f for fn in SCENARIOS for f in fn(steps, root)]


# ------------------------------------------------------------------ mutations

def _mut_revert_d7_boolean_skip(steps):
    """Collapses the tri-state guard back toward a boolean — an OPEN PR is
    now (incorrectly) classified the same as a done one, so it is never
    refreshed, matching the pre-feature "any existing PR means skip"
    defect.
    """
    steps[GUARD_STEP] = steps[GUARD_STEP].replace(
        "OPEN) pr_state=open ;;", "OPEN) pr_state=merged ;;")


def _mut_revert_d9_full_overwrite(steps):
    """Stops preserving prose outside the delimited region — always writes
    the region fresh, discarding whatever the existing body held.
    """
    steps[BODY_STEP] = steps[BODY_STEP].replace(
        'if grep -q \'<!-- wing-commander-finalize:state:begin -->\' "$prior_body_file" 2>/dev/null; then',
        'if false; then')


def _mut_revert_d9a_always_append(steps):
    """Removes the SHA-keyed idempotency check AND its range consequence —
    appends a new fold-log entry every run regardless of whether the tip
    changed, always counting from $DB rather than the last recorded entry
    (dropping only the `if` guard would leave the range computation's own
    emptiness as an accidental second guard, masking this mutation).
    """
    steps[BODY_STEP] = steps[BODY_STEP].replace(
        'if [ "$last_recorded_sha" != "$short_sha" ]; then', 'if true; then'
    ).replace(
        'range_start="$last_recorded_sha"', 'range_start="$DB"')


def _mut_remove_merged_closed_guard(steps):
    """The diff step stops short-circuiting for merged/closed — a merged
    or closed PR would reach the refresh/create steps.
    """
    steps[DIFF_STEP] = steps[DIFF_STEP].replace(
        'if [ "$GUARD_PR_STATE" = "merged" ] || [ "$GUARD_PR_STATE" = "closed" ]; then',
        'if false; then')


MUTATIONS = [
    ("D7 reverted: boolean skip restored", _mut_revert_d7_boolean_skip,
    scenario_guard_tri_state),
    ("D9 reverted: full-body overwrite", _mut_revert_d9_full_overwrite,
    scenario_refresh_preserves_and_appends),
    ("D9a reverted: always append", _mut_revert_d9a_always_append,
    scenario_idempotent_repeat_refresh),
    ("merged/closed guard removed from diff", _mut_remove_merged_closed_guard,
    scenario_diff_propagation),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped steps under test "
                 "commit and push, so nothing here can run without it.")

    failures = list(test_structural())
    steps = load_steps()
    root = tempfile.mkdtemp()
    try:
        behavioral_failures = suite(steps, root)
        failures.extend(behavioral_failures)
        for f in behavioral_failures:
            print(f"::error::{f}")

        for label, apply_mutation, scenario_fn in MUTATIONS:
            mutated = copy.deepcopy(steps)
            apply_mutation(mutated)
            if mutated == steps:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if scenario_fn(mutated, root):
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing this gate checks. Fix the scenarios, "
                      f"not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        if VERBOSE:
            print(f"::error::{f}")

    print(f"Gate 35: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
