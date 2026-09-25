#!/usr/bin/env python3
"""Board loop eligibility and selection (specs/057-autonomous-board-loop,
contracts/eligibility-and-selection.md, FR-006/FR-008/FR-009/FR-010).

WHY THIS EXISTS
---------------
The board loop MUST decide, in code, which open issues it is authorized to
act on -- never by reading the issue's text (FR-008). This module is that
decision, run twice per contracts/eligibility-and-selection.md: fed real
`gh api .../issues`/`gh api .../timeline` data at runtime, and fed the
checked-in fixtures under `.github/scripts/tests/board-eligibility/` by
`verify-board-eligibility.py` at PR time.

Expected shapes
----------------
`issue`: `gh issue list --json` does not support `authorAssociation` --
only `gh issue view` does, and the runtime caller needs every open issue
at once, so it remaps `gh api repos/OWNER/REPO/issues`'s REST shape
(which carries `author_association` natively) into this, i.e.
    {"number": 1, "author": {"login": "..."},
     "authorAssociation": "OWNER" | "MEMBER" | "COLLABORATOR" | "NONE" | ...,
     "labels": [{"name": "..."}, ...],
     "state": "OPEN" | "CLOSED", "createdAt": "2026-01-01T00:00:00Z"}

`labeled_events`: the `labeled` timeline events for ONE issue, each carrying
the actor who applied the label and that actor's own association with the
repository (resolved by the runtime caller -- e.g. cross-referenced against
the repository's collaborator list / the wing-commander bot's own login --
since GitHub's timeline API does not itself carry author_association):
    {"event": "labeled", "created_at": "2026-01-01T00:00:00Z",
     "label": {"name": "..."},
     "actor": {"login": "...", "association": "OWNER" | "MEMBER" |
               "COLLABORATOR" | "NONE" | "BOT" | ...}}

`labeled_events_by_issue` (for `select()`): {issue_number: [labeled_events]}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import read_marker_with_timestamp  # noqa: E402

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}

# FR-006's fixed label list: the pipeline's own filing labels, admitted
# regardless of the actor who applied them -- a bot-applied label is only
# ever eligible on THIS ground, never on "a maintainer applied it" (FR-008).
PIPELINE_LABEL_EXACT = {"pipeline-defect", "auto-release:failed"}
PIPELINE_LABEL_PREFIXES = ("auto-update:", "found-by:")

STALLED_LABEL = "board:stalled"
DISPOSITION_PREFIX = "disposition:"
LIFECYCLE_PREFIXES = ("stage:", "spec:")

# data-model.md "Step" / contracts/in-flight-detection.md: the loop's named
# steps, split by whether a PR can exist yet at that step. Pre-fix qualifies
# an in-flight candidate on the marker's step alone; fix-or-later needs its
# recorded PR to still resolve OPEN (FR-002).
#
# AWAITING_MERGE_STEP (#532) is the step readiness records when it reports
# ready and hands the PR to a human (spec 057: the loop stops at "ready to
# merge"). It is a fix-or-later step -- its marker carries the PR it waits
# on -- so FIX_OR_LATER_STEPS stays the one list the select job's PR-state
# lookup pass and the resume step's step resolution read to find which
# markers name a PR worth resolving; there is no second, parallel
# "PR-bearing steps" list. Unlike the other fix-or-later steps it never
# makes its issue in-flight, and select()'s oldest-first fallback passes it
# over while its PR may still be open -- see _awaiting_merge_holds().
AWAITING_MERGE_STEP = "awaiting-merge"
PRE_FIX_STEPS = frozenset({"triage", "route"})
FIX_OR_LATER_STEPS = frozenset({"fix", "review", "readiness", AWAITING_MERGE_STEP, "prove"})
TERMINAL_STEPS = frozenset({"closed", "stalled", "proven"})


def _label_names(issue):
    return [(label or {}).get("name") or "" for label in issue.get("labels") or []]


def _is_pipeline_label(name):
    if name in PIPELINE_LABEL_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in PIPELINE_LABEL_PREFIXES)


def _most_recent_labeled_actor_association(label_name, labeled_events):
    """The `association` field of the most recent `labeled` timeline event
    that applied `label_name`, or None if no such event is present."""
    matches = [
        event for event in labeled_events
        if event.get("event") == "labeled"
        and ((event.get("label") or {}).get("name")) == label_name
    ]
    if not matches:
        return None
    matches.sort(key=lambda event: event.get("created_at") or "")
    return (matches[-1].get("actor") or {}).get("association")


def classify_issue(issue, labeled_events):
    """Returns one of "maintainer-authored", "maintainer-labeled",
    "pipeline-labeled", "ineligible" (contracts/eligibility-and-selection.md).

    Never reads the label set alone as an allowlist (FR-008): a
    maintainer-applied label is decided from the `labeled` event's own
    actor, not from the label's mere presence.
    """
    if issue.get("authorAssociation") in MAINTAINER_ASSOCIATIONS:
        return "maintainer-authored"

    labels = _label_names(issue)

    for name in labels:
        if _is_pipeline_label(name):
            return "pipeline-labeled"

    for name in labels:
        association = _most_recent_labeled_actor_association(name, labeled_events)
        if association in MAINTAINER_ASSOCIATIONS:
            return "maintainer-labeled"

    return "ineligible"


def is_excluded(issue):
    """FR-010: (True, reason) when the issue is closed, carries a settled
    disposition:* marker, carries board:stalled, or carries any stage:*/
    spec:* label. (False, None) otherwise."""
    if (issue.get("state") or "").upper() == "CLOSED":
        return True, "closed"

    labels = _label_names(issue)

    if STALLED_LABEL in labels:
        return True, STALLED_LABEL

    for name in labels:
        if name.startswith(DISPOSITION_PREFIX):
            return True, name
        if any(name.startswith(prefix) for prefix in LIFECYCLE_PREFIXES):
            return True, name

    return False, None


# FR-011/CLAUDE.md single-home rule: "is this issue an in-flight board item
# of mine?" is decided here, and only here -- in_flight_candidate() and the
# select() that consults it first. Never re-derive this inline in a
# workflow's run: step or in a second module; point back at this comment
# instead (contracts/in-flight-detection.md).
def in_flight_candidate(open_issues, comments_by_issue, pr_state_by_number):
    """FR-001/FR-002/FR-003/FR-005. Returns (issue_number, multiple_found).

    issue_number is the newest-marker in-flight issue among open,
    non-excluded issues, or None. multiple_found is True when more than
    one issue qualified (FR-005) regardless of which one issue_number
    names.

    Skips (never raises on): an issue with no comments, an issue whose
    newest marker is unparsable (per board_item_marker.read_marker's own
    degrade rule), a marker naming a fix-or-later step whose pr is absent
    from pr_state_by_number or not OPEN there. `prove` never qualifies as a
    candidate here at all, even though it is non-terminal: this function
    only ever runs from the select job, which only runs off the schedule/
    workflow_dispatch triggers (never pull_request), and no job on that
    path consumes step == "prove" (only prove-gate/prove do, and those run
    solely on pull_request: closed). Prioritizing a stuck prove marker here
    would starve every other candidate forever for no possible benefit.
    select()'s oldest-first fallback carries this same exclusion (never a
    second, parallel rule), so a stuck prove marker is never selected by
    either path -- it stays untouched until something off this run's own
    trigger path (prove-gate/prove, or a maintainer) resolves it.

    `awaiting-merge` (#532) never qualifies here either, whatever its PR's
    state: readiness already reported ready and handed the PR to a human,
    and no job consumes that step. Treating it as in-flight while its PR
    was open re-selected the same item every run, re-posted an identical
    readiness report, and starved every other issue until a human merged.
    """
    candidates = []
    for issue in open_issues:
        excluded, _reason = is_excluded(issue)
        if excluded:
            continue
        number = issue.get("number")
        pair = read_marker_with_timestamp(comments_by_issue.get(number) or [])
        if pair is None:
            continue
        created_at, marker = pair
        step = marker.get("step")
        if step in TERMINAL_STEPS or step in ("prove", AWAITING_MERGE_STEP):
            continue
        if step in PRE_FIX_STEPS:
            candidates.append((created_at, number))
        elif step in FIX_OR_LATER_STEPS:
            try:
                pr = int(marker.get("pr"))
            except (TypeError, ValueError):
                continue
            if pr_state_by_number.get(pr) == "OPEN":
                candidates.append((created_at, number))
    if not candidates:
        return None, False
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1], len(candidates) > 1


def _awaiting_merge_holds(marker, pr_state_by_number):
    """True when `marker` records AWAITING_MERGE_STEP and its PR is not
    positively known to be CLOSED or MERGED -- the item is still handed to
    a human, so select()'s oldest-first fallback passes it over (#532).

    Fail-safe for an unknown state (the PR number absent from
    pr_state_by_number because the select job's lookup failed, or a
    malformed `pr`): the item is SKIPPED, not re-admitted. Re-admitting it
    would recreate #532's wedge whenever that lookup kept failing -- the
    resume step repeats the same lookup and resolves an unresolvable
    awaiting-merge PR to a no-op, so an oldest-eligible item would be
    re-selected and do nothing on every run. Skipping costs at most a
    delay for this one item (it is re-admitted on the first run whose
    lookup returns CLOSED or MERGED), and a human merge still reaches
    prove-gate/prove through pull_request: closed, which never consults
    this."""
    if (marker or {}).get("step") != AWAITING_MERGE_STEP:
        return False
    try:
        pr = int(marker.get("pr"))
    except (TypeError, ValueError):
        return True
    return pr_state_by_number.get(pr) not in ("CLOSED", "MERGED")


def select(open_issues, labeled_events_by_issue, comments_by_issue, pr_state_by_number):
    """FR-004/FR-011: consults in_flight_candidate() first; falls through to
    the existing oldest-first/classify_issue/is_excluded scan when it
    returns (None, ...). That fallback carries the same `prove`-marker skip
    as in_flight_candidate() above (never a second, parallel rule) so a
    stuck `prove` issue that ages to the front of the oldest-first queue is
    passed over instead of being re-selected every run with no consumer
    able to advance it. It likewise passes over an `awaiting-merge` issue
    while _awaiting_merge_holds() (#532); once that PR is closed unmerged,
    or merged with the issue still open, the item is eligible here again
    and the resume step sends it to a fresh triage."""
    in_flight, _multiple_found = in_flight_candidate(
        open_issues, comments_by_issue, pr_state_by_number)
    if in_flight is not None:
        return in_flight

    candidates = sorted(open_issues, key=lambda issue: issue.get("createdAt") or "")
    for issue in candidates:
        excluded, _reason = is_excluded(issue)
        if excluded:
            continue
        number = issue.get("number")
        pair = read_marker_with_timestamp(comments_by_issue.get(number) or [])
        if pair is not None and (pair[1] or {}).get("step") == "prove":
            continue
        if pair is not None and _awaiting_merge_holds(pair[1], pr_state_by_number):
            continue
        labeled_events = labeled_events_by_issue.get(number, [])
        if classify_issue(issue, labeled_events) != "ineligible":
            return number
    return None


def main():
    """Runtime entry point: reads `{"open_issues": [...],
    "labeled_events_by_issue": {...}, "comments_by_issue": {...},
    "pr_state_by_number": {...}}` from stdin, prints the selected issue
    number (or nothing) to stdout -- unchanged from before. Also prints
    FR-005's provenance -- `{"decided_by_marker": bool, "multiple_found":
    bool}` -- to stderr, so the caller can say the marker is why (spec.md
    US1 AS3) without re-deriving the decision."""
    payload = json.load(sys.stdin)
    open_issues = payload.get("open_issues", [])
    labeled_events_by_issue = {
        int(number): events
        for number, events in (payload.get("labeled_events_by_issue") or {}).items()
    }
    comments_by_issue = {
        int(number): comments
        for number, comments in (payload.get("comments_by_issue") or {}).items()
    }
    pr_state_by_number = {
        int(number): state
        for number, state in (payload.get("pr_state_by_number") or {}).items()
    }
    in_flight_issue, multiple_found = in_flight_candidate(
        open_issues, comments_by_issue, pr_state_by_number)
    selected = select(open_issues, labeled_events_by_issue, comments_by_issue, pr_state_by_number)
    print(json.dumps({
        "decided_by_marker": in_flight_issue is not None and in_flight_issue == selected,
        "multiple_found": multiple_found,
    }), file=sys.stderr)
    if selected is not None:
        print(selected)


if __name__ == "__main__":
    main()
