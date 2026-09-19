# Phase 0 Research: Bot Credential Lifetime Across Long Agent Cycles

spec.md carries no `[NEEDS CLARIFICATION]` markers — the clarify stage
already resolved the three open questions (which remedy, how far the sweep
reaches, whether the agent's own push credential is in scope). Phase 0
resolves the *design* questions the spec leaves to planning (it says so
explicitly: FR-002 names the remedy's shape but not its mechanism; FR-020
names two care points but not the check's structure). Decisions made without
a further clarification round are marked below and repeated in the issue
comment.

## D1 — Refresh mechanism: one job-scoped env var, rewritten after every agent step, not a chain of step ids

**Decision**: `wing-commander-context`'s existing `token` output is relayed
into a job-scoped environment variable (`WC_BOT_TOKEN`) the moment the
composite runs. Every bot-acting step in a job that calls the composite —
before *or* after the agent step — reads `env.WC_BOT_TOKEN`, never
`steps.<id>.outputs.token` directly. Immediately after each agent step, an
`if: always()` step calls `wing-commander-context` a second time and
overwrites `WC_BOT_TOKEN` via `$GITHUB_ENV`. Because a later write to the
same `$GITHUB_ENV` key wins for every subsequent step in the job (this is
how the Actions runner applies the environment file — documented runner
behaviour this repository has not previously needed to state), every step
below the refresh point sees the new value with **zero per-step edits** at
the call site itself.

**Rationale**: `implement.yml`'s `cycle → retry → progress` sequence (three
agent steps in one job, spec Edge Cases "two agent steps in one job") is the
case that decides between mechanisms. A chain of distinct step ids
(`ctx`, `ctx-refresh-1`, `ctx-refresh-2`, ...) would require every
downstream step *between* two agent steps to be repointed at the correct
generation's id — three different answers to "which token do I read" in one
job, silently wrong if a future edit inserts a step between the wrong pair.
The env-var relay collapses this to one fact per job: "the freshest mint
wins, always" — which is also the literal shape of the clarification's
chosen remedy ("every post-agent step reading the refreshed value" — not
"every post-agent step reading its own agent step's refresh"). It is also
what makes FR-020's gate tractable: the check has exactly one reference
form to disallow (`steps.*.outputs.token` / `steps.*.outputs.*token*`
outside the relay step itself) rather than a per-generation id table that
drifts every time a stage's step order changes.

The relay step lives **inside** `wing-commander-context`'s own composite
(one more `runs.steps` entry, `shell: bash`, `echo
"WC_BOT_TOKEN=$TOKEN" >> "$GITHUB_ENV"` sourced from `steps.app-token.
outputs.token`), not as a copy-pasted step at each of the 8 call sites —
this is itself the repository's single-home rule (CLAUDE.md "Shared logic
has exactly one home") applied to the relay logic, and it means the *second*
(post-agent) invocation of the composite refreshes the env var for free,
with no separate export step to keep in sync. The composite's `inputs:`/
`outputs:` block is unchanged — `token` is still emitted as a step output,
for the one caller (the "Checkout spec branch as wing-commander-bot" step,
D2) that needs a raw value rather than an ambient env var — so FR-002's "no
composite's declared input surface widens" holds exactly.

**Alternatives considered**:
- *A chain of step ids, downstream steps repointed per generation* —
  rejected above (harder to verify statically, wrong-by-default when a step
  is inserted or reordered).
- *Mint per call, inside each bot-acting composite* — explicitly declined by
  the spec's own clarification (FR-002); not reconsidered here.
- *A file dropped in `$RUNNER_TEMP` instead of `$GITHUB_ENV`* — rejected: no
  advantage over an env var for same-job consumption, and every downstream
  composite that takes `token:` as a `with:` input would need an extra read
  step to load the file, where `env.WC_BOT_TOKEN` is a direct expression.

## D2 — The authenticated git remote is refreshed by clearing the stale `http.extraheader` and re-embedding the fresh token in the remote URL, not a second checkout

**Decision**: The post-agent refresh step (D1) runs, inside the
already-checked-out spec-branch working tree, immediately after the token
relay rewrites:

```bash
git config --local --unset-all "http.https://github.com/.extraheader" 2>/dev/null || true
git remote set-url origin "https://x-access-token:${WC_BOT_TOKEN}@github.com/${{ github.repository }}.git"
```

This is the fix for the spec's own named care point: `.github/actions/
_shared/read-spec-meta.sh`'s bare `git fetch origin ...` (and any other step
that shells out to `git` rather than going through a composite's `token:`
input) authenticates against whatever credential `.git/config` actually
carries, which is exactly as stale as the step-output token it was minted
alongside unless both parts of that config are refreshed.

**Correction (found in this feature's own code review, T046)**: an earlier
draft of this decision refreshed only the remote URL, on the reasoning that
"the credential `actions/checkout@v5` embedded in `.git/config`" and "the
remote URL" were the same thing. They are not. With `persist-credentials`
at its default (`true`, unchanged by this feature), `actions/checkout@v5`
authenticates by writing an `http.https://github.com/.extraheader` local git
config entry carrying a Basic-auth header for the token it was given — it
does **not** embed any credential in the remote URL itself. A custom
`Authorization` header supplied this way takes precedence over the
Basic-auth header git's http transport would otherwise derive from a URL's
embedded userinfo, so a bare `git remote set-url` (the original plan) left
every subsequent `git fetch`/`push` against `origin` authenticating with the
**original, now-possibly-stale** extraheader — a no-op fix that would have
reproduced the exact 401 this feature exists to eliminate, undetected by
quickstart.md §4's shell test because that test drives the remote-refresh
step in a scratch repository with no extraheader configured. Unsetting the
extraheader removes the competing credential, so the URL-embedded token
(which the refresh step already sets) becomes the one git actually uses.

**Rationale**: A second `actions/checkout@v5` invocation was considered and
rejected specifically because of what runs between the agent step and the
refresh: the agent step is trusted to have pushed its own commits (FR-008's
residual risk already assumes this), but nothing in this feature guarantees
every stage's working tree is clean and fast-forwardable at that point —
composites between the two checkouts may hold uncommitted state a second
`checkout@v5` (even with `clean: false`) is not contracted to preserve.
Unsetting one local git config key and rewriting the remote URL touch only
metadata for `origin`; neither reads nor writes the working tree, so they
cannot discard a commit, a staged change, or an untracked file. This is the
narrowest fix for the narrow problem (an expired credential the checkout
step configured), matching the spec's framing of this exact edge case
("continues to reference the expired one unless it is refreshed too").

**Alternatives considered**:
- *Re-run `actions/checkout@v5`* — rejected above (working-tree risk).
- *Leave the remote alone and route every git operation through `gh api`
  instead* — rejected: several existing composites (`read-spec-meta.sh`
  among them) are call sites this feature does not otherwise need to touch;
  rewriting them to stop using `git` at all is a larger, riskier change than
  refreshing the one thing that goes stale.
- *Set `persist-credentials: false` on the initial checkout instead, relying
  solely on the remote URL's embedded token from the start* — rejected as a
  larger blast radius for this feature to take on: it would change the
  initial checkout's own authentication path (today's proven-working
  behavior) for all 8 stages, rather than fixing only the post-agent
  refresh this feature adds.

