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

It also pins the workflow side in private-image-dogfood.yml: the
startup-agent job carries continue-on-error: true on the action step, no
model credential, a prompt and the github-actions bot in allowed_bots (else
the action skips setup), and no always() gate; classify-startup retries the
job-log fetch; classify-startup's `if:` contains !cancelled(); the
classifier is invoked as a script (single home) and no inline copy of its
marker or verdict logic appears in the workflow.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 141. It is
numbered 147, not 141: 141-146 were taken by spec 110's PR #982, which
claimed them first among the open lifecycle branches.

Usage: python3 .github/scripts/verify-agent-startup-classifier.py [--self-test]
"""
import importlib.util
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
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "private-image-dogfood.yml")

VERDICTS = ("setup-completed", "setup-failed", "unclassified")
CREDENTIAL_INPUTS = ("anthropic_api_key", "claude_code_oauth_token", "anthropic_auth_token")


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
        errors.append("private-image-dogfood.yml has no startup-agent job")
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
        steps_text = yaml.safe_dump(steps)
        if "secrets." in steps_text:
            errors.append("startup-agent steps reference a secret; no model credential may reach them")
    if classify is None:
        errors.append("private-image-dogfood.yml has no classify-startup job")
    else:
        if "!cancelled()" not in str(classify.get("if", "")):
            errors.append("classify-startup's if: must contain !cancelled()")
        runs = "\n".join(str(s.get("run", "")) for s in classify.get("steps") or [])
        if "classify-agent-startup.py" not in runs:
            errors.append("classify-startup must invoke classify-agent-startup.py")
        if not classify.get("timeout-minutes"):
            errors.append("classify-startup needs timeout-minutes (a hung gh call would hold the job for 6 hours)")
        if "job-lookup-error.log" not in runs or "::warning::" not in runs:
            errors.append("classify-startup must name a failed job lookup or log fetch, not read it as an empty log")
        if not re.search(r"for attempt in[^\n]*\n(?:.*\n)*?.*actions/jobs/\$job_id/logs(?:.*\n)*?.*sleep ", runs):
            errors.append("classify-startup must retry the job-log fetch (a just-finished job's log can 404)")
    if re.search(r"AUTH_MARKERS|failed at authentication", text):
        errors.append("private-image-dogfood.yml carries an inline copy of the classifier's marker logic")
    return errors


def run_checks(classifier=CLASSIFIER, fixtures=FIXTURES, workflow=WORKFLOW):
    mod = load_classifier(classifier)
    return check_fixtures(mod, fixtures) + check_missing_log(mod) + check_workflow(workflow)


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
        doc = yaml.safe_load(src)

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

        def drop_timeout(jobs):
            jobs["classify-startup"].pop("timeout-minutes", None)

        def drop_cancelled(jobs):
            jobs["classify-startup"]["if"] = "inputs.startup-check"

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

        expect("no timeout", mutated(drop_timeout), "timeout-minutes")
        expect("no prompt", mutated(drop_prompt), "needs a prompt")
        expect("no allowed_bots", mutated(drop_bots), "allowed_bots")
        expect("always()", mutated(use_always), "always()")
        expect("no retry", mutated(drop_retry), "retry the job-log fetch")
        expect("no continue-on-error", mutated(drop_coe), "continue-on-error")
        expect("credential input", mutated(add_key), "model credential input")
        expect("no !cancelled", mutated(drop_cancelled), "!cancelled()")
        expect("no script call", mutated(drop_script), "must invoke classify-agent-startup.py")
        del doc
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
