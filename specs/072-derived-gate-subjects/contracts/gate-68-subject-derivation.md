# Contract: Gate 68's subject selection — `verify-post-agent-credential-refresh.py`

**File**: `.github/scripts/verify-post-agent-credential-refresh.py`,
already wired into `.github/workflows/lint-workflows.yml`'s PR-time job
(unchanged: `wc_gate_registry.py`'s filename convention already picks it up,
and `verify-gate-wiring.py` already confirms the wiring). This contract
amends spec 052's `post-agent-credential-refresh-gate.md` — that document's
"What it checks" items 1–3 (stale reference, un-refreshed second agent
step, un-tolerated observability step) and its `check_job()` mechanism are
unchanged; this document narrows on how the *subject set itself* is
produced and gated, which is this feature's whole scope.

**Numbering**: unchanged. Still Gate 68; this feature changes its subject
selection and its self-test, not its registry entry.

## Subject (changed)

Previously: the 8 files (9 job entries) `SUBJECTS` named by hand, matching
FR-007 of spec 052.

Now: every job, in every `.github/workflows/*.yml` file, that contains at
least one step whose `uses:` matches `^anthropics/claude-code-action@`
(`AGENT_ACTION_RE`, unchanged from the shipped gate) — see
`data-model.md`'s "Subject job" and "Agent step" entries for the exact
derivation rule and its edge cases (reusable-workflow-call jobs, comment
mentions). No file-path allowlist remains anywhere in the derivation path.

## What it checks (amended)

