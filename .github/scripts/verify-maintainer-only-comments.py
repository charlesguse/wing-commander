#!/usr/bin/env python3
"""Gate 180 -- comment-triggered stages act only on maintainers
(specs/133-maintainer-only-comments, contracts/comment-author-rule.md).

WHY THIS EXISTS
---------------
Constitution 3.0.0 (Principle V): a comment admits a stage run, or reaches
an agent as context, only when its author is not a bot and its
author_association is OWNER, MEMBER or COLLABORATOR. Nothing about the
commenter's identity or user id is consulted, and owning the issue admits
no comment. Before spec 133 several surfaces also
admitted the issue's own author, and nothing would have stopped that clause
from coming back.

WHAT IT CHECKS (default run, on the tree)
-----------------------------------------
(a) Every wrapper triggered by issue_comment, pull_request_review or
    pull_request_review_comment: no job `if:`, step `if:`, step `env:`
    value or `with:` value compares or passes an identity (`.user.id`,
    `issue-author-id`, `commenter-id ==`, actor/author ids, any read of
    the issue's author). The one exception is the issue author's kind
    (`issue.user.type`, as the Spec Kit wrapper requires a Bot-authored
    issue): it narrows who can start a run and is not an identity.
(b) clarify.yml's `clarify` job: the `comment-author` step exists, comes
    before `lifecycle-gate`, and both `lifecycle-gate` and "Note closed
    lifecycle and stop" carry its `maintainer == 'true'` condition. Every
    later step skips for a refused comment: one whole term of its `if:`'s
    && chain, never one inside a `!( ... )`, is the is-open condition or a
    condition that is false when an already-gated step was skipped; only
    the two argument-composing steps run ungated.
(c) wing-commander-issue-context's trust filter compares no user id (Gate
    96 runs its behaviour).
(d) auto-update-spec-kit.yml's `comment-reply` job `if:` compares no id.
(e) The auto-release e2e clarify decision script's qualifying rule
    compares no user id.
(f) clarify's tool grant has no `gh issue view`.
(g) intake's "Announce clarification needed" and clarify's "Announce
    remaining clarification questions" are each preceded, in the same job
    and under the same `if:`, by wing-commander-requester-relay-note on
    the same body file.
(h) Single home: the relay paragraph's text appears in no other file under
    .github/workflows, .github/actions or .github/scripts, nor in a live
    doc or contract (the files (i) reads), compared on letters and digits
    alone, so a copy wrapped at another width, in comment lines, quoted
    string pieces or a blockquote is still found. Each sentence is probed,
    so a copy of any one of them is found too.
(i) No live doc or contract in LIVE_DOCS writes an identity comparison (`actor.id ==`, `user.id ==`,
    `== ...author-id`, `commenter-id ==`): they describe the rule by
    association only (FR-009, SC-005).
(j) pr-conversation.yml's stage-side "Authorized-actor gate" (id
    actor-gate) admits by `inputs.actor-association` alone: its `if:`,
    `env:` and `run:` compare no identity (FR-010 names stages too).
(k) Single home of the relay step's comment: its key sentence appears only
    in clarify.yml, which carries Gate 47's `requester-relay-note`
    canonical marker; intake.yml points at it.
(l) No workflow, composite (.yml or .sh under .github/actions) or live
    doc or contract describes the issue's author in prose as admitted next
    to the maintainer set ("... or the issue's own author", "the
    association/author-id clause", "a maintainer or the original
    reporter", "the original requester or trusted members",
    "maintainer-or-author", "the issue author or a maintainer"), contrasts
    pr-conversation with clarify or intake as if they had an exception
    ("unlike clarify/intake"), or writes an identity comparison
    (`actor.id ==`) in a comment.
(m) contracts/comment-author-rule.md's "Where it is enforced" table has a
    row naming every comment-triggered wrapper in .github/workflows.
Plus two harnesses that run the shipped shell against a stub `gh`:
- the `comment-author` step: OWNER, MEMBER and COLLABORATOR give
  maintainer=true; NONE, CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR and a Bot
  give false; a failed read fails the step and never yields true;
- the relay composite: a NONE author appends the paragraph exactly once,
  an OWNER author leaves the file byte-identical, a failed read appends.

--self-test runs one mutant per check, each reintroducing what the check
forbids, and fails unless every mutant is caught.
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

GATE = "Gate 180"
WF = os.path.join(".github", "workflows")
CLARIFY = os.path.join(WF, "clarify.yml")
INTAKE = os.path.join(WF, "intake.yml")
UPDATER = os.path.join(WF, "auto-update-spec-kit.yml")
CONTEXT = os.path.join(".github", "actions", "wing-commander-issue-context", "action.yml")
E2E_SCRIPT = os.path.join(".github", "actions", "_shared", "auto-release-e2e-clarify-decision.sh")
RELAY = os.path.join(".github", "actions", "wing-commander-requester-relay-note", "action.yml")
RELAY_USES_SUFFIX = "/wing-commander-requester-relay-note"
COMMENT_TRIGGERS = {"issue_comment", "pull_request_review", "pull_request_review_comment"}
MAINTAINER_COND = "steps.comment-author.outputs.maintainer == 'true'"
IF_IDENTITY = re.compile(
    r"\.user\.id\b|issue-author-id|commenter-id\s*==|==\s*inputs\.commenter-id|"
    r"\bactor[._-]id\b|\bauthor[._-]id\b|issue\.user\b(?!\.type\b)")
JQ_IDENTITY = re.compile(r"\.user\.id\b|\$aid\b|author_id")
DOC_IDENTITY = re.compile(
    r"(?:user|actor|author)[._-]id\s*==|==\s*[\w.$-]*(?:user\.id|author[._-]id|\$aid)\b|"
    r"commenter-id\s*==")
PR_CONVERSATION = os.path.join(WF, "pr-conversation.yml")
# (i)'s subjects: the live docs and contracts that describe who a
# comment-triggered stage admits (spec 133's T001 inventory, plus the docs
# and contracts its review passes found). A literal list,
# not a directory walk, so verify-gate-wiring.py can see each subject and
# hold lint-workflows.yml's pull_request paths: to it. A missing file fails
# the gate loudly.
LIVE_DOCS = (
    "docs/adoption.md",
    "docs/architecture.md",
    "docs/setup.md",
    "specs/010-reusable-pipeline/contracts/stage-interfaces.md",
    "specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md",
    "specs/022-gate-closed-lifecycle/contracts/lifecycle-gate-points.md",
    "specs/029-intake-issue-comments/contracts/comment-trust-gate.md",
    "specs/029-intake-issue-comments/contracts/notice-callout.md",
    "specs/032-structured-clarification-gate/contracts/clarification-schema.md",
    "specs/032-structured-clarification-gate/contracts/decision-points.md",
    "specs/033-pr-conversation-commands/contracts/reusable-pr-conversation.md",
    "specs/033-pr-conversation-commands/contracts/wrapper-gate.md",
    "specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md",
    "specs/057-autonomous-board-loop/contracts/triage.md",
    "specs/063-stage-clarify-label/contracts/e2e-clarification-label-assertion.md",
    "specs/115-board-loop-self-merge/contracts/board-merge.md",
    "specs/133-maintainer-only-comments/contracts/comment-author-rule.md",
)
WRAPPER_GATE_DOC = os.path.normpath("specs/033-pr-conversation-commands/contracts/wrapper-gate.md")
BASH = None


def load_yaml(text):
    return yaml.safe_load(text)


def triggers(doc):
    on = doc.get("on", doc.get(True))  # PyYAML reads a bare `on:` key as True
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    if isinstance(on, dict):
        return set(on)
    return set()


def steps_of(doc, job):
    return ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []


def find(steps, key, value):
    for i, s in enumerate(steps):
        if s.get(key) == value:
            return i, s
    return None, None


# --------------------------------------------------------------------------
# Static checks. Each takes a `tree` dict {relpath: text} and returns a list
# of failure strings, so the self-test can hand it a mutated copy.
# --------------------------------------------------------------------------

def check_a(tree):
    failures = []
    for path, text in sorted(tree.items()):
        if not (path.startswith(WF + os.sep) and path.endswith(".yml")):
            continue
        doc = load_yaml(text) or {}
        if not (triggers(doc) & COMMENT_TRIGGERS):
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            cond = str(job.get("if", ""))
            if IF_IDENTITY.search(cond):
                failures.append(f"(a) {path} job {job_id!r}: its if: admits a comment by "
                                f"identity, not only by author_association")
            if "issue-author-id" in (job.get("with") or {}):
                failures.append(f"(a) {path} job {job_id!r} passes issue-author-id")
            for key, val in (job.get("with") or {}).items():
                if key != "issue-author-id" and IF_IDENTITY.search(str(val)):
                    failures.append(f"(a) {path} job {job_id!r} passes an identity as {key!r}")
            for n, step in enumerate(job.get("steps") or []):
                parts = [str(step.get("if", ""))]
                parts += [str(v) for v in (step.get("env") or {}).values()]
                parts += [str(v) for v in (step.get("with") or {}).values()]
                if IF_IDENTITY.search(" ".join(parts)):
                    failures.append(f"(a) {path} job {job_id!r} step {step.get('name') or n!r}: "
                                    f"its if:, env: or with: reads an identity")
    return failures


def check_b(tree):
    doc = load_yaml(tree[CLARIFY])
    steps = steps_of(doc, "clarify")
    ci, check = find(steps, "id", "comment-author")
    gi, gate = find(steps, "id", "lifecycle-gate")
    ni, note = find(steps, "name", "Note closed lifecycle and stop")
    failures = []
    if check is None:
        return ["(b) clarify.yml: no step with id 'comment-author' in the clarify job"]
    if gate is None or note is None:
        return ["(b) clarify.yml: the lifecycle-gate step or 'Note closed lifecycle and stop' is missing"]
    if ci > gi:
        failures.append("(b) clarify.yml: the comment-author step must run before lifecycle-gate")
    for label, s in (("lifecycle-gate", gate), ("Note closed lifecycle and stop", note)):
        if MAINTAINER_COND not in str(s.get("if", "")):
            failures.append(f"(b) clarify.yml: {label!r} lacks the condition {MAINTAINER_COND!r}")
    run = str(check.get("run", ""))
    for needle in ("author_association", "Bot"):
        if needle not in run:
            failures.append(f"(b) clarify.yml: the comment-author step does not read {needle!r}")
    failures += _ungated_after_gate(steps, gi)
    return failures


# (b)'s second half: a refused comment leaves lifecycle-gate skipped, so its
# is-open output is empty. Every later step in the clarify job must skip
# then: one whole term of its `if:` (an && chain, no ||, a term inside a
# `!( ... )` never counting) is the is-open condition, or a condition that
# is false when an already-gated step was skipped. Only the two steps that
# compose arguments and write nothing may run ungated.
IS_OPEN_COND = "steps.lifecycle-gate.outputs.is-open == 'true'"
UNGATED_OK = {"commit-guidance-clarify", "tool-args-clarify"}
SKIP_SAFE = re.compile(
    r"steps\.([\w-]+)\.(?:outputs\.[\w-]+\s*==\s*'[^']+'|outputs\.[\w-]+\s*!=\s*''|"
    r"outcome\s*!=\s*'skipped')")


def _conjuncts(cond):
    """The top-level terms of an && chain, each a whole term. A negated
    group `!( ... )` becomes one opaque term, and a plain grouping `( ... )`
    is opened, so a term inside a negation never counts as a gate. A
    function call (`always()`, `contains(...)`) becomes one opaque term."""
    prev = None
    while prev != cond:
        prev = cond
        cond = re.sub(r"(?<![\w.])[A-Za-z_]\w*\s*\([^()]*\)", " call ", cond)
        cond = re.sub(r"!\s*\([^()]*\)", " !negated ", cond)
        cond = re.sub(r"(?<![\w!])\(([^()]*)\)", r" \1 ", cond)
    return [" ".join(t.split()) for t in cond.split("&&")]


def _gates_on_skip(term, gated):
    """True when the whole term is false whenever an already-gated step
    was skipped (its outputs empty, its outcome 'skipped')."""
    if term in (IS_OPEN_COND, MAINTAINER_COND):
        return True
    m = SKIP_SAFE.fullmatch(term)
    return bool(m) and m.group(1) in gated


def _ungated_after_gate(steps, gi):
    gated = {"lifecycle-gate"}
    failures = []
    for n, s in enumerate(steps[gi + 1:], gi + 1):
        sid = s.get("id")
        cond = str(s.get("if") or "").strip()
        cond = re.sub(r"^\$\{\{\s*|\s*\}\}$", "", cond)
        ok = False
        if cond and "||" not in cond:
            ok = any(_gates_on_skip(t, gated) for t in _conjuncts(cond))
        if ok:
            if sid:
                gated.add(sid)
        elif sid not in UNGATED_OK:
            failures.append(f"(b) clarify.yml: step {s.get('name') or sid or n!r} would run for a "
                            f"refused comment; gate it on {IS_OPEN_COND!r}")
    return failures


def check_c(tree):
    doc = load_yaml(tree[CONTEXT])
    runs = " ".join(str(s.get("run", "")) for s in (doc.get("runs") or {}).get("steps") or [])
    if JQ_IDENTITY.search(runs):
        return ["(c) wing-commander-issue-context: the trust filter compares a user id"]
    return []


def check_d(tree):
    doc = load_yaml(tree[UPDATER])
    cond = str(((doc.get("jobs") or {}).get("comment-reply") or {}).get("if", ""))
    if not cond:
        return ["(d) auto-update-spec-kit.yml: no comment-reply job if:"]
    if IF_IDENTITY.search(cond):
        return ["(d) auto-update-spec-kit.yml: comment-reply admits a commenter by identity"]
    return []


def check_e(tree):
    text = tree[E2E_SCRIPT]
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    if JQ_IDENTITY.search(code):
        return ["(e) auto-release-e2e-clarify-decision.sh: the qualifying rule compares a user id"]
    return []


def check_f(tree):
    doc = load_yaml(tree[CLARIFY])
    _, step = find(steps_of(doc, "clarify"), "name", "Compose tool args (clarify)")
    if step is None:
        return ["(f) clarify.yml: no 'Compose tool args (clarify)' step"]
    grant = str((step.get("with") or {}).get("default-allowed-tools", ""))
    if "gh issue view" in grant:
        return ["(f) clarify.yml: the clarify agent is granted gh issue view"]
    return []


CALLOUTS = ((INTAKE, "intake", "Announce clarification needed"),
            (CLARIFY, "clarify", "Announce remaining clarification questions"))


def check_g(tree):
    failures = []
    for path, job, name in CALLOUTS:
        steps = steps_of(load_yaml(tree[path]), job)
        idx, callout = find(steps, "name", name)
        if callout is None:
            failures.append(f"(g) {path}: no step {name!r}")
            continue
        body = (callout.get("with") or {}).get("body-file")
        ok = any(str(s.get("uses", "")).endswith(RELAY_USES_SUFFIX)
                 and (s.get("with") or {}).get("body-file") == body
                 and str(s.get("if", "")) == str(callout.get("if", ""))
                 for s in steps[:idx])
        if not ok:
            failures.append(f"(g) {path}: {name!r} is not preceded by the relay composite on "
                            f"{body!r} under the same if:")
    return failures


def relay_paragraph(tree):
    doc = load_yaml(tree[RELAY])
    for s in (doc.get("runs") or {}).get("steps") or []:
        para = (s.get("env") or {}).get("RELAY_PARAGRAPH")
        if para:
            return str(para).strip()
    return None


def check_h(tree):
    if RELAY not in tree:
        return ["(h) the relay composite does not exist"]
    para = relay_paragraph(tree)
    if not para:
        return ["(h) the relay composite has no RELAY_PARAGRAPH"]
    # One probe per sentence, so a copy of any one sentence is found too.
    probes = [_letters(s)[:60] for s in re.split(r"(?<=[.!?])\s+", para)
              if len(_letters(s)) >= 30]
    others = [p for p, t in tree.items()
              if p != RELAY and any(probe in _letters(t) for probe in probes)]
    return [f"(h) the relay paragraph is copied into {p}" for p in others]


def _flatten(text):
    """Text with each line's leading `#` comment markers removed and all
    whitespace collapsed, so a copy wrapped at another width, or wrapped
    into `#` comment lines, compares equal to the folded paragraph."""
    lines = (re.sub(r"^\s*#+", " ", l) for l in text.splitlines())
    return re.sub(r"\s+", " ", " ".join(lines))


def _letters(text):
    """Only the text's letters and digits, lowercased: a copy wrapped at any
    width, inside quotes, comment markers, blockquotes or string
    continuations still compares equal to the paragraph."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def check_i(tree):
    failures = []
    for path, text in sorted(tree.items()):
        if not path.endswith(".md"):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if DOC_IDENTITY.search(line):
                failures.append(f"(i) {path}:{n}: a live doc or contract writes an identity "
                                f"comparison; describe the rule by association only")
    return failures


