#!/usr/bin/env python3
"""Gate — the FR-003 findings paragraph and the filing step travel together.

WHY THIS EXISTS
---------------
specs/056-stage-found-defect-filing wires two independent things into each
of the six published stage workflows: the FR-003 paragraph telling the
agent how to propose a finding, and the `wing-commander-stage-findings`
step that turns a proposal into a filed issue. Nothing else keeps them in
lockstep — an edit that drops one while leaving the other (a prompt
rewrite that trims the paragraph, or a workflow refactor that drops the
step) would silently degrade the mechanism: the agent proposing findings
into a void nothing reads, or the composite running with nothing ever
proposing anything. FR-031 requires both catchable at PR time, on all six
stages regardless of that stage's own `findings-filing-enabled` default
(FR-001a) — the mechanism's *presence* is not conditional on the default.

WHAT IT CHECKS
--------------
For each of the six stage workflows named below: the workflow file exists
and parses; the FR-003 paragraph's stable substring ("do not attempt to
file it yourself") appears somewhere in the file; the
`wing-commander-stage-findings` composite is `uses:`'d by some step in the
file. Exactly one of the two present without the other fails loudly,
naming the stage and which side is missing. A workflow that cannot be
found or parsed also fails loudly (Principle VIII: "loud rather than
vacuous").

The paragraph check scans every step's own `with.prompt` field (not a
per-step "prompt-composition" parse, and not a whole-file substring scan
either — maintainer review, Nit #8: a whole-file scan is satisfied by the
phrase sitting in an unrelated COMMENT even after the real paragraph is
removed from every prompt, which would let this gate go quietly blind to
the exact regression it exists to catch). `stage-wiring.md` already
documents that plan.yml/tasks.yml/implement.yml each carry the paragraph
in TWO agent steps (auto/pr, or cycle/retry), and intake.yml/clarify.yml/
finalize.yml carry it in one — checking "does ANY step's prompt carry it"
rather than a fixed per-stage step count stays correct across that spread
without six different step-count expectations, while still requiring the
phrase to live where only an actual agent prompt can put it.

Also checks (maintainer review, post-merge fix): for the three stages
whose filing step's `if:` needed a stage-health signal beyond a bare
non-skipped read-back (FR-024 — intake, implement, finalize; see
contracts/wing-commander-stage-findings.md's per-stage table), the
shipped `if:` condition still names that signal. A regression back to
the old, weaker `steps.<read-back>.outcome != 'skipped'` form would let a
failed/exhausted agent run reach the filing step again — silently, since
the paragraph/step co-occurrence check above cannot see it.

Also checks (maintainer review, Item 6, post-merge fix): each of the six
`wing-commander-<N>-<stage>.yml` wrapper workflows' `findings-filing-enabled:`
value is wrapped in `fromJSON(vars.<VAR> || '<default>')`, exactly matching
the parity pattern the adjacent `findings-cap` input already uses one line
below. A repository variable literally set to the string `false` is a
truthy operand to GitHub Actions' `||`, so a bare `vars.X || true/false`
form (without `fromJSON`) hands a `type: boolean` `workflow_call` input the
string `"false"` instead of the boolean `false` — it cannot disable a
default-on stage (FR-029). A regression back to the bare form would strand
that repository variable silently, since the composite still runs (just
with the wrong effective default) rather than erroring.

Also checks (#420, found by the spec 056 quickstart §3 drill): every agent
prompt that carries the paragraph also names every REQUIRED key of
.github/schemas/stage-finding.schema.json, quoted exactly as the schema
spells it, and the two structured-array stages (intake, clarify) declare
the same required keys, with additionalProperties closed, under
`findings.items` in their inline `--json-schema`. The first live run
with filing enabled proved why: the paragraph as first shipped described
the object in prose ("title, what is wrong, evidence file paths, and the
fingerprint basis fields"), the agent wrote a YAML block with invented
keys, and the composite dropped a real finding as "not valid JSON" —
while every harness fixture, written in the right shape, kept passing.
The schema file is the single home for the shape; this gate reads it
rather than carrying a second copy of the key list.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

STAGE_WORKFLOWS = (
    ".github/workflows/intake.yml",
    ".github/workflows/clarify.yml",
    ".github/workflows/plan.yml",
    ".github/workflows/tasks.yml",
    ".github/workflows/implement.yml",
    ".github/workflows/finalize.yml",
)

PARAGRAPH_SUBSTRING = "do not attempt to file it yourself"
FILING_STEP_NEEDLE = "wing-commander-stage-findings"

# #420: the finding's shape has exactly one home. The prompt check and the
# structured-schema check below both derive their expectations from it.
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "schemas", "stage-finding.schema.json")
# The two stages whose agent returns a schema-validated result (channel
# mode structured-array) — their `--json-schema` must carry the shape.
STRUCTURED_STAGES = (
    ".github/workflows/intake.yml",
    ".github/workflows/clarify.yml",
)
# Same extraction verify-clarification-gating.py uses: the one inline
# `--json-schema '{...}'` argument, alone on its line.
JSON_SCHEMA_ARG = re.compile(r"--json-schema '(\{.*?\})'\s*$", re.M)

# Maintainer review, post-merge fix: the stage-health signal each of these
# three stages' filing step's `if:` must name (FR-024) — see
# contracts/wing-commander-stage-findings.md's per-stage table. The other
# three stages (clarify/plan/tasks) keep the original bare non-skipped
# read-back check and are deliberately absent from this map.
HEALTH_SIGNALS = {
    ".github/workflows/intake.yml": "steps.agent-result.outputs.valid == 'true'",
    ".github/workflows/implement.yml": "steps.final.outputs.ok == 'true'",
    ".github/workflows/finalize.yml": "steps.summarize-verdict.outputs.verdict == 'healthy'",
}

failures = []


def fail(msg):
    failures.append(msg)
    print(f"::error::verify-stage-findings-wiring: {msg}")


def note(msg):
    print(f"note: {msg}")


def _step_lists(doc):
    if not isinstance(doc, dict):
        return []
    out = []
    for job_id, job in (doc.get("jobs") or {}).items():
        out.append((job_id, (job or {}).get("steps") or []))
    return out


def has_filing_step(doc):
    for _job_id, steps in _step_lists(doc):
        for step in steps:
            uses = str((step or {}).get("uses") or "")
            if FILING_STEP_NEEDLE in uses:
                return True
    return False


def has_paragraph_in_prompt(doc):
    for _job_id, steps in _step_lists(doc):
        for step in steps:
            prompt = str(((step or {}).get("with") or {}).get("prompt") or "")
            if PARAGRAPH_SUBSTRING in prompt:
                return True
    return False


def filing_step_if_condition(doc):
    """The `if:` string of the step that `uses:` the filing composite, or
    None if no such step exists in this document."""
    for _job_id, steps in _step_lists(doc):
        for step in steps:
            uses = str((step or {}).get("uses") or "")
            if FILING_STEP_NEEDLE in uses:
                return str((step or {}).get("if") or "")
    return None


def _required_tree(schema):
    """{key: subtree-or-None} for every REQUIRED key of an object schema,
    recursively — the part of the shape an agent cannot leave out."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return None
    props = schema.get("properties") or {}
    return {key: _required_tree(props.get(key)) for key in (schema.get("required") or [])}


