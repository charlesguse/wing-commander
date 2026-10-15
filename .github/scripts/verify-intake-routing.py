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
    first; "Open the spec PR" (`open-pr`) follows that push, and "Fail on a
    refused subfolder publish" (`refused-publish`) turns a refusal by either
    continue-on-error step into a red run naming it (T067);
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
if [ -n "${FAKE_GH_FAIL:-}" ]; then echo "fake gh: HTTP 502" >&2; exit 1; fi
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
if [ "$1 $2" = "pr create" ]; then
  echo "$*" >> "$FAKE_GH_LOG"
  # The first FAKE_PR_CREATE_FAILS creates fail, as a transient API error.
  if [ "$(grep -c '^pr create' "$FAKE_GH_LOG")" -le "${FAKE_PR_CREATE_FAILS:-0}" ]; then
    echo "fake gh: HTTP 502" >&2; exit 1
  fi
  exit 0
fi
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
    # MF-20: routing refuses rather than falling back to the root when the
    # labels cannot be read.
    r, outputs, _ = run_step(resolve, {**base_env, "CHECK_FOLDER": "false", "FAKE_GH_FAIL": "1",
                                       "FAKE_LABELS_JSON": labels_json(["node:ideas/alpha"])}, ROOT, bindir, PROJECT_ACTION)
    if r.returncode == 0 or output_value(outputs, "project") is not None or "could not read the labels" not in r.stdout:
        errors.append(f"label_count unreadable labels: expected refusal, rc={r.returncode} {r.stdout!r}")
    # MF-13 (FR-023): the findings-label prefix reaches validate-prefix
    # through the composite's input, not only through the fixed families.
    for pfx, findings, want_ok in (("found-by:", "found-by", False), ("found:", "found-by", False),
                                   ("found-by:", "", True), ("node:", "found-by", True)):
        env = {**base_env, "ROUTING_PREFIX": pfx, "FINDINGS_LABEL_PREFIX": findings, "CHECK_FOLDER": "false",
               "FAKE_LABELS_JSON": labels_json([])}
        r, _, _ = run_step(resolve, env, ROOT, bindir, PROJECT_ACTION)
        if (r.returncode == 0) != want_ok:
            errors.append(f"findings prefix: routing prefix {pfx!r} with findings-label-prefix {findings!r} "
                          f"rc={r.returncode}, want {'accepted' if want_ok else 'refused'} {r.stdout!r}")
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        resolve_env = yaml.safe_load(fh)["runs"]["steps"][0].get("env", {})
    if "inputs.findings-label-prefix" not in str(resolve_env.get("FINDINGS_LABEL_PREFIX", "")):
        errors.append("findings prefix: wing-commander-project does not hand its findings-label-prefix input to validate-prefix")
    for s in intake_doc()["jobs"].values():
        for st in s.get("steps") or []:
            w = st.get("with") or {}
            if str(st.get("uses", "")).endswith("/wing-commander-project") and w.get("routing-label-prefix"):
                if "inputs.findings-label-prefix" not in str(w.get("findings-label-prefix", "")):
                    errors.append(f"findings prefix: intake's {st.get('name')!r} does not pass findings-label-prefix")
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
    # MF-23: an intake job that never started (cancelled while pending in its
    # numbering group) releases the claim from a job of its own.
    rc_job = doc["jobs"].get("release-claim")
    if not isinstance(rc_job, dict):
        errors.append("race: no release-claim job releases the claim when the intake job never runs")
    else:
        rc_if = " ".join(str(rc_job.get("if", "")).split())
        if "always()" not in rc_if:
            errors.append(f"race: release-claim's if: is not always()-gated ({rc_if!r})")
        # MF-39: it runs whenever the intake job did not report the claim
        # released -- including a job that failed before any step ran, and
        # a successful one whose continue-on-error release failed (review
        # gate round 5) -- and never otherwise.
        for result, released, want in (("cancelled", "", True), ("skipped", "", True), ("failure", "", True),
                                       ("failure", "true", False), ("success", "true", False),
                                       ("success", "", True), ("cancelled", "true", False)):
            ctx = {"always()": True, "cancelled()": False, "needs.verify-image-prerequisites.result": "success",
                   "needs.routing-gate.outputs.claim-label": CLAIM, "needs.intake.result": result,
                   "needs.intake.outputs.claim-released": released}
            if evaluate_if(rc_if, ctx) != want:
                errors.append(f"race: release-claim {'skips' if want else 'runs'} for intake result={result!r} "
                              f"claim-released={released!r} ({rc_if!r})")
        if "steps.release-claim.outputs.released" not in str((doc["jobs"]["intake"].get("outputs") or {}).get("claim-released", "")):
            errors.append("race: the intake job does not export claim-released from its release step")
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "labels.json")
            with open(state, "w", encoding="utf-8") as fh:
                json.dump([CLAIM], fh)
            env = {"GH_TOKEN": "fake", "GH_REPO": "o/r", "ISSUE": "7", "CLAIM": CLAIM, "FAKE_LABEL_STATE": state}
            r, outputs, _ = run_step(release.get("run", ""), env, ROOT, bindir)
            if r.returncode != 0 or output_value(outputs, "released") != "true":
                errors.append(f"race: the in-job release did not report released=true rc={r.returncode} {outputs!r}")
        if "concurrency" in rc_job:
            errors.append("race: release-claim holds a concurrency group, so it can itself be left pending")
        if not {"routing-gate", "intake"} <= set(rc_job.get("needs") or []):
            errors.append("race: release-claim does not wait for the routing gate and the intake job")
        rc_steps = rc_job.get("steps") or []
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "labels.json")
            with open(state, "w", encoding="utf-8") as fh:
                json.dump([CLAIM], fh)
            env = {"GH_TOKEN": "fake", "GH_REPO": "o/r", "ISSUE": "7", "CLAIM": CLAIM, "FAKE_LABEL_STATE": state}
            for s in rc_steps:
                run_step(s.get("run", ""), env, ROOT, bindir)
            with open(state, encoding="utf-8") as fh:
                if CLAIM in json.load(fh):
                    errors.append("race: release-claim's steps did not remove the claim label")

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
    # -b main: the containment test reads the default branch from origin's HEAD.
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True, capture_output=True)
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
    # MF-47: the push is handed exactly the branch the label step labelled,
    # and no branch at all for the root or when nothing was labelled.
    def branch_for(prefix, project, slug):
        return interpolate(str(with_.get("branch", "")), {
            "inputs.routing-label-prefix": prefix, "steps.num.outputs.project": project,
            "steps.label-first.outputs.slug": slug, "inputs.spec-draft-prefix": "spec-draft/"})
    for prefix, project, slug, want in (("node:", "ideas/alpha", "001-login", "spec-draft/ideas/alpha/001-login"),
                                        ("node:", "ideas/alpha", "", ""), ("", "ideas/alpha", "001-login", ""),
                                        ("node:", "", "001-login", "")):
        got = branch_for(prefix, project, slug)
        if got != want:
            errors.append(f"label-first rescue: branch is {got!r} for prefix={prefix!r} project={project!r} "
                          f"slug={slug!r}, want {want!r}")
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
                # MF-47: a labelled slug handed some other branch is refused.
                penv = {**penv, "LF_SLUG": slug, "EXPECTED_BRANCH": case["ref"] + "-other"}
                r, outputs, _ = run_step(publish, penv, ws, bindir, PUBLISH_ACTION)
                if output_value(outputs, "push-ok") != "false":
                    errors.append(f"{tag}: the push published a branch other than the one labelled")
            env = {"BEFORE_SHA": base, "WORKDIR": "", "PUSH_TOKEN": "", "PUSH_REPO": "",
                   "EXPECTED_BRANCH": branch_for("node:", case["project"], slug),
                   "PROJECT": case["project"], "LF_ISSUE": "7", "LF_NUM": case["num"], "LF_PREFIX": "spec-draft/",
                   "LF_SLUG": slug}
            r, outputs, _ = run_step(publish, env, ws, bindir, PUBLISH_ACTION)
            ok = output_value(outputs, "push-ok")
            if r.returncode != 0 or ok not in ("true", "false"):
                errors.append(f"{tag}: the rescue step failed rc={r.returncode} push-ok={ok!r} {r.stderr!r}")
                continue
            judge_label_first(tag, case, 0 if ok == "true" else 1, lr.stdout + lr.stderr + r.stdout + r.stderr,
                              origin, state, errors)
            judge_refused_publish(steps, tag, case["project"], "success" if lr.returncode == 0 else "failure",
                                  slug, ok, case["expect"] == "fail", bindir, errors)
    # An agent that stopped without a spec: nothing to label, no error.
    with tempfile.TemporaryDirectory() as tmp:
        ws, _, _, _ = intake_workspace(tmp)
        lenv = {"GH_TOKEN": "fake", "ISSUE": "7", "PROJECT": "ideas/alpha", "NUM": "001", "PREFIX": "spec-draft/",
                "FAKE_LABEL_STATE": os.path.join(tmp, "labels.json")}
        lr, louts, log = run_step(label_run, lenv, ws, bindir, LABEL_FIRST_ACTION)
        if lr.returncode != 0 or output_value(louts, "slug") != "" or "label create" in log:
            errors.append(f"label-first rescue: an agent with no commit was not a quiet no-op rc={lr.returncode} {lr.stderr!r}")
        judge_refused_publish(steps, "label-first rescue (no commit)", "ideas/alpha", "success",
                              output_value(louts, "slug") or "", "true", False, bindir, errors)
    # T067: a push refused after the label landed (a race, or a branch the
    # label step did not label) still fails the run; the root never does.
    judge_refused_publish(steps, "label-first rescue (push refused after label)", "ideas/alpha", "success",
                          "001-login", "false", True, bindir, errors)
    judge_refused_publish(steps, "label-first rescue (root)", "", "failure", "", "false", False, bindir, errors)
    # MF-31: the branch is on the remote, but the label step labelled
    # nothing -- it got there around label-first.
    judge_refused_publish(steps, "label-first rescue (branch around label-first)", "ideas/alpha", "success",
                          "", "true", True, bindir, errors, created="ideas/alpha/001-login")
    judge_refused_publish(steps, "label-first rescue (root, branch found)", "", "skipped",
                          "", "true", False, bindir, errors, created="001-login")
    # MF-45: a failed containment check skips "Label first" (no orphan
    # spec label refusing every re-run) and leaves refused-publish quiet, so
    # the containment failure is the run's only red.
    fail_ctx = {"cancelled()": False, "steps.agent.outcome": "success", "inputs.routing-label-prefix": "node:",
                "steps.num.outputs.project": "ideas/alpha", "steps.containment.outcome": "failure",
                "steps.label-first.outcome": "skipped", "steps.label-first.outputs.slug": "",
                "steps.publish-stranded.outputs.push-ok": "", "steps.created-ref.outputs.slug": ""}
    if evaluate_if(str(lf_step.get("if", "")), fail_ctx):
        errors.append("label-first rescue: the label step runs after a failed containment check")
    if evaluate_if(str(step_by_id(steps, "refused-publish").get("if", "")),
                   {**fail_ctx, "steps.created-ref.outputs.slug": "ideas/alpha/001-login"}):
        errors.append("label-first rescue: refused-publish fires after a failed containment check")
    if not evaluate_if(str(lf_step.get("if", "")), {**fail_ctx, "steps.containment.outcome": "success"}):
        errors.append("label-first rescue: the label step does not run after a passing containment check")


