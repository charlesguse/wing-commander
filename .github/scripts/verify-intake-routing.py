#!/usr/bin/env python3
"""Gate: intake routing (spec 114 FR-001, FR-003, FR-014, FR-023).

Drives the real shell behind intake routing over
fixtures/project-intake-routing/cases.json:
  * `_shared/project-name.sh validate-prefix` and `slug-budget`;
  * the wing-commander-project composite's "Resolve project" step with a fake
    `gh` serving the issue's live labels: 0 routing labels route to the root,
    1 routes to its folder, 2 or more refuse; with check-folder on, a missing
    folder or a folder that is not a Spec Kit project refuses, naming it;
  * intake.yml's re-run refusal step (`rerun`, in the routing-gate job): with
    routing on, any `spec:` label refuses, with or without a routing label;
    the step and its refusal steps are skipped when routing is off;
  * intake.yml's concurrency (research D8, FR-012), evaluated from the shipped
    expressions: the routing gate holds a per-issue group, the numbering job
    a per-project group (`wing-commander-intake` at the root, unchanged), so
    two intakes routed to different projects never share a numbering group
    while the same issue routed twice shares its gate group;
  * intake.yml's project guidance (`project-guidance`): the pipeline labels
    before it publishes, the agent hands over the push, label and PR, and the
    root prompt gains nothing;
  * intake.yml's label-first pre-push hook (`label-first-hook`, installed by
    wing-commander-containment): it validates only, records a passing slug
    and refuses every agent push; the same check, then the label, then the
    push run in its "Publish stranded commits (post-agent)" step, whose
    hardened push runs no hook (T065): an over-budget, misnumbered or
    out-of-project branch is never pushed, and a pushed one is labelled
    first; "Open the spec PR" (`open-pr`) follows that push;
  * intake.yml's "Resolve created spec" (`created`) with a fake `git`: a
    subfolder slug over the label budget fails, the root has no budget;
  * root compatibility (FR-016, fixtures/project-root-compat/cases.json):
    with routing off, a `node:` label routes nothing, the routing gate is
    skipped and the numbering group is still `wing-commander-intake`;
  * the interface delta (FR-017, fixtures/project-root-compat/interface.json):
    no input, secret or output of a published stage was removed or renamed,
    and every new input is optional with its root-reproducing default.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile

import yaml

from wc_gha_expr import evaluate_if, interpolate
from wc_published_stages import published_stages

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
PROJECT_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-project")
INTAKE = os.path.join(ROOT, ".github", "workflows", "intake.yml")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-intake-routing", "cases.json")
ROOT_COMPAT = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-root-compat", "cases.json")
INTERFACE = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-root-compat", "interface.json")

# With FAKE_LABEL_STATE set, the issue's labels live in that file (a JSON
# array of names) and `issue edit --add-label/--remove-label` change them, so
# several runs can be interleaved against one issue; otherwise `issue view`
# serves FAKE_LABELS_JSON.
FAKE_GH = """#!/usr/bin/env bash
if [ "$1 $2" = "issue view" ]; then
  expr=""
  while [ "$#" -gt 0 ]; do [ "$1" = --jq ] && expr="$2"; shift; done
  if [ -n "${FAKE_LABEL_STATE:-}" ]; then
    jq -c '{labels: [.[] | {name: .}]}' "$FAKE_LABEL_STATE" | jq -r "$expr"
  else
    printf '%s' "$FAKE_LABELS_JSON" | jq -r "$expr"
  fi
  exit 0
fi
if [ "$1 $2" = "issue comment" ]; then echo "$*" >> "$FAKE_GH_LOG"; exit 0; fi
if [ "$1 $2" = "label create" ]; then echo "label create $3" >> "$FAKE_GH_LOG"; exit 0; fi
if [ "$1 $2" = "pr list" ]; then echo "pr list $*" >> "$FAKE_GH_LOG"; printf '%s' "${FAKE_PR_NUMBER:-}"; exit 0; fi
if [ "$1 $2" = "pr create" ]; then echo "$*" >> "$FAKE_GH_LOG"; exit 0; fi
if [ "$1 $2" = "issue edit" ] && [ -n "${FAKE_LABEL_STATE:-}" ]; then
  shift 3
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --add-label) jq --arg l "$2" '. + [$l] | unique' "$FAKE_LABEL_STATE" > "$FAKE_LABEL_STATE.tmp"; shift 2 ;;
      --remove-label) jq --arg l "$2" 'map(select(. != $l))' "$FAKE_LABEL_STATE" > "$FAKE_LABEL_STATE.tmp"; shift 2 ;;
      *) echo "fake gh: unexpected issue edit flag $1" >&2; exit 2 ;;
    esac
    mv "$FAKE_LABEL_STATE.tmp" "$FAKE_LABEL_STATE"
  done
  echo "issue edit" >> "$FAKE_GH_LOG"
  exit 0
