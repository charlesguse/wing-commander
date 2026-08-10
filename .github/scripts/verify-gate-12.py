#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 12.

Gate 12 asserts that every `gh`/API call a workflow makes runs under a token
whose permissions actually cover what it touches — the class of defect
behind spec 005's `gh workflow run` 403 and
specs/033-pr-conversation-commands T062/T063 (a `gh run cancel`/`gh run
list` pair that inherited the App token, which per docs/setup.md has no
Actions permission, and 403'd; T062's variant went further and reported that
403 to a maintainer as an "already completed" outcome). All three were found
by accident — a maintainer noticing a stall, not a check — and T062/T063
survived five pipeline cycles, a full quickstart desk-check, and three
rounds of executing the shipped shell against synthetic inputs first.

A gate that never fires is indistinguishable from one whose detection logic
is broken (gate 5 exists because that already happened once — a verifier sat
green for weeks checking a filter that did not ship). So this script feeds
Gate 12 synthetic workflow trees that each carry one known-bad call (or one
known-fine one) and asserts the verdict, including what the error text
names.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here, the same way verify-gate-6.py and
verify-gate-7.py do it. There is no second copy to fall out of sync — if the
shipped gate changes, this runs the changed gate.

Usage: python3 .github/scripts/verify-gate-12.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 12"
HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 12's python source, read out of the shipped workflow."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    run = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if name.startswith(STEP_PREFIX) and "self-test" not in name:
                run = step.get("run")
    if run is None:
        sys.exit(f"::error file={path}::verify-gate-12 could not find a step named "
                 f"{STEP_PREFIX!r}. If it was renamed, update this script and the "
                 f"workflow together.")

    lines = run.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == HEREDOC_OPEN)
        end = next(i for i, l in enumerate(lines)
                   if i > start and l.strip() == HEREDOC_CLOSE)
    except StopIteration:
        sys.exit(f"::error file={path}::verify-gate-12 found the {STEP_PREFIX} step "
                 f"but not the {HEREDOC_OPEN} ... {HEREDOC_CLOSE} block it keys on — "
                 f"the step's shape has changed.")
    return "\n".join(lines[start + 1:end]) + "\n"


# ---------------------------------------------------------------- fixtures
#
# Kept deliberately tiny and self-contained rather than mutating the real
# fleet: the real files change for unrelated reasons, and a self-test that
# breaks on every unrelated edit gets deleted rather than fixed.

DOCS_OK = """\
## 1. Create the wing-commander-bot GitHub App

1. GitHub -> Settings

2. **Repository permissions**:
   - Contents: **Read and write**
   - Issues: **Read and write**
   - Pull requests: **Read and write**
   - Everything else: No access
"""

APP_ENV = 'GH_TOKEN: ${{ steps.ctx.outputs.token }}'
DEFAULT_ENV = 'GH_TOKEN: ${{ github.token }}'


def wf(run_body, job_perms="", job_env="", name="w"):
    perms = f"    permissions:\n{job_perms}" if job_perms else ""
    env = f"    env:\n{job_env}" if job_env else ""
    return (f"name: {name}\n"
            f"on:\n  workflow_dispatch: {{}}\n"
            f"jobs:\n  work:\n    runs-on: ubuntu-latest\n{perms}{env}"
            f"    steps:\n      - name: step\n        env:\n"
            f"{run_body}\n")


def step(env_lines, run_lines):
    env = "".join(f"          {l}\n" for l in env_lines)
    run = "        run: |\n" + "".join(f"          {l}\n" for l in run_lines)
    return env + run


ACTIONS_WRITE = "      actions: write\n"
ACTIONS_READ = "      actions: read\n"
ISSUES_WRITE = "      issues: write\n"


def mkcase(job_perms, job_env, env_lines, run_lines, docs=DOCS_OK):
    return {
        ".github/workflows/w.yml": wf(step(env_lines, run_lines),
                                      job_perms=job_perms, job_env=job_env),
        "docs/setup.md": docs,
    }


