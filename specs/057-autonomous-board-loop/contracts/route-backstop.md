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

## Decision table

| agent_proposal | backstop verdict | `reason` | Outcome |
|---|---|---|---|
| fix | under threshold, no contract touch | `under_threshold` | proceeds to fix |
| fix | over threshold | `over_threshold` | re-routed to `spec-request`, before any push |
| fix | contract-widening | `contract_widening` | re-routed to `spec-request` regardless of size (FR-019) |
| spec | under threshold, no contract touch | `agent_proposed_spec` | stays `spec-request`; backstop never widens (FR-017). Reported as "Route sent this issue to a spec request (the route agent judged this spec-shaped; …)", not "re-routed", with the agent's one-line rationale after the marker when it gave one (#534) |
| spec (default: no usable proposal) | under threshold, no contract touch | `no_usable_proposal` | stays `spec-request`; reported as "sent", naming the missing proposal (#534). A parsed proposal whose `category` is missing or not `fix`/`spec` counts as no usable proposal |
| spec | over threshold / contract-widening | `over_threshold` / `contract_widening` | stays `spec-request`; the backstop condition that also fired is the reason. Reported as "sent … (the route agent judged this spec-shaped; the backstop also flagged: `<reason>`, measured=…)" -- never "re-routed", which is kept for a `fix` proposal the backstop narrowed |
| fix (post-push, final diff breaches) | — | `post_push_final_diff_breach` | branch/PR left open with a notice + link to the spun-off `spec-request`; `board:stalled` applied (FR-021) |

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
