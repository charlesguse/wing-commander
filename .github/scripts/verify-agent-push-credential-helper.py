#!/usr/bin/env python3
"""Gate 99 - every push-capable agent step holds a fresh-mint push credential
and, where a later push might rescue it, a deterministic publish step too.

WHY THIS EXISTS
---------------
specs/071-agent-push-credential fixes a defect only visible on a long-running
agent step: the minted App installation token has a one-hour lifetime, and an
agent step running past it starts failing every `git push` with "Invalid
username or token." The fix -- a `wing-commander-agent-push-credential` call
installing a `git config credential.helper` that mints fresh at push time,
plus a deterministic `wing-commander-publish-stranded-commits` rescue for
whatever the agent still could not push itself -- is wiring, and wiring is
exactly the kind of thing a later edit silently drops. This gate catches
that, structurally, on every PR that touches a workflow file.

WHAT THIS CHECKS
----------------
Over the 8 stages FR-007 names (SUBJECTS below; auto-update-spec-kit.yml
scoped to its `e2e-stage` job only), a step is "push-capable" when it is an
agent step (`uses: anthropics/claude-code-action@*`) whose composed
`--allowedTools` text -- resolved either through a referenced
`wing-commander-tool-args` call's own `default-allowed-tools` input, or from
a literal `--allowedTools "..."` in the agent step's own `claude_args`
(auto-update-spec-kit.yml's e2e-stage never calls wing-commander-tool-args at
all) -- contains `Bash(git push:*)`.

1. Every push-capable agent step has a `wing-commander-agent-push-credential`
   call somewhere between the previous agent step in the same job (or the
   job's start) and itself. Absent -> FAIL, naming the workflow, job, and
   agent step.
2. Every push-capable agent step that also has a post-agent
   `wing-commander-context` (or `scoped-app-token`) re-mint in its own
   window (between it and the next agent step, or the job's end) has a
   `wing-commander-publish-stranded-commits` call in that SAME window,
   sharing that re-mint's exact `if:` condition. Absent -> FAIL, naming the
   workflow, job, and agent step.
   Companion clause (auto-update-spec-kit.yml only): its scratch-repository
   publish call attaches to a deterministic step ("Re-mint scratch-
   repository App token (post-agent)"), not an agent step -- `decide` itself
   never pushes (FR-025) -- so it is checked on its own terms: that named
   remint step must exist, and a publish call sharing its exact `if:` must
   exist alongside it.
3. No file outside `.github/actions/wing-commander-agent-push-credential/`
   contains a JWT-header/payload construction matching the same structural
   shape (`"alg":"RS256"` co-occurring with `"typ":"JWT"` in one file) --
   structural, not a byte-identical diff check, so a rewritten copy is still
   caught. A match elsewhere -> FAIL, naming the file.
4. Negative check (FR-025): an agent step in a SUBJECTS job that is NOT
   push-capable must have neither a `wing-commander-agent-push-credential`
   call in its own preceding window NOR the retry-bound prompt paragraph
   (matched by its distinguishing substring) anywhere in its own text. A
   match -> FAIL.
5. Loud failure on an unreachable subject (FR-022, Constitution Principle
   VIII): a missing file, an unlocatable job, or zero push-capable agent
   steps found across all 8 files combined all fail the gate by name,
   rather than passing vacuously over an empty result set.

Static structural inspection only (`yaml.safe_load`), the same approach
Gate 68 already uses for the closest-shaped subject in this repository.
`bash -n` (a separate, existing PR-time gate) already proves
mint-credential.sh's syntax; Gate 100 proves its behaviour. Neither is this
gate's job.

Usage: python3 .github/scripts/verify-agent-push-credential-helper.py [--self-test]
"""
import copy
import io
import os
import re
import sys

import yaml

AGENT_ACTION_RE = re.compile(r"^anthropics/claude-code-action@")
TOOL_ARGS_MARKER = "wing-commander-tool-args"
CRED_HELPER_MARKER = "wing-commander-agent-push-credential"
PUBLISH_MARKER = "wing-commander-publish-stranded-commits"
CONTEXT_REMINT_MARKERS = ("wing-commander-context", "scoped-app-token")
# The canonical retry-bound paragraph's own distinguishing substring
# (research.md D7's exact text, T016) -- unique enough not to collide with
# any other prose in this repository.
RETRY_PARAGRAPH_MARKER = "is a credential problem this pipeline is already handling"

PUSH_GRANT_RE = re.compile(r"(?:^|,)\s*Bash\(git push:\*\)\s*(?:,|$)")
ALLOWED_TOOLS_REF_RE = re.compile(r"steps\.([\w-]+)\.outputs\.allowed-tools")
INLINE_ALLOWED_TOOLS_RE = re.compile(r"--allowedTools\s+\"([^\"]*)\"")