def _tree_keys(tree, out=None):
    out = [] if out is None else out
    for key, sub in (tree or {}).items():
        out.append(key)
        if sub:
            _tree_keys(sub, out)
    return out


def _open_objects(schema, at="findings.items", out=None):
    """Dotted paths of every object in `schema` whose additionalProperties
    is not literally false."""
    out = [] if out is None else out
    if isinstance(schema, dict) and schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            out.append(at)
        for key, sub in (schema.get("properties") or {}).items():
            _open_objects(sub, f"{at}.{key}", out)
    return out


_finding_schema_cache = {}


def finding_schema():
    if "doc" not in _finding_schema_cache:
        with open(SCHEMA_FILE, encoding="utf-8") as fh:
            _finding_schema_cache["doc"] = json.load(fh)
    return _finding_schema_cache["doc"]


def prompts_with_paragraph(doc):
    out = []
    for _job_id, steps in _step_lists(doc):
        for step in steps:
            prompt = str(((step or {}).get("with") or {}).get("prompt") or "")
            if PARAGRAPH_SUBSTRING in prompt:
                out.append(prompt)
    return out


def check_prompt_names_keys(path, doc):
    """#420: a prompt that asks for a finding must show the agent the keys."""
    required = _tree_keys(_required_tree(finding_schema()))
    for prompt in prompts_with_paragraph(doc):
        missing = [k for k in required if f'"{k}"' not in prompt]
        if missing:
            fail(f"{path}: an agent prompt carries the FR-003 findings paragraph "
                f"but does not name the finding's required key(s) {missing} "
                f"(quoted, exactly as .github/schemas/stage-finding.schema.json "
                f"spells them) — an agent left to guess the shape writes one the "
                f"composite drops as malformed, and the finding is lost (#420).")
            return
    note(f"{path}: every prompt carrying the paragraph names the finding's required keys.")


