# Phase 1 Data Model: Bot Credential Lifetime Across Long Agent Cycles

This feature introduces no new persisted data store. Every shape below is
ephemeral (a job/step output or an environment variable, scoped to the
lifetime of one job run) or a static reference-shape rule a gate checks
against the shipped YAML. `spec-meta.json`'s schema is untouched.

## `WC_BOT_TOKEN` (job-scoped environment variable, new)

| Property | Value |
|---|---|
| Written by | `wing-commander-context`'s new internal relay step, every time the composite runs in a job (both the pre-agent mint and any post-agent refresh) |
| Read by | Every bot-acting step in the job, before or after any agent step — replaces direct reads of `steps.<ctx-id>.outputs.token` |
| Lifetime | One job run. Never written to a file, never exported past the job boundary. |
| Refresh trigger | An `if: always()` step immediately after each agent step, re-invoking `wing-commander-context` |
| Scope | Every one of the 8 sweep-stage workflows' jobs that call `wing-commander-context` and run at least one agent step |

## `WC_SCRATCH_TOKEN` (job-scoped environment variable, new — `auto-update-spec-kit.yml`'s `e2e-stage` job only)

Same shape as `WC_BOT_TOKEN` (research.md D8), relayed from
`steps.scratch-token.outputs.token` instead of `wing-commander-context`'s
output — a structurally identical but independently-scoped credential,
authenticating against the disposable scratch repository rather than this
repository's own installation.

## Authenticated git remote (refreshed, not newly modeled)

| Property | Value |
|---|---|
| Established by | `actions/checkout@v5`'s `token:` input on the "Checkout spec branch as wing-commander-bot" step (pre-agent, unchanged) |
| Refreshed by | Clearing the stale `http.https://github.com/.extraheader` config entry `actions/checkout@v5` wrote (the header, not the remote URL, is what git's http transport actually authenticates with), then `git remote set-url origin https://x-access-token:${WC_BOT_TOKEN}@github.com/${{ github.repository }}.git` — both in the same post-agent refresh step that rewrites `WC_BOT_TOKEN` (research.md D2, corrected in this feature's own T046 code review) |
| Consumers relying on it implicitly | `.github/actions/_shared/read-spec-meta.sh`'s bare `git fetch origin`, and any other composite that shells out to `git` rather than taking a `token:` input |

## Agent-ran signal (new — one per job containing an agent step)

| Field | Type | Meaning |
|---|---|---|
| `agent-ran` (job output) | `"true"` \| unset | Set by an `if: always()` step immediately after each agent step in the job, before the credential refresh (research.md D3). Unset only when the job never reached any agent step. For a job with more than one agent step (`implement.yml`), each agent step's signal step overwrites the prior value — the job output always reflects the most recent agent step reached. |
| `agent-conclusion` (job output) | `"success"` \| `"failure"` \| `"cancelled"` | Mirrors `steps.<agent-id>.conclusion` for whichever agent step most recently ran. Never `"skipped"` — this signal step only executes (and only overwrites) once an agent step exists to report on. |

No prose field. FR-014 is unconditional; the diagnostics artifact each
stage's stall path already downloads remains the sole carrier of
model-authored text.

**Publication scope** (research.md D4): published in all 8 sweep stages
(FR-010, FR-026). **Consumption scope**: read by the stall path in the 6
stages that already have a `stalled`/survivor job today —
`implement`, `finalize`, `clarify`, `intake`, `pr-conversation`, `tasks`
(`generate` and `approved`). `plan.yml` and `auto-update-spec-kit.yml`
publish the signal with no reader (cheap, harmless, FR-006-compliant — a
`$GITHUB_OUTPUT` write costs no agent turn).

## Stall-path consumption (amended — the six stages of research.md D4)

| Existing input | New input | Effect |
|---|---|---|
| `needs.<entry-job>.result` / `.outputs.final-ok` (implement only) — decides whether the survivor job's abnormal-termination arm fires at all (spec 041, unchanged) | `needs.<entry-job>.outputs.agent-ran` / `.outputs.agent-conclusion` | Inside the abnormal-termination arm's existing "Determine which dependency did not start" step: when `agent-ran == 'true'`, the reason becomes "the agent step ran (concluded: `<agent-conclusion>`) and a step after it failed" instead of "the implement stage failed before it could run its own steps"; the chain-stop notice's rendered body drops the "No implementation attempt was made" sentence for this case and instead names the post-agent region as where the run stopped. When `agent-ran` is unset, today's diagnosis and wording are produced unchanged (FR-012). |
| Lifecycle record (`spec-meta.json` `stage` field, marked `"stalled"` unconditionally by the existing composite) | same field, unchanged schema | When `agent-ran == 'true'`, the record-mark step's accompanying restart-guidance text (already caller-rendered per stage, spec 041 D7/`wing-commander-chain-stop-notice`'s `restart-command` input) is passed a resume-oriented sentence instead of a restart-from-zero one — FR-015. No new field on the record itself; the distinction lives entirely in the rendered notice text, mirroring how spec 041 already renders two different bodies (`marked` / `unwritable`) from one `record-status` flag without a schema change. |

## Declared-observability step population (data, not schema — research.md D5)

The 12 call sites of the "Report over-budget agent run" step family, one
per stage/branch, each gaining `continue-on-error: true`:

| Stage | File:line (pre-change) |
|---|---|
| clarify (canonical) | `clarify.yml:928` |
| intake | `intake.yml:1169` |
| implement — cycle | `implement.yml:1010` |
| implement — retry | `implement.yml:1525` |
| implement — progress | `implement.yml:2047` |
| finalize | `finalize.yml:785` |
| tasks — auto | `tasks.yml:1096` |
| tasks — pr | `tasks.yml:1111` |
| plan — auto | `plan.yml:1125` |
| plan — pr | `plan.yml:1140` |
| pr-conversation — classify-and-announce | `pr-conversation.yml:1042` |
| pr-conversation — act | `pr-conversation.yml:2141` |

`auto-update-spec-kit.yml`'s `e2e-stage` has no matching step (confirmed by
inspection — it goes straight from its agent step to an already-tolerant
verdict check), so it contributes zero rows here; it is still in FR-007's
eight for the credential-relay requirement (D1/D8), just not for this
table. Line numbers are pre-change references for reviewers checking out
`main`; the gate (contracts/post-agent-credential-refresh-gate.md) locates
these steps by name pattern, not by line number, so it does not drift when
the file is edited.

## Gate registry entry (new)

| Gate | Script | Wired into | Proves |
|---|---|---|---|
| 68 (renumbered from the provisional 67 — #401 took 67 first) | `.github/scripts/verify-post-agent-credential-refresh.py` | `.github/workflows/lint-workflows.yml`, PR-time job (picked up automatically by `wc_gate_registry.py`'s filename convention) | FR-020 (no stale credential reference, no un-refreshed second agent step), FR-021 (every declared-observability step in the audited region is tolerated), FR-022 (reachable through the registry, same subject/arguments locally and in CI, fails loudly on an unreachable subject), FR-023 (every failure branch fixture-covered) |
| 69 (added in this feature's own T046 code review) | `.github/scripts/verify-credential-relay-shell.py` | `.github/workflows/lint-workflows.yml`, PR-time job | Behavioral proof that Gate 68 cannot provide statically: the relay's `$GITHUB_ENV` precedence (research.md D1) and that the post-agent remote refresh actually clears the stale `actions/checkout@v5` extraheader rather than leaving a no-op URL rewrite (research.md D2's correction) |

See `contracts/post-agent-credential-refresh-gate.md` for the check's exact
structure and required mutations.
