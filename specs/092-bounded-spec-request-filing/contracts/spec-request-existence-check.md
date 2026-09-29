# Contract: spec-request existence check

Owning module: `.github/scripts/board_spec_request_filing.py` (new,
research.md D1). This is the *one* implementation FR-001/FR-002/FR-003/
FR-004/FR-017/FR-018 require; every filing site calls it the same way.

## CLI

```
python3 board_spec_request_filing.py lookup \
  --issue ISSUE_NUMBER --bot-login BOT_LOGIN
```

Run as its **own workflow step**, immediately before the site's `gh issue
create ... --label spec-request` step, never inlined into it (Gate 93
check 3 forbids `gh api`/`gh issue view` inside a spec-request create
step). Requires `GH_TOKEN` in the environment.

### Behavior

1. Resolve `since`: the `created_at` of the issue's last `reopened` timeline
   event, or the issue's own `created_at` if it has never been reopened.
2. Fetch candidate issues: `gh api repos/OWNER/REPO/issues -f state=all -f
   since=SINCE -f creator=BOT_LOGIN --paginate`, filtered to
   `pull_request == null` (an issue, not a PR).
3. Build `footer = "Originating issue: {server}/{repo}/issues/{issue}"`.
4. Match: `user.type == "Bot" && user.login == BOT_LOGIN` AND the body
   contains `footer` as a whole line (CR-normalized). No other field is
   consulted — never title text, never an agent's judgment (FR-002,
   Constitution IX).
5. Of all matches, the one with the earliest `created_at` wins (FR-004);
   its `html_url` is the result. State (open/closed) is not a filter
   (FR-003).

### Outputs (`$GITHUB_OUTPUT`)

| Name | Value |
|---|---|
| `existing-spec-url` | the matched issue's URL, or empty when none matches |

### Failure

Any `gh api` failure (network, rate limit, auth) at either fetch **fails
the step** (`exit 1`, nothing written to `existing-spec-url`) — never
falls back to "no match found". Per spec.md's Edge Cases, this failure
counts as one failed filing attempt against the bound (see
`spec-request-attempt-bound.md`); the caller records it via
`record-attempt` even though no create was attempted this run (FR-007).

### Consumers

Route's spec verdict, the fix job's post-push breach, and both readiness
backstop-breach entries (the ordinary one, which has no lookup today, and
the `step=breach` retry, which currently inlines an equivalent lookup —
both migrate to this one step). A site skips its `gh issue create` and
instead reuses `existing-spec-url` when it is non-empty, wiring it into
the *same* step output (`spec-url`) a fresh create would populate, so every
downstream step (cross-link, stall marker, closing comment) is unaware of
which path produced it (data-model.md "Filing attempt"; research.md D10).
