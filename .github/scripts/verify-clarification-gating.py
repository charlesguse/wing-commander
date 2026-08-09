#!/usr/bin/env python3
"""Behavioral tests for the clarification callout gating in intake and clarify.

WHY THIS EXISTS
---------------
Both stages end in a two-way callout split: either "answer these questions"
or "review the spec PR". Which one fires is decided by shell in one step and
then by the `if:` expressions of the steps after it. Gates 1-3 in
lint-workflows.yml prove that shell parses and that the workflow registers;
none of them can see that the split sends a requester somewhere they cannot
act, or announces a spec as ready when it visibly is not.

That is not hypothetical. Four defects of exactly this class have shipped:

  #159   the marker grep used a literal that could never match, so the
         questionnaire branch never fired at all.
  (a)    spec 032 moved the decision onto structured output and removed the
         `spec-dir != ''` guard, but re-added it to only ONE arm of the
         split. The other arm could then fire on the "no discernible feature
         request" path — where the agent STOPs before any spec, branch, or
         spec:/stage: label exists. `--json-schema` still forces a conforming
         result there, so a non-empty `clarifications` array is plausible.
         Intake would post "Answer the open clarification questions" on an
         issue where wing-commander-2-clarify.yml's trigger (which requires a
         `spec:` label plus stage:spec|clarify) can never fire on the reply.
  (b)    the colon-form cross-check logged a mismatch and proceeded, so an
         agent that left [NEEDS CLARIFICATION: markers in the committed
         spec.md while returning `clarifications: []` got "Review the spec
         PR" announced and the markers merged.
  (c)    clarify grepped "$SPEC_DIR/spec.md" with no existence guard (intake
         had one), so an unreadable spec.md produced marker=false and a
         spurious mismatch on every run that legitimately had open questions.

So this harness EXECUTES the shipped decision shell against synthetic agent
transcripts, then evaluates the shipped `if:` expressions against the outputs
that shell actually produced, and asserts which callouts fire. It reads all
of it out of the workflows at run time — there is no second copy to drift
(same discipline as Gate 4's auto-update harness and Gate 5's collector
fixture, both added after a verifier sat green while checking a code path
that did not ship).

It ends with MUTATION checks that reintroduce each defect above and assert
the suite fails. A test that cannot fail is not a test.

Usage: python3 .github/scripts/verify-clarification-gating.py
Requires: bash, jq (both present on ubuntu-latest runners).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

INTAKE = ".github/workflows/intake.yml"
CLARIFY = ".github/workflows/clarify.yml"

# The literal token prefix the watchdog's collector scans for. Emitting a
# bare word instead put these signals behind the collector's first-match-wins
# cap, where any earlier "denied" line masked them permanently.
SENTINEL_PREFIX = "WC-SENTINEL: "


# --------------------------------------------------------------------------
# Per-stage wiring
# --------------------------------------------------------------------------
class Stage:
    def __init__(self, name, path, validate, decide, render, announce_q,
                 resolve_pr, announce_pr, out_prefix, spec_dir_ref,
                 validate_exits_in_place):
        self.name = name
        self.path = path
        self.validate = validate
        self.decide = decide
        self.render = render
        self.announce_q = announce_q
        self.resolve_pr = resolve_pr
        self.announce_pr = announce_pr
        # The `steps.<id>.outputs.` prefix the decision step publishes under.
        self.out_prefix = out_prefix
        # The `${{ ... }}` expression each stage uses for its spec dir env.
        self.spec_dir_ref = spec_dir_ref
        # clarify's validation gate exits 1 in place; intake's publishes a
        # verdict and defers the exit to the job's last step.
        self.validate_exits_in_place = validate_exits_in_place

    @property
    def callout_steps(self):
        return [self.render, self.announce_q, self.resolve_pr, self.announce_pr]

    @property
    def posting_steps(self):
        return {self.announce_q, self.announce_pr}


INTAKE_STAGE = Stage(
    name="intake",
    path=INTAKE,
    validate="Validate agent result",
    decide="Check whether the spec still needs clarification",
    render="Render clarification questionnaire",
    announce_q="Announce clarification needed",
    resolve_pr="Resolve spec PR URL",
    announce_pr="Announce spec PR ready for review",
    out_prefix="steps.clarification.outputs.",
    spec_dir_ref="${{ steps.created.outputs.spec-dir }}",
    validate_exits_in_place=False,
)

CLARIFY_STAGE = Stage(
    name="clarify",
    path=CLARIFY,
    validate="Fail on agent API error",
    decide="Determine clarification follow-up outcome",
    render="Render clarification questionnaire",
    announce_q="Announce remaining clarification questions",
    resolve_pr="Resolve spec PR URL",
    announce_pr="Announce spec PR ready for review",
    out_prefix="steps.clarification.outputs.",
    spec_dir_ref="${{ steps.ctx.outputs.spec-dir }}",
    validate_exits_in_place=True,
)


def load_steps(stage):
    """Map step name -> step dict for the single job in the stage file."""
    wf = yaml.safe_load(open(stage.path, encoding="utf-8")) or {}
    steps = {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name")
            if name and name not in steps:
                steps[name] = step
    wanted = [stage.validate, stage.decide] + stage.callout_steps
    missing = [n for n in wanted if n not in steps]
    if missing:
        sys.exit(
            f"::error file={stage.path}::verify-clarification-gating could not "
            f"find step(s) {missing!r}. If they were renamed, update this script "
            f"and the workflow together — do not delete the scenario."
        )
    return steps


# --------------------------------------------------------------------------
# A deliberately small GitHub-expression evaluator
# --------------------------------------------------------------------------
TERM = re.compile(r"^\s*(?P<lhs>[A-Za-z0-9_.\-]+)\s*(?P<op>==|!=)\s*'(?P<rhs>[^']*)'\s*$")


def evaluate_if(expr, ctx, step_name, path):
    """Evaluate an `if:` built from `&&`-joined `path == 'lit'` terms.

    Anything richer (||, !, functions, expression interpolation) is a hard
    error rather than a guess: silently mis-evaluating a condition is the very
    failure mode this harness exists to catch.
    """
    if expr is None:
        return True
    expr = str(expr).strip()
    if "||" in expr or "${{" in expr or "!" in expr.replace("!=", ""):
        sys.exit(
            f"::error file={path}::step {step_name!r} has an if: this harness "
            f"cannot evaluate ({expr!r}). Extend evaluate_if() in "
            f"verify-clarification-gating.py rather than dropping the step."
        )
    for term in expr.split("&&"):
        m = TERM.match(term)
        if not m:
            sys.exit(
                f"::error file={path}::step {step_name!r} has an if: term this "
                f"harness cannot parse ({term.strip()!r}). Extend evaluate_if()."
            )
        actual = ctx.get(m.group("lhs"), "")
        if m.group("op") == "==":
            if actual != m.group("rhs"):
                return False
        elif actual == m.group("rhs"):
            return False
    return True


# --------------------------------------------------------------------------
# Executing a shipped run: block
# --------------------------------------------------------------------------
def run_shell(script, workdir, env_extra, runner_temp, path):
    """Run one extracted run: block; return (rc, output, outputs, summary)."""
    script = script.replace("${{ runner.temp }}", runner_temp)
    if "${{" in script:
        sys.exit(
            f"::error file={path}::an extracted run: block still contains an "
            f"unhandled ${{{{ }}}} expression; teach run_shell() to resolve it."
        )

    out_file = os.path.join(workdir, "gh_output")
    sum_file = os.path.join(workdir, "gh_summary")
    open(out_file, "w").close()
    open(sum_file, "w").close()

    env = dict(os.environ)
    env.update({"RUNNER_TEMP": runner_temp,
                "GITHUB_OUTPUT": out_file,
                "GITHUB_STEP_SUMMARY": sum_file})
    env.update(env_extra)

    # GitHub's default shell for a `run:` step with no `shell:` key on Linux
    # is `bash -e {0}` — errexit, and NOT pipefail. Neither workflow sets a
    # step-level `shell:` or a `defaults:` block, so this is what really runs.
    # Adding -o pipefail would make the harness stricter than production.
    proc = subprocess.run(["bash", "-e", "-c", script],
                          cwd=workdir, env=env, capture_output=True, text=True)

    outputs = {}
    for line in open(out_file, encoding="utf-8"):
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1)
            outputs[k] = v
    return (proc.returncode, proc.stdout + proc.stderr, outputs,
            open(sum_file, encoding="utf-8").read())


def step_env(step, subs, path):
    resolved = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        for expr, value in subs.items():
            v = v.replace(expr, value)
        if "${{" in v:
            sys.exit(f"::error file={path}::unresolved env {k}={v!r}; add a "
                     f"substitution for it in the harness.")
        resolved[k] = v
    return resolved


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def transcript(result_obj, is_error=False, subtype="success", raw_result=None):
    """A claude-execution-output.json whose terminal .result is a JSON STRING.

    That is the real shape the action writes, and the shipped shell re-parses
    it with a second jq pass.
    """
    if raw_result is None:
        raw_result = json.dumps(result_obj)
    return json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": "..."}},
        {"type": "result", "subtype": subtype, "is_error": is_error,
         "result": raw_result},
    ])


QUESTIONS = [
    {"question": "Which auth provider should the service accept?",
     "context": "Security section",
     "options": [{"answer": "OIDC only", "implications": "No legacy clients"},
                 {"answer": "OIDC + API keys", "implications": None}]},
    {"question": "What is the retention window for audit logs?"},
]

# Every field the schema lets be an empty string is empty here. jq's // only
# falls through on null/false, so "" used to render a bare "**Context**:"
# line and an empty Implications cell inside the posted callout.
BLANK_FIELD_QUESTIONS = [
    {"question": "Question with blank optionals",
     "context": "",
     "options": [{"answer": "Only option", "implications": ""}]},
    {"question": "Question with whitespace context",
     "context": "   ",
     "options": []},
]


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
# markers: whether the spec.md on disk carries a colon-form marker.
#   True/False force it; None means "agree with the structured result".
#   "missing" means no spec.md file at all.
INTAKE_SCENARIOS = [
    dict(
        name="no discernible feature request, empty clarifications",
        why="The agent STOPped at prompt step 2 and left the array empty, as "
            "the prompt instructs. Its own issue comment is the whole output.",
        result={"specified": False, "clarifications": []},
        spec_dir="", expect_valid=True, expect_needed="false",
        expect_fires=set(),
    ),
    dict(
        name="no discernible feature request WITH questions (defect a)",
        why="--json-schema forces a conforming result wherever the agent "
            "stopped, so a step-2 STOP can still return questions. No spec, no "
            "branch, no spec:/stage: label exists, so wing-commander-2-clarify "
            "can never fire on a reply. A questionnaire here is a dead end.",
        result={"specified": False, "clarifications": QUESTIONS},
        spec_dir="", expect_valid=True, expect_needed="false",
        expect_fires=set(), expect_summary="dead end",
    ),
    dict(
        name="spec authored with open questions",
        why="The happy questionnaire path: render, then post it.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"},
    ),
    dict(
        name="spec authored, no open questions",
        why="The happy spec-PR path.",
        result={"specified": True, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="false",
        expect_fires={"resolve_pr", "announce_pr"},
    ),
    dict(
        name="no questions returned but the spec still has markers (defect b)",
        why="The agent left colon-form markers in the committed spec.md (which "
            "prompt step 3 tells it to do) but returned clarifications: []. "
            "Announcing 'Review the spec PR' here gets the markers merged. The "
            "cross-check must VETO the readiness claim and fail the run.",
        result={"specified": True, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=True,
        expect_valid=True, expect_needed="false", expect_blocked="true",
        expect_fires=set(), expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
    ),
    dict(
        name="questions returned but the spec has no markers (warn only)",
        why="The other direction of disagreement is harmless — the questions "
            "are real and answerable — so it warns and still posts.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", markers=False,
        expect_valid=True, expect_needed="true", expect_blocked="",
        expect_fires={"render", "announce_q"},
        expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
    ),
    dict(
        name="spec authored with questions but no discoverable branch",
        why="A failed push (or ls-remote read-back) must NOT swallow an "
            "authored questionnaire — that silent loss is why the spec-dir "
            "guard came off the decision. The questions post, and the orphan "
            "sentinel says the branch is missing.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"},
        expect_stdout=SENTINEL_PREFIX + "clarification-orphaned",
    ),
    dict(
        name="spec authored, no questions, no discoverable branch",
        why="Nothing to announce: there is no resolvable PR to point at.",
        result={"specified": True, "clarifications": []},
        spec_dir="", expect_valid=True, expect_needed="false",
        expect_fires=set(),
    ),
    dict(
        name="questionnaire whose optional fields are empty strings (defect d)",
        why="The schema permits context/implications to be \"\", and jq's // "
            "does not treat \"\" as absent. The posted callout must not carry a "
            "bare '**Context**:' line or an empty Implications cell.",
        result={"specified": True, "clarifications": BLANK_FIELD_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"},
    ),
    dict(
        name="terminal result missing the specified discriminator",
        why="FR-002: a malformed structured result is a loud failure, never "
            "coerced into a decision. Without this, a dropped `specified` would "
            "silently read as the step-2 STOP path.",
        result={"clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=False,
        expect_needed=None, expect_fires=set(),
    ),
    dict(
        name="terminal result is a bare array (no schema wrapper)",
        why="Deliberately NOT degraded to the array the way watchdog's diagnose "
            "read-back does. That precedent's payload has no discriminator, so "
            "unwrapping loses nothing; here it would mean inventing `specified` "
            "— the exact field whose absence caused defect (a). Loud failure "
            "beats a fabricated discriminator.",
        result=None, raw_result=json.dumps(QUESTIONS),
        spec_dir="specs/042-a-feature", expect_valid=False,
        expect_needed=None, expect_fires=set(),
    ),
    dict(
        name="terminal result is not JSON at all",
        why="Same contract, blunter input.",
        result=None, raw_result="I could not complete the task.",
        spec_dir="", expect_valid=False, expect_needed=None, expect_fires=set(),
    ),
    dict(
        name="agent errored",
        why="is_error true never reaches the decision.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="", is_error=True, subtype="error_during_execution",
        expect_valid=False, expect_needed=None, expect_fires=set(),
    ),
]

CLARIFY_SCENARIOS = [
    dict(
        name="reply answered nothing (early STOP)",
        why="answered=false is clarify's `none`: the agent's own comment is the "
            "only issue-facing output, and no cross-check runs.",
        result={"answered": False, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="none", expect_fires=set(),
    ),
    dict(
        name="reply resolved some questions, others remain",
        why="The happy questionnaire path.",
        result={"answered": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="needs-clarification", expect_fires={"render", "announce_q"},
    ),
    dict(
        name="reply resolved everything",
        why="The happy spec-PR path.",
        result={"answered": True, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="ready", expect_fires={"resolve_pr", "announce_pr"},
    ),
    dict(
        name="no questions returned but the spec still has markers (defect b)",
        why="Same veto as intake's: announcing readiness here merges the "
            "markers.",
        result={"answered": True, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=True,
        expect_valid=True, expect_outcome="ready", expect_blocked="true",
        expect_fires=set(), expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
    ),
    dict(
        name="spec.md is unreadable while questions remain (defect c)",
        why="clarify grepped $SPEC_DIR/spec.md with no existence guard while "
            "intake had one. A missing file made marker=false, so EVERY run "
            "with legitimately open questions reported a spurious mismatch — "
            "the cross-check crying wolf about its own inability to read.",
        result={"answered": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", markers="missing",
        expect_valid=True, expect_outcome="needs-clarification",
        expect_fires={"render", "announce_q"},
        forbid_stdout="clarification-mismatch",
    ),
    dict(
        name="questionnaire whose optional fields are empty strings (defect d)",
        why="Same render contract as intake's.",
        result={"answered": True, "clarifications": BLANK_FIELD_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="needs-clarification", expect_fires={"render", "announce_q"},
    ),
    dict(
        name="terminal result missing the answered discriminator",
        why="FR-002, clarify's half.",
        result={"clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=False,
        expect_outcome=None, expect_fires=set(),
    ),
]


# --------------------------------------------------------------------------
# The suite
# --------------------------------------------------------------------------
def run_scenario(stage, steps, sc, tmproot):
    failures = []
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    tag = f"[{stage.name}: {sc['name']}]"

    with open(os.path.join(runner_temp, "claude-execution-output.json"),
              "w", encoding="utf-8") as fh:
        fh.write(transcript(sc.get("result"), is_error=sc.get("is_error", False),
                            subtype=sc.get("subtype", "success"),
                            raw_result=sc.get("raw_result")))

    markers = sc.get("markers")
    if sc["spec_dir"] and markers != "missing":
        os.makedirs(os.path.join(workdir, sc["spec_dir"]), exist_ok=True)
        if markers is None:
            res = sc.get("result") or {}
            markers = bool(res.get("clarifications"))
        body = "# Spec\n"
        if markers:
            body += "\n[NEEDS CLARIFICATION: which auth provider?]\n"
        with open(os.path.join(workdir, sc["spec_dir"], "spec.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(body)
    elif markers == "missing":
        # The directory exists but spec.md does not — the case the guard is for.
        os.makedirs(os.path.join(workdir, sc["spec_dir"]), exist_ok=True)

    subs = {
        stage.spec_dir_ref: sc["spec_dir"],
        "${{ inputs.spec-draft-prefix }}": "spec-draft/",
        "${{ steps.num.outputs.num }}": "042",
        "${{ steps.ctx.outputs.token }}": "dummy-token",
    }
    ctx = {
        "steps.lifecycle-gate.outputs.is-open": "true",
        "steps.agent.outcome": "success",
        "steps.created.outputs.spec-dir": sc["spec_dir"],
    }

    # --- validation gate --------------------------------------------------
    job_failed = False
    v = steps[stage.validate]
    if evaluate_if(v.get("if"), ctx, stage.validate, stage.path):
        rc, out, outputs, _ = run_shell(v["run"], workdir,
                                        step_env(v, subs, stage.path),
                                        runner_temp, stage.path)
        if stage.validate_exits_in_place:
            got_valid = "false" if rc != 0 else "true"
            job_failed = rc != 0
        else:
            got_valid = outputs.get("valid", "")
            if rc != 0:
                failures.append(f"{tag} {stage.validate!r} exited {rc}; it must "
                                f"exit 0 and publish a verdict so the stage's "
                                f"side-effect steps still run.\n{out}")
        ctx["steps.agent-result.outputs.valid"] = outputs.get("valid", "")
    else:
        got_valid = ""
        ctx["steps.agent-result.outputs.valid"] = ""

    want_valid = "true" if sc["expect_valid"] else "false"
    if got_valid != want_valid:
        failures.append(f"{tag} expected the validation gate to say "
                        f"{want_valid!r}, got {got_valid!r}. {sc['why']}")

    # --- decision step ----------------------------------------------------
    decide_out = ""
    decide_sum = ""
    d = steps[stage.decide]
    if not job_failed and evaluate_if(d.get("if"), ctx, stage.decide, stage.path):
        rc, decide_out, outputs, decide_sum = run_shell(
            d["run"], workdir, step_env(d, subs, stage.path), runner_temp,
            stage.path)
        if rc != 0:
            failures.append(f"{tag} {stage.decide!r} exited {rc}:\n{decide_out}")
        for k, val in outputs.items():
            ctx[stage.out_prefix + k] = val
        for k in ("needed", "specified", "outcome", "blocked"):
            ctx.setdefault(stage.out_prefix + k, "")
    else:
        for k in ("needed", "specified", "outcome", "blocked"):
            ctx[stage.out_prefix + k] = ""

    for key, want in (("needed", sc.get("expect_needed", "SKIP")),
                      ("outcome", sc.get("expect_outcome", "SKIP")),
                      ("blocked", sc.get("expect_blocked", "SKIP"))):
        if want == "SKIP":
            continue
        want = want if want is not None else ""
        got = ctx.get(stage.out_prefix + key, "")
        if got != want:
            failures.append(f"{tag} expected {key}={want!r}, got {got!r}. "
                            f"{sc['why']}")

    if sc.get("expect_stdout") and sc["expect_stdout"] not in decide_out:
        failures.append(
            f"{tag} expected {sc['expect_stdout']!r} on stdout. The watchdog's "
            f"collector reads job logs, not the step summary, and only an "
            f"emitted '{SENTINEL_PREFIX}<token>' escapes its first-match-wins "
            f"cap on bare words. Got:\n{decide_out}")
    if sc.get("forbid_stdout") and sc["forbid_stdout"] in decide_out:
        failures.append(f"{tag} did NOT expect {sc['forbid_stdout']!r} on "
                        f"stdout. {sc['why']}\nGot:\n{decide_out}")
    if sc.get("expect_summary") and sc["expect_summary"] not in decide_sum:
        failures.append(f"{tag} expected {sc['expect_summary']!r} in the step "
                        f"summary. Got:\n{decide_sum}")

    # --- which callouts fire ---------------------------------------------
    by_key = {"render": stage.render, "announce_q": stage.announce_q,
              "resolve_pr": stage.resolve_pr, "announce_pr": stage.announce_pr}
    fired = {k for k, n in by_key.items()
             if not job_failed
             and evaluate_if(steps[n].get("if"), ctx, n, stage.path)}
    if fired != sc["expect_fires"]:
        failures.append(f"{tag} wrong callouts fired.\n"
                        f"    expected: {sorted(sc['expect_fires']) or '(none)'}\n"
                        f"    actual:   {sorted(fired) or '(none)'}\n"
                        f"    {sc['why']}")

    both = {by_key[k] for k in fired} & stage.posting_steps
    if len(both) > 1:
        failures.append(f"{tag} both posting callouts fired ({sorted(both)}). "
                        f"They are the two arms of one decision and can never "
                        f"be simultaneously correct (#159).")

    # --- the rendered questionnaire ---------------------------------------
    if "render" in fired:
        r = steps[stage.render]
        rc, out, _, _ = run_shell(r["run"], workdir, step_env(r, subs, stage.path),
                                  runner_temp, stage.path)
        target = None
        for cand in ("intake-clarification.md", "clarify-followup.md"):
            p = os.path.join(runner_temp, cand)
            if os.path.exists(p):
                target = p
        if rc != 0 or target is None:
            failures.append(f"{tag} {stage.render!r} exited {rc} / wrote no "
                            f"file:\n{out}")
        else:
            body = open(target, encoding="utf-8").read()
            n = len((sc.get("result") or {}).get("clarifications") or [])
            for i in range(1, n + 1):
                if f"## Question {i}" not in body:
                    failures.append(f"{tag} rendered questionnaire is missing "
                                    f"'## Question {i}'. Got:\n{body}")
            if "null" in body:
                failures.append(f"{tag} rendered questionnaire leaked a literal "
                                f"'null' into the posted markdown:\n{body}")
            if re.search(r"^\*\*Context\*\*:\s*$", body, re.M):
                failures.append(f"{tag} rendered a bare '**Context**:' line — "
                                f"an empty-string context must be omitted "
                                f"entirely, not rendered as a header with "
                                f"nothing under it:\n{body}")
            if re.search(r"^\|[^|\n]*\|[^|\n]*\|\s*\|\s*$", body, re.M):
                failures.append(f"{tag} rendered an empty Implications cell; "
                                f"blank implications must fall back to the em "
                                f"dash:\n{body}")
            if not body.strip():
                failures.append(f"{tag} rendered questionnaire is empty but "
                                f"{stage.announce_q!r} is about to post it.")

    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    return failures


def suite(loaded, tmproot):
    failures = []
    for stage, steps, scenarios in loaded:
        for sc in scenarios:
            failures += run_scenario(stage, steps, sc, tmproot)
    return failures


# --------------------------------------------------------------------------
# Mutations — each reintroduces a defect that actually shipped
# --------------------------------------------------------------------------
def _strip_conjunct(steps, stage, needle):
    for name in stage.callout_steps:
        cond = steps[name].get("if")
        if cond:
            steps[name]["if"] = " && ".join(
                t for t in str(cond).split("&&") if needle not in t).strip()


def mut_drop_specified(loaded):
    """Defect (a): the questionnaire arm ignores `specified`."""
    for stage, steps, _ in loaded:
        if stage.name != "intake":
            continue
        steps[stage.decide]["run"] = steps[stage.decide]["run"].replace(
            'if [ "$specified" = "true" ] && [ "$count" -gt 0 ]; then',
            'if [ "$count" -gt 0 ]; then')
        _strip_conjunct(steps, stage, "outputs.specified")


def mut_drop_veto(loaded):
    """Defect (b): the cross-check logs a mismatch and proceeds."""
    for stage, steps, _ in loaded:
        run = steps[stage.decide]["run"]
        steps[stage.decide]["run"] = run.replace(
            'echo "blocked=true" >> "$GITHUB_OUTPUT"', ':')
        _strip_conjunct(steps, stage, "outputs.blocked")


def mut_drop_existence_guard(loaded):
    """Defect (c): clarify greps spec.md with no existence guard."""
    for stage, steps, _ in loaded:
        if stage.name != "clarify":
            continue
        run = steps[stage.decide]["run"]
        steps[stage.decide]["run"] = run.replace(
            'if [ -n "$SPEC_DIR" ] && [ -f "$SPEC_DIR/spec.md" ]; then',
            'if true; then')


def mut_blank_strings(loaded):
    """Defect (d): jq's // treated "" as present."""
    for stage, steps, _ in loaded:
        run = steps[stage.render]["run"]
        run = run.replace("(if (.value.context | blank) then \"\" else "
                          "\"**Context**: \\(.value.context)\\n\\n\" end)",
                          "(if (.value.context // null) != null then "
                          "\"**Context**: \\(.value.context)\\n\\n\" else \"\" end)")
        run = run.replace("\\(if (.value.implications | blank) then \"—\" else "
                          "(.value.implications | cell) end)",
                          "\\((.value.implications // \"—\") | cell)")
        steps[stage.render]["run"] = run


