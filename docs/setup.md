# Setup

One-time configuration to bring the Wing Commander pipeline to life in this repository
(or in any repository that adopts it). An adopting repository must first have
its own `specify init` output — `.specify/` (including
`memory/constitution.md`) and `.claude/skills/speckit-*` — because the pipeline
reads all project-specific artifacts from the repository it runs in, never from
Wing Commander (see the [README](../README.md#using-this-on-your-own-project)).

## 1. Create the wing-commander-bot GitHub App

The pipeline performs pushes, PRs, labels, and comments as a dedicated GitHub App
instead of the default `GITHUB_TOKEN`. This is load-bearing, not cosmetic: events
created with `GITHUB_TOKEN` **do not trigger other workflows**, so a pipeline that
used it would silently stop after its first stage. App-authored events chain
normally, and the actor name (`<slug>[bot]`) gives workflows a reliable filter to
avoid reacting to their own actions.

1. GitHub → Settings → Developer settings → **GitHub Apps** → *New GitHub App*
   - Name: `wing-commander-bot` (any unique name works; the slug becomes the actor name)
   - Homepage URL: this repository's URL
   - Webhook: **uncheck** *Active* (no webhook needed)
2. **Repository permissions**:
   - Contents: **Read and write**
   - Issues: **Read and write**
   - Pull requests: **Read and write**
   - Everything else: No access

   Grant **exactly** these three and nothing more. The list is a contract,
   not a starting point: the pipeline's token-permission gate (Gate 12 in
   `lint-workflows.yml`) checks every `gh`/API call site against *this
   documented surface*, so a call that needs more than the App is documented
   to have is flagged in CI before it ships. An over-granted installation
   (say, Actions: read) makes such a call *succeed at runtime* while every
   correctly-configured adopter 403s — the defect is masked exactly where it
   is tested most. The pipeline never needs the App to read Actions run
   state; jobs that need it use their own `github.token` with an
   `actions: read` job permission. If your installation already carries
   extra grants, trim it to the three above (App settings → Install App →
   this repository → Configure).
3. Create the App, then on its settings page:
   - Note the **App ID**
   - Generate a **private key** (downloads a `.pem`)
4. **Install** the App on this repository (App settings → Install App).

## 2. Repository secrets

Settings → Secrets and variables → Actions → **Secrets**:

| Secret | Required | Value |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | one of the two Claude credentials | Claude subscription token — run `claude setup-token` locally and paste the result |
| `ANTHROPIC_API_KEY` | one of the two Claude credentials | API key from the [Claude Console](https://console.anthropic.com/) (pay-per-token billing) |
| `WING_COMMANDER_APP_ID` | yes | The App ID from step 1 |
| `WING_COMMANDER_APP_PRIVATE_KEY` | yes | Full contents of the downloaded `.pem` |
| `PIPELINE_REPO_TOKEN` | only if the pipeline repository you pin is **private** (e.g. a private fork) | Read-only contents token for that private pipeline repository (e.g. a single-repo fine-grained PAT) — see [docs/adoption.md](adoption.md#private-pipeline-repository). Not needed when pinning the public `charlesguse/wing-commander`, and never needed in the pipeline repository itself. |
| `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME` | only if `WING_COMMANDER_CONTAINER_IMAGE` (below) is set **and** its registry is private | Username for that registry — see [docs/adoption.md](adoption.md#runners-and-container-images) |
| `WING_COMMANDER_CONTAINER_REGISTRY_PASSWORD` | only if `WING_COMMANDER_CONTAINER_IMAGE` is set **and** its registry is private | Password or token for that registry; may be a short-lived token minted by the wrapper before its `uses:` call — see [docs/adoption.md](adoption.md#runners-and-container-images) |

Both Claude credentials are first-class: every stage accepts either, exactly
one is sufficient, and if you configure both the API key is used (Claude
Code's own
[authentication precedence](https://code.claude.com/docs/en/authentication#authentication-precedence)).
With neither configured, stages fail fast in a preflight step naming both
secret names, before any agent cost. Details:
[docs/adoption.md#credentials](adoption.md#credentials).

> **Using AWS Bedrock instead?** Bedrock is enabled per stage via the
> `use-bedrock` / `aws-role-arn` / `aws-region` `workflow_call` inputs (set in
> your wrapper's `with:` block), not as repository secrets or variables —
> credentials are assumed via OIDC inside each stage job, so there are no
> long-lived AWS secrets to add here. See
> [docs/adoption.md#credentials](adoption.md#credentials) for the full setup.

> **Gating a stage behind a deployment environment?** Every stage accepts an
> `environment` `workflow_call` input (set in your wrapper's `with:` block),
> not a repository secret or variable. If this repository is **private** or
> internal, mind the plan tiers: environments, environment secrets, and
> deployment branch policies need GitHub **Pro, Team, or Enterprise**, while
> **required reviewers and wait timers need Enterprise**. Public repositories
> get all of it on every plan. Below the required tier nothing errors — the
> environment is created and the rule is silently not enforced, which looks
> identical to a working gate in the settings UI. See
> [docs/adoption.md#deployment-environments](adoption.md#deployment-environments)
> for the full setup and caveats.

## 3. Repository variables

Settings → Secrets and variables → Actions → **Variables** (used by later stages;
create them now so the stubs' documentation stays true):

| Variable | Default | Meaning |
|---|---|---|
| `WING_COMMANDER_PLAN_REVIEW` | `pr` | `pr` = open a plan PR and wait for a human merge; `auto` = commit the plan directly and dispatch the tasks stage |
| `WING_COMMANDER_TASKS_REVIEW` | `auto` | `auto` = commit tasks.md straight to the spec branch; `pr` = open a tasks PR |
| `WING_COMMANDER_IMPLEMENT_MODEL` | `claude-sonnet-5` | Model for implement/converge; set `claude-opus-5` for hard specs |
| `WING_COMMANDER_SPEC_MODEL` | `claude-opus-5` | Model for the spec/clarify tier (intake and clarify stages) |
| `WING_COMMANDER_PLAN_MODEL` | `claude-sonnet-5` | Model for the plan/tasks tier (plan, tasks, and rebase stages) |
| `WING_COMMANDER_SUMMARY_MODEL` | `claude-haiku-4-5` | Model for the triage/summary tier (finalize, cleanup, and implement's progress comments) |
| `WING_COMMANDER_DIAGNOSE_MODEL` | `claude-opus-5` | Model for the watchdog's diagnose step. Its own knob, not the summary tier's — diagnose adjudicates multi-signal evidence against a strict schema and needs the headroom |
| `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` | `claude-opus-5` | Model for implement's one-tier-up retry after a failed attempt |
| `WING_COMMANDER_SPEC_DRAFT_PREFIX` | `spec-draft/` | Branch prefix for the draft spec branch (default `spec-draft/`) |
| `WING_COMMANDER_SPEC_PREFIX` | `spec/` | Branch prefix for the persistent spec branch (default `spec/`) |
| `WING_COMMANDER_PLAN_PREFIX` | `plan/` | Branch prefix for the plan branch (default `plan/`) |
| `WING_COMMANDER_TASKS_PREFIX` | `tasks/` | Branch prefix for the tasks branch (default `tasks/`) |
| `WING_COMMANDER_IMPL_PREFIX` | `impl/` | Branch prefix for the implement branch (default `impl/`) |
| `WING_COMMANDER_MAX_ITERATIONS` | `5` | Cap on implement ⟲ converge loops per spec |
| `WING_COMMANDER_WATCHDOG_PAUSED` | unset (not paused) | `true` = kill switch. Read in two places: the *wrapper* workflows (`wing-commander-8-watchdog.yml`, `wing-commander-8b-watchdog-self.yml`) gate on it so **no job starts at all** — nothing inspected, no agent invoked, nothing written; the published `watchdog.yml` stage also still suppresses every write, as a deprecated compatibility shim for adopters whose wrapper has no such gate. Gate your wrapper: the stage-side shim stops writes but not work, so the agents still run and bill. The shim is scheduled for removal in the watchdog rework's next major |
| `WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` | `3` | Max consecutive watchdog-inspects-watchdog runs before the chain stops writing (bounds a self-inspection loop); the run is still inspected and reported |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED` | unset (not paused) | `true` = kill switch for the Spec Kit auto-updater. Read wrapper-side (`wing-commander-auto-update-spec-kit.yml`'s job-level `if:`) so no job starts at all — nothing detected, no agent invoked, nothing written |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS` | `1` | Consecutive daily checks a newly detected upstream version must be observed unchanged before an upgrade is prepared (a settle window, not a fixed calendar delay). Raise it to let a fast-moving patch stream settle longer |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL` | `claude-sonnet-5` | Model for the auto-updater's `evaluate-path` judgment step (clean-bump / needs-migration / ambiguous-options) |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL` | `claude-sonnet-5` | Model for the `e2e-stage` disposable smoke-test agent step (minor/major candidates only) — a cheaper tier than a foundational spec, since its output is asserted only for existence/shape and never read by a human |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MAX_TURNS` | `20` | Max turns for the `e2e-stage` agent step |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO` | unset | `OWNER/NAME` of a **pre-created**, disposable repository the `e2e-stage` scaffolds each candidate into, on a branch it force-resets per run. Create one empty private repository by hand and install the wing-commander App on it (Contents: read and write is all it needs) — the App installation is what the job needs, because `e2e-stage` mints a second installation token scoped to that repository alone; if it lives under a different owner than this repository, the App needs its own installation there. The pipeline never creates or deletes repositories — an App installation token cannot create one on a user account, and the `Administration: write` needed to delete one would also let every stage delete *this* repository. Unset, minor/major candidates fail verification and are not adopted; patch candidates are unaffected |
| `WING_COMMANDER_PR_CONVERSATION_MODEL` | `claude-sonnet-5` | Model for the PR conversation stage's classify and act steps; a PR's `model:opus` label escalates to `claude-opus-5` regardless |
| `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` | unset (act-then-report for every category) | Comma-separated `RequestClassification.category` values requiring propose-and-confirm before `act` mutates anything, or the literal `all`. Spaces around the commas and a trailing comma are tolerated; an unrecognised category name is silently ignored, so check spelling against `contracts/classification-schema.md` |
| `WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT` | `pr-conversation-confirm` | Deployment environment name the `act` job binds to for a classification requiring confirmation |
| `WING_COMMANDER_RUNNER` | `ubuntu-latest` | Runner label every stage job runs on — a single label, or a JSON array (e.g. `["self-hosted","linux","x64"]`) applied as a conjunction — see [docs/adoption.md](adoption.md#runners-and-container-images) |
| `WING_COMMANDER_CONTAINER_IMAGE` | unset (no container) | Container image every stage job runs inside; empty means every job runs directly on the runner, unchanged from today — see [docs/adoption.md](adoption.md#runners-and-container-images) |

The watchdog reads no consuming-repo config file. It is a pure reporter: it
files, comments on, or reopens one `pipeline-defect` issue per finding and
reports every finding to the lifecycle issue — it proposes no fix diffs and
opens no pull requests, so there is nothing left to allowlist. See
[docs/architecture.md](architecture.md#stage-9--watchdog-watchdogyml-wrapper-wing-commander-8-watchdogyml)
for what it does with each dedup outcome.

## 4. Labels

Create these labels (Issues → Labels):

| Label | Purpose |
|---|---|
| `spec-request` | **The approval gate.** A maintainer applying this to an issue admits it into the pipeline. |
| `stage:spec` | Spec is being drafted / awaiting review |
| `stage:clarify` | Spec has open clarification questions |
| `stage:plan` | Plan PR in flight |
| `stage:tasks` | Tasks being generated |
| `stage:implement` | Implement ⟲ converge loop running |
| `stage:review` | Final PR awaiting human review |
| `stage:done` | Lifecycle complete |
| `model:opus` | Opt this spec's implementation into `claude-opus-5` |
| `disposition:confirmed` | **Watchdog precision.** A maintainer applying this to a `pipeline-defect` issue records that the finding was genuine |
| `disposition:false-positive` | The counterpart: the watchdog's finding was not a real defect |

`spec:<NNN-slug>` and `stage:stalled` labels are created on the fly by the
pipeline — no need to pre-create those, and the same goes for the watchdog's
own `pipeline-defect` and `🐕 · <finding-class>` labels.

The two `disposition:*` labels are the exception among watchdog labels: the
watchdog **never** writes them, so nothing creates them lazily. They are
maintainer-applied dispositions on the issues it files, and they are what its
precision criterion counts — the fraction of the most recent 20 distinct
`pipeline-defect` issues carrying `disposition:confirmed` rather than
`disposition:false-positive` (SC-008 of `specs/015-pipeline-watchdog/`).
Skip them if you do not intend to measure that; nothing else reads them.

Quick script (requires `gh` authenticated with repo scope):

```bash
gh label create spec-request    --color 0E8A16 --description "Maintainer approval: run spec intake on this issue"
gh label create stage:spec      --color 1D76DB --description "Spec drafted / awaiting review"
gh label create stage:clarify   --color 1D76DB --description "Open clarification questions"
gh label create stage:plan      --color 1D76DB --description "Plan in flight"
gh label create stage:tasks     --color 1D76DB --description "Tasks being generated"
gh label create stage:implement --color 1D76DB --description "Implement/converge loop running"
gh label create stage:review    --color FBCA04 --description "Final PR awaiting review"
gh label create stage:done      --color 5319E7 --description "Lifecycle complete"
gh label create model:opus      --color D93F0B --description "Use claude-opus-5 for implementation"
gh label create disposition:confirmed      --color 0E8A16 --description "Watchdog finding confirmed genuine by a maintainer"
gh label create disposition:false-positive --color B60205 --description "Watchdog finding judged a false positive by a maintainer"
```

## 5. Smoke test

1. Open an issue describing a small feature in plain language.
2. Apply the `spec-request` label.
3. Watch Actions → *Wing Commander · 1 intake*. Within a few minutes you should have:
   - a PR titled `Spec: … (#N)` targeting `main`,
   - `spec:NNN-slug` + `stage:spec` labels on the issue,
   - either a PR link comment or a `## 🔍 Clarification needed` comment.
4. If there were clarification questions, reply to the comment (as the issue
   author or a maintainer) — *Wing Commander · 2 clarify* folds your answers into the
   draft PR and confirms on the issue.
5. Review the spec PR; merge to accept (later stages take over from there) or
   close to reject.

## Notes

- The pipeline pins **spec-kit** at the `speckit_version` in `.specify/init-options.json`
  (mirrored as `SPECKIT_SUPPORTED_VERSION` in the preflight action). The
  auto-update-spec-kit stage proposes upgrades as PRs; to do one by hand, re-run
  `specify init --here --force --integration claude --script sh` with the newer
  version, move both pins, and re-verify `.specify/scripts` behavior before merging.
- Model usage draws on your Claude subscription limits. Model tiers are set
  by the `WING_COMMANDER_*_MODEL` variables above (spec/clarify default to
  `claude-opus-5`, plan/tasks and implement to `claude-sonnet-5`, summaries
  to `claude-haiku-4-5`), all with bounded `--max-turns`; the implement
  tier's `model:opus` opt-in is where the cost swing is largest.
