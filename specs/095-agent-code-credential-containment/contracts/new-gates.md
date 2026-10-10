# Contract: new gates

Each gate runs identically locally and in CI, ships `--self-test`, is
registered in `lint-workflows.yml` with a path trigger on the files it checks
(FR-019/FR-021), and has one checked-in fixture per failure branch (FR-020).

| Gate script | Requirements | Failure branches that need fixtures |
|-------------|--------------|--------------------------------------|
| `verify-gate-suite-credential-free.py` | FR-001, FR-005, FR-006 | job with App-token step; `permissions` above read; gate step still in credential-bearing job at any FR-005 site; cannot parse job graph |
| `verify-gate-verdict-fail-closed.py` | FR-002, FR-003, FR-004 | artifact missing; unparsable; unknown key; `outcome` not pass/fail; `head_sha` mismatch; `trusted_sha` mismatch; publisher `if:` that treats skipped as green |
| `verify-snapshot-integrity-statement.py` | FR-007–FR-010 | snapshot comment missing covered-steps or runner-assumption text; agent-code step remains in a job that later pushes |
| `verify-composite-run-provenance.py` | FR-011, FR-013, FR-014 | composite `run:` with workspace-relative script; composite set undeterminable (fails loud); composite moved out of view |
| `verify-hardened-push.py` | FR-015–FR-017, FR-022 | raw `git push origin` at a covered site; hardened idiom pasted instead of composite; planted `pre-push` hook ran; planted `insteadOf` redirected |
| `verify-agent-git-deny.py` | FR-018 (deny half) | `.git/**` missing at a covered label; second literal list instead of the spec-090 set |

Existing gates adjusted in the same commit as the workflow: 98
(`run-local-gates.py` carve-out), 104 (reads composites reachable from the new
jobs), `verify-implement-gate-suite-preflight.py`, `verify-stage-tool-lists.py`
(documented disallowed lists).

Cross-spec boundary: no gate here asserts spec 111's property (which credential
an agent step's environment holds).
