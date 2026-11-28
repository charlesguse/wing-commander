# Quickstart: validating spec 128

Prerequisites: a checkout of the implemented branch; Python 3.

1. Unit corpus: `python .github/scripts/verify-finding-triage-report.py`
   — expect exit 0. It routes the fixture corpus (in-scope, out-of-scope
   silent / loud / none, important-and-none, security-nit-and-loud, silent
   without description, absent class, unrecognised class) and checks the
   rendered list. Each negative fixture under
   `.github/scripts/fixtures/finding-triage/` must make it exit non-zero when
   fed to `--fixture`.
2. Parity (SC-005): the same script drives the gate's partition logic and the
   stage-findings prepare logic on the shared corpus and asserts equal
   outcomes for the out-of-scope findings.
3. Stage-findings harness: `python .github/scripts/stage-findings-tests/run_fixtures.py`
   — a loud proposal files nothing and appears under "triaged out" in the
   summary; a silent one is filed with a "How it fails silently" section.
4. Whole suite: `python .github/scripts/run-local-gates.py` — all green.
5. After merge (owner session, not the implement stage): sweep #889 per
   FR-012 and prove one gate round through `prove-after-merge`.

See [contracts/finding-triage.md](contracts/finding-triage.md) and
[data-model.md](data-model.md).
