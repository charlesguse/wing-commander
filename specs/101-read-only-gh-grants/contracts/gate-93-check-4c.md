# Contract: Gate 93 check 4b, the `gh` rule

Subject: `.github/scripts/verify-issue-context-single-home.py`. Despite the
file name, the rule extends check 4b and adds no gate number.

## Rule

For every read-only agent step in every `.github/workflows/*.yml` except
`board-loop.yml` (check 4 already holds it to the strict list), fail when any
shipped allowed entry authorizes `gh`:

- first token's basename is `gh`, with any wildcard spelling (`gh:*`, `gh*`,
  `gh *`, `gh api:*`, `gh pr view:*`) or path-qualified (`/usr/bin/gh ...`);
- bare `Bash` or `Bash(*)` (already reported; message unchanged).

Match by whitespace-split token, not substring. Routes read: tool-args
`default-allowed-tools`, `extra-allowed-tools`, `allowed-tools-override`, and
inline `claude_args --allowedTools`. `${{ inputs.* }}` values are not read:
the rule binds this repository's shipped defaults only (spec FR-014), and the
check's docstring says so.

## Failure message (required content)

Names the workflow, step, the offending grant, that `gh` reaches remote writes,
local file writes and (via `gh alias set` / `gh extension install`) arbitrary
execution, and the route to take: stage what the agent needs as a file in a
deterministic step. It points at `docs/agent-friendly-workflows.md` for the
rationale rather than restating it.

## Loud-failure cases

- A label in `FLEET_READ_ONLY_STEP_LABELS` with no matching site: fails.
- Zero read-only sites discovered across the fleet: fails.
- A stale or over-broad exemption (see data-model.md): fails.

## Fixtures (each failure branch needs one)

1. tool-args site granting `Bash(gh:*)`;
2. tool-args site granting a subcommand (`Bash(gh api:*)`);
3. step appending a `gh` grant in its own `claude_args`;
4. inline-only agent step (no tool-args site) granting `Bash(gh api:*)`;
5. path-qualified `Bash(/usr/bin/gh pr view:*)`;
6. forwarded `${{ inputs.extra-allowed-tools }}` containing `gh`: passes;
7. exempt site with an extra, unlisted `gh` grant: fails;
8. exempt site with no `gh` grant: fails (stale);
9. zero read-only sites: fails.

The existing fixture `_inline_fixture` default (`Bash(gh api:*)`, "gh left
alone") and the 4b "gh left alone" case must be updated, since they encode the
old behaviour.

## Mutations (self-test)

Restore `Bash(gh:*)` in watchdog.yml's `watchdog.diagnose` site and
`Bash(gh api:*)` in auto-update-spec-kit.yml's inline list on a copy of the
real file; the gate must fail on each.

## Registration

Unchanged: already invoked by `lint-workflows.yml` (check and `--self-test`)
and reachable through the gate registry and `run-local-gates.py`.
