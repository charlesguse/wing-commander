import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wc_fold_drop as d  # noqa: E402

TASKS = """- [ ] T001 base
- [ ] Review finding: add a cache
- [x] Review finding: done already
- [ ] Review finding: same
- [ ] Review finding: same
"""


def run(titles, assoc="OWNER"):
    return d.apply(TASKS, titles, assoc, 42)


class DropTests(unittest.TestCase):
    def test_parse(self):
        p = d.parse("Drop:\n- Review finding: a\n- [ ] Recurring review finding: b\n")
        self.assertEqual(p["titles"], ["Review finding: a", "Recurring review finding: b"])

    def test_parse_not_drop(self):
        self.assertIsNone(d.parse("stop"))
        self.assertIsNone(d.parse("> drop\nhello"))
        self.assertIsNone(d.parse("please drop it"))

    def test_removed(self):
        text, out, msg, _ = run(["Review finding: add a cache"])
        self.assertEqual(out["Review finding: add a cache"], "removed")
        self.assertNotIn("add a cache", text)
        self.assertIn("Wing-Commander-Drop: 42", msg)

    def test_unknown(self):
        self.assertEqual(run(["Review finding: nope"])[1]["Review finding: nope"], "unknown")

    def test_not_fold_task(self):
        self.assertEqual(run(["T001 base"])[1]["T001 base"], "not-fold-task")

    def test_already_checked(self):
        t = "Review finding: done already"
        text, out, msg, _ = run([t])
        self.assertEqual(out[t], "already-checked")
        self.assertEqual(text, TASKS)
        self.assertEqual(msg, "")

    def test_parse_accepts_non_fold_title(self):
        p = d.parse("drop\n- T012 some task\n")
        self.assertEqual(p["titles"], ["T012 some task"])

    def test_not_fold_task_via_parse(self):
        t = d.parse("drop\n- plain title\n")["titles"][0]
        _, out, _, _ = run([t])
        self.assertEqual(out[t], "not-fold-task")

    def test_already_absent(self):
        t = "Review finding: gone before"
        _, out, _, _ = d.apply(TASKS, [t], "OWNER", 42, dropped_titles=(t,))
        self.assertEqual(out[t], "already-absent")
        _, out2, _, _ = run([t])
        self.assertEqual(out2[t], "unknown")

    def test_non_maintainer(self):
        text, out, msg, _ = run(["Review finding: add a cache"], "NONE")
        self.assertEqual(out, {"*": "non-maintainer"})
        self.assertEqual(text, TASKS)

    def test_task_body_removed_with_title(self):
        tasks = ("- [ ] Review finding: a\n\n  Body para.\n\n  - file.py\n\n"
                 "  Detail: x\n\n- [ ] T002 keep\n")
        text, out, _, _ = d.apply(tasks, ["Review finding: a"], "OWNER", 1)
        self.assertEqual(out["Review finding: a"], "removed")
        self.assertEqual(text, "\n- [ ] T002 keep\n")
        self.assertNotIn("Body", text)

    def test_same_titled_both_removed(self):
        text, out, _, _ = run(["Review finding: same"])
        self.assertEqual(out["Review finding: same"], "removed")
        self.assertNotIn("same", text)


if __name__ == "__main__":
    unittest.main()
