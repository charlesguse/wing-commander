"""Fixture tests for decide.py: python3 -I test_decide.py"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decide  # noqa: E402


def finding(category, **kw):
    f = {"severity": "high", "category": category, "fold_task": "T031",
         "location": "tasks.md:10", "principle": "", "detail": "d"}
    f.update(kw)
    return f


def run(findings, tasks=1):
    return decide.decide("round-3", tasks, json.dumps({"findings": findings}), False)


class DecideTests(unittest.TestCase):
    def test_constitution_conflict_holds_and_names_task_and_principle(self):
        r = run([finding("constitution-conflict", principle="Principle II")])
        self.assertEqual(r["decision"], "hold")
        self.assertEqual(r["hold-reason"], "constitution-conflict")
        self.assertIn("T031", r["question-markdown"])
        self.assertIn("Principle II", r["question-markdown"])
        self.assertIn("<!-- wing-commander-fold-hold: fold=round-3 -->", r["question-markdown"])

    def test_inconsistency_only_dispatches_with_report(self):
        r = run([finding("inconsistency")])
        self.assertEqual(r["decision"], "dispatch")
        self.assertIn("T031", r["report-markdown"])
        self.assertEqual(r["question-markdown"], "")

    def test_duplication_dispatches(self):
        self.assertEqual(run([finding("duplication")])["decision"], "dispatch")

    def test_no_findings_dispatches(self):
        self.assertEqual(run([])["decision"], "dispatch")

    def test_malformed_json_holds_analyze_failed(self):
        r = decide.decide("x", 1, "not json", False)
        self.assertEqual((r["decision"], r["hold-reason"]), ("hold", "analyze-failed"))

    def test_bad_category_holds_analyze_failed(self):
        r = run([finding("bogus")])
        self.assertEqual(r["hold-reason"], "analyze-failed")

    def test_failed_step_holds(self):
        r = decide.decide("x", 1, "{}", True)
        self.assertEqual(r["hold-reason"], "analyze-failed")

    def test_empty_fold_section_skipped(self):
        self.assertEqual(run([], tasks=0)["decision"], "skipped")


if __name__ == "__main__":
    unittest.main()
