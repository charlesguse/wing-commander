# Quickstart: validating 095

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
