# Contract: FR-005, FR-009 — pr-conversation.yml's Stop procedure consumes the shared vocabulary

`research.md` D6 explains the rationale and the accepted narrow behaviour
change.

## `.github/workflows/pr-conversation.yml`, "Stop procedure" step (MODIFIED — one line)

**Before**:
```
if grep -qiE '409|already completed|cannot cancel' "$RUNNER_TEMP/cancel-err.txt" 2>/dev/null; then
  outcome="already-completed"
else
  outcome="cancel-failed"
fi
```

**After**:
```
if bash .github/actions/_shared/cancel-already-terminal.sh "$(cat "$RUNNER_TEMP/cancel-err.txt" 2>/dev/null)"; then
  outcome="already-completed"
else
  outcome="cancel-failed"
fi
```

**Unchanged**: everything else in this step — the `$RUNNER_TEMP/cancel-err.txt`
capture, the `outcome="cancelled"` default and the initial `if ! GH_TOKEN=...
gh run cancel ...` attempt above it, all three downstream `gh pr comment`
bodies (`cancelled` / `cancel-failed` / `already-completed`), the
`impl_run_id` lookup-and-cancel block, and every token this step uses. FR-009
is explicit that this site's own reporting is not moved, merged, or made
configurable by this change.

## Accepted behaviour change at this site

A failure whose text is not an already-terminal refusal but contains the
bare digits `409` (e.g. a permission error quoting a run id or URL) now
resolves to `outcome="cancel-failed"` instead of `outcome="already-completed"`.
This is FR-005's anchoring applied to a site that previously had no anchor,
and it moves this site *toward* its own governing requirement
(`contracts/autonomy-and-confirmation.md`: a cancellation failure must never
be reported to a maintainer as a confirmed completion), never away from it.
No fixture in `specs/033-pr-conversation-commands`'s own coverage asserts
the unanchored bare-`409` behaviour as a requirement (checked: `verify-gate-12.py`
asserts token routing, not the classification text) — this is a corrected
defect at this site, not a change requiring `specs/033`'s contracts to be
amended.

## Gate coverage

This step's own T031/T062-lineage coverage (`verify-gate-12.py`, spec 033's
Gate 12 token-permission assertions) is unaffected — it asserts *which
token* runs `gh run cancel`/`gh run list`, not the text of the
classification. No existing gate in this repository fixtures this step's
`grep` line directly; `contracts/gate-coverage-087.md` covers the new
shared script's own coverage, which is where this line's behaviour is now
proven.
