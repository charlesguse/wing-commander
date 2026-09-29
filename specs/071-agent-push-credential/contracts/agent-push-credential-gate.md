# Contract: Gate 122 — `verify-agent-push-credential-helper.py`

**File**: `.github/scripts/verify-agent-push-credential-helper.py`, wired
into `.github/workflows/lint-workflows.yml`'s existing PR-time job (a
`run:` step naming the script — `wc_gate_registry.py`'s filename convention
picks it up automatically, and `verify-gate-wiring.py` confirms the wiring
is complete in both directions).

**Numbering**: the highest gate at plan time was Gate 98
(`verify-issue-context-trust-filter.py`), so this pair provisionally
claimed Gate 99 and 100 — following spec 052's own documented renumbering
norm (Gate 68's contract). By implement time, main had already claimed
both numbers for other specs (Gate 99: spec 059's
`verify-tasks-checkbox-convergence-signal.py`; Gate 100: spec 079's
`verify-stage-turn-budget-docs.py`), and the highest gate actually in use
was Gate 119, so this pair was renumbered to Gate 120 and Gate 121. Main
then claimed those two numbers as well, for other specs (Gate 120:
`verify-dedup-key-canonical-rule.py`; Gate 121:
`verify-commit-message-scratch-path.py`), before this branch's own rebase
landed either time, so this pair was renumbered a second time to **Gate
122** and **Gate 123** (tasks.md T056).

**Gate 123 retired, then reused for a new subject**: an owner-directed
redesign (tasks.md's "Maintainer Feedback" section, T057) deleted the
`wing-commander-agent-push-credential` composite and its `mint-
credential.sh` script as a security defect — the composite staged the
GitHub App private key where a running agent step could reach it and mint
installation tokens itself, materially worse than the one-hour,
one-repository token the agent already has. Gate 123 existed solely to
drive `mint-credential.sh` directly; with that script gone, Gate 123 had
no remaining subject and was retired in the same redesign (T063) rather
than left in place checking nothing. Gate 122 survives — its check 2 (the
stranded-commit-publish wiring) is still live, since that composite is the
sole remaining remedy — and gained a new check 1 in its place, guarding
against the deleted composite's exact security defect reappearing. The
number was not renumbered down (122 was already the lower of the pair),
and 123 was left unreserved — until the maintainer review of PR #720
(T070) reused it for a new, unrelated behavioural companion: driving
`wing-commander-publish-stranded-commits`' own commits-published count
against a real git repository. See "Gate 123 — behavioural" below.

## Gate 122 — structural

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
(FR-025), so the gate must derive this rather than assume it. Check 1 also
scans every step in each of these jobs regardless of push-capability, since
the private-key exposure it guards against is not specific to push-capable
steps.

### What it checks

1. **The App private key is never staged where a running agent step could
   reach it** (FR-023 security guard, replacing the retired design's check
   1): `secrets.speckit-app-private-key`, or an adopter-facing wrapper's
   own `secrets.WING_COMMANDER_APP_PRIVATE_KEY` (dotted or bracket
   syntax), may only ever be handed to `actions/create-github-app-token@*`,
   directly or through the two composites that wrap it and expose only a
   derived, short-lived token — `wing-commander-context`,
   `_shared/scoped-app-token`. Any other consumer — a plain shell step, a
   different action, a `run:` block that writes the key (or a path to a
   file holding it) to `$GITHUB_ENV` or a file — fails the gate by name.
   Checked across every `.github/workflows/*.yml` file (T069 — not only
   the 8 SUBJECTS below, since watchdog/cleanup/rebase/board-loop and the
   adopter-facing wrappers stage the same secret), at workflow level, job
   level and step level, and across the whole job rather than just the
   steps positioned ahead of an agent step: once written to `$GITHUB_ENV`
   or a `$RUNNER_TEMP` file, the material outlives the step that wrote it.
2. **Stranded-commit publish step alongside every existing post-agent
   refresh** (FR-020 care point 2, extending spec 052's own Gate 68 check
   2's shape): for every push-capable agent step that also has spec 052's
   post-agent `wing-commander-context` re-mint (research.md D8 runs this
   feature's step alongside, not instead of, that one), a
   `wing-commander-publish-stranded-commits` call must appear with the
   same `if:` condition. Absent → FAIL, naming the workflow, job, and
   agent step.
3. **Single home for the on-demand JWT-signing shape** (FR-023): no file
   anywhere in the repository may contain a JWT-header/payload
   construction matching the same structural shape (`grep`-style,
   mirroring `verify-single-home-idioms.py`'s existing method for a
   different idiom, not a byte-identical diff check) — the shipped design
   has no legitimate site for this shape left at all, unlike the retired
   design which scoped this check to "outside the composite's own
   directory." A match anywhere → FAIL, naming the file.
4. **No cost where nothing can push** (FR-025, negative check): an agent
   step with no `Bash(git push:*)` in its allowed-tools must not carry the
   retry-bound prompt paragraph attributable to it. A match → FAIL (this
   feature must not spend anything where the spec says it must not).
5. **Loud failure on an unreachable subject** (FR-022, Constitution
   Principle VIII): if any of the 8 named files does not exist, or a named
   file's expected job (`e2e-stage` in `auto-update-spec-kit.yml`) cannot
   be located, or zero push-capable agent steps are found across all 8
   files combined, the gate exits non-zero naming which file/job it could
   not reach — never a silent pass over an empty result set.

### Mechanism

Static structural inspection via `yaml.safe_load` over each of the 8
files (check 3 walks the whole repository tree instead), the same approach
Gate 68 already uses for the closest-shaped subject in this repository.

### Fixtures (FR-022, applied to a `copy.deepcopy` of the real parsed
tree, per Gate 68's own precedent — no second synthetic YAML file to keep
in sync)

| Mutation | Expected result |
|---|---|
| Clean tree (no mutation) | PASS |
| Hand the App private key to a fixture composite ahead of `implement.yml`'s `cycle` agent step | FAIL — names `implement.yml` and the fixture step (check 1) |
| Delete the stranded-commit-publish call after `clarify.yml`'s agent step | FAIL — names `clarify.yml` and the step (check 2) |
| Duplicate the JWT-signing block into any file in the repository | FAIL — names the file (check 3) |
| Attach the retry-bound prompt paragraph to a fixture step whose allowed-tools carry no `Bash(git push:*)` | FAIL (check 4) |
| Point the subject list at a 9th, nonexistent workflow file | FAIL — "could not reach subject" (check 5) |
| Point the subject list at zero workflow files | FAIL — same, empty-result guard (check 5) |

## Local/CI parity (FR-021)

`run-local-gates.py` derives the gate's invocation from
`lint-workflows.yml`'s own `run:` blocks (`wc_gate_registry.
pr_time_invocations()`), so the local sweep runs the identical command CI
runs.

## Triggering (FR-021)

`lint-workflows.yml`'s `on.pull_request.paths` already includes
`.github/workflows/**` and `.github/actions/**` — the gate's subjects are
covered with no new path entry required.

## Gate 123 — behavioural (T070, maintainer review of PR #720)

**File**: `.github/scripts/verify-stranded-commit-publish-shell.py`.

### Subject

The "Publish stranded commits" step inside
`.github/actions/wing-commander-publish-stranded-commits/action.yml` — the
sole remaining remedy this feature ships (the mechanism Gate 122 check 2
wires into every in-scope stage). verify-chain-stop-notice-body.py already
proves that a given `(commits-published, push-ok)` pair renders the right
stall-notice wording, but only as fixture strings handed straight in; it
never exercises the `git rev-list --count` comparison that PRODUCES those
values (T060's origin-ref comparison, falling back to `before-sha..HEAD`
only when no remote-tracking ref exists). Gate 123 drives the shipped
`run:` text directly, via `wc_shell_harness.py` (the same harness Gate 35
and Gate 69 already use), against a real bare `origin` plus a clone.

### What it checks

1. Everything already pushed directly by the agent before this step ever
   runs (a real `git push`, advancing the local `refs/remotes/origin/
   <branch>`) → `commits-published=0`, `push-ok=true`.
2. Two commits stranded locally, never pushed by anything before this step
   → `commits-published=2`, `push-ok=true`, and `origin`'s branch tip
   actually advances to the pushed local `HEAD`.
3. No `refs/remotes/origin/<branch>` exists locally at all → falls back to
   `${BEFORE_SHA}..HEAD`.

### Mechanism

Behavioural: extracts the step's own `run:` text via `wc_shell_harness.
find_step` and executes it with `wc_shell_harness.run_step` against a real
git workspace built fresh per scenario — not a copy of the shell retyped
into the gate.

### Fixtures (`--self-test`)

| Mutation | Expected result |
|---|---|
| Clean scenarios (no mutation) | PASS (all 3) |
| Revert the origin-ref comparison to `${BEFORE_SHA}..HEAD` unconditionally | FAIL — scenario 1 recounts the agent's own already-pushed commits instead of reporting 0 |

## Local/CI parity and triggering (Gate 123)

Same as Gate 122 above: `run-local-gates.py` derives Gate 123's invocation
from `lint-workflows.yml`'s own `run:` blocks, and the existing
`.github/actions/**` path trigger already covers this gate's subject.