def check_j(tree):
    doc = load_yaml(tree[PR_CONVERSATION])
    for job in (doc.get("jobs") or {}).values():
        _, step = find(job.get("steps") or [], "id", "actor-gate")
        if step is None:
            continue
        env = step.get("env") or {}
        text = " ".join([str(step.get("if", "")), str(step.get("run", ""))]
                        + [f"{k} {v}" for k, v in env.items()])
        failures = []
        if "inputs.actor-association" not in " ".join(str(v) for v in env.values()):
            failures.append("(j) pr-conversation.yml: the actor-gate step does not read "
                            "inputs.actor-association")
        if IF_IDENTITY.search(text) or JQ_IDENTITY.search(text) or re.search(r"_ID\b", text):
            failures.append("(j) pr-conversation.yml: the actor-gate step reads an identity")
        return failures
    return ["(j) pr-conversation.yml: no step with id 'actor-gate'"]


# (l): prose that describes the issue's author as admitted next to the
# maintainer set, as the removed text did ("OWNER/MEMBER/COLLABORATOR or the
# issue's own author", "a maintainer or the issue author", "the
# association/author-id clause", "a maintainer or the original reporter",
# "the original requester or trusted members", "or `user.id` is the issue
# author's", "or from this id", "maintainer-or-author", "as the issue author
# or a maintainer"), contrasts pr-conversation with clarify or
# intake as if they had an exception ("unlike clarify/intake"), or writes
# an identity comparison in a comment (`actor.id ==`). Every such sentence
# spec 133 deleted is caught. Matched on text flattened by _flatten.
PROSE_EXCEPTION = re.compile(
    r"\bor (?:its author is )?(?:the|an) (?:lifecycle )?issue(?:['’]s)? (?:own )?author\b|"
    r"\bor (?:the )?original (?:requester|reporter)\b|\boriginal (?:requester|reporter) or\b|"
    r"\bunlike (?:the )?clarify(?:/| and | or )intake\b|\bgate admits (?:the|an) issue['’]s (?:own )?author\b|"
    r"\bor `?\.?user\.id`? is the issue(?:['’]s)? author|\bor from this id\b|"
    r"(?:user|actor|author)[._-]id\s*==|"
    r"\bmaintainer-or-author\b|\bissue(?:['’]s)? (?:own )?author or (?:a )?maintainer\b|"
    r"association/author-id|author-by-id|dropping the author-id clause", re.I)