fi
echo "fake gh: unexpected $*" >&2; exit 2
"""

FAKE_GIT = """#!/usr/bin/env bash
if [ "$1" = ls-remote ]; then printf '%s' "$FAKE_LS_REMOTE"; exit 0; fi
echo "fake git: unexpected $*" >&2; exit 2
"""


def run(env_extra, *args):
    env = {**os.environ, **env_extra}
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env=env, check=False)


def write_exec(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_step(script, env, cwd, bindir, action_path=""):
    """Run a step's shell as the runner would (bash -e) and return (proc, outputs, gh-log)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "output")
        summary = os.path.join(tmp, "summary")
        log = os.path.join(tmp, "gh.log")
        for p in (out, summary, log):
            open(p, "w", encoding="utf-8").close()
        full = dict(os.environ)
        full.update(env)
        full.update(
            PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
            GITHUB_OUTPUT=out,
            GITHUB_STEP_SUMMARY=summary,
            GITHUB_ACTION_PATH=action_path,
            FAKE_GH_LOG=log,
        )
        r = subprocess.run(["bash", "-e", "-c", script], capture_output=True, text=True, cwd=cwd, env=full, check=False)
        with open(out, encoding="utf-8") as fh:
            outputs = fh.read()
        with open(log, encoding="utf-8") as fh:
            gh_log = fh.read()
        return r, outputs, gh_log


def output_value(outputs, key):
    for line in outputs.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def labels_json(labels):
    return json.dumps({"labels": [{"name": n} for n in labels]})


def make_layout(base, project, layout):
    if layout == "none":
        return
    p = os.path.join(base, project)
    os.makedirs(p)
    if layout == "plain":
        return
    for d in (".specify/memory", ".claude/skills/speckit-specify", "specs"):
        os.makedirs(os.path.join(p, d))
    if layout != "no-constitution":
        with open(os.path.join(p, ".specify", "memory", "constitution.md"), "w", encoding="utf-8") as fh:
            fh.write("# constitution\n")


def intake_doc():
    with open(INTAKE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def step_by_id(steps, sid):
    for s in steps:
        if s.get("id") == sid:
            return s
    raise KeyError(sid)


def check_label_count(data, bindir, errors):
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        resolve = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    base_env = {"GH_TOKEN": "fake", "ROUTING_PREFIX": "node:", "ISSUE": "7", "IDENTITY": "", "IDENTITY_KIND": "slug"}
    for case in data["label_count"]:
        env = {**base_env, "CHECK_FOLDER": "false", "FAKE_LABELS_JSON": labels_json(case["labels"])}
        r, outputs, log = run_step(resolve, env, ROOT, bindir, PROJECT_ACTION)
        tag = f"label_count {case['name']!r}"
        if case["expect"] == "pass":
            if r.returncode != 0:
                errors.append(f"{tag}: expected pass, rc={r.returncode} {r.stdout + r.stderr!r}")
            elif output_value(outputs, "project") != case["project"]:
                errors.append(f"{tag}: project={output_value(outputs, 'project')!r}, want {case['project']!r}")
        else:
            if r.returncode == 0:
                errors.append(f"{tag}: expected refusal, passed")
            if output_value(outputs, "project") is not None:
                errors.append(f"{tag}: refused run still emitted outputs")
            for want in case.get("names", []):
                if want not in log:
                    errors.append(f"{tag}: lifecycle-issue callout does not name {want!r} (log {log!r})")
    for case in data["folder"]:
        with tempfile.TemporaryDirectory() as repo:
            make_layout(repo, case["project"], case["layout"])
            env = {**base_env, "CHECK_FOLDER": "true", "FAKE_LABELS_JSON": labels_json(["node:" + case["project"]])}
            r, outputs, log = run_step(resolve, env, repo, bindir, PROJECT_ACTION)
        tag = f"folder {case['name']!r}"
        if case["expect"] == "pass":
            if r.returncode != 0 or output_value(outputs, "project") != case["project"]:
                errors.append(f"{tag}: expected pass, rc={r.returncode} {r.stdout + r.stderr!r}")
        else:
            if r.returncode == 0:
                errors.append(f"{tag}: expected refusal, passed")
            for want in case.get("names", []):
                if want not in log:
                    errors.append(f"{tag}: lifecycle-issue callout does not name {want!r} (log {log!r})")


def check_rerun(data, steps, bindir, errors):
    rerun = step_by_id(steps, "rerun")
    if "inputs.routing-label-prefix != ''" not in str(rerun.get("if", "")):
        errors.append("rerun: intake.yml step `rerun` is not skipped when routing is off")
    gated = [s for s in steps if "steps.rerun.outputs.existing != ''" in str(s.get("if", ""))]
    if not any("exit 1" in str(s.get("run", "")) for s in gated):
        errors.append("rerun: no step gated on steps.rerun.outputs.existing fails the job")
    if not any("callout" in str(s.get("uses", "")) for s in gated):
        errors.append("rerun: no lifecycle-issue callout is gated on steps.rerun.outputs.existing")
    for case in data["rerun"]:
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "labels.json")
            with open(state, "w", encoding="utf-8") as fh:
                json.dump(case["labels"], fh)
            env = {"GH_TOKEN": "fake", "ISSUE": "7", "FAKE_LABEL_STATE": state}
            r, outputs, _ = run_step(rerun["run"], env, ROOT, bindir)
        got = output_value(outputs, "existing")
        if r.returncode != 0 or got != case["existing"]:
            errors.append(f"rerun {case['name']!r}: rc={r.returncode} existing={got!r}, want {case['existing']!r}")


CLAIM = "spec-intake-claimed"


