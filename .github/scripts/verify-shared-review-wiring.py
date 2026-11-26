#!/usr/bin/env python3
"""Gate: the shared reviewer is wired as specified (specs/127-shared-pr-reviewer,
FR-003, FR-005, FR-024, FR-026, FR-027, FR-028).

  * `record` is the only job that posts or mints a write token;
  * every downstream job depends on `prepare` (which depends on `guard`);
  * both agents carry explicit models and turn budgets from inputs;
  * the wrapper has the per-PR concurrency group (no cancel) and the kill
    switch is passed through;
  * nothing else in the repository reads the shared verdict (report-only use).

`--self-test` proves each check fails on a mutated workflow.
"""
import copy
import glob
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_shared_review  # noqa: E402

# Round 6: the named check twice (with and without the fix) and the gate
# suite, each at its own limit, must all fit in code-run's step timeout.
CODE_RUN_BUDGET_SECONDS = 2 * wc_shared_review.CODE_RUN_TIMEOUT + wc_shared_review.GATE_SUITE_TIMEOUT

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CALLABLE = os.path.join(ROOT, ".github", "workflows", "shared-pr-reviewer.yml")
WRAPPER = os.path.join(ROOT, ".github", "workflows", "wing-commander-shared-pr-reviewer.yml")
OWN = {"shared-pr-reviewer.yml", "wing-commander-shared-pr-reviewer.yml"}


def callable_problems(wf):
    problems = []
    jobs = wf.get("jobs") or {}
    for name in ("guard", "prepare", "code-run", "find", "check", "record"):
        if name not in jobs:
            problems.append("missing job " + name)
    if problems:
        return problems
    for name, job in jobs.items():
        text = yaml.safe_dump(job)
        if name != "record" and ("issues: write" in text or "permission-issues: write" in text
                                 or "pull-requests: write" in text or "-X POST" in text):
            problems.append("{0} writes or posts; only record may".format(name))
        if name not in ("prepare", "record") and "create-github-app-token" in text:
            problems.append("{0} mints an App token".format(name))
    # A mint with no permission-* input gets the installation's whole grant,
    # and write-all (or a widened scope) on guard, prepare or record is the
    # same hole; find, check and code-run are pinned by
    # verify-shared-review-isolation.py.
    for name, job in jobs.items():
        for s in job.get("steps") or []:
            if "create-github-app-token" in str(s.get("uses", "")) and not any(
                    str(k).startswith("permission-") for k in (s.get("with") or {})):
                problems.append("{0}'s App token mint has no permission-* input, so it gets the "
                                "installation's whole grant".format(name))
    for name, want in (("guard", {}), ("prepare", {"contents": "read", "actions": "read"}),
                       ("record", {"contents": "read"})):
        if jobs[name].get("permissions") != want:
            problems.append("{0}'s job permissions are not pinned to {1}".format(name, want))
    if "record" not in jobs or "-X POST" not in yaml.safe_dump(jobs["record"]):
        problems.append("record no longer posts the comment")
    # The record is a comment on a pull request: GitHub refuses it from an
    # App token without pull-requests: write (HTTP 403, T044 run 45628429265).
    mints = [s for s in (jobs["record"].get("steps") or [])
             if "create-github-app-token" in str(s.get("uses", ""))]
    if not any((s.get("with") or {}).get("permission-pull-requests") == "write" for s in mints):
        problems.append("record's App token lacks pull-requests: write, so its PR comment is refused")
    # That scope can also approve, request changes, retitle or close the PR
    # (FR-023 forbids each), so the token is held to issues and pull
    # requests (no contents: no merge, no push), to this repository (no
    # owner or repositories input) and to the one comment call. Only those
    # inputs are checked: the action's other inputs may change with its
    # versions.
    for s in mints:
        extra = sorted(k for k in (s.get("with") or {})
                       if k in ("owner", "repositories") or (k.startswith("permission-") and k not in (
                           "permission-issues", "permission-pull-requests")))
        if extra:
            problems.append("record's App token asks for more than issues and pull requests "
                            "on this repository: " + ", ".join(extra))
    record_text = yaml.safe_dump(jobs["record"])
    if len(mints) != 1 or record_text.count("secrets.app-private-key") != 1:
        problems.append("record mints its App token more than once")
    token = "steps.{0}.outputs.token".format((mints[0].get("id") if mints else None) or "app")
    users = [s for s in (jobs["record"].get("steps") or []) if token in yaml.safe_dump(s)]
    if record_text.count(token) != 1 or len(users) != 1:
        problems.append("record's write token reaches more than the one comment step")
    else:
        # Every gh call in the step is the one comment call; flags, a retry
        # loop, messages and other shell lines around it are free.
        run = str(users[0].get("run") or "").replace("\\\n", " ")
        gh = [ln.strip() for ln in run.splitlines() if re.search(r"\bgh\b", ln)
              and not re.match(r"\s*(#|echo\b|printf\b)", ln)]
        comment = r'\bgh api\b.*\brepos/\$\{?REPO\}?/issues/\$\{?PR\}?/comments(?!/)'
        if not all(re.search(comment, ln) for ln in gh):
            problems.append("record's write token does more than post the one PR comment: "
                            + " | ".join(gh))
        # The command's path comes from its env and its program from the
        # shell, so those are pinned too: the PR and repository the round was
        # asked about. Other env entries are free, and no shell: is bash on
        # record's runner.
        env = {k: str(v).replace(" ", "") for k, v in (users[0].get("env") or {}).items()}
        want = {"GH_TOKEN": "${{" + token + "}}", "PR": "${{inputs.pr}}",
                "REPO": "${{github.repository}}"}
        if any(env.get(k) != v for k, v in want.items()) or users[0].get("shell", "bash") != "bash":
            problems.append("record's comment step takes its token, target or shell from somewhere "
                            "else: env {0}, shell {1}".format(
                                {k: env.get(k) for k in want}, users[0].get("shell")))
    for name in ("find", "check", "code-run", "record"):
        needs = jobs[name].get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        if "prepare" not in needs:
            problems.append("{0} does not depend on prepare".format(name))
    if "guard" not in ([jobs["prepare"].get("needs")] if isinstance(jobs["prepare"].get("needs"), str)
                       else jobs["prepare"].get("needs") or []):
        problems.append("prepare does not depend on guard")
    if "needs.guard.outputs.proceed" not in str(jobs["prepare"].get("if", "")):
        problems.append("prepare is not gated on guard's output")
    for name, model, turns in (("find", "find-model", "find-max-turns"),
                               ("check", "check-model", "check-max-turns")):
        text = yaml.safe_dump(jobs[name])
        if "inputs." + model not in text or "inputs." + turns not in text:
            problems.append("{0} lacks an explicit model or turn budget input".format(name))
    return problems


