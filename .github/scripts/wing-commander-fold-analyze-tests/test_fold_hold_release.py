"""Fixture tests for fold-hold.yml's release job: its own shipped run:
blocks, run against a fake `gh` serving the lifecycle issue's comments and
recording what the job posts. Entry point: run-tests.sh beside this file."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "fold-hold.yml")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))
import wc_fold_hold  # noqa: E402

BOT = {"login": "wc[bot]", "type": "Bot"}


def job(name):
    with open(WORKFLOW, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["jobs"][name]


def release_step(name, job_name="release"):
    return next(s for s in job(job_name)["steps"] if s.get("name") == name)


def hold(fold_id, stamp):
    return {"body": "q\n\n" + wc_fold_hold.render_state(fold_id=fold_id, reason="constitution-conflict"),
            "created_at": stamp, "user": BOT}


class FoldHoldModule(unittest.TestCase):
    def test_an_answer_line_ending_in_crlf_is_read(self):
        # The web UI sends CRLF: an answer followed by another line.
        comments = [hold("f1", "2026-01-01T00:00:00Z")]
        r = wc_fold_hold.resolve(comments, BOT["login"], "/fold-hold proceed\r\nThanks", "OWNER")
        self.assertEqual(r["action"], "proceed")

    def test_a_dropped_folds_fingerprints_are_dismissed(self):
        # The owner's decision on F2 of #1062's pass-6 review.
        def state(fold_id, fps, stamp):
            folded = wc_fold_hold.with_fingerprints('[{{"id":"{0}","summary":"s"}}]'.format(fold_id), fps)
            return {"body": "q\n\n" + wc_fold_hold.render_state(
                fold_id=fold_id, reason="constitution-conflict", folded_json=folded),
                "created_at": stamp, "user": BOT}

        def resolved(fold_id, resolution, stamp, user=BOT):
            return {"body": wc_fold_hold.render_resolved(fold_id, resolution),
                    "created_at": stamp, "user": user}

        comments = [state("fd", "aa,bb", "2026-01-01T00:00:00Z"),
                    state("fk", "cc", "2026-01-01T00:00:01Z"),
                    resolved("fd", "drop", "2026-01-02T00:00:00Z"),
                    resolved("fk", "proceed", "2026-01-02T00:00:01Z"),
                    resolved("fk", "drop", "2026-01-03T00:00:00Z", {"login": "x", "type": "User"})]
        self.assertEqual(wc_fold_hold.dropped_fingerprints(comments, BOT["login"]), ["aa", "bb"])
        self.assertEqual(wc_fold_hold.dropped_fingerprints(comments[:2], BOT["login"]), [])


class ReleaseSteps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.symlink(ROOT, os.path.join(self.tmp, ".wing-commander-pipeline"))
        self.bindir = os.path.join(self.tmp, "bin")
        os.makedirs(self.bindir)
        self.posted = os.path.join(self.tmp, "posted.md")
        self.served = os.path.join(self.tmp, "served.json")
        with open(os.path.join(self.bindir, "gh"), "w", encoding="utf-8") as fh:
            fh.write('#!/usr/bin/env bash\n'
                     'if [ "$1" = api ]; then jq -c ".[]" "{0}"; exit 0; fi\n'
                     'while [ $# -gt 0 ]; do\n'
                     '  if [ "$1" = --body-file ]; then cat "$2" >> "{1}"; fi\n'
                     '  shift\n'
                     'done\n'.format(self.served, self.posted))
        os.chmod(os.path.join(self.bindir, "gh"), 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_step(self, name, env, comments=(), job_name="release"):
        with open(self.served, "w", encoding="utf-8") as fh:
            json.dump(list(comments), fh)
        out = os.path.join(self.tmp, "github-output")
        open(out, "w").close()
        full = dict(os.environ, GITHUB_OUTPUT=out, RUNNER_TEMP=self.tmp, GH_TOKEN="t",
                    GITHUB_REPOSITORY="o/r", ISSUE="7", BOT_LOGIN="wc[bot]",
                    PATH=self.bindir + os.pathsep + os.environ["PATH"], **env)
        proc = subprocess.run(["bash", "-e", "-c", release_step(name, job_name)["run"]], cwd=self.tmp,
                              env=full, capture_output=True, text=True)
        return proc

    def posted_text(self):
        if not os.path.isfile(self.posted):
            return ""
        with open(self.posted, encoding="utf-8") as fh:
            return fh.read()

    def recheck(self, comments, fold_id="fa"):
        env = {"BODY": "/fold-hold proceed", "ASSOCIATION": "OWNER",
               "ACTION": "proceed", "FOLD_ID": fold_id}
        proc = self.run_step("Re-check the hold is still open", env, comments)
        path = os.path.join(self.tmp, "fold-hold-not-applied.md")
        text = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        return proc, text

    def explain(self, drop_outcome=""):
        return self.run_step("Explain an answer the release did not apply",
                             {"ACTION": "drop" if drop_outcome else "proceed", "FOLD_ID": "fa",
                              "DROP_OUTCOME": drop_outcome})

    def test_the_answered_hold_still_open_passes_the_recheck(self):
        proc, text = self.recheck([hold("fa", "2026-01-01T00:00:00Z")])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(text, "")

    def test_a_newer_hold_posted_first_names_it_and_not_a_release(self):
        proc, text = self.recheck([hold("fa", "2026-01-01T00:00:00Z"),
                                   hold("fb", "2026-01-02T00:00:00Z")])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("was no longer the newest -- `fb` is. ", text)
        self.assertNotIn("already released", text)

    def test_an_already_released_hold_says_so(self):
        proc, text = self.recheck([hold("fa", "2026-01-01T00:00:00Z"),
                                   {"body": wc_fold_hold.render_resolved("fa", "proceed"),
                                    "created_at": "2026-01-02T00:00:00Z", "user": BOT}])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already released", text)

    def test_an_unapplied_answer_is_explained_on_the_issue(self):
        self.recheck([hold("fa", "2026-01-01T00:00:00Z"), hold("fb", "2026-01-02T00:00:00Z")])
        proc = self.explain()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("was not applied", self.posted_text())
        self.assertIn("`fb`", self.posted_text())

    def test_a_failed_drop_is_explained_on_the_issue(self):
        proc = self.explain(drop_outcome="failure")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("`/fold-hold drop` was not applied", self.posted_text())
        self.assertIn("still open", self.posted_text())

    def test_the_explanation_runs_on_a_failed_recheck_or_drop(self):
        cond = release_step("Explain an answer the release did not apply")["if"]
        for needle in ("steps.recheck.outcome == 'failure'", "steps.drop.outcome == 'failure'",
                       "!cancelled()"):
            self.assertIn(needle, cond)


    def test_a_failed_dispatch_is_explained_on_the_issue(self):
        cond = release_step("Explain a release that dispatched nothing")["if"]
        for needle in ("steps.fold-dispatch.outcome == 'failure'",
                       "steps.auth-remote.outcome == 'failure'", "!cancelled()"):
            self.assertIn(needle, cond)
        proc = self.run_step("Explain a release that dispatched nothing",
                             {"ACTION": "drop", "FOLD_ID": "fa", "DROPPED": "dropped"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("`/fold-hold drop` was not applied", self.posted_text())
        self.assertIn("still open", self.posted_text())

    def test_a_failed_remote_auth_neither_dispatches_nor_records_the_release(self):
        # The dispatch's fetch fails silently without the credential and
        # exits clean as nothing folded: the release must not be recorded
        # while "Explain a release that dispatched nothing" says it is open.
        for name in ("Dispatch implement for the released fold",
                     "Record the release on the lifecycle issue"):
            cond = " ".join(release_step(name)["if"].split())
            self.assertIn("steps.auth-remote.outcome == 'success'", cond, name)

    def test_a_cancelled_release_says_the_hold_is_still_open(self):
        cond = " ".join(job("release-cancelled")["if"].split())
        self.assertIn("needs.release.result == 'cancelled'", cond)
        self.assertTrue(cond.startswith("always()"), cond)
        proc = self.run_step("Say the cancelled release left the hold open",
                             {"ACTION": "proceed", "FOLD_ID": "fa"}, job_name="release-cancelled")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("`fa`", self.posted_text())
        self.assertIn("still open", self.posted_text())


    def held_reply(self, decision, post_outcome):
        with open(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml"), encoding="utf-8") as fh:
            steps = yaml.safe_load(fh)["jobs"]["dispatch-once"]["steps"]
        run = next(s for s in steps if s.get("name") == "Reply that this review's fold(s) are held")["run"]
        env = dict(os.environ, RUNNER_TEMP=self.tmp, GH_TOKEN="t", PR_NUMBER="3", ISSUE="7",
                   DECISION=decision, HOLD_REASON="constitution-conflict", POST_OUTCOME=post_outcome,
                   PATH=self.bindir + os.pathsep + os.environ["PATH"])
        proc = subprocess.run(["bash", "-e", "-c", run], cwd=self.tmp, env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.posted_text()

    def test_a_held_reply_points_at_a_question_that_was_posted(self):
        self.assertIn("The owner question is on #7", self.held_reply("hold", "success"))

    def test_a_held_reply_whose_question_never_posted_says_so(self):
        text = self.held_reply("hold", "failure")
        self.assertIn("could not be posted", text)
        self.assertNotIn("The owner question is on #7", text)


    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
                              + list(args), cwd=self.tmp, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, name):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
            fh.write(name)
        self.git("add", name)
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD")

    def tasks_commit(self, text):
        os.makedirs(os.path.join(self.tmp, "specs", "001-x"), exist_ok=True)
        with open(os.path.join(self.tmp, "specs", "001-x", "tasks.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def test_a_drop_reverses_only_the_fold_commits_own_diffs(self):
        # The owner's decision on C6 of #1062's pass-8 review: a hand edit
        # (T002) and an implement tick (T001) between two fold commits stay.
        self.git("init", "-q", "-b", "main")
        base = self.tasks_commit("# Tasks\n\n- [ ] T001\n")
        fold_a = self.tasks_commit("# Tasks\n\n- [ ] T001\n\n## Fold A\n\n- [ ] Review finding: a\n")
        self.tasks_commit("# Tasks\n\n- [X] T001\n- [ ] T002 hand edit\n\n## Fold A\n\n"
                          "- [ ] Review finding: a\n")
        fold_b = self.tasks_commit("# Tasks\n\n- [X] T001\n- [ ] T002 hand edit\n\n## Fold A\n\n"
                                   "- [ ] Review finding: a\n\n## Fold B\n\n- [ ] Review finding: b\n")
        folded = json.dumps([{"id": "r/1", "summary": "s", "commit_sha": fold_a},
                             {"id": "r/2", "summary": "s", "commit_sha": fold_b}])
        self.assertTrue(wc_fold_hold.drop_tasks("specs/001-x", base, fold_b, self.tmp, folded))
        with open(os.path.join(self.tmp, "specs", "001-x", "tasks.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# Tasks\n\n- [X] T001\n- [ ] T002 hand edit\n")

    def test_a_drop_that_no_longer_applies_leaves_tasks_md_as_it_was(self):
        self.git("init", "-q", "-b", "main")
        self.tasks_commit("# Tasks\n")
        fold_a = self.tasks_commit("# Tasks\n\n## Fold A\n\n- [ ] a\n")
        fold_b = self.tasks_commit("# Tasks\n\n## Fold A\n\n- [ ] a\n\n## Fold B\n\n- [ ] b\n")
        edited = "# Tasks\n\n## Fold A\n\n- [ ] a, since reworded\n\n## Fold B\n\n- [ ] b\n"
        self.tasks_commit(edited)
        folded = json.dumps([{"id": "r/1", "summary": "s", "commit_sha": fold_a},
                             {"id": "r/2", "summary": "s", "commit_sha": fold_b}])
        with self.assertRaises(SystemExit):
            wc_fold_hold.drop_tasks("specs/001-x", "", "", self.tmp, folded)
        with open(os.path.join(self.tmp, "specs", "001-x", "tasks.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), edited)

    def test_the_drop_step_passes_the_hold_states_fold_commits(self):
        drop = release_step("Drop the held fold's tasks")
        self.assertIn("needs.resolve.outputs.folded-json", drop["env"]["FOLDED_JSON"])
        self.assertIn('--folded-json "$FOLDED_JSON"', drop["run"])

    def test_the_stage_and_the_hold_state_carry_the_rounds_fold_commits(self):
        with open(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml"), encoding="utf-8") as fh:
            jobs = yaml.safe_load(fh)["jobs"]
        stage = next(s for s in jobs["fold-analyze"]["steps"] if s.get("id") == "analyze-stage")
        self.assertIn("round-folded-json", stage["with"]["folded-json"])
        self.assertIn("round-folded-json", jobs["fold-turn-dispatch"]["outputs"]["round-folded-json"].replace(
            "steps.round-folded.outputs.json", "round-folded-json"))
        mapped = next(s for s in jobs["fold-turn-dispatch"]["steps"] if s.get("id") == "round-folded")
        self.assertIn("commit_sha", mapped["run"])
        post = next(s for s in jobs["dispatch-once"]["steps"] if s.get("id") == "analyze-post")
        self.assertIn('--folded-json "${ROUND_FOLDED_JSON:-$FOLDED_JSON}"', post["run"])

if __name__ == "__main__":
    unittest.main()
