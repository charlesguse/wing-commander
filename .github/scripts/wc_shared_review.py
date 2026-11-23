#!/usr/bin/env python3
"""The shared PR reviewer's deterministic half (specs/127-shared-pr-reviewer).

Everything that gates a durable record is code here, not agent text
(Principle IX): the round record and its marker, finding identity, the
FR-015 transition table, the open-set fold, the blocking rule, the verdict,
request validation, run confirmation, the round budget and the hand-off.
shared-pr-reviewer.yml stays thin and calls the CLI at the bottom.

Gate registration (T002, research D3): an unpublished callable is listed,
with a reason, in unpublished-callables.json, which
wc_published_stages.unpublished_callables() reads; shared-pr-reviewer.yml
is registered there (T020).

The marker is `wing-commander-shared-review-round`, disjoint from
wc_convergence.ROUND_MARKER, so read_round_records() never counts a record
written here (FR-020) with no edit to that reader.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import (  # noqa: E402
    is_loop_branch, is_loop_marker_author, last_marker_match, marker_json, marker_regexes)
from wc_review_finding_fingerprint import fingerprint as finding_fingerprint  # noqa: E402

MARKER = "wing-commander-shared-review-round"
MARKER_RE, MARKER_OPEN_RE = marker_regexes(MARKER)
REVIEWER = "shared-pr-reviewer"
SCHEMA = 1
WORKFLOW_PATH = ".github/workflows/shared-pr-reviewer.yml"
WRAPPER_PATH = ".github/workflows/wing-commander-shared-pr-reviewer.yml"
ARTIFACT_PREFIX = "shared-review-"
MAX_RECORD_CHARS = 20000
# What a size-capped `findings` entry keeps (build_record).
STUB_KEYS = ("id", "status")
DEFAULT_BUDGET = 5

VERDICTS = ("clean", "findings", "undetermined", "incomplete")
OPEN_STATUSES = ("upheld", "reopened")
KINDS = ("fix", "spec", "plan", "final", "board-fix")
RUNNABLE_KINDS = ("fix", "board-fix")
POSITIVE, NEGATIVE, UNDETERMINABLE = "positive", "negative", "not_determinable"
ANSWER_KEYS = ("problem_real", "change_fixes", "check_fails_without_fix")
NOT_RECHECKED = "not re-checked: code-run results missing"

# FR-015: (previous status or None, new status) pairs the code accepts.
# Dismissal of an open finding is allowed only through a requester dismissal.
TRANSITIONS = {
    (None, "upheld"), (None, "dismissed"),
    ("dismissed", "reopened"), ("resolved", "reopened"),
    ("upheld", "upheld"), ("reopened", "reopened"),
    ("upheld", "resolved"), ("reopened", "resolved"),
    ("upheld", "dismissed"), ("reopened", "dismissed"),
    ("dismissed", "dismissed"), ("resolved", "resolved"),
}

# A merged spec's own documents are not defects (CLAUDE.md); contracts are.
SPEC_DOC_RE = re.compile(r"^specs/[^/]+/(spec|plan|tasks|research)\.md$")


# --------------------------------------------------------------- records ---

def short_sha(sha):
    return str(sha or "")[:7]


def header_line(record):
    """The fixed human header above the marker (research D11)."""
    return "Shared reviewer \u2014 round {0} at {1} \u2014 verdict {2}".format(
        record.get("round"), short_sha(record.get("head_sha")), record.get("verdict"))


def _marker(payload):
    return "<!-- {0}: {1} -->".format(MARKER, marker_json(payload))


def build_record(record, handoff=False):
    """The comment body for one round (or hand-off): header, a findings
    table, then the marker LAST. The marker is capped at MAX_RECORD_CHARS:
    `findings` is truncated first (with `findings_truncated` counting what
    was cut); `open_set` is never truncated. A cut entry keeps its id and
    status as a stub, because fold_open_set takes each finding's latest
    status from these records: dropping a resolved or dismissed entry
    would let an earlier round's `upheld` reopen it. Whole entries are
    dropped only if the stubs alone still do not fit."""
    payload = dict(record)
    payload.setdefault("schema", SCHEMA)
    payload.setdefault("reviewer", REVIEWER)
    if handoff:
        payload["kind"] = "handoff"
        payload.pop("verdict", None)
    findings = list(payload.get("findings") or [])
    payload["findings"] = findings
    cut = 0
    i = len(findings) - 1
    while len(_marker(payload)) > MAX_RECORD_CHARS and i >= 0:
        f = findings[i]
        if isinstance(f, dict) and set(f) - set(STUB_KEYS):
            findings[i] = {k: f.get(k) for k in STUB_KEYS}
            cut += 1
            payload["findings_truncated"] = cut
        i -= 1
    while len(_marker(payload)) > MAX_RECORD_CHARS and payload["findings"]:
        payload["findings"].pop()
        cut += 1
        payload["findings_truncated"] = cut
    if handoff:
        head = "Shared reviewer \u2014 hand-off after {0} of {1} rounds \u2014 {2} open".format(
            payload.get("rounds_used"), payload.get("budget"), len(payload.get("open_set") or []))
    else:
        head = header_line(payload)
    rows = ["| id | status | file | title |", "|---|---|---|---|"]
    for f in (payload.get("open_set") or []) + payload["findings"]:
        rows.append("| {0} | {1} | {2} | {3} |".format(
            f.get("id"), f.get("status"), _cell(f.get("file")), _cell(f.get("title"))))
    return "{0}\n\n{1}\n\n{2}".format(head, "\n".join(rows), _marker(payload))


def _cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:120]


def parse_records(comments, bot_login, kind="round"):
    """Records of `kind` ("round" or "handoff") in bot-authored comments,
    oldest first: only the LAST opener in a body, only this App's comments,
    only well-formed payloads. Confirmation against the run is separate
    (confirm_record); nothing here is trusted until then."""
    out = []
    for comment in comments or []:
        if not isinstance(comment, dict) or not is_loop_marker_author(comment, bot_login):
            continue
        match = last_marker_match(comment.get("body") or "", MARKER_RE, MARKER_OPEN_RE)
        if not match:
            continue
        try:
            rec = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("reviewer") != REVIEWER:
            continue
        is_handoff = rec.get("kind") == "handoff"
        if (kind == "handoff") != is_handoff:
            continue
        if not is_handoff and (isinstance(rec.get("round"), bool) or not isinstance(rec.get("round"), int)
                               or rec["round"] < 1 or rec.get("verdict") not in VERDICTS
                               or not isinstance(rec.get("head_sha"), str)):
            continue
        out.append((comment.get("created_at") or "", rec))
    out.sort(key=lambda pair: pair[0])
    return [rec for _stamp, rec in out]


def confirm_record(record, run, default_branch, repository=None):
    """D5: a record counts only when the run it names, read back from the
    Actions API, is this reviewer's own completed successful run on the
    default branch that uploaded `shared-review-<head_sha>`. Fails closed."""
    if not isinstance(record, dict) or not isinstance(run, dict):
        return False
    run_id = str(record.get("run_id") or "")
    if not run_id.isdigit() or str(run.get("id")) != run_id:
        return False
    if run.get("path") != WRAPPER_PATH or run.get("head_branch") != default_branch:
        return False
    repo = repository or run.get("repository")
    if not repo or run.get("status") != "completed" or run.get("conclusion") != "success":
        return False
    if record.get("reviewer_commit") != run.get("head_sha") or not record.get("reviewer_commit"):
        return False
    called = [str(p).split("@", 1)[0] for p in run.get("referenced_workflows") or []]
    if "{0}/{1}".format(repo, WORKFLOW_PATH) not in called:
        return False
    return ARTIFACT_PREFIX + str(record.get("head_sha")) in (run.get("artifacts") or [])


def latest_round_for_commit(confirmed, head_sha):
    """The highest-round confirmed record naming `head_sha`, or None."""
    at = [r for r in confirmed if r.get("head_sha") == head_sha]
    return max(at, key=lambda r: r["round"]) if at else None


# ------------------------------------------------------- findings/verdict ---

def is_blocking(finding):
    """FR-013: open, in scope and reachable. Code decides, never the agent."""
    return (finding.get("status") in OPEN_STATUSES and finding.get("in_scope") is True
            and finding.get("reachable") is True)


def non_blocking_rule(finding):
    """Why an open finding is non-blocking, or None when it blocks."""
    if finding.get("status") not in OPEN_STATUSES:
        return "not open"
    if finding.get("in_scope") is not True:
        return "out of the pull request's scope"
    if finding.get("reachable") is not True:
        return "failing case not shown reachable in this repository's configuration"
    return None


def compute_verdict(agent_ok, open_set, answers, code_run_status, has_purpose=True):
    """FR-014 order. An earlier round's still-open blocking finding is in
    `open_set`, so it counts. A negative purpose answer is a determined
    failure of the change: `findings`."""
    if not agent_ok:
        return "incomplete"
    if any(is_blocking(f) for f in open_set or []):
        return "findings"
    if code_run_status != "staged":
        return "incomplete"
    values = [(answers or {}).get(k) for k in ANSWER_KEYS]
    if NEGATIVE in values:
        return "findings"
    if not has_purpose or any(v != POSITIVE for v in values):
        return "undetermined"
    return "clean"


def _overlaps(a, b):
    if not a.get("file") or a.get("file") != b.get("file"):
        return False
    try:
        a1 = int(a.get("line")); a2 = int(a.get("line_end") or a1)
        b1 = int(b.get("line")); b2 = int(b.get("line_end") or b1)
    except (TypeError, ValueError):
        return False
    return a1 <= b2 and b1 <= a2


def _only_spec_docs(files):
    files = [f for f in files or [] if f]
    return bool(files) and all(SPEC_DOC_RE.match(f) for f in files)


def _transition(prev, new):
    return (prev, new) in TRANSITIONS


def apply_dismissals(prior, dismissals):
    """Requester dismissals, applied from the start of the round: only ids
    open in `prior` count. Returns (new prior list, applied, notes)."""
    by_id = {f["id"]: dict(f) for f in prior}
    applied, notes = [], []
    if not isinstance(dismissals, list):
        dismissals = []
    for d in dismissals:
        if not isinstance(d, dict):
            continue
        fid = d.get("id")
        f = by_id.get(fid)
        if f is None or f.get("status") not in OPEN_STATUSES or not (d.get("reason") or "").strip():
            notes.append("dismissal of {0} dropped: not open at round start or no reason".format(fid))
            continue
        f["status"], f["reason"] = "dismissed", str(d["reason"])
        applied.append({"id": fid, "reason": f["reason"]})
    return list(by_id.values()), applied, notes


def process_round(prior, candidates, checks, round_no, code_run_status):
    """One round's finding bookkeeping.

    prior: findings folded from confirmed rounds (dicts with id, status...).
    candidates: the find job's output; each has `key`, title, file, line,
    line_end, failing_case, optional `cites`.
    checks: the check job's output, keyed by `key` (candidates) or `id`
    (prior findings): {outcome: upheld|dismissed|resolved|confirmed,
    reason, in_scope, reachable, files, needs_code_run}.
    Returns (findings, notes): every finding with its latest status."""
    by_id = {f["id"]: dict(f) for f in prior}
    # Two namespaces: a candidate's `key` is the find agent's free text, so
    # it may equal a prior finding's id (F1-1); one dict would let a check
    # meant for one apply to the other.
    check_for_key, check_for_id = {}, {}
    for c in checks or []:
        if not isinstance(c, dict):
            continue
        if isinstance(c.get("id"), str) and c["id"]:
            check_for_id[c["id"]] = c
        if isinstance(c.get("key"), str) and c["key"]:
            check_for_key[c["key"]] = c
    notes, serial = [], 0

    def settle(f, c):
        f["in_scope"] = c.get("in_scope") is True
        f["reachable"] = c.get("reachable") is True

    for cand in candidates or []:
        c = check_for_key.get(cand.get("key")) or {}
        cited = cand.get("cites")
        base = {k: cand.get(k) for k in ("title", "claim", "file", "line", "line_end", "failing_case")}
        spec_only = c.get("cites_only_spec_docs") is True or _only_spec_docs(c.get("files"))
        upheld = (c.get("outcome") == "upheld" and bool(cand.get("failing_case")) and not spec_only)
        if cited in by_id:
            f = by_id[cited]
            if f["status"] in ("dismissed", "resolved"):
                if upheld and _transition(f["status"], "reopened"):
                    f["status"], f["reason"] = "reopened", c.get("reason") or "checker upheld a showing"
                    settle(f, c)
                else:
                    notes.append("{0} re-raised without an upheld showing; stays {1}".format(cited, f["status"]))
            continue
        if cited:
            notes.append("cite of unknown id {0} ignored".format(cited))
        serial += 1
        f = dict(base)
        f["id"] = "F{0}-{1}".format(round_no, serial)
        f["fingerprint"] = finding_fingerprint(0, f.get("title") or "", f.get("file") or "")
        f["cites"] = cited if cited in by_id else None
        overlap = [p["id"] for p in by_id.values() if _overlaps(f, p)]
        f["possible_repeat_of"] = overlap[0] if overlap else None
        if spec_only:
            f["status"], f["reason"] = "dismissed", "cites only a merged spec's own documents"
        elif upheld:
            f["status"], f["reason"] = "upheld", c.get("reason") or "checker upheld"
        else:
            f["status"] = "dismissed"
            f["reason"] = c.get("reason") or ("no failing case" if not cand.get("failing_case")
                                              else "checker did not uphold")
        f["note"] = None
        settle(f, c)
        by_id[f["id"]] = f
    for fid, f in list(by_id.items()):
        if f.get("status") not in OPEN_STATUSES or fid not in check_for_id or fid.startswith("F%d-" % round_no):
            continue
        c = check_for_id[fid]
        if c.get("needs_code_run") and code_run_status != "staged":
            f["note"] = NOT_RECHECKED
            continue
        if c.get("outcome") == "resolved" and _transition(f["status"], "resolved"):
            f["status"], f["reason"], f["note"] = "resolved", c.get("reason") or "no longer reproduces", None
        elif c.get("outcome") in ("confirmed", "upheld"):
            f["note"] = None
            settle(f, c)
    return list(by_id.values()), notes


def open_set(findings):
    return [f for f in findings if f.get("status") in OPEN_STATUSES]


def fold_open_set(confirmed_rounds):
    """The open set after the last confirmed round: each round record's
    `open_set` and `findings` carry the statuses; later rounds win. A
    size-capped stub (id and status only, build_record) updates the status
    and keeps the detail an earlier round recorded."""
    state = {}
    for rec in sorted(confirmed_rounds, key=lambda r: r["round"]):
        for f in (rec.get("findings") or []) + (rec.get("open_set") or []):
            if isinstance(f, dict) and f.get("id"):
                prev = state.get(f["id"])
                state[f["id"]] = dict(prev, **f) if prev and set(f) <= set(STUB_KEYS) else f
    return list(state.values())


# --------------------------------------------------------------- request ---

LIFECYCLE_BRANCH_RE = re.compile(r"^(spec|plan)/")


def derive_kind(head_branch, labels=()):
    """The PR's kind from its head branch and labels, never agent output."""
    branch = head_branch or ""
    labels = set(labels or ())
    for kind in ("final", "plan", "spec"):
        if "lifecycle:" + kind in labels or "kind:" + kind in labels:
            return kind
    match = re.match(r"^fix/(\d+)-", branch)
    if match and is_loop_branch(branch, match.group(1)):
        return "board-fix"
    if LIFECYCLE_BRANCH_RE.match(branch):
        return "spec"
    if re.match(r"^(fix|claude)/", branch):
        return "fix"
    return "unknown"


