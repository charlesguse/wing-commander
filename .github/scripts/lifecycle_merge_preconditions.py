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

`reviewed_at_this_head` AND THE GATE'S OWN RECORDING COMMIT (T069)
--------------------------------------------------------------
`disposition`'s round-recording commit necessarily advances the PR's real
head past the SHA it just wrote into `review_gate.head_sha` (a commit
cannot name its own resulting SHA inside its own content). Comparing
`review_gate.head_sha` against the RAW fresh `headRefOid` would therefore
refuse every merge of a round that already came back clean -- the branch
would always look "not yet reviewed at this exact head" even though
nothing but this gate's own bookkeeping changed. `evaluate()` peels the
fresh head back past this gate's own trailing "review-gate: round ..."
commits first (`wc_review_gate_settled_head.settled_head`, T069's single
home, shared with `select`'s own bash use of the same script) and compares
`review_gate.head_sha` against THAT settled value instead. `head_sha` in
the returned decision (used for `--match-head-commit`) stays the RAW,
unpeeled head -- the merge must still target the branch's actual current
tip.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_readiness import evaluate_from_snapshot as _readiness  # noqa: E402
from wc_review_gate_settled_head import settled_head as _settled_head  # noqa: E402

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
                           reviews, bot_login, settled_head_sha=None):
    """snapshot: the `gh pr view --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus` shape, fetched
    fresh by the caller. review_gate: the spec-meta.json review_gate object
    (or None/{} before any round has run). reviews: the `gh pr view --json
    reviews` list. bot_login: this App's own bot identity login, whose
    reviews never block its own merge. settled_head_sha: the fresh head,
    peeled back past this gate's own trailing recording commit(s) (T069) --
    defaults to the raw `snapshot["headRefOid"]` when not given (every
    existing fixture's behavior, unchanged). Returns the
    MergePreconditions dict (data-model.md §5), eight conditions evaluated
    in order, unmet_reason naming the first failing condition's own
    name."""
    head_sha = snapshot.get("headRefOid")
    review_gate = review_gate or {}
    if settled_head_sha is None:
        settled_head_sha = head_sha

    readiness = _readiness(snapshot, review_gate, kill_switch_paused)

    values = {
        "checks_green": readiness["checks_green"],
        "gate_suite_green": readiness["gate_suite_green"],
        "mergeable": readiness["mergeable"],
        # The merge-context polarity of readiness condition 4 -- see this
        # module's own docstring for why it is inverted here, and for why
        # this compares the SETTLED head, not readiness's own
        # not_yet_reviewed (which is always computed against the raw head).
        "reviewed_at_this_head": review_gate.get("head_sha") == settled_head_sha,
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
    captured (FR-026). Peels the fresh head back past this gate's own
    trailing recording commit(s) (T069) using the LOCAL git checkout the
    caller already has in its working directory (the `merge` job checks
    out the PR's own head ref before calling this)."""
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json",
         "headRefOid,statusCheckRollup,mergeable,mergeStateStatus"],
        capture_output=True, text=True, check=True)
    snapshot = json.loads(proc.stdout)
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "reviews"],
        capture_output=True, text=True, check=True)
    reviews = json.loads(proc.stdout).get("reviews") or []
    settled = _settled_head(snapshot.get("headRefOid"))
    return evaluate_from_snapshot(snapshot, review_gate, kill_switch_paused,
                                  reviews, bot_login, settled_head_sha=settled)


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
