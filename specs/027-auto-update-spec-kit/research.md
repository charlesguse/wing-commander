# Phase 0 Research: Auto-Update Spec Kit

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers — the three
genuine ambiguities it started with (cadence, verification scope,
version-scope policy) were already resolved during the clarify stage and
are cited inline in FR-002/FR-004/FR-014 as "resolved from #153." What
follows are the implementation-shape decisions this plan makes to turn
the spec's functional requirements into something `tasks.md` can build
against, grounded in what already exists in this repository (the eight
published stages, `rebase.yml`'s issue-marker dedup convention,
`watchdog.yml`'s tiered-gate and guardrail-file precedent, and
`wing-commander-preflight`'s existing spec-kit version check). Each
decision below states its rationale and rejected alternatives; decisions
explicitly *not* dictated by the spec text are marked "(made without
clarification)" and are repeated in the transmittal comment on issue
#153, per this pipeline's own convention for undocumented decisions
(precedent: `specs/015-pipeline-watchdog/research.md`).

## External research: blocked in this environment (documented gap, not invented)

**Status**: The spec's own Assumptions and FR-013 ask this feature to
research, at run time, whether Spec Kit has had past version/upgrade
pain and to record sources on the lifecycle issue when it does — that is
runtime behavior this plan designs a mechanism for (see "Decision:
sourcing FR-013's research" below), not a fact this plan itself needs to
already know. However, this plan's own drafting *did* attempt to
pre-check two things — Spec Kit's actual upgrade-mechanism shape (does
`specify` expose an `upgrade`/`update` command, or is re-running
`specify init` the only path?) and its release/versioning history — and
that attempt failed: this headless CI environment denies `WebSearch`
("Claude requested permissions to use WebSearch, but you haven't granted
it yet"), has no `WebFetch` tool registered, and denies outbound `curl`/
`git ls-remote` to github.com via Bash. No vendored copy of
`github/spec-kit` or its changelog exists in this repository to inspect
offline either.

**Decision (made without clarification)**: Proceed with the
already-clarified conservative default (FR-002: daily check, target the
settled latest release, no fixed calendar window) and design the
*mechanism* (below) so the feature performs this exact research itself,
live, using only already-trusted read paths (`gh api` against GitHub's
own REST API — not general web browsing) the first time it actually
detects an eligible upgrade. This plan does not fabricate a Spec-Kit
version history or a specific "upgrade command" name it could not verify.

**Rationale**: Constitution V's spirit — never assert as fact what
wasn't actually checked — applies to a plan document exactly as it does
to a lifecycle-issue comment. Blocking the whole plan on unavailable
network access would contradict the CI run's explicit instruction to
make a documented decision and continue rather than stall.

**Flagged for the human** (see issue comment): before this stage's first
real scheduled run, a maintainer should confirm (a) whether upstream
Spec Kit's CLI (`specify`/`uvx specify-cli`) exposes a dedicated
upgrade/update command distinct from re-running `specify init`, since
that determines the exact shell command the `prepare` job below runs,
and (b) whether Spec Kit's release history shows any past breaking
upgrade that would justify a stabilization window longer than this
plan's one-settled-check default (see "Decision: settle window" below).
The design below is deliberately conservative and fails toward routing
to a human (FR-018) whenever its own assumption about the upgrade
mechanism doesn't hold, so an incorrect guess here degrades safely
rather than silently misapplying the wrong upgrade steps.

## Decision: this is a maintenance stage-pair, not a tenth numbered lifecycle stage

**Decision**: Ship `.github/workflows/auto-update-spec-kit.yml` as a new
`workflow_call`-only reusable stage plus one wrapper,
`.github/workflows/wing-commander-auto-update-spec-kit.yml` — named
*without* a `wing-commander-N-` numeric prefix, matching `rebase.yml`'s
wrapper (`wing-commander-rebase.yml`) rather than the numbered
`1-intake` … `8-watchdog` sequence.

**Rationale**: The numbered wrappers (`1` through `8`) form the
per-spec lifecycle a single spec walks through end to end
(`docs/architecture.md`'s stage list); this feature has no per-spec
identity at all — it runs on a schedule, touches `.specify/` pin files
directly, and its lifecycle issue is not a `spec:<NNN-slug>`-labeled
issue (no `specs/NNN-slug/` directory is created). That is exactly
`rebase.yml`'s and `watchdog.yml`'s shape (repo-wide maintenance,
unnumbered or `8b`-suffixed wrapper naming), not a lifecycle stage's.

**Alternatives considered**: Numbering it `9` alongside watchdog's `8`
— rejected: the numbered sequence specifically encodes "step N of a
spec's own journey" (constitution's Development Workflow section lists
intake→plan→tasks→implement⟲converge→finalize→cleanup, with watchdog and
rebase already living outside that numbered chain despite watchdog's
`8-` prefix being a naming artifact of when it shipped, not a claim of
per-spec sequence membership). Folding this feature into `watchdog.yml`
itself (one more triage class) — rejected: watchdog inspects *pipeline
runs*, this feature inspects *upstream Spec Kit releases*; conflating
them would make watchdog's `workflow_run` trigger contract also need a
`schedule` trigger and an entirely different evidence model, violating
watchdog's own single-responsibility shape.

## Decision: one wrapper multiplexes three trigger types via a typed `trigger` input

**Decision**: `wing-commander-auto-update-spec-kit.yml` declares three
triggers — `schedule` (daily) + `workflow_dispatch` (on-demand, FR-002),
`pull_request: {types: [closed]}` (filtered to this feature's own
version-bump PRs via a body marker, for the close-with-summary step),
and `issue_comment: {types: [created]}` (filtered to the singular open
auto-update issue, for resuming an FR-012 ambiguous-path question) — and
resolves each into one typed `trigger: scheduled | dispatch | pr-merged
| comment-reply` input passed to `auto-update-spec-kit.yml`, which
branches its job graph on that input. No stage-side read of
`github.event.*` (constitution VII).

**Rationale**: The feature's total footprint (no per-spec branch, no
spec.md drafting, no draft-PR-review loop) is much smaller than the
intake/clarify pair's, so splitting the "detect and act" and "resume a
paused decision" halves into two file-pairs the way intake/clarify do
would mirror that precedent's *shape* without matching its actual
complexity — closer to watchdog/rebase's single-file-pair maintenance
shape, scaled up only enough to cover four trigger reasons instead of
one or two.

