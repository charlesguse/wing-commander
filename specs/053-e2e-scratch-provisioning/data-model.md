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
| `check` | function `(owner, name) -> ready\|not_ready` | Deterministic; makes only read calls (`gh repo view`, `gh secret list` for presence-only, `gh api repos/.../labels/spec-request`, `gh api .../contents/.github/workflows`, `gh variable list`). `app_installation`'s check makes no `gh` call at all — `GET /repos/{owner}/{repo}/installation` is App-JWT-only and can never succeed for either caller, so it trusts the `WC_APP_INSTALLATION_KNOWN_READY` hint alone (research.md D5, `specs/069-scratch-readiness-reporting/data-model.md`). Never inspects a secret's value (FR-009). |
| `remedy` | `privileged` \| `manual` | `privileged`: `provision-e2e-target.sh` can perform it under the maintainer's local credential. `manual`: only `app_installation` — the Declared Manual Step. |
| `remaining_action` | string template | Human-readable instruction emitted when `check` returns `not_ready`, naming the exact step and where to take it (FR-006). For `app_installation`: "Install the wing-commander App on `<owner>/<name>`: https://github.com/settings/installations". |

`scratch_marker` is new (research.md D3): it is `ready` when the repository
is empty (no commits) or its description matches the fixed marker string
this script writes on first successful provisioning; it is what makes
FR-007's refusal ("cannot establish as a reusable scratch verification
target") deterministic rather than heuristic. On the `--check-only` path
(`WC_CHECK_ONLY=true`) this element is exempt and always reports ready: the
refusal it exists to gate only applies to the mutating path, since nothing
mutates on a read-only run (`specs/069-scratch-readiness-reporting/contracts/cli.md`).

## ReadinessReport (amended, `specs/069-scratch-readiness-reporting/data-model.md`)

The per-element verdict produced by both callers (spec's Key Entities),
emitted as JSON on stdout and as a `GITHUB_STEP_SUMMARY` table when run in
the CI workflow. `ready: bool` (053's original shape) is replaced by the
tri-state `outcome`/`verdict` fields 069 introduced, because a boolean plus
a text-matched `remaining_action` cannot separately identify "genuinely
missing" from "this route's credential cannot check it" (FR-001/FR-002 of
069).

| Field | Type | Description |
|---|---|---|
| `target` | string `OWNER/NAME` | The repository provisioning or the readiness check was pointed at. |
| `profile` | `TargetProfile.name` | Which profile's element set was evaluated. |
| `elements` | list of `{key, outcome: "ready"\|"missing"\|"not_checkable", remaining_action: string \| null}` | One entry per element in `TargetProfile.required_elements`, in order. `remaining_action` is non-null iff `outcome != "ready"`; for `not_checkable` it names the route that can check the element instead. |
| `verdict` | `"all_clear"\|"not_clear"\|"unverified"` | `all_clear` iff every element is `ready`; `not_clear` if any element is `missing` (outranks `unverified`); `unverified` iff nothing is `missing` but at least one element is `not_checkable`. Maps 1:1 to the exit status (`0`/`1`/`2`). |
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

## Relationships (amended, `specs/069-scratch-readiness-reporting/data-model.md`)

```text
TargetProfile 1 ── * OnboardingElement        (required_elements, ordered, superset relationship)
ReadinessReport 1 ── * elements entry         (one per required OnboardingElement, same order)
ReadinessReport * ── 1 TargetProfile          (the profile evaluated)
elements entry 1 ── 1 ElementCheckOutcome     (ready | missing | not_checkable)
ReadinessReport 1 ── 1 AggregateVerdict       (all_clear | not_clear | unverified, replaces ready: bool)
OnboardingElement "app_installation" ── DeclaredManualStep  (singleton, remedy = manual)
```

## State transitions (amended, `specs/069-scratch-readiness-reporting/data-model.md`)

There is no stored state machine — "state" is always re-derived from the
target repository, and the local command still cannot itself observe an
App installation. The convergence path User Story 1's acceptance scenarios
4 and 5 describe now moves through the tri-state verdict, not a boolean:

```text
unverified (app_installation not_checkable; every other required element ready)
   │  [human installs the App in the GitHub UI — the only external event, then
   │   dispatch auto-update-spec-kit-scratch-preflight.yml against the same
   │   target — not a re-invocation of provision-e2e-target.sh: GET
   │   /repos/{owner}/{repo}/installation is App-JWT-only, so the local
   │   command can never itself observe the install and always reports
   │   app_installation as not_checkable (T043); the readiness workflow
   │   proves installation instead, from its own successful App-token mint]
   ▼
all_clear (spec-kit-scratch) — or unverified-with-different-elements
   (auto-release, whose claude_credential/container_image_pin stay
   not_checkable to the dispatched route by design, SC-007)
```

A further local re-invocation never changes `app_installation`'s row — it
stays `not_checkable` regardless of the real install state (idempotent
otherwise, FR-005, SC-003); convergence on that one element is only ever
observed by dispatching the readiness check, never by re-running the local
command a second time.
