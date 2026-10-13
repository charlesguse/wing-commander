# Quickstart: validating the feature

Prerequisites: repo checkout, Python 3 with PyYAML (already used by gates),
`bash`. No new dependency (FR-019).

1. **Whole suite**: `python .github/scripts/run-local-gates.py` — expect
   Gate 12, its self-test, Gate 28 and the single-home check all pass.
2. **Gate alone**: `python3 .github/scripts/verify-gate-12-token-permissions.py`
   — expect a pass line reporting >= 478 checked calls (SC-002).
3. **Self-test**: `python3 .github/scripts/verify-gate-12.py` — runs the
   183-scenario corpus, the failure-branch fixtures, the mutation check and
   the seeded real-bash differential; expect zero un-located-and-unrejected
   invocations (SC-001).
4. **Allowed vs disallowed spot check**: write a scratch workflow (outside
   the repo tree, via the self-test's fixture helpers) with
   `` X=`gh pr merge 1` `` and confirm failure text names file, line and the
   authoring-rule heading; with `echo "run gh pr merge"` confirm a pass.
5. **Single home**: add a throwaway `shlex`-based `gh` finder under
   `.github/scripts/` and confirm `verify-single-home-idioms.py` fails;
   remove it.
6. **Size**: `wc -l .github/scripts/wc_gh_callsites.py` is at most ~250
   lines of shell-reading code (SC-003).

Contract references: `contracts/locator-api.md`,
`contracts/authoring-rule.md`.
