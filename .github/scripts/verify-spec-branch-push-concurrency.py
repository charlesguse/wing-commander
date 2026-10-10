#!/usr/bin/env python3
"""Gate 80 - every job that pushes to a spec branch is in the per-spec group.

WHY THIS EXISTS
---------------
specs/013-serialize-rebase-stages put every stage that writes a
`spec/NNN-slug` branch into one concurrency group, `wing-commander-<spec-dir>`,
with `cancel-in-progress: false`, so GitHub runs one of them at a time per
specification. That is what stops the rebase stage's force-push from racing
a running implement cycle. The rule was written into the contract
(contracts/concurrency-groups.md: "Any future published stage that checks
out and publishes to a specification's working branch MUST declare ... in
this same form") and nothing enforced it.

`cleanup.yml`'s `mark-stalled` job rewrote `spec-meta.json` and pushed onto
the spec branch from a DIFFERENT group, keyed on the closed PR's head ref,
because spec 013's D5 assumed cleanup only runs after a spec's terminal
stage. Closing a plan or tasks PR mid-cycle is not terminal: the push was
unordered against a running implement or rebase on the same branch, and
either the marker or the cycle's push could lose (#397). A group name is
one line of YAML that reads correctly on its own; only a list of every
pusher, held against the rule, shows the one outside it.

WHAT IT CHECKS
--------------
For every job in `.github/workflows/*.yml` that can push, i.e. one that

  (a) runs `git push` in one of its own `run:` steps (comment lines and
      print-only `echo`/`printf` lines stripped first, so a runbook that
      prints the command for a human is not a pusher; a print line that
      continues into another command with `&&`, `;` or `|` is kept),
  (b) grants its agent `Bash(git push:*)` through `wing-commander-tool-args`
      (the agent stages push through the agent, not a `run:` step), or
  (c) calls a local composite whose own `run:` steps push -- directly, or
      through a `_shared/<script>.sh` they run that pushes (spec 095's
      wing-commander-hardened-push keeps its `git push` in
      `_shared/hardened-push.sh`),

the job's `concurrency.group` must be the per-spec group in one of the three
shipped spellings:

    wing-commander-${{ inputs.spec-dir }}
    wing-commander-${{ needs.<job>.outputs.spec-dir }}
    wing-commander-${{ matrix.spec_dir }}

or the (file, job) pair must be waived in
`.github/scripts/spec-branch-push-waivers.json`, with `pushes` (what it
pushes) and `reason`. A waiver is stale-checked: one naming a job that no
longer exists, or no longer pushes, fails the gate, so a waiver cannot
outlive its reason.

WHAT IT DOES NOT CHECK
----------------------
Where a push goes. A `git push` target is a runtime string; this gate
holds every pusher to the group or to a written reason, and the reason is
where "not a spec branch" is stated and reviewed.

SELF-TEST
---------
`--self-test` builds a synthetic tree - a job pushing from a `run:` step,
one pushing through an agent grant, one pushing through a composite, each
in and out of the group, plus waivers that match, are stale, or are
malformed - and asserts each verdict, including the file and job named.

Usage:
    python3 .github/scripts/verify-spec-branch-push-concurrency.py
    python3 .github/scripts/verify-spec-branch-push-concurrency.py --self-test
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

WORKFLOW_DIR = ".github/workflows"
ACTIONS_DIR = ".github/actions"
WAIVERS_PATH = ".github/scripts/spec-branch-push-waivers.json"
TOOL_ARGS_COMPOSITE = "wing-commander-tool-args"

PUSH_RE = re.compile(r"(?<![\w-])git\s+push\b")
PUSH_GRANT_RE = re.compile(r"(?:^|,)\s*Bash\(git push:\*\)\s*(?:,|$)")
# The three spellings the shipped stages use (specs/013 contract). The
# group must be EXACTLY one of these: a prefix match would admit
# `wing-commander-${{ inputs.spec-dir }}-something`, a different group.
PER_SPEC_GROUP_RE = re.compile(
    r"^wing-commander-\$\{\{\s*"
    r"(?:inputs\.spec-dir|needs\.[\w-]+\.outputs\.spec-dir|matrix\.spec_dir)"
    r"\s*\}\}$")
# The per-PR fallback pr-conversation.yml's stalled-mark job declares when
# needs.resolve-identity.outputs.spec-dir is empty (specs/077, T023's split
# of the original stalled job). Distinct
# from PER_SPEC_GROUP_RE: this is not a per-spec group at all, and its
# literal "pr-conversation-pr-{0}" / "inputs.pr-number" text is specific
# to this one job, not a general fourth per-spec spelling other stages
# could adopt.
PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE = re.compile(
    r"^wing-commander-\$\{\{\s*needs\.([\w-]+)\.outputs\.spec-dir\s*\}\}"
    r"\$\{\{\s*needs\.\1\.outputs\.spec-dir\s*==\s*''\s*&&\s*"
    r"format\('pr-conversation-pr-\{0\}',\s*inputs\.pr-number\)\s*\|\|\s*''\s*\}\}$"
)
LOCAL_COMPOSITE_RE = re.compile(r"(?:^|/)\.github/actions/([\w-]+)/?$")
COMMENT_LINE_RE = re.compile(r"^\s*#")
PRINT_LINE_RE = re.compile(r"^\s*(?:echo|printf)\b")
# A print line that continues into another command (`echo x && git push`,
# `echo x; git push`, `printf x | git push`) is not noise: the push runs.
CONTINUES_RE = re.compile(r"&&|\|\||;|\|")


def _rel(path):
    return path.replace(os.sep, "/")


def _is_noise(line):
    if COMMENT_LINE_RE.match(line):
        return True
    return bool(PRINT_LINE_RE.match(line)) and not CONTINUES_RE.search(line)


def _run_text(step):
    """A step's `run:` with comment lines and print-only lines dropped."""
    run = (step or {}).get("run")
    if not isinstance(run, str):
        return ""
    return "\n".join(line for line in run.splitlines() if not _is_noise(line))


