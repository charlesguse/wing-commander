# Research: One Reviewer for Every Kind of Pull Request (127)

Layer: this describes the consuming instrument (this repository's own wrapper and scripts). Nothing here widens the published contract (spec FR-002).

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below are the plan-level choices the spec leaves to this stage; each is reversible by one revert.

## D1. Distinct marker, not a reused one

- **Decision**: The round record is an HTML-comment marker named `wing-commander-shared-review-round`, with a JSON payload carrying `"reviewer": "shared-pr-reviewer"`, `"schema": 1` and the fields of data-model.md. It is not written under `wing-commander-convergence-round`.
- **Rationale**: `read_round_records` in `wc_convergence.py` matches only `ROUND_MARKER = "wing-commander-convergence-round"` (`ROUND_MARKER_RE`). A different marker name can never be read by it, so FR-020's "existing readers never count a shared-reviewer record" holds with **zero edits** to `wc_convergence.py` (FR-005 keeps the existing reviewers unchanged). The reviewer field is still written, so a later reader can tell the kind.
- **Extends, not forks**: the new module imports `board_item_marker.marker_json`, `last_marker_match` and `is_loop_marker_author` (the same helpers `read_round_records` uses): last-opener-wins, bot-authored-only, `-->` escaping. The payload keeps `round`, `head_sha`, `findings` (`fingerprint`/`file`/`line` kept per finding) so a later move of a reviewer onto this record is a field mapping.
- **Alternatives**: reuse the old marker and rely on a `reviewer` filter in `read_round_records` (rejected: edits an existing reader, and any reader that forgets the filter miscounts); a PR comment with a fenced JSON block (rejected: the marker form is the repo's established, forge-resistant form).

## D2. Where the code lives

- **Decision**: One deterministic module `.github/scripts/wc_shared_review.py` (record build/parse, identity assignment, open-set computation, blocking rule, verdict, budget, run confirmation, request validation) with a thin CLI used by the workflow. Gate-shaped tests under `.github/scripts/tests/` and `verify-*.py` gates registered in the gate registry. A composite `.github/actions/_shared/` script is used only for anything a second workflow also needs; at present nothing is, so no composite is added (CLAUDE.md "one home" is satisfied: the module is the single home).
- **Rationale**: Principle IX: identity, status, open set, blocking, verdict, budget and confirmation are judgment gating a durable record, so all are code, tested with fixtures (Principle VIII).
- **Alternatives**: jq/shell inside the workflow (rejected: untestable, and the exact paste-drift CLAUDE.md warns about).

## D3. Workflow shape

- **Decision**: `.github/workflows/shared-pr-reviewer.yml` is the callable workflow (`on: workflow_call` only); `.github/workflows/wing-commander-shared-pr-reviewer.yml` is the wrapper owning `workflow_dispatch` (input `pr`, optional `dismissals` JSON) and reading `vars.*`. Jobs, in order: `guard` (no agent; default-branch check FR-022, kill switch FR-026, fix-PR kind check FR-001, budget FR-025), `prepare` (no agent; reads PR, purpose source, earlier confirmed records, builds staged inputs), `code-run` (no agent, no secret), `find` (agent), `check` (agent, no shared context with `find`), `record` (deterministic; the only job that posts, the only one holding the App token, and it holds no agent output beyond the artifact).
- **Rationale**: FR-012/FR-027: the job that runs PR code must hold no secret, so it is separate from `prepare` and from both agent jobs; agents hold no write credential (the `record` job posts). A workflow `concurrency` group per PR (`shared-pr-reviewer-<pr>`, `cancel-in-progress: false`) gives FR-026 serialization.
- **Published-contract exclusion**: spec says the reviewer is not added to the published contract in this feature. The callable file lives beside the stage workflows because that is where `workflow_call` workflows live; the implement stage registers it in whatever the contract gate uses to enumerate published stages as "internal, unpublished" (task: find that registry and add the entry with its reason). If no such exclusion form exists, a registered, machine-checked exception naming the reason is added (Principle VII); workflows cannot use an underscore-prefixed directory.
- **Alternatives**: single job running both agents (rejected: FR-010 needs no shared context; and secrets/PR code separation).

## D4. Default-branch refusal and run identity

- **Decision**: `guard` compares `github.ref` to `refs/heads/<default branch>` passed as a wrapper input and fails closed to a visible summary refusal, before any agent job (`needs: guard`, `if:` on its output). All scripts, prompts and tool lists come from a checkout of the default branch SHA; the PR head is checked out only into a separate directory in `code-run` and as data for `prepare`. Prompts are never read from the PR tree.
- **Rationale**: FR-022, Story 4, SC-003. Gating follows the `review-step-gating` skill: downstream jobs use `!cancelled()` only where they must report; the `record` job never runs when `guard` refused.

## D5. Run confirmation

- **Decision**: `confirm_record(record, run, pr_head_sha_reviewed)` mirrors `verification_run_confirms`: the record's `run_id` must be digits and equal `run["id"]`; `run["path"]` equals the wrapper's path; `run["head_branch"]` equals the default branch; `status == completed`, `conclusion == success`; `referenced_workflows` contains `<repo>/.github/workflows/shared-pr-reviewer.yml`; and `run["head_sha"]` equals the record's `reviewer_commit` (the run's default-branch commit). The reviewed PR commit is bound by the record's `head_sha`, which only a confirmed run could have written; an artifact `shared-review-<head_sha>` uploaded by that run is required in `run["artifacts"]`, which binds the run to the reviewed commit the way the bump verification artifact does.
- **Rationale**: FR-021/SC-002. The record is posted by the `record` job inside the run, so the run is still `in_progress` when it posts; the reader therefore confirms later (when reading), and `conclusion == success` is required then. The reviewer writes its own count of the current round from the confirmed set only.
- **Alternatives**: trust the author being the App bot only (rejected: the spec requires run read-back).

## D6. Identity, repeats and the open set

- **Decision**: Finding ids are `F<round>-<n>` allocated by code in record order per PR. The finding job may emit `cites: "<id>"` per candidate; code keeps the cited id only if it exists among confirmed earlier findings (FR-016). Uncited candidates whose `file` equal and line range overlap an earlier finding's get a new id plus `possible_repeat_of`. `wc_review_finding_fingerprint.py` is reused for the stable `fingerprint` kept in each entry for later readers; it is not an identity input.
- **Open set**: fold confirmed records in round order; a finding's status is the latest row of FR-015's table; open = `upheld` or `reopened`. The requester dismissals ride in the dispatch input `dismissals` and are applied from the start of the round carrying them (and only if validated to name an open id).
- **Rationale**: FR-015..FR-018; Story 2 scenarios 1-8.

## D7. Blocking and verdict rules

- **Decision**: The checking job reports per finding: `in_scope` (bool), `reachable` (bool), `reproduces` (bool|null), `cites_only_spec_docs` (bool). Code: blocking = upheld/reopened ∧ in_scope ∧ reachable. A finding citing only a merged spec's spec/plan/tasks/research (path rule applied by code to its `files`) is dismissed with that reason by code. Verdict order exactly as FR-014, computed by `compute_verdict`.
- **Code-run missing**: re-check of an open finding with `needs_code_run` and `code_run == missing` yields status unchanged, note "not re-checked: code-run results missing"; never resolved (FR-015 row 7). A missing code-run is `incomplete` only after `findings` is ruled out.

## D8. Code-run isolation (SC-008)

- **Decision**: `code-run` job: `permissions: {}`, no `secrets` context referenced, `GITHUB_TOKEN` not persisted (`persist-credentials: false`, and `permissions: contents: read` only on the checkout step via a read-only token passed as data is avoided: the PR head is fetched in `prepare` and handed over as a tarball artifact). It runs exactly two commands: the PR's named check (a test path discovered by code from the diff's added test files and run through a fixed runner invocation, never a path chosen by the agent) and `python .github/scripts/run-local-gates.py` from the *default branch's* gate runner against the PR tree. Output is a JSON file with exit codes and truncated output uploaded as an artifact; `check` downloads it as data. Timeouts bound it. Evidence for SC-008 (a)-(d) is a checked-in fixture PR tree whose check tries `env`, `$ACTIONS_*`, writes into the artifact directory, and tries a third command; a verifier asserts the staged result.
- **Alternatives**: running the check in the `check` agent job via a Bash tool (rejected: FR-012 forbids).