def validate_request(pr, kind, dismissals):
    """(ok, reason): refusal text goes to the run summary only (FR-022)."""
    if not str(pr).isdigit():
        return False, "refused: pr is not a number"
    if kind not in RUNNABLE_KINDS:
        return False, "refused: pull request kind {0!r} is not a fix PR".format(kind)
    if dismissals is not None and not isinstance(dismissals, list):
        return False, "refused: dismissals is not a list"
    return True, None


_CLOSES_RE = re.compile(r"\b(?:closes|fixes|resolves|fix|close|resolve)[:\s]+#(\d+)", re.I)
_ISSUE_RE = re.compile(r"(?<![\w/])#(\d+)\b")
_LINE_RE = re.compile(r"\bbacklog line[:\s]+([a-z0-9][a-z0-9-]*)", re.I)
_RUN_RE = re.compile(r"https://[^\s/]+/[^\s/]+/[^\s/]+/actions/runs/(\d+)")


def resolve_purpose_source(pr_number, body):
    """D10 order: a cited issue (not the PR itself), a backlog line, a run.
    None means 'no source of purpose'."""
    body = body or ""
    for pattern in (_CLOSES_RE, _ISSUE_RE):
        for match in pattern.finditer(body):
            if match.group(1) != str(pr_number):
                return {"type": "issue", "ref": match.group(1)}
    match = _LINE_RE.search(body)
    if match:
        return {"type": "backlog", "ref": match.group(1)}
    match = _RUN_RE.search(body)
    if match:
        return {"type": "run", "ref": match.group(1)}
    return None


