# Contract: Hold interfaces

Live contract (fixed like code).

## Composite `wing-commander-lifecycle-hold`
| Input | Req | Notes |
|---|---|---|
| `mode` | yes | `check` or `set` |
| `issue` | yes | lifecycle issue number (declared input, VII) |
| `hold-label` | no | default `lifecycle:held` |
| `token` | yes | `issues: read` for check; `issues: write` for set |
| `reason` | set only | text posted on the issue |

Outputs: `state` (`clear|held|unreadable`, check), `set` (`true|already`, set).
Check never writes. Unreadable labels → `state=unreadable`; callers treat as
held and post the distinct "labels could not be read; dispatch implement by
hand once readable" text.

## Composite `wing-commander-fold-dispatch` (delta)
New input `hold-label` (default above). New output `withheld`
(`held|unreadable|""`). When non-empty: no `gh workflow run`,
`dispatched=false`, `ticket-unused=true`. Callers post the withheld line.

## Implement stage
Start check before any agent/write step. Held → job output `held=true`,
one status line on the issue, outcome `held` (not failure, no `stage:stalled`,
no dispatch, fold-queue ticket released). Fixture proves the watchdog does
not classify it as lost progress.

## Wrapper additions (consuming instrument)
- `wing-commander-5-implement.yml`: `issues: unlabeled`, filtered in-job to
  the hold label; release-plan → `workflow_dispatch` of itself; release note
  names the remover. Adopter docs updated.
- `wing-commander-9-pr-conversation.yml`: `lifecycle-stop` job (issue
  comments), `drop` job (PR comments, before classification).
- clarify: skips a strict-stop comment on a lifecycle issue.

## Fold-analyze verdict schema
See data-model.md. Model `claude-sonnet-5-5`, `--max-turns 8`, job
permissions `contents: read`.

## Drop comment grammar
```
drop
- Review finding: <title>
- Recurring review finding: <title>
```
First non-quoted line `drop` / `drop:` (case-insensitive); task lines exact
title match, optional `- [ ] ` prefix. Maintainer (OWNER/MEMBER/COLLABORATOR),
non-bot only.

## Merge preconditions (delta to spec 062 readiness-and-merge)
`may_merge` gains condition 9: the lifecycle issue does not carry the hold
label (fresh read, fail closed). Merge also refuses while constitution X on
the default branch does not name the hold condition (fail closed on read
error); readiness report names the unmet condition.

## Convergence signals (delta to spec 116 convergence-signals.md)
The gate passes the derived dismissed list as `evaluate(dismissed=...)` and
excludes dismissed fingerprints from folding and open in-scope counts.