JWT_ALG_RE = re.compile(r'"alg"\s*:\s*"RS256"')
JWT_TYP_RE = re.compile(r'"typ"\s*:\s*"JWT"')
CREDENTIAL_HELPER_DIR = ".github/actions/wing-commander-agent-push-credential"
# This gate's own source quotes the same two literal strings to detect
# them -- excluded from its own scan the same way CREDENTIAL_HELPER_DIR is,
# never a second construction site.
SELF_PATH = ".github/scripts/verify-agent-push-credential-helper.py"

# path -> job names in scope (FR-007's eight named stages, same scope Gate
# 68 already established for the closest-shaped subject).
SUBJECTS = {
    ".github/workflows/intake.yml": ["intake"],
    ".github/workflows/clarify.yml": ["clarify"],
    ".github/workflows/plan.yml": ["plan"],
    ".github/workflows/tasks.yml": ["tasks", "tasks-approved"],
    ".github/workflows/implement.yml": ["implement"],
    ".github/workflows/finalize.yml": ["finalize"],
    ".github/workflows/pr-conversation.yml": ["classify-and-announce", "act"],
    ".github/workflows/auto-update-spec-kit.yml": ["e2e-stage"],
}

AUTO_UPDATE_SPEC_KIT = ".github/workflows/auto-update-spec-kit.yml"
SCRATCH_REMINT_STEP_NAME = "Re-mint scratch-repository App token (post-agent)"


def _is_agent_step(step):
    return bool(AGENT_ACTION_RE.match(str((step or {}).get("uses", ""))))


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _step_text(step):
    return "\n".join(_walk_strings(step))


def _find_step_by_name(steps, name):
    for s in steps or []:
        if (s or {}).get("name") == name:
            return s
    return None


def composed_allowed_tools(step, steps_by_id):
    """-> the agent step's own composed --allowedTools text, or ''."""
    text = _step_text(step)
    m = ALLOWED_TOOLS_REF_RE.search(text)
    if m:
        ref_step = steps_by_id.get(m.group(1))
        if ref_step is None:
            return ""
        return str((ref_step.get("with") or {}).get("default-allowed-tools", ""))
    m2 = INLINE_ALLOWED_TOOLS_RE.search(text)
    if m2:
        return m2.group(1)
    return ""


def is_push_capable(step, steps_by_id):
    return bool(PUSH_GRANT_RE.search(composed_allowed_tools(step, steps_by_id)))


def check_job(path, job_name, job):
    """-> (failures, push_capable_count)."""
    failures = []
    steps = list((job or {}).get("steps") or [])
    steps_by_id = {(s or {}).get("id"): s for s in steps if (s or {}).get("id")}
    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]

    push_capable_count = 0
    prev_boundaries = [-1] + agent_idxs[:-1]
    next_boundaries = agent_idxs[1:] + [len(steps)]
    for idx, prev, nxt in zip(agent_idxs, prev_boundaries, next_boundaries):
        step = steps[idx]
        name = (step or {}).get("name", "<unnamed step>")
        before = steps[prev + 1:idx]
        after = steps[idx + 1:nxt]
        push_capable = is_push_capable(step, steps_by_id)
        has_cred_helper = any(
            CRED_HELPER_MARKER in str((s or {}).get("uses", "")) for s in before)

        if push_capable:
            push_capable_count += 1
            # check 1
            if not has_cred_helper:
                failures.append(
                    f"{path} [{job_name}] agent step {name!r} is push-"
                    f"capable (Bash(git push:*) in its composed allowed-"
                    f"tools) but has no {CRED_HELPER_MARKER} call before it "
                    f"(FR-020 care point 1).")
            # check 2
            remint = next(
                (s for s in after if any(
                    m in str((s or {}).get("uses", "")) for m in CONTEXT_REMINT_MARKERS)),
                None)
            if remint is not None:
                remint_if = str((remint or {}).get("if", ""))
                publishes = [s for s in after if PUBLISH_MARKER in str((s or {}).get("uses", ""))]
                if not any(str((p or {}).get("if", "")) == remint_if for p in publishes):
                    failures.append(
                        f"{path} [{job_name}] agent step {name!r} has a "
                        f"post-agent context re-mint but no "
                        f"{PUBLISH_MARKER} call sharing its exact if: "
                        f"condition {remint_if!r} (FR-020 care point 2).")
        else:
            # check 4 -- negative: nothing spent where nothing can push.
            if has_cred_helper:
                failures.append(
                    f"{path} [{job_name}] agent step {name!r} is not push-"
                    f"capable (no Bash(git push:*) in its composed allowed-"
                    f"tools) but has a {CRED_HELPER_MARKER} call before it "
                    f"(FR-025 -- this feature must spend nothing where the "
                    f"spec says it must not).")
            if RETRY_PARAGRAPH_MARKER in _step_text(step):
                failures.append(
                    f"{path} [{job_name}] agent step {name!r} is not push-"
                    f"capable but carries the retry-bound prompt paragraph "
                    f"(FR-025).")

    return failures, push_capable_count


