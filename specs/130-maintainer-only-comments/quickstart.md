# Quickstart: validating "Comment-Triggered Stages Act Only on Maintainers"

## 1. Local gates (before any push)

```bash
python .github/scripts/verify-maintainer-only-comments.py
python .github/scripts/verify-maintainer-only-comments.py --self-test   # every mutant must fail
python .github/scripts/run-local-gates.py   # filtered on Windows; compare failures with an origin/main worktree
```

Expected:
- The new gate passes on the tree, and every mutant is caught.
- The updated fixture gates pass: `verify-clarification-gating.py`, `verify-issue-context-single-home.py`, the auto-release e2e decision gates, and any others named in T001.

## 2. Harness checks (no network)

- **Clarify check step (D1).** Run it against a fake `gh` that returns, in turn, `OWNER`, `COLLABORATOR`, `NONE`, `CONTRIBUTOR`, a `Bot` user and a failed read.
  - `maintainer=true` only for the first two.
  - The failed read fails the step.
- **Relay composite (D3).** Run it with an issue whose author is `NONE`: the paragraph is appended exactly once. Run it with `OWNER`: the file is unchanged.
- **Comment filter (D4).** Use comments from a maintainer, from a non-maintainer author and from a bot. Only the maintainer's comment is staged, and `excluded-human-count=1`.
- **Spec Kit updater reply (FR-002).** `bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t6_reply`: the agent's context keeps the issue body, the pipeline's own question and maintainers' comments, and drops a non-maintainer's and another bot's; only a label the pipeline posted is accepted.

## 3. Scratch-repository run (before the PR)

Use `charlesguse/wing-commander-auto-release-scratch`, outside auto-release's 09:09 UTC run:
1. Pin its intake and clarify wrappers to the local branch's commit, on a throwaway ref.
2. Open an issue as the owner and label it `spec-request`. Intake's clarification-questions comment must not carry the relay paragraph, because the author is `OWNER`.
3. Answer as the owner. Clarify runs and folds the answer.
4. Restore the wrapper pins.

A private repository has no non-maintainer commenter, so the refusal and relay-present paths rest on section 2.

## 4. After merge (prove-after-merge)

- The next scheduled auto-release e2e passes its clarification step (SC-004).
- One real clarify run on this repository shows the check step with `maintainer=true` and an unchanged flow.
- The Spec Kit updater's reply path runs only while an options question is open, and this repository has never had one, so no after-merge run exercises it. Section 2's `t6_reply` checks, which lint-workflows.yml runs on every change, are its evidence.