def check_structured_schema(path, text):
    """#420: the structured-array stages' result schema carries the shape."""
    found = JSON_SCHEMA_ARG.findall(text)
    if len(found) != 1:
        fail(f"{path}: expected exactly one inline --json-schema argument to "
            f"check the findings item shape in, found {len(found)}.")
        return
    try:
        parsed = json.loads(found[0])
    except ValueError as exc:
        fail(f"{path}: its inline --json-schema is not valid JSON ({exc}).")
        return
    items = ((parsed.get("properties") or {}).get("findings") or {}).get("items")
    if not isinstance(items, dict):
        fail(f"{path}: its --json-schema declares no findings.items object, so "
            f"the action enforces nothing about a finding's shape (#420).")
        return
    want = _required_tree(finding_schema())
    have = _required_tree(items)
    if have != want:
        fail(f"{path}: the findings.items shape in its --json-schema requires "
            f"{have} but .github/schemas/stage-finding.schema.json requires "
            f"{want} — a finding the action accepts would be dropped as "
            f"malformed afterwards (#420).")
        return
    open_objects = _open_objects(items)
    if open_objects:
        fail(f"{path}: findings.items leaves additionalProperties open at "
            f"{open_objects} — the schema file closes every object, so an "
            f"extra key the action lets through is dropped as malformed "
            f"afterwards (#420).")
        return
    note(f"{path}: --json-schema's findings.items matches the finding schema's required shape.")


def check_stage(root, path):
    full = os.path.join(root, *path.split("/"))
    if not os.path.isfile(full):
        fail(f"{path} does not exist — cannot check its findings wiring at all.")
        return
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"{path} could not be parsed as YAML ({exc}) — cannot check its "
            f"findings wiring.")
        return

    has_paragraph = has_paragraph_in_prompt(doc)
    has_step = has_filing_step(doc)

    if has_paragraph and not has_step:
        fail(f"{path} carries the FR-003 findings paragraph in an agent "
            f"prompt, but no step in this workflow calls "
            f"wing-commander-stage-findings — a proposal with nothing to "
            f"read it.")
    elif has_step and not has_paragraph:
        fail(f"{path} calls wing-commander-stage-findings, but no agent "
            f"prompt in this workflow carries the FR-003 findings paragraph "
            f"(the stable substring {PARAGRAPH_SUBSTRING!r}) — a filing step "
            f"with nothing to propose to it.")
    elif has_paragraph and has_step:
        note(f"{path}: paragraph and filing step both present.")
    else:
        fail(f"{path} carries neither the FR-003 findings paragraph nor a "
            f"wing-commander-stage-findings step.")

    if has_paragraph:
        check_prompt_names_keys(path, doc)
    if path in STRUCTURED_STAGES:
        check_structured_schema(path, text)

    expected_signal = HEALTH_SIGNALS.get(path)
    if expected_signal and has_step:
        cond = filing_step_if_condition(doc) or ""
        if expected_signal not in cond:
            fail(f"{path}'s wing-commander-stage-findings step's `if:` "
                f"condition does not name the stage-health signal "
                f"{expected_signal!r} it requires (FR-024) — a regression "
                f"back to a bare non-skipped read-back check would let a "
                f"failed/exhausted agent run reach the filing step again.")
        else:
            note(f"{path}: filing step gated on the required stage-health signal.")


