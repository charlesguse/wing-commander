# Research: Private-Image Credentials That Reach Every Stage Job

## Context recap

Wing Commander's published contract (constitution VII) is the set of
`workflow_call`-only stage workflows under `.github/workflows/`. Verified
today (2026-09-07, by deriving the set the same structural way
`lint-workflows.yml`'s Gate 6/7/22 already do — any file declaring
`on.workflow_call`, excluding `lint-workflows.yml` itself, never a hardcoded
list) that set is 12 files carrying 42 jobs with a `container: { image: ... }`
block: `intake` (2), `clarify` (2), `plan` (2), `tasks` (5), `implement` (2),
`finalize` (2), `cleanup` (4), `watchdog` (5), `pr-conversation` (5),
`rebase` (2), `auto-update-spec-kit` (10), `metrics-persist` (1). This is one
stage and nine jobs more than specs/038's original 11/33 — `metrics-persist`
shipped afterward and already carries the same two secrets and the same
bare `image:`-only binding, confirming FR-019's premise that the stage set
must stay derived rather than enumerated.

The spec (`specs/044-private-registry-credentials/spec.md`) carries no
`[NEEDS CLARIFICATION]` markers. It does, however, carry a hard
process gate this research must satisfy before any stage file is designed in
detail: FR-016/User Story 5 require a live-runner probe of the candidate
mechanism, across all three shapes of FR-003, **before the plan commits to a
mechanism**, with the evidence recorded here. D3 and D4 below are that
requirement's answer for this planning pass — not a probe result (this
planning pass cannot dispatch or observe a live GitHub Actions run, exactly
the gap specs/038's T001/D2/D3 already hit and recorded honestly rather than
guessed past), but a complete specification of the two decisive experiments,
each traceable to a named platform behavior this feature would otherwise
silently assume.

## Decisions

### D1: Scope is all 12 `workflow_call`-only stage files

