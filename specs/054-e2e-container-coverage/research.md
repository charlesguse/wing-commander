# Research: Container-Mode Coverage in End-to-End Release Verification

Input: `specs/054-e2e-container-coverage/spec.md` (fully clarified — all three
plan-relevant open questions were already answered on issue #364 before this
stage ran; see spec.md's "Clarifications" section). This document resolves
the *design* unknowns the plan stage owns: how the alternation is derived,
how the container-image passthrough reaches the test repository, how the
reference image is built/published, and how the two new gates this feature
needs are shaped. Every decision below cites the existing mechanism it reuses
or the reason none exists.

## D1 — How the alternating mode is derived (FR-018, FR-020)

**Decision**: Compute the mode fresh, every run, from the UTC calendar date
the `verify-e2e` job starts — parity of day-of-year (`date -u +%j`) — in a new
`mode` step near the top of `verify-e2e`, before `config`. Even day-of-year →
default-runner leg; odd → container leg. No value is written back anywhere.

**Rationale**: The schedule is a fixed daily cron (`9 9 * * *`), so
consecutive scheduled runs are always on consecutive calendar days, which
always flips parity — alternation falls out for free. A repository grep
(`alternat|rotation|last-mode|previous-mode|mode-history` across
`.github/`) found no existing rotation-state mechanism to reuse, so this is
new surface regardless of shape; a *stateless* derivation was chosen
specifically because the spec's own Edge Case ("the alternation loses its
place... a cancelled, skipped, or manually dispatched run must not leave the
rotation stuck on one mode") describes exactly the failure mode a *stored*
counter is prone to (a run that never reaches the step that would advance the
counter leaves the next run reading the same stale value). A value nothing
persists cannot get stuck.

**Alternatives considered**:
- *Parity of a run count fetched via `gh run list --workflow auto-release.yml`.*
  Rejected: requires an extra API call and a definition of "which runs count"
  (does a `fail-infra` run before `verify-e2e` even starts count? does a
  cancelled run?) that the calendar-date approach never has to answer.
- *A repository variable the workflow updates after each run.* Rejected
  outright: FR-017 already forbids the verification's token gaining any new
  write permission (that requirement is stated for the image-reference
  variable specifically, but the same App token would have to gain the grant
  either way, and Constitution IX disfavors workflow-owned mutable state a
  missed write can desync).

**Interaction with the pause control (D3)**: the pause check runs after mode
derivation and, when set, overrides an odd-day (container) result to
default-runner — it never overrides an even-day result, since that leg was
never paused.

## D2 — How the image reference reaches the test repository, and how the off-turn is suppressed (FR-001, FR-002, FR-008, FR-017)

**Decision**: Reuse the *published, adopter-facing* mechanism verbatim — no
change to any stage's `workflow_call` interface. Every scaffolded wrapper
(`wing-commander-1-intake.yml` … `wing-commander-7-cleanup.yml`,
`wing-commander-rebase.yml`) already carries, unmodified since spec 038:

```yaml
with:
  container-image: ${{ vars.WING_COMMANDER_CONTAINER_IMAGE || '' }}
secrets:
  container-registry-username: ${{ secrets.WING_COMMANDER_CONTAINER_REGISTRY_USERNAME }}
  container-registry-password: ${{ secrets.WING_COMMANDER_CONTAINER_REGISTRY_PASSWORD }}
```

The maintainer's one-time setup (FR-015) is to set `WING_COMMANDER_CONTAINER_IMAGE`
— and, only if the reference image is private, the two registry-credential
secrets — directly **on the test repository**, exactly the way any adopter
configures container mode today (docs/adoption.md, "Runners and container
images"). Because the `scaffold` step copies these wrapper files byte-for-byte
from this repository's own checkout before rewriting their `uses:` targets
and default-branch references (`auto-release.yml` lines ~385-405), the
existing `sed` pass gains exactly one more rewrite:

- **Container-mode turn**: no rewrite — the copied wrapper's existing
  `vars.WING_COMMANDER_CONTAINER_IMAGE` read does the work, resolved against
  the test repository's own configuration at run time.
- **Default-runner turn**: the `scaffold` step's `sed` blanks the container
  passthrough in every copied wrapper file (e.g.
  `s/vars\.WING_COMMANDER_CONTAINER_IMAGE || ''/''/`), so a permanently
  configured test-repository variable cannot leak container mode into a run
  whose turn is the default-runner leg.

**Rationale**: this is the smallest possible change surface — the published
contract (Constitution VII) is untouched, because the passthrough already
exists there; only the consuming instrument (`auto-release.yml`, itself not a
published stage) changes. It also directly satisfies FR-002 ("the same stage
chain... not a reduced subset") for free, since the container leg runs the
identical scaffolded wrapper set as the default-runner leg, differing only in
one resolved value.

**Leg isolation (FR-008)**: already satisfied by the existing
`concurrency: group: wing-commander-auto-release` /
`cancel-in-progress: false` on `auto-release.yml` — a second run (scheduled or
manually dispatched) queues behind an in-flight one rather than running
concurrently, so two resets of the same test repository can never race. This
requires no new code; the plan only needs to document that the existing
concurrency group is what FR-008 relies on, so it is never loosened.

**Alternative considered**: minting a second App-token permission to read the
test repository's `WING_COMMANDER_CONTAINER_IMAGE` value directly (so
`auto-release.yml` could embed a literal, wing-commander-controlled value into
the copied wrapper via `sed`, the same way it already embeds the resolved
`HEAD_SHA` and default-branch name). Rejected: FR-017 states the verification
"MUST NOT... require any new permission on its token to obtain the
reference," and a repository-variable read is a distinct, currently
ungranted fine-grained permission on the App installation.

## D3 — Independent pause control (FR-009)

**Decision**: a new wing-commander-side repository variable,
`WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED`, read the same way the
existing global `WING_COMMANDER_AUTO_RELEASE_PAUSED` is read
(`vars.<NAME> == 'true'`), consulted by the `mode` step (D1) immediately after
computing the date-parity result. When set, the run's mode is forced to
default-runner regardless of parity, and the verdict/report state
"container mode not exercised: paused" rather than a pass. This mirrors an
established, already-documented pattern (`docs/setup.md`) rather than
inventing a new pause shape.

## D4 — Reference image visibility (FR-014's public/private choice, left to plan by spec.md's own note)

**Decision**: publish the reference image **public** by default. This removes
the credential-secret surface (and the "unreachable secrets" edge case)
entirely for the common case, while leaving the already-wired private path
(D2's `container-registry-*` passthrough, proven today by
`private-image-dogfood.yml`) available unchanged if a maintainer later
chooses to make it private — FR-014 then applies with zero additional code,
since the mechanism already exists end to end.

## D5 — Reference image build and publish (FR-016, FR-019)

**Decision**: a new Dockerfile at `.github/docker/e2e-reference-image/Dockerfile`,
built from a minimal base and installing exactly the tools
`.github/scripts/required-tools.txt` names (git, gh, jq, curl, python3, bash,
node, timeout — the last via coreutils), and a new, non-published workflow
`.github/workflows/wing-commander-e2e-reference-image.yml` (`on: push` paths
`.github/docker/e2e-reference-image/**` and
`.github/scripts/required-tools.txt`, plus `workflow_dispatch`) that builds
and pushes it to `ghcr.io/charlesguse/wing-commander-e2e-image`, tagged
`:latest` and with the commit SHA, and prints the resulting digest in the job
summary. The image is pinned **by digest**, never by the moving `:latest`
tag, in the test repository's `WING_COMMANDER_CONTAINER_IMAGE` variable
(Edge Case: "the image changes underneath the pin") — the maintainer copies
the printed digest into that variable by hand; the workflow never writes it
itself (no mechanism exists, or is added, for wing-commander to write an
arbitrary test repository's configuration).

**Naming precedent**: `charlesguse/wing-commander` is already a hardcoded
literal elsewhere in `auto-release.yml` (the rewritten `uses:` target), so a
registry path under the same owner is consistent with existing practice
rather than a new convention.

**Why not published as a stage**: this workflow has no `workflow_call`
interface and no adopter-facing surface — it is wing-commander's own
maintenance tooling, the same category `auto-release.yml` and
`watchdog.yml`'s wrapper already occupy (Constitution VII, "consuming
instrument").

## D6 — Gate: reference image tool set vs. the canonical list (FR-019, SC-007, SC-008)

**Decision**: a new gate (next free number: **Gate 62**, since Gate 61 is the
highest currently registered) that `docker build`s the reference image
locally (no push) and runs the exact same
`docker run --rm --entrypoint sh "$IMAGE" -c 'for t in $REQUIRED_TOOLS; do command -v "$t"...'`
check every stage's `verify-image-prerequisites` job already runs, comparing
against `.github/scripts/required-tools.txt`. Registered as a step in
`.github/workflows/lint-workflows.yml` the same way Gates 23/27 are (a
`python3 .github/scripts/verify-gate-62.py` invocation plus a
`--selftest` companion), so `run-local-gates.py` and `verify-gate-wiring.py`
pick it up automatically with no separate manifest.

**Rationale (Constitution VIII)**: Gate 23's existing drift check is purely
textual (it compares embedded `REQUIRED_TOOLS=` string literals against the
canonical file) — it cannot fail if the *Dockerfile* silently stops
installing a tool the text still claims to install. A gate that actually
builds and inspects the image is the only version of this check that can
fail its own subject. Unconditional execution on every PR (rather than a new
path-filtered trigger) was chosen to match this repository's existing
convention — no gate in `lint-workflows.yml` is currently path-filtered — and
a minimal image build is cheap enough not to need one.

## D7 — Recording the image reference in the verdict (FR-003)

**Decision**: the container-mode leg's verdict fields it can populate
directly (`mode`, `container-image-configured: true/false`) are set locally
from what `auto-release.yml` itself resolved (D1's mode, D2's sed outcome).
The literal image reference string is **not** fetched by `auto-release.yml`
(doing so would need the new, FR-017-forbidden repository-variable-read
permission on the test repository); instead the verdict's existing
`evidence_url` field is pointed at the container leg's
`verify-image-prerequisites` job run in the test repository, whose own
`docker pull`/`docker login` log lines already name the exact reference used.
This is the same "record a pointer, not a copy" shape the verdict schema
already uses for other fields (e.g. `evidence_url:$repo` today).

**Decision made without further clarification** — flagged in the issue
comment: FR-003 could also be read as requiring the literal reference string
inside the verdict JSON itself, which would require the new permission
FR-017 rules out. This plan resolves the tension in FR-017's favor (no new
permission) and reports the reference via evidence pointer instead of by
value; the maintainer should confirm this reading during tasks/implement or
correct it via a comment on issue #364.

## D8 — Container leg's own time budget (FR-010)

**Decision**: no new budget mechanism. The existing `POLL_BUDGET_SECONDS`
loop in `verify-e2e`'s `poll` step already bounds total wall clock and
already degrades to a `fail-timeout` verdict (rather than a step being killed
before it can write one) regardless of which leg is running — the container
leg's added risk (an extra `docker pull`/`docker login` inside the
scaffolded stage jobs) is additional time spent *before* the polled issue
reaches a terminal state, which the same budget already covers. The plan
only adds mode-attribution to this existing verdict (D9), not a second
timeout mechanism.

## D9 — Verdict schema extension (FR-003, FR-007, FR-020)

**Decision**: extend the existing verdict object
(`{outcome, verified_head, failing_check, expected, observed, evidence_url}`)
with two new fields, `mode` (`"container"` | `"default-runner"`) and
`container_image_configured` (boolean, present only when `mode` is
`"container"`), set once by the new `mode` step and threaded through
unchanged by every later step exactly as `verified_head` already is today.
`report`'s failure-body builder gains one line surfacing `mode` alongside the
`failing_check` it already names, satisfying FR-007 ("identify the failure as
belonging to the container leg specifically") without a parallel verdict
vocabulary.

## Summary of files touched

- `.github/workflows/auto-release.yml` — new `mode` step; `scaffold`'s
  existing `sed` pass gains the off-turn blank-out; `verdict` schema gains
  `mode`/`container_image_configured`; `report`'s body builders surface mode.
- `.github/docker/e2e-reference-image/Dockerfile` — new.
- `.github/workflows/wing-commander-e2e-reference-image.yml` — new, build +
  publish to `ghcr.io/charlesguse/wing-commander-e2e-image`.
- `.github/scripts/verify-gate-62.py` (+ `--selftest` path) — new.
- `.github/workflows/lint-workflows.yml` — register Gate 62.
- `docs/setup.md` — new row for `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED`;
  a note that `WING_COMMANDER_CONTAINER_IMAGE`/registry-credential secrets, set
  on the test repository, now also configure the auto-release container leg.
- `docs/adoption.md` — short new subsection under "Runners and container
  images" stating the reference image's provenance/ownership/non-adopter
  status (FR-013).
- `docs/architecture.md` — short addition describing the alternating leg in
  `auto-release.yml`'s flow.

No change to any published stage workflow (`intake.yml` … `cleanup.yml`,
`rebase.yml`) or to any `.github/actions/**` composite — the container-image
passthrough these already carry is sufficient as-is (D2).
