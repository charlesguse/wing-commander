---
name: "review-until-clean"
description: "Drive a fix PR (a maintenance, gate or tooling change) through review passes until one comes back clean, CI is green on the exact head and it can merge. Every pass is a brand-new session that reviews the PR with code-review (no findings cap), fixes the real findings with a test that fails without each fix, runs the gate suite and reports on the PR; the next pass is another new session. Between passes the orchestrating session checks the loop for thrash and stops to ask instead of grinding. Use for 'review and fix until green', 'review and merge', 'add it to your queue'. Lifecycle PRs already get this loop from lifecycle-review-gate.yml -- don't run it on one unless the owner asks."
compatibility: "Needs git, gh, python3, and a way to start a fresh session per pass (create_session in the cloud, claude -p locally)"
user-invocable: true
disable-model-invocation: false
---

# Reviewing a fix PR until a pass comes back clean

## What this loop is for, and how it goes wrong

CLAUDE.md requires a code review before every fix PR merges, with the
findings fixed in the same PR. Constitution X spells out what makes the
review count:

- an independent review, sharing no context with whoever wrote the code;
- zero open findings at the end;
- a head whose checks are green.

One review rarely gets there. On 2026-10-09 #976, #977, #981 and #984 each
took three passes (a typical run of real findings was 4, then 1, then
none), and #978 took four.

The way this loop fails is not stopping too early; it is not stopping.
#969's four passes found 10 cases Gate 12 would miss, and 8 of them were in
the PR's own new parsing. #954 took 15 rounds and grew into a full shell
parser. Every round found something real, so every round looked like
progress. The tell was where the findings were: in code the loop itself had
written. The thrash check measures that after every pass.

## Who does what

- **The orchestrating session** is the one the owner is talking to. It:
  - starts every pass;
  - keeps the ledger and runs the thrash check;
  - decides whether to continue, stop or merge;
  - files Maintenance backlog lines.

  It never reviews or fixes the PR itself.
- **A pass session** is a brand-new, top-level session started for one
  pass. It reviews the PR, fixes what it finds, reports, and ends. The
  next pass is another new session.

Why a fresh top-level session for every pass, not a subagent:

- **It gets the full review.** A top-level session can start its own
  agents, so `code-review` runs its full recipe: independent finders, then
  a separate pass that checks each candidate. Without that, the recipe falls
  back to one unchecked pass in a single context.
- **It is independent.** A new session shares nothing with whoever wrote
  the code it reviews, including the previous pass's fixes. So the pass
  that declares the PR clean is the independent review constitution X asks
  for.

## Before the first pass (orchestrator)

- **Record H0,** the PR's head SHA before any review fix. Every later
  signal is measured against it.
- **Keep a ledger** in the scratchpad (`review-ledger-<PR>.md`). Per pass:
  the head before and after, the real-finding count, and every candidate
  with its verdict and file:line, copied from the pass's report on the PR.
  The next pass is told the ledger's dismissed list; the thrash check reads
  the counts.
- **Keep to two concurrent sessions or agents.** Pipeline runs and local
  sessions share one usage window (CLAUDE.md). Note any lifecycle in
  `stage:implement` before starting, so a stall there can be attributed.

## Starting a pass session (orchestrator)

One pass session at a time per PR. Each starts from the head the last one
left.

The prompt carries:

- "You are pass N of the review-until-clean loop on PR #X (branch B)";
- the head it must start from;
- the effort (`medium`, or `high` for the final pass described under
  "Effort level");
- the ledger's dismissed list ("don't reopen these unless you can show the
  dismissal was wrong");
- the earlier passes' fix commits ("check that these hold; look hardest at
  the code they added");
- **this skill's "The pass session" section, verbatim.**

The PR branch may predate this skill, so don't ask the pass session to
find the section itself. Extract it here and paste it in:

```
sed -n '/^## The pass session/,/^## The thrash check/{/^## The thrash check/!p}' \
  .claude/skills/review-until-clean/SKILL.md
```

How to start one:

