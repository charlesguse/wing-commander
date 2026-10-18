"""The two review loops' shipped steps, run against a throwaway repository:
lifecycle-review-gate.yml's `disposition` partition (FR-002, FR-003, FR-006,
SC-001) and board-loop.yml's convergence evaluation, review body and round
decision (FR-003, FR-006, FR-007, FR-009). Each test runs the step's own
`run:` block, never a copy, so a wiring change that drops the recurrence
class or the not-converging stop fails here."""
import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.normpath(os.path.join(SCRIPTS, "..", ".."))
sys.path.insert(0, SCRIPTS)
import wc_convergence as wc  # noqa: E402
from wc_review_finding_fingerprint import fingerprint  # noqa: E402
from wc_shell_harness import find_step, resolve_bash, run_step  # noqa: E402

LIFECYCLE = os.path.join(ROOT, ".github", "workflows", "lifecycle-review-gate.yml")
BOARD = os.path.join(ROOT, ".github", "workflows", "board-loop.yml")
HELPERS = ("wc_convergence.py", "wc_review_finding_fingerprint.py", "board_item_marker.py",
           "board_spec_request_body.py", "wc_lifecycle_review_marker.py", "wc_fold_hold.py")
BOT = "wing-commander-bot[bot]"
ISSUE = "42"
BASH = resolve_bash()


def finding(title, path, line, in_scope=True):
    return {"title": title, "what": "w", "evidence": {"file_paths": [path]},
            "in_scope": in_scope, "line": line,
            "fingerprint_basis": {"file_path": path, "gate_or_artifact": "g"}}


def review(round_, head, entries, stamp):
    return {"body": "review\n\n" + wc.round_record_marker(round_, head, entries),
            "submitted_at": stamp, "user": {"login": BOT, "type": "Bot"}}


def entry(title, path, line):
    return {"fingerprint": fingerprint(ISSUE, title, path), "file": path, "line": line}


class LoopRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.runner_temp = os.path.join(self.tmp.name, "runner")
        os.makedirs(self.repo)
        os.makedirs(self.runner_temp)
        self.git("init", "-q", "-b", "main")
        self.base = self.commit("a\nb\nc\n")
        self.git("checkout", "-q", "-b", "spec/001-x")
        pr = "pr2\npr3\npr4\npr5\npr6\n"
        self.h1 = self.commit("a\nb\nc\npr1\n" + pr)
        self.h2 = self.commit("a\nb\nc\npr1-fixed\n" + pr + "fix1\n")
        self.h3 = self.commit("a\nb\nc\npr1-fixed\n" + pr + "fix1-refixed\nfix2\n")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        for parent in (os.path.join(self.repo, ".wc-pristine-repo", ".github", "scripts"),
                       os.path.join(self.runner_temp, "wc-pristine", "scripts")):
            os.makedirs(parent)
            for helper in HELPERS:
                shutil.copyfile(os.path.join(SCRIPTS, helper), os.path.join(parent, helper))

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
                              + list(args), cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, text):
        with open(os.path.join(self.repo, "f.py"), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", "f.py")
        self.git("commit", "-q", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def write_temp(self, rel, obj):
        path = os.path.join(self.runner_temp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return path

    def run_shipped(self, path, name, env, path_prepend=None):
        rc, out, outputs, _ = run_step(BASH, find_step(path, name)["run"], self.repo, env,
                                       self.runner_temp, path_prepend=path_prepend)
        self.assertEqual(rc, 0, out)
        return outputs


class LifecyclePartition(LoopRepo):
    STEP = "Partition, dedup, and render this round's findings"

    def partition(self, round_, head, findings, reviews, folded=(), filed=(), env=None,
                  issue_comments=()):
        self.write_temp("lifecycle-review-findings-artifact/lifecycle-review-findings.json", findings)
        self.write_temp("lifecycle-pr-reviews.json", reviews)
        self.write_temp("lifecycle-issue-comments.json", list(issue_comments))
        self.git("checkout", "-q", head)
        gate = {"round": round_ - 1, "head_sha": "prev", "outcome": "findings",
                "findings_open": 1, "folded_fingerprints": list(folded),
                "filed_fingerprints": list(filed), "updated_at": None}
        step_env = {
            "ISSUE": ISSUE, "PR_NUMBER": "7", "HEAD_SHA": head, "BOT_LOGIN": BOT,
            "ROUND_BUDGET": "5", "REVIEW_GATE_JSON": json.dumps(gate)}
        step_env.update(env or {})
        return self.run_shipped(LIFECYCLE, self.STEP, step_env)

    def section(self):
        with open(os.path.join(self.runner_temp, "lifecycle-review-fold-section.md"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_a_folded_finding_raised_again_is_a_recurrence_not_clean(self):
        # #833: round 1 folded F; round 2 raises only F. Before spec 116 the
        # round resolved clean and posted success.
        f = finding("F", "f.py", 4)
        out = self.partition(2, self.h2, [f], [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fingerprint(ISSUE, "F", "f.py")])
        self.assertEqual(out["outcome"], "findings")
        self.assertEqual(out["recurrences"], fingerprint(ISSUE, "F", "f.py"))
        self.assertIn("Recurring review finding: F", self.section())

    def test_an_unreadable_tasks_md_still_reports_the_recurrence(self):
        # Reading every folded finding as pending when tasks.md cannot be
        # read would resolve #833's case clean (FR-003, SC-001).
        f = finding("F", "f.py", 4)
        out = self.partition(2, self.h2, [f], [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fingerprint(ISSUE, "F", "f.py")],
                             env={"SPEC_DIR": "specs/missing"})
        self.assertEqual((out["outcome"], out["recurrences"]),
                         ("findings", fingerprint(ISSUE, "F", "f.py")))

    def test_a_fold_still_waiting_in_tasks_md_is_not_a_recurrence(self):
        # A held or blocked fold leaves its task unchecked; the finding
        # re-raised is that fold pending, not a fixed finding coming back.
        os.makedirs(os.path.join(self.repo, "specs", "001-x"))
        with open(os.path.join(self.repo, "specs", "001-x", "tasks.md"), "w", encoding="utf-8") as fh:
            fh.write("- [ ] Review finding: F\n")
        f = finding("F", "f.py", 4)
        out = self.partition(2, self.h2, [f], [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fingerprint(ISSUE, "F", "f.py")],
                             env={"SPEC_DIR": "specs/001-x"})
        self.assertEqual((out["outcome"], out["recurrences"]), ("clean", ""))
        self.assertEqual(self.section(), "")

    def test_a_dropped_folds_finding_raised_again_is_dismissed(self):
        # The owner answered `/fold-hold drop` on round 1's fold: F raised
        # again is neither a recurrence nor folded again (F2, pass 6).
        import wc_fold_hold as fh
        fp = fingerprint(ISSUE, "F", "f.py")
        state = fh.render_state(fold_id="review-gate-round-1", reason="constitution-conflict",
                                folded_json=fh.with_fingerprints(
                                    '[{"id":"review-gate-round-1","summary":"s"}]', fp))
        comments = [{"body": "q\n\n" + state, "created_at": "2026-01-01T00:00:00Z",
                     "user": {"login": BOT, "type": "Bot"}},
                    {"body": fh.render_resolved("review-gate-round-1", "drop"),
                     "created_at": "2026-01-02T00:00:00Z", "user": {"login": BOT, "type": "Bot"}}]
        out = self.partition(2, self.h2, [finding("F", "f.py", 4)],
                             [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fp], issue_comments=comments)
        self.assertEqual((out["outcome"], out["recurrences"], out["fold-fingerprints"]),
                         ("clean", "", ""))
        self.assertEqual(self.section(), "")
        # A proceeded fold dismisses nothing: F recurs.
        comments[1]["body"] = fh.render_resolved("review-gate-round-1", "proceed")
        out = self.partition(2, self.h2, [finding("F", "f.py", 4)],
                             [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fp], issue_comments=comments)
        self.assertEqual((out["outcome"], out["recurrences"]), ("findings", fp))

    def test_fresh_findings_are_unchanged(self):
        out = self.partition(2, self.h2, [finding("G", "f.py", 5)],
                             [review(1, self.h1, [entry("F", "f.py", 4)], "t1")],
                             folded=[fingerprint(ISSUE, "F", "f.py")])
        self.assertEqual((out["outcome"], out["recurrences"]), ("findings", ""))
        self.assertIn("- [ ] Review finding: G", self.section())

    def test_round_three_count_not_falling_stops_not_converging(self):
        out = self.partition(3, self.h3, [finding("H", "f.py", 5)], [
            review(1, self.h1, [entry("A", "f.py", 4), entry("B", "f.py", 5)], "t1"),
            review(2, self.h2, [entry("C", "f.py", 6)], "t2")])
        self.assertEqual((out["outcome"], out["findings-open"]), ("not-converging", "1"))
        self.assertEqual(self.section(), "")
        self.assertNotIn("fold-summary", out)
        decision = json.loads(base64.b64decode(out["convergence-b64"]))
        self.assertTrue(decision["stop"])
        self.assertIn("count-not-falling", decision["tripped"])

    def test_round_three_counts_filed_in_scope_findings_as_its_record_does(self):
        # The review job's round record counts every in-scope finding,
        # filed or not; this round's count must too, or the trend compares
        # two populations (round 2's 2 against this round's 1).
        out = self.partition(3, self.h3, [finding("H", "f.py", 5), finding("X", "f.py", 6)], [
            review(1, self.h1, [entry("A", "f.py", 4), entry("B", "f.py", 5),
                                entry("C", "f.py", 6)], "t1"),
            review(2, self.h2, [entry("D", "f.py", 4), entry("E", "f.py", 5)], "t2")],
            filed=[fingerprint(ISSUE, "X", "f.py")])
        self.assertEqual(out["outcome"], "not-converging")
        decision = json.loads(base64.b64decode(out["convergence-b64"]))
        self.assertIn("count-not-falling", decision["tripped"])

    def test_round_three_with_a_falling_count_on_original_lines_folds(self):
        out = self.partition(3, self.h3, [finding("H", "f.py", 5)], [
            review(1, self.h1, [entry("A", "f.py", 4), entry("B", "f.py", 5),
                                entry("C", "f.py", 6)], "t1"),
            review(2, self.h2, [entry("D", "f.py", 4), entry("E", "f.py", 5)], "t2")])
        self.assertEqual(out["outcome"], "findings")
        self.assertIn("Review finding: H", self.section())


class LifecycleReport(LoopRepo):
    STEP = "Compose and post the round's outcome"

    def post(self, analyze_decision, fold_decide_result="success"):
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir, exist_ok=True)
        sent = os.path.join(self.tmp.name, "sent.txt")
        stub = os.path.join(bindir, "gh")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >> '{0}'\n".format(sent))
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
        self.run_shipped(LIFECYCLE, self.STEP, {
            "GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r", "ISSUE": ISSUE, "PR_NUMBER": "7",
            "HEAD_SHA": self.h2, "REVIEW_RESULT": "success", "PARSE_FAILED": "false",
            "IN_SCOPE_COUNT": "1", "OUT_OF_SCOPE_COUNT": "0", "ROUND": "2",
            "DISPOSITION_RESULT": "success", "DISPOSITION_OUTCOME": "findings",
            "FINDINGS_OPEN": "1", "FOLDED_FINGERPRINTS": "", "FILED_FINGERPRINTS": "",
            "CONVERGENCE_B64": "", "RECURRENCES": "", "ANALYZE_DECISION": analyze_decision,
            "FOLD_DECIDE_RESULT": fold_decide_result,
            "COST_LINE": "", "PATH": bindir + os.pathsep + os.environ["PATH"]},
            path_prepend=bindir)
        with open(sent, encoding="utf-8") as fh:
            return fh.read()

    def test_a_held_fold_is_not_reported_as_re_dispatched(self):
        body = self.post("hold")
        self.assertNotIn("re-dispatched implement", body)
        self.assertIn("held for the owner", body)
        self.assertIn("re-dispatched implement", self.post("dispatch"))

    def test_a_failed_fold_decide_is_not_reported_as_re_dispatched(self):
        body = self.post("dispatch", fold_decide_result="failure")
        self.assertNotIn("re-dispatched implement", body)
        self.assertIn("was not re-dispatched", body)
        self.assertNotIn("re-dispatched implement", self.post("", fold_decide_result="failure"))


class BoardRound(LoopRepo):
    DECIDE = "Decide the round outcome"

    def decide(self, **env):
        base = {"PARSE_FAILED": "false", "IN_SCOPE_COUNT": "2", "DROPPED_COUNT": "0",
                "ROUND": "2", "ROUND_BUDGET": "5"}
        base.update(env)
        return self.run_shipped(BOARD, self.DECIDE, base)

    def test_not_converging_stalls(self):
        out = self.decide(CONVERGENCE_STOP="true")
        self.assertEqual((out["outcome"], out["stall-reason"]), ("stalled", "not-converging"))

    def test_budget_still_wins(self):
        out = self.decide(ROUND="5", CONVERGENCE_STOP="true")
        self.assertEqual(out["stall-reason"], "budget-spent")
        self.assertEqual(self.decide(ROUND="5", CONVERGENCE_STOP="false")["stall-reason"],
                         "budget-spent")

    def test_continue_without_a_stop_and_converged_without_findings(self):
        self.assertEqual(self.decide(CONVERGENCE_STOP="false")["outcome"], "continue")
        self.assertEqual(self.decide(CONVERGENCE_STOP="")["outcome"], "continue")
        self.assertEqual(self.decide(IN_SCOPE_COUNT="0", CONVERGENCE_STOP="true")["outcome"],
                         "converged")

    def gh_stub(self, reviews):
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir, exist_ok=True)
        data = os.path.join(self.tmp.name, "reviews.jsonl")
        with open(data, "w", encoding="utf-8") as fh:
            for r in reviews:
                fh.write(json.dumps(r) + "\n")
        stub = os.path.join(bindir, "gh")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\ncat '{0}'\n".format(data))
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
        return bindir

    def test_evaluate_step_and_review_body(self):
        # Round index 2 is the third review: its count did not fall, and
        # it re-raises a finding round index 0's review-fixup fixed.
        self.git("checkout", "-q", self.h3)
        bindir = self.gh_stub([
            review(1, self.h1, [entry("A", "f.py", 4), entry("B", "f.py", 5)], "t1"),
            review(2, self.h2, [entry("C", "f.py", 6)], "t2")])
        self.write_temp("board-review-findings.json", [finding("A", "f.py", 5)])
        out = self.run_shipped(BOARD, "Evaluate this round's convergence", {
            "GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r", "PR_NUMBER": "7", "ISSUE_NUMBER": ISSUE,
            "ROUND": "2", "ROUND_BUDGET": "5", "HEAD_SHA": self.h3, "BOT_LOGIN": BOT,
            "PATH": bindir + os.pathsep + os.environ["PATH"]}, path_prepend=bindir)
        self.assertEqual((out["stop"], out["reason"]), ("true", "not-converging"))
        self.assertEqual(out["recurrences"], "1")
        self.assertIn("recurrence", out["tripped"])

        self.run_shipped(BOARD, "Compose the review body", {
            "PARSE_FAILED": "false", "DROPPED_COUNT": "0", "ISSUE_NUMBER": ISSUE,
            "ROUND": "2", "HEAD_SHA": self.h3})
        with open(os.path.join(self.runner_temp, "board-review-body.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("Recurring findings", body)
        records = wc.read_round_records([{"body": body, "user": {"login": BOT, "type": "Bot"}}], BOT)
        self.assertEqual([(r["round"], r["head_sha"]) for r in records], [(3, self.h3)])


if __name__ == "__main__":
    unittest.main()
