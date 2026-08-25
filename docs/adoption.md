# Adopting the Wing Commander pipeline

The pipeline's eight stages are published from this repository as reusable
`workflow_call` workflows (`.github/workflows/<stage>.yml`), versioned by
release tags. You adopt them **by reference**: your repository keeps thin
wrapper workflows that own the triggers, gates, and configuration, and call
the published stages with your credentials. You never copy stage logic, and a
version bump on your side picks up fixes.

Any subset works — adopt the full lifecycle below, or wire a single stage to
any trigger you like (see the [stage reference](#stage-reference)). No stage
requires this repository's label taxonomy, branch gate sequence, or sibling
stages to exist.

This repository is its own first adopter: its `wing-commander-*.yml` workflows are
exactly the thin wrappers described here, calling the same stages by local
path. When in doubt, read them — they are the living example.

## Prerequisites

1. **Your own spec-kit artifacts.** Run
   [`specify init`](https://github.com/github/spec-kit) in your repository
   (pin **the spec-kit version this pipeline supports** — read
   `SPECKIT_SUPPORTED_VERSION` from `.github/actions/wing-commander-preflight/action.yml`
   at the tag you adopt; use
   `--integration claude --script sh`), then write your constitution with
   `/speckit-constitution`. The pipeline reads `.specify/`,
   `.claude/skills/speckit-*`, and `specs/` **only from your repository's
   checkout** — it never bundles or substitutes its own. Stages fail fast
   with guidance if these are missing.
2. **A dedicated GitHub App** installed on your repository, with Contents,
   Issues, and Pull requests read/write — one-time setup, walkthrough in
   [docs/setup.md](setup.md#1-create-the-wing-commander-bot-github-app). Store its
   ID and private key as the `WING_COMMANDER_APP_ID` /
   `WING_COMMANDER_APP_PRIVATE_KEY` secrets.
3. **A Claude credential** from *your* plan — see
   [Credentials](#credentials). Exactly one is sufficient.
4. **Labels** for the full-lifecycle flow (only `spec-request` is needed for
   the gate; the script in [docs/setup.md](setup.md#4-labels) creates the
   rest).
5. **Access to the pipeline repository.** Reusable workflows and the stages'
   composite-action self-checkout both require that the pipeline repository
   is accessible to your repository. `charlesguse/wing-commander` is
   **public**, so this is automatic — no extra setup. Only if you pin a
   **private** fork/republish instead does the one-time setup in
   [Private pipeline repository](#private-pipeline-repository) apply; forks
   that republish under another name also set the `pipeline-repo` input.

## Credentials

Every agent-running stage declares two **optional** secrets; configure at
least one:

| Secret (stage interface name) | Where it comes from | Plan type |
|---|---|---|
| `claude-code-oauth-token` | Run `claude setup-token` locally and paste the result | Claude subscription (Pro/Max/Team/Enterprise) |
| `anthropic-api-key` | [Claude Console](https://console.anthropic.com/) → API keys | Metered API billing |

Rules:

- **Neither configured** → the stage fails deterministically in its preflight
  step, before any agent work (zero agent cost), with exactly this guidance:

  > No Claude credential configured. Add one of these repository secrets and
  > pass it to the stage: `claude-code-oauth-token` (from
  > `claude setup-token`, subscription plans) or `anthropic-api-key` (from
  > the Claude Console). Exactly one is sufficient. See
  > docs/adoption.md#credentials.

- **Both configured** → *the API key is used.* The pipeline passes both
  through to `anthropics/claude-code-action` and adds no selection logic of
  its own; Claude Code's documented
  [authentication precedence](https://code.claude.com/docs/en/authentication#authentication-precedence)
  applies, in which `ANTHROPIC_API_KEY` outranks `CLAUDE_CODE_OAUTH_TOKEN`.
- No validity probe is performed — an expired/invalid credential fails at the
  first agent call, still before any successful billable work.

Your repository-side secret names are your choice; the wrappers map them:

```yaml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

Leave either line out (or the secret unset) if you only use one.

### AWS Bedrock

To run the agent steps against **AWS Bedrock** instead of the Anthropic API,
every agent-running stage accepts three optional `workflow_call` inputs (set
in your wrapper's `with:` block, not as repository secrets):

| Input | Type | Default | Purpose |
|---|---|---|---|
| `use-bedrock` | boolean | `false` | Route this stage's agent step through Bedrock. Off by default — leaving it unset is a zero-change no-op for existing Anthropic adopters. |
| `aws-role-arn` | string | `""` | IAM role ARN the stage assumes via OIDC. **Required** when `use-bedrock: true`. |
| `aws-region` | string | `""` | AWS region for both credential configuration and the Bedrock endpoint. **Required** when `use-bedrock: true`. |

Rules:

- **Credentials are assumed via OIDC inside each stage job** — the stage calls
  `aws-actions/configure-aws-credentials` with `role-to-assume:
  ${{ inputs.aws-role-arn }}` and no long-lived AWS secrets (no access-key /
  secret-key inputs exist). Your `aws-role-arn` must trust GitHub's OIDC
  provider for this repository.
- **No new permission grant.** The stage jobs already request
  `id-token: write` for the pipeline-ref OIDC resolution every stage uses;
  enabling Bedrock reuses that same grant and adds nothing.
- **Both `use-bedrock: true` and an Anthropic credential configured** →
  *Bedrock is used, regardless.* Setting `use-bedrock: true` selects Bedrock
  whether or not an Anthropic credential is also present; the Anthropic
  credentials are still passed through unconditionally, and upstream Claude
  Code's own provider precedence honors the Bedrock flag.
- **Preflight** requires `aws-role-arn` and `aws-region` (naming whichever is
  missing) when `use-bedrock: true`, and skips the Anthropic-credential check
  in that case — still deterministically, before any agent cost.
- **Models are pure pass-through.** Supply Bedrock-compatible model
  identifiers through the existing per-stage `model` inputs (constitution II
  tiering) exactly as you would Anthropic model names — the pipeline performs
  no translation or mapping.

```yaml
    with:
      use-bedrock: true
      aws-role-arn: arn:aws:iam::123456789012:role/wing-commander-bedrock
      aws-region: us-east-1
      # model inputs carry Bedrock-compatible identifiers directly
```

## Wrapper security obligations

The published stages carry the pipeline's internal security posture
(untrusted-content prompt framing, least-privilege agent tool allowlists, no
web tools, trusted-ref checkouts). What they **cannot** carry is your
trigger-side gating — the wrapper owns the trigger, so the wrapper owns these
gates. The examples below include them; keep them when you customize:

- **Maintainer-label entry gate before intake** — only a maintainer-applied
  label (e.g. `spec-request`) admits an issue into the pipeline. Issue text
  is user data, never an instruction to run anything.
- **Commenter gate before clarify** — react only when the commenter is a
  maintainer (`OWNER`/`MEMBER`/`COLLABORATOR`) or the original issue author,
  and never a bot.
- **Never pass fork-PR head refs** as checkout targets or slugs. The
  full-lifecycle triggers below only fire on same-repo pipeline branches.
- **Bot-actor loop guard on rebase** — skip runs triggered by your App's own
  pushes.

## The minimal full-pipeline wrapper set

Copy these eight files into `.github/workflows/` of your repository. They are
pinned to the floating major tag `@v2` (see
[Version pinning](#version-pinning)); adopters still on `@v1` should read
[Migrating to `@v2`](#migrating-to-v2) — the `v1` snippets differ in both
filenames and secret names. Replace `main` in the `branches:` filters if your default
branch is named differently — the *stages* never assume a name, but your
triggers are yours.

> The implement and finalize wrappers are **dispatch targets**: earlier
> stages chain to them via `gh workflow run` with the payload inputs
> (`spec_dir`, `issue`, `iteration`/`converged`) shown verbatim below. Keep
> those `workflow_dispatch` input names exactly as written — they are part of
> the published chaining contract.

### 1. `wing-commander-1-intake.yml`

```yaml
name: "Wing Commander · 1 intake"

on:
  issues:
    types: [labeled]

permissions: {}

jobs:
  intake:
    # Security gate: only the maintainer-applied approval label starts intake.
    if: github.event.label.name == 'spec-request'
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/intake.yml@v2
    with:
      issue-number: ${{ github.event.issue.number }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 2. `wing-commander-2-clarify.yml`

```yaml
name: "Wing Commander · 2 clarify"

on:
  issue_comment:
    types: [created]

permissions: {}

jobs:
  clarify:
    # Security gates, all must hold: a real issue in the spec-drafting stage,
    # owned by the pipeline, and a human commenter who is a maintainer or the
    # original requester.
    if: >-
      !github.event.issue.pull_request &&
      contains(join(github.event.issue.labels.*.name, ','), 'spec:') &&
      (contains(github.event.issue.labels.*.name, 'stage:spec') || contains(github.event.issue.labels.*.name, 'stage:clarify')) &&
      github.event.comment.user.type != 'Bot' &&
      (contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) || github.event.comment.user.id == github.event.issue.user.id)
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/clarify.yml@v2
    with:
      issue-number: ${{ github.event.issue.number }}
      comment-id: ${{ github.event.comment.id }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 3. `wing-commander-3-plan.yml`

```yaml
name: "Wing Commander · 3 plan"

on:
  pull_request:
    types: [closed]
    paths: ["specs/**"]
  workflow_dispatch:
    inputs:
      slug:
        description: "Spec slug (NNN-name) to (re)start planning for"
        required: true
        type: string

permissions: {}

jobs:
  plan:
    # Gate: a draft spec PR merged into the default branch, or a manual
    # restart. The head-prefix guard prevents unrelated PRs touching specs/**
    # from false-triggering.
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.pull_request.merged == true &&
       github.event.pull_request.base.ref == 'main' &&
       startsWith(github.event.pull_request.head.ref, 'spec-draft/'))
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/plan.yml@v2
    with:
      head-ref: ${{ github.event.pull_request.head.ref }}
      slug: ${{ inputs.slug }}
      merged: ${{ github.event_name == 'workflow_dispatch' || github.event.pull_request.merged }}
      pr-number: ${{ github.event.pull_request.number }}
      plan-review: ${{ vars.WING_COMMANDER_PLAN_REVIEW || 'pr' }}
      next-workflow: wing-commander-4-tasks.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 4. `wing-commander-4-tasks.yml`

```yaml
name: "Wing Commander · 4 tasks"

on:
  pull_request:
    types: [closed]
    branches: ["spec/**"]
    paths: ["specs/**"]
  workflow_dispatch:
    inputs:
      slug:
        description: "Spec slug (NNN-name) to (re)start task generation for"
        required: true
        type: string

permissions: {}

jobs:
  # A merged plan PR (or manual restart) generates the task list.
  tasks:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.pull_request.merged == true &&
       startsWith(github.event.pull_request.head.ref, 'plan/'))
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/tasks.yml@v2
    with:
      mode: generate
      head-ref: ${{ github.event.pull_request.head.ref }}
      slug: ${{ inputs.slug }}
      restart: ${{ github.event_name == 'workflow_dispatch' }}
      tasks-review: ${{ vars.WING_COMMANDER_TASKS_REVIEW || 'auto' }}
      next-workflow: wing-commander-5-implement.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}

  # A merged tasks PR (pr review mode) is the acceptance signal — agent-free
  # hand-off to implementation. The permissions grant must cover every job
  # in the called workflow file (GitHub validates them all at startup, even
  # `if`-skipped ones); the called job's own narrower declaration still
  # scopes the actual token.
  tasks-approved:
    if: >-
      github.event_name == 'pull_request' &&
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'tasks/')
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/tasks.yml@v2
    with:
      mode: approved
      head-ref: ${{ github.event.pull_request.head.ref }}
      next-workflow: wing-commander-5-implement.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 5. `wing-commander-5-implement.yml` (dispatch target — keep the input names)

```yaml
name: "Wing Commander · 5 implement"

on:
  workflow_dispatch:
    inputs:
      spec_dir:
        description: "Spec directory (e.g. specs/001-my-feature)"
        required: true
        type: string
      issue:
        description: "Lifecycle issue number"
        required: true
        type: string
      iteration:
        description: "Implement/converge iteration (1-based)"
        required: false
        default: "1"
        type: string

permissions: {}

jobs:
  implement:
    permissions:
      contents: write
      issues: write
      actions: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/implement.yml@v2
    with:
      spec-dir: ${{ inputs.spec_dir }}
      issue-number: ${{ fromJSON(inputs.issue) }}
      iteration: ${{ fromJSON(inputs.iteration) }}
      max-iterations: ${{ fromJSON(vars.WING_COMMANDER_MAX_ITERATIONS || '5') }}
      self-workflow: wing-commander-5-implement.yml
      next-workflow: wing-commander-6-finalize.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 6. `wing-commander-6-finalize.yml` (dispatch target — keep the input names)

```yaml
name: "Wing Commander · 6 finalize"

on:
  workflow_dispatch:
    inputs:
      spec_dir:
        description: "Spec directory (e.g. specs/001-my-feature)"
        required: true
        type: string
      issue:
        description: "Lifecycle issue number"
        required: true
        type: string
      converged:
        description: "Whether the converge loop finished cleanly"
        required: false
        default: "true"
        type: string

permissions: {}

jobs:
  finalize:
    permissions:
      contents: write
      issues: write
      pull-requests: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/finalize.yml@v2
    with:
      spec-dir: ${{ inputs.spec_dir }}
      issue-number: ${{ fromJSON(inputs.issue) }}
      converged: ${{ fromJSON(inputs.converged) }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 7. `wing-commander-7-cleanup.yml`

```yaml
name: "Wing Commander · 7 cleanup"

on:
  pull_request:
    types: [closed]

permissions: {}

jobs:
  cleanup:
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/cleanup.yml@v2
    with:
      head-ref: ${{ github.event.pull_request.head.ref }}
      base-ref: ${{ github.event.pull_request.base.ref }}
      merged: ${{ github.event.pull_request.merged }}
      pr-number: ${{ github.event.pull_request.number }}
      merge-commit-sha: ${{ github.event.pull_request.merge_commit_sha || '' }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### 8. `wing-commander-rebase.yml` (triggers are automatic — push + nightly)

```yaml
name: "Wing Commander · rebase"

on:
  push:
    branches: [main]
  schedule:
    - cron: "17 4 * * *"
  workflow_dispatch: {}   # redispatch target; push cannot reach
                           # claude-code-action directly, so `redispatch`
                           # below re-fires the run through this event

permissions: {}

jobs:
  # push cannot reach claude-code-action directly — redispatch through
  # workflow_dispatch, a supported event, instead of calling the reusable
  # stage from here. Loop guard stays here: a push made by the pipeline's
  # own App identity is skipped.
  redispatch:
    if: ${{ github.event_name == 'push' && !endsWith(github.actor, '[bot]') }}
    runs-on: ubuntu-latest
    permissions:
      actions: write
    steps:
      - name: Redispatch via workflow_dispatch (a supported event for the conflict-resolution agent)
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          gh workflow run wing-commander-rebase.yml \
            --repo "$GITHUB_REPOSITORY" \
            --ref "${{ github.ref_name }}"

  # schedule and workflow_dispatch (including this file's own redispatch,
  # above) both reach claude-code-action successfully.
  rebase:
    if: ${{ github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' }}
    permissions:
      contents: write
      issues: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/rebase.yml@v2
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed if the pipeline repository you pin is private (e.g. a
      # private fork) — see "Private pipeline repository" below. Harmless
      # when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

With the wrappers in place, run the smoke test in
[docs/setup.md](setup.md#5-smoke-test): open an issue, apply `spec-request`,
and a spec PR built from **your** templates and constitution appears.

## Version pinning

| Pin | Behavior | Choose it when |
|---|---|---|
| `@v2.0.0` (exact tag) | Immutable — your behavior changes only when you edit the pin | You want reviewable, deliberate upgrades |
| `@v2` (floating major) | Force-moved on every **non-breaking** release within major 2 — fixes arrive automatically, breaking changes never do | You want fixes without maintenance (recommended) |
| `@main` | Unreleased head — the publisher's dogfooding line | Early adoption / testing an unreleased fix, at your own risk |

Breaking interface changes (an input/secret/output removed or renamed, a
behavior-altering default, an incompatible precondition) ship **only** behind
a new major tag (e.g. `v3`), and every release's notes carry an explicit
**Breaking changes** section (possibly "None") so breakage is identifiable
before you upgrade.

A pin covers the *whole* stage: workflow body **and** the shared composite
actions, because each stage checks out its own repository at the running
workflow's exact commit (`github.job_workflow_sha`). There is no path by
which a pinned adopter receives newer internal logic.

## Migrating to `@v2`

The product's rename from "speckit-action" to "Wing Commander" ships its
breaking interface changes behind the `v2` major
(`specs/012-rename-wing-commander/contracts/rename-migration.md`). **No
action is needed to stay on `@v1`**: the `v1` floating tag and every exact
`v1.y.z` tag are immutable, and `charlesguse/speckit-action/...` pins keep
resolving through GitHub's repository-rename redirect. The GitHub App you
already created needs no change either — Apps authenticate by App ID, not
display name.

An adopter moving a pin from `@v1`/`v1.y.z` to `@v2`/`v2.y.z` must, in the
same change:

1. **Update every `uses:` line** — both the owner/repo *and* the filename
   change (the `reusable-` prefix is dropped):

   | `@v1` | `@v2` |
   |---|---|
   | `charlesguse/speckit-action/.github/workflows/reusable-<stage>.yml@v1` | `charlesguse/wing-commander/.github/workflows/<stage>.yml@v2` |

2. **Rename your repository secrets/variables** (the underlying values — App
   ID, private key, etc. — do not change, only the names), and update the
   `secrets:`/`vars:` value expressions in your wrapper YAML to match:

   | Old name | New name |
   |---|---|
   | `SPECKIT_APP_ID` | `WING_COMMANDER_APP_ID` |
   | `SPECKIT_APP_PRIVATE_KEY` | `WING_COMMANDER_APP_PRIVATE_KEY` |
   | `SPECKIT_TASKS_REVIEW` | `WING_COMMANDER_TASKS_REVIEW` |
   | `SPECKIT_IMPLEMENT_MODEL` | `WING_COMMANDER_IMPLEMENT_MODEL` |
   | `SPECKIT_MAX_ITERATIONS` | `WING_COMMANDER_MAX_ITERATIONS` |

3. **If you pin `pipeline-repo` explicitly** (rather than relying on the
   published default), update it from `charlesguse/speckit-action` to
   `charlesguse/wing-commander`.

No other adopter-visible interface changes (job outputs, `workflow_call`
input names other than the filename, label conventions, PR/issue comment
formats) are part of this migration. The `v2` release's mandatory
**Breaking changes** notes carry these same tables.

### Permission grants that changed between refs

A reusable workflow's caller must grant a **superset** of every permission
the called workflow declares. GitHub validates this at startup and, when the
caller grants less, kills the run with **zero jobs** — there is no failing
step to read, so the cause is invisible in the run's own UI. Whenever a
stage starts touching a new API, bumping your `@ref` therefore requires
widening the wrapper's `permissions:` in the same change.

| Stage | Wrapper | Added grant | Why |
|---|---|---|---|
| `watchdog.yml` | `wing-commander-8-watchdog.yml` | `checks: read` | The annotations collector reads `check-runs/.../annotations`, which the GitHub App token has no permission for, so it runs under `github.token` instead. |

So a stage-8 wrapper must now grant at least:

```yaml
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: read
      checks: read
      id-token: write
```

`lint-workflows.yml` Gate 3 enforces this for the in-repo wrappers; it
cannot see yours, so check this table when you bump a pin.

## Private pipeline repository

Adopting from a **private** pipeline repository needs two things a public one
doesn't (both verified against a private publisher):

1. **Workflow resolution.** The pipeline repository's owner must allow its
   Actions components to be used by their other repositories:
   *Settings → Actions → General → Access →* "Accessible from repositories
   owned by …" (API:
   `gh api -X PUT repos/<owner>/<pipeline-repo>/actions/permissions/access -f access_level=user`).
   GitHub only shares private Actions components within the same
   user/organization — a private pipeline repo is not adoptable across
   accounts.
2. **The composite self-checkout.** Your repository's `GITHUB_TOKEN` cannot
   read a different private repository, so each stage's pipeline self-checkout
   needs a token: set a repository secret with **read-only contents access**
   to the pipeline repository (e.g. a fine-grained PAT scoped to that single
   repo) and pass it to every stage as the optional `pipeline-repo-token`
   secret:

   ```yaml
       secrets:
         pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
   ```

   Keep the token read-only and single-repo — it is a code-fetch credential,
   not a pipeline identity (the pipeline's acting identity remains your
   GitHub App).

## Deployment environments

Every stage accepts `environment` (string, default `""`) and
`environment-deployment` (boolean, default `true`) so you can gate an
expensive stage behind a
[GitHub deployment environment](https://docs.github.com/en/actions/deploying-with-github-actions/managing-environments-for-deployment)'s
protection rules (required reviewer, wait timer, branch/tag policy, custom
App rule) — see [Stage reference](#stage-reference) below for the full
per-stage input list. Leaving `environment` unset (the default) changes
nothing: no gate, no deployment record, no phantom environment created. Seven
things to know before you bind one:

- **Approval is per job, not per stage call.** `environment` binds *every* job
  in the stage file, and each bound job that actually runs gates
  independently — a required reviewer is prompted once per job, and a wait
  timer is paid once per job, not once per call. A job skipped by its own
  `if:` never prompts.

  **Two documented exceptions, both registered and machine-checked by Gate
  7 — not oversights.**

  1. **`pr-conversation`'s `act` job.** It does **not** honour
     `inputs.environment`. Each of its matrix legs binds its own
     `confirm-environment`, because whether a leg needs propose-and-confirm
     is a property of that leg's own classification, not of the stage call
     (a job may carry only one `environment:`, so it cannot do both).
     Binding `environment` on this stage therefore gates the read-only
     `classify-and-announce` job and **not** the job that actually
     writes — the inverse of what you probably intend. To gate mutations
     here, set `confirm-categories` (and `confirm-environment`) instead.
  2. **Every stage's `verify-image-prerequisites` job**, which runs on
     every stage call and does nothing unless you set `container-image` (see
     [Runners and container images](#runners-and-container-images)). It is
     deliberately unbound, so it costs you **no** approval prompt. Binding it would not buy you
     anything: its entire body is a `docker login` and `docker pull` of the
     image *you* named, performed before any other job of the stage starts,
     so an approval would land after the credential had already been used,
     not before. It needs no `GITHUB_TOKEN` permissions and writes nothing to your
     repository.
     The jobs it gates — the ones that actually run agents and push
     commits — are bound normally.

  Counting the jobs that do run:

  | Stage call | Jobs that run | Prompts per call |
  |---|---|---|
  | `intake`, `clarify`, `finalize` | 1 | 1 |
  | `implement` | `implement` (plus `stalled` only on failure) | 1 |
  | `plan` | `resolve-spec` → `plan` | 2 |
  | `tasks` (`generate` or `approved`) | `resolve-spec` → one mode job | 2 |
  | `cleanup` | `select` → one outcome job | 2 |
  | `rebase` | `discover` → one matrix leg per branch | 1 + N |
  | `watchdog` | `collect`, `diagnose`, `report-unhandled-failure` + one `triage` and one `act` leg per finding | 3 + 2N |
  | `pr-conversation` | `classify-and-announce` (bound by `environment`) + one `act` leg per classification (bound by `confirm-categories`, **not** by `environment` — see the exception above) + `dispatch-once` and `report-fold-outcomes` (both bound by `environment`, each running once per call, after the whole `act` matrix) | 1, plus one per confirm-gated `act` leg, plus 2 |
  | `auto-update-spec-kit` (scheduled) | `health-check` → `detect` → `settle` → `evaluate-path` → `prepare` → `verify` → `act` | 7, sequentially |

  So the cheapest possible gate is a one-job stage (`intake`, `clarify`,
  `finalize`), and `auto-update-spec-kit` is the most expensive by an order of
  magnitude — seven serial approvals, each blocking the next. Every row of
  that table also carries a `verify-image-prerequisites` job, but no prompt
  for it, per exception 2 above.
- **Approval is also per run, not per feature.** A required reviewer prompts
  on every iteration of a looping stage (`implement`, once per cycle) — there
  is no pipeline-side dedup or memory of a prior approval. For a single
  approval per feature, prefer a once-per-feature stage over one that
  re-dispatches itself; note from the table above that even those cost two
  prompts, not one.
- **A pending job holds its concurrency slot, and only one call can wait.**
  Stages serialize per spec via a job-level `concurrency:` group; a job
  waiting on environment approval occupies that group for as long as it stays
  pending. GitHub keeps at most **one** pending run per concurrency group: if
  a third call arrives while one is running and one is already waiting, the
  waiting one is **cancelled**, not queued behind it (observed directly in
  this pipeline's own rebase serialization work,
  `specs/013-serialize-rebase-stages` research D4). Retriggers that arrive
  during a long review pause are therefore silently dropped — the longer you
  hold an approval, the more iterations you can lose.
- **Binding rewrites the OIDC subject, which breaks Bedrock trust policies.**
  A bound job's OIDC token carries `sub:
  repo:OWNER/REPO:environment:<name>` *instead of* the `ref:refs/heads/...`
  form an unbound job gets. If you run agents on Bedrock, the stage assumes
  your role via OIDC ([AWS Bedrock](#aws-bedrock) above), and a trust policy
  whose condition matches `repo:OWNER/REPO:ref:refs/heads/*` stops matching
  the instant you set `environment` — every Bedrock stage then fails at
  `configure-aws-credentials` with an `AssumeRoleWithWebIdentity` denial that
  mentions nothing about environments. Add the `environment:` subject form to
  the trust policy's condition *before* you bind.
- **Environment secrets don't work with this pipeline.** Your wrapper resolves
  `secrets.*` in its own calling job, and that job has no environment — the
  binding lives on the stage's jobs, one level down. GitHub is explicit that
  this cannot be bridged: "Environment secrets cannot be passed from the caller
  workflow as `on.workflow_call` does not support the `environment` keyword"
  ([reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)).
  So pointing a stage's secret at an environment-scoped value resolves empty
  and preflight fails with an unrelated-looking "no credential" error, not an
  "environment secret not found" error. Note this is not about the stages'
  kebab-case secret names (`anthropic-api-key`, `speckit-app-private-key`):
  those are `workflow_call` parameter names, not stored-secret names, so
  renaming them changes nothing — the value still comes from wherever your
  wrapper's `secrets.*` resolves.
- **A typo silently creates a new, unprotected environment.** GitHub creates
  an environment on first reference if the name doesn't already exist, with
  no protection rules — a misspelled `environment` value doesn't fail, it
  just doesn't gate anything.
- **On a private repository, the rules worth having are Enterprise-only.**
  Public repositories get all of this on every plan. On a private or internal
  repository, environments, environment secrets, and deployment branch
  policies need GitHub Pro, Team, or Enterprise — but **required reviewers and
  wait timers, the two rules that actually gate an expensive stage, need
  Enterprise**. Being on the wrong plan is not an error: the environment
  exists, the binding works, and the rule simply never fires (see
  [docs/setup.md](setup.md)).

## Runners and container images

Every stage accepts `runner` (string, default `ubuntu-latest`) and
`container-image` (string, default `""`) so you can run the pipeline's jobs
on your own infrastructure or inside your own container image, instead of
GitHub's hosted `ubuntu-latest` runner — see [Stage reference](#stage-reference)
below for the full per-stage input list. Leaving both unset (the default)
changes nothing: same runner, no container, no new failure mode. What to
know before you set either:

- **`runner` accepts one label or a JSON array of labels (a conjunction).**
  A value that does not start with `[` is used as a single label verbatim
  (`runner: my-self-hosted-label`). A value starting with `[` is parsed as
  JSON and applied as a list — GitHub's own `runs-on:` conjunction semantics,
  meaning the runner must carry *every* named label:

  ```yaml
      with:
        runner: '["self-hosted", "linux", "x64"]'
  ```

  There is no third form and no pipeline-side validation of the string —
  a malformed JSON-looking value (starts with `[` but doesn't parse) fails at
  GitHub's own expression-evaluation time, not with a pipeline-authored
  error.
- **`container-image` runs every job of the stage inside that image**,
  exactly as written (registry, repository, tag or digest — whatever you'd
  hand `docker pull`). Before any agent-bearing job's own container is
  created, a dedicated `verify-image-prerequisites` job pulls the named
  image and checks it for every tool the pipeline's own steps and shared
  composite actions need: `git`, `gh`, `jq`, `curl`, `python3`, `bash`,
  `node` (an inferred dependency of the Claude Code action, not something
  this repository's own scripts invoke directly), and `timeout`. A missing
  tool fails the stage fast, before any billable agent step, naming every
  missing tool at once — never just the first one found. An image with no
  POSIX shell at all is reported as that, rather than as "every tool is
  missing".

  **`timeout` became a real requirement in v2.5.1, before it was listed
  here or checked.** The shared lifecycle gate wraps its issue-state read
  in `timeout` so that a hung GitHub API call becomes a retryable failure
  instead of a stalled stage, and that gate runs inside your image at the
  entry of six stages. If you pin `v2` or `v2.5.1` and your image lacks
  `timeout`, those stages currently fail at their first step with a bare
  exit 127 that the gate reports as an unclassifiable failure. From this
  version the prerequisite check names it directly instead. Any image
  already carrying the other seven tools almost certainly has it —
  `timeout` is part of coreutils, and BusyBox provides an applet — so in
  practice this changes the error message you would get, not whether your
  image works.

  Presence is all the check verifies, here as for every other tool. A
  BusyBox build older than 1.30 (2018) provides `timeout` but requires
  `-t DURATION`, so it would pass the check and still fail the call; an
  image that old cannot run this pipeline for other reasons.
- **Private registry credentials** are two optional secrets,
  `container-registry-username` and `container-registry-password`, meaningful
  only when `container-image` is set:

  ```yaml
      with:
        container-image: ghcr.io/your-org/your-image:latest
      secrets:
        container-registry-username: ${{ secrets.YOUR_REGISTRY_USERNAME }}
        container-registry-password: ${{ secrets.YOUR_REGISTRY_PASSWORD }}
  ```

  `container-registry-password` can be a static value or a short-lived token
  your wrapper mints in its own step, before its `uses:` call to the
  stage — a cloud registry (ECR/GCR/ACR) credential, for instance. The stage
  itself never mints, refreshes, or manages a credential's lifecycle; it only
  ever forwards what you hand it. A pull failure's error message tells you
  whether no credentials were supplied at all, or the registry rejected the
  ones you gave it.

  **These credentials reach the prerequisite check and nothing else, today.**
  They authenticate `verify-image-prerequisites`, which pulls the image and
  checks it for the required tools. Every *other* job pulls with whatever
  authentication its runner already has. GitHub's job-level
  `container.credentials` cannot be conditionally omitted — once the key is
  written, an empty value is a template error that stops the job before its
  first step, and that is every run that names no image — so the stages do
  not carry one ([#227](https://github.com/charlesguse/wing-commander/issues/227),
  measured against real runners in
  [PR #226](https://github.com/charlesguse/wing-commander/pull/226)).

  **For a private image, use a runner that is already logged in** to the
  registry — the same `runner` input above is how you point the stage at
  one. A public (or otherwise unauthenticated) image needs nothing.
- **Both controls are set once per stage call and apply to every job in
  that call — there is no per-job selector.** `tasks.yml`, called twice by
  `wing-commander-4-tasks.yml` (`mode: generate` and `mode: approved`),
  already gives you the two call sites you'd need to run only the
  agent-running call on your own infrastructure: set `runner`/`container-image`
  on the `generate` call and leave the `approved` call at its defaults.
- **A container needs a Linux runner with Docker available.** Every stage's
  steps are Linux shell scripts; a non-Linux runner label is accepted (there
  is no pipeline-side validation of the runner value) but will fail once a
  step actually runs.
- **Out of scope**: runner groups (a different targeting shape than a label
  list); per-job targeting within one stage call; and the remaining
  `container:` settings GitHub Actions supports — volumes, ports,
  environment variables, extra Docker options, service containers. Pass-through
  matches Actions' own behavior everywhere else in this pipeline: no implicit
  registry, no implicit tag, no rewriting.
- **Self-hosted runner capacity interacts with this pipeline's per-spec
  concurrency design.** Each stage serializes per spec via its own
  `concurrency:` group (see [Deployment environments](#deployment-environments)
  above for how a pending job holds that slot); pointing multiple specs at a
  small self-hosted pool can queue jobs behind each other the way GitHub's
  hosted runners never do.

## Stage reference

Common to every stage below:

- **`on: workflow_call` only** — your wrapper owns the trigger. Any event
  works: the full-lifecycle triggers above are conventions, not requirements.
- **Common inputs** (rarely needed):
  `pipeline-repo` (string, default `charlesguse/wing-commander`) — where the
  stage checks out its shared composite actions; only republishing forks set
  it. `pipeline-ref` (string, default `""` = the running workflow's exact
  commit, resolved via `github.job_workflow_sha` or the OIDC token) — set it
  to match your `uses:` pin only if your calling job cannot grant
  `id-token: write`. `default-branch` (string, default `""` = derived via
  `gh repo view`) — stages never assume `main`. `environment` (string,
  default `""`) / `environment-deployment` (boolean, default `true`) — bind
  every job in the stage to a deployment environment; see
  [Deployment environments](#deployment-environments) above. `runner`
  (string, default `ubuntu-latest`) / `container-image` (string, default
  `""`) — run every job in the stage on your own runner(s) and/or inside
  your own container image; see
  [Runners and container images](#runners-and-container-images) above.
- **Tool-list inputs** (every agent-running stage): `extra-allowed-tools` /
  `extra-disallowed-tools` (string, default `""`) *append* to that stage's
  built-in default allow/deny tool lists (union — you don't restate the
  defaults); `allowed-tools-override` / `disallowed-tools-override` (string,
  default `__unset__`) *replace* the corresponding default list entirely (a
  literal `""` replaces it with nothing). Append and replace are per-direction,
  independent choices; supplying both for the same direction fails the stage
  before any agent runs. Leaving all four unset reproduces today's behavior
  byte-for-byte. On a multi-step stage (`implement`, whose cycle / retry /
  post-progress-comment steps each have their own defaults), these inputs are
  *stage-scoped* — the same values apply identically to every internal step,
  each composed against that step's own defaults, so a replacement must include
  everything each internal step needs. The per-stage default tool lists are
  documented in
  [stage-interfaces.md](../specs/010-reusable-pipeline/contracts/stage-interfaces.md#per-stage-default-tool-lists).
  These composed lists also drive the stage's own stated-tooling prompt where
  one exists (`implement.yml`'s cycle/retry steps) — see
  [tool-composition-action.md#outputs](../specs/026-configurable-tool-lists/contracts/tool-composition-action.md#outputs).
- **Common secrets**: `claude-code-oauth-token` / `anthropic-api-key`
  (one-of, see [Credentials](#credentials)); `speckit-app-id` /
  `speckit-app-private-key` (required — the App writes pushes/PRs/comments);
  `pipeline-repo-token` (optional — only for a
  [private pipeline repository](#private-pipeline-repository)).
- **Preflight** — every stage fails fast, before any agent step, on: no
  credential, missing spec-kit artifacts, or missing stage preconditions,
  with a message naming the missing piece and the step that provides it. A
  spec-kit version different from the supported pin (`SPECKIT_SUPPORTED_VERSION`
  in the preflight action) produces a warning, never a failure.
- **Side effects land in your repository only** — branches, commits, PRs,
  labels, comments. The branch *prefixes* — each configurable via its
  repository variable and defaulting to today's literal:
  `WING_COMMANDER_SPEC_DRAFT_PREFIX` (`spec-draft/`),
  `WING_COMMANDER_SPEC_PREFIX` (`spec/`), `WING_COMMANDER_PLAN_PREFIX`
  (`plan/`), `WING_COMMANDER_TASKS_PREFIX` (`tasks/`), and
  `WING_COMMANDER_IMPL_PREFIX` (`impl/`) (see
  [docs/setup.md](setup.md#3-repository-variables) for the variable list) —
  and the `specs/NNN-slug/` layout (with `spec-meta.json` as lifecycle
  state) are the shared artifact contract; the default branch is whatever
  yours is.
- **Chaining is opt-in** — `next-workflow`/`self-workflow` inputs default to
  `""` (no dispatch), so every stage runs standalone; when set, they name a
  *wrapper file in your repository* to `gh workflow run` with the payload
  shown in [the chaining contract](#chaining-payload-contract).
- **Per-spec serialization** — stages declare job-level concurrency groups
  (`wing-commander-<slug>`-shaped), which apply in your repository. Don't add the
  same group name to your wrapper (a workflow-level group with the same name
  as a called job's group deadlocks the run).

### intake

| | |
|---|---|
| Inputs | `issue-number` (number, required); `model` (string, `claude-opus-5`); `max-turns` (number, `50`) |
| Secrets | credentials + App (all stages; omitted below) |
| Preconditions | spec-kit present in your checkout |
| Side effects | `spec-draft/NNN-slug` branch (prefix configurable via `WING_COMMANDER_SPEC_DRAFT_PREFIX`, default `spec-draft/`) + draft spec PR to your default branch; `specs/NNN-slug/` with `spec.md`, `spec-meta.json`; `spec:NNN-slug` + `stage:spec` labels; clarification-questions or ready-for-review comment |
| Outputs | `spec-dir`, `feature-num` |

Single-stage example — spec PRs from a manual dispatch instead of a label:

```yaml
on:
  workflow_dispatch:
    inputs:
      issue:
        description: "Issue number to specify"
        required: true
        type: string
jobs:
  intake:
    permissions: { contents: write, pull-requests: write, issues: write, id-token: write }
    uses: charlesguse/wing-commander/.github/workflows/intake.yml@v2
    with:
      issue-number: ${{ fromJSON(inputs.issue) }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### clarify

| | |
|---|---|
| Inputs | `issue-number` (number, required); `comment-id` (number, required); `model` (string, `claude-opus-5`); `max-turns` (number, `40`) |
| Preconditions | spec-kit present; issue carries a `spec:NNN-slug` label; open `spec-draft/NNN-slug` branch (prefix configurable via `WING_COMMANDER_SPEC_DRAFT_PREFIX`, default `spec-draft/`) |
| Side effects | commits to the draft branch (PR updates automatically); 👀 reaction on the comment; updated PR body; status comment on the issue |
| Outputs | none |

The wrapper owns the commenter-authorization gate — see wrapper 2 above.

### plan

| | |
|---|---|
| Inputs | `head-ref` (string) **or** `slug` (string) — one required; `merged` (boolean, `true`; `false` no-ops); `pr-number` (string, `""` — refusal comments only); `model` (string, `claude-sonnet-5`); `max-turns` (number, `110`) |
| Preconditions | `specs/NNN-slug/spec.md` + `spec-meta.json` on your default branch; no existing `plan/NNN-slug` branch (prefix configurable via `WING_COMMANDER_PLAN_PREFIX`, default `plan/`) (duplicate guard) |
| Side effects | `spec/NNN-slug` persistent branch (prefix configurable via `WING_COMMANDER_SPEC_PREFIX`, default `spec/`), created if absent; `plan/NNN-slug` branch (prefix configurable via `WING_COMMANDER_PLAN_PREFIX`, default `plan/`) + plan PR into the spec branch; lifecycle issue created for hand-submitted specs; `spec-meta.json` → `plan`; label flip |
| Outputs | `spec-branch`, `spec-dir` |

Single-stage example — plan a hand-written spec via manual dispatch:

```yaml
on:
  workflow_dispatch:
    inputs:
      slug:
        description: "Spec slug (NNN-name)"
        required: true
        type: string
jobs:
  plan:
    permissions: { contents: write, pull-requests: write, issues: write, id-token: write }
    uses: charlesguse/wing-commander/.github/workflows/plan.yml@v2
    with:
      slug: ${{ inputs.slug }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

### tasks

| | |
|---|---|
| Inputs | `mode` (string `generate`\|`approved`, default `generate`); `head-ref` or `slug` (one required — `plan/…` for generate, `tasks/…` for approved); `restart` (boolean, `false` — admits a `stalled` spec on deliberate manual restart); `tasks-review` (string `auto`\|`pr`, default `auto`); `model` (string, `claude-sonnet-5`); `max-turns` (number, `60`); `next-workflow` (string, `""` = no dispatch) |
| Preconditions | `generate`: `plan.md` on the spec branch; `spec-meta.json.stage == "plan"` (or `stalled` with `restart: true`). `approved`: `spec-meta.json.stage == "tasks"` |
| Side effects | `auto`: `tasks.md` + stage flip committed to the spec branch, implement dispatched if configured. `pr`: `tasks/NNN-slug` branch (prefix configurable via `WING_COMMANDER_TASKS_PREFIX`, default `tasks/`) + review PR, no dispatch. `approved`: dispatch only |
| Outputs | `spec-dir` |

`mode: approved` is agent-free (no Claude credential needed) — it exists so
your wrapper's `pull_request: closed` trigger for merged tasks PRs can hand
off to implementation; a `workflow_call` workflow cannot own that trigger
itself.

### implement

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `iteration` (number, required); `model` (string, `claude-sonnet-5`); `max-turns` (number, `180`); `max-iterations` (number, `5`); `self-workflow` (string, `""`); `next-workflow` (string, `""`) |
| Preconditions | `spec.md`/`plan.md`/`tasks.md`/`spec-meta.json` on the `spec/NNN-slug` branch; spec-meta agrees with the inputs; `(stage, iteration)` is the next expected step |
| Side effects | ONE implement ⟲ converge cycle committed to the spec branch; per-cycle progress comment; tier-up retry on failure (→ `claude-opus-5`); stall marking + runbook comment on exhausted retry; dispatches `self-workflow` (next iteration) or `next-workflow` (finalize) when configured, otherwise reports to the issue and stops |
| Outputs | `converged` (boolean; empty on failure/skip) |

One call = one cycle. The loop exists only through `self-workflow`
re-dispatch, so you decide whether iteration is automatic (wrapper 5 above)
or one-cycle-at-a-time manual.

### finalize

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `converged` (boolean, required); `summary-model` (string, `claude-haiku-4-5`); `max-turns` (number, `20`) |
| Preconditions | full artifact set on `spec/NNN-slug`; branch has commits ahead of your default branch; no final PR exists yet (any state) |
| Side effects | final PR `spec/NNN-slug` → default branch (summary, changed files, remaining-manual-work); same remaining-work list commented on the issue; `spec-meta.json` → `review`; `stage:review` label |
| Outputs | `pr-number` |

### cleanup

| | |
|---|---|
| Inputs | `head-ref`, `base-ref` (string, required); `merged` (boolean, required); `pr-number` (number, required); `merge-commit-sha` (string, `""`); `summary-model` (string, `claude-haiku-4-5`); `max-turns` (number, `20`) |
| Preconditions | matched spec's artifacts exist and self-identify consistently (identity refusal otherwise) |
| Side effects | self-selects exactly one outcome from the raw PR facts: merged final PR → full teardown + issue closed (`teardown-done`); unmerged draft PR → draft deleted, issue left open (`teardown-rejected`); unmerged final/plan/tasks/impl PR (the `plan/`, `tasks/`, `impl/` prefixes are configurable defaults, set via `WING_COMMANDER_PLAN_PREFIX`/`WING_COMMANDER_TASKS_PREFIX`/`WING_COMMANDER_IMPL_PREFIX`) → marked stalled, nothing deleted (`mark-stalled`); everything else → no-op |
| Outputs | `outcome` (`teardown-done` \| `teardown-rejected` \| `mark-stalled` \| `none`) |

Wire it to a repo-wide `pull_request: closed` trigger and forward the raw
facts (wrapper 7 above) — the selection logic is inside the stage.

**The close-race caveat (#73):** closing a PR *together with* deleting its
head branch (the UI's close-and-delete flow, `gh pr close --delete-branch`)
can race GitHub's creation of the `pull_request: closed` run — the close
then produces **no cleanup run at all**, and every outcome is silently
skipped. Prefer closing first and deleting the branch after the cleanup run
appears (for pipeline branches, prefer not deleting at all — teardown owns
that). The reference wrapper also carries a daily scheduled **sweeper**: it
re-derives the raw facts from the API for any pipeline PR closed in the
last 48 hours whose close left no `pull_request`-event cleanup run behind,
marks the PR with a comment, and re-delivers the facts to this same stage.
To adopt the sweeper, copy the reference wrapper's `schedule` and
`workflow_dispatch` triggers plus its `sweep` and `resweep` jobs
([`wing-commander-7-cleanup.yml`](../.github/workflows/wing-commander-7-cleanup.yml) —
the minimal wrapper in §7 above deliberately omits them), then change
`resweep`'s `uses:` from the local path to the same pinned
`charlesguse/wing-commander/.github/workflows/cleanup.yml@v2` reference
your event-arm job uses. Nothing else needs renaming: the sweep probe
derives your wrapper's own filename from `github.workflow_ref`, and a
failed run lookup skips that PR until the next sweep rather than
re-delivering on a guess.

### rebase

The stage the spec calls "auto-rebase" — `rebase` is its canonical published
id, and its triggers (push to default branch + schedule) are automatic
conventions your wrapper owns.

| | |
|---|---|
| Inputs | `model` (string, `claude-sonnet-5`); `max-turns` (number, `50`) |
| Preconditions | none — discovers in-flight `spec/*` branches itself; empty discovery is a clean no-op |
| Side effects | per-branch rebase onto your default branch: clean → force-push with lease; conflicting → agent resolution with a deterministic scope check; unresolvable → abandoned untouched + `rebase:blocked` escalation comment (deduped by SHA marker) |
| Outputs | none |

### pr-conversation

Optional, additive stage — not part of the eight-file minimal set above. It
classifies and routes a maintainer's review or comment on an implementation
PR (`spec/NNN-slug → default branch`): fold-in + implement re-dispatch,
new-issue/new-PR spin-offs, manual-step/permission handling, or a plain
reply. See [Stage 10 — PR Conversation](architecture.md#stage-10--pr-conversation-pr-conversationyml-wrapper-wing-commander-9-pr-conversationyml--see-specs033-pr-conversation-commands)
for the full routing design.

| | |
|---|---|
| Inputs | `pr-number` (number, required); `event-kind` (string `review`\|`review-comment`\|`issue-comment`, required); `body` (string, required, untrusted); `actor-login`/`actor-association` (string, required); `comment-id`/`review-id` (number, `0`); `thread-path`/`thread-diff-hunk` (string, `""`); `confirm-categories` (string, `""` = act-then-report for every category); `confirm-environment` (string, `pr-conversation-confirm`); `confirm-timeout-minutes` (number, `1440` — how long a confirm-gated leg may wait on that environment's approval before GitHub cancels it outright); `model` (string, `claude-sonnet-5`); `max-turns` (number, `40`); `implement-workflow` (string, `""`) |
| Preconditions | the PR's base is your default branch and its head starts with `spec-prefix` (not `spec-draft-prefix`/`plan-prefix`/`tasks-prefix`) — anything else short-circuits with no reply at all; the lifecycle issue is open |
| Side effects | posts one `IntentAnnouncement` per classification before any mutation; routes per category — see the architecture doc for the full list |
| Outputs | none — side effects only. (`classify-and-announce` has *job*-level outputs, which a caller cannot read; `needs.pr-conversation.outputs.qualifies` in your own wrapper resolves to an empty string.) |

`implement-workflow` is your implement wrapper's **filename**, the same
opt-in chaining convention every other stage uses — pass
`wing-commander-5-implement.yml` (or whatever you renamed it to) to have an
in-scope fold-in re-drive implement automatically, and to have a `stop`
request cancel that dispatched run too. Left at its `""` default, an
in-scope fold-in is still committed and pushed to `spec/<slug>`; the PR
reply then says no implement workflow is configured and gives you the
`spec_dir`/`issue`/`iteration` payload to dispatch by hand.

Deliberately **no `workflow_dispatch`** — this is the only stage that is
purely event-triggered, since its whole purpose is reacting to a review or
comment. Authorization is **two layers**, and the split matters: the
wrapper's `if:` excludes bots only, and the stage's `classify-and-announce`
job checks `OWNER`/`MEMBER`/`COLLABORATOR` association as its own first
deterministic step, posting a notice-and-stop reply when it fails. Do not
move the association check up into the wrapper `if:` — a wrapper `if:`
cannot post a reply, so an unauthorized human would get silence instead of
that notice. What *is* absent at both layers, unlike clarify/intake, is any
requester carve-out: the lifecycle issue's own author gets no special
standing here.

```yaml
name: "Wing Commander · 9 pr conversation"

on:
  pull_request_review:
    types: [submitted]
  pull_request_review_comment:
    types: [created]
  issue_comment:
    types: [created]

permissions: {}

jobs:
  pr-conversation:
    # Bot-exclusion ONLY — do not add the OWNER/MEMBER/COLLABORATOR check
    # here. A wrapper `if:` cannot post a reply, so gating on association at
    # this level silently skips the job and leaves a non-bot, unauthorized
    # commenter with no response at all, violating FR-021/SC-006. The
    # association check belongs to the stage: pr-conversation.yml's
    # classify-and-announce job runs it as its own first deterministic step
    # and posts the notice-and-stop reply when it fails. There is also no
    # `|| actor.id == issue.author.id` requester carve-out here (unlike the
    # clarify and intake wrappers) — the lifecycle issue's own author gets
    # no special standing with this stage.
    if: >-
      (github.event_name == 'issue_comment' &&
       github.event.issue.pull_request != null &&
       github.event.comment.user.type != 'Bot') ||
      (github.event_name == 'pull_request_review_comment' &&
       github.event.comment.user.type != 'Bot') ||
      (github.event_name == 'pull_request_review' &&
       github.event.review.body != '' &&
       github.event.review.user.type != 'Bot')
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: write
      id-token: write
    uses: charlesguse/wing-commander/.github/workflows/pr-conversation.yml@v2
    with:
      pr-number: ${{ github.event.pull_request.number || github.event.issue.number }}
      event-kind: >-
        ${{ github.event_name == 'pull_request_review' && 'review'
          || github.event_name == 'pull_request_review_comment' && 'review-comment'
          || 'issue-comment' }}
      body: ${{ github.event.review.body || github.event.comment.body || '' }}
      actor-login: ${{ github.event.review.user.login || github.event.comment.user.login }}
      actor-association: ${{ github.event.review.author_association || github.event.comment.author_association }}
      # Your implement wrapper's filename — opt-in, like every other
      # chaining input. Omit it and an in-scope fold-in is committed but
      # nothing is dispatched (the PR reply says so).
      implement-workflow: wing-commander-5-implement.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      speckit-app-id: ${{ secrets.WING_COMMANDER_APP_ID }}
      speckit-app-private-key: ${{ secrets.WING_COMMANDER_APP_PRIVATE_KEY }}
```

## Chaining payload contract

When a stage dispatches a `next-workflow`/`self-workflow`, the target is a
**wrapper file in your repository**, invoked via `gh workflow run` with these
`workflow_dispatch` inputs (snake_case — historical dispatch names; your
wrapper translates them to the stage's kebab-case inputs, as wrappers 5 and 6
show):

| Dispatch target | Required `workflow_dispatch` inputs |
|---|---|
| implement wrapper (`next-workflow` of tasks; `self-workflow` of implement) | `spec_dir` (string), `issue` (string), `iteration` (string) |
| finalize wrapper (`next-workflow` of implement) | `spec_dir` (string), `issue` (string), `converged` (string) |

Rename the wrapper *files* freely — the stages take the filenames as inputs —
but keep the input *names* exactly.