def check_l(tree):
    failures = []
    roots = (os.path.normpath(WF) + os.sep, os.path.normpath(os.path.join(".github", "actions")) + os.sep)
    live = {os.path.normpath(p) for p in LIVE_DOCS}
    for path, text in sorted(tree.items()):
        if not (path in live or (path.startswith(roots) and path.endswith((".yml", ".yaml", ".sh")))):
            continue
        m = PROSE_EXCEPTION.search(_flatten(text))
        if m:
            failures.append(f"(l) {path}: describes the issue's author as admitted ({m.group(0)!r}); "
                            f"describe the rule by association only")
    return failures


RELAY_COMMENT_KEY = "the questions say up front that only a maintainer's reply is folded in"


def check_k(tree):
    """The relay step's comment has one canonical copy, in clarify.yml
    (Gate 47 marker requester-relay-note); intake.yml points at it."""
    homes = [p for p, t in tree.items() if RELAY_COMMENT_KEY in _flatten(t)]
    if homes != [CLARIFY]:
        return [f"(k) the relay step's comment must live only in {CLARIFY} (other sites "
                f"point at it with `-- see clarify.yml`); found in {sorted(homes)}"]
    return []


RULE_CONTRACT = os.path.normpath("specs/133-maintainer-only-comments/contracts/comment-author-rule.md")
RULE_TABLE_HEADING = "## Where it is enforced"


