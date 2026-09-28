# Contract: the "Confirm the fixture maintainer identity's credential" step accepts two shapes, and the verdict schema is unchanged

This contract extends `auto-release.yml`'s existing "Confirm the fixture
maintainer identity's credential" step (specs/055-unattended-e2e-gates D2,
Gate 67) rather than replacing it. Its inputs, outputs, and the shared
`auto-release-verdict.sh` helper it calls are unchanged in shape from
specs/055; only the step's internal branching changes.

## Inputs (UNCHANGED)

| Env | Source | Notes |
|---|---|---|
| `MAINTAINER_TOKEN` | `secrets.WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` | Now may hold either accepted shape (research.md D1). |
| `MAINTAINER_USERNAME` | `secrets.WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME` | Unchanged. |
| `E2E_REPO` | `steps.config.outputs.e2e-repo` | Unchanged. |
| `HEAD_SHA`, `MODE` | unchanged | Unchanged. |

## Outputs (UNCHANGED SHAPE)

| Output | Values | Notes |
|---|---|---|
| `ok` | `"true"` / `"false"` | Unchanged. |
| `verdict` | `auto-release-verdict.sh`'s six-field JSON, or absent on `ok=true` | Unchanged shape; new `expected`/`observed` text content per the branch table below. Never contains the credential or the unredacted login (FR-009 — Gate 67's existing invariant, extended to every new branch). |

No new output is added. The `report` job's classification logic and the
durable failure-issue body-building logic are both untouched by this
feature (FR-021) — every branch below still reports as `fail-infra`,
exactly as every credential failure does today.

## Step body — decision order

```text
1. Strip whitespace from MAINTAINER_USERNAME (unchanged, specs/055 #396 review)
2. If MAINTAINER_TOKEN unset -> fail-infra (unchanged, table row #1)
3. If MAINTAINER_USERNAME unset -> fail-infra (unchanged, table row #1)
4. shape := classify(MAINTAINER_TOKEN)   # research.md D1, prefix match only
   if shape not in {classic, fine-grained} -> fail-infra (table row #0, NEW)
5. if shape == classic:
     -- every following check is BYTE-IDENTICAL to specs/055 D2/today's step --
     a. viewerPermission WRITE-or-higher, else fail-infra (table row #2/#4)
     b. gh api user --jq .login matches MAINTAINER_USERNAME, else fail-infra (table row #2/#3)
     c. containment: reachable set == {E2E_REPO}, else fail-infra (table rows #6/#7, research.md D4 fix applies to BOTH shapes)
6. if shape == fine-grained:
     a. any probe call transport-fails outright -> fail-infra (table row #2)
     b. gh api user --jq .login matches MAINTAINER_USERNAME, else fail-infra (table row #3)
        (viewerPermission is READ ONLY here, as a reachability check -- research.md D6;
        its value is never used as a permission proof for this shape)
     c. D6 probe: Issues:write AND Contents:write both accepted, else fail-infra (table row #4)
     d. D5 probe: Administration REJECTED, else fail-infra (table row #5, FR-016)
     e. containment: reachable set == {E2E_REPO}, else fail-infra (table rows #6/#7, same check as 5c)
     f. D2: if github-authentication-token-expiration header present and already
        past -> fail-infra (table row #2, "rejected/expired"); if within the
        warning window -> proceed, note recorded for the report (not a verdict field)
7. ok=true
```

Row numbers refer to `data-model.md`'s Credential precheck outcome table.
Steps 5 and 6 are mutually exclusive branches of the same step, not two
steps — `auto-release.yml`'s `outputs:` wiring for this job
(`steps.maintainer-credential.outputs.*`) does not change.

## Fine-grained-only probes (research.md D5/D6) — exact call shape

| Probe | Call | Accepted (fails precheck) | Rejected (passes this probe) |
|---|---|---|---|
| Administration absence (D5) | `GET /repos/{owner}/{repo}/actions/permissions` | 200 — token grants Administration | 403 naming the missing permission |
| Issues write (D6) | `POST /repos/{owner}/{repo}/issues/999999999/comments` | 404 (permission present, resource absent) | 403 (permission absent, checked before lookup) |
| Contents write (D6) | `PUT /repos/{owner}/{repo}/pulls/999999999/merge` | 404 | 403 |

Every probe is read-only or targets a resource that cannot exist; none
creates, modifies, or deletes anything in the test repository. The merge
attempt is gated by GitHub on Contents:write, not Pull-requests:write
(maintainer feedback on #506), so its rejection is reported naming
Contents.

## Fixture coverage obligation (FR-015, Constitution VIII)

Every row of `data-model.md`'s Credential precheck outcome table — all
eight, not just the six specs/055 shipped — MUST have a scenario in the
extended `verify-auto-release-credential-step.py` (Gate 67), with a stubbed
`gh` covering both the classic and fine-grained shapes, and MUST have at
least one mutation that breaks that scenario's assertion, per the existing
gate's own pattern (`mut_raw_repository_names`, `mut_no_username_guard`,
etc.). The `github-authentication-token-expiration` header and the two new
probe response codes are all supplied by the stub, matching Gate 67's
existing "no network call, ever" property.