def _composite_name(uses):
    m = LOCAL_COMPOSITE_RE.search(str(uses or "").strip())
    return m.group(1) if m else None


SHARED_SCRIPT_RE = re.compile(r"_shared/([\w.-]+\.sh)\b")
# A shared script's push may carry git's own options first
# (`git --git-dir="$shim/.git" push`, hardened-push.sh).
SHARED_PUSH_RE = re.compile(r"(?<![\w-])git\s+(?:-\S+\s+)*push\b")


def _shared_pushes(root, text):
    """True when `text` runs a `_shared/<script>.sh` whose own lines push."""
    for name in SHARED_SCRIPT_RE.findall(text):
        path = os.path.join(root, ACTIONS_DIR, "_shared", name)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8") as fh:
            body = "\n".join(line for line in fh.read().splitlines() if not _is_noise(line))
        # wc_push_from_shim (git-push-hardening.sh) is a push by name.
        if SHARED_PUSH_RE.search(body) or "wc_push_from_shim" in body:
            return True
    return False


def pushing_composites(root="."):
    """-> {composite-name} whose action.yml runs `git push` itself, or runs
    a _shared script that does."""
    out = set()
    for path in sorted(glob.glob(os.path.join(root, ACTIONS_DIR, "*", "action.yml"))):
        with io.open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        steps = ((doc.get("runs") or {}).get("steps")) or []
        texts = [_run_text(s) for s in steps if isinstance(s, dict)]
        if any(PUSH_RE.search(t) or "wc_push_from_shim" in t or _shared_pushes(root, t)
               for t in texts):
            out.add(os.path.basename(os.path.dirname(path)))
    return out