CASES = [
    # name, files, expect_fail, must_mention

    ("healthy: App-token issue comment (App has Issues)",
     mkcase("", "", [APP_ENV], ['gh issue comment "$N" --body hi']),
     False, ()),

    ("the T062/T063 defect: App-token `gh run cancel` (App has no Actions)",
     mkcase("", "", [APP_ENV], ['gh run cancel "$RUN_ID" -R "$REPO"']),
     True, ("run cancel", "App token", "actions")),

    ("the T062/T063 fix: per-command prefix routes to github.token, which "
     "the job grants actions:write",
     mkcase(ACTIONS_WRITE, "", [APP_ENV, "DISPATCH_TOKEN: ${{ github.token }}"],
            ['GH_TOKEN="$DISPATCH_TOKEN" gh run cancel "$RUN_ID" -R "$REPO"']),
     False, ()),

    ("github.token call with no permissions: block anywhere to resolve "
     "(inherits the repo default) is reported as unverified, not silently "
     "passed and not failed on a guess - same rule Gate 3 already uses",
     mkcase("", "", [DEFAULT_ENV], ['gh run list -R "$REPO"']),
     False, ("cannot resolve",)),

    ("github.token call with only read granted cannot satisfy a write call",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV], ['gh run cancel "$RUN_ID" -R "$REPO"']),
     True, ("run cancel", "actions")),

    ("github.token call with read granted satisfies a read call",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV], ['gh run list -R "$REPO"']),
     False, ()),

    ("gh api under the App token needing Actions (the watchdog collector class)",
     mkcase("", "", [APP_ENV],
            ['jobs="$(gh api "repos/$REPO/actions/runs/$RUN_ID/jobs")"']),
     True, ("actions", "App token")),

    ("gh api under the App token for a permission it DOES have (Issues)",
     mkcase("", "", [APP_ENV],
            ['gh api -X PATCH "repos/$REPO/issues/comments/$ID" -f body=hi']),
     False, ()),

    ("cross-repository gh api call is out of scope (different owner/repo)",
     mkcase("", "", [DEFAULT_ENV],
            ['releases="$(gh api repos/github/spec-kit/releases)"']),
     False, ()),

    ("unrecognised subcommand fails loudly rather than passing silently",
     mkcase("", "", [APP_ENV], ['gh totallynew thing "$X"']),
     True, ("totallynew", "SUBCOMMAND_PERMS")),

    ("an unresolvable gh api path (traced to a $(...) computed value) fails "
     "loudly rather than being silently skipped",
     mkcase("", "", [APP_ENV], ['gh api -X PATCH "$(compute_path)" -f body=hi']),
     True, ("cannot resolve",)),

    ("no false positive: a gh mention inside an echo string never runs",
     mkcase("", "", [APP_ENV],
            ['echo "   gh run cancel $RUN_ID -R $REPO"']),
     False, ()),

    ("no false positive: a gh mention inside a `#` comment never runs",
     mkcase("", "", [APP_ENV],
            ['# gh run cancel is mentioned here for humans only',
             'gh issue view "$N"']),
     False, ()),

    ("no false positive: a gh mention inside a heredoc body (data for "
     "another interpreter) never runs",
     mkcase("", "", [APP_ENV],
            ["python3 - <<'PYEOF'",
             'print("gh run cancel $RUN_ID")',
             "PYEOF"]),
     False, ()),

    ("agent tool grant: Bash(gh run view:*) handed to an agent step whose "
     "token is the App token 403s exactly like a deterministic call would",
     {".github/workflows/w.yml": (
         "name: w\non:\n  workflow_dispatch: {}\njobs:\n  work:\n"
         "    runs-on: ubuntu-latest\n    steps:\n"
         "      - name: Compose tool args\n"
         "        uses: ./.github/actions/wing-commander-tool-args\n"
         "        with:\n"
         '          default-allowed-tools: "Read,Bash(gh run view:*)"\n'
         "      - name: Agent step\n"
         "        uses: anthropics/claude-code-action@v1\n"
         "        env:\n"
         f"          {APP_ENV}\n"),
      "docs/setup.md": DOCS_OK},
     True, ("agent tool grant", "run view", "App token")),

    ("agent tool grant under github.token with the matching job permission "
     "is fine",
     {".github/workflows/w.yml": (
         "name: w\non:\n  workflow_dispatch: {}\njobs:\n  work:\n"
         "    runs-on: ubuntu-latest\n    permissions:\n      actions: read\n"
         "    steps:\n"
         "      - name: Compose tool args\n"
         "        uses: ./.github/actions/wing-commander-tool-args\n"
         "        with:\n"
         '          default-allowed-tools: "Read,Bash(gh run view:*)"\n'
         "      - name: Agent step\n"
         "        uses: anthropics/claude-code-action@v1\n"
         "        env:\n"
         f"          {DEFAULT_ENV}\n"),
      "docs/setup.md": DOCS_OK},
     False, ()),
]


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate12_")
    gate_path = os.path.join(root, "gate12.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            for relpath, body in files.items():
                full = os.path.join(case_dir, *relpath.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                io.open(full, "w", encoding="utf-8").write(body)

            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            out = (proc.stdout or "") + (proc.stderr or "")
            fired = proc.returncode != 0

            problems = []
            if fired != expect_fail:
                problems.append(
                    f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                    f"it {'FAILED' if fired else 'PASSED'}")
            for token in must_mention:
                if token not in out:
                    problems.append(f"error text never mentions {token!r}")

            if problems:
                failures.append((name, problems, out.strip()))
                print(f"FAIL  {name}")
                for p in problems:
                    print(f"        - {p}")
                for line in out.strip().splitlines():
                    print(f"        | {line}")
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 12 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate "
              f"12's detection logic does not do what its name claims, so a "
              f"green Gate 12 on the real fleet means nothing.")
        return 1
    print(f"Gate 12 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