def diff_read_problems(wf):
    """R3-F5: the PR's diff, added files and commits are read with no
    `|| true` to swallow a failure, and an empty diff stops the round."""
    problems = []
    steps = ((wf.get("jobs") or {}).get("prepare") or {}).get("steps") or []
    runs = [str((s or {}).get("run") or "") for s in steps]
    reader = [r for r in runs if "pr.diff" in r]
    if not reader:
        return ["prepare no longer writes the PR's diff"]
    for line in reader[0].splitlines():
        if re.search(r"\bgit (diff|log)\b", line) and re.search(r"\|\|\s*(true|:)\b", line):
            problems.append("prepare swallows a failed git read: " + line.strip())
    if not re.search(r"\[ -s [^\]]*pr\.diff \]", reader[0]):
        problems.append("prepare does not stop the round on an empty diff")
    return problems


def head_fetch_problems(wf):
    """R3-F10: the PR-head fetch is authenticated with prepare's read-only
    App token, passed only through git's environment config (never argv,
    never persisted), and the token never leaves prepare."""
    problems = []
    jobs = wf.get("jobs") or {}
    steps = (jobs.get("prepare") or {}).get("steps") or []
    fetch = next((s for s in steps if "refs/pull/" in str((s or {}).get("run") or "")), None)
    if fetch is None:
        return ["prepare no longer fetches the PR head"]
    run = str(fetch.get("run"))
    if str((fetch.get("env") or {}).get("GH_TOKEN", "")).replace(" ", "") != "${{steps.app.outputs.token}}":
        problems.append("the PR-head fetch does not get prepare's read-only App token")
    if "GIT_CONFIG_VALUE_0=\"AUTHORIZATION: basic" not in run or ".extraheader" not in run:
        problems.append("the PR-head fetch is not authenticated through git's environment config")
    if re.search(r"git\s+config\b|git\s+-c\b|remote set-url|x-access-token:\$\{?GH_TOKEN\}?@", run):
        problems.append("the PR-head fetch puts the token in argv, the remote URL or .git/config")
    if "steps.app.outputs.token" in yaml.safe_dump((jobs.get("prepare") or {}).get("outputs") or {}):
        problems.append("prepare exposes its App token as a job output")
    return problems


