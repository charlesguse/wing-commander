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

1. `startup-agent` — `if: inputs.startup-check && inputs.container-image != ''`,
   same `runs-on`/`container`/`credentials` binding as `dogfood`
   (Gates 7/22). One step: `uses: anthropics/claude-code-action@v1`,
   `continue-on-error: true`, `github_token: ${{ github.token }}`, no model
   credential input. No `prompt` reaching a model is possible because the
   action stops at authentication.
2. `classify-startup` — `needs: startup-agent`, `if: !cancelled() &&
   inputs.startup-check && inputs.container-image != ''`, `permissions:
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

## Image probe addition (FR-013)

Inside the existing `docker run --entrypoint sh` probe of every
`verify-image-prerequisites` job, the fragment from
`.github/scripts/image-git-floor.sh` runs after the tool presence loop:

- git version parsed from `git --version`; `< 2.38` fails with
  `git <found> is older than the 2.38 minimum`;
- output that does not parse fails with `could not parse git version from
  "<output>"`.

Gate 23 fails a stage whose probe lacks the fragment verbatim.

## Gate

`verify-agent-startup-classifier.py [--self-test]`, registered in
`lint-workflows.yml`: runs the classifier over the fixture set and fails on
any mismatch or on a verdict branch with no fixture.
