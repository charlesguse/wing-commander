# Quickstart: Validating the Implement Stage's Write Boundary

This feature ships no user-facing surface to click through — it adds a
stated boundary, a deterministic classification, and a routed filing path
inside `implement.yml`/`finalize.yml`. Validation is entirely gate-driven
(Principle VIII: a manual demonstration is evidence for one reviewer, not
coverage for the next), plus one optional live replay shaped like spec
060's `T055`.

## Prerequisites

- A checkout of this repository on `spec/090-stage-write-boundary` (or any
  branch carrying the shipped implementation).
- Python 3 with the repo's existing gate dependencies (`PyYAML`) — the same
  environment `python .github/scripts/run-local-gates.py` already requires.
- `git`, `bash`, and `jq` on `PATH` (the gate's synthetic-repo harness,
  `wc_shell_harness.py`, resolves a real bash the same way CI does).

## Run the full PR-time gate suite

```bash
python .github/scripts/run-local-gates.py
```

This runs every gate `lint-workflows.yml` invokes, including the new gate
this feature registers (`Gate <N> — the implement stage's write boundary is
stated, classified, and routed consistently`; see contracts/
write-boundary-gate.md). A clean run is the primary acceptance signal for
this feature — CLAUDE.md requires it before every push.

## Run just the new gate

```bash
python .github/scripts/verify-write-boundary.py
python .github/scripts/verify-write-boundary.py --self-test
```

Expected: both exit 0. The first executes every fixture named in
contracts/write-boundary-gate.md §"Pass conditions" against the *shipped*
`compose`/classification/read-back/lookup bodies — never a hand-copied
stand-in. The second reintroduces each of the seven mutations that same
contract names and asserts every one is caught.

## Sanity-check the two new composites directly

```bash
# Confirm the statement renders as expected for a given boundary:
# (exercised by the gate above via wc_shell_harness.run_step; there is no
# standalone CLI beyond the gate's own harness, matching how
# wing-commander-tasks-checkbox-count and wing-commander-spec-meta have
# none either)
git show <ref>:<spec-dir>/tasks.md    # confirm a fixture's tasks.md shape
```

## Replay a `T055`-shaped fixture end-to-end

The gate's own fixture table includes a scenario built directly from spec
060's `T055` (an unchecked task naming a `.claude/skills/...` path, nothing
else outstanding), but to see it end-to-end against the real workflow file
rather than a synthetic harness, a maintainer can:

1. Seed a throwaway spec branch's `tasks.md` with one checked-off task and
   one unchecked task naming a `.claude/skills/...` path.
2. Dispatch `implement.yml` by hand against that branch.
3. Confirm: the rendered prompt states the write boundary before the
   agent's first tool call; the agent does not attempt the out-of-boundary
   edit; the cycle ends without exhausting the iteration budget; a new
   issue appears labeled `route-out-of-boundary:implement`, naming the
   task and path; the lifecycle issue's recap comment names it; a second
   dispatch against the same unchanged `tasks.md` files no second issue.

This is not required for every change to this feature — the gate is the
checked-in proof (Principle VIII) — but is useful the first time this
ships, and per CLAUDE.md a change to behavior that only runs in Actions
should be proven after merge by re-driving one run and recording the
evidence on the PR or issue.

## Confirm `finalize.yml`'s pointer (SC-005)

Against the same throwaway branch, once the loop has handed off: dispatch
`finalize.yml` by hand and confirm the final PR's remaining-manual-work
list renders the out-of-boundary task as `<task text> — routed, see
<issue url>` rather than bare prose.

## Expected outcomes checklist

- [ ] `python .github/scripts/run-local-gates.py` exits 0.
- [ ] The new gate's fixture table covers every Edge Case in spec.md:
      single out-of-boundary path (routes); mixed paths (falls through);
      no path named (falls through); checked task with an out-of-boundary
      path (never touched); the same task met twice across specs (distinct
      fingerprints); a truncated cycle (files nothing); an empty boundary
      (states so plainly, classifies nothing); a boundary-widening task
      under `.claude/settings.json` (still routed, not fallen-through).
- [ ] An adopter who sets neither `no-write-paths` nor
      `write-boundary-label-prefix` sees `implement.yml` behave exactly as
      before, plus the added statement (SC-008).
- [ ] Spec 060's `T055` outcome (#490) is recorded on issue #675 as this
      feature's worked example (FR-017, SC-006) — no further code change
      to `T055` itself is required.
