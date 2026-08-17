# Contract: `wing-commander-tool-args` Composite Action (implementer-facing)

**Feature**: 026-configurable-tool-lists

Draft contract for the new shared composite action introduced by this
feature (research.md D1), to live at
`.github/actions/wing-commander-tool-args/action.yml` alongside the
existing `wing-commander-preflight`, `wing-commander-context`, etc. This
document is the internal contract between each stage workflow and the
composition logic — not consumer-facing (consumers see
`tool-list-inputs.md` only).

## Purpose

Given one agent step's hard-coded default tool lists and a stage's
consumer-supplied append/override inputs (D2), produce the composed,
ready-to-splice `--allowedTools`/`--disallowedTools` values, or fail the
run with a clear error if the inputs conflict (FR-010).

## Inputs

| Input | Required | Notes |
|---|---|---|
| `default-allowed-tools` | yes | The step's existing hard-coded allowed list (literal, unchanged from today's inline value). |
| `default-disallowed-tools` | yes | The step's existing hard-coded disallowed list. |
| `extra-allowed-tools` | no (default `""`) | Passthrough of the stage's `extra-allowed-tools` workflow_call input. |
| `extra-disallowed-tools` | no (default `""`) | Passthrough of the stage's `extra-disallowed-tools` workflow_call input. |
| `allowed-tools-override` | no (default `__unset__`) | Passthrough of the stage's `allowed-tools-override` workflow_call input. |
| `disallowed-tools-override` | no (default `__unset__`) | Passthrough of the stage's `disallowed-tools-override` workflow_call input. |
| `step-label` | yes | Human-readable identifier for error messages, e.g. `implement.cycle`, `watchdog.diagnose` — lets one stage with multiple internal steps (D5) produce an error naming the specific step. |

## Outputs

| Output | Notes |
|---|---|
| `allowed-tools` | Composed, deduplicated, comma-joined effective allowed list — the exact value to splice into that step's `claude_args:` after `--allowedTools`. |
| `disallowed-tools` | Composed, deduplicated, comma-joined effective disallowed list — spliced after `--disallowedTools`. |
| `shell-commands` | A complete, grammatical sentence stating exactly which shell commands this run permits — derived from `allowed-tools` after subtracting anything `disallowed-tools` fully covers, distinguishing an unrestricted grant, a command grant with any arguments, and an exact-command-only grant. Non-`Bash` entries (`Read`, `Grep`, `Skill`, …) are omitted: they are tools, not shell commands. Added after this feature shipped, by the change that made `implement.yml`'s tooling paragraph derive; the render contract is `specs/037-rendered-tooling-list/contracts/tooling-statement-render.md` — see the guarantees below. |

## Behavior

1. **Validate (FR-010)**: for each direction independently, if the `extra-*`
   input is non-empty *and* the corresponding `*-override` input is not the
   `__unset__` sentinel, fail: `::error::` + `GITHUB_STEP_SUMMARY` line
   naming `step-label`, the direction, and both supplied values. Exit
   non-zero — the calling job's agent step never runs (same fail-fast
   position as `wing-commander-preflight`, i.e. before credentials are
   exercised).
2. **Compose** each direction per research.md D4:
   - `effective_allowed = override-allowed if provided else (default-allowed ∪ extra-allowed)`
   - `effective_disallowed = (override-disallowed if provided else (default-disallowed ∪ extra-disallowed)) − explicit_allow`
     where `explicit_allow` is `extra-allowed` (append mode) or the full
     `allowed-tools-override` list (override mode) — never
     `default-allowed-tools`.
3. **Deduplicate and join**: split each composed set on `,`, trim
   whitespace, drop exact-duplicate entries (edge case: same tool named
   twice collapses to one), rejoin with `,` preserving first-seen order for
   determinism (stable, reviewable `GITHUB_STEP_SUMMARY`/log output).
