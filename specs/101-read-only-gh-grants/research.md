# Research: Read-Only Agents Hold No Write-Capable `gh` Grant

No `[NEEDS CLARIFICATION]` markers remain in spec.md. Line numbers below are
as read on this branch (they differ from the spec's 2026-09-30 numbers).

## D1 — Where the gate rule lives

- **Decision**: Extend Gate 93 check 4b (`verify-issue-context-single-home.py`,
  `_bash_grant_problems`, `check_read_only_git(strict=False)`). In the
  non-strict branch, a `Bash` grant whose first token's basename is `gh` (any
  wildcard spelling, path-qualified) is a problem; bare `Bash`/`Bash(*)` is
  already reported.
- **Rationale**: 4b already discovers read-only sites fleet-wide, parses the
  tool-args composite inputs and inline `claude_args`, ignores `${{ inputs.* }}`
  via `_shipped`, and carries the fixtures and mutation harness. Currently the
  `elif not strict: continue` branch is what skips `gh`; the `gh` branch below
  it (strict only) already carries a message, which is reworded to name the
  staged-file route.
- **Alternatives**: a new numbered gate (duplicates discovery and harness;
  rejected); a per-subcommand allow-list (cannot see `--method`/`--cache`
  options; rejected by spec FR-002).

## D2 — How diagnose gets job logs without `gh`

- **Decision**: New `.github/actions/_shared/fetch-job-logs.sh` holds the
  per-job log fetch (jobs listing, one bounded retry, return codes). The
  existing `collect-step-summary` step (watchdog.yml ~1277-1309) is rewritten to
  call it, and a new `Stage failed-job logs` step in the `diagnose` job calls it
  too, with `ACTIONS_TOKEN: ${{ github.token }}` (workflow already grants
  `actions: read`, line 233). Logs for jobs whose conclusion is `failure` are
  written to `$RUNNER_TEMP/watchdog-job-logs/<job_id>.log`; an index
  `watchdog-job-logs-status.json` records `{outcome, failed:[...], reason}`.
- **Rationale**: `collect` and `diagnose` are separate jobs (separate containers,
  no shared filesystem), and collect's outputs are strings capped well below log
  size. Spec FR-018 allows "one helper shared with" the collector in place of a
  second inline copy; a second inline copy is what CLAUDE.md forbids. Fetching
  from diagnose avoids an artifact round-trip and a new upload/download pair.
- **Alternatives**: collect uploads logs as an artifact and diagnose downloads
  it (extra artifact surface, two steps that can fail independently, still needs
  a helper); passing logs through job outputs (size-limited, untrusted text in
  an output).

## D3 — Loud failure and verdict reporting (FR-019, FR-020)

- **Decision**: The staging step uses a direct pipeline with `|| rc=` capture
  (the pattern collect-step-summary documents at ~1262-1275), never lets a
  failed read become file content (spec 091 FR-002/FR-005), and on an
  authorization failure, missing run, or empty response writes the status file
  with `outcome:"failed"` and appends `"job-logs"` to
  `watchdog-untrusted-collectors.json` (the existing file the prompt already
  tells the agent to report from), then continues. The step is
  `continue-on-error: true`; the diagnose prompt reads the status file. No
  staged file is created for a failed fetch, so absence cannot be read as
  "nothing there": the status file is always written.
- **Rationale**: Reuses the mechanism the owner chose (Q3 Option A); the verdict
  stays schema-valid; no widening of the App token.
- **Alternatives**: failing the diagnose job on gather failure (gives no verdict;
  contradicts FR-006).

## D4 — `pr-conversation.classify` (open owner decision)

- **Decision**: Ship FR-007's total rule, and register `pr-conversation.classify`
  as an explicit, tracked exemption in the gate (an `EXEMPT_*`-style table keyed
  by workflow and step label, citing the Maintenance backlog issue as tracker,
  scoped to exactly its three current grants `gh pr view`, `gh issue view`,
  `gh search issues`). The gate fails if the exempt site holds any other `gh`
  grant, or if the exemption is stale (the site no longer holds a `gh` grant).
  This feature does not narrow `classify`.
- **Rationale**: The spec records the conflict and says no owner answer covers
  it. Failing the gate on a clean tree is not shippable (SC-001 and US3
  scenario 4 require a green tree); silently narrowing `classify` is a design
  decision reserved to the owner. A visible, tracked, self-expiring exemption
  keeps the rule total for every other site and leaves the owner's question
  open. Per CLAUDE.md, the waiver is cited to an open issue and Gate 124 must
  see it (verify the register shape at implementation time).
- **Alternatives**: narrow `classify` too (out of the owner's answers); carve
  `gh pr view|issue view|search issues` out as a read allow-list (reintroduces
  the per-subcommand reasoning FR-002 rejects, and `--comments` is unfiltered).
- **Reported to the human**: this is listed under "Decisions made without
  clarification" on the lifecycle issue.

## D5 — Auto-update agent

- **Decision**: Remove `Bash(gh api:*)` from the inline `--allowedTools` at
  auto-update-spec-kit.yml:1131 and rewrite the prompt sentence at 1092-1094
  to say Bash is restricted to the git wrapper only. Nothing is staged; the
  prompt already names `release-notes.json` as the sole evidence. The step has
  no tool-args site, so the gate covers it through the inline-list path.

## D6 — Docs and contracts, single rationale home (FR-015..FR-017)

- **Decision**: The canonical rationale lives in
  `docs/agent-friendly-workflows.md` (read-only tool-allow-list section). The
  four live contracts and Gate 93's docstring/messages point to it and state
  only the new shipped lists. The spec 051 "pre-existing, wider grant"
  paragraph is rewritten in the past tense with a pointer. A "single home"
  check is added to check 4b's neighbour only if a cheap deterministic form
  exists (a grep-style assertion that the rationale's distinguishing sentence
  occurs in exactly one file); otherwise tasks must note why not (CLAUDE.md:
  a rule with no gate lasts until the next session).

## D7 — Findings noticed while planning

- `spec.md`'s status update cites `watchdog.yml:2363` and `:1133/1146`; on this
  branch the lines are 2585 and 1277-1306. Spec documents are not corrected
  after merge (repo rule); noted only.
