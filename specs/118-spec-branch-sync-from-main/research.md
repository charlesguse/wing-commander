# Research: Keep Spec Branches Current by Merging Main (sync-from-main)

No `[NEEDS CLARIFICATION]` markers remain in spec.md (three clarifications were
answered in the 2026-10-21 and 2026-10-22 sessions). The decisions below close
the open design points the spec leaves to the plan.

## D1. One stage, one input — not a second stage

- **Decision**: Keep `rebase.yml` as the single published stage and add one
  typed input, `sync-method` (string, `rebase` | `merge`, default `rebase`).
  The merge path is a second arm of the same per-branch matrix job, selected
  by `if: inputs.sync-method == 'merge'` on its steps.
- **Rationale**: Discovery, the matrix, the container/runner/environment
  plumbing, credential refresh, verdict/metrics/cost reporting and the
  escalation path are about 80% of the file and are exactly what FR-009 and
  FR-010 say must be shared. A second stage workflow would paste them
  (CLAUDE.md "Shared logic has exactly one home"). Adding an input with a
  behaviour-preserving default is an additive widening of the published
  contract (constitution VII, FR-006).
- **Alternatives**: a new `sync-from-main.yml` stage (duplicates ~1000 lines,
  new published id, adopters must re-wire); a boolean `merge: true` input
  (cannot grow a third method, and the wrapper variable is a word, not a flag).

## D2. Switch plumbing

- **Decision**: `wing-commander-rebase.yml` passes
  `sync-method: ${{ vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase' }}`. The
  stage reads no `vars.*`. Validation happens in the stage's `discover` job,
  first step after checkout, by calling `wc_sync_from_main.py validate-method`
  (D6). An unknown value fails the job before `Select in-flight branches`,
  so no matrix leg exists.
- **Rationale**: FR-004/005/006/012. The variable is read per run, so
  switching mid-lifecycle (FR-012) needs no state; `discover` selects the same
  branches either way.