def _true(value):
    return value is True or str(value).lower() == "true"


TOLERATED_JOBS = ("code-run", "find", "check")


def tolerated_job_problems(wf):
    """A5/P2: a failure no step handles in code-run, find or check (a
    checkout or download, a timeout, PR code crashing the job) must leave a
    successful run, so record's incomplete round is confirmed. And since a
    tolerated job's result reads `success` whatever failed, no condition
    may read those jobs' results; their outputs carry the signal."""
    problems = []
    jobs = wf.get("jobs") or {}
    for name in TOLERATED_JOBS:
        if not _true((jobs.get(name) or {}).get("continue-on-error")):
            problems.append("{0} can fail the run (no job-level continue-on-error)".format(name))
    text = yaml.safe_dump(jobs)
    for name in TOLERATED_JOBS:
        if re.search(r"needs\.{0}\.result".format(re.escape(name)), text):
            problems.append("a condition reads needs.{0}.result, which a tolerated job always "
                            "reports as success".format(name))
    # A job timeout cancels rather than fails, so each long step has its
    # own timeout under the job's: code-run's run step and both agents.
    for name, pick in (("code-run", lambda x: " code-run " in " " + " ".join(str(x.get("run") or "").split()) + " "),
                       ("find", lambda x: x.get("id") == "agent"), ("check", lambda x: x.get("id") == "agent")):
        job = jobs.get(name) or {}
        step = next((x for x in job.get("steps") or [] if pick(x or {})), {})
        try:
            ok = int(step.get("timeout-minutes")) < int(job.get("timeout-minutes"))
        except (TypeError, ValueError):
            ok = False
        if not ok:
            problems.append("{0}'s long step has no timeout under the job's".format(name))
        elif name == "code-run" and int(step["timeout-minutes"]) * 60 < CODE_RUN_BUDGET_SECONDS:
            problems.append("code-run's step timeout ({0} min) is under its commands' limits ({1} s), so "
                            "a slow gate suite ends as missing".format(step["timeout-minutes"],
                                                                         CODE_RUN_BUDGET_SECONDS))
    return problems


AGENT_TREES = "${{ runner.temp }}/shared-review-trees"
PROMPTS = (os.path.join(ROOT, ".github", "prompts", "shared-review-find.md"),
           os.path.join(ROOT, ".github", "prompts", "shared-review-check.md"))


def agent_tree_problems(wf, prompt_texts=None):
    """P1 (FR-027): the PR tree can supply neither agent's instructions or
    settings. Each agent job downloads the trees outside its working
    directory, renames everything loadable before any agent setup, and
    reaches them only through --add-dir; nothing opts --add-dir into
    loading CLAUDE.md; the prompt files name no tree inside the workspace."""
    problems = []
    jobs = wf.get("jobs") or {}
    if "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD" in yaml.safe_dump(wf):
        problems.append("the callable opts --add-dir into loading CLAUDE.md")
    for role in ("find", "check"):
        steps = [x or {} for x in (jobs.get(role) or {}).get("steps") or []]
        names = [x.get("name") or "" for x in steps]
        dl = next((i for i, x in enumerate(steps)
                   if (x.get("with") or {}).get("name") == "shared-review-trees"), None)
        if dl is None or str(steps[dl]["with"].get("path")) != AGENT_TREES:
            problems.append("{0} does not download the trees to {1}".format(role, AGENT_TREES))
            continue
        defuse = next((i for i, x in enumerate(steps) if "defuse-agent-config" in str(x.get("run") or "")), None)
        agent = next((i for i, x in enumerate(steps) if x.get("id") == "agent"), None)
        setup = next((i for i, n in enumerate(names) if n.startswith("Compose tool args")), agent)
        if defuse is None or not dl < defuse < (setup if setup is not None else 10 ** 6):
            problems.append("{0} does not defuse the trees after downloading them and before the "
                            "agent's setup".format(role))
        elif _true(steps[defuse].get("continue-on-error")) or str((steps[defuse].get("env") or {})
                                                                    .get("TREES")) != AGENT_TREES:
            problems.append("{0}'s defuse step does not fail closed on {1}".format(role, AGENT_TREES))
        args = str(((steps[agent] if agent is not None else {}).get("with") or {}).get("claude_args", ""))
        if "--add-dir " + AGENT_TREES not in args:
            problems.append("{0}'s agent does not reach the trees through --add-dir".format(role))
        prompt = str(((steps[agent] if agent is not None else {}).get("with") or {}).get("prompt", ""))
        if AGENT_TREES + "/pr-tree/" not in " ".join(prompt.split()):
            problems.append("{0}'s task prompt does not name the PR tree at {1}".format(role, AGENT_TREES))
    texts = prompt_texts if prompt_texts is not None else [open(x, encoding="utf-8").read() for x in PROMPTS]
    for text in texts:
        if "trees/pr-tree/" in text:
            problems.append("a prompt file names the PR tree inside the working directory")
    return problems


