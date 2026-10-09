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

def is_excluded(issue: dict, spec_request_state_by_number: dict[int, str] | None = None,
                 duplicate_marker: dict | None = None) -> tuple[bool, str | None]:
    """FR-010: True + reason when the issue is closed, carries a
    disposition:* settled marker, carries board:stalled, or carries any
    stage:* / spec:* label, a LIFECYCLE_LABELS label or a
    SELF_MANAGED_LABELS label (auto-update:tracking,
    auto-release:failed). spec 108 carve-out: an OPEN issue whose ONLY
    exclusion reason is disposition:duplicate is NOT excluded when its
    newest step=="duplicate" board-item marker (found by scanning every
    comment, not just the issue's overall-newest marker -- a later
    route/fix/review marker must not hide it) names a spec-request that
    spec_request_state_by_number resolves CLOSED (contracts/
    eligibility-and-readmission-delta.md)."""

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
first run); `spec-proposal` or `spec-request` (`LIFECYCLE_LABELS`, board
reset of 2026-10-01); a stage's own self-managed tracker
(`SELF_MANAGED_LABELS`): `auto-update:tracking`, whose open issue the
auto-update stage reads its settle state from, and `auto-release:failed`,
which auto-release.yml alone files, appends to and closes once every mode
its record names has passed (#966, #977). Both stay pipeline-labeled
above; exclusion wins, so the loop never triages, routes or closes them
(closing
`auto-release:failed` as a spec proposal's duplicate erased the open
failure, #979 -> #980). Board status lists an open `auto-release:failed`
issue under "Waiting on you".

The one exception (spec 108, contracts/eligibility-and-readmission-delta.md):
an OPEN issue whose only exclusion reason is `disposition:duplicate` is
re-admitted once its linked spec-request (named by the issue's own newest
step=="duplicate" board-item marker, found by scanning every comment
rather than only the issue's overall-newest marker, so a later
route/fix/review marker never hides it) resolves `CLOSED` — a
maintainer's reopen while that spec-request is still open does NOT
re-admit it, and the re-admission persists for as long as
`disposition:duplicate` remains on the issue (the label is never removed
programmatically).

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
