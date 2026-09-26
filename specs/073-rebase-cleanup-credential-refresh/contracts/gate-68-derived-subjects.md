# Contract: Gate 68's Derived Subject Set, Floor, and Exemption Record

**Subject**: `.github/scripts/verify-post-agent-credential-refresh.py`
("Gate 68"), registered in `.github/workflows/lint-workflows.yml`'s `lint`
job and reachable locally via `python .github/scripts/run-local-gates.py`
(no separate registration required — `run-local-gates.py` derives its gate
list from `lint-workflows.yml` itself).

**Origin**: issue #410 item 1, decided by spec 072's Clarifications
(#549) but never implemented (spec 072 is `Draft`, no code shipped). This
feature (#558, spec 073) implements the decided shape. This document is
the mechanism's first contract — spec 072 never reached Phase 1.

**Amends**: this document is new. It does not replace
`specs/052-agent-credential-lifetime/contracts/
post-agent-credential-refresh-gate.md`, whose "Subject" section is amended
in place (not forked) to describe the derived set, the floor, and the
exemption table this document specifies — see that document for the
per-check behavioural contract (checks 1 through 9) this one does not
restate.

## What this contract governs

Three questions Gate 68 must answer the same way every run, given only the
repository's own `.github/workflows/*.yml` files and this gate's own
checked-in constants:

1. **Which jobs does the gate inspect?** (the Derived Subject rule)
2. **How does the gate notice a subject it used to inspect has vanished?**
   (the Subject Floor)
3. **How does a job with an agent step opt out of the post-agent
   composite requirement, and what stops that opt-out from becoming a
   silent, unconditional exemption?** (the Exemption Record)

## 1. Derivation rule

```text
derived_subjects = {
    (path, job_name)
    for path in glob(".github/workflows/*.yml")
    for job_name, job in parse(path).get("jobs", {}).items()
    if any(_is_agent_step(step) for step in job.get("steps", []))
}
```

- `_is_agent_step` is the gate's existing structural test (matches a
  step's `uses:` value against the pinned agent-action reference) — no new
  detection logic, reused verbatim.
- A job qualifies on the presence of at least one agent step. No further
  reading of the job (whether a bot-acting step follows, whether the
  agent step is bounded, whether the job is a matrix) narrows the set.
  Those questions are answered by disposition (§3), never by exclusion
  from derivation itself.
- A workflow file that fails to parse fails the gate, naming the file — it
  never silently contributes zero subjects.
- A derived set of size zero fails the gate as misconfigured — it never
  passes vacuously.
- On both a passing and a failing run, the gate's output names every
  `(workflow_path, job_name)` pair it derived, so a reader can confirm
  coverage without reading this gate's source.

## 2. Subject Floor

```text
SUBJECT_FLOOR: dict[str, set[str]]   # workflow_path -> job_names
```

- Checked-in, hand-maintained, in the gate script itself.
- **Contract**: `SUBJECT_FLOOR ⊆ derived_subjects` on every run. A floor
  member missing from `derived_subjects` fails the gate, naming that
  pair — this is the one regression pure derivation cannot detect on its
  own (the edit that removes a job's last agent step removes the only
  evidence the job was ever a subject).
- A `derived_subjects` member absent from `SUBJECT_FLOOR` is still fully
  inspected under its computed disposition; it never fails for being
  absent from the floor. The floor names a known-lower-bound, not an
  exhaustive registry — a newly added agent-bearing job is covered by
  derivation the day it ships, with zero edits to this gate.
- Updating the floor when a new agent-bearing job ships is expected
  maintenance, not a design gap: an un-updated floor after a new job ships
  fails safe (nothing shrinks), never fails tight (nothing new is
  rejected).

## 3. Exemption Record

```text
EXEMPT_JOBS: dict[tuple[str, str], ExemptionEntry]

class ExemptionEntry:
    reason: str            # prose; informational, not itself checked
    issue: tuple[int, ...] # the deciding issue(s), e.g. (558,) or (558, 410)
    condition: Callable[[dict], bool]  # takes the job's parsed YAML
```

- Every `(workflow_path, job_name)` in `derived_subjects` MUST resolve to
  exactly one of: **full subject** (every post-agent composite check
  applies), **agentless-in-scope** (pre-existing `AGENTLESS_JOBS` — checks
  1/2 do not apply since there is no agent step to be "after"; checks 3/5
  still apply), or **exempt** (an `EXEMPT_JOBS` entry exists, its
  post-agent composite checks do not apply, and `condition(job)` is
  asserted true).
- A pair in `derived_subjects` matching none of the three fails the gate,
  naming the pair — this is the "neither compliant nor exempt" failure
  mode (spec 072 FR-013).
- `condition` MUST be evaluated on every run for every exempt entry. A
  `condition` that returns `False` fails the gate, naming the entry and
  its `reason`/`issue`, so an exemption cannot silently stop holding —
  raising `cleanup.yml`'s bound past 10 minutes, or deleting
  `board-loop.yml`'s adopted composite call, is caught the same run it
  happens.
- An exemption with no `condition` (or a condition that is always `True`)
  is not a valid entry — Constitution IX (judgment gating a durable
  action belongs in deterministic code, never an unconditional pass) and
  FR-007 of spec.md both forbid it. There is no unconditional-exemption
  state in this contract.

### Entries this feature adds

| `(workflow_path, job_name)` | `condition` shape | `issue` |
|---|---|---|
| `(".github/workflows/cleanup.yml", "teardown-done")` | wall-clock bound, `<= 10` min | `(558,)` |
| `(".github/workflows/watchdog.yml", "diagnose")` | wall-clock bound, `<= 10` min | `(558,)` |
| `(".github/workflows/board-loop.yml", "triage")` | composite adoption (context + credential-status) | `(558, 410)` |
| `(".github/workflows/board-loop.yml", "route")` | composite adoption | `(558, 410)` |
| `(".github/workflows/board-loop.yml", "fix")` | composite adoption | `(558, 410)` |
| `(".github/workflows/board-loop.yml", "review")` | composite adoption, both agent steps | `(558, 410)` |
| `(".github/workflows/auto-update-spec-kit.yml", "evaluate-path")` | wall-clock bound, `<= 10` min | mechanizes spec 052's existing prose exclusion |
| `(".github/workflows/auto-update-spec-kit.yml", "comment-reply")` | wall-clock bound, `<= 10` min | mechanizes spec 052's existing prose exclusion |

The last two rows are not new *dispositions* (both jobs were already
excluded from `SUBJECTS` by spec 052) — they are new *mechanically checked*
records replacing a prose-only exclusion, which SC-004/FR-007 of this
feature require once any wall-clock-bound condition function exists in the
gate at all (leaving these two as the sole remaining unchecked exclusions
would be the same defect this feature exists to close, one entry later).

## Self-test coverage this contract requires

Per FR-009/FR-010 (spec 072) and FR-012 (spec 073), `--self-test` MUST
assert, at minimum, one failing mutation for:

- a floor member's agent step removed (§2 regression),
- a derived set of zero (§1 misconfiguration),
- an agent step spelled so the derivation rule no longer recognizes it
  (§1 recognition regression),
- a derived subject in neither full/agentless/exempt state (§3 "neither"
  regression),
- each exemption's `condition` broken in the direction that should fail it
  (bound removed, bound raised past threshold, adopted composite call
  deleted) — one mutation per `EXEMPT_JOBS` entry this feature adds.

See `data-model.md`'s Derived Subject / Subject Floor / Exempt Job
sections for the field-level shape these mutations operate on, and
`research.md` D12 for the full mutation list.
