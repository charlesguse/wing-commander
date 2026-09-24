# Contract: Review and Findings

## `.github/schemas/board-review-finding.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["title", "what", "evidence", "in_scope", "fingerprint_basis"],
    "additionalProperties": false,
    "properties": {
      "title": {"type": "string", "maxLength": 120},
      "what": {"type": "string"},
      "evidence": {
        "type": "object",
        "required": ["file_paths"],
        "additionalProperties": false,
        "properties": {
          "file_paths": {"type": "array", "items": {"type": "string"}},
          "detail": {"type": "string"}
        }
      },
      "in_scope": {"type": "boolean"},
      "fingerprint_basis": {
        "type": "object",
        "required": ["file_path", "gate_or_artifact"],
        "additionalProperties": false,
        "properties": {
          "file_path": {"type": "string"},
          "gate_or_artifact": {"type": "string"}
        }
      }
    }
  }
}
```

## Channel

The reviewer's final message carries a fenced block:

    ```wing-commander-review-findings
    [{"title": "...", "what": "...", "evidence": {...}, "in_scope": true,
      "fingerprint_basis": {...}}]
    ```

Extracted from the `.result` field of the last `type=="result"` transcript
entry — the same extraction shape as spec 056's D2, distinct marker
string.

## Reviewer invocation (research.md D10)

- Separate job/step; no fixer transcript, memory, or prompt continuation.
- Prompt input: the PR diff, the originating issue's body (framed as
  data), the fix's own commit messages. Never the fixer's session.
- Every input is a file a deterministic step stages before the agent runs
  (#503): the diff, commit list and PR title/body under
  `/tmp/wing-commander/`, and the issue through
  `wing-commander-issue-context`. The reviewer has no `gh` grant, so PR
  comments, which `gh pr view --comments` returns unfiltered, never reach
  it (FR-056). Gate 93 enforces both.
- Posts via `gh api repos/:owner/:repo/pulls/:number/reviews -f
  event=COMMENT -F body=@review-body.md` — never `APPROVE`/`REQUEST_CHANGES`
  (GitHub rejects both from the PR's own author identity, FR-029).

## Round loop (FR-030/FR-031)

1. Reviewer runs against the current head.
2. `verify-board-review-finding-schema.py`'s `validate_finding()` filters
   malformed entries (dropped, logged — same discipline as spec 056's
   D5/D11).
3. In-scope findings (`in_scope: true`) → fixer makes a follow-up commit →
   round count increments → reviewer re-runs against the new head (FR-031).
4. Out-of-scope findings (`in_scope: false`) → filed per research.md D12,
   never held against the PR (FR-032).
5. Zero in-scope open findings → proceed to readiness.
6. Round budget (research.md D18, 5) exhausted with findings still open →
   PR left open/unmerged, issue gets a stall notice naming the remaining
   findings, `board:stalled` applied (FR-030). Removing the label is the
   sole re-eligibility condition, and the notice says so.

## Gate: `verify-board-review-finding-schema.py`

Fixture set: one well-formed finding (validates); one per omitted required
field (`title`, `what`, `evidence.file_paths`, `in_scope`,
`fingerprint_basis`) — each must be rejected with the missing field named.
