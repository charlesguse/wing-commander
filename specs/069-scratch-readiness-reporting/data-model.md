# Phase 1 Data Model: A readiness verdict that is reachable and documentation that matches it

Same storage posture as spec 053 (Storage: N/A — nothing here is persisted;
every shape is re-derived live on each invocation, per FR-008's "the same
deterministic code computes it every time from the same inputs"). This
document amends spec 053's `data-model.md` in place (spec.md Assumptions:
"053 remains the governing spec for the provisioning tool itself"); it is
the target state the User Story 2 documentation tasks converge
`specs/053-e2e-scratch-provisioning/data-model.md` to. Entities not listed
here (`TargetProfile`, `ProvisioningCredential`) are unchanged from 053.

## ElementCheckOutcome (new — replaces the implicit ready/not-ready boolean)

The per-element result of one `OnboardingElement`'s `check` (FR-001).

| Value | Meaning |
|---|---|
| `ready` | The checking route verified this element is in place. |
| `missing` | The checking route verified this element is genuinely absent. |
| `not_checkable` | The checking route's credential cannot answer this element at all — neither ready nor missing is a real observation (FR-002). |

Computed by `assemble_report` (`.github/scripts/e2e-provisioning/checks.sh`)
from each `check_<key>` function's boolean return plus a per-key
`<KEY_UPPER>_NOT_CHECKABLE` flag the function itself sets when the failure
is a property of the credential rather than the target (research.md D1).
`not_checkable` is never treated as `ready` and never as `missing` in the
verdict computation (FR-002/FR-003).

`app_installation` is the one element whose `check` never produces
`missing` — only `ready` or `not_checkable` (research.md D5): the one route
that could ever prove non-installation (the readiness workflow's App-token
mint failing) already stops before `checks.sh` runs at all, unchanged by
this feature.

## AggregateVerdict (new — replaces `ready: bool`)

The single conclusion `assemble_report` derives from every element's
`ElementCheckOutcome` (FR-002), surfaced as `ReadinessReport.verdict` and
as `provision-e2e-target.sh`'s exit status.

| Value | Meaning | Exit status |
|---|---|---|
| `all_clear` | Every required element is `ready`. | `0` |
| `not_clear` | At least one required element is `missing`. | `1` |
| `unverified` | No element is `missing`, but at least one is `not_checkable`. | `2` |

Precedence (FR-003, Edge Cases — "a real failure outranks an unverified
element"): `missing` anywhere → `not_clear`, regardless of how many
elements are `not_checkable`; only when nothing is `missing` does any
`not_checkable` element move the verdict to `unverified`; `all_clear` only
when every element is `ready`. Exit codes are research.md D3's assignment
— `1` reuses this script's existing generic non-verdict failure code (bad
flags, self-refusal, a failed privileged write all already exit `1` before
`assemble_report` ever runs); `2` is a code no other path in this script
emits, so `unverified` is a caller-distinguishable outcome even for a
caller that has always branched on exit status alone (FR-004, SC-008).

## ReadinessReport (amended)

Same top-level entity as 053's `data-model.md`, with the tri-state fields:

