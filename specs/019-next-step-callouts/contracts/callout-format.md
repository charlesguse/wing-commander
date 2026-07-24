# Contract: `wing-commander-callout` Composite Action

This is the interface contract for the one new shared composite action this
feature introduces:
`.github/actions/wing-commander-callout/action.yml`. It is the single
enforcement point for FR-004/FR-005/FR-011's action-required vs
informational convention (research.md). This file is the acceptance
contract Phase 2 (`tasks.md`) and implementation are checked against — not
new design.

## Inputs

| Input | Required | Description |
|---|---|---|
| `token` | yes | GitHub token with `issues: write` (the same App-installation token every stage already mints via `wing-commander-context`) |
| `issue-number` | yes | The lifecycle issue to comment on |
| `kind` | yes | `action` or `info` — selects the rendering template |
| `summary` | yes | One-sentence plain-language statement: what the reader must do (`kind: action`) or what happened (`kind: info`) |
| `body` | no | Literal short markdown string for additional detail. Mutually exclusive with `body-file` |
| `body-file` | no | Path to a file containing additional markdown detail (used for agent-authored or otherwise multi-line content). Mutually exclusive with `body` |
| `pr-url` | no | Direct URL to the related pull request. `kind: action` only |
| `pr-label` | no | Human label for the PR (e.g. `"the spec PR"`, `"the implementation PR"`). Defaults to `"the pull request"` when `pr-url` is set |
| `timing` | no | Free-text statement of when the action should be performed (e.g. `"after this PR merges"`). `kind: action` only |

**Contract clauses**:
- Exactly one of `body`/`body-file` may be set; the action fails fast
  (`::error::` + non-zero exit) if both are set.
- `body-file` content is posted via `gh issue comment --body-file`
  (composited with the envelope by writing the full rendered comment to a
  temp file first) — never `--body "$(cat ...)"` shell interpolation
  (research.md, injection-safety decision).
- `timing`/`pr-url`/`pr-label` are silently ignored (no error) when
  `kind: info` — informational callouts never render a PR line or timing
  line, keeping the two templates visually distinct by construction.

## Rendering templates

### `kind: action`

```markdown
> [!IMPORTANT]
> **Action needed: <summary>**
>
> <body, if given — agent- or caller-authored detail>
>
> **PR:** [<pr-label>](<pr-url>)
> **When:** <timing>
```

- The `**PR:**` line is emitted only when `pr-url` is set (FR-008: "the
  action-required callout MUST still be posted... omitting only the PR
  link").
- The `**When:**` line is emitted only when `timing` is set (FR-007).
- Every line of the alert block is prefixed with `>` (GitHub Alert syntax
  requirement) including blank separator lines within the block.

### `kind: info`

```markdown
<summary>

<body, if given>
```

- No alert wrapper, no `**Action needed:**` phrase, no PR/timing lines —
  informational callouts are visually and textually distinct from
  action-required ones by construction (FR-004, FR-005).
- Callers keep prefixing their own existing per-stage icon inside `summary`
  if they choose (e.g. `"📝 spec drafting started"`) — this feature does not
  require removing the icon convention for informational messages it
  doesn't migrate (research.md scope decision).

## Behavior contract

- Posts exactly one issue comment per invocation (`gh issue comment`) —
  never edits or deletes a prior comment (FR-012: fresh, append-only).
- Never fails the calling job on a GitHub API error from the comment post
  itself beyond what `gh issue comment`'s own non-zero exit already causes —
  same failure shape every existing `gh issue comment` step already has (no
  new retry/backoff logic is introduced; out of scope).
- Is pure output — it never reads or mutates `spec-meta.json`, labels, or
  any other pipeline state. Callers that also need a label flip (e.g.
  `finalize.yml`'s `stage:review`) keep doing so in their own existing,
  separate step.
- Runs with no network access beyond the `gh` CLI call itself — no new
  external dependency (constitution V: web tools stay disabled in
  issue/comment-driven stages; this action makes no web calls at all).

## Non-goals (explicitly out of contract)

- Deciding *whether* a given moment is action-required or informational —
  that decision is made by the calling workflow's own deterministic
  condition (`research.md`, "deterministic step decides kind"), not by this
  action.
- Deduplicating or superseding a prior callout — FR-012 is satisfied by
  simple append-only posting; any per-caller dedup (e.g. `rebase.yml`'s
  HTML marker skip-if-unchanged check) stays in the calling workflow,
  unmodified, and is passed through inside `body`/`body-file` untouched.
- Any rendering target other than a GitHub issue comment (e.g. Slack, email)
  — constitution III (GitHub-native only).