def evaluate(root="."):
    failures.clear()
    for path in STAGE_WORKFLOWS:
        check_stage(root, path)
    return list(failures)


# Maintainer review, Item 6: path -> (repository-variable name, the
# fromJSON(...) fallback literal that stage's default-on/default-off
# posture requires). implement/finalize default on ('true'); the other
# four default off ('false').
WRAPPER_FILING_ENABLED = {
    ".github/workflows/wing-commander-1-intake.yml": ("WING_COMMANDER_INTAKE_FINDINGS_FILING_ENABLED", "false"),
    ".github/workflows/wing-commander-2-clarify.yml": ("WING_COMMANDER_CLARIFY_FINDINGS_FILING_ENABLED", "false"),
    ".github/workflows/wing-commander-3-plan.yml": ("WING_COMMANDER_PLAN_FINDINGS_FILING_ENABLED", "false"),
    ".github/workflows/wing-commander-4-tasks.yml": ("WING_COMMANDER_TASKS_FINDINGS_FILING_ENABLED", "false"),
    ".github/workflows/wing-commander-5-implement.yml": ("WING_COMMANDER_IMPLEMENT_FINDINGS_FILING_ENABLED", "true"),
    ".github/workflows/wing-commander-6-finalize.yml": ("WING_COMMANDER_FINALIZE_FINDINGS_FILING_ENABLED", "true"),
}

FILING_ENABLED_LINE = re.compile(r"findings-filing-enabled:\s*(.+)")


def check_wrapper_coercion(root, path, var_name, default_literal):
    full = os.path.join(root, *path.split("/"))
    if not os.path.isfile(full):
        fail(f"{path} does not exist — cannot check its "
            f"findings-filing-enabled coercion.")
        return
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    lines = [m.group(1).strip() for m in FILING_ENABLED_LINE.finditer(text)]
    if not lines:
        fail(f"{path} has no findings-filing-enabled: line to check.")
        return
    expected = f"${{{{ fromJSON(vars.{var_name} || '{default_literal}') }}}}"
    bad = sorted({line for line in lines if line != expected})
    if bad:
        fail(f"{path}'s findings-filing-enabled value(s) {bad} do not match "
            f"the fromJSON parity form {expected!r} the adjacent "
            f"findings-cap input uses one line below — a repository "
            f"variable literally set to the string {default_literal!r} "
            f"would not coerce to the boolean it names (FR-029).")
    else:
        note(f"{path}: findings-filing-enabled coerced via fromJSON, "
            f"matching findings-cap's parity pattern.")


def evaluate_wrapper_filing_enabled(root="."):
    """Standalone from evaluate(): the existing STAGE_WORKFLOWS self-tests
    build tmp fixtures containing only the six *published* workflows, and
    were never exercising the six *wrapper* workflows this check reads —
    folding this into evaluate() would make every one of those fixtures
    also need six wrapper files they don't otherwise test."""
    added = []
    for path, (var_name, default_literal) in WRAPPER_FILING_ENABLED.items():
        before = len(failures)
        check_wrapper_coercion(root, path, var_name, default_literal)
        added.extend(failures[before:])
    return added


