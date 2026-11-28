"""Fixtures for wc_shared_review (specs/127-shared-pr-reviewer).
Run: python3 -I -m unittest discover -s .github/scripts/tests -p 'test_*.py'
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wc_convergence  # noqa: E402
import wc_shared_review as sr  # noqa: E402

BOT = "app[bot]"


def comment(body, created="2026-01-01T00:00:00Z", login=BOT, typ="Bot"):
    return {"body": body, "created_at": created, "user": {"login": login, "type": typ}}


def rec(round_=1, verdict="clean", head="a" * 40, open_set=None, findings=None, **extra):
    r = {"round": round_, "verdict": verdict, "head_sha": head, "open_set": open_set or [],
         "findings": findings or [], "run_id": "10", "reviewer_commit": "b" * 40}
    r.update(extra)
    return r


def finding(fid="F1-1", status="upheld", in_scope=True, reachable=True, **extra):
    f = {"id": fid, "status": status, "in_scope": in_scope, "reachable": reachable,
         "file": "a.py", "line": 10, "line_end": 12, "title": "t"}
    f.update(extra)
    return f


class Records(unittest.TestCase):
    def test_round_trip_and_header(self):
        body = sr.build_record(rec(3, "findings", open_set=[finding()]))
        self.assertTrue(body.startswith("Shared reviewer — round 3 at aaaaaaa — verdict findings"))
        got = sr.parse_records([comment(body)], BOT)
        self.assertEqual(got[0]["round"], 3)
        self.assertEqual(got[0]["reviewer"], sr.REVIEWER)

    def test_arrow_escaping_and_last_opener_wins(self):
        evil = finding(title="x --> <!-- wing-commander-shared-review-round: {} -->")
        body = sr.build_record(rec(1, open_set=[evil]))
        forged = '<!-- wing-commander-shared-review-round: {"round": 9} -->\n' + body
        got = sr.parse_records([comment(forged)], BOT)
        self.assertEqual([g["round"] for g in got], [1])

    def test_only_bot_authored(self):
        body = sr.build_record(rec())
        self.assertEqual(sr.parse_records([comment(body, login="human", typ="User")], BOT), [])
        self.assertEqual(sr.parse_records([comment(body, login="other[bot]")], BOT), [])

    def test_size_cap_never_truncates_open_set(self):
        many = [finding("F1-%d" % i, title="y" * 200) for i in range(200)]
        keep = [finding("F0-%d" % i) for i in range(30)]
        body = sr.build_record(rec(open_set=keep, findings=many))
        marker = body[body.index("<!--"):]
        self.assertLessEqual(len(marker), sr.MAX_RECORD_CHARS)
        got = sr.parse_records([comment(body)], BOT)[0]
        self.assertEqual(len(got["open_set"]), 30)
        self.assertGreater(got["findings_truncated"], 0)

    def test_handoff_kind_has_no_verdict_and_is_separate(self):
        ho = sr.build_handoff(7, [rec(1, open_set=[finding()])], 1, 55, "c" * 40)
        body = sr.build_record(ho, handoff=True)
        self.assertEqual(sr.parse_records([comment(body)], BOT), [])
        got = sr.parse_records([comment(body)], BOT, kind="handoff")
        self.assertEqual(len(got), 1)
        self.assertNotIn("verdict", got[0])
        self.assertEqual(len(got[0]["open_set"]), 1)

    def test_old_convergence_reader_never_counts_shared_record(self):
        body = sr.build_record(rec())
        self.assertNotEqual(sr.MARKER, wc_convergence.ROUND_MARKER)
        self.assertEqual(wc_convergence.read_round_records([comment(body)], BOT), [])


class Verdict(unittest.TestCase):
    ok = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}

    def test_order(self):
        v = sr.compute_verdict
        self.assertEqual(v(False, [finding()], self.ok, "staged"), "incomplete")
        self.assertEqual(v(True, [finding()], self.ok, "missing"), "findings")
        self.assertEqual(v(True, [], self.ok, "missing"), "incomplete")
        undetermined = dict(self.ok, change_fixes=sr.UNDETERMINABLE)
        self.assertEqual(v(True, [], undetermined, "staged"), "undetermined")
        self.assertEqual(v(True, [], self.ok, "staged", has_purpose=False), "undetermined")
        self.assertEqual(v(True, [], self.ok, "staged"), "clean")

    def test_earlier_open_blocking_counts(self):
        self.assertEqual(sr.compute_verdict(True, [finding("F1-1", "reopened")], self.ok, "staged"), "findings")

    def test_non_blocking_does_not_block(self):
        self.assertEqual(sr.compute_verdict(True, [finding(in_scope=False)], self.ok, "staged"), "clean")
        self.assertEqual(sr.compute_verdict(True, [finding(reachable=False)], self.ok, "staged"), "clean")
        self.assertIn("scope", sr.non_blocking_rule(finding(in_scope=False)))

    def test_sc005_check_passes_without_fix(self):
        answers = dict(self.ok, check_fails_without_fix=sr.NEGATIVE)
        self.assertNotEqual(sr.compute_verdict(True, [], answers, "staged"), "clean")


class BlockingRule(unittest.TestCase):
    def cand(self, **kw):
        c = {"key": "k1", "title": "t", "file": "a.py", "line": 1,
             "failing_case": {"state": "s", "wrong_result": "w"}}
        c.update(kw)
        return c

    def run_one(self, cand, check):
        check = dict({"key": "k1", "outcome": "upheld", "in_scope": True, "reachable": True}, **check)
        found, _ = sr.process_round([], [cand], [check], 1, "staged")
        return found[0]

    def test_absent_failing_case_dismissed(self):
        f = self.run_one(self.cand(failing_case=None), {})
        self.assertEqual(f["status"], "dismissed")

    def test_spec_doc_only_dismissed_but_contract_reviewable(self):
        f = self.run_one(self.cand(), {"files": ["specs/001-x/plan.md"]})
        self.assertEqual(f["status"], "dismissed")
        self.assertIn("spec", f["reason"])
        f = self.run_one(self.cand(), {"files": ["specs/001-x/contracts/a.md"]})
        self.assertEqual(f["status"], "upheld")

    def test_sc006_unreproducible_claim_dismissed(self):
        f = self.run_one(self.cand(), {"outcome": "dismissed", "reason": "does not reproduce"})
        self.assertEqual(f["status"], "dismissed")
        self.assertFalse(sr.is_blocking(f))

    def test_upheld_blocks(self):
        self.assertTrue(sr.is_blocking(self.run_one(self.cand(), {})))


class Request(unittest.TestCase):
    def test_kind(self):
        self.assertEqual(sr.derive_kind("fix/12-thing"), "board-fix")
        self.assertEqual(sr.derive_kind("claude/some-fix"), "fix")
        self.assertEqual(sr.derive_kind("spec/127-x"), "spec")
        self.assertEqual(sr.derive_kind("whatever", ["lifecycle:final"]), "final")

    def test_refusals(self):
        self.assertFalse(sr.validate_request("5", "spec", [])[0])
        self.assertFalse(sr.validate_request("x", "fix", [])[0])
        self.assertTrue(sr.validate_request("5", "fix", [])[0])

    def test_purpose_source_order(self):
        r = sr.resolve_purpose_source
        self.assertEqual(r(5, "Fixes #7"), {"type": "issue", "ref": "7"})
        self.assertEqual(r(5, "see #5 and #9"), {"type": "issue", "ref": "9"})
        self.assertEqual(r(5, "backlog line abc-1"), {"type": "backlog", "ref": "abc-1"})
        self.assertEqual(r(5, "https://github.com/o/r/actions/runs/99"), {"type": "run", "ref": "99"})
        self.assertIsNone(r(5, "nothing, and #5 itself"))

    def test_purpose_source_reads_the_shared_closing_pattern(self):
        # The code review of #1314: a local copy of the closing-keyword
        # pattern missed the past tenses and every form but a bare #N, so
        # an issue mentioned first won. #981's body is the real case: it
        # mentions #977, then "closed #979".
        r = sr.resolve_purpose_source
        repo = "o/r"
        self.assertEqual(r(5, "since #977 ... closed #979", repo), {"type": "issue", "ref": "979"})
        self.assertEqual(r(5, "see #3. Resolved: #8", repo), {"type": "issue", "ref": "8"})
        self.assertEqual(r(5, "see #3. Fixes GH-8", repo), {"type": "issue", "ref": "8"})
        self.assertEqual(r(5, "see #3. Fixes o/r#8", repo), {"type": "issue", "ref": "8"})
        self.assertEqual(r(5, "see #3. Closes https://github.com/O/R/issues/8", repo),
                         {"type": "issue", "ref": "8"})
        # Another repository's issue is not this PR's purpose.
        self.assertEqual(r(5, "see #3. Fixes x/y#8", repo), {"type": "issue", "ref": "3"})
        # The repository defaults to $GITHUB_REPOSITORY, as in Actions.
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r"}):
            self.assertEqual(r(5, "see #3. Fixes o/r#8"), {"type": "issue", "ref": "8"})


class Memory(unittest.TestCase):
    def cand(self, key="k", **kw):
        c = {"key": key, "title": "reworded", "file": "a.py", "line": 11,
             "failing_case": {"state": "s", "wrong_result": "w"}}
        c.update(kw)
        return c

    def chk(self, key, **kw):
        c = {"key": key, "outcome": "upheld", "in_scope": True, "reachable": True}
        c.update(kw)
        return c

    def test_cite_kept_unknown_cite_new_and_overlap_flagged(self):
        prior = [finding("F1-1")]
        found, notes = sr.process_round(prior, [self.cand("a", cites="F1-1"), self.cand("b", cites="F9-9"),
                                                self.cand("c", file="z.py")],
                                        [self.chk("a"), self.chk("b"), self.chk("c")], 2, "staged")
        ids = {f["id"]: f for f in found}
        self.assertEqual(len(found), 3)
        self.assertEqual(ids["F2-1"]["possible_repeat_of"], "F1-1")
        self.assertIsNone(ids["F2-2"]["possible_repeat_of"])
        self.assertEqual(ids["F1-1"]["status"], "upheld")
        self.assertTrue(any("unknown id" in n for n in notes))

    def test_uncited_overlap_never_merged(self):
        found, _ = sr.process_round([finding("F1-1")], [self.cand("a")], [self.chk("a")], 2, "staged")
        self.assertEqual(len(found), 2)

    def test_transitions(self):
        self.assertTrue(sr._transition("dismissed", "reopened"))
        self.assertFalse(sr._transition("dismissed", "resolved"))
        self.assertFalse(sr._transition("resolved", "upheld"))
        self.assertFalse(sr._transition(None, "reopened"))

    def test_reopen_only_when_upheld_and_reraise_stays_dismissed(self):
        prior = [finding("F1-1", "dismissed", reason="r")]
        f, notes = sr.process_round(prior, [self.cand("a", cites="F1-1")], [self.chk("a", outcome="dismissed")], 2, "staged")
        self.assertEqual(f[0]["status"], "dismissed")
        self.assertTrue(notes)
        f, _ = sr.process_round(prior, [self.cand("a", cites="F1-1")], [self.chk("a", reason="shown")], 2, "staged")
        self.assertEqual((f[0]["id"], f[0]["status"]), ("F1-1", "reopened"))

    def test_recheck_resolves_and_missing_code_run_keeps(self):
        prior = [finding("F1-1")]
        chk = [{"id": "F1-1", "outcome": "resolved", "needs_code_run": True}]
        f, _ = sr.process_round(prior, [], chk, 2, "staged")
        self.assertEqual(f[0]["status"], "resolved")
        f, _ = sr.process_round(prior, [], chk, 2, "missing")
        self.assertEqual(f[0]["status"], "upheld")
        self.assertEqual(f[0]["note"], sr.NOT_RECHECKED)

    def test_dismissals(self):
        prior = [finding("F1-1"), finding("F1-2", "resolved")]
        out, applied, notes = sr.apply_dismissals(prior, [{"id": "F1-1", "reason": "ok"},
                                                          {"id": "F1-2", "reason": "x"}, {"id": "F9", "reason": "y"}])
        self.assertEqual([a["id"] for a in applied], ["F1-1"])
        self.assertEqual(len(notes), 2)
        self.assertEqual({f["id"]: f["status"] for f in out}["F1-1"], "dismissed")

    def test_fold_and_seeded_two_round(self):
        r1 = rec(1, "findings", open_set=[finding("F1-1")])
        r2 = rec(2, "clean", findings=[finding("F1-1", "resolved", reason="fixed")])
        state = sr.fold_open_set([r2, r1])
        self.assertEqual(sr.open_set(state), [])
        self.assertEqual(len(sr.open_set(sr.fold_open_set([r1]))), 1)
        # dismissal-shaped comments are not records
        self.assertEqual(sr.parse_records([comment("dismiss F1-1: no")], BOT), [])


class Confirm(unittest.TestCase):
    def run_(self, **kw):
        r = {"id": 10, "path": sr.WRAPPER_PATH, "head_branch": "main", "status": "completed",
             "conclusion": "success", "head_sha": "b" * 40, "repository": "o/r",
             "referenced_workflows": ["o/r/" + sr.WORKFLOW_PATH + "@refs/heads/main"],
             "artifacts": [sr.ARTIFACT_PREFIX + "a" * 40],
             "artifact_verdicts": {sr.ARTIFACT_PREFIX + "a" * 40: "clean"}}
        r.update(kw)
        return r

    def test_confirms(self):
        self.assertTrue(sr.confirm_record(rec(), self.run_(), "main"))

    def test_edited_verdict_never_confirms(self):
        # #889 (found by the code review of #1346): an App comment edited
        # from `findings` to `clean` keeps its run and head; only the run's
        # own artifact still says `findings`.
        posted = rec(verdict="findings")
        run = self.run_(artifact_verdicts={sr.ARTIFACT_PREFIX + "a" * 40: "findings"})
        self.assertTrue(sr.confirm_record(posted, run, "main"))
        edited = sr.parse_records([comment(sr.build_record(dict(posted, verdict="clean")))], BOT)[0]
        self.assertFalse(sr.confirm_record(edited, run, "main"))

    def test_unreadable_artifact_never_confirms(self):
        # The artifact is listed but its verdict could not be read (expired,
        # 404/410, no well-formed record): the record does not confirm.
        name = sr.ARTIFACT_PREFIX + "a" * 40
        for verdicts in ({}, {name: None}, None):
            self.assertFalse(sr.confirm_record(rec(), self.run_(artifact_verdicts=verdicts), "main"), verdicts)

    def test_each_failure(self):
        for kw in ({"path": "x"}, {"head_branch": "feat"}, {"head_sha": "c" * 40}, {"conclusion": "failure"},
                   {"status": "in_progress"}, {"artifacts": []}, {"referenced_workflows": []}, {"id": 11}):
            self.assertFalse(sr.confirm_record(rec(), self.run_(**kw), "main"), kw)
        self.assertFalse(sr.confirm_record(rec(run_id="abc"), self.run_(), "main"))
        self.assertFalse(sr.confirm_record(rec(), None, "main"))

    def test_latest_round_for_commit(self):
        rs = [rec(1), rec(2), rec(3, head="d" * 40)]
        self.assertEqual(sr.latest_round_for_commit(rs, "a" * 40)["round"], 2)

    def test_latest_round_is_pr_wide(self):
        rs = [rec(1), rec(2, head="d" * 40), rec(1, verdict="findings")]
        self.assertEqual(sr.latest_round(rs)["head_sha"], "d" * 40)
        self.assertEqual(sr.latest_round(rs[:1] + rs[2:])["verdict"], "findings")
        self.assertIsNone(sr.latest_round([]))


class GuardAndBudget(unittest.TestCase):
    def test_guard(self):
        self.assertEqual(sr.guard("refs/heads/feat", "main", "fix", "")[0], False)
        self.assertIn("refused", sr.guard("refs/heads/feat", "main", "fix", "")[1])
        self.assertEqual(sr.guard("refs/heads/main", "main", "spec", "")[0], False)
        self.assertEqual(sr.guard("refs/heads/main", "main", "fix", "true"), (False, "paused"))
        # #889, the one switch rule: `true` in any case pauses; nothing else does.
        for value in ("True", "TRUE"):
            self.assertEqual(sr.guard("refs/heads/main", "main", "fix", value), (False, "paused"), value)
        for value in ("1", "yes", "true ", "false", None):
            self.assertEqual(sr.guard("refs/heads/main", "main", "fix", value), (True, None), value)
        self.assertEqual(sr.guard("refs/heads/main", "main", "fix", ""), (True, None))

    def test_budget(self):
        rounds = [rec(i, "incomplete") for i in range(1, 6)]
        self.assertTrue(sr.budget_spent(rounds)[0])
        self.assertFalse(sr.budget_spent(rounds[:4])[0])
        self.assertTrue(sr.budget_spent(rounds[:2], "2")[0])
        self.assertEqual(sr.budget_spent([], "junk")[1], 5)

    def test_handoff_carries_last_open_set(self):
        rs = [rec(1, open_set=[finding("F1-1")]), rec(2, open_set=[finding("F1-1"), finding("F2-1")])]
        ho = sr.build_handoff(3, rs, 2, 9, "c" * 40)
        self.assertEqual(len(ho["open_set"]), 2)
        self.assertNotIn("verdict", ho)


class CodeRun(unittest.TestCase):
    def test_discover(self):
        d = sr.discover_named_check
        self.assertEqual(d(["README.md"]), None)
        self.assertEqual(d(["x/test_a.py"]),
                         ["python3", "-I", "-m", "unittest", "discover", "-v", "-s", "x", "-p", "test_a.py"])
        self.assertEqual(d(["x/verify-a.py"]), ["python3", "-I", "x/verify-a.py"])
        self.assertIsNone(d(["../test_a.py", "/abs/test_b.py"]))

    def test_stages_exit_codes_as_data_inside_the_sandbox(self):
        # The real hostile run is verify-shared-review-isolation.py's; here
        # the sandbox is faked, so this checks what stage_code_run asks it
        # to run and how it stages the answers.
        box = FakeSandbox({1: {"exit": 1, "output_tail": "LEAKED:\n"}, 2: {"exit": 3, "output_tail": ""}})
        out = sr.stage_code_run("tree", "rev", ["verify-probe-check.py"], timeout=60, sandbox=box)
        self.assertEqual(out["status"], "staged")
        self.assertEqual(out["named_check"]["exit"], 1)
        self.assertEqual(out["gate_suite"]["exit"], 3)
        self.assertEqual(box.opened, (os.path.abspath("tree"), os.path.abspath("rev")))
        self.assertEqual(box.ran[0], (["python3", "-I", "verify-probe-check.py"], 60, 1))
        self.assertEqual(box.ran[1], (["python3", "-I", "/box/run-local-gates.py"], sr.GATE_SUITE_TIMEOUT, 2))
        self.assertTrue(box.closed)

    def test_no_named_check_is_none_not_failure(self):
        box = FakeSandbox({2: {"exit": 0, "output_tail": "ok"}})
        out = sr.stage_code_run("tree", "rev", [], timeout=30, sandbox=box)
        self.assertIsNone(out["named_check"])
        self.assertEqual(out["gate_suite"]["exit"], 0)
        self.assertEqual(len(box.ran), 1)

    def test_any_exception_is_missing_and_still_closes(self):
        # P2: an OSError from a failed fork, or anything else, is `missing`
        # with the sandbox closed, never a crash of the code-run step.
        for exc in (OSError(11, "Resource temporarily unavailable"), ValueError("odd"), KeyError("x")):
            box = FakeSandbox({})

            def boom(*a, exc=exc):
                raise exc
            box.run = boom
            out = sr.stage_code_run("tree", "rev", ["x/verify-a.py"], timeout=30, sandbox=box)
            self.assertEqual(out["status"], "missing", exc)
            self.assertTrue(box.closed)

    def test_close_kills_and_cleans_up_whatever_was_raised(self):
        calls = []

        class Box(sr.UidSandbox):
            def _kill_all(self):
                calls.append("kill")
                raise OSError(11, "fork failed")

            def _sudo(self, *argv, **kw):
                calls.append(argv[0])
                raise OSError(11, "fork failed")
        box = Box()
        box.work, box.private = "/nonexistent/work", None
        box.close()
        self.assertEqual(calls, ["kill", "rm"])

    def test_commands_run_under_a_process_cap(self):
        import subprocess
        from unittest import mock
        seen = {}

        class Box(sr.UidSandbox):
            def _fresh_tree(self, n, src=None, overlay=()):
                return "/t", "/h"

            def _kill_all(self):
                pass
        box = Box()
        box.private = __import__("tempfile").mkdtemp()

        class P:
            pid = 1

            def wait(self, timeout=None):
                return 0

        def fake_popen(argv, **kw):
            seen["argv"] = argv
            return P()
        with mock.patch.object(subprocess, "Popen", fake_popen), \
                mock.patch.object(Box, "_sudo", lambda self, *a, **k: subprocess.CompletedProcess(a, 0, b"", b"")):
            box.run(["true"], 5, 1)
        argv = seen["argv"]
        self.assertEqual(argv[argv.index("prlimit") + 1], "--nproc={0}:{0}".format(sr.SANDBOX_NPROC))
        self.assertLess(argv.index("prlimit"), argv.index("env"))

    def test_no_sandbox_runs_nothing_and_is_missing(self):
        # R3-F6: where the sandbox cannot be set up, or a process survives
        # its kill, nothing is staged and nothing of the PR runs unisolated.
        for where in ("open", "run"):
            box = FakeSandbox({}, fail=where)
            out = sr.stage_code_run("tree", "rev", ["x/verify-a.py"], timeout=30, sandbox=box)
            self.assertEqual(out["status"], "missing", where)
            self.assertIn("sandbox", out["reason"])
            self.assertTrue(box.closed)
        self.assertNotEqual(sr.SANDBOX_USER, "runner")

    def test_tree_copy_is_a_git_repository_with_origin(self):
        # A4: gates find the repository root through git, and one reads
        # OWNER/NAME from origin; the sandbox user makes each copy a repo.
        import subprocess
        calls = []

        def fake_sh(argv, **kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        saved = sr._sh
        sr._sh = fake_sh
        try:
            sr.UidSandbox(origin_url="https://github.com/o/r.git")._git_init("/t", "/h")
        finally:
            sr._sh = saved
        tails = [c[c.index("-C") + 2:] for c in calls]
        self.assertTrue(all(c[:5] == ["sudo", "-n", "-u", sr.SANDBOX_USER, "--"] for c in calls))
        self.assertIn(["-c", "core.hooksPath=/dev/null", "init", "-q"], [t[-4:] for t in tails])
        self.assertIn(["remote", "add", "origin", "https://github.com/o/r.git"], [c[-4:] for c in calls])
        self.assertTrue(any("commit" in c for c in calls))

    def test_kill_and_listing_match_effective_and_real_uid(self):
        # A sandbox process inside a setuid program keeps its real uid only.
        calls = []

        class Box(sr.UidSandbox):
            def _sudo(self, *argv, **kw):
                import subprocess
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 1 if argv[0] == "ps" else 0, b"", b"")
        Box()._kill_all()
        self.assertIn(("pkill", "-KILL", "-u", sr.SANDBOX_USER), calls)
        self.assertIn(("pkill", "-KILL", "-U", sr.SANDBOX_USER), calls)
        ps = next(c for c in calls if c[0] == "ps")
        self.assertIn("-U", ps)
        self.assertIn("-u", ps)

    def test_kill_check_ignores_zombies_but_not_live_processes(self):
        # A killed process whose new parent never reaps it (a container's
        # bare PID 1) stays listed as a zombie; it runs no code.
        class Box(sr.UidSandbox):
            listing = b""

            def _sudo(self, *argv, **kw):
                import subprocess
                if argv[0] == "ps":
                    return subprocess.CompletedProcess(argv, 0, self.listing, b"")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
        saved = sr.KILL_ATTEMPTS
        sr.KILL_ATTEMPTS = 2
        try:
            box = Box()
            box.listing = b"   37 Z\n   61 Zs\n"
            box._kill_all()
            self.assertEqual(box.live_pids(), [])
            box.listing = b"   37 Z\n   62 S\n"
            self.assertEqual(box.live_pids(), [62])
            with self.assertRaises(sr.SandboxUnavailable):
                box._kill_all()
        finally:
            sr.KILL_ATTEMPTS = saved


class FakeSandbox:
    def __init__(self, results, fail=None):
        self.results, self.fail = results, fail
        self.opened, self.ran, self.closed = None, [], False

    def open(self, pr_tree, reviewer_tree):
        if self.fail == "open":
            raise sr.SandboxUnavailable("no sudo")
        self.opened = (pr_tree, reviewer_tree)
        return self

    def gate_runner(self):
        return "/box/run-local-gates.py"

    def run(self, argv, timeout, n, src=None, overlay=()):
        if self.fail == "run":
            raise sr.SandboxUnavailable("processes survived the kill")
        self.ran.append((argv, timeout, n))
        self.trees = getattr(self, "trees", {})
        self.trees[n] = (src, list(overlay))
        return self.results[n]

    def close(self):
        self.closed = True


class Finalize(unittest.TestCase):
    def test_end_to_end_clean_and_findings(self):
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        state = {"round": 1, "prior": []}
        code = {"status": "staged", "named_check": {"exit": 0, "output_tail": ""},
                "named_check_without_fix": {"exit": 1, "output_tail": "fails"}}
        out = sr.finalize_round(state, {"answers": {}, "candidates": []}, {"checks": [], "answers": answers}, code,
                                {"type": "issue", "ref": "7"}, "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(out["verdict"], "clean")
        cand = {"key": "k", "title": "t", "file": "a.py", "line": 1, "failing_case": {"state": "s", "wrong_result": "w"}}
        chk = {"key": "k", "outcome": "upheld", "in_scope": True, "reachable": True}
        out = sr.finalize_round(state, {"answers": {}, "candidates": [cand]}, {"checks": [chk], "answers": answers}, code,
                                {"type": "issue", "ref": "7"}, "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(out["verdict"], "findings")
        self.assertTrue(out["open_set"][0]["blocking"])
        # agent output missing -> incomplete, never clean
        out = sr.finalize_round(state, None, None, code, None, "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(out["verdict"], "incomplete")
        # code-run missing with an earlier open blocking finding stays findings
        state2 = {"round": 2, "prior": [finding("F1-1")]}
        recheck = {"id": "F1-1", "outcome": "confirmed", "needs_code_run": True}
        out = sr.finalize_round(state2, {"answers": {}, "candidates": []}, {"checks": [recheck], "answers": answers}, None,
                                {"type": "issue", "ref": "7"}, "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(out["verdict"], "findings")


class ReviewRound2Fixes(unittest.TestCase):
    def test_unknown_branch_is_not_fix(self):
        self.assertEqual(sr.derive_kind("whatever"), "unknown")
        ok, _ = sr.validate_request(1, sr.derive_kind("whatever"), None)
        self.assertFalse(ok)

    def test_non_list_dismissals_ignored(self):
        prior = [{"id": "F1-1", "status": "upheld"}]
        for bad in ({"id": "F1-1"}, "x", ["str", None]):
            out, applied, _ = sr.apply_dismissals(prior, bad)
            self.assertEqual(applied, [])
            self.assertEqual(out[0]["status"], "upheld")

    def test_code_run_relative_trees(self):
        box = FakeSandbox({2: {"exit": 0, "output_tail": "ok"}})
        sr.stage_code_run("trees/pr-tree", "trees/rev", [], sandbox=box)
        self.assertEqual(box.opened, (os.path.abspath("trees/pr-tree"), os.path.abspath("trees/rev")))

    def test_gh_api_404_only_on_a_real_http_404(self):
        # Round 4: a transient error whose text merely contains "404" is a
        # failed read (None), never "the run does not exist".
        import subprocess
        from unittest import mock

        def fake(stderr):
            return lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", stderr)
        with mock.patch.object(subprocess, "run", fake("gh: Not Found (HTTP 404)\n")):
            with self.assertRaises(sr.GhNotFound):
                sr._gh_api(["repos/o/r/actions/runs/404"])
        for transient in ("HTTP 502: Bad Gateway (https://api.github.com/repos/o/r/actions/runs/404)\n",
                          "error connecting to api.github.com: dial tcp 140.82.114.404\n"):
            with mock.patch.object(subprocess, "run", fake(transient)):
                self.assertIsNone(sr._gh_api(["repos/o/r/actions/runs/404"]))

    def test_failed_reads_raise(self):
        with self.assertRaises(sr.GhReadError):
            sr.confirmed_from_github(1, "bot", "main", "o/r", lambda a: None)

    def test_run_and_artifact_reads_use_the_runs_reader(self):
        # Run 45614694181: the App is granted no Actions scope, so earlier
        # rounds' runs and artifacts are read with the job's own token. The
        # comments read stays on the App reader; nothing under actions/
        # reaches it.
        app_paths, run_paths = [], []
        comment = {"user": {"login": "bot"}, "body": "x"}

        def app(args):
            app_paths.append(args[0])
            return [[comment]]

        def runs(args):
            run_paths.append(args[0])
            return {"artifacts": []} if args[0].endswith("/artifacts") else {}
        from unittest import mock
        with mock.patch.object(sr, "parse_records", lambda flat, bot: [{"run_id": "7"}]), \
                mock.patch.object(sr, "confirm_record", lambda *a: False):
            sr.confirmed_from_github(1, "bot", "main", "o/r", app, runs)
        self.assertEqual(app_paths, ["repos/o/r/issues/1/comments"])
        self.assertEqual(run_paths, ["repos/o/r/actions/runs/7", "repos/o/r/actions/runs/7/artifacts"])

    def test_gh_api_token_overrides_gh_token_for_one_call(self):
        import subprocess
        from unittest import mock
        seen = {}

        def fake(argv, **kw):
            seen["env"] = kw.get("env")
            return subprocess.CompletedProcess(argv, 0, "{}", "")
        with mock.patch.object(subprocess, "run", fake), mock.patch.dict(os.environ, {"GH_TOKEN": "app"}):
            sr._gh_api(["repos/o/r/actions/runs/1"], token="run")
            self.assertEqual(seen["env"]["GH_TOKEN"], "run")
            sr._gh_api(["repos/o/r/issues/1/comments"])
            self.assertIsNone(seen["env"])  # inherits GH_TOKEN (the App token)

    def test_state_without_run_token_fails_closed(self):
        from unittest import mock
        env = {k: v for k, v in os.environ.items() if k != "RUN_TOKEN"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sr, "confirmed_from_github", side_effect=AssertionError("read")):
            self.assertEqual(sr.main(["state", "--pr", "1", "--bot-login", "b[bot]",
                                      "--default-branch", "main", "--repository", "o/r"]), 1)


def artifact_zip(record_body, head="a" * 40, member=None):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member or "record-{0}.md".format(head), record_body)
    return buf.getvalue()


class ArtifactVerdict(unittest.TestCase):
    """#889: the verdict confirm_record compares, read from the run's
    `shared-review-<head>` artifact (the record job's record-<head>.md)."""
    NAME = sr.ARTIFACT_PREFIX + "a" * 40

    def test_reads_the_records_verdict(self):
        body = sr.build_record(rec(verdict="findings"))
        self.assertEqual(sr.artifact_verdict(artifact_zip(body), self.NAME), "findings")

    def test_unreadable_is_none(self):
        body = sr.build_record(rec())
        for data in (b"not a zip", artifact_zip(body, member="other.md"), artifact_zip("no marker"),
                     artifact_zip(sr.build_record(rec(head="d" * 40))),
                     artifact_zip(sr.build_record(sr.build_handoff(1, [], 5, 9, "c" * 40), handoff=True))):
            self.assertIsNone(sr.artifact_verdict(data, self.NAME))

    def runs(self, artifacts):
        def runs(args):
            if args[0].endswith("/artifacts"):
                return {"artifacts": artifacts}
            return {"id": 10, "repository": {"full_name": "o/r"}}
        return runs

    def test_fetch_run_facts_downloads_the_head_artifact_only(self):
        seen = []
        zipped = artifact_zip(sr.build_record(rec(verdict="findings")))

        def gh_zip(args):
            seen.append(args[0])
            return zipped
        run = sr.fetch_run_facts("o/r", "10", self.runs([{"id": 5, "name": self.NAME},
                                                          {"id": 6, "name": "shared-review-input"}]), gh_zip)
        self.assertEqual(seen, ["repos/o/r/actions/artifacts/5/zip"])
        self.assertEqual(run["artifact_verdicts"], {self.NAME: "findings"})

    def test_a_reruns_newest_artifact_wins(self):
        # The API lists newest first; the re-run attempt's artifact decides.
        zips = {"5": artifact_zip(sr.build_record(rec(verdict="findings"))),
                "8": artifact_zip(sr.build_record(rec(verdict="clean")))}
        run = sr.fetch_run_facts("o/r", "10", self.runs([
            {"id": 8, "name": self.NAME, "created_at": "2026-01-02T00:00:00Z"},
            {"id": 5, "name": self.NAME, "created_at": "2026-01-01T00:00:00Z"}]),
            lambda args: zips[args[0].split("/")[-2]])
        self.assertEqual(run["artifact_verdicts"], {self.NAME: "clean"})

    def test_a_gone_artifact_has_no_verdict(self):
        # Expired (listed as such, or 404/410 on download) or no zip reader:
        # the record it backs is unconfirmed, never a read failure.
        def gone(args):
            raise sr.GhNotFound(args[0])
        for arts, gh_zip in (([{"id": 5, "name": self.NAME, "expired": True}], lambda a: b""),
                             ([{"id": 5, "name": self.NAME}], gone),
                             ([{"id": 5, "name": self.NAME}], None),
                             ([{"name": self.NAME}], lambda a: b"")):
            run = sr.fetch_run_facts("o/r", "10", self.runs(arts), gh_zip)
            self.assertEqual(run["artifact_verdicts"], {self.NAME: None})

    def test_a_failed_download_raises(self):
        with self.assertRaises(sr.GhReadError):
            sr.fetch_run_facts("o/r", "10", self.runs([{"id": 5, "name": self.NAME}]), lambda a: None)

    def test_confirmed_from_github_drops_an_edited_record(self):
        # The reviewer's loop: the edited record is dropped like any other
        # unconfirmed one; the unedited one confirms.
        run = Confirm().run_()
        artifact = artifact_zip(sr.build_record(rec(verdict="findings")))
        posted = comment(sr.build_record(rec(verdict="findings")))

        def gh(args):
            if args[0].endswith("/comments"):
                return [[posted]]
            if args[0].endswith("/artifacts"):
                return {"artifacts": [{"id": 5, "name": n} for n in run["artifacts"]]}
            return dict(run, repository={"full_name": "o/r"},
                        referenced_workflows=[{"path": p} for p in run["referenced_workflows"]])
        self.assertEqual(len(sr.confirmed_from_github(5, BOT, "main", "o/r", gh, gh, lambda a: artifact)), 1)
        posted["body"] = sr.build_record(rec(verdict="clean"))
        self.assertEqual(sr.confirmed_from_github(5, BOT, "main", "o/r", gh, gh, lambda a: artifact), [])
        # An artifact that is gone drops the record too; a failed download
        # stops the round.
        posted["body"] = sr.build_record(rec(verdict="findings"))

        def gone(args):
            raise sr.GhNotFound(args[0])
        self.assertEqual(sr.confirmed_from_github(5, BOT, "main", "o/r", gh, gh, gone), [])
        with self.assertRaises(sr.GhReadError):
            sr.confirmed_from_github(5, BOT, "main", "o/r", gh, gh, lambda a: None)

    def test_gh_zip_returns_bytes_and_maps_gone(self):
        import subprocess
        with mock.patch.object(subprocess, "run",
                               lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"PK\x03", b"")):
            self.assertEqual(sr._gh_zip(["x"]), b"PK\x03")
        for code, raises in ((410, True), (404, True), (500, False)):
            err = "gh: Gone (HTTP {0})".format(code).encode()
            with mock.patch.object(subprocess, "run",
                                   lambda argv, err=err, **kw: subprocess.CompletedProcess(argv, 1, b"", err)):
                if raises:
                    self.assertRaises(sr.GhNotFound, sr._gh_zip, ["x"])
                else:
                    self.assertIsNone(sr._gh_zip(["x"]))

    def test_state_passes_a_zip_reader(self):
        seen = {}

        def fake(*args):
            seen["gh_zip"] = args[6] if len(args) > 6 else None
            return []
        with mock.patch.dict(os.environ, {"RUN_TOKEN": "t"}), mock.patch.object(sr, "confirmed_from_github", fake), \
                mock.patch("sys.stdout"):
            sr.main(["state", "--pr", "1", "--bot-login", "b[bot]", "--default-branch", "main",
                     "--repository", "o/r"])
        self.assertTrue(callable(seen.get("gh_zip")))


