# Quickstart: validating 132-workflow-trigger-security

Prerequisite: zizmor at the version in `.github/scripts/zizmor-pin.txt` on PATH.

1. Full gate suite: `python .github/scripts/run-local-gates.py`. Expect green, including the new gates.
2. Injection gate: on a scratch branch add `run: echo "${{ github.event.issue.title }}"` to any workflow. Run `python3 .github/scripts/verify-zizmor.py`. Expect failure naming file, line and `template-injection`. Move it to `env:` and rerun: pass.
3. Register: delete one `dangerous-triggers` record; the gate names the finding. Add a record for a nonexistent finding; the gate names the stale record.
4. Self-repository reason: delete it from `.github/zizmor.yml`; the gate fails.
5. Exposure audit: `python3 .github/scripts/verify-untrusted-checkout-local-uses.py --audit` lists exposed jobs; empty on main once FR-015 fixes land.
6. Self-tests: each new gate with `--self-test`; every failure fixture must fail.
7. Event policy: add `on: discussion:` to a wrapper; `verify-adopter-event-policy.py` fails until the docs block lists it.
8. Pin bump: rewrite one SHA pin with its register rows; the suite passes. Without the rows, Gate 170 fails.
9. Local and CI parity: compare the verdicts for the same commit.

Contracts: [zizmor-gate.md](contracts/zizmor-gate.md), [untrusted-checkout-gate.md](contracts/untrusted-checkout-gate.md).
