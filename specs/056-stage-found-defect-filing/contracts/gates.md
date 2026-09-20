# Contract: FR-030, FR-031, FR-032 — gate coverage

## `verify-stage-findings-wiring.py` (NEW), FR-031

Registered in `lint-workflows.yml` as a PR-time gate (so `run-local-gates.py`
picks up its arguments automatically per Principle VIII). For each of the
six stage workflows named in `stage-wiring.md`:
- parses the workflow's job YAML for the `wing-commander-stage-findings`
  `uses:` step;
- parses the agent step's prompt-composition (wherever that stage builds
  its prompt string) for the stable substring naming the FR-003 paragraph;
- fails loudly, naming the stage and which side is missing, if exactly one
  of the two is present — checked identically whether or not that stage's
  `findings-filing-enabled` default is `true` (FR-001a: the mechanism's
  presence is not conditional on the default).
- fails loudly (not "0 stages checked, pass") if it cannot find the
  workflow file at all — Principle VIII's "loud rather than vacuous" rule.

Fixture (FR-030): a checked-in copy of one stage workflow with the step
present/paragraph absent, and the mirror case, each asserted to fail; the
real six workflows, post-implementation, asserted to pass.

## `verify-single-home-idioms.py` (EXTENDED), FR-032

`DECLARED_HOMES` gains two entries:
- `"stage-findings": ".github/actions/wing-commander-stage-findings/action.yml"`
- `"outstanding-task-item": ".github/actions/wing-commander-outstanding-task-item/action.yml"`

and its existing `"failure-issue"` entry is repointed to
`.github/actions/wing-commander-durable-failure-issue/action.yml`
(`wing-commander-durable-failure-issue.md`'s "Move" section).

Each new entry needs a `check_*` function mirroring `check_failure_issue`'s
shape: a regex fingerprint of the idiom's distinguishing fragment (for
`stage-findings`, the co-occurrence of the fingerprint formula and the
schema-validation call; for `outstanding-task-item`, the literal
`gh issue comment ... "- [ ] "` pattern), scanned across every workflow and
every non-declared-home action file. `check_promotion` (the existing
`_shared/`-reference scan) needs no new logic — it already scans every
`published_stages()` workflow and every non-underscore composite for a
`_shared/` reference, which is sufficient to catch a future stage or
composite that tries to reach either new composite by an internal path (it
would not be an internal path, since both are promoted, so this is really
confirming no *regression* introduces a `_shared/`-rooted twin later).

Fixture (FR-030): the gate's own mutation-testing pattern (seen in
`verify-metrics-summary-record-emission.py`) — plant a second copy of each
idiom's fingerprint fragment in a scratch file, assert the gate catches
it, remove it, assert clean.

## `wing-commander-stage-findings`'s own fixtures, FR-030

Per `research.md` D14, colocated under
`.github/actions/wing-commander-stage-findings/tests/`, one fixture per
required branch: malformed proposal (dropped, reason logged), dedup hit
against an open issue (commented, not duplicated), dedup hit against a
closed issue (new issue created and linked, not reopened), cap overflow
(excess dropped in proposal order), API failure (finding text preserved in
log, stage outcome unaffected), and the no-findings case (silent, no new
output). Both channel shapes are exercised, including a `structured-array`
result that omits the `findings` property entirely (must validate as zero
findings, not fail).