def check_rerun_race(doc, bindir, errors):
    """FR-003/FR-012 (T060): the refusal is race-safe across the whole intake.
    The per-issue group ends with the routing-gate job, before the intake job
    creates the `spec:` label, so the gate claims the issue inside the group.
    Interleavings run the shipped `rerun` and "Release the intake claim"
    steps against one stateful issue."""
    gate = doc["jobs"]["routing-gate"]
    rerun = step_by_id(gate["steps"], "rerun")
    if "steps.rerun.outputs.claim-label" not in str(gate.get("outputs", {}).get("claim-label", "")):
        errors.append("race: the routing gate does not export its claim label as `claim-label`")
    release = [s for s in doc["jobs"]["intake"]["steps"] if s.get("name") == "Release the intake claim"]
    if len(release) != 1:
        errors.append("race: the intake job has no single \"Release the intake claim\" step")
        return
    release = release[0]
    cond = str(release.get("if", ""))
    if "always()" not in cond or "needs.routing-gate.outputs.claim-label != ''" not in cond:
        errors.append(f"race: the claim release is not always()-gated on the gate's claim ({cond!r})")
    if doc["jobs"]["intake"]["steps"][-1] is not release:
        errors.append("race: the claim release is not the intake job's last step")

    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "labels.json")

        def labels(value=None):
            if value is not None:
                with open(state, "w", encoding="utf-8") as fh:
                    json.dump(value, fh)
            with open(state, encoding="utf-8") as fh:
                return json.load(fh)

        def gate_run(who):
            r, outputs, _ = run_step(rerun["run"], {"GH_TOKEN": "fake", "ISSUE": "7", "FAKE_LABEL_STATE": state},
                                     ROOT, bindir)
            if r.returncode != 0:
                errors.append(f"race: {who}'s gate failed rc={r.returncode} {r.stderr!r}")
            return output_value(outputs, "existing") or "", output_value(outputs, "claim-label") or ""

        def release_run(claim):
            env = {"GH_TOKEN": "fake", "GH_REPO": "o/r", "ISSUE": "7", "CLAIM": claim, "FAKE_LABEL_STATE": state}
            r, _, _ = run_step(release["run"], env, ROOT, bindir)
            if r.returncode != 0:
                errors.append(f"race: the claim release failed rc={r.returncode} {r.stderr!r}")

        # A passes its gate; B, queued behind A's per-issue group, runs its
        # gate before A's intake job has created the spec label.
        labels([])
        a_existing, a_claim = gate_run("A")
        if a_existing or a_claim != CLAIM or CLAIM not in labels():
            errors.append(f"race: the first intake did not claim the issue (existing={a_existing!r}, claim={a_claim!r})")
        b_existing, b_claim = gate_run("B")
        if not b_existing or b_claim:
            errors.append(f"race: a second intake passed between the first's gate and its spec label "
                          f"(existing={b_existing!r}, claim={b_claim!r})")
        # A creates its spec label (the label-first hook), then releases.
        labels(labels() + ["spec:ideas/alpha/001-x"])
        release_run(a_claim)
        if CLAIM in labels():
            errors.append("race: the claim was not released at the end of the intake job")
        c_existing, _ = gate_run("C")
        if "spec:ideas/alpha/001-x" not in c_existing:
            errors.append(f"race: after the first intake finished, a re-run was not refused ({c_existing!r})")
        # A failed intake that created no spec label leaves the issue free.
        labels([])
        _, d_claim = gate_run("D")
        release_run(d_claim)
        e_existing, e_claim = gate_run("E")
        if e_existing or e_claim != CLAIM:
            errors.append(f"race: a failed intake's released claim still refuses a re-run ({e_existing!r})")


CONTAINMENT_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-containment")


def install_label_first_hook(hook, case, tmp, ws, bindir):
    """Run wing-commander-containment's install-pre-push shell with the
    inputs intake's `label-first-hook` step hands it. -> (proc, record path)."""
    with open(os.path.join(CONTAINMENT_ACTION, "action.yml"), encoding="utf-8") as fh:
        install = next(s for s in yaml.safe_load(fh)["runs"]["steps"] if s.get("id") == "install")
    record = os.path.join(tmp, "rt", "validated-slug")
    env = {"PROJECT": case["project"], "HOOKS_DIR": os.path.join(tmp, "rt", "hooks"), "LF_PREFIX": "spec-draft/",
           "LF_NUM": case["num"], "RECORD": record, "RUNNER_TEMP": os.path.join(tmp, "rt")}
    r, _, _ = run_step(install["run"], env, ws, bindir, CONTAINMENT_ACTION)
    return r, record


