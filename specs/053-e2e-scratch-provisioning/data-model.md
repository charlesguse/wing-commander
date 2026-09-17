# Phase 1 Data Model: On-demand E2E scratch repository provisioning

These are not persisted records — nothing in this feature has a database or
a file-based store (see plan.md's Technical Context: Storage = N/A). Every
entity below is a shape passed between the shared library, the two callers
(`provision-e2e-target.sh`, the generalized readiness-check workflow), and
their JSON output, and read back from the target repository's own live
state on every invocation (FR-008: the same deterministic code computes it
every time from the same inputs).

## TargetProfile

The named set of onboarding elements a verification point requires
(spec's Key Entities).

| Field | Type | Description |
|---|---|---|
| `name` | enum: `auto-release` \| `spec-kit-scratch` | Selects which elements apply. |
| `required_elements` | ordered list of `OnboardingElement.key` | `spec-kit-scratch`: `repository`, `app_installation`, `scratch_marker`. `auto-release`: those three plus `claude_credential`, `spec_request_label`, `wrapper_set`, `container_image_pin`. |

Validation: `auto-release`'s element set is a strict superset of
`spec-kit-scratch`'s (spec Assumptions: "the auto-release profile is a
superset of the spec-kit scratch profile rather than a different shape") —
enforced by construction, since `profiles.sh` defines
`spec-kit-scratch` first and `auto-release` as
`spec-kit-scratch + { ... }` rather than as two independent lists.

## OnboardingElement

One independently checkable precondition of a target.

| Field | Type | Description |
|---|---|---|
| `key` | string | Stable identifier: `repository`, `app_installation`, `scratch_marker`, `claude_credential`, `spec_request_label`, `wrapper_set`, `container_image_pin`. |
| `check` | function `(owner, name) -> ready\|not_ready` | Deterministic; makes only read calls (`gh repo view`, `gh api .../installation`, `gh secret list` for presence-only, `gh label view`, `gh api .../contents/.github/workflows`, `gh variable list`). Never inspects a secret's value (FR-009). |
| `remedy` | `privileged` \| `manual` | `privileged`: `provision-e2e-target.sh` can perform it under the maintainer's local credential. `manual`: only `app_installation` — the Declared Manual Step. |
| `remaining_action` | string template | Human-readable instruction emitted when `check` returns `not_ready`, naming the exact step and where to take it (FR-006). For `app_installation`: "Install the wing-commander App on `<owner>/<name>`: https://github.com/settings/installations". |

`scratch_marker` is new (research.md D3): it is `ready` when the repository
is empty (no commits) or its description matches the fixed marker string
this script writes on first successful provisioning; it is what makes
FR-007's refusal ("cannot establish as a reusable scratch verification
target") deterministic rather than heuristic.

## ReadinessReport

The per-element ready/not-ready verdict produced by both callers (spec's
Key Entities), emitted as JSON on stdout and as a `GITHUB_STEP_SUMMARY`
table when run in the CI workflow.

| Field | Type | Description |
|---|---|---|
| `target` | string `OWNER/NAME` | The repository provisioning or the readiness check was pointed at. |
| `profile` | `TargetProfile.name` | Which profile's element set was evaluated. |
| `elements` | list of `{key, ready: bool, remaining_action: string \| null}` | One entry per element in `TargetProfile.required_elements`, in order. |
| `ready` | bool | `true` iff every entry in `elements` is `ready` — never computed any other way (FR-004: "MUST NOT report the target as ready while any element for the chosen profile is missing"). |
| `generated_at` | ISO-8601 timestamp | For the CI job summary and for correlating a report with a specific dispatch. |

No field ever carries a credential value (FR-009) — `claude_credential`'s
check reports presence only, never the secret body, matching how
`gh secret list` itself works (it cannot return values).

## DeclaredManualStep

Not a general concept — exactly one: `app_installation`. Modeled as the one
`OnboardingElement` whose `remedy` is `manual` rather than `privileged`.
Kept as its own named row in this document (rather than folded silently
into the element table) because FR-015 forbids a second manual step ever
being introduced — a reviewer checking a future change for a new
`remedy: manual` element is checking this invariant directly.

## ProvisioningCredential (actor, not a data record)

The maintainer's own `repo`-scoped GitHub authentication (spec's Key
Entities), held only in the invoking shell's already-authenticated `gh`
context. Not modeled as a field anywhere in `ReadinessReport` or logged —
its presence is inferred only from whether `gh auth status` and the
privileged calls it attempts succeed. This is what FR-014 requires: the
identity is never a payload this feature's code carries.

## Relationships

```text
TargetProfile 1 ── * OnboardingElement   (required_elements, ordered, superset relationship)
ReadinessReport 1 ── * elements entry    (one per required OnboardingElement, same order)
ReadinessReport * ── 1 TargetProfile     (the profile evaluated)
OnboardingElement "app_installation" ── DeclaredManualStep  (singleton, remedy = manual)
```

## State transitions

There is no stored state machine — "state" is always re-derived from the
target repository. The only transition worth naming is the convergence
path User Story 1's acceptance scenarios 4 and 5 describe:

```text
not-ready (app_installation missing)
   │  [human installs the App in the GitHub UI — the only external event]
   ▼
re-invoke provision-e2e-target.sh (same command, same target)
   │  [claude_credential / spec_request_label / wrapper_set / container_image_pin
   │   were blocked behind app_installation for auto-release's App-scoped
   │   checks only where the check itself requires the installation to exist;
   │   elements provisionable without it were already completed on the first run]
   ▼
ready (all elements ready) — idempotent from here: a further re-invocation
changes nothing (FR-005, SC-003)
```
