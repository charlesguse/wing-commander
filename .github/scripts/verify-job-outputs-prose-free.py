#!/usr/bin/env python3
"""Gate 48: no published stage lifts free prose into a job-level output.

WHY THIS EXISTS (issue #287)
----------------------------
pr-conversation.yml carried every classified review leg — including the
drafted tasks.md prose — through the `classifications` job output of
`classify-and-announce`, and `act`'s matrix was built from it. The runner
checks every JOB output at job completion and, if any substring of the
value would be redacted by its secret masker, drops the WHOLE output
("Skip output '<name>' since it may contain secret"). The masker redacts
more than configured secrets: it also redacts any key=value token whose key
is one of two well-known credential words (the p-word and its three-letter
abbreviation, case-insensitive), whether or not a secret matches. A drafted
task that quoted a shell line from the repository assigning such a variable
therefore emptied the output, the matrix job was skipped, no leg folded, and
the stage reported success. Four review folds on one final PR were lost
that way before anyone noticed.

The structural fix is that a job output must never carry text a human or a
model wrote, or text copied out of the repository: those bodies now travel
in a workflow artifact, and the job output carries only a projection of
synthesized identifiers. This gate is what keeps that true after the next
edit.

THE RULE, PRAGMATICALLY
-----------------------
For every published stage (wc_published_stages), every job-level
`outputs:` entry, and every `steps.<id>.outputs.<name>` reference inside
its value: the producing step must not be PROSE-TAINTED, unless the output
carries a VERIFIED prose-free declaration.

A step is prose-tainted when any of these hold:

  (a) it is an agent step — `uses:` names `claude-code-action` — so its
      outputs and its transcript are model-authored;
  (b) its `run:`, `env:` or `with:` text references a taint SOURCE:
        - the agent transcript file, claude-execution-output.json;
        - a request-text input (`inputs.<x>` whose name ends in body, hunk,
          text, message or prompt);
        - an event body (`github.event.{comment,review,issue,
          pull_request,discussion}.body`, or a `diff_hunk`);
  (c) it references `steps.<t>.outputs` of an earlier prose-tainted step;
  (d) it names a same-job scratch file an earlier prose-tainted step also
      names — `$RUNNER_TEMP/<f>`, `${{ runner.temp }}/<f>` or
      `/tmp/wing-commander/<f>`, keyed on the first path component — which
      is how a transcript's structured result reaches a later step here
      (schema-check writes classifications-raw.json, confirm reads it);
  (e) it is an `actions/download-artifact` step whose `with.name` matches an
      artifact an `actions/upload-artifact` step in a prose-tainted step of
      the same file uploaded.

Taint is propagated forward through a job's steps in order, so the shape
that bit — agent step -> transcript -> raw JSON file -> confirm step ->
job output — is caught at the confirm step's output.

Deliberately NOT modelled (say so rather than pretend): text fetched with
`gh api`/`gh pr view`/`gh issue view` (comment bodies are human-authored
too), and repository files read directly with `cat`/`jq` from the checkout.
Widening the sources to those flags nearly every identity-resolution step
in the fleet (spec-meta.json reads, PR head refs) for outputs that are
numbers and branch names. The declaration mechanism below is how a future
output that genuinely needs one of those sources says so verifiably.

VERIFIED DECLARATIONS
---------------------
A tainted step may still feed a job output when the output line is
immediately preceded by a comment line of the form

    # prose-free: <shape>

and the gate can verify the shape against the step's own `run:` text.
Three shapes exist; anything else is a failure, not an exemption:

  map({k1, "k2", ...})   the `<name>=` write line must apply exactly this jq
                          program (`jq [-flags] 'map({...})'`), and every
                          key must be in PROSE_FREE_KEYS below — identifiers
                          the workflow synthesizes or copies from a declared
                          input, never from a person or a model.
  length                  the `<name>=` write line must apply exactly
                          `jq [-flags] 'length'` — a count.
  literal                 every `<name>=` write line is literal text plus
                          `$VAR`/`${VAR}` references, each of which is either
                          a runner-provided GITHUB_*/RUNNER_* variable or a
                          step `env:` entry whose expression names no taint
                          source and no prose-tainted step.

A declaration whose shape the run: text does not bear is reported as its
own failure, so the comment can never drift into a lie.

REGISTERED EXCEPTIONS
---------------------
EXCEPTIONS below names (file, job, output) triples that are flagged today
and pre-date this gate. Each is reported as a warning with its reason, and
the gate FAILS if an entry stops being flagged — a stale exception is a
rule that has silently widened (Gate 7's precedent for the pr-conversation
act binding). Fixing one means deleting its entry in the same change.

USAGE
-----
    python3 .github/scripts/verify-job-outputs-prose-free.py
    python3 .github/scripts/verify-job-outputs-prose-free.py --self-test
"""
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_published_stages import published_stages  # noqa: E402

