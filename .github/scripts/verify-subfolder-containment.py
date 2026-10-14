#!/usr/bin/env python3
"""Gate: subfolder containment (spec 114 FR-021, FR-022).

Runs the real shell of two composites against fixtures/project-containment/
cases.json:
  * wing-commander-tool-args -- the project-aware .claude/ and .git/ denies,
    which must hold even when no-write-paths is overridden by the caller;
  * wing-commander-containment -- fails on any change outside the project
    folder, passes for changes (moves, child-index edits) inside it.
  * _shared/containment.sh pre-push -- the hook an agent that pushes itself
    (pr-conversation's act leg) runs: refuses a push carrying a change
    outside the folder, allows one inside it and a branch deletion.
  * wing-commander-publish-stranded-commits -- the !cancelled() rescue after
    the containment check: publishes nothing when the unpushed commits touch
    a path outside the folder, and is handed the job's project wherever a
    containment check runs.
It also checks that every workflow step running claude-code-action in a
workflow that composes tool-args consumes the composed allowed-tools output,
and that every Edit/Write agent in a project-wired job has a containment
guard (the composite, or a step calling _shared/containment.sh).

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIONS = os.path.join(ROOT, ".github", "actions")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-containment", "cases.json")


def action_script(name):
    with open(os.path.join(ACTIONS, name, "action.yml"), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["runs"]["steps"][0]["run"]


def run_script(script, env, cwd, name):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "output")
        summary = os.path.join(tmp, "summary")
        for p in (out, summary):
            open(p, "w", encoding="utf-8").close()
        full = dict(os.environ)
        full.update(env)
        full.update(
            GITHUB_OUTPUT=out,
            GITHUB_STEP_SUMMARY=summary,
            GITHUB_ACTION_PATH=os.path.join(ACTIONS, name),
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=full, check=False)
        with open(out, encoding="utf-8") as fh:
            return r, fh.read()


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def tool_args_env():
    with open(os.path.join(ACTIONS, "wing-commander-tool-args", "action.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)["runs"]["steps"][0]["env"]


def tool_args(case, script):
    env = {
        "STEP_LABEL": "fixture",
        "DEFAULT_ALLOWED": case.get("default_allowed", "Read,Edit,Write"),
        "DEFAULT_DISALLOWED": "",
        "EXTRA_DISALLOWED": "",
        "ALLOWED_OVERRIDE": "__unset__",
        "DISALLOWED_OVERRIDE": case.get("disallowed_override", "__unset__"),
        "NO_WRITE_PATHS": case.get("no_write_paths", ""),
        "PROJECT": case["project"],
        "PROJECT_DENY": case.get("project_deny_tools", ""),
        # The step's own constant, read from action.yml as the runner sets it.
        "HOOK_BYPASS_DENIES": tool_args_env()["HOOK_BYPASS_DENIES"],
        "PROJECT_API_DENY": tool_args_env()["PROJECT_API_DENY"],
        "EXTRA_ALLOWED": case.get("extra_allowed", ""),
    }
    r, out = run_script(script, env, ROOT, "wing-commander-tool-args")
    if r.returncode != 0:
        return None, None, r.stderr
    m = re.search(r"^disallowed-tools=(.*)$", out, re.M)
    a = re.search(r"^allowed-tools=(.*)$", out, re.M)
    s = re.search(r"^shell-commands=(.*)$", out, re.M)
    if s and any(f"`{c}`" in s.group(1) for c in case.get("not_stated", [])):
        return None, None, f"the tooling statement still names one of {case['not_stated']!r}: {s.group(1)!r}"
    return (m.group(1) if m else ""), (a.group(1) if a else ""), ""


def contain(case, script):
    with tempfile.TemporaryDirectory() as top:
        origin = os.path.join(top, "origin.git")
        tmp = os.path.join(top, "work")
        os.makedirs(tmp)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True, capture_output=True)
        git(tmp, "init", "-q", "-b", "main")
        git(tmp, "config", "user.email", "g@example.invalid")
        git(tmp, "config", "user.name", "gate")
        for rel in case["base_files"]:
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("x\n")
        git(tmp, "add", "-A")
        git(tmp, "commit", "-q", "-m", "base")
        # The remote's main is the default branch the merge-base leg diffs
        # from (read with ls-remote, never origin/main).
        git(tmp, "remote", "add", "origin", origin)
        git(tmp, "push", "-q", "origin", "main")
        if case.get("remote_branch"):
            # Content already on another remote branch, outside P: it must
            # still be flagged when it arrives through a merge.
            git(tmp, "checkout", "-q", "-b", "other")
            for rel in case["remote_branch"]:
                with open(os.path.join(tmp, rel), "a", encoding="utf-8") as fh:
                    fh.write("o\n")
            git(tmp, "commit", "-q", "-am", "other")
            git(tmp, "push", "-q", "origin", "other")
            git(tmp, "checkout", "-q", "main")
            git(tmp, "merge", "-q", "--no-ff", "-m", "merge other", "other")
        if case.get("suffix_collision"):
            # MF-50: a remote branch whose name ends in /refs/heads/main also
            # matches `git ls-remote origin refs/heads/main`.
            git(tmp, "push", "-q", "origin", "HEAD:refs/heads/x/refs/heads/main")
        if case.get("forged_tracking_ref"):
            # The agent points origin/main at its own tip: the check must
            # still diff from the tip the remote reports.
            git(tmp, "update-ref", "refs/remotes/origin/main", "HEAD")
        if case.get("no_remote"):
            git(tmp, "remote", "remove", "origin")
        if case.get("earlier_run"):
            # A commit an earlier (restarted) run already made on the branch:
            # it precedes base-sha, so only the merge-base leg sees it.
            for rel in case["earlier_run"]:
                path = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("r\n")
            git(tmp, "add", "-A")
            git(tmp, "commit", "-q", "-m", "earlier run")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True, check=True).stdout.strip()
        helpers = ""
        if case.get("snapshot"):
            # MF-48: install-pre-push's helper copies and its pre-agent
            # snapshot of the remote's branch heads.
            helpers = os.path.join(top, "helpers")
            os.makedirs(helpers)
            for name in ("containment.sh", "project-name.sh", "git-push-hardening.sh"):
                with open(os.path.join(ACTIONS, "_shared", name), encoding="utf-8") as src, \
                        open(os.path.join(helpers, name), "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            heads = subprocess.run(["git", "ls-remote", "origin", "refs/heads/*"], cwd=tmp,
                                   capture_output=True, text=True, check=True).stdout
            if not case.get("drop_snapshot"):
                with open(os.path.join(helpers, "remote-heads.before"), "w", encoding="utf-8") as fh:
                    fh.write(heads)
        for ref, files in case.get("agent_pushes", {}).items():
            # The agent commits on another branch and pushes it itself.
            git(tmp, "checkout", "-q", "-b", "agent-side", base)
            for rel in files:
                path = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("p\n")
            git(tmp, "add", "-A")
            git(tmp, "commit", "-q", "-m", "agent push")
            git(tmp, "push", "-q", "origin", "HEAD:refs/heads/" + ref)
            git(tmp, "checkout", "-q", "main")
            git(tmp, "branch", "-q", "-D", "agent-side")
        for ref, files in case.get("concurrent_pushes", {}).items():
            # Another lifecycle's run moves its own branch meanwhile, from a
            # clone this checkout never fetches.
            other = os.path.join(top, "other-" + ref.replace("/", "-"))
            subprocess.run(["git", "clone", "-q", origin, other], check=True, capture_output=True)
            git(other, "config", "user.email", "g@example.invalid")
            git(other, "config", "user.name", "other")
            for rel in files:
                path = os.path.join(other, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("c\n")
            git(other, "add", "-A")
            git(other, "commit", "-q", "-m", "concurrent")
            git(other, "push", "-q", "origin", "HEAD:refs/heads/" + ref)
        for rel in case.get("modify", []):
            with open(os.path.join(tmp, rel), "a", encoding="utf-8") as fh:
                fh.write("y\n")
        for rel in case.get("create", []):
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("z\n")
        for src, dst in case.get("move", []):
            os.makedirs(os.path.dirname(os.path.join(tmp, dst)), exist_ok=True)
            git(tmp, "mv", src, dst)
        for src, dst in case.get("copy", []):
            os.makedirs(os.path.dirname(os.path.join(tmp, dst)), exist_ok=True)
            with open(os.path.join(tmp, src), encoding="utf-8") as fh:
                body = fh.read()
            with open(os.path.join(tmp, dst), "w", encoding="utf-8") as fh:
                fh.write(body)
        for rel in case.get("remove", []):
            os.remove(os.path.join(tmp, rel))
        for rel in case.get("nested_repo", []):
            # An untracked nested git repository, like the trusted checkout.
            path = os.path.join(tmp, rel)
            os.makedirs(path, exist_ok=True)
            git(path, "init", "-q")
            with open(os.path.join(path, "f.txt"), "w", encoding="utf-8") as fh:
                fh.write("n\n")
        if case.get("commit"):
            git(tmp, "add", "-A")
            git(tmp, "commit", "-q", "-m", "agent")
        env = {"PROJECT": case["project"], "BASE_SHA": base, "DEFAULT_BRANCH": case.get("default_branch", "main"),
               "HELPERS_DIR": helpers}
        r, _ = run_script(script, env, tmp, "wing-commander-containment")
        return r


def check_wiring(errors):
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            text = fh.read()
        if "wing-commander-tool-args" not in text or "claude-code-action" not in text:
            continue
        doc = yaml.safe_load(text)
        for job_name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            composes = any("wing-commander-tool-args" in str(s.get("uses", "")) for s in steps)
            if not composes:
                continue
            for s in steps:
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                if "outputs.allowed-tools" not in json.dumps(s):
                    errors.append(f"{fn}:{job_name}: claude-code-action step {s.get('name')!r} does not consume tool-args")


def writes(tool_list):
    return any(t.strip().split("(")[0] in ("Edit", "Write") for t in tool_list.split(","))


def check_guard_coverage(errors, wf_dir=None):
    """FR-021: every Edit/Write agent in a project-wired job is followed by a
    containment guard -- the wing-commander-containment composite, or a run
    step that calls the test's single home, _shared/containment.sh (the
    pre-push hook an agent that pushes itself needs, or rebase's scope
    check). A job is project-wired when it resolves a project or hands one to
    wing-commander-tool-args."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            steps = job.get("steps") or []
            grants = {}
            wired = False
            for s in steps:
                uses = str(s.get("uses", ""))
                if uses.endswith("/wing-commander-project"):
                    wired = True
                if uses.endswith("/wing-commander-tool-args"):
                    w = s.get("with") or {}
                    if str(w.get("project", "")).strip():
                        wired = True
                    if s.get("id"):
                        grants[s["id"]] = str(w.get("default-allowed-tools", ""))
            if not wired:
                continue
            for i, s in enumerate(steps):
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                ids = re.findall(r"steps\.([\w-]+)\.outputs\.allowed-tools", json.dumps(s))
                if not any(writes(grants.get(x, "")) for x in ids):
                    continue
                guarded = any(
                    str(t.get("uses", "")).endswith("/wing-commander-containment")
                    or "_shared/containment.sh" in str(t.get("run", ""))
                    for j, t in enumerate(steps)
                    if j != i
                )
                if not guarded:
                    errors.append(f"{fn}:{job_name}: Edit/Write agent {s.get('name')!r} in a project-wired job has no containment guard (FR-021)")
                else:
                    covered += 1
                # MF-10: for an agent granted `git push`, the post-agent check
                # comes after a push it made itself, so a pre-push hook must
                # already be in place.
                if not any("Bash(git push" in grants.get(x, "") for x in ids):
                    continue
                hooked = any(
                    str(t.get("uses", "")).endswith("/wing-commander-containment")
                    and str((t.get("with") or {}).get("mode", "")) == "install-pre-push"
                    for t in steps[:i]
                )
                if not hooked:
                    errors.append(f"{fn}:{job_name}: Edit/Write agent {s.get('name')!r} in a project-wired job runs with no containment pre-push hook installed before it (FR-021)")
    return covered