def push_reasons(job, composites):
    """-> ["run step 'X'", "agent grant on 'Y'", "composite Z via 'W'"]."""
    reasons = []
    for step in (job or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = step.get("name") or step.get("id") or "<unnamed step>"
        if PUSH_RE.search(_run_text(step)):
            reasons.append("run step {0!r}".format(name))
        uses = str(step.get("uses") or "")
        with_ = step.get("with") or {}
        if TOOL_ARGS_COMPOSITE in uses and PUSH_GRANT_RE.search(
                str(with_.get("default-allowed-tools", ""))):
            reasons.append("agent grant Bash(git push:*) on {0!r}".format(name))
        comp = _composite_name(uses)
        if comp and comp in composites:
            reasons.append("composite {0} via {1!r}".format(comp, name))
    return reasons


def discover(root="."):
    """-> [(file, job, group, reasons)] for every job that can push."""
    composites = pushing_composites(root)
    found = []
    for path in sorted(glob.glob(os.path.join(root, WORKFLOW_DIR, "*.yml"))):
        with io.open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        rel = _rel(os.path.relpath(path, root))
        for job_name, job in ((doc.get("jobs") or {}).items()):
            reasons = push_reasons(job, composites)
            if not reasons:
                continue
            conc = (job or {}).get("concurrency")
            group = conc.get("group") if isinstance(conc, dict) else conc
            found.append((rel, job_name, group, reasons))
    return found


def load_waivers(root="."):
    """-> (waivers, failures). A missing file is no waivers, not an error."""
    path = os.path.join(root, WAIVERS_PATH)
    if not os.path.exists(path):
        return [], []
    try:
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return [], ["{0} could not be read ({1}); a waiver file that does not "
                    "parse would silence every waiver check.".format(WAIVERS_PATH, e)]
    waivers = data.get("waivers") if isinstance(data, dict) else None
    if not isinstance(waivers, list):
        return [], ["{0} must contain a \"waivers\" list.".format(WAIVERS_PATH)]
    failures = []
    good = []
    for i, w in enumerate(waivers):
        missing = [k for k in ("file", "job", "pushes", "reason")
                   if not isinstance(w, dict) or not str(w.get(k, "")).strip()]
        if missing:
            # A malformed waiver waives nothing: the job it half-names is
            # reported as unwaived as well, so the fix is to complete it.
            failures.append("{0} waiver #{1} is missing {2}: every waiver names "
                            "the file, the job, what it pushes, and why that is "
                            "not a spec branch write.".format(
                                WAIVERS_PATH, i, ", ".join(missing)))
        else:
            good.append(w)
    return good, failures


def evaluate(found, waivers):
    """-> list of failure strings."""
    failures = []
    waived = {(w.get("file"), w.get("job")) for w in waivers}
    seen = set()
    for rel, job_name, group, reasons in found:
        seen.add((rel, job_name))
        if (rel, job_name) in waived:
            continue
        if isinstance(group, str) and (
                PER_SPEC_GROUP_RE.match(group.strip())
                or PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE.match(group.strip())):
            continue
        failures.append(
            "{0} [{1}] can push ({2}) but its concurrency group is {3!r}, not "
            "the per-spec group `wing-commander-<spec-dir>` every spec-branch "
            "writer shares (specs/013 contract, #397). Join the group, or "
            "waive the job in {4} with what it pushes and why.".format(
                rel, job_name, "; ".join(reasons),
                group, WAIVERS_PATH))
    for w in waivers:
        key = (w.get("file"), w.get("job"))
        if key not in seen:
            failures.append(
                "{0} waives {1} [{2}], which does not exist or no longer pushes; "
                "a waiver cannot outlive its reason - remove it.".format(
                    WAIVERS_PATH, key[0], key[1]))
    return failures


def run(root="."):
    waivers, failures = load_waivers(root)
    found = discover(root)
    return found, failures + evaluate(found, waivers)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
_NL = chr(10)


def _job(name, group, steps):
    text = "  {0}:{1}    runs-on: ubuntu-latest{1}".format(name, _NL)
    if group is not None:
        text += "    concurrency:{0}      group: \"{1}\"{0}".format(_NL, group)
    text += "    steps:" + _NL + steps
    return text


RUN_PUSH = ("      - name: Publish" + _NL +
            "        run: |" + _NL +
            "          git commit -am x" + _NL +
            "          git push origin HEAD" + _NL)
RUN_ECHO_ONLY = ("      - name: Runbook" + _NL +
                 "        run: |" + _NL +
                 "          # git push origin --delete x" + _NL +
                 "          echo \"git push origin --delete x\"" + _NL)
RUN_ECHO_THEN_PUSH = ("      - name: Publish" + _NL +
                      "        run: |" + _NL +
                      "          echo publishing && git push origin HEAD" + _NL)
AGENT_GRANT = ("      - uses: ./.github/actions/wing-commander-tool-args" + _NL +
               "        with:" + _NL +
               "          step-label: \"x\"" + _NL +
               "          default-allowed-tools: \"Read,Bash(git push:*),Bash(ls:*)\"" + _NL)
COMPOSITE_CALL = ("      - uses: ./.wing-commander-pipeline/.github/actions/pusher" + _NL)
COMPOSITE_ACTION = ("name: pusher" + _NL + "runs:" + _NL +
                    "  using: composite" + _NL + "  steps:" + _NL +
                    "    - shell: bash" + _NL +
                    "      run: git push origin HEAD:refs/heads/x" + _NL)
GOOD_GROUP = "wing-commander-${{ inputs.spec-dir }}"
MATRIX_GROUP = "wing-commander-${{ matrix.spec_dir }}"
NEEDS_GROUP = "wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}"
BAD_GROUP = "wing-commander-cleanup-${{ inputs.head-ref }}"
NEAR_GROUP = "wing-commander-${{ inputs.spec-dir }}-extra"
FALLBACK_GROUP = ("wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}"
                   "${{ needs.resolve-identity.outputs.spec-dir == '' && "
                   "format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}")
FALLBACK_GROUP_MISMATCHED_JOB = (
    "wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}"
    "${{ needs.other-job.outputs.spec-dir == '' && "
    "format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}")
FALLBACK_GROUP_NEAR_MISS_LITERAL = (
    "wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}"
    "${{ needs.resolve-identity.outputs.spec-dir == '' && "
    "format('pr-conversation-{0}', inputs.pr-number) || '' }}")
FALLBACK_GROUP_NEAR_MISS_IDENTIFIER = (
    "wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}"
    "${{ needs.resolve-identity.outputs.spec-dir == '' && "
    "format('pr-conversation-pr-{0}', inputs.pr_number) || '' }}")


def _pr_conversation_jobs():
    """Loads .github/workflows/pr-conversation.yml's `jobs:` mapping straight
    from the shipped file, for self-test assertions about job *shape*
    (e.g. whether a job carries a concurrency block at all) that discover()
    does not surface, since discover() only reports push-capable jobs
    together with their group string, not the full jobs mapping."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(repo_root, WORKFLOW_DIR, "pr-conversation.yml")
    with io.open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return doc.get("jobs") or {}


def _resolve_identity_spec_dir_line():
    """Extracts the exact `echo "spec-dir=..."` line from resolve-identity's
    own step in the real .github/workflows/pr-conversation.yml, so this
    self-test exercises the shipped workflow rather than a second,
    independently maintained copy of the same derivation (CLAUDE.md's
    single-home rule) -- a revert of T020's fix in the real file must be
    caught here, not just in a hand-copied string."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workflow_path = os.path.join(repo_root, WORKFLOW_DIR, "pr-conversation.yml")
    with io.open(workflow_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.startswith('echo "spec-dir='):
                return stripped
    raise AssertionError(
        "could not find resolve-identity's 'echo \"spec-dir=...\"' line in "
        + workflow_path)


def _run_spec_dir_line(line, slug):
    """Runs a single `echo "spec-dir=..."`-shaped bash line against a
    candidate slug and returns the value after `spec-dir=`."""
    out = subprocess.run(
        ["bash", "-c", "slug=$1; " + line, "bash", slug],
        capture_output=True, text=True, check=True).stdout
    prefix = "spec-dir="
    assert out.startswith(prefix), out
    return out[len(prefix):].rstrip(_NL)


def _resolve_identity_spec_dir(slug):
    """Runs resolve-identity's own `spec-dir=...` line, extracted from the
    real pr-conversation.yml (pr-conversation.yml, specs/077), against a
    candidate slug, to prove the non-qualifying (empty-slug) case yields an
    empty spec-dir rather than the malformed `specs/`."""
    return _run_spec_dir_line(_resolve_identity_spec_dir_line(), slug)


def _fallback_group_value(spec_dir, pr_number):
    """Mirrors FALLBACK_GROUP's two `${{ }}` blocks once GitHub Actions has
    substituted spec-dir and, only when it is empty, the per-PR
    format(...) fallback -- so a caller can check what the stalled-mark
    job's concurrency group actually resolves to for a given spec-dir
    value."""
    tail = "pr-conversation-pr-{0}".format(pr_number) if spec_dir == "" else ""
    return "wing-commander-" + spec_dir + tail


SHARED_PUSHER_CALL = ("      - uses: ./.github/actions/shared-pusher" + _NL)
SHARED_PUSHER_ACTION = ("name: shared-pusher" + _NL + "runs:" + _NL +
                        "  using: composite" + _NL + "  steps:" + _NL +
                        "    - shell: bash" + _NL +
                        "      run: bash \"$GITHUB_ACTION_PATH/../_shared/push-it.sh\"" + _NL)


def _tree(jobs_text, waivers=None, composite=True):
    tmp = tempfile.mkdtemp(prefix="gate80-")
    os.makedirs(os.path.join(tmp, WORKFLOW_DIR))
    with io.open(os.path.join(tmp, WORKFLOW_DIR, "stage.yml"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write("name: stage" + _NL + "on: [push]" + _NL + "jobs:" + _NL + jobs_text)
    if composite:
        os.makedirs(os.path.join(tmp, ACTIONS_DIR, "pusher"))
        with io.open(os.path.join(tmp, ACTIONS_DIR, "pusher", "action.yml"),
                     "w", encoding="utf-8", newline="") as fh:
            fh.write(COMPOSITE_ACTION)
        os.makedirs(os.path.join(tmp, ACTIONS_DIR, "shared-pusher"))
        with io.open(os.path.join(tmp, ACTIONS_DIR, "shared-pusher", "action.yml"),
                     "w", encoding="utf-8", newline="") as fh:
            fh.write(SHARED_PUSHER_ACTION)
        os.makedirs(os.path.join(tmp, ACTIONS_DIR, "_shared"))
        with io.open(os.path.join(tmp, ACTIONS_DIR, "_shared", "push-it.sh"),
                     "w", encoding="utf-8", newline="") as fh:
            fh.write("#!/usr/bin/env bash" + _NL +
                     "git --git-dir=\"$shim/.git\" push \"$url\" HEAD:refs/heads/x" + _NL)
    if waivers is not None:
        os.makedirs(os.path.join(tmp, ".github/scripts"), exist_ok=True)
        with io.open(os.path.join(tmp, WAIVERS_PATH), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write(waivers if isinstance(waivers, str)
                     else json.dumps({"waivers": waivers}))
    return tmp


def self_test():
    bad = 0

    def case(label, jobs_text, expect_failing_jobs, waivers=None,
             expect_substrings=(), composite=True):
        nonlocal bad
        tmp = _tree(jobs_text, waivers, composite)
        try:
            _found, failures = run(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        joined = " | ".join(failures)
        # Only "<file> [<job>] can push" lines name a failing job; a stale
        # waiver's message names the job it waives, which is not one.
        named = sorted({m.group(1) for m in
                        (re.match(r"\S+ \[([\w-]+)\] can push", f) for f in failures)
                        if m})
        ok = named == sorted(expect_failing_jobs) and all(
            s in joined for s in expect_substrings)
        if ok:
            print("[ok] {0}".format(label))
        else:
            bad += 1
            print("[FAIL] {0}: expected jobs {1} and {2}, got: {3}".format(
                label, expect_failing_jobs, list(expect_substrings), failures or "clean"))

    case("a run-step pusher in the per-spec group passes (all three spellings)",
         _job("a", GOOD_GROUP, RUN_PUSH) + _job("b", MATRIX_GROUP, RUN_PUSH)
         + _job("c", NEEDS_GROUP, RUN_PUSH), [])
    case("a run-step pusher outside the group fails, naming the job and the group",
         _job("a", BAD_GROUP, RUN_PUSH), ["a"],
         expect_substrings=[BAD_GROUP, "run step 'Publish'"])
    case("a run-step pusher with no concurrency at all fails",
         _job("a", None, RUN_PUSH), ["a"], expect_substrings=["None"])
    case("a group that merely starts with the per-spec spelling is not the group",
         _job("a", NEAR_GROUP, RUN_PUSH), ["a"])
    case("the pr-conversation stalled-mark job's per-PR fallback spelling passes",
         _job("a", FALLBACK_GROUP, RUN_PUSH), [])
    case("the fallback spelling with a mismatched needs.<job> name across "
         "its two halves still fails (defeats the backreference)",
         _job("a", FALLBACK_GROUP_MISMATCHED_JOB, RUN_PUSH), ["a"])
    case("the bare wing-commander- constant still fails",
         _job("a", "wing-commander-", RUN_PUSH), ["a"])
    case("a near-miss literal (pr-conversation-{0}, missing -pr-) still fails",
         _job("a", FALLBACK_GROUP_NEAR_MISS_LITERAL, RUN_PUSH), ["a"])
    case("a near-miss identifier (inputs.pr_number, underscore) still fails",
         _job("a", FALLBACK_GROUP_NEAR_MISS_IDENTIFIER, RUN_PUSH), ["a"])

    label = ("resolve-identity emits an empty spec-dir for a non-qualifying "
             "PR (empty slug), so the stalled-mark job's fallback group "
             "resolves to the per-PR spelling, not wing-commander-specs/")
    empty_spec_dir = _resolve_identity_spec_dir("")
    empty_group = _fallback_group_value(empty_spec_dir, "42")
    if empty_spec_dir == "" and empty_group == "wing-commander-pr-conversation-pr-42":
        print("[ok] {0}".format(label))
    else:
        bad += 1
        print("[FAIL] {0}: spec-dir={1!r} group={2!r}".format(
            label, empty_spec_dir, empty_group))

    label = "resolve-identity emits specs/<slug> for a qualifying PR"
    qualifying_spec_dir = _resolve_identity_spec_dir("042-example")
    if qualifying_spec_dir == "specs/042-example":
        print("[ok] {0}".format(label))
    else:
        bad += 1
        print("[FAIL] {0}: got {1!r}".format(label, qualifying_spec_dir))

    label = ("a pre-T020 fixture (the hand-copied 'echo \"spec-dir=specs/"
             "$slug\"' line T020 replaced) yields the malformed non-empty "
             "'specs/' for an empty slug -- proving a future revert of "
             "T020's fix in the real workflow would be caught by this "
             "self-test's own assertions, not silently pass")
    pre_t020_spec_dir = _run_spec_dir_line('echo "spec-dir=specs/$slug"', "")
    if pre_t020_spec_dir == "specs/":
        print("[ok] {0}".format(label))
    else:
        bad += 1
        print("[FAIL] {0}: got {1!r}".format(label, pre_t020_spec_dir))

    case("an agent grant of Bash(git push:*) outside the group fails",
         _job("a", "wing-commander-intake", AGENT_GRANT), ["a"],
         expect_substrings=["agent grant Bash(git push:*)"])
    case("a composite that pushes, called from outside the group, fails",
         _job("a", None, COMPOSITE_CALL), ["a"],
         expect_substrings=["composite pusher"])
    case("a composite that pushes through a _shared script, called from outside the "
         "group, fails (spec 095's hardened push)",
         _job("a", None, SHARED_PUSHER_CALL), ["a"],
         expect_substrings=["composite shared-pusher"])
    case("the same composite call inside the group passes",
         _job("a", GOOD_GROUP, COMPOSITE_CALL), [])
    case("a runbook that only echoes or comments `git push` is not a pusher",
         _job("a", None, RUN_ECHO_ONLY), [])
    case("a print line that continues into `git push` is a pusher",
         _job("a", None, RUN_ECHO_THEN_PUSH), ["a"])
    case("a waiver naming the job suppresses exactly that job",
         _job("a", None, RUN_PUSH) + _job("b", None, RUN_PUSH), ["b"],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "a tag", "reason": "not a spec branch"}])
    case("a stale waiver (job gone) fails",
         _job("a", GOOD_GROUP, RUN_PUSH), [],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "ghost",
                   "pushes": "x", "reason": "y"}],
         expect_substrings=["does not exist or no longer pushes"])
    case("a stale waiver (job no longer pushes) fails",
         _job("a", None, RUN_ECHO_ONLY), [],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "x", "reason": "y"}],
         expect_substrings=["does not exist or no longer pushes"])
    case("a waiver missing its reason fails",
         _job("a", None, RUN_PUSH), ["a"],
         waivers=[{"file": ".github/workflows/stage.yml", "job": "a",
                   "pushes": "x"}],
         expect_substrings=["missing reason"])
    case("an unparseable waiver file fails rather than silencing the check",
         _job("a", GOOD_GROUP, RUN_PUSH), [], waivers="{not json",
         expect_substrings=["could not be read"])

    # The shipped defect, replayed against the real tree: cleanup.yml's
    # mark-stalled back in its own head-ref group must fail (#397).
    found = discover(".")
    waivers, _ = load_waivers(".")
    mutated = [(f, j, BAD_GROUP if (f, j) == (".github/workflows/cleanup.yml", "mark-stalled") else g, r)
               for f, j, g, r in found]
    if any(j == "mark-stalled" for _, j, _, _ in found) and any(
            "cleanup.yml [mark-stalled]" in x for x in evaluate(mutated, waivers)):
        print("[ok] the shipped defect replayed: cleanup.yml mark-stalled in its "
              "old head-ref group fails")
    else:
        bad += 1
        print("[FAIL] cleanup.yml mark-stalled back in its old group was not caught")

    # T034 (Maintainer Feedback): stalled must carry no concurrency block at
    # all -- T023's per-PR group was also classify-and-announce's own, so a
    # newer run's classify-and-announce could evict an older run's still-
    # pending stall notice. This is not something evaluate() would ever
    # catch on its own: stalled is (and stays) permanently waived, so its
    # group value never enters the per-spec-group check.
    label = ("pr-conversation.yml's stalled job regains a concurrency block "
             "shared with classify-and-announce or any other job (T032)")
    pr_conversation_jobs = _pr_conversation_jobs()
    stalled_concurrency = (pr_conversation_jobs.get("stalled") or {}).get("concurrency")

    def _group_of(job):
        conc = (job or {}).get("concurrency")
        return conc.get("group") if isinstance(conc, dict) else conc

    stalled_group = _group_of({"concurrency": stalled_concurrency})
    colliding = sorted(
        name for name, job in pr_conversation_jobs.items()
        if name != "stalled" and stalled_group is not None
        and _group_of(job) == stalled_group)
    if stalled_concurrency is None:
        print("[ok] {0}".format(label))
    elif not colliding:
        print("[ok] {0} (stalled carries a group again, but it collides "
              "with no other job)".format(label))
    else:
        bad += 1
        print("[FAIL] {0}: stalled's group {1!r} is shared with {2}".format(
            label, stalled_group, colliding))

    print("Gate 80 self-test: {0} failure(s).".format(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="Gate 80 - spec-branch pushers share the per-spec group")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    found, failures = run(args.root)
    for f in failures:
        print("::error::Gate 80: {0}".format(f))
    print("Gate 80: {0} pushing job(s) checked against the per-spec concurrency "
          "group and {1}; {2} failure(s).".format(len(found), WAIVERS_PATH, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
