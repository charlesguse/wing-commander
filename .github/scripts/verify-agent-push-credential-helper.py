#!/usr/bin/env python3
"""Gate 122 - the App private key is never staged where a running agent
step could reach it, and every push-capable agent step's unpublished work
is rescued after the fact.

WHY THIS EXISTS
---------------
specs/071-agent-push-credential set out to fix a defect only visible on a
long-running agent step: the minted App installation token this pipeline
already relies on (spec 052) has a one-hour lifetime, and an agent step
still pushing past it starts failing every `git push` with "Invalid
username or token." An earlier design on this branch (tasks.md T003-T004,
T007-T014) fixed that by installing a `git credential.helper` that minted
a fresh installation token on demand -- which meant staging the GitHub
App's PRIVATE KEY itself, not a derived token, in a file a running agent
step's own shell could read, and exporting its path via $GITHUB_ENV. An
owner-directed redesign (tasks.md's "Maintainer Feedback" section, T057)
deleted that composite as a security defect: a script the agent runs, or a
prompt injection it processes, could read the key and mint installation
tokens for every installation the App is on -- materially worse than the
one-hour, one-repository token the agent already has. The shipped remedy
is narrower: a mid-cycle push may still fail, but
`wing-commander-publish-stranded-commits` -- which runs AFTER the agent
step, with its own credential the agent never saw -- carries anything the
agent could not push itself to the branch. This gate holds both halves of
that redesign in place structurally, on every PR that touches a workflow
or composite-action file.

WHAT THIS CHECKS
----------------
1. The App private key (`secrets.speckit-app-private-key`, or an
   adopter-facing wrapper's own `secrets.WING_COMMANDER_APP_PRIVATE_KEY`,
   dotted or bracket-syntax) is never handed to anything except
   `actions/create-github-app-token@*` (directly, or through the two
   composites that wrap it and expose only a derived token --
   `wing-commander-context`, `_shared/scoped-app-token`). Any other
   consumer -- a plain shell step, a different action, a `run:` block
   that writes the key to a file or to `$GITHUB_ENV` -- fails the gate by
   name. Checked across every `.github/workflows/*.yml` file (not only
   the 8 SUBJECTS below -- watchdog, cleanup, rebase, board-loop and the
   adopter-facing wrappers all stage this same secret), at step level, job
   level and workflow level (a job- or workflow-level `env:` block exposes
   the secret to every step underneath it, with no `uses:` of its own to
   judge trust against), and across the whole job rather than just the
   steps ahead of an agent step: once written to $GITHUB_ENV or a
   $RUNNER_TEMP file, the material outlives the step that wrote it, so a
   write positioned AFTER an agent step in job-step order is no safer
   than one positioned directly ahead of it.
2. Over the 8 stages FR-007 names (SUBJECTS below; auto-update-spec-kit.yml
   scoped to its `e2e-stage` job only), every push-capable agent step
   (`uses: anthropics/claude-code-action@*` whose composed `--allowedTools`
   contains `Bash(git push:*)`) that also has a post-agent
   `wing-commander-context` (or `scoped-app-token`) re-mint in its own
   window has a `wing-commander-publish-stranded-commits` call in that
   SAME window, sharing that re-mint's exact `if:` condition. Absent ->
   FAIL, naming the workflow, job, and agent step.
   Companion clause (auto-update-spec-kit.yml only): its scratch-repository
   publish call attaches to a deterministic step ("Re-mint scratch-
   repository App token (post-agent)"), not an agent step -- `decide` itself
   never pushes at all (FR-025) -- so it is checked on its own terms: that
   named remint step must exist, and a publish call sharing its exact
   `if:` must exist alongside it.
3. No file anywhere in the repository contains a JWT-header/payload
   construction (`"alg":"RS256"` co-occurring with `"typ":"JWT"` in one
   file) -- the on-demand JWT-signing shape the deleted composite used has
   no legitimate home left in this repository at all. A match -> FAIL,
   naming the file. "The repository" is its git-tracked files, not the
   filesystem: an untracked `.wing-commander-pipeline/` checkout beside
   the tree is not repository content (#808).
4. Negative check (FR-025): an agent step in a SUBJECTS job that is NOT
   push-capable must not carry the retry-bound prompt paragraph (matched
   by its distinguishing substring) -- a step that never pushes has no
   push to retry. A match -> FAIL.
5. Loud failure on an unreachable subject (FR-022, Constitution Principle
   VIII): a missing file, an unlocatable job, or zero push-capable agent
   steps found across all 8 files combined all fail the gate by name,
   rather than passing vacuously over an empty result set.

Static structural inspection only (`yaml.safe_load`), the same approach
Gate 68 already uses for the closest-shaped subject in this repository.

Gate 123 (a behavioural companion that drove the deleted composite's own
mint-credential.sh directly) was retired in the same redesign, along with
the script it drove -- see tasks.md's Maintainer Feedback section (T057,
T063) -- rather than leaving the number reserved for a script with no
remaining subject.

Usage: python3 .github/scripts/verify-agent-push-credential-helper.py [--self-test]
"""
import copy
import io
import os
import re
import subprocess
import sys

