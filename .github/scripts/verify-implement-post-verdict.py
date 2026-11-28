#!/usr/bin/env python3
"""Gate 185 -- the implement stage's post-agent verdict keeps its shape
(specs/133-post-agent-gate-verdict FR-005..FR-007, FR-010, FR-014).

WHAT IT CHECKS (implement.yml, parsed)
  1. the "Dispatch next step" step exists exactly once, inside
     `implement-dispatch`;
  2. `gate-suite-implement-post` runs only when the cycle is converging or
     handing off (its `if:` names `tasks-converged` and `handoff`), and its
     suite budget (`suite-timeout-minutes`) sits below the step's
     `timeout-minutes` (FR-007);
  3. the workflow_call `converged` output is sourced from
     `jobs.implement-dispatch.outputs.converged` (FR-006);
  4. finalize.yml's `workflow_call` inputs (its dispatch signature) are untouched: no
     post-agent input appears there (SC-007);
  5. the non-convergence reason names the post-agent full suite, the
     stall-hand-off note carries its marker, the two reasons are distinct,
     and the first failure is rendered inside a fence (FR-010, FR-014).

Usage: python3 .github/scripts/verify-implement-post-verdict.py [--self-test]
"""
import copy
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = os.path.join(HERE, "..", "workflows")
DISPATCH_STEP = "Dispatch next step"
POST_JOB = "gate-suite-implement-post"
READER_JOB = "implement-dispatch"
DECIDE_ID = "decide"
NON_CONVERGED = "Not converged — the post-agent full suite did not pass."
HANDOFF_MARKER = "<!-- wing-commander:post-agent-verdict -->"
UNCHECKED_REASON_RE = re.compile(r"unchecked", re.I)


def _steps(job):
    steps = (job or {}).get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def check(impl, finalize_doc, claude_text=""):
    """`impl`/`finalize_doc`: parsed workflow documents. Returns problems."""
    problems = []
    jobs = (impl or {}).get("jobs") or {}
    post = jobs.get(POST_JOB)
    reader = jobs.get(READER_JOB)
    if post is None or reader is None:
        return ["implement.yml has no job {0!r}".format(
            POST_JOB if post is None else READER_JOB)]

    # 1. the dispatch step lives once, in the reader.
    homes = [(jid, s) for jid, job in jobs.items() for s in _steps(job)
             if s.get("name") == DISPATCH_STEP]
    if [h[0] for h in homes] != [READER_JOB]:
        problems.append("the {0!r} step must exist exactly once, in {1!r}; found in {2}".format(
            DISPATCH_STEP, READER_JOB, [h[0] for h in homes] or "no job"))

    # 2. the post job's condition and budget.
    cond = str(post.get("if") or "")
    for needle in ("tasks-converged", "handoff"):
        if needle not in cond:
            problems.append("{0}: `if:` does not name {1} (it must run for a converging "
                            "cycle and a stall hand-off only)".format(POST_JOB, needle))
    for st in _steps(post):
        if "contained-gate-suite" in str(st.get("uses", "")):
            step_min = st.get("timeout-minutes")
            suite_min = (st.get("with") or {}).get("suite-timeout-minutes")
            try:
                if not int(str(suite_min)) < int(str(step_min)):
                    problems.append("{0}: suite-timeout-minutes {1} is not below the step's "
                                    "timeout-minutes {2} (FR-007)".format(POST_JOB, suite_min,
                                                                         step_min))
            except (TypeError, ValueError):
                problems.append("{0}: the suite step needs numeric timeout-minutes and "
                                "suite-timeout-minutes (FR-007)".format(POST_JOB))

    # 3. converged output sourced from the reader.
    on = (impl or {}).get(True) or (impl or {}).get("on") or {}
    out = (((on.get("workflow_call") or {}).get("outputs") or {}).get("converged") or {})
    if "jobs.{0}.outputs.converged".format(READER_JOB) not in str(out.get("value", "")):
        problems.append("the workflow_call `converged` output is not sourced from "
                        "jobs.{0}.outputs.converged (FR-006)".format(READER_JOB))

    # 4. finalize's dispatch signature.
    fon = (finalize_doc or {}).get(True) or (finalize_doc or {}).get("on") or {}
    inputs = ((fon.get("workflow_call") or {}).get("inputs") or {})
    for name in inputs:
        if "verdict" in name or "post-agent" in name or "post_agent" in name:
            problems.append("finalize.yml grew a post-agent dispatch input {0!r} (SC-007)"
                            .format(name))

    # 5. reason strings.
    decide = next((s for s in _steps(reader) if s.get("id") == DECIDE_ID), None)
    script = str((decide or {}).get("run", ""))
    if decide is None:
        problems.append("{0}: no step with id {1!r}".format(READER_JOB, DECIDE_ID))
    else:
        if NON_CONVERGED not in script:
            problems.append("the non-convergence reason no longer says {0!r} (FR-010)"
                            .format(NON_CONVERGED))
        if UNCHECKED_REASON_RE.search(NON_CONVERGED):
            problems.append("the post-agent reason is not distinct from the unchecked-tasks "
                            "reason (FR-010)")
        if HANDOFF_MARKER not in script:
            problems.append("the stall hand-off note lost its marker {0!r} (FR-014)"
                            .format(HANDOFF_MARKER))
        fences = re.findall(r"printf '\\n%smarkdown\\n%s\\n%s\\n' \"\$fence\" \"\$ff\" \"\$fence\"",
                            script)
        if len(fences) < 2:
            problems.append("the first failure is not rendered inside a fence in both the "
                            "non-convergence and hand-off notes (FR-010, FR-014)")
    problems += check_guidance(impl, claude_text)
    return problems