GUIDANCE_SPLICE = re.compile(r"\S\$\{\{ steps\.[\w-]+\.outputs\.(?:prompt-paragraph|routing-notes) \}\}")


def check_prompt_guidance(errors, wf_dir=None):
    """FR-006 (MF-12): every Edit/Write agent in a project-wired job reads
    the project folder's own constitution, extension hooks and skills, so
    its prompt carries the deterministic project paragraph (the
    wing-commander-project `prompt-paragraph` output; intake's own
    `routing-notes`),
    spliced onto the end of a prompt line so a root prompt gains no line."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            steps = job.get("steps") or []
            grants, wired = {}, False
            for s in steps:
                uses = str(s.get("uses", ""))
                if uses.endswith("/wing-commander-project"):
                    wired = True
                if uses.endswith("/wing-commander-tool-args"):
                    w = s.get("with") or {}
                    wired = wired or bool(str(w.get("project", "")).strip())
                    if s.get("id"):
                        grants[s["id"]] = str(w.get("default-allowed-tools", ""))
            if not wired:
                continue
            for s in steps:
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                ids = re.findall(r"steps\.([\w-]+)\.outputs\.allowed-tools", json.dumps(s))
                if not any(writes(grants.get(x, "")) for x in ids):
                    continue
                prompt = str((s.get("with") or {}).get("prompt", ""))
                if not GUIDANCE_SPLICE.search(prompt):
                    errors.append(f"{fn}:{job_name}: Edit/Write agent {s.get('name')!r} in a project-wired job carries no project paragraph spliced onto a prompt line (FR-006)")
                else:
                    covered += 1
    return covered


def check_guidance_output(errors):
    """The paragraph itself: it names the folder's constitution, extension
    hooks and skills, and the root gets nothing."""
    with open(os.path.join(ACTIONS, "wing-commander-project", "action.yml"), encoding="utf-8") as fh:
        resolve = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    for identity, want in (("ideas/alpha/001-x", True), ("001-x", False)):
        env = {"GH_TOKEN": "", "ROUTING_PREFIX": "", "ISSUE": "", "IDENTITY": identity,
               "IDENTITY_KIND": "slug", "CHECK_FOLDER": "false", "FINDINGS_LABEL_PREFIX": ""}
        r, out = run_script(resolve, env, ROOT, "wing-commander-project")
        m = re.search(r"^prompt-paragraph<<(\w+)\n(.*?)\n\1$", out, re.M | re.S)
        text = m.group(2) if m else ""
        if r.returncode != 0:
            errors.append(f"guidance: resolve failed for {identity!r}: {r.stderr!r}")
        elif want:
            for path in ("ideas/alpha/.specify/memory/constitution.md", "ideas/alpha/.specify/extensions.yml",
                         "ideas/alpha/.claude/skills/<name>/SKILL.md"):
                if path not in text:
                    errors.append(f"guidance: the project paragraph does not name {path}")
            if not text.startswith("\n\n") or not text.endswith("\n"):
                errors.append("guidance: the project paragraph does not carry its own blank lines")
        elif m or "prompt-paragraph=\n" not in out:
            errors.append(f"guidance: the root gets a paragraph: {out!r}")


# Jobs whose last checkout is of the ref an earlier folder check already
# read: intake's agent works on the default branch the routing gate checked
# the folder on (with check-folder on), re-checked out only as the bot.
STALE_FOLDER_EXEMPT = {("intake.yml", "intake")}


def is_root_checkout(step):
    w = step.get("with") or {}
    return str(step.get("uses", "")).startswith("actions/checkout@") and w.get("path") in (None, "", ".", "./")


def is_folder_check(step):
    uses, w = str(step.get("uses", "")), step.get("with") or {}
    if uses.endswith("/wing-commander-project"):
        return str(w.get("check-folder", "true")) != "false"
    return uses.endswith("/wing-commander-preflight") and "outputs.project" in str(w.get("project", ""))


def check_stale_folder(errors, wf_dir=None):
    """T036 (MF-22): in a project-wired job, the recorded folder is
    re-checked on the ref the agent works from -- a folder check
    (wing-commander-project with check-folder on, or a project preflight)
    after the last root checkout before every Edit/Write agent."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            if (fn, job_name) in STALE_FOLDER_EXEMPT:
                continue
            steps = job.get("steps") or []
            grants, wired = {}, False
            for s in steps:
                uses = str(s.get("uses", ""))
                if uses.endswith("/wing-commander-project"):
                    wired = True
                if uses.endswith("/wing-commander-tool-args"):
                    w = s.get("with") or {}
                    wired = wired or bool(str(w.get("project", "")).strip())
                    if s.get("id"):
                        grants[s["id"]] = str(w.get("default-allowed-tools", ""))
            if not wired:
                continue
            for i, s in enumerate(steps):
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                ids = re.findall(r"steps\.([\w-]+)\.outputs\.allowed-tools", json.dumps(s))
                if not any(writes(grants.get(x, "")) for x in ids):
                    continue
                last = max((j for j in range(i) if is_root_checkout(steps[j])), default=-1)
                if any(is_folder_check(t) for t in steps[last + 1:i]):
                    covered += 1
                else:
                    errors.append(f"{fn}:{job_name}: Edit/Write agent {s.get('name')!r} runs with no project-folder check after its last checkout (T036)")
    return covered


