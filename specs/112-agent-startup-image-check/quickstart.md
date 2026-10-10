# Quickstart: validating the start-up check

Contracts: [agent-startup-check.md](contracts/agent-startup-check.md). Data
shapes: [data-model.md](data-model.md).

## 1. Calibrate against the real action (once, before fixtures are final)

Run `wing-commander-private-image-dogfood.yml` with `workflow_dispatch` on a
branch that sets `startup-check: true`, against the current reference image.
Save the `startup-agent` job log; its no-credential failure line becomes the
auth marker, and the log becomes the `setup-completed` fixture.

## 2. Local gate run

```
python .github/scripts/verify-agent-startup-classifier.py --self-test
python .github/scripts/run-local-gates.py
```

Expected: every fixture verdict matches its expectation; the full suite is
green.

## 3. Git floor

```
python .github/scripts/run-local-gates.py   # includes Gate 23
```

On a throwaway copy of a stage with the fragment removed, Gate 23 fails. To
see the probe itself: run it against `ubuntu:22.04` (git 2.34.1, expect a
failure naming 2.34.1) and `ubuntu:24.04` (expect pass).

## 4. End to end (SC-001, SC-002)

1. Dispatch the dogfood wrapper against the reference image: `classify-startup`
   passes, no model call appears in the run.
2. Dispatch against an image built without `unzip`: `classify-startup` fails
   naming "Install Bun" and `Unable to locate executable file: unzip`.
3. Push a Dockerfile change to main (or dispatch the reference-image
   workflow): its new check job passes on the published digest.

After merge, record the evidence with the `prove-after-merge` skill.