class FetchRunFacts(unittest.TestCase):
    """fetch_run_facts is the run read's one home (wc_merge_evidence.py
    calls it too): shaped for confirm_record, None only for a real 404."""

    def test_shapes_the_run_for_confirm_record(self):
        def runs(args):
            if args[0].endswith("/artifacts"):
                return {"artifacts": [{"name": "shared-review-" + "a" * 40}]}
            return {"id": 7, "repository": {"full_name": "o/r"},
                    "referenced_workflows": [{"path": "o/r/.github/workflows/shared-pr-reviewer.yml@x"}]}
        run = sr.fetch_run_facts("o/r", "7", runs)
        self.assertEqual(run["repository"], "o/r")
        self.assertEqual(run["artifacts"], ["shared-review-" + "a" * 40])
        self.assertEqual(run["referenced_workflows"], ["o/r/.github/workflows/shared-pr-reviewer.yml@x"])

    def test_a_missing_run_is_none(self):
        def runs(args):
            raise sr.GhNotFound(args[0])
        self.assertIsNone(sr.fetch_run_facts("o/r", "7", runs))

    def test_a_failed_read_raises_not_none(self):
        for failing in ("run", "artifacts"):
            def runs(args, failing=failing):
                is_arts = args[0].endswith("/artifacts")
                if (failing == "artifacts") == is_arts:
                    return None
                return {"artifacts": []} if is_arts else {"id": 7}
            with self.assertRaises(sr.GhReadError):
                sr.fetch_run_facts("o/r", "7", runs)