def guard(ref, default_branch, kind, paused, dismissals=None):
    """The guard job's decision: (proceed, reason). Never a record."""
    if not default_branch or ref != "refs/heads/{0}".format(default_branch):
        return False, "refused: not run from the default branch ({0})".format(ref)
    if str(paused).lower() in ("true", "1", "yes"):
        return False, "paused"
    ok, reason = validate_request(0, kind, dismissals)
    if not ok:
        return False, reason
    return True, None


# --------------------------------------------------------------- budget ---

def budget_spent(confirmed_rounds, budget=DEFAULT_BUDGET):
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        budget = DEFAULT_BUDGET
    if budget < 1:
        budget = DEFAULT_BUDGET
    return len(confirmed_rounds) >= budget, budget


def build_handoff(pr, confirmed_rounds, budget, run_id, reviewer_commit):
    last = max(confirmed_rounds, key=lambda r: r["round"]) if confirmed_rounds else {}
    return {"schema": SCHEMA, "reviewer": REVIEWER, "kind": "handoff", "pr": pr,
            "rounds_used": len(confirmed_rounds), "budget": budget,
            "open_set": list(last.get("open_set") or []), "run_id": str(run_id),
            "reviewer_commit": reviewer_commit}


CHECK_OUTCOMES = ("upheld", "dismissed", "resolved", "confirmed")
ANSWER_VALUES = (POSITIVE, NEGATIVE, UNDETERMINABLE)


