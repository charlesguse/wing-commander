#!/usr/bin/env python3
"""Gate 147 - the agent start-up classifier is driven by a fixture per branch
(specs/112-agent-startup-image-check, FR-008, SC-003).

A start-up check that cannot fail its subject proves nothing (Constitution
VIII). This gate imports the SAME classify() the workflow runs
(.github/scripts/classify-agent-startup.py) and drives it over every
fixture in .github/scripts/agent-startup-fixtures/:

  * each <name>.log has a <name>.expect.json and the verdict, step and
    error_contains it declares match the classifier's actual output;
  * all three verdicts (setup-completed, setup-failed, unclassified) have at
    least one fixture, and every unclassified reason begins "could not reach
    subject";
  * a missing --log is unclassified, exit 2.

It also pins the workflow side in agent-startup-check.yml: the
startup-agent job carries continue-on-error: true on the action step, no
model credential, a prompt and the github-actions bot in allowed_bots (else
the action skips setup), and no always() gate; classify-startup retries the
job-log fetch; classify-startup's `if:` contains !cancelled(); the
classifier is invoked as a script (single home) and no inline copy of its
marker or verdict logic appears in the workflow.

Both start-up jobs run whatever verify-image-prerequisites found, and
classify-startup reports that result beside its verdict: spec 112's edge
case ("the required-tool list and the start-up check disagree ... both
results are reported; neither silently overrides the other"), and SC-001's
proof (an image without `unzip`, which the tool list also rejects) is
unreachable otherwise. An `if:` that reads the prerequisite check's result
fails here.

FR-010 / SC-005: the start-up jobs live in their own reusable workflow
because GitHub checks every nested job's permissions when a reusable
workflow starts, skipped jobs included. private-image-dogfood.yml must stay
callable with `permissions: {}`, as it was before spec 112: its top level
and every job declare `permissions: {}` (or nothing), so a grant there
fails here. The dogfood wrapper's dogfood call grants nothing, and its
start-up call carries the same GHCR-namespace guard.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 141. It is
numbered 147, not 141: 141-146 were taken by spec 110's PR #982, which
claimed them first among the open lifecycle branches.

Usage: python3 .github/scripts/verify-agent-startup-classifier.py [--self-test]
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CLASSIFIER = os.path.join(HERE, "classify-agent-startup.py")
FIXTURES = os.path.join(HERE, "agent-startup-fixtures")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "agent-startup-check.yml")
DOGFOOD = os.path.join(ROOT, ".github", "workflows", "private-image-dogfood.yml")

VERDICTS = ("setup-completed", "setup-failed", "unclassified")
CREDENTIAL_INPUTS = ("anthropic_api_key", "claude_code_oauth_token", "anthropic_auth_token")
MODEL_CREDENTIAL_ENV = re.compile(
    r"\b(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|CLAUDE_CODE_OAUTH_TOKEN|CLAUDE_CODE_USE_(BEDROCK|VERTEX|FOUNDRY)"
    r"|AWS_BEARER_TOKEN_BEDROCK|ANTHROPIC_FEDERATION_RULE_ID)\b")


def load_classifier(path=CLASSIFIER):
    spec = importlib.util.spec_from_file_location("classify_agent_startup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_fixtures(mod, fixtures_dir):
    errors = []
    seen = set()
    if not os.path.isdir(fixtures_dir):
        return ["fixture directory %s is missing" % fixtures_dir]
    names = sorted(f[:-4] for f in os.listdir(fixtures_dir) if f.endswith(".log"))
    for exp in sorted(os.listdir(fixtures_dir)):
        if exp.endswith(".expect.json") and exp[: -len(".expect.json")] not in names:
            errors.append("%s has no matching .log" % exp)
    for name in names:
        expect_path = os.path.join(fixtures_dir, name + ".expect.json")
        if not os.path.exists(expect_path):
            errors.append("fixture %s lacks its .expect.json" % name)
            continue
        try:
            with open(expect_path, encoding="utf-8") as fh:
                expect = json.load(fh)
            with open(os.path.join(fixtures_dir, name + ".log"), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, ValueError) as exc:
            errors.append("fixture %s is unreadable: %s" % (name, exc))
            continue
        got = mod.classify(text)
        seen.add(got["verdict"])
        if got["verdict"] != expect.get("verdict"):
            errors.append("fixture %s: expected verdict %s, got %s" % (name, expect.get("verdict"), got["verdict"]))
            continue
        if expect.get("step") != got["step"]:
            errors.append("fixture %s: expected step %r, got %r" % (name, expect.get("step"), got["step"]))
        needle = expect.get("error_contains")
        if needle and needle not in (got["error"] or ""):
            errors.append("fixture %s: error %r does not contain %r" % (name, got["error"], needle))
        if got["verdict"] == "unclassified" and not got["reason"].startswith("could not reach subject"):
            errors.append("fixture %s: unclassified reason lacks the 'could not reach subject' prefix" % name)
        if got["verdict"] == "setup-failed" and not got["reason"].startswith("setup failed in image"):
            errors.append("fixture %s: setup-failed reason lacks the 'setup failed in image' prefix" % name)
    for v in VERDICTS:
        if v not in seen:
            errors.append("no fixture produces the %s verdict" % v)
    return errors


def check_missing_log(mod):
    errors = []
    with contextlib.redirect_stdout(io.StringIO()):
        rc = mod.main(["--log", os.path.join(tempfile.gettempdir(), "no-such-agent-startup-log.txt")])
    if rc != 2:
        errors.append("a missing --log exited %s, expected 2 (unclassified)" % rc)
    return errors


def check_workflow(path):
    errors = []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        doc = yaml.safe_load(text)
    except (OSError, yaml.YAMLError) as exc:
        return ["cannot read %s: %s" % (path, exc)]
    jobs = (doc or {}).get("jobs") or {}
    agent = jobs.get("startup-agent")
    classify = jobs.get("classify-startup")
    if agent is None:
        errors.append("agent-startup-check.yml has no startup-agent job")
    else:
        steps = agent.get("steps") or []
        action = [s for s in steps if str(s.get("uses", "")).startswith("anthropics/claude-code-action")]
        if len(action) != 1:
            errors.append("startup-agent must have exactly one claude-code-action step")
        for s in action:
            if s.get("continue-on-error") is not True:
                errors.append("startup-agent's action step must carry continue-on-error: true")
            with_ = {str(k).lower(): v for k, v in (s.get("with") or {}).items()}
            for bad in CREDENTIAL_INPUTS:
                if bad in with_:
                    errors.append("startup-agent passes the model credential input %s" % bad)
            # Without a prompt the action exits 0 before installing Claude
            # Code (agent mode's trigger is the prompt), so the check could
            # never see setup finish; a bot-dispatched run needs the bot
            # allowed past the action's human-actor check.
            if not str(with_.get("prompt") or "").strip():
                errors.append("startup-agent's action step needs a prompt, or the action skips setup")
            bots = [b.strip().lower().replace("[bot]", "") for b in str(with_.get("allowed_bots") or "").split(",")]
            if "github-actions" not in bots and "*" not in bots:
                errors.append("startup-agent's action step must allow the github-actions bot (allowed_bots)")
        for s in steps:
            if "always()" in str(s.get("if", "")):
                errors.append("startup-agent step %r uses always(); use !cancelled()" % s.get("name"))
        # The whole job but its registry credentials (container.credentials,
        # the image pull's own secrets): job env, container env and steps.
        scoped = {k: v for k, v in agent.items() if k != "container"}
        container = agent.get("container")
        scoped["container"] = ({k: v for k, v in container.items() if k != "credentials"}
                               if isinstance(container, dict) else container)
        job_text = yaml.safe_dump(scoped)
        if "secrets." in job_text:
            errors.append("startup-agent references a secret outside its registry credentials; "
                          "no model credential may reach it")
        if MODEL_CREDENTIAL_ENV.search(job_text):
            errors.append("startup-agent sets a model-credential variable")
    if classify is None:
        errors.append("agent-startup-check.yml has no classify-startup job")
    else:
        if "!cancelled()" not in str(classify.get("if", "")):
            errors.append("classify-startup's if: must contain !cancelled()")
        runs = "\n".join(str(s.get("run", "")) for s in classify.get("steps") or [])
        if "classify-agent-startup.py" not in runs:
            errors.append("classify-startup must invoke classify-agent-startup.py")
        if not classify.get("timeout-minutes"):
            errors.append("classify-startup needs timeout-minutes (a hung gh call would hold the job for 6 hours)")
        if "without a verdict" not in runs:
            errors.append("classify-startup must name a crashed classifier, not print a blank reason")
        if "job-lookup-error.log" not in runs or "::warning::" not in runs:
            errors.append("classify-startup must name a failed job lookup or log fetch, not read it as an empty log")
        if ("head -n 1" in runs or "tail -n 1" in runs
                or not re.search(r'printf \'%s\\n\' "\$job_ids" \| grep -c \.\)" -eq 1', runs)):
            errors.append("classify-startup must refuse an ambiguous startup-agent lookup, not take the first match")
        if not re.search(r"for attempt in[^\n]*\n(?:.*\n)*?.*actions/jobs/\$job_id/logs(?:.*\n)*?.*sleep ", runs):
            errors.append("classify-startup must retry the job-log fetch (a just-finished job's log can 404)")
    if re.search(r"AUTH_MARKERS|failed at authentication", text):
        errors.append("agent-startup-check.yml carries an inline copy of the classifier's marker logic")
    # Spec 112's edge case: the tool-list result never gates the start-up
    # check; both are reported.
    for name in ("startup-agent", "classify-startup"):
        job = jobs.get(name)
        if isinstance(job, dict) and "verify-image-prerequisites.result" in str(job.get("if", "")):
            errors.append("%s's if: reads verify-image-prerequisites' result, so a failed tool-list check "
                          "hides the start-up verdict (spec 112 edge case: both are reported)" % name)
    if classify is not None:
        if "container" in classify:
            errors.append("classify-startup must run on the runner, not in the image under test: there it "
                          "cannot report on an image without a shell, python3 or gh, or one that fails to pull")
        runs_on = " ".join(str(classify.get("runs-on", "")).split())
        # The same literal Gate 22 compares its registered exception against.
        if runs_on != "${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}":
            errors.append("classify-startup must keep the runner passthrough (the exact inputs.runner ternary)")
        runs = "\n".join(str(s.get("run", "")) for s in classify.get("steps") or [])
        # The classifier ships with this workflow, not the caller's repo.
        checkout = [s for s in classify.get("steps") or []
                    if str(s.get("uses", "")).startswith("actions/checkout")]
        cwith = (checkout[0].get("with") or {}) if len(checkout) == 1 else {}
        if (" ".join(str(cwith.get("repository", "")).split()) != "${{ inputs.pipeline-repo }}"
                or "steps.pipeline-ref.outputs.ref" not in str(cwith.get("ref", ""))
                or "classifier=.wing-commander-pipeline/.github/scripts/classify-agent-startup.py" not in runs
                or 'python3 "$classifier"' not in runs):
            errors.append("classify-startup must check the classifier out of inputs.pipeline-repo at the "
                          "resolved pipeline ref and run that copy, not the caller's repository's")
        if 'env.PREFIX + "startup-agent"' not in runs or "env.RUNNER_NAME" not in runs:
            errors.append("classify-startup must scope its startup-agent lookup to its own call's job-name prefix")
        envs = [s.get("env") or {} for s in classify.get("steps") or []]
        if ("needs.verify-image-prerequisites.result" not in yaml.safe_dump(envs)
                or "Image prerequisite check" not in runs):
            errors.append("classify-startup must report verify-image-prerequisites' result beside its verdict")
        # It runs on the runner, not the image: a runner without gh/jq/python3,
        # or a classifier that was never checked out, is named as such rather
        # than read as an empty log and an "exited 2" verdict.
        if ('for t in jq python3 gh; do' not in runs or 'command -v "$t"' not in runs
                or '[ ! -f "$classifier" ]' not in runs or "could not reach subject" not in runs):
            errors.append("classify-startup must name a runner missing gh/jq/python3 or a classifier "
                          "that was not checked out (could not reach subject) before classifying")
    return errors


def check_dogfood_permissions(path=DOGFOOD):
    """FR-010 / SC-005: private-image-dogfood.yml stays callable with
    `permissions: {}`, as before spec 112 -- no job may need a grant."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        return ["cannot read %s: %s" % (path, exc)]
    errors = []
    if doc.get("permissions") != {}:
        errors.append("private-image-dogfood.yml's top-level permissions are %r, not {}" % doc.get("permissions"))
    jobs = doc.get("jobs") or {}
    if not jobs:
        errors.append("private-image-dogfood.yml has no jobs")
    for name, job in sorted(jobs.items()):
        perms = (job or {}).get("permissions", {})
        if perms not in ({}, None):
            errors.append("private-image-dogfood.yml job %s declares permissions %r: GitHub checks every "
                          "job's permissions when the workflow starts, skipped or not, so a caller granting "
                          "permissions: {} would fail (FR-010, SC-005)" % (name, perms))
    return errors


