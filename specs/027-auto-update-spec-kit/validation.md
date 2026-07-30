# Validation record: Auto-Update Spec Kit

This file captures the Polish-phase validation (tasks.md T032/T033) so the
finalize stage can lift it into the version-bump feature PR body and the
transmittal comment on lifecycle issue #153. It is authored by the
implement stage, which opens no PRs and posts no issue comments itself.

## T032 — quickstart.md 15-scenario walk

Every scenario below was **desk-checked** against the finished
`.github/workflows/auto-update-spec-kit.yml` and
`.github/workflows/wing-commander-auto-update-spec-kit.yml` — mapped to the
concrete job/step and `if:` guard that implements it. **None were exercised
live**: this feature has no automated test harness (plan.md), the workflows
call `github/spec-kit`'s real Releases API and open real issues/PRs, and the
headless implement environment has neither the scratch fork nor a deliberately
lowered pinned version those scenarios require. Live exercise (scratch
`workflow_dispatch` runs / a fork with a lowered pin) is left for the
maintainer per the quickstart's own prerequisites.

| # | Scenario | Implemented by | Desk-check result |
|---|---|---|---|
| 1 | No eligible update: no-op | `detect` `compare` step: `newer=false` → summary "up to date", no issue, no PR; `settle` gated `newer == 'true'` | ✅ maps |
| 2 | First detection: watching issue, no same-day adopt | `settle` `count -eq 0` branch: creates issue, marker `observed=1`, "waiting to settle", `settled=false` | ✅ maps |
| 3 | Settling: threshold reached proceeds | `settle` same-candidate branch: `observed >= STABILIZATION_CHECKS` → `settled=true`; else increments and stops | ✅ maps |
| 4 | Superseded candidate resets counter | `settle` `candidate != LATEST` branch: rewrites marker to new candidate, `observed=1`, comments supersession | ✅ maps |
| 5 | Clean bump passes → version-bump PR | `evaluate-path` `clean-bump` → `prepare` → `verify` pass → `act` "Open version-bump PR" (`Closes #N`, marker, PR link comment, never merged) | ✅ maps |
| 6 | Verification fails before adoption | `act` fail branch: branch never pushed, `wing-commander-callout` `kind: info` failure detail, `auto-update:failed` label, issue stays open | ✅ maps |
| 7 | Tiered verification (patch vs minor/major) | `verify`: lightweight always; `end-to-end` step gated `release-type != 'patch'`; worktree discarded, real `specs/` untouched | ✅ maps |
| 8 | Health-check regression → rollback | `health-check` fail sets `pinned-ok=false`; `act` rollback branch computes prior pin from `git log -p`, opens revert PR (no `Closes`), flagged issue naming failed/proposed version + detail | ✅ maps |
| 9 | Lifecycle issue closes itself on merge | Success closes only via the PR's own `Closes #N` (T020, no `gh issue close`); `pr-merged` `version-bump` branch posts the rich summary | ✅ maps |
| 10 | Failed/rolled-back issue stays open + flagged | `act` fail/rollback both apply `auto-update:failed` and never close; `pr-merged` revert branch keeps it open | ✅ maps |
| 11 | Duplicate-attempt guard | `settle` singular-open-issue search; `count -gt 1` reported as data-integrity, never a second issue; `concurrency` group serializes cycles | ✅ maps |
| 12 | Ambiguous path: questions posted, no adoption | `evaluate-path` `ambiguous-options` branch (T023): `kind: action` callout with options/reasoning/sources, marker `awaiting-decision=true`, no `prepare` | ✅ maps |
| 13 | Ambiguous resume from verified maintainer | `comment-reply` job-level actor gate (T024) + `awaiting-decision` guard (T025) + haiku interpret (T026) + resume re-entry (T027); non-maintainer → job skipped, silent | ✅ maps |
| 14 | Clearly-better path decided, reasoning recorded | `evaluate-path` `clean-bump` records reasoning via `kind: info` callout; PR body carries reasoning + sources (FR-013) | ✅ maps |
| 15 | Untrusted content never executed | `evaluate-path` prompt frames release-notes JSON as untrusted data (read-only tools, `WebSearch`/`WebFetch`/`Write`/`Edit`/`git commit`/`git push` disallowed); `comment-reply` interpret step reads the reply from a file, read-only `Read` only, framed as untrusted | ✅ maps — property of prompt framing, no separate code path |

## T033 — maintainer-confirmation items flagged by research.md

Surfaced here (rather than silently assumed) for a maintainer to confirm
before the first live scheduled run:

1. **Regeneration command.** `prepare` regenerates `.specify/` artifacts at
   the candidate version via
   `uvx --from git+https://github.com/github/spec-kit.git@v<CANDIDATE> specify init . --ai claude --script sh --ai-skills --here --force`.
   research.md could not verify from within CI whether upstream Spec Kit
   exposes a **dedicated upgrade/update command distinct from re-running
   `specify init`**. If one exists, `prepare`'s regeneration step should use
   it. The current step fails loudly (`::error::` + non-zero exit) rather than
   silently mis-applying the wrong steps if the assumption is wrong.
2. **Stabilization default.** `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS`
   defaults to `1` (one settled daily check). research.md could not verify
   whether Spec Kit's **release history shows any past breaking upgrade** that
   would justify a longer default. A maintainer who knows the upstream cadence
   should confirm or raise the default via the repository variable.