def check_m(tree):
    """The rule contract's enforcement table has a row for every
    comment-triggered wrapper in the tree."""
    text = tree[RULE_CONTRACT]
    if RULE_TABLE_HEADING not in text:
        return [f"(m) {RULE_CONTRACT}: no {RULE_TABLE_HEADING!r} section"]
    table = text.split(RULE_TABLE_HEADING, 1)[1].split("\n## ", 1)[0]
    failures = []
    for path, wf in sorted(tree.items()):
        if not (path.startswith(WF + os.sep) and path.endswith(".yml")):
            continue
        if not (triggers(load_yaml(wf) or {}) & COMMENT_TRIGGERS):
            continue
        name = os.path.basename(path)
        if f"`{name}`" not in table:
            failures.append(f"(m) {RULE_CONTRACT}: the enforcement table has no row for "
                            f"the comment-triggered wrapper {name}")
    return failures


STATIC_CHECKS = (check_a, check_b, check_c, check_d, check_e, check_f, check_g, check_h,
                 check_i, check_j, check_k, check_l, check_m)


# --------------------------------------------------------------------------
# Harnesses: run the shipped shell against a stub gh.
# --------------------------------------------------------------------------

STUB_GH = r'''#!/usr/bin/env bash
# Stub gh for Gate 180: `gh api <path> [--jq EXPR]` only.
[ "$1" = "api" ] || { echo "stub gh: unexpected: $*" >&2; exit 2; }
shift
path=""; expr="."
while [ $# -gt 0 ]; do
  case "$1" in
    --jq) expr="$2"; shift 2 ;;
    *) path="$1"; shift ;;
  esac
done
if [ "$path" != "$STUB_PATH" ]; then echo "stub gh: unexpected path $path" >&2; exit 2; fi
if [ -n "${STUB_FAIL:-}" ]; then echo "HTTP 502: Bad Gateway" >&2; exit 1; fi
jq -r "$expr" "$STUB_JSON"
'''


