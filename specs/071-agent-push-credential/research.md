# Phase 0 Research: The Agent's Own Push Credential Outlives Its Cycle

Spec Clarifications (session 2026-09-25) already resolved the only two
open questions the spec itself posed (remedy shape, scope of agent steps).
Nothing below reopens those; each decision here is the plan-level "how" for
an FR the spec already fixed the "what" of. No `[NEEDS CLARIFICATION]`
marker remains in spec.md.

## D1 — Mechanism: a git credential helper script, not a periodic remote rewrite

**Decision**: Every agent-bearing job's spec-branch checkout gets one new
step, before its agent step, that (a) clears the stale
`http.https://github.com/.extraheader` `actions/checkout@v5` left (the same
header spec 052's `wing-commander-refresh-remote` already knows is what
git's http transport actually authenticates with — research.md D2 of specs
052) and (b) configures `credential.https://github.com.helper` to a script
that mints a fresh App installation token on every invocation. Git invokes
a configured `credential.helper` once per outbound `https://github.com/...`
operation whose cached credential (if any) is absent or rejected, so from
the agent's perspective nothing changes: it runs `git push` the way it
always has, and the credential underneath it is never more than the time
of one mint old.

**Rationale**: This is FR-002's own wording ("a credential the agent's
remote resolves freshly at the moment of each push") applied literally.
The declined alternative — re-running `wing-commander-refresh-remote` on a
timer from a background process — was never in the running: nothing in
this job can run concurrently with the agent step to keep re-writing the
remote out from under it, and the spec's own Clarifications record the
wall-clock alternative as declined for a different reason (no third way
for an agent step to end). A credential helper is the only mechanism that
runs synchronously with — and only when — git itself needs it.

**Alternatives considered**: A GitHub Actions "sidecar" step running in
parallel with the agent step, polling and rewriting the remote every few
minutes — rejected: `actions/checkout`'s embedded extraheader would still
win over a mid-push race, and coordinating two steps racing the same
`.git/config` file across process boundaries inside a container is a new
failure mode that a credential helper (invoked synchronously, in-process,
by git itself, never racing anything) does not have.

## D2 — Minting inside the helper: sign a JWT with `openssl`, resolve the installation, call the REST API directly

**Decision**: The credential helper cannot invoke `actions/create-github-app-token`
— that is a JavaScript Actions toolkit action, runnable only as a workflow
step, not as a subprocess git can exec mid-push. The helper script instead
does, in shell, what that action does internally:

1. Build a GitHub App JWT: header `{"alg":"RS256","typ":"JWT"}` and payload
   `{"iat": now-60, "exp": now+540, "iss": <app-id>}`, base64url-encode
   both, sign `header.payload` with `openssl dgst -sha256 -sign
   <private-key-file>`, base64url-encode the signature, concatenate.
2. Resolve the installation id for the target repository with `GET
   /repos/{owner}/{repo}/installation` (Bearer: the App JWT) — the same
   repository-scoped resolution `actions/create-github-app-token` performs
   when given `owner`+`repositories`, and a plain read that needs no
   installation permission beyond the App's own identity.
3. Mint a scoped installation token with `POST
   /app/installations/{id}/access_tokens` (Bearer: the App JWT), and emit
   `username=x-access-token` / `password=<token>` on stdout, the shape
   `git credential fill` expects.

**Rationale**: `openssl`, `curl`, and `jq` are already load-bearing
dependencies of this repository's existing workflow steps (e.g.
`implement.yml`'s own "Resolve pipeline ref" step already signs and
decodes an OIDC token by hand with the same toolchain) — no new runner
dependency is introduced for `curl`/`jq`; `openssl` is the one addition,
and it is a standard part of every base image this pipeline's stages have
run against (`ubuntu-latest` and every `container-image` an adopter has
used to date per specs/038). Its presence is verified as part of Phase 1's
quickstart rather than assumed silently.

