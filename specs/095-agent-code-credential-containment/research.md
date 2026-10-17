# Research: Agent-Authored Code Never Runs Beside the Loop's Write Token

Phase 0 output. Spec 095 carries no `[NEEDS CLARIFICATION]` markers, but two
questions were left open in its 2026-09-30 status update (owner questions 1
and 2). Those, and every fact the spec cites by line number, were re-read
against current `main`. Line numbers in the spec have drifted; this file
cites what is on the branch now.

## R1. Path 3 is already closed on `main`

- **Finding**: `wing-commander-board-stop-check/action.yml` invokes
  `python3 -I "$GITHUB_ACTION_PATH/../../scripts/board_stop_check.py"`
  (lines 159 and 320). `$GITHUB_ACTION_PATH` is the action's own directory,
  and spec 086 resolves that action from `.wc-pristine-repo`, so the script
  is the trusted commit's copy. A grep for `python3 .github/scripts` in the
  composite finds nothing. The spec's status update ("still runs
  `python3 .github/scripts/board_stop_check.py` from the workspace") is stale.
- **Decision**: FR-012 is already satisfied. The work that remains for FR-011
  to FR-014 is the *gate* (FR-013/FR-014): Gate 98 reads only `run:` blocks in
  `board-loop.yml` and Gate 104 reads only `uses:` references, so nothing
  stops a later edit from reintroducing a workspace-relative call inside a
  composite. No behavioural change to the composite.
- **Rationale**: Re-implementing a fix that exists would violate FR-023's
  spirit and Principle VIII (a gate that cannot fail its subject).
- **Alternatives**: Treat FR-012 as open work and rewrite the invocation —
  rejected, it is already the target form.

## R2. Containment topology: a credential-free job per call site

The spec fixes the strategy (Q2 = A). The planning question is how a separate
job gets the agent's tree, because the agent's working tree lives in the
credential-bearing job.

- **Decision**: The credential-bearing job ends its agent phase by uploading
  a **workspace bundle** — a `git bundle` of `<base-sha>..HEAD` plus the
  recorded `head-sha` — as an artifact. A `gate-suite` job
  (`permissions: contents: read`, no `create-github-app-token`, no
  `wing-commander-context`) checks out the trusted commit with
  `persist-credentials: false`, fetches the bundle, checks out the bundle's
  head, runs `run-local-gates.py`, and uploads a **verdict artifact**
  (contract: `contracts/gate-verdict.schema.json`). A later
  credential-bearing job downloads bundle and verdict, checks the verdict,
  and pushes.
- **Rationale**: A separate job is the only candidate that closes FR-007 and
  FR-008 too (own filesystem, own `$GITHUB_ENV`, own `$GITHUB_PATH`). A bundle
  is content-addressed: the verdict names the head SHA it judged, and the
  publisher refuses to push any other SHA. That closes the swap between
  "gated" and "pushed".
