# Quickstart: Validating "A Not-Ready PR Releases the Board"

Every scenario below is checked-in-fixture testable (spec.md's own
Independent Test statements) — none requires a live scheduled run or a
real PR in a red state (User Story 4).

## Prerequisites

- A checkout of this repository at the implementing branch.
- Python 3.11 (no third-party packages — every board-loop script is
  stdlib-only).

## 1. Run the full local gate suite

```console
python .github/scripts/run-local-gates.py
```

Expect every existing gate to stay green, in particular Gate 81
(`verify-board-eligibility.py`) and Gate 97
(`verify-board-loop-resume-gating.py`) — this feature extends both rather
than adding a new one (FR-013).

## 2. Exercise the new eligibility fixtures directly (US1, US3)

```console
python .github/scripts/verify-board-eligibility.py
```

Confirms, among the existing cases: a durable, unmoved-head not-ready
item is excluded from both `in_flight_candidate()` and `select()`'s
fallback while a second eligible issue is selected instead
(`not-ready-durable-unmoved-held`); the same item is admitted once its
head moves (`not-ready-durable-moved-admitted`); a self-clearing item is
never held (`not-ready-self-clearing-not-held`); an unresolvable head
degrades to held, never admitted (`not-ready-head-unresolvable`); two
independently-held items never block each other or a third eligible issue
(`not-ready-two-held-one-eligible`).

## 3. Prove the rule is load-bearing (User Story 4)

```console
git stash push .github/scripts/board_eligibility.py   # remove _not_ready_holds()'s call site
python .github/scripts/verify-board-eligibility.py    # expect: FAIL, naming the case
git stash pop
```

Repeat for `board_eligibility.NOT_READY_THRESHOLD` (raise it to an
arbitrarily large number) and for the not-ready-report step's marker
write in `board-loop.yml` (delete it) against
`verify-board-loop-resume-gating.py`'s self-test — each MUST fail on its
own (SC-006).

## 4. Exercise the resume-gating simulation (US2, US3)

```console
python .github/scripts/verify-board-loop-resume-gating.py --simulate
```

Confirms the new `RESUME_CASES` rows: a durable, unmoved-head `readiness`
marker resolves back to `readiness`; a moved-head one resolves to `review`
carrying the marker's own preserved `round` (not `0`); this feature's own
`stalled` handover marker (with `pr`/`nr_head_sha` recorded) resolves to
`readiness` or `review` depending on whether the fallback-recovered PR's
head matches; every other stall site's `stalled` marker (no `pr`
recorded) is unaffected and still resolves to `review` (regression, FR-015).

## 5. Regression: everything this feature does not touch

```console
python .github/scripts/verify-board-eligibility.py
python .github/scripts/verify-board-loop-resume-gating.py
```

Both must still pass every pre-existing fixture unchanged: `ready` →
`awaiting-merge`, `prove`, `breach`, the unowned-open-PR hold, the
forged-marker author rule (FR-015, SC-008).

## 6. Post-merge proof (Actions-only behaviour)

Per CLAUDE.md, a fix to behaviour that only runs in Actions is proven
after merge by re-driving one run:

```console
gh workflow run board-loop.yml -f directed-stage=readiness -f directed-pr=<a PR held or handed over by this feature>
```

Record the run URL and its outcome (held/re-admitted/handed-over, as
expected) on the lifecycle issue.
