# Data Model: Fine-grained maintainer token for the auto-release end-to-end harness

Like specs/055-unattended-e2e-gates' own data model, this feature has no
application database — every entity below is state read from the secret's
own literal value, from GitHub's REST responses, or carried between steps
of the `verify-e2e` job as step outputs. This document extends specs/055's
entities (`specs/055-unattended-e2e-gates/data-model.md`) rather than
replacing them; every field that document already defined keeps its
meaning unless stated otherwise below. It does **not** touch the
end-to-end verdict's JSON shape (unchanged per FR-021 — see
`contracts/credential-precheck.md`).

## Fixture maintainer identity (extends specs/055)

| Field | Source | Notes |
|---|---|---|
| `login` | repository secret `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME` | Unchanged from specs/055. |
| `relationship to the test repository` | — | **Changed by this feature**: owner (after the FR-002 transfer), not invited Write collaborator. Ownership confers Admin on the repository by construction (FR-016); this is accepted for the *account*, and separately bounded for the *credential* (see Maintainer credential, below). |
| `repository set the account can reach` | `gh api user/repos` under the credential | Observed at runtime by the containment check (research.md D3); unchanged mechanism from specs/055, now also correctly generalizes to a fine-grained token's own narrower view. |

## Maintainer credential (extends specs/055; the entity this feature actually changes)

| Field | Source | Notes |
|---|---|---|
| `shape` | the token's own literal prefix (research.md D1) | `classic` (`ghp_...`) or `fine-grained` (`github_pat_...`); a value matching neither is its own `fail-infra` branch, distinct from every shape-specific check below. |
| `repository selection` | implicit, observed via containment (research.md D3) | For `classic`: whatever the account's own memberships produce (specs/055, unchanged). For `fine-grained`: whatever repositories the token was issued against, per its own selection at issuance — never read from a declarative field, always observed as the reachable set. |
| `granted permissions` | probed, not declared (research.md D5/D6) | For `classic`: `viewerPermission` WRITE-or-higher remains the authoritative proof, unchanged from specs/055. For `fine-grained`: `viewerPermission` is downgraded to a reachability check only (it reports the account's ADMIN role post-transfer regardless of the token's own grant); Issues:write and Pull-requests:write are proven by the D6 accept/reject probe, and the *absence* of Administration is proven by the D5 accept/reject probe. |
| `expiry` | `github-authentication-token-expiration` response header (research.md D2), fine-grained only | Absent for `classic` (expiry not observable — proceeds as today). Present for `fine-grained` (mandatory per FR-002); compared against now + `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS` (default 14). |
| `containment` | `gh api user/repos` (research.md D3/D4) | Same invariant for both shapes: the reachable set MUST equal exactly `{WING_COMMANDER_AUTO_RELEASE_E2E_REPO}`. A `gh api` call that itself fails (transport/auth) is now distinguished from a call that succeeds and returns an empty set (research.md D4) — see the precheck outcome table below. |

## Credential precheck outcome (extends specs/055's `fail-infra` verdict; the FR-008 branch table)

One attempt produces exactly one of: a pass, or one `fail-infra` verdict
from the first branch below that fires, in this order. Every `expected` /
`observed` pair is distinguishable text (FR-008); none of the six may
collapse into another.

| # | Failure | Applies to | `expected` names | `observed` distinguishes it as |
|---|---|---|---|---|
| 0 | Malformed credential | both | "a value matching the classic (`ghp_`) or fine-grained (`github_pat_`) token prefix" | "matches neither accepted shape" (research.md D1) — new branch, ahead of every existing one |
| 1 | Secret(s) unset | both | unchanged from specs/055 | unchanged from specs/055 |
| 2 | Rejected/expired credential | both | "the credential authenticates" | "gh rejected the token" (classic: `viewerPermission` call fails; fine-grained: any probe call fails outright rather than returning a permission-denied response) — kept distinguishable from #4/#5 below |
| 3 | Authenticated as a different account | both | "authenticates as `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME`" | unchanged from specs/055 |
| 4 | Insufficient permission on the test repository | both | classic: "Write (or higher) `viewerPermission`" (unchanged); fine-grained: "Issues and Pull-requests write, per research.md D6" | classic: unchanged; fine-grained: the D6 probe was rejected |
| 5 | Grants Administration permission | **fine-grained only** | "no Administration permission on the test repository" | the D5 probe succeeded (FR-016) — never produced for a classic credential (FR-003's stated asymmetry) |
| 6 | Containment could not be established | both | "the credential's reachable-repository set can be observed" | the `gh api user/repos` call itself failed (research.md D4) — distinct from #7 |
| 7 | Containment failed | both | "reaches exactly one repository, the configured test repository" | reached a set other than exactly `{e2e-repo}`, repository names shown with the account's own login redacted (unchanged from specs/055) |

Approaching expiry (research.md D2) is not a failure branch: it is a
report-only note attached to a `pass` outcome, exactly as specs/055 treats
gate evidence — presentation, not a new verdict field (see
`contracts/credential-precheck.md`).

## Canonical statement (new entity — FR-017/FR-018/FR-019/FR-020)

| Field | Value |
|---|---|
| `canonical location` | `docs/setup.md` §2, the `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` secret row |
| `content` | The accepted shape(s) (dual, transitionally — FR-003), each shape's scope/permissions/expiry, the Administration bound (FR-016), the rotation procedure (FR-006), and the two ownership options not taken (FR-020) |
| `pointer sites` | `auto-release.yml`'s credential-step comment block; the precheck's own `expected` text and Gate 67's scenario descriptions (`.github/scripts/verify-auto-release-credential-step.py`); specs/055-unattended-e2e-gates' D1/D2 and Clarifications session (annotated as superseded, FR-019 — never rewritten to read as though the new shape had always been chosen) |
| `enforcement` | the new gate of `contracts/canonical-statement-gate.md` (research.md D7) — distinct from Gate 47, whose declared scope is `.github/workflows/*.yml` comments only |

## End-to-end verdict (UNCHANGED — reference only)

This feature adds no field and no new `outcome` value to the six-field
shape specs/045 defined and specs/055 extended
(`specs/055-unattended-e2e-gates/data-model.md`'s "End-to-end verdict"
section). Every credential-precheck failure in the table above is reported
as `outcome: "fail-infra"`, exactly as every credential failure is today —
only the `failing_check` / `expected` / `observed` text content is new,
never the schema. See `contracts/credential-precheck.md` for the full
mapping.
