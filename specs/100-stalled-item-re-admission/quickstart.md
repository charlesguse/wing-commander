# Quickstart: Validating A Stall Holds Until a Maintainer Re-Admits It

This feature has no UI and no runtime service — it changes
`.github/workflows/board-loop.yml`'s resume step resolution and adds a gate
script. Validation is: run the local gate suite, then exercise the fixture
cases the new gate carries, then (per CLAUDE.md) prove the Actions-only
behavior by re-driving one real run after merge.

## Prerequisites

- A checkout of this repository with `.github/scripts/` on `PYTHONPATH` (the
  gate scripts already assume this — see any existing `verify-*.py` for the
  `sys.path.insert(0, ".github/scripts")` idiom).
- Python 3.11+ (matches the interpreter `board-loop.yml`'s `run:` steps
  invoke via `python3 -I`).
- `gh` CLI authenticated against this repository, for the post-merge
  re-drive step only.

## Local validation

1. Run the full local gate suite (mandatory before any PR from CLAUDE.md):

   ```console
   python .github/scripts/run-local-gates.py
   ```

   Expect: every existing gate still green (no invariant from research.md
   D1 regressed), plus the new gate (research.md D8) green on `main`'s
   post-implementation state.

2. Exercise the new gate's fixture matrix directly (once implemented,
   likely `.github/scripts/tests/board-loop-readmission/` alongside the
   existing `board-eligibility`/`board-readiness` fixture directories):

   - Open `board:owned` PR, reviewed head established, head commit newer
     than the last review comment → resolves `review`.
   - Open `board:owned` PR, reviewed head established, head commit at or
     before the last review comment → resolves `readiness`.
   - Open `board:owned` PR, no reviewed head resolvable (no prior review
     comment matches, or the arm was parse-failed/malformed-findings) →
     resolves `review` (FR-006b default).
   - `breach` marker, PR recovered only via the fallback → resolves
     `breach` regardless of head movement (#530 carve-out preserved).
   - No open PR recovered → falls through to `triage`.
   - Reverting clause 2 to the pre-feature unconditional `"review"` → the
     gate fails and names the clause (mirrors FR-005's existing style).

3. Confirm SC-004 by inspecting (or fixture-testing) that a labeled
   `board:stalled` issue is excluded from both `in_flight_candidate()` and
   `select()`'s oldest-first fallback — this is existing, unmodified
   behavior (`board_eligibility.py`'s `is_excluded()`/`TERMINAL_STEPS`); the
   new gate does not need to re-test it, but a reviewer sanity-checking
   SC-004 can point at `.github/scripts/tests/board-eligibility/` for
   existing coverage.

## End-to-end scenario walkthrough (matches spec.md's US3 acceptance scenarios)

Using a disposable test issue in a sandbox/fork (never against a real
maintainer-facing issue):

1. Drive an item to a `review` budget-spent stall (five rounds, in-scope
   findings left open at round 5). Confirm: `board:stalled` present,
   `stalled` marker posted, issue excluded from the next `select()` run
   (US1 AS5).
2. Without pushing a new commit, remove `board:stalled`. Run `select`
   again. Confirm: resolved step is `readiness`, not `review` — no reviewer
   invocation spent (US3 AS2 / SC-005).
3. Push a new commit to the same PR, then remove `board:stalled` again (a
   fresh stall/removal cycle, or directly if the label was left off — either
   way the marker is still `stalled`). Run `select`. Confirm: resolved step
   is `review`, with `round == 0` (US3 AS1 / SC-006).
4. Let the fresh round budget exhaust again with findings still open.
   Confirm: it stalls again on the same terms (SC-006's second half).
5. Read the run summary for steps 2-4's runs. Confirm each names the
   re-admission, the clause that fired, and (for step 2/3) whether the head
   had moved (SC-009).

## Post-merge Actions proof (CLAUDE.md)

Because this behavior only executes inside `board-loop.yml`'s Actions runs,
after the implementation PR merges: re-drive one `board-loop.yml` run via
its dispatchable wrapper (`gh workflow run <wrapper> ...`) against a real
stalled item (or a directed single-issue run, if the wrapper supports one),
and record the run URL plus the resolved step and summary line on the PR or
lifecycle issue #752, per CLAUDE.md's "A fix to behaviour that only runs in
Actions is proven after merge."

## Readiness stand-down spot-check (FR-012-015, unmodified — regression only)

Not new work, but worth a quick re-confirmation given how close this
feature's changes sit to readiness's durable steps: with the kill switch
set, run readiness against a stub where the backstop breaches. Confirm zero
durable writes (SC-007) — this should already pass unmodified; a failure
here would indicate this feature's clause-2 change accidentally touched
readiness's stand-down gating, which it should not (they are different code
paths — clause 2 lives in the `select` job's resume step, stand-down gating
lives in the `readiness` job).
