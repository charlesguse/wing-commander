# Research: Feature Health

No `[NEEDS CLARIFICATION]` markers remain in spec.md (the three questions were answered on 2026-11-22). The decisions below are the plan's own; those marked **default** are made without the owner and may be reversed by one revert.

## D1. Pure classifier plus runtime collector (default)

- **Decision**: a new `.github/scripts/wc_feature_health.py` with a pure half (`classify_workflow`, `classify_feature`, `render_section`) that takes already-read data and an injected `now`, and a runtime half (`collect`, `build`) that reads through `gh`. The pure half does no I/O.
- **Rationale**: SC-003 (same inputs, same states) and SC-006 (a fixture per failed read) need the classifier driven from checked-in JSON. This is the split `wc_proof_list.py` and `wc_board_status.py` already use.
- **Alternatives**: classify inside `wc_board_status.py` (grows a file that is already the issue's writer, and a failed health read would risk the whole rewrite); a shell/jq program (untestable per branch, and Principle IX prefers code).

## D2. The registry is one JSON file, validated by a gate (FR-001, FR-002, SC-007)

- **Decision**: `.github/scripts/feature-health-registry.json`, one object per feature: `name`, `workflows` (list of `{file, stage?, cadence}`), `kill_switch`, `requires_var`, `signal` (`{kind, ...}` or null), `quiet_days` (optional, default 14). JSON, not YAML, so the pure half and the gate read it with the stdlib. `verify-feature-health.py` (new, unnumbered step in `lint-workflows.yml`, as `verify-proof-list.py` is) checks:
  - every workflow in reference.md's "At a glance", "Housekeeping and observability" and "Schedules" tables has an entry, or sits in a small `EXEMPT_UNREGISTERED` table citing the Maintenance backlog (#889) (dispatch-only helpers, `agent-startup-check` is registered, not exempt);
  - every `file` exists under `.github/workflows/`;
  - every `kill_switch` is a name in reference.md's "Kill switches" table;
  - the fixture where reference.md lists a feature the registry lacks fails (SC-007).
- **Rationale**: the spec requires one home and a drift gate. Parsing the Markdown tables is the same technique other gates use on reference.md.
- **Alternatives**: put the registry in reference.md itself (a table cannot carry per-workflow cadence and signal structure); one YAML per feature (many homes).
- **Waiver rule**: the gate takes its exemption table as a parameter (CLAUDE.md, Gate 124 note in the proof-list plan), so fixtures pass their own dict.

## D3. A separate workflow, handing off an artifact (FR-009, FR-012, FR-013, FR-015)

- **Decision**: `.github/workflows/wing-commander-feature-health.yml`, daily 06:29 UTC (before board status at 07:17, after the proof list at 06:19), `workflow_dispatch` from the default branch only, read-only permissions (`contents`, `actions`, `issues`, `pull-requests`: read), no agent, no App token. It uploads the artifact `feature-health-section`. `wc_board_status.py` stays the issue's only writer: a `feature_health_snapshot()` beside `proof_list_snapshot()` reads the workflow's finished default-branch runs, decides `built`, `paused`, `failed`, `never` or `unreadable` and the last good build (FR-014), downloads the artifact, and `render()` embeds it. A new kill switch `WING_COMMANDER_FEATURE_HEALTH_PAUSED` joins `SWITCH_ENV`; creating it is the owner's (FR-015). `WING_COMMANDER_BOARD_STATUS_PAUSED` still stops the rewrite.
- **Rationale**: FR-015 permits a separate workflow with its own switch. A separate workflow isolates failures: a health read that fails must not stop Board status. It repeats the shape spec 124 settled, so the writer's hand-off code is reused rather than rewritten.
- **Alternatives**: run the build inside `board-status.yml` (no new switch, but one failed read could block the whole rewrite, and `board-status.yml` would need read scopes for every feature); a second tracking issue (the spec puts the report in Board status).

## D4. Reads that stay complete: date-sliced run listing (FR-010, FR-011, User Story 3)

- **Decision**: per workflow file, `GET /repos/{r}/actions/workflows/{file}/runs?status=completed&created=START..END&per_page=100`, paginated. If a page reports `total_count` above 1,000, the window is split by day (then by hour) and read per slice; a slice that still reaches 1,000 makes that workflow, and so its feature, *unreadable* with the reason. The window is `max(30, longest quiet_days, failing-window span) + 1` days. Skipped-by-design is read from the run's conclusion `skipped` together with the configuration variable (D6), not from step logs.
- **Rationale**: the spec names the 1,000-run cap for event-driven wrappers. Slicing mirrors the proof list's D5 reader.
- **Alternatives**: read the latest 1,000 and trust it (silent truncation, the failure FR-011 forbids).

## D5. Output signals use the repository's own records (FR-003)

Each signal is a function from a read-through-`gh` listing to the time of the latest occurrence:

| Feature | Signal kind | Read |
|---|---|---|
| lifecycle | `merged_pr` | merged PRs with head `spec/*` or label of a final PR |
| Spec Kit updater | `merged_pr` | merged PRs whose head matches the updater's branch pattern |
| auto-release | `release` | `GET releases`, latest `published_at` |
| watchdog | `issue_or_comment` | issues with its label, or the inspected-run notice marker |
| board loop | `merged_pr` (`fix/` head) or `triage_close` | merged `fix/` PRs; issues closed with a triage marker whose ground is `rate-limited run` or `upstream action bump` (grounds read from `board_triage.py`, not copied) |
| metrics | `branch_commit` | latest commit on the metrics branch (`WING_COMMANDER_METRICS_BRANCH`) |
| board status | `issue_updated` | the tracking issue's `updated_at` |
| proof list | `issue_section` | the section's marker in the Board status body, plus its build time |

A signal read that fails makes the feature *unreadable* (FR-010). Patterns (branch prefixes, labels, marker strings) are imported from the scripts that own them where one exists; the plan's task list names each import so the gate can check it.

- **Alternatives**: infer success from green runs (FR-008 forbids it).

## D6. Kill switch and configuration reads (FR-004, FR-010)

- **Decision**: one `GET /repos/{r}/actions/variables` page is read once per build into a dict; an entry's `kill_switch` is on when `wc_board_status._switch_on` says so (called, not re-implemented). `requires_var` (the private-image dogfood's image variable) unset means *not configured* when the workflow's runs were skipped. A 403/404 on the variables read makes each entry that names a variable *unreadable*, and entries that name none are still classified. The workflow's `GITHUB_TOKEN` cannot read variables; **default**: pass them in as `vars.*` env, as `board-status.yml` already passes its switches (`SWITCH_ENV`), and treat an empty-and-unreadable distinction by the same convention `wc_board_status.switches_from` uses.
- **Rationale**: reuse the writer's existing switch plumbing rather than a second reader.