def release_problems(wf):
    """R2: prepare's `proceed` is set by its last step, after every upload,
    gated on success only, so a failed upload releases no round (a record
    posted from a failed run is never confirmed)."""
    job = (wf.get("jobs") or {}).get("prepare") or {}
    steps = [x or {} for x in job.get("steps") or []]
    m = re.search(r"steps\.([A-Za-z0-9_-]+)\.outputs\.proceed", str((job.get("outputs") or {}).get("proceed", "")))
    idx = next((i for i, x in enumerate(steps) if m and x.get("id") == m.group(1)), None)
    uploads = [i for i, x in enumerate(steps) if "upload-artifact" in str(x.get("uses") or "")]
    if idx is None or not uploads or idx < max(uploads):
        return ["prepare releases the round (proceed) before its uploads have landed"]
    cond = str(steps[idx].get("if") or "")
    if re.search(r"always\(\)|!cancelled\(\)|failure\(\)", cond) or _true(steps[idx].get("continue-on-error")):
        return ["prepare's release step runs even when an upload failed"]
    return []


def failure_path_problems(wf):
    """R3-F1, R3-F3 and the round-2 lines: an agent job's failure degrades
    to a missing output and never fails the job, nothing an unhealthy agent
    wrote is staged, and check runs only on find's healthy, valid output.
    A failed job would turn the run red, and confirm_record never confirms
    the incomplete round of a run that did not succeed."""
    problems = []
    jobs = wf.get("jobs") or {}
    if "needs.find.outputs.ok == 'true'" not in str((jobs.get("check") or {}).get("if", "")):
        problems.append("check does not wait for find's staged output (needs.find.outputs.ok)")
    if "steps.upload.outcome" not in str(((jobs.get("find") or {}).get("outputs") or {}).get("ok", "")):
        problems.append("find's `ok` output is not its output upload's outcome")
    for role in ("find", "check"):
        job = jobs.get(role) or {}
        steps = [s or {} for s in job.get("steps") or []]
        agent = next((s for s in steps if s.get("id") == "agent"), {})
        try:
            if not int(agent.get("timeout-minutes")) < int(job.get("timeout-minutes")):
                raise ValueError
        except (TypeError, ValueError):
            problems.append("{0}'s agent step has no step timeout under the job's".format(role))
        for s in steps:
            sid = s.get("id")
            if (sid == role + "-verdict" or "claude-execution-output" in str((s.get("with") or {}).get("name"))) \
                    and not _true(s.get("continue-on-error")):
                problems.append("{0}: step {1!r} can fail the job".format(role, s.get("name")))
        stage = next((s for s in steps if "validate-output" in str(s.get("run") or "")), None)
        if stage is None:
            problems.append("{0} no longer validates its output".format(role))
        else:
            if "steps.{0}-verdict.outputs.verdict == 'healthy'".format(role) not in str(stage.get("if", "")):
                problems.append("{0} stages output from an agent whose verdict is not healthy".format(role))
            if not _true(stage.get("continue-on-error")):
                problems.append("{0}: the stage step can fail the job".format(role))
            # Every candidate needs a check entry (FR-010), so check's
            # validation reads the find output it was given.
            if role == "check" and "--find input/find.json" not in str(stage.get("run") or ""):
                problems.append("check validates its output without the find output's candidates")
        upload = next((s for s in steps if (s.get("with") or {}).get("name") == "shared-review-" + role), None)
        if upload is None or "steps.stage.outputs.ok == 'true'" not in str(upload.get("if", "")) \
                or not _true(upload.get("continue-on-error")):
            problems.append("{0} uploads an output that was not staged as valid, or can fail on it".format(role))
    return problems


