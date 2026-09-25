#!/usr/bin/env python3
"""Gate 95 -- board-loop.yml's reviewer fail-closed wiring actually works.

WHY THIS EXISTS
----------------
#499 code review, round 4 (BLOCKER): "Extract and validate the review
findings" only set `parse_failed = True` inside branches reached through
`if os.path.isfile(path):` -- a reviewer step that died before ever
writing claude-execution-output.json (crashed, was OOM-killed, hit a
runner failure) left `parse_failed` at its initial `False`, and
`in-scope-count` at `0`, which "Decide the round outcome" read as
`converged` -- a PR advanced to readiness having never actually been
reviewed. That fix (this same PR, same round) is only as good as
something that keeps checking it stayed fixed: a static/structural check
here would have stayed green through the fix being silently reverted
(`if [ "$PARSE_FAILED" != "false" ]` replaced with `if false`, or the new
`else: parse_failed = True` branch deleted) as long as the *shape* of the
code looked right. This gate instead EXECUTES the three real steps
("Extract and validate the review findings", "Decide the round outcome",
"Compose the review body" -- read out of board-loop.yml at run time, so
there is no second copy to drift) end to end, chained through the same
$RUNNER_TEMP and step-output relationships the real job uses, against
four scenarios a reviewer round can actually land in.

WHAT IT CHECKS
--------------
Four end-to-end scenarios, each run through all three steps in sequence
(extract's outputs feed round's env, both feed compose-review's env, and
extract's board-review-findings.json file is left in the same
$RUNNER_TEMP compose-review reads it from -- the exact wiring the real
job uses):

  1. missing transcript file: claude-execution-output.json never written
     at all. Must be parse-failed=true, outcome=stalled (not converged),
     and the posted body says "Inconclusive", never "No findings.".
  2. non-healthy agent verdict (a valid transcript, but
     steps.review-verdict.outputs.verdict != 'healthy'): same three
     assertions.
  3. every extracted finding malformed (dropped > 0, kept == 0 -- not the
     same as the agent genuinely returning `[]`): same three assertions.
  4. CONTROL -- a genuinely empty, well-formed findings array with a
     healthy verdict: parse-failed=false, outcome=converged, body says
     "No findings.". Proves the fail-closed wiring above does not also
     swallow the legitimate "reviewer found nothing" case.

Then THREE mutations, each reverting one of the three steps' shipped text
to the shape that let scenario 1 fail open, and asserting scenario 1's
own assertions now FAIL against the mutated step -- proving this gate
would actually catch each fix being silently reverted, not just that its
current shape happens to look right.

Usage: python3 .github/scripts/verify-reviewer-fail-closed.py
Requires: bash. See wc_shell_harness.py for running this on Windows.
"""
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = os.path.join(".github", "workflows", "board-loop.yml")
EXTRACT_STEP = "Extract and validate the review findings"
ROUND_STEP = "Decide the round outcome"
COMPOSE_STEP = "Compose the review body"
BASH = None

SHARED_SCRIPTS = ("wc_fence_extract.py", "verify-board-review-finding-schema.py",
                  "board_spec_request_body.py")
SHARED_SCHEMAS = ("board-review-finding.schema.json",)


def _fenced_transcript(findings_json_text):
    """A minimal claude-execution-output.json transcript whose terminal
    result carries the given raw findings JSON text inside the fenced
    block the extract step looks for."""
    text = (
        "Here is my review.\n\n"
        "```wing-commander-review-findings\n"
        + findings_json_text + "\n"
        "```\n"
    )
    # Encode as a Python literal safely via json, then hand-assemble the
    # minimal transcript JSON (avoids importing json just for this one
    # call site's escaping).
    import json
    return json.dumps([{"type": "result", "result": text}])


VALID_FINDING = (
    '[{"title": "t", "what": "w", '
    '"evidence": {"file_paths": ["x.py"]}, "in_scope": true, '
    '"fingerprint_basis": {"file_path": "x.py", "gate_or_artifact": "g"}}]'
)


