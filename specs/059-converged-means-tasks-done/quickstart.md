# Quickstart: Validating the Converged-Means-No-Task-Is-Left Signal

This feature ships no user-facing surface to click through — it corrects a
deterministic decision inside `implement.yml`. Validation is entirely gate-
driven (Principle VIII: a manual demonstration is evidence for one reviewer,
not coverage for the next), plus one optional live replay.

## Prerequisites

- A checkout of this repository on `spec/059-converged-means-tasks-done`
  (or any branch carrying the shipped implementation).
- Python 3 with the repo's existing gate dependencies (`PyYAML`) — the same
  environment `python .github/scripts/run-local-gates.py` already requires.
- `git` and `bash` on `PATH` (the gate's synthetic-repo harness,
  `wc_shell_harness.py`, resolves a real bash the same way CI does).

## Run the full PR-time gate suite

```bash
python .github/scripts/run-local-gates.py
```

This runs every gate `lint-workflows.yml` invokes, including the new gate
this feature registers (`Gate <N> — ...`, see contracts/convergence-signal.md
and data-model.md's decision table). A clean run is the primary acceptance
signal for this feature — CLAUDE.md requires it before every push.

## Run just the new gate

```bash
python .github/scripts/verify-tasks-checkbox-convergence-signal.py
```

Expected: exits 0, having executed every fixture named in FR-019 against the
*shipped* `run:` text of `Read back cycle outcome`, `Read back retry
outcome`, `Consolidate final outcome`, and `Dispatch next step` — not a
hand-copied stand-in. Each fixture builds a synthetic git repo (a real bare
remote + clone, per `wc_shell_harness.py`) with a `tasks.md` at a
controlled checked/unchecked state at a base commit and at a tip commit, and
asserts the extracted shell produces the expected `ok`/`truncated`/
`converged`/`progressed`/`handoff`/`remaining` outputs. A trailing mutation
battery (mirroring `verify-truncated-cycle-carry-forward.py`'s `MUTATIONS`)
re-introduces the pre-fix behavior (deciding `converged` from the
converge-commit's presence alone, dropping the progress test, inverting it)
and asserts each mutant flips at least one scenario — proving the fixtures
are load-bearing (FR-020).

Also asserted by this gate, per FR-020: the gate step itself is present in
`lint-workflows.yml`, not `if: false`, and its `run:` line invokes this exact
script by path (the `check_gate_wired()`-style reflexive check Gate 30
already applies to itself).

## Sanity-check the composite action directly

```bash
# From a checkout with a synthetic tasks.md committed to a branch:
git show <ref>:<spec-dir>/tasks.md    # confirm the fixture looks right
# The composite itself is exercised indirectly by the gate above; there is
# no standalone CLI for it beyond the gate's harness, matching how
# wing-commander-spec-meta has no standalone CLI either.
```

## Replay spec 057's cycle-1 conditions (SC-003)

The gate's own fixture table includes this scenario by construction (11 of
65 tasks ticked, no `converge:` commit, a healthy non-truncated exit), but
to see it end-to-end against the real workflow file rather than a synthetic
harness, a maintainer can dispatch `implement.yml` by hand against a spec
branch seeded with the same shape (some tasks checked, most unchecked, no
`converge:` commit in range) and confirm the run posts `converged=false`
and dispatches the next cycle rather than finalize. This is not required for
every change to this feature — the gate is the checked-in proof (Principle
VIII) — but is useful the first time this ships, and per CLAUDE.md a change
to behavior that only runs in Actions should be proven after merge by
re-driving one run and recording the evidence on the PR or issue.

## Expected outcomes checklist

- [ ] `python .github/scripts/run-local-gates.py` exits 0.
- [ ] The new gate's fixture table covers every FR-019 branch: progress +
      no converge commit ⇒ false/next cycle; zero progress + no converge
      commit ⇒ false/handoff to finalize; zero progress + converge commit
      ⇒ false/next cycle; tick-one-untick-one ⇒ no progress; zero
      outstanding ⇒ true; truncated ⇒ false with no scan; unreadable
      `tasks.md` ⇒ loud failure; a `- [ ]` inside a fenced block ⇒ not
      counted; retry arm ⇒ identical verdict on its own base;
      no-converge-commit remaining-work report ⇒ non-empty.
- [ ] `implement.yml`'s header comment (lines 5-9), the "Failure detection"
      comment (1151-1164), both agent prompts' convergence-related text, and
      `docs/architecture.md`'s stage-4 section and risk-table row no longer
      describe "no converge commit ⇒ converged" as the rule (FR-015,
      FR-016, SC-009).