Items 1–3 and 5–8 of spec 052's contract (stale reference, un-refreshed
re-mint, un-tolerated declared-observability step, single-home composite
resolution, per-agent-step composite calls by position, the failed-post-
agent-step composite's existence) are unchanged in mechanism, and now run
against every derived subject rather than only the 9 hand-named ones,
*except* a subject named in `EXCLUSIONS` (see below), which skips only the
credential-freshness-specific items (1, 2, 6, 9 in the gate's own numbering)
and still runs the rest.

Four checks are new or amended for subject derivation itself:

1. **Floor coverage** (FR-004): every `(path, job)` pair in `SUBJECT_FLOOR`
   MUST appear in the derived subject set; a floor member the derived set no
   longer yields fails the gate, naming that `(path, job)`. A derived
   member absent from the floor is inspected like any other subject and
   never fails for that reason (FR-004's second bullet — this is what makes
   an un-updated floor fail *safe*, never a shrink-and-pass).
2. **Non-empty derivation** (FR-005): if the derived subject set is empty —
   whether because the glob found no files, every found file parsed to zero
   agent steps, or the glob step itself is unreachable — the gate fails as
   misconfigured, naming that it found nothing, rather than reporting a
   vacuous pass. (This subsumes the shipped gate's existing "zero agent
   steps found across the whole named subject" check — the check is the
   same assertion, now phrased over the derived set instead of the
   hand-named one.)
3. **Unreadable/unparseable file** (FR-006): a `.github/workflows/*.yml`
   file that exists but cannot be parsed by `yaml.safe_load` fails the
   gate, naming the file — never silently contributing zero subjects.
4. **Exclusion completeness** (FR-012/FR-013): every derived subject not
   passing the credential-freshness checks (1/2/6/9) MUST be a key of
   `EXCLUSIONS`; a derived subject that is neither compliant nor excluded
   fails the gate under its ordinary failure message (no new message class
   — an unexcluded, non-compliant subject was always going to fail checks
   1/2/6/9 on its own merits; the exclusion record's job is only to let a
   *compliant-by-construction-impossibility* subject like `watchdog.yml`'s
   `diagnose` opt out of those checks instead of failing them).

## Disposition of the four newly-surfaced workflows (FR-014, this feature's own scope)

`board-loop.yml` (`triage`, `route`, `fix`, `review` — 5 agent steps across
4 jobs), `cleanup.yml` (`teardown-done`), and `rebase.yml` (`rebase`) each
adopt the post-agent credential contract as production code changes in this
feature (data-model.md's "Subject floor" gains all six job entries).
`watchdog.yml`'s `diagnose` is excluded, recorded once in `EXCLUSIONS`, on
the stated `timeout-minutes: 10` basis FR-014 already names. See
research.md D5 for the per-job structural evidence (wall-clock bound
presence, which bot-acting steps follow the agent step, and what credential
form they read) grounding each of these seven dispositions.

## Mechanism (unchanged)

Static structural inspection via `yaml.safe_load`, no `wc_shell_harness.py`
execution pass — this gate's subject remains step *ordering and reference
shape*, never step *behaviour*. The only mechanism addition is the glob
(`glob.glob(".github/workflows/*.yml")`, or equivalent directory listing)
that replaces `SUBJECTS.keys()` as the file-enumeration source.

## Fixtures (FR-009, FR-010, FR-011 — every failure branch checked in)

| Mutation | Expected result | Status |
|---|---|---|
| Clean tree (no mutation) | PASS | unchanged |
| Rewrite a post-agent step's credential reference back to `steps.ctx.outputs.token` (and its bracket/`fromJSON`/`toJSON` variants) | FAIL — names workflow, job, step | unchanged (10 existing variants) |
| Delete a refresh step between two agent steps, or after a job's only/last agent step | FAIL | unchanged |
| Strip `continue-on-error: true` from a "Report over-budget agent run" step, bare or suffixed | FAIL | unchanged |
| A single-home composite call (agent-ran-signal, refresh-remote, failed-post-agent-step, stall-reason) reverted to a non-composite step, or deleted outright | FAIL | unchanged |
| Per-agent-step composite call deleted for one agent step while another's is duplicated (job-wide total unchanged) | FAIL | unchanged |
| A pre-agent step relays the pre-agent token into a non-canonical `$GITHUB_ENV` variable | FAIL | unchanged |
| An unrelated, non-mint step's `toJSON(steps.<id>)` dump | PASS (negative control) | unchanged |
| `SUBJECT_FLOOR` names a workflow file the derived set no longer reaches | FAIL — "subject dropped," names the file | **replaces** `mut_nonexistent_ninth_file` |
| `SUBJECT_FLOOR` names a job the derived set no longer reaches inside an existing file | FAIL — "subject dropped," names the job | **replaces** `mut_nonexistent_job_in_existing_file` |
| Derivation yields zero subjects (glob step returns no files) | FAIL — "misconfigured, zero subjects" | **replaces** `mut_zero_files`; also satisfies FR-009's "derived set emptied" minimum |
| A subject job's agent step replaced with a non-agent step | FAIL — now via the floor-mismatch branch (the job silently drops out of derivation and the floor still names it), not the old per-job "expected an agent step, found none" branch | unchanged mutation, changed failure branch (FR-010) |
| A real agent step's `uses:` respelled to a reference `AGENT_ACTION_RE` does not match (e.g. `claude-code-action-v2@v1`), on a job distinct from the one above | FAIL — "subject dropped" | **new** — FR-009's third named minimum |
| `watchdog.yml`/`diagnose`'s `EXCLUSIONS` entry removed | FAIL — `diagnose` is now inspected under the full checks and fails them (no relay/refresh/signal/credential-status machinery exists in that job) | **new** — proves the exclusion record is load-bearing (FR-013) |

Every mutation continues to apply to a `copy.deepcopy` of the real parsed
tree (and, for the floor-keyed mutations, of `SUBJECT_FLOOR` itself) — no
second, synthetic YAML fixture file, consistent with spec 052's research.md
D6 rationale.

## Subject report (FR-007, new)

Every invocation of `main()` outside `--self-test` prints the derived
`(path, job)` set — sorted, one per line — alongside its existing
`::error::` failure lines, on both a passing and a failing run, sourced
from the same `scan()` call that decides pass/fail (never a second
derivation pass). See data-model.md's "Gate report" entry.

## Local/CI parity (FR-016, unchanged)

`run-local-gates.py` derives this gate's invocation from
`lint-workflows.yml`'s own `run:` block
(`wc_gate_registry.pr_time_invocations()`) — untouched by this feature,
since neither the gate's registration nor its argument-free invocation
(`python3 .github/scripts/verify-post-agent-credential-refresh.py`) changes.

## Triggering (FR-016, unchanged)

`lint-workflows.yml`'s `on.pull_request.paths` already includes
`.github/workflows/**` — a change to any of the 34 workflow files this gate
now reads, not only the 9 (now 15) it used to, already triggers it; no new
path entry is required.

## Docstring and registry comment (FR-017, new obligation)

The module docstring's "WHAT THIS CHECKS" preamble ("For each of the 8
sweep-stage jobs...") and `lint-workflows.yml`'s Gate 68 comment block
("Every agent-bearing job in the 8 sweep stages...") both currently state a
fixed count. Both MUST be rewritten to describe the derived rule (D1/D2)
and the floor/exclusion split (D3/D4) instead of a count, since the count
is no longer fixed by this feature's own design.