def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _opt(value, kinds):
    return value is None or (isinstance(value, kinds) and not isinstance(value, bool))


def validate_output(data, role, prior=None):
    """Problems with one agent job's output, [] when it is well-formed.

    `role` is "find" or "check"; each has its own schema, the same one its
    --json-schema states plus the types process_round relies on. Output
    that fails is malformed, so the round is `incomplete` (FR-014), never
    a quieter verdict from a half-read output. For `check`, `prior` is the
    round's memory: every finding open in it must be evaluated by id
    (FR-010)."""
    if role not in ("find", "check"):
        return ["unknown role {0!r}".format(role)]
    if not isinstance(data, dict):
        return ["output is not a JSON object"]
    problems = []
    if not isinstance(data.get("answers"), dict):
        problems.append("answers is not an object")
    if role == "find":
        items = data.get("candidates")
        if not isinstance(items, list):
            return problems + ["candidates is not a list"]
        for n, c in enumerate(items):
            if not isinstance(c, dict):
                problems.append("candidate {0} is not an object".format(n))
                continue
            for k in ("key", "title", "file"):
                if not _nonempty_str(c.get(k)):
                    problems.append("candidate {0} has no {1}".format(n, k))
            for k in ("line", "line_end"):
                if not _opt(c.get(k), int):
                    problems.append("candidate {0} {1} is not an integer".format(n, k))
            if not _opt(c.get("failing_case"), dict):
                problems.append("candidate {0} failing_case is not an object".format(n))
            if not _opt(c.get("cites"), str):
                problems.append("candidate {0} cites is not a string".format(n))
        return problems
    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    for k in ANSWER_KEYS:
        if answers.get(k) not in ANSWER_VALUES:
            problems.append("purpose answer {0} is not one of {1}".format(k, "/".join(ANSWER_VALUES)))
    items = data.get("checks")
    if not isinstance(items, list):
        return problems + ["checks is not a list"]
    evaluated = set()
    for n, c in enumerate(items):
        if not isinstance(c, dict):
            problems.append("check {0} is not an object".format(n))
            continue
        if not (_nonempty_str(c.get("id")) or _nonempty_str(c.get("key"))):
            problems.append("check {0} names neither an id nor a key".format(n))
        for k in ("id", "key", "reason"):
            if not _opt(c.get(k), str):
                problems.append("check {0} {1} is not a string".format(n, k))
        if c.get("outcome") not in CHECK_OUTCOMES:
            problems.append("check {0} outcome is not one of {1}".format(n, "/".join(CHECK_OUTCOMES)))
        for k in ("in_scope", "reachable", "cites_only_spec_docs", "needs_code_run"):
            if c.get(k) is not None and not isinstance(c.get(k), bool):
                problems.append("check {0} {1} is not a boolean".format(n, k))
        files = c.get("files")
        if files is not None and not (isinstance(files, list) and all(isinstance(x, str) for x in files)):
            problems.append("check {0} files is not a list of strings".format(n))
        if _nonempty_str(c.get("id")):
            evaluated.add(c["id"])
    for f in prior or []:
        if isinstance(f, dict) and f.get("status") in OPEN_STATUSES and f.get("id") not in evaluated:
            problems.append("open finding {0} was not evaluated (FR-010)".format(f.get("id")))
    return problems


