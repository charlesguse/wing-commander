# Contract: Gate 104 — board-loop's composites resolve from the trusted copy, never the workspace

Registered as two steps in `.github/workflows/lint-workflows.yml`,
immediately after Gate 98's block, in the same shape every existing gate
uses:

```yaml
# Gate 104 — #468/#504/#615: board-loop.yml's review, readiness and fix
# (resume path, and every post-agent step) jobs check out board-item
# content and then resolve the loop's own shared composites by a
# relative `uses:` path, which resolves from that same untrusted
# workspace. Gate 98 closed the run:-block half of this exposure
# (helper scripts and schemas, #583); this gate closes the uses:-block
# half, unconditionally across every job in the file -- see
# board-loop.yml's own header for the trusted-copy statement both gates
# enforce a piece of. #640 maintainer review: this gate also requires
# a write-protect step (chmod -R a-w) immediately after each job's
# trusted-copy checkout, since the fixer and review-fixup agents hold
# unrestricted Write/Edit on the workspace and could otherwise rewrite
# the sidecar before it runs with the App private key. Numbered 104,
# not the 99 this branch's own commit first picked (#450/#463's Gate 99,
# converged-means-tasks-done, immediately above, claimed 99 first on the
# default branch before this branch's rebase landed) nor the 100 this
# gate held next (main's own Gate 100, spec 079, claimed 100 first on
# the default branch before this branch's second rebase landed).
- name: "Gate 104 — every uses: ./.github/actions/ reference in board-loop.yml resolves from the trusted copy, never the workspace"
  if: "!cancelled()"
  run: python3 .github/scripts/verify-board-loop-composite-provenance.py
- name: "Gate 104 self-test — a raw workspace uses:, a moved, dropped, mis-pinned, or continue-on-error checkout, a missing .gitignore entry, a widened ban, or a dropped write-protect step each fail"
  if: "!cancelled()"
  run: python3 .github/scripts/verify-board-loop-composite-provenance.py --self-test
```

Gate 98's own comment block gains one appended sentence pointing here
(contracts/documentation-updates.md); Gate 98's own allowlist and
mutation set are otherwise untouched, but its `structural_problems()`
one-checkout-per-job count now excludes the canonical trusted-copy
checkout step by name (T027/T028; research.md D6).

## Subject

`.github/workflows/board-loop.yml` (parsed as YAML) and this repository's
own `.gitignore`. No fixtures beyond the mutations below — Gate 104 checks
the real, shipped file directly, the same way Gate 97/98 do, rather than
a synthetic sample workflow (Principle VIII: "runs the same subject with
the same arguments locally as it does in CI").

## Rules (data-model.md "Board-Loop Job")

| Rule | Statement | FR |
|---|---|---|
| (a) | No line anywhere in the file matches `uses: ./.github/actions/` (the raw, workspace-relative form) | FR-001 |
| (b) | Every job containing a `uses: ./.wc-pristine-repo/.github/actions/...` reference contains the canonical `Checkout board-loop's own trusted copy (composites)` step, at a step index lower than every such reference, every `wing-commander-context` call, and every `anthropics/claude-code-action@` step in that same job | FR-002, FR-011 |
| (c) | That step's `with.ref` is exactly `${{ github.sha }}` | FR-003 |
| (d) | That step carries no `continue-on-error: true` | FR-006 |
| (e) | `.gitignore` contains an entry matching `.wc-pristine-repo` (or a parent-directory ignore covering it) | FR-007 |
| (f) | Every job that carries the trusted-copy checkout also carries the canonical `Write-protect board-loop's own trusted copy (composites)` step, after the checkout and before every dependent reference in that job | FR-002, FR-006, FR-007 (#640 maintainer review) |

Rule (a) is file-wide and unconditional — it is not scoped to `fix`,
`review`, and `readiness` the way Gate 98's `run:`-block check is
(research.md D5). A job with zero composite references (today: only
`resolve-model`) trivially satisfies rules (a)-(d) and (f); rule (e) is
a file-level fact independent of any one job.

## The one thing this gate does not check

`run:`-block behavior — interpreter spelling, import hygiene, the
`$RUNNER_TEMP/wc-pristine` snapshot's own correctness — stays Gate 98's
job entirely (research.md D6). Gate 104 has no gate-suite exemption to
state (research.md D8): it never inspects `run:` blocks, so the one
case FR-010 asks every such gate to carve out narrowly (the gate suite
legitimately running the item's own tree) never arises here.

## Self-test (FR-009, data-model.md "Gate 104 Fixture Set")

`--self-test` asserts the shipped `board-loop.yml` is clean under rules
(a)-(f) first, then applies each of the eight mutations in research.md D7
in turn (a fresh copy of the parsed document or raw text per mutation, the
existing Gate 97/98 convention) and asserts each is caught and
attributable to the rule it targets — never credited to a different rule
that happens to also fire. `main()` exits non-zero if any mutation goes
uncaught or if the unmutated file is not itself clean.

## Reachability (FR-065-equivalent — Principle VIII)

`python3 .github/scripts/run-local-gates.py` picks up both Gate 104 steps
automatically, the same way it already does for every other gate
(`wc_gate_registry.py` parses `lint-workflows.yml`'s own `run:` lines) —
no manifest edit beyond the two steps above.
