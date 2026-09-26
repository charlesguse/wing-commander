# Contract: Gate 99 — board-loop's composites resolve from the trusted copy, never the workspace

Registered as two steps in `.github/workflows/lint-workflows.yml`,
immediately after Gate 98's block, in the same shape every existing gate
uses:

```yaml
# Gate 99 — #468/#504/#615: board-loop.yml's review, readiness and fix
# (resume path, and every post-agent step) jobs check out board-item
# content and then resolve the loop's own shared composites by a
# relative `uses:` path, which resolves from that same untrusted
# workspace. Gate 98 closed the run:-block half of this exposure
# (helper scripts and schemas, #583); this gate closes the uses:-block
# half, unconditionally across every job in the file -- see
# board-loop.yml's own header for the trusted-copy statement both gates
# enforce a piece of.
- name: "Gate 99 — every uses: ./.github/actions/ reference in board-loop.yml resolves from the trusted copy, never the workspace"
  if: "!cancelled()"
  run: python3 .github/scripts/verify-board-loop-composite-provenance.py
- name: "Gate 99 self-test — a raw workspace uses:, a moved, dropped, mis-pinned, or continue-on-error checkout, a missing .gitignore entry, or a widened ban each fail"
  if: "!cancelled()"
  run: python3 .github/scripts/verify-board-loop-composite-provenance.py --self-test
```

Gate 98's own comment block gains one appended sentence pointing here
(contracts/documentation-updates.md); Gate 98's scope and self-test are
otherwise untouched.

## Subject

`.github/workflows/board-loop.yml` (parsed as YAML) and this repository's
own `.gitignore`. No fixtures beyond the mutations below — Gate 99 checks
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

Rule (a) is file-wide and unconditional — it is not scoped to `fix`,
`review`, and `readiness` the way Gate 98's `run:`-block check is
(research.md D5). A job with zero composite references (today: only
`resolve-model`) trivially satisfies rules (a)-(d); rule (e) is a
file-level fact independent of any one job.

## The one thing this gate does not check

`run:`-block behavior — interpreter spelling, import hygiene, the
`$RUNNER_TEMP/wc-pristine` snapshot's own correctness — stays Gate 98's
job entirely (research.md D6). Gate 99 has no gate-suite exemption to
state (research.md D8): it never inspects `run:` blocks, so the one
case FR-010 asks every such gate to carve out narrowly (the gate suite
legitimately running the item's own tree) never arises here.

## Self-test (FR-009, data-model.md "Gate 99 Fixture Set")

`--self-test` asserts the shipped `board-loop.yml` is clean under rules
(a)-(e) first, then applies each of the seven mutations in research.md D7
in turn (a fresh copy of the parsed document or raw text per mutation, the
existing Gate 97/98 convention) and asserts each is caught and
attributable to the rule it targets — never credited to a different rule
that happens to also fire. `main()` exits non-zero if any mutation goes
uncaught or if the unmutated file is not itself clean.

## Reachability (FR-065-equivalent — Principle VIII)

`python3 .github/scripts/run-local-gates.py` picks up both Gate 99 steps
automatically, the same way it already does for every other gate
(`wc_gate_registry.py` parses `lint-workflows.yml`'s own `run:` lines) —
no manifest edit beyond the two steps above.