CONFIRMATION_RETENTION_DAYS = 90  # GitHub's maximum


def retention_problems(wf):
    """Round 4: a record counts only while its run still lists the
    shared-review-<head> artifact, so that artifact is kept as long as
    GitHub allows."""
    steps = ((wf.get("jobs") or {}).get("record") or {}).get("steps") or []
    for s in steps:
        name = str(((s or {}).get("with") or {}).get("name") or "")
        if name.startswith("shared-review-") and "head-sha" in name:
            if str(s["with"].get("retention-days")) != str(CONFIRMATION_RETENTION_DAYS):
                return ["the confirmation artifact is kept {0} days, not {1}".format(
                    s["with"].get("retention-days"), CONFIRMATION_RETENTION_DAYS)]
            return []
    return ["record no longer uploads the confirmation artifact"]


def queued_dispatch_note_problems(wrapper_text):
    """Round 4: GitHub keeps one pending run per concurrency group, so the
    wrapper must say that a third dispatch cancels a queued second one."""
    prose = " ".join(re.sub(r"\n\s*#", " ", wrapper_text).split())
    if "third dispatch cancels a queued second one" not in prose:
        return ["the wrapper no longer warns that a third dispatch cancels a queued one"]
    return []


def wrapper_problems(wf):
    problems = []
    conc = wf.get("concurrency") or {}
    if "shared-pr-reviewer-" not in str(conc.get("group", "")) or conc.get("cancel-in-progress") is not False:
        problems.append("the wrapper lacks the per-PR concurrency group with cancel-in-progress: false")
    if "WING_COMMANDER_SHARED_REVIEWER_PAUSED" not in yaml.safe_dump(wf):
        problems.append("the wrapper does not pass the kill switch")
    return problems


def readers_problems(root=ROOT):
    """No existing workflow or skill reads the shared verdict (FR-005, FR-028)."""
    problems = []
    needles = ("wing-commander-shared-review-round", "wc_shared_review", "shared-review-")
    paths = glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml"))
    paths += glob.glob(os.path.join(root, ".claude", "skills", "**", "*.md"), recursive=True)
    for path in sorted(paths):
        if os.path.basename(path) in OWN:
            continue
        if os.path.basename(path) == "lint-workflows.yml":
            continue  # the gate registry names the gates, it reads no verdict
        text = open(path, encoding="utf-8", errors="replace").read()
        if any(n in text for n in needles):
            problems.append("{0} reads the shared reviewer's output".format(os.path.relpath(path, root)))
    return problems


def _prepare_diff_step(wf):
    return next(s for s in wf["jobs"]["prepare"]["steps"] if "pr.diff" in str(s.get("run") or ""))


def _swallow_diff(wf):
    step = _prepare_diff_step(wf)
    step["run"] = step["run"].replace("> ../input/pr.diff", "> ../input/pr.diff || true", 1)


def _drop_empty_diff_stop(wf):
    step = _prepare_diff_step(wf)
    step["run"] = "\n".join(l for l in step["run"].splitlines() if "[ -s " not in l)


def _step(wf, job, pred):
    return next(s for s in wf["jobs"][job]["steps"] if pred(s))


def _check_on_find_result(wf):
    wf["jobs"]["check"]["if"] = "!cancelled() && needs.find.result == 'success'"


def _stage_unhealthy_find(wf):
    _step(wf, "find", lambda s: "validate-output" in str(s.get("run")))["if"] = \
        "!cancelled() && steps.agent.outcome == 'success'"


def _upload_unstaged_check(wf):
    _step(wf, "check", lambda s: (s.get("with") or {}).get("name") == "shared-review-check")["if"] = \
        "!cancelled() && steps.agent.outcome == 'success'"