**Alternatives considered**: Shipping a small Python script using `PyJWT`
or `cryptography` — rejected: those are not stdlib, and adding a `pip
install` step ahead of every agent-bearing job's agent step is exactly the
per-agent-turn-adjacent cost FR-005 forbids introducing casually, plus a
new supply-chain dependency this repository does not otherwise carry.
Resolving the installation id via `actions/create-github-app-token`'s own
`owner`+`repositories` inputs once at job start and threading the numeric
id through to the helper — rejected as an unnecessary two-mechanism split
for a value that costs one cheap, cacheable API call inside the helper
itself the first time it runs (D3 covers the caching).

## D3 — Caching: the installation id is cached per job; the token itself is never cached across pushes

**Decision**: The helper writes the resolved installation id to a file
under `$RUNNER_TEMP` on its first invocation in a job and reads it back on
every later invocation in the same job, skipping step 2 of D2 thereafter.
The installation token itself (step 3) is minted fresh on every
invocation — no caching, no reuse across pushes, per the spec's own
Assumptions ("the chosen remedy mints per push... That volume is
accepted").

**Rationale**: The installation id is a stable property of the App's
installation on this repository (it does not rotate mid-job); caching it
removes eleven-to-seventeen of the twelve-to-eighteen-per-cycle API calls
without touching the one call FR-002 actually requires to be fresh (the
token mint itself). This is a performance detail, not a correctness one —
even without the cache, D2 still satisfies FR-001/FR-002.

## D4 — Credential material reaches the helper the same way `WC_BOT_TOKEN` already reaches every other step: via `$GITHUB_ENV`, plus one private-key file under `$RUNNER_TEMP`

**Decision**: The new setup step (D1) writes the App private key to
`$RUNNER_TEMP/wc-agent-push-credential.pem` with `chmod 600`, and exports
`WC_AGENT_PUSH_APP_ID`, `WC_AGENT_PUSH_KEY_PATH`, `WC_AGENT_PUSH_OWNER`,
and `WC_AGENT_PUSH_REPO` via `$GITHUB_ENV` — the same relay convention
spec 052 established for `WC_BOT_TOKEN` (research.md D1 of specs 052),
because the helper script runs as a subprocess of the *agent* step, which
is a later step in the same job and therefore inherits `$GITHUB_ENV`
exports the same way every step after `wing-commander-context` already
does.

**Rationale**: The private key is a secret; writing it to a step input
alone (rather than a file) would put it on a command line the helper
re-reads on every invocation, and command lines are visible to any process
that can list the container's process table. A `chmod 600` file under
`$RUNNER_TEMP` (already the convention this pipeline uses for scratch
material that must not appear in step logs) is read once per invocation
without ever appearing in `ps`. Owner/repo are threaded as inputs, not
hardcoded to `github.repository`, so the identical composite serves the
end-to-end arm's scratch-repository credential (D9) without a second
implementation.

## D5 — Single home: one composite, one script, parameterized, never duplicated per stage

**Decision**: `.github/actions/wing-commander-agent-push-credential/`
(one new composite, alongside its sibling `mint-credential.sh` script in
the same directory — the composite's `runs.steps` stage the key material
and export the env vars per D4; the standalone shell script is what git
actually execs, since a `run:` step cannot be the target of
`credential.helper`). Inputs: `app-id`, `private-key`, `owner`,
`repo-name` — the same four-input shape `scoped-app-token` already
established for "mint scoped to a repository distinct from (or the same
as) this workflow's own." Every one of the 8 in-scope stages' agent-bearing
jobs calls this one composite; none re-implements the JWT signing or the
credential-helper wiring locally, per CLAUDE.md's single-home rule.

