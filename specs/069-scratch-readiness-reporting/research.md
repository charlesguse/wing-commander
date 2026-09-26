# Phase 0 Research: A readiness verdict that is reachable and documentation that matches it

Every decision below resolves a design question the spec leaves to planning
(spec.md carries no `[NEEDS CLARIFICATION]` marker — Q1 was answered in
Clarifications, 2026-09-25). None of these is a spec-mandated literal; they
are documented here so tasks/implementation don't re-derive them, and so the
plan-stage issue comment can list them as decisions made without a second
clarification round.

## D1: How the three-valued element outcome is represented in `checks.sh`

**Decision**: Keep every `check_<key>` function's calling convention as a
plain boolean (`return 0` ready, `return 1` not-ready) — every existing call
site (`provision-e2e-target.sh`'s act-skip loop, the marker/self-refusal
guards) only ever needs "is it ready" to decide whether to act, never the
three-way split. Add a second, per-key signal: a global
`<KEY_UPPER>_NOT_CHECKABLE` flag, set to `true` by the check function itself
exactly when it determines the failure is a property of the checking
credential rather than the target. `assemble_report` (the one place that
already loops over every key — data-model.md's single home) reads both the
boolean and the flag after calling `check_$key`, and classifies each element
as `ready` / `missing` / `not_checkable`.

**Rationale**: `claude_credential` and `container_image_pin` already carry
exactly this pattern (`CLAUDE_CREDENTIAL_NOT_CHECKABLE`,
`CONTAINER_IMAGE_PIN_NOT_CHECKABLE`, set on a `gh_permission_denied` hit) —
extending it to `app_installation` (a new `APP_INSTALLATION_NOT_CHECKABLE`,
set whenever `WC_APP_INSTALLATION_KNOWN_READY` is not the literal `true`)
reuses a convention already reviewed and tested (T036) instead of
introducing a second, incompatible representation of the same idea.
Constitution IX: the classification stays in `assemble_report`'s
deterministic code, never a judgment call left implicit in a caller.

**Alternatives considered**: (a) a three-way exit code (0/1/2) from each
`check_<key>` function — rejected because it changes the meaning of the
boolean return every existing non-`assemble_report` call site relies on,
for no gain the flag doesn't already give. (b) A single global associative
array (`OUTCOME[$key]=...`) set directly by each check function instead of
a boolean-plus-flag pair — rejected as a bigger diff for the same result;
the flag pattern is already half-built and reviewed.

## D2: Aggregate verdict precedence

**Decision**: `assemble_report` computes the verdict in this order: any
element `missing` → `not_clear`; else any element `not_checkable` →
`unverified`; else → `all_clear`.

**Rationale**: Directly implements FR-003 and the Edge Cases section ("a
real failure outranks an unverified element"). A single ordered check (missing
first) makes the precedence readable in one place rather than split across
two boolean folds.

**Alternatives considered**: computing `all_clear`/`not_clear` first and
only checking for `not_checkable` when nothing is missing — same result,
less obviously ordered; rejected for clarity, not correctness.

## D3: Exit status values

**Decision**: `0` = `all_clear`, `1` = `not_clear`, `2` = `unverified`.

**Rationale**: `1` is already `provision-e2e-target.sh`'s generic
non-verdict failure code (bad flags, self-refusal, marker-write failure —
none of which reach `assemble_report` at all), so keeping "a required
element is missing" on the same code a caller already treats as failure is
the smallest change. `2` is deliberately a code no existing call site emits
today, so a caller that only branches on `$? -eq 0` still fails safe (a
caller checking `-ne 0` behaves as it always has; FR-004 forbids exit `0`
for `unverified`, which this satisfies either way), while a caller that
wants to distinguish "genuinely broken" from "nothing found missing, some
elements unverified" (SC-008) has a code to test for.

**Alternatives considered**: `3` for `unverified` to leave `2` free for
some future meaning — rejected, nothing in this feature or its Assumptions
anticipates a fourth code, and an unused reserved value is speculative.

## D4: `ReadinessReport` schema changes (`ready: bool` → tri-state)

**Decision**: Per-element `ready: bool` becomes `outcome: "ready" |
"missing" | "not_checkable"`. Top-level `ready: bool` becomes `verdict:
"all_clear" | "not_clear" | "unverified"`. `remaining_action` keeps its
current meaning and is non-null whenever `outcome != "ready"` — for a
`not_checkable` element it already names the checking route the report
must name per FR-005 (the existing "Not checkable with this token... run
... --check-only locally" wording, and the existing `app_installation`
wording naming the dispatched readiness check).

**Rationale**: FR-001 requires the three outcomes to be "separately
identifiable by a machine consumer," which a boolean plus a text-matched
substring is not — a consumer would have to pattern-match
`remaining_action` to tell `missing` from `not_checkable`, which is exactly
the "judgement the readiness report exists to remove" the spec's User
Story 1 opens with. This is a breaking change to the JSON shape, which is
acceptable: `provision-e2e-target.sh` and this workflow are the
consuming-instrument, not the published stage contract (Constitution VII;
`contracts/readiness-workflow.md` already says so), and this repository's
own search (see below) found no other script, workflow, or gate that
parses `.ready` or `.elements[].ready` from this specific report — the only
two readers are `provision-e2e-target.sh` itself and
`auto-update-spec-kit-scratch-preflight.yml`, both edited in this same
feature. `board_readiness.py`'s unrelated `ReadinessDecision` (board-loop
PR-merge readiness, specs/057) shares the English word "ready" but not this
schema, this file, or this feature's element list.

