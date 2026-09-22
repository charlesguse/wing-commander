# Contract: Eligibility and Selection

## `.github/scripts/board_eligibility.py`

```python
def classify_issue(issue: dict, labeled_events: list[dict]) -> str:
    """Returns one of: "maintainer-authored", "maintainer-labeled",
    "pipeline-labeled", "ineligible".

    issue: gh issue view --json number,author,authorAssociation,labels,state
    labeled_events: gh api repos/:owner/:repo/issues/:num/timeline
                     --paginate --jq '.[] | select(.event=="labeled")'
    """

def is_excluded(issue: dict) -> tuple[bool, str | None]:
    """FR-010: True + reason when the issue is closed, carries a
    disposition:* settled marker, carries board:stalled, or carries any
    stage:* / spec:* label."""

def select(open_issues: list[dict], labeled_events_by_issue: dict) -> int | None:
    """Oldest (by createdAt asc) issue where classify_issue() != "ineligible"
    and is_excluded() is False. None when no issue qualifies."""
```

## Eligibility rule (FR-006/FR-008)

- Maintainer-authored: `issue.authorAssociation` is `OWNER`, `MEMBER`, or
  `COLLABORATOR` (this repository's existing maintainer-association set —
  match whatever `pr-conversation.yml`'s own authorized-actor check already
  uses, not a second definition).
- Maintainer-labeled: the issue carries a label whose most recent `labeled`
  timeline event's `actor.login` is a maintainer (by the same association
  check) — never "the label is present" alone.
- Pipeline-labeled: the issue carries one of `pipeline-defect` (and the
  watchdog's other finding classes), `auto-update:*`, `auto-release:failed`,
  or `found-by:*` (spec 056) — admitted regardless of actor, because the
  pipeline itself filed it under a label only it applies.
- Anything else: ineligible. No comment, no proposal, no durable action
  (FR-007 dropped this path entirely — an ineligible issue is untouched).

## Exclusion rule (FR-010)

Excluded regardless of eligibility: `state == closed`; any
`disposition:*` label marking it settled (e.g. `disposition:false-positive`);
`board:stalled`; any `stage:*` or `spec:*` label (the feature lifecycle
already owns it, including this feature's own lifecycle issue #408 on its
first run).

## Gate: `verify-board-eligibility.py`

Fixtures (FR-064 bullet 2), each a checked-in `issue.json` +
`timeline.json` pair:
1. Maintainer-authored, no label → admitted (`maintainer-authored`).
2. Maintainer-applied entry label → admitted (`maintainer-labeled`).
3. The identical label applied by the bot's own actor login → NOT admitted
   (`ineligible`) — the branch FR-008's answer exists for.
4. A pipeline-only label (`pipeline-defect`) → admitted
   (`pipeline-labeled`), regardless of actor.

Each fixture asserts `classify_issue()`'s exact return value; the gate
fails loudly if any fixture file is missing rather than skipping it.