def judge_refused_publish(steps, tag, project, lf_outcome, slug, push_ok, want_fail, bindir, errors, created=None):
    """T067 (FR-014): intake's "Fail on a refused subfolder publish"
    (`refused-publish`) turns a refusal by the continue-on-error label or
    push step into a red run naming it, and stays quiet otherwise. MF-31: a
    branch "Resolve created spec" found with no label-step slug reached the
    remote around label-first, and fails the run too."""
    if created is None:
        created = f"{project}/{slug}" if slug and push_ok == "true" else ""
    step = step_by_id(steps, "refused-publish")
    if steps.index(step) < steps.index(step_by_id(steps, "publish-stranded")):
        errors.append("refused-publish: runs before the label-first push")
    if step.get("continue-on-error"):
        errors.append("refused-publish: carries continue-on-error, so it cannot fail the run")
    ctx = {"cancelled()": False, "steps.agent.outcome": "success", "inputs.routing-label-prefix": "node:",
           "steps.num.outputs.project": project, "steps.label-first.outcome": lf_outcome if project else "skipped",
           "steps.label-first.outputs.slug": slug, "steps.publish-stranded.outputs.push-ok": push_ok,
           "steps.created-ref.outputs.slug": created,
           "steps.containment.outcome": "success" if project else "skipped"}
    fires = evaluate_if(step["if"], ctx)
    if fires != want_fail:
        errors.append(f"{tag}: refused-publish {'fires' if fires else 'stays quiet'} "
                      f"(label={lf_outcome}, slug={slug!r}, push-ok={push_ok!r})")
        return
    if not fires:
        return
    env = {key: interpolate(str(val), {**ctx, "inputs.spec-draft-prefix": "spec-draft/"})
           for key, val in (step.get("env") or {}).items()}
    r, _, _ = run_step(step["run"], env, ROOT, bindir)
    if lf_outcome != "failure" and not slug and created:
        want = "without the label-first check"
    else:
        want = "label-first check refused" if lf_outcome == "failure" else "was refused after spec:"
    if r.returncode == 0 or "::error::" not in r.stdout or want not in r.stdout or project not in r.stdout:
        errors.append(f"{tag}: refused-publish did not fail naming the refusal rc={r.returncode} {r.stdout!r}")


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
    # Review round 2: a failed create must not skip the success()-gated
    # steps after it; a deferred step near the job's end turns it red, and
    # the failed-post-agent-step report names that step.
    if step.get("continue-on-error") is not True:
        errors.append("open-pr: not continue-on-error, so a failed create skips every success()-gated step after it")
    fail = step_by_id(steps, "unopened-pr")
    if fail is None:
        errors.append("open-pr: no 'Fail on an unopened subfolder spec PR' step turns a failed create red")
    else:
        fcond = str(fail.get("if", ""))
        for outcome, want_run in (("failure", True), ("success", False), ("skipped", False)):
            if evaluate_if(fcond, {"cancelled()": False, "steps.open-pr.outcome": outcome}) != want_run:
                errors.append(f"unopened-pr: runs={not want_run} with open-pr outcome {outcome!r} ({fcond!r})")
        if fail.get("continue-on-error"):
            errors.append("unopened-pr: is continue-on-error, so it cannot fail the run")
        failed_step = step_by_id(steps, "failed-step")
        cands = str((failed_step or {}).get("with", {}).get("candidates-json", ""))
        if "steps.unopened-pr.conclusion" not in cands or steps.index(failed_step) < steps.index(fail):
            errors.append("unopened-pr: not among the failed-post-agent-step candidates read after it")
        with tempfile.TemporaryDirectory() as tmp:
            r, _, _ = run_step(fail["run"], {"PROJECT": "ideas/alpha", "BRANCH": "spec-draft/ideas/alpha/001-login"},
                               tmp, bindir)
            if r.returncode == 0 or "spec-draft/ideas/alpha/001-login" not in r.stdout:
                errors.append(f"unopened-pr: did not fail naming the branch rc={r.returncode} {r.stdout!r}")
    # Review round 1: the siblings' guards -- a closed lifecycle or a
    # skipped agent opens no PR.
    open_ctx = {"cancelled()": False, "steps.lifecycle-gate.outputs.is-open": "true",
                "steps.agent.outcome": "success", "steps.publish-stranded.outputs.push-ok": "true",
                "steps.publish-stranded.outputs.label-first-slug": "001-login"}
    if not evaluate_if(cond, open_ctx):
        errors.append("open-pr: does not run after a published label-first push")
    for key, val in (("steps.lifecycle-gate.outputs.is-open", "false"), ("steps.agent.outcome", "skipped")):
        if evaluate_if(cond, {**open_ctx, key: val}):
            errors.append(f"open-pr: runs with {key} == {val!r}")
    # A transient create failure is retried, re-checking for an open PR
    # first; one that persists fails the step naming the branch.
    with tempfile.TemporaryDirectory() as tmp:
        nosleep = os.path.join(tmp, "bin")
        os.makedirs(nosleep)
        write_exec(os.path.join(nosleep, "sleep"), "#!/usr/bin/env bash\nexit 0\n")
        spec = os.path.join(tmp, "ideas", "alpha", "specs", "001-login")
        os.makedirs(spec)
        with open(os.path.join(spec, "spec.md"), "w", encoding="utf-8") as fh:
            fh.write("# Feature Specification: Login\n")
        for fails, want_ok in ((1, True), (9, False)):
            state = os.path.join(tmp, "labels.json")
            with open(state, "w", encoding="utf-8") as fh:
                json.dump([], fh)
            env = {"GH_TOKEN": "fake", "ISSUE": "7", "PROJECT": "ideas/alpha", "SLUG": "001-login",
                   "PREFIX": "spec-draft/", "BASE": "main", "BODY_FILE": os.path.join(tmp, "body.md"),
                   "RECORD": os.path.join(tmp, "record"), "FAKE_LABEL_STATE": state, "FAKE_PR_NUMBER": "",
                   "FAKE_PR_CREATE_FAILS": str(fails)}
            r, _, log = run_step(step["run"], env, tmp, nosleep + os.pathsep + bindir)
            creates = [line for line in log.splitlines() if line.startswith("pr create")]
            lists = [line for line in log.splitlines() if line.startswith("pr list")]
            if want_ok and (r.returncode != 0 or len(creates) != 2 or len(lists) != 2):
                errors.append(f"open-pr: a transient create failure was not retried rc={r.returncode} "
                              f"creates={len(creates)} lookups={len(lists)} {r.stderr!r}")
            if not want_ok and (r.returncode == 0 or len(creates) != 3
                                or "spec-draft/ideas/alpha/001-login" not in r.stdout or "::error::" not in r.stdout):
                errors.append(f"open-pr: a persistent create failure did not fail naming the branch "
                              f"rc={r.returncode} creates={len(creates)} {r.stdout!r}")
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
    elif "Do not push" not in outputs or "skip step 6's" not in outputs:
        errors.append("label-first: the subfolder intake prompt does not hand the push, label and PR to the pipeline")
    elif "at most 33 characters" not in outputs:
        errors.append("label-first: the subfolder intake prompt does not carry the slug budget")
    # MF-30: a routed agent cannot push at all, so no push skips label-first.
    targs = (step_by_id(steps, "tool-args-intake").get("with") or {})
    # MF-49: the pipeline creates and applies the label and opens the PR,
    # so the routed agent is denied those calls too, keeping issue comments.
    denied = [t.strip() for t in str(targs.get("project-deny-tools", "")).split(",")]
    for tool in ("Bash(git push:*)", "Bash(gh label create:*)",
                 "Bash(gh issue edit:*)", "Bash(gh pr create:*)"):
        if tool not in denied:
            errors.append(f"label-first: the routed intake agent is not denied {tool} (project-deny-tools)")
    if any(t.startswith("Bash(gh issue comment") for t in denied):
        errors.append("label-first: the routed intake agent is denied gh issue comment (project-deny-tools)")
    r, outputs, _ = run_step(guidance["run"], {"PROJECT": "", "SLUG_BUDGET": ""}, ROOT, bindir)
    body = outputs.split("\n", 1)[1] if "\n" in outputs else ""
    if r.returncode != 0 or body.strip() != "WC_INTAKE_PROJECT_GUIDANCE_EOF":
        errors.append(f"label-first: root project guidance is not empty: {outputs!r}")
    # MF-24 (FR-016): the empty root paragraph adds no line to the prompt,
    # so it is interpolated at the end of an existing line, not on its own.
    prompt = str((step_by_id(steps, "agent").get("with") or {}).get("prompt", ""))
    if "specs/.${{ steps.project-guidance.outputs.routing-notes }}\n4. Write" not in prompt:
        errors.append("label-first: the routing paragraph is not spliced onto step 3's last line, so a root prompt gains lines")


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
    """Resolve created spec: the ref step reads the pushed branch back (and
    the slug budget); the spec dir comes from the shared parser
    (wing-commander-project, MF-21), never an inline path split."""
    created_ref = step_by_id(steps, "created-ref")
    names = step_by_id(steps, "created")
    if not str(names.get("uses", "")).endswith("/wing-commander-project") \
            or "steps.created-ref.outputs.slug" not in str((names.get("with") or {}).get("identity", "")):
        errors.append("created: the spec dir is not read from the created slug by wing-commander-project")
    if "##*/" in created_ref["run"] or "%/*" in created_ref["run"]:
        errors.append("created: the ref step still splits the project path inline")
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        resolve = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    for case in data["created"]:
        env = {
            "NUM": case["branch"].rsplit("/", 1)[-1][:3],
            "PROJECT": case["project"],
            "SLUG_BUDGET": case["budget"],
            "SPEC_DRAFT_PREFIX": "spec-draft/",
            "FAKE_LS_REMOTE": f"0123abcd\trefs/heads/spec-draft/{case['branch']}\n",
        }
        r, outputs, _ = run_step(created_ref["run"], env, ROOT, bindir)
        tag = f"created {case['name']!r}"
        if case["expect"] == "pass":
            slug = output_value(outputs, "slug") or ""
            nenv = {"GH_TOKEN": "", "ROUTING_PREFIX": "", "ISSUE": "", "IDENTITY": slug, "IDENTITY_KIND": "slug",
                    "CHECK_FOLDER": "false", "FINDINGS_LABEL_PREFIX": ""}
            nr, nouts, _ = run_step(resolve, nenv, ROOT, bindir, PROJECT_ACTION)
            if r.returncode != 0 or nr.returncode != 0 or output_value(nouts, "spec-dir") != case["spec_dir"]:
                errors.append(f"{tag}: rc={r.returncode}/{nr.returncode} spec-dir={output_value(nouts, 'spec-dir')!r} {r.stdout!r}")
            if output_value(outputs, "branch") != "spec-draft/" + case["branch"]:
                errors.append(f"{tag}: branch={output_value(outputs, 'branch')!r}, want the exact spec-draft/{case['branch']}")
        else:
            if r.returncode == 0:
                errors.append(f"{tag}: over-budget slug was accepted")
            for want in case.get("names", []):
                if want not in r.stdout + r.stderr:
                    errors.append(f"{tag}: error does not name {want!r}")


