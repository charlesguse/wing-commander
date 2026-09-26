# Contract: `wing-commander-agent-push-credential` + `mint-credential.sh`

**Files**: `.github/actions/wing-commander-agent-push-credential/action.yml`
(composite, new), `.github/actions/wing-commander-agent-push-credential/
mint-credential.sh` (shell script, new, colocated — never referenced from
outside its own composite's directory, per Gate 99 check 3).

## Composite interface

**Inputs**:

| Input | Required | Meaning |
|---|---|---|
| `app-id` | yes | GitHub App ID (`secrets.speckit-app-id`, same secret every other mint in this repository already uses) |
| `private-key` | yes | GitHub App private key (`secrets.speckit-app-private-key`) |
| `owner` | yes | Target repository's owner — `github.repository_owner` for the pipeline's own remote, the scratch repository's owner for the end-to-end arm (research.md D9) |
| `repo-name` | yes | Target repository's name, same owner/repo-name split `scoped-app-token` already uses |

**Outputs**: none. This composite's only effect is a git-config side
effect (`credential.https://github.com.helper`) inside the caller's
existing checkout — nothing downstream reads a step output from it, unlike
every other composite in this fleet, because its consumer is git itself,
not a later workflow step.

**What it does** (composite `runs.steps`, in order):

1. Write `inputs.private-key` to `$RUNNER_TEMP/wc-agent-push-credential-
   <run-id>-<step-id>.pem` (a run/step-scoped filename — `implement.yml`
   calls this composite up to three times per job, and each call's key
   file must not collide with, or be overwritten mid-use by, another),
   `chmod 600`.
2. Clear the stale `http.https://github.com/.extraheader` config entry
   `actions/checkout@v5` wrote (identical to `wing-commander-refresh-
   remote`'s existing first line) — required because that header, not the
   remote URL or a credential helper, is what git's http transport tries
   FIRST, and it would otherwise silently override the helper this
   composite is about to install.
3. `git config --local credential.https://github.com.helper` — reset to
   empty, then set to `!<absolute path to mint-credential.sh>`, per git's
   own "shell command" credential-helper convention (a `!`-prefixed value
   is run through the shell rather than looked up as `git-credential-
   <name>`).
4. Export `WC_AGENT_PUSH_APP_ID`, `WC_AGENT_PUSH_KEY_PATH`,
   `WC_AGENT_PUSH_OWNER`, `WC_AGENT_PUSH_REPO` via `$GITHUB_ENV` (data-
   model.md) — read by `mint-credential.sh` when git execs it later, since
   the composite's own steps and the eventual agent step are different
   processes that share only the job's environment file and the checkout's
   git config.

## `mint-credential.sh` contract

**Invocation**: exec'd by git with `get` on stdin (protocol/host lines)
whenever an outbound `https://github.com/...` git operation needs
credentials it does not already have cached. Never invoked directly by any
workflow step.

**On success**: stdout is exactly

```
username=x-access-token
password=<freshly minted installation token>
```

exit 0.

**On failure** (installation-lookup 4xx/5xx, token-mint 4xx/5xx, or the key
file at `$WC_AGENT_PUSH_KEY_PATH` missing/unreadable): stdout empty,
stderr's first line is `wing-commander-agent-push-credential: mint failed:
<reason>` where `<reason>` is one of the closed enumeration in data-
model.md, exit 1. Never retries internally — retry policy for the *agent's*
own next push attempt is the prompt guidance (research.md D7), not this
script's job.

**Never**: writes the private key, the JWT, or the minted token to stdout
on any path other than the single `password=` line on success; never
echoes to a step log (the script runs as git's own subprocess, not a
`run:` step, so nothing it prints reaches `$GITHUB_STEP_SUMMARY` — but its
stderr does reach the enclosing agent step's own transcript, which is the
mechanism the retry-bound prompt guidance and the mint-failure-attribution
check both rely on to see the signature at all).

## Call-site convention (every in-scope stage)

Positioned after the "Checkout spec branch as wing-commander-bot" step (or
that stage's equivalent push-capable checkout) and before the agent step
that pushes. `implement.yml` calls it three times — once before each of
`cycle`, `retry`, `progress` — because each is a distinct agent step whose
own turn budget could independently outlive the App-installation-id cache
window is irrelevant (the id itself does not expire), but whose own
private-key staging step must exist before it, matching the one-call-per-
agent-step shape the existing post-agent refresh triple already uses.

## What Gate 99 checks here

That every job containing an agent step with `Bash(git push:*)` in its
allowed-tools has exactly one call to this composite positioned between
its push-capable checkout and that agent step. See
`agent-push-credential-gate.md`.