def _agent_without_step_timeout(wf):
    _step(wf, "find", lambda s: s.get("id") == "agent").pop("timeout-minutes", None)


def _verdict_can_fail(wf):
    _step(wf, "check", lambda s: s.get("id") == "check-verdict").pop("continue-on-error", None)


def dismissals_guard_problems(wf):
    """Round 6: the dismissals input reaches the guard, which refuses one
    that is not JSON or not a list of {id, reason}, before the round runs.
    The guard reads the value from the environment (--dismissals-env
    DISMISSALS), never argv: as an argument, a value starting with "-" (a
    typo such as -x) is read by argparse as an option, so the step fails
    instead of refusing in the summary (pass 2 of #1219's review)."""
    step = next((s for s in ((wf.get("jobs") or {}).get("prepare") or {}).get("steps") or []
                 if " guard " in str(s.get("run") or "")), {})
    run = str(step.get("run") or "")
    if (step.get("env") or {}).get("DISMISSALS") != "${{ inputs.dismissals }}" \
            or "--dismissals-env DISMISSALS" not in run or "$DISMISSALS" in run:
        return ["prepare's guard does not read the dismissals input from the environment "
                "(--dismissals-env DISMISSALS)"]
    return []


def _record_mint(wf):
    return _step(wf, "record", lambda s: "create-github-app-token" in str(s.get("uses", "")))


def _record_post_step(wf):
    return _step(wf, "record", lambda s: "steps.app.outputs.token" in yaml.safe_dump(s))


def _head_fetch_step(wf):
    return _step(wf, "prepare", lambda s: "refs/pull/" in str(s.get("run") or ""))


def _unauthenticated_fetch(wf):
    step = _head_fetch_step(wf)
    step["env"].pop("GH_TOKEN", None)
    step["run"] = "cd reviewer\ngit fetch --no-tags origin \"refs/pull/${PR}/head\"\n"


def _persisted_fetch_token(wf):
    step = _head_fetch_step(wf)
    step["run"] = ("git config --local http.https://github.com/.extraheader \"AUTHORIZATION: basic x\"\n"
                   + step["run"])


