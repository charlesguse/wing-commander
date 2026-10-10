#!/usr/bin/env python3
"""Gate 146 -- the watchdog's diagnose shadow acts on nothing.

WHY THIS EXISTS
---------------
spec 110 (FR-008, FR-009, FR-012, SC-003) and constitution Principle II
(2.4.0): a trial shadow declares its own explicit Haiku model and turn
budget, is bounded and off by default, and acts on nothing -- its output is
recorded for comparison and never files, labels, comments, writes or
decides. The shadow is a second agent step in watchdog.yml's `diagnose`
job, the one job whose verdict does file and route, so every property that
keeps it inert is a property of YAML that a later edit can quietly undo:
one `if: always()`, one App-token reference, one adopter-extensible tool
list, one job output wired to the wrong step. This gate holds each of them
structurally, on every pull request.

WHAT IT CHECKS (watchdog.yml unless named)
-----------------------------------------
1. Inputs: `diagnose-shadow-enabled` is a boolean defaulting to false;
   `diagnose-shadow-model` defaults to claude-haiku-5-5;
   `diagnose-shadow-max-turns` is a number.
2. The shadow family -- every `diagnose` job step named "diagnose shadow"
   or "diagnose-shadow" (case-insensitive; the same test
   verify-watchdog-run.sh subtracts from the acting duration ceiling) --
   is non-empty, holds exactly one agent step (id `diagnose-shadow`), and
   is the job's contiguous TAIL: it runs after every step that reads back,
   uploads or reports the acting verdict, and no unnamed step can hide
   among it.
3. Every family step is `continue-on-error: true`, and its `if:` is a
   conjunction (no `||`, `failure()`, `success()`) gated on
   `inputs.diagnose-shadow-enabled` -- the first step directly, every later
   one through a family step that is. `always()`/`!cancelled()` (which
   Gate 23 requires of the verdict and fail-loud steps) is allowed only
   beside `steps.diagnose-shadow.outcome != 'skipped'`, so it can only
   admit a run on which the shadow agent itself ran.
4. The agent step: `timeout-minutes` <= 5, and the Diagnose step's own
   timeout plus the shadow's stays under the job's backstop; `GH_TOKEN`
   and `github_token` are exactly `${{ github.token }}`; `--model` is the
   `diagnose-shadow-model` input; its prompt and `--json-schema` are
   byte-equal to the Diagnose step's (the fallback research.md D7 names:
   no composite may invoke the agent action, Gate 38).
5. Its tool lists come from a family `wing-commander-tool-args` call with
   no adopter extra/override input; the allowed list holds no Write, Edit,
   NotebookEdit, bare Bash, Bash(gh:*), Bash(gh api:*) or Bash(git:*), and
   every Bash(gh ...) grant is a read-only subcommand; the disallowed list
   names Write and Edit.
6. No family step reads the App token (`steps.ctx.outputs.token`,
   `env.WC_BOT_TOKEN`), any `vars.*`, or a secret other than the two
   Claude credentials; no non-family step and no `diagnose` job output
   reads a family step's id.
7. wing-commander-8-watchdog.yml passes `diagnose-shadow-enabled` as
   exactly `${{ needs.trial-bound.outputs.enabled == 'true' }}` -- false
   whenever the trial-bound job was skipped or failed.

Usage: verify-diagnose-shadow-acts-on-nothing.py [--self-test]
Exit 0 = every check holds (self-test: every mutation is caught);
exit 1 = otherwise.
"""
import copy
import re
import sys

import yaml

WATCHDOG = ".github/workflows/watchdog.yml"
WRAPPER = ".github/workflows/wing-commander-8-watchdog.yml"
FAMILY_RE = re.compile(r"diagnose[ -]shadow", re.I)
AGENT_PREFIX = "anthropics/claude-code-action@"
TOOL_ARGS = "wing-commander-tool-args"
GITHUB_TOKEN = "${{ github.token }}"
ENABLED = "inputs.diagnose-shadow-enabled"
WRAPPER_ENABLED = "${{ needs.trial-bound.outputs.enabled == 'true' }}"
SHADOW_MAX_TIMEOUT = 5
# Read-only, and readable under this stage's github.token grant (issues,
# actions, checks -- no pull-requests; Gate 12 holds the grant side).
READ_ONLY_GH = {
    "gh run view", "gh run list", "gh issue view", "gh issue list",
    "gh label list",
}
FORBIDDEN_ALLOWED = {"Write", "Edit", "NotebookEdit", "Bash", "Bash(*)",
                     "Bash(gh:*)", "Bash(gh api:*)", "Bash(git:*)"}
