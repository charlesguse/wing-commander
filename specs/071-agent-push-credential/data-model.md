# Phase 1 Data Model: The Agent's Own Push Credential Outlives Its Cycle

This feature introduces no new persisted data store. Every shape below is
ephemeral (a job-scoped file, environment variable, or step/job output,
gone when the runner is destroyed) or a static reference-shape rule a gate
checks against the shipped YAML/shell. `spec-meta.json`'s schema is
untouched.

## `WC_AGENT_PUSH_APP_ID` / `WC_AGENT_PUSH_KEY_PATH` / `WC_AGENT_PUSH_OWNER` / `WC_AGENT_PUSH_REPO` (job-scoped environment variables, new)

| Property | Value |
|---|---|
| Written by | `wing-commander-agent-push-credential`'s setup step, once per call (once per agent step in `implement.yml`, since each of its three agent steps gets its own installation) |
| Read by | `mint-credential.sh`, invoked by git's `credential.helper` mechanism as a subprocess of whichever step (agent or deterministic) next needs to authenticate to `https://github.com/...` |
| Lifetime | One job run. `WC_AGENT_PUSH_KEY_PATH` names a file under `$RUNNER_TEMP`, `chmod 600`, never logged (research.md D4) |
| Scope | Every in-scope stage's job that calls `wing-commander-agent-push-credential` before an agent step whose allowed-tools include `Bash(git push:*)` |

## `$RUNNER_TEMP/wc-agent-push-installation-id` (job-scoped cache file, new)

| Property | Value |
|---|---|
| Written by | `mint-credential.sh`, on its first invocation in a job, after resolving the installation id via `GET /repos/{owner}/{repo}/installation` |
| Read by | Every later invocation of `mint-credential.sh` in the same job, skipping the installation-lookup API call (research.md D3) |
| Lifetime | One job run. Contains only a small integer — never a credential. |

## `credential.https://github.com.helper` (git config, local to the job's checkout — new use of an existing git mechanism)

| Property | Value |
|---|---|
| Set by | `wing-commander-agent-push-credential`'s setup step, after clearing the stale `http.https://github.com/.extraheader` `actions/checkout@v5` left (the same clearing `wing-commander-refresh-remote` already performs, research.md D2 of specs 052) |
| Value | An absolute path to `mint-credential.sh` inside the pipeline repository's self-checkout (`.wing-commander-pipeline/.github/actions/wing-commander-agent-push-credential/mint-credential.sh`), prefixed `!` per git's "shell command" credential-helper convention |
| Consumed by | git itself, on every `https://github.com/...` operation that needs a credential and has none cached — no caller in this repository invokes it directly |
| Never confused with | `env.WC_BOT_TOKEN` (spec 052) — that variable authenticates every *deterministic* step's own `gh`/`git` calls via an explicit `token:`/`GH_TOKEN` input; this git-config entry authenticates only the agent's own ad hoc `git push` calls (and, incidentally, the new stranded-commit publish step's push, which also benefits from a fresh credential at no extra design cost) |

## Mint attempt (ephemeral — not modeled as persisted state)

| Field | Meaning |
|---|---|
| Success | stdout carries exactly `username=x-access-token\npassword=<token>\n`; exit 0 |
| Failure | stdout empty; stderr begins `wing-commander-agent-push-credential: mint failed: <reason>`; exit 1 (research.md D6) |

`<reason>` is one of: `installation-lookup-failed`, `token-mint-failed`,
`key-unreadable` — a closed, small enumeration, never free-form prose, so a
later deterministic check can match on it without guessing at phrasing.

## Retry-bound prompt paragraph (new — published text, not a data shape)

One canonical copy, at `clarify.yml` (this repository's existing home for
canonical prompt/comment prose, Gate 47-enforced pointer convention),
appended to every in-scope stage's `prompt:` block. Presence is a binary
per call site: published (agent step's allowed-tools include `Bash(git
push:*)`) or absent (FR-025 — no cost where nothing can push). No
model-authored variant of the text exists; every call site quotes the
canonical paragraph verbatim or points at it, matching CLAUDE.md's
"Repeated comment prose gets ONE canonical comment" rule as applied to
prompt prose.

## Stranded-commit publish step (new — one per existing post-agent refresh triple)

| Field | Type | Meaning |
|---|---|---|
| `commits-published` (step output) | integer (string) | `git rev-list --count <before-sha>..HEAD` computed immediately before the push, where `<before-sha>` is the same "spec branch before this agent step ran" SHA `implement.yml`'s existing convergence-signal step already records (`implement.yml:2428`'s `before_sha`/`after_sha` pattern, reused rather than re-derived) |
| `push-ok` (step output) | `"true"` \| `"false"` | Whether the deterministic push itself succeeded. `"false"` on a genuine race (e.g. a concurrent auto-rebase force-push) — reported, never hard-failing the job (research.md D8, `continue-on-error: true`) |

**Publication scope**: one call per existing post-agent `wing-commander-
context` re-mint across the 8 in-scope stages (three in `implement.yml`,
one each elsewhere) — the same footprint as spec 052's own post-agent
refresh triple, since this step runs immediately alongside it.

**Consumption**: each stage's existing stall-path callout (spec 041's
`wing-commander-chain-stop-notice` family) gains one optional line, present
only when `commits-published` is nonzero — "N commit(s) the agent could
not push during the run were published after it" — following the same
"appears only when there is something to report" convention
`wing-commander-post-agent-credential-status`'s `ok=false` warning already
established (FR-016/FR-017).

## Mint-failure attribution (new — FR-006)

| Field | Type | Meaning |
|---|---|---|
| `mint-failure-detected` (job output, per in-scope job) | `"true"` \| unset | Set by a deterministic grep over the agent step's uploaded execution-output artifact (or, if the implement stage instead realizes research.md D6's structured-file alternative, a direct file read) for the literal `wing-commander-agent-push-credential: mint failed:` prefix |
| Consumed by | The stall path's existing ok-first check (docs/architecture.md), extended to read this output on the same terms it already reads `credential-refresh-ok` (spec 052) — attributing a later real failure to a mint failure rather than to the agent or an unrelated downstream step |

No prose field, matching spec 052's own `agent-ran`/`agent-conclusion`
precedent (FR-014's cross-feature analogue): the diagnostics artifact each
stage's stall path already downloads remains the sole carrier of
model-authored text.

## Gate registry entries (new)

| Gate | Script | Wired into | Proves |
|---|---|---|---|
| 99 (provisional — highest at plan time is 98; may renumber, per spec 052's Gate 68 precedent) | `.github/scripts/verify-agent-push-credential-helper.py` | `.github/workflows/lint-workflows.yml`, PR-time job | FR-020 (every push-capable agent step has the credential-helper install and the stranded-commit publish step), FR-021 (reachable, same subject/arguments locally and in CI), FR-022 (fails loudly on an unreachable subject, triggered by the paths it already covers), FR-023 (single-home: no second minting-shell copy outside its own composite directory) |
| 100 (provisional, immediately following 99, mirroring the Gate 68/69 split) | `.github/scripts/verify-agent-push-credential-shell.py` | `.github/workflows/lint-workflows.yml`, PR-time job | Behavioural proof Gate 99 cannot provide statically: `mint-credential.sh`'s JWT construction against a fixed test keypair and a stubbed `curl`, asserting the emitted `username=`/`password=` pair is well-formed |

See `contracts/agent-push-credential-gate.md` for each check's exact
structure and required mutations.