def check_label_first_hook(data, doc, bindir, errors):
    """FR-014 (T061, MF-04): no branch reaches the remote before its spec
    label exists. The pre-push hook the shipped `label-first-hook` step
    installs (wing-commander-containment, install-pre-push mode) validates
    only -- ref, allocated number, slug budget, containment -- and makes no
    API call: it records a passing slug and refuses every push, so the
    agent's own push never publishes the branch. Driven by a real
    `git push` into a bare origin."""
    steps = doc["jobs"]["intake"]["steps"]
    hook = step_by_id(steps, "label-first-hook")
    cond = str(hook.get("if", ""))
    if "inputs.routing-label-prefix != ''" not in cond or "steps.num.outputs.project != ''" not in cond:
        errors.append(f"label-first hook: not limited to routing on and a subfolder target ({cond!r})")
    if steps.index(hook) > steps.index(step_by_id(steps, "agent")):
        errors.append("label-first hook: installed after the intake agent step")
    if not str(hook.get("uses", "")).endswith("/wing-commander-containment"):
        errors.append("label-first hook: not installed through wing-commander-containment")
    w = hook.get("with") or {}
    for key, want in (("mode", "install-pre-push"), ("label-first-number", "steps.num.outputs.num"),
                      ("label-first-prefix", "inputs.spec-draft-prefix"), ("record-file", "runner.temp")):
        if want not in str(w.get(key, "")):
            errors.append(f"label-first hook: {key} is not {want} ({w.get(key)!r})")
    with open(os.path.join(ROOT, ".github", "actions", "_shared", "intake-pre-push.sh"), encoding="utf-8") as fh:
        if any(line.lstrip().startswith("gh ") or " gh " in line for line in fh if not line.lstrip().startswith("#")):
            errors.append("label-first hook: _shared/intake-pre-push.sh makes a gh call (Gate 12; it validates only)")
    for case in data["label_first_hook"]:
        tag = f"label-first hook {case['name']!r}"
        with tempfile.TemporaryDirectory() as tmp:
            ws, origin, git, base = intake_workspace(tmp)
            r, record = install_label_first_hook(hook, case, tmp, ws, bindir)
            if r.returncode != 0:
                errors.append(f"{tag}: the install step failed rc={r.returncode} {r.stderr!r}")
                continue
            commit_case(ws, git, case)
            state = os.path.join(tmp, "labels.json")
            push_env = {**os.environ, "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
                        "GH_TOKEN": "fake", "FAKE_LABEL_STATE": state, "FAKE_GH_LOG": os.path.join(tmp, "gh.log")}
            p = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/" + case["ref"]], cwd=ws, env=push_env,
                               capture_output=True, text=True, check=False)
            judge_label_first(tag, {**case, "expect": "fail", "names": case.get("names", [])},
                              p.returncode, p.stderr, origin, state, errors)
            recorded = open(record, encoding="utf-8").read().strip() if os.path.exists(record) else ""
            want = case["ref"].rsplit("/", 1)[1] if case["expect"] == "pass" else ""
            if recorded != want:
                errors.append(f"{tag}: the hook recorded {recorded!r}, want {want!r}")
            if case["expect"] == "pass" and "passed the label-first check" not in p.stderr:
                errors.append(f"{tag}: the refusal does not tell the agent its branch passed ({p.stderr!r})")