## D3 — The agent-ran signal is a job output, written by a step separate from the credential refresh

**Decision**: Immediately after each agent step, before the credential
refresh (D1), an `if: always()` step (`id` e.g. `agent-ran`) writes two
enum-shaped values to `$GITHUB_OUTPUT`: `ran=true` and `conclusion=<value
of steps.<agent-id>.conclusion>` (one of `success`/`failure`/`cancelled` —
never `skipped`, since this step's own `if: always()` only produces output
when the agent step was reached at all; a `cancelled()` mid-run agent step
still yields this step's best-effort attempt to run within the Actions
cancellation grace window, matching FR-013's cancellation requirement). The
job's `outputs:` block exposes these as `agent-ran` / `agent-conclusion`.
No prose field is added — FR-014 is a hard line, and every existing
prose-bearing signal in this fleet (refusal `reason`, spec 041's own
`refusal-reason`) is free text a *human* wrote in the step, not the model;
this signal never touches anything the agent authored.

**Rationale**: Keeping this a separate step from the credential refresh (not
folded into D1's relay step) means the signal is written *before* a mint
failure could prevent it — FR-004 requires a credential failure be
distinguishable from "the agent never ran," and ordering the signal ahead of
the refresh is what makes that literally true: even when the very next step
(the re-mint) fails outright, `agent-ran=true` has already been durably
recorded as a job output, because GitHub Actions preserves a step's written
outputs regardless of what a later step in the same job does (the same
runner guarantee spec 041's D2 already established and this repository now
relies on twice).

For `implement.yml`'s three-agent-step job, the *last* agent step to run
determines the signal — each subsequent agent step's own `agent-ran` step
overwrites the prior one's job-output-bound values the same way D1's token
relay does, so `agent-ran`/`agent-conclusion` always describe "the most
recent agent step that ran," matching what a maintainer reading the stall
notice needs (whether *any* further agent-mediated progress happened before
the job died).

**Alternatives considered**:
- *Fold the signal into the same step as the credential refresh* — rejected:
  would make the signal's presence depend on the refresh's own success,
  reintroducing exactly the ambiguity FR-004 forbids (a mint failure would
  look identical to "the agent never ran").
- *One job output per agent step (`agent-ran-cycle`, `agent-ran-retry`,
  `agent-ran-progress`)* — rejected for `implement.yml` specifically: the
  stall path (D4) needs one answer to "did the agent run," not three, and a
  three-field table would need updating in the two other stages that gain a
  second agent step only hypothetically, in the future — the overwrite
  convention scales to N agent steps in a job with zero schema change.

## D4 — Where the signal is consumed: only the stages that already have a stalled/survivor job (spec 041's six), not plan.yml

**Decision**: The signal (D3) is published uniformly in all 8 sweep stages
(FR-010 is unconditional: "each agent stage's job"), but only *read* by a
stall path in the six stages spec 041 already gave a `stalled`/survivor job
to — `implement`, `finalize`, `clarify`, `intake`, `pr-conversation`, and
`tasks` (both `generate` and `approved` entry jobs). `plan.yml` has no
`stalled` job at all today (confirmed by inspection — spec 041's own sweep
excluded it), so there is no "stage failed before it could run its own
steps" wording to correct there; FR-011/FR-012/FR-013/User Story 2 are
satisfied vacuously for `plan.yml` in the same sense FR-026 already grants
stages with no agent step a zero-cost pass — a job output with no reader is
harmless, cheap (FR-006: no additional turns, no additional invocations —
a `$GITHUB_OUTPUT` write costs neither), and sets `plan.yml` up for a future
survivor job without a second sweep. `auto-update-spec-kit.yml`'s
`e2e-stage` job is likewise not wired into the six-stage survivor-job
pattern — its failure reporting is that workflow's own multi-job structure,
out of the `wing-commander-chain-stop-notice` composite's reach entirely —
so the signal is published there too (uniformity, cheap) with the same
"no reader yet" status.

**Rationale**: FR-011's wording ("the stall path MUST read that signal")
presupposes a stall path exists; the spec's own Assumptions section leans on
"the steps this feature must make safe are enumerable by inspecting the
stage workflows" — inspecting `plan.yml` finds no survivor job to wire, and
inventing one is a different feature (widening spec 041's six-stage decision
to seven) that this spec's scope does not ask for. Publishing everywhere and
consuming only where a consumer already exists keeps FR-007's "all eight
stages... single sweep" honest for the credential remedy (D1/D2, which is
genuinely uniform) without silently inventing new stall infrastructure
FR-007 never asked for.

**Alternatives considered**:
- *Add a survivor job to `plan.yml` in this feature too, for full
  uniformity* — rejected as out of this spec's stated scope (User Story 2 is
  framed entirely around the *existing* stall path's wording, not around
  giving a seventh stage a stall path it never had); flagged instead as a
  natural follow-up alongside FR-008's residual-risk issue.

