# Contract: Containment and the trusted pipeline checkout

Live contract.

## Write denies (FR-022)

For a subfolder lifecycle in project `P`, `wing-commander-tool-args` adds to the single `no-write-paths` definition, for every agent holding `Edit`/`Write`:

| Pattern | Purpose |
|---|---|
| `.claude/**` | root control surface |
| `.git/**` | repository metadata |
| `E/.claude/**` for each proper ancestor `E` of `P` | enclosing projects (for `P = a/b`: `a/.claude/**`) |
| `P/.claude/**` | the project's own control surface |
| `P/**/.claude/**` | nested projects |

The denies hold under the default `no-write-paths` and under any override, whatever the agent's working directory. Root lifecycles keep today's semantics.

Agents covered on main: intake, clarify, plan, tasks, implement, rebase, finalize, cleanup, pr-conversation `act` and `act.fold`. A gate enumerates every `claude-code-action` step with `Edit` or `Write` in its grants and asserts it consumes `tool-args`.

For the same lifecycles `wing-commander-tool-args` also denies, whatever the overrides or extra grants:

| Tool | Why |
|---|---|
| `Bash(git push --no-verify:*)`, `Bash(git push -n:*)` | a push that skips the pre-push hook |
| `Bash(gh api:*)` | the raw API writes repository contents outside `P` with no commit the guard or the hook sees |

## Confinement guard (FR-021)

Before each agent that pushes itself, `wing-commander-containment` (mode `install-pre-push`) installs a pre-push hook that refuses a push carrying a change outside `P/` (intake's hook is the label-first check instead). After each Edit/Write agent the same composite (mode `check`):

- Input: the pre-agent SHA and `P`.
- Computes `git diff --name-only --no-renames` from the pre-agent SHA and from the default branch's merge base to `HEAD`, plus the working-tree status and the untracked files (the root trusted checkout excluded).
- Passes when every path starts with `P/`. Whole-folder operations (moves or deletions of nested project folders) and edits to a child-project index README all start with `P/`, so they pass.
- Fails the stage with a callout listing the offending paths. The lifecycle PR is not advanced.
- Skipped for root lifecycles.
- Runner-temp files outside the checkout are not in the diff.

## Trusted checkout references (FR-025)

| Reference | Required form |
|---|---|
| Agent grants to `.wing-commander-pipeline/.github/scripts/git_read.py` | Absolute path under `${GITHUB_WORKSPACE}` |
| Prompt text and script invocations naming the trusted checkout | Absolute path under `${GITHUB_WORKSPACE}` |
| Repository tooling in default or adopter grants (`.github/scripts/run-local-gates.py`) | Resolves to the workspace root under working directory `P` |
| Tracked files matching `**/.wing-commander-pipeline/**` on a branch | Refused by the pipeline-checkout guard |

`extra-allowed-tools` entries are adopter-supplied and not rewritten. The adoption guide notes workspace-root resolution.

## Fixtures required (FR-019)

- Read-only agent grant under working directory `P` still names the workspace-root checkout.
- A branch tracking `P/.wing-commander-pipeline/x` is refused.
- With `P = a/b`, an Edit to `a/.claude/settings.json` is denied.
- A change outside `P` fails the guard; a change inside `P` that moves a nested folder passes.
- The deny set holds with `no-write-paths` overridden.