# FR-008/FR-009: the implement prompt and CLAUDE.md say the same thing -- the
# agent runs gates for its changed files by name; the full suite runs after
# the agent step and decides convergence. Neither may ask the agent for a
# full-suite run.
GUIDANCE_PHRASES = ("only the gates for the files",
                    "by name",
                    "run-local-gates.py <name>",
                    "decides convergence")
OLD_GUIDANCE_RE = re.compile(r"not a\s+substitute\s+for\s+the\s+gate-suite|still\s+asks\s+you\s+to\s+make")


def check_guidance(impl, claude_text):
    problems = []
    texts = {"CLAUDE.md": " ".join((claude_text or "").split())}
    for jid, job in ((impl or {}).get("jobs") or {}).items():
        for st in _steps(job):
            if str(st.get("id", "")).startswith("gate-suite-summary-"):
                texts["implement.yml " + str(st["id"])] = " ".join(
                    str(st.get("run", "")).replace("\\`", "`").split())
    if len(texts) < 3:
        problems.append("guidance: expected CLAUDE.md and both gate-suite summary steps, "
                        "found {0}".format(sorted(texts)))
    for where, text in texts.items():
        for phrase in GUIDANCE_PHRASES:
            if phrase not in text:
                problems.append("guidance: {0} does not say {1!r} (FR-008)".format(where, phrase))
        if OLD_GUIDANCE_RE.search(text):
            problems.append("guidance: {0} still asks the agent for a full-suite run "
                            "(FR-008)".format(where))
    return problems


def load(directory):
    docs = []
    for name in ("implement.yml", "finalize.yml"):
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            docs.append(yaml.safe_load(fh))
    return docs


def load_claude():
    with open(os.path.join(HERE, "..", "..", "CLAUDE.md"), encoding="utf-8") as fh:
        return fh.read()


def run():
    impl, fin = load(WORKFLOWS)
    problems = check(impl, fin, load_claude())
    for p in problems:
        print("::error::Gate 185: " + p)
    if problems:
        return 1
    print("Gate 185: the post-agent verdict job graph, budget, output and reasons hold.")
    return 0


