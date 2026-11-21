import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wc_lifecycle_hold as h  # noqa: E402


def plan(**kw):
    base = dict(issue_state="open", labels=[], branch_exists=True,
                spec_stage="tasks", recorded_iteration=1, spec_dir="specs/1-x")
    base.update(kw)
    return h.release_plan(**base)


class ReleasePlanTests(unittest.TestCase):
    def test_due_tasks_stage(self):
        p = plan()
        self.assertTrue(p["due"])
        self.assertEqual(p["iteration"], 2)

    def test_due_implement_stage(self):
        self.assertTrue(plan(spec_stage="implement")["due"])

    def test_closed(self):
        self.assertEqual(plan(issue_state="closed")["reason"], "issue-not-open")

    def test_parked(self):
        self.assertEqual(plan(labels=["parked"])["reason"], "parked")

    def test_stalled(self):
        self.assertEqual(plan(labels=["stage:stalled"])["reason"], "stalled")

    def test_no_branch(self):
        self.assertEqual(plan(branch_exists=False)["reason"], "no-spec-branch")

    def test_stage_not_ready(self):
        p = plan(spec_stage="plan")
        self.assertFalse(p["due"])
        self.assertIsNone(p["iteration"])
        self.assertEqual(p["reason"], "stage-not-ready")


if __name__ == "__main__":
    unittest.main()