**Alternatives considered**: A separate `auto-update-spec-kit-resume.yml`
stage mirroring `clarify.yml`'s split from `intake.yml` — rejected as
premature file-count growth for a feature this narrow; revisit if a
future spec adds enough resume-path complexity to justify it.

## Decision: settle-window tracking lives in the lifecycle issue, not a new state file

**Decision**: "Has the same-minor patch stream settled" (FR-002) is
tracked entirely in the singular open auto-update lifecycle issue via a
hidden marker in its body, reusing `rebase.yml`/`watchdog.yml`'s
marker-in-body-plus-`gh search issues` convention:
`<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N -->`,
where `observed` is a small integer counting consecutive daily checks
that found the *same* `latest_upstream` value. Each scheduled run:

1. `gh search issues --repo "$GITHUB_REPOSITORY" "\"wing-commander-auto-update-spec-kit:\" in:body" --json number,state,body`
   (quoted-phrase search per the watchdog-established gotcha:
   `gh search issues` has no `--state all`/`all` value — omit `--state`
   to search both; the marker text must be quoted or GitHub over-matches
   on its tokenized words).
2. Zero results and a newer eligible version exists → create a new open
   issue with `observed=1`, comment the detected version + release type
   + "waiting for the patch stream to settle" note, stop (no PR, no
   verification yet — this is what makes FR-002's "not the same day"
   guarantee hold).
3. One open result, its `candidate` equals today's `latest_upstream` →
   increment `observed`; once `observed >=
   vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS`
   (default `1`, i.e. one full daily cycle with no change is already
   "settled" — no fixed calendar window, matching FR-002's literal
   text), proceed to `evaluate-path`/`prepare`/`verify`.
4. One open result, its `candidate` differs (a newer patch of the same
   minor landed, or upstream published a further release) → update the
   marker to the new candidate, reset `observed=1`, comment explaining
   the supersession and why (FR-013), stop.
