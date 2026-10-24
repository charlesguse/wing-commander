# Contract: `sync-method` input and merge-sync behaviour

**Layer**: published contract (`.github/workflows/rebase.yml`), plus the
consuming-instrument wrapper line that feeds it. Constitution VII.

## Stage input (additive widening)

| Name | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `sync-method` | string | no | `rebase` | `rebase`: today's behaviour, unchanged. `merge`: bring `main` into each in-flight spec branch by a sync commit; never rewrite history. |

- No input, secret or output is renamed or removed. No new secret. No output.
- An empty string is treated as `rebase` (an adopter's wrapper that forwards an
  unset variable keeps working). Any other value fails the `discover` job:
  `::error::wing-commander rebase: sync-method '<value>' is not valid; accepted values are 'rebase' and 'merge'`
  before any branch is selected, so no matrix leg runs and no branch is touched.
- The stage reads no `vars.*` and no `github.event.*` for this feature.

## Wrapper (consuming instrument, `wing-commander-rebase.yml`)

```yaml
sync-method: ${{ vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase' }}
```

Triggers unchanged: non-bot push to `main` (via redispatch), nightly,
`workflow_dispatch`.

## Behaviour under `merge`

| Situation | Result |
|---|---|
| Branch already contains `origin/<default>` | No commit, no push. |
| Otherwise, clean merge | One two-parent sync commit (first parent = old tip, second = `origin/<default>` tip); plain fast-forward `git push`; no `--force*`, no `+` refspec. |
| Merged tree equals branch tree | The sync commit is still created. |
| Conflict | Agent resolves under `model`/`max-turns` with tools `Read,Edit,Grep,Glob,Bash(git status/diff/add/merge --continue/merge --abort)`; deterministic `verify-scope` then decides publish vs escalate. |
| Push rejected (remote head moved) | Skipped silently; next run retries. |
| Scope check fails / agent unhealthy / markers left | `git merge --abort`, nothing pushed, `rebase:blocked` label + callout on the lifecycle issue with the SHA dedup marker. |

Pre-sync refusals, discovery exclusions, project-folder scoping, metrics,
execution-log, cost line, over-budget callout and agent-verdict handling are
the same steps rebase uses.

## Names

| Method | Matrix leg / job title | Step summary prefix | Escalation callout summary |
|---|---|---|---|
| `rebase` | `rebase (<slug>, <spec_dir>, <issue>)` — unchanged | unchanged | `Manually rebase this branch` — unchanged |
| `merge` | `Sync spec branch with main (<slug>, <spec_dir>, <issue>)` | `sync-from-main` | `Merge main into this branch` |

## Deterministic helper contract (`.github/scripts/wc_sync_from_main.py`)

| Subcommand | Input | Exit / output |
|---|---|---|
| `validate-method <value>` | method string | 0 and prints the normalised method; 1 with the error above |
| `decide --main <sha>` | git state | prints `current` \| `merge` |
| `verify-scope` | `--before --main --conflicted-tree --manifest --project --verdict` | 0 = pass; 1 = fail with each reason on stderr (wrong parents, path outside manifest, leftover marker, unhealthy verdict) |
| `publish-refspec <branch>` | spec branch name | prints `HEAD:refs/heads/<branch>`; exits 1 for a value with `+` or a force token |

Every exit-1 branch has a checked-in fixture run through the gate registry
(`verify-sync-from-main.py`), FR-016.

## n/a reason (FR-014), consuming-side text

Convergence report cells and hand-off text that cannot be computed after a
rebase read: `n/a — usually a rebase or force-push rewrote history; merge sync avoids it`. #1062's
stored per-round diff size continues to feed growth.
