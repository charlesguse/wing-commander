# Setup

One-time configuration to bring the speckit pipeline to life in this repository
(or in any repository that adopts it). An adopting repository must first have
its own `specify init` output — `.specify/` (including
`memory/constitution.md`) and `.claude/skills/speckit-*` — because the pipeline
reads all project-specific artifacts from the repository it runs in, never from
speckit-action (see the [README](../README.md#using-this-on-your-own-project)).

## 1. Create the speckit-bot GitHub App

The pipeline performs pushes, PRs, labels, and comments as a dedicated GitHub App
instead of the default `GITHUB_TOKEN`. This is load-bearing, not cosmetic: events
created with `GITHUB_TOKEN` **do not trigger other workflows**, so a pipeline that
used it would silently stop after its first stage. App-authored events chain
normally, and the actor name (`<slug>[bot]`) gives workflows a reliable filter to
avoid reacting to their own actions.

1. GitHub → Settings → Developer settings → **GitHub Apps** → *New GitHub App*
   - Name: `speckit-bot` (any unique name works; the slug becomes the actor name)
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
| `SPECKIT_APP_ID` | yes | The App ID from step 1 |
| `SPECKIT_APP_PRIVATE_KEY` | yes | Full contents of the downloaded `.pem` |

Both Claude credentials are first-class: every stage accepts either, exactly
one is sufficient, and if you configure both the API key is used (Claude
Code's own
[authentication precedence](https://code.claude.com/docs/en/authentication#authentication-precedence)).
With neither configured, stages fail fast in a preflight step naming both
secret names, before any agent cost. Details:
[docs/adoption.md#credentials](adoption.md#credentials).

## 3. Repository variables

Settings → Secrets and variables → Actions → **Variables** (used by later stages;
create them now so the stubs' documentation stays true):

| Variable | Default | Meaning |
|---|---|---|
| `SPECKIT_TASKS_REVIEW` | `auto` | `auto` = commit tasks.md straight to the spec branch; `pr` = open a tasks PR |
| `SPECKIT_IMPLEMENT_MODEL` | `claude-sonnet-5` | Model for implement/converge; set `claude-opus-4-8` for hard specs |
| `SPECKIT_MAX_ITERATIONS` | `5` | Cap on implement ⟲ converge loops per spec |

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
3. Watch Actions → *speckit · 1 intake*. Within a few minutes you should have:
   - a PR titled `Spec: … (#N)` targeting `main`,
   - `spec:NNN-slug` + `stage:spec` labels on the issue,
   - either a PR link comment or a `## 🔍 Clarification needed` comment.
4. If there were clarification questions, reply to the comment (as the issue
   author or a maintainer) — *speckit · 2 clarify* folds your answers into the
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
