# Quickstart: Validating Trusted Composite Resolution

Prerequisites: a checkout with this feature implemented, and the local
gate suite runnable (`python .github/scripts/run-local-gates.py`). Steps
4-5 need a real dispatched run against a disposable/test repository you
own — never against this repository or any repository you do not control.

## 1. Static: Gate 99 against the shipped workflow

```bash
python .github/scripts/verify-board-loop-composite-provenance.py
python .github/scripts/verify-board-loop-composite-provenance.py --self-test
python .github/scripts/run-local-gates.py
```

Expected: the first two exit 0 (the shipped file is clean; every
self-test mutation is caught — contracts/gate-99.md, data-model.md "Gate
99 Fixture Set"); the third runs the full suite including Gate 98
(unchanged) and Gate 99, both green.

To confirm Gate 99 can actually fail its own subject (Principle VIII),
temporarily reintroduce one raw `uses: ./.github/actions/wing-commander-context`
line in `board-loop.yml`, re-run the first command, confirm it fails
naming the job and the line, then revert.

## 2. Static: no raw composite reference survives anywhere in the file

```bash
grep -n 'uses: \./\.github/actions/' .github/workflows/board-loop.yml
```

Expected: no output. Every reference reads
`uses: ./.wc-pristine-repo/.github/actions/...`.

## 3. Static: the sidecar cannot be staged

```bash
git check-ignore -v .wc-pristine-repo
```

(Run from a checkout where `.wc-pristine-repo` has been created, e.g. by
manually running the checkout step's shape locally, or by inspecting a
real Actions run's logs.) Expected: `.gitignore` reports the match.
Confirm the negative directly: `mkdir .wc-pristine-repo && touch
.wc-pristine-repo/probe && git add -A && git status --porcelain` shows
nothing staged for that path, then clean up
(`rm -rf .wc-pristine-repo`).

## 4. User Story 1 — the judging surface cannot be edited by the branch it judges

In a disposable/test repository running this feature's `board-loop.yml`,
open a fix PR whose diff:

- replaces one composite the `review` job calls (e.g.
  `wing-commander-agent-verdict`) with a version that emits a
  distinguishing marker or approves unconditionally, and
- replaces one helper script the `readiness` job imports with a version
  that always reports `ready: true`.

Drive that PR through `review` and `readiness`. Confirm: the review pass
shows the trusted behaviour (the distinguishing marker never appears in
the review's output; the verdict is computed by the real classifier), and
readiness's decision does not simply mirror the branch's forged helper.
Confirm the PR's own diff (visible on GitHub) never gained
`.wc-pristine-repo` files.

Repeat for the `fix` job's resume path: stop a fix mid-round (so the
branch exists with no PR yet), edit one composite `fix` calls on that
branch, resume the job, and confirm the resumed run's post-branch-switch
composites are the trusted commit's copies, not the branch's.

## 5. User Story 2 — an old branch never hard-fails on a missing composite

Cut an item branch from a commit that predates one of the composites
`review`/`readiness` reference today (or, more simply, delete that
composite's directory on the test branch entirely). Drive it through
`review` and `readiness`. Confirm both jobs complete — the composite
resolves from `.wc-pristine-repo`, never from the branch — where before
this feature the job would have failed to locate the action.

## 6. SC-002/SC-006 spot check

Across the runs in steps 4-5: confirm review/readiness behaviour was
byte-identical to a control run against an unmodified branch (SC-002), and
confirm no PR from any of these runs ever contained a
`.wc-pristine-repo` path in its file list (SC-006,
`gh pr view <n> --json files`).
