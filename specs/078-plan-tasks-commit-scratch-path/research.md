# Phase 0 Research: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

No `[NEEDS CLARIFICATION]` markers remain in spec.md — the three original
ones were resolved on issue #585 before this plan ran (see spec.md's "What
was settled"). This document records the *implementation-shaped* decisions
the spec leaves open: not whether to do something, but how, given this
repository's existing conventions.

## D1: How the canonical guidance source is implemented

**Decision**: A new composite action, `.github/actions/wing-commander-commit-message-guidance/action.yml`,
mirroring the existing "one canonical source, many call sites" pattern this
repository already uses twice:

- `wing-commander-tool-args`'s `shell-commands` output — one rendered prose
  sentence, computed once per call site from that site's own inputs,
  consumed verbatim via `${{ steps.<id>.outputs.shell-commands }}` inside a
  `prompt: |` block (e.g. `plan.yml:783`). This is the direct precedent for
  rendering prose *into an agent prompt*, which `cost-line` never does (it
  only ever reaches a `run:`/issue-comment step).
- `wing-commander-metrics-summary`'s `cost-line` output — the "single home"
  example CLAUDE.md itself names for this exact pattern.

**Rationale**: FR-011 requires "one canonical source... rendered into each
in-scope prompt" with "the source MUST be able to render a different path
per site." A composite action's inputs→output is exactly this shape, it is
the mechanism this repository already trusts for the identical problem
(prose that must reach an agent's prompt text, not just a human-facing
comment), and it is checked by the same style of gate (`verify-tooling-
statement.py` for the render's correctness) this feature's own gate will
extend.

**Alternatives considered**:
- *A shared Python/Node script invoked by each workflow's `run:` step*,
  writing the guidance to a file the prompt then `cat`s. Rejected: nothing
  in this repository's `prompt: |` blocks currently interpolates a file's
  contents (only step outputs, via `${{ }}`), and it would need its own
  new indirection where a composite-action output already does the job.
- *A per-site copy carrying a canonical-pointer comment* ("see
  implement.yml:938"). Explicitly rejected by FR-011 itself: "a pointer is
  followable only by a human editor and not by the agent reading the
  prompt."
- *A repository-root Markdown/JSON file the gate reads and workflows also
  read at runtime somehow*. Rejected: workflows have no built-in step for
  "read this repo file and interpolate its contents into a prompt
  expression" the way `${{ steps.x.outputs.y }}` already works; this would
  invent a second mechanism to do what a composite action output already
  does.

## D2: Per-site scratch filenames

**Decision**: give all nine sites distinct filenames (extending, not
reusing, `implement.yml`'s existing `implement-commit-message-cycle.txt` /
`implement-commit-message-retry.txt` pattern) — e.g.
`plan-commit-message-direct.txt`, `plan-commit-message-pr.txt`,
`tasks-commit-message-direct.txt`, `tasks-commit-message-pr.txt`,
`board-loop-commit-message-fixer.txt`,
`board-loop-commit-message-review-fixup.txt`,
`pr-conversation-commit-message-fold.txt` (exact names finalized in
data-model.md).

**Rationale**: FR-006 requires distinct paths only for "two agent sites that
can execute within the same job invocation." `plan.yml`'s two sites are
different jobs selected by mutually-exclusive `mode` inputs (never
co-running per the spec's own Edge Cases note); same for `tasks.yml`.
`board-loop.yml`'s fixer (job `fix`) and review-fixup (job `review`) sites
are separate jobs — each gets its own fresh `${{ runner.temp }}` on its own
runner, so no path could collide across jobs regardless of filename choice.
Only `implement.yml`'s cycle/retry pair are two steps in *one* job (`implement`)
and can both run in one job invocation, which is exactly why #440 already
gave them distinct names. Giving every site its own filename anyway, rather
than reasoning job-by-job about which pairs are safe to share, is the
simpler and strictly safer choice: it costs nothing (the composite action
takes the filename as a plain input either way) and it remains correct even
if a future change makes two currently-separate jobs co-runnable (the Edge
Cases section's explicit warning for exactly this drift).

**Alternatives considered**: sharing one filename across `plan.yml`'s two
sites (or `tasks.yml`'s, or `board-loop.yml`'s) since they cannot currently
co-run. Rejected: it would require the plan to re-derive and document a
co-runnability proof per pair (the Edge Cases section demands exactly this
proof for `board-loop.yml`'s pair before sharing a name), for a saving
(one shorter constant) not worth the fragility.

## D3: The new gate's shape and number

**Decision**: `.github/scripts/verify-commit-message-scratch-path.py`,
following `verify-rate-limited-exemption.py`'s (Gate 51) structural shape
most closely:

1. Statically enumerate every in-scope `(workflow file, job, step)` by
   YAML-parsing the five workflow files and finding every step whose
   `prompt:` (or the composite action's step-label convention, TBD in
   Phase 1) instructs a commit — the nine sites named in spec.md's Context
   table are the seed list, not a hand-count the gate trusts blindly: the
   gate discovers steps whose prompt text contains `git commit` the way
   Gate 51 discovers steps whose `run:` contains `gh issue create`, so a
   tenth future site is caught rather than silently exempt-by-omission.
2. For each discovered site, require either (a) its prompt text contains
   the rendered guidance — checked by confirming the step consumes the new
   composite action's output (`${{ steps.<id>.outputs.guidance }}` appears
   in the `prompt:` string, and a preceding step in the same job actually
   invokes `wing-commander-commit-message-guidance`), or (b) the site's
   `(basename, step name)` is a literal entry in this script's own
   `EXEMPT_SITES` constant, each entry commented with why it is exempt —
   mirroring Gate 51's `EXEMPT_SITES` exactly.
3. Also assert, for `implement.yml`'s two sites specifically, that the
   *rendered* guidance still contains the two site-specific facts FR-013
   pins (the correct per-site filename, and retry's "distinct filename"
   addendum) — proven by executing the composite action's shipped `run:`
   step (via `wc_shell_harness.run_step`, the same technique
   `verify-tooling-statement.py` and `verify-plan-tasks-cost-line.py` use to
   avoid re-implementing shipped shell in the test), not by re-deriving the
   expected string in Python.
4. `--self-test` reintroduces each regression this gate exists to catch: a
   site's prompt with the render stripped, a composite-action step deleted
   from a job that still claims to consume its output, `EXEMPT_SITES`
   containing a stale/nonexistent site, and (for `implement.yml`) the
   rendered output missing the per-site filename or the retry addendum.

**Gate number**: the next unused number as of this research is **99**
(highest currently in use across `.github/scripts/*.py` is 98). This
repository assigns gate numbers by writing them into the script/registration
at the time they are added, not by reservation, so the exact number is
confirmed — not re-chosen — at implementation time by re-running the same
`grep -rhoE "Gate [0-9]+"` check immediately before naming the new gate, in
case another spec's gate lands on `main` first.

**Rationale**: Gate 51 is the closest existing shape (dynamic discovery +
literal exemption constant) for exactly the same kind of question — "does
every site with this pattern also have that other thing" — and Gate 63 /
`verify-tooling-statement.py` are the precedent for proving a *render*,
rather than a string literal, is correct by executing the shipped shell
rather than re-implementing it (Constitution VIII's "same subject... as in
CI").

**Alternatives considered**: a purely static string-match gate ("does the
literal filename appear in the prompt text"). Rejected for the same reason
`verify-plan-tasks-cost-line.py`'s docstring gives for its own site: "A
purely static check... cannot tell a correctly-gated emission from the same
line hoisted above the branch" — here, a purely static match cannot tell a
real render from a hand-typed string that merely happens to look like one,
which is exactly the drift FR-011/FR-012 exist to prevent.

## D4: Keeping `implement.yml`'s retry-specific sentence

**Decision**: the composite action accepts an optional `extra-note` input
(default empty), appended verbatim after the canonical paragraph. Only
`implement.yml`'s retry site sets it, to the existing sentence: "Use a name
distinct from the cycle step's scratch file above — the cycle attempt may
have left one behind, and this is a fresh session that never read it."

**Rationale**: FR-013 requires the retry agent to keep reading exactly what
it reads today. That sentence is retry-specific context (it references a
sibling step, not a general rule every site needs), so it does not belong in
the shared paragraph FR-009 says must carry "the same meaning" everywhere;
an optional trailing input keeps the shared text identical across all nine
sites while preserving retry's one extra fact.

**Alternatives considered**: folding the sentence into the shared paragraph
as a generic "if a sibling step in this job may have left a file behind,
use a different name" clause running at every site. Rejected: it would
introduce a hypothetical ("may have left one behind") that is false at the
other eight sites (none has a same-job sibling agent step today), reading as
confusing boilerplate rather than the same rule with a per-site path
FR-009 asks for.

## D5: FR-007 (tool-allowlist correctness)

**Decision**: no `default-allowed-tools`/`default-disallowed-tools` change
at any of the nine sites.

**Rationale**: confirmed by direct inspection (research pass over
`plan.yml:681,883`, `tasks.yml:683,870`, `implement.yml`'s two
`tool-args-*` steps, `board-loop.yml`'s `tool-args-fix` /
`tool-args-review-fixup`, and `pr-conversation.yml`'s `tool-args-act`):
every one already grants `Write` and `Bash(git commit:*)`. FR-007's
"corrected as part of this change" clause is therefore not triggered
anywhere; the plan carries no task to widen an allowlist.

## D6: The exemption list ships empty

**Decision**: `EXEMPT_SITES` in the new gate is declared but starts with no
entries; all nine sites are covered sites, not exemptions.

**Rationale**: spec.md's Context table and Assumptions section list all nine
sites as in scope, including `plan.yml`/`tasks.yml`'s four sites whose
*current* template happens to be a one-liner — the guidance is conditional
("longer than one line") per FR-005, so adding it does not force a body,
it only makes one safe the first time an agent's judgment calls for one.
None of the nine is "always" a one-liner in the sense FR-012's exemption
carve-out means (a site whose messages are deterministically composed by a
`run:` step, like `finalize.yml`/`cleanup.yml` — both already Out of Scope,
never candidates for `EXEMPT_SITES` at all since they are not agent
prompts). The constant exists, per SC-008, so a future site that genuinely
is one-liner-only has somewhere auditable to be recorded, matching Gate
51's own precedent of a small, may-be-empty, always-explicit allowlist.
