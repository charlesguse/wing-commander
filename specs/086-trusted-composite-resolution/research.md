# Research: The Loop's Own Code Comes From a Trusted Commit

Input: `spec.md` carries no `[NEEDS CLARIFICATION]` markers. The decisions
below fix the concrete mechanism (sidecar path and naming, checkout shape,
staging defense, gate structure) the tasks stage needs before it can write
file-level tasks, and record why each departs from — or matches — the
repository's existing sidecar precedents.

## D1: One sidecar checkout per job, this same repository at `github.sha`, path `.wc-pristine-repo`

**Decision**: Every job that resolves a local composite gains one
`actions/checkout@v5` step: `repository` defaulted to the current
repository (no `pipeline-repo` input — board-loop.yml is not a published
stage and has no adopter-supplied pipeline ref, spec.md Assumptions),
`ref: ${{ github.sha }}`, `path: .wc-pristine-repo`, `persist-credentials:
false`, default `fetch-depth` (a single commit's tree is all a composite
needs). Every `uses: ./.github/actions/<name>` in the file becomes
`uses: ./.wc-pristine-repo/.github/actions/<name>`.

**Rationale**: `github.sha` is the exact commit whose `board-loop.yml` is
running, on every trigger this file has (`schedule`, `workflow_dispatch`,
`pull_request: closed`) — the same commit the existing helper-script
snapshot already uses via `$GITHUB_SHA` (issue #583), so FR-003/FR-004's
"one provenance" claim is a fact about the mechanism, not just a written
rule. `job_workflow_sha` and the OIDC-audience fallback the published
stages' `wing-commander-context` header documents are irrelevant here:
that machinery exists to resolve the *calling* workflow's pinned version
of an *adopter-configurable, potentially separate* pipeline repository
(specs/010-reusable-pipeline D3) — board-loop.yml is not called, has no
adopter, and is always resolving itself.

**Why `.wc-pristine-repo` and not `.wing-commander-pipeline`**: the
published-stage sidecar name (`.wing-commander-pipeline`) is loaded with
the pipeline-repo/OIDC machinery above; reusing it here would suggest to a
future reader that board-loop.yml also takes a `pipeline-repo` input, which
it does not and per FR-062/FR-063 (spec 057) never will. `wc-pristine`
already names this file's *other* trusted-provenance mechanism (the
`$RUNNER_TEMP/wc-pristine` helper/schema snapshot); `.wc-pristine-repo`
extends that naming to "the same idea, but a real checkout instead of a
tar extract" rather than borrowing a name that means something narrower
elsewhere in the repository.