**Alternatives considered**: keep `ready: bool` alongside a new `outcome`
field, deriving `ready` for compatibility — rejected per this repository's
own convention against compatibility shims for an interface nothing
external pins (CLAUDE.md/constitution VII); a field nothing reads is a
stale field waiting to happen (constitution's own recurring lesson, see
`.specify/memory/constitution.md`'s 1.5.1 Sync Impact Report on exactly
this failure mode for a different literal).

## D5: `app_installation` never reports `missing`

**Decision**: Document explicitly (data-model.md) that `check_app_installation`
only ever classifies as `ready` or `not_checkable`, never `missing`, given
the existing call graph: `auto-update-spec-kit-scratch-preflight.yml`
already exits before invoking `checks.sh` at all when the App-token mint
fails (the workflow's existing "Run the readiness check" step, unchanged by
this feature), so the only time `checks.sh` runs in CI, the mint already
succeeded and the hint is `true`. Locally, the hint is never set at all
(Assumptions: no maintainer credential can supply it). No code path this
feature adds ever sets the hint to a value proving non-installation.

**Rationale**: Prevents a reader (or a future task) from expecting a
"missing" `app_installation` row from either route and adding dead code to
produce one; documents the existing (and unchanged) short-circuit as the
reason.

## D6: FR-013 — `act_repository`'s return code

**Decision**: Change

```bash
if ! check_repository "$OWNER" "$NAME"; then
  act_repository "$OWNER" "$NAME"
fi
```

to check `act_repository`'s own exit status and stop immediately, before
the scratch-marker step, naming repository creation as the failed action —
mirroring the existing T046 pattern for `act_scratch_marker`'s own failure
handling (`provision-e2e-target.sh:264-268`), which already establishes
"exit non-zero, name the action, touch nothing further" as this script's
convention for a failed privileged write.

**Rationale**: Directly implements FR-013/SC-004: today a failed `gh repo
create` is silently ignored (`set -uo pipefail`, no `-e`, and the call's
output is redirected to `/dev/null`), so the run falls through to the
scratch-marker step and fails there with "failed to write the scratch
marker to OWNER/NAME," misdiagnosing a repository-creation failure as a
marker-write failure.

## D7: FR-014 — regression test placement and fixture

**Decision**: Add the new case to `t4_refuse_self.sh` (already this
repository's home for FR-007 self-refusal coverage), using the same
stubbed-`git` fixture `t9_maintainer_feedback.sh`'s T045 case already
builds (a `PATH`-shadowing `git` that fails only `remote.origin.url`), but
with `GITHUB_REPOSITORY` exported naming the target itself rather than left
unset — asserting refusal with the FR-007 self-target message, not the
T045 "could not determine this repository" message, and zero `gh` calls.

**Rationale**: FR-014 explicitly calls this "distinct from the existing
coverage of the case where no identity resolves at all" (T045, already in
`t9_maintainer_feedback.sh`) — placing the new, closely related case beside
the other self-refusal coverage in `t4_refuse_self.sh` keeps the two
"which signal resolved, and to what" fixtures next to each other rather
than splitting FR-007-family coverage across files.