**Rationale**: Consistent with `scoped-app-token`'s own precedent (D2)
and this repository's own stated cost of a pasted-not-shared idiom
(CLAUDE.md's per-run cost line example). `wing-commander-refresh-remote`
and `wing-commander-agent-ran-signal` are the two closest existing
precedents for "one small composite per concern, referenced by every
call site" rather than one large composite acquiring an unrelated new
input.

## D6 — Mint-failure attribution (FR-006): a distinct stderr signature, read by a new post-agent status step, never surfaced as an agent failure

**Decision**: When the helper's mint fails (a non-2xx from either API
call, a missing/unreadable key file, or a non-2xx installation lookup), it
writes nothing to stdout and one line to stderr beginning
`wing-commander-agent-push-credential: mint failed: <reason>`, then exits
1. Git surfaces a helper's non-zero exit as its own authentication
failure, distinguishable from an *expired*-credential rejection because
the message never reaches GitHub at all (no `remote: Invalid username or
token` line — the request was never sent). A new composite,
`wing-commander-agent-push-credential-status`, mirrors
`wing-commander-post-agent-credential-status`'s existing shape (spec 052):
it does not run inline with the agent (nothing can observe the agent
step's live transcript deterministically while it runs), but the agent's
own transcript is already uploaded and read by the existing "Compute agent
run verdict" step; a new deterministic grep for the `mint failed:`
prefix inside the uploaded execution-output artifact, alongside the
existing verdict computation, sets a `mint-failure-detected` output the
stall path reads on the same terms `wing-commander-post-agent-credential-
status`'s `ok` output already is (docs/architecture.md's existing
ok-first check).

**Rationale**: FR-006 requires attribution "to the credential and the site
that needed it," and "not reported as an agent failure." A literal,
grep-able prefix that only this helper ever emits is a deterministic fact
a later step can check without asking a model to judge it (Constitution
Principle IX) — the same shape `wing-commander-agent-ran-signal` already
uses (`steps.<id>.outcome`, not a model's own account of what happened).

**Alternatives considered**: Having the helper write a structured file
(e.g. JSON) to `$RUNNER_TEMP` on failure, read directly rather than grepped
from the transcript — deferred to the implement stage as an equally valid
realization of the same contract; either satisfies this research decision,
so the plan does not force one over the other. The gate (D10) checks for
the *stderr signature's existence in the script*, not which of the two
downstream read mechanisms consumes it.

## D7 — FR-010–FR-014: a short, single-homed prompt addition, not a new tool or a new judgment

**Decision**: Every agent-bearing job whose agent step's allowed-tools
include `Bash(git push:*)` gets one short paragraph appended to its
`prompt:` block (canonical copy at `clarify.yml`, per this repository's
existing canonical-comment convention — Gate 47 already enforces pointer
consistency for prose like this): *"A `git push` that fails with `remote:
Invalid username or token` or `Authentication failed`, or with a message
beginning `wing-commander-agent-push-credential: mint failed:`, is a
credential problem this pipeline is already handling — retry it at most
twice, then commit your work locally if it still fails and continue; do
not spend further turns retrying the same push."* Stages whose agent step
never pushes (FR-025) receive neither this text nor the D5 composite call.

**Rationale**: This is guidance about behaviour the agent already
exhibits (retrying a failed push), narrowed to one recognisable, literal
signature — not a new judgment call the model must make (the spec's Out
of Scope is explicit: "nothing in this feature asks a model to decide
whether a credential expired"). The bound is two retries (three attempts
total including the first): small enough that SC-004 ("no more than the
stated bound... against the ten further attempts observed") is easy to
verify by counting matching Bash tool calls in a seeded transcript, large
enough that a single flaky network blip (Edge Cases: "a transient network
error") is not mistaken for the credential signature by an agent that
gives up on the very first retry.

**Alternatives considered**: A tool-result hint injected by wrapping the
`Bash(git push:*)` tool itself — rejected: this pipeline's agent tool
surface is `claude-code-action`'s own allowed-tools list, not a custom
tool this repository controls the result-formatting of; a prompt addition
is the only lever available without forking the action.

## D8 — FR-015–FR-018: a new, genuinely deterministic "publish any commits the agent could not push" step, not a rename of the existing remote refresh

**Decision**: Immediately after each agent step's existing post-agent
`wing-commander-context` re-mint (spec 052), a new step —
`wing-commander-publish-stranded-commits` — runs `git push` unconditionally
against the now-freshly-credentialed remote (D1's helper is *also* still
installed at this point, so even this deterministic push resolves its own
credential fresh) and reports how many commits, if any, it moved. Gated
identically to the existing refresh triple: `if: "!cancelled() &&
steps.<agent-id>.outcome != 'skipped'"` (FR-019 — the run-cancelled
exclusion this feature does not touch) and `continue-on-error: true` (a
push that itself fails here — e.g. a real non-fast-forward race with a
concurrent auto-rebase — must not strand the read-back below it, matching
`cleanup.yml`'s "Report stalled" step's own reasoning for `always()` over a
push that can be rejected by a legitimate race).