def main():
    cal = yaml.safe_load(open(CALLABLE, encoding="utf-8")) or {}
    wrap = yaml.safe_load(open(WRAPPER, encoding="utf-8")) or {}
    problems = (callable_problems(cal) + diff_read_problems(cal) + failure_path_problems(cal)
                + head_fetch_problems(cal) + retention_problems(cal) + tolerated_job_problems(cal)
                + agent_tree_problems(cal) + dismissals_guard_problems(cal)
                + release_problems(cal)
                + queued_dispatch_note_problems(open(WRAPPER, encoding="utf-8").read())
                + wrapper_problems(wrap) + readers_problems())
    if "--self-test" in sys.argv:
        bad = 0
        muts = {
            "find posts": lambda c: c["jobs"]["find"].update({"permissions": {"issues": "write"}}),
            "check loses its model": lambda c: c["jobs"]["check"]["steps"].clear(),
            "prepare loses the guard": lambda c: c["jobs"]["prepare"].update({"needs": []}),
            "record's token cannot comment on a pull request": lambda c: next(
                s for s in c["jobs"]["record"]["steps"]
                if "create-github-app-token" in str(s.get("uses", "")))["with"].update(
                {"permission-pull-requests": "read"}),
            "find gets pull-requests: write": lambda c: c["jobs"]["find"].update(
                {"permissions": {"pull-requests": "write"}}),
            "record's token asks for contents: write": lambda c: next(
                s for s in c["jobs"]["record"]["steps"]
                if "create-github-app-token" in str(s.get("uses", "")))["with"].update(
                {"permission-contents": "write"}),
            "record approves the pull request": lambda c: _record_post_step(c).update(
                {"run": _record_post_step(c)["run"] + 'gh pr review "$PR" --approve\n'}),
            "record mints a second write token": lambda c: c["jobs"]["record"]["steps"].insert(
                -1, dict(copy.deepcopy(next(s for s in c["jobs"]["record"]["steps"]
                                            if "create-github-app-token" in str(s.get("uses", "")))),
                         id="app2")),
            "record's token reaches the build step": lambda c: next(
                s for s in c["jobs"]["record"]["steps"] if s.get("id") == "build")["env"].update(
                {"GH_TOKEN": "${{ steps.app.outputs.token }}"}),
            "record's one command reviews the pull request": lambda c: _record_post_step(c).update(
                {"run": 'set -euo pipefail\n'
                        'gh api -X POST "repos/${REPO}/pulls/${PR}/reviews" -f event=APPROVE\n'}),
            "a record step reads the App private key": lambda c: c["jobs"]["record"]["steps"].append(
                {"name": "x", "env": {"KEY": "${{ secrets.app-private-key }}"}, "run": "true\n"}),
            "record's token reaches another owner": lambda c: next(
                s for s in c["jobs"]["record"]["steps"]
                if "create-github-app-token" in str(s.get("uses", "")))["with"].update(
                {"owner": "${{ github.repository_owner }}"}),
            "record's comment goes to another pull request": lambda c: _record_post_step(c)["env"].update(
                {"PR": "${{ needs.prepare.outputs.spent }}"}),
            "record's comment step runs another shell": lambda c: _record_post_step(c).update(
                {"shell": "python {0}"}),
            "prepare's mint drops all its permission inputs": lambda c: [
                s["with"].pop(k) for s in c["jobs"]["prepare"]["steps"]
                if "create-github-app-token" in str(s.get("uses", ""))
                for k in [k for k in s["with"] if k.startswith("permission-")]],
            "record's mint drops all its permission inputs": lambda c: [
                _record_mint(c)["with"].pop(k) for k in list(_record_mint(c)["with"])
                if k.startswith("permission-")],
            "guard gets write-all": lambda c: c["jobs"]["guard"].update({"permissions": "write-all"}),
            "prepare gets write-all": lambda c: c["jobs"]["prepare"].update({"permissions": "write-all"}),
            "record gets write-all": lambda c: c["jobs"]["record"].update({"permissions": "write-all"}),
        }
        for label, mutate in muts.items():
            clone = copy.deepcopy(cal)
            mutate(clone)
            if not callable_problems(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        # Ordinary edits to record's mint and post that must stay legal.
        legal = {
            "the post logs the comment URL with --jq": lambda c: _record_post_step(c).update(
                {"run": 'set -euo pipefail\n'
                        'gh api -X POST "repos/${REPO}/issues/${PR}/comments" -F body=@record.md --jq .html_url\n'}),
            "the post retries": lambda c: _record_post_step(c).update(
                {"run": 'set -euo pipefail\n# Retry a transient 5xx from gh.\nfor i in 1 2 3; do\n'
                        '  gh api -X POST "repos/$REPO/issues/$PR/comments" -F body=@record.md > /dev/null 2>&1 && break\n'
                        '  echo "::warning::gh failed, retrying"\n  sleep 10\ndone\n'}),
            "the post is split over lines": lambda c: _record_post_step(c).update(
                {"run": 'gh api -X POST \\\n  repos/${REPO}/issues/${PR}/comments \\\n  -F body=@record.md\n'}),
            "the post step drops shell: bash": lambda c: _record_post_step(c).pop("shell"),
            "the post step gets another env entry": lambda c: _record_post_step(c)["env"].update(
                {"GH_PROMPT_DISABLED": "1"}),
            "the post step is renamed": lambda c: _record_post_step(c).update({"name": "Post the round"}),
            "the mint gets a new action input": lambda c: _record_mint(c)["with"].update(
                {"skip-token-revoke": "false"}),
            "the mint drops issues: write": lambda c: _record_mint(c)["with"].pop("permission-issues"),
        }
        for label, edit in legal.items():
            clone = copy.deepcopy(cal)
            edit(clone)
            found = callable_problems(clone)
            if found:
                print("::error::self-test: legal edit refused: {0}: {1}".format(label, found))
                bad += 1
        for label, mutate, check in (
                ("a git read swallowed with || true", _swallow_diff, diff_read_problems),
                ("the empty-diff stop removed", _drop_empty_diff_stop, diff_read_problems),
                ("check runs on find's job result", _check_on_find_result, failure_path_problems),
                ("find stages an unhealthy agent's output", _stage_unhealthy_find, failure_path_problems),
                ("check uploads an unstaged output", _upload_unstaged_check, failure_path_problems),
                ("the find agent has no step timeout", _agent_without_step_timeout, failure_path_problems),
                ("the check verdict step can fail the job", _verdict_can_fail, failure_path_problems),
                ("check validates without the find output", lambda w: _step(
                    w, "check", lambda x: "validate-output" in str(x.get("run") or "")).update(
                    {"run": _step(w, "check", lambda x: "validate-output" in str(x.get("run") or ""))["run"]
                     .replace("--find input/find.json ", "")}), failure_path_problems),
                ("prepare releases the round before its uploads", lambda w: w["jobs"]["prepare"]["outputs"]
                    .update({"proceed": "${{ steps.state.outputs.ready }}"}), release_problems),
                ("the release step runs after a failed upload", lambda w: _step(
                    w, "prepare", lambda x: x.get("id") == "release").update(
                    {"if": "!cancelled() && steps.state.outputs.ready == 'true'"}), release_problems),
                ("code-run can fail the run", lambda w: w["jobs"]["code-run"].pop("continue-on-error"),
                 tolerated_job_problems),
                ("find can fail the run", lambda w: w["jobs"]["find"].pop("continue-on-error"),
                 tolerated_job_problems),
                ("code-run's step timeout is back to 36 minutes", lambda w: _step(
                    w, "code-run", lambda x: "--out out/code-run.json" in str(x.get("run") or ""))
                    .update({"timeout-minutes": 36}), tolerated_job_problems),
                ("code-run's run step loses its timeout", lambda w: _step(
                    w, "code-run", lambda x: "--out out/code-run.json" in str(x.get("run") or ""))
                    .pop("timeout-minutes"), tolerated_job_problems),
                ("find unpacks the trees in its working directory", lambda w: _step(
                    w, "find", lambda x: (x.get("with") or {}).get("name") == "shared-review-trees")
                    ["with"].update({"path": "trees"}), agent_tree_problems),
                ("check stops defusing the trees", lambda w: w["jobs"]["check"]["steps"].remove(
                    _step(w, "check", lambda x: "defuse-agent-config" in str(x.get("run") or ""))),
                 agent_tree_problems),
                ("find's agent loses --add-dir", lambda w: _step(w, "find", lambda x: x.get("id") == "agent")
                    ["with"].update({"claude_args": "--model x"}), agent_tree_problems),
                ("--add-dir opted into CLAUDE.md", lambda w: w.update(
                    {"env": {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1"}}), agent_tree_problems),
                ("record reads a tolerated job's result", lambda w: w["jobs"]["record"].update(
                    {"if": "!cancelled() && needs.check.result == 'success'"}), tolerated_job_problems),
                ("the PR-head fetch loses its token", _unauthenticated_fetch, head_fetch_problems),
                ("the guard stops reading the dismissals", lambda w: next(
                    x for x in w["jobs"]["prepare"]["steps"] if " guard " in str(x.get("run") or ""))
                    ["env"].pop("DISMISSALS"), dismissals_guard_problems),
                ("the guard takes the dismissals as an argument", lambda w: next(
                    x for x in w["jobs"]["prepare"]["steps"] if " guard " in str(x.get("run") or "")).update(
                    {"run": next(x for x in w["jobs"]["prepare"]["steps"] if " guard " in str(x.get("run") or ""))
                     ["run"].replace("--dismissals-env DISMISSALS", '--dismissals "$DISMISSALS"')}),
                 dismissals_guard_problems),
                ("the PR-head fetch persists its token", _persisted_fetch_token, head_fetch_problems)):
            clone = copy.deepcopy(cal)
            mutate(clone)
            if not check(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        rclone = copy.deepcopy(cal)
        next(x for x in rclone["jobs"]["record"]["steps"]
             if "head-sha" in str((x.get("with") or {}).get("name")))["with"]["retention-days"] = 30
        if not retention_problems(rclone):
            print("::error::self-test: mutation not caught: confirmation artifact kept 30 days")
            bad += 1
        if not queued_dispatch_note_problems("# One round at a time per pull request.\n"):
            print("::error::self-test: mutation not caught: the queued-dispatch note removed")
            bad += 1
        wclone = copy.deepcopy(wrap)
        wclone["concurrency"] = {}
        if not wrapper_problems(wclone):
            print("::error::self-test: dropped concurrency not caught")
            bad += 1
        return 1 if bad or problems else 0
    for p in problems:
        print("::error::verify-shared-review-wiring: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
