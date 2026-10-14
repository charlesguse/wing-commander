# Contract: Routing input and intake behaviour

Live contract.

## Published interface delta (additive, FR-017)

| Workflow | Change |
|---|---|
| `intake.yml` | New optional input `routing-label-prefix`, type string, default `''`. Description states the empty default turns routing off. No existing input, secret or output is removed or renamed. |
| other stage workflows | No new inputs. They take `P` from the identity they already receive (branch, label, slug, `spec_dir`). |

The `spec-dir` output of intake carries the repository-relative form. For the root this is identical to today's.

## Intake decision table

| Routing prefix | `node:` labels | `spec:` label already on issue | Result |
|---|---|---|---|
| empty | any | any | Today's behaviour exactly. No refusal, no label-first creation, no slug-budget check. |
| invalid | any | any | Fail loudly (FR-023). |
| set | 0 | no | Root lifecycle, today's names, groups and numbering, plus the per-issue intake group. |
| set | 1 | no | Validate `P`, then subfolder lifecycle. |
| set | ≥ 2 | no | Refuse with callout. Nothing created. |
| set | any | yes | Refuse with callout. |

All label reads use `gh issue view <issue-number> --json labels`, live, never the event payload or body.

## Order of operations when routing is set and `P` is non-empty

1. Take the per-issue concurrency group (gate job).
2. Validate the prefix.
3. Count labels; validate `P` and its folder on the default branch.
4. Refuse if the issue already has a `spec:` label.
5. Allocate the number from `P` (`project-name.sh next-number`).
6. Compute and pass the slug budget to the agent.
7. Agent runs with working directory `P`.
8. Check the slug against the budget.
9. Create the `spec:P/<NNN-slug>` label.
10. Push the first branch. This must come last (label before any branch).
11. Post-agent confinement guard (see containment contract).

## Concurrency groups

| Group | When |
|---|---|
| `wing-commander-intake` | Root numbering sequence |
| `wing-commander-intake/P` | Project `P` numbering sequence |
| `wing-commander-intake-issue/<issue-number>` | Only when the routing prefix is set; held by the gate job that runs steps 1–4 |

`cancel-in-progress` stays `false` as today.

## Downstream stages

Each stage derives `(P, NNN-slug)` from its identity input using the shared parser, re-validates the folder on the ref it works from, and fails with the folder named if it is gone or no longer a Spec Kit project. It never writes to a stale path.

## Wrapper setup (documented, FR-018)

One shared wrapper set. Set `routing-label-prefix` on the intake wrapper; widen the plan wrapper's `paths:` filter (and the tasks wrapper's in `pr` review mode) to `**/specs/**`; create one `node:<path>` label per project; pass `slug=P/<NNN-slug>` to plan and tasks restarts and `spec_dir=P/specs/<NNN-slug>` to implement, finalize and fold-cycle-guard restarts.
