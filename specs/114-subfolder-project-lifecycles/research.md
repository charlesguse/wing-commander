# Research: Subfolder Project Lifecycles

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The spec leaves several decisions to planning. Those are resolved here, and the ones that rest on an unverified assumption are marked **Assumption** so implement can verify them early.

## D1 — Where project logic lives

**Decision**: One shared script `.github/actions/_shared/project-name.sh` holds the path grammar, the name parser in both directions (build and parse) and the label-budget arithmetic. A composite `wing-commander-project` sources it and emits outputs. Workflows consume the outputs. Each call site keeps at most a one-line fallback for when the composite never ran.

**Rationale**: CLAUDE.md "Shared logic has exactly one home". FR-013 requires one parser for every name type. The per-run cost line is the cautionary precedent.

**Alternatives**: Inline `run:` per workflow (rejected: pasted copies drift). A Python module (rejected: composites in this repo are bash and `_shared/` already holds `.sh` helpers; gates, not runtime, are Python).

## D2 — Shared parser algorithm (FR-013)

**Decision**: Input is one name plus its kind: `branch`, `label`, `slug`, or `spec-dir`.

1. Strip the repository-wide flat prefix: the spec-draft, spec or implement prefix for branches; `spec:` for labels.
2. For implement branches, strip a trailing `-iterN`.
3. For `spec-dir`, require the form `[P/]specs/<NNN-slug>`.
4. Take the last `/`-segment as `NNN-slug` (must match `^[0-9]{3}-[a-z0-9-]+$`). The remainder, possibly empty, is `P`, and `P` must pass the grammar.

Output is `(P, NNN-slug)`. Slug, branch, label and spec-dir forms of one lifecycle yield the same pair.

**Rationale**: The spec bans `specs` and `NNN-` segments inside `P` (FR-002), so the last segment is unambiguous. The flat prefixes are single-segment (preflight rule), so stripping them first is exact.

**Alternatives**: Encode `P` inside the prefix (rejected by the spec: it breaks watchdog and fold-cycle-guard prefix assumptions).

## D3 — Path validation (FR-002)

**Decision**: `project-name.sh validate-path` checks, in order:

1. Regex `^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*$`.
2. No segment equal to `specs`; no segment matching `^[0-9]{3}-`.
3. Length ≤ 28.
4. The path is a real directory on the checked-out ref, with no symlinked ancestor. Walk each prefix with `test -L`.
5. `P/.specify`, `P/.claude`, `P/.claude/skills/speckit-*`, `P/specs` (when present) and the constitution `P/.specify/memory/constitution.md` are real, non-symlink entries.

Rejection is a hard failure; the path is never normalised. The check runs against the default-branch checkout at intake and against the working ref in later stages (the stale-folder check).

**Rationale**: Deterministic code, per Principle IX and FR-002.

## D4 — Routing label read (FR-001, FR-003)

**Decision**: Intake gets one new optional input, `routing-label-prefix` (default `''`). When non-empty, a deterministic step:

1. Validates the prefix (D5).
2. Lists the issue's live labels with `gh issue view <issue-number> --json labels`, using the `issue-number` input and never the event payload or body.
3. Filters labels by prefix.
4. Counts: 0 gives root; 1 gives `P` (then D3); 2 or more gives a callout on the lifecycle issue and a failed run.

Later stages never read it; they parse identity (D2).

With routing on, a re-run on an issue that already carries a `spec:` label refuses (D8). With routing off, none of this runs and intake is byte-identical to today (FR-016).

## D5 — Prefix validation (FR-023)

**Decision**: Regex `^[a-z0-9][a-z0-9-]*:$` (lowercase segment characters, exactly one trailing `:`). Reject if equal to, or a prefix-overlap with, any of the families `spec:`, `stage:`, `model:`, `board:`, `disposition:`, the intake input `findings-label-prefix`, the write-boundary default `route-out-of-boundary`, and the entry labels `spec-request` and `spec-proposal`. Overlap means a family name starts with the candidate, or the candidate starts with a family name. A prefix `spec-` is rejected because `spec-request` starts with it. Also require `len(prefix) + 28 ≤ 50`.

