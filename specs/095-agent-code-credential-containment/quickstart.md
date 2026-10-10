# Quickstart: validating 095

## Call-site notes (T001-T003, recorded at implement cycle 2)

Anchors on the branch as of this cycle (line numbers drift; names are stable):

- `board-loop.yml` `fix` job: step `Run local gate suite (fixer)` (id
  `gate-suite`), then `Comment the failing gate on the issue (fixer, gate suite
  red)`, `Re-check kill switch ...`, `Push and open the PR` (`git push origin
  "HEAD:refs/heads/$BRANCH"`). Job outputs `pr-number` and `breach` come from
  `push-pr` / `final-diff-backstop`, which stay in the publish job.
- `board-loop.yml` review-fixup: step writing
  `board-review-fixup-gate-suite.log`, then a push guarded by
  `if ! git push origin "HEAD:refs/heads/$BRANCH"`.
- `implement.yml`: cycle gate-suite preflight (writes `gate-suite-cycle.log`,
  skips when `run-local-gates.py` is absent), retry preflight
  (`gate-suite-retry.log`), and the spec-branch push `git push origin
  "HEAD:refs/heads/${SPEC_PREFIX}$SLUG"` plus the agent-composed `git push`
  further down.

What the existing gates assert about the in-job gate step (hot spot):

- Gate 98 (`verify-board-loop-helper-provenance.py`): every `python3` in
  fix/review/readiness is `-I` and imports from `$RUNNER_TEMP/wc-pristine`;
  the `GATE_SUITE_CALL` (`python3 .github/scripts/run-local-gates.py`) is the
  sole carve-out, so moving the step needs the carve-out moved with it.
- Gate 104 (`verify-board-loop-composite-provenance.py`): composites are
  `uses:`d from `.wc-pristine-repo`; a new gate-suite job must do the same.
- `verify-implement-gate-suite-preflight.py`: asserts the preflight text and
  the `script-exists` skip shape of both implement sites.
- `verify-stage-tool-lists.py`: owns the `Bash(python ...run-local-gates.py:*)`
  grant and the stage write-boundary lists the `.git/**` deny (T029) extends.

Gate registration: a gate is a `verify-*.py` invoked from a
`lint-workflows.yml` step (plain run plus `--self-test`) with path triggers;
`wc_gate_registry.py` recovers argv from those steps and `run-local-gates.py`
runs them, so one registration serves CI and local (FR-019/FR-021). Gates 149
and 150 are the examples (Gate 151, `verify-composite-run-provenance.py`, is
registered the same way).

## Job-split hazards found at implement cycle 4 (for T011-T014)

Splitting board-loop's `fix` job at the push boundary is not a mechanical
move. (1) `fix` holds `concurrency: group: wing-commander-board-loop`; a
second job in the same group would queue behind it and deadlock, while a
publish job with no group lets the next queued run start before the push.
(2) `review` reads `needs.fix.outputs.pr-number`/`breach` and `needs.fix.result`,
so the job that pushes must keep the name `fix` or those readers move with
it. (3) Every post-gate step reads `steps.base`, `steps.ctx`, the snapshot
and the `.wc-pristine-repo` copy, so the publish job must rebuild all four
from the bundle. Gates 98/104 and the resume-gating gate each hold `fix` to
its current shape and move in the same commit. None of this could be run
(the gate suite needs PyYAML, absent in this job), so the split was not
attempted blind.

## How the split landed (T011-T014, local session)

The three hazards above, resolved:

