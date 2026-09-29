# Quickstart: A readiness verdict that is reachable and documentation that matches it

Validates User Story 1 (P1, all five Acceptance Scenarios) and User Story 3
(P3, Acceptance Scenarios 1 and 3). User Story 2 (P2) is a documentation
correction with no independently runnable behavior of its own — its
Independent Test is "read each named location end to end against the
shipped behaviour," which this quickstart's own numbered steps double as
once User Story 1 ships (the corrected `quickstart.md` step 3 below is
what FR-008 requires).

Run against the same kind of target as
`specs/053-e2e-scratch-provisioning/quickstart.md` (a disposable, maintainer
-owned repository) — this feature changes what the readiness check reports,
not what it provisions (FR-007, SC-005).

## Prerequisites

Same as `specs/053-e2e-scratch-provisioning/quickstart.md`: `gh`
authenticated locally with `repo` scope; `CLAUDE_CODE_OAUTH_TOKEN` or
`ANTHROPIC_API_KEY` exported for the `auto-release` profile; checked out at
the commit under test.

## 1. `spec-kit-scratch` reaches `all_clear` — but only through the dispatched route (Acceptance Scenario 1, SC-001)

```console
$ .github/scripts/provision-e2e-target.sh \
    --repo your-account/wc-e2e-scratch --profile spec-kit-scratch
```

Expected: `repository` and `scratch_marker` report `outcome: ready`;
`app_installation` reports `outcome: not_checkable` (never `missing` —
research.md D5) with a `remaining_action` naming the dispatched readiness
check. `verdict: unverified`. Exit code `2`. This is the one behavioral
change to `spec-kit-scratch`'s local run FR-006 describes: before this
feature the same run reported not-ready/exit `1`; nothing else about this
profile's required elements changes.

Install the wing-commander App on the target in the GitHub UI, then:

```console
$ gh workflow run auto-update-spec-kit-scratch-preflight.yml \
    -f target=your-account/wc-e2e-scratch -f profile=spec-kit-scratch
```

Expected: the job summary shows every element ✅ (`ready`), the aggregate
line states `all_clear`, exit code `0` — this is the all-clear route SC-001
narrows to.

## 2. `auto-release`'s best attainable verdict is `unverified`, never `all_clear` (Acceptance Scenario 2, SC-001)

Provision a fully onboarded `auto-release` target (repeat
`specs/053-e2e-scratch-provisioning/quickstart.md` steps 1-2, or reuse an
existing one), install the App, then:

```console
$ gh workflow run auto-update-spec-kit-scratch-preflight.yml \
    -f target=your-account/wc-e2e-scratch -f profile=auto-release
```

Expected: `repository`, `app_installation`, `scratch_marker`,
`spec_request_label`, `wrapper_set` all ✅ (`ready`); `claude_credential`
and `container_image_pin` render as `not_checkable` (the distinct glyph
`../contracts/readiness-workflow.md` defines — never ❌), each naming that
the App token cannot read Secrets/Variables on this target and that
`--check-only` run locally is the route that can. The aggregate line states
`unverified`, never `all_clear`. Exit code `2`. No element is reported as a
failure (Acceptance Scenario 2's own wording).

## 3. A genuinely missing element still reports `not_clear`, never `unverified` (Acceptance Scenario 3, Edge Cases)

Against the same target, remove the Claude credential secret, then re-run
step 2's dispatch.

Expected: `claude_credential` renders as `missing` (❌), naming the export
+ re-run remedy; `container_image_pin` still renders `not_checkable` (➖).
The aggregate line states `not_clear` — the checked-and-missing element
outranks the unverified one (Edge Cases) — with its own exit code (`1`,
distinct from both `0` and `2`).

## 4. The CI job summary distinguishes all three states at a glance (Acceptance Scenario 5, SC-002)

Read the `GITHUB_STEP_SUMMARY` from either dispatch above without reading
any `remaining_action` text: confirm every row's glyph alone identifies
`ready`/`missing`/`not_checkable`, and the aggregate line names one of
`all_clear`/`not_clear`/`unverified` explicitly (not a bare pass/fail).

## 5. A failed repository creation names itself, not the marker step (User Story 3, Acceptance Scenario 1, FR-013)

Force `gh repo create` to fail (e.g. target a name you don't have
permission to create under, or one that already exists under different
ownership than expected):

```console
$ .github/scripts/provision-e2e-target.sh \
    --repo an-org-you-cannot-create-under/wc-e2e-fail --profile spec-kit-scratch
```

Expected: the run stops immediately and its stderr names repository
creation as the failed action. It never attempts to write the scratch
marker, and never prints "failed to write the scratch marker" for this
case (the pre-fix misdiagnosis, originating review item 7).

## 6. The honoured hint is disclosed, not silent (User Story 3, Acceptance Scenario 3, FR-015)

```console
$ WC_APP_INSTALLATION_KNOWN_READY=true .github/scripts/provision-e2e-target.sh \
    --repo your-account/wc-e2e-scratch --profile spec-kit-scratch --check-only
```

Expected: `app_installation` reports `ready`, and the human-readable
summary on stderr states that this was because
`WC_APP_INSTALLATION_KNOWN_READY` was honoured — confirm this note appears
even though nothing about the target itself changed. `docs/setup.md` names
this variable and the false-`ready` hazard of a stray value in a
maintainer's own shell (FR-016).

## 7. Existing 053 scenarios still hold unchanged

Re-run `specs/053-e2e-scratch-provisioning/quickstart.md` steps 4-7
(idempotent re-run, real dispatch against `auto-release.yml`, the two
refusal cases, `--check-only`'s zero-mutation guarantee) — none of this
feature's changes touch what is provisioned, refused, or mutated (FR-007,
SC-005), only how readiness is reported.