The overlap test strips a trailing `:` from the candidate before comparing, so `spec:` is rejected as equal and `spec-:` is rejected as the `spec-request` / `spec-proposal` prefix. Each reject branch has a fixture.

## D6 — Numbering (FR-009, FR-010)

**Decision**: Replace the inline scan in `intake.yml` ("Allocate feature number") with `project-name.sh next-number <P>`:

- Scan `P/specs/[0-9][0-9][0-9]-*` (root: `specs/…`).
- `git ls-remote --heads origin` filtered by anchored full refnames: `refs/heads/<prefix>P/<NNN-slug>` for the spec-draft and spec prefixes.
- For the root, count only refs whose remainder after the prefix has no `/`.

Take the highest `NNN` and add 1. The target project's own `specs/` is always included (FR-010). The root path is the old code path in effect and reproduces today's numbers.

**Rationale**: Anchoring prevents nested and sibling projects' refs from counting.

## D7 — Label-first creation and slug budget (FR-014)

**Decision**: When routing is on and `P` is non-empty, a deterministic step computes `budget = 44 − len(P)`. It passes the budget to the intake agent in the prompt and checks the resulting slug length after the agent writes the spec directory. It creates the `spec:P/<NNN-slug>` label before any branch is pushed, and fails loudly on overflow. Routing-off and root lifecycles skip this (FR-016).

**Assumption**: the current intake lets the agent pick the slug and creates the label after the branch. Implement must read `intake.yml` around lines 900–1000 to find the exact insertion point; the design requires only that label creation precede the first branch push.

## D8 — Re-run refusal and concurrency (FR-003, FR-012)

**Decision**: With routing on, intake refuses if the issue already carries any `spec:` label, whether or not it carries a `node:` label. Concurrency becomes:

- Per-numbering group: `wing-commander-intake` (root) or `wing-commander-intake/P`.
- Per-issue group: `wing-commander-intake-issue/<issue-number>`, applied only when routing is on.

GitHub concurrency allows one group per job, so intake is split. A small **gate job** holds the per-issue group (`cancel-in-progress: false`) and the refusal check. The existing numbering-group job `needs:` it.

**Rationale**: Two intakes for the same issue routed to different projects sit in different numbering groups. Only a shared per-issue group can serialize them, and the refusal check must run inside it so the second sees the first's `spec:` label.

**Alternative**: A single group keyed on issue (rejected: loses per-project parallelism and breaks root numbering serialization).

**Assumption**: the dispatching wrapper passes `issue-number` as an input usable in a reusable workflow's job-level `concurrency.group`. Intake already reads it. Implement should confirm the expression is available at job level.

## D9 — Working directory for agents (FR-006)

**Decision**: Agent steps run with `working-directory: ${{ steps.project.outputs.project || '.' }}` if `claude-code-action` supports it. Otherwise Spec Kit's own project-root override (an environment variable honoured by the vendored scripts, per the spec's Assumptions) is set, and every path in the prompt and allowed-tools list is project-relative.

**Assumption**: whether `claude-code-action` honours a working directory, and which of the parent `CLAUDE.md` or settings files it loads, must be confirmed in implement task 1 (spec Assumptions, last bullet of "Agent instruction files"). The adoption guide documents the parent-file reach either way (FR-018).

**T001 outcome (implement)**: A step-level `working-directory:` is a property of `run:` steps only; a `uses:` step such as `anthropics/claude-code-action@v1` cannot take one, so the first option is not available. The stages therefore take the fallback: the agent starts at the workspace root, `SPECIFY_INIT_DIR` is set to `<workspace>/P` (the vendored `.specify/scripts/bash/common.sh` resolves `.specify/` and `specs/` under it and refuses a folder without `.specify/`), and `SPECIFY_FEATURE_DIRECTORY` is passed absolute, because those scripts resolve a relative one under `SPECIFY_INIT_DIR` (a repository-relative `P/specs/...` would become `P/P/specs/...`). Prompts name the project's own skill files and scripts (`P/.claude/skills/...`, `bash P/.specify/scripts/...`), `wing-commander-tool-args` grants the `P/.specify/` script twins and workspace-absolute twins of the trusted-checkout and repository-tooling grants (D10), and the containment guard (D11) holds every change inside `P/`. Because the agent starts at the root, the root `CLAUDE.md` and `.claude/settings` are the ones it loads at start; a `P/CLAUDE.md` is read only when the agent reads files under `P/`. This is the parent-file reach the adoption guide describes.

