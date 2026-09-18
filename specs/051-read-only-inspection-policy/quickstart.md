# Quickstart: Validating the read-only inspection policy

This is a validation guide, not an implementation checklist — it names the
commands that prove the feature works once tasks.md's edits land, and points
at the contracts that define what "working" means. It assumes the repo root
as the working directory.

## Prerequisites

- Python 3 with `pyyaml` installed (the same interpreter `run-local-gates.py`
  and the `verify-*.py` gates already require).
- `jq` and `actionlint` on `PATH` (or discoverable the way
  `.github/scripts/wc_shell_harness.py`'s `ensure_jq()`/`resolve_bash()`
  already probe for them) — needed only for Gate 21's shipped-script harness
  and for exercising `run-local-gates.py` itself.
- Bash (for Gate 21's `run_step` execution of the composite action's `run:`
  block).

## 1. The policy document exists and is the one home

```bash
grep -n "^## Read-only inspection policy" specs/010-reusable-pipeline/contracts/stage-interfaces.md
```

Expect one match, positioned before `## Per-stage default tool lists`
(see [contracts/inspection-policy.md](./contracts/inspection-policy.md) for
the exact text this section must contain).

## 2. Every read-capable stage carries the inspection set

```bash
python3 .github/scripts/verify-stage-tool-lists.py
```

Expect exit 0. This single command is Gate 27, extended per
[contracts/gate-extensions.md](./contracts/gate-extensions.md) with the
inspection-set-completeness and repository-guidance-reconciliation checks —
a failing primitive or an unpermitted mandated command surfaces here by
name, per User Story 1's Acceptance Scenario 1 and User Story 3's
Acceptance Scenario 3.

```bash
python3 .github/scripts/verify-stage-tool-lists.py --self-test
```

Expect exit 0 and an `[ok] mutation caught` line for each of the two new
mutations (dropping a primitive from a read-capable row; removing the
gate-suite grant from `implement.cycle`) — this is Constitution VIII's "a
green check means what it says" proven locally, the same way the file's
existing mutations already are.

## 3. The rendered tooling statement carries the compound-command rule

```bash
python3 .github/scripts/verify-tooling-statement.py
```

Expect exit 0, including the new case asserting the appended sentence
(research.md D3) is present in every rendered `shell-commands` value, and
the new mutation (deleting the sentence from the shipped action) turning
every case red during the mutation phase, then a clean re-run afterward
(the script restores the original script and re-verifies, per its existing
`main()` structure).

## 4. Replay the recorded denied commands (User Story 1's Independent Test)

For each shape in [contracts/inspection-policy.md](./contracts/inspection-policy.md)'s
occurrence table, confirm the *documented* row now covers it:

```bash
# plan's composed allowed list (after tasks.md's edits) should contain the
# full inspection set — spot-check with the same table the gate reads:
grep -A2 '| plan | `plan.direct-commit`' specs/010-reusable-pipeline/contracts/stage-interfaces.md
```

For the two shapes no allowlist addition can close (the `cd … && for …`
loop, the `git stash; …; git stash pop` compound), confirm the corresponding
stage prompt's rendered tooling statement — not just the allowed list —
states the rule: run Gate 21's case output (step 3 above) and read the
printed `expect(...)` string for that stage's baseline case.

## 5. `gh api` is absent everywhere, and its two routes exist

```bash
grep -n 'default-allowed-tools:.*gh api' .github/workflows/*.yml
```

Expect no matches. (`watchdog.diagnose`'s wider `Bash(gh:*)` is a different
literal and is the one documented, untouched exception per FR-008 — it will
not match `gh api` either, since the grep is for that literal substring.)

Then confirm the routes by hand: `clarify.yml`'s prompt names
`/tmp/wing-commander/clarification-answer.md`; `plan.yml`'s prompt names its
`gh pr view --json` grant (User Story 2's Independent Test).

## 6. The implement gate-suite self-check behaves under both prerequisite states

Prerequisite present (the common case in the real `implement` container):

```bash
timeout 600 python3 .github/scripts/run-local-gates.py
```

Expect a clean run finishing well inside the 10-minute step timeout
research.md D5 sets (measured at ~3.5 minutes parallel).

Prerequisite absent (simulate a drifted container — SC-008's second
demonstration):

```bash
python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('yaml') else 1)" \
  && echo "pyyaml present — preflight should proceed" \
  || echo "pyyaml ABSENT — preflight should degrade, not fail"
```

Confirm (by reading `implement.yml`'s new preflight step, once tasks.md
lands it) that an absent prerequisite produces a `$GITHUB_STEP_SUMMARY` note
naming the missing tool and skips the gate-suite step via its own `if:`,
never a denied-tool occurrence and never a failed job (FR-009a, SC-008).

## 7. `CLAUDE.md` addresses only implement and humans

```bash
sed -n '/## Before pushing/,/^## /p' CLAUDE.md | head -20
```

Expect the first line(s) under the heading to name the audience explicitly
(implement stage agent + human/local sessions), before the existing
gate-suite command (FR-009b, User Story 3's Acceptance Scenario 1).

## 8. Full local gate sweep

```bash
python .github/scripts/run-local-gates.py
```

This is the same command CLAUDE.md's "Before pushing" section (as scoped by
this feature) tells a human or the implement agent to run — a clean run here
is the final proof that this feature's own change passes the suite it
edits, including Gate 27 and Gate 21's extended self-tests (SC-003).
