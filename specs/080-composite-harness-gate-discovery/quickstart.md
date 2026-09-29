# Quickstart: Validating Composite Test Harness Gate Discovery

Prerequisites: a checkout with this feature implemented, `python3` and
`bash` on PATH (`python .github/scripts/run-local-gates.py` already
resolves both portably).

## 0. Confirm what was already true (research.md D1) — no code to test here, just facts

```bash
grep -n '".github/actions/\*\*"\|".github/scripts/\*\*"' .github/workflows/lint-workflows.yml
```

Expected: both present in `lint-workflows.yml`'s `pull_request: paths:`
list (FR-008 — confirms the filter needs no edit).

```bash
python .github/scripts/run-local-gates.py dispatch-and-wait-tests size-path-backstop-tests stage-findings-tests
```

Expected: all three composite harnesses run (FR-002), confirming they
were never actually invisible to the *local runner* — only to naive
tree-placement, which is what this feature makes a gate rather than an
accident (D1).

## 1. Gate identity (FR-007)

```bash
python .github/scripts/run-local-gates.py --jobs 1 dispatch-and-wait-tests size-path-backstop-tests stage-findings-tests
```

Expected: the final table lists three distinct identities of the shape
`<name>-tests/run-tests.sh`, never the collapsed `run-tests.sh` three
times over. Repeat with all five `*/run-tests.sh` harnesses (add
`auto-update-spec-kit-tests`/`e2e-provisioning-tests` to the filter, or
drop the filter entirely) — five distinct rows, five distinct timing-cache
keys.

## 2. The new enforcement gate (FR-001/006/012/014)

```bash
python .github/scripts/verify-actions-no-gate-scripts.py --self-test
python .github/scripts/verify-actions-no-gate-scripts.py
```

Expected: the self-test's fixture list (contracts/enforcement-gate-
cli.md) all pass; the live run reports zero unsupported locations against
this repository's real tree (verified today: nothing under `.github/
actions/` currently matches `run-tests.sh` or a standalone `verify-*`).

To see it fail (Principle VIII: prove a gate can fail its own subject,
not only pass it):

```bash
mkdir -p .github/actions/wing-commander-context/tests
echo 'echo hi' > .github/actions/wing-commander-context/tests/run-tests.sh
python .github/scripts/verify-actions-no-gate-scripts.py
# expect: ::error:: naming .github/actions/wing-commander-context/tests/run-tests.sh,
# .github/scripts/, and verify-actions-no-gate-scripts.py
rm -rf .github/actions/wing-commander-context/tests
```

Repeat with a `.github/actions/wing-commander-context/verify-widget.py`
(standalone script — same failure shape) and with a file placed instead
under `.github/actions/_shared/run-tests.sh` (must NOT fail — the
carve-out), then remove both.

## 3. Reverse-direction `.github/actions/` wiring (FR-004/FR-013)

```bash
python .github/scripts/verify-gate-wiring.py --self-test
python .github/scripts/verify-gate-wiring.py
```

Expected: `--self-test`'s new fixtures (research.md D6) pass, including
the self-checkout-prefix fixture (one file, referenced two ways, reported
once); the live run passes clean against the real tree, including the
real `./.wing-commander-pipeline/.github/actions/_shared/...` references
already in `auto-update-spec-kit.yml` today.

To see the reverse check fail:

```bash
grep -n "auto-release-verdict.sh" .github/workflows/auto-release.yml | head -1
```

(confirm it names an existing file), then temporarily point a copied
line at a nonexistent `.github/actions/_shared/does-not-exist.sh` in a
scratch workflow file under `.github/workflows/` and re-run
`verify-gate-wiring.py` — expect a failure naming that path and the
workflow. Remove the scratch file afterward.

## 4. Placement vs. orphan-hood do not conflate (spec.md Edge Case, Story 2 #4)

```bash
mkdir -p .github/actions/wing-commander-context/tests
echo 'echo hi' > .github/actions/wing-commander-context/tests/run-tests.sh
python .github/scripts/verify-actions-no-gate-scripts.py   # fails: placement
python .github/scripts/verify-gate-wiring.py               # unaffected: this path is not under .github/scripts/, so Gate 10's forward check has nothing to say about it
rm -rf .github/actions/wing-commander-context/tests
```

Expected: the placement failure names the file and location; Gate 10
neither reports nor suppresses it — the two gates answer different
questions about the same file, per research.md D6's non-double-report
fixture.

## 5. Canonical prose, not three copies (FR-009/FR-011)

```bash
python .github/scripts/verify-comment-canonical-pointers.py
grep -rn "why this harness\|lives under .github/scripts" \
  .github/scripts/dispatch-and-wait-tests/run-tests.sh \
  .github/scripts/size-path-backstop-tests/run-tests.sh \
  .github/scripts/stage-findings-tests/run-tests.sh
```

Expected: Gate 47 passes; each of the three harness files carries a short
pointer comment naming `verify-actions-no-gate-scripts.py`, not its own
restatement of the rationale. Confirm with `git log --oneline -- <one of
the three files>` that no second full copy of the explanation was
reintroduced.

## 6. Full suite, unchanged pass count plus the new gate (SC-007)

```bash
python .github/scripts/run-local-gates.py
```

Expected: every gate that passed before this feature still passes
(SC-007 — no existing gate changes subject or arguments), plus the new
Gate's two steps, plus Gate 10 now printing its self-test alongside its
live run. Compare the reported gate count before/after implementation to
confirm growth by exactly the gates this feature adds.
