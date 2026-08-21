# Quickstart: Validating the Lifecycle Gate's Retry and Error Classification

Prerequisites: a checkout of this repository, Python 3, `bash`, `jq` on
`PATH` (same prerequisites `wc_shell_harness.py` already documents for
every existing shell-harness gate). Unlike specs/022, every scenario below
is mechanically verifiable **locally**, without a live triggered workflow
run — this feature's whole coverage strategy (research.md D6/D7) is
built on `wc_shell_harness.py` driving the shipped composite step against
a stubbed `gh`, exactly what `python3 .github/scripts/verify-lifecycle-
gate-retry.py` does in CI as Gate 25.

## Scenario 1 — A transient blip costs a retry, not a run (US1; FR-001, FR-011, SC-001)

```
python3 .github/scripts/verify-lifecycle-gate-retry.py
```

This single command runs every scenario in
`contracts/lifecycle-gate-retry-coverage.md`'s table, including the
transient-then-succeed case: a stubbed `gh` that fails with `HTTP 502` on
its first two calls and succeeds on the third. Confirm exit code 0 and
that the script's own output reports the retry-then-succeed scenario
passed with the correct `state`/`is-open` values and more than one `gh`
invocation recorded.

**Expected**: SC-001 holds — a transient failure run shorter than the
3-attempt budget recovers fully; Acceptance Scenario 1 (US1) reproduced
with the opposite outcome from the source incident (run 31597186484).

## Scenario 2 — A real failure still fails immediately (US3; FR-002, FR-012, SC-002)

Same command as Scenario 1 covers this — the always-not-found and
always-credential-rejected rows of the coverage table. To inspect it by
hand instead of trusting the script's own assertions, read the script's
generated stub for either scenario and confirm the call-count file it
writes never exceeds `1` before the step exits non-zero.

**Expected**: SC-002 holds — zero added delay compared to today; US3
Acceptance Scenarios 1–2 hold.

## Scenario 3 — The error says what actually happened (US2; FR-004, FR-005, SC-003, SC-007)

```
python3 .github/scripts/verify-lifecycle-gate-retry.py -v
```

(or read the script's captured `::error::` lines from its own assertions
for the always-not-found, always-credential-rejected, and both
budget-exhausted scenarios). Confirm by inspection:

- The not-found failure's message contains "may not exist" wording and
  does **not** name the credential.
- The credential-rejected failure's message names the token and does
  **not** contain "may not exist" wording.
- Both budget-exhausted messages quote the last attempt's diagnostic text
  verbatim (the stub's own `HTTP 503` or unrecognised-fault string) and
  state the attempt count.
- The two budget-exhausted messages differ in exactly one respect: one
  says the failures were a recognised transient class, the other says they
  could not be classified (FR-006).

**Expected**: SC-003 (every failure message contains what was actually
observed) and SC-007 (a maintainer can tell the three failure kinds apart
from the reported line alone) hold. This is the direct fix for the source
incident's misdirection — a maintainer reading only the `::error::` line no
longer goes hunting for a token-scope problem that isn't there.

## Scenario 4 — A first-attempt success is unchanged (SC-005)

```
python3 .github/scripts/verify-lifecycle-gate-retry.py
```

The coverage script's own first scenario (an unstubbed, always-succeeds
`gh`) is the baseline every other scenario is compared against. Confirm
its `state`/`is-open` outputs and call count (`1`) match what the
unmodified specs/022 composite already produced — i.e., diff this run
against a checkout of the composite from before this feature (`git show
main:.github/actions/wing-commander-lifecycle-gate/action.yml` piped
through the same harness) and confirm the outputs are byte-for-byte
identical.

**Expected**: SC-005 holds — no measurable behavior change on the
overwhelmingly common path.

## Scenario 5 — The retry is proven to run, not merely shipped (US4; FR-013, FR-014, SC-006)

```
git stash
# apply one of the four mutations research.md D7 / contracts/
# lifecycle-gate-retry-coverage.md describe by hand to action.yml, e.g.
# collapse the retry loop back to a single attempt
python3 .github/scripts/verify-lifecycle-gate-retry.py; echo "exit: $?"
git checkout -- .github/actions/wing-commander-lifecycle-gate/action.yml
git stash pop
```

**Expected**: a non-zero exit for each of the four mutations
(contracts/lifecycle-gate-retry-coverage.md's "Required mutations" table),
and exit 0 once the mutation is reverted. This is the same check Gate 25
performs automatically in `lint-workflows.yml` on every PR — this scenario
just runs it by hand to build confidence before pushing. Confirm separately
that `Gate 25` appears in `lint-workflows.yml`'s job output when the full
`lint · workflows` job runs (`gh workflow run lint-workflows.yml` or a PR's
own check run), satisfying SC-006's "removing or disabling the new coverage
fails a check."

## Scenario 6 — Worst-case latency stays inside budget (FR-003, SC-004)

Inspect the constants directly rather than timing a live run (research.md
D1, contracts/lifecycle-gate-retry-coverage.md non-goals — timing-based
assertions would be flaky under CI load):

```
grep -nE "timeout 4|sleep 1|MAX_ATTEMPTS" .github/actions/wing-commander-lifecycle-gate/action.yml
```

**Expected**: a 4-second per-attempt timeout, a 3-attempt budget, and a
1-second inter-attempt delay — `4+1+4+1+4 = 14` seconds worst case, inside
FR-003/SC-004's 15-second ceiling.
