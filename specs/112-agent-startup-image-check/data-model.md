# Data Model: Agent Start-up Image Check

## Verdict (classifier output)

| Field | Type | Notes |
|---|---|---|
| `verdict` | enum | `setup-completed` \| `setup-failed` \| `unclassified` |
| `step` | string or null | Setup step group that failed; set only for `setup-failed` |
| `error` | string or null | First error line quoted verbatim; set for `setup-failed` and for the offending line in `unclassified` when one exists |
| `reason` | string | Human sentence for the job summary and `::error::` |

Rules: only `setup-completed` exits 0. `unclassified` and `setup-failed` have
distinct `reason` prefixes ("could not reach subject" vs "setup failed in
image") so FR-004 holds.

## Log fixture

| Field | Type | Notes |
|---|---|---|
| file | `agent-startup-fixtures/<branch>.log` | Raw job log text |
| expectation | `<branch>.expect.json` | `{"verdict": ..., "step": ..., "error_contains": ...}` |

Invariant (enforced by the gate): every verdict branch the classifier can
return has at least one fixture, and every fixture's actual verdict equals its
expectation.

## Auth marker table

A list of regular expressions in the classifier naming the action's
no-credential failure. Replaced by hand when the action's wording changes;
absence of a match is `unclassified`, never a pass.

## Git floor

| Field | Value |
|---|---|
| minimum | 2.38 |
| source of truth | `.github/scripts/image-git-floor.sh` (fragment) |
| result | pass; fail naming version found; fail on unparseable output |

## State transitions

None. The check is stateless per run.