def finalize_round(state, find_out, check_out, code_run, purpose, head_sha, dismissals,
                   run_id, reviewer_commit, pr_state, agent_ok=True):
    """One round's whole record, from staged data only. Agent output is
    read as data; every status, blocking flag and the verdict is code's."""
    round_no = int(state.get("round") or 1)
    # The same per-role schema the agent jobs' validate-output step applies:
    # a malformed output is read as missing, so the round is `incomplete`.
    if validate_output(find_out, "find"):
        find_out = None
    if validate_output(check_out, "check", state.get("prior")):
        check_out = None
    prior, applied, notes = apply_dismissals(state.get("prior") or [], dismissals)
    code_status = (code_run or {}).get("status") if (code_run or {}).get("status") == "staged" else "missing"
    agent_ok = bool(agent_ok and isinstance(find_out, dict) and isinstance(check_out, dict))
    findings, more = process_round(prior, (find_out or {}).get("candidates") or [],
                                   (check_out or {}).get("checks") or [], round_no, code_status)
    answers = (check_out or {}).get("answers") or {}
    opened = open_set(findings)
    for f in opened:
        f["blocking"] = is_blocking(f)
        f["non_blocking_rule"] = non_blocking_rule(f)
    verdict = compute_verdict(agent_ok, opened, answers, code_status, has_purpose=bool(purpose))
    return {"schema": SCHEMA, "reviewer": REVIEWER, "pr_kind": "fix", "round": round_no,
            "head_sha": head_sha, "verdict": verdict, "pr_state": pr_state,
            "purpose": {"source": purpose, "version_used": (purpose or {}).get("version_used", "current"),
                        "answers": answers},
            "open_set": opened, "findings": [f for f in findings if f not in opened],
            "dismissals": applied, "notes": notes + more,
            "reviewer_commit": reviewer_commit, "run_id": str(run_id)}


