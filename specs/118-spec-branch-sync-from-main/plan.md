# Implementation Plan: Keep Spec Branches Current by Merging Main (sync-from-main)

**Branch**: `spec/118-spec-branch-sync-from-main` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/118-spec-branch-sync-from-main/spec.md`

## Summary

Add a second way to keep in-flight `spec/*` branches current: merge the default
branch into the branch with a sync commit, never rewriting history, selected by
the repository variable `WING_COMMANDER_SPEC_BRANCH_SYNC` (`rebase` default,
`merge`). The wrapper reads the variable and passes it as a new typed
`sync-method` input on the existing `rebase.yml` stage (additive contract
widening, constitution VII). The merge arm shares discovery, the matrix,
credential handling, agent verdict, metrics and escalation with rebase; it
differs in how the branch is updated (`git merge --no-ff --no-commit` then an
explicit commit), how a conflict is verified (tree comparison against
`git merge-tree --write-tree`, restricted to the conflict manifest), and how it
publishes (plain fast-forward push, no force). All judgment lives in a new
deterministic helper `wc_sync_from_main.py`, with a gate that runs real git
fixtures through every failure branch. Consumers of branch history
(`wc_convergence.py`, finalize's fold range) are made to attribute `main`-side
commits to the base and report an explicit reason when a rebase made a signal
unknowable. Design detail: [research.md](research.md).

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (reusable `workflow_call` stage), bash steps, Python 3 (stdlib only) for deterministic helpers and gates; git ≥ 2.38 (already the image floor; `merge-tree --write-tree` needs it).

**Primary Dependencies**: `anthropics/claude-code-action@v1` (conflict agent, unchanged), existing composites `wing-commander-tool-args`, `-turn-ceiling`, `-agent-verdict`, `-containment`, `-callout`, `-post-agent-credential-status`, `-metrics-summary`.

**Storage**: N/A — state is git history and step outputs; no new file or field in `spec-meta.json`.

**Testing**: checked-in git-fixture gate `verify-sync-from-main.py` (origin + clone per case, mutation cases), existing `verify-rebase-discover-selection.py` and convergence tests extended; whole suite via `python .github/scripts/run-local-gates.py`.

**Target Platform**: GitHub Actions runners / adopter container images.

**Project Type**: CI pipeline (published reusable workflows + composites + gate scripts).

**Performance Goals**: no regression — one extra `git merge-tree` per conflicting branch; no extra agent calls.

**Constraints**: no force-push under `merge` (SC-002); `rebase` method byte-identical in names, history and reporting (SC-004); stage reads no `vars.*` (VII); every agent step keeps explicit model and `--max-turns` (II); agent never gets `git commit`/`push`/`gh` (V).

**Scale/Scope**: one stage file edited, one script and one gate added, two consumer scripts touched, docs in three files.

## Constitution Check

*GATE: passes before Phase 0; re-checked after Phase 1.*

| Principle | Verdict | Notes |
|---|---|---|
| I Guide | Pass | Built through the pipeline (issue #1074 → spec 118). |
| II Model tiering | Pass | Reuses `inputs.model` (Sonnet default) and `max-turns` (50) for the conflict agent; ceiling and verdict composites unchanged. No new agent invocation. |
| III GitHub-native | Pass | Escalation on the lifecycle issue as today; no new surface. |
| IV Automation-first | Pass | Replaces a manual "rebase it yourself" remedy with "merge main"; still reported on the issue. |
| V Security | Pass | Same trusted-ref checkout, same bot identity, same least-privilege tools (`git merge --continue/--abort` instead of rebase verbs); pipeline-checkout guard and post-agent re-checkout steps shared unchanged. |
| VI Portability | Pass | No repo names; paths resolve relative to the project folder; subfolder lifecycles honoured via existing `wing-commander-project`/containment composites. |
| VII Two interfaces | Pass | `sync-method` is a declared, typed, defaulted input — an additive widening, documented in `contracts/`. The variable is read only in the wrapper. `.github/scripts/` helper is internal. |
| VIII Green means it | Pass | `verify-sync-from-main.py` runs real git; every failure branch has a fixture; mutation cases; registered in the gate registry (`lint-workflows.yml`) so it runs locally and in CI with the same arguments. |
| IX Deterministic judgment | Pass | Method validation, publish refspec and scope verification are code, not prompt. |
| X Bounded autonomy | N/A | No board-loop or merge-class change; final PR merge untouched (FR-013). |

**Post-design re-check**: unchanged. No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/118-spec-branch-sync-from-main/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── sync-method-input.md
└── tasks.md             # /speckit-tasks — not created here
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── rebase.yml                   # + sync-method input; discover validates it;
│   │                                #   merge arm steps (attempt/clean/verify/publish/escalate),
│   │                                #   leg name & prose switch on the method
│   └── wing-commander-rebase.yml    # + sync-method: vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase'
├── scripts/
│   ├── wc_sync_from_main.py         # NEW: validate-method / decide / verify-scope / publish-refspec
│   ├── verify-sync-from-main.py     # NEW gate: git fixtures, every failure branch, mutations
│   ├── verify-single-home-idioms.py # + single-home check for the merge scope check/validation
│   ├── wc_convergence.py            # main-side commits attribute to base; n/a reason text
│   └── wc_convergence_tests/        # + fixtures: sync commit between rounds; post-rebase n/a reason
└── workflows/lint-workflows.yml     # register the new gate

docs/
├── adoption.md                      # `### rebase`: input row, merge side effect, variable, squash assumption
├── architecture.md                  # Rebase section: "Merge sync" and the trade-off
└── setup.md                         # WING_COMMANDER_SPEC_BRANCH_SYNC in the variable list
```

**Structure Decision**: extend the existing `rebase` stage rather than add a
stage (research D1); keep deterministic logic in one stdlib Python helper with a
fixture gate (D6), matching how the rebase stage already pairs with
`verify-rebase-discover-selection.py`.

## Complexity Tracking

No constitution violations to justify.
