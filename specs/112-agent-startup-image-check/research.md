# Research: Agent Start-up Image Check

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
resolve the technical unknowns the plan met; D2, D3 and D6 are made without
the owner and are flagged for review.

## D1 — Where the check runs

- **Decision**: A job in `private-image-dogfood.yml` behind a new optional
  boolean input `startup-check` (default `false`). The scheduled wrapper sets
  it `true`. The reference-image workflow adds a job that calls the same
  stage with the freshly published image and `startup-check: true`.
- **Rationale**: A job with `container:` cannot be inside a composite, so the
  stage file is the one home; both triggers reuse it (CLAUDE.md "one home").
  Default `false` keeps adopters unchanged (FR-010).
- **Alternatives**: a per-stage preflight (rejected in clarification);
  a copy of the job in the reference-image workflow (pasted copy, rejected).

## D2 — How the log is read (decision without owner)

- **Decision**: The agent step runs with `continue-on-error: true` and no
  model credential. A second job `classify-startup` (`needs` the first,
  `if: !cancelled()`) fetches the first job's log with
  `gh api repos/{repo}/actions/jobs/{id}/logs` using `actions: read`, and
  pipes it to `classify-agent-startup.py`. The classifier job fails unless the
  verdict is `setup-completed`.
- **Rationale**: Steps inside the action are not visible to the calling job
  (only the top-level step's conclusion is), so the only observable "which
  setup step failed" evidence is the log. The job log is retrievable once
  that job has finished, while the run is still in progress.
- **Alternatives**: parse the step conclusion alone (cannot tell setup from
  auth failure, fails FR-003); replay setup by hand (clarification chose the
  real action). Cost: the caller must grant `actions: read` to this job; the
  wrapper does, an adopter who leaves `startup-check` off needs nothing.

## D3 — Classification rules (decision without owner)

- **Decision**: The classifier scans the log for the action's step-group
  headers (`##[group]Run oven-sh/setup-bun...` / "Install Bun", "Install
  Dependencies" and similar, read from the log, not hard-coded to a list that
  must stay complete) and the first `##[error]`. Verdicts:
  - `setup-completed`: the first error occurs after all setup groups and its
    text matches the authentication marker (missing credential message from
    the action's prepare step).
  - `setup-failed`: the first error is inside a setup group; output names the
    group and quotes the error line (e.g. `Unable to locate executable file:
    unzip`).
  - `unclassified`: log empty or truncated, no error at all (action
    succeeded), error after setup that is not the auth marker, pull failure
    (job never started), or markers absent.
- **Rationale**: Principle VIII and FR-004: pass only on positive evidence.
  The auth marker is a data table in the script so a change in the action's
  wording turns the check red (`unclassified`) and is a one-line, reviewable
  fix.
- **Risk**: the real wording must be captured from a live run before the
  fixtures are final; quickstart step 1 does that, and the first
  implementation task records it. With no credential the action might fail on
  OIDC/token acquisition before auth; the check passes `github_token:
  ${{ github.token }}` so the first failure is the credential one.

## D4 — Git floor placement

- **Decision**: Add the git >= 2.38 assertion to the in-container probe
  (the `docker run ... sh -c` already in every stage's
  `verify-image-prerequisites`). The fragment lives canonically in
  `.github/scripts/image-git-floor.sh`; Gate 23 verifies each stage's probe
  contains it byte-for-byte, like it compares `REQUIRED_TOOLS`.
- **Rationale**: The job has no checkout and is deliberately self-contained
  (Gate 23/22 shape), so it cannot source a script; the probe is pasted in 14
  files already. The gate is what makes the repetition safe. Failure message
  names version found and the 2.38 minimum; unparseable output fails.
- **Alternatives**: a composite via self-checkout (changes the job shape that
  Gates 22/23 pin and adds a checkout to a no-checkout job; larger scope);
  encoding the floor in `required-tools.txt` as `git>=2.38` (changes the set
  semantics Gate 23 and Gate 62 compare, and the contract table).

## D5 — Reference-image rebuild trigger

- **Decision**: Add the call job to `wing-commander-e2e-reference-image.yml`
  after `build-and-publish`, passing the digest reference output by the build
  step. Gate 62 remains as is.
- **Rationale**: The workflow already runs on Dockerfile or
  `required-tools.txt` changes; checking the image just pushed tests the
  exact artifact. FR-005.

## D6 — Floating tag policy

- **Decision**: Keep `@v1`; document in `docs/adoption.md` ("Runners and
  container images") and the 038 image-prerequisite contract that dependency
  changes arrive through it and are caught by the start-up check on the next
  daily or rebuild run.
- **Rationale**: FR-007; owner decision in clarification.
- **Note for tasks**: the 038 contract is under `specs/*/contracts/`, which is
  live; it is edited in the implement stage, not here.

## D7 — Fixtures and gate

- **Decision**: `verify-agent-startup-classifier.py` runs the classifier over
  `agent-startup-fixtures/`: one log per branch (auth reached, setup failed
  at Install Bun missing unzip, setup failed other step, action succeeded,
  error after setup not auth, empty log, truncated log, image not pulled). The
  gate fails when any fixture's verdict differs from its declared expectation
  or when a verdict branch has no fixture. Wired into `lint-workflows.yml`
  (path-triggered by the script, fixtures and the workflows it reads) so
  `run-local-gates.py` picks it up.
- **Rationale**: FR-008, SC-003, Principle VIII.
- **Alternatives**: none; this is the repository's pattern.

## D8 — Registry credentials for the reference image

- **Decision**: The reference-image job passes the repository's
  `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME/_PASSWORD` secrets, as the
  dogfood wrapper does, since `GITHUB_TOKEN` forwarded through a `uses:` job
  does not reach the package pull (documented in the wrapper header).