# ------------------------------------------------- code-run and GitHub ---

CODE_RUN_TIMEOUT = 600
TAIL_CHARS = 4000


def discover_named_check(added_files):
    """The change's named check, found by code from the diff's ADDED files
    (never chosen by an agent, research D8): the first added test file, run
    through a fixed runner. Returns an argv list or None."""
    for path in sorted(added_files or []):
        if ".." in path.split("/") or path.startswith("/"):
            continue
        base = path.rsplit("/", 1)[-1]
        if re.fullmatch(r"verify-[\w.-]+\.py", base):
            return ["python3", "-I", path]
        if re.fullmatch(r"test_[\w.-]+\.py", base):
            # discover puts the file's directory on sys.path, which -I
            # otherwise leaves out.
            return ["python3", "-I", "-m", "unittest", "discover", "-v",
                    "-s", path.rsplit("/", 1)[0] if "/" in path else ".", "-p", base]
        if base == "run-tests.sh":
            return ["bash", path]
    return None


def _run_staged(argv, cwd, timeout, env):
    """One command, its exit code staged as data -- a non-zero exit, a
    crash or a hang is never a job failure (FR-012, spec edge cases)."""
    import subprocess
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        out = (proc.stdout or "") + (proc.stderr or "")
        return {"exit": proc.returncode, "output_tail": out[-TAIL_CHARS:]}
    except subprocess.TimeoutExpired:
        return {"exit": 124, "output_tail": "timed out after {0}s".format(timeout)}
    except OSError as exc:
        return {"exit": 127, "output_tail": str(exc)[-TAIL_CHARS:]}


