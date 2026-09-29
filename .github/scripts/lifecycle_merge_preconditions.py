#!/usr/bin/env python3
"""Lifecycle review gate merge preconditions (specs/062-lifecycle-review-gate,
contracts/readiness-and-merge.md, data-model.md "Merge Preconditions").

WHY THIS EXISTS
---------------
Auto-merge (US4) is off by default and, when a maintainer switches it on,
it merges only a lifecycle PR whose review came back clean at the exact
head SHA about to be merged. Every condition is re-derived against a
freshly fetched snapshot at merge time -- never the `review` job's own
earlier evaluation, because the head SHA may have moved since (spec.md
Edge Cases: "the head SHA moves mid-round").

`evaluate_from_snapshot()` is the pure decision, fixturable without a live
`gh` call; `evaluate()` is the runtime wrapper that fetches both snapshots.

CONDITION 4'S POLARITY (a deliberate, documented departure from
contracts/readiness-and-merge.md's literal wording)
---------------------------------------------------
The contract says merge re-derives "every lifecycle_readiness.py condition
above" -- which includes readiness condition 4, `not_yet_reviewed`
(`review_gate.head_sha != head_sha`) -- AND, as condition 6, that
`review_gate.head_sha == head_sha`. Those two are exact negations of each
other, so a literal conjunction of all eight can never be true and the
contract's own fixture 3 ("readiness holds, round clean, no human review ->
may_merge: true") would be unsatisfiable. The contract's fixture 4 shows
the intent: a moved head SHA must fail and must name the stale round
rather than a merge-specific "round not clean". So condition 4 is
evaluated here in its merge-context polarity -- `reviewed_at_this_head`,
the inversion of readiness's `not_yet_reviewed` -- and the contract's
condition 6 keeps only its outcome half (`round_clean`). The other four
readiness conditions are taken verbatim from lifecycle_readiness.py's own
decision, never re-derived here.

`reviewed_at_this_head` AND WHERE `review_gate` NOW LIVES (T074/F3)
--------------------------------------------------------------
`review_gate` used to be a field `disposition` committed to the reviewed
PR's own branch, so `evaluate()` here had to peel the fresh head back past
that gate's own trailing "review-gate: round ..." commit(s)
(`wc_review_gate_settled_head.settled_head`, T069) before comparing --
without it, a round that just came back clean would always look "not yet
reviewed at this exact head", because the recording push itself moved the
head. T074 moved `review_gate` off the PR branch entirely, onto the
lifecycle issue's own marker comment (`wc_lifecycle_review_marker.py`):
nothing this gate does ever commits to the reviewed branch, so the head
this script compares against never moves on its own account, and no
peeling is needed or performed (T075 deleted `wc_review_gate_settled_head.py`
along with the security hole its subject-only peel was: anyone who could
push to the branch could forge a "review-gate: round ..." commit subject
and have their own code peeled away as if it were this gate's own
bookkeeping).
"""
import json
import subprocess
import sys

from lifecycle_readiness import evaluate_from_snapshot as _readiness

# In the order unmet_reason names them (contracts/readiness-and-merge.md
# "Conditions"; data-model.md §5).
CONDITIONS = ("checks_green", "gate_suite_green", "mergeable",
              "reviewed_at_this_head", "kill_switch_clear", "round_clean",
              "no_open_findings", "no_unresolved_human_review")

# A review state that neither clears nor raises a reviewer's standing
# verdict: GitHub keeps a CHANGES_REQUESTED standing until the SAME
# reviewer approves or dismisses it, and a plain comment does neither.
_NEUTRAL_REVIEW_STATES = ("COMMENTED", "PENDING")


def _same_identity(login, bot_login):
    """`gh pr view --json reviews` reports an App's review author as the
    bare slug, while the App's own commits and tokens spell it
    `<slug>[bot]` -- normalise both sides rather than depending on which
    spelling a caller happened to thread through."""
    def norm(value):
        value = (value or "").strip().lower()
        return value[:-len("[bot]")] if value.endswith("[bot]") else value
    return bool(login) and norm(login) == norm(bot_login)


