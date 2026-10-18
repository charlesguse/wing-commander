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
        self.assertIn("`fb` is", text)
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

    def earliest_base(self, base, commits):
        with open(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml"), encoding="utf-8") as fh:
            steps = yaml.safe_load(fh)["jobs"]["fold-analyze"]["steps"]
        run = next(s for s in steps if s.get("id") == "analyze-base")["run"]
        out = os.path.join(self.tmp, "github-output")
        open(out, "w").close()
        env = dict(os.environ, GITHUB_OUTPUT=out, BASE_SHA=base, ROUND_FOLDED_JSON=json.dumps(
            [{"id": "r/{0}".format(i), "summary": "s", "commit_sha": c} for i, c in enumerate(commits)]))
        proc = subprocess.run(["bash", "-e", "-c", run], cwd=self.tmp, env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out, encoding="utf-8") as fh:
            return fh.read().strip().split("=", 1)[1]

    def test_the_analyzed_range_starts_before_the_rounds_earliest_fold(self):
        self.git("init", "-q")
        root = self.commit("root")
        fold_a = self.commit("fold-a")
        base_b = self.commit("unrelated")
        fold_b = self.commit("fold-b")
        # Run B's classify read base_b, after run A's fold landed: A's fold
        # is analyzed too, from its parent.
        self.assertEqual(self.earliest_base(base_b, [fold_a, fold_b]), root)
        # Folds all after base-sha leave it alone.
        self.assertEqual(self.earliest_base(base_b, [fold_b]), base_b)
        # A commit the fetch cannot see leaves base-sha.
        self.assertEqual(self.earliest_base(base_b, ["0" * 40, ""]), base_b)

    def test_the_stage_and_the_hold_state_use_that_range(self):
        with open(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml"), encoding="utf-8") as fh:
            jobs = yaml.safe_load(fh)["jobs"]
        stage = next(s for s in jobs["fold-analyze"]["steps"] if s.get("id") == "analyze-stage")
        self.assertIn("steps.analyze-base.outputs.before", stage["with"]["fold-ref-before"])
        post = next(s for s in jobs["dispatch-once"]["steps"] if s.get("id") == "analyze-post")
        self.assertIn("needs.fold-analyze.outputs.fold-ref-before", post["env"]["FOLD_BEFORE"])
        self.assertIn('--fold-ref-before "$FOLD_BEFORE"', post["run"])


if __name__ == "__main__":
    unittest.main()
