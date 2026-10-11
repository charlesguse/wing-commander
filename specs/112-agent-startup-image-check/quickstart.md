# Quickstart: validating the start-up check

Contracts: [agent-startup-check.md](contracts/agent-startup-check.md). Data
shapes: [data-model.md](data-model.md).

## 1. Calibrate against the real action (once, before fixtures are final)

Run `wing-commander-private-image-dogfood.yml` with `workflow_dispatch`
against the current reference image (its `startup-check` job calls
`agent-startup-check.yml`). Save the `startup-agent` job log; its no-credential failure line becomes the
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
python .github/scripts/run-local-gates.py   # includes Gate 148
```

On a throwaway copy of a stage with the fragment removed, Gate 148
(verify-image-git-floor.py) fails. To see the probe itself: run it against `ubuntu:22.04` (git 2.34.1, expect a
failure naming 2.34.1) and `ubuntu:24.04` (expect pass).

## 4. End to end (SC-001, SC-002)

1. Dispatch the dogfood wrapper against the reference image: `classify-startup`
   passes, no model call appears in the run.
2. Dispatch against an image built without `unzip`, pushed inside this
   owner's `ghcr.io/<owner>/` namespace (the wrapper refuses any other
   image): `classify-startup` fails naming "Install Bun" and
   `Unable to locate executable file: unzip`. `verify-image-prerequisites`
   fails too, naming `unzip`; the start-up jobs run regardless, and
   `classify-startup`'s summary shows both results (spec edge case: neither
   overrides the other). An earlier draft skipped the start-up jobs
   here, so this step could not be reached.
3. Push a Dockerfile change to main (or dispatch the reference-image
   workflow): its new check job passes on the published digest.

After merge, record the evidence with the `prove-after-merge` skill.