def _run_with_stub(script, payload, stub_path, env_extra, fail=False, files=None):
    root = tempfile.mkdtemp(prefix="gate180-")
    try:
        bindir = os.path.join(root, "bin")
        workdir = os.path.join(root, "work")
        runner_temp = os.path.join(root, "rt")
        for d in (bindir, workdir, runner_temp):
            os.makedirs(d)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB_GH)
        os.chmod(gh, 0o755)
        data = os.path.join(root, "payload.json")
        with open(data, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh)
        env = dict(env_extra)
        env.update({"GH_TOKEN": "dummy", "GITHUB_REPOSITORY": "acme/widgets",
                    "STUB_PATH": stub_path, "STUB_JSON": data.replace("\\", "/"),
                    "PATH": bindir + os.pathsep + os.environ["PATH"]})
        if fail:
            env["STUB_FAIL"] = "1"
        written = {}
        for name, content in (files or {}).items():
            p = os.path.join(root, name)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            written[name] = p
            env["BODY_FILE"] = p.replace("\\", "/")
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
        after = {}
        for name, p in written.items():
            with open(p, encoding="utf-8") as fh:
                after[name] = fh.read()
        return rc, out, outputs, after
    finally:
        shutil.rmtree(root, ignore_errors=True)


COMMENT_CASES = (
    ("OWNER", "User", "true"), ("MEMBER", "User", "true"), ("COLLABORATOR", "User", "true"),
    ("NONE", "User", "false"), ("CONTRIBUTOR", "User", "false"),
    ("FIRST_TIME_CONTRIBUTOR", "User", "false"), ("OWNER", "Bot", "false"),
)


def harness_comment_author(tree):
    doc = load_yaml(tree[CLARIFY])
    _, step = find(steps_of(doc, "clarify"), "id", "comment-author")
    if step is None:
        return ["(b-harness) no comment-author step to run"]
    script = str(step.get("run", ""))
    if "${{" in script:
        return ["(b-harness) the comment-author run: block holds a ${{ }} expression; pass values through env:"]
    failures = []
    path = "repos/acme/widgets/issues/comments/4242"
    for assoc, utype, want in COMMENT_CASES:
        payload = {"id": 4242, "author_association": assoc, "user": {"login": "x", "type": utype}}
        rc, out, outputs, _ = _run_with_stub(script, payload, path, {"COMMENT_ID": "4242"})
        got = outputs.get("maintainer")
        if rc != 0 or got != want:
            failures.append(f"(b-harness) {assoc}/{utype}: expected maintainer={want}, got rc={rc} "
                            f"maintainer={got!r}: {out.strip()[:200]}")
    rc, out, outputs, _ = _run_with_stub(script, {}, path, {"COMMENT_ID": "4242"}, fail=True)
    if rc == 0 or outputs.get("maintainer") == "true":
        failures.append(f"(b-harness) a failed read must fail the step and never yield true "
                        f"(rc={rc}, maintainer={outputs.get('maintainer')!r})")
    return failures


def harness_relay(tree):
    if RELAY not in tree:
        return ["(relay-harness) the relay composite does not exist"]
    doc = load_yaml(tree[RELAY])
    steps = (doc.get("runs") or {}).get("steps") or []
    step = next((s for s in steps if s.get("run")), None)
    if step is None:
        return ["(relay-harness) the relay composite has no run step"]
    script = str(step["run"])
    if "${{" in script:
        return ["(relay-harness) the run: block holds a ${{ }} expression; pass values through env:"]
    para = relay_paragraph(tree) or ""
    env = {"ISSUE_NUMBER": "77", "RELAY_PARAGRAPH": para}
    path = "repos/acme/widgets/issues/77"
    original = "## Questions\n\nQ1: something?\n"
    failures = []
    for assoc, fail, want_appended in (("NONE", False, True), ("CONTRIBUTOR", False, True),
                                       ("OWNER", False, False), ("COLLABORATOR", False, False),
                                       ("", True, True)):
        rc, out, _o, after = _run_with_stub(script, {"author_association": assoc}, path, env,
                                            fail=fail, files={"body.md": original})
        body = after.get("body.md", "")
        label = "failed read" if fail else assoc
        if rc != 0:
            failures.append(f"(relay-harness) {label}: the step failed: {out.strip()[:200]}")
        elif want_appended and body.count(para) != 1:
            failures.append(f"(relay-harness) {label}: the paragraph must be appended exactly once")
        elif not want_appended and body != original:
            failures.append(f"(relay-harness) {label}: the body must be left byte-identical")
        elif want_appended and not body.startswith(original):
            failures.append(f"(relay-harness) {label}: the original body must be kept in front")
    return failures


HARNESSES = (harness_comment_author, harness_relay)


def load_tree():
    tree = {}
    for top in (os.path.join(".github", "workflows"), os.path.join(".github", "actions"),
                os.path.join(".github", "scripts")):
        for dirpath, _dirs, files in os.walk(top):
            for f in files:
                if f.endswith((".yml", ".yaml", ".sh", ".py", ".jq")):
                    p = os.path.join(dirpath, f)
                    if os.path.abspath(p) == os.path.abspath(__file__):
                        continue
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        tree[os.path.normpath(p)] = fh.read()
    for p in LIVE_DOCS:
        with open(p, encoding="utf-8") as fh:
            tree[os.path.normpath(p)] = fh.read()
    return tree