- **In the cloud:** call `create_session` with:
  - `source_url`: the repository;
  - `source_revision`: the PR branch;
  - `outcome_branch`: the PR branch, so it pushes to the PR and not to a
    session branch of its own;
  - `title`: "Review pass N of #X";
  - never `permission_mode: plan`, which would wait for an approval nobody
    gives.

  It won't report back by itself. Schedule one check-in with `send_later`
  for about 25 minutes (passes took 15–20), then:
  - `get_session`'s `status_bucket` says whether it finished or failed;
  - the pass's report comment on the PR says what it did.
- **Locally:** a new session in a worktree of the PR branch. Run
  `claude -p "<prompt>"` in the background from the orchestrator, or have
  the owner open one. Give it permissions to edit, run the gates, commit
  and push.

## The pass session

You are one pass of a review loop on a pull request. You review the PR,
fix what you find, and report. You don't merge, you don't start another
pass, and you don't edit the Maintenance backlog; the orchestrating
session does those.

**1. Start from the head you were given.** Check out the PR branch and
confirm `HEAD` is the head named in your prompt. If it isn't, report that
and stop.

**2. Review.** Run `code-review <effort> --max-findings all origin/main...HEAD`.

- **Why the explicit range:** with no target, the review diffs against
  the branch's own upstream, which on a pushed PR branch is empty.
  `origin/main...HEAD` is the PR's whole diff, and it needs no GitHub
  access.

- **Why `--max-findings all`:** without it a medium review reports only
  its 8 most severe findings. The loop needs all of them, both to fix them
  in this pass and to count them truthfully for the thrash check. The
  recipe can still clamp `all` to 32 in some modes, so a review reporting
  exactly 32 was cut short; say so.
- **Check it ran its full recipe.** If the review's summary says it was a
  single-pass review done without the Agent tool, it did not run its
  checked, multi-finder recipe. Report that and stop: this is not a valid
  pass.
- **Other skills, when the diff calls for them:**
  - `spec-cross-reference`: a spec governs the changed files;
  - `review-step-gating`: the diff touches an `if:`, a
    `continue-on-error:` or a step that exits non-zero;
  - `container-shell-safety`: it touches a `container:` job or a `run:`
    step inside one;
  - `security-review`: it touches a credential, a token mint, a
    `permissions:` block or a `gh` call that writes.

**3. Sort every candidate.** Each one gets exactly one verdict:

- **Real and in scope:** a realistic path from a real caller or input to
  the failure, traced, in code this PR adds or changes. Fix it.
- **Refuted:** name what refutes it: an FR, a structural guarantee (a
  concurrency group, an allowlist), an unreachable path. Never drop one
  silently.
- **Already dismissed:** it matches the dismissed list in your prompt.
  One line.
- **Out of scope:** real, but not this PR's. Don't fix it; list it in your
  report.

A comment or wording nit counts as a finding only if it touches something
a gate reads. Workflow comments are load-bearing (gates byte-compare
them), so a comment edit in a workflow is a code edit; a comment no gate
reads is not. Any other change to code is a finding.

**4. Give each fix a test that fails without it, and check that test
alone.** A fix with no such test is a claim, not a fix. Add a gate
scenario, fixture or self-test mutation that exercises the finding. Then
check only that test, not the whole suite: in a throwaway worktree at the
new head, put the fixed code back the way it was and keep the new test.

```
OLD=<the head you started from>
git worktree add --detach "$SCRATCH/unfixed" HEAD
git -C "$SCRATCH/unfixed" checkout "$OLD" -- <the files the fix changed, not the test files>
(cd "$SCRATCH/unfixed" && python .github/scripts/run-local-gates.py <gate-name-filter>)
git worktree remove --force "$SCRATCH/unfixed"
```

- A file the fix added doesn't exist at `$OLD`, and naming it makes the
  checkout fail with `pathspec did not match`, leaving the worktree
  fixed. Leave it out of the checkout and delete it in the worktree
  instead: `git -C "$SCRATCH/unfixed" rm -q <the files the fix added>`.
- When the fix and its test share a file (a gate and its own self-test),
  revert just the fix's hunk in the worktree instead.
