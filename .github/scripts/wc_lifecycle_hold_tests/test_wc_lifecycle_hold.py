import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wc_lifecycle_hold as h  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "fixtures", "lifecycle-hold")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def proc(rc=0, err=""):
    return types.SimpleNamespace(returncode=rc, stdout="", stderr=err)


class CheckTests(unittest.TestCase):
    def test_clear(self):
        reader = lambda i, r: h.parse_labels(fixture("labels-clear.json"))
        self.assertEqual(h.check(1, reader=reader), "clear")

    def test_held(self):
        reader = lambda i, r: h.parse_labels(fixture("labels-held.json"))
        self.assertEqual(h.check(1, reader=reader), "held")

    def test_custom_label(self):
        reader = lambda i, r: h.parse_labels(fixture("labels-custom.json"))
        self.assertEqual(h.check(1, hold_label="paused:x", reader=reader), "held")
        self.assertEqual(h.check(1, reader=reader), "clear")

    def test_unreadable_on_failure(self):
        def reader(i, r):
            raise ValueError("boom")
        self.assertEqual(h.check(1, reader=reader), "unreadable")

    def test_unreadable_on_garbage(self):
        reader = lambda i, r: h.parse_labels("not json")
        self.assertEqual(h.check(1, reader=reader), "unreadable")

    def test_parse_labels_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            h.parse_labels(json.dumps({"nolabels": []}))


class SetTests(unittest.TestCase):
    def run_set(self, labels_fixture):
        calls = []

        def runner(args):
            calls.append(args)
            return proc()
        reader = lambda i, r: h.parse_labels(fixture(labels_fixture))
        out = h.set_hold(1, "why", reader=reader, runner=runner)
        return out, calls

    def test_set_adds_label_and_comments(self):
        out, calls = self.run_set("labels-clear.json")
        self.assertEqual(out, "true")
        self.assertTrue(any(c[:2] == ["issue", "edit"] for c in calls))
        self.assertTrue(any(c[:2] == ["issue", "comment"] for c in calls))

    def test_set_twice_is_idempotent_but_still_comments(self):
        out, calls = self.run_set("labels-held.json")
        self.assertEqual(out, "already")
        self.assertFalse(any(c[:2] == ["issue", "edit"] for c in calls))
        self.assertTrue(any(c[:2] == ["issue", "comment"] for c in calls))

    def test_set_custom_label(self):
        calls = []
        runner = lambda a: calls.append(a) or proc()
        reader = lambda i, r: []
        h.set_hold(1, "why", hold_label="paused:x", reader=reader, runner=runner)
        edit = [c for c in calls if c[:2] == ["issue", "edit"]][0]
        self.assertIn("paused:x", edit)

    def test_add_failure_raises(self):
        runner = lambda a: proc(1, "no") if a[:2] == ["issue", "edit"] else proc()
        with self.assertRaises(RuntimeError):
            h.set_hold(1, "why", reader=lambda i, r: [], runner=runner)

    def test_empty_reason_still_posts_nonempty_comment(self):
        calls = []
        runner = lambda a: calls.append(a) or proc()
        h.set_hold(1, "", reader=lambda i, r: [], runner=runner)
        comment = [c for c in calls if c[:2] == ["issue", "comment"]][0]
        self.assertTrue(comment[comment.index("--body") + 1].strip())

    def test_label_create_failure_raises(self):
        runner = lambda a: proc(1, "no") if a[:2] == ["label", "create"] else proc()
        with self.assertRaises(RuntimeError):
            h.set_hold(1, "why", reader=lambda i, r: [], runner=runner)


class MessageTests(unittest.TestCase):
    def test_unreadable_message_distinct_from_hold(self):
        self.assertIn("labels could not be read", h.UNREADABLE_MESSAGE)
        self.assertIn("dispatch implement by hand", h.UNREADABLE_MESSAGE)


if __name__ == "__main__":
    unittest.main()
