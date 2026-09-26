# Quickstart: Validating rebase.yml / cleanup.yml Credential Refresh + Derived Gate 68 Subjects

This is a validation guide, not an implementation guide — it names the
runnable checks that prove this feature works, keyed to spec.md's
Independent Tests and Acceptance Scenarios. It assumes the implementation
described in `plan.md`/`research.md`/`data-model.md`/`contracts/
gate-68-derived-subjects.md` has landed.

## Prerequisites

- A checkout of this repository on the branch carrying this feature's
  implementation.
- Python 3.11+ with `PyYAML` installed (already a repository dependency —
  no new install step).
- No network access or GitHub credentials are required for any check
  below; every one is a static check over the checked-in YAML/Python.

## 1. The full local gate suite passes

```bash
python .github/scripts/run-local-gates.py
```

**Expected**: every gate passes, including Gate 68 and its self-test step.
This is CLAUDE.md's own pre-push bar and subsumes every check below —
run this first; the finer-grained commands are for isolating a failure.

## 2. Gate 68 alone, and its self-test

```bash
python3 .github/scripts/verify-post-agent-credential-refresh.py
python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test
```

**Expected (plain run)**: passes, and the output names every derived
`(workflow, job)` pair it inspected — confirm `rebase.yml`/`rebase`
appears as a full subject and `cleanup.yml`/`teardown-done`,
`watchdog.yml`/`diagnose`, and `board-loop.yml`'s four jobs appear as
exempt entries with their `condition` satisfied (SC-002, contracts/
gate-68-derived-subjects.md §1/§3).

**Expected (`--self-test`)**: every documented mutation is reported as
failing the gate, including the new ones this feature adds — a floor
member's agent step removed, a derived set emptied, `cleanup.yml`'s or
`watchdog.yml`'s `timeout-minutes` deleted or raised past 10, and
`board-loop.yml`'s adopted composite call deleted (SC-005; research.md
D12; contracts/gate-68-derived-subjects.md "Self-test coverage").

## 3. User Story 1 — a long rebase still publishes its result

**Independent Test** (spec.md): confirm the publish and escalate arms act
on a post-agent credential, and a failed re-establishment surfaces as a
named credential failure.

Static proof (no live GitHub Actions run required):

```bash
grep -n "steps.ctx.outputs.token" .github/workflows/rebase.yml
```

**Expected**: no match inside the `rebase` job at or after the `Resolve
conflicts` step (line ~693) other than the agent step's own `with:` block,
which legitimately reads the pre-agent mint for its own invocation
(Acceptance Scenario 1/2). Every step after it — `Report over-budget agent
run`, `Publish rebased branch`, `Abandon and escalate`, `Announce the
rebase escalation` — reads `env.WC_BOT_TOKEN` instead.

```bash
python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test 2>&1 | grep -i rebase
```

**Expected**: the `rebase.yml` mutations (credential reference reverted,
`wing-commander-context` call deleted, `wing-commander-refresh-remote`
call deleted) each report as caught (Acceptance Scenario 3).

A clean rebase (Acceptance Scenario 4) is proven by re-driving a real run
per the User Story's own note and this repository's "prove" step (§5
below) — a clean rebase's outcome, artifacts, and comments are unchanged
from before this feature, which is not something a static check alone can
demonstrate.

## 4. User Story 2 — teardown finishes even behind a slow summary agent

**Independent Test**: confirm the bound is present and asserted, then
confirm removing or raising it fails the gate naming the job.

```bash
grep -n -A2 "name: Completion summary" .github/workflows/cleanup.yml
```

**Expected**: `timeout-minutes: 10` present on the step (Acceptance
Scenario 1).

```bash
python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test 2>&1 | grep -i "teardown-done\|cleanup"
```

**Expected**: the "bound removed" and "bound raised" mutations both report
as caught, naming `cleanup.yml`'s `teardown-done` job (Acceptance
Scenario 2).

A normal one-minute teardown (Acceptance Scenario 3) and a
bound-triggered kill (Acceptance Scenario 4) are runtime behaviours; see
§5.

## 5. User Story 3 — no agent-bearing workflow is invisible to the gate

**Independent Test**: add an agent step to a workflow that is neither
covered nor exempt and confirm the gate fails naming it; remove all
subjects and confirm the gate fails loudly rather than passing over an
empty set.

```bash
python3 - <<'PY'
import copy, sys
sys.path.insert(0, ".github/scripts")
import verify_post_agent_credential_refresh as g

trees = g.load_all()
# add a synthetic agent-bearing job with no disposition
target = copy.deepcopy(trees)
sample_path = next(iter(target))
target[sample_path].setdefault("jobs", {})["rogue-job"] = {
    "runs-on": "ubuntu-latest",
    "steps": [{"name": "Agent", "uses": "anthropics/claude-code-action@v1"}],
}
ok, msgs = g.check_all(target)   # illustrative call shape; see the gate's own self-test harness for the exact entry point
print("expected failure:", not ok, msgs)
PY
```

(This is illustrative of the property being proven, not a literal
prerequisite command — the gate's own `--self-test` mode already exercises
this exact scenario as one of its checked-in mutations; §2 above is the
authoritative way to run it.)

**Expected**: the gate reports the synthetic job as neither a full
subject, agentless-in-scope, nor exempt, and fails naming it (Acceptance
Scenario 1). Confirm via `--self-test` (§2) rather than the ad hoc snippet
above for CI-equivalent evidence.

## 6. Contract documentation matches the checked set (FR-016)

```bash
grep -n "rebase.yml\|cleanup.yml\|watchdog.yml\|board-loop.yml" \
  specs/052-agent-credential-lifetime/contracts/post-agent-credential-refresh-gate.md \
  specs/052-agent-credential-lifetime/contracts/wing-commander-context-relay.md
```

**Expected**: both documents name all four workflows and their
dispositions (full subject vs. exempt), matching the Disposition Summary
Table in `data-model.md`.

## 7. Proving a behaviour that only runs in Actions (post-merge)

Per CLAUDE.md's "Working the issue board" rule for this class of fix: after
this feature's implementation PR merges, re-drive one real run of
`rebase.yml` (on a branch with a genuine conflict, so the agent step
actually executes) via `gh workflow run rebase.yml ...` on the wrapper that
can dispatch it, and record the run's evidence — specifically that the
publish or escalate arm completed using a post-agent credential — on the
PR or lifecycle issue (#558). The same applies to `cleanup.yml`'s
`teardown-done` job for a normal teardown, to confirm SC-007's
byte-identical-outcome claim against a live run, not only the static
checks above.
