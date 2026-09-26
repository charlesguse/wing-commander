# Contract: `wing-commander-commit-message-guidance` composite action

This is the FR-011 canonical source. It is a plain (non-`_shared`)
`.github/actions/` composite, resolved from the consuming repository's own
checkout the same way `wing-commander-tool-args` and `wing-commander-
metrics-summary` already are (Constitution VI/VII) — every field below is
part of the interface a future edit must keep, and a breaking change to it
follows the same discipline as any other composite in this repository.

Full input/output field definitions live in
[data-model.md](../data-model.md#entity-canonical-guidance-source) — this
contract states behavior, not just shape.

## Inputs

- `scratch-filename` (required): a bare filename, no directory component and
  no `${{ runner.temp }}` prefix — the action supplies that prefix itself so
  no call site can typo the path's root (FR-002's "no shell variable, no
  value it must derive" applies here too: the call site supplies a literal
  string, the action does the one substitution).
- `extra-note` (optional, default `""`): appended verbatim, on its own
  sentence boundary, after the canonical paragraph, when non-empty.

## Output

- `guidance`: a single string, safe to interpolate directly into a
  `prompt: |` block via `${{ steps.<id>.outputs.guidance }}`, containing:
  1. That a commit message longer than one line goes through the `Write`
     tool to exactly `${{ runner.temp }}/<scratch-filename>` and the commit
     is then made with `git commit -F` from that path (FR-001, FR-002).
  2. That the path lies outside the repository and why a path under the
     repository is unusable — refused inside `.git/`, swept into the commit
     anywhere else (FR-003).
  3. That a heredoc or `$(cat ...)` on the command line is refused by the
     permission layer, named explicitly so an agent does not discover this
     by trial (FR-004).
  4. That this only applies to messages longer than one line — an inline
     `-m` one-liner remains available (FR-005).
  5. `extra-note`'s text, if supplied, as a trailing sentence.

## Behavioral guarantees

- **Determinism**: for a fixed `(scratch-filename, extra-note)` pair, the
  output is byte-identical on every invocation — no timestamp, run id, or
  other non-reproducible content. This is what lets the gate compare two
  sites' rendered output and expect equality modulo the substituted fields
  (FR-009).
- **No network, no agent**: pure `bash` in the composite's own `run:` step,
  runs before the agent step it feeds, mirroring `wing-commander-tool-
  args`'s and `wing-commander-preflight`'s fail-fast-before-credentials
  position.
- **Single home**: after this feature ships, this action's `run:` step is
  the only place in the repository this paragraph's wording is written.
  Every one of the nine call sites (data-model.md's table) — including
  `implement.yml`'s two, converted from their own hand-written copies —
  consumes this output rather than embedding the sentence itself (FR-011,
  SC-009).

## Consumption pattern at a call site

```yaml
- name: Compose commit-message guidance (plan.direct-commit)
  id: commit-guidance-plan-direct
  uses: ./.github/actions/wing-commander-commit-message-guidance
  with:
    scratch-filename: plan-commit-message-direct.txt

- name: Generate implementation plan (direct commit)
  id: agent-auto
  uses: anthropics/claude-code-action@v1
  with:
    prompt: |
      ...
      3. Commit everything the skill generated ... Open no PR.

         ${{ steps.commit-guidance-plan-direct.outputs.guidance }}
      ...
```

`implement.yml`'s retry site is the one call site that also sets
`extra-note`, keeping the sentence that tells the agent to use a name
distinct from the cycle step's file (FR-013, research.md D4):

```yaml
- name: Compose commit-message guidance (implement.retry)
  id: commit-guidance-retry
  uses: ./.github/actions/wing-commander-commit-message-guidance
  with:
    scratch-filename: implement-commit-message-retry.txt
    extra-note: >-
      Use a name distinct from the cycle step's scratch file above --
      the cycle attempt may have left one behind, and this is a fresh
      session that never read it.
```