## D5 — The observability-tolerance sweep's population is exactly the "Report over-budget agent run" family; `rebase.yml`/`cleanup.yml` are out of scope by FR-007's own enumeration

**Decision**: `continue-on-error: true` is added to every "Report over-budget
agent run" step between an agent step and its deterministic read-back, in
all 8 sweep stages (FR-007's list) — the canonical comment at
`clarify.yml:928` (currently marked observability "in place" without
enforcement) is corrected in the same change to describe the mechanism that
now actually ships, keeping its `# (canonical copy; do not condense)`
marker so Gate 47 continues to pin the pointer sites. No other step in the
agent-to-read-back region across the 8 stages is documented in place as
observability-not-failure (confirmed by inspection — the only other
`continue-on-error: true` steps near an agent step carry a different,
already-enforced rationale, e.g. `implement.yml`'s "Fail loud on non-healthy
agent verdict" family). `rebase.yml` and `cleanup.yml` carry a byte-identical
copy of the same over-budget pattern but are not among FR-007's eight named
stages — they run no agent step of their own reachable by this feature's
definition of "agent stage," so they are left untouched; a maintainer
wanting the same tolerance there has a separate, smaller fix on hands that
this feature's gate (FR-021) does not need to reach, because its subject is
defined as the 8 enumerated stages, not "every workflow containing the
canonical comment's pointer text."

**Rationale**: FR-019 requires the audit be "recorded so a reviewer can see
which steps were examined and why each was or was not tolerated" — this
decision, plus the per-stage line numbers research turned up (12 call
sites), is that record.

**Alternatives considered**: none — the population was empirically closed by
inspection (research phase), not a judgment call with a rejected
alternative.

## D6 — Gate design: one new check, structural + fixture-mutation, following `verify-plan-tasks-cost-line.py`'s live-tree-mutation convention

**Decision**: One new script, `.github/scripts/verify-post-agent-credential-
refresh.py`, wired into `.github/workflows/lint-workflows.yml`'s existing
`pull_request` job (picked up automatically by `wc_gate_registry.py`'s
filename convention — no registry edit). Numbering: claimed **Gate 67**
provisionally at plan time (highest existing was Gate 66); #401
(`verify-auto-release-credential-step.py`) landed first on the same base
and took that number, so this gate shipped as **Gate 68** — renumbering on
merge conflict with a parallel-landed spec is expected and already this
repository's norm — see the Gate 62–67 collision comments in
`lint-workflows.yml`. It checks, for
each of the 8 sweep-stage workflow files' jobs that contain an agent step:

1. **No stale reference** (FR-020 care point 1): no bot-acting step
   positioned after an agent step reads `steps.<id>.outputs.token` (or
   equivalent raw output form) directly — every such step must resolve its
   credential through `env.WC_BOT_TOKEN` (D1) instead.
2. **No un-refreshed second agent step** (FR-020 care point 2): every agent
   step in a job except the first must be preceded, since the previous
   agent step, by a `wing-commander-context` invocation (the refresh).
3. **No un-tolerated declared-observability step** (FR-021): every step
   between an agent step and its job's deterministic read-back step whose
   name/comment matches the "Report over-budget agent run" family (D5) must
   carry `continue-on-error: true`.
4. **Loud failure on an unreachable subject** (FR-022, Principle VIII): if
   any of the 8 named workflow files is missing, or a file is present but
   contains no job the check can identify as running an agent step, the
   gate fails outright rather than reporting a vacuous pass over zero
   stages — mirroring `verify-gate-N.py`'s repository-root guard precedent
   cited in Principle VIII's own worked example.

Static structure (steps 1–3, YAML inspection via `yaml.safe_load`, the same
approach `verify-plan-tasks-cost-line.py` and `verify-implement-stall-
notice-unchanged.py` already use for their subject workflows) is the
primary mechanism — this check's subject is step *ordering and reference
shape*, not step *behaviour*, so no `wc_shell_harness.py` execution pass is
needed the way spec 041's Gate 28 needed one for expression evaluation.
Every failure branch (FR-023) is proven with the `MUTATIONS`-table-over-the-
live-tree pattern: `copy.deepcopy` the parsed workflow, apply one mutation
(revert one reference to the stale form; delete one refresh step ahead of a
second agent step; strip one `continue-on-error: true`; point the check at
a nonexistent ninth file), assert the mutated tree fails and the unmutated
tree passes, exactly as `verify-plan-tasks-cost-line.py`'s `self_test()`
does today.

**Rationale**: The live-tree-mutation convention is the closer precedent
here (over spec 041's separate synthetic-fixture-file convention) because
this gate's subject is the *real* 8 workflow files' real step graphs, not a
newly-invented composite with no prior shape to mutate from — mutating the
real, already-checked-in YAML in memory is both less fixture code to
maintain (no 8 duplicate synthetic trees) and a stronger guarantee that a
passing gate reflects the shipped files, not a stand-in for them (Principle
VIII's "a copy sat green for weeks checking a filter that did not ship"
warning, cited verbatim in that script's own docstring).

**Alternatives considered**:
- *Split into two gates (credential-reference gate, tolerance gate)* —
  rejected: FR-020/FR-021 are phrased as "the check" (singular) sharing one
  subject region (agent step → read-back); one gate with three assertions
  over one parse pass is cheaper to run and to keep in sync than two gates
  independently re-parsing the same 8 files.
- *Behavioral execution of the refresh step's shell via
  `wc_shell_harness.py`* — rejected as unnecessary: the refresh step's
  `run:` block is trivial shell (an env-file write and a `git remote
  set-url`) whose only defect class this feature cares about is "is it
  present and correctly ordered," which static inspection answers
  completely; executing it would only prove the shell itself is
  syntactically valid, which `bash -n` (already a PR-time gate) covers.

## D7 — Canonical documentation: one workflow-comment home (co-located with the existing over-budget marker), one `docs/architecture.md` section, FR-008's residual risk recorded at both

**Decision**: The credential re-establishment mechanism (D1/D2) gets its own
`# (canonical copy; do not condense)` comment block at `clarify.yml`,
immediately above its "Wing Commander context" step — the same file that
already hosts the FR-017 over-budget canonical comment, so a reader looking
for "how does this stage's agent-adjacent plumbing work" finds both in one
place. The other 7 stages' equivalent step carries a one-line pointer
(`-- see clarify.yml.`) in the form Gate 47 already parses. `docs/
architecture.md`'s existing "Identity & chaining: the wing-commander-bot
App" section (today: one sentence, no lifetime, no remote-refresh mention)
is rewritten to state the one-hour lifetime, the env-var relay, the remote
refresh, and — per FR-008 — the residual risk that the agent's own push
credential is not covered by this feature, with a forward reference to the
follow-up issue. `implement.yml`'s read-back step (the one whose comment
already narrates the credential arrangement in place today) gets the same
residual-risk sentence, short form, pointing at the architecture doc for the
full statement — this is FR-008's two required locations, satisfied by one
canonical prose statement (architecture.md) and one pointer (implement.yml),
consistent with the single-home rule rather than writing the residual-risk
paragraph out twice.

**Rationale**: FR-024 requires "one canonical statement with pointers from
the other sites, following this repository's single-home rule" — `docs/
architecture.md` is prose, outside Gate 47's workflow-comment-only scope,
so it is the natural home for the *fuller* explanation (lifetime, mechanism,
residual risk in one place), while the in-workflow comments stay short and
point outward the way `clarify.yml`'s existing FR-017 comment already does
for its own topic.

**Alternatives considered**:
- *Put the canonical workflow comment on `wing-commander-context`'s own
  `action.yml` instead of `clarify.yml`* — rejected: `action.yml` already
  carries a substantial canonical comment about cross-repo self-checkout
  resolution (lines 1–23); a second, differently-scoped canonical block in
  the same file blurs which one a `-- see` pointer resolves to, and Gate
  47's own topic-word-overlap check is more naturally satisfied when the
  credential-lifetime topic lives beside the over-budget topic it is
  causally entangled with (both fire only because a cycle ran long).

## D8 — `auto-update-spec-kit.yml`'s `scratch-token` is a second, independent credential in scope for the same remedy

**Decision**: The e2e arm's `steps.scratch-token.outputs.token` (minted
before its agent step, read again afterward at "Push agent-produced
spec.md") gets the same treatment as `steps.ctx.outputs.token` — relayed
into its own job-scoped env var (`WC_SCRATCH_TOKEN`, kept distinct from
`WC_BOT_TOKEN` because it authenticates against the disposable scratch
repository, not this repository's own installation) and refreshed by a
second mint immediately after the e2e arm's agent step, same as D1/D3. Its
existing `continue-on-error: true` on the "Push agent-produced spec.md" step
is unrelated to this feature (it is a pre-existing best-effort design
choice for that push, not a stand-in for a working credential) and is left
as-is — FR-001 requires the credential actually work, independent of
whether the step that uses it also tolerates failure for other reasons.

**Rationale**: FR-007 names "the auto-update stage's end-to-end arm"
explicitly as one of the eight; FR-001's "any credential value... written
to a file or environment for a later step" covers `scratch-token` on its
own terms, distinct from — and in addition to — `steps.ctx`, since
`e2e-stage` mints both.

**Alternatives considered**: *Treat `scratch-token`'s existing
`continue-on-error: true` as already satisfying this feature's requirement,
skip refreshing it* — rejected: tolerance and correctness are different
properties (D5's own rationale draws the same line); a tolerated failure
still means the scratch repository never receives the agent's work, which
is a real defect this feature commits to fixing (FR-001 has no carve-out
for "already wrapped in continue-on-error").

## D9 — The FR-008 follow-up issue is filed at PR-open time, not by this plan

**Decision** (recorded here, not an action this plan document takes): per
spec Out of Scope and FR-008, a follow-up issue for the agent's own push
credential is filed when this feature's implementation PR opens — a task
for the tasks/implement stage's own workflow, not something the plan stage
produces. This plan records the requirement (D7) so the implement stage has
a concrete pointer (the architecture.md residual-risk section) to cite when
filing it.