import yaml

AGENT_ACTION_RE = re.compile(r"^anthropics/claude-code-action@")
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
# This gate's own source quotes the same two literal strings to detect
# them -- excluded from its own scan, by repo-relative path AND by file
# identity (_is_self()), so the exclusion still holds when the gate runs
# from a copy at some other path (#808).
SELF_PATH = ".github/scripts/verify-agent-push-credential-helper.py"

# check 1: the only things ever allowed to see the raw private key. Matches
# both the reusable workflows' own secret name (speckit-app-private-key)
# and the adopter-facing wrappers' secret name
# (WING_COMMANDER_APP_PRIVATE_KEY), dotted (secrets.NAME) or bracket
# (secrets['NAME'] / secrets["NAME"]) syntax.
PRIVATE_KEY_SECRET_RE = re.compile(
    r"secrets(?:\.|\[\s*['\"])(?:speckit-app-private-key|WING_COMMANDER_APP_PRIVATE_KEY)")
TRUSTED_KEY_CONSUMER_RES = (
    re.compile(r"^actions/create-github-app-token@"),
    re.compile(r"/wing-commander-context$"),
    re.compile(r"/_shared/scoped-app-token$"),
)

SINGLE_HOME_SCAN_EXTENSIONS = (".sh", ".yml", ".yaml", ".py")

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


def _is_trusted_key_consumer(uses):
    return any(p.search(uses) for p in TRUSTED_KEY_CONSUMER_RES)


def check_private_key_containment(loaded):
    """check 1: the App private key must never be handed to anything except
    actions/create-github-app-token@* (directly, or through
    wing-commander-context/_shared/scoped-app-token, the two composites
    that wrap it and expose only a derived, short-lived token through
    their own `token` output). This is the structural guard against the
    exact defect the redesign removed: a step that stages the raw key (or
    a path to a file holding it) somewhere a running agent step's own
    shell -- or a script/prompt injection it processes -- could read it,
    whether via $GITHUB_ENV or a file under $RUNNER_TEMP the agent's tool
    allowlist can reach. Scoped to every `.github/workflows/*.yml` file
    (T069 -- not only the 8 SUBJECTS below, since watchdog/cleanup/rebase/
    board-loop and the adopter-facing wrappers stage the same secret), at
    workflow level, job level, and step level, and across the whole job
    rather than just the steps ahead of an agent step: once written to
    $GITHUB_ENV or a file, the material outlives the step that wrote it.
    """
    failures = []
    for path, wf in sorted(loaded.items()):
        if wf is None or not path.startswith(".github/workflows/"):
            continue
        if PRIVATE_KEY_SECRET_RE.search(_step_text(wf.get("env") or {})):
            failures.append(
                f"{path}: workflow-level env: exposes the App private key "
                f"secret to every job and step in the workflow (FR-023 "
                f"security guard, specs/071-agent-push-credential "
                f"Maintainer Feedback).")
        jobs = wf.get("jobs") or {}
        for job_name, job in jobs.items():
            if PRIVATE_KEY_SECRET_RE.search(_step_text((job or {}).get("env") or {})):
                failures.append(
                    f"{path} [{job_name}]: job-level env: exposes the App "
                    f"private key secret to every step in the job (FR-023 "
                    f"security guard, specs/071-agent-push-credential "
                    f"Maintainer Feedback).")
            for step in (job or {}).get("steps") or []:
                if not PRIVATE_KEY_SECRET_RE.search(_step_text(step)):
                    continue
                uses = str((step or {}).get("uses", ""))
                if _is_trusted_key_consumer(uses):
                    continue
                name = (step or {}).get("name", "<unnamed step>")
                failures.append(
                    f"{path} [{job_name}] step {name!r} references "
                    f"the App private key secret through "
                    f"{uses or '(no uses: -- inline run:/env:)'} -- the App "
                    f"private key must never be staged to a file or "
                    f"exported anywhere except as the direct input to "
                    f"actions/create-github-app-token@* or the two "
                    f"composites that wrap it (FR-023 security guard, "
                    f"specs/071-agent-push-credential Maintainer "
                    f"Feedback).")
    return failures


