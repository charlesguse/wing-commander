# Data Model: Single home for the auto-release / auto-update shared idioms

This feature has no runtime data store. "Entities" here are the shared
GitHub Actions artifacts (composite actions, a script, a gate, a waiver
file) and the call sites that consume them — the shapes a later
tasks/implement stage will build against. Field names match spec.md's Key
Entities section; sources are the concrete files/lines gathered in
research.md and the plan-stage exploration.

## Shared Definition: Scoped App token + reachability check

`.github/actions/_shared/scoped-app-token/action.yml`

| Field | Type | Notes |
|---|---|---|
| `app-id` (input) | secret string | passed through, not defaulted (caller's own App credentials) |
| `private-key` (input) | secret string | passed through |
| `owner` (input) | string | target repo's owner |
| `repo-name` (input) | string | target repo's name |
| `head-sha` / context (input) | string, optional | only auto-release's verdict-emitting caller needs this; the action itself does not require it — see below |
| `token` (output) | string | empty if mint failed |
| `ok` (output) | `"true"`/`"false"` | reachability result |
| `default-branch` (output) | string, optional | only populated when `check-default-branch: true` is passed (auto-release needs it; auto-update-spec-kit does not) |
| `failure-reason` (output) | string, one of `token-mint-failed` \| `unreachable` \| `""` | lets each caller compose its own remediation message/verdict — the action does not build a verdict object itself (D3: verdict-building stays out of this idiom's scope; only `auto-release.yml` has a verdict shape at all) |

**Call sites**: `auto-release.yml` `verify-e2e` job (mint+reachable steps,
today lines 166-217, `check-default-branch: true`);
`auto-update-spec-kit.yml` `e2e-stage` job (scratch-token+scratch-repo
steps, today lines ~1755-1784, `check-default-branch: false`).

**Fallback**: if the composite step itself never ran (e.g. skipped job),
each call site's existing one-line fallback is its current hard failure
path (auto-release: emit a `fail-infra` verdict via
`_shared/auto-release-verdict.sh` with `failing_check: "shared token-mint
action did not run"`; auto-update-spec-kit: `::error::` + `exit 1`) — no
second implementation of the mint/reachability logic.

## Shared Definition: Orphan-branch force-reset

`.github/actions/_shared/orphan-branch-reset/action.yml`

| Field | Type | Notes |
|---|---|---|
| `token` (input) | secret string | the already-minted, already-verified token for the target repo |
| `repo` (input) | string | `owner/name` |
| `branch` (input) | string | branch to reset — the target repo's default branch (auto-release) or a deterministic side branch (auto-update-spec-kit) |
| `bot-name` (input) | string | commit identity, e.g. `wing-commander-auto-release[bot]` or `${{ steps.ctx.outputs.bot-slug }}[bot]` |
| `bot-email` (input) | string | matching `[bot]@users.noreply.github.com` address |
| `workdir` (input) | string | local clone directory name, caller-chosen so two callers in one job never collide |
| `commit-message` (input) | string | the one empty/placeholder commit each caller makes immediately after the reset |
| `ok` (output) | `"true"`/`"false"` | |
| `failure-stage` (output) | string, one of `clone` \| `push` \| `""` | lets each caller compose its own remediation, matching D3's approach of not baking a verdict shape into a definition only one caller needs |

**Call sites**: `auto-release.yml` `verify-e2e` job, "reset" step (today
lines 227-294) — note the "close prior leftovers" issue/PR cleanup
immediately preceding this in the same step stays *outside* the composite,
since it is not part of the reset idiom itself (spec.md's idiom
description covers only detach→orphan→push, not repo-wide issue/PR
cleanup); `auto-update-spec-kit.yml` `e2e-stage` job, "Scaffold and
force-push" step's reset portion (today lines 1815-1850) — the
`uvx specify init` scaffolding and commit-with-real-content that follow
stay at the call site, since only the *reset* (through the first empty
commit) is the shared idiom; each caller pushes its own real content in
its own subsequent step.

**Fallback**: caller's own current hard-fail path if the action step
didn't run — a `set -e`-style `exit 1`/verdict emission naming the reset as
the failure point, never a re-implemented `checkout --orphan` sequence.

## Shared Definition: Durable failure issue

`.github/actions/_shared/durable-failure-issue/action.yml`

| Field | Type | Notes |
|---|---|---|
| `token` (input) | secret string | usually the shared context token; `GITHUB_REPOSITORY`-scoped, never the second repo's token |
| `operation` (input) | `report` \| `close` | selects the two halves of the idiom (D4) |
| `label` (input) | string | e.g. `auto-release:failed`, `auto-update:failed` |
| `label-color` (input) | string | hex, no `#` (matches `gh label create --color` today) |
| `label-description` (input) | string | |
| `title` (input) | string, `report` only | |
| `body-file` (input) | path, `report` only | caller writes its own body to a temp file first (matches today's pattern at every hand-rolled site) — no `body:` string input, to avoid a second body-templating surface competing with `wing-commander-callout` |
| `close-comment` (input) | string, `close` only | |
| `issue-number` (output) | string, may be empty | the found-or-created (report) / found-or-none (close) issue |
| `action-taken` (output) | `commented` \| `created` \| `closed` \| `none` | lets the caller's own step-summary line stay accurate without re-deriving what happened |

**Call sites — report**: `auto-release.yml` `report` job's three sites
(verification failed, version collision, release dispatch failed — today
lines 810-876); `auto-update-spec-kit.yml`'s four sites (rollback/health-check
failed, verification failed, prepare failed, revert-merged summary — today
lines 2542-2622, 2774-2799, 2811-2851, 2972-2991). Comment-body rendering
via `wing-commander-callout` (2 of the 4 auto-update-spec-kit sites, per
D6) is unaffected; the file each such site hands to `--body-file` is
whatever `wing-commander-callout` or the site's own heredoc already
produces.

**Call sites — close**: `auto-release.yml` `report` job's success path
(today lines 848-852) only. `auto-update-spec-kit.yml` makes no `close`
call (D5 — deliberate, not an oversight).

**Fallback**: caller's own current inline `gh issue create`/`gh issue
comment` degrades to a one-line `::warning::` noting the shared definition
did not run, never a re-declared `file_or_update_failure`/
`close_failure_on_success` shell function.

## Internal helper (not cross-workflow, not under FR-022): fail-infra verdict

`.github/actions/_shared/auto-release-verdict.sh`

| Field | Type | Notes |
|---|---|---|
| `outcome` (arg) | string | `pass` \| `fail-infra` \| `fail-pipeline-defect` (whatever the existing outcome vocabulary is at each site — unchanged by this feature) |
| `head` (arg) | string | commit SHA |
| `failing_check` (arg) | string, may be empty → JSON `null` | matches today's `write_verdict`'s empty-to-null coercion |
| `expected` (arg) | string, may be empty → JSON `null` | |
| `observed` (arg) | string, may be empty → JSON `null` | |
| `evidence_url` (arg) | string | |
| stdout | one-line JSON | `{outcome, verified_head, failing_check, expected, observed, evidence_url}` — byte-identical to today's `write_verdict` output for the same inputs (FR-009) |

**Call sites**: all 14 sites listed in research.md D3 (`config`×3,
`reachable`×2 — now delegated to the composite's own `failure-reason`
output feeding this script, `reset`×2 — same, `speckit-version`×1,
`scaffold`×3, `kickoff`×2, `report`'s defensive fallback×1). Each keeps its
own `echo 'verdict<<AUTO_RELEASE_VERDICT_EOF' ... EOF` `GITHUB_OUTPUT`
framing; only the `jq -n '{...}'` line is replaced by a call to this
script.

**Byte-identity test (FR-009)**: a fixture in the gate's self-test (or a
small standalone script test) calls the shipped script with each of the 14
sites' actual current literal inputs and diffs the output against the
current tree's own `jq -n` output for the same inputs, captured once before
the refactor.

## Single-home gate

`.github/scripts/verify-single-home-idioms.py` (Gate 52)

| Field | Type | Notes |
|---|---|---|
| subject | `.github/workflows/*.yml`, `.github/actions/**` | everything under both trees, per FR-010 |
| checks | 4 | orphan-reset fragment co-occurrence; failure-issue fragment co-occurrence; verdict-shape field-name co-occurrence; token-mint structural signature (continue-on-error `create-github-app-token` step + later `.outcome` read in the same job) |
| declared homes | 4 paths | the three composites' `action.yml` paths + `auto-release-verdict.sh`'s path — excluded from their own checks |
| promotion check | separate pass | published stages (via `wc_published_stages.py`) and non-underscore composites scanned for any `_shared/` reference (FR-025) |
| waiver file | `.github/scripts/single-home-waivers.json` | see below |
| failure message | string | names the offending `file:line` and the shared definition's path, per FR-011 |
| self-test | `--self-test` flag | synthetic fixtures (Gate 47 style) for each of the 4 checks + the promotion check + each waiver-shape failure mode, since none of the real, checked-in call sites can safely be *mutated* in place to prove the gate catches a regression the way Gate 47's synthetic tempdir fixtures do |

## Waiver

`.github/scripts/single-home-waivers.json` — schema identical to
`.github/scripts/stage-invariant-waivers.json` (Gate 31's waiver file):

| Field | Type | Notes |
|---|---|---|
| `file` | string | repo-relative path of the waived site |
| `check` | string | one of the gate's check names (`token-mint`, `orphan-reset`, `failure-issue`, `verdict-shape`, `promotion`) |
| `pattern` | regex string | what within that file the waiver covers — narrow enough that a wider recurrence still fails |
| `count` | int | expected number of matches; stale-checked both directions (0 matches → fail, "reason no longer applies"; more matches → fail, "wider than granted") |
| `issue` | string | tracking issue, e.g. `#326` |
| `reason` | string | why this site cannot call the shared definition |

No waivers are expected to exist at merge time for this feature (SC-009: a
waiver's absence is not itself checked, only that any that do exist are
discoverable in this one file) — the file is created with an empty
`"waivers": []` list and the `$comment` block explaining the mechanism,
mirroring `stage-invariant-waivers.json`'s own header.

## Records corrected (not new entities, existing artifacts)

| Record | Current state | Corrected state |
|---|---|---|
| `docs/architecture.md` | no `auto-release.yml` section (0 hits repo-wide) | new `## Auto-Release` H2 section, positioned after `## Private-image dogfood` (line 1079-1103 today) and before `## Reusability` (line 1105 today), matching that section's depth (Trigger paragraph + one prose block, no bullet list, no bold run-in subsections) |
| `specs/045-auto-release-verified-head/tasks.md` T023 (line 199) | claims the `shell_exempt` array was/should-be updated | records that no `shell_exempt` registration exists or is needed, because `auto-release.yml` is never derived as a published stage (`wc_published_stages.py`) and Gate 48's closure check therefore never forces it into `SHELL_LINTED` or `SHELL_EXEMPT` |
| PR #317 body (spec 045's finalize narrative, `<!-- wing-commander-finalize:narrative:begin -->` block) | claims "all gate suite checks passing" and a `shell_exempt` registration that was never made | states CI on #317 failed Gate 12 then Gate 15 before going green, and that no `release.yml`/Gate 1a change was made or was required |