STALE = """\
jobs:
  stage:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - uses: actions/checkout@v5
      - id: tool-args
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-tool-args
        with:
          default-allowed-tools: "Read,Edit"
          project: ${{ steps.project.outputs.project }}
      - name: Agent
        uses: anthropics/claude-code-action@v1
        with:
          claude_args: --allowedTools "${{ steps.tool-args.outputs.allowed-tools }}"
"""


def check_preflight_project(errors, wf_dir=None):
    """FR-005 (MF-14): in a project-wired job (one that reads any
    `outputs.project`), every preflight that requires Spec Kit is handed the
    project, so a subfolder lifecycle is checked inside its folder rather
    than refused at a root that need not be a Spec Kit project."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            if "outputs.project" not in json.dumps(job):
                continue
            for s in job.get("steps") or []:
                w = s.get("with") or {}
                if not str(s.get("uses", "")).endswith("/wing-commander-preflight") or str(w.get("require-speckit", "")) != "true":
                    continue
                if "outputs.project" not in str(w.get("project", "")):
                    errors.append(f"{fn}:{job_name}: preflight {s.get('name')!r} requires Spec Kit but is not handed the project (FR-005)")
                else:
                    covered += 1
    return covered


UNPROJECTED_PREFLIGHT = """\
jobs:
  stage:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - name: Preflight
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-preflight
        with:
          require-speckit: "true"
      - run: echo "${{ steps.project.outputs.project }}"