def stage_code_run(pr_tree, reviewer_tree, added_files, timeout=CODE_RUN_TIMEOUT):
    """The two commands the code-run job may run, nothing else: the named
    check, and the default branch's gate runner against the PR tree. The
    environment is scrubbed: no ACTIONS_*, token or secret variable
    reaches PR code (SC-008)."""
    pr_tree, reviewer_tree = os.path.abspath(pr_tree), os.path.abspath(reviewer_tree)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("TMPDIR", "/tmp"),
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    argv = discover_named_check(added_files)
    named = _run_staged(argv, pr_tree, timeout, env) if argv else None
    gates = _run_staged(["python3", "-I", os.path.join(reviewer_tree, ".github/scripts/run-local-gates.py")],
                        pr_tree, timeout, env)
    return {"status": "staged", "named_check": named, "gate_suite": gates}


def confirmed_from_github(pr, bot_login, default_branch, repository, gh):
    """Round records of `pr` that confirm_record() accepts, oldest first.
    `gh(args)` returns parsed JSON for a `gh api` path (None on failure,
    which fails the record closed)."""
    comments = gh(["repos/{0}/issues/{1}/comments".format(repository, pr), "--paginate", "--slurp"])
    if comments is None:
        raise GhReadError("comments read failed")
    flat = [c for page in comments for c in (page if isinstance(page, list) else [page])]
    confirmed = []
    for record in parse_records(flat, bot_login):
        run_id = str(record.get("run_id") or "")
        if not run_id.isdigit():
            continue
        try:
            run = gh(["repos/{0}/actions/runs/{1}".format(repository, run_id)])
        except GhNotFound:
            continue  # a real 404: the run does not exist, so unconfirmed
        arts = gh(["repos/{0}/actions/runs/{1}/artifacts".format(repository, run_id)])
        if not isinstance(run, dict) or arts is None:
            raise GhReadError("run or artifacts read failed for run " + run_id)
        run = dict(run)
        run["repository"] = (run.get("repository") or {}).get("full_name") or repository
        run["artifacts"] = [a.get("name") for a in (arts or {}).get("artifacts", [])]
        run["referenced_workflows"] = [w.get("path") for w in run.get("referenced_workflows") or []]
        if confirm_record(record, run, default_branch, repository):
            confirmed.append(record)
    return confirmed


class GhReadError(RuntimeError):
    """A GitHub read failed: the round stops rather than counting zero."""


class GhNotFound(GhReadError):
    pass


