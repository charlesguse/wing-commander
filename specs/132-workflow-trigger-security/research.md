# Research: 132-workflow-trigger-security

No [NEEDS CLARIFICATION] markers remained in spec.md. The spec delegated several choices to the plan; they are decided here.

## D1. Analyser version and invocation
- **Decision**: zizmor 1.33.1, run as `zizmor --offline --format json --config .github/zizmor.yml .github/workflows .github/actions`. The version string lives in one file, `.github/zizmor.yml`'s neighbour `.github/scripts/zizmor-pin.txt`, read by the gate and by CI's install step.
- **Rationale**: matches the issue's scan; `--offline` meets FR-004; JSON output is parseable (FR-003).
- **Alternatives**: floating latest (rejected: a new audit would turn main red unprompted); online mode (rejected: needs a token, differs on fork PRs).

## D2. Register key
- **Decision**: key is `(file, audit, location)` where location is `job:<id>` or `job:<id>/step:<id-or-name>`, or `workflow` for workflow-level findings. No line numbers. The gate maps zizmor's reported location to the nearest enclosing job/step by parsing the YAML.
- **Rationale**: survives unrelated edits (spec edge case).
- **Alternatives**: line numbers (churn); zizmor's own ignore comments (scatter exceptions across files, no tracker field).

## D3. Where the register lives
- **Decision**: `.github/scripts/zizmor-findings-waivers.json`. Entries carry `issue` ("#N" or permanent with reason), optional `decided_by`, plus `reason` and `control`.
- **Rationale**: gate 124 globs `*-waivers.json`, so FR-013 holds with no change to it.

## D4. Trusted-publisher home
- **Decision**: the `unpinned-uses` policy in `.github/zizmor.yml` (`actions/*`, `github/*`, `anthropics/*` as `ref-pin`; `*` as `hash-pin`) is the home. The gate and the single-home check read it. Any other `.github/` file listing publishers as a pin policy fails.
- **Rationale**: zizmor enforces it directly, so no generated copy can drift (FR-009a first branch).
- **Alternatives**: separate JSON plus generated YAML plus a diff check (two files to keep aligned for no benefit).

## D5. `self-repository` disabled
- **Decision**: `disable: true` for the `self-repository` audit in `.github/zizmor.yml`, with the recorded reason in a YAML comment on the line directly above plus a `reason` field the gate parses. The gate fails when the reason is missing (FR-016, SC-011).
- **Alternatives**: move to `$/` (rejected by owner, clarify Q2).

## D6. Pin-update automation
- **Decision**: add `.github/dependabot.yml` for `github-actions` (weekly, grouped), which updates SHA and version comment together. A small workflow step or gate check on bump PRs ensures Gate 170 rows are present; first choice is a workflow `update-action-pins.yml` that runs on `pull_request` for `dependabot[bot]` PRs and fails with a pointer when register rows are missing. If Dependabot cannot write `action-runtime-pins.json`, the human adds rows before merge (FR-017a permits that). Bump PRs are human-merged.
- **Rationale**: no new bot merge class (FR-009b); Dependabot is the smallest mechanism. Adding `.github/dependabot.yml` is a repository config file, not a repository setting.
- **Open for tasks stage**: confirm Dependabot's SHA-plus-comment behaviour for composites under `.github/actions/**` (directories must be listed). Fall back to a scheduled workflow if not.

## D7. Untrusted-checkout gate model
- **Decision**: per job, build an ordered list of workspace-placing steps: `actions/checkout` (repository, ref, path), `download-artifact`, `tar`/`unzip` in `run:`, and writes. Classify by repository+ref: trusted copy = running repo at `github.sha` (top-level and repo-only reusable workflows) or pipeline repo at the resolved pipeline ref (published stages). Anything else is untrusted. For each `uses: ./<path>`, find which placement the path falls under; if untrusted, fail. A `./` path under no tracked placement but at the workspace root with an untrusted root checkout also fails. Composites are evaluated in the context of each calling job.
- **Fold plan**: the checkout-before-`./` rule of Gates 104 and the lifecycle-review-gate provenance gate moves into this gate; each older gate keeps only its workflow-specific rules (helper provenance, pristine-copy path names). Task stage verifies no rule logic is duplicated.
- **Alternatives**: keep three separate rules (rejected by FR-016a one-home requirement).

## D8. Repo-only reusable workflows
- **Decision**: `.github/scripts/repo-only-reusable-workflows.json` lists them (initially `shared-pr-reviewer.yml`). A `workflow_call` workflow not listed is a published stage. The gate fails a repo-only treatment of an unlisted file (FR-006).

## D9. Event-policy docs and check
- **Decision**: `docs/adoption.md` gains a "Events and gates" section with a table and a fenced `yaml` sample policy block labelled `wc-event-policy`. `verify-adopter-event-policy.py` extracts events from every `wing-commander-*.yml` `on:` and fails when one is missing from the block. Also fails when the block is absent.
- **Rationale**: docs and wrappers cannot drift (FR-020).

## D10. Exposure audit delivery
- **Decision**: the untrusted-checkout gate has an `--audit` mode printing the jobs it would fail; its output is posted to lifecycle issue #1188 once at implement time. `pr-conversation.yml`'s `wing-commander-outstanding-task-item` step is fixed in its own PR (spec assumption); the gate's baseline must be green after that PR lands.

## D11. Remaining findings (`github-env`, `artipacked`, `excessive-permissions`, `github-app`)
- **Decision**: triage one by one at implement time. Default: fix `artipacked` with `persist-credentials: false` where no later git push needs it; record the rest with reason, control and tracker. Rule: none left unrecorded (FR-008).

## D12. Zizmor install in CI
- **Decision**: download the release asset for the pinned version with a checksum recorded next to the pin; local runner uses `zizmor` on PATH and fails if its `--version` differs from the pin. A missing binary fails the gate (FR-003).
- **Alternatives**: `pip install zizmor` / `uvx` (needs network at gate time, no checksum by default).