## D7. Classification order and worst-of (FR-004, FR-005, FR-006, FR-017, FR-018)

- **Decision**: `classify_workflow` returns the first fitting state in the order *unreadable, paused, not configured, failing, not running, quiet, idle, healthy*. Runs are filtered to finished; skipped (except *not configured*) and cancelled runs count only toward cadence. The failing window is the last 3 qualifying runs. *Not running* applies per workflow stream, scheduled only: no run started within interval plus one interval (interval parsed from the cron in the workflow's `on.schedule`, read with PyYAML; an entry with both a schedule and events uses the schedule for this test only). `classify_feature` takes the worst state by that same order, dropping *idle* workflows when a sibling has a qualifying run. Runs are never pooled.
- **Rationale**: this is the spec, verbatim; deterministic code, no clock reads (`now` is a parameter).
- **Alternative**: deriving the interval from the registry instead of the workflow file (a second place to drift); the file is the source of truth, and the gate checks the entry names a scheduled workflow only where it declares a schedule.

## D8. Report shape and size (FR-009, FR-014, User Story 1)

- **Decision**: the artifact is a Markdown fragment: build time, the unreadable count, the call-out lines (called-out states only), then the full table in a `<details>` block. Each row: feature (stage rows indented beneath the lifecycle), state, last success, last failure, last signal, and the threshold or "signal not measured". The writer wraps it in its own markers, as for the proof list, so a rewrite with a failed or paused latest build says so and names the last good build date. If the table would exceed the body limit, the writer drops the table and keeps the call-outs and a "table shortened" line, using `MAX_BODY_UNITS`.
- **Alternative**: only call-outs (loses the "which features exist" context the spec's Assumptions chose to keep).

## D9. The report's own feature and the first cut (SC-001)

- **Decision**: board status's row reflects the previous build because the writer runs after the build. SC-001 replays from a checked-in corpus (`fixtures/feature-health/sc001/corpus.json`, `expected.json`) holding run listings, signal timestamps and switches for 2026-10-14 to 2026-11-12, with `now` fixed at 2026-11-12. Capture is a `[maintainer]` task (needs full history and an authenticated `gh`); until it lands the check reports "not yet captured" under an `EXEMPT_SC001_PENDING` entry citing #889, as spec 124 did. The implement stage must not edit the corpus or expected file.
- **Alternatives**: synthesise the corpus (cannot show the first cut's real shapes).

## D10. Files and docs the change touches

`docs/reference.md` (FR-016): the board-status row, "Housekeeping and observability" new row, "Kill switches", "Schedules" (06:29), and the At-a-glance line. `docs/setup.md` §3 gains a row for the new variable. The README's repository-only workflow list gains the workflow. These are listed as an ordinary docs task.
