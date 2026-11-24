#!/usr/bin/env python3
"""Report-only comparison (specs/127-shared-pr-reviewer, FR-029, SC-007).

Lists, per fix PR, the shared reviewer's latest confirmed round and the
hand-review comment (review-until-clean's record) that cover the same head,
so the owner can compare the two before deciding when the report-only
period ends. Reads only; the review-until-clean skill is not changed.

usage: shared_review_compare.py <comments.json> <confirmed.json>
  comments.json   the PR's issue comments (REST shape)
  confirmed.json  confirmed round records (`wc_shared_review.py state` .confirmed)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_session_record  # noqa: E402


def hand_reviews(comments):
    """(head_sha, record) for each review-until-clean pass comment. The
    head a pass covers is the one it started from and reviewed (`started`,
    the review-until-clean skill's H(n-1)); a commit it then pushed is the
    next pass's subject, never this one's."""
    out = []
    for comment in comments or []:
        try:
            rec = wc_session_record.read((comment or {}).get("body") or "")
        except wc_session_record.RecordError:
            continue
        if rec and rec.get("kind") == "review":
            out.append((rec.get("started"), rec))
    return out


def compare(comments, confirmed):
    """One row per head either side covers: {head, shared, hand}. `shared`
    is the highest confirmed round at that head (verdict, round), `hand`
    the latest pass (verdict, pass), either may be None."""
    rows = {}
    for rec in confirmed or []:
        row = rows.setdefault(rec.get("head_sha"), {"head": rec.get("head_sha"), "shared": None, "hand": None})
        rnd = rec.get("round") or 0
        if row["shared"] is None or rnd > (row["shared"]["round"] or 0):
            row["shared"] = {"round": rec.get("round"), "verdict": rec.get("verdict")}
    for head, rec in hand_reviews(comments):
        for key in rows:
            if head and key and (key.startswith(head) or head.startswith(key)):
                head = key
                break
        row = rows.setdefault(head, {"head": head, "shared": None, "hand": None})
        row["hand"] = {"pass": rec.get("pass"), "verdict": rec.get("verdict")}
    return sorted(rows.values(), key=lambda r: str(r["head"]))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        comments = json.load(fh)
    with open(argv[1], encoding="utf-8") as fh:
        confirmed = json.load(fh)
    if isinstance(confirmed, dict):  # the whole `state` object: take .confirmed
        confirmed = confirmed.get("confirmed") or []
    confirmed = [r for r in confirmed if isinstance(r, dict)]
    for row in compare(comments, confirmed):
        print("{0}\tshared: {1}\thand: {2}".format(
            str(row["head"])[:7], row["shared"] or "-", row["hand"] or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
