# Contract: Agent Start-up Check

Layer: this contract describes both layers (Principle VII). The published
surface is one optional input on `private-image-dogfood.yml`; the instrument
is this repository's classifier, gate, fixtures and wrappers.

## Published surface (additive, FR-010)

`private-image-dogfood.yml` `workflow_call`:

| Name | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `startup-check` | input | boolean | `false` | Also run the agent action's setup in `container-image` with no model credential and classify the outcome. Inert when `container-image` is empty |

No new secret. With `startup-check: true` the caller must grant the stage
`actions: read` (the classify job reads the agent job's log). Callers that
leave it `false` change nothing.

No published stage workflow other than `private-image-dogfood.yml` gains an
input, secret or output (spec Assumptions).

## Jobs added to `private-image-dogfood.yml`

1. `startup-agent` — `needs: verify-image-prerequisites`, `if: !cancelled()
   && needs.verify-image-prerequisites.result != 'failure' &&
   inputs.startup-check && inputs.container-image != ''`,
   same `runs-on`/`container`/`credentials` binding as `dogfood`
   (Gates 7/22). One step: `uses: anthropics/claude-code-action@v1`,
   `continue-on-error: true`, `github_token: ${{ github.token }}`, a fixed
   `prompt` and `allowed_bots: github-actions`, and no model credential input.
   The prompt is required: without one the action's agent mode exits 0 before
   installing Claude Code. It never reaches a model because the action stops
   at its credential check.
2. `classify-startup` — `needs: [verify-image-prerequisites, startup-agent]`,
   `if:` the same as startup-agent's, `timeout-minutes: 10`, `permissions:
   actions: read`. Fetches the agent job's log, runs
   `classify-agent-startup.py`, writes the verdict to the job summary, exits
   non-zero unless `setup-completed`.

`verify-image-prerequisites` remains the first job and both new jobs honour
its skip/failure result like `dogfood` does (Gate 23).

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
lookup or a crashed classifier, and the dogfood wrapper runs a dispatched
`container-image` only inside the owner's GHCR namespace.