def _no_unresolved_human_review(reviews, bot_login):
    """FR-026/US4 scenario 4: any CHANGES_REQUESTED review whose author is
    not this App's own bot identity blocks the merge, until that same
    reviewer approves or dismisses it."""
    standing = {}
    for review in reviews or []:
        login = ((review.get("author") or {}).get("login") or "")
        if not login or _same_identity(login, bot_login):
            continue
        state = (review.get("state") or "").upper()
        if state in _NEUTRAL_REVIEW_STATES or not state:
            continue
        standing[login] = state
    return not any(state == "CHANGES_REQUESTED" for state in standing.values())


def evaluate_from_snapshot(snapshot, review_gate, kill_switch_paused,
                           reviews, bot_login):
    """snapshot: the `gh pr view --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus` shape, fetched
    fresh by the caller. review_gate: the lifecycle issue's own marker
    dict (wc_lifecycle_review_marker.read_marker(), or {}/None before any
    round has run). reviews: the `gh pr view --json reviews` list.
    bot_login: this App's own bot identity login, whose reviews never
    block its own merge. Returns the MergePreconditions dict
    (data-model.md §5), eight conditions evaluated in order, unmet_reason
    naming the first failing condition's own name."""
    head_sha = snapshot.get("headRefOid")
    review_gate = review_gate or {}

    readiness = _readiness(snapshot, review_gate, kill_switch_paused)

    values = {
        "checks_green": readiness["checks_green"],
        "gate_suite_green": readiness["gate_suite_green"],
        "mergeable": readiness["mergeable"],
        # The merge-context polarity of readiness condition 4 -- see this
        # module's own docstring for why it is inverted here. review_gate
        # never lives on the reviewed branch (T074), so nothing this gate
        # does ever moves `head_sha` on its own account -- the raw fresh
        # head is the only head there is to compare against.
        "reviewed_at_this_head": review_gate.get("head_sha") == head_sha,
        "kill_switch_clear": readiness["kill_switch_clear"],
        "round_clean": review_gate.get("outcome") == "clean",
        "no_open_findings": review_gate.get("findings_open") == 0,
        "no_unresolved_human_review": _no_unresolved_human_review(
            reviews, bot_login),
    }

    may_merge = all(values[name] for name in CONDITIONS)

    unmet_reason = None
    for name in CONDITIONS:
        if not values[name]:
            unmet_reason = name
            break

    decision = {"head_sha": head_sha, "may_merge": may_merge,
                "unmet_reason": unmet_reason}
    decision.update(values)
    return decision


def evaluate(pr_number, review_gate, kill_switch_paused, bot_login):
    """Runtime entry point: both `gh pr view` reads happen here, fresh at
    this exact moment, never a value an earlier step or an earlier job
    captured (FR-026). `review_gate` is the caller's own fresh read of the
    lifecycle issue's marker (wc_lifecycle_review_marker.read_marker()) --
    this function performs no git operation of its own, unlike the T069
    era, since there is no longer a bookkeeping commit on the reviewed
    branch to peel past (T074)."""
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json",
         "headRefOid,statusCheckRollup,mergeable,mergeStateStatus"],
        capture_output=True, text=True, check=True)
    snapshot = json.loads(proc.stdout)
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "reviews"],
        capture_output=True, text=True, check=True)
    reviews = json.loads(proc.stdout).get("reviews") or []
    return evaluate_from_snapshot(snapshot, review_gate, kill_switch_paused,
                                  reviews, bot_login)


def main():
    """Reads {"snapshot": {...}, "review_gate": {...}|null,
    "kill_switch_paused": bool, "reviews": [...], "bot_login": str} from
    stdin, prints the MergePreconditions decision as JSON."""
    payload = json.load(sys.stdin)
    decision = evaluate_from_snapshot(
        payload["snapshot"], payload.get("review_gate"),
        payload["kill_switch_paused"], payload.get("reviews") or [],
        payload.get("bot_login") or "")
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
