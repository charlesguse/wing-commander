"""Fixtures for shared_review_compare (specs/127, FR-029, SC-007)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import shared_review_compare as cmp  # noqa: E402
import wc_session_record  # noqa: E402

HEAD = "a" * 40


class Compare(unittest.TestCase):
    def fake_read(self, body):
        if body == "boom":
            raise wc_session_record.RecordError(["bad"])
        if body.startswith("review"):
            return {"kind": "review", "pass": 2, "verdict": "clean", "started": "aaaaaaa", "pushed": None}
        return None

    def test_same_head_lists_both_sides(self):
        confirmed = [{"round": 1, "head_sha": HEAD, "verdict": "findings"},
                     {"round": 2, "head_sha": HEAD, "verdict": "clean"}]
        comments = [{"body": "review"}, {"body": "unrelated"}, {"body": "boom"}]
        with mock.patch.object(wc_session_record, "read", self.fake_read):
            rows = cmp.compare(comments, confirmed)
        self.assertEqual(rows, [{"head": HEAD, "shared": {"round": 2, "verdict": "clean"},
                                 "hand": {"pass": 2, "verdict": "clean"}}])

    def test_one_sided_rows(self):
        with mock.patch.object(wc_session_record, "read", self.fake_read):
            rows = cmp.compare([{"body": "review"}], [{"round": 1, "head_sha": "b" * 40, "verdict": "clean"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["shared"] is None for r in rows), [False, True])


    def test_main_takes_the_whole_state_object(self):
        # Round 4: `wc_shared_review.py state` output is a dict whose
        # `confirmed` key holds the records; main must not crash on it.
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            comments, state = os.path.join(d, "c.json"), os.path.join(d, "s.json")
            with open(comments, "w", encoding="utf-8") as fh:
                json.dump([], fh)
            with open(state, "w", encoding="utf-8") as fh:
                json.dump({"rounds": 1, "confirmed": [{"round": 1, "head_sha": HEAD, "verdict": "clean"}]}, fh)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cmp.main([comments, state]), 0)
        self.assertIn("aaaaaaa", out.getvalue())


if __name__ == "__main__":
    unittest.main()
