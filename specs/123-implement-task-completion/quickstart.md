# Quickstart: validating Implement Finishes Its Tasks

Prerequisites: repo checkout on the feature branch; `bash`, `git`, `jq`, `python3`.

1. Run all gates: `python .github/scripts/run-local-gates.py`. Expect green, including the new buildable-classification gate.
2. Classification fixtures (`.github/scripts/fixtures/123-implement-task-completion/`): a tasks.md with a post-merge proof, a drill, a `.claude/` write, a fold line, a `[maintainer]` line, a standing line and ordinary tasks. Run `bash .github/actions/_shared/count-tasks-checkboxes.sh <ref> <path>`; expect only the ordinary tasks in `buildable-unchecked-*`, folds in `fold-unchecked-*`, the rest in `maintainer-items` (see contracts/buildable-classification.md).
3. Stop rule: feed `decide-implement-outcome.sh` the fixture cases (cap with buildable left → handoff; cap with folds only → no handoff; cap with maintainer-only → converged; blocker with buildable left → handoff). Expect the outputs in data-model.md.
4. Finalize/gate wait: run the verify gate over fixtures with buildable > 0 and = 0; expect refusal and acceptance respectively.
5. Migration: run the script with `dry-run` over fixtures for qualifying, folds-only, already-migrated and closed lifecycles; a second run changes nothing.
6. After merge (`prove-after-merge`): re-drive one implement cycle on a multi-phase spec and confirm it ticks tasks in more than one phase and records the cycle outcome line.
