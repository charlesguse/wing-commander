# Contract: Read-only inspection policy text and occurrence dispositions

This is the review copy of the policy text tasks.md will land in
`specs/010-reusable-pipeline/contracts/stage-interfaces.md` (research.md D1),
plus the occurrence-disposition table FR-016/SC-001/SC-007 require. The
shipped copy is the one in stage-interfaces.md; this file stops being read
once this feature merges (data-model.md item 5).

## Policy text (to land verbatim as stage-interfaces.md's new section)

```markdown
## Read-only inspection policy

Nine `denied-tool` occurrences on #266 shared one cause: no owner-level
statement of what a read-only inspection is allowed to look like, so every
new prompt instruction shipped a denial first and an allowlist patch second.
This section is that statement. Everything else — a stage prompt, a gate's
error message, a future spec — points here rather than restating it.

**The inspection primitive set.** Every read-capable stage's default
allowed list carries `Bash(grep:*)`, `Bash(head:*)`, `Bash(tail:*)`,
`Bash(sort:*)`, `Bash(uniq:*)`, `Bash(wc:*)`, `Bash(cut:*)` — the set
`plan.*`/`tasks.*` shipped first. A read-capable row that omits one records
why in its own table row rather than silently drifting from its peers.

**Compound, piped, and redirected commands.** Claude Code matches each
command in a `|`, `;`, or `&&` chain separately, so a pipe into an unlisted
primitive is denied even when every other command in the chain is allowed.
An output redirect (`>`, `>>`) or a `cd … &&` prefix is denied regardless of
list contents — these are their own shape, not the primitive that follows
them. No allowlist addition closes this family; the fix is telling the agent
to use the built-in Read/Grep/Glob tools, or a single command, for anything
multi-step. This guidance reaches every stage prompt as one appended
sentence in `wing-commander-tool-args`'s `shell-commands` output
(specs/037-rendered-tooling-list) — the same single home the permitted-
command list itself renders from, so it cannot drift per workflow.

**Read-capable stage, defined.** A stage's internal agent step is
read-capable if its job is open-ended repository exploration in service of
authoring or modifying an artifact: `intake`, `clarify`,
`plan.direct-commit`, `plan.pr`, `tasks.direct-commit`, `tasks.pr`,
`implement.cycle`, `implement.retry`. A step whose allowed list is a fixed,
narrow replay of a small command set regardless of run content is not
read-capable and is not widened by this policy:
`implement.post-progress-comment`, `finalize`, `cleanup`, `rebase`,
`watchdog.diagnose`, `pr-conversation.classify`.

**`gh api`.** No stage is granted `gh api` — it cannot be scoped to GET, and
clarify's and intake's token can write issues. Every read that once reached
for it has a sanctioned route named in that stage's own prompt: clarify's
issue-comment body is staged into the checkout by a deterministic workflow
step before the agent runs (matching specs/029-intake-issue-comments' existing
pattern for intake); plan's pull-request reads use its own `gh pr view --json`
grant. `watchdog.diagnose` reaches `gh api` today only through its
pre-existing, wider `Bash(gh:*)` grant — recorded here as pre-existing and
untouched by this policy, not a grant this policy makes.

**The gate suite.** `python .github/scripts/run-local-gates.py` is permitted
only for `implement.cycle`/`implement.retry`, run by a deterministic step
ahead of the agent step under an explicit timeout, preceded by a preflight
for its prerequisites (pyyaml, jq, actionlint) that degrades to a step-
summary note rather than a denial or a stage failure when one is missing.
`CLAUDE.md`'s "Before pushing" instruction to run it is scoped to that
audience plus human/local sessions.

Occurrence-by-occurrence disposition:
[specs/051-read-only-inspection-policy/contracts/inspection-policy.md](../../051-read-only-inspection-policy/contracts/inspection-policy.md).
```

## Occurrence disposition table (FR-016, SC-001, SC-007)

| # | Stage | Run(s) | Denied command | Disposition | Resolved by |
|---|---|---|---|---|---|
| 1 | plan | 32849659993 | `cd .github/workflows && for …` loop | denied-on-purpose (shape) + routed | Compound/redirect rule states this shape is denied whole; agent is told to use Grep/Glob instead |
| 2 | plan | 34160921063 (23 denials) | pipelines of allowed primitives (`grep … \| sort \| tail`, `ls … \| grep`) | permitted | Inspection primitive set already on `plan.*`; per-command chain matching now stated so the agent stops retrying the pipe form |
| 3 | plan | 34160921063 | `gh api repos/{owner}/{repo}/pulls/224` | routed | `gh pr view --json` sentence added to plan's prompt (FR-007) |
| 4 | plan | 34160921063 | `gh auth status` | denied-on-purpose | Grant removed (FR-013); prompt already states it would not have explained the denial anyway |
| 5 | plan | 34664853479 | `printenv SPECIFY_FEATURE_DIRECTORY` | permitted (already granted) | `plan.*` already carries this grant; occurrence predates it and needs no further change |
| 6 | intake | 34666884809 | `printenv SPECIFY_FEATURE_DIRECTORY` | permitted | Grant added (FR-011); prompt's export claim scoped away from intake (FR-012) |
| 7 | intake | 34799900127 | `python .github/scripts/run-local-gates.py` (×3) | gate-suite-scoped | `CLAUDE.md` no longer addresses intake with this instruction (FR-009b); intake's allowlist never gains this grant |
| 8 | clarify | 34791425104 | `gh issue view N --json comments --jq … > /tmp/q.md` (redirect) | denied-on-purpose (shape) + routed | Redirect rule states this shape is denied whole; clarify's prompt points at the already-staged answer file instead |
| 9 | clarify | 34802081261 | `gh api repos/<repo>/issues/comments/N --jq '.body'` | routed | Prompt sentence added naming the already-staged `/tmp/wing-commander/clarification-answer.md` file as the route (FR-007) — the deterministic staging step already exists (`clarify.yml`'s "Stage the answer as a data file") |
| 10 | implement | 34709026525 | `git stash; actionlint … ; git stash pop` (compound) | denied-on-purpose | Compound-chain rule states this shape is denied whole; `git stash`/`git stash pop` are not added to `implement.*`'s allowlist — stashing mid-run is not a sanctioned move for this agent |

Ten rows for nine occurrences: row 1 and row 2 both come from the
23-denial run 34160921063's plan occurrence as recorded in the spec's
Overview table, split here because the pipe-of-primitives shape (row 2,
almost all 23) and the `cd … && for …` loop shape (row 1) resolve
differently — one by the inspection set already being sufficient, the other
by the compound-command rule alone. Every occurrence has exactly one
disposition; SC-001's "zero occurrences left without a disposition" is
satisfied by this table having no blank cell in the Disposition column.
