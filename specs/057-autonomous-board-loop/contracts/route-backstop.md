# Contract: Route Backstop

## `.github/actions/wing-commander-size-path-backstop/action.yml` (extracted, shared)

| Input | Type | Default | Notes |
|---|---|---|---|
| `file-changes` | string (JSON) | required | the same shape `pr-conversation.yml`'s `drafted-content.file-changes` already produces |
| `max-files` | number | `3` | `pr-conversation.yml`'s existing call site omits this, keeping its current behavior |
| `max-lines` | number | `40` | same |

| Output | Type | Notes |
|---|---|---|
| `over-threshold` | boolean | |
| `measured-files` | number | |
| `measured-lines` | number | |

`pr-conversation.yml`'s `classify-and-announce` job is repointed at this
composite in the same change that introduces it (research.md D5) — its own
behavior is unchanged because it passes no `max-files`/`max-lines`
override.

## `.github/scripts/board_route_backstop.py` (board-specific logic on top)

```python
def contract_widened(diff_paths: list[str], diff_text: str) -> list[str]:
    """research.md D6: returns the subset of diff_paths that touch a
    workflow_call: inputs:/outputs: block or a wing-commander-* composite's
    action.yml inputs:/outputs: keys. Non-empty => contract-widening."""

def route(agent_proposal: str, file_changes: dict, board_max_files: int,
          board_max_lines: int) -> RouteDecision:
    """FR-016..FR-020. Calls wing-commander-size-path-backstop with the
    board's own thresholds; ORs in contract_widened(); can only narrow
    agent_proposal ("fix" -> "spec"), never widen ("spec" stays "spec")."""

def route_final_diff(route_decision: RouteDecision, final_diff: dict) -> RouteDecision:
    """FR-021/FR-018: re-applies route() to the pushed branch's final
    diff. If this newly breaches (files/lines grew during the fix, or a
    late commit touched a published contract), the branch and PR are left
    open under a notice, board:stalled is applied, and a spec-request is
    filed pointing at them — the branch/PR are never deleted."""
```

## Board reset of 2026-10-01 (constitution X, 2.2.0)

- Every outcome below that names `spec-request` now files a
  `spec-proposal` instead; only the owner promotes one by applying
  `spec-request`.
- The pre-push contract check is `drafted_contract_widened()`: it applies
  the route agent's drafted hunks to main's file content by their own
  lines (never their header numbers), and flags a path whose contract
  block (`on: workflow_call:`, or a composite's `inputs:`/`outputs:`)
  changes, or a `wing-commander-*` composite added or deleted. The old
  `touches_protected_file()` proxy, which flagged any touched workflow or
  composite, is gone. A drafted diff it cannot apply to main is an
  unknown, not a widening: it is flagged only when its own added or
  removed lines carry a contract signal (a workflow's `workflow_call`
  trigger, or a composite's column-0 `inputs:`/`outputs:` key). Any other
  unappliable diff is left to `route_final_diff()`'s check of the pushed
  diff; one the loop cannot push is held under `workflow_scope` with its
  contract effect named as unchecked (#936, #955).
- The final-diff check (`route_final_diff()`) also compares against the
  base side (`read_base_contents()`), so a contract removed is a breach,
  not only one added. Its paths come from `diff_name_list()` and its patch
  from `git diff --no-renames`, so a `workflow_call` workflow moved out of
  `.github/workflows/` is a contract removed, not an unrelated new file
  (#889).
- A new verdict, `hold`, comes before `fix`:

| agent_proposal | backstop verdict | `reason` | Outcome |
|---|---|---|---|
| fix | under threshold, no contract change, drafted diff edits a file under `.github/workflows/`, `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` off | `workflow_scope` | held: `board:stalled` and a comment naming the files, for a maintainer whose token has the `workflow` scope; any path in the held change whose drafted diff could not be applied to main, a composite as well as a workflow, is named in that comment as contract-unchecked. Never filed as a spec. The fix job's pre-push check holds the same way when the fixer's real diff edits one, and review-fixup's on its follow-up commit; each lists the real diff itself (`diff_name_list()`: NUL-separated, so a non-ASCII path is never C-quoted, and `--no-renames`, so a rename is its deleted path and its added one), whatever route drafted, and its comment names whether that diff changes a published contract (`contract_widened()` against the base), since a held change never reaches `route_final_diff()`. An unreadable or malformed route decision is an `::error::` naming the site, and nothing is held (#889) |

## Decision table

| agent_proposal | backstop verdict | `reason` | Outcome |
|---|---|---|---|
| fix | under threshold, no contract touch | `under_threshold` | proceeds to fix |
| fix | over threshold | `over_threshold` | re-routed to `spec-request`, before any push |
| fix | contract-widening | `contract_widening` | re-routed to `spec-request` regardless of size (FR-019) |
| spec | under threshold, no contract touch | `agent_proposed_spec` | stays `spec-request`; backstop never widens (FR-017). Reported as "Route sent this issue to a spec request (the route agent judged this spec-shaped; …)", not "re-routed", with the agent's one-line rationale after the marker when it gave one (#534) |
| spec (default: no usable proposal), route agent's own verdict `rate-limited` | under threshold, no contract touch | `agent_rate_limited` | verdict `defer`: nothing is filed, closed or labelled. The issue's `route` marker keeps it in flight, and the next run triages it again (a rate-limited triage defers as well and posts nothing, `board_triage.defer_on_rate_limit()`) and routes it once the usage window resets. Filing the default spec instead closed the original as a duplicate during the 2026-10-01 usage outage (#902 → #907, #906 → #908) |
| spec (default: no usable proposal) | under threshold, no contract touch | `no_usable_proposal` | stays `spec-request`; reported as "sent", naming the missing proposal (#534). A parsed proposal whose `category` is missing or not `fix`/`spec` counts as no usable proposal. The category is read through `normalize_category()` (whitespace stripped, lowercased), in both the extract step's `extracted` and `route()`, so `SPEC`/` spec ` are the agent's spec and `Fix` its fix; any other value (a typo, `null`, a non-string) is no usable proposal and routes to spec whatever the caller passed as `proposal_extracted` (#548) |
| spec | over threshold / contract-widening | `over_threshold` / `contract_widening` | stays `spec-request`; the backstop condition that also fired is the reason. Reported as "sent … (the route agent judged this spec-shaped; the backstop also flagged: `<reason>`, measured=…)" -- never "re-routed", which is kept for a `fix` proposal the backstop narrowed |
| fix (post-push, final diff breaches) | — | `post_push_final_diff_breach` | branch/PR left open with a notice + link to the spun-off `spec-request`; `board:stalled` applied (FR-021). A `breach` marker is posted before the spec-request is filed, so a failed create is retried by `readiness` on a later run, never reviewed (#530, contracts/board-item-marker.md "Breach step") |

## Gate: `verify-board-route-backstop.py`

Fixtures (FR-064 bullet 3):
1. Under threshold → `fix`.
2. Over threshold (files) → `spec-request`, reason names measured files
   and the threshold.
3. Contract-widening diff, small otherwise → `spec-request` regardless of
   size.
4. Post-push final-diff breach → branch/PR left open, notice posted,
   `spec-request` filed, `board:stalled` applied — nothing deleted.
5. Agent proposes spec, under threshold, no contract touch → `spec`,
   reason `agent_proposed_spec` (#534); over threshold → `over_threshold`;
   no usable proposal → `no_usable_proposal`.
6. Category spelling (#548): `"SPEC"` and `" spec "` → `spec`,
   `agent_proposed_spec`; `"Fix"` → `fix`; `"banana"` and `null` → `spec`,
   `no_usable_proposal`.