"""


PRE_PUSH = os.path.join(ACTIONS, "_shared", "containment.sh")

UNGUARDED = """\
jobs:
  act:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - id: tool-args
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-tool-args
        with:
          default-allowed-tools: "Read,Write,Bash(git push:*)"
          project: ${{ steps.project.outputs.project }}
      - name: Agent
        uses: anthropics/claude-code-action@v1
        with:
          claude_args: --allowedTools "${{ steps.tool-args.outputs.allowed-tools }}"
"""


UNSCOPED_RESCUE = """\
jobs:
  stage:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - name: Check agent changes stay inside the project folder
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-containment
        with:
          project: ${{ steps.project.outputs.project }}
      - name: Publish stranded commits (post-agent)
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-publish-stranded-commits
        with:
          before-sha: abc
"""


UNGATED_RESCUE = """\
jobs:
  stage:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - name: Check agent changes stay inside the project folder
        id: containment
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-containment
        with:
          project: ${{ steps.project.outputs.project }}
      - name: Publish stranded commits (post-agent)
        if: "!cancelled()"
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-publish-stranded-commits
        with:
          project: ${{ steps.project.outputs.project }}
"""


def check_rescue_scope(errors, wf_dir=None):
    """FR-021: the stranded-commit rescue runs on !cancelled(), after the
    containment check, so in a project-wired job it must be handed the same
    project the job's containment check uses -- else it publishes exactly
    what that check failed."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            steps = job.get("steps") or []
            guards = {
                str((s.get("with") or {}).get("project", "")).strip()
                for s in steps
                if str(s.get("uses", "")).endswith("/wing-commander-containment")
            }
            wired = bool(guards) or any(str(s.get("uses", "")).endswith("/wing-commander-project") for s in steps)
            if not wired:
                continue
            last_check = None
            for s in steps:
                uses = str(s.get("uses", ""))
                if uses.endswith("/wing-commander-containment") and str((s.get("with") or {}).get("mode", "check")) == "check":
                    last_check = s
                    # MF-28: the caller hands over the default branch it
                    # resolved; the composite reads no event payload.
                    if not str((s.get("with") or {}).get("default-branch", "")).strip():
                        errors.append(f"{fn}:{job_name}: containment check {s.get('name')!r} is not handed the job's default branch (MF-28)")
                if not uses.endswith("/wing-commander-publish-stranded-commits"):
                    continue
                project = str((s.get("with") or {}).get("project", "")).strip()
                if not project or (guards and project not in guards):
                    errors.append(f"{fn}:{job_name}: {s.get('name')!r} is not handed the project its containment check uses (FR-021)")
                    continue
                # MF-36: the rescue runs on !cancelled(), so it must also be
                # gated on the check above it not having failed.
                if last_check is not None:
                    cid = last_check.get("id")
                    if not cid or f"steps.{cid}.outcome != 'failure'" not in str(s.get("if", "")):
                        errors.append(f"{fn}:{job_name}: {s.get('name')!r} is not gated on its containment check ({cid or 'no id'}) not having failed (FR-021, MF-36)")
                        continue
                covered += 1
    return covered


