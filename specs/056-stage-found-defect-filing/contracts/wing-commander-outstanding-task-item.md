# Contract: FR-017, FR-018, FR-019 — the outstanding-task-item composite

`research.md` D9 explains why this is promoted out of `pr-conversation.yml`
in this feature rather than left as a second inline copy.

## `.github/actions/wing-commander-outstanding-task-item/action.yml` (NEW)

**Inputs**:

| name | required | default | description |
|---|---|---|---|
| `token` | true | — | token to comment with |
| `issue-number` | true | — | the lifecycle issue to post to |
| `phrase` | true | — | the sentence fragment naming what happened, e.g. "a new lifecycle issue was opened" |
| `artifact-url` | true | — | the URL of the thing spun off |
| `context` | false | `""` | optional trailing parenthetical, e.g. `(from PR #123)` or `(run https://...)` — the composite appends it verbatim after the artifact URL if non-empty |

**Steps**: one `shell: bash` step:

```bash
gh issue comment "$ISSUE_NUMBER" --body "- [ ] $PHRASE — $ARTIFACT_URL${CONTEXT:+ $CONTEXT}"
```

**Outputs**: none — a failure to comment is the caller's to handle (both
callers already run this under `continue-on-error`/failure-tolerant
gating for other reasons; this composite adds no new tolerance logic of
its own).

## Call sites

- `pr-conversation.yml`'s existing "Post outstanding task item on the
  lifecycle issue" step is replaced by a `uses:` call to this composite,
  with `phrase` taken from the same `case "$EFFECTIVE_CATEGORY"` switch
  that already exists there (unchanged routing logic — only the final
  `gh issue comment` line moves into the composite) and `context` set to
  `(from PR #$PR_NUMBER)`.
- `wing-commander-stage-findings` (new, this feature) calls it once per
  filed-or-appended finding, per `data-model.md`'s "Outstanding Task Item"
  entity, with `context` set to `(run $RUN_URL)`, and skips the call
  entirely when no lifecycle issue number was passed to it (FR-019) —
  recording that absence in its own run-summary output instead.

## Gate coverage

`verify-single-home-idioms.py` gains a `DECLARED_HOMES["outstanding-task-item"]`
entry pointed at this composite's `action.yml`, so a future `gh issue
comment ... "- [ ] ..."` literal appearing anywhere else fails the gate
the same way a second `durable-failure-issue`-shaped lookup would.