def check_job(path, job_name, job):
    """-> (failures, push_capable_count)."""
    failures = []
    steps = list((job or {}).get("steps") or [])
    steps_by_id = {(s or {}).get("id"): s for s in steps if (s or {}).get("id")}
    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]

    push_capable_count = 0
    next_boundaries = agent_idxs[1:] + [len(steps)]
    for idx, nxt in zip(agent_idxs, next_boundaries):
        step = steps[idx]
        name = (step or {}).get("name", "<unnamed step>")
        after = steps[idx + 1:nxt]
        push_capable = is_push_capable(step, steps_by_id)

        if push_capable:
            push_capable_count += 1
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
            if RETRY_PARAGRAPH_MARKER in _step_text(step):
                failures.append(
                    f"{path} [{job_name}] agent step {name!r} is not push-"
                    f"capable but carries the retry-bound prompt paragraph "
                    f"(FR-025).")

    return failures, push_capable_count


AUTO_UPDATE_SPEC_KIT = ".github/workflows/auto-update-spec-kit.yml"
SCRATCH_REMINT_STEP_NAME = "Re-mint scratch-repository App token (post-agent)"


def check_e2e_scratch_companion(loaded):
    """Companion clause for check 2: auto-update-spec-kit.yml's scratch
    publish call attaches to a deterministic step, not an agent step (T014;
    `decide` never pushes, FR-025) -- checked on its own terms.

    Deliberately narrow, not "every re-mint in a job with no push-capable
    agent step" (code review of this PR tried that generalization and
    reverted it): finalize.yml, classify-and-announce, and tasks-approved
    all have post-agent context re-mints with no push-capable agent step
    in the same job EITHER, but for reasons unrelated to FR-008 scratch-
    repository coverage -- a job-wide rule there produced false positives
    against every one of them. A genuinely new site needing this same
    exception is exactly what the code review of the PR introducing it
    should catch and add here by name, matching how this named exception
    itself was added.
    """
    wf = loaded.get(AUTO_UPDATE_SPEC_KIT)
    if wf is None:
        return []
    job = (wf.get("jobs") or {}).get("e2e-stage")
    if job is None:
        return []
    steps = (job or {}).get("steps") or []
    remint = next((s for s in steps if (s or {}).get("name") == SCRATCH_REMINT_STEP_NAME), None)
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


def _is_self(path, rel):
    if rel == SELF_PATH:
        return True
    try:
        return os.path.samefile(path, os.path.abspath(__file__))
    except OSError:
        return False