- **Alternatives**: validate in the wrapper (the stage would then trust an
  unchecked input and an adopter's own wrapper could skip it); pin the method
  into `spec-meta.json` per lifecycle (rejected by FR-012).

## D3. Name

- **Decision**: matrix-leg `name:` becomes
  `${{ inputs.sync-method == 'merge' && format('Sync spec branch with main ({0}, {1}, {2})', ...) || format('rebase ({0}, {1}, {2})', ...) }}`.
  The step summary lines, the escalation heading and the callout summary read
  "sync-from-main" / "Sync spec branch with main" under merge. Under `rebase`
  every existing string stays byte-identical (SC-004).
- **Rationale**: FR-007. Gate registry byte-compares rebase comments, so the
  rebase-method strings are not touched; merge strings are new lines.
- **Alternatives**: rename the job for both methods (breaks SC-004 and the
  `rebase (…)` leg name that checks and docs cite).

## D4. How the merge is made and published

- **Decision**: In the checked-out spec branch (fetch-depth 0, as today):
  1. `git fetch --no-tags origin "$DB:refs/remotes/origin/$DB"` (never a bare
     fetch — same lease-preserving rule as rebase).
  2. If `git merge-base --is-ancestor origin/$DB HEAD`, outcome `current`,
     no commit (FR-003 first half).
  3. Else `git merge --no-ff --no-commit origin/$DB`. Exit 0 → outcome `clean`;
     `--no-commit` plus an explicit `git commit` guarantees the sync commit
     exists even when the merged tree equals the branch tree (FR-003 second
     half, which `--no-ff` alone does not give for an already-up-to-date-tree
     case). Unmerged paths → outcome `conflict`; other failure → `error`.
  4. Publish with a plain `git push origin HEAD:refs/heads/<spec>` — no `+`,
     no `--force*`. A non-fast-forward means the remote head moved: the push is
     rejected and the next run retries (FR-002, spec edge case 3).
- **Rationale**: A plain push of a descendant is the strongest no-force form:
  the server enforces fast-forward, so SC-002 holds even if a script bug sent
  the wrong ref. Lease semantics are unnecessary because there is nothing to
  overwrite.
- **Commit message**: `sync: merge <default-branch> into <spec-branch>`.
  Author is the App identity set the same way as in the rebase arm.

## D5. Scope verification for a conflicting merge

- **Decision**: Deterministic and tree-based. Before the agent runs, the step
  records `T_conflicted = git merge-tree --write-tree --no-messages
  origin/$DB HEAD` (git ≥ 2.38, already the pipeline's image floor — see the
  `verify-image-prerequisites` job). That tree is the merge with conflict
  markers left in the conflicted paths only. After the agent finishes, the
  check passes only if all of:
  - HEAD is a two-parent commit, first parent = recorded pre-merge tip, second
    parent = recorded `origin/$DB` tip (no extra commits, no rewrites);
  - `git diff --name-only T_conflicted HEAD^{tree}` ⊆ the conflict manifest
    (narrowed to the project folder by the existing containment composite,
    spec 114 FR-021) — i.e. the agent changed only conflicting paths relative
    to a clean merge;
  - no path in the manifest still contains a conflict marker line
    (`^(<<<<<<<|=======|>>>>>>>)( |$)`) in HEAD;
  - the agent verdict is `healthy`.
- **Rationale**: Rebase checks per replayed commit; a merge is one commit, so a
  single tree comparison is both simpler and stricter. Spec edge case "textually
  clean but a file outside the conflict set differs from a clean merge" is
  exactly the `diff` clause.
- **Alternatives**: re-run the merge and compare (non-deterministic across git
  versions' rename detection — `merge-tree` is used once and the OID stored
  instead); agent-reported manifest only (insufficient, constitution IX).

## D6. Where the deterministic logic lives

- **Decision**: New `.github/scripts/wc_sync_from_main.py` with subcommands
  `validate-method`, `decide` (current/clean/conflict from git state),
  `verify-scope`, and `publish-refspec` (emits the one allowed refspec and
  refuses any with `+` or a force flag). The workflow steps call it; it holds
  all branching. A new gate `verify-sync-from-main.py` builds real local git
  fixtures (origin + clone) and exercises every failure branch (FR-016,
  constitution VIII): unknown method, already-current, clean, same-tree merge,
  conflict resolved in scope, resolution touching an extra path, leftover
  markers, wrong parents, remote moved between checkout and publish (push
  rejected, branch untouched), publish refspec with `+`. Mutation cases revert
  each guard and assert the gate then fails, as
  `verify-rebase-discover-selection.py` does.
- **Rationale**: FR-016 forbids a gate that only inspects workflow text.
  A single-home helper also keeps `rebase.yml` from growing another 200 lines
  of inline bash. The composite-action home is not needed because only
  `rebase.yml` consumes it; a script under `.github/scripts/` matches the
  `wc_*` pattern already used by the stage.
- A second gate extension adds "single home" to the nearest existing gate
  (`verify-single-home-idioms.py`): the merge-sync scope check and the method
  validation must not be copied into any other workflow.

## D7. Agent tool surface for the conflict arm

- **Decision**: Compose via the existing `wing-commander-tool-args` composite
  with `default-allowed-tools` = `Read,Edit,Grep,Glob,Bash(git status:*),
  Bash(git diff:*),Bash(git add:*),Bash(git merge --continue:*),
  Bash(git merge --abort:*)`; same disallowed list, same model and `max-turns`
  inputs, same turn-ceiling and verdict composites (constitution II, V; FR-008).
  The prompt text is the merge analogue of the rebase prompt (one stop, not
  many; resolve, `git add`, `git merge --continue`).
- **Alternatives**: allow `git commit` (wider than needed; `merge --continue`
  keeps the two-parent commit and the prepared message).

## D8. Escalation under merge

- **Decision**: Reuse the `Abandon and escalate` arm. Under merge it runs
  `git merge --abort` instead of `git rebase --abort`, keeps the label
  `rebase:blocked` (owner decision 2026-10-22) and the SHA dedup marker
  `<!-- wing-commander-rebase: blocked … -->` unchanged so discovery's dedup
  needs no change, and swaps the prose: heading "Spec branch sync needs a
  human", remedy "merge `$DB` into the branch (`git merge origin/$DB`) and push,
  or decide how to reconcile". Callout summary: "Merge main into this branch".
- **Rationale**: FR-008 and the 2026-10-22 clarification.

## D9. History-derived consumers (FR-011, FR-014)

Findings from reading `.github/scripts/wc_convergence.py` and finalize:

- `compute_history` already works when every head is an ancestor of the next
  (merge sync preserves that), and `measure()` already warns about merged
  commits that `--base` does not contain.
- **Decision (attribution)**: `Origins` must label a commit that is reachable
  from the sync commit's second parent (the `main` side) as base-origin, not
  `passK`. Implement by passing the latest recorded `main` tip as an extra
  "base-side" ref: any commit that is an ancestor of it and not first-parent
  reachable from the branch's own work is `base`. Deterministic, in the script.
- **Decision (diff size / fingerprint)**: `diff_size` and `diff_fingerprint`
  already diff against `git merge-base(base, head)`. After a sync commit the
  merge base advances to the synced `main`, so changes that arrived from `main`
  drop out and conflict-resolution lines (which differ from `main`) stay in —
  exactly FR-011. No change; a fixture proves it.
- **Decision (finalize)**: the fold range start is a recorded SHA; under merge
  it stays reachable, so `git log --grep '^fold(' range_start..tip` resolves.
  No finalize change beyond a fixture asserting the range resolves across a
  sync commit. Merge commits are excluded from the `fold(` grep by subject.
- **Decision (rebase path, FR-014)**: keep #1062's stored per-round diff size.
  Replace the existing "(the branch was rebased or force-pushed)" n/a prose in
  `render_handoff` with the reason "rebase rewrites history; merge sync avoids
  it" and add the same reason to the n/a cells; add no new workaround.
- **Rationale**: Keeps the consumer change small and testable. Whether
  `Origins` can express "main-side" without a new input is confirmed in
  tasks (spike T-first); if it cannot, the fallback is `--base` taken as the
  latest `main` tip, which `measure()` already supports.

## D10. Final-merge method (FR-013)

- **Decision**: Documentation-only. A paragraph in `docs/adoption.md` states the
  squash-merge assumption. No check, warning or coupling is added anywhere.

## D11. Docs layer statement (FR-015)

- `docs/adoption.md` `### rebase` table (published contract) gains the
  `sync-method` input row and the merge side-effect row; `docs/setup.md` (or
  adoption's variable list — consuming instrument) gains
  `WING_COMMANDER_SPEC_BRANCH_SYNC`; `docs/architecture.md` Rebase section
  gains a "Merge sync" subsection with the linear-vs-stable-history trade-off.
  Each section opens with a sentence naming its layer.

## Decisions made without clarification

None of the spec's markers were open. Plan-level choices a reviewer may want to
revisit: the single-stage-with-input shape (D1), the `merge-tree` tree-compare
scope check (D5), and plain-push-no-lease publishing (D4).