def run_all(tree):
    failures = []
    for check in STATIC_CHECKS:
        try:
            failures += check(tree)
        except (KeyError, yaml.YAMLError) as exc:
            failures.append(f"{check.__name__}: could not read the tree ({exc})")
    for harness in HARNESSES:
        failures += harness(tree)
    return failures


# --------------------------------------------------------------------------
# Self-test mutants: each must make run_all report a failure.
# --------------------------------------------------------------------------

def _sub(tree, path, old, new):
    t = dict(tree)
    if old not in t[path]:
        raise ValueError(f"mutant anchor {old!r} not found in {path}")
    t[path] = t[path].replace(old, new, 1)
    return t


def _yaml_edit(tree, path, edit):
    t = dict(tree)
    doc = copy.deepcopy(load_yaml(t[path]))
    edit(doc)
    t[path] = yaml.safe_dump(doc, sort_keys=False, width=10_000)
    return t


def _clarify_wrapper_mutant(tree):
    p = os.path.join(WF, "wing-commander-2-clarify.yml")
    def edit(doc):
        job = doc["jobs"]["clarify"]
        job["if"] = str(job["if"]) + " || github.event.comment.user.id == github.event.issue.user.id"
    return _yaml_edit(tree, p, edit)


def _updater_wrapper_login_mutant(tree):
    p = os.path.join(WF, "wing-commander-auto-update-spec-kit.yml")
    def edit(doc):
        for job in doc["jobs"].values():
            if "uses" in job:
                job["if"] = (str(job["if"]) + " || github.event.issue.user.login == "
                             "github.event.comment.user.login")
                return
    return _yaml_edit(tree, p, edit)


def _updater_wrapper_node_id_mutant(tree):
    p = os.path.join(WF, "wing-commander-auto-update-spec-kit.yml")
    def edit(doc):
        for job in doc["jobs"].values():
            if "uses" in job:
                job["if"] = (str(job["if"]) + " || github.event.issue.user.node_id == "
                             "github.event.comment.user.node_id")
                return
    return _yaml_edit(tree, p, edit)


def _updater_wrapper_whole_author_mutant(tree):
    p = os.path.join(WF, "wing-commander-auto-update-spec-kit.yml")
    def edit(doc):
        for job in doc["jobs"].values():
            if "uses" in job:
                job["if"] = (str(job["if"]) + " || toJSON(github.event.issue.user) == "
                             "toJSON(github.event.comment.user)")
                return
    return _yaml_edit(tree, p, edit)


def _updater_wrapper_mutant(tree):
    p = os.path.join(WF, "wing-commander-auto-update-spec-kit.yml")
    def edit(doc):
        for job in doc["jobs"].values():
            if "uses" in job:
                job.setdefault("with", {})["issue-author-id"] = "${{ github.event.issue.user.id || '' }}"
                return
    return _yaml_edit(tree, p, edit)


def _gate_cond_mutant(tree):
    def edit(doc):
        _, s = find(steps_of(doc, "clarify"), "id", "lifecycle-gate")
        s.pop("if", None)
    return _yaml_edit(tree, CLARIFY, edit)


def _order_mutant(tree):
    def edit(doc):
        steps = steps_of(doc, "clarify")
        ci, check = find(steps, "id", "comment-author")
        steps.pop(ci)
        gi, _ = find(steps, "id", "lifecycle-gate")
        steps.insert(gi + 1, check)
    return _yaml_edit(tree, CLARIFY, edit)


def _accept_none_mutant(tree):
    def edit(doc):
        _, s = find(steps_of(doc, "clarify"), "id", "comment-author")
        s["run"] = s["run"].replace("OWNER|MEMBER|COLLABORATOR)", "OWNER|MEMBER|COLLABORATOR|NONE)", 1)
    return _yaml_edit(tree, CLARIFY, edit)


def _filter_mutant(tree):
    return _sub(tree, CONTEXT, '.author_association == "COLLABORATOR")',
                '.author_association == "COLLABORATOR" or .user.id == $aid)')


def _updater_if_mutant(tree):
    def edit(doc):
        job = doc["jobs"]["comment-reply"]
        job["if"] = str(job["if"]) + " || inputs.commenter-id == inputs.issue-author-id"
    return _yaml_edit(tree, UPDATER, edit)


def _e2e_mutant(tree):
    return _sub(tree, E2E_SCRIPT, '((.author_association // "") == "COLLABORATOR")',
                '((.author_association // "") == "COLLABORATOR")\n            or (((.user.id // -1) | tostring) == $author_id)')


def _grant_mutant(tree):
    def edit(doc):
        _, s = find(steps_of(doc, "clarify"), "name", "Compose tool args (clarify)")
        s["with"]["default-allowed-tools"] += ",Bash(gh issue view:*)"
    return _yaml_edit(tree, CLARIFY, edit)


def _relay_dropped_mutant(tree):
    def edit(doc):
        steps = steps_of(doc, "intake")
        for i, s in enumerate(steps):
            if str(s.get("uses", "")).endswith(RELAY_USES_SUFFIX):
                steps.pop(i)
                return
    return _yaml_edit(tree, INTAKE, edit)


def _copy_mutant(tree):
    para = relay_paragraph(tree)
    t = dict(tree)
    t[CLARIFY] = t[CLARIFY] + "\n# " + para[:80] + "\n"
    return t


