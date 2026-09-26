# Contract: Proof Outcome Taxonomy

Supersedes, for implementation purposes, the three-branch table in
`specs/057-autonomous-board-loop/contracts/prove-step.md`'s "Re-drive"
section (`conclusion == success` / `conclusion in {failure, timeout}` /
uncorrelated). During implementation that section is edited to point at
this taxonomy (FR-019/research.md D9).

## The eight `outcome_reason` values (SC-003)

Computed by `board_prove.py` (research.md D6), never by the workflow's own
shell conditionals, and always accompanied by a distinct, named sentence on
the issue (FR-009):

| `outcome_reason` | Meaning | Issue stays open? | Distinguished from |
|---|---|---|---|
| `group-busy` | FR-001a's pre-dispatch check found `wing-commander-board-loop-directed-proof` already occupied; nothing was dispatched | yes | every other reason — no dispatch attempt was even made |
| `not-started` | dispatched, correlated, but the correlated run's own `status` never left `queued` before the wait budget exhausted | yes | `unfinished` (below) — this run never began executing anything |
| `unfinished` | dispatched, correlated, started, but did not reach a terminal `conclusion` inside the wait budget | yes | `not-started` — this run did begin, and (research.md D6) is proof it needs a bound established (FR-002a's "the feature MUST establish that bound rather than assume it"), not merely a queue problem |
| `displaced` | the dispatch's pending slot was taken by a later run before it could even queue for correlation, or correlation found no matching run at all where one was expected | yes | `uncorrelated` (below) — this is eviction, not ambiguity |
| `uncorrelated` | correlation returned an ambiguous result (two or more matching titles) | yes | `displaced` — a data problem in correlation, not a scheduling one |
| `no-target` | `directed_stage()` found no aimable job (FR-010a) reaches the changed behaviour, though `board-loop.yml` itself is a valid re-drive target for something | yes, for a human to close after reading the evidence | `nothing-reaches` — this is a job-level gap, not a workflow-level one |
| `nothing-reaches` | `redrive_target()` found no dispatchable workflow at all references the changed path(s) | yes | `no-target` — this is a workflow-level gap; no candidate workflow exists to even consider a job within |
| `success` / `failure` | the directed (or, for an external target, whole-workflow) run reached a terminal conclusion | closes on `success` (FR-010), stays open on `failure` | every reason above — this is the only branch where a real run actually finished |

## Recording rule (FR-008, FR-009)

Every row above that is not `success` leaves the issue open, carrying:

1. which of the eight conditions applied, in words a maintainer does not
   need the Actions tab to parse (SC-007);
2. enough to decide whether to look at the fix or at the loop (FR-009) —
   concretely, `group-busy`/`not-started`/`unfinished`/`displaced` point at
   the loop's own scheduling, `uncorrelated` points at the composite's
   correlation (out of this feature's scope to fix, but worth naming),
   `no-target`/`nothing-reaches` point at the mechanism's own reach, and
   `failure` points at the fix itself.

## Cost line / metrics record label (FR-012)

`board-loop.yml`'s existing "Determine this run's outcome for the metrics
record" step (`:2775-2789`) maps each `outcome_reason` to a `run-label`
distinct from today's four (`stood down`, `closed on merge evidence
alone`, `proof run uncorrelated`, `proof: <conclusion>`), so an abandoned
dispatch's cost is visible in the same durable metrics record every other
stage already emits, under a label naming the condition — never folded
back into the generic `proof run uncorrelated` label the current tree
uses for every non-`success`/`failure` case today.
