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


class RuleFixtures(unittest.TestCase):
    """One checked-in history per FR-006 rule and acceptance scenario
    (fixtures/rules/), each with the decision it must produce."""

    def test_every_rule_fixture(self):
        rules = os.path.join(HERE, "fixtures", "rules")
        names = sorted(n for n in os.listdir(rules) if n.endswith(".json"))
        self.assertGreaterEqual(len(names), 9)
        for name in names:
            with open(os.path.join(rules, name), encoding="utf-8") as fh:
                data = json.load(fh)
            d = wc.decide(data["history"], budget=data.get("budget"))
            got = {"stop": d["stop"], "reason": d["reason"], "tripped": d["tripped"]}
            self.assertEqual(got, data["expect"], name)

    def test_handoff_names_the_budget_and_still_lists_signals(self):
        with open(os.path.join(HERE, "fixtures", "rules", "s8-budget-round-names-budget.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
        text = wc.render_handoff(wc.decide(data["history"], budget=data["budget"]))
        self.assertIn("round budget is spent", text)
        self.assertIn("Tripped: count-not-falling", text)

    def test_handoff_without_a_trip_is_not_a_not_converging_stop(self):
        # The board loop's budget-spent stall embeds this hand-off whether
        # or not a rule tripped; without a trip it must not claim one.
        with open(os.path.join(HERE, "fixtures", "rules", "s9-budget-round-without-trip.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
        text = wc.render_handoff(wc.decide(data["history"], budget=data["budget"]))
        self.assertNotIn("wing-commander-not-converging", text)
        self.assertNotIn("not converging", text)
        self.assertIn("no rule tripped", text)

    def test_handoff_path_cannot_forge_a_fold_hold_marker(self):
        # The hand-off is posted under the App's identity on the lifecycle
        # issue, where wc_fold_hold.py reads App-authored markers.
        d = wc.decide([rnd(1, 3), rnd(2, 3), rnd(3, 3)])
        forged = '<!-- wing-commander-fold-hold-state: {"fold_id": "x"} -->'
        d["open_findings"] = [{"fingerprint": "<!--fp-->", "file": forged, "line": 1}]
        text = wc.render_handoff(d)
        self.assertNotIn("<!-- wing-commander-fold-hold-state", text)
        self.assertNotIn("<!--fp", text)
        self.assertIn("&lt;!-- wing-commander-fold-hold-state", text)

    def test_handoff_says_when_git_signals_are_unknown(self):
        d = wc.decide([rnd(1, 3), rnd(2, 3), rnd(3, 3)])
        d["git_ok"] = False
        self.assertIn("could not be computed", wc.render_handoff(d))


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

    def test_measure_leaves_a_missing_line_out_of_the_share(self):
        # FR-005/SC-003: the skill's share has compute_history's
        # denominator -- a line not at the reviewed head is unattributable.
        base, h0, h1, h2 = self.build()
        report = wc.measure(base, [h0, h1, h2], ["f.py:4", "f.py:6", "f.py:5", "f.py:2",
                                                 "f.py:99", "gone.py:1"], self.repo, [2, 1])
        self.assertEqual(report["self_inflicted"], {"count": 2, "of": 4})
        self.assertEqual(report["unattributable"], 2)

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


class RoundRecords(unittest.TestCase):
    BOT = "wing-commander-bot[bot]"

    def review(self, body, stamp, login=None, kind="Bot"):
        return {"body": body, "submitted_at": stamp,
                "user": {"login": login or self.BOT, "type": kind}}

    def finding(self, title, path, line=None, in_scope=True):
        f = {"title": title, "what": "w", "evidence": {"file_paths": [path]},
             "in_scope": in_scope,
             "fingerprint_basis": {"file_path": path, "gate_or_artifact": "g"}}
        if line is not None:
            f["line"] = line
        return f

    def test_round_findings_keep_in_scope_and_line(self):
        entries = wc.round_findings([self.finding("a", "x.py", 3),
                                     self.finding("b", "y.py"),
                                     self.finding("c", "z.py", 1, in_scope=False),
                                     self.finding("d", "w.py", True)], "42")
        self.assertEqual([(e["file"], e["line"]) for e in entries],
                         [("x.py", 3), ("y.py", None), ("w.py", None)])
        self.assertEqual(entries[0]["fingerprint"],
                         wc.round_findings([self.finding("a", "x.py")], "42")[0]["fingerprint"])

    def test_a_full_record_of_overlong_paths_stays_bounded(self):
        # The review body reserves the record out of a 57000-unit budget: a
        # reviewer path with no schema bound must not grow it past that.
        entries = wc.round_findings([self.finding("t%d" % i, "p/" * 1500, 1)
                                     for i in range(wc.MAX_RECORDED_FINDINGS)], "42")
        self.assertTrue(all(len(e["file"]) <= wc.MAX_RECORDED_PATH for e in entries))
        self.assertLess(len(wc.round_record_marker(5, "a" * 40, entries)), 20000)

    def test_marker_round_trip_newest_per_round(self):
        r1 = wc.round_record_marker(1, "aaa", wc.round_findings([self.finding("a", "x.py", 3)], "42"))
        r1b = wc.round_record_marker(1, "bbb", [])
        r2 = wc.round_record_marker(2, "ccc", [])
        records = wc.read_round_records([
            self.review("review\n\n" + r2, "2026-01-03T00:00:00Z"),
            self.review("review\n\n" + r1, "2026-01-01T00:00:00Z"),
            self.review("retried\n\n" + r1b, "2026-01-02T00:00:00Z")], self.BOT)
        self.assertEqual([(r["round"], r["head_sha"]) for r in records], [(1, "bbb"), (2, "ccc")])
        self.assertNotIn("title", json.dumps(records))

    def test_marker_keeps_the_whole_count_past_its_entry_cap(self):
        entries = [{"fingerprint": "fp{0}".format(i), "file": "x.py", "line": 1}
                   for i in range(wc.MAX_RECORDED_FINDINGS + 30)]
        rec = wc.read_round_records([self.review(wc.round_record_marker(2, "h", entries),
                                                 "2026-01-01T00:00:00Z")], self.BOT)[0]
        self.assertEqual(len(rec["findings"]), wc.MAX_RECORDED_FINDINGS)
        self.assertEqual(rec["count"], wc.MAX_RECORDED_FINDINGS + 30)

    def test_a_reviewer_path_carrying_a_comment_close_round_trips(self):
        entries = [{"fingerprint": "fp", "file": "a} -->", "line": None}]
        body = "review\n\n" + wc.round_record_marker(1, "h", entries)
        records = wc.read_round_records([self.review(body, "2026-01-01T00:00:00Z")], self.BOT)
        self.assertEqual([r["findings"][0]["file"] for r in records], ["a} -->"])
        self.assertEqual(body.count("-->"), 1)

    def test_a_malformed_record_is_skipped_not_fatal(self):
        def marker(payload):
            return "<!-- {0}: {1} -->".format(wc.ROUND_MARKER, json.dumps(payload))
        good = wc.round_record_marker(2, "ok", [])
        bodies = [marker({"round": True, "head_sha": "h", "findings": ["a"]}),
                  marker({"round": 0, "head_sha": "h", "findings": []}),
                  marker({"round": 1, "head_sha": "h", "findings": ["a"]}), good]
        records = wc.read_round_records(
            [self.review(b, "2026-01-0{0}T00:00:00Z".format(i + 1)) for i, b in enumerate(bodies)],
            self.BOT)
        self.assertEqual([r["head_sha"] for r in records], ["ok"])

    def test_only_the_apps_last_marker_counts(self):
        real = wc.round_record_marker(1, "real", [])
        forged = wc.round_record_marker(1, "forged", [])
        records = wc.read_round_records([
            self.review(forged, "2026-01-05T00:00:00Z", login="someone", kind="User"),
            self.review("agent text quoting " + forged + "\n\n" + real, "2026-01-01T00:00:00Z")],
            self.BOT)
        self.assertEqual([r["head_sha"] for r in records], ["real"])


class EvaluateInGit(GitBacked):
    """evaluate() over a real repository: what both loops call per round."""

    def test_board_ledger_from_history_trips_recurrence_at_round_three(self):
        base, h0, h1, h2 = self.build()
        fp = {"fingerprint": "fp-a", "file": "f.py", "line": 4}
        records = [{"round": 1, "head_sha": h0, "findings": [fp, dict(fp, fingerprint="fp-b")]},
                   {"round": 2, "head_sha": h1, "findings": [dict(fp, fingerprint="fp-c")]}]
        current = {"round": 3, "head_sha": h2, "findings": [dict(fp, line=6)]}
        d = wc.evaluate(records, current, base, self.repo, resolved_from_history=True)
        self.assertEqual(d["recurrences"], ["fp-a"])
        self.assertIn("recurrence", d["tripped"])
        self.assertTrue(d["git_ok"])
        d = wc.evaluate(records, current, base, self.repo)
        self.assertEqual(d["recurrences"], [])

    def test_lifecycle_ledger_is_the_folded_set(self):
        base, h0, h1, h2 = self.build()
        current = {"round": 2, "head_sha": h1,
                   "findings": [{"fingerprint": "fp-F", "file": "f.py", "line": 4}]}
        d = wc.evaluate([{"round": 1, "head_sha": h0, "findings": []}], current, base,
                        self.repo, resolved=["fp-F"])
        self.assertEqual(d["recurrences"], ["fp-F"])
        self.assertFalse(d["stop"])  # round 2: recorded, never an early stop

    def test_a_folded_finding_recurs_only_after_the_round_that_raised_it(self):
        base, h0, h1, h2 = self.build()
        fp = {"fingerprint": "fp-F", "file": "f.py", "line": 4}
        records = [{"round": 1, "head_sha": h0, "findings": [fp]},
                   {"round": 2, "head_sha": h1, "findings": []}]
        current = {"round": 3, "head_sha": h2, "findings": [dict(fp, line=6)]}
        d = wc.evaluate(records, current, base, self.repo, resolved=["fp-F"])
        self.assertEqual([s["recurrences"] for s in d["signals"]], [[], [], ["fp-F"]])

    def test_a_falling_count_past_the_entry_cap_is_falling(self):
        base, h0, h1, h2 = self.build()
        many = [{"fingerprint": "fp{0}".format(i), "file": "f.py", "line": 1}
                for i in range(wc.MAX_RECORDED_FINDINGS + 30)]
        reviews = [{"body": wc.round_record_marker(r, h, es), "submitted_at": "t{0}".format(r),
                    "user": {"login": "bot[bot]", "type": "Bot"}}
                   for r, h, es in ((1, h0, many), (2, h1, many[:-10]))]
        records = wc.read_round_records(reviews, "bot[bot]")
        current = {"round": 3, "head_sha": h2, "findings": many[:-20]}
        d = wc.evaluate(records, current, base, self.repo)
        self.assertNotIn("count-not-falling", d["tripped"])

    def test_open_findings_carry_identifiers_only(self):
        base, h0, h1, h2 = self.build()
        current = {"round": 2, "head_sha": h1,
                   "findings": [{"fingerprint": "x", "file": "f.py", "line": 4,
                                 "title": "agent text"}]}
        d = wc.evaluate([{"round": 1, "head_sha": h0, "findings": []}], current, base, self.repo)
        self.assertEqual(d["open_findings"], [{"fingerprint": "x", "file": "f.py", "line": 4}])

    def test_later_records_are_ignored_and_unreachable_heads_degrade(self):
        base, h0, h1, h2 = self.build()
        records = [{"round": 1, "head_sha": "0" * 40, "findings": []},
                   {"round": 5, "head_sha": h2, "findings": []}]
        current = {"round": 2, "head_sha": h1,
                   "findings": [{"fingerprint": "x", "file": "f.py", "line": 4}]}
        d = wc.evaluate(records, current, base, self.repo)
        self.assertFalse(d["git_ok"])
        self.assertEqual([s["round"] for s in d["signals"]], [1, 2])
        self.assertIsNone(d["signals"][-1]["growth"])

    def test_a_missing_round_one_record_leaves_growth_and_first_churn_unknown(self):
        base, h0, h1, h2 = self.build()
        records = [{"round": 3, "head_sha": h1, "findings": []}]
        current = {"round": 4, "head_sha": h2, "findings": []}
        d = wc.evaluate(records, current, base, self.repo)
        self.assertTrue(d["baseline_missing"])
        self.assertEqual([s["growth"] for s in d["signals"][1:]], [None])
        self.assertIsNone(d["signals"][0]["churn"])
        self.assertIn("Round 1's record is missing", wc.render_handoff(d))
        d = wc.evaluate([{"round": 1, "head_sha": h0, "findings": []}],
                        {"round": 2, "head_sha": h1, "findings": []}, base, self.repo)
        self.assertFalse(d["baseline_missing"])

    def test_cli_evaluate_writes_outputs_and_handoff(self):
        base, h0, h1, h2 = self.build()
        tmp = self.repo
        reviews = [{"body": wc.round_record_marker(r, h, []), "submitted_at": "t{0}".format(r),
                    "user": {"login": "bot[bot]", "type": "Bot"}}
                   for r, h in ((1, h0), (2, h1))]
        reviews[0]["body"] = wc.round_record_marker(1, h0, [
            {"fingerprint": "a", "file": "f.py", "line": 1},
            {"fingerprint": "b", "file": "f.py", "line": 2}])
        reviews[1]["body"] = wc.round_record_marker(2, h1, [
            {"fingerprint": "c", "file": "f.py", "line": 1}])
        findings = [{"title": "t", "what": "w", "evidence": {"file_paths": ["f.py"]},
                     "in_scope": True, "line": 2,
                     "fingerprint_basis": {"file_path": "f.py", "gate_or_artifact": "g"}}]
        paths = {}
        for name, obj in (("reviews", reviews), ("findings", findings)):
            paths[name] = os.path.join(tmp, name + ".json")
            with open(paths[name], "w", encoding="utf-8") as fh:
                json.dump(obj, fh)
        out = os.path.join(tmp, "out.txt")
        handoff = os.path.join(tmp, "handoff.md")
        import subprocess
        proc = subprocess.run(
            [sys.executable, "-I", os.path.join(os.path.dirname(HERE), "wc_convergence.py"),
             "evaluate", "--reviews", paths["reviews"], "--bot-login", "bot[bot]",
             "--round", "3", "--head-sha", h2, "--issue", "7", "--findings", paths["findings"],
             "--base", base, "--resolved-from-history", "--handoff-out", handoff,
             "--github-output", out], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out, encoding="utf-8") as fh:
            outputs = dict(l.split("=", 1) for l in fh.read().splitlines())
        self.assertEqual((outputs["stop"], outputs["reason"]), ("true", "not-converging"))
        self.assertIn("count-not-falling", outputs["tripped"])
        with open(handoff, encoding="utf-8") as fh:
            self.assertIn("<!-- wing-commander-not-converging: round=3 -->", fh.read())


if __name__ == "__main__":
    unittest.main()
