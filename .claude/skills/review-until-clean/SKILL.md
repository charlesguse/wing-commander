---
name: "review-until-clean"
description: "Drive a fix PR (a maintenance, gate or tooling change) through fresh-reviewer passes until one comes back clean, CI is green on the exact head and it can merge: each pass reviews, verifies every finding, fixes the real ones with a test that fails without the fix, and runs the gate suite; after every pass the loop checks itself for thrash and stops to ask instead of grinding. Use for 'review and fix until green', 'review and merge', 'add it to your queue'. Lifecycle PRs already get this loop from lifecycle-review-gate.yml -- don't run it on one unless the owner asks."
compatibility: "Needs git, gh, python3 and the Agent tool (one fresh reviewer per pass)"
user-invocable: true
disable-model-invocation: false
---

# Reviewing a fix PR until a pass comes back clean

## What this loop is for, and how it goes wrong

CLAUDE.md requires a code review before every fix PR merges, with the
findings fixed in the same PR; constitution X spells out what makes the
review count: an independent review, a second agent invocation sharing no
context with the fixer, ending with zero open findings, on a head whose
checks are green. One review rarely gets there. On 2026-10-09 #976, #977,
#981 and #984 each took three passes (a typical run of real findings was
4, then 1, then none) and #978 took four.

The way this loop fails is not stopping too early; it is not stopping.
#969's four passes found 10 cases Gate 12 would miss, and 8 of them were in
the PR's own new parsing. #954 took 15 rounds and grew into a full shell
parser. Every round found something real, so every round looked like
progress. The tell was where the findings were: in code the loop itself had
written. Step 4 measures that after every pass.

## Before the first pass

- Record H0, the PR's head SHA before any review fix. Every later signal is
  measured against it.
- Start a ledger in the scratchpad (`review-ledger-<PR>.md`): one row per
  pass with the head before and after, and every candidate finding with its
  verdict (fixed, refuted, dismissed, out of scope), file:line and one line
  of reasoning. The ledger is what the next reviewer is told and what the
  thrash check reads; the reviewers themselves remember nothing.
- Keep to two local agents at a time (CLAUDE.md; pipeline runs share the
  usage window). Note any lifecycle in `stage:implement` before starting, so
  a stall there can be attributed.

## 1. One pass = one fresh reviewer that also fixes

Start a new general-purpose agent with worktree isolation for every pass.
Never resume an earlier pass's agent: the pass that declares the PR clean
must share no context with whoever wrote the fixes. Give it:

- the PR number and branch, and the governing spec if
  `spec-cross-reference`'s script finds one;
- the ledger's **already dismissed** list ("don't reopen these unless you
  can show the dismissal was wrong") and the earlier passes' fix commits
  ("check that these hold; look hardest at the code they added");
- the skills to run on the diff (`origin/main...HEAD`):
  - `code-review` at the effort in "Effort level" below, always;
  - `spec-cross-reference` when a spec governs the changed files;
  - `review-step-gating` when the diff touches an `if:`, a
    `continue-on-error:` or a step that exits non-zero;
  - `container-shell-safety` when it touches a `container:` job or a `run:`
    step inside one;
  - `security-review` when it touches a credential, a token mint, a
    `permissions:` block or a write path.

The reviewer sorts every candidate:

- **Real and in scope:** a realistic path from a real caller or input to
  the failure, traced, in code this PR adds or changes. Fix it.
- **Refuted:** name what refutes it: an FR, a structural guarantee (a
  concurrency group, an allowlist), an unreachable path. Never drop one
  silently.
- **Already dismissed:** matches a ledger entry. One line.
- **Out of scope:** real, but not this PR's. Not fixed here; it becomes a
  Maintenance backlog line carrying `(found by the code review of #N)`.

A comment or wording nit counts as a finding only if it touches
something a gate reads. Workflow comments are load-bearing (gates
byte-compare them), so a comment edit in a workflow is a code edit; a
comment no gate reads is not. Any other change to code is a finding.

## 2. Each fix comes with a test that fails without it, checked alone

A fix with no test that fails without it is a claim, not a fix. Add a gate
scenario, fixture or self-test mutation that exercises the finding, then
check **that test alone** with the fix taken out, not the whole suite: in a
throwaway worktree at the new head, put the fixed code back the way it was
and keep the new test.

```
OLD=<head before this pass>
git worktree add --detach "$SCRATCH/unfixed" HEAD
git -C "$SCRATCH/unfixed" checkout "$OLD" -- <the files the fix changed, not the test files>
(cd "$SCRATCH/unfixed" && python .github/scripts/run-local-gates.py <gate-name-filter>)
git worktree remove --force "$SCRATCH/unfixed"
```

When the fix and its test share a file (a gate and its own self-test),
revert just the fix's hunk in the worktree instead.

`run-local-gates.py` treats its arguments as a substring filter on gate
names and runs only the gates that match (a filter that matches nothing
prints the list). Read the failure line: the test must fail **for the
reason the finding names**, not because a fixture is missing. The same
filter must pass on the new head.