def _gh_api(args):
    import subprocess
    proc = subprocess.run(["gh", "api"] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        if "404" in (proc.stderr or "") or "Not Found" in (proc.stderr or ""):
            raise GhNotFound(args[0])
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


# ------------------------------------------------------------------ CLI ---

def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("guard")
    g.add_argument("--ref"); g.add_argument("--default-branch"); g.add_argument("--kind")
    g.add_argument("--paused", default="")
    p = sub.add_parser("prepare")
    p.add_argument("--pr", required=True); p.add_argument("--body-file", required=True)
    p.add_argument("--head-branch", default=""); p.add_argument("--labels", default="")
    s = sub.add_parser("state")
    s.add_argument("--pr", required=True); s.add_argument("--bot-login", required=True)
    s.add_argument("--default-branch", required=True); s.add_argument("--repository", required=True)
    s.add_argument("--budget", default=str(DEFAULT_BUDGET))
    c = sub.add_parser("code-run")
    c.add_argument("--pr-tree", required=True); c.add_argument("--reviewer-tree", required=True)
    c.add_argument("--added-files", required=True)
    r = sub.add_parser("record")
    r.add_argument("--input", required=True)
    r.add_argument("--handoff", action="store_true")
    f = sub.add_parser("finalize")
    for name in ("state", "find", "check", "code-run", "purpose", "dismissals"):
        f.add_argument("--" + name, default=None)
    f.add_argument("--head-sha", required=True); f.add_argument("--run-id", required=True)
    f.add_argument("--reviewer-commit", required=True); f.add_argument("--pr-state", default="open")
    v = sub.add_parser("validate-output")
    v.add_argument("--input", required=True)
    v.add_argument("--role", required=True, choices=("find", "check"))
    v.add_argument("--memory", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "guard":
        ok, reason = guard(args.ref, args.default_branch, args.kind, args.paused)
        print(json.dumps({"proceed": ok, "reason": reason}))
        # A refusal is a decision, not a failure: the workflow reads `proceed`.
        return 0
    if args.cmd == "prepare":
        with open(args.body_file, encoding="utf-8") as fh:
            body = fh.read()
        labels = [x for x in args.labels.split(",") if x]
        print(json.dumps({"kind": derive_kind(args.head_branch, labels),
                          "purpose_source": resolve_purpose_source(args.pr, body)}))
        return 0
    if args.cmd == "finalize":
        def opt(path):
            try:
                return _load(path) if path else None
            except (OSError, ValueError):
                return None
        record = finalize_round(opt(args.state) or {}, opt(args.find), opt(args.check), opt(args.code_run),
                                opt(args.purpose), args.head_sha,
                                (lambda d: d if isinstance(d, list) else [])(opt(args.dismissals)),
                                args.run_id, args.reviewer_commit, args.pr_state)
        print(build_record(record))
        return 0
    if args.cmd == "state":
        confirmed = confirmed_from_github(args.pr, args.bot_login, args.default_branch,
                                          args.repository, _gh_api)
        spent, budget = budget_spent(confirmed, args.budget)
        print(json.dumps({"rounds": len(confirmed), "round": len(confirmed) + 1, "budget": budget,
                          "spent": spent, "open_set": open_set(fold_open_set(confirmed)),
                          "prior": fold_open_set(confirmed), "confirmed": confirmed}))
        return 0
    if args.cmd == "code-run":
        with open(args.added_files, encoding="utf-8") as fh:
            added = [line.strip() for line in fh if line.strip()]
        print(json.dumps(stage_code_run(args.pr_tree, args.reviewer_tree, added)))
        return 0
    if args.cmd == "validate-output":
        try:
            data = _load(args.input)
        except (OSError, ValueError):
            data = None
        prior, problems = None, []
        if args.memory:
            try:
                prior = _load(args.memory).get("prior")
            except (OSError, ValueError, AttributeError):
                problems.append("the round's memory could not be read")
        problems += validate_output(data, args.role, prior)
        print(json.dumps({"ok": not problems, "problems": problems}))
        return 1 if problems else 0
    print(build_record(_load(args.input), handoff=args.handoff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