**Alternatives considered**: adding it to `t9_maintainer_feedback.sh` next
to T045 — rejected only because `t4_refuse_self.sh` is the test whose
entire subject is FR-007's self-refusal path from a real (not stubbed)
`this_repo()`, and the new case is a variant of exactly that scenario, not
a maintainer-feedback regression.

## D8: FR-015/FR-016 — announcing the honoured hint

**Decision**: When `check_app_installation` returns ready because
`WC_APP_INSTALLATION_KNOWN_READY=true`, `assemble_report` appends one
sentence to that element's already-present-when-ready-is-false convention —
concretely, the human-readable summary block `provision-e2e-target.sh`
already prints on stderr (the `jq -r '.elements[] | ...'` line) gains a
one-line note after `app_installation`'s row when the hint was honoured:
`  (confirmed via WC_APP_INSTALLATION_KNOWN_READY -- see docs/setup.md if
this was not set intentionally)`. The CI job summary table
(`auto-update-spec-kit-scratch-preflight.yml`) is unaffected beyond the
table already showing this row `ready` — that workflow always sets the hint
deliberately (it is the "caller that legitimately sets it," FR-016), so
"say so" for that route is already implicit in FR-016 naming it as the
legitimate setter; the risk FR-015/016 target is a maintainer's own shell.

**Rationale**: Keeps the note where a maintainer running the script locally
would actually see it, and ties it to docs/setup.md, which FR-016 requires
to name the hint and the hazard.

## D9: FR-017 — what `t9`'s existing hint-dependent case must say

**Decision**: The T037/T044 case in `t9_maintainer_feedback.sh` (the one
`--check-only` exit-0 case that depends on exporting
`WC_APP_INSTALLATION_KNOWN_READY=true`) gains an explicit comment stating:
this stands in for the dispatched readiness check's own token-mint proof of
installation (D5); it does not exercise real JWT-only verification; and
that is why the local, maintainer-run path can never itself reach
`app_installation: ready` — masking the exact limitation User Story 1 of
this feature addresses (originating review item 9, `#516`).

**Rationale**: FR-017 in the words of spec.md: "state in the test itself
what the hint stands in for and which limitation it masks." The comment
already partially explains *why* the hint is used (T044's Independent Test
is framed as the readiness check); it does not yet say *what limitation
depending on it hides. This decision closes that gap with the specific
wording tasks/implementation should use.

## Summary of touched files (for tasks generation)

- `.github/scripts/e2e-provisioning/checks.sh` — D1, D5, D8 (tri-state
  classification, `APP_INSTALLATION_NOT_CHECKABLE`, hint-honoured note,
  `assemble_report` verdict computation per D2).
- `.github/scripts/provision-e2e-target.sh` — D3 (exit codes), D6
  (`act_repository` return-code check).
- `.github/workflows/auto-update-spec-kit-scratch-preflight.yml` — job
  summary rendering for three outcomes/verdicts (still calling
  `provision-e2e-target.sh` unmodified in invocation shape — Gate
  `verify-e2e-provisioning-single-home.py` must keep passing).
- `.github/scripts/e2e-provisioning-tests/t4_refuse_self.sh` — D7 (new
  case).
- `.github/scripts/e2e-provisioning-tests/t9_maintainer_feedback.sh` — D9
  (comment), plus a new case for FR-013 (failed `gh repo create`, using
  `gh_stub.py`'s existing failure-injection seams).
- `.github/scripts/e2e-provisioning-tests/lib.sh` / `gh_stub.py` — only if
  a new failure-injection seam is needed for FR-013's fixture (repository
  creation failing); the existing `edit_forbidden`/`secrets_forbidden`-style
  flags are the precedent to extend rather than a new mechanism.
- `specs/053-e2e-scratch-provisioning/{spec.md,plan.md,data-model.md,
  quickstart.md,contracts/cli.md,contracts/readiness-workflow.md,
  contracts/readiness-report.schema.json}` and `docs/{setup.md,
  adoption.md}` — User Story 2's documentation corrections (FR-008–012),
  target state specified in this feature's own `data-model.md` and
  `contracts/`.