def _wrapped_copy_mutant(tree):
    import textwrap
    para = relay_paragraph(tree)
    t = dict(tree)
    lines = "\n".join("      # " + l for l in textwrap.wrap(para, 40))
    t[INTAKE] = t[INTAKE] + "\n" + lines + "\n"
    return t


def _doc_mutant(tree):
    p = WRAPPER_GATE_DOC
    t = dict(tree)
    t[p] = t[p] + ("\nUnlike clarify's comment-reading precedent, there is no\n"
                   "`|| actor.id == issue.author.id` carve-out here.\n")
    return t


def _updater_step_mutant(tree):
    p = os.path.join(WF, "wing-commander-auto-update-spec-kit.yml")
    def edit(doc):
        for job in doc["jobs"].values():
            if "uses" in job:
                job.setdefault("with", {})["commenter-id"] = "${{ github.event.comment.user.id || '' }}"
                return
    return _yaml_edit(tree, p, edit)


def _pr_conversation_mutant(tree):
    def edit(doc):
        for job in doc["jobs"].values():
            _, s = find(job.get("steps") or [], "id", "actor-gate")
            if s is not None:
                s.setdefault("env", {})["ISSUE_AUTHOR_ID"] = "${{ inputs.issue-author-id }}"
                s["run"] = s["run"].replace(
                    "case ", '[ "$ACTOR_ID" = "$ISSUE_AUTHOR_ID" ] && ACTOR_ASSOCIATION=OWNER\ncase ', 1)
                return
    return _yaml_edit(tree, PR_CONVERSATION, edit)


def _wrapper_step_mutant(tree):
    p = os.path.join(WF, "wing-commander-2-clarify.yml")
    def edit(doc):
        doc["jobs"]["author-probe"] = {"runs-on": "ubuntu-latest", "steps": [{
            "name": "Admit the issue's author",
            "if": "github.event.comment.user.id == github.event.issue.user.id",
            "run": "true"}]}
    return _yaml_edit(tree, p, edit)


def _actor_gate_gone_mutant(tree):
    def edit(doc):
        for job in doc["jobs"].values():
            _, s = find(job.get("steps") or [], "id", "actor-gate")
            if s is not None:
                s["id"] = "actor-gate-renamed"
                return
    return _yaml_edit(tree, PR_CONVERSATION, edit)


def _actor_gate_no_association_mutant(tree):
    def edit(doc):
        for job in doc["jobs"].values():
            _, s = find(job.get("steps") or [], "id", "actor-gate")
            if s is not None:
                s["env"] = {"ACTOR_ASSOCIATION": "OWNER"}
                return
    return _yaml_edit(tree, PR_CONVERSATION, edit)


def _comment_copy_mutant(tree):
    return _sub(tree, INTAKE, "      # The maintainer-relay note for a requester who is not a maintainer\n"
                              "      # -- see clarify.yml.\n",
                "      # FR-008: when the issue's author is not a maintainer, the questions\n"
                "      # say up front that only a maintainer's reply is folded in.\n")


def _relay_never_mutant(tree):
    def edit(doc):
        for s in doc["runs"]["steps"]:
            if s.get("run"):
                s["run"] = s["run"].replace("OWNER|MEMBER|COLLABORATOR)", "OWNER|MEMBER|COLLABORATOR|NONE|CONTRIBUTOR|*)", 1)
    return _yaml_edit(tree, RELAY, edit)


def _agent_ungated_mutant(tree):
    cond = "steps.lifecycle-gate.outputs.is-open == 'true' && steps.tool-args-clarify.outputs.allowed-tools != ''"
    return _sub(tree, CLARIFY, "id: agent\n        if: " + cond,
                "id: agent\n        if: steps.tool-args-clarify.outputs.allowed-tools != ''")


def _agent_negated_gate_mutant(tree):
    cond = "steps.lifecycle-gate.outputs.is-open == 'true' && steps.tool-args-clarify.outputs.allowed-tools != ''"
    return _sub(tree, CLARIFY, "id: agent\n        if: " + cond,
                "id: agent\n        if: \"!(" + cond + ")\"")


def _callout_reporter_mutant(tree):
    return _sub(tree, INTAKE, "this issue did not qualify for the specification (not from a\n"
                "            maintainer)",
                "this issue did not qualify for the specification (not from a\n"
                "            maintainer or the original reporter)")


def _sentence_copy_mutant(tree):
    import textwrap
    para = relay_paragraph(tree)
    last = re.split(r"(?<=[.!?])\s+", para)[-1]
    t = dict(tree)
    t[INTAKE] = t[INTAKE] + "\n" + "\n".join("# " + l for l in textwrap.wrap(last, 50)) + "\n"
    return t


def _contrast_mutant(tree):
    p = os.path.join(WF, "pr-conversation.yml")
    t = dict(tree)
    t[p] = t[p] + "\n# Deliberately no requester carve-out, unlike clarify/intake (FR-019).\n"
    return t


def _quoted_copy_mutant(tree):
    import textwrap
    para = relay_paragraph(tree)
    p = os.path.join(".github", "scripts", "verify-issue-context-trust-filter.py")
    t = dict(tree)
    t[p] = (t[p] + "\nRELAY = (\n"
            + "\n".join(f'    "{l} "' for l in textwrap.wrap(para, 40)) + "\n)\n")
    return t


def _prose_mutant(tree):
    p = os.path.join(".github", "actions", "wing-commander-issue-context", "action.yml")
    return _sub(tree, p, "never a bot", "or the issue's own author, never a bot")


def _stage_header_mutant(tree):
    return _sub(tree, CLARIFY, "security gates (commenter is a maintainer, OWNER/MEMBER/COLLABORATOR, and",
                "security gates (commenter is maintainer-or-author and not a bot, and")


