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
  (e)    the `specified` guard added for (a) also gates the spec-PR arm, and
         its overlap with a resolvable spec dir suppresses BOTH arms at once.
         An agent that authored the spec, pushed it and opened the PR but
         mis-set the discriminator left a real spec PR unannounced, with no
         mismatch (both views say "no questions"), no sentinel and no failing
         step — the whole stage swallowed, green.

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

RUNNING THIS ON WINDOWS
-----------------------
It works, but two PATH entries lie about what they are, and both fail in
ways that look like a defect in the workflows rather than in the harness:

  * `bash` on PATH is usually C:\\Windows\\System32\\bash.exe — the WSL
    launcher, not a POSIX bash in this machine's environment. WSL is a
    separate Linux VM: it does NOT inherit the Windows process environment
    (that needs WSLENV), so RUNNER_TEMP/GITHUB_OUTPUT/GITHUB_STEP_SUMMARY
    all arrive empty and every scenario fails on a missing transcript.
    Windows temp paths handed to it would be meaningless anyway.
    resolve_bash() below probes for this and picks Git Bash instead.
  * `python3` on PATH is usually the Microsoft Store stub, which exits 49
    without running anything. Invoke this file with `python`, or with an
    explicit interpreter path.

Set WC_BASH to override the bash choice.
"""
import copy
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, resolve_bash, run_step, use_utf8_stdout)

INTAKE = ".github/workflows/intake.yml"
CLARIFY = ".github/workflows/clarify.yml"

# The literal token prefix the watchdog's collector scans for. Emitting a
# bare word instead put these signals behind the collector's first-match-wins
# cap, where any earlier "denied" line masked them permanently.
SENTINEL_PREFIX = "WC-SENTINEL: "


BASH = None          # set in main(), so importing this module probes nothing


# --------------------------------------------------------------------------
# Per-stage wiring
# --------------------------------------------------------------------------
class Stage:
    def __init__(self, name, path, validate, decide, render, announce_q,
                 resolve_pr, announce_pr, out_prefix, spec_dir_ref,
                 validate_exits_in_place, fail_steps):
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
        # The deferred `exit 1` steps at the end of the job. These are the
        # ONLY thing that turns a verdict into a red run, and they are not
        # callouts — nothing they do is visible on the issue. Left
        # unevaluated (as they were until this was added), the suite could
        # not tell "vetoed and failed the run" from "vetoed and finished
        # green having posted nothing at all" — which is the worse of the
        # two, because the requester then sees only the run-started comment
        # while a marker-carrying spec PR sits in the review queue.
        self.fail_steps = fail_steps

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
    fail_steps=["Fail on invalid agent result",
                "Fail on unresolved clarification markers"],
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
    fail_steps=["Fail on unresolved clarification markers"],
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
    wanted = ([stage.validate, stage.decide] + stage.callout_steps
              + stage.fail_steps)
    missing = [n for n in wanted if n not in steps]
    if missing:
        sys.exit(
            f"::error file={stage.path}::verify-clarification-gating could not "
            f"find step(s) {missing!r}. If they were renamed, update this script "
            f"and the workflow together — do not delete the scenario. Deleting a "
            f"'Fail on ...' step is how a vetoed run goes green with nothing "
            f"posted, so its absence is a hard error here, not a skipped check."
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
        term = term.strip()
        # always() only cancels the implicit success() GitHub Actions would
        # otherwise AND onto every `if:` — it says nothing about any ctx
        # value. Every caller already tracks job_failed separately from this
        # evaluator (see the `not job_failed and evaluate_if(...)` call
        # sites), so a bare always() term is a no-op here, not a hard error.
        if term == "always()":
            continue
        m = TERM.match(term)
        if not m:
            sys.exit(
                f"::error file={path}::step {step_name!r} has an if: term this "
                f"harness cannot parse ({term!r}). Extend evaluate_if()."
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

    # Neither workflow sets a step-level `shell:` or a `defaults:` block, so
    # wc_shell_harness's default (`bash -e <file>`, no pipefail) is exactly
    # what the runner does here. See that module for why the script goes over
    # as a file and why the bash and the decoding are both chosen explicitly.
    return run_step(BASH, script, workdir, env_extra, runner_temp)


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

# Agent-authored strings land inside a markdown TABLE cell, where a bare "|"
# opens a new column and a newline ends the table outright. The schema
# constrains none of this — it says "string" — so the render step, not the
# agent, has to be the thing that makes it safe. A pipe in an answer is not
# exotic: "OIDC | API keys" is how anyone would write an either/or option.
#
# The 28-option question exercises the ordinal fallback past "Z". The schema
# sets no maxItems, and the letter table has 26 entries, so options 27 and 28
# indexed past the end of it and rendered the literal string "null" as their
# label until the fallback was added.
ADVERSARIAL_QUESTIONS = [
    {"question": "Which auth combination should ship?",
     "context": "Table-hostile characters in every free-text field",
     "options": [
         {"answer": "OIDC | API keys",
          "implications": "Two code paths | twice the tests"},
         {"answer": "First line\nSecond line",
          "implications": "Trailing newline\n"},
         {"answer": "Pipes | and\nnewlines | together",
          "implications": "A | B\nC | D"},
     ]},
    {"question": "Pick one of many",
     "options": [{"answer": f"Option {i}", "implications": f"Cost {i}"}
                 for i in range(1, 29)]},
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
        expect_fires=set(), expect_run_red=False,
        expect_silent_green=True,   # the agent's own issue comment is the output
    ),
    dict(
        name="no discernible feature request WITH questions (defect a)",
        why="--json-schema forces a conforming result wherever the agent "
            "stopped, so a step-2 STOP can still return questions. No spec, no "
            "branch, no spec:/stage: label exists, so wing-commander-2-clarify "
            "can never fire on a reply. A questionnaire here is a dead end.",
        result={"specified": False, "clarifications": QUESTIONS},
        spec_dir="", expect_valid=True, expect_needed="false",
        expect_fires=set(), expect_summary="dead end", expect_run_red=False,
        expect_silent_green=True,   # suppression is deliberate and is reported
    ),
    dict(
        name="spec authored with open questions",
        why="The happy questionnaire path: render, then post it.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"}, expect_run_red=False,
    ),
    dict(
        name="spec authored, no open questions",
        why="The happy spec-PR path.",
        result={"specified": True, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="false",
        expect_fires={"resolve_pr", "announce_pr"}, expect_run_red=False,
    ),
    dict(
        name="no questions returned but the spec still has markers (defect b)",
        why="The agent left colon-form markers in the committed spec.md (which "
            "prompt step 3 tells it to do) but returned clarifications: []. "
            "Announcing 'Review the spec PR' here gets the markers merged. The "
            "cross-check must VETO the readiness claim AND fail the run — a "
            "veto that posts nothing and stays green is the worse outcome, "
            "because the requester sees only the run-started comment while the "
            "marker-carrying spec PR sits in the review queue.",
        result={"specified": True, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=True,
        expect_valid=True, expect_needed="false", expect_blocked="true",
        expect_fires=set(), expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
        expect_run_red=True,
    ),
    dict(
        name="questions returned but the spec has no markers (warn only)",
        why="The other direction of disagreement is harmless — the questions "
            "are real and answerable — so it warns, still posts, and the run "
            "must stay GREEN. A veto here would block a legitimate "
            "questionnaire on a warning.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", markers=False,
        expect_valid=True, expect_needed="true", expect_blocked="",
        expect_fires={"render", "announce_q"},
        expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
        expect_run_red=False,
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
        expect_run_red=False,
    ),
    dict(
        name="spec authored, no questions, no discoverable branch",
        why="Nothing to announce: there is no resolvable PR to point at.",
        result={"specified": True, "clarifications": []},
        spec_dir="", expect_valid=True, expect_needed="false",
        expect_fires=set(), expect_run_red=False,
        # Accepted gap, pinned here so it is a decision rather than an
        # oversight: intake authored a spec, nothing is wrong with it, but no
        # branch resolved, so there is no PR URL to point anyone at.
        expect_silent_green=True,
    ),
    dict(
        name="specified=false but a spec branch resolved (defect e)",
        why="The one combination that suppresses BOTH arms of the split: "
            "`specified` gates the announce steps, so a spec PR the agent "
            "really did open goes unannounced, and with a marker-free spec.md "
            "the cross-check agrees (structured=false, marker=false) and says "
            "nothing. Green run, spec PR in the queue, requester holding only "
            "the run-started comment. The guard stays — a stale branch from an "
            "earlier run on this issue must not be announced as this run's "
            "output — but the contradiction must be emitted where the watchdog "
            "can see it.",
        result={"specified": False, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=False,
        expect_valid=True, expect_needed="false", expect_blocked="",
        expect_fires=set(),
        expect_stdout=SENTINEL_PREFIX + "clarification-unclaimed-spec",
        expect_run_red=False,
        # Nothing is posted BY DESIGN (which run authored that branch is not
        # knowable here), so this opts out of the silent-green assertion — but
        # only because expect_stdout above pins that the run is loud in the
        # log. Silent to the issue is a decision; silent everywhere was a bug.
        expect_silent_green=True,
    ),
    dict(
        name="specified=false, spec branch resolved, markers present (defect e)",
        why="The dangerous half of the same contradiction. A step-2 STOP "
            "leaves no spec at all, so reaching this means a marker-carrying "
            "spec.md IS in the workspace while the agent claims no discernible "
            "feature request — never routine, unlike clarify's `none`. The "
            "veto fires and the run goes RED rather than finishing green over "
            "a spec nobody was told about.",
        result={"specified": False, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=True,
        expect_valid=True, expect_needed="false", expect_blocked="true",
        expect_fires=set(),
        expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
        expect_run_red=True,
    ),
    dict(
        name="questionnaire whose optional fields are empty strings (defect d)",
        why="The schema permits context/implications to be \"\", and jq's // "
            "does not treat \"\" as absent. The posted callout must not carry a "
            "bare '**Context**:' line or an empty Implications cell.",
        result={"specified": True, "clarifications": BLANK_FIELD_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"}, expect_run_red=False,
    ),
    dict(
        name="questionnaire carrying pipes, newlines and 28 options",
        why="Agent free text lands in markdown table cells. An unescaped '|' "
            "opens a column and a newline ends the table, so a perfectly "
            "reasonable answer like 'OIDC | API keys' would silently mangle "
            "the posted callout into unreadable columns. Past 26 options the "
            "letter table runs out and the label rendered the literal 'null'. "
            "The schema constrains none of this, so the render step must.",
        result={"specified": True, "clarifications": ADVERSARIAL_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"}, expect_run_red=False,
        # The ordinal fallback for options past "Z", asserted positively —
        # "no literal null" alone would also pass on an empty label.
        expect_body=["| 27 |", "| 28 |"],
    ),
    dict(
        name="spec.md unreadable while questions remain",
        why="SPEC_DIR is resolved from `git ls-remote` (the REMOTE) while the "
            "-f test reads the LOCAL workspace, so the two can disagree. The "
            "cross-check must not then cry wolf about its own unreadable file "
            "— and it must SAY it skipped, because a silent skip retires the "
            "veto in the one situation it exists for.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", markers="missing",
        expect_valid=True, expect_needed="true",
        expect_fires={"render", "announce_q"},
        forbid_stdout="clarification-mismatch",
        expect_summary="Cross-check skipped", expect_run_red=False,
    ),
    dict(
        name="spec.md unreadable with NO questions returned (the silent skip)",
        why="The dangerous half of the same disagreement: the veto CANNOT "
            "evaluate, and 'Review the spec PR' is announced over a spec.md "
            "this job never managed to read. That may still be right — the "
            "file is simply not in this workspace — but it must be visible in "
            "the log, or the safety net reads as having passed when it never "
            "ran. This is the intake-side gap that clarify already covered.",
        result={"specified": True, "clarifications": []},
        spec_dir="specs/042-a-feature", markers="missing",
        expect_valid=True, expect_needed="false", expect_blocked="",
        expect_fires={"resolve_pr", "announce_pr"},
        forbid_stdout="clarification-mismatch",
        expect_summary="Cross-check skipped", expect_run_red=False,
    ),
    dict(
        name="terminal result missing the specified discriminator",
        why="FR-002: a malformed structured result is a loud failure, never "
            "coerced into a decision. Without this, a dropped `specified` would "
            "silently read as the step-2 STOP path.",
        result={"clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=False,
        expect_needed=None, expect_fires=set(), expect_run_red=True,
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
        expect_needed=None, expect_fires=set(), expect_run_red=True,
    ),
    dict(
        name="terminal result is not JSON at all",
        why="Same contract, blunter input.",
        result=None, raw_result="I could not complete the task.",
        spec_dir="", expect_valid=False, expect_needed=None, expect_fires=set(),
        expect_run_red=True,
    ),
    dict(
        name="agent errored",
        why="is_error true never reaches the decision.",
        result={"specified": True, "clarifications": QUESTIONS},
        spec_dir="", is_error=True, subtype="error_during_execution",
        expect_valid=False, expect_needed=None, expect_fires=set(),
        expect_run_red=True,
    ),
]

CLARIFY_SCENARIOS = [
    dict(
        name="reply answered nothing (early STOP)",
        why="answered=false is clarify's `none`: the agent's own comment is the "
            "only issue-facing output, and no cross-check runs.",
        result={"answered": False, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="none", expect_fires=set(), expect_run_red=False,
        expect_silent_green=True,   # the agent's own issue comment is the output
    ),
    dict(
        name="reply resolved some questions, others remain",
        why="The happy questionnaire path.",
        result={"answered": True, "clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="needs-clarification", expect_fires={"render", "announce_q"},
        expect_run_red=False,
    ),
    dict(
        name="reply resolved everything",
        why="The happy spec-PR path.",
        result={"answered": True, "clarifications": []},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="ready", expect_fires={"resolve_pr", "announce_pr"},
        expect_run_red=False,
    ),
    dict(
        name="no questions returned but the spec still has markers (defect b)",
        why="Same veto as intake's: announcing readiness here merges the "
            "markers. And the same second half — blocking the callout without "
            "failing the run leaves a green run that posted nothing.",
        result={"answered": True, "clarifications": []},
        spec_dir="specs/042-a-feature", markers=True,
        expect_valid=True, expect_outcome="ready", expect_blocked="true",
        expect_fires=set(), expect_stdout=SENTINEL_PREFIX + "clarification-mismatch",
        expect_run_red=True,
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
        expect_summary="Cross-check skipped", expect_run_red=False,
    ),
    dict(
        name="questionnaire whose optional fields are empty strings (defect d)",
        why="Same render contract as intake's.",
        result={"answered": True, "clarifications": BLANK_FIELD_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="needs-clarification", expect_fires={"render", "announce_q"},
        expect_run_red=False,
    ),
    dict(
        name="questionnaire carrying pipes, newlines and 28 options",
        why="Same render contract as intake's — the two render blocks are "
            "asserted byte-identical, so this proves it for both.",
        result={"answered": True, "clarifications": ADVERSARIAL_QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=True,
        expect_outcome="needs-clarification", expect_fires={"render", "announce_q"},
        expect_run_red=False, expect_body=["| 27 |", "| 28 |"],
    ),
    dict(
        name="terminal result missing the answered discriminator",
        why="FR-002, clarify's half.",
        result={"clarifications": QUESTIONS},
        spec_dir="specs/042-a-feature", expect_valid=False,
        expect_outcome=None, expect_fires=set(), expect_run_red=True,
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
        # Baseline for every scenario here: a healthy agent run. These
        # scenarios exercise clarification-shape defects downstream of the
        # verdict, not the verdict computation itself (that is Gate 22's
        # job) — specs/037-agent-turn-budget-guard/ replaced both stages'
        # validation-gate condition with this output.
        "steps.agent-verdict.outputs.verdict": "healthy",
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

    # --- does the run actually go red? -----------------------------------
    # Asserted separately from the callouts because the two can disagree in
    # the direction that matters: a veto that blocks both callouts and then
    # forgets to fail leaves a GREEN run that posted nothing, which reads to
    # the requester as "still working" and to a reviewer as "this spec PR is
    # fine". `blocked=true` is only half the contract; this is the other.
    #
    # The steps are EXECUTED, not just condition-checked, so a `Fail on ...`
    # step that lost its `exit 1` (or grew a `continue-on-error`) is caught
    # too — that is the same shape as the #101 defect where continue-on-error
    # hid agent failures from the watchdog.
    run_red = job_failed
    red_by = ["the validation gate exited non-zero in place"] if job_failed else []
    if not job_failed:
        for name in stage.fail_steps:
            step = steps[name]
            if step.get("continue-on-error"):
                failures.append(
                    f"{tag} {name!r} carries continue-on-error, so its exit 1 "
                    f"cannot fail the run. That step is the ONLY thing turning "
                    f"the verdict into a red run.")
                continue
            if not evaluate_if(step.get("if"), ctx, name, stage.path):
                continue
            rc, out, _, _ = run_shell(step["run"], workdir,
                                      step_env(step, subs, stage.path),
                                      runner_temp, stage.path)
            if rc == 0:
                failures.append(
                    f"{tag} {name!r} fired but exited 0, so the run stays "
                    f"green. Its whole job is to turn the verdict above into "
                    f"a failed run.\n{out}")
            else:
                run_red = True
                red_by.append(name)

    want_red = sc.get("expect_run_red")
    if want_red is not None and run_red != want_red:
        failures.append(
            f"{tag} expected the run to go {'RED' if want_red else 'GREEN'}, "
            f"got {'RED' if run_red else 'GREEN'} "
            f"(triggered by: {red_by or '(nothing)'}). {sc['why']}")

    # A run that posts no callout at all and still goes green has silently
    # swallowed the whole stage — the requester sees only the run-started
    # comment. Legitimate for the paths where the agent posted its own issue
    # comment instead, so those scenarios opt out with expect_silent_green.
    if not fired and not run_red and not sc.get("expect_silent_green"):
        failures.append(
            f"{tag} the run posted NO callout and finished green. Nothing "
            f"reached the requester and nothing flagged the run. If that is "
            f"genuinely correct here (the agent posted its own comment), set "
            f"expect_silent_green=True on the scenario and say why.")

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

            # Table integrity. Every row of the options table — header,
            # separator and each option — is exactly three columns, so it
            # carries exactly four unescaped pipes. An agent-authored "|"
            # that reached the output unescaped adds a column and shifts
            # every cell after it; an unescaped newline ends the table
            # outright and leaves the remaining options as loose prose. Both
            # show up here as a row whose pipe count is not 4.
            for lineno, line in enumerate(body.splitlines(), 1):
                if not line.startswith("|"):
                    continue
                bare = line.replace("\\|", "").count("|")
                if bare != 4:
                    failures.append(
                        f"{tag} table row {lineno} has {bare} unescaped pipe(s), "
                        f"expected 4 — agent text broke out of its cell and the "
                        f"posted callout will render as mangled columns:\n"
                        f"    {line}\n\nfull body:\n{body}")
            for want in sc.get("expect_body", ()):
                if want not in body:
                    failures.append(f"{tag} rendered questionnaire is missing "
                                    f"{want!r}. {sc['why']}\nGot:\n{body}")

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
# Structural checks — two copies that must not drift
# --------------------------------------------------------------------------
SCHEMA_CONTRACT = ("specs/032-structured-clarification-gate/contracts/"
                   "clarification-schema.md")
# The output filename is the ONLY difference the two render blocks are
# allowed to have; everything else is one algorithm written down twice.
RENDER_OUTPUTS = ("intake-clarification.md", "clarify-followup.md")


def structural_checks(loaded):
    """Assert the things the scenarios cannot see, because they run one copy.

    Every scenario executes whichever render block belongs to its own stage,
    so a fix applied to one and forgotten on the other would leave the suite
    fully green while the two stages posted differently-shaped callouts. Same
    for the schema: the scenarios feed synthetic transcripts, so they never
    exercise the `--json-schema` string that decides what the agent may
    actually return. Both are pure text comparisons, and both are the kind of
    second copy that has already drifted in this repo once (gate 5).
    """
    failures = []

    # 1. The two render blocks are one algorithm.
    renders = {}
    for stage, steps, _ in loaded:
        text = str(steps[stage.render]["run"])
        for name in RENDER_OUTPUTS:
            text = text.replace(name, "<OUT>")
        renders[stage.name] = text
    if len(set(renders.values())) > 1:
        failures.append(
            "the intake and clarify 'Render clarification questionnaire' "
            "blocks have diverged. They are the same algorithm and must stay "
            "byte-identical apart from the output filename — otherwise a "
            "render fix lands on one stage, the suite stays green, and the "
            "two stages post differently-shaped questionnaires.")

    # 2. The inline --json-schema strings match the published contract.
    try:
        contract = open(SCHEMA_CONTRACT, encoding="utf-8").read()
    except OSError as exc:
        failures.append(f"cannot read {SCHEMA_CONTRACT} ({exc}); the schemas "
                        f"below have nothing to be checked against.")
        return failures
    published = re.findall(r"^\{\"type\":\"object\".*\}$", contract, re.M)
    for stage, _, _ in loaded:
        wf = open(stage.path, encoding="utf-8").read()
        inline = re.findall(r"--json-schema '(\{.*?\})'\s*$", wf, re.M)
        if len(inline) != 1:
            failures.append(
                f"{stage.path}: expected exactly one --json-schema argument, "
                f"found {len(inline)}. The agent's permitted result shape is "
                f"declared in exactly one place per stage.")
            continue
        if inline[0] not in published:
            failures.append(
                f"{stage.path}: its --json-schema string is not present in "
                f"{SCHEMA_CONTRACT}. The contract document is what reviewers "
                f"read to know what the agent may return; a workflow that has "
                f"quietly widened or narrowed its schema is a contract nobody "
                f"is holding it to.\n    workflow:  {inline[0]}")
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


def mut_fail_step_never_fires(loaded):
    """The veto blocks both callouts, then the run finishes GREEN.

    Flipping this one guard is the cheapest possible way to reach the worst
    possible outcome: nothing posted, nothing red, a marker-carrying spec PR
    in the review queue and a requester who sees only "run started".
    """
    for stage, steps, _ in loaded:
        for name in stage.fail_steps:
            cond = str(steps[name].get("if") or "")
            steps[name]["if"] = cond.replace("outputs.blocked == 'true'",
                                             "outputs.blocked != 'true'")


def mut_fail_step_exits_zero(loaded):
    """The `Fail on ...` step fires but no longer fails the run."""
    for stage, steps, _ in loaded:
        for name in stage.fail_steps:
            steps[name]["run"] = str(steps[name]["run"]).replace("exit 1",
                                                                 "exit 0")


def mut_silent_skip(loaded):
    """The cross-check skips an unreadable spec.md without saying so.

    The outcome is unchanged — that is the point. The only thing separating
    "the veto ran and cleared it" from "the veto never ran" is this line.
    """
    for stage, steps, _ in loaded:
        steps[stage.decide]["run"] = steps[stage.decide]["run"].replace(
            'echo "Cross-check skipped: no readable ${SPEC_DIR:-<unset>}'
            '/spec.md." >> "$GITHUB_STEP_SUMMARY"', ':')


def mut_drop_unclaimed_sentinel(loaded):
    """Defect (e): specified=false over a resolvable spec dir says nothing.

    The outcome is again unchanged — no callout either way. The only thing
    separating "intake decided not to announce someone else's branch" from
    "a spec PR this run opened is sitting unannounced" is this emission.
    """
    for stage, steps, _ in loaded:
        if stage.name != "intake":
            continue
        run = str(steps[stage.decide]["run"])
        steps[stage.decide]["run"] = run.replace(
            'if [ "$specified" != "true" ] && [ -n "$SPEC_DIR" ]; then',
            'if false; then')


def mut_no_cell_escape(loaded):
    """Agent text reaches the markdown table cell unescaped."""
    for stage, steps, _ in loaded:
        steps[stage.render]["run"] = steps[stage.render]["run"].replace(
            'def cell: tostring | gsub("\\\\|"; "\\\\|") | gsub("[\\r\\n]+"; "<br>");',
            'def cell: tostring;')


def mut_no_ordinal_fallback(loaded):
    """Options past "Z" index off the end of the letter table."""
    for stage, steps, _ in loaded:
        steps[stage.render]["run"] = steps[stage.render]["run"].replace(
            "$letters[.key] // ((.key + 1) | tostring)", "$letters[.key]")


MUTATIONS = [
    ("the questionnaire arm ignoring `specified` (dead-end callout)",
     mut_drop_specified),
    ("the cross-check logging a mismatch instead of vetoing readiness",
     mut_drop_veto),
    ("clarify grepping spec.md with no existence guard", mut_drop_existence_guard),
    ("jq's // treating an empty string as a present value", mut_blank_strings),
    ("a veto that posts nothing and still finishes the run green",
     mut_fail_step_never_fires),
    ("a `Fail on ...` step that fires but exits 0", mut_fail_step_exits_zero),
    ("skipping the marker cross-check without saying so", mut_silent_skip),
    ("suppressing both callouts on specified=false without saying so",
     mut_drop_unclaimed_sentinel),
    ("agent text reaching a markdown table cell unescaped", mut_no_cell_escape),
    ("options past Z rendering their label as null", mut_no_ordinal_fallback),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    loaded = [
        (INTAKE_STAGE, load_steps(INTAKE_STAGE), INTAKE_SCENARIOS),
        (CLARIFY_STAGE, load_steps(CLARIFY_STAGE), CLARIFY_SCENARIOS),
    ]

    tmproot = tempfile.mkdtemp()
    try:
        failures = suite(loaded, tmproot) + structural_checks(loaded)
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
