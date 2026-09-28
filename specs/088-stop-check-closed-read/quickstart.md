# Quickstart: Validating the Honest Read-Failure Policy

This feature ships no user-facing surface to click through — it corrects a
deterministic composite action's failure policy, five comments, and adds
one gate. Validation is gate-driven (Principle VIII: a manual demonstration
is evidence for one reviewer, not coverage for the next), plus one optional
live replay for the part that only runs in Actions (CLAUDE.md).

## Prerequisites

- A checkout of this repository on `spec/088-stop-check-closed-read` (or
  any branch carrying the shipped implementation).
- Python 3 with the repo's existing gate dependencies (`PyYAML`) — the same
  environment `python .github/scripts/run-local-gates.py` already requires.
- `git`, `bash`, and `jq` on `PATH` (the existing
  `verify-board-stop-check.py` shell-case harness needs all three today).

## Run the full PR-time gate suite

```bash
python .github/scripts/run-local-gates.py
```

This runs every gate `lint-workflows.yml` invokes, including the new gate
this feature registers and the extended `verify-board-stop-check.py`. A
clean run is the primary acceptance signal — CLAUDE.md requires it before
every push.

## Run just the new gate (FR-007/FR-008/FR-009)

```bash
python .github/scripts/verify-errexit-claim-comments.py
python .github/scripts/verify-errexit-claim-comments.py --self-test
```

Expected: the bare run finds zero violations across
`.github/workflows/*.yml` and `.github/actions/**/action.yml` on the
shipped, corrected tree (SC-002). The self-test exits 0 having proven, per
contracts/errexit-claim-gate.md: a correct comment and a quoting-to-correct
comment produce no violation; each bare false-claim phrasing is caught; and
mutating each of the five shipped, corrected comments back to its pre-fix
claim is caught (FR-009's own mutation-coverage requirement, not just a
synthetic fixture).

## Run the extended board-stop-check harness (FR-013, SC-007)

```bash
python .github/scripts/verify-board-stop-check.py
```

Expected: every pre-existing fixture and shell case still passes, plus (per
contracts/board-stop-check-composite.md and research.md D7):

- a structural assertion that `closed-check` carries no
  `continue-on-error` and comes after `check` in step order, and that
  `check`'s `run:` text no longer references `steps.closed-check`;
- shell cases covering every SC-007 branch (OPEN, CLOSED, fails-then-
  succeeds, fails all attempts, and `lifecycle-gate`'s own unrecognized-
  value exit, exercised as the same "closed-check outcome: failure" case
  from this composite's point of view);
- a mutation reintroducing `continue-on-error: true` on `closed-check`
  (the pre-fix shape) is caught by at least one of the above.

## Confirm Gate 24's boundary is recorded (FR-012)

```bash
python -c "
import re
text = open('.github/scripts/verify-gate-24.py', encoding='utf-8').read()
assert 'actions' in text.lower() and 'workflows/*.yml' in text
print('Gate 24 boundary documented:', 'actions' in text.lower())
"
```

Expected: the docstring states the `.github/workflows/*.yml`-only scope
and names the follow-up issue filed during implementation (D8) — read it
directly to confirm the issue number is a real, open issue, not a
placeholder.

## Confirm no change to the out-of-scope files (FR-005, FR-006, FR-011)

```bash
git diff main --name-only
```

Expected: does **not** include `.github/actions/wing-commander-lifecycle-gate/
action.yml`, `.github/workflows/watchdog.yml`, or a change to
`wing-commander-board-stop-check/action.yml:171`'s `gh run cancel ...
failed: $cancel_error` line (SC-005, SC-006-adjacent — SC-006 itself is
spec 087's, not measured here).

## Sanity-check the composite's reordering directly

```bash
python3 -c "
import yaml
action = yaml.safe_load(open('.github/actions/wing-commander-board-stop-check/action.yml'))
steps = action['runs']['steps']
ids = [s.get('id') for s in steps]
print('step order:', ids)
closed = next(s for s in steps if s.get('id') == 'closed-check')
print('continue-on-error on closed-check:', closed.get('continue-on-error'))
"
```

Expected: `check` (or its renamed equivalent) appears before
`closed-check` in `ids`, and `continue-on-error` on `closed-check` is
`None`/absent.

## Replay a total read failure end-to-end (optional, post-merge per CLAUDE.md)

The gate suite is the checked-in proof (Principle VIII); this step is not
required for every change to this feature, but per CLAUDE.md a fix to
behaviour that only runs in Actions is proven after merge by re-driving one
run and recording the evidence. A maintainer can temporarily point
`closed-check`'s `issue-number` input at a nonexistent issue number on a
scratch branch, dispatch a workflow that reaches `wing-commander-board-
stop-check` with `check-issue-closed: "true"`, and confirm: the run fails,
the failure names the issue number, the kill-switch/stop-request step's
log shows it ran (including, if applicable, the `gh run cancel` cancel
attempt), and no durable action beyond it ran in that job.

## Expected outcomes checklist

- [ ] `python .github/scripts/run-local-gates.py` exits 0.
- [ ] `verify-errexit-claim-comments.py` finds zero violations on the
      shipped tree and its self-test (including the five-site mutation
      battery) passes.
- [ ] `verify-board-stop-check.py` passes with the new structural checks,
      extended shell cases, and the reintroduced-`continue-on-error`
      mutation caught.
- [ ] `verify-gate-24.py`'s docstring states its scope and names a real,
      open follow-up issue.
- [ ] `git diff main --name-only` excludes `lifecycle-gate/action.yml`,
      `watchdog.yml`, and `action.yml:171`'s cancel-error line.
- [ ] The composite's step order has `check` before `closed-check`, and
      `closed-check` carries no `continue-on-error`.
- [ ] All five corrected comments state the true read-failure/errexit
      behavior, describe pre-#465 behavior (where mentioned) as failing
      the job, and point at `verify-errexit-claim-comments.py` rather than
      restating the mechanism.