**Alternatives considered**: A `path:` outside `GITHUB_WORKSPACE` (e.g.
`../wc-pristine-repo`), which would let the sidecar sit entirely outside
the item's own git working tree and remove D4's question by construction —
rejected: `actions/checkout` refuses a path outside `GITHUB_WORKSPACE`
(confirmed by `auto-update-spec-kit.yml`'s own comment at the site it
checks its pipeline sidecar out: "actions/checkout refuses a path outside
GITHUB_WORKSPACE"). Extending the existing `git archive`/tar snapshot to
also cover composites — rejected: `git archive` produces file content, not
a `uses:`-addressable directory GitHub Actions can invoke a composite
from; a real checkout is the only mechanism that produces one (confirmed
by inspecting how `uses: ./<path>` resolution actually works — it is a
literal filesystem lookup relative to the workspace at step-execution
time, not something a `run:` step's output can redirect).

## D2: Placement — immediately after the job's own trusted-content step, before the first composite, credential mint, or agent step

**Decision**: In `fix`, `review`, `readiness` (the three jobs Gate 98
already instruments), the sidecar checkout is placed immediately after the
existing "Snapshot helper scripts (before any agent runs)" step — both are
now "established from trusted content before anything else runs" steps,
adjacent by convention. In `select`, `triage`, `route`, `prove-gate`,
`prove` (which have no helper-script snapshot, since #583's exposure never
applied to them), the sidecar checkout is placed immediately after the
job's own initial `Checkout` step. In every job, it precedes the job's
first `uses: ./.wc-pristine-repo/...` reference, which is always
`wing-commander-context` (the credential-minting composite) — so FR-002's
"before any credential is minted" is satisfied as a direct consequence of
being the first composite call in every job, not a separately-tracked
rule.

**Rationale**: Matches the existing precedent's own ordering discipline
(`wing-commander-lifecycle-gate`'s header: "before wing-commander-preflight,
before any branch checkout, and before any agent step") applied to the one
thing board-loop.yml's item-branch jobs do differently — they check out or
switch to item content mid-job, so "before any branch checkout" becomes,
concretely, "before the branch switch (`fix`'s resume path) or before the
job's only checkout is already the item's branch (`review`/`readiness`)."

## D3: `resolve-model` needs no new step; FR-011 covers it by construction, not by addition

**Decision**: `resolve-model` has no checkout and no `uses: ./.github/actions/...`
reference today, and gains neither. Nothing is added to it.

**Rationale**: FR-011 requires the *rule* to apply uniformly, not that
every job carry a copy of a step it has no use for — spec.md's own framing
("a per-job allowlist is the same shape as the gap being fixed") is about
the gate's coverage, not about padding jobs with no-op checkouts. Gate 99
(D5) is written to fail on *any* job that ever gains a
`uses: ./.github/actions/...` reference without the preceding sidecar
checkout, `resolve-model` included, so the day this job (or any future
job) starts resolving a composite, the same unconditional check already
covers it with no gate edit required.

## D4: Staging defense is `.gitignore`, not the exclude-pathspec or `clean: false` disciplines the existing sidecars rely on

**Decision**: `.wc-pristine-repo/` is added to this repository's own
`.gitignore`. FR-007 ("MUST NOT be committed to, pushed to, or otherwise
included in the board item's branch or pull request") is satisfied because
`git add` — any invocation, `-A`, `.`, or a specific path — skips an
ignored, untracked directory automatically; nothing needs to remember to
exclude it.

**Rationale**: The two existing sidecar precedents each rely on a
different, narrower discipline instead of `.gitignore`: `clarify.yml` et
al. pass `clean: false` on the later item-content checkout (so `git clean`
does not delete the sidecar) and instruct their agent's prompt, in prose,
never to `git add -A`/`git add .`; `auto-update-spec-kit.yml` runs `git add
-A -- . ':(exclude).wing-commander-pipeline'` in its own deterministic
commit step. Neither transfers cleanly to board-loop's `fix` job: the
fixer and review-fixup agents hold `Bash(git add:*)` and commit their own
work turn-by-turn (`Commit your work with `git commit` as you go`), so the
"tell the agent not to" discipline is a prompt instruction an agent can
silently fail to follow (exactly the failure mode Constitution Principle
IX exists to close), and the "one scripted commit with an exclude
pathspec" discipline does not apply because there is no single scripted
commit — the agent's own commits happen throughout its turns, each one a
fresh opportunity to stage the sidecar if it is not ignored. A
`.gitignore` entry is the one mechanism in this repository's existing
toolbox that protects every future `git add` invocation — scripted or
agent-typed — without asking anything of the caller.

**A defect worth flagging, out of this feature's scope**: this same
reasoning suggests `auto-update-spec-kit.yml`'s exclude-pathspec pattern is
more fragile than a `.gitignore` entry for the identical problem (a bare
`git add -A` at some future, second call site in that file would
reintroduce the exact PR #201 bug the comment there describes), but
`auto-update-spec-kit.yml` is not a file this feature touches, and
`.wing-commander-pipeline` is the published-stage sidecar name — gitignoring
it repository-wide could affect a published stage's own adopter-facing
checkout behavior in ways this feature has not evaluated. Reported as a
`wing-commander-findings` entry rather than fixed here.

## D5: Gate 99 is a file-wide, unconditional rule over `uses:` blocks — not a job-tuple allowlist

**Decision**: `verify-board-loop-composite-provenance.py` (Gate 99) parses
`board-loop.yml` once and checks, with no per-job allowlist: (a) no
`uses: ./.github/actions/` (the raw, workspace-relative form) may appear
anywhere in the file; (b) every job containing a
`uses: ./.wc-pristine-repo/.github/actions/...` reference must contain a
`Checkout board-loop's own trusted copy (composites)` step (the canonical
step name, contracts/trusted-copy-checkout.md) positioned before that
reference, before any `wing-commander-context` call, and before any
`anthropics/claude-code-action@` step in the same job; (c) that step's
`ref:` must be exactly `${{ github.sha }}` — no other expression, no
hardcoded branch; (d) that step must carry no `continue-on-error: true`
and no `if:` that could skip it while a dependent reference still runs
(FR-006); (e) `.gitignore` must contain an entry matching the sidecar path
(D4, FR-007).

**Rationale**: FR-011 is explicit that the rule and its gate are one
unconditional statement, and names a per-job allowlist as "the same shape
as the gap being fixed." Gate 98's own `JOBS = ("fix", "review",
"readiness")` tuple is exactly that shape, applied to a different surface
(`run:` blocks); Gate 99 must not inherit it. Scanning the whole file for
the banned raw form and requiring every sidecar reference to be preceded
by the one correctly-shaped step is both simpler to implement than a
per-job check list and automatically covers a job added to this file
after this feature ships, with no edit to the gate.

## D6: Gate 99 is a new script, not an extension of Gate 98

**Decision**: A new file, `.github/scripts/verify-board-loop-composite-provenance.py`,
registered as **Gate 99** — the next available number (98 is the highest
in use; confirmed by scanning every `Gate N` step name in
`lint-workflows.yml` and every `verify-*.py` under `.github/scripts`) —
with the standard two-step registration (`Gate 99 — ...` and `Gate 99
self-test — ...`), immediately after Gate 98's block. Gate 98's own
`lint-workflows.yml` comment gains one added sentence pointing at Gate 99
for the composite half of the same provenance property (FR-014,
contracts/documentation-updates.md); Gate 98's own scope, allowlist, and
self-test are untouched (spec.md Out of Scope: "Re-litigating the
helper-script snapshot shipped for issue #583 or its gate").

**Rationale**: Gate 98 checks `run:`-block behavior (interpreter spelling,
import hygiene, the pristine-copy snapshot's own correctness) — a
different subject with a different failure shape than "does this `uses:`
line point at the sidecar." Folding Gate 99's file-wide, allowlist-free
check into Gate 98's existing three-job, `run:`-scoped structure would
either weaken Gate 98's precision (its allowlist logic has no notion of
`uses:` lines at all) or force Gate 98 to grow a second, structurally
unrelated code path — the opposite of Principle VIII's "every gate is
reachable and runs the same subject" discipline, which reads better with
two focused gates than one gate wearing two hats. `run-local-gates.py` and
`verify-gate-wiring.py` both derive their invocation lists by parsing
`lint-workflows.yml`'s own `run:` lines (`wc_gate_registry.py`), so no
separate manifest edit is needed beyond the two `lint-workflows.yml` steps.

## D7: Self-test mutations — one per rule in D5, plus the shipped-clean baseline

**Decision**: Gate 99's `--self-test` mode follows Gate 97/98's exact
convention (a `MUTATIONS` list of `(label, mutate_fn, expected_substring)`
tuples, `main()` asserting the unmutated file is clean, then that every
mutation is caught and attributable to its own rule):

1. Reintroduce one raw `uses: ./.github/actions/wing-commander-context` in
   a job that currently uses the sidecar form — must fail, naming the job
   and the offending line (User Story 3 Acceptance Scenario 2).
2. Move the sidecar checkout step to *after* a composite reference in one
   job — must fail (User Story 3 Acceptance Scenario 3).
3. Drop the sidecar checkout step entirely from a job that still carries a
   `.wc-pristine-repo`-relative reference — must fail (an orphaned
   reference with nothing establishing it).
4. Change the sidecar checkout's `ref:` to a literal branch name (or blank
   it) — must fail (FR-003).
5. Add `continue-on-error: true` to the sidecar checkout step — must fail
   (FR-006's fail-closed requirement).
6. Remove the `.gitignore` entry for the sidecar path — must fail (FR-007,
   D4).
7. Widen the file-wide ban in rule (a) to tolerate a second exempted
   pattern (simulating a future maintainer trying to special-case a job) —
   must fail, proving the rule admits no allowlist (FR-010's "MUST NOT
   admit any broader workspace reference," read onto this gate's own
   design rather than Gate 98's existing gate-suite exemption, which Gate
   99 does not need at all since it never inspects `run:` blocks).

**Rationale**: FR-009 requires one mutation per rule the gate enforces;
this enumerates D5's five structural checks plus the one behavioral
guarantee (D4) tightly enough that Principle VIII's "every failure branch
a gate ships MUST be exercised by a checked-in fixture" holds without
relying on a future maintainer's manual demonstration.

## D8: FR-010's exemption is empty by construction — Gate 99 has none to state

**Decision**: Gate 99 inspects only `uses:` blocks, never `run:` blocks.
The gate-suite invocation (`python3 .github/scripts/run-local-gates.py`)
that legitimately runs the item's own tree (spec.md's edge case, FR-005,
FR-010) is a `run:`-block concern already carved out narrowly by Gate 98;
Gate 99 has no analogous case to exempt, because a board-loop job never
invokes a composite *as* its own gate-suite step — the gate suite is a
plain Python script call, not a `uses:` reference. FR-010 is satisfied
here by having nothing to exempt, stated explicitly in Gate 99's own
docstring so a future reader does not go looking for a carve-out that does
not exist.

**Rationale**: Keeps the two gates' scopes cleanly disjoint (D6) and
avoids inventing an exemption clause with no real call site behind it,
which would itself be the kind of unenforced, un-fixture-backed rule
Principle VIII warns against.

## D9: FR-013 provenance is a one-line step-summary echo, not a new artifact or output

**Decision**: The sidecar checkout step is immediately followed (same
step, via a `run:` line right after the `actions/checkout@v5` step, or a
tiny sibling step) that writes
`echo "board-loop: composites resolved from $(git -C .wc-pristine-repo rev-parse HEAD) at ref github.sha." >> "$GITHUB_STEP_SUMMARY"`
in every job that has the checkout.

**Rationale**: FR-013 asks only that "each job's run record MUST show the
provenance... so the property is observable after the fact rather than
inferred" — the exact bar the `fix` job's own "Fetch main / checkout the
fix branch" step already clears for its own base-SHA fact
(`echo "board-loop: resuming fix on existing branch..." >> $GITHUB_STEP_SUMMARY`).
Reusing that idiom needs no new mechanism, no new schema, and no new
consumer to build.

## D10: FR-012's "work the item normally" needs no new code — it is the absence of a branch, not a new rule to add

**Decision**: No code change implements FR-012 directly. Once trusted
resolution is unconditional (FR-001/FR-011), there is nothing left in the
loop's code path that could vary based on whether an item's branch touches
the loop's own judging surface — no step reads the diff to decide whether
to stand the item down, because no such step exists today either. FR-012
is a statement about what this feature must *not* add, verified by its
absence rather than by a positive check.

**Rationale**: Avoids inventing a no-op guard clause purely to have
something to point at for FR-012 — Principle IV/IX both favor the item
being worked exactly as it is today, minus the resolution exposure, over a
new conditional whose only job would be to always evaluate to "proceed."

## D11: The two structural edge cases (branch deletes/adds a composite) need no new code either

**Decision**: An item branch that deletes a composite or helper the loop
uses is already a no-op for the loop's own execution once resolution is
trusted (the sidecar has its own copy regardless of what the branch
contains) — the deletion surfaces only as a diff for the review pass to
read, which review already does. An item branch that adds a *new*
composite cannot be invoked by the job until it lands on the trusted ref
(`github.sha` on a later run) — this is the direct, accepted consequence
of D1, not a behavior this feature has to implement or guard separately.

**Rationale**: Both edge cases in spec.md are stated as consequences of
the design, not additional requirements; recording them here confirms
tasks does not need to write code for either.

## D12: Fork-headed PRs need no special case

**Decision**: `review`/`readiness` checking out `steps.pr.outputs.branch`
already resolves within this repository (the loop only ever opens fix
PRs from branches it created itself) — this feature adds no fork-specific
logic, since D1's sidecar checkout is entirely independent of what the
job's *other* checkout points at, fork head or not.

**Rationale**: Spec.md's edge case ("trusted resolution must hold
identically" for a fork-headed PR) is a resilience statement about the
mechanism's generality, not a call for fork-specific code — D1 already
holds identically regardless of the item checkout's origin, since the two
checkouts are unrelated actions with no shared state.

## D13: FR-004's "one provenance rule" is a documentation and naming fact, not a code merge

**Decision**: The existing `git archive`/tar helper-script-and-schema
snapshot (issue #583) is untouched by this feature — same steps, same
`$RUNNER_TEMP/wc-pristine` path, same three jobs (`fix`, `review`,
`readiness`). This feature's own sidecar checkout (`.wc-pristine-repo`,
D1) is presented alongside it, in board-loop.yml's header and in each
job's adjacent step placement (D2), as the same commit resolved two
different ways for two structurally different needs (a tar extract for
importable Python modules; a real checkout for a `uses:`-addressable
composite directory) — never merged into one step, since `git archive`
cannot produce the latter (D1's rejected alternative).

**Rationale**: FR-004 requires the two guarantees be "presented as one
provenance rule rather than two unrelated mechanisms" without weakening
either — satisfied by naming and colocating them, not by forcing one
mechanism to do the other's job.
