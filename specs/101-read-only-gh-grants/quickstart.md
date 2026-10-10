# Quickstart: validating spec 101

Prerequisites: repo checkout on the implementation branch; Python 3 with PyYAML.

## 1. Gate passes on the real tree and fails on fixtures

```text
python .github/scripts/verify-issue-context-single-home.py
python .github/scripts/verify-issue-context-single-home.py --self-test
python .github/scripts/run-local-gates.py
```

Expected: all pass. The self-test reports each fixture in
[contracts/gate-93-check-4c.md](contracts/gate-93-check-4c.md) as a caught
failure, and both mutations (restoring either removed grant) as caught.

## 2. Grants are gone

Grep `watchdog.yml` and `auto-update-spec-kit.yml` for `Bash(gh`: the only
remaining hits must be none. `pr-conversation.yml` keeps its three exempt
grants (research D4).

## 3. Docs and contracts agree

Grep `docs/` and `specs/*/contracts/` for `Bash(gh:*)` and `Bash(gh api:*)`:
every hit is labelled historical. The rationale text occurs in exactly one
file.

## 4. After merge (Actions-only behaviour, CLAUDE.md "prove")

- Re-drive one watchdog run with `gh workflow run` on the wrapper that can
  dispatch it; confirm a schema-valid verdict and no denied-tool event for a
  route the prompt names (SC-004).
- Re-drive one auto-update evaluation; confirm one of the three outcomes with
  sources from `release-notes.json` (SC-005).
- Record the evidence on the PR or issue #759.
- Force a log-fetch failure (an unknown run id on a manual dispatch) and
  confirm a verdict naming `job-logs` as ungathered (SC-008).