**Implement-stage result (T001)**: The implement runner has no network or documentation access, so whether `claude-code-action` honours a step `working-directory` could not be confirmed. No workflow in this repository passes one to that action (the only `working-directory:` uses are on `run:` steps and `wing-commander-fold-evidence`). The fallback is therefore the decision: the vendored Spec Kit scripts honour `SPECIFY_INIT_DIR` (`.specify/scripts/bash/common.sh`, which validates a `.specify/` directory at that path), so agent steps set `SPECIFY_INIT_DIR` to the project folder and every path in a prompt or allowed-tools entry is written repository-relative (`P/specs/NNN-slug/...`). A later run can switch to `working-directory` without changing the names anything else reads. Which parent `CLAUDE.md`/settings files the action loads from a subfolder is likewise unconfirmed; docs/adoption.md (T055) states the conservative reading, that parent instruction files may reach the agent.

**D7 insertion point (T002)**: In `intake.yml` the agent itself creates the spec directory, the branch (step 5) and the `spec:` label (step 7), so label-first creation is a prompt reorder, backed by a deterministic check: step 7's `gh label create` moves ahead of step 5's branch push when routing is on, and the post-agent "Resolve created spec" step verifies the slug against the budget.

**D8 job-level expression (T003)**: The `inputs` context is available in `jobs.<id>.concurrency` of a reusable workflow, so `wing-commander-intake-issue/${{ inputs.issue-number }}` is valid at job level.

**Agent-step inventory (T004)**: `uses: anthropics/claude-code-action` occurs in `intake`, `clarify`, `plan` (2), `tasks` (2), `implement` (3), `finalize`, `rebase`, `cleanup`, `pr-conversation` (2) and `watchdog` (2) among the stage workflows; the board, release, auto-update and lifecycle-review workflows also use it but operate on the repository, not a project. Root-only patterns to convert live in those stage workflows' prompts and allowed-tools (`specs/` scans, `.specify/`, constitution reads, `.claude/skills/speckit-*`, `.wing-commander-pipeline/`) and in the composites `wing-commander-tool-args`, `-preflight`, `-write-boundary`, `-context`, `-spec-meta` and the fold-queue actions; the single-home gate (Gate 159) lists the converted files.

## D10 — Trusted checkout and repository tooling references (FR-025)

**Decision**: Every grant, prompt line and script invocation naming `.wing-commander-pipeline/` or `.github/scripts/…` becomes an absolute path under `${GITHUB_WORKSPACE}` (computed once in `wing-commander-tool-args`, the single home for grants). A new check, run in the existing pipeline-checkout guard (`pipeline-checkout-guard.sh`), refuses a branch whose tracked files include `**/.wing-commander-pipeline/**` at any depth, using `git ls-files`.

Adopter `extra-allowed-tools` entries are not rewritten. The adoption guide notes that repository-level paths there resolve to the workspace root.

## D11 — Containment (FR-021, FR-022)

**Decision**: Two layers.

1. **Deny list.** `wing-commander-tool-args` derives from `P` the Edit/Write denies: root `.claude/`, repo `.git/`, each enclosing `E/.claude/` for every proper ancestor `E` of `P`, `P/.claude/`, and `P/**/.claude/` for nested projects. They are appended to the single `no-write-paths` definition (spec 090) so they hold under the default and under any override. Every Edit/Write agent consumes `tool-args`, so none needs separate wiring; a gate lists the agents and asserts each consumes it.
2. **Confinement guard.** New composite `wing-commander-containment` runs after each Edit/Write agent. It lists files changed relative to the pre-agent SHA (already recorded as `pre-agent` in intake and equivalent steps) and fails the stage if any path lies outside `P/`. Whole-folder operations and parent-index edits inside `P` pass, because they are inside. Runner-temp files are outside the checkout and are not in the diff.

