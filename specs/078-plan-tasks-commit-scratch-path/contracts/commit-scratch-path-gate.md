# Contract: the FR-012 gate (`verify-commit-message-scratch-path.py`)

This is the User Story 3 backstop: a future prompt edit that drops the
scratch-path guidance, or adds a tenth commit-instructing prompt with none,
fails the PR-time gate suite by name rather than the next agent run. Gate
number is confirmed at implementation time (research.md D3); this contract
does not depend on the exact number.

## Registration

Two steps in `.github/workflows/lint-workflows.yml`, alongside the other
`verify-*.py` gates (e.g. next to `verify-stage-tool-lists.py` /
`verify-plan-tasks-cost-line.py`):

```yaml
- name: Gate NN - commit-message scratch path is named at every in-scope site
  run: python3 .github/scripts/verify-commit-message-scratch-path.py
- name: Gate NN self-test - commit-message scratch path
  run: python3 .github/scripts/verify-commit-message-scratch-path.py --self-test
```

`run-local-gates.py` needs no separate edit — its gate list is derived from
`lint-workflows.yml` via `wc_gate_registry.pr_time_invocations` (the same
mechanism that already picks up every other gate), so registering the two
steps above is sufficient (Constitution VIII: "reachable through the gate
registry").

## Inputs (what the gate reads)

- Every `.github/workflows/*.yml` file, YAML-parsed (never grepped, per
  Gate 7/23/51's stated rationale — a step in flow style or unusual
  indentation must not be silently missed).
- `.github/actions/wing-commander-commit-message-guidance/action.yml`'s
  shipped `run:` step, executed via `wc_shell_harness.run_step` to obtain
  the real rendered `guidance` string for the sites this gate deep-checks
  (FR-013's two `implement.yml` sites) — never a Python re-implementation of
  the render.

## Discovery (what counts as an in-scope site)

A step, in any job, in any `.github/workflows/*.yml` file, whose `prompt:`
value contains `git commit` (case-sensitive, matching the literal command
every one of the nine sites already issues). This is a dynamic scan, so a
future eleventh site is found automatically rather than requiring an edit to
a hand-maintained list.

## Pass condition, per discovered site

One of:

**(a) Covered.** A step in the same job, ordered before the discovered
step, invokes `./.github/actions/wing-commander-commit-message-guidance`
under some step id `X`; the discovered step's `prompt:` contains the
literal substring `steps.X.outputs.guidance`. (This proves consumption
without needing to know the rendered text for every site — only
`implement.yml`'s two sites get the deeper, render-executing check below,
since they are the ones FR-013 pins to specific content.)

**(b) Exempt.** `(os.path.basename(path), step_name)` is a literal entry in
this script's own `EXEMPT_SITES` constant.

A site satisfying neither fails, naming the workflow file, job, and step —
matching Gate 51's `::error file=...::Gate NN: job {job!r} step {step!r}:
{msg}` format.

## Deeper check: `implement.yml`'s two sites (FR-013)

For the `cycle` and `retry` steps specifically, the gate additionally:

1. Confirms each site's guidance-composing step passes
   `scratch-filename: implement-commit-message-cycle.txt` /
   `implement-commit-message-retry.txt` respectively (the two filenames
   #440 already shipped, unchanged).
2. Confirms the `retry` site's guidance-composing step sets `extra-note` to
   a non-empty value, and that the value, once rendered, still names "a
   name distinct from the cycle step's scratch file."
3. Executes the composite action's shipped `run:` step for both filenames
   (with and without the retry `extra-note`) and asserts the rendered
   `guidance` string is identical between the two calls except for the
   substituted filename and the trailing `extra-note` sentence — proving
   FR-009's "same meaning, same named forms" holds for this pair
   specifically, since they are the two sites most likely to accidentally
   diverge (research.md D2's reasoning for why they need distinct names in
   the first place).

## `EXEMPT_SITES`

A Python set of `(basename, step_name)` tuples, each with a comment stating
why that site's commit messages are always deterministic one-liners.
Ships empty (research.md D6, data-model.md's Exemption list entity) — no
current site qualifies. A future addition is a one-line diff to this
constant, auditable the same way Gate 51's two watchdog entries are.

## `--self-test`

Reintroduces, and asserts each one is caught:

1. A discovered site whose `prompt:` has the `steps.X.outputs.guidance`
   substring removed (simulates a future hand-edit dropping the render).
2. A discovered site whose preceding guidance-composing step is deleted
   from the job while the `prompt:` still references its output (simulates
   a step reordering/removal that orphans the reference).
3. An `EXEMPT_SITES` entry naming a `(basename, step_name)` pair that does
   not exist in any workflow (a stale exemption — proves the gate does not
   just trust the constant blindly for sites it can't find, matching Gate
   51's own stale-exemption self-test shape).
4. For `implement.yml`: the `cycle` site's `scratch-filename` changed to
   collide with `retry`'s (must fail — FR-006), and the `retry` site's
   `extra-note` blanked (must fail — FR-013).
5. Zero sites discovered at all (must fail loudly — Constitution VIII's "a
   gate that cannot reach its subject... MUST fail loudly rather than
   report a pass it did not earn," matching Gate 51's own zero-sites guard).

## Out of scope for this gate

- PR-body composition (`gh pr create --body`, `gh issue comment --body`) —
  explicitly Out of Scope in spec.md; this gate's `git commit` substring
  match does not fire on those steps at all.
- `finalize.yml` / `cleanup.yml` — their commits are fixed one-liners inside
  `run:` steps, not `prompt:` bodies, so they are never discovered by this
  gate's scan in the first place; they do not need an `EXEMPT_SITES` entry
  because they are never candidates.