def _mutations():
    def second_dispatch(impl, fin):
        impl["jobs"]["implement"]["steps"].append({"name": DISPATCH_STEP, "run": "true"})

    def no_dispatch(impl, fin):
        reader = impl["jobs"][READER_JOB]
        reader["steps"] = [s for s in reader["steps"] if s.get("name") != DISPATCH_STEP]

    def cond_loses_handoff(impl, fin):
        post = impl["jobs"][POST_JOB]
        post["if"] = str(post["if"]).replace("handoff", "other")

    def budget_equal(impl, fin):
        for st in impl["jobs"][POST_JOB]["steps"]:
            if "contained-gate-suite" in str(st.get("uses", "")):
                st["with"]["suite-timeout-minutes"] = str(st["timeout-minutes"])

    def output_from_implement(impl, fin):
        on = impl.get(True) or impl.get("on")
        on["workflow_call"]["outputs"]["converged"]["value"] = \
            "${{ jobs.implement.outputs.converged }}"

    def finalize_input(impl, fin):
        on = fin.get(True) or fin.get("on")
        on["workflow_call"]["inputs"]["post-agent-verdict"] = {"required": False}

    def reason_reworded(impl, fin):
        for st in impl["jobs"][READER_JOB]["steps"]:
            if st.get("id") == DECIDE_ID:
                st["run"] = st["run"].replace(NON_CONVERGED, "Not converged.")

    def marker_dropped(impl, fin):
        for st in impl["jobs"][READER_JOB]["steps"]:
            if st.get("id") == DECIDE_ID:
                st["run"] = st["run"].replace(HANDOFF_MARKER, "")

    def fence_dropped(impl, fin):
        for st in impl["jobs"][READER_JOB]["steps"]:
            if st.get("id") == DECIDE_ID:
                st["run"] = st["run"].replace('printf \'\\n%smarkdown\\n%s\\n%s\\n\' "$fence" "$ff" "$fence"',
                                              'echo "$ff"')

    return (
        ("a second dispatch step in the implement job", second_dispatch, "exactly once"),
        ("the dispatch step removed", no_dispatch, "exactly once"),
        ("the post job's if: loses handoff", cond_loses_handoff, "does not name handoff"),
        ("suite budget equal to the step timeout", budget_equal, "not below"),
        ("converged output sourced from the implement job", output_from_implement,
         "not sourced from"),
        ("finalize grows a post-agent input", finalize_input, "post-agent dispatch input"),
        ("the non-convergence reason reworded", reason_reworded, "no longer says"),
        ("the hand-off marker dropped", marker_dropped, "lost its marker"),
        ("the first failure unfenced", fence_dropped, "not rendered inside a fence"),
    )


def self_test():
    failures = []
    impl, fin = load(WORKFLOWS)
    claude = load_claude()
    shipped = check(impl, fin, claude)
    if shipped:
        failures += ["the shipped workflows already fail: " + p for p in shipped]
    # Guidance texts (FR-008): each drift is caught on its own.
    drift = (
        ("CLAUDE.md asks for the full suite again", impl,
         claude + "\nThat is not a substitute for the gate-suite run.", "still asks"),
        ("CLAUDE.md loses the by-name rule", impl,
         claude.replace("by name", "by hand"), "by name"),
        ("CLAUDE.md loses the convergence sentence", impl,
         claude.replace("decides convergence", "runs"), "decides convergence"),
    )
    for label, doc, text, expect in drift:
        if not any(expect in p for p in check_guidance(doc, text)):
            failures.append("guidance drift {0!r} not caught for {1!r}".format(label, expect))
    prompt = copy.deepcopy(impl)
    for st in prompt["jobs"]["implement"]["steps"]:
        if st.get("id") == "gate-suite-summary-cycle":
            st["run"] = st["run"].replace("decides convergence", "is informational")
    if not any("decides convergence" in p for p in check_guidance(prompt, claude)):
        failures.append("an implement prompt that stops saying the suite decides convergence "
                        "was not caught")
    for label, mutate, expect in _mutations():
        i2, f2 = copy.deepcopy(impl), copy.deepcopy(fin)
        mutate(i2, f2)
        got = check(i2, f2)
        if not any(expect in p for p in got):
            failures.append("mutation {0!r} not caught for {1!r}: {2}".format(label, expect, got))
    if UNCHECKED_REASON_RE.search(NON_CONVERGED):
        failures.append("the post-agent reason matches the unchecked-tasks reason")
    for f in failures:
        print("::error::Gate 185 self-test: " + f)
    if failures:
        return 1
    print("Gate 185 self-test: {0} mutation(s), each caught for its own reason."
          .format(len(_mutations())))
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else run())
