# Contract: Containment and the trusted pipeline checkout

Live contract.

## Write denies (FR-022)

For a subfolder lifecycle in project `P`, `wing-commander-tool-args` adds to the single `no-write-paths` definition, for every agent holding `Edit`/`Write`:

| Pattern | Purpose |
|---|---|
| `.claude/**` | root control surface |
| `.git/**` | repository metadata |
| `.wing-commander-pipeline/**` | the trusted pipeline checkout, whose composites and helpers run after the agent |
| `E/.claude/**` for each proper ancestor `E` of `P` | enclosing projects (for `P = a/b`: `a/.claude/**`) |
| `P/.claude/**` | the project's own control surface |
| `P/**/.claude/**` | nested projects |

The denies hold under the default `no-write-paths` and under any override, whatever the agent's working directory. Root lifecycles keep today's semantics.

Agents covered on main: intake, clarify, plan, tasks, implement, rebase, finalize, cleanup, pr-conversation `act` and `act.fold`. A gate enumerates every `claude-code-action` step with `Edit` or `Write` in its grants and asserts it consumes `tool-args`.

For the same lifecycles `wing-commander-tool-args` also denies, whatever the overrides or extra grants:

| Tool | Why |
|---|---|
| `Bash(git push --no-verify:*)` | the plain form of a push that skips the pre-push hook (`git push -n` is a dry run and stays allowed) |
| `Bash(gh api:*)` | the raw API writes repository contents outside `P` with no commit the guard or the hook sees |

A caller may add its own subfolder-only denies through `project-deny-tools`, placed the same way. Intake passes `Bash(git push:*)`, so a routed intake agent cannot push at all: "Label first" and "Publish stranded commits (post-agent)" make the branch's one push, after its label exists (FR-014).

## Confinement guard (FR-021)

Before each agent that pushes itself, `wing-commander-containment` (mode `install-pre-push`) installs a pre-push hook that refuses a push carrying a change outside `P/` (intake's hook is the label-first check instead).

**What the pre-push hook guarantees: nothing.** It is advisory, an early stop that saves a wasted push. The agent can repoint `core.hooksPath`, pass `--no-verify` in a form the deny list does not match, or overwrite the hook's helper copies under `$RUNNER_TEMP` with a git command that writes a file (`git diff --output=<path>`, `git log --output=<path>`). A push the hook refuses was refused; a push it allowed proves nothing.

**Where containment is enforced:** the post-agent `check` mode below. The agent can write `.wing-commander-pipeline/` (`git diff --output=<path>`), so directly after every agent step in a subfolder-capable job, and before any step runs code from that checkout, the job deletes it (`rm -rf -- .wing-commander-pipeline`) and checks the pipeline out again at the job's pinned ref (`steps.pipeline-ref.outputs.ref`), gated on a non-empty project (MF-46; `verify-subfolder-containment.py` asserts the pair precedes the first such step). What that guarantees, and no more: the files it restores (the check, label-first, publish-stranded and hardened-push composites and their helpers) are as published at that ref, not as the agent left them. It does not restore the job's environment: a variable or `PATH` entry the agent added through the runner's file commands still reaches those steps (see the residual gaps below). The check runs under the hardened git environment (`wc_harden_git_env`: hooks, fsmonitor and global config off; `GIT_NO_REPLACE_OBJECTS=1`), with the helper copies `install-pre-push` took before the agent ran (its `helpers-dir` output: a fresh, randomly named, read-only directory) rather than the workspace's `.wing-commander-pipeline/`. When it fails, the stage fails, and every "Publish stranded commits (post-agent)" step is gated on `steps.<containment>.outcome != 'failure'`, so the rescue never publishes what the check refused. A push the agent already made is not undone: the branch carries the violation, and every later stage's check (which diffs from the default branch's merge base) fails until it is removed.

After each Edit/Write agent the same composite (mode `check`):

- Input: the pre-agent SHA, `P`, the default branch the job resolved (`default-branch`; empty means `git ls-remote --symref origin HEAD`) and the pre-agent helper copies (`helpers-dir`; empty means the pipeline checkout's `_shared/`).
- Resolves the default branch's tip from the remote itself (`containment.sh trusted-base`: `git ls-remote origin refs/heads/<default>`, fetched when the checkout lacks it), never from `origin/<default>` or `--not --remotes`, both refs the agent can rewrite. A branch or tip that cannot be resolved fails the check.
- Computes `git diff --name-only --no-renames` from the pre-agent SHA and from the merge base of that tip and `HEAD`, plus the working-tree status and the untracked files (the root trusted checkout excluded). The pre-push hook uses the same base: every commit since `merge-base(<trusted tip>, <local sha>)`, so content already on another remote branch that arrives through a merge or a reset is still checked.
- With `helpers-dir` set (a job whose agent pushes itself), also compares the remote's branch heads with the snapshot `install-pre-push` took before the agent (`remote-heads.before`) and runs the pre-push test, from the trusted tip, over every branch created or moved whose new tip is reachable from `HEAD`, from a local `refs/heads/*` or from `HEAD`'s reflog, so a push to another branch is caught. A fetch writes only `refs/remotes/*`, so a branch another lifecycle's concurrent run moved is left alone even when the agent ran `git fetch origin` and holds its commits. Each agent step's check compares with a snapshot taken directly before that agent (implement's retry takes its own, MF-55), so nothing moved before the agent ran is charged to it. Offending branches are named; a missing snapshot fails the check.
- Passes when every path starts with `P/`. Whole-folder operations (moves or deletions of nested project folders) and edits to a child-project index README all start with `P/`, so they pass.
- Fails the stage with a callout listing the offending paths. The lifecycle PR is not advanced.
- Skipped for root lifecycles.
- Runner-temp files outside the checkout are not in the diff.

Accepted residual gaps:

- `origin`'s URL comes from the repository's own `.git/config`, which the environment cannot neutralise (see `_shared/git-push-hardening.sh`), so an agent that rewrites it can steer `ls-remote` to another remote.
- The read-only helper copies and the heads snapshot under `$RUNNER_TEMP` stop a non-root writer only; an agent that rewrites them in place before the check runs can weaken it.
- The re-checkout covers pipeline code that runs after the agent; it does not stop the agent writing the checkout while it runs, and a root lifecycle gets no re-checkout.
- The other-branch leg covers `refs/heads/*` only (not tags), ignores deletions, and skips a moved branch whose tip is not reachable from `HEAD`, a local branch or `HEAD`'s reflog: an agent that pushes a commit and then drops every local trace of it (deletes the branch, expires the reflog, or pushes a commit it only fetched) escapes this leg.
- A push the agent already made is not undone; the failed check stops the stage, not the push.
- The runner's file-command files are writable by the agent (spec 095 FR-008). With the granted `git log --output=<path>` / `git diff --output=<path>`, a subfolder agent can write its own step's `$GITHUB_ENV` and `$GITHUB_PATH` files under `$RUNNER_TEMP/_runner_file_commands`. A `BASH_ENV`, `PATH` or `LD_PRELOAD` set that way reaches every later step in the job, including the re-checkout, the check and the publish push, so it can subvert all three. No cheap, contained mitigation exists today: the re-checkout restores files, not the environment.

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
