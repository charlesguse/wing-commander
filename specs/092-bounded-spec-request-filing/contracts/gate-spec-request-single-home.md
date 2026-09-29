# Contract: the single-home gate for spec-request filing (FR-019)

Owning gate: **Gate 93** (`.github/scripts/verify-issue-context-single-home.py`),
new **check 6**, `check_spec_request_filing_bound()` — added beside
existing checks 1-5 in the same file (research.md D8), not a new gate
file. Registered in `.github/scripts/wc_gate_registry.py`'s existing Gate
93 entry so `run-local-gates.py` and `lint-workflows.yml` both pick it up
with no new invocation to wire.

## What it checks, per spec-request filing site in `.github/workflows/board-loop.yml`

For each of the three sites (route's spec verdict, the fix job's
post-push breach, and both of readiness's backstop-breach entries):

1. **Lookup precedes create.** A step invoking
   `board_spec_request_filing.py lookup` exists earlier in the same job,
   and the create step's `if:` (or its internal branch) is conditioned on
   that step's `existing-spec-url` output being empty — a site that calls
   `gh issue create --label spec-request` with no preceding lookup step
   fails this check.
2. **No hand-rolled counting.** The site's failed-attempt branch calls
   `board_spec_request_filing.py record-attempt`; a literal `+ 1`,
   `$((...))`, or any other increment of an attempts-shaped variable
   outside that call fails this check.
3. **One budget constant.** `.github/workflows/board-loop.yml`'s
   `env:` block defines exactly one `BOARD_LOOP_SPEC_REQUEST_ATTEMPT_
   BUDGET`; every site's `record-attempt --budget` argument reads
   `env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET` — a literal number or a
   second `BOARD_LOOP_*` name used the same way fails this check.
4. **A fourth site is caught.** The check enumerates spec-request-create
   sites the same way check 3 already does (any `gh issue create ...
   --label spec-request`), so a new filing site added later that skips
   (1) or (2) fails this check without needing its own update — the same
   "a fourth site inherits or fails the gate suite" guarantee spec.md's
   Edge Cases section states.

## What it deliberately does not check

- The *content* of the lookup's match predicate (bot authorship + footer
  line, research.md D2) — that is fixture-tested directly against
  `board_spec_request_filing.find_existing()` in
  `.github/scripts/tests/board-spec-request-filing/`, the same split Gate
  93 already uses between "workflow wiring" (check 3, this check) and
  "helper module correctness" (`verify-board-eligibility.py`'s own
  fixture tests for `board_eligibility.py`).
- Gate 93 check 3's existing rules (body builder, context-file provenance,
  the #514 URL-shape guard) are unchanged; check 6 is additive.

## Fixtures

Following `verify-board-eligibility.py`'s pattern
(`.github/scripts/tests/<case>/`), this check's own regression coverage is
a small set of synthetic `board-loop.yml` fragments (not the real
workflow) exercising: a compliant site, a site with no lookup step, a site
with a hand-rolled increment, and a site reading a second `BOARD_LOOP_*`
budget name — each checked to fail for the right stated reason (Constitution
VIII: every failure branch a gate ships is exercised by a checked-in
fixture).