# Keys a `map({...})` projection may carry into a job output. Every entry
# is a value the workflow itself synthesizes (`leg-<index>`) or copies from
# a declared workflow_call input (an adopter's environment name) — nothing
# a person typed into a comment or a model drafted.
PROSE_FREE_KEYS = {"id", "confirm-environment"}

# (file, job, output) -> why it is tolerated. See REGISTERED EXCEPTIONS.
# Two groups, both pre-dating this gate. PROSE: the value really can carry
# model-authored text, so these are #287's defect class waiting to recur —
# each needs the artifact treatment in its own change. ENUM: the value is a
# fixed token or boolean the step chose, computed from a tainted read; a
# masked substring there is implausible, but the rule cannot tell an enum
# write from a prose write without shell dataflow, and a declaration shape
# for "one of these literals" does not exist yet.
EXCEPTIONS = {
    # PROSE
    (".github/workflows/watchdog.yml", "diagnose", "findings"):
        "PROSE: the diagnose agent's findings (description/evidence text) "
        "feed act's matrix through this output — the same shape as #287.",
    (".github/workflows/implement.yml", "implement", "agent-final-message"):
        "PROSE: the implement agent's final message, lifted for the "
        "lifecycle-issue reply.",
    (".github/workflows/implement.yml", "implement", "final-reason"):
        "PROSE: the consolidated outcome reason can quote the transcript's "
        "terminal result.",
    # ENUM
    (".github/workflows/implement.yml", "implement", "final-ok"):
        "ENUM: true/false chosen by the consolidate step.",
    (".github/workflows/implement.yml", "implement", "final-tier"):
        "ENUM: a model name copied from an input or a step output.",
    (".github/workflows/implement.yml", "implement", "converged"):
        "ENUM: true/false chosen by the consolidate step.",
    (".github/workflows/watchdog.yml", "diagnose", "outcome"):
        "ENUM: diagnose-failed / passed-inspection / findings.",
    (".github/workflows/auto-update-spec-kit.yml", "evaluate-path", "outcome"):
        "ENUM: guard-skip / clean-bump / the read-back decision token.",
    (".github/workflows/auto-update-spec-kit.yml", "comment-reply", "resumed"):
        "ENUM: the literal true, written after the decision is recorded.",
}

AGENT_USES = re.compile(r"claude-code-action")
SOURCE_PATTERNS = [
    re.compile(r"claude-execution-output\.json"),
    re.compile(r"\binputs\.[\w-]*(?:body|hunk|text|message|prompt)\b"),
    re.compile(r"\bgithub\.event\.(?:comment|review|issue|pull_request|"
               r"discussion)\.(?:body|diff_hunk)\b"),
]
FILE_TOKEN = re.compile(
    r"(?:\$RUNNER_TEMP|\$\{RUNNER_TEMP\}|\$\{\{\s*runner\.temp\s*\}\}"
    r"|/tmp/wing-commander)/([\w.-]+)")
STEP_OUTPUT_REF = re.compile(r"\bsteps\.([\w-]+)\.outputs\.([\w-]+)")
DECLARATION = re.compile(r"^\s*#\s*prose-free:\s*(.+?)\s*\.?\s*$")
MAP_SHAPE = re.compile(r"^map\(\{(.*)\}\)$")
VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


def _rel(path):
    out = path.replace(os.sep, "/")
    while out.startswith("./"):
        out = out[2:]
    return out