- **Alternatives**: (a) scrub env in place — leaves `$GITHUB_ENV`/snapshot
  rewrite open; (b) container/user-namespace sandbox around the suite —
  costs more for the same guarantee (both rejected on #737); (c) push the
  tree to a scratch ref for the gate job to fetch — needs a write token
  before the verdict, defeating the point.

## R3. Verdict binding and fail-closed reader

- **Decision**: One reader, `wc_gate_verdict.py` (single home), validates the
  artifact: schema-valid, `head_sha` equals the SHA about to be pushed,
  `trusted_sha` equals `github.sha`, `outcome ∈ {pass, fail}`. Everything
  else — missing artifact, unreadable file, wrong keys, SHA mismatch, an
  `outcome` of anything but the two literals — is emitted as `outcome=fail`
  with `first-failure` naming the reason (FR-004). The first-failure text
  continues through `wc_step_output.py first-failure` for control-character
  stripping and `fenced_section()` for fencing (FR-003); the reader does not
  re-implement either.
- **Rationale**: The `gate-suite` job can fail, be cancelled or time out
  without writing an artifact; the publisher must read absence as red, so the
  publisher's `needs:` uses `if: !cancelled()` and the reader treats a missing
  file as `fail` rather than the step being skipped. Apply the
  `review-step-gating` skill to every new `if:`.

## R4. Which call sites, and what each needs

| Site | Today | Containment shape |
|------|-------|-------------------|
| board-loop `fix` (fixer gate suite) | step in `fix`, before push | bundle → `gate-suite` job → publish steps read verdict |
| board-loop review-fixup | step in `review`, before push | same |
| implement "cycle" | step at job start, `continue-on-error`, verdict feeds the agent's prompt | `gate-suite` job runs *before* the implement job on the spec branch head; verdict is prompt input only (no push decision) |
| implement "retry" | step after the cycle agent, `continue-on-error`, feeds retry prompt | needs a bundle of the cycle's output; see R6 |
| `pr-conversation` | no gate-suite step | FR-001/FR-006 not applicable; FR-018 only |

Note the line numbers the spec gave (`board-loop.yml:2236`, `implement.yml:796`)
have moved: the fixer step is now at `board-loop.yml:3000`, review-fixup at
`~4379`, cycle at `implement.yml:955`, retry at `~1800`.

## R5. Open owner question 1 — scope narrowing

The 2026-09-29 owner note says clarify "should scope to the gate suite and the
`.git` hardening". No answer was recorded. Decision, per the CI deviation: **keep
all four paths and the Q1 widening**, because dropping any would leave a path
unaddressed against SC-007, and the board loop's own structure is why: FR-007
and FR-008 come for free from the separate job (R2) rather than costing extra
work. Path 3 shrinks to the gate (R1). This is a *decision made without
clarification* and is flagged in the issue comment.

## R6. Open owner question 2 — agent-invoked gates and agent pushes

The implement agent holds `Bash(python3 .github/scripts/run-local-gates.py:*)`
and `Bash(python3 .github/scripts/verify-*)`, and `github_token:` is the App
token. Agent-invoked gates therefore run beside the token; a separate job
cannot contain a command the agent runs mid-session.

- **Decision**: **Out of scope for 095, recorded as a deferral on #737**
  (SC-007 permits an explicit, recorded deferral). It is bounded by spec 111
  (#815), which removes the write credential from agent steps that do not need
  it; 095 must not restate that requirement. The push-hardening idiom (R7)
  *is* applied to the two agent-issued pushes where the workflow controls the
  environment (the agent step's `env:`); where the agent composes the command
  itself it is not reachable and the deferral says so.
- **Implement retry** (R4): if retry runs in the same job as the cycle agent,
  the bundle is produced after the cycle agent step and the retry gate
  becomes a downstream job; if that restructuring is disproportionate, retry
  is deferred together with this question. Tasks decide after reading the
  job graph; the plan commits only to cycle + board-loop sites.

## R7. Git hook / config hardening (FR-015 to FR-018)

- **Decision**: One helper, the composite `wing-commander-hardened-push`
  (under `.github/actions/`, script in `_shared/`), wraps the push:
  `git -c core.hooksPath=/dev/null push <explicit-url> HEAD:refs/heads/<b>`
  with `GIT_CONFIG_GLOBAL=<pristine empty file>`, `GIT_CONFIG_NOSYSTEM=1`,
  and an explicit authenticated URL built from `$GITHUB_REPOSITORY` and
  `github.server_url` rather than `origin`. Repo-level config
  (`.git/config`) is not disabled by `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_NOSYSTEM` — , so the helper also sets
  `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` overrides for
  `core.hooksPath` (command-line and env config outrank repo config). Whether
  an env override neutralises a planted `url.<base>.insteadOf` is not assumed:
  the fixture plants one and a task confirms the push still reaches the
  stated URL; if it does not, the fallback is pushing from a freshly
  `git init`-ed shim repository holding only the pushed objects. Verified by
  fixture (planted hook and `insteadOf`).
- **Rationale**: One home for the idiom (FR-022); call sites keep a
  one-line fallback only per CLAUDE.md. The push sites are `board-loop.yml:3089`
  and `~4415`, and `implement.yml:3161`.
- **`.git/**` deny (FR-018 first half)**: added to the shared deny set that
  spec 090's write-boundary composite defines for implement (an entry, not a
  second literal list), and to the `default-disallowed-tools` of the fixer,
  review-fixup and `pr-conversation.act`. `verify-stage-tool-lists.py` already
  documents every site's disallowed list; the new gate asserts `.git/**`
  appears (as `Edit(.git/**)`, `Write(.git/**)`) at every covered label.

## R8. Gate-suite read-access audit (spec Assumption)

Scripts under `.github/scripts/verify-*` were surveyed for `gh `, `GH_TOKEN`
and `git fetch` use. The audit is a task (T-audit), because a conclusion
needs running the suite with the token unset; the gate job grants
`contents: read` and a read-only `github.token`, which covers read-only API
use. Any gate found needing a write credential is a defect to fix before
shipping, not an exemption.

## R9. Snapshot caveats (FR-009/FR-010)

`chmod -R a-w` is advisory against the same user. After R2 the snapshot is
trusted because the *only* agent-code execution in the credential-bearing
job's lifetime moved to another runner; the comment documenting the snapshot
states exactly that and the runner assumption (each job gets a fresh VM;
self-hosted runners must be ephemeral or this protection is conditional).
Prior-art gates 98 and 104 stay.

## R10. In-flight items

A board item cut before this ships reaches the changed jobs afterwards.
Because the gate job consumes a bundle the *same run* produced, no stored
state crosses versions, so nothing hard-fails (spec 086's failure mode).

## Decisions made without clarification

1. Kept all four paths and the Q1 widening (R5).
2. Path 3 treated as already closed; only its gate is built (R1).
3. Agent-invoked gates / agent-issued pushes deferred, recorded on #737 (R6).
4. Implement retry site committed conditionally (R6).
