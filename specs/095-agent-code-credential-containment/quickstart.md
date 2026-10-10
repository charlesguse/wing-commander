# Quickstart: validating 095

## Call-site notes (T001-T003, recorded at implement cycle 2)

Anchors on the branch as of this cycle (line numbers drift; names are stable):

- `board-loop.yml` `fix` job: step `Run local gate suite (fixer)` (id
  `gate-suite`), then `Comment the failing gate on the issue (fixer, gate suite
  red)`, `Re-check kill switch ...`, `Push and open the PR` (`git push origin
  "HEAD:refs/heads/$BRANCH"`). Job outputs `pr-number` and `breach` come from
  `push-pr` / `final-diff-backstop`, which stay in the publish job.
- `board-loop.yml` review-fixup: step writing
  `board-review-fixup-gate-suite.log`, then a push guarded by
  `if ! git push origin "HEAD:refs/heads/$BRANCH"`.
- `implement.yml`: cycle gate-suite preflight (writes `gate-suite-cycle.log`,
  skips when `run-local-gates.py` is absent), retry preflight
  (`gate-suite-retry.log`), and the spec-branch push `git push origin
  "HEAD:refs/heads/${SPEC_PREFIX}$SLUG"` plus the agent-composed `git push`
  further down.

What the existing gates assert about the in-job gate step (hot spot):

- Gate 98 (`verify-board-loop-helper-provenance.py`): every `python3` in
  fix/review/readiness is `-I` and imports from `$RUNNER_TEMP/wc-pristine`;
  the `GATE_SUITE_CALL` (`python3 .github/scripts/run-local-gates.py`) is the
  sole carve-out, so moving the step needs the carve-out moved with it.
- Gate 104 (`verify-board-loop-composite-provenance.py`): composites are
  `uses:`d from `.wc-pristine-repo`; a new gate-suite job must do the same.
- `verify-implement-gate-suite-preflight.py`: asserts the preflight text and
  the `script-exists` skip shape of both implement sites.
- `verify-stage-tool-lists.py`: owns the `Bash(python ...run-local-gates.py:*)`
  grant and the stage write-boundary lists the `.git/**` deny (T029) extends.

Gate registration: a gate is a `verify-*.py` invoked from a
`lint-workflows.yml` step (plain run plus `--self-test`) with path triggers;
`wc_gate_registry.py` recovers argv from those steps and `run-local-gates.py`
runs them, so one registration serves CI and local (FR-019/FR-021). Gates 141
and 142 are the examples (Gate 143, `verify-composite-run-provenance.py`, is
registered the same way).

## Job-split hazards found at implement cycle 4 (for T011-T014)

Splitting board-loop's `fix` job at the push boundary is not a mechanical
move. (1) `fix` holds `concurrency: group: wing-commander-board-loop`; a
second job in the same group would queue behind it and deadlock, while a
publish job with no group lets the next queued run start before the push.
(2) `review` reads `needs.fix.outputs.pr-number`/`breach` and `needs.fix.result`,
so the job that pushes must keep the name `fix` or those readers move with
it. (3) Every post-gate step reads `steps.base`, `steps.ctx`, the snapshot
and the `.wc-pristine-repo` copy, so the publish job must rebuild all four
from the bundle. Gates 98/104 and the resume-gating gate each hold `fix` to
its current shape and move in the same commit. None of this could be run
(the gate suite needs PyYAML, absent in this job), so the split was not
attempted blind.

Prerequisites: a checkout of the branch, Python 3 with PyYAML, `jq`, `git`.

## Local

1. Full PR-time suite: `python .github/scripts/run-local-gates.py`
   — expect every new gate listed in
   [contracts/new-gates.md](contracts/new-gates.md) to pass.
2. Each gate's failure branches: `python .github/scripts/<gate>.py --self-test`
   — expect every fixture to be rejected for its named reason.
3. Hardened push: `python .github/scripts/verify-hardened-push.py --self-test`
   plants a `pre-push` hook and a `url.<base>.insteadOf` value in a scratch
   repo; expect the hook not to run and the push to reach the stated bare repo.
4. Reader: feed `wc_gate_verdict.py` a missing file, junk, a SHA-mismatched
   verdict and a valid pass; expect `fail, fail, fail, pass`.

## After merge (FR-024 / SC-008)

1. Probe fixture: on a throwaway fix branch add a gate script that prints its
   environment and tries `chmod u+w` on the snapshot and an append to
   `$GITHUB_ENV`. Drive one board-loop item through `fix` (via `gh workflow
   run` on the wrapper that can dispatch it). Expect: no token in the printed
   environment, later steps unaffected, and a red suite yields a fenced comment
   and `board:stalled`, no push.
2. Re-drive a green item: expect push and an opened PR.
3. Re-drive one `implement` cycle: expect the gate verdict to reach the agent
   prompt and the stage to push through the hardened composite.
4. Record run URLs on the PR or #737.