def _text(value):
    """Flatten a step's run/env/with into one searchable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _step_text(step):
    return "\n".join(_text(step.get(k)) for k in ("run", "env", "with"))


def taint_jobs(wf):
    """-> {job_id: {step_id_or_index: bool tainted}} plus the tainted
    artifact-name set, following the docstring's rules (a)-(e)."""
    tainted_artifacts = set()
    result = {}
    for job_id, job in (wf.get("jobs") or {}).items():
        tainted_ids = set()
        tainted_files = set()
        per_step = {}
        for idx, step in enumerate((job or {}).get("steps") or []):
            step = step or {}
            sid = step.get("id") or f"#{idx}"
            text = _step_text(step)
            uses = str(step.get("uses") or "")
            tainted = False
            if AGENT_USES.search(uses):
                tainted = True
            if any(p.search(text) for p in SOURCE_PATTERNS):
                tainted = True
            for ref_id, _ in STEP_OUTPUT_REF.findall(text):
                if ref_id in tainted_ids:
                    tainted = True
            files = set(FILE_TOKEN.findall(text))
            if files & tainted_files:
                tainted = True
            if uses.startswith("actions/download-artifact"):
                name = str((step.get("with") or {}).get("name") or "")
                if name in tainted_artifacts:
                    tainted = True
            if tainted:
                tainted_ids.add(sid)
                tainted_files |= files
                if uses.startswith("actions/upload-artifact"):
                    tainted_artifacts.add(
                        str((step.get("with") or {}).get("name") or ""))
            per_step[sid] = tainted
        result[job_id] = per_step
    return result


def _steps_by_id(job):
    out = {}
    for step in (job or {}).get("steps") or []:
        if (step or {}).get("id"):
            out[step["id"]] = step
    return out


def _declaration_for(raw_lines, name, sid, oname):
    """The `# prose-free:` shape declared directly above the job-output line
    `<name>: ${{ ... steps.<sid>.outputs.<oname> ... }}`, or None."""
    line_re = re.compile(
        r"^\s*" + re.escape(name) + r":\s*\$\{\{.*\bsteps\."
        + re.escape(sid) + r"\.outputs\." + re.escape(oname) + r"\b.*\}\}\s*$")
    for i, line in enumerate(raw_lines):
        if not line_re.match(line):
            continue
        j = i - 1
        while j >= 0 and raw_lines[j].strip().startswith("#"):
            m = DECLARATION.match(raw_lines[j])
            if m:
                return m.group(1)
            j -= 1
        return None
    return None


def _write_lines(run_text, oname):
    """Every non-comment run: line that writes `<oname>=` to an output."""
    pat = re.compile(r"(?:echo|printf)\s+[\"']?" + re.escape(oname) + r"=")
    return [l for l in run_text.splitlines()
            if not l.lstrip().startswith("#") and pat.search(l)]


def _env_is_clean(expr, tainted_ids):
    text = str(expr)
    if any(p.search(text) for p in SOURCE_PATTERNS):
        return False
    return not any(ref in tainted_ids
                   for ref, _ in STEP_OUTPUT_REF.findall(text))