- `run-local-gates.py` treats its arguments as a substring filter on gate
  names and runs only the gates that match (a filter that matches nothing
  prints the list).
- Read the failure line. The test must fail **for the reason the finding
  names**, not because a fixture is missing.
- The same filter must pass on the new head.

**5. Then run the full suite once, on the new head.**

```
python .github/scripts/run-local-gates.py --jobs 4
```

- Run it in the background and wait on its exit, and never kill the run.
- Don't poll with `pgrep -f run-local-gates.py`: the watcher's own command
  line matches, so it never exits.
- Some failures are local-only. Check #889 for gates known to be
  load-sensitive or to need Docker, and re-run any single failure alone
  with its filter before believing it.

**6. Commit with the session's trailers, and push to the PR branch.**

**7. Report on the PR.** Post one comment, with `gh` or the session's
GitHub tools, that begins with `<!-- review-until-clean pass N -->` and
contains:

- the review's own effort line;
- the head you started from and the head you pushed;
- every candidate, with its verdict, file:line and one line of why;
- which test covers each fix;
- the gate result, naming any failure you waived and why;
- the out-of-scope list;
- **CLEAN** (no real in-scope findings) or **NOT CLEAN**. A commit that
  only changes comments or wording no gate reads doesn't make a pass
  NOT CLEAN, as on #984's last pass.

End the comment with the attribution footer, and end the session with
the same report.

## The thrash check (orchestrator, after every pass)

```
python3 .claude/skills/review-until-clean/scripts/thrash_signals.py \
  --base origin/main --heads H0,H1,...,Hn \
  --finding path:line --finding path:line ... --counts c1,c2,...,cn
```

`--finding` takes this pass's real findings, located on the latest head.
`--counts` takes the real findings per pass from the ledger. The script
reports, from git alone:

- **self-inflicted share:** how many findings sit on lines the loop's own
  fix commits wrote, rather than on the PR as submitted;
- **churn:** lines each pass rewrote that an earlier pass wrote (a fix of a
  fix; a pass undoing a pass is the extreme);
- **growth:** the PR's diff against main at every head.

