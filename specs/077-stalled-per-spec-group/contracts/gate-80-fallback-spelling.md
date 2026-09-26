# Contract: Gate 80's fourth accepted spelling

`.github/scripts/verify-spec-branch-push-concurrency.py` today accepts
exactly three group spellings via `PER_SPEC_GROUP_RE`:

```
wing-commander-${{ inputs.spec-dir }}
wing-commander-${{ needs.<job>.outputs.spec-dir }}
wing-commander-${{ matrix.spec_dir }}
```

FR-018 requires a fourth, exact spelling for the per-PR fallback
`stalled-job-concurrency.md` introduces — accepted in addition to, never in
place of, the three above.

## New pattern

```python
# The per-PR fallback pr-conversation.yml's stalled job declares when
# needs.resolve-identity.outputs.spec-dir is empty (specs/077). Distinct
# from PER_SPEC_GROUP_RE: this is not a per-spec group at all, and its
# literal "pr-conversation-pr-{0}" / "inputs.pr-number" text is specific
# to this one job, not a general fourth per-spec spelling other stages
# could adopt.
PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE = re.compile(
    r"^wing-commander-\$\{\{\s*needs\.([\w-]+)\.outputs\.spec-dir\s*\}\}"
    r"\$\{\{\s*needs\.\1\.outputs\.spec-dir\s*==\s*''\s*&&\s*"
    r"format\('pr-conversation-pr-\{0\}',\s*inputs\.pr-number\)\s*\|\|\s*''\s*\}\}$"
)
```

`evaluate()`'s acceptance check:

```python
if isinstance(group, str) and (
        PER_SPEC_GROUP_RE.match(group.strip())
        or PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE.match(group.strip())):
    continue
```

The `([\w-]+)` / `\1` backreference requires the identical `needs.<job>`
name in both halves — a group reading `spec-dir` from one job while gating
the fallback on a *different* job's result is a real bug (the fallback
would trigger on the wrong job's failure), and must still fail the gate.

## Required self-test cases (added to `self_test()`, alongside the existing cases)

| # | Case | Job's declared group | Expect |
|---|---|---|---|
| 1 | Exact fallback spelling, no waiver | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` | Passes (no failure reported for this job) |
| 2 | Mismatched job name across the two halves | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.other-job.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` | Fails — the backreference does not match |
| 3 | The bare degenerate constant | `wing-commander-` | Fails (already covered by `PER_SPEC_GROUP_RE`'s non-match; asserted again here as the literal shape this fallback exists to avoid producing) |
| 4 | Near-miss literal (`pr-conversation-{0}`, missing `-pr-`) | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-{0}', inputs.pr-number) || '' }}` | Fails |
| 5 | Near-miss identifier (`inputs.pr_number`, underscore) | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr_number) || '' }}` | Fails |
| 6 | The three existing spellings, unaffected | (existing `GOOD_GROUP`/`MATRIX_GROUP`/`NEEDS_GROUP` fixtures) | Still pass, unchanged |

Cases 1–5 follow this script's existing `case(...)` self-test helper
exactly (same `_job()`/`RUN_PUSH` fixtures already defined in the file);
case 6 is a regression assertion that the new pattern is additive, not a
replacement (Constitution VIII: no gate that currently catches something may
stop catching it).

## Non-goals

- No change to the three existing spellings' regex.
- No change to the waiver file's schema or `load_waivers()`/`evaluate()`'s
  waiver-matching logic — only the "is this group acceptable on its own
  merits" branch gains a second pattern.
- This fourth spelling is not offered as a general-purpose escape hatch: its
  literal text names `pr-conversation-pr-` and `inputs.pr-number`
  specifically, so a different future stage needing a similar fallback would
  need its own reviewed spelling, not a copy of this one (FR-018: "the only
  addition to the accepted set").