class ReviewRound3Fixes(unittest.TestCase):
    """Gate round 3 findings on #1184, built by hand."""

    def test_candidate_key_equal_to_prior_id_keeps_its_own_check(self):
        # R3-F8: a candidate keyed "F1-1" and the prior finding F1-1 each
        # keep their own check entry.
        prior = [finding("F1-1")]
        cand = {"key": "F1-1", "title": "new", "file": "b.py", "line": 1,
                "failing_case": {"state": "s", "wrong_result": "w"}}
        checks = [{"id": "F1-1", "outcome": "resolved", "reason": "gone"},
                  {"key": "F1-1", "outcome": "upheld", "in_scope": True, "reachable": True}]
        out, _ = sr.process_round(prior, [cand], checks, 2, "staged")
        by = {f["id"]: f for f in out}
        self.assertEqual(by["F1-1"]["status"], "resolved")
        self.assertEqual(by["F2-1"]["status"], "upheld")

    def test_size_cap_never_reopens_a_resolved_finding(self):
        # R3-F2: round 2 resolves F1-1, but its record is over the cap and
        # F1-1 sits at the end of `findings`. The fold must still see it
        # resolved, not fall back to round 1's `upheld`.
        r1 = rec(1, "findings", open_set=[finding("F1-1", title="kept detail")])
        filler = [finding("F2-%d" % i, "dismissed", title="y" * 200) for i in range(150)]
        body = sr.build_record(rec(2, "clean", findings=filler + [finding("F1-1", "resolved")]))
        self.assertLessEqual(len(body[body.index("<!--"):]), sr.MAX_RECORD_CHARS)
        r2 = sr.parse_records([comment(body)], BOT)[0]
        self.assertGreater(r2["findings_truncated"], 0)
        state = {f["id"]: f for f in sr.fold_open_set([r1, r2])}
        self.assertEqual(state["F1-1"]["status"], "resolved")
        self.assertEqual(state["F1-1"]["title"], "kept detail")
        self.assertEqual(sr.open_set(list(state.values())), [])

    def test_validate_output_has_a_schema_per_role(self):
        # R3-F7: an empty object, the wrong job's schema, a non-object entry
        # or an unevaluated open finding is malformed.
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        good_find = {"answers": {}, "candidates": [{"key": "k", "title": "t", "file": "a.py", "line": 3}]}
        good_check = {"answers": answers, "checks": [{"key": "k", "outcome": "upheld", "in_scope": True,
                                                         "reachable": True}]}
        self.assertEqual(sr.validate_output(good_find, "find"), [])
        self.assertEqual(sr.validate_output(good_check, "check"), [])
        for bad, role in (({}, "find"), ({}, "check"), (good_check, "find"), (good_find, "check"),
                          ({"answers": {}, "candidates": ["x"]}, "find"),
                          ({"answers": {}, "candidates": [{"key": "k", "title": "t", "file": "a", "line": "3"}]}, "find"),
                          ({"answers": answers, "checks": [{"key": "k", "outcome": "maybe"}]}, "check"),
                          ({"answers": {}, "checks": []}, "check"), ([], "find")):
            self.assertNotEqual(sr.validate_output(bad, role), [], (bad, role))
        # FR-010: every finding open in the round's memory must be evaluated.
        prior = [finding("F1-1"), finding("F1-2", "resolved")]
        self.assertNotEqual(sr.validate_output(good_check, "check", prior), [])
        covered = dict(good_check, checks=good_check["checks"] + [{"id": "F1-1", "outcome": "confirmed"}])
        self.assertEqual(sr.validate_output(covered, "check", prior), [])

    def test_round4_validator_and_settle_hardening(self):
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        # upheld/confirmed without in_scope/reachable is malformed
        bad = {"answers": answers, "checks": [{"key": "k", "outcome": "upheld"}]}
        self.assertNotEqual(sr.validate_output(bad, "check"), [])
        # a confirmed recheck may omit them (settle keeps the previous flags)
        ok = {"answers": answers, "checks": [{"id": "F1-1", "outcome": "confirmed"}]}
        self.assertEqual(sr.validate_output(ok, "check", [finding("F1-1")]), [])
        # duplicate candidate keys are refused
        cand = {"key": "k", "title": "t", "file": "a.py"}
        self.assertNotEqual(sr.validate_output({"answers": {}, "candidates": [cand, dict(cand)]}, "find"), [])
        # an omitted flag keeps the previous value on a recheck
        prior = [dict(finding("F1-1"), in_scope=True, reachable=True)]
        found, _ = sr.process_round(prior, [], [{"id": "F1-1", "outcome": "confirmed"}], 2, "staged")
        self.assertTrue(found[0]["in_scope"] and found[0]["reachable"])

    def test_finalize_records_the_derived_pr_kind(self):
        rec_ = sr.finalize_round({"round": 1, "prior": []}, None, None, None, None, "a" * 40, [], 5,
                                 "b" * 40, "open", pr_kind="board-fix")
        self.assertEqual(rec_["pr_kind"], "board-fix")

    def test_check_agent_schema_matches_the_validator(self):
        # The check agent's --json-schema must ask for exactly what
        # validate_output requires, or a well-meant answer reads incomplete.
        import json
        import re
        import yaml
        wf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workflows",
                               "shared-pr-reviewer.yml")
        wf = yaml.safe_load(open(wf_path, encoding="utf-8"))
        agent = next(s for s in wf["jobs"]["check"]["steps"] if s.get("id") == "agent")
        schema = json.loads(re.search(r"--json-schema '([^']*)'", agent["with"]["claude_args"]).group(1))
        answers = schema["properties"]["answers"]
        self.assertEqual(sorted(answers.get("required") or []), sorted(sr.ANSWER_KEYS))
        for key in sr.ANSWER_KEYS:
            self.assertEqual(sorted(answers["properties"][key]["enum"]), sorted(sr.ANSWER_VALUES))
        outcome = schema["properties"]["checks"]["items"]["properties"]["outcome"]["enum"]
        self.assertEqual(sorted(outcome), sorted(sr.CHECK_OUTCOMES))

    def test_validate_output_cli_refuses_an_empty_object(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "find.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({}, fh)
            self.assertEqual(sr.main(["validate-output", "--input", path, "--role", "find"]), 1)

    def test_finalize_reads_a_malformed_output_as_missing(self):
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        out = sr.finalize_round({"round": 1, "prior": []}, {}, {"checks": [], "answers": answers},
                                {"status": "staged"}, {"type": "issue", "ref": "7"}, "a" * 40, [], 5,
                                "b" * 40, "open")
        self.assertEqual(out["verdict"], "incomplete")

    def test_named_check_also_runs_without_the_fix(self):
        # A3 (FR-008(c)): the named check runs a second time on the merge
        # base with only its own file taken from the PR.
        import tempfile
        with tempfile.TemporaryDirectory() as base:
            box = FakeSandbox({1: {"exit": 0, "output_tail": ""}, 3: {"exit": 1, "output_tail": "fails"},
                               2: {"exit": 0, "output_tail": ""}})
            out = sr.stage_code_run("tree", "rev", ["x/test_fix.py"], timeout=60, sandbox=box, base_tree=base)
            self.assertEqual(out["named_check_without_fix"], {"exit": 1, "output_tail": "fails"})
            self.assertEqual(box.trees[3], (os.path.abspath(base), ["x/test_fix.py"]))
            self.assertEqual(box.trees[1], (None, []))
        # no base tree, or no named check: nothing is run without the fix
        box = FakeSandbox({1: {"exit": 0, "output_tail": ""}, 2: {"exit": 0, "output_tail": ""}})
        out = sr.stage_code_run("tree", "rev", ["x/test_fix.py"], timeout=60, sandbox=box)
        self.assertIsNone(out["named_check_without_fix"])

    def test_a_modified_check_is_the_named_check_when_none_is_added(self):
        # R1: most fixes extend an existing test; added still wins.
        f = sr.named_check_file
        self.assertEqual(f([], ["a/test_old.py"]), "a/test_old.py")
        self.assertEqual(f(["z/test_new.py"], ["a/test_old.py"]), "z/test_new.py")
        self.assertEqual(f(["README.md"], ["b/verify-x.py", "a/fixtures/test_f.py", "specs/1/test_s.py"]),
                         "b/verify-x.py")
        self.assertIsNone(f([], ["-x/test_a.py", "src/mod.py"]))
        import tempfile
        with tempfile.TemporaryDirectory() as base:
            box = FakeSandbox({1: {"exit": 0, "output_tail": ""}, 3: {"exit": 1, "output_tail": "fails"},
                               2: {"exit": 0, "output_tail": ""}})
            out = sr.stage_code_run("tree", "rev", [], timeout=60, sandbox=box, base_tree=base,
                                    modified_files=["x/test_old.py"])
            self.assertEqual(box.trees[3], (os.path.abspath(base), ["x/test_old.py"]))
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        rec_ = sr.finalize_round({"round": 1, "prior": []}, {"answers": {}, "candidates": []},
                                 {"checks": [], "answers": answers}, out, {"type": "issue", "ref": "7"},
                                 "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(rec_["verdict"], "clean")

    def test_a_modified_check_passing_without_the_fix_is_left_to_the_agent(self):
        # N1: a modified check may be the very file the fix changes, so its
        # exit 0 on the overlay tree is no evidence; code decides nothing.
        ok = {"exit": 0, "output_tail": ""}
        mod = {"status": "staged", "named_check": ok, "named_check_tier": "modified",
               "named_check_without_fix": ok}
        answer, why = sr.check_fails_without_fix(mod)
        self.assertIsNone(answer)
        self.assertIn("modified", why)
        self.assertEqual(sr.check_fails_without_fix(dict(mod, named_check_tier="added"))[0], sr.NEGATIVE)
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}

        def finalize(ans):
            return sr.finalize_round({"round": 1, "prior": []}, {"answers": {}, "candidates": []},
                                     {"checks": [], "answers": ans}, mod, {"type": "issue", "ref": "7"},
                                     "a" * 40, [], 5, "b" * 40, "open")
        out = finalize(answers)
        self.assertEqual(out["verdict"], "clean")
        self.assertTrue(any("left to the checking job" in n for n in out["notes"]))
        out = finalize(dict(answers, check_fails_without_fix=sr.NEGATIVE))
        self.assertEqual(out["verdict"], "findings")

    def test_check_fails_without_fix_is_decided_by_code_where_it_can_be(self):
        d = sr.check_fails_without_fix
        ok = {"exit": 0, "output_tail": ""}
        self.assertEqual(d(None)[0], sr.UNDETERMINABLE)
        self.assertEqual(d({"status": "staged", "named_check": None})[0], sr.UNDETERMINABLE)
        self.assertEqual(d({"status": "staged", "named_check": ok})[0], sr.UNDETERMINABLE)
        self.assertEqual(d({"status": "staged", "named_check": ok, "named_check_without_fix": ok})[0],
                         sr.NEGATIVE)
        for code in (124, 127):
            self.assertEqual(d({"status": "staged", "named_check": ok,
                                "named_check_without_fix": {"exit": code}})[0], sr.UNDETERMINABLE)
        self.assertEqual(d({"status": "staged", "named_check": ok, "named_check_without_fix": {"exit": 1}}),
                         (None, None))

    def test_verdict_reads_the_run_without_the_fix(self):
        # SC-005: an added check that passes without the fix is never clean.
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        ok = {"exit": 0, "output_tail": ""}

        def verdict(code_run):
            out = sr.finalize_round({"round": 1, "prior": []}, {"answers": {}, "candidates": []},
                                    {"checks": [], "answers": answers}, code_run, {"type": "issue", "ref": "7"},
                                    "a" * 40, [], 5, "b" * 40, "open")
            return out["verdict"], out["purpose"]["answers"]["check_fails_without_fix"]
        self.assertEqual(verdict({"status": "staged", "named_check": ok, "named_check_without_fix": ok}),
                         ("findings", sr.NEGATIVE))
        self.assertEqual(verdict({"status": "staged", "named_check": ok}), ("undetermined", sr.UNDETERMINABLE))
        self.assertEqual(verdict({"status": "staged", "named_check": ok,
                                  "named_check_without_fix": {"exit": 1, "output_tail": "AssertionError"}}),
                         ("clean", sr.POSITIVE))

    def test_defuse_renames_everything_an_agent_could_load(self):
        # P1: at every depth, whatever the case, and without clobbering a
        # .as-data name the PR already ships.
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            def put(rel, text="x"):
                path = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            put("pr-tree/CLAUDE.md", "orders")
            put("pr-tree/CLAUDE.md.as-data", "shipped by the PR")
            put("pr-tree/.claude/settings.json", "{}")
            put("pr-tree/.claude/skills/x/SKILL.md")
            put("pr-tree/a/b/claude.md")
            put("pr-tree/a/CLAUDE.local.md")
            put("pr-tree/.mcp.json", "{}")
            put("pr-tree/keep/README.md", "kept")
            renamed = sr.defuse_agent_config(root)
            self.assertEqual(sr.agent_config_left(root), [])
            self.assertEqual(len(renamed), 5)
            with open(os.path.join(root, "pr-tree", "CLAUDE.md.as-data"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "shipped by the PR")
            with open(os.path.join(root, "pr-tree", "CLAUDE.md.as-data-2"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "orders")
            self.assertTrue(os.path.isfile(os.path.join(root, "pr-tree", ".claude.as-data", "settings.json")))
            self.assertTrue(os.path.isfile(os.path.join(root, "pr-tree", "keep", "README.md")))
            self.assertEqual(sr.main(["defuse-agent-config", "--root", root]), 0)

    def test_named_check_skips_fixtures_specs_and_dash_paths(self):
        # R3-F9: a fixture or a spec file sorted first is not the change's
        # own check, and no path component may read as an option.
        d = sr.discover_named_check
        self.assertEqual(d(["a/fixtures/x/test_probe.py", "b/test_fix.py"])[-1], "test_fix.py")
        self.assertEqual(d(["specs/127-x/verify-a.py", "z/verify-b.py"]), ["python3", "-I", "z/verify-b.py"])
        self.assertIsNone(d(["-s/test_a.py"]))
        self.assertIsNone(d(["x/--help/verify-a.py"]))
        self.assertIsNone(d(["fixtures/sub/run-tests.sh"]))


class ReviewRound5Fixes(unittest.TestCase):
    def test_defuse_walks_into_the_renamed_claude_directory(self):
        # Round 5, finding 1: a .claude/ that holds its own CLAUDE.md,
        # .mcp.json or .claude/ is defused all the way down, so a PR that
        # adds one does not end its round incomplete.
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            for rel in ("pr-tree/.claude/skills/x/CLAUDE.md", "pr-tree/.claude/.mcp.json",
                        "pr-tree/.claude/.claude/settings.json"):
                path = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("x")
            renamed = sr.defuse_agent_config(root)
            self.assertEqual(sr.agent_config_left(root), [])
            self.assertEqual(len(renamed), 4)
            top = os.path.join(root, "pr-tree", ".claude.as-data")
            self.assertTrue(os.path.isfile(os.path.join(top, "skills", "x", "CLAUDE.md.as-data")))
            self.assertTrue(os.path.isfile(os.path.join(top, ".claude.as-data", "settings.json")))
            self.assertEqual(sr.main(["defuse-agent-config", "--root", root]), 0)

    def test_a_recheck_cannot_dismiss_an_open_finding(self):
        # Round 5, finding 5: FR-010 lets a re-check confirm or resolve an
        # open finding, never dismiss it, so that output is malformed and
        # the round is incomplete rather than the answer silently ignored.
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        prior = [finding("F1-1")]
        bad = {"answers": answers, "checks": [{"id": "F1-1", "outcome": "dismissed", "reason": "r"}]}
        self.assertTrue(any("dismisses open finding F1-1" in p for p in sr.validate_output(bad, "check", prior)))
        ok = {"answers": answers, "checks": [{"id": "F1-1", "outcome": "confirmed"},
                                             {"key": "k", "outcome": "dismissed", "reason": "r"}]}
        self.assertEqual(sr.validate_output(ok, "check", prior), [])
        self.assertEqual(sr.validate_output(
            {"answers": answers, "checks": [{"id": "F1-1", "outcome": "dismissed", "reason": "r"}]},
            "check", [finding("F1-1", "resolved", reason="x")]), [])
        staged = {"status": "staged", "named_check": None}
        out = sr.finalize_round({"round": 2, "prior": prior}, {"answers": {}, "candidates": []}, bad,
                                staged, {"type": "issue", "ref": "7"}, "a" * 40, [], 5, "b" * 40, "open")
        self.assertEqual(out["verdict"], "incomplete")

    def test_file_lists_are_nul_separated_and_never_quoted(self):
        # Round 5, finding 3: prepare writes `git diff -z --name-only`, so a
        # non-ASCII or spaced path arrives as itself and can be the check.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "modified-files.txt")
            with open(path, "wb") as fh:
                fh.write("tests/test_ü.py\0a b/README.md\0".encode("utf-8"))
            self.assertEqual(sr.read_path_list(path), ["tests/test_ü.py", "a b/README.md"])
            self.assertEqual(sr.named_check_file([], sr.read_path_list(path)), "tests/test_ü.py")

    def test_with_more_than_one_candidate_a_passing_added_check_is_not_determinable(self):
        # Round 5, finding 2: only the first candidate runs, so an added one
        # passing without the fix says nothing about the others: not
        # determinable, never negative, and never clean on the agent's say-so.
        self.assertEqual(sr.named_check_candidates(["z/test_new.py", "a/test_x.py"], ["b/verify-y.py", "c.md"]),
                         ["a/test_x.py", "z/test_new.py", "b/verify-y.py"])
        import tempfile
        ok = {"exit": 0, "output_tail": ""}
        answers = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}
        for added, modified in ((["x/test_weak.py", "x/test_fix.py"], []), (["x/test_weak.py"], ["x/test_old.py"])):
            with tempfile.TemporaryDirectory() as base:
                box = FakeSandbox({1: ok, 3: ok, 2: ok})
                out = sr.stage_code_run("tree", "rev", added, timeout=60, sandbox=box, base_tree=base,
                                        modified_files=modified)
            self.assertEqual(out["named_check_file"], sorted(added)[0])
            self.assertEqual(out["named_check_tier"], "added")
            answer, why = sr.check_fails_without_fix(out)
            self.assertEqual(answer, sr.UNDETERMINABLE)
            self.assertIn("2 files could be", why)
            self.assertEqual(sr.check_fails_without_fix(dict(out, named_check_without_fix={"exit": 124}))[0],
                             sr.UNDETERMINABLE)
            self.assertEqual(sr.check_fails_without_fix(dict(out, named_check_without_fix={"exit": 1})),
                             (None, None))
            rec_ = sr.finalize_round({"round": 1, "prior": []}, {"answers": {}, "candidates": []},
                                     {"checks": [], "answers": answers}, out, {"type": "issue", "ref": "7"},
                                     "a" * 40, [], 5, "b" * 40, "open")
            self.assertEqual(rec_["purpose"]["answers"]["check_fails_without_fix"], sr.UNDETERMINABLE)
            self.assertEqual(rec_["verdict"], "undetermined")
        # one candidate: an added check passing without the fix is still negative (SC-005)
        with tempfile.TemporaryDirectory() as base:
            out = sr.stage_code_run("tree", "rev", ["x/test_fix.py"], timeout=60,
                                    sandbox=FakeSandbox({1: ok, 3: ok, 2: ok}), base_tree=base)
        self.assertEqual(sr.check_fails_without_fix(out)[0], sr.NEGATIVE)



def _round(state, find_out, check_out, dismissals=()):
    ok = {"exit": 0, "output_tail": ""}
    code_run = {"status": "staged", "named_check": ok, "named_check_tier": "added",
                "named_check_without_fix": {"exit": 1, "output_tail": "AssertionError"}, "gate_suite": ok}
    return sr.finalize_round(state, find_out, check_out, code_run, {"type": "issue", "ref": "7"},
                             "a" * 40, list(dismissals), 5, "b" * 40, "open")


class Round6Fixes(unittest.TestCase):
    ANSWERS = {k: sr.POSITIVE for k in sr.ANSWER_KEYS}

    def test_a_candidate_with_no_check_makes_the_round_incomplete(self):
        # Round 6, finding 1: FR-010 asks the checking job to evaluate every
        # candidate; one it leaves out used to be dismissed as "checker did
        # not uphold", so a real defect could end the round clean.
        cand = {"key": "k", "title": "t", "file": "a.py", "line": 1,
                "failing_case": {"state": "s", "wrong_result": "w"}}
        find_out = {"answers": {}, "candidates": [cand]}
        unchecked = {"answers": self.ANSWERS, "checks": []}
        self.assertEqual(sr.validate_output(unchecked, "check", [], [cand]),
                         ["candidate 'k' was not evaluated (FR-010)"])
        self.assertEqual(_round({"round": 1, "prior": []}, find_out, unchecked)["verdict"], "incomplete")
        checked = {"answers": self.ANSWERS, "checks": [{"key": "k", "outcome": "dismissed", "reason": "no"}]}
        self.assertEqual(sr.validate_output(checked, "check", [], [cand]), [])
        self.assertEqual(_round({"round": 1, "prior": []}, find_out, checked)["verdict"], "clean")


    def test_the_next_round_is_past_the_highest_and_never_reuses_ids(self):
        # Round 6, finding 3: with round 1's record no longer confirming,
        # the count gives round 2 again, and F2-1 would be overwritten.
        self.assertEqual(sr.next_round([]), 1)
        self.assertEqual(sr.next_round([rec(2), rec(3)]), 4)
        prior = [finding("F2-1", title="kept")]
        cand = {"key": "k", "title": "new", "file": "a.py", "line": 1,
                "failing_case": {"state": "s", "wrong_result": "w"}}
        check = {"answers": self.ANSWERS, "checks": [{"id": "F2-1", "outcome": "confirmed"},
                                                     {"key": "k", "outcome": "upheld", "in_scope": True,
                                                      "reachable": True}]}
        out = _round({"round": 2, "prior": prior}, {"answers": {}, "candidates": [cand]}, check)
        self.assertEqual(out["verdict"], "incomplete")
        self.assertEqual([(f["id"], f["title"]) for f in out["open_set"]], [("F2-1", "kept")])
        self.assertTrue(any("reuse the ids" in n for n in out["notes"]))
        out = _round({"round": 3, "prior": prior}, {"answers": {}, "candidates": [cand]}, check)
        self.assertEqual(sorted(f["id"] for f in out["open_set"]), ["F2-1", "F3-1"])


    def test_dismissals_that_are_not_json_or_not_id_and_reason_refuse_the_run(self):
        # Round 6, finding 4: they used to read as [] at finalize, so the
        # requested dismissal was dropped and the finding stayed open.
        import contextlib
        import io
        import json as _json

        def decide(text):
            buf = io.StringIO()
            argv = ["guard", "--ref", "refs/heads/main", "--default-branch", "main", "--kind", "fix"]
            with contextlib.redirect_stdout(buf):
                self.assertEqual(sr.main(argv + ([] if text is None else ["--dismissals", text])), 0)
            return _json.loads(buf.getvalue())
        for text in ('[{"id": "F1-1", "reason": "ok"}', '{"id": "F1-1"}', '[{"id": "F1-1"}]', '["F1-1"]'):
            out = decide(text)
            self.assertFalse(out["proceed"], text)
            self.assertTrue(out["reason"].startswith("refused: dismissals")
                            or out["reason"].startswith("refused: each dismissal"), out)
        for text in (None, "", "[]", '[{"id": "F1-1", "reason": "ok"}]'):
            self.assertEqual(decide(text), {"proceed": True, "reason": None}, text)


    def test_a_candidate_check_upholds_or_dismisses_it_once(self):
        # Pass 1 of #1219's review: a check that "confirms" a new candidate
        # (the word the prompt gives re-checks), or answers it twice, used
        # to validate, and process_round dismissed it, so the round with a
        # real defect ended clean.
        cand = {"key": "k", "title": "t", "file": "a.py", "line": 1,
                "failing_case": {"state": "s", "wrong_result": "w"}}
        find_out = {"answers": {}, "candidates": [cand]}
        upheld = {"key": "k", "outcome": "upheld", "in_scope": True, "reachable": True, "reason": "real"}
        for checks in ([dict(upheld, outcome="confirmed")], [dict(upheld, outcome="resolved")],
                       [upheld, {"key": "k", "outcome": "dismissed", "reason": "no"}]):
            check = {"answers": self.ANSWERS, "checks": checks}
            self.assertTrue(sr.validate_output(check, "check", [], [cand]), checks)
            self.assertEqual(_round({"round": 1, "prior": []}, find_out, check)["verdict"], "incomplete", checks)
        # A re-check of an earlier finding still confirms it by id.
        prior = [finding("F1-1")]
        check = {"answers": self.ANSWERS, "checks": [upheld, {"id": "F1-1", "outcome": "confirmed"}]}
        self.assertEqual(sr.validate_output(check, "check", prior, [cand]), [])

    def test_the_state_command_numbers_the_round_past_the_highest(self):
        # Pass 1 of #1219's review: only next_round() itself was tested, so
        # the state command could go back to len(confirmed) + 1 unnoticed.
        import contextlib
        import io
        import json as _json
        from unittest import mock
        buf = io.StringIO()
        # state reads earlier rounds' runs with RUN_TOKEN and fails closed
        # without it (#1240).
        with mock.patch.object(sr, "confirmed_from_github", return_value=[rec(2), rec(3)]), \
                mock.patch.dict(os.environ, {"RUN_TOKEN": "run"}), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(sr.main(["state", "--pr", "7", "--bot-login", "b[bot]", "--default-branch", "main",
                                      "--repository", "o/r"]), 0)
        out = _json.loads(buf.getvalue())
        self.assertEqual((out["rounds"], out["round"]), (2, 4))

    def test_null_dismissals_refuse_the_run(self):
        # Pass 1 of #1219's review: null is not a list (round-record.md),
        # but parsed to None, which the guard reads as "not given".
        self.assertEqual(sr.parse_dismissals("null"), (None, "refused: dismissals is not a list"))
        self.assertEqual(sr.parse_dismissals("[]"), ([], None))

    def test_a_dismissals_value_starting_with_a_dash_refuses_from_the_environment(self):
        # Pass 2 of #1219's review: as an argument, "-x" is read by argparse
        # as an option and the guard exits 2, failing prepare instead of
        # refusing in the summary; the workflow passes --dismissals-env
        # (verify-shared-review-wiring.py checks that form).
        import contextlib
        import io
        import json as _json
        from unittest import mock
        argv = ["guard", "--ref", "refs/heads/main", "--default-branch", "main", "--kind", "fix"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            sr.main(argv + ["--dismissals", "-x"])

        def decide(env):
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(buf):
                self.assertEqual(sr.main(argv + ["--dismissals-env", "WC_TEST_DISMISSALS"]), 0)
            return _json.loads(buf.getvalue())
        self.assertEqual(decide({"WC_TEST_DISMISSALS": "-x"}),
                         {"proceed": False, "reason": "refused: dismissals is not valid JSON"})
        self.assertEqual(decide({"WC_TEST_DISMISSALS": "[]"}), {"proceed": True, "reason": None})
        self.assertEqual(decide({"WC_TEST_DISMISSALS": '[{"id": "F1-1", "reason": "ok"}]'}),
                         {"proceed": True, "reason": None})

    def test_the_gate_suite_has_its_own_limit(self):
        # Round 6, finding 5: the suite took 361 s on 4 CPUs, so it no
        # longer shares the named check's 600 s.
        import tempfile
        self.assertGreater(sr.GATE_SUITE_TIMEOUT, sr.CODE_RUN_TIMEOUT)
        ok = {"exit": 0, "output_tail": ""}
        with tempfile.TemporaryDirectory() as base:
            box = FakeSandbox({1: ok, 3: ok, 2: ok})
            sr.stage_code_run("tree", "rev", ["x/test_fix.py"], sandbox=box, base_tree=base)
        self.assertEqual({n: t for _, t, n in box.ran},
                         {1: sr.CODE_RUN_TIMEOUT, 3: sr.CODE_RUN_TIMEOUT, 2: sr.GATE_SUITE_TIMEOUT})


if __name__ == "__main__":
    unittest.main()