def _setup_doc_mutant(tree):
    p = os.path.normpath("docs/setup.md")
    return _sub(tree, p, "reply to the comment as a\n   maintainer (`OWNER`, `MEMBER` or `COLLABORATOR`)",
                "reply to the comment (as the issue\n   author or a maintainer)")


def _lifecycle_contract_mutant(tree):
    p = os.path.normpath("specs/022-gate-closed-lifecycle/contracts/lifecycle-gate-points.md")
    return _sub(tree, p, "non-bot commenter is a maintainer (`OWNER`/`MEMBER`/`COLLABORATOR`)",
                "non-bot commenter is maintainer-or-author")


def _contract_row_mutant(tree):
    return _sub(tree, RULE_CONTRACT, "| `wing-commander-auto-update-spec-kit.yml` | wrapper `if:` |",
                "| the Spec Kit wrapper | wrapper `if:` |")


MUTANTS = (
    ("(a) the clarify wrapper admits the issue's author", _clarify_wrapper_mutant),
    ("(m) the rule contract has no row for the Spec Kit wrapper", _contract_row_mutant),
    ("(a) the Spec Kit wrapper passes issue-author-id", _updater_wrapper_mutant),
    ("(a) the Spec Kit wrapper admits the issue's author by login", _updater_wrapper_login_mutant),
    ("(a) the Spec Kit wrapper admits the issue's author by node_id", _updater_wrapper_node_id_mutant),
    ("(a) the Spec Kit wrapper admits the issue's author as a whole object", _updater_wrapper_whole_author_mutant),
    ("(b) lifecycle-gate loses the maintainer condition", _gate_cond_mutant),
    ("(b) the comment-author step runs after lifecycle-gate", _order_mutant),
    ("(b-harness) the comment-author step accepts NONE", _accept_none_mutant),
    ("(c) the trust filter admits the issue's author", _filter_mutant),
    ("(d) comment-reply admits the issue's author", _updater_if_mutant),
    ("(e) the e2e decision admits the issue's author", _e2e_mutant),
    ("(f) clarify is granted gh issue view", _grant_mutant),
    ("(g) intake's questions lose the relay composite", _relay_dropped_mutant),
    ("(h) the relay paragraph is copied into clarify.yml", _copy_mutant),
    ("(h) the relay paragraph is copied into intake.yml as 40-column comment lines",
     _wrapped_copy_mutant),
    ("(i) a live contract describes the issue-author carve-out", _doc_mutant),
    ("(a) the Spec Kit wrapper passes the commenter's user id", _updater_step_mutant),
    ("(j) pr-conversation's actor gate admits the issue's author", _pr_conversation_mutant),
    ("(a) a clarify wrapper step admits the issue's author", _wrapper_step_mutant),
    ("(k) intake.yml copies the relay step's comment", _comment_copy_mutant),
    ("(j) pr-conversation's actor-gate step is gone", _actor_gate_gone_mutant),
    ("(j) pr-conversation's actor gate stops reading actor-association",
     _actor_gate_no_association_mutant),
    ("(b) clarify's agent step loses the is-open condition", _agent_ungated_mutant),
    ("(h) the relay paragraph is copied into a gate script as a wrapped Python string",
     _quoted_copy_mutant),
    ("(l) the issue-context composite says it admits the issue's own author", _prose_mutant),
    ("(b) clarify's agent step runs under a negated is-open condition", _agent_negated_gate_mutant),
    ("(l) intake's callout counts the original reporter as qualifying", _callout_reporter_mutant),
    ("(l) a pr-conversation comment contrasts it with clarify/intake", _contrast_mutant),
    ("(h) the relay paragraph's last sentence alone is copied into intake.yml",
     _sentence_copy_mutant),
    ("(relay-harness) the relay composite never appends", _relay_never_mutant),
    ("(l) clarify.yml's header says the wrapper admits maintainer-or-author", _stage_header_mutant),
    ("(l) docs/setup.md tells the issue's author to reply", _setup_doc_mutant),
    ("(l) the spec 022 contract says the wrapper admits maintainer-or-author",
     _lifecycle_contract_mutant),
)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isdir(WF):
        sys.exit(f"::error::{GATE}: run this from the repository root.")
    tree = load_tree()
    failures = run_all(tree)
    if "--self-test" in sys.argv[1:]:
        if failures:
            failures = [f"the tree itself fails, so mutants cannot be judged: {f}" for f in failures]
        else:
            for label, mutate in MUTANTS:
                try:
                    caught = run_all(mutate(tree))
                except (ValueError, KeyError, TypeError) as exc:
                    failures.append(f"mutant {label!r} could not be applied ({exc}); update the "
                                    f"mutant alongside the file")
                    continue
                # Caught only by the check the label names: a YAML re-dump
                # drops every comment, so an unrelated check (k) would
                # otherwise "catch" each such mutant for the wrong reason.
                tag = label.split(")", 1)[0] + ")"
                own = [c for c in caught if c.startswith(tag)]
                if own:
                    print(f"note: mutant caught -- {label}: {own[0]}")
                else:
                    failures.append(f"mutant NOT caught by its own check {tag} -- {label}"
                                    + (f" (only by: {caught[0]})" if caught else ""))
    for f in failures:
        print(f"::error::{GATE}: {f}")
    if failures:
        print(f"{GATE}: {len(failures)} failure(s).")
        return 1
    mode = "self-test: every mutant caught" if "--self-test" in sys.argv[1:] else "0 failure(s)"
    print(f"{GATE}: comment-triggered stages admit maintainers only; {mode}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