def check_e2e_scratch_companion(loaded):
    """Companion clause for check 2: auto-update-spec-kit.yml's scratch
    publish call attaches to a deterministic step, not an agent step (T014;
    `decide` never pushes, FR-025) -- checked on its own terms."""
    wf = loaded.get(AUTO_UPDATE_SPEC_KIT)
    if wf is None:
        return []
    job = (wf.get("jobs") or {}).get("e2e-stage")
    if job is None:
        return []
    steps = (job or {}).get("steps") or []
    remint = _find_step_by_name(steps, SCRATCH_REMINT_STEP_NAME)
    if remint is None:
        return [f"{AUTO_UPDATE_SPEC_KIT} [e2e-stage]: no {SCRATCH_REMINT_STEP_NAME!r} "
                f"step found -- cannot check the scratch-repository publish "
                f"companion (FR-020 care point 2, T014's own documented "
                f"exception)."]
    remint_if = str((remint or {}).get("if", ""))
    publishes = [s for s in steps if PUBLISH_MARKER in str((s or {}).get("uses", ""))]
    if not any(str((p or {}).get("if", "")) == remint_if for p in publishes):
        return [f"{AUTO_UPDATE_SPEC_KIT} [e2e-stage]: {SCRATCH_REMINT_STEP_NAME!r} "
                f"has no {PUBLISH_MARKER} call sharing its exact if: "
                f"condition {remint_if!r} (FR-020 care point 2 companion "
                f"clause)."]
    return []


SINGLE_HOME_SCAN_EXTENSIONS = (".sh", ".yml", ".yaml", ".py")


def check_single_home(root="."):
    """check 3 -- no JWT-header/payload construction outside the composite.

    Scoped to files that could actually IMPLEMENT the construction (shell,
    workflow/action YAML, Python) -- this feature's own spec/plan/tasks
    prose (specs/071-agent-push-credential/*.md) quotes the same literal
    header/payload strings to DESCRIBE the mechanism, which would otherwise
    read as a second construction site and false-positive on every PR.
    """
    # os.walk, not glob -- glob's `**`/`*` wildcards skip dot-prefixed
    # entries by default, which would silently never descend into
    # `.github/` at all (the one directory this check most needs to see).
    failures = []
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            paths.append(os.path.join(dirpath, filename))
    for path in sorted(paths):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel.startswith(CREDENTIAL_HELPER_DIR) or rel.startswith(".git/"):
            continue
        if rel == SELF_PATH:
            continue
        if not rel.endswith(SINGLE_HOME_SCAN_EXTENSIONS):
            continue
        try:
            with io.open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        if JWT_ALG_RE.search(text) and JWT_TYP_RE.search(text):
            failures.append(
                f"{rel}: contains a JWT header/payload construction "
                f"(\"alg\":\"RS256\" and \"typ\":\"JWT\") outside "
                f"{CREDENTIAL_HELPER_DIR}/ -- the minting shell has exactly "
                f"one home (FR-023, CLAUDE.md single-home rule).")
    return failures


def load_all(root="."):
    out = {}
    for path in SUBJECTS:
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            out[path] = None
            continue
        with io.open(full, encoding="utf-8") as fh:
            out[path] = yaml.safe_load(fh) or {}
    return out


def scan(loaded, subjects=None, root="."):
    subjects = SUBJECTS if subjects is None else subjects
    failures = []
    total_push_capable = 0
    for path, job_names in subjects.items():
        wf = loaded.get(path)
        if wf is None:
            failures.append(f"{path}: file not found -- cannot reach this "
                            f"subject (FR-022).")
            continue
        jobs = wf.get("jobs") or {}
        for job_name in job_names:
            job = jobs.get(job_name)
            if job is None:
                failures.append(f"{path}: job {job_name!r} not found -- "
                                f"cannot reach this subject (FR-022).")
                continue
            job_failures, n = check_job(path, job_name, job)
            failures += job_failures
            total_push_capable += n

    if total_push_capable == 0:
        failures.append(
            "zero push-capable agent steps were found across the named "
            "workflow files/jobs -- the subject list is misconfigured or "
            "unreachable, never a silent pass over an empty result set "
            "(FR-022).")

    failures += check_e2e_scratch_companion(loaded)
    failures += check_single_home(root)
    return failures


