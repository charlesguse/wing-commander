# Adopting the speckit pipeline

The pipeline's eight stages are published from this repository as reusable
`workflow_call` workflows (`.github/workflows/reusable-*.yml`), versioned by
release tags. You adopt them **by reference**: your repository keeps thin
wrapper workflows that own the triggers, gates, and configuration, and call
the published stages with your credentials. You never copy stage logic, and a
version bump on your side picks up fixes.

Any subset works — adopt the full lifecycle below, or wire a single stage to
any trigger you like (see the [stage reference](#stage-reference)). No stage
requires this repository's label taxonomy, branch gate sequence, or sibling
stages to exist.

This repository is its own first adopter: its `speckit-*.yml` workflows are
exactly the thin wrappers described here, calling the same stages by local
path. When in doubt, read them — they are the living example.

## Prerequisites

1. **Your own spec-kit artifacts.** Run
   [`specify init`](https://github.com/github/spec-kit) in your repository
   (pin **spec-kit v0.12.4**, the version this pipeline supports; use
   `--integration claude --script sh`), then write your constitution with
   `/speckit-constitution`. The pipeline reads `.specify/`,
   `.claude/skills/speckit-*`, and `specs/` **only from your repository's
   checkout** — it never bundles or substitutes its own. Stages fail fast
   with guidance if these are missing.
2. **A dedicated GitHub App** installed on your repository, with Contents,
   Issues, and Pull requests read/write — one-time setup, walkthrough in
   [docs/setup.md](setup.md#1-create-the-speckit-bot-github-app). Store its
   ID and private key as the `SPECKIT_APP_ID` / `SPECKIT_APP_PRIVATE_KEY`
   secrets.
3. **A Claude credential** from *your* plan — see
   [Credentials](#credentials). Exactly one is sufficient.
4. **Labels** for the full-lifecycle flow (only `spec-request` is needed for
   the gate; the script in [docs/setup.md](setup.md#4-labels) creates the
   rest).
5. **Access to the pipeline repository.** Reusable workflows and the stages'
   composite-action self-checkout both require that
   `charlesguse/speckit-action` is accessible to your repository. The
   pipeline repository is currently **private**, so the one-time setup in
   [Private pipeline repository](#private-pipeline-repository) is required;
   that whole section becomes unnecessary only if the pipeline repository is
   made public. Forks that republish under another name set the
   `pipeline-repo` input.

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
pinned to the floating major tag `@v1` (see
[Version pinning](#version-pinning)); before the first release, `@main`
works the same way. Replace `main` in the `branches:` filters if your default
branch is named differently — the *stages* never assume a name, but your
triggers are yours.

> The implement and finalize wrappers are **dispatch targets**: earlier
> stages chain to them via `gh workflow run` with the payload inputs
> (`spec_dir`, `issue`, `iteration`/`converged`) shown verbatim below. Keep
> those `workflow_dispatch` input names exactly as written — they are part of
> the published chaining contract.

### 1. `speckit-1-intake.yml`

```yaml
name: "speckit · 1 intake"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-intake.yml@v1
    with:
      issue-number: ${{ github.event.issue.number }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 2. `speckit-2-clarify.yml`

```yaml
name: "speckit · 2 clarify"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-clarify.yml@v1
    with:
      issue-number: ${{ github.event.issue.number }}
      comment-id: ${{ github.event.comment.id }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 3. `speckit-3-plan.yml`

```yaml
name: "speckit · 3 plan"

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
      id-token: write
    uses: charlesguse/speckit-action/.github/workflows/reusable-plan.yml@v1
    with:
      head-ref: ${{ github.event.pull_request.head.ref }}
      slug: ${{ inputs.slug }}
      merged: ${{ github.event_name == 'workflow_dispatch' || github.event.pull_request.merged }}
      pr-number: ${{ github.event.pull_request.number }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 4. `speckit-4-tasks.yml`

```yaml
name: "speckit · 4 tasks"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-tasks.yml@v1
    with:
      mode: generate
      head-ref: ${{ github.event.pull_request.head.ref }}
      slug: ${{ inputs.slug }}
      restart: ${{ github.event_name == 'workflow_dispatch' }}
      tasks-review: ${{ vars.SPECKIT_TASKS_REVIEW || 'auto' }}
      next-workflow: speckit-5-implement.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-tasks.yml@v1
    with:
      mode: approved
      head-ref: ${{ github.event.pull_request.head.ref }}
      next-workflow: speckit-5-implement.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 5. `speckit-5-implement.yml` (dispatch target — keep the input names)

```yaml
name: "speckit · 5 implement"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-implement.yml@v1
    with:
      spec-dir: ${{ inputs.spec_dir }}
      issue-number: ${{ fromJSON(inputs.issue) }}
      iteration: ${{ fromJSON(inputs.iteration) }}
      max-iterations: ${{ fromJSON(vars.SPECKIT_MAX_ITERATIONS || '5') }}
      self-workflow: speckit-5-implement.yml
      next-workflow: speckit-6-finalize.yml
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 6. `speckit-6-finalize.yml` (dispatch target — keep the input names)

```yaml
name: "speckit · 6 finalize"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-finalize.yml@v1
    with:
      spec-dir: ${{ inputs.spec_dir }}
      issue-number: ${{ fromJSON(inputs.issue) }}
      converged: ${{ fromJSON(inputs.converged) }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 7. `speckit-7-cleanup.yml`

```yaml
name: "speckit · 7 cleanup"

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
    uses: charlesguse/speckit-action/.github/workflows/reusable-cleanup.yml@v1
    with:
      head-ref: ${{ github.event.pull_request.head.ref }}
      base-ref: ${{ github.event.pull_request.base.ref }}
      merged: ${{ github.event.pull_request.merged }}
      pr-number: ${{ github.event.pull_request.number }}
      merge-commit-sha: ${{ github.event.pull_request.merge_commit_sha || '' }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### 8. `speckit-rebase.yml` (triggers are automatic — push + nightly)

```yaml
name: "speckit · rebase"

on:
  push:
    branches: [main]
  schedule:
    - cron: "17 4 * * *"

permissions: {}

jobs:
  rebase:
    # Security gate: a push made by the pipeline's own App identity is
    # skipped (loop guard); a scheduled run always proceeds.
    if: ${{ !endsWith(github.actor, '[bot]') }}
    permissions:
      contents: write
      issues: write
      id-token: write
    uses: charlesguse/speckit-action/.github/workflows/reusable-rebase.yml@v1
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # Only needed while the pipeline repository is private — see
      # "Private pipeline repository" below. Harmless when unset.
      pipeline-repo-token: ${{ secrets.PIPELINE_REPO_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

With the wrappers in place, run the smoke test in
[docs/setup.md](setup.md#5-smoke-test): open an issue, apply `spec-request`,
and a spec PR built from **your** templates and constitution appears.

## Version pinning

| Pin | Behavior | Choose it when |
|---|---|---|
| `@v1.2.3` (exact tag) | Immutable — your behavior changes only when you edit the pin | You want reviewable, deliberate upgrades |
| `@v1` (floating major) | Force-moved on every **non-breaking** release within major 1 — fixes arrive automatically, breaking changes never do | You want fixes without maintenance (recommended) |
| `@main` | Unreleased head — the publisher's dogfooding line | Early adoption / testing an unreleased fix, at your own risk |

Breaking interface changes (an input/secret/output removed or renamed, a
behavior-altering default, an incompatible precondition) ship **only** behind
a new major tag (`v2`), and every release's notes carry an explicit
**Breaking changes** section (possibly "None") so breakage is identifiable
before you upgrade.

A pin covers the *whole* stage: workflow body **and** the shared composite
actions, because each stage checks out its own repository at the running
workflow's exact commit (`github.job_workflow_sha`). There is no path by
which a pinned adopter receives newer internal logic.

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

## Stage reference

Common to every stage below:

- **`on: workflow_call` only** — your wrapper owns the trigger. Any event
  works: the full-lifecycle triggers above are conventions, not requirements.
- **Common inputs** (rarely needed):
  `pipeline-repo` (string, default `charlesguse/speckit-action`) — where the
  stage checks out its shared composite actions; only republishing forks set
  it. `pipeline-ref` (string, default `""` = the running workflow's exact
  commit, resolved via `github.job_workflow_sha` or the OIDC token) — set it
  to match your `uses:` pin only if your calling job cannot grant
  `id-token: write`. `default-branch` (string, default `""` = derived via
  `gh repo view`) — stages never assume `main`.
- **Common secrets**: `claude-code-oauth-token` / `anthropic-api-key`
  (one-of, see [Credentials](#credentials)); `speckit-app-id` /
  `speckit-app-private-key` (required — the App writes pushes/PRs/comments);
  `pipeline-repo-token` (optional — only for a
  [private pipeline repository](#private-pipeline-repository)).
- **Preflight** — every stage fails fast, before any agent step, on: no
  credential, missing spec-kit artifacts, or missing stage preconditions,
  with a message naming the missing piece and the step that provides it. A
  spec-kit version different from the supported pin (v0.12.4) produces a
  warning, never a failure.
- **Side effects land in your repository only** — branches, commits, PRs,
  labels, comments. The branch *prefixes* `spec-draft/`, `spec/`, `plan/`,
  `tasks/`, `impl/` and the `specs/NNN-slug/` layout (with `spec-meta.json`
  as lifecycle state) are the shared artifact contract; the default branch
  is whatever yours is.
- **Chaining is opt-in** — `next-workflow`/`self-workflow` inputs default to
  `""` (no dispatch), so every stage runs standalone; when set, they name a
  *wrapper file in your repository* to `gh workflow run` with the payload
  shown in [the chaining contract](#chaining-payload-contract).
- **Per-spec serialization** — stages declare job-level concurrency groups
  (`speckit-<slug>`-shaped), which apply in your repository. Don't add the
  same group name to your wrapper (a workflow-level group with the same name
  as a called job's group deadlocks the run).

### intake

| | |
|---|---|
| Inputs | `issue-number` (number, required); `model` (string, `claude-opus-4-8`); `max-turns` (number, `50`) |
| Secrets | credentials + App (all stages; omitted below) |
| Preconditions | spec-kit present in your checkout |
| Side effects | `spec-draft/NNN-slug` branch + draft spec PR to your default branch; `specs/NNN-slug/` with `spec.md`, `spec-meta.json`; `spec:NNN-slug` + `stage:spec` labels; clarification-questions or ready-for-review comment |
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
    uses: charlesguse/speckit-action/.github/workflows/reusable-intake.yml@v1
    with:
      issue-number: ${{ fromJSON(inputs.issue) }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### clarify

| | |
|---|---|
| Inputs | `issue-number` (number, required); `comment-id` (number, required); `model` (string, `claude-opus-4-8`); `max-turns` (number, `40`) |
| Preconditions | spec-kit present; issue carries a `spec:NNN-slug` label; open `spec-draft/NNN-slug` branch |
| Side effects | commits to the draft branch (PR updates automatically); 👀 reaction on the comment; updated PR body; status comment on the issue |
| Outputs | none |

The wrapper owns the commenter-authorization gate — see wrapper 2 above.

### plan

| | |
|---|---|
| Inputs | `head-ref` (string) **or** `slug` (string) — one required; `merged` (boolean, `true`; `false` no-ops); `pr-number` (string, `""` — refusal comments only); `model` (string, `claude-sonnet-5`); `max-turns` (number, `80`) |
| Preconditions | `specs/NNN-slug/spec.md` + `spec-meta.json` on your default branch; no existing `plan/NNN-slug` branch (duplicate guard) |
| Side effects | `spec/NNN-slug` persistent branch (created if absent); `plan/NNN-slug` branch + plan PR into the spec branch; lifecycle issue created for hand-submitted specs; `spec-meta.json` → `plan`; label flip |
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
    uses: charlesguse/speckit-action/.github/workflows/reusable-plan.yml@v1
    with:
      slug: ${{ inputs.slug }}
    secrets:
      claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      speckit-app-id: ${{ secrets.SPECKIT_APP_ID }}
      speckit-app-private-key: ${{ secrets.SPECKIT_APP_PRIVATE_KEY }}
```

### tasks

| | |
|---|---|
| Inputs | `mode` (string `generate`\|`approved`, default `generate`); `head-ref` or `slug` (one required — `plan/…` for generate, `tasks/…` for approved); `restart` (boolean, `false` — admits a `stalled` spec on deliberate manual restart); `tasks-review` (string `auto`\|`pr`, default `auto`); `model` (string, `claude-sonnet-5`); `max-turns` (number, `60`); `next-workflow` (string, `""` = no dispatch) |
| Preconditions | `generate`: `plan.md` on the spec branch; `spec-meta.json.stage == "plan"` (or `stalled` with `restart: true`). `approved`: `spec-meta.json.stage == "tasks"` |
| Side effects | `auto`: `tasks.md` + stage flip committed to the spec branch, implement dispatched if configured. `pr`: `tasks/NNN-slug` branch + review PR, no dispatch. `approved`: dispatch only |
| Outputs | `spec-dir` |

`mode: approved` is agent-free (no Claude credential needed) — it exists so
your wrapper's `pull_request: closed` trigger for merged tasks PRs can hand
off to implementation; a `workflow_call` workflow cannot own that trigger
itself.

### implement

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `iteration` (number, required); `model` (string, `claude-sonnet-5`); `max-turns` (number, `100`); `max-iterations` (number, `5`); `self-workflow` (string, `""`); `next-workflow` (string, `""`) |
| Preconditions | `spec.md`/`plan.md`/`tasks.md`/`spec-meta.json` on the `spec/NNN-slug` branch; spec-meta agrees with the inputs; `(stage, iteration)` is the next expected step |
| Side effects | ONE implement ⟲ converge cycle committed to the spec branch; per-cycle progress comment; tier-up retry on failure (→ `claude-opus-4-8`); stall marking + runbook comment on exhausted retry; dispatches `self-workflow` (next iteration) or `next-workflow` (finalize) when configured, otherwise reports to the issue and stops |
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
| Side effects | self-selects exactly one outcome from the raw PR facts: merged final PR → full teardown + issue closed (`teardown-done`); unmerged draft PR → draft deleted, issue left open (`teardown-rejected`); unmerged final/plan/tasks/impl PR → marked stalled, nothing deleted (`mark-stalled`); everything else → no-op |
| Outputs | `outcome` (`teardown-done` \| `teardown-rejected` \| `mark-stalled` \| `none`) |

Wire it to a repo-wide `pull_request: closed` trigger and forward the raw
facts (wrapper 7 above) — the selection logic is inside the stage.

### rebase

The stage the spec calls "auto-rebase" — `rebase` is its canonical published
id, and its triggers (push to default branch + schedule) are automatic
conventions your wrapper owns.

| | |
|---|---|
| Inputs | `model` (string, `claude-sonnet-5`); `max-turns` (number, `30`) |
| Preconditions | none — discovers in-flight `spec/*` branches itself; empty discovery is a clean no-op |
| Side effects | per-branch rebase onto your default branch: clean → force-push with lease; conflicting → agent resolution with a deterministic scope check; unresolvable → abandoned untouched + `rebase:blocked` escalation comment (deduped by SHA marker) |
| Outputs | none |

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
