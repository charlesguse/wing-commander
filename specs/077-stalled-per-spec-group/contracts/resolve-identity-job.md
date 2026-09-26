# Contract: `resolve-identity` job (`pr-conversation.yml`, new)

This is the API-calling counterpart to the `resolve-spec` job contract in
`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`: same
purpose (make the specification's identity available as a **job** output
before a downstream job's `concurrency:` block is evaluated), same
no-checkout/no-secrets shape, differing in the one way spec.md's Context
section already names — this stage receives only `pr-number`, so it must
read the GitHub API before it can derive anything, where `resolve-spec`
derives everything by pure string manipulation over a declared `head-ref`/
`slug` input.

This job is internal to the `pr-conversation.yml` stage file. It is not a
`workflow_call` output, input, or secret of the stage (FR-017) — nothing
outside this one workflow file's own job graph references it by name.

## Shape

```yaml
resolve-identity:
  runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
  container:
    image: ${{ inputs.container-image }}
    credentials: >-
      ${{
        (secrets.container-registry-username != '' && secrets.container-registry-password != '')
          && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
          || fromJSON('{}')
      }}
  environment:
    name: ${{ inputs.environment }}
    deployment: ${{ inputs.environment-deployment }}
  needs: verify-image-prerequisites
  if: "!cancelled() && needs.verify-image-prerequisites.result != 'failure'"
  permissions:
    pull-requests: read
    contents: read
  outputs:
    qualifies: ${{ steps.identity.outputs.qualifies }}
    slug: ${{ steps.identity.outputs.slug }}
    spec-dir: ${{ steps.identity.outputs.spec-dir }}
    default-branch: ${{ steps.identity.outputs.default-branch }}
    reason: ${{ steps.identity.outputs.reason }}
  steps:
    - name: Resolve PR identity and check qualification
      id: identity
      shell: bash
      env:
        GH_TOKEN: ${{ github.token }}
        PR_NUMBER: ${{ inputs.pr-number }}
        DEFAULT_BRANCH_INPUT: ${{ inputs.default-branch }}
        SPEC_PREFIX: ${{ inputs.spec-prefix }}
        SPEC_DRAFT_PREFIX: ${{ inputs.spec-draft-prefix }}
        PLAN_PREFIX: ${{ inputs.plan-prefix }}
        TASKS_PREFIX: ${{ inputs.tasks-prefix }}
      run: |
        # Byte-identical body to today's classify-and-announce "Resolve PR
        # identity and check qualification" step (pr-conversation.yml).
        # Relocated, not rewritten: the API-failure branch already fails
        # loudly (::error:: + exit 1, FR-005); the non-qualifying branch
        # already stays green with qualifies=false (FR-007).
        ...
```

No checkout, no secrets, no `Bash(git push:*)` grant anywhere in this job —
Gate 80 (`verify-spec-branch-push-concurrency.py`) never lists it as a
pusher, so it needs no waiver and no group at all beyond GitHub's default.

## Outputs

| Output | Type | Meaning | Consumers |
|---|---|---|---|
| `qualifies` | `"true"`\|`"false"` | Whether this PR is an implementation PR this stage acts on | `classify-and-announce` (every `if:` gated on qualification; its own job output) |
| `slug` | string, or empty | `NNN-slug` | `classify-and-announce` (job output, prompt text); `stalled` (lifecycle-issue lookup, chain-stop-notice `spec-branch`) |
| `spec-dir` | string, or empty | `specs/<slug>` | `classify-and-announce` (job output, prompt text); `stalled` (concurrency group, lifecycle-issue lookup guard, chain-stop-notice `spec-dir`) |
| `default-branch` | string | The repository's default branch | `classify-and-announce` (job output; `Resolve default branch`-style consumers, if any, downstream) |
| `reason` | string, or empty | One sentence naming the unreadable API response, set only when this job fails | None today (observability / symmetry with `resolve-spec`'s `refusal-reason`) |

## Behavioral guarantees (mirrors `resolve-spec`'s own, adapted for the API-read case)

1. **FR-005 / FR-011**: an unreadable `gh repo view`/`gh pr view` response
   fails this job loudly (`::error::`, non-empty `reason`, `exit 1`) — it is
   never reported as `qualifies: false`, which would be indistinguishable
   from an ordinary non-qualifying PR and would let a maintainer's request
   vanish with no reply and no error.
2. **FR-007**: a readable response whose head ref is not `spec/NNN-slug` (or
   matches an excluded prefix) is not an error. This job stays green,
   `qualifies` is `"false"`, `slug`/`spec-dir` are empty.
3. **FR-009 / FR-010**: for every PR, this job's `qualifies` verdict is
   identical to what `classify-and-announce`'s own identity step computes
   today for the same PR — the logic is unchanged, only relocated.
4. **No new `workflow_call` surface** (FR-017): this job is invisible
   outside `pr-conversation.yml`'s own job graph.