1. Every new board-loop job joins `wing-commander-board-loop`. They run in
   sequence through `needs:`, so sharing the group never makes one wait on
   another. The group is taken per job, not per run, so the split adds
   handoff gaps (fix-agent → gate-suite-fix → fix) in which another run's
   pending job can take it -- the exposure the gaps between select, triage,
   route and fix already carried; select's marker read is what keeps two
   runs off one item (code review of #990).
2. The publishing job keeps the name `fix` (and its `pr-number`/`breach`
   outputs); the agent's half is the new `fix-agent`. review-fixup's
   publisher is the new `review-fixup-publish`; `review` keeps its outputs
   and gains `branch`, `round`, `reviewed-sha` and `fixup-head-sha`.
3. Each publisher rebuilds checkout, snapshot, trusted copy and context,
   restores the agent's commits from the bundle (refusing any head but the
   producing job's own `head-sha` output), and reads the verdict under the
   old in-job suite's step id (`gate-suite`, `gate-suite-review-fixup`), so
   every later step reads the same outputs it always did.

Board loop: `fix-agent` → `gate-suite-fix` → `fix`, and `review` →
`gate-suite-review-fixup` → `review-fixup-publish`. Implement:
`gate-suite-implement-cycle` → `implement`.

## T015 decision: the implement retry site is deferred

Decision: **defer**, recorded in
`.github/scripts/wc_gate_suite_sites.py`'s `EXEMPT_GATE_SUITE_SITES`, which
cites the Maintenance backlog (#889) as its tracker because #737 closes when
this spec ships (Gate 124 keeps the citation honest). The maintainer adds the
matching checklist line on #889 and records the deferrals below on #737.

Reason: the retry leg's suite runs after the cycle agent and before the
retry agent, in the same job, and its verdict feeds the retry prompt. A job
boundary cannot sit between two steps of one job, so containing it means
moving the whole retry chain -- the retry agent, its post-agent credential
steps, its read-back and outcome artifact, and the consolidation the
dispatch steps read -- into a job of its own. That is a restructuring of
the stage's control flow, not a containment change, and it buys little
while the implement agent still runs the same suite itself with the token
in its environment (agent-invoked gates, deferred per research R6 and
bounded by spec 111). Gate 152 holds the retry step as the one recorded
deferral, fails if any other credential-bearing step runs the suite, and
fails if the deferral outlives its step.

## Deferrals to record on #737 (SC-007)

- Agent-invoked gates: the implement agent runs `run-local-gates.py` and
  `verify-*.py` itself, with the App token in its environment (R6; bounded
  by spec 111).
- The implement retry leg's deterministic suite (T015 above).
- Agent-composed pushes: the implement agent's and pr-conversation act's own
  `Bash(git push:*)` pushes are not hardened. The workflow cannot set the
  hardening env on those agent steps without a second copy of the idiom
  (the container env already uses `GIT_CONFIG_COUNT` for safe.directory,
  so a step-level copy would have to restate it), and an empty
  `GIT_CONFIG_GLOBAL` would also hide the action's own git setup. The
  `.git/**` deny (Gate 154) removes the agent's own route to plant a hook or
  config value; the deterministic push sites are hardened (Gate 150).
- FR-015 beyond the push: git calls other than the push that run after an
  agent in the same credential-bearing job -- implement's bookkeeping
  `git reset`/`git commit` before the hardened truncated-count push, its
  checkbox-count fetches, and `wing-commander-fold-commit`'s commit -- run
  without the hardening environment, so a hook the agent planted (a
  `pre-commit`, a `reference-transaction`) would still run there with the
  token in reach. FR-015 names "any git operation" (code review of #990,
  cross-referenced). Closing it means hardening the whole job's git
  environment after each agent step, which also switches off
  pr-conversation's own run-attribution `core.hooksPath` and changes the
  agent steps' git setup -- a trade-off for the owner. Until then the
  `.git/**` deny (Gate 154) is the mitigation.

## Read-access audit (T032, research R8)

Run on 2026-10-10 against this branch: `python3 .github/scripts/run-local-gates.py
--jobs 6` with `GH_TOKEN`, `GITHUB_TOKEN` and `GH_ENTERPRISE_TOKEN` unset, `HOME`
and `GH_CONFIG_DIR` pointed at an empty directory (no gh login, no git
credential helper), so no gate could reach any credential at all -- stricter
than the gate jobs, which keep a read-only `github.token` the checkout does
not persist. Result: 248/249 gates passed. The one failure,
`verify-auto-release-gate-waits-for-stage.py`, is a 2-second poll budget
missed under parallel load; it passes on its own, with the same empty
environment, and reads no credential. No gate needs a write credential, or
any credential, so nothing was changed for the audit.

## Probe fixture for SC-001/SC-005 (T018)

A gate that prints what it can reach. Put it on a throwaway fix branch as
`.github/scripts/verify-zz-probe.py` and register it in
`lint-workflows.yml` like any gate (a plain `run: python3
.github/scripts/verify-zz-probe.py` step), so `run-local-gates.py` runs it:

```python
#!/usr/bin/env python3
import os, sys
hits = sorted(k for k in os.environ
              if any(w in k for w in ("TOKEN", "SECRET", "KEY", "PASSWORD")))
print("credential-shaped variables: " + (", ".join(hits) or "none"))
print("WC_BOT_TOKEN present: " + str("WC_BOT_TOKEN" in os.environ))
for f in (os.environ.get("GITHUB_ENV"), os.environ.get("GITHUB_PATH")):
    if f:
        with open(f, "a") as fh:  # a write the publisher must never see
            fh.write("WC_PROBE_INJECTED=1\n" if f.endswith("env") else "/tmp/wc-probe\n")
pristine = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "wc-pristine")
print("snapshot present in this job: " + str(os.path.isdir(pristine)))
sys.exit(int(os.environ.get("WC_PROBE_FAIL", "0")))
```

Walkthrough, one board-loop item through `fix`:

1. Green (`WC_PROBE_FAIL` unset): `gate-suite-fix`'s log prints
   `credential-shaped variables: none` (at most `ACTIONS_*` runtime names,
   none of which writes to the repository) and `WC_BOT_TOKEN present:
   False` and `snapshot present in this job: False`. `fix` reads
   `outcome=pass`, its environment has no `WC_PROBE_INJECTED`, and it
   pushes through the hardened composite and opens the PR (SC-001,
   SC-002).
2. Red (the probe exits 1): `fix` reads `outcome=fail`, posts the first
   failing gate inside a fence, applies `board:stalled`, and pushes nothing
   (SC-005).
3. No verdict (cancel `gate-suite-fix` mid-run): `fix` still runs, reads
   `reason=verdict artifact missing`, and takes the red path of step 2
   (FR-004).
4. The same probe on a spec branch drives `gate-suite-implement-cycle`; the
   implement agent's prompt carries the verdict, and `implement`'s
   environment has no `WC_PROBE_INJECTED`.

Prerequisites: a checkout of the branch, Python 3 with PyYAML, `jq`, `git`.

## Local

1. Full PR-time suite: `python .github/scripts/run-local-gates.py`
   — expect every new gate listed in
   [contracts/new-gates.md](contracts/new-gates.md) to pass.
2. Each gate's failure branches: `python .github/scripts/<gate>.py --self-test`
   — expect every fixture to be rejected for its named reason.
3. Hardened push: `python .github/scripts/verify-hardened-push.py --self-test`
   plants a `pre-push` hook and a `url.<base>.insteadOf` value in a scratch
   repo; expect the hook not to run and the push to reach the stated bare repo.
4. Reader: feed `wc_gate_verdict.py` a missing file, junk, a SHA-mismatched
   verdict and a valid pass; expect `fail, fail, fail, pass`.

## After merge (FR-024 / SC-008)

1. Probe fixture: on a throwaway fix branch add a gate script that prints its
   environment and tries `chmod u+w` on the snapshot and an append to
   `$GITHUB_ENV`. Drive one board-loop item through `fix` (via `gh workflow
   run` on the wrapper that can dispatch it). Expect: no token in the printed
   environment, later steps unaffected, and a red suite yields a fenced comment
   and `board:stalled`, no push.
2. Re-drive a green item: expect push and an opened PR.
3. Re-drive one `implement` cycle: expect the gate verdict to reach the agent
   prompt and the stage to push through the hardened composite.
4. Record run URLs on the PR or #737.
