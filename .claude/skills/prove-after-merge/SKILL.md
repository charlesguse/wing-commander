---
name: "prove-after-merge"
description: "After a fix to behaviour that only runs in GitHub Actions merges, prove it: find the runs that reach the changed path, re-drive one (or wait for the run that is due), check that run took the changed path on the merged code, and record the evidence on the PR or issue. Use right after merging such a fix, or when asked to 'prove it', 're-drive a run', or 'check the run after merge'."
compatibility: "Needs git, gh, python3 with PyYAML; send_later or a /loop for the check-in"
user-invocable: true
disable-model-invocation: false
---

# Proving a merged fix in a real run

## Why this exists

CLAUDE.md and constitution X: a fix to behaviour that only runs in Actions
is proven after merge by re-driving one run, with the evidence recorded on
the PR or the issue. A green PR proves the gates, not the behaviour. The
gates run fixtures; the fix runs in a workflow nobody has watched yet.

Proof goes wrong in three quiet ways:

- **The wrong run.** auto-release alternates container and default-runner
  modes by day. A container-mode failure (#966) was closed by a
  default-runner pass that never exercised it. A run that cannot reach the
  changed path proves nothing, however green it is.
- **A green run that skipped the step.** A run can conclude `success` with
  the changed step skipped by its `if:`, or with the stage paused by a
  `WING_COMMANDER_*_PAUSED` variable.
- **No record.** Evidence that lives only in a session's chat is gone for
  the next one.

## Procedure

**1. Does it need a run, and which runs reach it?** On a checkout that
contains the merge:

```
python3 .claude/skills/prove-after-merge/scripts/redrive_candidates.py --merge <merge-sha>
```

It reuses the pipeline's own rules: `board_prove.actions_only()` says
whether a run is needed at all, and board-loop's prove job runs the same
code. A change to docs/specs only, or to `verify-*.py` only, is proven by
the PR's own checks.

Then it lists every workflow that reaches a changed path:

- dispatchable ones first, with any required inputs;
- then the ones reached only by a schedule or an event.

It also prints the board loop's own pick. That pick is narrower by design:
the pipeline may only re-drive a workflow it can correlate by an
`attempt-token`, and today that is `board-loop.yml` alone.

**2. Pick the run that actually exercises the fix.** From the candidates:

- **The right wrapper.** Prefer the wrapper that runs the changed code in
  the situation the fix is about. A fix to a stall path needs a run that
  stalls; a fix to container mode needs a container-mode day.
- **The changed step will run.** Read its `if:` and the job's, and check
  that the relevant `WING_COMMANDER_*_PAUSED` variable is not set.
- **Can't be dispatched into that situation?** Name the scheduled or
  event-driven run that will hit it, and when.
- **No candidate at all?** Say so on the PR: "no run reaches this change;
  proven by its checks only". Don't dispatch something unrelated to have
  a green run to point at.
- **One run, never a burst.** Re-driving an agent stage spends the usage
  window that pipeline runs and local sessions share.
- **Board-loop logic.** Use a directed proof run (`directed-stage`,
  `directed-issue`, `directed-pr`; see
  `specs/*/contracts/directed-proof-run.md`) rather than an ordinary tick.

**3. Dispatch, and find the run you started.**

```
R=$(gh repo view --json nameWithOwner -q .nameWithOwner)
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run <workflow>.yml --ref main [-f input=value ...]
gh run list --workflow <workflow>.yml --event workflow_dispatch \
  --json databaseId,createdAt,headSha,status --limit 5 \
  --jq "[.[] | select(.createdAt >= \"$since\")]"
```

Leave `attempt-token` blank on a manual dispatch; it is for the pipeline's
own correlation.

**4. Schedule the check-in; don't poll.** Look at how long the workflow
usually takes:

```
gh run list --workflow <workflow>.yml --status completed --limit 5 \
  --json createdAt,updatedAt
```

Then schedule one check-in for about then: `send_later`, or a trigger that
fires into this session. If the run is still going when it fires, re-arm
it once or twice; then say it is overdue rather than waiting forever.

**5. Verify. Green isn't enough.**

- **The run is on the merged code.**
  `git merge-base --is-ancestor <merge-sha> <run headSha>` must succeed.
- **The changed step ran.** Open the job: `gh run view <id> --json jobs`
  shows each step's conclusion.
- **It did what the fix says.** Read the log line the fix changes:
  `gh run view <id> --log --job <job-id> | grep ...`. Quote that line.

**6. Record the evidence.** Comment on the merged PR, or on the issue it
closed. Give:

- the run link and the head SHA it ran on;
- the step that exercised the change;
- the quoted line;
- the verdict.

End the comment with the attribution footer. If the fix came from the
Maintenance backlog, add "(proven by run N)" to its line there.

**7. If it fails, it's this fix's failure until shown otherwise.**

- Diagnose it from the log.
- Fix it on a new branch with the `review-until-clean` skill, or add a
  backlog line saying what failed and why it isn't this fix's.
- Tell the owner either way.

## Reporting

One line per merge:

- **Proven:** `#N proven by run <link> on <sha>: <quoted evidence>`.
- **Pending:** `#N proof pending: run <link> due ~<time>, check-in set`.
- **Not provable:** `#N no run reaches it` with the reason.