**Rationale**: Investigation of the two evidence runs this spec cites
found that today's "rescue" is *incidental*, not deterministic: spec 052's
post-agent step refreshes the remote's credential but issues no `git
push` of its own; the six stranded commits in run 35486482556 reached the
branch only because the *retry* agent's own next `git push` call, now
credentialed correctly, happened to carry every locally-ahead commit with
it. That path has no rescue at all when no further agent step runs after
the one that stranded work (a cycle that converges healthy needs no
retry) or when the agent step is killed before attempting its own final
push. FR-015's "before the job ends... on every path the job can take"
requires a step that runs whether or not another agent step follows —
this decision adds exactly that step, once per existing post-agent
refresh triple (three call sites in `implement.yml`, one each in the
other seven stages, matching D1's own footprint).

**FR-018 falls out for free**: once this new step runs and succeeds, any
closing lifecycle-record commit it carries is already on the branch by the
time the job's own deterministic read-back (`wing-commander-spec-meta`)
runs later in the same job — no separate fix to the read-back itself is
needed, matching spec 052's own precedent of fixing the *publication* side
rather than teaching the read-back to guess.

**FR-016/FR-017**: the new step's own output (`commits-published` — a
count, computed from `git rev-list --count <recorded-before-sha>..HEAD`
immediately before the push, per the existing "Read spec-meta.json"
step's own before/after-SHA convention at `implement.yml:2428`) is
consumed by each stage's existing stall-path callout (spec 041's
`wing-commander-chain-stop-notice` family) as one more line, present only
when the count is nonzero — the same "record appears only when there is
something to report" convention `wing-commander-post-agent-credential-
status` already established for its own `ok=false` warning.

## D9 — FR-008: the end-to-end arm's scratch-repository credential gets the same composite, parameterized to the scratch repo, not a second mechanism

**Decision**: `auto-update-spec-kit.yml`'s `e2e-stage` job calls
`wing-commander-agent-push-credential` a second way: `owner`/`repo-name`
set to the scratch repository's own coordinates (already resolved earlier
in that job by the existing `scoped-app-token` step) rather than
`github.repository`. No new composite; D5's parameterization exists
specifically so this call site differs only in its inputs.

**Rationale**: FR-008 requires this arm covered "on the same terms as the
pipeline repository's own remote" — reusing the identical composite is
what makes "same terms" true structurally rather than by two
independently-maintained implementations drifting apart, the exact
failure mode CLAUDE.md's single-home section warns about.

## D10 — FR-020–FR-023: a new gate, provisionally Gate 99, structural + one behavioural companion

**Decision**: `.github/scripts/verify-agent-push-credential-helper.py`
(provisionally **Gate 99** — the highest gate at plan time is Gate 98;
per spec 052's own documented renumbering norm, this number may shift if
another PR claims 99 first, in which case the implement stage renumbers
and records the collision the same way spec 052's Gate 68 did). Static,
structural checks over the 8 in-scope workflow files:

1. Every job containing an agent step whose allowed-tools include
   `Bash(git push:*)` has a `wing-commander-agent-push-credential` call
   positioned after that job's spec-branch checkout and before that agent
   step.
2. The same job has a `wing-commander-publish-stranded-commits` call
   (D8) positioned immediately after (gated the same way as) the existing
   post-agent `wing-commander-context` re-mint for that same agent step.
3. No second, independently-authored copy of the JWT-signing or
   credential-helper-wiring shell appears anywhere outside
   `wing-commander-agent-push-credential`'s own directory (a grep-shaped
   check, mirroring `verify-single-home-idioms.py`'s existing method for a
   different idiom).
4. A stage's agent step with no `Bash(git push:*)` in its allowed-tools is
   *not* required to carry either of checks 1–2 (FR-025) — and the gate
   fails loudly, naming the file/job it could not reach, rather than
   passing vacuously, when any of the 8 named files or their expected
   jobs cannot be located (Constitution Principle VIII, matching Gate 68's
   own check 4).

A companion behavioural gate (numbered immediately after, following Gate
68/69's own precedent of splitting the static structural check from a
`wc_shell_harness.py`-driven behavioural one) drives the actual
`mint-credential.sh` script's JWT-construction arithmetic against a fixed,
checked-in test keypair and a stubbed `curl`, asserting the emitted
`username=`/`password=` pair matches a fixture-recorded expected output —
proving the shell is correct, not just present, the same gap Gate 69
closed for spec 052's relay shell.

**Fixtures (FR-022)**: mutations mirroring Gate 68's own table — delete
the credential-helper call ahead of one agent step, delete one
stranded-commit-publish call, reintroduce a second JWT-signing block
outside the composite's own directory, and the two unreachable-subject
cases — each proven to fail with a message naming the workflow/job/step,
per spec 052's own established fixture convention (reused, not
reinvented).

## D11 — Documentation consolidation (FR-023): one canonical statement replaces the FR-008 residual-risk paragraph, not two independent rewrites

**Decision**: `docs/architecture.md`'s "Identity & chaining" section's
closing residual-risk sentence ("This remedy does not cover the credential
an agent step itself pushes with while it is still running... tracked in
issue #402") is replaced by a new paragraph describing the credential
helper (D1–D5), the retry bound (D7), and the stranded-commit publish step
(D8) as what now covers that case — with issue #402 kept as a closed
historical pointer (it is not deleted; CLAUDE.md's amendment-history norm
for the constitution's own Sync Impact Reports is the same instinct
applied to this doc's own history). `implement.yml`'s existing short-form
pointer comment at the FR-008 site (`implement.yml` — see D8's own commit)
is edited to point at the *new* architecture.md paragraph rather than
duplicating its content, per the single canonical-statement-plus-pointers
shape CLAUDE.md's "Shared logic has exactly one home" section requires and
Gate 47 (`verify-comment-canonical-pointers.py`) checks mechanically.

**Rationale**: FR-023 names exactly these two sites. Writing the fuller
mechanism explanation twice (once in the doc, once in the workflow
comment) is the CLAUDE.md-documented failure mode this repository has
already paid for once (the per-run cost line, 12 sites); this feature does
not repeat it for its own documentation.

## D12 — Teardown accounting (FR-009/SC-010): no new revocation obligation

**Decision**: Every token the helper mints is the same kind of credential
`wing-commander-context` already mints — a short-lived (one-hour) GitHub
App installation token, expiring on its own regardless of whether this
job's runner is destroyed first. This feature introduces no new
credential *type* and therefore no new revocation step: the existing,
already-accepted "Token expired, skipping token revocation" outcome
(spec 052's own cited evidence) continues to apply, now to a larger number
of short-lived tokens per job rather than a qualitatively different kind
of live credential. FR-009 is satisfied by this being true, not by adding
an explicit revoke-on-teardown step this repository has never had for any
of its other per-job mints.

## Summary of what remains for tasks/implement

This research resolves every mechanism decision the spec leaves open. No
further clarification is needed. The follow-up issue FR-008 itself would
otherwise require (per specs 052's own D9 precedent) is not applicable
here — this feature *is* that follow-up (issue #402, closed by the
maintainer directly as "this" — the originating input — rather than
staying open for a second pass).