5. One open result already marked "awaiting maintainer decision"
   (FR-012's ambiguous-path state) → left untouched (FR-015); at most a
   "still waiting" comment if the target itself changed underneath the
   open question.
6. More than one match → data-integrity condition, reported and left for
   a human, never auto-resolved (mirrors watchdog's identical handling
   of its own dedup search).

**Rationale**: `specs/015-pipeline-watchdog/research.md` already
rejected a separate ledger file for its fingerprint→issue mapping
("a second source of truth that can desync from actual issue state");
the identical argument applies here — a `.specify/memory/*.json` file
tracking "what candidate did we last see" could drift from the issue
that's the actual human-visible record of that same fact. Keeping it in
the issue body also means a maintainer can literally read why the
process is still waiting by opening the issue, matching constitution
III's "legible from its own issue alone."

**Alternatives considered**: A fixed calendar stabilization window (e.g.
"wait 3 days") — rejected outright: FR-002's text is explicit ("no fixed
calendar stabilization window"), because a purely date-based wait
neither speeds up for an obviously-quiet release nor slows down for a
release upstream is visibly still patching; a settle-check counter tied
to the daily cadence itself does both. A `vars.*`-only counter with no
issue-body record — rejected: would make "why is this still pending"
invisible without reading workflow-run logs, contradicting SC-004.

## Decision: "last known working version" is read from git history, never a new ledger file

**Decision**: There is no persisted "last known working version" field
anywhere. Every version-bump PR this feature opens only reaches `main`
after (a) this feature's own verification passed and (b) a human's
merge click (constitution V) — so the value in
`.specify/init-options.json`'s `speckit_version` on `main` HEAD is, by
construction, always the last version that passed verification, *unless*
a routine re-check (the health-check step below) finds it broken. In
that failure case, the prior value is read directly from git history:
`git log -p -- .specify/init-options.json`, walking backward from HEAD
to the most recent commit that changed `speckit_version`, and reading
the diff's removed line as the rollback target.

**Rationale**: Same reasoning as the settle-window decision above and
explicitly the same shape `015-pipeline-watchdog/research.md` already
established for this repo: git/GitHub state that already exists is
preferred over a new file that could desync from it. FR-007 only
requires the system be "able to identify" the last known working
version, not that it store it separately — git history already
satisfies that identification requirement exactly, and a revert PR
generated from it is indistinguishable in spirit from `git revert` on
the previous bump commit.

**Alternatives considered**: A `.specify/memory/auto-update-spec-kit-state.json`
ledger recording `{"last_known_working": "0.12.4"}` on every successful
merge — rejected: introduces a write this feature would need to make
*after* a PR merges (a second, easy-to-miss write path beyond "open a
PR"), and the value it would hold is always mechanically derivable from
git history anyway, so the file would only ever be a cache that can go
stale, not a new fact.

## Decision: routine re-verification of the *currently pinned* version is what triggers rollback (FR-006's "already applied" branch)

**Decision**: Before checking for a newer upstream release, every
scheduled/dispatch run first re-runs the lightweight verification
(FR-004) against the version *currently pinned on `main`* — a
"health-check" job. If it fails: open a revert PR (title `revert: Spec
Kit vX.Y.Z regression — restore vA.B.C`, using the git-history lookup
above for `vA.B.C`), open/reuse a flagged lifecycle issue explaining what
the health check found and which version is now proposed as pinned
again, and skip upstream-detection entirely for this run (nothing useful
to check for while the currently-pinned version itself is suspect).

**Rationale**: FR-006's second branch — "if it had already been applied
[and found not to work], automatically roll back" — only makes sense if
something can discover a regression *after* a version already merged
(verification passed once, at merge time, by definition, since this
feature never opens a PR that didn't pass). A daily re-check of the
currently-pinned version is the simplest mechanism that can make that
discovery at all, without inventing a second, independent
"observe-production" signal source this repository doesn't otherwise
have (no runtime telemetry beyond the pipeline's own CI runs).

**Alternatives considered**: Relying on `watchdog.yml` to notice a
pinned-version regression as one more finding class — rejected for this
plan: watchdog's evidence model is "inspect one just-completed pipeline
run" (`workflow_run`-triggered), not "periodically re-validate a
checked-in configuration value" — extending it would duplicate this
feature's own lightweight-verification logic inside a different stage
for no shared benefit, and would blur watchdog's single-responsibility
boundary the same way folding this feature into watchdog outright would
(see the first decision above).

## Decision: verification tiers reuse `.specify/` scripts directly; no reusable smoke test exists yet to extend

**Decision**: `release.yml`'s Gate 1/1b (actionlint + interface-invariant
greps over the eight numbered stage files) is unrelated machinery (a
release-time workflow-file lint, not a spec-kit-behavior check) and is
not reused. No existing "run `.specify/` scripts and confirm they work"
smoke test exists anywhere in this repository to extend — FR-004's
lightweight check is new:

- **Lightweight (always)**: in an isolated temporary worktree/checkout
  (never the real working tree), install the candidate version's
  `.specify/` artifacts using the same install path
  `.specify/init-options.json`'s existing recorded flags imply (`ai:
  claude`, `script: sh`, `ai_skills: true`) re-applied at the candidate
  version, then run `.specify/scripts/bash/check-prerequisites.sh` and
  `create-new-feature.sh --json` against a throwaway feature name and
  confirm both exit `0` and produce the JSON shape those scripts
  document today (FR-004's "at minimum... produce expected outputs").
- **End-to-end (minor/major only)**: additionally run one real
  spec-kit-driven stage against the same throwaway feature — generate a
  disposable `specs/<scratch>/spec.md` via the equivalent of the
  `/speckit-specify` flow — confirm the expected files land, then
  discard the scratch worktree entirely (never committed, never opens
  a real lifecycle issue, never touches the real `specs/` tree).

**Rationale**: FR-004's own text draws exactly this line (scripts-run
check always; one real stage's throwaway output additionally for
larger jumps), and `wing-commander-preflight`'s existing
`SPECKIT_SUPPORTED_VERSION` constant (`.github/actions/wing-commander-preflight/action.yml`)
already establishes that this repository treats "the pinned spec-kit
version" as something worth a dedicated, checked value elsewhere in the
codebase — this feature's version-bump PR must update that constant
alongside `.specify/init-options.json`, or preflight starts warning on
every subsequent stage run.

**Alternatives considered**: Trusting Spec Kit's own `specify check`
command (if one exists) as sufficient verification on its own —
rejected pending the external-research gap above: without confirming
what `specify check` actually validates, treating it as sufficient could
under-verify; the scripts-actually-run check is this repository's own
ground truth regardless of what Spec Kit's own tooling additionally
offers.

## Decision: eligibility and "clearly better path" are a deterministic detector plus one judgment step, mirroring watchdog's diagnose/act split

**Decision**: Two categories of work, never blended into one step:

1. **Deterministic** (`gh api repos/github/spec-kit/releases --paginate`,
   `jq`): fetch all releases, keep `prerelease == false` (spec's own
   Assumption: pre-releases are out of scope), semver-sort, pick the
   highest — this is `latest_upstream`, and its diff against the pinned
   version's major/minor/patch components is the deterministic
   `release_type` classification FR-004/FR-014 key their tier decision
   on. No model involvement — a version comparison is not a judgment
   call.
2. **Judgment** (`evaluate-path`, one agent step, `claude-sonnet-5` —
   see model-tiering decision below): given the release notes text for
   every release between the pinned version and `latest_upstream`
   (fetched via `gh api`, never live-browsed — framed explicitly as
   untrusted data per constitution V, same convention every
   comment-triggered stage already uses for issue bodies) plus a diff of
   what the candidate version's `.specify/` artifacts would actually
   change, decides one of three outcomes: **clean bump** (proceed to
   `prepare`/`verify`), **needs migration** (FR-018 — routes to a human,
   never auto-applies a partial migration), or **ambiguous options**
   (FR-012 — posts the options plus reasoning and sources as a question
   on the issue, stops, awaits a maintainer's reply).

**Rationale**: Directly mirrors `015-pipeline-watchdog/research.md`'s
"deterministic collection, one LLM synthesis step" split and its stated
reason (a crisp, testable rule belongs in code; only genuinely
unstructured judgment — "is one upgrade path clearly better" — belongs
to the model). Feeding the model release-notes *text* rather than
letting it browse satisfies FR-013's "include sources" (the release
notes' own URLs, cited back in the issue) without needing web tools at
all.

**Alternatives considered**: Giving the judgment step live `WebSearch`/
`WebFetch` access to look up additional context beyond the release notes
GitHub already serves — rejected: this step's input is otherwise fully
auditable (a fixed set of `gh api`-fetched release bodies); adding
open-ended browsing would make its "sources" list unpredictable and
reintroduces exactly the kind of untrusted-content-as-instruction risk
constitution V's default posture (web tools off) exists to avoid, for a
step that already has everything it needs from the releases API.

## Decision: model tiering

| Step | Model | Constitution II category |
|---|---|---|
| Health-check, detect, settle-tracking, dedup search, rollback-target lookup | none (deterministic bash/`gh`/`jq`) | n/a |
| `evaluate-path` (clean-bump vs. needs-migration vs. ambiguous; drafts PR/issue reasoning+sources) | `claude-sonnet-5` | implementation-weight (authors a real diff + a judgment call), matching `rebase.yml`'s conflict-resolution tier |
| Comment-reply interpretation (map a maintainer's free-text reply onto one of the posted options) | `claude-haiku-4-5` | triage/classification — a closed-set choice, not open-ended judgment, matching `cleanup.yml`'s summary tier |
| Verification (lightweight + end-to-end) | none (deterministic script execution + exit-code/JSON-shape assertions) | n/a |

Every agent step declares `--model` and `--max-turns`, per constitution
II's blanket rule. Both `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL`
knobs default to the values above but remain overridable via repo
variable, matching every other stage's `vars.WING_COMMANDER_*_MODEL ||
'claude-...'` fallback idiom (e.g. `wing-commander-rebase.yml`'s
`vars.WING_COMMANDER_PLAN_MODEL || 'claude-sonnet-5'`).

## Decision: configuration knobs are repo variables, not a new guardrails file

**Decision**:

- `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED` (`true`/unset,
  default unset ⇒ not paused) — checked in the **wrapper's** `if:`
  (not the stage's — `wing-commander-8-watchdog.yml`'s own fix, learned
  the hard way, moved this exact check from stage to wrapper so a paused
  run doesn't still bill for agent steps before finding out it's
  paused).
- `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS`
  (default `1`) — the settle-window decision above.
- `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_MODEL` (default
  `claude-sonnet-5`, `evaluate-path` only) — model-tiering override.

No new `.specify/memory/*.json` file is introduced by this feature (see
the two "no new ledger file" decisions above) — unlike
`watchdog-guardrails.json`, there is no maintainer-editable allowlist
this feature needs, since its tiering (patch/minor/major → verification
depth) is a fixed rule straight from FR-004/FR-014's own text, not a
flexible classification scheme a maintainer would want to hand-tune
per-change-class the way rung-1 auto-fixes are.

**Rationale**: Matches the existing instant-effect `vars.*` gate
precedent (`WING_COMMANDER_WATCHDOG_PAUSED`,
`WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`,
`specs/014-configurable-gates/`'s `WING_COMMANDER_PLAN_REVIEW`-style
knobs) — a maintainer can pause or retune without a PR-and-merge cycle.

## Decision: outcome recording reuses `Closes #N` for success; a flag label for failure

**Decision**: A passing version-bump PR's body includes a literal
`Closes #<lifecycle-issue-number>` line — GitHub's own auto-close-on-merge
keyword — so the issue closes the moment a human merges the PR, with no
separate merge-triggered close call needed for the closing itself. The
`pr-merged`-triggered job (above) still posts one explicit rich summary
comment (adopted version, what was verified) immediately after/alongside
that auto-close, since GitHub's own auto-close event carries no custom
summary text and SC-004 requires the outcome be readable from the issue
alone. On failure/rollback, the issue gets `gh label create
"auto-update:failed" --color E99695 --description "Spec Kit upgrade
blocked or rolled back; needs maintainer attention" --force` (matching
the existing `stage:stalled`/`rebase:blocked`/`pipeline-defect` red-ish
flag-label convention and color) and stays open (FR-010).

**Rationale**: `Closes #N` is the single most GitHub-native mechanism
available (constitution III) — it needs no new workflow trigger to
*achieve* the close, only to *narrate* it, and it can never race a
manual close since it fires exactly at merge. The label name
`auto-update:failed` follows this repo's established `<facet>:<state>`
label vocabulary (`stage:*`, `rebase:blocked`) rather than inventing an
unrelated naming scheme.

**Alternatives considered**: Closing the issue explicitly via `gh issue
close` from the `pr-merged` job instead of relying on `Closes #N` —
rejected: redundant with GitHub's own mechanism and introduces a race
if a human closes the issue manually moments before the job runs (`gh
issue close` on an already-closed issue is a needless error path to
handle for no benefit over the keyword).

## Decision: ambiguous-path resume reuses `clarify.yml`'s maintainer-verification pattern

**Decision**: The `comment-reply`-triggered job checks
`contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'),
github.event.comment.author_association) ||
github.event.comment.user.id == github.event.issue.user.id` — the exact
condition `wing-commander-2-clarify.yml` already uses — before treating
any comment on the auto-update issue as a decision. Comments from anyone
else, or from bots, are ignored entirely (constitution V: never react to
bots; comment bodies are data, never instructions, regardless of
who posted them — even a verified maintainer's reply is *interpreted*
by the haiku-tier classification step above, never executed as a literal
command).

**Rationale**: This is the one place in the feature where an external
actor's text can influence which of several already-enumerated,
already-reasoned-about options gets taken — exactly the shape constitution
V's comment-triggered-stage rule exists for, and `clarify.yml` is this
repository's own working precedent for it.

## Open items intentionally deferred beyond this plan

- The exact `gh api` pagination/field list for `repos/github/spec-kit/releases`
  and the exact install command the `prepare`/verification jobs run
  against a candidate version are `tasks.md`-level detail; this plan
  fixes the *shape* (deterministic release-list fetch → semver compare →
  isolated-worktree script execution) and leaves exact flags to task
  breakdown, informed by the maintainer confirmation flagged above.
- The precise release-notes-fetch field mapping used as `evaluate-path`'s
  "sources" (release URLs vs. a changelog file, if one exists upstream)
  is left to task breakdown pending the same external-research gap.