## 3. Then the full suite, once per pass, on the new head

```
python .github/scripts/run-local-gates.py --jobs 4
```

Run it in the background and wait on its exit. Don't poll with
`pgrep -f run-local-gates.py`: the watcher's own command line matches and
it never exits. Never kill the run. Some failures are local-only; check
#889 for gates known to be load-sensitive or to need Docker, re-run any
single failure alone with its filter before believing it, and say in the
pass report which failures were waived and why.

Commit (with the session's trailers), push, and report: every candidate
with its verdict, which test covers each fix, the new head SHA, the gate
result, the out-of-scope list, and **CLEAN** (no real in-scope findings;
a commit that only changes comments or wording no gate reads doesn't
change that, as on #984's last pass) or **NOT CLEAN**.

## 4. The thrash check, after every pass

```
python3 .claude/skills/review-until-clean/scripts/thrash_signals.py \
  --base origin/main --heads H0,H1,...,Hn \
  --finding path:line --finding path:line ... --counts c1,c2,...,cn
```

`--finding` takes this pass's real findings (on the latest head), and
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

- **Continue** while the count falls and findings are mostly on the PR's
  original lines.
- **Stop and ask the owner**, from pass 3 on, when any of these holds:
  the count did not fall; at least half of this pass's real findings are
  self-inflicted; a fixed finding recurs; two passes in a row churned an
  earlier pass's lines; the diff has grown by more than half since H0.
- **Budget:** 5 passes, the same as board-loop.yml's
  `BOARD_LOOP_ROUND_BUDGET` and lifecycle-review-gate.yml's
  `LIFECYCLE_REVIEW_ROUND_BUDGET`. At the budget, stop whatever the
  signals say.

Stopping means asking, with what is still open, the signals that tripped,
and options, recommending one:

- **(a) merge as is**, with the remaining findings filed as backlog lines;
  fits when they are edge cases in new code that fails closed;
- **(b) one targeted pass with a different method**, e.g. differential
  fuzzing against real bash for a parser (#969's option b);
- **(c) trim the scope:** split out or drop the part that keeps breeding
  findings.

## Effort level

`medium` by default; one `high` pass for high-risk diffs.

`code-review`'s effort levels trade precision for recall: higher levels
report more findings, more of them uncertain. In this loop that trade
mostly goes the wrong way:

- The loop is already a recall multiplier. Three independent medium passes
  are three samples, and the observed 4 -> 1 -> 0 runs show that they
  converge.
- This repository's failure mode is too much recall, not too little. The
  thrash on #954 and #969 was reviewers pushing ever-deeper edge cases into
  a shell parser; the Gate 12 lines on #889 are full of them, several
  marked "(contrived)". Higher recall feeds exactly that.
- Every uncertain finding still needs a traced path and a failing test
  before anything changes, and pipeline runs and local agents share one
  usage window.

Run **one `high` pass** once medium comes back clean, as the last pass
before merge, when the diff changes what a miss would be expensive in:

- a credential, or a token mint or refresh;
- a `permissions:` block, or a `gh` call that writes;
- a merge gate, a kill switch, or anything that decides a durable action
  (constitution VIII, IX, X);
- the published `workflow_call` contract (constitution VII).

Its real findings re-enter the loop like any other pass's; its uncertain
ones are verified or dismissed, never fixed on speculation.

When a whole class of defect keeps slipping past medium, the fix is not a
higher effort on every PR. Write it down where every pass will catch it: a
specialist skill (that is how `review-step-gating`,
`container-shell-safety` and `spec-cross-reference` came about) or a gate.

## 5. Merge

Merge only with the owner's permission for this class of PR, given
explicitly or as a standing instruction. Never merge a spec PR, a plan PR or
a constitution amendment: those merges stay human (constitution V).

When a pass is CLEAN:

1. Every check run on the exact head SHA has completed successfully. A head
   with no checks is not green (constitution VIII).
2. The PR is mergeable.
3. Squash-merge, pinned to that head:
   `gh api -X PUT repos/{owner}/{repo}/pulls/N/merge -f merge_method=squash -f sha=<head>`.

- **Workflow-scope refusal:** when GitHub refuses a PR touching
  `.github/workflows/` because the token lacks the `workflow` scope, hand
  the merge to the maintainer (CLAUDE.md). Never push to main around it.
- **CI failure:** a flake gets one re-run, and only when the failing test
  is outside the diff's reach and passes alone locally. A second failure is
  real. Record the flake as a backlog line either way.

After merge, tick the PR's backlog line and file the out-of-scope findings.
If the change runs only in Actions, prove it with the `prove-after-merge`
skill.

## Reporting

Per PR, in chat:

- **Passes:** one line each, with the count of real findings and what they
  were.
- **Thrash signals:** the last numbers.
- **Merge:** merge SHA and CI state, or the stop question with its options.
- **Backlog:** the lines it filed.