PIPELINE_DIR = ".wing-commander-pipeline"
PROJECT_GATE = re.compile(r"(?:steps\.[\w-]+\.outputs|matrix)\.project != ''")


def _reads_pipeline(step):
    """A step that runs code from the pipeline checkout: a composite under
    it, or a run block that names it."""
    return str(step.get("uses", "")).startswith(f"./{PIPELINE_DIR}/") or f"{PIPELINE_DIR}/" in str(step.get("run", ""))


def _is_pipeline_removal(step):
    return str(step.get("run", "")).strip() == f"rm -rf -- {PIPELINE_DIR}"


def _is_pipeline_recheckout(step):
    w = step.get("with") or {}
    return (str(step.get("uses", "")).startswith("actions/checkout@")
            and str(w.get("path", "")) == PIPELINE_DIR
            and str(w.get("ref", "")).strip() == "${{ steps.pipeline-ref.outputs.ref }}")


def check_pipeline_recheckout(errors, wf_dir=None):
    """MF-46: the agent can write the pipeline checkout in the workspace
    (`git diff --output=<path>`), so in every subfolder-capable job (one
    with a containment check) each agent step is followed, before any step
    that runs code from that checkout, by `rm -rf -- .wing-commander-pipeline`
    and then a re-checkout at the job's pinned ref, both gated on a
    non-empty project. Subfolder-capable means the job uses
    wing-commander-containment in any mode."""
    wf_dir = wf_dir or os.path.join(ROOT, ".github", "workflows")
    covered = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            steps = job.get("steps") or []
            if not any(str(s.get("uses", "")).endswith("/wing-commander-containment") for s in steps):
                continue
            for i, s in enumerate(steps):
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                after = steps[i + 1:]
                first = next((j for j, t in enumerate(after) if _reads_pipeline(t)), len(after))
                rm = next((j for j, t in enumerate(after[:first]) if _is_pipeline_removal(t)), None)
                co = next((j for j, t in enumerate(after[:first]) if _is_pipeline_recheckout(t)), None)
                where = f"{fn}:{job_name}: agent {s.get('name')!r}"
                if rm is None or co is None or co < rm:
                    errors.append(f"{where} is not followed by `rm -rf -- {PIPELINE_DIR}` and a re-checkout at "
                                  f"steps.pipeline-ref.outputs.ref before the first step that runs pipeline code (MF-46)")
                    continue
                if not any(t.get("id") == "pipeline-ref" for t in steps[:i]):
                    errors.append(f"{where}: the job has no pipeline-ref step before the agent to re-checkout at (MF-46)")
                    continue
                if not all(PROJECT_GATE.search(str(after[j].get("if", ""))) for j in (rm, co)):
                    errors.append(f"{where}: the pipeline re-checkout is not gated on a non-empty project (MF-46)")
                    continue
                covered += 1
    return covered