def intake_workspace(tmp):
    """A checkout of a bare origin carrying `main`, with the pipeline checkout
    linked in and the project folder present -> (ws, origin, git, base-sha)."""
    ws = os.path.join(tmp, "ws")
    origin = os.path.join(tmp, "origin.git")
    os.makedirs(os.path.join(tmp, "rt"))
    subprocess.run(["git", "init", "-q", "--bare", origin], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", ws], check=True, capture_output=True)
    os.symlink(ROOT, os.path.join(ws, ".wing-commander-pipeline"))

    def git(*args):
        return subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True, check=False)
    for k, v in (("user.email", "g@example.invalid"), ("user.name", "gate"), ("commit.gpgsign", "false")):
        git("config", k, v)
    with open(os.path.join(ws, ".git", "info", "exclude"), "a", encoding="utf-8") as fh:
        fh.write(".wing-commander-pipeline\n")
    os.makedirs(os.path.join(ws, "ideas", "alpha"))
    with open(os.path.join(ws, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("root\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("remote", "add", "origin", origin)
    git("push", "-q", "origin", "main")
    with open(os.path.join(tmp, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump([], fh)
    return ws, origin, git, git("rev-parse", "HEAD").stdout.strip()


def commit_case(ws, git, case):
    for rel in case["commit"]:
        path = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("x\n")
    git("add", "-A")
    git("commit", "-q", "-m", "spec")


def judge_label_first(tag, case, rc, stderr, origin, state, errors):
    pushed = subprocess.run(["git", "--git-dir", origin, "rev-parse", "--verify", "-q",
                             "refs/heads/" + case["ref"]], capture_output=True, text=True,
                            check=False).returncode == 0
    with open(state, encoding="utf-8") as fh:
        on_issue = json.load(fh)
    if case["expect"] == "pass":
        if rc != 0 or not pushed:
            errors.append(f"{tag}: push refused rc={rc} {stderr!r}")
        if case["label"] not in on_issue:
            errors.append(f"{tag}: the spec label {case['label']!r} is not on the issue ({on_issue!r})")
    else:
        if rc == 0 or pushed:
            errors.append(f"{tag}: the push went through; no branch may exist")
        if any(n.startswith("spec:") for n in on_issue):
            errors.append(f"{tag}: a refused push still labelled the issue ({on_issue!r})")
        for want in case.get("names", []):
            if want not in stderr:
                errors.append(f"{tag}: refusal does not name {want!r} ({stderr!r})")


PUBLISH_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-publish-stranded-commits")


LABEL_FIRST_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-label-first")


def check_label_first_rescue(data, doc, bindir, errors):
    """FR-014 (T065, MF-05): intake's "Label first" step
    (wing-commander-label-first) checks the branch and creates and adds the
    spec label under its declared token; "Publish stranded commits
    (post-agent)" then pushes with hooks off (wc_harden_git_env), re-running
    the check and publishing only the branch the label step labelled. Each
    label-first case is replayed as a stranded branch -- with the hook
    installed, to prove the check holds without it -- plus a push the label
    step never labelled, and the intake wiring passes the inputs only with
    routing on and a subfolder."""
    steps = doc["jobs"]["intake"]["steps"]
    hook = step_by_id(steps, "label-first-hook")
    rescue = step_by_id(steps, "publish-stranded")
    lf_step = step_by_id(steps, "label-first")
    with_ = rescue.get("with", {})
    if not str(lf_step.get("uses", "")).endswith("/wing-commander-label-first"):
        errors.append("label-first rescue: the label step does not use wing-commander-label-first")
    if "env.WC_BOT_TOKEN" not in str((lf_step.get("with") or {}).get("token", "")):
        errors.append("label-first rescue: the label step is not handed the App token")
    if not steps.index(lf_step) < steps.index(rescue):
        errors.append("label-first rescue: the label step does not run before the push")
    if "steps.label-first.outputs.slug" not in str(with_.get("label-first-slug", "")):
        errors.append("label-first rescue: the push is not handed the label step's slug")
    lf_cond = str(lf_step.get("if", ""))
    if "inputs.routing-label-prefix != ''" not in lf_cond or "steps.num.outputs.project != ''" not in lf_cond:
        errors.append(f"label-first rescue: the label step is not limited to routing on and a subfolder ({lf_cond!r})")
    with open(os.path.join(LABEL_FIRST_ACTION, "action.yml"), encoding="utf-8") as fh:
        label_run = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    for prefix, project, want in (("node:", "ideas/alpha", "7"), ("", "ideas/alpha", ""), ("node:", "", "")):
        ctx = {"inputs.routing-label-prefix": prefix, "inputs.issue-number": "7", "steps.num.outputs.project": project}
        got = interpolate(str(with_.get("label-first-issue", "")), ctx)
        if got != want:
            errors.append(f"label-first rescue: label-first-issue is {got!r} for prefix={prefix!r} "
                          f"project={project!r}, want {want!r}")
    for key, expr in (("label-first-number", "steps.num.outputs.num"), ("label-first-prefix", "inputs.spec-draft-prefix")):
        if expr not in str(with_.get(key, "")):
            errors.append(f"label-first rescue: {key} is not {expr} ({with_.get(key)!r})")
    with open(os.path.join(PUBLISH_ACTION, "action.yml"), encoding="utf-8") as fh:
        publish = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    for case in data["label_first_hook"]:
        tag = f"label-first rescue {case['name']!r}"
        with tempfile.TemporaryDirectory() as tmp:
            ws, origin, git, base = intake_workspace(tmp)
            r, _ = install_label_first_hook(hook, case, tmp, ws, bindir)
            if r.returncode != 0:
                errors.append(f"{tag}: the install step failed rc={r.returncode} {r.stderr!r}")
                continue
            git("checkout", "-q", "-b", case["ref"])
            commit_case(ws, git, case)
            state = os.path.join(tmp, "labels.json")
            lenv = {"GH_TOKEN": "fake", "ISSUE": "7", "PROJECT": case["project"], "NUM": case["num"],
                    "PREFIX": "spec-draft/", "FAKE_LABEL_STATE": state}
            lr, louts, _ = run_step(label_run, lenv, ws, bindir, LABEL_FIRST_ACTION)
            slug = output_value(louts, "slug") or ""
            if (lr.returncode == 0) != (case["expect"] == "pass") or (case["expect"] == "pass") != bool(slug):
                errors.append(f"{tag}: the label step rc={lr.returncode} slug={slug!r} for an expected {case['expect']}")
            if case["expect"] == "pass":
                # The push refuses a branch the label step did not label.
                penv = {"BEFORE_SHA": base, "WORKDIR": "", "PUSH_TOKEN": "", "PUSH_REPO": "", "EXPECTED_BRANCH": "",
                        "PROJECT": case["project"], "LF_ISSUE": "7", "LF_NUM": case["num"], "LF_PREFIX": "spec-draft/",
                        "LF_SLUG": ""}
                r, outputs, _ = run_step(publish, penv, ws, bindir, PUBLISH_ACTION)
                if output_value(outputs, "push-ok") != "false":
                    errors.append(f"{tag}: the push published a branch no label step labelled")
            env = {"BEFORE_SHA": base, "WORKDIR": "", "PUSH_TOKEN": "", "PUSH_REPO": "", "EXPECTED_BRANCH": "",
                   "PROJECT": case["project"], "LF_ISSUE": "7", "LF_NUM": case["num"], "LF_PREFIX": "spec-draft/",
                   "LF_SLUG": slug}
            r, outputs, _ = run_step(publish, env, ws, bindir, PUBLISH_ACTION)
            ok = output_value(outputs, "push-ok")
            if r.returncode != 0 or ok not in ("true", "false"):
                errors.append(f"{tag}: the rescue step failed rc={r.returncode} push-ok={ok!r} {r.stderr!r}")
                continue
            judge_label_first(tag, case, 0 if ok == "true" else 1, lr.stdout + lr.stderr + r.stdout + r.stderr,
                              origin, state, errors)
    # An agent that stopped without a spec: nothing to label, no error.
    with tempfile.TemporaryDirectory() as tmp:
        ws, _, _, _ = intake_workspace(tmp)
        lenv = {"GH_TOKEN": "fake", "ISSUE": "7", "PROJECT": "ideas/alpha", "NUM": "001", "PREFIX": "spec-draft/",
                "FAKE_LABEL_STATE": os.path.join(tmp, "labels.json")}
        lr, louts, log = run_step(label_run, lenv, ws, bindir, LABEL_FIRST_ACTION)
        if lr.returncode != 0 or output_value(louts, "slug") != "" or "label create" in log:
            errors.append(f"label-first rescue: an agent with no commit was not a quiet no-op rc={lr.returncode} {lr.stderr!r}")


def check_open_pr(doc, bindir, errors):
    """FR-014 (MF-05): with the agent's push refused, the PR and stage:spec
    follow the rescue's label-first push, never precede it."""
    steps = doc["jobs"]["intake"]["steps"]
    step = step_by_id(steps, "open-pr")
    cond = str(step.get("if", ""))
    if "steps.publish-stranded.outputs.push-ok == 'true'" not in cond or "label-first-slug != ''" not in cond:
        errors.append(f"open-pr: not gated on the label-first push having published ({cond!r})")
    if steps.index(step) < steps.index(step_by_id(steps, "publish-stranded")):
        errors.append("open-pr: runs before the label-first push")
    for existing, want_create in (("", True), ("12", False)):
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "ideas", "alpha", "specs", "001-login")
            os.makedirs(spec)
            with open(os.path.join(spec, "spec.md"), "w", encoding="utf-8") as fh:
                fh.write("# Feature Specification: Login\n")
            state = os.path.join(tmp, "labels.json")
            with open(state, "w", encoding="utf-8") as fh:
                json.dump(["spec:ideas/alpha/001-login"], fh)
            env = {"GH_TOKEN": "fake", "ISSUE": "7", "PROJECT": "ideas/alpha", "SLUG": "001-login",
                   "PREFIX": "spec-draft/", "BASE": "main", "BODY_FILE": os.path.join(tmp, "body.md"),
                   "RECORD": os.path.join(tmp, "record"), "FAKE_LABEL_STATE": state, "FAKE_PR_NUMBER": existing}
            r, _, log = run_step(step["run"], env, tmp, bindir)
            with open(state, encoding="utf-8") as fh:
                labels = json.load(fh)
            created = [line for line in log.splitlines() if line.startswith("pr create")]
            if r.returncode != 0:
                errors.append(f"open-pr (existing={existing!r}): failed rc={r.returncode} {r.stderr!r}")
            elif "stage:spec" not in labels:
                errors.append(f"open-pr (existing={existing!r}): stage:spec not on the issue ({labels!r})")
            elif "--head spec-draft/ideas/alpha/001-login" not in log:
                errors.append(f"open-pr (existing={existing!r}): did not look the PR up by its exact branch ({log!r})")
            elif bool(created) != want_create:
                errors.append(f"open-pr (existing={existing!r}): pr create calls {created!r}")
            elif want_create and "--title Spec: Login (#7)" not in created[0]:
                errors.append(f"open-pr: title not taken from spec.md's heading ({created[0]!r})")


def check_label_first(steps, bindir, errors):
    guidance = step_by_id(steps, "project-guidance")
    r, outputs, _ = run_step(guidance["run"], {"PROJECT": "ideas/alpha", "SLUG_BUDGET": "33"}, ROOT, bindir)
    if r.returncode != 0:
        errors.append(f"label-first: project-guidance failed {r.stderr!r}")
    elif not any("spec label BEFORE it publishes" in line for line in outputs.splitlines()):
        errors.append("label-first: the subfolder intake prompt does not say the pipeline labels before it publishes")
    elif "never pass --no-verify" not in outputs or "skip step 6's" not in outputs:
        errors.append("label-first: the subfolder intake prompt does not hand the push, label and PR to the pipeline")
    elif "at most 33 characters" not in outputs:
        errors.append("label-first: the subfolder intake prompt does not carry the slug budget")
    r, outputs, _ = run_step(guidance["run"], {"PROJECT": "", "SLUG_BUDGET": ""}, ROOT, bindir)
    body = outputs.split("\n", 1)[1] if "\n" in outputs else ""
    if r.returncode != 0 or body.strip() != "WC_INTAKE_PROJECT_GUIDANCE_EOF":
        errors.append(f"label-first: root project guidance is not empty: {outputs!r}")


def resolve_project(labels, bindir):
    """The project the real routing composite resolves from these live labels."""
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        resolve = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    env = {"GH_TOKEN": "fake", "ROUTING_PREFIX": "node:", "ISSUE": "7", "IDENTITY": "",
           "IDENTITY_KIND": "slug", "CHECK_FOLDER": "false", "FAKE_LABELS_JSON": labels_json(labels)}
    r, outputs, _ = run_step(resolve, env, ROOT, bindir, PROJECT_ACTION)
    return output_value(outputs, "project") if r.returncode == 0 else None


def check_concurrency(doc, bindir, errors):
    """Research D8 / FR-012: per-issue gate group, per-project numbering group."""
    jobs = doc["jobs"]
    gate, intake, stalled = jobs["routing-gate"], jobs["intake"], jobs["stalled"]
    gate_group = gate["concurrency"]["group"]
    intake_group = intake["concurrency"]["group"]
    if stalled["concurrency"]["group"] != intake_group:
        errors.append("concurrency: the stalled job does not share the intake job's numbering group")
    if gate["concurrency"].get("cancel-in-progress") is not False:
        errors.append("concurrency: the routing gate's per-issue group may cancel a queued intake")
    if "routing-gate" not in (intake.get("needs") or []):
        errors.append("concurrency: the numbering job does not `needs:` the routing gate")

    def groups(prefix, issue, labels):
        ctx = {"inputs.routing-label-prefix": prefix, "inputs.issue-number": issue,
               "needs.verify-image-prerequisites.result": "skipped", "cancelled()": False}
        gate_runs = evaluate_if(gate["if"], ctx)
        project = (resolve_project(labels, bindir) if gate_runs else "") or ""
        ctx.update({"needs.routing-gate.result": "success" if gate_runs else "skipped",
                    "needs.routing-gate.outputs.project": project})
        if not evaluate_if(intake["if"], ctx):
            errors.append(f"concurrency: intake does not run for prefix={prefix!r} labels={labels!r}")
        return (interpolate(gate_group, ctx) if gate_runs else None), interpolate(intake_group, ctx)

    root_gate, root_num = groups("", "7", ["node:ideas/alpha"])
    if root_gate is not None or root_num != "wing-commander-intake":
        errors.append(f"concurrency: routing off changed intake (gate={root_gate!r}, group={root_num!r})")
    a_gate, a_num = groups("node:", "7", ["node:ideas/alpha"])
    b_gate, b_num = groups("node:", "8", ["node:ideas/beta"])
    c_gate, c_num = groups("node:", "9", ["spec-request"])
    if (a_num, b_num, c_num) != ("wing-commander-intake/ideas/alpha", "wing-commander-intake/ideas/beta",
                                 "wing-commander-intake"):
        errors.append(f"concurrency: numbering groups {a_num!r}, {b_num!r}, {c_num!r} are not per project")
    if a_gate == b_gate:
        errors.append("concurrency: two issues share one per-issue gate group")
    a2_gate, a2_num = groups("node:", "7", ["node:ideas/beta"])
    if a2_gate != a_gate or a2_num == a_num:
        errors.append("concurrency: the same issue routed to two projects is not serialized by its gate group")
    ctx = {"inputs.routing-label-prefix": "node:", "needs.verify-image-prerequisites.result": "success",
           "cancelled()": False, "needs.routing-gate.result": "failure"}
    if evaluate_if(intake["if"], ctx):
        errors.append("concurrency: intake still runs after the routing gate refused")
    ctx.update({"needs.intake.result": "skipped", "needs.intake.outputs.refusal-reason": "",
                "needs.routing-gate.outputs.refused": "true"})
    if evaluate_if(stalled["if"], ctx):
        errors.append("concurrency: a routing-gate refusal is also reported as a stall")
    ctx["needs.routing-gate.outputs.refused"] = ""
    if not evaluate_if(stalled["if"], ctx):
        errors.append("concurrency: a routing gate that died unrefused is not reported as a stall")


def stage_interface():
    """{workflow file: {"inputs": {name: {required, default}}, "secrets": [..], "outputs": [..]}}."""
    result = {}
    for path in published_stages(ROOT):
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        on = doc.get("on", doc.get(True)) or {}
        call = on.get("workflow_call") or {}
        inputs = call.get("inputs") or {}
        result[os.path.basename(path)] = {
            "inputs": {k: {"required": bool((v or {}).get("required", False)), "default": (v or {}).get("default")}
                       for k, v in inputs.items()},
            "secrets": sorted((call.get("secrets") or {}).keys()),
            "outputs": sorted((call.get("outputs") or {}).keys()),
        }
    return result


def baseline_of(current, additions):
    out = {}
    for fn, iface in sorted(current.items()):
        added = additions.get(fn, {})
        out[fn] = {
            "inputs": sorted(k for k in iface["inputs"] if k not in added.get("inputs", {})),
            "secrets": [s for s in iface["secrets"] if s not in added.get("secrets", [])],
            "outputs": [o for o in iface["outputs"] if o not in added.get("outputs", [])],
        }
    return out


def check_interface(errors):
    """FR-017: additive only -- nothing removed or renamed, every new input defaults to the root."""
    with open(INTERFACE, encoding="utf-8") as fh:
        spec = json.load(fh)
    current = stage_interface()
    for fn, base in spec["baseline"].items():
        if fn not in current:
            errors.append(f"interface: published stage {fn} is gone")
            continue
        cur = current[fn]
        for kind in ("inputs", "secrets", "outputs"):
            for name in base[kind]:
                if name not in cur[kind]:
                    errors.append(f"interface: {fn} {kind[:-1]} {name!r} was removed or renamed")
    for fn, cur in current.items():
        base = spec["baseline"].get(fn)
        if base is None:
            continue
        added = spec["additions"].get(fn, {})
        for name, meta in cur["inputs"].items():
            if name in base["inputs"]:
                continue
            if name not in added.get("inputs", {}):
                errors.append(f"interface: {fn} input {name!r} is new but not recorded in interface.json additions")
            elif meta["required"] or meta["default"] != added["inputs"][name]:
                errors.append(f"interface: {fn} new input {name!r} must be optional with the root-reproducing "
                              f"default {added['inputs'][name]!r} (got required={meta['required']}, default={meta['default']!r})")
        for kind in ("secrets", "outputs"):
            for name in cur[kind]:
                if name not in base[kind] and name not in added.get(kind, []):
                    errors.append(f"interface: {fn} {kind[:-1]} {name!r} is new but not recorded in interface.json additions")
    for fn, added in spec["additions"].items():
        for name in added.get("secrets", []):
            if name in current.get(fn, {}).get("secrets", []):
                errors.append(f"interface: {fn} added secret {name!r} -- a new secret is not additive for an adopter")


def check_root_compat(bindir, errors):
    """FR-016: with routing off, intake routes nothing and keeps its old numbering group."""
    with open(ROOT_COMPAT, encoding="utf-8") as fh:
        off = json.load(fh)["routing_off"]
    project = None
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        resolve = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    env = {"GH_TOKEN": "fake", "ROUTING_PREFIX": off["routing_label_prefix"], "ISSUE": "7", "IDENTITY": "",
           "IDENTITY_KIND": "slug", "CHECK_FOLDER": "false", "FAKE_LABELS_JSON": labels_json(off["labels"])}
    r, outputs, log = run_step(resolve, env, ROOT, bindir, PROJECT_ACTION)
    project = output_value(outputs, "project")
    if r.returncode != 0 or project != "" or log:
        errors.append(f"root-compat: routing off resolved project={project!r} (rc={r.returncode}, gh log {log!r})")
    doc = intake_doc()
    ctx = {"inputs.routing-label-prefix": off["routing_label_prefix"], "inputs.issue-number": "7",
           "needs.verify-image-prerequisites.result": "skipped", "cancelled()": False}
    if evaluate_if(doc["jobs"]["routing-gate"]["if"], ctx):
        errors.append("root-compat: the routing gate runs with routing off")
    ctx.update({"needs.routing-gate.result": "skipped", "needs.routing-gate.outputs.project": ""})
    group = interpolate(doc["jobs"]["intake"]["concurrency"]["group"], ctx)
    if group != off["numbering_group"]:
        errors.append(f"root-compat: routing-off numbering group {group!r}, want {off['numbering_group']!r}")


def check_created(data, steps, bindir, errors):
    created = step_by_id(steps, "created")
    for case in data["created"]:
        env = {
            "NUM": case["branch"].rsplit("/", 1)[-1][:3],
            "PROJECT": case["project"],
            "SLUG_BUDGET": case["budget"],
            "SPEC_DRAFT_PREFIX": "spec-draft/",
            "FAKE_LS_REMOTE": f"0123abcd\trefs/heads/spec-draft/{case['branch']}\n",
        }
        r, outputs, _ = run_step(created["run"], env, ROOT, bindir)
        tag = f"created {case['name']!r}"
        if case["expect"] == "pass":
            if r.returncode != 0 or output_value(outputs, "spec-dir") != case["spec_dir"]:
                errors.append(f"{tag}: rc={r.returncode} spec-dir={output_value(outputs, 'spec-dir')!r} {r.stdout!r}")
        else:
            if r.returncode == 0:
                errors.append(f"{tag}: over-budget slug was accepted")
            for want in case.get("names", []):
                if want not in r.stdout + r.stderr:
                    errors.append(f"{tag}: error does not name {want!r}")


def main():
    if sys.argv[1:] == ["--print-interface"]:
        # Regenerates interface.json's baseline: the current interface minus
        # its recorded additions. Run only when an interface change is
        # intended and reviewed, never to make this gate pass.
        with open(INTERFACE, encoding="utf-8") as fh:
            additions = json.load(fh).get("additions", {})
        print(json.dumps(baseline_of(stage_interface(), additions), indent=2))
        return 0
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    env = data["env"]
    errors = []
    for pfx in data["prefix_accept"]:
        r = run(env, "validate-prefix", pfx)
        if r.returncode != 0:
            errors.append(f"accept prefix {pfx!r} refused: {r.stderr!r}")
    for pfx in data["prefix_reject"]:
        if run(env, "validate-prefix", pfx).returncode == 0:
            errors.append(f"reject prefix {pfx!r} was accepted")
    for case in data["budget"]:
        r = run(env, "slug-budget", case["project"])
        if r.returncode != 0 or r.stdout.strip() != str(case["budget"]):
            errors.append(f"slug-budget {case['project']!r}: rc={r.returncode} out={r.stdout!r}")
    with tempfile.TemporaryDirectory() as bindir:
        write_exec(os.path.join(bindir, "gh"), FAKE_GH)
        check_label_count(data, bindir, errors)
        doc = intake_doc()
        steps = doc["jobs"]["intake"]["steps"]
        check_rerun(data, doc["jobs"]["routing-gate"]["steps"], bindir, errors)
        check_rerun_race(doc, bindir, errors)
        check_label_first(steps, bindir, errors)
        check_label_first_hook(data, doc, bindir, errors)
        check_label_first_rescue(data, doc, bindir, errors)
        check_open_pr(doc, bindir, errors)
        check_concurrency(doc, bindir, errors)
        check_root_compat(bindir, errors)
        with tempfile.TemporaryDirectory() as gitbin:
            write_exec(os.path.join(gitbin, "git"), FAKE_GIT)
            check_created(data, steps, gitbin + os.pathsep + bindir, errors)
    check_interface(errors)
    if errors:
        print("verify-intake-routing: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    counts = ", ".join(f"{len(data[k])} {k}" for k in ("prefix_accept", "prefix_reject", "budget", "label_count", "folder", "rerun", "created", "label_first_hook"))
    print(f"verify-intake-routing: OK ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