Add the one signal git can't see: **recurrence**, a finding the ledger
marks fixed that a later pass raises again (the fix didn't hold).

Rules (starting points; tune them in this file, not per run):

- **Continue** while the count falls and the findings are mostly on the
  PR's original lines.
- **Stop and ask the owner**, from pass 3 on, when any of these holds:
  - the count did not fall;
  - at least half of this pass's real findings are self-inflicted;
  - a fixed finding recurs;
  - two passes in a row churned an earlier pass's lines;
  - the diff has grown by more than half since H0.
- **Budget:** 5 passes, the same as board-loop.yml's
  `BOARD_LOOP_ROUND_BUDGET` and lifecycle-review-gate.yml's
  `LIFECYCLE_REVIEW_ROUND_BUDGET`. At the budget, stop whatever the
  signals say.

Stopping means asking the owner. Give them what is still open, the
signals that tripped, and these options, recommending one:

- **(a) Merge as is,** with the remaining findings filed as backlog lines.
  This fits when they are edge cases in new code that fails closed.
- **(b) One targeted pass with a different method,** e.g. differential
  fuzzing against real bash for a parser (#969's option b).
- **(c) Trim the scope:** split out or drop the part that keeps breeding
  findings.

## Effort level

`medium` by default, with no findings cap. One `high` pass for high-risk
diffs. Never `low`.

What each level does, from the `code-review` recipe in Claude Code 2.1.296.
Re-read it when the recipe changes; the levels differ in more than "how
many findings".

| Level | Finders | Checks each finding | Default cap | Skips |
|---|---|---|---|---|
| `low` | one pass over the diff hunks, no subagents, no full-file reads | no | about 4 | test and fixture hunks (`test/`, `spec/`, `__tests__/`, `*_test.*`, `*.test.*`, `fixtures/`, `testdata/`); flags only runtime bugs visible in the hunk |
| `medium` | 8 angles (3 correctness, 3 cleanup, altitude, conventions), up to 6 candidates each | yes, one vote, precision | 8 | nothing |
| `high` | the same 8 angles | yes, one vote, recall-biased | 10 | nothing |
| `xhigh`, `max` | 10 angles (5 correctness), up to 8 each, plus a sweep for gaps | yes, one vote, recall | 15 | nothing |

- **Never `low`.** It doesn't read `.github/scripts/fixtures/` (60 files
  the gates run on) or any other fixture hunk, and nothing checks what it
  reports.
- **Every pass runs with `--max-findings all`.** That lifts the default
  cap (see "The pass session"). The setting is remembered for later
  `/code-review` runs where the pass ran:
  - a cloud pass session's environment is thrown away afterwards;
  - a local pass session on the owner's machine leaves it set, and the
    owner resets it with `--max-findings default`.

Above `low`, the levels trade precision for recall: higher levels report
more findings, more of them uncertain. In this loop that trade mostly goes
the wrong way:

- **The loop already multiplies recall.** Three independent medium passes
  are three samples, and the observed 4 -> 1 -> 0 runs show that they
  converge.
- **This repository's failure mode is too much recall, not too little.**
  The thrash on #954 and #969 was reviewers pushing ever-deeper edge cases
  into a shell parser. The Gate 12 lines on #889 are full of them, several
  marked "(contrived)". Higher recall feeds exactly that.
- **Every finding costs.** An uncertain finding still needs a traced path
  and a failing test before anything changes, and pipeline runs and local
  sessions share one usage window.

Run **one `high` pass**, in its own fresh session, once medium comes back
clean, as the last pass before merge. Do it when the diff changes
something a miss would be expensive in:

- a credential, or a token mint or refresh;
- a `permissions:` block, or a `gh` call that writes;
- a merge gate, a kill switch, or anything that decides a durable action
  (constitution VIII, IX, X);
- the published `workflow_call` contract (constitution VII).

Its real findings re-enter the loop like any other pass's. Its uncertain
ones are checked or dismissed, never fixed on speculation.

When a whole class of defect keeps slipping past medium, the fix is not a
higher effort on every PR. Write the class down where every pass will catch
it: a specialist skill (that is how `review-step-gating`,
`container-shell-safety` and `spec-cross-reference` came about) or a gate.

## Merge (orchestrator)

Merge only with the owner's permission for this class of PR, given
explicitly or as a standing instruction. Never merge a spec PR, a plan PR or
a constitution amendment: those merges stay human (constitution V).

When a pass is CLEAN:

1. Every check run on the exact head SHA has completed successfully. A head
   with no checks is not green (constitution VIII).

   Some PRs have nothing for CI to run. lint-workflows.yml runs on a pull
   request only when a changed path matches its `pull_request: paths:`
   list, and a change to most of `.claude/skills/` or to CLAUDE.md matches
   none of it. In that case:
   - say so on the PR, with the last pass's local gate-suite result;
   - merge only on the owner's explicit go-ahead for that PR.
2. The PR is mergeable.
3. Squash-merge, pinned to that head:
   `gh api -X PUT repos/{owner}/{repo}/pulls/N/merge -f merge_method=squash -f sha=<head>`.

If it can't merge:

- **Workflow-scope refusal:** when GitHub refuses a PR touching
  `.github/workflows/` because the token lacks the `workflow` scope, hand
  the merge to the maintainer (CLAUDE.md). Never push to main around it.
- **CI failure:** a flake gets one re-run, and only when the failing test
  is outside the diff's reach and passes alone locally. A second failure is
  real. Record the flake as a backlog line either way.

After merge:

- tick the PR's backlog line;
- file the passes' out-of-scope findings as backlog lines carrying
  `(found by the code review of #N)`;
- if the change runs only in Actions, prove it with the `prove-after-merge`
  skill.

## Reporting

Per PR, in chat:

- **Passes:** one line each, with the count of real findings and what they
  were.
- **Thrash signals:** the last numbers.
- **Merge:** merge SHA and CI state, or the stop question with its options.
- **Backlog:** the lines it filed.