## D9. Agent jobs

- **Decision**: Both use `anthropics/claude-code-action` like the sibling reviewers, with `model` from `vars.WING_COMMANDER_SHARED_REVIEW_FIND_MODEL`/`..._CHECK_MODEL` defaulting `claude-sonnet-5-5`, `--max-turns` set from vars with defaults (find 40, check 40), no effort override, tools from `wing-commander-tool-args` (read-only: Read, Grep, Glob, and git read verbs; no web, no Write/Edit outside a scratch output file path). Untrusted text is wrapped in delimited data blocks stated as data (Principle V).
- **Rationale**: FR-024, FR-027, Principle II.
- Turn defaults are plan-level numbers; a repository variable overrides them.

## D10. Purpose source, budget, kill switch

- **Purpose source** resolved by code in `prepare` in the order: issue cited as closing/`#N` in PR body that is not the PR itself; a Maintenance-backlog line reference; a run URL. Issue text is taken as of PR creation by reading the issue's edit history is not available via the permitted API in all cases, so the implementation records "version used: current" unless a `userContentEdits` read succeeds (recorded either way, spec edge case).
- **Budget**: `WING_COMMANDER_SHARED_REVIEW_ROUND_BUDGET` default 5, counted over confirmed rounds (including `incomplete` ones). Hand-off record is a distinct marker kind `handoff` in the same marker family.
- **Kill switch**: `WING_COMMANDER_SHARED_REVIEWER_PAUSED`.
- **CLAUDE.md line** (FR-004): the implement stage adds the one sentence from the spec Scope to the fix-PR section; docs/reference.md gets the loop row, defaults and switch (CLAUDE.md says which changes update it).

## D11. Comparison (FR-029, SC-007)

- **Decision**: The record comment carries a fixed human header line (`Shared reviewer — round N at <short sha> — verdict V`) above the marker; `review-until-clean` already reports on the PR, so both are findable from the PR. A small reader script `shared_review_compare.py` lists, per fix PR, confirmed record and the hand-review comment at the same head. No change to `review-until-clean`.
