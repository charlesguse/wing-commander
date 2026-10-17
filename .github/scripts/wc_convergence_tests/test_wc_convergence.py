"""Unit tests for wc_convergence (spec 116). Run: python3 -I -m unittest discover -s .github/scripts/wc_convergence_tests"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wc_convergence as wc  # noqa: E402


def rnd(n, count, attributable=None, self_inflicted=0, churn=0, growth=0.0,
        recurrences=(), unattributable=0):
    return {"round": n, "count": count,
            "attributable": count - unattributable if attributable is None else attributable,
            "self_inflicted": self_inflicted, "unattributable": unattributable,
            "churn": churn, "growth": growth, "recurrences": list(recurrences)}


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


class DecideRules(unittest.TestCase):
    def test_empty_before_round_three(self):
        d = wc.decide([rnd(1, 4), rnd(2, 4, self_inflicted=4, churn=3, growth=2.0)])
        self.assertEqual(d["tripped"], [])
        self.assertFalse(d["stop"])
        self.assertEqual(len(d["signals"]), 2)

    def test_round_one_signals_zero(self):
        s = wc.decide([rnd(1, 3, self_inflicted=3, churn=5, growth=9.0)])["signals"][0]
        self.assertEqual((s["self_inflicted_share"], s["churn"], s["growth"]), (0.0, 0, 0.0))

    def test_count_not_falling(self):
        d = wc.decide([rnd(1, 3), rnd(2, 2), rnd(3, 2)])
        self.assertEqual(d["tripped"], ["count-not-falling"])
        self.assertEqual(d["reason"], "not-converging")

    def test_falling_count_clean(self):
        self.assertFalse(wc.decide([rnd(1, 4), rnd(2, 3), rnd(3, 2)])["stop"])

    def test_self_inflicted_half(self):
        d = wc.decide([rnd(1, 4), rnd(2, 3), rnd(3, 2, self_inflicted=1)])
        self.assertEqual(d["tripped"], ["self-inflicted"])

    def test_self_inflicted_below_half(self):
        d = wc.decide([rnd(1, 5), rnd(2, 4), rnd(3, 3, self_inflicted=1)])
        self.assertFalse(d["stop"])

    def test_unattributable_excluded_from_share(self):
        # 1 attributable, 0 self-inflicted, 2 unattributable: share 0, not tripped.
        d = wc.decide([rnd(1, 5), rnd(2, 4), rnd(3, 3, attributable=1, unattributable=2)])
        self.assertEqual(d["signals"][-1]["self_inflicted_share"], 0.0)
        self.assertFalse(d["stop"])
        self.assertEqual(d["signals"][-1]["unattributable"], 2)

    def test_no_attributable_share_is_none(self):
        d = wc.decide([rnd(1, 5), rnd(2, 4), rnd(3, 3, attributable=0, unattributable=3)])
        self.assertIsNone(d["signals"][-1]["self_inflicted_share"])
        self.assertFalse(d["stop"])

    def test_recurrence(self):
        d = wc.decide([rnd(1, 3), rnd(2, 2), rnd(3, 1, recurrences=["fp"])])
        self.assertEqual(d["tripped"], ["recurrence"])

    def test_churn_streak_needs_two_rounds(self):
        self.assertEqual(wc.decide([rnd(1, 4), rnd(2, 3, churn=1), rnd(3, 2, churn=2)])["tripped"],
                         ["churn-streak"])
        self.assertFalse(wc.decide([rnd(1, 4), rnd(2, 3), rnd(3, 2, churn=2)])["stop"])

    def test_growth_over_half(self):
        self.assertEqual(wc.decide([rnd(1, 4), rnd(2, 3), rnd(3, 2, growth=0.51)])["tripped"],
                         ["growth"])
        self.assertFalse(wc.decide([rnd(1, 4), rnd(2, 3), rnd(3, 2, growth=0.5)])["stop"])

    def test_zero_findings_round_converged(self):
        self.assertFalse(wc.decide([rnd(1, 3), rnd(2, 1), rnd(3, 0)])["stop"])

    def test_handoff_marker_and_table(self):
        d = wc.decide([rnd(1, 3), rnd(2, 3), rnd(3, 3, unattributable=1)])
        d["open_findings"] = [{"file": "a.py", "line": 2, "fingerprint": "fp"}]
        text = wc.render_handoff(d)
        self.assertIn("<!-- wing-commander-not-converging: round=3 -->", text)
        self.assertIn("count-not-falling", text)
        self.assertIn("Unattributable findings: 1", text)
        self.assertIn("`a.py:2`", text)


class Recurrence(unittest.TestCase):
    def test_match_and_fresh(self):
        fresh, rec = wc.classify_recurrence(
            [{"fingerprint": "a"}, {"fingerprint": "b"}], {"resolved": {"a": 2}})
        self.assertEqual([f["fingerprint"] for f in fresh], ["b"])
        self.assertEqual([f["fingerprint"] for f in rec], ["a"])

    def test_dismissed_never_matches(self):
        fresh, rec = wc.classify_recurrence(
            [{"fingerprint": "a"}], {"resolved": {"a": 2}, "dismissed": ["a"]})
        self.assertEqual((len(fresh), len(rec)), (1, 0))

    def test_replay_833(self):
        data = fixture("replay-833.json")
        _, rec = wc.classify_recurrence(data["round3_findings"], data["ledger"])
        self.assertEqual(len(rec), 1)
        fresh, rec = wc.classify_recurrence(fixture("fresh-only.json")["findings"],
                                            data["ledger"])
        self.assertEqual((len(fresh), len(rec)), (2, 0))

    def test_replays_stop_by_round_three(self):
        for name in ("replay-954.json", "replay-969.json"):
            history = fixture(name)["history"]
            d = wc.decide(history[:3])
            self.assertTrue(d["stop"], name)


class GitBacked(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_git(self, *args):
        wc.git(list(args), self.repo)

    def write(self, text, name="f.py"):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, message):
        self.run_git("add", "-A")
        self.run_git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                     "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)
        return wc.rev("HEAD", self.repo)

    def build(self):
        self.run_git("init", "-q", "-b", "main")
        self.write("a\nb\nc\n")
        base = self.commit("main")
        self.run_git("checkout", "-q", "-b", "pr")
        self.write("a\nb\nc\npr1\npr2\n")
        h0 = self.commit("pr")
        self.write("a\nb\nc\npr1-fixed\npr2\nfix1\n")
        h1 = self.commit("pass 1")
        self.write("a\nb\nc\npr1-fixed\npr2\nfix1-refixed\nfix2\n")
        h2 = self.commit("pass 2")
        return base, h0, h1, h2

    def test_validate_line(self):
        _, h0, _, _ = self.build()
        self.assertTrue(wc.validate_line("f.py", 5, h0, self.repo))
        self.assertFalse(wc.validate_line("f.py", 6, h0, self.repo))
        self.assertFalse(wc.validate_line("f.py", 0, h0, self.repo))
        self.assertFalse(wc.validate_line("f.py", None, h0, self.repo))
        self.assertFalse(wc.validate_line("f.py", True, h0, self.repo))
        self.assertFalse(wc.validate_line("nope.py", 1, h0, self.repo))

    def test_measure_matches_skill_self_test(self):
        base, h0, h1, h2 = self.build()
        report = wc.measure(base, [h0, h1, h2], ["f.py:4", "f.py:6", "f.py:5", "f.py:2"],
                            self.repo, [2, 1])
        self.assertEqual([f["origin"] for f in report["findings"]],
                         ["pass1", "pass1", "pr", "main"])
        self.assertEqual(report["self_inflicted"], {"count": 2, "of": 4})
        self.assertEqual([c["total"] for c in report["churn"]], [0, 1])
        self.assertEqual([g["lines"] for g in report["growth"]], [2, 3, 4])
        self.assertEqual(report["warnings"], [])

    def test_main_merge_is_not_loop_written(self):
        base, h0, _, _ = self.build()
        self.run_git("checkout", "-q", "-b", "newer", base)
        self.write("m1\n", "m.py")
        newer = self.commit("main moves")
        self.run_git("checkout", "-q", "-b", "merged", h0)
        self.run_git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                     "merge", "-q", "--no-edit", newer)
        merged = wc.rev("HEAD", self.repo)
        history = wc.compute_history(newer, [
            {"round": 1, "head_sha": h0, "findings": []},
            {"round": 2, "head_sha": merged,
             "findings": [{"fingerprint": "x", "file": "m.py", "line": 1}]}], None, self.repo)
        self.assertEqual(history[1]["self_inflicted"], 0)
        self.assertEqual(history[1]["attributable"], 1)

    def test_compute_history_unattributable_and_recurrence(self):
        base, h0, h1, h2 = self.build()
        rounds = [
            {"round": 1, "head_sha": h0, "findings": [{"fingerprint": "a", "file": "f.py", "line": 4}]},
            {"round": 2, "head_sha": h1, "findings": [
                {"fingerprint": "b", "file": "f.py", "line": 6},
                {"fingerprint": "c", "file": "f.py", "line": 99},
                {"fingerprint": "d", "file": "f.py"}]},
            {"round": 3, "head_sha": h2, "findings": [{"fingerprint": "a", "file": "f.py", "line": 6}]},
        ]
        history = wc.compute_history(base, rounds, {"resolved": {"a": 1}}, self.repo)
        self.assertEqual(history[0]["recurrences"], [])
        self.assertEqual((history[1]["attributable"], history[1]["unattributable"]), (1, 2))
        self.assertEqual(history[1]["self_inflicted"], 1)
        self.assertEqual(history[2]["recurrences"], ["a"])
        self.assertEqual(history[1]["churn"], 0)
        self.assertEqual(history[2]["churn"], 1)
        self.assertTrue(wc.decide(history)["stop"])


if __name__ == "__main__":
    unittest.main()
