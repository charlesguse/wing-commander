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
| `shell-commands` | Prose rendering of the `Bash(...)` entries in `allowed-tools`, unwrapped to the bare command prefixes they authorize and comma-joined as backticked text — for a prompt to state its own shell tooling from the list that is actually enforced, instead of a hand-maintained copy. Non-`Bash` entries (`Read`, `Grep`, `Skill`, …) are omitted: they are tools, not shell commands. Added after this feature shipped, by the change that made `implement.yml`'s tooling paragraph derive; **specified retroactively in `specs/037-rendered-tooling-list/`**, which is also where its known divergences are being fixed — see the caveats below. |

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
4. **Render `shell-commands`** from `effective_allowed`: keep the
   `Bash(<cmd>)` entries, strip the wrapper and a trailing `:*` or ` *`
   (matcher syntax, not part of the command), and join the survivors as
   backticked text.

   **Caveats as shipped.** This render post-dates the feature and does not
   yet meet the contract `specs/037-rendered-tooling-list/` sets for it.
   Four divergences are known, all latent against the tool lists this
   repository and its published stages actually use — none is reachable
   without consumer configuration that no caller supplies today:

   - It walks `effective_allowed` only, so an entry that `effective_disallowed`
     denies is still rendered as permitted. Deliberate at the composition
     layer — see the `effective_disallowed` formula above and quickstart's
     User Story 2 Acceptance #2, where an allowed list that still names a
     separately-denied tool is the *specified* outcome, resolved downstream
     by the engine's deny-precedence. It is only a defect in the render,
     which states that list as if it were the enforced set (037 FR-002).
   - A bare `Bash` grant (unrestricted shell — legal, and the most
     permissive grant a consumer can give) renders as nothing, which reads
     as the most restrictive (037 FR-005).
   - `Bash(git status)` (exact) and `Bash(git status:*)` (prefix) both
     render as `git status`, advertising arguments the exact form denies;
     granting both renders the command twice, since dedupe happens before
     the unwrap (037 FR-004, FR-007).
   - An `effective_allowed` with no `Bash(...)` entry renders empty. The
     agent-step guard is `allowed-tools != ''`, which such a list passes,
     so the empty render reaches the model (037 FR-006, FR-008, FR-016).

   Callers must not read `shell-commands` as the enforced set. `allowed-tools`
   and `disallowed-tools` are the enforcement surface; this output is prose
   derived from one of them.
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