def _repo_files(root="."):
    """-> every file check 3 scans, repo-root-relative ('/'-separated).

    The git-tracked files (`git ls-files -z`) when `root` is the top of a
    git working tree -- the repository's content is what is committed, not
    whatever else sits on disk. An implement run checks the pipeline
    repository out at `.wing-commander-pipeline/` beside the tree under
    test, untracked; walking the filesystem scanned that copy of this very
    gate, whose source quotes the two JWT strings, and failed the gate and
    its self-test on every implement cycle (#808, #822, #823). Same idiom
    as verify-stage-tool-lists.py's _glob_has_match(). Outside a git
    working tree (a synthetic fixture) there is nothing to ask, so the
    on-disk files stand in for tracked ones, `.git/` excluded.
    """
    try:
        top = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Only when root IS the top: a fixture directory nested inside some
        # other repository's work tree is not that repository.
        if top.returncode == 0 and os.path.realpath(
                top.stdout.decode("utf-8").strip()) == os.path.realpath(root):
            proc = subprocess.run(
                ["git", "-C", root, "ls-files", "-z"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode == 0:
                return sorted(p for p in proc.stdout.decode("utf-8").split("\0") if p)
    except OSError:
        pass
    rels = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            rels.append(os.path.relpath(
                os.path.join(dirpath, filename), root).replace(os.sep, "/"))
    return sorted(rels)


def check_no_jwt_construction(root="."):
    """check 3 -- no JWT-header/payload construction anywhere in the
    repository (its git-tracked files -- _repo_files()). The deleted
    wing-commander-agent-push-credential composite was the one legitimate
    site that ever needed this shape (signing a GitHub App JWT to mint
    installation tokens on demand, reachable by a running agent step); the
    redesign has no legitimate site left at all, so any match anywhere is
    a regression, not a location to relocate to.
    """
    failures = []
    for rel in _repo_files(root):
        path = os.path.join(root, rel)
        if rel.startswith(".git/") or _is_self(path, rel):
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
                f"(\"alg\":\"RS256\" and \"typ\":\"JWT\") -- the on-demand "
                f"JWT-signing shape the deleted "
                f"wing-commander-agent-push-credential composite used has "
                f"no legitimate home left in this repository (FR-023).")
    return failures


def _iter_workflow_paths(root="."):
    """-> every `.github/workflows/*.yml` path, repo-root-relative -- the
    full scan surface for check 1 (T069), wider than SUBJECTS below."""
    wf_dir = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(wf_dir):
        return []
    return sorted(
        "/".join((".github", "workflows", name))
        for name in os.listdir(wf_dir)
        if name.endswith((".yml", ".yaml")))


def load_all(root="."):
    out = {}
    for path in _iter_workflow_paths(root):
        full = os.path.join(root, path)
        with io.open(full, encoding="utf-8") as fh:
            out[path] = yaml.safe_load(fh) or {}
    for path in SUBJECTS:
        out.setdefault(path, None)
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

    if subjects is SUBJECTS:
        failures += check_private_key_containment(loaded)
        failures += check_e2e_scratch_companion(loaded)
        failures += check_no_jwt_construction(root)
    return failures


# --------------------------------------------------------------------------
# Self-test (fixtures per contracts/agent-push-credential-gate.md)
# --------------------------------------------------------------------------
def mut_delete_publish_after_clarify_agent(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Publish stranded commits (post-agent)"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_non_push_capable_gets_retry_paragraph(loaded):
    """check 4: attach the retry-bound prompt paragraph to a fixture step
    whose allowed-tools carry no Bash(git push:*) -- finalize's summarize
    step, which never pushes (FR-025)."""
    job = loaded[".github/workflows/finalize.yml"]["jobs"]["finalize"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Summarize change and extract remaining manual work"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    step = steps[idx]
    with_block = step.setdefault("with", {})
    prompt = str(with_block.get("prompt", ""))
    with_block["prompt"] = prompt + "\n" + RETRY_PARAGRAPH_MARKER + "\n"


def mut_private_key_leaked_to_untrusted_step(loaded):
    """check 1 (T059): insert a step ahead of implement.yml's cycle agent
    step that hands the App private key to something other than
    actions/create-github-app-token@*/wing-commander-context/
    _shared/scoped-app-token -- the exact shape the deleted
    wing-commander-agent-push-credential composite had."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Implement and converge (cycle)"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    fake = {"name": "Stage App private key for on-demand minting (fixture)",
            "uses": "./.wing-commander-pipeline/.github/actions/some-other-composite",
            "with": {"private-key": "${{ secrets.speckit-app-private-key }}"}}
    steps.insert(idx, fake)


def mut_private_key_in_job_env(loaded):
    """check 1 (T069): a job-level env: block exposing the App private key
    has no uses: of its own to judge trust against, so it must fail
    unconditionally."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    env = job.setdefault("env", {})
    env["FIXTURE_LEAKED_KEY"] = "${{ secrets.speckit-app-private-key }}"


def mut_private_key_bracket_syntax(loaded):
    """check 1 (T069): bracket-syntax secret reference
    (secrets['WING_COMMANDER_APP_PRIVATE_KEY']) handed to an untrusted
    step, ahead of implement.yml's cycle agent step."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
               if (s or {}).get("name") == "Implement and converge (cycle)"), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    fake = {"name": "Stage App private key via bracket syntax (fixture)",
            "uses": "./.wing-commander-pipeline/.github/actions/some-other-composite",
            "with": {"private-key": "${{ secrets['WING_COMMANDER_APP_PRIVATE_KEY'] }}"}}
    steps.insert(idx, fake)


def mut_private_key_out_of_subjects_workflow(loaded):
    """check 1 (T069): staging in a workflow outside the 8 named SUBJECTS
    files -- watchdog.yml's collect job -- must still be caught, since
    check 1 now scans every .github/workflows/*.yml file."""
    job = loaded[".github/workflows/watchdog.yml"]["jobs"]["collect"]
    steps = job["steps"]
    fake = {"name": "Stage App private key (fixture, out-of-SUBJECTS)",
            "uses": "./.wing-commander-pipeline/.github/actions/some-other-composite",
            "with": {"private-key": "${{ secrets.speckit-app-private-key }}"}}
    steps.insert(0, fake)


def self_test(root="."):
    base = load_all(root)
    problems = []

    clean = scan(copy.deepcopy(base), root=root)
    if clean:
        problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))
    else:
        print("[ok] clean tree passes")

    mutations = [
        ("the App private key handed to an untrusted composite ahead of "
         "implement.yml's cycle agent step",
         mut_private_key_leaked_to_untrusted_step,
         ["implement.yml", "must never be staged"]),
        ("the stranded-commit-publish call after clarify.yml's agent step "
         "deleted", mut_delete_publish_after_clarify_agent,
         ["clarify.yml"]),
        ("the retry-bound prompt paragraph attached to a fixture step "
         "whose allowed-tools carry no Bash(git push:*)",
         mut_non_push_capable_gets_retry_paragraph, ["finalize.yml", "FR-025"]),
        ("the App private key exposed via a job-level env: block",
         mut_private_key_in_job_env,
         ["clarify.yml", "job-level env:"]),
        ("the App private key referenced via bracket syntax "
         "(secrets['WING_COMMANDER_APP_PRIVATE_KEY']) to an untrusted step",
         mut_private_key_bracket_syntax,
         ["implement.yml", "must never be staged"]),
        ("the App private key staged in a workflow outside the 8 named "
         "SUBJECTS files (watchdog.yml)",
         mut_private_key_out_of_subjects_workflow,
         ["watchdog.yml", "must never be staged"]),
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
    tmp = tempfile.mkdtemp(prefix="gate122-jwt-")
    try:
        shutil.copytree(root, tmp, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git"))
        rogue = os.path.join(tmp, ".github", "scripts", "rogue-jwt-copy.sh")
        with io.open(rogue, "w", encoding="utf-8") as fh:
            fh.write('header=\'{"alg":"RS256","typ":"JWT"}\'\n')
        broke = check_no_jwt_construction(tmp)
        if any("rogue-jwt-copy.sh" in f for f in broke):
            print("[ok] a JWT-signing block anywhere in the repository: "
                  "caught, naming the file.")
        else:
            problems.append("MUTATION SURVIVED -- a JWT-signing block "
                            f"introduced anywhere was not caught: {broke}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # check 3 (#808) -- scope is the git-tracked files. In a git fixture, a
    # violating file under an untracked `.wing-commander-pipeline/` (the
    # nested pipeline checkout an implement run leaves beside the tree)
    # must NOT be flagged, while the same content tracked must be.
    tmp = tempfile.mkdtemp(prefix="gate122-tracked-")
    try:
        jwt_line = 'header=\'{"alg":"RS256","typ":"JWT"}\'\n'
        nested = os.path.join(tmp, ".wing-commander-pipeline", ".github", "scripts")
        os.makedirs(nested)
        with io.open(os.path.join(nested, "untracked-jwt.sh"), "w",
                     encoding="utf-8") as fh:
            fh.write(jwt_line)
        with io.open(os.path.join(tmp, "tracked-jwt.sh"), "w",
                     encoding="utf-8") as fh:
            fh.write(jwt_line)
        for cmd in (["init", "-q"], ["add", "tracked-jwt.sh"]):
            subprocess.run(["git", "-C", tmp] + cmd, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        broke = check_no_jwt_construction(tmp)
        if any("untracked-jwt.sh" in f for f in broke):
            problems.append("an untracked JWT-signing copy under "
                            ".wing-commander-pipeline/ was flagged -- check "
                            f"3 is scanning beyond git-tracked files: {broke}")
        elif not any(f.startswith("tracked-jwt.sh:") for f in broke):
            problems.append("MUTATION SURVIVED -- a tracked JWT-signing "
                            f"file in a git fixture was not caught: {broke}")
        else:
            print("[ok] check 3 scans git-tracked files only: a tracked "
                  "JWT-signing file is caught, an untracked copy under "
                  ".wing-commander-pipeline/ is not.")
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
        print(f"::error::Gate 122 self-test: {p}")
    if problems:
        return 1
    print("Gate 122 self-test: clean tree passes; each documented mutation fails.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(load_all())
    for f in failures:
        print(f"::error::Gate 122: {f}")
    print(f"Gate 122: agent push-credential helper wiring; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