def prepare_workdir(tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    scripts_dir = os.path.join(workdir, ".github", "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    for name in SHARED_SCRIPTS:
        shutil.copyfile(os.path.join(".github", "scripts", name),
                        os.path.join(scripts_dir, name))
    schemas_dir = os.path.join(workdir, ".github", "schemas")
    os.makedirs(schemas_dir, exist_ok=True)
    for name in SHARED_SCHEMAS:
        shutil.copyfile(os.path.join(".github", "schemas", name),
                        os.path.join(schemas_dir, name))
    return workdir, runner_temp


def run_pipeline(extract_script, round_script, compose_script, tmproot,
                 transcript=None, review_verdict="healthy"):
    """Run the three steps end to end, chained the way the real job
    chains them. Returns (extract_outputs, round_outputs, body_text)."""
    workdir, runner_temp = prepare_workdir(tmproot)
    try:
        if transcript is not None:
            with open(os.path.join(runner_temp, "claude-execution-output.json"),
                      "w", encoding="utf-8") as fh:
                fh.write(transcript)

        rc1, out1, outputs1, _ = run_step(
            BASH, extract_script, workdir,
            {"REVIEW_VERDICT": review_verdict}, runner_temp)
        if rc1 != 0:
            return outputs1, {}, None, f"extract step exited {rc1}: {out1}"

        rc2, out2, outputs2, _ = run_step(
            BASH, round_script, workdir,
            {"PARSE_FAILED": outputs1.get("parse-failed", ""),
             "IN_SCOPE_COUNT": outputs1.get("in-scope-count", "0"),
             "ROUND": "1", "ROUND_BUDGET": "5"},
            runner_temp)
        if rc2 != 0:
            return outputs1, outputs2, None, f"round step exited {rc2}: {out2}"

        rc3, out3, _outputs3, _ = run_step(
            BASH, compose_script, workdir,
            {"PARSE_FAILED": outputs1.get("parse-failed", "")},
            runner_temp)
        body = None
        body_path = os.path.join(runner_temp, "board-review-body.md")
        if os.path.isfile(body_path):
            with open(body_path, encoding="utf-8") as fh:
                body = fh.read()
        if rc3 != 0:
            return outputs1, outputs2, body, f"compose step exited {rc3}: {out3}"

        return outputs1, outputs2, body, None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(runner_temp, ignore_errors=True)


SCENARIOS = [
    ("missing transcript file",
     dict(transcript=None, review_verdict="healthy"),
     dict(parse_failed="true", outcome="stalled", body_has=("Inconclusive",),
          body_lacks=("No findings.",))),
    ("non-healthy agent verdict",
     dict(transcript=_fenced_transcript("[]"), review_verdict="rate_limited"),
     dict(parse_failed="true", outcome="stalled", body_has=("Inconclusive",),
          body_lacks=("No findings.",))),
    ("every extracted finding malformed",
     dict(transcript=_fenced_transcript('[{"not": "a valid finding"}]'),
          review_verdict="healthy"),
     dict(parse_failed="true", outcome="stalled", body_has=("Inconclusive",),
          body_lacks=("No findings.",))),
    ("control: genuinely zero findings, healthy verdict",
     dict(transcript=_fenced_transcript("[]"), review_verdict="healthy"),
     dict(parse_failed="false", outcome="converged", body_has=("No findings.",),
          body_lacks=("Inconclusive",))),
]


def check_scenarios(extract_script, round_script, compose_script, tmproot, label_prefix=""):
    failures = []
    for name, kwargs, want in SCENARIOS:
        outputs1, outputs2, body, err = run_pipeline(
            extract_script, round_script, compose_script, tmproot, **kwargs)
        prefix = f"{label_prefix}{name}"
        if err:
            failures.append(f"{prefix}: {err}")
            continue
        if outputs1.get("parse-failed") != want["parse_failed"]:
            failures.append(
                f"{prefix}: extract's parse-failed={outputs1.get('parse-failed')!r}, "
                f"expected {want['parse_failed']!r}")
        if outputs2.get("outcome") != want["outcome"]:
            failures.append(
                f"{prefix}: round outcome={outputs2.get('outcome')!r}, "
                f"expected {want['outcome']!r}")
        for want_text in want["body_has"]:
            if not body or want_text not in body:
                failures.append(
                    f"{prefix}: review body does not contain {want_text!r}: {body!r}")
        for unwanted_text in want["body_lacks"]:
            if body and unwanted_text in body:
                failures.append(
                    f"{prefix}: review body unexpectedly contains {unwanted_text!r}: {body!r}")
    return failures


# The round step alone, isolated from the full pipeline: an EMPTY
# PARSE_FAILED (the extract step's output step never ran at all, or the
# output was dropped by the runner) must stall too, per the round-4
# review's explicit `!= "false"` requirement. This is deliberately
# separate from SCENARIOS above -- every one of those produces a literal
# "true"/"false" parse-failed value from a real extract run, none of them
# exercises the empty-string case the `!= "false"` (vs `= "true"`) test
# was specifically written to close.
ROUND_ALONE_SCENARIOS = [
    ("empty PARSE_FAILED (extract's output step never ran)",
     dict(PARSE_FAILED="", IN_SCOPE_COUNT="0", ROUND="1", ROUND_BUDGET="5"),
     "stalled"),
    ("PARSE_FAILED=true overrides a nonzero in-scope-count too",
     dict(PARSE_FAILED="true", IN_SCOPE_COUNT="5", ROUND="1", ROUND_BUDGET="5"),
     "stalled"),
    ("control: PARSE_FAILED=false, zero in-scope -> converged",
     dict(PARSE_FAILED="false", IN_SCOPE_COUNT="0", ROUND="1", ROUND_BUDGET="5"),
     "converged"),
]


def check_round_alone(round_script, tmproot):
    failures = []
    for name, env, want_outcome in ROUND_ALONE_SCENARIOS:
        workdir = tempfile.mkdtemp(dir=tmproot)
        runner_temp = tempfile.mkdtemp(dir=tmproot)
        try:
            rc, out, outputs, _ = run_step(BASH, round_script, workdir, env, runner_temp)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            shutil.rmtree(runner_temp, ignore_errors=True)
        if rc != 0:
            failures.append(f"round-alone {name}: step exited {rc}: {out}")
            continue
        if outputs.get("outcome") != want_outcome:
            failures.append(
                f"round-alone {name}: outcome={outputs.get('outcome')!r}, "
                f"expected {want_outcome!r}")
    return failures


# --- Mutations: each reverts one of the three steps to the shape that let
# scenario 1 (missing transcript file) fail open, and is asserted to make
# scenario 1's own assertions fail. -----------------------------------

EXTRACT_MISSING_ELSE_RE = re.compile(
    r"else:\n"
    r"(?:[ \t]*#[^\n]*\n)*"
    r'[ \t]*print\("::warning::board-loop reviewer: '
    r'claude-execution-output\.json does not exist[^\n]*"\)\n'
    r"[ \t]*parse_failed = True\n")


def mut_extract_missing_file(script):
    new_script, n = EXTRACT_MISSING_ELSE_RE.subn("else:\n    pass\n", script, count=1)
    if n != 1:
        sys.exit(f"::error::verify-reviewer-fail-closed: expected exactly one "
                 f"match for the extract step's missing-file branch in "
                 f"{WORKFLOW}, found {n} -- the step text may have changed "
                 f"shape; update this harness alongside it.")
    return new_script


ROUND_GOOD_TEST = 'if [ "$PARSE_FAILED" != "false" ]; then'
ROUND_BROKEN_TEST = 'if [ "$PARSE_FAILED" = "true" ]; then'


def mut_round_ordering(script):
    if script.count(ROUND_GOOD_TEST) != 1:
        sys.exit(f"::error::verify-reviewer-fail-closed: expected exactly one "
                 f"occurrence of {ROUND_GOOD_TEST!r} in {WORKFLOW}, found "
                 f"{script.count(ROUND_GOOD_TEST)} -- the step text may have "
                 f"changed shape; update this harness alongside it.")
    return script.replace(ROUND_GOOD_TEST, ROUND_BROKEN_TEST, 1)


COMPOSE_GOOD_RE = re.compile(
    r'parse_failed = os\.environ\.get\("PARSE_FAILED", ""\) != "false"\n')


def mut_compose_ignores_parse_failed(script):
    new_script, n = COMPOSE_GOOD_RE.subn("parse_failed = False\n", script, count=1)
    if n != 1:
        sys.exit(f"::error::verify-reviewer-fail-closed: expected exactly one "
                 f"match for the compose step's parse_failed read in "
                 f"{WORKFLOW}, found {n} -- the step text may have changed "
                 f"shape; update this harness alongside it.")
    return new_script


MUTATIONS = [
    ("extract's missing-file branch stops setting parse_failed (the #499 "
     "round-4 blocker itself, put back)",
     "extract", mut_extract_missing_file),
    ("round outcome reverts to testing = \"true\" instead of != \"false\" "
     "(an empty/missing output falls through to in-scope-count again)",
     "round", mut_round_ordering),
    ("compose-review stops reading parse_failed at all (posts \"No "
     "findings.\" even on a parse failure)",
     "compose", mut_compose_ignores_parse_failed),
]

MISSING_FILE_SCENARIO = SCENARIOS[0]


def check_mutations(extract_script, round_script, compose_script, tmproot):
    failures = []
    for label, target, mutate in MUTATIONS:
        scripts = {"extract": extract_script, "round": round_script,
                   "compose": compose_script}
        scripts[target] = mutate(scripts[target])

        if target == "round":
            # The round-ordering mutation (`= "true"` instead of
            # `!= "false"`) is invisible to scenario 1's full pipeline --
            # extract always emits a literal "true"/"false", never an
            # empty string, so both forms agree on every SCENARIOS case.
            # It is only visible against an EMPTY PARSE_FAILED, which is
            # exactly what ROUND_ALONE_SCENARIOS' first case exercises.
            workdir = tempfile.mkdtemp(dir=tmproot)
            runner_temp = tempfile.mkdtemp(dir=tmproot)
            try:
                rc, out, outputs, _ = run_step(
                    BASH, scripts["round"], workdir,
                    dict(PARSE_FAILED="", IN_SCOPE_COUNT="0", ROUND="1",
                        ROUND_BUDGET="5"),
                    runner_temp)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
                shutil.rmtree(runner_temp, ignore_errors=True)
            if rc != 0:
                failures.append(
                    f"mutation {label!r}: the mutated round step errored "
                    f"instead of demonstrating the regression: {out}")
                continue
            if outputs.get("outcome") == "stalled":
                failures.append(
                    f"mutation {label!r} did NOT change the empty-"
                    f"PARSE_FAILED outcome -- this gate would not catch "
                    f"this regression (outcome={outputs.get('outcome')!r}).")
            else:
                print(f"note: mutation {label!r} confirmed caught "
                      f"(empty-PARSE_FAILED outcome={outputs.get('outcome')!r}, "
                      f"expected != 'stalled').")
            continue

        name, kwargs, want = MISSING_FILE_SCENARIO
        outputs1, outputs2, body, err = run_pipeline(
            scripts["extract"], scripts["round"], scripts["compose"],
            tmproot, **kwargs)
        if err:
            failures.append(
                f"mutation {label!r}: the mutated pipeline errored instead "
                f"of demonstrating the regression: {err}")
            continue
        # The mutation must make AT LEAST ONE of the real assertions fail
        # -- proving this gate's scenario 1 would have caught it.
        broke_something = (
            outputs1.get("parse-failed") != want["parse_failed"]
            or outputs2.get("outcome") != want["outcome"]
            or not body or "Inconclusive" not in body
            or (body and "No findings." in body))
        if not broke_something:
            failures.append(
                f"mutation {label!r} did NOT change scenario 1's outcome -- "
                f"this gate would not catch this regression "
                f"(parse-failed={outputs1.get('parse-failed')!r}, "
                f"outcome={outputs2.get('outcome')!r}, body={body!r}).")
        else:
            print(f"note: mutation {label!r} confirmed caught "
                  f"(parse-failed={outputs1.get('parse-failed')!r}, "
                  f"outcome={outputs2.get('outcome')!r}).")
    return failures


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")

    extract_step = find_step(WORKFLOW, EXTRACT_STEP)
    round_step = find_step(WORKFLOW, ROUND_STEP)
    compose_step = find_step(WORKFLOW, COMPOSE_STEP)
    for step_name, step in ((EXTRACT_STEP, extract_step),
                            (ROUND_STEP, round_step),
                            (COMPOSE_STEP, compose_step)):
        if step is None:
            sys.exit(f"::error file={WORKFLOW}::step {step_name!r} not found.")
        if "${{" in str(step["run"]):
            sys.exit(f"::error file={WORKFLOW}::step {step_name!r}'s run: "
                     f"block contains a ${{{{ }}}} expression this harness "
                     f"does not resolve.")

    extract_script = str(extract_step["run"])
    round_script = str(round_step["run"])
    compose_script = str(compose_step["run"])

    tmproot = tempfile.mkdtemp()
    try:
        failures = check_scenarios(extract_script, round_script, compose_script, tmproot)
        failures += check_round_alone(round_script, tmproot)
        failures += check_mutations(extract_script, round_script, compose_script, tmproot)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    for f in failures:
        print(f"::error::Gate 95: {f}")
    if failures:
        print(f"Gate 95: {len(failures)} failure(s).")
        return 1
    print(f"Gate 95: {len(SCENARIOS)} pipeline scenario(s), "
          f"{len(ROUND_ALONE_SCENARIOS)} round-alone scenario(s), and "
          f"{len(MUTATIONS)} mutation(s) confirmed the reviewer's "
          f"fail-closed wiring (extract -> round outcome -> review body) "
          f"is real and would catch each of its three failure modes "
          f"reverting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
