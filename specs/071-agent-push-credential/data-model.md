# Phase 1 Data Model: The Agent's Own Push Credential Outlives Its Cycle

This feature introduces no new persisted data store. Every shape below is
ephemeral (a job-scoped file, environment variable, or step/job output,
gone when the runner is destroyed) or a static reference-shape rule a gate
checks against the shipped YAML/shell. `spec-meta.json`'s schema is
untouched.

**Superseded 2026-09-29 (everything up to "Stranded-commit publish step";
tasks.md T057, Maintainer Feedback)**: the credential-helper mechanism
described below (`WC_AGENT_PUSH_*` env vars, the installation-id cache
file, the `credential.https://github.com.helper` git-config entry, the
mint attempt/mint-failure shapes, `mint-credential.sh` itself) was deleted
as a security defect — it staged the GitHub App's own private key where a
running agent step's shell could read it. Kept below as the historical
record of the rejected design. The retry-bound prompt paragraph and the
"Stranded-commit publish step" section both survive largely as described
(the paragraph dropped its now-nonexistent mint-failure clause; the
publish step was always a deterministic step independent of the
credential-helper mechanism around it, and gained a `push-ok`-aware
consumer at 3 more call sites and an origin-ref-based count, per the
maintainer review of PR #720). "Mint-failure attribution" has no
remaining subject — there is no agent-visible mint failure once nothing
mints on the agent's behalf — and was removed along with the composite
that produced it. The Gate registry table at the bottom is rewritten to
match what actually shipped.

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

## Mint-failure attribution (SUPERSEDED — removed, no remaining subject)

Described a `mint-failure-detected` job output, grepped from the agent
step's transcript for the deleted composite's own stderr signature. Once
nothing mints an installation token on the agent's behalf, there is no
agent-visible mint failure left to detect — the composite that would have
produced this output (`wing-commander-agent-push-credential-status`) and
`wing-commander-stall-reason`'s `push-credential-mint-failed` input/branch
were both removed in the same redesign (tasks.md T057, T062).

## Gate registry entries

| Gate | Script | Wired into | Proves |
|---|---|---|---|
| 122 (renumbered three times: a provisional 99 at plan time — highest at plan time was 98 — became 120 when main claimed 99 for spec 059 and 100 for spec 079 before this branch first landed, per spec 052's Gate 68 precedent for renumbering; main then claimed 120 too, for the dedup-key-rule gate, so this pair moved again to 122/123 (tasks.md T056); Gate 123 was then retired (T063) when the redesign (T057) deleted its subject, leaving 122 as the sole survivor with a rewritten check 1) | `.github/scripts/verify-agent-push-credential-helper.py` | `.github/workflows/lint-workflows.yml`, PR-time job | FR-020 (every push-capable agent step has a stranded-commit publish step; the App private key is never staged where a running agent step could reach it, across every workflow file — T069), FR-021 (reachable, same subject/arguments locally and in CI), FR-022 (fails loudly on an unreachable subject, triggered by the paths it already covers), FR-023 (single-home: no JWT-signing shell anywhere in the repository) |
| 123 (retired T063, then reused for a new, unrelated subject by the maintainer review of PR #720 — T070 — rather than left reserved) | `.github/scripts/verify-stranded-commit-publish-shell.py` | `.github/workflows/lint-workflows.yml`, PR-time job | Behavioural proof no static check can provide: `wing-commander-publish-stranded-commits`' own `commits-published` count (the origin-ref comparison, falling back to before-sha..HEAD) driven against a real bare `origin` plus a clone |

See `contracts/agent-push-credential-gate.md` for each check's exact
structure and required mutations.
