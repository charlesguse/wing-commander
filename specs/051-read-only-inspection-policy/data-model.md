# Data Model: One read-only inspection policy for stage tool allowlists

This feature has no runtime data store — its "entities" are the documents,
table rows, and rendered strings the policy governs. This document names
each one's shape, where it lives, and what keeps it honest, so tasks.md can
be written against fixed structures rather than re-deriving them from the
spec's Key Entities prose.

## 1. Read-only inspection policy (the document)

| Field | Value |
|---|---|
| Location | `specs/010-reusable-pipeline/contracts/stage-interfaces.md`, new `## Read-only inspection policy` section, immediately before `## Per-stage default tool lists` (research.md D1) |
| Contents | (a) the seven-primitive inspection set; (b) the compound/pipe/redirect matching rule; (c) the read-capable-stage definition (research.md D2); (d) a pointer to the composite's rendered `shell-commands` output as where (b) reaches an agent; (e) a pointer to this feature's `contracts/inspection-policy.md` occurrence table |
| Consistency rule | Every other mention of this material (a stage prompt, a gate script's error message, a future spec) points at this section rather than restating it (FR-001) |
| Checked by | Gate 27's new inspection-set-completeness check (research.md D7) reads (a)+(c) indirectly, via the hand-authored primitive-set/read-capable-set constants it carries (Constitution IX: the judgment is in the gate's code, keyed to this document by convention, the same way `TABLE_DOC`/`COMPOSITE` already are) |

## 2. Per-stage default tool list (existing entity, extended)

Unchanged shape from specs/026/010: a row of
`(stage, step-label, default-allowed-tools, default-disallowed-tools)` in
the "Per-stage default tool lists" table, one-to-one with a
`wing-commander-tool-args` call site keyed by `step-label`.

**New attribute this feature adds to the concept** (not a new column — an
implicit property Gate 27 now computes): **read-capable** (boolean, per
research.md D2) — determines whether the inspection-set-completeness check
applies to that row, and whether an absent primitive must carry a recorded
exception.

**Rows this feature edits** (see plan.md Project Structure for the file list):

| step-label | Change |
|---|---|
| `intake` | + inspection set (7 primitives), + `Bash(printenv SPECIFY_FEATURE_DIRECTORY)` |
| `clarify` | + inspection set (7 primitives) |
| `plan.direct-commit` | + inspection set already present; − `Bash(gh auth status)` |
| `plan.pr` | same as `plan.direct-commit` (relative row — inherits both changes) |
| `tasks.direct-commit` | + inspection set already present; − `Bash(gh auth status)` |
| `tasks.pr` | same as `tasks.direct-commit` (relative row — inherits both changes) |
| `implement.cycle` | + inspection set (7 primitives), + `Bash(python .github/scripts/run-local-gates.py:*)` |
| `implement.retry` | same as `implement.cycle` plus its existing extras (relative row — inherits both changes) |

Rows explicitly **not** touched (research.md D2's "deliberately minimal"
set): `implement.post-progress-comment`, `finalize`, `cleanup`, `rebase`,
`watchdog.diagnose`, `pr-conversation.classify`, `pr-conversation.act`.

**Checked by**: Gate 27 (existing table-vs-call-site comparison, unchanged
mechanism; new completeness check per research.md D7).

## 3. Rendered tooling statement (existing entity, extended)

The `shell-commands` output of `wing-commander-tool-args`. Existing shape
unchanged (one of: "permits no shell command." / "permits any shell
command[, except: …]." / "permits these shell commands: …."). This feature
appends one static, configuration-independent sentence (research.md D3) to
every rendered value, including the empty case.

| Field | Value |
|---|---|
| Producer | `.github/actions/wing-commander-tool-args/action.yml`, `Compose tool args` step |
| Consumers | Every stage prompt that interpolates `steps.<id>.outputs.shell-commands` (`intake.yml`, `clarify.yml`, `plan.yml` ×2, `tasks.yml` ×2, `implement.yml` ×2) |
| New content | The compound/pipe/redirect rule + built-in-tools preference, exactly once, appended after the existing sentence |
| Checked by | Gate 21 — one new case asserting the appended sentence is present verbatim in every existing case's expected output; one new mutation removing it from the shipped script, asserted to turn every case red |

## 4. Repository guidance (existing entity, newly load-bearing)

`CLAUDE.md` (the "Before pushing" section) plus the affected stage prompts
(clarify, plan). This feature does not model guidance as a new structured
entity — it is prose — but two specific facts about it become
gate-checkable:

| Field | Value |
|---|---|
| Audience scoping | `CLAUDE.md`'s "Before pushing" section gains a leading sentence naming its audience as the implement stage agent and human/local sessions — not intake/clarify/plan/tasks (FR-009b) |
| Mandated-command set | The one command this section mandates for an agent (`python .github/scripts/run-local-gates.py`) is the input to Gate 27's new reconciliation check (research.md D7 item 2) — hand-authored as a `(command, [stages])` pair in the gate script itself, not parsed from `CLAUDE.md`'s prose |
| `gh api` route sentences | `clarify.yml` and `plan.yml`'s prompts each gain one sentence naming their sanctioned non-`gh api` route (FR-007) — clarify points at the already-staged `/tmp/wing-commander/clarification-answer.md` file (already produced by an existing deterministic step; only the prompt sentence is new — see research.md's clarify.yml read of lines 460-473/522-529), plan points at its own `gh pr view --json` grant |

**Checked by**: Gate 27's new reconciliation check (mandated-command set);
no automated check for the `gh api`-route sentences beyond the existing
prompt-review/human-diff review (SC-002's "verified mechanically" claim
covers the allowlist side, i.e. that `gh api` is genuinely absent from
clarify's and plan's composed lists — Gate 27's existing disallowed-list
comparison already proves that once `gh api` is confirmed absent from both
rows' `default-allowed-tools`).

## 5. Denied-tool occurrence (existing entity from #266, closed out)

| Field | Value |
|---|---|
| Identity | `(stage, run-id, denied command)`, as recorded in the spec's Overview table |
| New attribute | **disposition** — one of `permitted` (inspection-set/printenv grant), `routed` (gh api → sanctioned alternative), `gate-suite-scoped` (implement-only grant + CLAUDE.md scoping), `denied-on-purpose` (git stash) |
| Location of the mapping | `specs/051-read-only-inspection-policy/contracts/inspection-policy.md` (research.md D8) — a table with one row per occurrence, not a new column on the per-stage table (which has no per-occurrence granularity) |
| Consumed by | The #266-closing issue comment (SC-007) and SC-001's verification |
