# Data Model: sync-from-main

No new persisted store. All state is derived from git and the run.

## Sync method (input value)

| Field | Value |
|---|---|
| Source | repository variable `WING_COMMANDER_SPEC_BRANCH_SYNC` (consuming instrument) → stage input `sync-method` (published contract) |
| Domain | `rebase` \| `merge`; unset or empty → `rebase` (wrapper default) |
| Validation | `wc_sync_from_main.py validate-method`; any other value → job fails naming the value and the accepted set, before discovery selects a branch |
| Lifetime | read every run; not stored per lifecycle (FR-012) |

## Per-branch sync attempt (job-local, step outputs)

| Field | Description |
|---|---|
| `before` | spec branch tip at checkout (reused from rebase) |
| `main_sha` | `origin/<default-branch>` tip fetched for this attempt |
| `outcome` | `current` (branch already contains `main_sha`; no commit) \| `clean` \| `conflict` \| `error` |
| `conflicted_tree` | tree OID from `git merge-tree --write-tree` (conflict markers in conflicting paths only); recorded only for `conflict` |
| conflict manifest | newline list of conflicting paths; seeded deterministically, extended by the agent, narrowed to the project folder (spec 114) |
| `push` / `escalate` | booleans from the verify step, as in rebase |

### State transitions

```
checkout ─► fetch main ─► contains main? ─yes─► current (end, no write)
                              │no
                              ▼
                     git merge --no-ff --no-commit
              ┌───────────────┼────────────────┐
           exit 0        unmerged paths      other failure
              │               │                  │
            clean         conflict             error ─► abort ─► escalate
              │               │
        git commit      agent resolves ─► verify-scope ─pass─► publish
              │                                │fail/incomplete
           publish                             └──► merge --abort ─► escalate
publish: plain `git push` (fast-forward only). Rejected ⇒ skip silently, next run retries.
```

## Sync commit

- Parents: `[previous branch head, main_sha]` in that order.
- Message: `sync: merge <default-branch> into <spec-branch>`.
- Created even when its tree equals the first parent's tree (FR-003).
- Carries no lifecycle work other than conflict resolutions (FR-011: those
  lines count as lifecycle work because they differ from `main`).

## Escalation record (unchanged shape)

- Label `rebase:blocked` (both methods, owner decision 2026-10-22).
- Marker `<!-- wing-commander-rebase: blocked branch-sha=<before> main-sha=<main> -->`
  — discovery's dedup reads it unchanged.
- Prose differs by method; the marker and label do not.

## Recorded heads (existing, no schema change)

Review round heads, fold-range starts and "started from" SHAs remain ordinary
SHAs. Invariant under merge sync: each stays an ancestor of the branch tip until
cleanup, which is what SC-001 asserts.
