# Contract: `provision-e2e-target.sh` CLI

**Location**: `.github/scripts/provision-e2e-target.sh` (FR-001, FR-014).
**Invoked by**: a maintainer's local shell, or an agent session running
against an already-authenticated local `gh` (FR-013). Never invoked from a
GitHub Actions job — no workflow in this repository may hold a credential
capable of creating a repository (FR-014).

## Invocation

```text
provision-e2e-target.sh --repo OWNER/NAME --profile auto-release|spec-kit-scratch [--check-only]
```

| Flag | Required | Description |
|---|---|---|
| `--repo OWNER/NAME` | yes | The target repository identifier. Refused if it case-insensitively equals this repository (FR-007), or — on the mutating path only, never under `--check-only` — fails the `scratch_marker` check against a non-empty, unmarked, pre-existing repository (data-model.md D3; `specs/069-scratch-readiness-reporting/contracts/cli.md`). |
| `--profile` | yes | `auto-release` or `spec-kit-scratch` (data-model.md `TargetProfile`). Selects the required-elements list. |
| `--check-only` | no | Performs zero mutating calls — runs the same `checks.sh` functions the privileged path would, but skips every `remedy: privileged` action. This is what the generalized readiness-check workflow uses (contracts/readiness-workflow.md), and what a maintainer can run locally without `repo` scope, using only read access to the target. |

No other flags. No interactive prompts under any flag combination (FR-013).

## Preconditions

- `gh` is already authenticated locally with `repo` scope for the target
  owner (assumed per spec.md's Assumptions; not verified beyond `gh auth
  status` failing loudly if unauthenticated at all).
- For the `claude_credential` element (auto-release profile only): the
  invoking shell has `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` set
  (research.md D5). Absence is reported as a not-ready element, not a
  script failure.

## Behavior

1. Refuse and exit non-zero immediately if `--repo` names this repository,
   or is malformed (not `OWNER/NAME` shape) — FR-007.
2. Unless `--check-only`: for each `OnboardingElement` in the selected
   profile whose `remedy` is `privileged` and whose `check` currently
   returns `not_ready`, perform the corresponding privileged action (create
   the repository, write the Claude credential secret, create the
   `spec-request` label, push the wrapper workflow set, set
   `WING_COMMANDER_CONTAINER_IMAGE`, write the `scratch_marker`
   description). Performing an element that is already in place is a no-op,
   not an error (FR-005) — every action is preceded by its own `check` and
   skipped if already `ready`.
3. Run every element's `check` (including `app_installation`, which is
   never performed, only checked) and assemble a `ReadinessReport`
   (data-model.md).
4. Print the `ReadinessReport` as JSON to stdout (contracts/readiness-report.schema.json)
   and a human-readable summary to stderr.
5. Exit status is a faithful summary of `ReadinessReport.verdict`
   (amended by `specs/069-scratch-readiness-reporting/data-model.md` — the
   original `ready: bool` no longer exists), never computed any other way:

   | `verdict` | Exit status | Meaning |
   |---|---|---|
   | `all_clear` | `0` | Every required element is `ready`. |
   | `not_clear` | `1` | At least one required element is `missing` — the same code this script already uses for every other failure (bad flags, self-refusal, a failed privileged write). |
   | `unverified` | `2` | Nothing is `missing`, but at least one required element is `not_checkable` by this route. |

   A run MUST NOT exit `0` for `unverified` or `not_clear`, so a calling
   agent session or CI step can act on the exit code alone without
   re-parsing JSON if it only needs a pass/fail signal (FR-004, FR-008) —
   and one that wants to distinguish "genuinely broken" from "unverified"
   has a third code to test for (SC-008).

## Guarantees (contract, not implementation detail)

- **No deletion, ever** (FR-016, SC-008): no code path in this script or
  the shared library it sources issues `gh repo delete`, `gh repo archive`,
  or any equivalent API call. The test harness (contracts and tasks stage)
  asserts this the same way `auto-update-spec-kit-tests/t4_verify.sh`
  already asserts it for `e2e-stage`'s narrower scope.
- **No credential value ever printed** (FR-009): stdout/stderr/the JSON
  report never contain a secret body — only presence booleans.
- **No App installation token used or widened** (FR-003): every privileged
  call in this script runs under the maintainer's own `gh` authentication,
  never under `secrets.WING_COMMANDER_APP_ID`/`_PRIVATE_KEY`.
- **Idempotent** (FR-005, SC-003): a second invocation with identical flags
  against an already-`ready` target performs zero privileged actions (every
  one is skipped by its own `check`) and produces the same `ReadinessReport`.
