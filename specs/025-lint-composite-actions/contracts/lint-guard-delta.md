# Contract Delta: `lint-workflows.yml` (Lint Composite Action Scripts)

There is no prior contract document for `lint-workflows.yml` — this is the
first spec to touch it. This delta describes only what this feature adds or
changes; everything else in the file (Gate 2 `workflow_run` name resolution,
Gate 3 permission-grant checking, the `registered` job / Gate 1) is
unchanged and out of scope (spec Assumptions).

## Trigger contract addition

```yaml
on:
  pull_request:
    paths: [".github/workflows/**", ".github/actions/**"]  # was: [".github/workflows/**"]
```

**Purpose**: FR-002 — a pull request that changes only a composite action
must trigger the `lint` job, not only the `registered` job's unrelated
triggers (`push`/`schedule`/`workflow_dispatch`, which stay unchanged since
Gate 1 does not apply to composite actions).

**Behavior**: `paths:` entries are inclusive-OR — a pull request matching
either glob (workflow-only, composite-action-only, or both) runs the `lint`
job (spec User Story 2, Acceptance Scenarios 1 and 2).

## Check-step contract addition: composite action discovery and collection

Inside the existing "Parse YAML and bash -n every run block" step's inline
Python script:

```python
import glob, subprocess, sys, re, yaml

failures = 0

def check_script(f, step_identity, run):
    """Neutralize expression interpolation, then bash -n. Returns 1 on
    failure (and prints the annotation), 0 otherwise."""
    script = re.sub(r"\$\{\{[^}]*\}\}", "EXPR", run)
    r = subprocess.run(["bash", "-n"], input=script.encode(), capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode().strip().replace("%", "%25").replace("\n", "%0A")
        print(f"::error file={f}::{step_identity}: {err}")
        return 1
    return 0

# Existing: reusable-workflow files
for f in sorted(glob.glob(".github/workflows/*.yml")):
    try:
        wf = yaml.safe_load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"::error file={f}::YAML parse failure: {e}")
        failures += 1
        continue
    for jname, job in (wf.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            run = step.get("run")
            if not run:
                continue
            name = step.get("name", f"step {i}")
            failures += check_script(f, f"{jname} / {name}", run)

# New: composite action files, any depth, both extensions (FR-008)
action_files = sorted(
    glob.glob(".github/actions/**/action.yml", recursive=True)
    + glob.glob(".github/actions/**/action.yaml", recursive=True)
)
for f in action_files:
    try:
        action = yaml.safe_load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"::error file={f}::YAML parse failure: {e}")
        failures += 1
        continue
    steps = (action.get("runs") or {}).get("steps") or []
    for i, step in enumerate(steps):
        run = step.get("run")
        if not run:
            continue
        name = step.get("name", f"step {i}")
        failures += check_script(f, name, run)

print(f"Checked all run blocks; {failures} failure(s).")
sys.exit(1 if failures else 0)
```

**Purpose**: FR-001, FR-003, FR-004, FR-008, FR-009 — collect and
syntax-check composite-action embedded scripts through the identical
neutralization/`bash -n` path already used for workflow scripts, discovered
recursively at any depth, with parse-failure parity.

**Behavior**:

1. Both script sources (workflow job steps, composite action steps) share one
   `check_script` helper and one `failures` counter — a syntax error in
   either source fails the run and emits an `::error file={f}::{identity}:
   {stderr}` annotation identifying the offending file and step (FR-005).
2. A composite action file that fails `yaml.safe_load` is reported and
   counted exactly like a malformed workflow file (FR-009) — never silently
   skipped, never partially checked.
3. An action whose `runs.steps` is empty or absent (container/JavaScript
   actions, or a composite action with no `run:` steps) contributes zero
   scripts and zero failures — no `using:` branch needed (research.md R4).
4. This change is purely additive to the existing loop over
   `.github/workflows/*.yml` — that loop's logic, order, and output format
   are byte-for-byte unchanged, satisfying FR-007 (no regression).

**Permissions**: unchanged — the `lint` job still declares only
`contents: read`; the check reads files already in the checkout, writes
nothing beyond `::error` annotations.

**Non-goals**: this step still performs a syntax check only
(`bash -n`, no execution) — it does not exercise `errexit`/`pipefail`
runtime behavior of composite `shell: bash` steps, and does not become
errexit-safe as a side effect of this extension (FR-006). Runtime-semantics
coverage via a fixture harness remains explicitly out of scope (spec
Assumptions).

## Documentation contract addition: header comment

The file's existing header comment (the block explaining why each gate
exists) gains one clause stating the syntax-only limitation, so a maintainer
reading "the lint guard's own documentation" (spec User Story 3) finds it in
the same place the guard's other scope/limitation statements already live
(research.md R6). No new documentation file is introduced.