BAD_IF = re.compile(r"\|\||failure\(\)|success\(\)")
STATUS_IF = re.compile(r"always\(\)|cancelled\(\)")
AGENT_RAN = "steps.diagnose-shadow.outcome != 'skipped'"
CLAUDE_SECRETS = {"claude-code-oauth-token", "anthropic-api-key"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        # GitHub's `on:` parses as True under YAML 1.1; nothing here reads it.
        return yaml.safe_load(fh)


def is_agent(step):
    return str((step or {}).get("uses", "")).startswith(AGENT_PREFIX)


def text_of(value):
    return yaml.safe_dump(value, default_flow_style=True, width=10 ** 9) \
        if not isinstance(value, str) else value


def step_ids_referenced(text):
    return set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", text))


def arg_value(claude_args, flag):
    """The value after `flag` in a claude_args block, quotes stripped; an
    unquoted value runs to the end of its line."""
    m = re.search(re.escape(flag) + r"[ \t]+('([^']*)'|\"([^\"]*)\"|([^\n]*\S))",
                  claude_args or "")
    if not m:
        return None
    return next(g for g in m.groups()[1:] if g is not None)


def tools(text):
    """Split a comma-joined tool list, keeping commas inside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in text or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def check(watchdog, wrapper):
    failures = []
    fail = failures.append

    # 1. Inputs.
    on = watchdog.get("on") or watchdog.get(True) or {}
    inputs = ((on.get("workflow_call") or {}).get("inputs")) or {}
    enabled = inputs.get("diagnose-shadow-enabled") or {}
    if enabled.get("type") != "boolean" or enabled.get("default") is not False:
        fail("input diagnose-shadow-enabled must be a boolean defaulting to "
             "false (FR-012: off by default for adopters)")
    if (inputs.get("diagnose-shadow-model") or {}).get("default") != "claude-haiku-5-5":
        fail("input diagnose-shadow-model must default to claude-haiku-5-5 "
             "(constitution II: the shadow declares an explicit Haiku model)")
    if (inputs.get("diagnose-shadow-max-turns") or {}).get("type") != "number":
        fail("input diagnose-shadow-max-turns must be a number (its own turn budget)")

    job = ((watchdog.get("jobs") or {}).get("diagnose")) or {}
    steps = list(job.get("steps") or [])
    family_idx = [i for i, s in enumerate(steps)
                  if FAMILY_RE.search(str((s or {}).get("name", "")))]
    if not family_idx:
        fail("no diagnose-shadow step found in the diagnose job -- the shadow "
             "was removed or renamed; update this gate with it")
        return failures
    family = [steps[i] for i in family_idx]
    family_ids = {s.get("id") for s in family if s.get("id")}

    # 2. Exactly one agent step; the family is the job's contiguous tail.
    agents = [s for s in family if is_agent(s)]
    if len(agents) != 1 or agents[0].get("id") != "diagnose-shadow":
        fail("the shadow family must hold exactly one agent step, id "
             "diagnose-shadow")
    if family_idx != list(range(len(steps) - len(family_idx), len(steps))):
        first = family_idx[0]
        stray = [s.get("name") for s in steps[first:] if s not in family]
        fail("the shadow family must be the diagnose job's contiguous tail, "
             "after every acting step; out of place: "
             + (", ".join(map(str, stray)) or "a family step precedes an "
                "acting step"))
    acting = steps[:family_idx[0]]
    diagnose = next((s for s in acting if s.get("id") == "diagnose"), None)
    if diagnose is None or not is_agent(diagnose):
        fail("the acting Diagnose step (id diagnose) must precede the shadow")

    # 3. continue-on-error and enable-gated conjunctive ifs.
    gated = set()
    for s in family:
        name = s.get("name")
        if s.get("continue-on-error") is not True:
            fail(f"shadow step {name!r} must be continue-on-error: true -- a "
                 "failed shadow may not change the diagnose job's result")
        cond = str(s.get("if") or "")
        if not cond or BAD_IF.search(cond):
            fail(f"shadow step {name!r} needs a conjunctive if: (no ||, "
                 f"failure(), success()); got {cond!r}")
            continue
        if STATUS_IF.search(cond) and AGENT_RAN not in cond:
            fail(f"shadow step {name!r} uses always()/!cancelled() without "
                 f"{AGENT_RAN!r}; got {cond!r}")
            continue
        refs = step_ids_referenced(cond)
        if ENABLED in cond or (refs & gated):
            if s.get("id"):
                gated.add(s["id"])
        else:
            fail(f"shadow step {name!r} is not gated on {ENABLED}, directly "
                 "or through a family step that is")
    if family and ENABLED not in str(family[0].get("if") or ""):
        fail(f"the first shadow step must test {ENABLED} itself")

    # 4/5. The agent step.
    if agents:
        agent = agents[0]
        timeout = agent.get("timeout-minutes")
        if not isinstance(timeout, (int, float)) or timeout > SHADOW_MAX_TIMEOUT:
            fail(f"the shadow agent step needs timeout-minutes <= "
                 f"{SHADOW_MAX_TIMEOUT}, got {timeout!r}")
        acting_timeout = (diagnose or {}).get("timeout-minutes")
        backstop = job.get("timeout-minutes")
        if (isinstance(timeout, (int, float))
                and isinstance(acting_timeout, (int, float))
                and isinstance(backstop, (int, float))):
            if acting_timeout + timeout >= backstop:
                fail(f"Diagnose ({acting_timeout}) + shadow ({timeout}) "
                     f"timeout-minutes must stay under the job backstop "
                     f"({backstop}), or a hung shadow can cost the acting "
                     "path its outputs")
        else:
            fail("the Diagnose step, the shadow step and the diagnose job "
                 "must each carry a numeric timeout-minutes")
        env = agent.get("env") or {}
        with_ = agent.get("with") or {}
        if env.get("GH_TOKEN") != GITHUB_TOKEN:
            fail("the shadow agent's GH_TOKEN must be exactly "
                 f"{GITHUB_TOKEN}, never the App token")
        if with_.get("github_token") != GITHUB_TOKEN:
            fail("the shadow agent's github_token must be exactly "
                 f"{GITHUB_TOKEN}, never the App token")
        args = str(with_.get("claude_args") or "")
        if arg_value(args, "--model") != "${{ inputs.diagnose-shadow-model }}":
            fail("the shadow agent's --model must be the diagnose-shadow-model "
                 "input")
        dwith = (diagnose or {}).get("with") or {}
        if with_.get("prompt") != dwith.get("prompt"):
            fail("the shadow's prompt must be byte-equal to the Diagnose "
                 "step's (research.md D7 fallback): paste the change into both")
        if arg_value(args, "--json-schema") != arg_value(
                str(dwith.get("claude_args") or ""), "--json-schema"):
            fail("the shadow's --json-schema must be the Diagnose step's")
        allowed_ref = arg_value(args, "--allowedTools") or ""
        disallowed_ref = arg_value(args, "--disallowedTools") or ""
        tool_steps = [s for s in family
                      if TOOL_ARGS in str(s.get("uses", ""))]
        tool_step = tool_steps[0] if len(tool_steps) == 1 else None
        if tool_step is None:
            fail("the shadow family must compose its tools with exactly one "
                 f"{TOOL_ARGS} call")
        else:
            tid = tool_step.get("id")
            if (allowed_ref != f"${{{{ steps.{tid}.outputs.allowed-tools }}}}"
                    or disallowed_ref
                    != f"${{{{ steps.{tid}.outputs.disallowed-tools }}}}"):
                fail("the shadow agent's --allowedTools/--disallowedTools must "
                     "be its own tool-args step's outputs")
            twith = tool_step.get("with") or {}
            extras = sorted(k for k in twith if k.startswith("extra-")
                            or k.endswith("-override"))
            if extras:
                fail("the shadow's tool list is fixed read-only; no adopter "
                     "extra/override may reach it: " + ", ".join(extras))
            allowed = tools(twith.get("default-allowed-tools"))
            disallowed = set(tools(twith.get("default-disallowed-tools")))
            for t in allowed:
                if t in FORBIDDEN_ALLOWED:
                    fail(f"the shadow may not be granted {t}")
                m = re.fullmatch(r"Bash\((gh[^:)]*)(?::\*)?\)", t)
                if m and m.group(1).strip() not in READ_ONLY_GH:
                    fail(f"the shadow's gh grant {t} is not a read-only "
                         "subcommand")
            for t in ("Write", "Edit"):
                if t not in disallowed:
                    fail(f"the shadow's disallowed list must name {t}")

    # 6. Credentials, ambient state, and nothing reads the shadow.
    for s in family:
        blob = text_of(s)
        name = s.get("name")
        if "steps.ctx.outputs.token" in blob or "WC_BOT_TOKEN" in blob:
            fail(f"shadow step {name!r} reads the App token")
        if re.search(r"\bvars\.", blob):
            fail(f"shadow step {name!r} reads vars.* -- the wrapper decides "
                 "(FR-012, Principle VII)")
        for secret in re.findall(r"secrets\.([A-Za-z0-9_-]+)", blob):
            if secret not in CLAUDE_SECRETS:
                fail(f"shadow step {name!r} reads secrets.{secret}")
    for s in acting:
        hit = step_ids_referenced(text_of(s)) & family_ids
        if hit:
            fail(f"acting step {s.get('name')!r} reads shadow step(s) "
                 f"{sorted(hit)}")
    for out, value in (job.get("outputs") or {}).items():
        hit = step_ids_referenced(str(value)) & family_ids
        if hit:
            fail(f"diagnose job output {out!r} reads shadow step(s) "
                 f"{sorted(hit)}")

    # 7. The wrapper's one-line false fallback.
    wjob = ((wrapper.get("jobs") or {}).get("watchdog")) or {}
    passed = (wjob.get("with") or {}).get("diagnose-shadow-enabled")
    if passed != WRAPPER_ENABLED:
        fail(f"{WRAPPER} must pass diagnose-shadow-enabled as exactly "
             f"{WRAPPER_ENABLED!r}, got {passed!r}")
    return failures


# ── self-test ──────────────────────────────────────────────────────────────
def _job(wd):
    return wd["jobs"]["diagnose"]


def _family(wd):
    return [s for s in _job(wd)["steps"]
            if FAMILY_RE.search(str(s.get("name", "")))]


def _agent(wd):
    return next(s for s in _family(wd) if s.get("id") == "diagnose-shadow")


def _tool_step(wd):
    return next(s for s in _family(wd) if TOOL_ARGS in str(s.get("uses", "")))


def _move_family_before_upload(wd):
    steps = _job(wd)["steps"]
    fam = _family(wd)
    rest = [s for s in steps if s not in fam]
    at = next(i for i, s in enumerate(rest) if s.get("name") == "Upload findings")
    _job(wd)["steps"] = rest[:at] + fam + rest[at:]


def _unnamed_step_in_family(wd):
    steps = _job(wd)["steps"]
    at = steps.index(_agent(wd)) + 1
    steps.insert(at, {"name": "Post the comparison", "continue-on-error": True,
                      "if": "steps.diagnose-shadow.outcome != 'skipped'",
                      "run": "gh issue comment 1 --body x"})


def _acting_reads_shadow(wd):
    step = next(s for s in _job(wd)["steps"]
                if s.get("name") == 'Report "passed inspection" to lifecycle issue')
    step.setdefault("env", {})["SHADOW"] = \
        "${{ steps.diagnose-shadow-trial.outputs.outcome }}"


MUTATIONS = [
    ("enable input defaults to true",
     lambda wd, w: wd.get("on", wd.get(True))["workflow_call"]["inputs"]
     ["diagnose-shadow-enabled"].__setitem__("default", True)),
    ("shadow model default drifts",
     lambda wd, w: wd.get("on", wd.get(True))["workflow_call"]["inputs"]
     ["diagnose-shadow-model"].__setitem__("default", "claude-opus-5-5")),
    ("shadow agent step loses continue-on-error",
     lambda wd, w: _agent(wd).pop("continue-on-error")),
    ("a later shadow step loses continue-on-error",
     lambda wd, w: _family(wd)[-1].pop("continue-on-error")),
    ("a shadow step runs on always()",
     lambda wd, w: _family(wd)[-2].__setitem__("if", "always()")),
    ("a shadow step runs on always() gated only on its own predecessor",
     lambda wd, w: _family(wd)[-1].__setitem__(
         "if", "always() && steps.diagnose-shadow-metrics.outcome == 'success'")),
    ("a shadow step's if: admits a run through ||",
     lambda wd, w: _family(wd)[-1].__setitem__(
         "if", "steps.diagnose-shadow-metrics.outcome == 'success' || "
               "steps.diagnose.outcome == 'success'")),
    ("the first shadow step is not gated on the enable input",
     lambda wd, w: _family(wd)[0].__setitem__(
         "if", "steps.diagnose.outcome != 'skipped'")),
    ("shadow agent GH_TOKEN is the App token",
     lambda wd, w: _agent(wd)["env"].__setitem__(
         "GH_TOKEN", "${{ steps.ctx.outputs.token }}")),
    ("shadow agent github_token is the App token",
     lambda wd, w: _agent(wd)["with"].__setitem__(
         "github_token", "${{ steps.ctx.outputs.token }}")),
    ("shadow agent timeout removed",
     lambda wd, w: _agent(wd).pop("timeout-minutes")),
    ("shadow agent timeout pushes past the job backstop",
     lambda wd, w: _agent(wd).__setitem__("timeout-minutes", 10)),
    ("the acting timeout grows until the sum reaches the job backstop",
     lambda wd, w: next(s for s in _job(wd)["steps"]
                        if s.get("id") == "diagnose").__setitem__(
         "timeout-minutes", 15)),
    ("shadow agent runs the acting model",
     lambda wd, w: _agent(wd)["with"].__setitem__(
         "claude_args", _agent(wd)["with"]["claude_args"].replace(
             "${{ inputs.diagnose-shadow-model }}",
             "${{ steps.resolve-diagnose-model.outputs.model }}"))),
    ("shadow prompt drifts from Diagnose's",
     lambda wd, w: _agent(wd)["with"].__setitem__(
         "prompt", _agent(wd)["with"]["prompt"] + "Also be brief.\n")),
    ("shadow granted Write",
     lambda wd, w: _tool_step(wd)["with"].__setitem__(
         "default-allowed-tools",
         _tool_step(wd)["with"]["default-allowed-tools"] + ",Write")),
    ("shadow granted every gh command",
     lambda wd, w: _tool_step(wd)["with"].__setitem__(
         "default-allowed-tools",
         _tool_step(wd)["with"]["default-allowed-tools"] + ",Bash(gh:*)")),
    ("shadow granted a writing gh subcommand",
     lambda wd, w: _tool_step(wd)["with"].__setitem__(
         "default-allowed-tools",
         _tool_step(wd)["with"]["default-allowed-tools"]
         + ",Bash(gh issue comment:*)")),
    ("adopter extra tools reach the shadow",
     lambda wd, w: _tool_step(wd)["with"].__setitem__(
         "extra-allowed-tools", "${{ inputs.extra-allowed-tools }}")),
    ("shadow reads a vars.* switch",
     lambda wd, w: _family(wd)[0].__setitem__(
         "if", _family(wd)[0]["if"]
         + " && vars.WING_COMMANDER_DIAGNOSE_SHADOW_SINCE != ''")),
    ("shadow family moved before the findings upload",
     lambda wd, w: _move_family_before_upload(wd)),
    ("an unnamed step hides inside the shadow family",
     lambda wd, w: _unnamed_step_in_family(wd)),
    ("an acting report step reads the shadow's outcome",
     lambda wd, w: _acting_reads_shadow(wd)),
    ("a diagnose job output reads the shadow",
     lambda wd, w: _job(wd)["outputs"].__setitem__(
         "shadow", "${{ steps.diagnose-shadow.outcome }}")),
    ("wrapper hard-codes the shadow on",
     lambda wd, w: w["jobs"]["watchdog"]["with"].__setitem__(
         "diagnose-shadow-enabled", True)),
]


def self_test(watchdog, wrapper):
    bad = 0
    base = check(watchdog, wrapper)
    if base:
        print("self-test: the shipped tree must pass first:")
        for f in base:
            print(f"  - {f}")
        return 1
    for name, mutate in MUTATIONS:
        wd, w = copy.deepcopy(watchdog), copy.deepcopy(wrapper)
        mutate(wd, w)
        got = check(wd, w)
        if got:
            print(f"[ok] caught: {name} ({got[0][:90]})")
        else:
            bad += 1
            print(f"[FAIL] not caught: {name}")
    print(f"Gate 146 self-test: {len(MUTATIONS)} mutation(s), {bad} missed")
    return 1 if bad else 0


def main(argv):
    watchdog, wrapper = load(WATCHDOG), load(WRAPPER)
    if "--self-test" in argv:
        return self_test(watchdog, wrapper)
    failures = check(watchdog, wrapper)
    for f in failures:
        print(f"::error::Gate 146: {f}")
    if failures:
        return 1
    print("Gate 146: the diagnose shadow acts on nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
