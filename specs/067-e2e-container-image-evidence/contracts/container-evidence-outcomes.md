# Contract: Container-Mode Evidence Outcomes

Extends `specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md`
§2 (the verdict JSON shape) and follows the precedent
`specs/055-unattended-e2e-gates/contracts/verdict-extension.md` set: no new
field, new values within `failing_check`. Supersedes §1's "Unset behavior"
accepted-gap language (FR-016).

## 1. When these checks run

| Check | Runs when | Gated on |
|---|---|---|
| Configuration evidence | `mode == container` | `steps.maintainer-credential.outputs.ok == 'true'`, before `cleanup`/`scaffold`/`kickoff` |
| Execution evidence | `mode == container` and the `poll` step's loop reaches a terminal, non-chain-stop state | Immediately before the single `pass`-writing `write_verdict` call |

Neither check runs, and neither is required, on a `default-runner` turn
(FR-008) or while the container leg's kill switch
(`WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED`) is set (FR-017) — the
existing mode-derivation step already forces `default-runner` in that case,
so no new condition is needed for the pause path.

## 2. `failing_check` vocabulary this feature adds

All rows below use `outcome: fail-infra` and `container_image_configured:
false`, consistent with the existing verdict shape's other infrastructure-
class failures.

| FR-005 case | `failing_check` (exact string, for `report`'s classification and SC-005) | `expected` | `observed` |
|---|---|---|---|
| (i) never configured | `container image not configured on the test repository` | This repository's pinned image reference | `(unset)` or `(empty)` |
| (ii) drift | `container image configured but does not match this repository's pin` | This repository's pinned image reference | The test repository's differing value |
| (iii) configured but unpullable/unauthorized | *(unchanged — existing chain-stop-notice detection, `auto-release.yml` ~lines 1091–1113)* | *(unchanged)* | *(unchanged)* |
| (iv) configured but not executed in a container | `container image configured but stage jobs did not execute inside a container` | The stage jobs expected to run containerized | The stage job name(s) observed without container initialization |
| (v) evidence unreadable | `container-mode evidence unreadable` | A successful read of the named evidence source | The read failure (credential unset / access insufficient / read refused) |
| (v, rate-limited variant) | `container-mode evidence rate-limited` | A successful read of the named evidence source | The rate-limit condition observed, distinct from a hard read failure (US2 AC2) |
| (vi) configured and exercised | *(existing `pass` path — no `failing_check`)* | — | Both evidence observations, per data-model.md |

Case (iii) is explicitly unchanged (FR-005's last sentence): this feature
adds cases in front of it, per spec Assumptions, never reclassifies it.

## 3. Fail-closed guarantee

Every branch in §2 except (vi) MUST be reached, and MUST NOT reach `pass`,
under each of these conditions (FR-004, US2):

- The evidence source is unreachable (credential unset, access revoked,
  insufficient permission).
- The read is refused by a transient condition (rate limit, transient API
  error) — distinct `failing_check` from a hard read failure, never
  reported as "not configured."
- This repository's own pin is unreadable at comparison time — fails
  closed, never compared as if empty (FR-007's last sentence).

## 4. Report readability (FR-010, SC-005)

The run's report MUST let a maintainer distinguish all six named outcomes
without opening the test repository, using exactly the fields the existing
verdict already carries: `failing_check` names which check failed,
`expected`/`observed` state what was expected and what was seen, and
`evidence_url` names where it was read (the test repository's variable
page for the configuration cases, the run's Jobs API / Actions UI for the
execution case).

## 5. Cross-reference to `specs/054`

`specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md` §1's
"Unset behavior" accepted-gap paragraph is replaced (FR-016) with a pointer
to this contract; its §2 verdict JSON shape is unchanged by this feature
and needs no edit.