UNRECHECKED = """\
jobs:
  stage:
    steps:
      - id: project
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-project
      - name: Agent
        id: agent
        uses: anthropics/claude-code-action@v1
      - name: Remove the pipeline checkout (post-agent)
        if: always() && steps.project.outputs.project != ''
        run: rm -rf -- .wing-commander-pipeline
      - name: Check agent changes stay inside the project folder
        id: containment
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-containment
      - name: Re-checkout pipeline repository (post-agent)
        if: always() && steps.project.outputs.project != ''
        uses: actions/checkout@v5
        with:
          ref: ${{ steps.pipeline-ref.outputs.ref }}
          path: .wing-commander-pipeline
"""


def staged_clone(tmp, case):
    """A clone whose origin already holds the base commit, with the case's
    local commits on top. Returns (work, origin, base sha)."""
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True, capture_output=True)
    os.makedirs(work)
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "g@example.invalid")
    git(work, "config", "user.name", "gate")
    for rel in case["base_files"]:
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    base = rev(work, "HEAD")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-q", "origin", "main")
    if case.get("remote_branch"):
        # Content already on another remote branch, outside P, merged in:
        # `--not --remotes` would have let it through (MF-33).
        git(work, "checkout", "-q", "-b", "other")
        for rel in case["remote_branch"]:
            with open(os.path.join(work, rel), "a", encoding="utf-8") as fh:
                fh.write("o\n")
        git(work, "commit", "-q", "-am", "other")
        git(work, "push", "-q", "origin", "other")
        git(work, "checkout", "-q", "main")
        git(work, "merge", "-q", "--no-ff", "-m", "merge other", "other")
    for rel in case.get("commit_files", []):
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("y\n")
    if case.get("commit_files"):
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "agent")
    if case.get("replace_object"):
        # A planted refs/replace/* that swaps the agent's tip for a clean
        # commit inside P: git must ignore it (GIT_NO_REPLACE_OBJECTS).
        tip = rev(work, "HEAD")
        git(work, "checkout", "-q", "--detach", base)
        with open(os.path.join(work, case["project"], "clean.md"), "w", encoding="utf-8") as fh:
            fh.write("c\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "clean")
        clean = rev(work, "HEAD")
        git(work, "checkout", "-q", "main")
        git(work, "replace", tip, clean)
    if case.get("evil_merge_files"):
        # A merge of a side branch that changed only P, whose merge commit
        # itself also changes the listed paths (an evil merge).
        git(work, "checkout", "-q", "-b", "side", base)
        with open(os.path.join(work, case["project"], "side.md"), "w", encoding="utf-8") as fh:
            fh.write("s\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "side")
        git(work, "checkout", "-q", "main")
        git(work, "merge", "-q", "--no-ff", "--no-commit", "side")
        for rel in case["evil_merge_files"]:
            with open(os.path.join(work, rel), "a", encoding="utf-8") as fh:
                fh.write("e\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "merge")
    return work, origin, base


def action_step(name, step_name):
    with open(os.path.join(ACTIONS, name, "action.yml"), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return next(s["run"] for s in doc["runs"]["steps"] if s.get("name") == step_name)


def check_modes(errors):
    """MF-07: wing-commander-containment's install-pre-push mode writes a
    working hook from copies of the helpers (the containment test, or with
    label-first-number intake's label-first check, which records the slug
    and refuses the push either way), and filter mode narrows a path file
    to the folder in place."""
    install = action_step("wing-commander-containment", "Install containment pre-push hook")
    base_files = ["a/b/x.md", "README.md"]
    for name, files, lf, ref, want_pushed in (
        ("containment hook allows a push inside P", ["a/b/x.md"], False, "main", True),
        ("containment hook refuses a push outside P", ["README.md"], False, "main", False),
        ("label-first hook records a valid slug and refuses the push", ["a/b/x.md"], True, "spec-draft/a/b/001-x", False),
        ("label-first hook refuses an unallocated number", ["a/b/x.md"], True, "spec-draft/a/b/002-x", False),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            work, origin, _ = staged_clone(tmp, {"base_files": base_files})
            hooks = os.path.join(tmp, "hooks")
            record = os.path.join(tmp, "record")
            env = {"PROJECT": "a/b", "HOOKS_DIR": hooks, "LF_PREFIX": "spec-draft/" if lf else "",
                   "LF_NUM": "001" if lf else "", "RECORD": record if lf else "", "RUNNER_TEMP": tmp}
            r, out = run_script(install, env, work, "wing-commander-containment")
            if r.returncode != 0 or "pre-agent-sha=" not in out:
                errors.append(f"install-pre-push {name}: install failed rc={r.returncode} {r.stderr!r}")
                continue
            for rel in files:
                with open(os.path.join(work, rel), "a", encoding="utf-8") as fh:
                    fh.write("h\n")
            git(work, "commit", "-q", "-am", "agent")
            p = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + ref], cwd=work,
                               capture_output=True, text=True, check=False)
            moved = subprocess.run(["git", "--git-dir", origin, "rev-parse", "-q", "--verify", "refs/heads/" + ref],
                                   capture_output=True, text=True, check=False).stdout.strip() == rev(work, "HEAD")
            if moved != want_pushed or (p.returncode == 0) != want_pushed:
                errors.append(f"install-pre-push {name}: push rc={p.returncode} reached origin={moved}, want {want_pushed} {p.stderr!r}")
            recorded = open(record, encoding="utf-8").read().strip() if os.path.exists(record) else ""
            want_record = "001-x" if ref.endswith("/001-x") else ""
            if lf and recorded != want_record:
                errors.append(f"install-pre-push {name}: recorded slug {recorded!r}, want {want_record!r}")
    flt = action_step("wing-commander-containment", "Filter paths to the project folder")
    with tempfile.TemporaryDirectory() as tmp:
        paths = os.path.join(tmp, "manifest.txt")
        with open(paths, "w", encoding="utf-8") as fh:
            fh.write("a/b/x.md\nREADME.md\na/bc/y.md\na/b/c/z.md\n")
        r, _ = run_script(flt, {"PROJECT": "a/b", "PATHS_FILE": paths}, tmp, "wing-commander-containment")
        got = open(paths, encoding="utf-8").read().split()
        if r.returncode != 0 or got != ["a/b/x.md", "a/b/c/z.md"]:
            errors.append(f"filter: kept {got!r}, want ['a/b/x.md', 'a/b/c/z.md'] rc={r.returncode} {r.stderr!r}")


GUARD = os.path.join(ROOT, ".github", "scripts", "pipeline-checkout-guard.sh")


def check_trusted_checkout_excluded(errors):
    """#1030: after the pipeline-checkout guard passes a consumer checkout,
    `git add -A` no longer stages the untracked trusted checkout as a
    gitlink, and a second guard run does not duplicate the exclude line."""
    with tempfile.TemporaryDirectory() as tmp:
        git(tmp, "init", "-q")
        pipe = os.path.join(tmp, ".wing-commander-pipeline")
        os.makedirs(pipe)
        git(pipe, "init", "-q")
        git(pipe, "config", "user.email", "g@example.invalid")
        git(pipe, "config", "user.name", "gate")
        with open(os.path.join(pipe, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("p\n")
        git(pipe, "add", "-A")
        git(pipe, "commit", "-q", "-m", "pipe")
        for _ in range(2):
            r = subprocess.run(["bash", GUARD], cwd=tmp, capture_output=True, text=True, check=False)
            if r.returncode != 0:
                errors.append(f"trusted checkout exclude: guard failed rc={r.returncode} {r.stdout!r}")
                return
        git(tmp, "add", "-A")
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=tmp,
                                capture_output=True, text=True, check=True).stdout
        if ".wing-commander-pipeline" in staged:
            errors.append("trusted checkout exclude: `git add -A` staged .wing-commander-pipeline after the guard ran (#1030)")
        with open(os.path.join(tmp, ".git", "info", "exclude"), encoding="utf-8") as fh:
            if fh.read().count("/.wing-commander-pipeline/") != 1:
                errors.append("trusted checkout exclude: the exclude line is missing or duplicated")


def rev(cwd, ref):
    return subprocess.run(["git", "rev-parse", ref], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def pre_push(case):
    """Run containment.sh's pre-push mode after the case's local commits."""
    with tempfile.TemporaryDirectory() as tmp:
        work, _, _ = staged_clone(tmp, case)
        line = case.get("stdin", "refs/heads/x {sha} refs/heads/x " + "0" * 40).format(sha=rev(work, "HEAD")) + "\n"
        return subprocess.run(["bash", PRE_PUSH, "pre-push", case["project"]], input=line,
                              capture_output=True, text=True, cwd=work, check=False)


def publish_stranded(case, script):
    """Run wing-commander-publish-stranded-commits' real shell after the
    case's local commits. Returns (result, push-ok, whether origin moved to
    the local tip)."""
    with tempfile.TemporaryDirectory() as tmp:
        work, origin, base = staged_clone(tmp, case)
        env = {"BEFORE_SHA": base, "WORKDIR": work, "PUSH_TOKEN": "", "PUSH_REPO": "",
               "EXPECTED_BRANCH": "", "PROJECT": case["project"]}
        r, out = run_script(script, env, tmp, "wing-commander-publish-stranded-commits")
        m = re.search(r"^push-ok=(.*)$", out, re.M)
        return r, (m.group(1) if m else ""), rev(origin, "refs/heads/main") == rev(work, "HEAD")


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    errors = []
    ta = action_script("wing-commander-tool-args")
    for name, case in data["tool_args"].items():
        got, allowed, err = tool_args(case, ta)
        if got is None:
            errors.append(f"tool_args {name}: composite failed: {err!r}")
            continue
        if "allowed" in case and allowed.split(",") != case["allowed"]:
            errors.append(f"tool_args {name}: allowed-tools {allowed!r}, want {case['allowed']!r}")
        for want in case.get("denied", []):
            for tool in ("Edit", "Write"):
                if f"{tool}({want})" not in got.split(","):
                    errors.append(f"tool_args {name}: {tool}({want}) missing from {got!r}")
        for want in case.get("denied_tools", []):
            if want not in got.split(","):
                errors.append(f"tool_args {name}: {want} missing from {got!r}")
        for bad in case.get("not_denied", []):
            if bad in got:
                errors.append(f"tool_args {name}: unexpected {bad!r} in {got!r}")
    cs = action_script("wing-commander-containment")
    for name, case in data["containment"].items():
        r = contain(case, cs)
        if case["expect"] == "pass" and r.returncode != 0:
            errors.append(f"containment {name}: expected pass, rc={r.returncode} {r.stderr!r}")
        if case["expect"] == "fail":
            if r.returncode == 0:
                errors.append(f"containment {name}: expected fail, passed")
            for p in case.get("names", []):
                if p not in r.stdout + r.stderr:
                    errors.append(f"containment {name}: output does not name {p!r}")
    for name, case in data.get("pre_push", {}).items():
        r = pre_push(case)
        if case["expect"] == "pass" and r.returncode != 0:
            errors.append(f"pre_push {name}: expected pass, rc={r.returncode} {r.stderr!r}")
        if case["expect"] == "fail":
            if r.returncode == 0:
                errors.append(f"pre_push {name}: expected the push refused, it was allowed")
            for p in case.get("names", []):
                if p not in r.stderr:
                    errors.append(f"pre_push {name}: refusal does not name {p!r}")
    ps = action_script("wing-commander-publish-stranded-commits")
    for name, case in data.get("publish_stranded", {}).items():
        r, ok, moved = publish_stranded(case, ps)
        if case["expect"] == "pass" and (ok != "true" or not moved):
            errors.append(f"publish_stranded {name}: expected the commits published, push-ok={ok!r} origin moved={moved} {r.stderr!r}")
        if case["expect"] == "fail":
            if ok != "false" or moved:
                errors.append(f"publish_stranded {name}: expected nothing published, push-ok={ok!r} origin moved={moved}")
            for p in case.get("names", []):
                if p not in r.stdout + r.stderr:
                    errors.append(f"publish_stranded {name}: refusal does not name {p!r}")
    check_trusted_checkout_excluded(errors)
    check_modes(errors)
    if check_stale_folder(errors) == 0:
        errors.append("stale folder: no Edit/Write agent in a project-wired job was found -- the check has lost its subject")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "stale.yml"), "w", encoding="utf-8") as fh:
            fh.write(STALE)
        probe = []
        check_stale_folder(probe, tmp)
        if not probe:
            errors.append("stale folder: a folder resolved only before the checkout was not flagged")
    check_guidance_output(errors)
    if check_prompt_guidance(errors) == 0:
        errors.append("prompt guidance: no Edit/Write agent in a project-wired job was found -- the check has lost its subject")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "unguided.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNGUARDED)
        probe = []
        check_prompt_guidance(probe, tmp)
        if not probe:
            errors.append("prompt guidance: an Edit/Write agent with no project paragraph was not flagged")
    if check_preflight_project(errors) == 0:
        errors.append("preflight project: no Spec Kit preflight in a project-wired job was found -- the check has lost its subject")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "unprojected.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNPROJECTED_PREFLIGHT)
        probe = []
        check_preflight_project(probe, tmp)
        if not probe:
            errors.append("preflight project: a Spec Kit preflight with no project in a project-wired job was not flagged")
    check_wiring(errors)
    if check_rescue_scope(errors) == 0:
        errors.append("rescue scope: no stranded-commit rescue in a project-wired job was found -- the check has lost its subject")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "unscoped.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNSCOPED_RESCUE)
        probe = []
        check_rescue_scope(probe, tmp)
        if not probe:
            errors.append("rescue scope: a project-wired rescue with no project input was not flagged")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "ungated.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNGATED_RESCUE)
        probe = []
        check_rescue_scope(probe, tmp)
        if not any("MF-36" in p for p in probe):
            errors.append("rescue scope: a rescue not gated on its failed containment check was not flagged")
    if check_pipeline_recheckout(errors) == 0:
        errors.append("pipeline re-checkout: no agent in a subfolder-capable job was found -- the check has lost its subject")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "unrechecked.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNRECHECKED)
        probe = []
        check_pipeline_recheckout(probe, tmp)
        if not any("MF-46" in p for p in probe):
            errors.append("pipeline re-checkout: a re-checkout after the first pipeline composite was not flagged")
    if check_guard_coverage(errors) == 0:
        errors.append("guard coverage: no Edit/Write agent in a project-wired job was found -- the check has lost its subject")
    # Self-test: the coverage check must flag an unguarded Edit/Write agent.
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "unguarded.yml"), "w", encoding="utf-8") as fh:
            fh.write(UNGUARDED)
        probe = []
        check_guard_coverage(probe, tmp)
        if not any("no containment guard" in p for p in probe):
            errors.append("guard coverage: an unguarded Edit/Write agent in a project-wired job was not flagged")
        if not any("no containment pre-push hook" in p for p in probe):
            errors.append("guard coverage: a pushing agent with no pre-push hook before it was not flagged")
    if errors:
        print("verify-subfolder-containment: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print("verify-subfolder-containment: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
