# Contract: Gate 59 resolves through composites (FR-001–FR-010, FR-027)

Status: normative for this feature's implementation. Amends, does not
replace, `specs/048-correlated-release-dispatch/contracts/regression-gate.md`
("the five checks" table and its self-test fixture shape section) —
that document keeps checks 1 and 2 (`release.yml`, unaffected, FR-009)
and this document narrows checks 3, 4 and 5 for `auto-release.yml`. Both
documents describe the same script,
`.github/scripts/verify-correlated-release-dispatch.py` — no gate
renumbering, per research.md's convention of amending a contract in
place rather than forking it (CLAUDE.md, "Repeated comment prose gets
ONE canonical comment").

## Subject

Unchanged file, unchanged gate number (Gate 59). What changes is what
the gate reads: no longer `auto-release.yml`'s raw text alone for checks
3–5, but that text plus the shell of any local composite action the
`dispatch-release` job's own steps call, one level deep (research.md D1,
D3).

## The resolution algorithm

1. Load `auto-release.yml`, find the `dispatch-release` job's step list
   (in file order).
2. Build the checks-3/5 corpus by walking that step list: a `run:` step
   contributes its own text; a `uses:` step matching a local-composite
   reference (`./.github/actions/<name>`) is resolved and its
   `runs.steps[*].run` text is spliced in at that position, in the
   composite's own step order; any other `uses:` contributes nothing.
3. Build the check-4 corpus as the job's own `run:` step text only —
   never spliced with composite text (FR-027).
4. Run checks 3 and 5 against the checks-3/5 corpus, check 4 against the
   check-4 corpus, exactly as today's per-check logic already does
   (substring search + windowed co-occurrence) — no change to what each
   check looks for, only to what text it looks in.
5. Attribute each pass to the tagged source (job file or resolved
   composite path) that satisfied it (FR-005).

### Resolving a `uses:` reference

- Path does not exist on disk → hard fail: `::error::` naming the exact
  path, e.g. `auto-release.yml's dispatch-release job calls
  ./.github/actions/<name>, which does not exist -- unresolvable
  composite reference.` Never a pass, never "the invariant was deleted"
  (FR-004).
- Path exists, resolved shell lacks the checked construct, and contains
  no further local `uses:` → the check's existing clause-specific
  failure message (unchanged wording from today), naming only that
  clause (SC-003).
- Path exists, resolved shell lacks the checked construct, but *does*
  contain a further local `uses:` (two levels deep) → hard fail naming
  that second-level reference as unresolved. The gate never opens a
  third file (research.md's Assumptions: "one level deep... failing
  loudly beyond it").

## Failure-clause isolation (unchanged bar, SC-003)

Every failure message continues to name exactly one FR-018 clause
(spec 048) regardless of which corpus construction found or failed to
find it — the resolution step changes *where* the gate looks, never
*what* each check's own pass/fail wording says about the clause it
protects.

## Self-test fixture shape

`CLEAN_RELEASE`/`CLEAN_AUTO` (existing, unchanged) plus two new in-memory
fixtures: `CLEAN_COMPOSITE` (a resolved composite's shell carrying checks
3 and 5's constructs) and `CLEAN_AUTO_VIA_COMPOSITE` (a `dispatch-release`
job whose relevant step is a `uses:` reference to that composite instead
of an inline `run:`). `contract_errors` gains a `resolve` parameter — a
callable/mapping from local composite path to composite text — that the
self-test population supplies as an in-memory dict, so no real file is
read or written by `--self-test` (matching every other gate's discipline
of a synthetic, filesystem-free self-test).

Full case list: research.md D5. Each case's assertion mirrors today's
`check(name, cond, detail)` helper shape, unchanged.

## Wiring (Constitution VIII checklist, unchanged from today except where noted)

- **Reachable through the gate registry**: unchanged — same script path,
  same `lint-workflows.yml` PR-time step, `run-local-gates.py` derives it
  automatically.
- **Same subject, same arguments, locally and in CI**: unchanged — the
  plain invocation now additionally reads whatever `dispatch-release`'s
  own `uses:` steps resolve to, which is repository state, not an
  argument; local and CI both read the same checked-out tree.
- **Triggered by what it checks**: `lint-workflows.yml`'s PR-time gate
  job already triggers on `.github/workflows/**` and `.github/actions/**`
  (confirmed: `lint-workflows.yml:19-23`) — no new trigger path is needed
  even though the gate's effective subject now spans both trees (FR-008
  is met by the existing glob, not a new one).
- **Fails loudly when it can't reach its subject**: strengthened — the
  two new unresolvable-reference cases (D3) are additional loud-failure
  branches beyond today's "file does not exist" guard in `run_gate()`.
- **Not suppressible by an unrelated gate**: unchanged — same
  `if: "!cancelled()"` sequential step.
- **Every failure branch fixture-covered**: strengthened — D5's matrix
  supersedes today's four-fixture self-test with the ten-case list above.