4. **Render `shell-commands`** from `effective_allowed` and
   `effective_disallowed` together, per
   `specs/037-rendered-tooling-list/contracts/tooling-statement-render.md`:
   classify every entry as unrestricted (bare `Bash`), a command prefix
   (`Bash(cmd:*)`/`Bash(cmd *)`, any arguments), an exact command
   (`Bash(cmd)`, that literal invocation only), or not a shell grant at all
   (any other tool entry — excluded from this render); subtract an allow
   grant only when a disallowed grant for the same command (or, for an
   unrestricted allow, any disallowed grant at all) fully covers its scope;
   group surviving grants by command, stating the broader form once; and
   emit one of four complete sentences chosen by the result.

   **Guarantees.**

   - Subtraction runs against `effective_disallowed`, not `effective_allowed`
     alone — an entry `effective_disallowed` fully covers never reads as
     permitted in the statement (037 FR-002, FR-003). `effective_allowed`/
     `effective_disallowed` themselves are never rewritten by this step; the
     render is a pure read of the already-composed lists.
   - A bare `Bash` grant (unrestricted shell — legal, and the most
     permissive grant a consumer can give) renders as `` This run permits
     any shell command. ``, or, under a partial deny, `` This run permits
     any shell command except: `cmd`. `` — never as nothing (037 FR-005).
   - `Bash(git status)` (exact) and `Bash(git status:*)` (prefix) granted
     together render once, as `` `git status` `` (the broader, prefix
     form); an exact-only grant renders with an
     `` (exact command only) `` qualifier so it is never confused with the
     any-arguments form (037 FR-004, FR-007).
   - An `effective_allowed` with no surviving `Bash`/`Bash(...)` grant
     renders `` This run permits no shell command. `` as a complete
     sentence — never an empty string or dangling fragment, even though the
     agent-step guard (`allowed-tools != ''`) still lets such a list reach
     the model when other, non-shell tools remain granted (037 FR-006,
     FR-008, FR-016).

   Callers must not read `shell-commands` as the enforced set. `allowed-tools`
   and `disallowed-tools` are the enforcement surface; this output is prose
   derived from both of them, after the fact.
5. **Emit outputs** via `$GITHUB_OUTPUT`, consistent with existing
   composite actions' output style (e.g. `wing-commander-context`).
6. **Never reached on validation failure** — steps 2–5 only run once step 1
   passes for both directions.

## Call-site shape (one call per internal agent step)

Each stage's job calls this composite action once per internal agent step,
immediately before that step, reusing the *same* stage-level `extra-*`/
`*-override` `workflow_call` inputs across all calls but each call's own
`default-*` values and `step-label` (D5). Example shape for `implement.yml`
(three internal steps → three calls):

```yaml
- name: Compose tool args (cycle)
  id: tool-args-cycle
  uses: ./.github/actions/wing-commander-tool-args
  with:
    default-allowed-tools: "Skill,Read,Write,Edit,...,Bash(gh run list:*)"
    default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage"
    extra-allowed-tools: ${{ inputs.extra-allowed-tools }}
    extra-disallowed-tools: ${{ inputs.extra-disallowed-tools }}
    allowed-tools-override: ${{ inputs.allowed-tools-override }}
    disallowed-tools-override: ${{ inputs.disallowed-tools-override }}
    step-label: "implement.cycle"

- name: Implement and converge (cycle)
  if: steps.tool-args-cycle.outputs.allowed-tools != ''  # composition succeeded
  uses: anthropics/claude-code-action@v1
  with:
    claude_args: |
      --model ...
      --max-turns ...
      --allowedTools "${{ steps.tool-args-cycle.outputs.allowed-tools }}"
      --disallowedTools "${{ steps.tool-args-cycle.outputs.disallowed-tools }}"
```

(Exact `claude_args:` assembly/quoting is an implementation detail for the
implement stage of *this* feature — resolved at task-generation/
implementation time, not fixed by this plan.)

## Resolution and versioning

Resolved from the pipeline repository's own checkout at
`github.job_workflow_sha`, identically to every other shared composite
action referenced from a published stage workflow (see the header comment
convention in `wing-commander-preflight/action.yml`).