**Rationale**: Per-tool path allow-lists cannot express "only `P`" for Bash writes. A post-hoc diff is deterministic and cannot be argued around. The deny list protects the control surface *during* the run.

**Alternatives**: Allow-list only `P/**` for Edit/Write (rejected: Bash writes bypass it and it fights the spec's no-write-paths single definition). Diff guard only (rejected: leaves the control surface writable mid-run).

## D12 — Constitution amendment (FR-024)

**Decision**: A separate PR on its own branch, human-merged and landing on `main` no later than the lifecycle PR (spec 110 FR-003 pattern). It changes Principle VI's artifact list, Principle V's `.claude/` deny scope, and the two Operational Constraints bullets. It bumps 2.4.0 → 2.5.0, and its Sync Impact Report is moved to the top of `constitution-history.md` in the same commit. The lifecycle PR must not carry it. A gate keeps the lifecycle PR from reaching `main` first, if the constitution-merge gate family has a hook for it; otherwise it is an ordering note on the lifecycle issue.

## D13 — Watchdog, fold-cycle guard, spec-collision (FR-013, FR-019)

**Decision**: Both read the project by calling the shared parser on the branch, label, slug or spec-dir names they already parse. The watchdog's spec-collision collector scopes its scan to `P/specs/` for the inspected lifecycle's `P`. Neither reads per-call wrapper inputs for the project. Defaults that ignore the project (for example a hard-coded `specs/` glob) are removed and covered by FR-020's gate.

## D14 — spec-meta and the self-identity check (FR-008)

**Decision**: `spec-meta.json` keeps `spec_dir = specs/<NNN-slug>` (project-relative). `read-spec-meta.sh` is called with the repository-relative spec directory to locate the file and requires the recorded `spec_dir` to be exactly the project-relative form; a record carrying any project path fails. `spec_branch` is the real branch and is never required to resolve. Existing root records pass unchanged.

## D15 — Preflight (FR-005)

**Decision**: Preflight receives the `project` output and `cd`s the checks into it: `.specify/`, `.claude/skills/speckit-*`, constitution, real-entry rules, and `.specify/init-options.json` for version drift. Its failure messages name the folder and the missing piece.

## D16 — Gates (FR-019, FR-020)

**Decision**: New gates are `verify-*.py`, each with checked-in accept and reject fixtures, registered through `lint-workflows.yml` so `run-local-gates.py` picks them up.

| Gate | Covers |
|---|---|
| `verify-project-path-grammar.py` | FR-002, FR-005, FR-023 prefix, label budget |
| `verify-project-name-parser.py` | FR-013 each name type, FR-007 spec-dir accept and reject |
| `verify-project-single-home.py` | FR-020: root-only spec-dir patterns, `.specify` or constitution paths, `specs/` scans, root skill paths; a fixture per rejected pattern |
| `verify-intake-routing.py` | label count, re-run refusal pair, two-intake race (modelled with a fake `gh`), label-first order |
| `verify-project-numbering.py` | FR-009, FR-010, per-project spec-collision scope |
| `verify-subfolder-containment.py` | FR-021 and FR-022 including the `P=a/b` write to `a/.claude/` denied |
| `verify-pipeline-checkout-containment.py` | FR-025 grants and tracked `P/.wing-commander-pipeline/` refusal |
| spec-meta self-identity (extend the existing gate if present) | FR-008 including copy-out |

Gate numbers are assigned by the tasks stage from the next free ones in `run-local-gates.py`.

## D17 — Adoption guide (FR-018)

**Decision**: A new "Multiple projects in one repository" section in `docs/adoption.md` covering FR-018 (a)–(d), the parent-instruction-file note, and the `extra-allowed-tools` workspace-root note. Existing root-level instructions stay valid.

## Decisions made without clarification

Spec had no unresolved markers. The planning-level choices above that the spec explicitly delegated: containment mechanism (D11), deny-list delivery (D11), amendment mechanics (D12), and pipeline-checkout handling (D10). Assumptions to verify early in implement: D7 insertion point, D8 job-level expression, D9 working-directory support.