# --------------------------------------------------------------------------
# --self-test
# --------------------------------------------------------------------------
def _write(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


# #420: the finding's required keys, quoted the way the schema spells them —
# every fixture prompt that carries the paragraph carries these too, so the
# self-tests below keep testing the co-occurrence they were written for
# rather than tripping the key check.
KEYS_CLAUSE = ('"title" "what" "evidence" "file_paths" "fingerprint_basis" '
               '"file_path" "gate_or_artifact"')
# A --json-schema whose findings.items is the real shape (#420). Harmless on
# a fixture for a fenced-block stage: the structured check only reads
# STRUCTURED_STAGES paths.
GOOD_ITEMS = ('{"type":"object","properties":{"title":{"type":"string"},'
              '"what":{"type":"string"},"evidence":{"type":"object","properties":'
              '{"file_paths":{"type":"array","items":{"type":"string"}},'
              '"detail":{"type":"string"}},"required":["file_paths"],'
              '"additionalProperties":false},"fingerprint_basis":{"type":"object",'
              '"properties":{"file_path":{"type":"string"},"gate_or_artifact":'
              '{"type":"string"}},"required":["file_path","gate_or_artifact"],'
              '"additionalProperties":false}},"required":["title","what","evidence",'
              '"fingerprint_basis"],"additionalProperties":false}')
# The shape the two structured stages shipped with (#420): array of untyped
# objects — the action enforces nothing about a finding's keys.
UNTYPED_ITEMS = '{"type":"object"}'
# Right required keys, but the object left open: an extra key gets through
# the action and is dropped as malformed afterwards.
OPEN_ITEMS = GOOD_ITEMS.replace(',"additionalProperties":false}', '}', 1)


def _schema_arg(items):
    return ("--json-schema '{\"type\":\"object\",\"properties\":{\"findings\":"
            "{\"type\":\"array\",\"items\":" + items + "}}}'")


def _agent_step(prompt_tail=KEYS_CLAUSE, items=GOOD_ITEMS):
    lines = ["      - uses: anthropics/claude-code-action@v1",
             "        with:",
             "          prompt: |",
             "            do not attempt to file it yourself"]
    if prompt_tail:
        lines.append("            " + prompt_tail)
    if items is not None:
        lines += ["          claude_args: |",
                  "            " + _schema_arg(items)]
    return "\n".join(lines) + "\n"


def _filing_step(if_expr=None):
    s = ("      - uses: ./.wing-commander-pipeline/.github/actions/"
         "wing-commander-stage-findings\n")
    if if_expr:
        s += "        if: ${{ !cancelled() && " + if_expr + " }}\n"
    return s


HEADER = "on:\n  workflow_call: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"

PARAGRAPH_ONLY = HEADER + _agent_step()
STEP_ONLY = HEADER + _filing_step()
BOTH = HEADER + _agent_step() + _filing_step()
# Nit #8 regression fixture: the phrase sits in a YAML COMMENT, never in any
# step's `with.prompt` — proves the scoped check no longer treats that as
# satisfying the paragraph requirement the way a whole-file substring scan
# would.
COMMENT_ONLY_PARAGRAPH_WITH_STEP = (
    HEADER
    + "      # do not attempt to file it yourself (stale comment, not a prompt)\n"
    + _filing_step())
# #420 regression fixtures.
PROMPT_MISSING_KEY = HEADER + _agent_step(
    prompt_tail=KEYS_CLAUSE.replace(' "gate_or_artifact"', "")) + _filing_step()
UNTYPED_ITEMS_STRUCTURED = HEADER + _agent_step(items=UNTYPED_ITEMS) + _filing_step(
    HEALTH_SIGNALS[".github/workflows/intake.yml"])
OPEN_ITEMS_STRUCTURED = HEADER + _agent_step(items=OPEN_ITEMS) + _filing_step(
    HEALTH_SIGNALS[".github/workflows/intake.yml"])
NO_SCHEMA_STRUCTURED = HEADER + _agent_step(items=None) + _filing_step(
    HEALTH_SIGNALS[".github/workflows/intake.yml"])


def _both_with_if(expected_signal):
    return HEADER + _agent_step() + _filing_step(expected_signal)


def _default_both_for(path):
    """BOTH, but carrying the required `if:` for a HEALTH_SIGNALS stage —
    otherwise every self-test case that doesn't override that stage's
    index would trip the health-gating check with a false positive."""
    signal = HEALTH_SIGNALS.get(path)
    return _both_with_if(signal) if signal else BOTH


def _tmp_with_stages(contents_by_index):
    tmp = tempfile.mkdtemp(prefix="wc-stage-findings-wiring-")
    for i, path in enumerate(STAGE_WORKFLOWS):
        _write(tmp, path, contents_by_index.get(i, _default_both_for(path)))
    return tmp


def selftest_real_six_pass():
    case = "the real six stage workflows pass post-implementation"
    found = evaluate(".")
    if found:
        fail(f"[{case}] real tree failed: {found}")
    else:
        note(f"[{case}] passed")


def selftest_paragraph_without_step_fails():
    case = "paragraph present, step absent fails, naming the stage"
    tmp = _tmp_with_stages({0: PARAGRAPH_ONLY})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[0] in f and "nothing to read it" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[0]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_step_without_paragraph_fails():
    case = "step present, paragraph absent fails, naming the stage"
    tmp = _tmp_with_stages({1: STEP_ONLY})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[1] in f and "nothing to propose to it" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[1]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_comment_only_paragraph_does_not_satisfy():
    case = "the phrase in a YAML comment (not a prompt:) does not satisfy the paragraph check"
    tmp = _tmp_with_stages({1: COMMENT_ONLY_PARAGRAPH_WITH_STEP})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[1] in f and "nothing to propose to it" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[1]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_health_signal_fails():
    case = "a filing step missing its required stage-health signal fails, naming it"
    tmp = _tmp_with_stages({0: BOTH})  # BOTH's `if:` (none) doesn't name intake's required signal
    try:
        found = evaluate(tmp)
        expected = HEALTH_SIGNALS[STAGE_WORKFLOWS[0]]
        hit = [f for f in found if STAGE_WORKFLOWS[0] in f and expected in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[0]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_prompt_missing_key_fails():
    case = "a prompt carrying the paragraph but not every required key fails, naming the key (#420)"
    tmp = _tmp_with_stages({2: PROMPT_MISSING_KEY})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[2] in f and "gate_or_artifact" in f
               and "required key" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[2]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_structured_untyped_items_fails():
    case = "a structured stage whose --json-schema leaves findings.items untyped fails (#420, the shipped shape)"
    tmp = _tmp_with_stages({0: UNTYPED_ITEMS_STRUCTURED})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[0] in f and "findings.items" in f
               and "requires" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[0]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_structured_open_items_fails():
    case = "a structured stage whose findings.items leaves additionalProperties open fails (#420)"
    tmp = _tmp_with_stages({0: OPEN_ITEMS_STRUCTURED})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[0] in f and "additionalProperties" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[0]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_structured_no_schema_fails():
    case = "a structured stage with no inline --json-schema fails (#420)"
    tmp = _tmp_with_stages({1: NO_SCHEMA_STRUCTURED})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[1] in f and "--json-schema" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[1]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_workflow_fails_loud():
    case = "a missing named stage workflow fails loudly, not vacuously"
    tmp = tempfile.mkdtemp(prefix="wc-stage-findings-wiring-")
    try:
        for i, path in enumerate(STAGE_WORKFLOWS):
            if i == 2:
                continue
            _write(tmp, path, _default_both_for(path))
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[2] in f and "does not exist" in f]
        if not hit:
            fail(f"[{case}] expected a finding for missing {STAGE_WORKFLOWS[2]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_clean_fixture_passes():
    case = "all six carrying both sides passes clean"
    tmp = _tmp_with_stages({})
    try:
        found = evaluate(tmp)
        if found:
            fail(f"[{case}] unexpected finding(s): {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Item 6 regression fixture: the pre-fix bare `vars.X || true/false` form,
# missing the fromJSON(...) wrap the findings-cap input one line below
# already relies on.
BROKEN_FILING_ENABLED_WRAPPER = (
    "on:\n  workflow_call: {}\njobs:\n  x:\n    uses: ./.github/workflows/implement.yml\n"
    "    with:\n"
    "      findings-filing-enabled: ${{ vars.WING_COMMANDER_IMPLEMENT_FINDINGS_FILING_ENABLED || true }}\n"
    "      findings-cap: ${{ fromJSON(vars.WING_COMMANDER_FINDINGS_CAP || '3') }}\n"
)


def selftest_wrapper_missing_fromjson_fails():
    case = "a wrapper's findings-filing-enabled without fromJSON() fails, naming the stage and the coercion gap"
    tmp = tempfile.mkdtemp(prefix="wc-stage-findings-wiring-")
    try:
        target = ".github/workflows/wing-commander-5-implement.yml"
        _write(tmp, target, BROKEN_FILING_ENABLED_WRAPPER)
        before = len(failures)
        check_wrapper_coercion(tmp, target, *WRAPPER_FILING_ENABLED[target])
        found = failures[before:]
        hit = [f for f in found if target in f and "fromJSON parity form" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {target}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_literal_string_false_coerces_off_via_fromjson():
    """Item 6's actual ask: prove the literal repository-variable string
    "false" turns filing off through fromJSON, where the pre-fix bare `||`
    form could not. GitHub Actions' `||` returns its first truthy operand,
    and a non-empty string ("false") is truthy — so `vars.X || true` (the
    old form) evaluates to the *string* "false", which a `type: boolean`
    workflow_call input cannot rely on coercing to `false`. `fromJSON`
    parses that same string as JSON instead, the same coercion
    `findings-cap` already relies on for its own numeric default."""
    case = "fromJSON('false')/fromJSON('true') coerce the literal strings to real booleans"
    if json.loads("false") is not False:
        fail(f"[{case}] json.loads('false') did not produce boolean False — "
            f"the coercion this fix relies on does not hold.")
    elif json.loads("true") is not True:
        fail(f"[{case}] json.loads('true') did not produce boolean True — "
            f"the coercion this fix relies on does not hold.")
    else:
        note(f"[{case}] passed")


def selftest_wrapper_real_six_pass():
    case = "the real six wrapper workflows' findings-filing-enabled all match the fromJSON parity form"
    found = evaluate_wrapper_filing_enabled(".")
    if found:
        fail(f"[{case}] real tree failed: {found}")
    else:
        note(f"[{case}] passed")


def run_selftest():
    use_utf8_stdout()
    selftest_clean_fixture_passes()
    selftest_paragraph_without_step_fails()
    selftest_step_without_paragraph_fails()
    selftest_comment_only_paragraph_does_not_satisfy()
    selftest_missing_health_signal_fails()
    selftest_prompt_missing_key_fails()
    selftest_structured_untyped_items_fails()
    selftest_structured_open_items_fails()
    selftest_structured_no_schema_fails()
    selftest_missing_workflow_fails_loud()
    selftest_wrapper_missing_fromjson_fails()
    selftest_literal_string_false_coerces_off_via_fromjson()
    selftest_real_six_pass()
    selftest_wrapper_real_six_pass()
    print(f"verify-stage-findings-wiring --self-test: {len(failures)} failure(s).")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()

    if args.self_test:
        sys.exit(run_selftest())

    found = evaluate(".")
    found += evaluate_wrapper_filing_enabled(".")
    print(f"verify-stage-findings-wiring: {len(found)} failure(s).")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