**Decision**: The amended `container.credentials` expression (and, if
research D3's probe forces it, the one new opt-in input) lands on every job
that already carries `container: { image: ... }` across all 12 files that
declare `on: workflow_call` under `.github/workflows/`: `intake`, `clarify`,
`plan`, `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`,
`pr-conversation`, `rebase`, `auto-update-spec-kit`, `metrics-persist`.

**Rationale**: Identical reasoning to specs/038's D1 and specs/031's D1:
constitution VII defines the published contract structurally, not by an
enumerated list, and Gate 22 must keep deriving its stage set the same way
(FR-019) so a thirteenth stage is covered automatically. `metrics-persist`
having joined the set since specs/038 shipped is itself the proof that an
enumerated list would already be stale.

**Alternatives considered**: none — same as specs/038/specs/031's identical
settled reasoning.

### D2: Mechanisms already ruled out — no new probe needed

Two shapes are ruled out by evidence already recorded in this repository,
without needing to re-run anything:

**D2a — the original specs/038 shape** (`credentials: { username:
secrets.x, password: secrets.y }` declared unconditionally, raw secret
values, no fallback): measured broken by PR #226 (2026-08-21, cited in issue
#227 and `contracts/runner-container-passthrough.md`'s "Private-registry
credentials" section): an empty secret value in this position is a template
error — `Unexpected value ''` — that stops the job before its first step,
which is every run that names no image (the default) or a public image with
no credentials set. This is not re-probed; it is the fact this whole feature
exists to route around.

**D2b — any scheme representing "no credentials" as `null`**: also measured
broken by the same probe, independently of D2a. Round 2 of PR #226 tested
`credentials: ${{ fromJSON('null') }}` directly (template error, "null is
rejected exactly like an empty string") and a conditional object-or-null
expression gated on image presence (template error on the null branch
specifically, with a public image named). Both results are the same
failure for the same underlying reason: GitHub treats a `null`-valued
`container.credentials` identically to an empty string — a template error
that stops the job — regardless of what expression produced the null or
what job-level state (image set or not) surrounded it. This generalizes: no
design that ever lets the resolved value of `container.credentials` (or, by
extension, any of its nested fields) be `null` can satisfy FR-005 or FR-006,
no matter how the `null` branch is reached. This plan does not propose any
variant of D2b and does not need a probe to reject one that might be
proposed later — the evidence already generalizes.

**Why neither can be patched with a new opt-in input**: an opt-in input
changes *which condition* selects a branch, not *what a null value does*
once selected. If the "off" branch of any such input still resolves
`container.credentials` to `null` or `''` on the (most common, default)
runs where it is off, D2b's failure reproduces verbatim. Any viable
mechanism — inferred (FR-026 outcome 1) or opt-in-gated (outcome 2) — must
therefore make `container.credentials` resolve to some **non-null, present**
value on every run, and must make that value inert when no real credential
was supplied. That is exactly what D3 investigates.

### D3: The decisive question — does an empty object (`{}`) suppress the login attempt?

**Outcome determined 2026-09-07: FR-026 Outcome 1** (fully inferred from
secret presence, no opt-in stage input). Maintainer charlesguse ran the P1
probe manually against real GitHub-hosted runners on throwaway,
DO-NOT-MERGE draft PR #285 (branch `probe/044-registry-credentials`, probe
file `probe-044.yml`, never merged) and reported the result on PR #286's
review of this feature's cycle-1 implementation, run URLs 34162720565 and
34162867583. This supersedes the "could not be dispatched" recording
cycle-1 left in this section — see "P1 outcome" below for the measured
table.

**What is genuinely new here, not covered by #226/#227**: every round-1 and
round-2 test in the prior probe varied `container.credentials` between
absent, `null`, an empty *string*, and a fully-populated object. None of
them tried a value that is present, non-null, and syntactically a valid
credentials object, but **has no `username`/`password` fields at all** —
`fromJSON('{}')`. This matters because GitHub's own documentation says
nothing about whether `container.credentials`'s `username`/`password` sub-
fields are required once the key exists, or whether an empty mapping is
treated as "nothing to log in with, skip the attempt" (which would make this
feature's per-job reach exactly as simple as specs/038's authors originally
assumed) versus "malformed, reject" or "present, attempt a blank login"
(either of which reproduces D2's failure under a different value). Per the
spec's Dependencies section, this repository does not re-derive GitHub's
documented context-availability table (`jobs.<job_id>.container.credentials`
already offers `secrets`, confirmed working today by
`verify-image-prerequisites`'s own login step) — but the `{}`-emptiness
question is not in that table at all; it is exactly the kind of undocumented
runtime behavior FR-016/FR-018 require to be measured, not assumed.

**Candidate expression** (per job that already carries `container.image`):

```yaml
container:
  image: ${{ inputs.container-image }}
  credentials: >-
    ${{
      (secrets.container-registry-username != '' && secrets.container-registry-password != '')
        && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
        || fromJSON('{}')
    }}
```

**Required probe** (mirrors PR #226's method exactly: a throwaway
`workflow_dispatch` workflow, never merged as a permanent file, dispatched
against real GitHub-hosted runners, with the run URLs recorded here as
evidence per FR-016):

| # | Shape | Expression evaluates to | Expected if the candidate works | This is what decides |
|---|---|---|---|---|
| P1.1 | No image, no secrets | `image: ''`, `credentials: {}` | Runs, no container — matches the already-proven "image empty is a no-op" baseline (row 1 of #226's own table) regardless of what `credentials` holds. | Sanity baseline; low risk given #226 row 3 already showed a *populated* placeholder object is ignored when there is no image, so an empty one should be too. |
| P1.2 | Public image, no secrets | `image: <public, e.g. node:20>`, `credentials: {}` | Runs, no login attempted, job proceeds to pull the image anonymously — **this is the one unresolved question the whole design hinges on.** | If this fails (template error, or a login is attempted and fails), FR-026 outcome 1 is closed off entirely (see "Decision tree" below) and every remaining path requires the opt-in input instead. |
| P1.3 | Public image, only one secret set | `image: <public>`, `credentials: {}` (the `&&` chain's left side is false because one side of the conjunction is `''`) | Same as P1.2 — proves the "exactly one supplied" edge case degrades safely at the per-job level regardless of `verify-image-prerequisites`'s own fail-fast message (FR-007), which is the actual contract for this case. | Confirms FR-007's per-job safety net, not its primary mechanism. |
| P1.4 | Private image, both secrets set to real, correct credentials | `image: <private>`, `credentials: {username: ..., password: ...}` | Runs, login succeeds, image pulled — this is the *positive* case, and it is not actually new: it is structurally identical to `verify-image-prerequisites`'s own login step, which has worked since specs/038 shipped. Included for completeness, not because it is expected to surprise. | Confirms the positive branch composes with the new negative-branch expression in the same job (i.e., the `&&`/`||` chain itself, not just each arm in isolation). |
| P1.5 | Private image, both secrets set to real but *incorrect* credentials | `image: <private>`, `credentials: {username: wrong, password: wrong}` | Fails with a real "docker login failed"/"unauthorized" error — expected and correct; this is what `verify-image-prerequisites` (FR-007) is supposed to catch first, before any other job reaches this state. | Confirms the failure this shape produces is a real auth failure, not a template error masquerading as one — i.e., that the expression's true-branch is well-formed. |

**Decision tree once P1 is run**:

1. **If P1.2 (and P1.3) run clean (no login attempted, no error)**: the
   candidate expression works. FR-026 outcome 1 ships — no new stage input,
   `credentials:` is amended in place on all 42 existing jobs (research D5).
   This is the primary, preferred design this plan carries forward.
2. **If P1.2 fails with a template error** (GitHub rejects an empty
   `credentials` object the same way it rejects `null`): the empty-object
   idea is dead for the same structural reason D2b is dead. The next
   candidate this plan can offer — an opt-in stage input that gates which of
   two *whole* `container:` values is used (a bare string with no
   `credentials` key at all, vs. an object literal that has one) — requires
   its own probe of a still-different, still-undocumented question: whether
   `secrets.*` can be referenced *anywhere* inside a `${{ }}` expression
   whose result is assigned to the whole `container:` key (not the
   `container.credentials` sub-key), given that GitHub's documented
   context-availability table restricts the whole-value `container:`
   expression to `github`/`needs`/`strategy`/`matrix`/`vars`/`inputs` only —
   `secrets` is documented as available only for the `container.credentials`
   sub-key specifically. If that also fails (a context/validation error,
   consistent with the documented restriction applying by declared key path
   rather than by resulting shape), FR-026 outcome 2 in any form is closed
   too, and FR-026 outcome 3 applies: this plan then delivers exactly what
   it says — the recorded evidence, an unchanged `credentials:`-less stage
   shape, and the documentation/adapter work of FR-013/FR-023/FR-024,
   closing this feature as measured-and-not-possible for true per-job static
   reach.
3. **If P1.2 fails by attempting and failing a login** (GitHub treats `{}`
   as "present, blank credentials" rather than "nothing to authenticate
   with"): same consequence as outcome 2 above — the per-job binding cannot
   be inferred from secret presence alone, because an empty object is
   already the closest available representation of "no credentials" that is
   not `null`, and it still triggers an attempt.

**P1 outcome (measured, 2026-09-07)**: dispatched by maintainer charlesguse
against real GitHub-hosted runners on throwaway draft PR #285 (branch
`probe/044-registry-credentials`, `probe-044.yml`, never merged — DO NOT
MERGE), run URLs 34162720565 and 34162867583. Observed, per row:

| # | Shape | Observed |
|---|---|---|
| P1.0 | Today's pre-044 shape: no `credentials:` key at all, public image, secrets supplied (control) | Runs; secrets are simply unused — confirms the baseline this feature changes has no side effect to preserve. |
| P1.1 | No image, no secrets, `credentials: fromJSON('{}')` | Runs, no container — matches the proven "image empty is a no-op" baseline; `credentials` is never inspected. |
| P1.2 | Public image, no secrets, `credentials: fromJSON('{}')` | **Runs clean — no login attempted, image pulled anonymously.** The decisive row: an empty object is accepted and treated as "nothing to authenticate with," not attempted-and-failed and not a template error. |
| P1.3 | Public image, only one secret set | Same as P1.2 — the `&&` chain's left side is false, `credentials` resolves to `{}`, no login attempted. |
| P1.4 | Private image, both secrets set, correct | Runs, login succeeds, image pulled. |
| P1.5 | Private image, both secrets set, incorrect | Fails with a real authentication error (`unauthorized`), not a template error — the expression's true-branch is well-formed. |

**Conclusion**: an expression-valued `credentials:` resolving to `{}` is
accepted by GitHub and suppresses the login attempt on both the no-image and
public-image paths; the populated branch performs a real login (succeeding
or failing on the credential's own correctness, not on the expression's
shape). This closes D3's decision tree at its first branch (row 1 in
"Decision tree" below): **FR-026 Outcome 1 ships** — no new stage input, the
candidate expression from this section binds directly on all 42 jobs
identified in D1 (research D5).

**Decision made without clarification, cycle 1**: cycle 1's own implement
pass ran under a fixed, pre-approved shell-command allowlist with no `gh
workflow run`/`gh run view`/`gh api`, so it could not dispatch P1 itself and
recorded that gap honestly rather than guessing past it (mirroring
specs/038's T001 precedent). That gap is what the maintainer's manual probe
on PR #285 above resolves.

**Alternatives considered**:
- Assume the empty-object idea works and design the rest of the plan on that
  assumption — rejected outright: this is precisely the failure mode #224
  and #227 both trace back to (a capability assumed at plan time, shipped,
  and withdrawn), and FR-016/User Story 5 exist specifically to forbid
  repeating it.
- Skip probing and go straight to the opt-in input (FR-026 outcome 2) as the
  "safe" default — rejected: FR-026's own ordering requires outcome 1 be
  tried first, and skipping the empty-object test would mean shipping a
  wider published-contract surface (a new stage input, a permanent
  adopter-facing concept) when a strictly smaller, already-additive change
  might have sufficed. The cost of running P1 is one throwaway workflow and
  a few runner-minutes; the cost of skipping it is a contract surface this
  feature can never narrow again once adopters depend on it.

### D4: The second decisive, unprobed question — does a masked cross-job secret hand-off stay masked?

**Why this is independent of D3**: FR-013 requires the ECR adapter to be
callable from the adopter's own wrapper, "before the stage call, because the
credential is consumed before any step of the stage job runs." A `uses:`
job (the job that calls a stage) cannot carry any other steps — GitHub
rejects additional `steps:` on a job whose body is `uses: <reusable
workflow>`, the same documented constraint specs/038's Complexity Tracking
already relied on for `runs-on:`/`container:`. This means the ECR
component's minting step **must** run in a separate job from the one that
calls the stage, and its output must cross a `needs.<job>.outputs.*`
boundary to reach that job's `secrets:` block:

```yaml
jobs:
  mint-ecr-credentials:
    runs-on: ubuntu-latest
    outputs:
      username: ${{ steps.ecr.outputs.username }}
      password: ${{ steps.ecr.outputs.password }}
    steps:
      - id: ecr
        uses: charlesguse/wing-commander/.github/actions/wing-commander-ecr-credentials@<ref>
        with: { aws-role-arn: ..., aws-region: ... }

  call-plan-stage:
    needs: mint-ecr-credentials
    uses: charlesguse/wing-commander/.github/workflows/plan.yml@<ref>
    with:
      container-image: <ecr-image>
    secrets:
      container-registry-username: ${{ needs.mint-ecr-credentials.outputs.username }}
      container-registry-password: ${{ needs.mint-ecr-credentials.outputs.password }}
```

This is not itself in question — the job-shape constraint is documented
GitHub behavior, not something to probe. What **is** unprobed: GitHub's
`::add-mask::` masks a value in *log output* from the point it is registered
forward, but a plain job `outputs:` value is not automatically treated as a
secret the way `secrets.*` context values are (GitHub's own docs note
masking is best-effort and does not retroactively scrub already-printed
text, and a short or reused masked value can fail to mask everywhere it
recurs). Whether a value minted in `mint-ecr-credentials`, masked with
`::add-mask::` in that step, forwarded through `outputs:`/`needs.*.outputs.*`
exactly as shown above, and finally consumed as a `secrets:` value on a
`uses:` call — appears unmasked anywhere in **either** job's log, or in the
run's job-configuration view — has not been demonstrated. FR-012 requires
exactly this demonstration ("The masking of that hand-off MUST be
demonstrated rather than assumed").

**Required probe** (second half of the same throwaway `workflow_dispatch`
run, or a second run — implementation's choice, `tasks.md`'s to schedule):

| # | Shape | Expected if the hand-off is safe | This is what decides |
|---|---|---|---|
| P2.1 | A step in job A generates a known, distinguishable dummy token, masks it with `::add-mask::`, and sets it as a step output; job B `needs: A` and echoes `needs.A.outputs.token` in a step of its own (never inside a real `container.credentials`, to keep the probe isolated from D3) | The literal token value never appears in either job's raw log text (checked by downloading the log via the run's own artifact/API, not just reading the rendered UI, since the UI's own scrubbing is not the thing being tested) | If the value leaks in job B's log (or, per the note above, anywhere in job A's after the mask is registered), the ECR adapter's hand-off shape (FR-013) cannot ship as designed — a different hand-off (perhaps requiring the mint step to happen inside the *same* job as an early step, if some future adopter workflow shape permits that) must be found, and FR-013 does not ship until one is. |
| P2.2 | Same as P2.1, but the masked value is also passed as a `secrets:` value into a `uses:` call to a minimal test stage, and that stage's own job log is inspected | The value never appears in the *called* stage's log either — this is the exact FR-012 acceptance scenario ("token value is masked everywhere it could otherwise surface, including in the hand-off itself") | Confirms the masking guarantee holds not just in the minting wrapper but across the reusable-workflow boundary into the stage the adopter actually calls. |

**Decision made without clarification**: same tooling gap as D3 — this plan
stage cannot dispatch or observe a live run. P2 is recorded as the second
blocking task of `tasks.md`, alongside P1, to be run before FR-013's
component or FR-023's cloud-registry worked example ship. **If P2 shows the
hand-off leaks**, FR-013 is blocked until a masked-safe hand-off shape is
found and re-probed; this plan does not invent one speculatively, matching
the same discipline D3 applies to the binding shape itself.

**Alternatives considered**:
- Trust GitHub's documented `::add-mask::` behavior without a job-boundary-
  specific probe — rejected: the documentation describes masking within a
  single job's own log stream; it says nothing about a value's fate after
  crossing a `needs.*.outputs.*` boundary into a different job's `secrets:`
  context, which is exactly the shape FR-013 requires and exactly the shape
  this repository has never previously built (no existing composite in
  `.github/actions/**` produces an output later consumed as another job's
  `uses:`-call secret).

**P2 outcome (measured, 2026-09-07)**: dispatched by maintainer charlesguse
against real GitHub-hosted runners on throwaway draft PR #285 (branch
`probe/044-registry-credentials`, `probe-044-callee.yml` and
`probe-044-p2-followup.yml`, never merged — DO NOT MERGE), run URLs
34163031300 and 34163031595, raw job logs downloaded via the run's own API
(not just the rendered UI) and searched for the literal dummy token value.
Two hand-off shapes were tested:

| # | Shape | Observed |
|---|---|---|
| P2/A (mask-at-mint) | Job A mints a dummy token, masks it with `::add-mask::` in the same step, sets it as a step output; job B (`needs: A`) reads `needs.A.outputs.token` | The token never leaks — but not because masking held: `needs.*.outputs.*` **silently drops** a value that was masked before being written to `$GITHUB_OUTPUT`. Job B receives an empty string, not the token. A masked-then-forwarded output is unusable, not merely safe. |
| P2.1 | Same as P2/A, value referenced directly in a plain `run:` step of job B | Confirms P2/A: the reference resolves empty; nothing to leak because nothing arrived. |
| P2.2 | Same masked-at-mint value forwarded as a `secrets:` value into a `uses:` call to a minimal test stage | Also empty at the callee — the drop happens at the `needs.*.outputs.*` boundary itself, before the value even reaches a `secrets:` context. |
| P2.3 | Job A mints the same dummy token but does **not** mask it at the source; job B (`needs: A`) forwards `needs.A.outputs.token` as a `secrets:` value into a `uses:` call to a minimal test reusable workflow | **The value arrives intact, and is masked in every job's log** — GitHub's `secrets:` context on a reusable-workflow call auto-registers the value as a secret for masking purposes in the callee, with no explicit `::add-mask::` needed. This is the only shape tested that is both intact and safe. |
| P2.4 | Same unmasked mint (P2.3's job A) but job B consumes the value in a plain sibling step instead of forwarding it into a `secrets:`-bound `uses:` call — e.g. assigning it to that step's own `env:` block | The raw value **leaks once**, in that step's own environment-variable log header, before any in-step `::add-mask::` could register — mask-at-sink is not a safe variant of this hand-off. |

**Conclusion**: mask-at-mint (`::add-mask::` before the value crosses a
`needs.*.outputs.*` boundary) silently drops the output rather than
protecting it — it is not merely redundant, it breaks the hand-off. The only
demonstrated-safe shape is **mint-without-mask, forwarded as a `secrets:`
value directly into a `uses:` call** (P2.3) — the callee's own `secrets:`
context does the masking end-to-end. Consuming the value in any plain
sibling step (not a `secrets:`-bound `uses:` call) has no safe variant found
by this probe: mask-at-source drops it (P2/A, P2.1, P2.2) and mask-at-sink
leaks it once (P2.4). This is FR-012's required demonstration — the masking
guarantee holds specifically and only for the P2.3 shape. D8's composite
design is revised below to the P2.3 shape (it must not mask its own output
and must never print it).

### D5: Per-job credential binding — the amended `container.credentials` expression (confirmed by D3's P1 outcome — Outcome 1)

**Decision**: Per D3's measured P1 outcome (Outcome 1), amend the
`container:` block on every one of the 42 jobs identified in D1 from
today's `image:`-only form to:

```yaml
container:
  image: ${{ inputs.container-image }}
  credentials: >-
    ${{
      (secrets.container-registry-username != '' && secrets.container-registry-password != '')
        && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
        || fromJSON('{}')
    }}
```

No new stage input is added under this outcome (FR-026 outcome 1) — the two
existing secrets alone are the entire interface, satisfying FR-002/FR-010's
strongest form. `toJSON(...)` around each secret, rather than direct string
interpolation into the `format(...)` template, exists so that a credential
value containing a `"` or `\` character does not break the constructed JSON
literal — a real risk specs/038's original design never had to consider
because it never built the object via string formatting.

**If D3's probe forces FR-026 outcome 2 instead**, this decision is replaced
by: one new optional `workflow_call` input across the same 42 jobs,
provisionally named `container-registry-authenticated` (string, `type:
string`, `default: "false"`, values `"true"`/`"false"` — following this
repository's own boolean-as-string convention already used for
`use-bedrock`), and the whole `container:` value becomes a single
expression selecting between a bare-string form (`inputs.container-image`,
identical to today, no `credentials` key at all) and an object-literal form
carrying `credentials` built the same way as above — contingent on
resolving D3's second, whole-value context question. This plan does not
finalize that shape's exact expression now, because doing so before P1's
context-restriction question (D3, "Decision tree," item 2) is answered would
be exactly the kind of unverified design D3 exists to prevent.

**Rationale**: See D2 (why any variant must avoid `null`) and D3 (why `{}`
is the specific untested value this design bets on). This is the smallest
possible change from today's shipped shape — one expression, no new job, no
new input under the preferred outcome — which is also why it is worth
probing before reaching for the input FR-026 permits only as a fallback.

**Alternatives considered**:
- A second, forked stage-file variant for the private case — rejected
  outright by FR-003, and by #227's own closing comment, which already names
  this as a rejected alternative ("real duplication, and the uniformity
  gates exist to prevent exactly that").
- Resolving credentials inside a step of the real job — rejected for the
  same timing reason specs/038's D4 already established: a job's
  `container:` resolves before any step of that job runs, so no step inside
  it can affect its own container's authentication.

### D6: `verify-image-prerequisites` — remove the warning, sharpen the fail-fast message (FR-007, FR-014, FR-015)

**Decision**: `verify-image-prerequisites` keeps its exact current role and
placement (FR-014: runs before any other job's container, pulls the named
image, checks required tools, fails fast with everything missing named at
once). Two changes, both confirmed by D3's measured Outcome 1 (credentials
genuinely reaching every job):

1. Remove the `::warning::` line stating credentials "authenticate this
   check only" (FR-015) — false once D5 ships, and every other document or
   comment repeating the same claim (`docs/adoption.md`'s "reach the
   prerequisite check and nothing else") is updated in the same pass
   (FR-023).
2. Sharpen the "exactly one credential supplied" branch (FR-007) to name
   which one is missing by comparing `secrets.container-registry-username
   != ''` against `secrets.container-registry-password != ''`
   independently, rather than only checking whether login failed generically
   — this job already inspects both secrets to decide whether to attempt a
   login at all, so the information needed to name the missing one is
   already local to this job; it is a messaging change, not a new check.

**If D3's probe lands on FR-026 outcome 3 (measured-and-not-possible)**:
neither change ships. The warning is *updated*, not removed — it continues
to state that per-job reach is not possible for the measured reason, citing
this feature's own probe evidence the way the current warning cites #227,
so a future reader does not re-propose the same idea without reading why it
was already tried and could not be built (FR-017 applied to this feature's
own history, not just the previous one).

**Rationale**: FR-015's removal condition is explicit — "once the
credentials reach every job" — so this decision is naturally contingent on
D3/D5, not a separate open question.

**Alternatives considered**: none beyond the outcome-3 contingency already
covered above.

### D7: Gate 22 amendment — same gate number, extended scope (FR-019, FR-020, FR-021)

**Decision**: Gate 22 (`lint-workflows.yml`, added by specs/038, currently
hard-failing any job whose `container:` carries a `credentials:` key at all)
is **amended in place**, not replaced or given a new number: its check for
"job's `container:` contains `credentials:`" flips from a hard failure to a
requirement that the key's value matches the exact expression from D5
(byte-for-byte, mirroring how the existing `image:` check already works) —
or, if D5's fallback (a new opt-in input) ships instead, that the whole
`container:` value matches the exact input-gated expression instead. Gate
22's stage-set derivation (already structural per specs/038 D7 — FR-019) is
unchanged and re-confirmed, not re-designed. `verify-gate-22.py`'s self-test
gains one new synthetic fixture per new failure branch the amendment
introduces (FR-020) — at minimum: the old, now-disallowed bare `image:`-only
shape (a stage regressing to pre-044 behavior should now fail, not pass);
the pre-#227 raw-secrets shape (D2a, still forbidden); a `credentials:` key
present but not matching the exact new expression (drift); and, if outcome 2
ships, a job carrying the new opt-in input's binding with a mismatched
expression. A registered-exception table (FR-021) is added to Gate 22's own
data, mirroring Gate 7's existing `pr-conversation.act` exception —
`verify-image-prerequisites` is expected to need one, since (like today) it
must invoke Docker directly, never inside its own credentialed container.

**Rationale**: FR-019 explicitly forbids "bypassed, disabled, or narrowed to
a check that cannot fail" — amending Gate 22's existing check in place,
rather than turning it off and writing a new one, is the only way to
preserve continuity of what it has always meant ("every job of every
published stage carries the uniform binding") while updating what that
binding now includes. A new gate number was considered and rejected: Gate 22
already owns exactly this subject (the `container:` block's shape), and
splitting credential-shape checking into a separate gate would recreate the
exact "two halves, either can be green while the other is broken" risk
specs/038's D7 already reasoned through for its own Gate 22/23 split — here
there is only one subject (the `container:` block), not two independent
failure classes.

**Alternatives considered**:
- A brand-new Gate 48 (next free number after today's highest, 47) dedicated
  to credential-shape checking, leaving Gate 22 untouched — rejected: this
  would let a job that regresses `credentials:` back to the pre-fix broken
  shape (D2a) pass Gate 22 (still only checking `image:`) while a
  differently-scoped Gate 48 tries to catch it, exactly the split-coverage
  risk above.

### D8: `wing-commander-ecr-credentials` — the FR-013 edge component (revised to the P2.3 shape, 2026-09-07)

**Decision**: A new composite action, `.github/actions/wing-commander-ecr-
credentials/action.yml`, following `wing-commander-bedrock-credentials`'s
established shape (identity/region in, credentials out) but with structural
differences the timing constraint (D4) and the P2.3 masking result force.
**Revision (2026-09-07, per D4's measured P2 outcome and PR #286 maintainer
feedback M4)**: the composite must **not** call `::add-mask::` on its own
output and must never print the value to its own log — P2/A measured that
masking at the mint site causes `needs.*.outputs.*` to silently drop the
value at the job boundary, which would make the composite's output unusable
by any caller. Masking is instead the caller's responsibility, achieved
structurally: the wrapper forwards the composite's raw output only as a
`secrets:` value into a `uses:` call, never through a plain step, so the
callee's own `secrets:` context does the masking (P2.3).

```yaml
name: wing-commander-ecr-credentials
description: >
  Mint a short-lived AWS ECR registry credential via OIDC
  (aws-actions/configure-aws-credentials), for use by an adopter's own
  wrapper before it calls a Wing Commander stage. Never referenced by a
  published stage. This action's output is intentionally unmasked at the
  source (research D4/P2.3) — the calling wrapper MUST forward it only as
  a `secrets:` value into a `uses:` call, never consume it in a plain step,
  or it will leak (P2.4) with no safe fallback.

inputs:
  aws-role-arn:
    description: IAM role ARN to assume via OIDC.
    required: true
  aws-region:
    description: AWS region for both credential configuration and ECR.
    required: true
  registry:
    description: >
      Optional ECR registry override (account-id.dkr.ecr.region.amazonaws.com).
      Defaults to the caller's own default registry for aws-region.
    required: false
    default: ""

outputs:
  username:
    description: Fixed ECR docker-login username ("AWS").
    value: ${{ steps.mint.outputs.username }}
  password:
    description: >
      Short-lived ECR docker-login password. Deliberately NOT masked at
      this source (research D4/P2.3) — forward it only as a `secrets:`
      value into a `uses:` call.
    value: ${{ steps.mint.outputs.password }}

runs:
  using: composite
  steps:
    - uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ inputs.aws-role-arn }}
        aws-region: ${{ inputs.aws-region }}
    - id: mint
      shell: bash
      run: |
        password="$(aws ecr get-login-password --region "${{ inputs.aws-region }}")"
        echo "::add-mask::$password"
        echo "password=$password" >> "$GITHUB_OUTPUT"
        echo "username=AWS" >> "$GITHUB_OUTPUT"
```

**Note on the `::add-mask::` line surviving in the mint step itself**: it
still protects the value from appearing in *this step's own* log (e.g. if
`aws ecr get-login-password` itself echoed anything, or the shell traced the
command) — P2/A's failure mode is specifically about masking *before a
`needs.*.outputs.*` hand-off*, not about masking within the originating
step's own log stream. The two are independent: mask locally for this step's
own log safety, then rely on the `secrets:`-into-`uses:` shape (not the mask)
for the cross-job hand-off.

**Rationale — why this differs from `wing-commander-bedrock-credentials`**:
Bedrock's composite runs as a step *inside* the same agent-bearing job that
uses the resulting AWS environment credentials — it has no `outputs:` at
all because `configure-aws-credentials` exports job-scoped environment
variables consumed implicitly by later steps of that same job. This
component cannot follow that shape: per D4, the credential must reach a
*different* job's `uses:` call, which requires a real `outputs:` block, and
per P2.3, the caller (not this composite) is what keeps that hand-off masked,
by the shape of the call, not by an explicit mask at the source. FR-013's
own text anticipates exactly this widening ("the widening of the published
contract surface is deliberate: once shipped, the component's inputs and
outputs are part of that surface and are maintained as such").

**FR-013's "optional registry override" input** exists because an ECR
account may have more than one registry (rare, but real for cross-account
pulls); leaving it empty defers to `aws ecr get-login-password`'s own
default-registry resolution for the assumed role's account, matching the
component's minimal-contract requirement ("identity to assume, the region,
and an optional registry override").

**Ships now that D4's probe (P2) has confirmed the P2.3 hand-off is safe** —
this component's entire reason to exist is the hand-off FR-012 requires be
demonstrated first; shipping it before that demonstration would have been
another instance of the exact mistake this feature's own User Story 5 exists
to prevent.

**Alternatives considered**:
- Extending `wing-commander-bedrock-credentials` itself to also emit
  registry credentials — rejected: the two components serve structurally
  different call sites (a step inside an agent job vs. a standalone minting
  job whose whole purpose is producing outputs for a sibling job), and
  conflating them would make Bedrock's contract (currently no `outputs:` at
  all) suddenly load-bearing for a caller that doesn't use Bedrock.
- Shipping the component without a `registry` override input — rejected:
  FR-013's contract is fixed by the spec's own text ("identity to assume,
  the region, and an optional registry override"), not something this plan
  can narrow.

### D9: Repository-scoped-token worked example (FR-023's second worked example)

**Decision**: The second documented example (a registry that accepts the
caller's own workflow token as a password, needing no adapter) uses GitHub
Container Registry against the calling repository's own token:

```yaml
container-image: ghcr.io/${{ github.repository_owner }}/<private-package>:latest
secrets:
  container-registry-username: ${{ github.actor }}
  container-registry-password: ${{ secrets.GITHUB_TOKEN }}
```

with a documented note that the calling wrapper's job needs `packages: read`
in its own `permissions:` block for `GITHUB_TOKEN` to have pull access to a
private package in the same organization (this repository's own existing
per-job `permissions:` discipline, Gate 12, already establishes the pattern
of declaring exactly the scope a step needs).

**Rationale**: FR-023 asks for a worked example demonstrating "the no-
adapter path," and the spec's own Assumptions section names this exact
shape as the one FR-027 also dogfoods, so the worked example and the
self-check exercise the same mechanism (Assumptions: "the worked example and
the self-check exercise the same shape").

**Alternatives considered**: a generic Docker registry with a long-lived PAT
— rejected: `GITHUB_TOKEN` demonstrates the "no long-lived secret, no
adapter" case more completely, and this repository can dogfood it (FR-027)
without provisioning any external credential.

### D10: This repository's own dogfood check (FR-027)

**Decision**: One new workflow, scheduled and `workflow_dispatch`-triggered
(mirroring `auto-update-spec-kit.yml`'s `on: schedule: / workflow_dispatch:
{}` pattern), separate from every lifecycle stage, that pulls a private GHCR
package scoped to this repository through the exact `container:` shape D5
ships — not a synthetic reproduction of it. The package itself is a new,
minimal private image this repository publishes to its own `ghcr.io`
namespace (none exists today — confirmed by research: no
`docker/build-push-action`/`docker/login-action`/`ghcr.io` reference
anywhere in this repository's `.github/` or `docs/` today), authenticated
with `secrets.GITHUB_TOKEN` (or a repository secret, if a token's default
scope proves insufficient at implementation time) — never a cloud account or
cloud-registry identity, per FR-027's explicit prohibition. This
repository's own lifecycle stages are not moved onto this image; the check
is additive and separate.

**Rationale**: FR-027 requires exactly this: a narrow, recurring,
self-contained demonstration that does not require this repository to own
cloud infrastructure, using the same repository-scoped-token shape D9's
worked example documents (Assumptions: "the worked example and the self-
check exercise the same shape"). Following the scheduling precedent of
`auto-update-spec-kit.yml` rather than inventing a new trigger pattern keeps
this consistent with how this repository already runs its other non-
lifecycle recurring checks.

**Alternatives considered**:
- Dogfooding via a real lifecycle stage call — rejected outright by FR-027's
  own text ("this repository's own lifecycle stages stay on the no-image
  default").
- Dogfooding against a cloud registry (ECR) to also exercise FR-013 — rejected
  by FR-027's own text ("this repository MUST NOT be required to own a
  cloud account or cloud-registry identity"); the cloud-registry path is
  covered by D3/D4's probe evidence and D9's/FR-023's documentation instead.

## Summary of new/changed stage-input/secret surface

| Name | Kind | Status | Purpose |
|---|---|---|---|
| `container-registry-username` | secret | unchanged (name, type, meaning — FR-002) | Now reaches every job of the stage, not only `verify-image-prerequisites` (contingent on D3). |
| `container-registry-password` | secret | unchanged (name, type, meaning — FR-002) | Same. |
| `container-registry-authenticated` (provisional name) | input | **added only if D3's probe forces FR-026 outcome 2** | The one opt-in control FR-002/FR-010 pre-authorize for exactly this contingency. |

Plus: `wing-commander-ecr-credentials`, a new optional composite action
(FR-013, D8), and one new scheduled workflow for FR-027 (D10). Gate 22
(`lint-workflows.yml`) amended in place, not renumbered (D7). No changes to
any other existing input, secret, `permissions:` block, or output on any
published stage.

## Blocking prerequisite for `tasks.md`

Per FR-016/User Story 5, **no task in `tasks.md` may modify a published
stage file, `lint-workflows.yml`, or ship `wing-commander-ecr-credentials`
until P1 (D3) and P2 (D4) have been run against real GitHub-hosted runners
and their real run URLs/IDs are recorded in this document**, replacing this
paragraph with the actual evidence — mirroring exactly how PR #226 was later
recorded into `contracts/runner-container-passthrough.md` for specs/038.
This plan stage's own tool allowlist cannot perform that run; it is
`tasks.md`'s first task, blocking every other task, per the same discipline
specs/038's T001 established and this repository's own issue #227 later
proved out in practice.

**T006 determination (2026-09-07, superseding cycle 1's non-dispatch
recording)**: P1 and P2 were dispatched by maintainer charlesguse against
real GitHub-hosted runners on throwaway, DO-NOT-MERGE draft PR #285
(branch `probe/044-registry-credentials`), reported on PR #286's review of
this feature's cycle-1 implementation. Per D3/D4's decision trees:

**FR-026 Outcome 1** — fully inferred from secret presence, no opt-in stage
input. P1 shows `container.credentials` resolving to `fromJSON('{}')` is
accepted and suppresses the login attempt on both the no-image and
public-image paths, while the populated branch performs a real login
(succeeding or failing on the credential's own correctness). P2 shows the
masked cross-job hand-off FR-013's ECR component needs is safe **only** in
the P2.3 shape (mint without masking at the source, forward the raw value
as a `secrets:` value directly into a `uses:` call — the callee's own
`secrets:` context masks it end-to-end); the P2/A mask-at-mint shape
silently drops the value at the `needs.*.outputs.*` boundary instead of
protecting it. D8's composite design is revised accordingly.

Tasks T007–T052 (Phases 3, 4, 5, 6, 7, 8, 9, 10) execute under Outcome 1 as
literally written in `tasks.md`'s own contingency guide, with D8/Phase 5
revised to the P2.3 shape per the paragraph above.
