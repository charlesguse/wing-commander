# Quickstart: validating spec 049

These are the checks a reviewer or CI runs to confirm the feature's
acceptance scenarios and success criteria actually hold, once
implementation lands. No implementation code here — see contracts/ for
interfaces and data-model.md for shapes.

## Prerequisites

- Repository root, `main` rebased in (per FR-021 — this feature is a
  follow-up against `main`, after #317).
- `.github/actions/_shared/scoped-app-token/action.yml`,
  `.github/actions/_shared/orphan-branch-reset/action.yml`,
  `.github/actions/_shared/durable-failure-issue/action.yml`,
  `.github/actions/_shared/auto-release-verdict.sh` exist.
- `.github/scripts/verify-single-home-idioms.py` and
  `.github/scripts/single-home-waivers.json` exist.

## 1. The gate suite passes on the consolidated tree (SC-004)

```
python .github/scripts/run-local-gates.py
```
Expected: every gate passes, including the new Gate 52 and its
self-test step, and Gate 52 is listed among the gates
`run-local-gates.py` ran (confirming it is reachable from the registry —
constitution VIII / FR-012).

## 2. A fix to a shared idiom lands once (User Story 1, SC-001)

For each of the three shared homes, make one observable edit and confirm
both consumers change:

- Edit the remediation text in `_shared/scoped-app-token/action.yml`'s
  reachability step. Grep both `auto-release.yml`'s and
  `auto-update-spec-kit.yml`'s rendered failure messages (their own
  wrapper text around `failure-reason`) — confirm neither hardcodes the
  old text, i.e. the edit is visible without touching either workflow.
- Edit the branch-naming/detach clause in
  `_shared/orphan-branch-reset/action.yml`. Confirm
  `git grep -n "checkout --quiet --orphan"` returns exactly one hit
  (the composite itself) across `.github/workflows/` and
  `.github/actions/`.
- Edit the label color in `_shared/durable-failure-issue/action.yml`'s
  default-color guidance (callers still pass their own `label-color`, but
  confirm the lookup/create logic itself has one copy):
  `git grep -n "gh label create" .github/workflows .github/actions` finds
  no `--force` label-create call outside the composite.

## 3. The next paste fails CI, naming the shared home (User Story 2, SC-003)

```
python .github/scripts/verify-single-home-idioms.py --self-test
```
Expected: PASS, including the fixture case that pastes an idiom into a
synthetic third workflow (neither `auto-release.yml` nor
`auto-update-spec-kit.yml`) and confirms the gate fails, naming both the
fixture's offending file:line and the real shared home's path.

Manual confirmation (not required for CI, useful for a reviewer): copy the
`checkout --quiet --orphan` / `git rm -rq --cached` / `find ... -exec rm
-rf` three-fragment block into a scratch workflow file under
`.github/workflows/`, run
`python .github/scripts/verify-single-home-idioms.py`, confirm it fails
naming that file and `_shared/orphan-branch-reset/action.yml`; delete the
scratch file, confirm it passes again.

## 4. The fail-infra verdict has one shape (User Story 3, SC-002)

```
git grep -n "outcome:" .github/workflows/auto-release.yml .github/actions
```
Expected: the only site defining the `{outcome, verified_head,
failing_check, expected, observed, evidence_url}` shape is
`_shared/auto-release-verdict.sh`; every other match is a call site
invoking it or reading its output. Byte-identity: run the script's test
harness (contracts/verdict-helper.md) against each of the 14 sites'
captured pre-refactor inputs and diff against their pre-refactor `jq -n`
output — zero diffs.

## 5. The adopter-pinned surface is unchanged (SC-008)

```
python .github/scripts/verify-single-home-idioms.py --self-test
```
includes the promotion-prevention fixture (a synthetic `workflow_call`
stage and a synthetic non-underscore composite, each referencing
`_shared/`) and confirms both fail. Separately, diff the set of directory
names directly under `.github/actions/` that do **not** start with `_`
before and after this feature's changes — expected: identical set (no
new published composite added, no existing one removed or renamed).

## 6. The records describe the tree that shipped (User Story 4, SC-006, SC-007)

- `git grep -n "## Auto-Release" docs/architecture.md` — one hit,
  positioned after `## Private-image dogfood` and before `## Reusability`
  (`git grep -n "^## " docs/architecture.md` to see the full section
  order).
- Read `specs/045-auto-release-verified-head/tasks.md` T023 — confirm it
  states no `shell_exempt` registration exists or is required, not that
  one was made.
- `gh pr view 317 --json body --jq .body` — confirm the finalize narrative
  states CI failed Gate 12 then Gate 15 before passing, and does not claim
  a `release.yml`/Gate 1a registration.

## 7. Waivers are discoverable in one place (SC-009)

```
cat .github/scripts/single-home-waivers.json
```
Expected: valid JSON, a `"waivers"` list (empty unless a genuinely new
third use was found during implementation — see research.md D8/D9).
`git grep -n "single-home-waiver\|gate52-waiver"` across
`.github/workflows/` and `.github/actions/` for any comment-based waiver
attempt — expected: none; Gate 52's self-test (case (d), see
contracts/single-home-gate.md) already proves a comment-only "waiver" does
not suppress a finding.

## 8. Constitution VII amendment (FR-024)

`head -40 .specify/memory/constitution.md` — confirm a new Sync Impact
Report is stacked at the top (version 1.6.0 → 1.6.1, PATCH, clarification
only), and `grep -n "underscore-prefixed" .specify/memory/constitution.md`
finds the new sentence inside Principle VII.
