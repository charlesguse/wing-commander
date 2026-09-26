# Phase 1 Data Model: Gate 68 Derives Its Own Subjects

This feature introduces no new persisted data store and no new runtime
artifact. Every shape below is either a static, checked-in Python
constant inside `.github/scripts/verify-post-agent-credential-refresh.py`,
or an ephemeral value computed fresh each time the gate runs. `spec-
meta.json`'s schema is untouched, and no new job output, environment
variable, or file is written by any workflow as a *direct* consequence of
this feature (User Story 3's newly-adopting jobs reuse the exact
`WC_BOT_TOKEN` / agent-ran-signal / credential-status shapes spec
052's data-model.md already defines — see that document for their fields).

## Subject job (derived, not persisted)

| Property | Value |
|---|---|
| Identity | `(path, job_name)` — the workflow file's repo-relative path and the job's key under `jobs:` |
| Produced by | `derive_subjects()` (new): glob `.github/workflows/*.yml`, parse each with `yaml.safe_load`, for every `(path, job_name, job)` where `job.get("steps")` contains at least one step whose `uses:` matches `AGENT_ACTION_RE`, yield `(path, job_name)` |
| Cardinality today | 15 pairs: the 9 `SUBJECT_FLOOR` already names (`intake`, `clarify`, `plan`, `tasks`/`tasks-approved`, `implement`, `finalize`, `classify-and-announce`/`act`, `e2e-stage`) plus the 6 this feature's own disposition work adds (`board-loop.yml`'s `triage`/`route`/`fix`/`review`, `cleanup.yml`'s `teardown-done`, `rebase.yml`'s `rebase`) plus `watchdog.yml`'s `diagnose` (derived and excluded, not floored — D6) |
| Never a subject | A job with a job-level `uses:` (a `workflow_call` reference) and no local `steps:` — evaluates to zero agent steps, contributes nothing, raises nothing |
| Consumed by | `scan()`, which routes each derived subject to `check_job()` either as an ordinary inspected subject or, when `(path, job_name)` is a key of `EXCLUSIONS`, as an excluded one (D4) |

## Agent step (recognition rule, unchanged from the shipped gate)

| Property | Value |
|---|---|
| Marker | A step whose parsed `uses:` field matches `^anthropics/claude-code-action@` (`AGENT_ACTION_RE`, unchanged) |
| Recognition is structural | Only the YAML step mapping's `uses:` key is consulted — a string match against `run:` text, a comment, or a fixture embedded elsewhere in the file can never satisfy this, by construction of `yaml.safe_load` plus a field-specific check (FR-008) |
| Reference-shape tolerance | No trailing version anchor — `anthropics/claude-code-action@v1`, `@v2`, or any future tag all match; only the org/repo prefix is pinned |

## Subject floor (`SUBJECT_FLOOR`, checked-in constant, renamed in place from today's `SUBJECTS`)

| Property | Value |
|---|---|
| Shape | `Dict[str, List[str]]` — workflow path to the list of job names the repository is known to contain an agent step in, same shape as today's `SUBJECTS` |
| Purpose | FR-004 drop-detection only — no longer used to select what `scan()` inspects (D1/D2's glob-and-derive does that) |
| Comparison | `set(SUBJECT_FLOOR items, flattened) ⊆ derived_subjects` — a floor member absent from `derived_subjects` fails, naming it; a `derived_subjects` member absent from the floor is inspected normally and never fails for that reason |
| Membership rule | Every adopting subject (inspected under the full credential checks) belongs on the floor; an excluded subject (D4/D6) does not — the floor answers "is this covered job still here," and an excluded job's disappearance leaves no covered contract to lose (D6) |
| Content change this feature makes | Gains `board-loop.yml`: `["triage", "route", "fix", "review"]`, `cleanup.yml`: `["teardown-done"]`, `rebase.yml`: `["rebase"]`. Does not gain `watchdog.yml`: `["diagnose"]` |

## Exclusion record (`EXCLUSIONS`, new checked-in constant)

| Property | Value |
|---|---|
| Shape | `Dict[Tuple[str, str], str]` — `(path, job_name) -> reason` |
| Purpose | FR-012/FR-013: an explicit, checked-in statement that a derived subject is deliberately not held to the post-agent credential contract, and why |
| Effect on `check_job()` | When `(path, job_name)` is a key, checks 1 (stale reference), 2 (re-mint after agent step), 6 (per-agent-step composite calls), and 9 (pre-agent shadow relay) are skipped for that job; checks 3 (declared-observability tolerance) and 7 (failed-post-agent-step composite, where also named in `FAILED_STEP_REQUIRED_JOBS`) still run unconditionally, mirroring how `AGENTLESS_JOBS` already keeps checks 3/5 live for `tasks-approved` today |
| Content at ship time | One entry: `(".github/workflows/watchdog.yml", "diagnose") -> "agent step carries timeout-minutes: 10, an order of magnitude under the credential's one-hour lifetime (same basis as spec 052's auto-update-spec-kit.yml exclusions)"` |
| Failure mode it prevents | A derived subject present in neither `EXCLUSIONS` nor passing the full checks fails the gate (FR-013) — there is no third, silent state |

## Mutation (self-test fixture, `--self-test` only)

| Property | Value |
|---|---|
| Shape | `(label: str, apply_mutation: Callable)` — unchanged from today; `apply_mutation` mutates a `copy.deepcopy` of the real parsed tree (`SIMPLE_MUTATIONS`) or of `(loaded, SUBJECT_FLOOR)` (the renamed `SUBJECT_MUTATIONS`, formerly keyed to `SUBJECTS`) |
| Assertion | `self_test()` asserts every mutation's `scan()` result is non-empty (the mutation must fail the gate) and that the mutation actually changed something relative to the clean tree (FR-011, unchanged) |
| Net change this feature makes | 3 of today's `SUBJECT_MUTATIONS` entries are retired and replaced one-for-one with floor-mismatch equivalents (research.md D8); 2 new mutations are added (`mut_agent_step_reference_respelled`, `mut_excluded_job_removed_from_exclusions`); 1 existing mutation (`mut_job_loses_agent_step`) is unchanged in code but now fails via the floor-comparison branch instead of the old per-job "found none" branch |
| Total count after this feature | Strictly greater than the shipped count (SC-005) |

## Gate report (FR-007, new — printed, not persisted)

| Property | Value |
|---|---|
| Trigger | Every non-`--self-test` invocation of `main()`, on both a passing and a failing run |
| Content | The sorted `derived_subjects` set, one `path [job_name]` per line, printed alongside (not instead of) the existing `::error::` failure lines |
| Source | The same `scan()` call `main()` already makes for the pass/fail decision — never a second, independent derivation pass, so the printed set cannot drift from the set actually inspected |

## Gate registry entry (unchanged identity, updated docstring)

| Gate | Script | Wired into | Changed by this feature |
|---|---|---|---|
| 68 | `.github/scripts/verify-post-agent-credential-refresh.py` | `.github/workflows/lint-workflows.yml`, PR-time job (unchanged wiring — no registry edit, `wc_gate_registry.py`'s filename convention already covers it) | Subject selection (FR-001–FR-005), the exclusion record (FR-012/FR-013), the companion-map reasons (FR-015), the self-test mutation set (FR-009/FR-010), the module docstring and the `lint-workflows.yml` comment block (FR-017) — no numbering change, no new registry entry |

See `contracts/gate-68-subject-derivation.md` for the check's exact
structure and required mutations.