def verify_declaration(decl, step, oname, tainted_ids):
    """-> None when the run: text bears the declared shape, else a reason."""
    run_text = str(step.get("run") or "")
    lines = _write_lines(run_text, oname)
    if not lines:
        return (f"no run: line writes '{oname}=' in step "
                f"{step.get('id')!r}, so the declaration verifies nothing")
    m = MAP_SHAPE.match(decl)
    if m:
        keys = [k.strip().strip("\"'") for k in m.group(1).split(",")
                if k.strip()]
        bad = [k for k in keys if k not in PROSE_FREE_KEYS]
        if bad or not keys:
            return (f"projection key(s) {bad or keys!r} are not in "
                    f"PROSE_FREE_KEYS {sorted(PROSE_FREE_KEYS)!r}")
        prog = re.compile(r"\bjq(?:\s+-\w+)*\s+'" + re.escape(decl) + r"'")
        if not all(prog.search(l) for l in lines):
            return (f"the '{oname}=' write line does not apply exactly "
                    f"jq '{decl}'")
        return None
    if decl == "length":
        prog = re.compile(r"\bjq(?:\s+-\w+)*\s+'length'")
        if not all(prog.search(l) for l in lines):
            return f"the '{oname}=' write line does not apply exactly jq 'length'"
        return None
    if decl == "literal":
        env = step.get("env") or {}
        for line in lines:
            value = line.split(oname + "=", 1)[1]
            value = re.sub(r"\s*>>\s*\"?\$GITHUB_OUTPUT\"?\s*$", "", value)
            value = value.rstrip().rstrip("\"'")
            if "$(" in value or "`" in value:
                return (f"the '{oname}=' write line embeds a command "
                        f"substitution: {line.strip()!r}")
            for var in VAR_REF.findall(value):
                if var.startswith(("GITHUB_", "RUNNER_")):
                    continue
                if var not in env:
                    return (f"'{oname}=' references ${var}, which is not a "
                            f"step env: entry (a shell-computed value is "
                            f"not literal)")
                if not _env_is_clean(env[var], tainted_ids):
                    return (f"'{oname}=' references ${var}, whose env: "
                            f"expression names a taint source or a "
                            f"prose-tainted step")
        return None
    return f"unknown declaration shape {decl!r}"


def scan(root=".", exceptions=None):
    """-> (failures, warnings). Each is a list of strings."""
    exceptions = EXCEPTIONS if exceptions is None else exceptions
    failures, warnings = [], []
    seen_exceptions = set()
    stages = published_stages(root)
    if not stages:
        return (["no workflow declares on.workflow_call — the derivation "
                 "is broken or the stages moved; refusing to pass by "
                 "checking nothing"], warnings)
    for rel in stages:
        path = os.path.join(root, rel) if root != "." else rel
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        raw_lines = raw.splitlines()
        wf = yaml.safe_load(raw) or {}
        taints = taint_jobs(wf)
        for job_id, job in (wf.get("jobs") or {}).items():
            steps = _steps_by_id(job)
            tainted_ids = {s for s, t in taints.get(job_id, {}).items() if t}
            for name, value in ((job or {}).get("outputs") or {}).items():
                for sid, oname in STEP_OUTPUT_REF.findall(str(value)):
                    if sid not in tainted_ids:
                        continue
                    step = steps.get(sid, {})
                    decl = _declaration_for(raw_lines, name, sid, oname)
                    key = (_rel(rel), job_id, name)
                    if decl is None:
                        msg = (f"{key[0]}: job {job_id!r} output {name!r} is "
                               f"fed from steps.{sid}.outputs.{oname}, and "
                               f"step {sid!r} is prose-tainted (it reads "
                               f"model-, human- or repository-authored "
                               f"text). A masked substring anywhere in the "
                               f"value makes the runner drop the whole "
                               f"output silently (#287). Carry the bodies "
                               f"in an artifact and lift only a "
                               f"`# prose-free:` projection.")
                        if key in exceptions:
                            seen_exceptions.add(key)
                            warnings.append(f"{msg} [registered exception: "
                                            f"{exceptions[key]}]")
                        else:
                            failures.append(msg)
                        continue
                    why = verify_declaration(decl, step, oname, tainted_ids)
                    if why:
                        failures.append(
                            f"{key[0]}: job {job_id!r} output {name!r} "
                            f"declares `prose-free: {decl}` but the run: "
                            f"text does not bear it — {why}. A declaration "
                            f"the code does not honour is worse than none.")
    for key, reason in exceptions.items():
        if key not in seen_exceptions:
            failures.append(
                f"stale EXCEPTIONS entry {key!r} ({reason}) — it is no "
                f"longer flagged, so either it was fixed (delete the entry "
                f"in the same change) or the rule has silently narrowed.")
    return failures, warnings


# ------------------------------------------------------------ self-test

STAGE_HEAD = """\
name: fixture
on:
  workflow_call:
    inputs:
      body:
        type: string
        required: true
jobs:
"""

