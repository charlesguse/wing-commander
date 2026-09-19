# Contract: FR-001, FR-004 (token sites), FR-005, FR-006, FR-007 — the scoped App token mint + reachability check

`research.md` D1/D2 explain the composite-vs-script and call-site-path
choices; `data-model.md`'s "Shared Definition: Scoped App token +
reachability check" table gives the field shape.

## `.github/actions/_shared/scoped-app-token/action.yml` (NEW)

**Inputs**: `app-id`, `private-key` (secrets, passed through, never
defaulted — callers keep owning which App credentials they use),
`owner`, `repo-name` (the target repo, split the way both current call
sites already split it before this feature), `check-default-branch`
(`"true"`/`"false"`, default `"false"`).

**Steps** (mirrors the current two-step shape at both call sites,
collapsed into one composite):
1. `uses: actions/create-github-app-token@v3`, `continue-on-error: true`,
   scoped via `owner`/`repositories: repo-name` — the only step in this
   composite that is a `uses:` step, which is FR-022's stated reason this
   idiom needs composite shape rather than a script.
2. A `shell: bash` step reading the prior step's `.outcome` and
   `.outputs.token`: if the mint failed, set `ok=false`,
   `failure-reason=token-mint-failed`, empty `token`. If it succeeded, run
   `gh repo view "$OWNER/$REPO_NAME"`; if that fails, `ok=false`,
   `failure-reason=unreachable`. If `check-default-branch` is `"true"`,
   additionally require `--json defaultBranchRef` to report a non-empty
   name, publishing it as `default-branch`; a mint that succeeds but a
   repo with no readable default branch is `ok=false`,
   `failure-reason=unreachable` (matching auto-release's current behaviour
   — a reachable-but-branchless repo is not distinguished from an
   unreachable one today, and this feature does not introduce that
   distinction per FR-007's no-regression rule).

**Outputs**: `token`, `ok`, `default-branch` (empty unless requested and
resolved), `failure-reason` (`token-mint-failed` \| `unreachable` \| `""`).

**What this composite does NOT do**: build a remediation message or a
verdict object. FR-005 forbids a parameter no call site varies, and the
two call sites' remediation text and verdict-vs-plain-exit behaviour
differ (auto-release emits a `fail-infra` verdict via
`_shared/auto-release-verdict.sh`; auto-update-spec-kit emits an
`::error::` line and exits 1) — that composition stays at each call site,
reading `failure-reason` to pick its own wording.

## Call site: `auto-release.yml`, `verify-e2e` job

Replaces today's "Mint a scoped App token for the test repository" +
"Confirm the test repository is reachable" steps (lines 166-217) with one
`uses: ./.github/actions/_shared/scoped-app-token` step (`check-default-branch: "true"`),
followed by a short `run:` step that, on `ok != 'true'`, calls
`_shared/auto-release-verdict.sh` with `failing_check`/`expected`/`observed`
text keyed off `failure-reason` (two `if`/`elif` arms, one per
`failure-reason` value — the same two remediation messages the workflow
emits today, unchanged text, per FR-007).

## Call site: `auto-update-spec-kit.yml`, `e2e-stage` job

Replaces today's "Mint a scratch-repository App token" + "Resolve the
scratch repository" steps (lines ~1755-1784) with one
`uses: ./.wing-commander-pipeline/.github/actions/_shared/scoped-app-token`
step (`check-default-branch: "false"`, default), followed by a short
`run:` step that on `ok != 'true'` emits the same two `::error::` messages
this job emits today (unchanged text) and `exit 1`.

## Fallback (FR-006)

If the composite step is skipped or never dispatched (a workflow-level
failure upstream of it), each call site's existing hard-failure path
already covers "no token, no reachability" as an `ok`-less state — no new
fallback code is needed beyond what `ok != 'true'` already handles, since
an un-run composite step simply leaves its outputs empty, which both call
sites' existing `if [ "$OK" != "true" ]` checks already treat as failure.

## Gate coverage

Gate 60 (contracts/single-home-gate.md) fails if a job anywhere outside
this composite contains both a `continue-on-error: true` step invoking
`actions/create-github-app-token@*` and a later step in the same job
reading that step's `.outcome` — the two-clause structural signature of
this idiom, distinct from `wing-commander-context`'s bare token mint
(no reachability re-check follows it).
