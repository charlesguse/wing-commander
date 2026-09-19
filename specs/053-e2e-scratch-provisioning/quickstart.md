# Quickstart: On-demand E2E scratch repository provisioning

Validates User Story 1 (P1) end to end, using its own Acceptance Scenarios
1, 3, 4, and 5. Run locally — this entry point never runs in Actions
(FR-014).

## Prerequisites

- `gh` authenticated locally with `repo` scope for the account that will
  own the target repository (`gh auth status`).
- `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` exported in the shell
  (only needed for the `auto-release` profile — see
  `contracts/cli.md` and `data-model.md` D5).
- Checked out at the commit under test (the wrapper set provisioning copies
  for the `auto-release` profile comes from this checkout, per research.md
  D6 — not from the last released tag).

## 1. Provision a brand-new auto-release target (Acceptance Scenario 1)

```console
$ .github/scripts/provision-e2e-target.sh \
    --repo your-account/wc-e2e-scratch \
    --profile auto-release
```

Expected: the repository is created; the `spec-request` label, the Claude
credential secret, the eight-file wrapper set (pinned to this checkout's
commit), and the `WING_COMMANDER_CONTAINER_IMAGE` variable are all written;
the printed `ReadinessReport` (contracts/readiness-report.schema.json) shows
every element `ready: true` **except** `app_installation`, whose
`remaining_action` names installing the wing-commander App at
`https://github.com/settings/installations`. Exit code `1` (not ready).

## 2. Install the App (the one declared manual step)

In the GitHub UI, install the wing-commander App on
`your-account/wc-e2e-scratch`.

## 3. Confirm the App is installed, then re-invoke the same command (Acceptance Scenario 5)

`GET /repos/{owner}/{repo}/installation` requires GitHub App JWT
authentication (REST API reference, Apps category): neither a maintainer's
own token nor an installation access token can ever get a real answer from
it, so this local command cannot verify `app_installation` itself and
always reports it as the outstanding manual step (T043 of this feature's
maintainer feedback). Convergence is observed through the readiness check
(User Story 2) instead, since that workflow already proves installation
from its own successful App-token mint:

```console
$ gh workflow run auto-update-spec-kit-scratch-preflight.yml \
    -f target=your-account/wc-e2e-scratch -f profile=auto-release
```

Expected: the dispatched run's `GITHUB_STEP_SUMMARY` shows every element
(including `app_installation`) `ready`, exit code `0`. Re-invoking the
local command from step 1 still re-checks and re-reports every other
element correctly, but its own `app_installation` row stays `not ready`
regardless of the real install state — that is expected, not a bug.
Elements already written in step 1 are untouched either way — no second
commit to the wrapper set, no label recreated, no secret rewritten.

## 4. Re-run against an already-ready target (Acceptance Scenario 3, FR-005, SC-003)

```console
$ .github/scripts/provision-e2e-target.sh \
    --repo your-account/wc-e2e-scratch \
    --profile auto-release
```

Expected: identical `ReadinessReport` to a re-run of step 1's local
command (not step 3's CI dispatch — see step 3's note on why the local
path's own `app_installation` row never flips), zero privileged calls
made. Exit code stays `1` locally, for the same reason as step 1; dispatch
the readiness check again if you want to see exit code `0`.

## 5. Dispatch a real verification against the provisioned target (Acceptance Scenario 2)

Set the repository variable `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` to
`your-account/wc-e2e-scratch`, then dispatch `auto-release.yml`. Expected:
the run passes `config`, `reachable`, `reset`, `scaffold`, and `kickoff`
without an infrastructure failure — the same infrastructure checks
`docs/setup.md`'s pre-created-repository row already documents.

## 6. Confirm the refusal cases (Acceptance Scenario 4, FR-007)

```console
$ .github/scripts/provision-e2e-target.sh --repo <this-repository> --profile auto-release
```

Expected: immediate refusal naming self-targeting as the reason, no calls
made.

```console
$ .github/scripts/provision-e2e-target.sh --repo your-account/some-unrelated-repo --profile spec-kit-scratch
```

(where `some-unrelated-repo` is pre-existing, non-empty, and carries no
scratch marker) Expected: refusal naming that the repository cannot be
established as a reusable scratch target (data-model.md D3), no mutation
made.

## 7. Check readiness without provisioning anything (User Story 2)

```console
$ .github/scripts/provision-e2e-target.sh \
    --repo your-account/wc-e2e-scratch \
    --profile auto-release \
    --check-only
```

Expected: same `ReadinessReport` shape, zero mutating calls, usable with
only read access to the target.

Or, from the CI side (SC-006 — zero Claude quota, ≤1 runner-minute):

```console
$ gh workflow run auto-update-spec-kit-scratch-preflight.yml \
    -f target=your-account/wc-e2e-scratch -f profile=auto-release
```

Expected: the run's job summary lists every element with a ✅/❌ and, for
any ❌, the exact remaining action — no agent step runs.
