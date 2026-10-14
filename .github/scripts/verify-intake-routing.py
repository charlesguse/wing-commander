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
  * intake.yml's project guidance (`project-guidance`): the label is created
    before the first branch push, and the root prompt gains nothing;
  * intake.yml's "Resolve created spec" (`created`) with a fake `git`: a
    subfolder slug over the label budget fails, the root has no budget.

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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
PROJECT_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-project")
INTAKE = os.path.join(ROOT, ".github", "workflows", "intake.yml")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-intake-routing", "cases.json")

FAKE_GH = """#!/usr/bin/env bash
if [ "$1 $2" = "issue view" ]; then
  expr=""
  while [ "$#" -gt 0 ]; do [ "$1" = --jq ] && expr="$2"; shift; done
  printf '%s' "$FAKE_LABELS_JSON" | jq -r "$expr"
  exit 0
fi
if [ "$1 $2" = "issue comment" ]; then echo "$*" >> "$FAKE_GH_LOG"; exit 0; fi
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
        env = {"GH_TOKEN": "fake", "ISSUE": "7", "FAKE_LABELS_JSON": labels_json(case["labels"])}
        r, outputs, _ = run_step(rerun["run"], env, ROOT, bindir)
        got = output_value(outputs, "existing")
        if r.returncode != 0 or got != case["existing"]:
            errors.append(f"rerun {case['name']!r}: rc={r.returncode} existing={got!r}, want {case['existing']!r}")


def check_label_first(steps, bindir, errors):
    guidance = step_by_id(steps, "project-guidance")
    r, outputs, _ = run_step(guidance["run"], {"PROJECT": "ideas/alpha", "SLUG_BUDGET": "33"}, ROOT, bindir)
    if r.returncode != 0:
        errors.append(f"label-first: project-guidance failed {r.stderr!r}")
    elif not any("BEFORE you push" in line and "label" in line for line in outputs.splitlines()):
        errors.append("label-first: the subfolder intake prompt does not create the spec label before the first push")
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
        check_label_first(steps, bindir, errors)
        check_concurrency(doc, bindir, errors)
        with tempfile.TemporaryDirectory() as gitbin:
            write_exec(os.path.join(gitbin, "git"), FAKE_GIT)
            check_created(data, steps, gitbin + os.pathsep + bindir, errors)
    if errors:
        print("verify-intake-routing: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    counts = ", ".join(f"{len(data[k])} {k}" for k in ("prefix_accept", "prefix_reject", "budget", "label_count", "folder", "rerun", "created"))
    print(f"verify-intake-routing: OK ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
