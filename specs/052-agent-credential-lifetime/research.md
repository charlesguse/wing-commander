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

## D5a — `auto-update-spec-kit.yml`'s `evaluate-path` and `comment-reply` jobs are out of scope, same as `rebase.yml`/`cleanup.yml` (second maintainer review of PR #407, FR-005/SC-005)

**Decision**: `auto-update-spec-kit.yml` runs three agent steps across three
jobs — `evaluate-path`, `comment-reply`, and `e2e-stage` — but FR-007's
eight-stage enumeration names only "the auto-update stage's end-to-end
arm," i.e. `e2e-stage`. `evaluate-path` and `comment-reply` are left
untouched by this feature's sweep (D1-D3's relay/refresh mechanism, D4's
signal, D5's tolerance), same as `rebase.yml`/`cleanup.yml`: neither is one
of the 8 named stages. Each carries its own `timeout-minutes: 10` on its
agent step (an order of magnitude under the minted token's one-hour
lifetime), so the defect this feature fixes — a bot-acting step running
after the credential has actually expired — cannot occur there regardless.
This was previously recorded only in the YAML comments at the two jobs'
own agent steps (`auto-update-spec-kit.yml:1093`, `:3246`) and one
tasks.md line citing this D4/D5 table without either job actually being
listed in it; this entry is that listing.

**Rationale**: SC-005 requires "zero stages... neither covered nor recorded
with a reason" — an exclusion resting only on an inline YAML comment, with
the spec-level scope table it cites not actually naming the excluded jobs,
does not satisfy that bar for a reviewer reading spec.md/research.md
without also reading the workflow file.

**Alternatives considered**:
- *Fold both jobs into the sweep for full uniformity* — rejected: their
  10-minute timeout already makes the defect structurally unreachable, so
  adding the relay/refresh/signal/tolerance machinery would be inert
  weight with no defect it could ever catch, the same reasoning D5 applies
  to `rebase.yml`/`cleanup.yml`.

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

## D10 — Corrections from the maintainer's code review of PR #407 (head bb064e9)

**Decision**: rather than editing D1-D9 in place, this entry records what
changed and why, the same precedent D2's own in-place correction note
already set for a narrower fix.

- **D1's `.conclusion` was wrong.** The agent-ran signal reads
  `steps.<agent-id>.outcome`, never `.conclusion` — the agent step's own
  `continue-on-error: true` (spec 037) rewrites a real failure's
  `.conclusion` to `success`, so reading it signaled a failed agent as
  having run to completion. `.outcome` is unaffected by
  `continue-on-error` and is the value every downstream consumer
  (`wing-commander-agent-ran-signal`, the stall-reason branch, the
  chain-stop-notice wording) now reads.
- **D1/D2's single-home claim was aspirational, not enforced.** The relay
  and refresh steps were pasted at every call site with no gate asserting
  they matched. Both are now shared composites
  (`wing-commander-agent-ran-signal`, `wing-commander-refresh-remote`;
  `wing-commander-context`'s own internal relay was already single-homed),
  and Gate 68 gained a check asserting every site calls them.
- **FR-004 was undersized.** The original design assumed a failed mint or
  refresh would simply surface as a 401 on whichever step used the stale
  credential next. A new `wing-commander-post-agent-credential-status`
  composite fails loud, naming the credential as cause, right where the
  re-establishment itself did not succeed — deferred to each job's own
  last steps (not immediately after the refresh pair) so its hard exit
  cannot strand the business-logic/report steps between it and the agent
  step, which are gated on their own implicit `success()` (review-step-
  gating self-review, not a maintainer-review finding).
- **D3's "a step after it did not complete" was as specific as the design
  got.** FR-011/SC-003 ask for the step to be *named*. A new per-job
  "Determine failed post-agent step" step (the job's actual last step)
  publishes which step failed, read by the stall-reason branch ahead of
  the generic fallback. It read `toJSON(steps)` when this was written;
  D10a records its replacement by the `wing-commander-failed-post-agent-
  step` composite fed an explicit candidate list (#410 item 4).
- **Cancellation window.** Every new step's guard changed from
  `always() && ...` to `!cancelled() && ...`, so a cancelled run no longer
  performs a network mint or a remote rewrite after cancellation was
  requested.
- **D5's over-budget tolerance and D6's gate self-test both had real
  holes**, closed in the same pass: the over-budget continue-on-error
  check now matches every `(cycle)`/`(retry)`/etc. suffix, not only the
  bare name; the refresh-after-agent-step check covers a job's *last*
  agent step, not only gaps between two; and a subject job silently
  losing its agent step now fails the gate instead of skipping its checks.

None of D1-D9's underlying reasoning (env-var relay over a step-id chain,
in-place remote refresh, a separate signal step, consumption scoped to the
six existing survivor jobs, the over-budget population, the gate's
structural-fixture design, the canonical-documentation placement, scratch-
token as a second credential, and the follow-up issue's filing point) is
overturned by this review — only the specific mechanics listed above.

## D10a — Further corrections from the second and third maintainer reviews of PR #407

**Decision**: two of D10's own mechanics did not survive later review; this
entry records what changed on top of D10, same convention.

- **D10's "fails loud" was wrong too.** The second review found that a
  transient re-mint failure at `wing-commander-post-agent-credential-
  status`'s own step — the job's last one, every earlier step already
  healthy — hard-failing there reports a false "stalled" outcome for a run
  that already did its work. The composite now never fails the job: it
  emits `::warning::` naming the credential as cause, and publishes
  `ok=false`. `wing-commander-stall-reason`'s ok-first check is what
  attributes a *later, real* failure to the credential; a run whose later
  steps all succeeded despite the warning stays green.
- **D10's `toJSON(steps)` was replaced.** "Determine failed post-agent
  step" does not read the whole `steps` context (it can exceed Linux's
  128 KiB per-env-var limit in `implement.yml`'s 87-step job, and `steps`
  is not guaranteed to serialize in execution order). It is now the
  `wing-commander-failed-post-agent-step` composite, given an explicit,
  caller-supplied ordered list of `{name, conclusion}` candidates — every
  genuinely hard-failing (non-`continue-on-error`) step at each call site
  is named by its own `name:` field (a readable name, not its `id:` — a
  polish-pass correction, also third review, since the stall notice used
  to print the bare id) — and it selects the last one on `.conclusion ==
  "failure"`, excluding the agent step itself, so a tolerated
  `continue-on-error` step or the agent step is never misnamed as the
  cause.
- **The credential branch's precedence was backwards.** The third review
  found `wing-commander-stall-reason` checking `credential-refresh-ok ==
  'false'` *ahead of* a named `failed-post-agent-step`, so a stage that
  failed for an unrelated, already-identified reason while an earlier
  re-mint also happened to warn was wrongly blamed on the credential; the
  branch also discarded the named step when both were known. A named
  failure now always outranks the credential-only diagnosis; when both are
  known, the reason names the step and mentions the credential as context
  (`"the credential could not be re-established, and step '<step>' failed
  after it"`) rather than picking one.

D10's own closing statement (none of D1-D9's underlying reasoning
overturned) still holds; this entry narrows two of D10's own corrections,
not the original design.
