# Quickstart: Validating the widened script-grant existence check

This is a validation guide, not an implementation checklist — it names the
commands that prove the feature works once tasks.md's edits land, and points
at the contracts that define what "working" means. It assumes the repo root
as the working directory.

## Prerequisites

- Python 3 with `pyyaml` installed (the same interpreter Gate 27 and every
  other `verify-*.py` gate already requires).

## 1. The gate is green against the real repository

```bash
python3 .github/scripts/verify-stage-tool-lists.py
```

Expect exit 0. Per research.md D0, this now inspects 13 grant occurrences
across all three surfaces (up from the composite-only, `.specify`-only
subset it checked before this feature): 6 resolve directly against the
tree, 6 are covered by the two entries in
`.github/scripts/script-grant-waivers.json`, and 1
(`board-loop.yml`'s `board-loop.reviewer`, a `${{ runner.temp }}`-prefixed
grant) is skipped as an unresolvable expression per FR-008 — none of these
three outcomes produces a failure line.

## 2. The self-test proves every new branch, not just the old ones

```bash
python3 .github/scripts/verify-stage-tool-lists.py --self-test
```

Expect exit 0 and one `[ok] mutation caught` line for each of
[contracts/gate-27-extension.md](./contracts/gate-27-extension.md)'s six new
mutations (research.md D9): a missing non-`.specify` script at a composite
site, a missing script via each of the two new collectors, a bare-command
grant raising nothing, an expression-valued grant raising nothing, and a
stale waiver entry — Constitution VIII's "a green check means what it says,"
proven locally the same way the file's four pre-existing mutations already
are.

## 3. Replay the two closed blind spots (User Stories 1 and 2's Independent Tests)

```bash
# US1: rename a first-party helper the composite grants and confirm the
# gate now catches it outside .specify/scripts/bash/ too.
mv .github/scripts/git_read.py .github/scripts/git_read.py.bak
python3 .github/scripts/verify-stage-tool-lists.py; echo "exit: $?"
mv .github/scripts/git_read.py.bak .github/scripts/git_read.py
```

Expect a non-zero exit and a failure line naming `board-loop.triage-propose`
(or `board-loop.route-propose`), the grant, and the missing path, while the
gate is restored to green immediately after the file is moved back.

```bash
# US2: point the wrapper's extra-allowed-tools at a script that doesn't
# exist, confirm the gate fails naming the wrapper file and job, then
# revert.
git diff --stat .github/workflows/wing-commander-5-implement.yml   # expect empty before you start
```

Edit `wing-commander-5-implement.yml`'s `extra-allowed-tools` line to
reference a path that does not exist (e.g. append
`,Bash(bash .github/scripts/zzz-does-not-exist.sh:*)`), re-run the gate,
confirm the failure names the workflow file, the `implement` job, and the
input key, then discard the edit (`git checkout -- .github/workflows/wing-commander-5-implement.yml`).

## 4. The waiver mechanism is auditable and honest (User Story 3's Independent Test)

```bash
# Remove the e2e-scratch waiver entry from script-grant-waivers.json and
# confirm the gate now fails naming the grant.
python3 -c "
import json
with open('.github/scripts/script-grant-waivers.json') as f:
    data = json.load(f)
data['waivers'] = [w for w in data['waivers'] if 'e2e-scratch' not in w['path']]
with open('/tmp/waivers-no-e2e.json', 'w') as f:
    json.dump(data, f)
"
cp .github/scripts/script-grant-waivers.json /tmp/waivers-backup.json
cp /tmp/waivers-no-e2e.json .github/scripts/script-grant-waivers.json
python3 .github/scripts/verify-stage-tool-lists.py; echo "exit: $?"
cp /tmp/waivers-backup.json .github/scripts/script-grant-waivers.json
```

Expect a non-zero exit with a failure naming the `create-new-feature.sh`
grant, then a clean run once the entry is restored.

```bash
# Add a waiver entry for a path that DOES resolve (e.g. this gate script
# itself) and confirm the gate reports it as stale.
python3 -c "
import json
with open('.github/scripts/script-grant-waivers.json') as f:
    data = json.load(f)
data['waivers'].append({'path': '.github/scripts/verify-stage-tool-lists.py', 'issue': '#0', 'reason': 'test'})
with open('.github/scripts/script-grant-waivers.json', 'w') as f:
    json.dump(data, f)
"
python3 .github/scripts/verify-stage-tool-lists.py; echo "exit: $?"
git checkout -- .github/scripts/script-grant-waivers.json
```

Expect a non-zero exit with a failure naming
`.github/scripts/verify-stage-tool-lists.py` as a stale waiver entry, then a
clean run once the edit is discarded.

## 5. Full local gate sweep

```bash
python .github/scripts/run-local-gates.py
```

The same command CLAUDE.md's "Before pushing" section tells the implement
agent and human/local sessions to run — a clean run here, including this
gate's own widened self-test, is the final proof that this feature passes
the suite it edits (SC-003, mirroring how every prior Gate 27 change has
verified itself).
