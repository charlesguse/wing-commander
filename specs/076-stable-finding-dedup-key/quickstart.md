# Quickstart: Validating a Stable Finding Dedup Key

Prerequisites: a checkout with this feature implemented, and the local
gate suite runnable (`python .github/scripts/run-local-gates.py`). Every
step below runs with no agent, no live `gh`, and no scratch repository —
this is exactly what SC-007 asks the fixtures to prove in under a minute.

## 1. Unit-level: the anchor check and both key shapes (User Story 2's independent test)

```bash
bash .github/scripts/stage-findings-tests/run-tests.sh
```

Expected: PASS lines including (see `contracts/anchor-verification.md`'s
fixture table for the full set) —
- two findings with differently-punctuated/cased/spaced anchors that both
  verify against one fixture file, plus differing titles and `what` text,
  produce **one** with-anchor key;
- two findings naming genuinely different, both-verifiable anchors in one
  file produce **two** with-anchor keys;
- a finding whose anchor cannot be found in the named file takes the
  fallback key, and a second such finding in the same file shares it;
- a fallback-keyed finding and a with-anchor-keyed finding in the same file
  key apart;
- an anchor that normalizes to empty never produces an empty-string key
  component.

## 2. Gate-level: the new and extended gates

```bash
python .github/scripts/verify-dedup-key-canonical-rule.py
python .github/scripts/verify-stage-findings-wiring.py
python .github/scripts/verify-comment-canonical-pointers.py
python .github/scripts/run-local-gates.py
```

Expected: all pass against the real tree post-implementation. To confirm
User Story 4's "the change is provable without a five-run drill":
temporarily change one shape tag (research.md D2) in
`wing-commander-stage-findings/action.yml` without updating
`specs/056-stage-found-defect-filing/data-model.md`'s fenced formula, and
re-run `verify-dedup-key-canonical-rule.py` — it must fail naming the
missing literal, then revert the change. Separately, temporarily make
`board-loop.yml`'s out-of-scope-finding formula byte-identical to this
feature's and re-run the same gate — it must fail naming FR-015 as the
reason convergence is rejected, then revert.

## 3. End-to-end: the five-run drill this feature retires (User Story 1's independent test)

This is the drill #424 recorded by hand; running it once end-to-end
confirms the fixtures in step 1 are testing the real thing, not a
simplification of it. Requires a real dispatch of a stage workflow (e.g.
`finalize`) against a disposable spec/branch in a repository you're
authorized to file test issues in.

1. Plant one deliberately findable defect in a file the stage will read,
   with a heading or gate name the agent can quote as an anchor.
2. Drive the stage run three times, without editing anything between runs
   that would make the agent phrase its title/`what` identically twice.
3. After all three runs, confirm exactly one issue exists, carrying two
   "seen again" appends, each showing that run's own phrasing of `what`
   (FR-008) — not a column of three near-identical issues.
4. Repeat with a defect that has nothing quotable to anchor on (User
   Story 3's independent test): confirm it still reaches the board under
   the stage-and-file fallback issue, readable in full, and that a second,
   different unanchorable defect in the same file appends to that same
   issue with its own description intact (FR-007, FR-008).
5. Confirm the run's own summary distinguishes filed from appended exactly
   as before (FR-009) and reports no new counter for the anchor-rejection
   case (research.md D4).

## 4. Compatibility (FR-014)

Using an issue filed before this feature (a marker under the pre-076
single-shape formula), re-drive the same stage against the same defect
once more: confirm a new issue is filed (the old marker does not match
either new shape) and that its *next* encounter dedups normally against
the new issue — no migration step is expected or required.
