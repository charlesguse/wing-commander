# Quickstart: validating subfolder project lifecycles

Contracts: [project-path-and-names](contracts/project-path-and-names.md), [routing-and-intake](contracts/routing-and-intake.md), [containment](contracts/containment-and-trusted-checkout.md). Entities: [data-model](data-model.md).

## 1. Local gates (every PR)

```
python .github/scripts/run-local-gates.py
```

Expect all gates to pass, including the new project gates (path grammar, name parser, single-home, intake routing, numbering, containment, pipeline-checkout containment). Each gate must fail when its reject fixture is the subject.

Because workflow comments are load-bearing, re-run the suite after any comment edit. A change touching an `if:`, `continue-on-error:` or a failing step gets the `review-step-gating` skill pass. A new `run:` step in a container job gets `container-shell-safety`.

## 2. Shared parser, by hand

From the repository root, with the fixtures:

```
bash .github/actions/_shared/project-name.sh validate-path ideas/alpha        # ok
bash .github/actions/_shared/project-name.sh validate-path Ideas/alpha        # rejected
bash .github/actions/_shared/project-name.sh parse branch spec-draft/ideas/alpha/003-foo
bash .github/actions/_shared/project-name.sh parse slug ideas/alpha/003-foo   # same pair
bash .github/actions/_shared/project-name.sh parse spec-dir ideas/alpha/specs/003-foo
```

Expect `project=ideas/alpha` and `slug=003-foo` from the last three, and the same pair for the root forms with `project=` empty.

## 3. Root adopter unchanged (Story 3, SC-003)

Run this repository's own lifecycle with unchanged wrappers. Compare spec path, branch names, label, concurrency groups and allocated number to the pre-change run.

Expected: identical, with routing off.

## 4. Subfolder end to end (Story 1, SC-001)

In a test repository with a root project and `ideas/alpha/` carrying its own Spec Kit state:

1. Set `routing-label-prefix: node:` on the intake wrapper; widen the plan wrapper filter.
2. Create the label `node:ideas/alpha`, apply it with `spec-request`.
3. Drive to cleanup.

Expected: spec at `ideas/alpha/specs/<NNN-slug>/`, `spec-meta.json` with `spec_dir: specs/<NNN-slug>`, branch `spec-draft/ideas/alpha/<NNN-slug>`, label `spec:ideas/alpha/<NNN-slug>`, every agent-authored change under `ideas/alpha/`, and cleanup leaving other projects' refs alone.

## 5. Isolation (Story 2, SC-002)

Start lifecycles in `ideas/alpha` and `ideas/beta` that both produce `001-login`. Expected: distinct branches, labels and per-spec groups; both run concurrently; the watchdog attributes each run to the right project; the collision check does not flag the other project's `001`.

## 6. Refusals

| Input | Expected |
|---|---|
| `node:` label naming a missing folder | Fails on the lifecycle issue; nothing created |
| Two `node:` labels | Refused with callout |
| Re-run intake on an issue that has `spec:`, routing on | Refused; routing off: unchanged |
| Two intakes for one issue routed to different projects | One proceeds |
| Branch tracking `P/.wing-commander-pipeline/x` | Refused |
| Agent edit to `a/.claude/` with `P = a/b` | Denied |
| Slug over `44 − len(P)` | Fails before any branch exists |

## 7. Graduation (Story 4, SC-004)

Copy a completed project folder to a fresh repository root, add wrappers, secrets and labels, and run a lifecycle. Expected: zero edits inside the folder, `spec-meta.json` files still pass the self-identity check, next number continues the sequence.

## 8. After merge

Behaviour that only runs in Actions is proven by re-driving one run (`prove-after-merge`), recording evidence on the PR or lifecycle issue. The constitution amendment is a separate human-merged PR that must reach `main` no later than the lifecycle PR.
