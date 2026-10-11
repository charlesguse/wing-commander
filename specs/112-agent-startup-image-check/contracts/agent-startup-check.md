# Contract: Agent Start-up Check

Layer: this contract describes both layers (Principle VII). The published
surface is one new reusable workflow, `agent-startup-check.yml`; the
instrument is this repository's classifier, gate, fixtures and wrappers.

## Published surface (additive, FR-010)

A new published workflow, `.github/workflows/agent-startup-check.yml`
(`on: workflow_call` only). Nothing calls it unless a caller opts in, so an
adopter who changes nothing keeps working. `private-image-dogfood.yml` and
every lifecycle stage gain no input, secret, output or permission: an
earlier draft put the start-up jobs inside `private-image-dogfood.yml`
behind an optional input, and GitHub checks every job's permissions when a
reusable workflow starts, skipped jobs included, so every caller of that
workflow would have had to grant `actions: read` (SC-005). Gate 147 pins
`private-image-dogfood.yml` to `permissions: {}` at the top level and on
every job.

`agent-startup-check.yml` `workflow_call`:

| Name | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `container-image` | input | string | `""` | The image under test. Empty makes the whole workflow a no-op |
| `runner` | input | string | `ubuntu-latest` | As every published stage |
| `environment` / `environment-deployment` | input | string / boolean | `""` / `true` | As every published stage |
| `pipeline-repo` | input | string | `charlesguse/wing-commander` | Where the classifier script is checked out from |
| `pipeline-ref` | input | string | `""` | Classifier commit; empty = `github.job_workflow_sha`. No OIDC fallback (the job holds no `id-token`): set it when that is empty |
| `container-registry-username` / `-password` | secret | | | Optional, for a private image |
| `pipeline-repo-token` | secret | | | Optional, only for a private `pipeline-repo`; used by classify-startup's checkout alone |

The calling job grants `actions: read` and `contents: read`. No model
credential is accepted. classify-startup finds its own call's
`startup-agent` job by the job-name prefix the two share (read off its own
job, found by runner name), so a matrix or a second call in one run is
told apart; an ambiguous lookup is `unclassified`.

## Jobs in `agent-startup-check.yml`

0. `verify-image-prerequisites` — the same job every published stage
   carries (Gates 7/22/23/148).
1. `startup-agent` — `needs: verify-image-prerequisites`, `if: !cancelled()
   && inputs.container-image != ''`, same `runs-on`/`container`/`credentials`
   binding as every stage job (Gates 7/22). One step: `uses:
   anthropics/claude-code-action@v1`, `continue-on-error: true`,
   `github_token: ${{ github.token }}`, a fixed `prompt` and
   `allowed_bots: github-actions`, and no model credential input. The prompt
   is required: without one the action's agent mode exits 0 before
   installing Claude Code. It never reaches a model because the action stops
   at its credential check.
2. `classify-startup` — `needs: [verify-image-prerequisites, startup-agent]`,
   `if:` the same as startup-agent's, `timeout-minutes: 10`, `permissions:
   actions: read, contents: read` (the classifier's checkout needs the
   second). Runs on `runner` with no `container:` (Gate 22's one
   registered exception): it only reads another job's log, and inside the
   image under test it could not report on an image without a shell,
   python3 or gh, or one that fails to pull. Checks out the classifier from `pipeline-repo` at the
   running workflow's commit, fetches the agent job's log, runs
   `classify-agent-startup.py`, writes the verdict and the
   `verify-image-prerequisites` result to the job summary, and exits
   non-zero unless `setup-completed`.

Neither start-up job honours a failed `verify-image-prerequisites`. The
spec's edge case reads "The required-tool list and the start-up check
disagree ... both results are reported; neither silently overrides the
other", and SC-001's image without `unzip` fails the tool list too. A
failed prerequisite check stays red on its own job, and the start-up verdict
is reported next to it. Gate 23 exempts exactly these two jobs, by file and
job name, from its result guard (they must still need the check and carry
`!cancelled()`). Gate 147 fails if either `if:` reads the check's result.

## Callers in this repository (FR-005)

`wing-commander-private-image-dogfood.yml` runs daily and on dispatch. It
calls `private-image-dogfood.yml` with `permissions: {}` and
`agent-startup-check.yml` with `actions: read`, both under the same
GHCR-namespace guard. The e2e reference-image rebuild dispatches that
wrapper against the digest it just published, because the agent action
does not support the rebuild's `push` event (Gate 6).

## Classifier CLI

```
python3 .github/scripts/classify-agent-startup.py --log <file> [--json]
```

Exit 0 only for `setup-completed`; 1 for `setup-failed`; 2 for `unclassified`.
Stdout: the Verdict (data-model.md). A missing, unreadable or empty `--log`
is `unclassified`, exit 2.

Rules, against claude-code-action@v1's own shape (one `run.ts` step that
prepares, installs Claude Code, then checks the model credential):
`setup-completed` needs the install's own success line and then the
credential check's error. `setup-failed` is an error after the action's
step started and before that success line, in a setup step (Install Bun,
Install Dependencies, or the Claude Code install itself), named as the job
page names it. `unclassified` is anything else: an error before the action
started (job set-up, image pull), the action's own prepare refusing the run
before it installs anything, the credential check before the success line,
a non-credential error after it, no error, or no log.

## Image probe addition (FR-013)

Inside the existing `docker run --entrypoint sh` probe of every
`verify-image-prerequisites` job, the fragment from
`.github/scripts/image-git-floor.sh` runs after the tool presence loop:

- git version parsed from `git --version`; `< 2.38` fails with
  `git <found> is older than the 2.38 minimum`;
- output that does not parse fails with `could not parse git version from
  "<output>"`.

Gate 148 (`verify-image-git-floor.py`) fails a stage whose probe lacks the
fragment, or the host-side report of a floor failure, verbatim. Gate 62
runs the same fragment against the reference image it builds.

## Gate

`verify-agent-startup-classifier.py [--self-test]` (Gate 147), registered in
`lint-workflows.yml`: runs the classifier over the fixture set and fails on
any mismatch or on a verdict branch with no fixture. It also pins the jobs:
no secret or model-credential variable reaches startup-agent outside its
registry credentials, classify-startup fails closed and names a failed
lookup or a crashed classifier, neither start-up job's `if:` reads the
prerequisite result and classify-startup reports it, `private-image-dogfood.yml`
declares no permission, and the dogfood wrapper's two calls run a dispatched
`container-image` only inside the owner's GHCR namespace.