# --------------------------------------------------------------------------
# Self-test (fixtures per contracts/agent-push-credential-gate.md)
# --------------------------------------------------------------------------
def _find_step(job, name):
    for step in (job or {}).get("steps") or []:
        if (step or {}).get("name") == name:
            return step
    return None


def mut_delete_cred_helper_before_retry(loaded):
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Install fresh-mint push credential (retry)"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_delete_publish_after_clarify_agent(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Publish stranded commits (post-agent)"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_no_grant_gets_cred_helper(loaded):
    """check 4: attach the credential-helper call to a fixture agent step
    whose allowed-tools carry no Bash(git push:*) -- finalize's summarize."""
    job = loaded[".github/workflows/finalize.yml"]["jobs"]["finalize"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Summarize change and extract remaining manual work"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    fake = {"name": "Install fresh-mint push credential (finalize, fixture)",
            "uses": "./.wing-commander-pipeline/.github/actions/wing-commander-agent-push-credential",
            "with": {"app-id": "x"}}
    steps.insert(idx, fake)


def self_test(root="."):
    base = load_all(root)
    problems = []

    clean = scan(copy.deepcopy(base), root=root)
    if clean:
        problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))
    else:
        print("[ok] clean tree passes")

    mutations = [
        ("the credential-helper call ahead of implement.yml's retry agent "
         "step deleted", mut_delete_cred_helper_before_retry,
         ["implement.yml", "implement", "retry"]),
        ("the stranded-commit-publish call after clarify.yml's agent step "
         "deleted", mut_delete_publish_after_clarify_agent,
         ["clarify.yml"]),
        ("the credential-helper call attached to a fixture agent step "
         "whose allowed-tools carry no Bash(git push:*)",
         mut_no_grant_gets_cred_helper, ["finalize.yml", "FR-025"]),
    ]
    for label, apply_mutation, expect_substrings in mutations:
        mutated = copy.deepcopy(base)
        apply_mutation(mutated)
        if mutated == base:
            problems.append(f"mutation {label!r} changed nothing -- the "
                            f"code it edits was rewritten; update the "
                            f"mutation.")
            continue
        broke = scan(mutated, root=root)
        joined = " | ".join(broke)
        if not broke or not all(s in joined for s in expect_substrings):
            problems.append(f"MUTATION SURVIVED (or wrong reason) -- "
                            f"reintroducing {label!r} produced: {broke or 'nothing'}")
        else:
            print(f"[ok] {label}: {len(broke)} assertion(s) fail.")

    # check 3 -- duplicate the JWT-signing block into a second file.
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="gate99-jwt-")
    try:
        shutil.copytree(root, tmp, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git"))
        rogue = os.path.join(tmp, ".github", "scripts", "rogue-jwt-copy.sh")
        with io.open(rogue, "w", encoding="utf-8") as fh:
            fh.write('header=\'{"alg":"RS256","typ":"JWT"}\'\n')
        broke = check_single_home(tmp)
        if any("rogue-jwt-copy.sh" in f for f in broke):
            print("[ok] duplicated JWT-signing block outside the composite "
                  "directory: caught, naming the file.")
        else:
            problems.append("MUTATION SURVIVED -- a duplicated JWT-signing "
                            f"block outside the composite directory was not "
                            f"caught: {broke}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # check 5 -- subject-list mutations.
    ninth = copy.deepcopy(SUBJECTS)
    ninth["nonexistent-ninth-workflow.yml"] = ["some-job"]
    broke = scan(copy.deepcopy(base), subjects=ninth, root=root)
    if any("nonexistent-ninth-workflow.yml" in f for f in broke):
        print("[ok] subject list pointed at a 9th, nonexistent file: caught.")
    else:
        problems.append("MUTATION SURVIVED -- a 9th nonexistent subject "
                        f"file was not caught: {broke}")

    broke = scan(copy.deepcopy(base), subjects={}, root=root)
    if any("zero push-capable" in f for f in broke):
        print("[ok] subject list pointed at zero files: caught.")
    else:
        problems.append("MUTATION SURVIVED -- an empty subject list was "
                        f"not caught: {broke}")

    for p in problems:
        print(f"::error::Gate 99 self-test: {p}")
    if problems:
        return 1
    print("Gate 99 self-test: clean tree passes; each documented mutation fails.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(load_all())
    for f in failures:
        print(f"::error::Gate 99: {f}")
    print(f"Gate 99: agent push-credential helper wiring; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
