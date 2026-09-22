#!/usr/bin/env python3
"""Board loop eligibility and selection (specs/057-autonomous-board-loop,
contracts/eligibility-and-selection.md, FR-006/FR-008/FR-009/FR-010).

WHY THIS EXISTS
---------------
The board loop MUST decide, in code, which open issues it is authorized to
act on -- never by reading the issue's text (FR-008). This module is that
decision, run twice per contracts/eligibility-and-selection.md: fed real
`gh issue list`/`gh api .../timeline` data at runtime, and fed the checked-in
fixtures under `.github/scripts/tests/board-eligibility/` by
`verify-board-eligibility.py` at PR time.

Expected shapes
----------------
`issue`: the JSON object `gh issue view --json
number,author,authorAssociation,labels,state,createdAt` produces, i.e.
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
import sys

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}

# FR-006's fixed label list: the pipeline's own filing labels, admitted
# regardless of the actor who applied them -- a bot-applied label is only
# ever eligible on THIS ground, never on "a maintainer applied it" (FR-008).
PIPELINE_LABEL_EXACT = {"pipeline-defect", "auto-release:failed"}
PIPELINE_LABEL_PREFIXES = ("auto-update:", "found-by:")

STALLED_LABEL = "board:stalled"
DISPOSITION_PREFIX = "disposition:"
LIFECYCLE_PREFIXES = ("stage:", "spec:")


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


def select(open_issues, labeled_events_by_issue):
    """Oldest (by createdAt asc) issue where classify_issue() != "ineligible"
    and is_excluded() is False. None when no issue qualifies (FR-009)."""
    candidates = sorted(open_issues, key=lambda issue: issue.get("createdAt") or "")
    for issue in candidates:
        excluded, _reason = is_excluded(issue)
        if excluded:
            continue
        labeled_events = labeled_events_by_issue.get(issue.get("number"), [])
        if classify_issue(issue, labeled_events) != "ineligible":
            return issue.get("number")
    return None


def main():
    """Runtime entry point: reads `{"open_issues": [...],
    "labeled_events_by_issue": {...}}` from stdin, prints the selected
    issue number (or nothing) to stdout."""
    payload = json.load(sys.stdin)
    open_issues = payload.get("open_issues", [])
    labeled_events_by_issue = {
        int(number): events
        for number, events in (payload.get("labeled_events_by_issue") or {}).items()
    }
    selected = select(open_issues, labeled_events_by_issue)
    if selected is not None:
        print(selected)


if __name__ == "__main__":
    main()
