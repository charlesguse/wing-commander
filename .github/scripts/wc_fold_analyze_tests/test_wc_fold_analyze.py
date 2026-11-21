import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wc_fold_analyze as fa  # noqa: E402

DIFF = """--- a/tasks.md
+++ b/tasks.md
@@ -1,0 +2,2 @@
+- [ ] Review finding: add a cache
+- [ ] Review finding: drop the gate
"""
CONST = "## Core Principles\n### I. Tests First\n### II. Public Repo\n## Other\n"


def inp(diff=DIFF):
    return fa.build_input("a", "b", diff, "spec", CONST)


def obj(task="Review finding: drop the gate", conflict=True, principle="I. Tests First"):
    return {"task": task, "constitution_conflict": conflict,
            "principle": principle, "reasoning": "why"}


class FoldAnalyzeTests(unittest.TestCase):
    def test_added_tasks_only_additions(self):
        ids = [t["id"] for t in inp()["added_tasks"]]
        self.assertEqual(ids, ["Review finding: add a cache",
                               "Review finding: drop the gate"])

    def test_no_tasks_diff(self):
        self.assertEqual(inp("")["added_tasks"], [])

    def test_principles(self):
        self.assertEqual(inp()["principles"], ["I. Tests First", "II. Public Repo"])

    def test_hold(self):
        r = fa.decide(inp(), {"objections": [obj()]})
        self.assertTrue(r["hold"])
        self.assertEqual(r["status"], "ok")

    def test_record_only(self):
        r = fa.decide(inp(), {"objections": [obj(conflict=False, principle=None)]})
        self.assertFalse(r["hold"])
        self.assertEqual(len(r["recorded_items"]), 1)

    def test_malformed(self):
        self.assertEqual(fa.decide(inp(), {"nope": 1})["status"], "malformed")
        bad = fa.decide(inp(), {"objections": [{"task": "x"}]})
        self.assertEqual(bad["status"], "malformed")
        self.assertFalse(bad["hold"])

    def test_one_malformed_keeps_valid_hold(self):
        r = fa.decide(inp(), {"objections": [{"task": "x"}, obj()]})
        self.assertTrue(r["hold"])
        self.assertEqual(r["status"], "malformed")

    def test_non_fold_added_lines_excluded(self):
        diff = DIFF + "+- [ ] T001 reworded base task\n"
        ids = [t["id"] for t in inp(diff)["added_tasks"]]
        self.assertNotIn("T001 reworded base task", ids)

    def test_unknown_principle(self):
        r = fa.decide(inp(), {"objections": [obj(principle="IX. Invented")]})
        self.assertFalse(r["hold"])

    def test_task_not_in_fold(self):
        r = fa.decide(inp(), {"objections": [obj(task="Earlier task")]})
        self.assertFalse(r["hold"])

    def test_agent_failed(self):
        r = fa.decide(inp(), None)
        self.assertEqual(r["status"], "agent-failed")
        self.assertFalse(r["hold"])

    def test_first_attempt(self):
        self.assertTrue(fa.is_first_attempt("1"))
        self.assertFalse(fa.is_first_attempt("2"))
        self.assertFalse(fa.is_first_attempt("x"))


if __name__ == "__main__":
    unittest.main()