# The shape that bit: agent -> transcript -> raw JSON file -> confirm step
# -> job output.
FIXTURE_SHIPPED_SHAPE = STAGE_HEAD + """\
  classify:
    runs-on: ubuntu-latest
    outputs:
      classifications: ${{ steps.confirm.outputs.classifications }}
    steps:
      - id: agent
        uses: anthropics/claude-code-action@v1
      - id: schema-check
        run: |
          jq -c '.classifications' "$RUNNER_TEMP/claude-execution-output.json" > "$RUNNER_TEMP/classifications-raw.json"
      - id: confirm
        run: |
          result=$(jq -c 'map(. + {id: "x"})' "$RUNNER_TEMP/classifications-raw.json")
          echo "classifications=$result" >> "$GITHUB_OUTPUT"
"""

FIXTURE_DIRECT_AGENT = STAGE_HEAD + """\
  j:
    runs-on: ubuntu-latest
    outputs:
      summary: ${{ steps.agent.outputs.result }}
    steps:
      - id: agent
        uses: anthropics/claude-code-action@v1
"""

FIXTURE_INPUT_BODY = STAGE_HEAD + """\
  j:
    runs-on: ubuntu-latest
    outputs:
      echoed: ${{ steps.stage.outputs.echoed }}
    steps:
      - id: stage
        env:
          BODY: ${{ inputs.body }}
        run: echo "echoed=$BODY" >> "$GITHUB_OUTPUT"
"""

FIXTURE_UNTAINTED = STAGE_HEAD + """\
  j:
    runs-on: ubuntu-latest
    outputs:
      spec-dir: ${{ steps.identity.outputs.spec-dir }}
    steps:
      - id: identity
        run: echo "spec-dir=specs/001-x" >> "$GITHUB_OUTPUT"
"""


def _declared_fixture(decl_line, keys_program, program_used=None):
    program_used = program_used or keys_program
    return STAGE_HEAD + f"""\
  classify:
    runs-on: ubuntu-latest
    outputs:
{decl_line}      legs: ${{{{ steps.confirm.outputs.legs }}}}
      # prose-free: length
      leg-count: ${{{{ steps.confirm.outputs.leg-count }}}}
      # prose-free: literal
      group: ${{{{ steps.confirm.outputs.group }}}}
    steps:
      - id: agent
        uses: anthropics/claude-code-action@v1
      - id: confirm
        env:
          PR_NUMBER: ${{{{ inputs.pr-number }}}}
        run: |
          result=$(jq -c '.classifications' "$RUNNER_TEMP/claude-execution-output.json")
          echo "legs=$(printf '%s' "$result" | jq -c '{program_used}')" >> "$GITHUB_OUTPUT"
          echo "leg-count=$(printf '%s' "$result" | jq 'length')" >> "$GITHUB_OUTPUT"
          echo "group=stop-pr-${{PR_NUMBER}}" >> "$GITHUB_OUTPUT"
"""


FIXTURE_DECLARED_OK = _declared_fixture(
    '      # prose-free: map({id, "confirm-environment"})\n',
    'map({id, "confirm-environment"})')
FIXTURE_DECLARED_BAD_KEY = _declared_fixture(
    '      # prose-free: map({id, summary})\n', 'map({id, summary})')
FIXTURE_DECLARED_NOT_BORNE = _declared_fixture(
    '      # prose-free: map({id, "confirm-environment"})\n',
    'map({id, "confirm-environment"})',
    program_used='map({id, "confirm-environment", summary})')
FIXTURE_UNDECLARED_PROJECTION = _declared_fixture(
    "", 'map({id, "confirm-environment"})')
# `literal` must reject a write that smuggles a command substitution or a
# shell-computed variable in behind literal-looking text.
FIXTURE_LITERAL_SUBSTITUTION = _declared_fixture(
    '      # prose-free: map({id, "confirm-environment"})\n',
    'map({id, "confirm-environment"})').replace(
    'echo "group=stop-pr-${PR_NUMBER}"',
    'echo "group=$(printf \'%s\' "$result" | jq -r \'.[0].summary\')"')


