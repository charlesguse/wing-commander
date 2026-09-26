# Phase 1 Data Model: rebase.yml / cleanup.yml Credential Refresh + Derived Gate 68 Subjects

This feature has no application data model — its "entities" are the shapes
Gate 68 (`.github/scripts/verify-post-agent-credential-refresh.py`) reads
and asserts over, plus the workflow-YAML structures those assertions cover.
This document names each one, its fields, and the invariants spec.md's
Functional Requirements attach to it, so the tasks stage can turn each
invariant into a concrete code change or self-test mutation without
re-deriving the shape from prose.

## 1. Derived Subject

The unit Gate 68 inspects after this feature ships.

| Field | Type | Source |
|---|---|---|
| `workflow_path` | str (e.g. `.github/workflows/rebase.yml`) | discovered by globbing `.github/workflows/*.yml` |
| `job_name` | str (e.g. `rebase`) | a job key in the parsed YAML |
| `agent_steps` | list of step dicts | every step in the job's `steps:` list where `_is_agent_step(step)` is true |
| `disposition` | enum: `full_subject` \| `exempt` \| `agentless_in_scope` | computed: `exempt` if `(workflow_path, job_name)` is a key in `EXEMPT_JOBS`; `agentless_in_scope` if `job_name` is in `AGENTLESS_JOBS` (unchanged, pre-existing — `tasks-approved` only); otherwise `full_subject` |

**Invariant (FR-009 spec 072, FR-009 spec 073)**: every job with
`len(agent_steps) >= 1` has a `disposition`. There is no fourth state. A
job that is neither `full_subject`-compliant nor `exempt`-compliant fails
the gate, naming `workflow_path` and `job_name`.

**Invariant (FR-002 spec 072)**: `disposition` is never computed from
whether a bot-acting step follows the agent step — presence of an agent
step alone is what makes a job a Derived Subject. (A job with no bot-acting
step after its agent step is still a Derived Subject; per spec 072's Edge
Cases it is simply an `exempt` entry whose reason is "no bot-acting step
follows.")

## 2. Subject Floor

The checked-in list Gate 68 compares the *set* of Derived Subjects against,
so a subject's disappearance is caught even though nothing about a missing
step can be "derived" from its own absence.

| Field | Type |
|---|---|
| `workflow_path` | str |
| `job_names` | set of str — every agent-bearing job the repository is known to contain in this file, regardless of disposition |

**Invariant (FR-004 spec 072)**: for every `(workflow_path, job_name)` pair
in the floor, that pair MUST appear in the Derived Subject set computed
from the current tree. A floor member absent from derivation fails the
gate, naming the missing pair. A Derived Subject absent from the floor
MUST NOT fail for that reason alone (an un-updated floor fails safe, never
tight).

**Seed content (this feature)**: the floor gains six new job entries this
feature ships — `rebase.yml`/`rebase`, `cleanup.yml`/`teardown-done`,
`watchdog.yml`/`diagnose`, `board-loop.yml`/`triage`,
`board-loop.yml`/`route`, `board-loop.yml`/`fix`,
`board-loop.yml`/`review` — seven, not six (`board-loop.yml` contributes
four job entries for five agent steps, since `review` holds two: `Reviewer`
and `Review-fixup`). Combined with the eight pre-existing floor entries
(`intake`/`intake`, `clarify`/`clarify`, `plan`/`plan`, `tasks`/`tasks`,
`implement`/`implement`, `finalize`/`finalize`,
`pr-conversation`/`classify-and-announce`, `pr-conversation`/`act`,
`auto-update-spec-kit.yml`/`e2e-stage`) — nine pre-existing plus seven new
— the floor holds sixteen entries after this feature. (`tasks-approved` is
agentless and is tracked by `AGENTLESS_JOBS`, a separate, pre-existing set
this feature does not change — it is not an agent-bearing job and does not
belong on the agent-step floor.)

## 3. Exempt Job (Exemption Record)

A Derived Subject whose disposition is `exempt`: the post-agent composite
checks (1, 2, 7 in the gate's own numbering) do not apply to it, but a
different, per-entry `condition` must hold or the gate fails.

| Field | Type | Notes |
|---|---|---|
| `workflow_path`, `job_name` | str | the keyed identity, same as Derived Subject |
| `reason` | str | human-readable prose; not itself checked, informational only |
| `issue` | int or tuple of int | the deciding issue(s) this exemption cites — `#558` for `cleanup.yml`/`watchdog.yml`, `#558` and `#410` for `board-loop.yml` |
| `condition` | callable `(parsed_job_yaml) -> bool` | the mechanical assertion FR-007 (spec 073) requires |

**Invariant (FR-007 spec 073)**: `condition(job)` MUST be evaluated on
every gate run, for every exempt job, and MUST fail the gate — naming the
job and the exemption — when it returns false. An exemption entry whose
`condition` cannot be expressed as code is not a valid entry (there is no
"exempt, unconditionally" state).

**Two condition shapes this feature introduces** (see research.md D4):

- **Wall-clock bound** (`cleanup.yml`, `watchdog.yml`): `condition` reads
  each agent step's `timeout-minutes` (or the job-level
  `timeout-minutes` if the step has none) and asserts it is present and
  `<= 10`.
- **Composite adoption** (`board-loop.yml`): `condition` walks each agent
  step's post-step window (the same by-position walk check 7 already
  performs) and asserts a `wing-commander-context` call and a
  `wing-commander-post-agent-credential-status` call both appear before the
  next agent step or the job's end.