def check_spec_pr_lookup(steps, bindir, errors):
    """MF-16: the spec PR is found by the exact branch "Resolve created
    spec" read back, never by a `<prefix>NNN-` prefix match (which misses a
    subfolder branch and can match another project's NNN); no branch looks
    up nothing."""
    for name in ("Resolve spec PR URL", "Label spec PR to match the issue"):
        step = next((s for s in steps if s.get("name") == name), None)
        if step is None:
            errors.append(f"spec PR lookup: no {name!r} step")
            continue
        if "steps.created-ref.outputs.branch" not in str((step.get("env") or {}).get("BRANCH", "")):
            errors.append(f"spec PR lookup: {name!r} is not handed the created branch")
        if "startswith(" in step["run"]:
            errors.append(f"spec PR lookup: {name!r} still matches a branch-name prefix")
        for branch, want in (("spec-draft/ideas/alpha/001-login", True), ("", False)):
            env = {"GH_TOKEN": "fake", "ISSUE": "7", "BRANCH": branch, "FAKE_PR_NUMBER": ""}
            _, _, log = run_step(step["run"], env, ROOT, bindir)
            looked = f"--head {branch}" in log if branch else "pr list" in log
            if looked != want:
                errors.append(f"spec PR lookup: {name!r} with branch={branch!r} -> gh log {log!r}")


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
        check_spec_pr_lookup(steps, bindir, errors)
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
