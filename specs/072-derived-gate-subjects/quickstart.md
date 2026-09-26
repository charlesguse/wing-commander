# Quickstart: Validating Gate 68's derived subjects

Prerequisites: a checkout of this repository with `PyYAML` available
(already a dependency of every `verify-*.py` gate; no new install step).
All commands run from the repository root.

## 1. Run the full local gate suite (baseline)

    python .github/scripts/run-local-gates.py

Expected: passes before and after this feature (SC-006). This is the same
command CLAUDE.md's "Before pushing" section already requires.

## 2. Run Gate 68 alone and read the subject report

    python3 .github/scripts/verify-post-agent-credential-refresh.py

Expected: exits 0, and prints the full derived `(path, job)` subject set —
now covering `board-loop.yml` (`triage`, `route`, `fix`, `review`),
`cleanup.yml` (`teardown-done`), `rebase.yml` (`rebase`), and
`watchdog.yml` (`diagnose`, reported as excluded rather than inspected) in
addition to the 9 job entries it named before this feature. A reader should
be able to name every inspected file and job from this output alone,
without opening the script (FR-007, SC-007).

## 3. Run Gate 68's self-test

    python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test

Expected: `Gate 68 self-test: clean tree passes; each mutation fails.`
Confirm the mutation count printed (one `Mutation OK` line per entry) is
strictly greater than the count on `main` before this feature — the two
floor-mismatch mutations, the emptied-derivation mutation, the respelled-
agent-step mutation, and the exclusion-removed mutation should all appear
(SC-005).

## 4. Prove User Story 1 — a new agent-bearing job is checked with no gate edit

1. In a scratch copy of a workflow file already covered by the derived set
   (e.g. `intake.yml`), duplicate an existing job and give the copy a new
   name, keeping its agent step and stripping the post-agent re-mint step
   after it.
2. Re-run step 2 above. Expected: the gate now fails, naming the new job
   and the specific stale-credential or missing-re-mint condition — with
   zero lines of `verify-post-agent-credential-refresh.py` touched (SC-001).
3. Restore the re-mint step (or discard the scratch copy). Expected: passes
   again.

## 5. Prove User Story 2 — a disappearing subject fails loudly

1. In a scratch copy, remove the agent step from one of the jobs
   `SUBJECT_FLOOR` names (e.g. replace `clarify.yml`'s agent step's `uses:`
   with `actions/checkout@v5`).
2. Re-run step 2 above. Expected: fails, naming that job as no longer
   reachable by derivation even though `SUBJECT_FLOOR` still names it
   (SC-002).
3. Restore the file. Expected: passes again.

## 6. Prove User Story 3 — the four newly-surfaced workflows end in one of two recorded states

For each of `board-loop.yml`, `cleanup.yml`, `rebase.yml`, and
`watchdog.yml`:

    python3 -c "
    import verify_post_agent_credential_refresh as g
    subs = g.derive_subjects()
    for path, job in sorted(subs):
        if '<workflow-file-name>' in path:
            excluded = (path, job) in g.EXCLUSIONS
            print(path, job, 'excluded:', g.EXCLUSIONS.get((path, job), '') if excluded else 'no (inspected)')
    "

(Run from `.github/scripts/`, or adjust the import path — this is a
validation snippet, not a shipped entry point.) Expected: every job printed
is either `excluded: <reason>` or `excluded: no (inspected)` and passing
under step 2's clean run — never a third state (SC-003).

## Rollback check

Reverting this feature's changes to `.github/scripts/verify-post-agent-
credential-refresh.py` and `lint-workflows.yml`'s Gate 68 comment block
alone (leaving the six newly-adopting jobs' workflow changes in place)
should leave `run-local-gates.py` green — the credential-relay code those
jobs gained is independent of who selects them as a subject; only Gate 68's
own coverage of them would regress.
