# Contract: Gate 99 — `verify-agent-push-credential-helper.py`, and Gate 100 — `verify-agent-push-credential-shell.py`

**Files**: `.github/scripts/verify-agent-push-credential-helper.py` and
`.github/scripts/verify-agent-push-credential-shell.py`, both wired into
`.github/workflows/lint-workflows.yml`'s existing PR-time job (new `run:`
steps naming each script — `wc_gate_registry.py`'s filename convention
picks both up automatically, and `verify-gate-wiring.py` confirms the
wiring is complete in both directions).

**Numbering**: the highest gate at plan time is Gate 98
(`verify-issue-context-trust-filter.py`), so this pair provisionally
claims Gate 99 and 100 — following spec 052's own documented renumbering
norm (Gate 68's contract), the implement stage renumbers and records a
collision note if another PR lands first on the same base and takes
either number.

## Gate 99 — structural

### Subject

The 8 workflow files FR-007 names, by literal path: `intake.yml`,
`clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`,
`pr-conversation.yml`, `auto-update-spec-kit.yml` (scoped to its
`e2e-stage` job only). Push-capable agent steps are identified
structurally: a step whose `uses:` resolves to
`anthropics/claude-code-action@*` (the existing marker every gate that
locates an agent step already keys on) AND whose composed allowed-tools
(via `wing-commander-tool-args`'s `default-allowed-tools`/
`extra-allowed-tools` inputs at that call site) contains
`Bash(git push:*)` — not every agent step in these 8 files is push-capable
(FR-025), so the gate must derive this rather than assume it.

### What it checks

1. **Credential-helper installed before every push-capable agent step**
   (FR-020 care point 1): for every push-capable agent step, a
   `wing-commander-agent-push-credential` call must appear after that
   job's push-capable checkout and before that agent step. Absent → FAIL,
   naming the workflow, job, and agent step.
2. **Stranded-commit publish step alongside every existing post-agent
   refresh** (FR-020 care point 2, extending spec 052's own Gate 68 check
   2's shape): for every push-capable agent step that also has spec 052's
   post-agent `wing-commander-context` re-mint (research.md D8 runs this
   feature's step alongside, not instead of, that one), a
   `wing-commander-publish-stranded-commits` call must appear with the
   same `if:` condition. Absent → FAIL, naming the workflow, job, and
   agent step.
3. **Single home for the minting shell** (FR-023): no file outside
   `.github/actions/wing-commander-agent-push-credential/` may contain a
   JWT-header/payload construction matching the same structural shape
   (`grep`-style, mirroring `verify-single-home-idioms.py`'s existing
   method for a different idiom, not a byte-identical diff check). A match
   elsewhere → FAIL, naming the file.
4. **No cost where nothing can push** (FR-025, negative check): an agent
   step with no `Bash(git push:*)` in its allowed-tools must have neither
   a `wing-commander-agent-push-credential` call nor the retry-bound
   prompt paragraph attributable to it. A match → FAIL (this feature must
   not spend anything where the spec says it must not).
5. **Loud failure on an unreachable subject** (FR-022, Constitution
   Principle VIII): if any of the 8 named files does not exist, or a named
   file's expected job (`e2e-stage` in `auto-update-spec-kit.yml`) cannot
   be located, or zero push-capable agent steps are found across all 8
   files combined, the gate exits non-zero naming which file/job it could
   not reach — never a silent pass over an empty result set.

### Mechanism

Static structural inspection via `yaml.safe_load` over each of the 8
files, the same approach Gate 68 already uses for the closest-shaped
subject in this repository. `bash -n` (an existing, separate PR-time gate)
already proves `mint-credential.sh`'s syntax; Gate 99 does not re-check
shell syntax.

### Fixtures (FR-022, applied to a `copy.deepcopy` of the real parsed
tree, per Gate 68's own precedent — no second synthetic YAML file to keep
in sync)

| Mutation | Expected result |
|---|---|
| Clean tree (no mutation) | PASS |
| Delete the credential-helper call ahead of `implement.yml`'s `retry` agent step | FAIL — names `implement.yml`, `implement` job, `retry` (check 1) |
| Delete the stranded-commit-publish call after `clarify.yml`'s agent step | FAIL — names `clarify.yml` and the step (check 2) |
| Duplicate the JWT-signing block into a second file outside the composite's own directory | FAIL — names the second file (check 3) |
| Attach the credential-helper call to a fixture agent step whose allowed-tools carry no `Bash(git push:*)` | FAIL (check 4) |
| Point the subject list at a 9th, nonexistent workflow file | FAIL — "could not reach subject" (check 5) |
| Point the subject list at zero workflow files | FAIL — same, empty-result guard (check 5) |

## Gate 100 — behavioural companion

Drives `mint-credential.sh` directly via `wc_shell_harness.py` (the same
harness spec 052's Gate 69 already established for exercising a
composite's `run:`-equivalent shell without a live token):

1. A fixed, checked-in throwaway RSA test keypair (never a real App key)
   stands in for `WC_AGENT_PUSH_KEY_PATH`.
2. `curl` is stubbed (a shell function shadowing the name on `PATH` for
   the duration of the test, matching `wc_shell_harness.py`'s existing
   stubbing convention) to return a fixed installation-lookup response,
   then a fixed token-mint response.
3. Assert the script's stdout is exactly `username=x-access-token\npassword=<the stubbed token>\n` and exit 0.
4. Repeat with the stubbed token-mint call returning a 401; assert stdout
   is empty, stderr's first line matches `^wing-commander-agent-push-
   credential: mint failed: token-mint-failed$`, and exit 1.
5. Repeat with `WC_AGENT_PUSH_KEY_PATH` pointing at a nonexistent file;
   assert the `key-unreadable` reason and exit 1, with zero network calls
   attempted (the stubbed `curl` records whether it was invoked at all).

## Local/CI parity (FR-021)

`run-local-gates.py` derives both gates' invocations from
`lint-workflows.yml`'s own `run:` blocks (`wc_gate_registry.
pr_time_invocations()`), so the local sweep runs the identical commands CI
runs.

## Triggering (FR-021)

`lint-workflows.yml`'s `on.pull_request.paths` already includes
`.github/workflows/**` and `.github/actions/**` — both gates' subjects are
covered with no new path entry required.