WRAPPER = os.path.join(ROOT, ".github", "workflows", "wing-commander-private-image-dogfood.yml")


def check_wrapper(path=WRAPPER):
    """The wrapper's dispatch input names an image; the registry secrets go
    with it only inside this owner's own GHCR namespace."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        return ["cannot read %s: %s" % (path, exc)]
    jobs = (doc or {}).get("jobs") or {}
    refuse = jobs.get("refuse-foreign-image") or {}
    norm = lambda v: " ".join(str(v or "").split())
    # The one namespace test lives on refuse-foreign-image, which fails for
    # a foreign dispatched image; dogfood runs only when it was skipped.
    want_refuse = ("inputs.container-image != '' && !startsWith(inputs.container-image, "
                   "format('ghcr.io/{0}/', github.repository_owner))")
    want_job = ("!cancelled() && needs.refuse-foreign-image.result == 'skipped' && "
                "(inputs.container-image != '' || vars.WING_COMMANDER_PRIVATE_IMAGE_DOGFOOD_IMAGE != '')")
    errors = []
    if norm(refuse.get("if")) != want_refuse:
        errors.append("the wrapper's refuse-foreign-image job no longer holds the namespace test "
                      "(if: %r)" % norm(refuse.get("if")))
    refuse_steps = refuse.get("steps") or []
    refuse_runs = "\n".join(str(s.get("run", "")) for s in refuse_steps)
    tolerated = refuse.get("continue-on-error") or any(
        s.get("continue-on-error") or "if" in s for s in refuse_steps)
    if (tolerated or "::error::" not in refuse_runs
            or not re.search(r"(?m)^\s*exit 1\s*$", refuse_runs)):
        errors.append("the wrapper's refuse-foreign-image job does not fail (::error:: and exit 1, "
                      "no continue-on-error, no step if:)")
    calls = (("dogfood", "./.github/workflows/private-image-dogfood.yml"),
             ("startup-check", "./.github/workflows/agent-startup-check.yml"))
    for name, uses in calls:
        job = jobs.get(name) or {}
        needs = job.get("needs")
        needs = needs if isinstance(needs, list) else [needs]
        if job.get("uses") != uses:
            errors.append("the wrapper's %s job does not call %s (uses: %r)" % (name, uses, job.get("uses")))
        if "refuse-foreign-image" not in needs:
            errors.append("the wrapper's %s job does not need refuse-foreign-image (needs: %r)" % (name, needs))
        if norm(job.get("if")) != want_job:
            errors.append("the wrapper's %s job may run on a dispatched container-image outside this "
                          "owner's GHCR namespace (if: %r)" % (name, norm(job.get("if"))))
    perms = (jobs.get("startup-check") or {}).get("permissions") or {}
    granted = (perms in ("read-all", "write-all") if isinstance(perms, str)
               else isinstance(perms, dict) and all(perms.get(k) in ("read", "write")
                                                    for k in ("actions", "contents")))
    if not granted:
        errors.append("the wrapper's startup-check job must grant actions: read and contents: read "
                      "(the called jobs request both; GitHub refuses a call granting less)")
    # Both calls check the same image with the same credentials.
    dog, start = jobs.get("dogfood") or {}, jobs.get("startup-check") or {}
    if ((dog.get("with") or {}).get("container-image") != (start.get("with") or {}).get("container-image")
            or dog.get("secrets") != start.get("secrets")):
        errors.append("the wrapper's dogfood and startup-check calls must pass the same container-image "
                      "and registry secrets")
    if " ".join(str(((jobs.get("startup-check") or {}).get("with") or {}).get("pipeline-repo", "")).split()) \
            != "${{ github.repository }}":
        errors.append("the wrapper's startup-check job must pass pipeline-repo: ${{ github.repository }} "
                      "(a fork's commit is not in the default pipeline repository)")
    # The dogfood call is the adopter who never opted in: it grants nothing.
    if (jobs.get("dogfood") or {}).get("permissions") != {}:
        errors.append("the wrapper's dogfood job must call private-image-dogfood.yml with permissions: {} "
                      "(FR-010: an adopter who changes nothing keeps working)")
    return errors


def run_checks(classifier=CLASSIFIER, fixtures=FIXTURES, workflow=WORKFLOW):
    mod = load_classifier(classifier)
    return (check_fixtures(mod, fixtures) + check_missing_log(mod) + check_workflow(workflow)
            + check_dogfood_permissions() + check_wrapper())


def self_test():
    failures = []

    def expect(label, errs, needle):
        if not any(needle in e for e in errs):
            failures.append("%s: expected an error containing %r, got %r" % (label, needle, errs))

    base = run_checks()
    if base:
        failures.append("baseline is not clean: %r" % base)
    mod = load_classifier()
    with tempfile.TemporaryDirectory() as tmp:
        # Missing expect file.
        d = os.path.join(tmp, "a")
        shutil.copytree(FIXTURES, d)
        os.remove(os.path.join(d, "auth-reached.expect.json"))
        expect("missing expect", check_fixtures(mod, d), "lacks its .expect.json")
        # Verdict branch without a fixture.
        d = os.path.join(tmp, "b")
        shutil.copytree(FIXTURES, d)
        for f in os.listdir(d):
            if f.startswith("setup-failed"):
                os.remove(os.path.join(d, f))
        expect("no setup-failed fixture", check_fixtures(mod, d), "no fixture produces the setup-failed")
        # Drifted verdict.
        d = os.path.join(tmp, "c")
        shutil.copytree(FIXTURES, d)
        p = os.path.join(d, "auth-reached.expect.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "unclassified", "step": None, "error_contains": None}, fh)
        expect("drifted verdict", check_fixtures(mod, d), "expected verdict unclassified")
        # Workflow mutations.
        with open(WORKFLOW, encoding="utf-8") as fh:
            src = fh.read()

        def mutated(fn):
            m = yaml.safe_load(src)
            fn(m["jobs"])
            p = os.path.join(tmp, "wf.yml")
            with open(p, "w", encoding="utf-8") as fh:
                yaml.safe_dump(m, fh)
            return check_workflow(p)

        def drop_coe(jobs):
            for s in jobs["startup-agent"]["steps"]:
                s.pop("continue-on-error", None)

        def add_key(jobs):
            for s in jobs["startup-agent"]["steps"]:
                if "uses" in s:
                    s.setdefault("with", {})["anthropic_api_key"] = "x"

        def first_match(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace('grep -c .)" -eq 1', 'grep -c .)" -ge 1')

        def drop_timeout(jobs):
            jobs["classify-startup"].pop("timeout-minutes", None)

        def drop_cancelled(jobs):
            jobs["classify-startup"]["if"] = "inputs.container-image != ''"

        def drop_script(jobs):
            for s in jobs["classify-startup"]["steps"]:
                s.pop("run", None)

        def drop_prompt(jobs):
            for s in jobs["startup-agent"]["steps"]:
                if "uses" in s and "claude-code-action" in s["uses"]:
                    s["with"].pop("prompt", None)

        def drop_bots(jobs):
            for s in jobs["startup-agent"]["steps"]:
                if "uses" in s and "claude-code-action" in s["uses"]:
                    s["with"].pop("allowed_bots", None)

        def use_always(jobs):
            jobs["startup-agent"]["steps"][-1]["if"] = "always()"


        def drop_retry(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = re.sub(r"for attempt in [^\n]*", "true", s["run"])

        def job_env_secret(jobs):
            jobs["startup-agent"]["env"] = {"CLAUDE_CODE_OAUTH_TOKEN": "${{ secrets.X }}"}

        def container_env_secret(jobs):
            jobs["startup-agent"]["container"].setdefault("env", {})["ANTHROPIC_API_KEY"] = "x"

        def drop_warning(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace("::warning::", "")

        def drop_no_verdict(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace("without a verdict", "")

        expect("job env secret", mutated(job_env_secret), "outside its registry credentials")
        expect("container env credential", mutated(container_env_secret), "model-credential variable")
        expect("no lookup warning", mutated(drop_warning), "name a failed job lookup")
        expect("no crash reason", mutated(drop_no_verdict), "crashed classifier")
        p_inline = os.path.join(tmp, "inline.yml")
        with open(p_inline, "w", encoding="utf-8") as fh:
            fh.write(src + "\n# AUTH_MARKERS = [...]\n")
        expect("inline marker copy", check_workflow(p_inline), "inline copy")
        expect("no timeout", mutated(drop_timeout), "timeout-minutes")
        with open(WRAPPER, encoding="utf-8") as fh:
            wsrc = fh.read()
        p_wrap = os.path.join(tmp, "wrapper.yml")
        with open(p_wrap, "w", encoding="utf-8") as fh:
            fh.write(wsrc.replace("needs.refuse-foreign-image.result == 'skipped'",
                                  "needs.refuse-foreign-image.result != 'cancelled'"))
        expect("unconstrained wrapper dispatch", check_wrapper(p_wrap), "outside this owner's GHCR namespace")
        with open(p_wrap, "w", encoding="utf-8") as fh:
            fh.write(wsrc.replace("&& !startsWith(inputs.container-image", "&& startsWith(inputs.container-image"))
        expect("refuse test inverted", check_wrapper(p_wrap), "namespace test")
        with open(p_wrap, "w", encoding="utf-8") as fh:
            fh.write(wsrc.replace("    needs: refuse-foreign-image\n", ""))
        expect("dogfood without needs", check_wrapper(p_wrap), "does not need refuse-foreign-image")
        with open(p_wrap, "w", encoding="utf-8") as fh:
            fh.write(wsrc.replace("    needs: refuse-foreign-image\n", "", 1))
        expect("dogfood (only) without needs", check_wrapper(p_wrap), "dogfood job does not need")
        def wrapper_jobs(fn):
            m = yaml.safe_load(wsrc)
            fn(m["jobs"])
            with open(p_wrap, "w", encoding="utf-8") as fh:
                yaml.safe_dump(m, fh)
            return check_wrapper(p_wrap)

        expect("startup call unguarded",
               wrapper_jobs(lambda j: j["startup-check"].update({"if": "!cancelled()"})),
               "startup-check job may run")
        expect("startup call dropped", wrapper_jobs(lambda j: j.pop("startup-check")),
               "startup-check job does not call")
        expect("startup call without pipeline-repo",
               wrapper_jobs(lambda j: j["startup-check"]["with"].pop("pipeline-repo")),
               "pipeline-repo")
        read_all = wrapper_jobs(lambda j: j["startup-check"].update({"permissions": "read-all"}))
        if any("actions: read" in e for e in read_all):
            failures.append("startup call with permissions: read-all was refused: %r" % read_all)
        expect("startup call without contents: read",
               wrapper_jobs(lambda j: j["startup-check"].update({"permissions": {"actions": "read"}})),
               "contents: read")
        expect("startup call on another image",
               wrapper_jobs(lambda j: j["startup-check"]["with"].update({"container-image": "x"})),
               "same container-image")
        expect("startup call without actions: read",
               wrapper_jobs(lambda j: j["startup-check"].update({"permissions": {}})),
               "must grant actions: read")
        expect("dogfood call granted",
               wrapper_jobs(lambda j: j["dogfood"].update({"permissions": {"actions": "read"}})),
               "permissions: {}")
        # O1 regression (FR-010 / SC-005): a grant on any
        # private-image-dogfood.yml job, the shape spec 112 first shipped.
        with open(DOGFOOD, encoding="utf-8") as fh:
            dsrc = fh.read()
        p_dog = os.path.join(tmp, "dogfood.yml")

        def dogfood_mutated(fn):
            m = yaml.safe_load(dsrc)
            fn(m)
            with open(p_dog, "w", encoding="utf-8") as fh:
                yaml.safe_dump(m, fh)
            return check_dogfood_permissions(p_dog)

        expect("dogfood job granted actions: read",
               dogfood_mutated(lambda m: m["jobs"]["dogfood"].update(
                   {"permissions": {"actions": "read", "contents": "read"}})),
               "job dogfood declares permissions")
        expect("dogfood gains a start-up job with a grant",
               dogfood_mutated(lambda m: m["jobs"].update(
                   {"startup-agent": {"if": "false", "permissions": {"contents": "read"},
                                      "runs-on": "x", "steps": [{"run": "true"}]}})),
               "job startup-agent declares permissions")
        expect("dogfood top level granted",
               dogfood_mutated(lambda m: m.update({"permissions": {"contents": "read"}})),
               "top-level permissions")
        def wrapper_mutated(fn):
            m = yaml.safe_load(wsrc)
            fn(m["jobs"]["refuse-foreign-image"])
            with open(p_wrap, "w", encoding="utf-8") as fh:
                yaml.safe_dump(m, fh)
            return check_wrapper(p_wrap)

        def no_exit(job):
            for s in job["steps"]:
                s["run"] = s["run"].replace("exit 1", "true")

        expect("refusal that does not fail", wrapper_mutated(no_exit), "does not fail")
        expect("refusal tolerated", wrapper_mutated(lambda j: j.update({"continue-on-error": True})),
               "does not fail")
        expect("refusal step skipped", wrapper_mutated(lambda j: j["steps"][0].update({"if": "false"})),
               "does not fail")
        expect("first match", mutated(first_match), "ambiguous")

        def last_match(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace("""if [ "$(printf '%s\\n' "$job_ids" | grep -c .)" -eq 1 ]; then""",
                                                """if [ -n "$job_ids" ]; then job_ids=$(echo "$job_ids" | sed '$!d')""")

        expect("last match (only the self-name count left)", mutated(last_match), "ambiguous")
        expect("no prompt", mutated(drop_prompt), "needs a prompt")
        expect("no allowed_bots", mutated(drop_bots), "allowed_bots")
        expect("always()", mutated(use_always), "always()")
        expect("no retry", mutated(drop_retry), "retry the job-log fetch")
        expect("no continue-on-error", mutated(drop_coe), "continue-on-error")
        expect("credential input", mutated(add_key), "model credential input")
        expect("no !cancelled", mutated(drop_cancelled), "!cancelled()")

        # O2 regression: the start-up jobs gated on the tool-list result, the
        # shape that made SC-001's image-without-unzip proof unreachable.
        def gate_on_prereq(name):
            def fn(jobs):
                jobs[name]["if"] = ("!cancelled() && needs.verify-image-prerequisites.result != 'failure' "
                                    "&& inputs.container-image != ''")
            return fn

        expect("startup-agent gated on prereqs", mutated(gate_on_prereq("startup-agent")),
               "startup-agent's if: reads verify-image-prerequisites")
        expect("classify-startup gated on prereqs", mutated(gate_on_prereq("classify-startup")),
               "classify-startup's if: reads verify-image-prerequisites")

        def drop_prereq_report(jobs):
            for s in jobs["classify-startup"]["steps"]:
                (s.get("env") or {}).pop("PREREQ_RESULT", None)

        def classify_in_image(jobs):
            jobs["classify-startup"]["container"] = {"image": "${{ inputs.container-image }}"}

        expect("classify-startup in the image", mutated(classify_in_image), "must run on the runner")
        expect("classify-startup off the runner passthrough",
               mutated(lambda j: j["classify-startup"].update({"runs-on": "ubuntu-latest"})),
               "runner passthrough")
        def caller_checkout(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if str(s.get("uses", "")).startswith("actions/checkout"):
                    s["with"] = {"sparse-checkout": ".github/scripts"}
                if "run" in s:
                    s["run"] = s["run"].replace(".wing-commander-pipeline/.github/scripts/", ".github/scripts/")
                    s["run"] = s["run"].replace('python3 "$classifier"', "python3 .github/scripts/classify-agent-startup.py")

        expect("classifier from the caller's checkout", mutated(caller_checkout), "inputs.pipeline-repo")

        def unscoped_lookup(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace('env.PREFIX + "startup-agent"', '"startup-agent"')

        expect("unscoped lookup", mutated(unscoped_lookup), "own call's job-name prefix")
        def drop_preflight(jobs):
            for s in jobs["classify-startup"]["steps"]:
                if "run" in s:
                    s["run"] = s["run"].replace('[ ! -f "$classifier" ]', "false")

        expect("no runner/classifier preflight", mutated(drop_preflight), "could not reach subject")
        expect("prereq result not reported", mutated(drop_prereq_report),
               "report verify-image-prerequisites' result")
        expect("no script call", mutated(drop_script), "must invoke classify-agent-startup.py")
    for f in failures:
        print("::error::Gate 147 self-test: " + f)
    if not failures:
        print("Gate 147 self-test: ok")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    errors = run_checks()
    for e in errors:
        print("::error::Gate 147: " + e)
    if not errors:
        print("Gate 147: ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