## 4. Bot Credential (unchanged entity, new consumers)

Carried over from spec 052's data-model.md without redefinition — the
minted App installation token, ~60-minute lifetime, held in
`steps.<mint-id>.outputs.token` immediately after mint and relayed into
`env.WC_BOT_TOKEN` for the rest of the job. This feature adds two new
holders of the job-scoped relay (`rebase.yml`'s `rebase` job) and confirms
one job (`cleanup.yml`'s `teardown-done`) deliberately keeps reading the
raw pre-agent form throughout, per D8.

## 5. Persisted Remote Credential (unchanged entity, one new re-authentication site)

Carried over from spec 052 — the copy of the credential a `checkout` step
embeds into the git remote's `http.https://github.com/.extraheader` or
equivalent. This feature adds one new re-authentication site
(`rebase.yml`'s post-agent `wing-commander-refresh-remote` call, D5 point
1) and confirms `cleanup.yml`'s persisted remote is covered by the bound
(D8) rather than by re-authentication (FR-002 spec 073 states this
explicitly as the two workflows' differing remedy for the same kind of
exposure).

## 6. Report-Over-Budget Tolerance Step (existing entity, widened reach)

A step named `Report over-budget agent run` (with the existing per-variant
suffixes) — checked by Gate 68's check 3 regardless of a job's Derived
Subject disposition. This feature's only effect on this entity is *reach*:
two new instances (`rebase.yml`, `cleanup.yml`) come into check 3's view
once `load_all()` reads every workflow file (D2), and both currently lack
`continue-on-error: true` (D5 point 3, D9) — a required edit, not a new
requirement.

## State / Disposition Summary Table

| Workflow | Job | Agent step(s) | Disposition after this feature | Mechanism |
|---|---|---|---|---|
| `intake.yml` | `intake` | 1 | `full_subject` (unchanged) | spec 052 |
| `clarify.yml` | `clarify` | 1 | `full_subject` (unchanged) | spec 052 |
| `plan.yml` | `plan` | 1 | `full_subject` (unchanged) | spec 052 |
| `tasks.yml` | `tasks` | 1 | `full_subject` (unchanged) | spec 052 |
| `tasks.yml` | `tasks-approved` | 0 | `agentless_in_scope` (unchanged) | spec 052 |
| `implement.yml` | `implement` | 3 | `full_subject` (unchanged) | spec 052 |
| `finalize.yml` | `finalize` | 1 | `full_subject` (unchanged) | spec 052 |
| `pr-conversation.yml` | `classify-and-announce`, `act` | 1 each | `full_subject` (unchanged) | spec 052 |
| `auto-update-spec-kit.yml` | `e2e-stage` | 1 | `full_subject` (unchanged) | spec 052 |
| `auto-update-spec-kit.yml` | `evaluate-path`, `comment-reply` | 1 each | `exempt` (**new EXEMPT_JOBS entries** — previously invisible, now recorded per spec 072 US3; condition = wall-clock bound `<= 10`) | this feature (mechanizing a pre-existing prose-only precedent) |
| **`rebase.yml`** | **`rebase`** | 1 | **`full_subject` (new)** | **this feature** |
| **`cleanup.yml`** | **`teardown-done`** | 1 | **`exempt` (new)** | **this feature** |
| **`watchdog.yml`** | **`diagnose`** | 1 | **`exempt` (new)** | **this feature** |
| **`board-loop.yml`** | **`triage`, `route`, `fix`, `review`** | 1, 1, 1, 2 | **`exempt` (new, 4 entries)** | **this feature** |

Row count check against SC-002/SC-003: zero agent-bearing jobs in the
repository end this feature neither a Derived Subject with `full_subject`
disposition nor an `exempt` entry with an asserted condition — sixteen rows
above account for every agent-bearing job (`AGENTLESS_JOBS`'
`tasks-approved` excluded, since it has zero agent steps and was never in
scope for this count).
