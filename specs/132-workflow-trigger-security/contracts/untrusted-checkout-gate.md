# Contract: `verify-untrusted-checkout-local-uses.py`

**Layer**: consuming instrument gate.

## Invocation
`python3 .github/scripts/verify-untrusted-checkout-local-uses.py [--audit] [--self-test]`

`--audit` prints every job whose `./` reference resolves in an untrusted tree and exits 0 (for the FR-014 report); the default mode exits 1 on any.

## Rule (FR-016a)
- Trusted copy: checkout of the running repo at `github.sha` (top-level and repo-only reusable workflows), or of the pipeline repo at the resolved pipeline ref (published stages), at any path.
- Untrusted tree: any other checkout (PR head, item branch, consumer repo at any ref), artifact extraction or step-written content inside the workspace.
- A `./` reference fails when its path lies inside an untrusted tree. Trust comes from repository and ref, never from a directory name.
- Composites are judged per calling job.

## Classification input
`repo-only-reusable-workflows.json` (FR-016b). A `workflow_call` workflow not listed is a published stage.

## Fixtures
exposed job (fails); safe job (passes); artifact-extracted tree (fails); sidecar at pipeline ref (passes); pristine repo at `github.sha` (passes); unlisted `workflow_call` treated as repo-only (fails).

## Out of scope
Agent-writable workspace exposure stays with spec 086's gates. Gate 151 is unchanged.
