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

## 3. Repository variables

Settings → Secrets and variables → Actions → **Variables** (used by later stages;
create them now so the stubs' documentation stays true):

| Variable | Default | Meaning |
|---|---|---|
| `WING_COMMANDER_PLAN_REVIEW` | `pr` | `pr` = open a plan PR and wait for a human merge; `auto` = commit the plan directly and dispatch the tasks stage |
| `WING_COMMANDER_TASKS_REVIEW` | `auto` | `auto` = commit tasks.md straight to the spec branch; `pr` = open a tasks PR |
| `WING_COMMANDER_IMPLEMENT_MODEL` | `claude-sonnet-5` | Model for implement/converge; set `claude-opus-4-8` for hard specs |
| `WING_COMMANDER_MAX_ITERATIONS` | `5` | Cap on implement ⟲ converge loops per spec |
| `WING_COMMANDER_WATCHDOG_PAUSED` | unset (not paused) | `true` = kill switch: the watchdog still inspects and reports, but performs **no** autonomous write (no PR, issue, comment, or reopen) at any rung until you clear it |
| `WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` | `3` | Max consecutive watchdog-inspects-watchdog runs before the chain stops writing (bounds a self-inspection loop); the run is still inspected and reported |

The watchdog also reads one consuming-repo-owned config file,
`.specify/memory/watchdog-guardrails.json`, which defines the change-class
allowlist and per-class line caps that gate its lightest-touch autonomous
fixes (rung 1). It is read-only from the watchdog's perspective — edit it via
an ordinary PR to your default branch like any other file; a change-class
absent from it (or the file missing entirely) simply makes that class
ineligible for a rung-1 fix, never inventing a default. See
[docs/architecture.md](architecture.md#stage-9--watchdog-watchdogyml-wrapper-wing-commander-8-watchdogyml)
for the full triage ladder.

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
| `model:opus` | Opt this spec's implementation into `claude-opus-4-8` |

`spec:<NNN-slug>` and `stage:stalled` labels are created on the fly by the
pipeline — no need to pre-create those.

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
gh label create model:opus      --color D93F0B --description "Use claude-opus-4-8 for implementation"
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

- The pipeline pins **spec-kit v0.12.4** (see `.specify/init-options.json`). To
  upgrade, re-run `specify init --here --force --integration claude --script sh`
  with the newer version and re-verify `.specify/scripts` behavior before merging.
- Model usage draws on your Claude subscription limits. Intake/clarify run on
  `claude-sonnet-5` with bounded `--max-turns`; the heavy stages are where
  Opus opt-in matters.
