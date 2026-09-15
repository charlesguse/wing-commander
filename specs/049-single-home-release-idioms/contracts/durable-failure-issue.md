# Contract: FR-003, FR-004 (failure-issue sites), FR-005, FR-006, FR-007 — the durable failure issue

`research.md` D4/D5/D6 explain the one-composite-two-operations design and
the deliberate, recorded divergence this contract must NOT flatten;
`data-model.md`'s "Shared Definition: Durable failure issue" table gives
the field shape.

## `.github/actions/_shared/durable-failure-issue/action.yml` (NEW)

**Inputs**: `token`, `operation` (`report` \| `close`), `label`,
`label-color`, `label-description`, `title` (report only), `body-file`
(report only — a path the caller has already written; this action never
templates a body itself, so it does not compete with `wing-commander-callout`
as a second body-rendering surface), `close-comment` (close only).

**Steps**: one `shell: bash` step. Both operations begin with the same
lookup:
```
existing="$(gh issue list --repo "$GITHUB_REPOSITORY" --label "$LABEL" --state open --json number --jq '.[0].number // empty' 2>/dev/null || true)"
```
- `operation: report` — if `existing` is set, `gh issue comment $existing
  --body-file "$BODY_FILE"`, `action-taken=commented`; else,
  `gh label create "$LABEL" --color "$LABEL_COLOR" --description
  "$LABEL_DESCRIPTION" --force` then `gh issue create --title "$TITLE"
  --label "$LABEL" --body-file "$BODY_FILE"`, `action-taken=created`.
- `operation: close` — if `existing` is set, `gh issue close $existing
  --comment "$CLOSE_COMMENT"`, `action-taken=closed`; else,
  `action-taken=none` (no-op — matches today's behaviour: nothing to
  close is not an error).

**Outputs**: `issue-number`, `action-taken`.

## Call sites: `report`, `auto-release.yml`'s `report` job (3 sites)

The label (`auto-release:failed`), color, and description stay identical
across all three; each site keeps composing its own `title` and writing
its own body to a temp file (verification-failed, version-collision,
release-dispatch-failed — the three distinct bodies today), then calls
`uses: ./.github/actions/_shared/durable-failure-issue` with
`operation: report`.

## Call site: `close`, `auto-release.yml`'s `report` job (1 site)

`operation: close`, `close-comment: "Resolved: ${NEXT_VERSION} released."`
— unchanged text from today's `close_failure_on_success`.

## Call site: `report`, `auto-update-spec-kit.yml` (1 site)

Of `auto-update-spec-kit.yml`'s four `auto-update:failed` sites, only the
rollback site — "File or update the auto-update:failed issue (rollback)"
— matches this composite's report contract (lookup by label,
comment-if-found, create-if-not) and calls
`uses: ./.wing-commander-pipeline/.github/actions/_shared/durable-failure-issue`
with `operation: report`, label `auto-update:failed`, color `E99695`,
composing its own title and writing its own body to a temp file.

The other three `auto-update:failed` sites do not implement the shared
idiom's full lookup-then-create-or-comment shape and are deliberately left
calling their own narrower logic (FR-007's no-regression rule):
- "Label the issue as failed" and "Label the issue as failed (prepare
  failed)" each label a specific, already-known issue via
  `gh issue edit --add-label`, with no lookup-by-label search.
- "Post closing summary (revert)" looks up by label but must never create
  an issue when none is open — it comments on a found issue and leaves it
  open, which is neither this composite's `report` operation (which
  creates when nothing is found) nor its `close` operation (which closes
  the found issue).

**No site calls `operation: close`** — D5 is the explicit, recorded
decision this contract exists to prevent a well-meaning consolidation from
silently correcting: `auto-update-spec-kit.yml`'s `auto-update:failed`
issues are only ever closed by a human, because a rollback having happened
is itself durable signal worth keeping visible (`auto-update-spec-kit.yml`'s
own comment at the pr-merged job, today's lines 2970-2971).

## Fallback (FR-006)

If the composite step is skipped, `issue-number`/`action-taken` are empty;
each call site's existing step-summary/log line already tolerates an empty
issue number (it was informational, not branched on, at every current
site) — no new fallback branch needed.

## Gate coverage

Gate 52 fails on any occurrence, anywhere under `.github/workflows/` or
`.github/actions/` outside this composite's own `action.yml`, of the
co-occurrence of a `gh label create ... --force` call and a
`gh issue list ... --label "..." --state open --json number --jq
'.[0].number // empty'`-shaped lookup in the same step or job.
