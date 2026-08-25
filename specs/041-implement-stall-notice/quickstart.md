# Quickstart: Validating the Chain-Stop Notice

This feature has no user-facing UI or CLI — validation means driving the
shipped GitHub Actions conditions and composite against modelled failures,
the same way this repository already validates every other gate/composite
(no adopter-facing manual steps to document; the runbook a maintainer follows
is embedded *in the notice itself*, per FR-008).

## Prerequisites

- Python 3, `bash`, `git`, `jq`, `gh` on `PATH` (already required by every
  existing `verify-*.py` gate script in this repository).
- No live GitHub API access needed — every scenario below is modelled
  locally, matching this repository's `wc_shell_harness.py` convention (a
  stubbed `gh` on `PATH`, a local bare-remote git repo for push/checkout
  steps).

## 1. Prove the notice is reachable when it should be, and only then (Gate 28)

```bash
python3 .github/scripts/verify-chain-stop-notice.py
```

Expected: PASS for all seven survivor-job conditions across every modelled
`needs.*` combination in contracts/chain-stop-gate-coverage.md's table, and
PASS on each of the four required mutations independently turning at least
one row red (confirming the coverage cannot be quietly weakened — FR-013).

## 2. Prove Gate 15 still catches the shape this feature fixes, and now catches its output-based cousin too

```bash
python3 .github/scripts/verify-gate-15.py
```

Expected: PASS, including the new fixture modelling `stalled`'s literal
pre-fix condition (must be flagged) and the fixed, `!cancelled()`-prefixed
version (must not be flagged) — the regression proof research.md D9
requires.

## 3. Drive the new composite's own shell against a modelled abnormal termination

Using `wc_shell_harness.py`'s existing `run_step`/stubbed-`gh` pattern
(the same one `verify-stall-restart-runbook.py` already established for
today's `stalled` job):

1. Build a synthetic git repo with a `spec-meta.json` reading
   `{"stage": "implement", "iteration": 2}` on a branch matching the
   composite's expected naming.
2. Run `wing-commander-chain-stop-notice`'s steps via `run_step`, with
   `spec-dir`/`spec-branch` pointing at the synthetic repo and a stubbed
   `gh` recording every `issue comment`/`label` invocation.
3. Assert: the branch's `spec-meta.json` now reads `"stage": "stalled"`; the
   stubbed `gh` recorded exactly one `issue comment` call whose body matches
   the "stage did not start" template (data-model.md); exactly one
   `stage:stalled` label add and (when `stage-label` was non-empty) one
   label removal.
4. Repeat with the synthetic repo's remote deliberately unreachable (no
   bare remote configured) — assert the composite still posts exactly one
   comment, now using the "record could not be updated" wording, and does
   not raise (FR-011, Edge Cases).
5. Repeat with `spec-dir` empty (the intake case, research.md D5) — assert
   the record-mark step is skipped entirely and the same "record could not
   be updated" comment is posted.

## 4. Drive a refusal-shaped step and confirm the in-job callout fires, not the survivor job

1. Extract `wing-commander-preflight`'s step via `find_step`, run it with
   `require-credential: "true"` and both credential inputs empty (forces the
   existing refusal branch).
2. Assert `steps.preflight.outputs.refused == 'true'` and `.reason` is
   non-empty, then confirm (per Gate 28's fixture table) that with
   `needs.<job>.outputs.refusal-reason` set from this value, the survivor
   job's modelled condition evaluates `false` — the refusal and the
   abnormal-termination path cannot both fire for the same run.

## 5. Manual / integration confirmation (documented, not automated by this feature)

A live end-to-end drill — dispatching a real `implement` run against a
deliberately broken container image or a deliberately revoked credential in
a scratch adopter repository — is the same category of verification this
repository already defers to a human pass for runner/container-image
features (see specs/038's plan.md T001 precedent). Recommended before first
release of this feature:
1. Dispatch `implement` with an intentionally invalid `container-image`, so
   `verify-image-prerequisites` fails and `implement` never starts. Confirm
   the lifecycle issue receives the "stage did not start" notice, the
   `stage:stalled` label is applied, and `spec-meta.json` reads `"stage":
   "stalled"` afterward.
2. Dispatch `clarify` (or any of the other four minimally-bookkept stages)
   against a spec whose `.claude/skills/speckit-clarify/SKILL.md` was
   removed from the checkout, forcing a preflight refusal. Confirm only the
   `[!IMPORTANT]` could-not-start note appears, and the lifecycle record's
   `stage` field is unchanged.
3. Cancel an in-flight `implement` run by hand. Confirm no notice appears
   and the record is unchanged (FR-009).