MUTATIONS = [
    ("the questionnaire arm ignoring `specified` (dead-end callout)",
     mut_drop_specified),
    ("the cross-check logging a mismatch instead of vetoing readiness",
     mut_drop_veto),
    ("clarify grepping spec.md with no existence guard", mut_drop_existence_guard),
    ("jq's // treating an empty string as a present value", mut_blank_strings),
]


def main():
    if not shutil.which("jq"):
        sys.exit("::error::verify-clarification-gating requires jq on PATH.")

    loaded = [
        (INTAKE_STAGE, load_steps(INTAKE_STAGE), INTAKE_SCENARIOS),
        (CLARIFY_STAGE, load_steps(CLARIFY_STAGE), CLARIFY_SCENARIOS),
    ]

    tmproot = tempfile.mkdtemp()
    try:
        failures = suite(loaded, tmproot)
        for f in failures:
            print(f"::error::{f}")

        for label, apply_mutation in MUTATIONS:
            mutated = [(s, copy.deepcopy(steps), sc) for s, steps, sc in loaded]
            apply_mutation(mutated)
            if all(copy.deepcopy(a[1]) == b[1]
                   for a, b in zip(loaded, mutated)):
                print(f"::error::mutation {label!r} changed nothing — the code "
                      f"it edits was rewritten. Update the mutation so this "
                      f"harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, tmproot)
            if broke:
                print(f"Mutation OK — {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} broke "
                      f"nothing in this suite, so the suite is not testing that "
                      f"defect. Fix the scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    total = sum(len(s[2]) for s in loaded)
    print(f"clarification gating: {total} scenario(s) across "
          f"{len(loaded)} stage(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