| Field | Type | Description |
|---|---|---|
| `target` | string `OWNER/NAME` | Unchanged. |
| `profile` | `TargetProfile.name` | Unchanged. |
| `elements` | list of `{key, outcome: ElementCheckOutcome, remaining_action: string \| null}` | `remaining_action` non-null iff `outcome != "ready"`. For `not_checkable`, `remaining_action` names the route that can check it (FR-005) — the existing wording pattern ("Not checkable with this token... run ... --check-only locally", or `app_installation`'s "...confirm it by dispatching the readiness check..."). |
| `verdict` | `AggregateVerdict` | Replaces `ready: bool`. |
| `generated_at` | ISO-8601 timestamp | Unchanged. |

No field ever carries a credential value (FR-009, unchanged from 053).

This is a breaking change to the JSON shape (`ready` → `outcome`/`verdict`).
Acceptable per research.md D4: this report is part of the consuming
instrument (Constitution VII), and a repository-wide search found exactly
two readers of this shape — `provision-e2e-target.sh` and
`auto-update-spec-kit-scratch-preflight.yml` — both amended in this same
feature. No compatibility field is kept (this repository's own convention
against unread compatibility shims).

## AppInstallationAssertionHint (elevated from spec.md's Key Entities to its own row)

The environment signal (`WC_APP_INSTALLATION_KNOWN_READY`) by which a
caller that has already proved the App installation asserts it rather than
re-checking it (spec.md Key Entities). Unchanged mechanism from 053; this
feature adds:

- **Announcement** (FR-015): whenever `check_app_installation` classifies
  `ready` because of this hint, the human-readable summary
  `provision-e2e-target.sh` prints on stderr names that the hint was
  honoured (research.md D8).
- **Documentation** (FR-016): `docs/setup.md` and `docs/adoption.md` name
  the hint, state that the generalized readiness-check workflow is its
  legitimate setter, and warn that a stray `true` value in a maintainer's
  shell produces a false-`ready` local report for `app_installation`
  specifically (never for any other element — the hint has no effect on
  any other `check_<key>` function).
- Treated as absent for any value other than the exact string `true`
  (Edge Cases) — unchanged from the existing `[ "${WC_APP_INSTALLATION_KNOWN_READY:-}" = "true" ]` comparison.

## ReadinessRoute (elevated from spec.md's Key Entities to its own row)

A way of producing a `ReadinessReport` — spec.md's Key Entities already
names the two: the local entry point under a maintainer's own credential,
and the dispatched readiness check under the App installation token. This
feature makes the route explicitly load-bearing in the data model because
which elements are `not_checkable` is a property of the route, not the
target (Assumptions):

| Route | `app_installation` | `claude_credential` / `container_image_pin` | Reachable verdict on a fully onboarded target |
|---|---|---|---|
| Local (`provision-e2e-target.sh`, no `--check-only` or with it, maintainer credential) | always `not_checkable` (hint never set locally) | checkable (maintainer's own `gh` scope reads secrets/variables directly) | `unverified` at best, for either profile (FR-006) |
| Dispatched (`auto-update-spec-kit-scratch-preflight.yml`, App installation token, always `--check-only`) | `ready` (job already stopped before `checks.sh` runs if the mint — and therefore this proof — failed) | `not_checkable` for `auto-release` (App token has no Secrets/Variables read, docs/setup.md); not applicable for `spec-kit-scratch` (that profile never requires them) | `all_clear` for `spec-kit-scratch`; `unverified` for `auto-release` (SC-001) |

This table is what makes SC-001 concrete: `spec-kit-scratch`'s only
`not_checkable`-capable element (`app_installation`) is the one the
dispatched route CAN check, so that route reaches `all_clear`; every
element `auto-release` adds beyond `spec-kit-scratch` that the dispatched
route cannot check stays `not_checkable` there by the App's unchanged,
narrower permission set (SC-007) — the profile's documented best
attainable verdict, never presented as a failure.

## Relationships (amended)

```text
TargetProfile 1 ── * OnboardingElement        (unchanged, 053)
ReadinessReport 1 ── * elements entry         (one per required OnboardingElement, same order)
ReadinessReport * ── 1 TargetProfile          (the profile evaluated)
elements entry 1 ── 1 ElementCheckOutcome     (new: ready | missing | not_checkable)
ReadinessReport 1 ── 1 AggregateVerdict       (new: all_clear | not_clear | unverified, replaces ready: bool)
OnboardingElement "app_installation" ── DeclaredManualStep   (singleton, remedy = manual, unchanged)
OnboardingElement "app_installation" ── AppInstallationAssertionHint  (the only element this hint affects)
ReadinessReport * ── 1 ReadinessRoute          (new: which caller produced this report — not a report field, but determines which elements can be not_checkable)
```

## State transitions (amended)

053's convergence path is corrected, not replaced (FR-009): there is still
no stored state machine, and the local command still cannot itself observe
an App installation. What changes is what "not yet converged" looks like:

```text
unverified (app_installation not_checkable; every other required element ready)
   │  [dispatch auto-update-spec-kit-scratch-preflight.yml against the same
   │   target — proves app_installation from its own successful App-token
   │   mint, per the ReadinessRoute table above]
   ▼
all_clear (spec-kit-scratch) — or unverified-with-different-elements
   (auto-release, whose claude_credential/container_image_pin stay
   not_checkable to the dispatched route by design, SC-007)
```

A further local re-invocation never changes `app_installation`'s row
(research.md D5, unchanged from 053's T043 finding) — it stays
`not_checkable` regardless of the real install state. This is the behaviour
`quickstart.md` and `docs/setup.md`/`docs/adoption.md` must describe
(FR-009) instead of "converges on a re-run" / "for as long as it is
absent," neither of which is a re-run of the *local* command.