def _run_fixture(text, name="fixture.yml"):
    root = tempfile.mkdtemp()
    try:
        wdir = os.path.join(root, ".github", "workflows")
        os.makedirs(wdir)
        with open(os.path.join(wdir, name), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(text)
        return scan(root, exceptions={})
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _subject_mutations():
    """Mutations of the shipped pr-conversation.yml, each of which this
    gate must flag: the gate has to be able to fail its own subject."""
    subject = ".github/workflows/pr-conversation.yml"
    with open(subject, encoding="utf-8") as fh:
        original = fh.read()
    legs_line = "      legs: ${{ steps.confirm.outputs.legs }}\n"
    decl_line = '      # prose-free: map({id, "confirm-environment"})\n'
    for needle in (legs_line, decl_line):
        if original.count(needle) != 1:
            sys.exit(f"::error file={subject}::self-test expected exactly one "
                     f"occurrence of {needle.strip()!r} in the subject; "
                     f"update the self-test alongside the workflow.")
    return original, [
        ("the #287 shape restored: the full classifications JSON lifted "
         "to a job output",
         original.replace(
             legs_line,
             legs_line + "      classifications: ${{ steps.confirm.outputs"
                         ".classifications }}\n")),
        ("the legs projection declared with a prose key",
         original.replace(decl_line, "      # prose-free: map({id, summary})\n")
         .replace("jq -c 'map({id, \"confirm-environment\"})'",
                  "jq -c 'map({id, summary})'")),
        ("the legs declaration removed",
         original.replace(decl_line, "")),
        ("the legs projection widened behind an unchanged declaration",
         original.replace("jq -c 'map({id, \"confirm-environment\"})'",
                          "jq -c 'map({id, \"confirm-environment\", summary})'")),
    ]


def self_test():
    failures = []

    def expect(label, text, flagged, needle=None):
        found, _ = _run_fixture(text)
        if flagged and not found:
            failures.append(f"{label}: expected a finding, got none")
        elif not flagged and found:
            failures.append(f"{label}: expected clean, got {found}")
        elif flagged and needle and not any(needle in f for f in found):
            failures.append(f"{label}: finding does not mention {needle!r}: "
                            f"{found}")

    expect("shipped shape (agent -> file -> confirm -> output)",
           FIXTURE_SHIPPED_SHAPE, True, "prose-tainted")
    expect("direct agent-step output", FIXTURE_DIRECT_AGENT, True)
    expect("inputs.body echoed into an output", FIXTURE_INPUT_BODY, True)
    expect("untainted identity output", FIXTURE_UNTAINTED, False)
    expect("declared projection with allowlisted keys, length, literal",
           FIXTURE_DECLARED_OK, False)
    expect("declared projection carrying a prose key",
           FIXTURE_DECLARED_BAD_KEY, True, "PROSE_FREE_KEYS")
    expect("declaration the run: text does not bear",
           FIXTURE_DECLARED_NOT_BORNE, True, "does not apply exactly")
    expect("prose-free projection without a declaration",
           FIXTURE_UNDECLARED_PROJECTION, True, "prose-tainted")
    expect("literal declaration hiding a command substitution",
           FIXTURE_LITERAL_SUBSTITUTION, True, "command substitution")

    # The gate must be able to fail its own subject.
    original, mutations = _subject_mutations()
    root = tempfile.mkdtemp()
    try:
        wdir = os.path.join(root, ".github", "workflows")
        os.makedirs(wdir)
        target = os.path.join(wdir, "pr-conversation.yml")
        for label, mutated in mutations:
            if mutated == original:
                failures.append(f"subject mutation {label!r} changed "
                                f"nothing — update the self-test")
                continue
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(mutated)
            found, _ = scan(root, exceptions={})
            if not found:
                failures.append(f"MUTATION SURVIVED — {label}: the gate "
                                f"passed a pr-conversation.yml carrying it")
            else:
                print(f"Mutation OK — {label}: caught.")
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)
        found, _ = scan(root, exceptions={})
        if found:
            failures.append(f"the shipped pr-conversation.yml is not clean "
                            f"under this gate: {found}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        print(f"::error::self-test: {f}")
    print(f"Gate 48 self-test: 9 fixture(s), {len(mutations)} subject "
          f"mutation(s); {len(failures)} failure(s).")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures, warnings = scan()
    for w in warnings:
        print(f"::warning::{w}")
    for f in failures:
        print(f"::error::{f}")
    print(f"Gate 48: {len(failures)} failure(s), {len(warnings)} registered "
          f"exception(s) still flagged.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
