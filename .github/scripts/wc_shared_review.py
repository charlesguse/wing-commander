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
        # An omitted flag keeps the previous value (never silently clears a
        # blocking finding); validate_output requires both on upheld/confirmed.
        for k in ("in_scope", "reachable"):
            if isinstance(c.get(k), bool):
                f[k] = c[k]
            else:
                f[k] = f.get(k) is True

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
        seen_keys = set()
        for n, c in enumerate(items):
            if not isinstance(c, dict):
                problems.append("candidate {0} is not an object".format(n))
                continue
            for k in ("key", "title", "file"):
                if not _nonempty_str(c.get(k)):
                    problems.append("candidate {0} has no {1}".format(n, k))
            if _nonempty_str(c.get("key")):
                if c["key"] in seen_keys:
                    problems.append("candidate {0} repeats key {1!r}".format(n, c["key"]))
                seen_keys.add(c["key"])
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
        # An upheld candidate is new, so its flags must be stated. A
        # confirmed recheck may omit them: settle() keeps the previous
        # flags, and a recheck that needed missing code-run results
        # (FR-010) cannot restate them.
        if c.get("outcome") == "upheld":
            for k in ("in_scope", "reachable"):
                if not isinstance(c.get(k), bool):
                    problems.append("check {0} {1} is required (boolean) when outcome is {2}".format(
                        n, k, c.get("outcome")))
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
                   run_id, reviewer_commit, pr_state, agent_ok=True, pr_kind="fix"):
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
    answers = dict((check_out or {}).get("answers") or {})
    if check_out is not None:
        # FR-008(c) is answered from the staged results where code can
        # decide it, whatever the agent said.
        decided, why = check_fails_without_fix(code_run)
        if decided is not None:
            if answers.get("check_fails_without_fix") != decided:
                more.append("check_fails_without_fix is {0} by code: {1}".format(decided, why))
            answers["check_fails_without_fix"] = decided
        elif why:
            more.append("check_fails_without_fix left to the checking job: " + why)
    opened = open_set(findings)
    for f in opened:
        f["blocking"] = is_blocking(f)
        f["non_blocking_rule"] = non_blocking_rule(f)
    verdict = compute_verdict(agent_ok, opened, answers, code_status, has_purpose=bool(purpose))
    return {"schema": SCHEMA, "reviewer": REVIEWER, "pr_kind": pr_kind or "fix", "round": round_no,
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
    path = named_check_file(added_files)
    return named_check_argv(path) if path else None


def named_check_argv(path):
    base = path.rsplit("/", 1)[-1]
    if re.fullmatch(r"verify-[\w.-]+\.py", base):
        return ["python3", "-I", path]
    if re.fullmatch(r"test_[\w.-]+\.py", base):
        # discover puts the file's directory on sys.path, which -I
        # otherwise leaves out.
        return ["python3", "-I", "-m", "unittest", "discover", "-v",
                "-s", path.rsplit("/", 1)[0] if "/" in path else ".", "-p", base]
    return ["bash", path]


def named_check_file(added_files, modified_files=None):
    """The path of the change's named check, or None.

    Preference order, deterministic: an ADDED file first, else a MODIFIED
    one (a fix usually extends an existing test or verify script, R1), each
    tier in sorted order. Its run without the fix overlays the PR's version
    of that one file on the merge-base tree, so a modified check runs its
    new case against the unfixed code.

    The change's own check is a test the change adds to exercise its fix,
    not a file it adds as test data: a path under a `fixtures` directory or
    a spec's directory is never chosen. A path component starting with `-`
    is refused, so no part of the path reads as an option to the runner."""
    for path in sorted(added_files or []) + sorted(modified_files or []):
        parts = path.split("/")
        if ".." in parts or path.startswith("/") or any(p.startswith("-") for p in parts):
            continue
        if "fixtures" in parts[:-1] or parts[0] == "specs":
            continue
        base = path.rsplit("/", 1)[-1]
        if re.fullmatch(r"(verify-[\w.-]+|test_[\w.-]+)\.py", base) or base == "run-tests.sh":
            return path
    return None


# The PR's code runs as this throwaway system user, never as the runner's
# own user (FR-012, SC-008(b)). Being another uid is the boundary: that user
# cannot write the runner's files (the staged result, GITHUB_ENV,
# GITHUB_OUTPUT, GITHUB_STEP_SUMMARY), cannot read the runner's processes'
# environments, holds no sudo, and every process it owns, detached or not,
# is killed before the result is written.
SANDBOX_USER = "wc-code-run"
SANDBOX_ENV_PATH = "/usr/local/bin:/usr/bin:/bin"
KILL_ATTEMPTS = 50
# Processes the sandbox user may have at once (RLIMIT_NPROC counts by real
# uid), so a fork bomb cannot exhaust the runner's pids (P2).
SANDBOX_NPROC = 4096


class SandboxUnavailable(RuntimeError):
    """The code-run sandbox cannot be set up here: nothing of the PR runs."""


def _sh(argv, **kw):
    import subprocess
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("capture_output", True)
    return subprocess.run(argv, **kw)


class UidSandbox:
    """Runs PR code as SANDBOX_USER through passwordless sudo (GitHub-hosted
    Linux runners). Each command gets a fresh copy of the PR tree, extracted
    by the sandbox user itself so nothing is chowned by root, and writes its
    output to a runner-private file through an inherited descriptor. After
    the command, every process of the sandbox user is killed and the kill
    is confirmed before the output is read."""

    def __init__(self, user=SANDBOX_USER, origin_url=None):
        self.user = user
        self.origin_url = origin_url
        self.work = self.private = self.reviewer = None

    def _sudo(self, *argv, **kw):
        return _sh(["sudo", "-n"] + list(argv), **kw)

    def _check_host(self):
        import shutil
        if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
            raise SandboxUnavailable("needs a non-root POSIX runner user")
        for tool in ("sudo", "tar", "env", "pkill", "ps", "install", "prlimit", "git"):
            if not shutil.which(tool):
                raise SandboxUnavailable("{0} is not installed".format(tool))
        if self._sudo("true").returncode != 0:
            raise SandboxUnavailable("passwordless sudo is not available")
        if _sh(["id", "-u", self.user]).returncode != 0:
            made = self._sudo("useradd", "--system", "--no-create-home", "--home-dir", "/nonexistent",
                              "--user-group", "--shell", "/usr/sbin/nologin", self.user)
            if made.returncode != 0:
                raise SandboxUnavailable("could not create " + self.user)
        groups = _sh(["id", "-nG", self.user]).stdout.decode().split()
        if groups != [self.user]:
            raise SandboxUnavailable("{0} is in groups {1}".format(self.user, groups))
        listed = self._sudo("-l", "-U", self.user)
        if b"not allowed" not in listed.stdout + listed.stderr:
            raise SandboxUnavailable(self.user + " may run sudo")

    def open(self, pr_tree, reviewer_tree):
        import shutil
        import tempfile
        self._check_host()
        self.pr_tree = pr_tree
        # work/: runner-owned 0755, so the sandbox user can enter but never
        # create, rename or remove an entry in it. private/: runner-only.
        self.work = tempfile.mkdtemp(prefix="wc-code-run-")
        os.chmod(self.work, 0o755)
        self.private = tempfile.mkdtemp(prefix="wc-code-run-out-")
        # The default branch's gate runner: readable, never writable, by the
        # sandbox user, so the named check cannot rewrite it.
        self.reviewer = os.path.join(self.work, "reviewer")
        shutil.copytree(reviewer_tree, self.reviewer, symlinks=True)
        for root, dirs, files in os.walk(self.reviewer):
            for name in dirs:
                os.chmod(os.path.join(root, name), 0o755)
            for name in files:
                path = os.path.join(root, name)
                if not os.path.islink(path):
                    os.chmod(path, 0o755 if os.access(path, os.X_OK) else 0o644)
        os.chmod(self.reviewer, 0o755)
        self._kill_all()
        return self

    def gate_runner(self):
        return os.path.join(self.reviewer, ".github", "scripts", "run-local-gates.py")

    def live_pids(self):
        """Processes of the sandbox user that can still run code. A zombie
        (state Z) is dead and only waits to be reaped by its new parent,
        which a container's bare PID 1 may never do, so it does not count.
        Matched by effective OR real uid (-u, -U), so a sandbox process
        running a setuid program is still listed."""
        listed = self._sudo("ps", "-o", "pid=,stat=", "-u", self.user, "-U", self.user)
        if listed.returncode not in (0, 1):
            raise SandboxUnavailable("cannot list the processes of " + self.user)
        live = []
        for line in listed.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and not parts[1].startswith("Z"):
                live.append(int(parts[0]))
        return live

    def _kill_all(self):
        import time
        for _ in range(KILL_ATTEMPTS):
            # -u matches the effective uid only, -U the real uid only.
            self._sudo("pkill", "-KILL", "-u", self.user)
            self._sudo("pkill", "-KILL", "-U", self.user)
            if not self.live_pids():
                return
            time.sleep(0.1)
        raise SandboxUnavailable("processes of {0} survived the kill".format(self.user))

    def _fresh_tree(self, n, src=None, overlay=()):
        """A fresh copy of `src` (the PR tree by default), owned by the
        sandbox user, with each path in `overlay` copied over it from the
        PR tree, and made a git repository."""
        import subprocess
        tree = os.path.join(self.work, "tree-{0}".format(n))
        home = os.path.join(self.work, "home-{0}".format(n))
        for path in (tree, home):
            if self._sudo("install", "-d", "-o", self.user, "-g", self.user, "-m", "0700", path).returncode:
                raise SandboxUnavailable("could not create " + path)
        copies = [(src or self.pr_tree, ["."])]
        if overlay:
            copies.append((self.pr_tree, ["--"] + list(overlay)))
        for root, members in copies:
            pack = subprocess.Popen(["tar", "-C", root, "-cf", "-"] + members, stdout=subprocess.PIPE)
            unpack = self._sudo("-u", self.user, "--", "tar", "-C", tree, "-xf", "-", stdin=pack.stdout)
            pack.stdout.close()
            if pack.wait() != 0 or unpack.returncode != 0:
                raise SandboxUnavailable("could not copy a tree for " + self.user)
        self._git_init(tree, home)
        return tree, home

    def _git_init(self, tree, home):
        """The copy is an archive with no .git, and gates that find the
        repository root through git (git rev-parse --show-toplevel) read
        `/` without one (A4). The sandbox user makes it a repository with
        one commit, so the root resolves to the copy, and gives it the
        repository's own URL as `origin` for gates that read OWNER/NAME from
        the remote (provision-e2e-target.sh). Nothing is fetched or pushed,
        no credential is configured and no hook runs."""
        git = ["sudo", "-n", "-u", self.user, "--", "env", "-i", "PATH=" + SANDBOX_ENV_PATH,
               "HOME=" + home, "LANG=C.UTF-8", "GIT_CONFIG_NOSYSTEM=1",
               "git", "-C", tree, "-c", "init.defaultBranch=main", "-c", "user.name=" + self.user,
               "-c", "user.email={0}@localhost".format(self.user), "-c", "commit.gpgsign=false",
               "-c", "core.hooksPath=/dev/null"]
        steps = [["init", "-q"], ["add", "-A"], ["commit", "-q", "--no-verify", "--allow-empty",
                                                 "-m", "code-run tree"]]
        if self.origin_url:
            steps.append(["remote", "add", "origin", self.origin_url])
        for args in steps:
            if _sh(git + args).returncode != 0:
                raise SandboxUnavailable("could not make the PR tree a git repository")

    def run(self, argv, timeout, n, src=None, overlay=()):
        import subprocess
        tree, home = self._fresh_tree(n, src, overlay)
        log = os.path.join(self.private, "out-{0}.log".format(n))
        env = ["PATH=" + SANDBOX_ENV_PATH, "HOME=" + home, "TMPDIR=" + home,
               "LANG=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1"]
        with open(log, "wb") as fh:
            proc = subprocess.Popen(["sudo", "-n", "-u", self.user, "--", "prlimit",
                                     "--nproc={0}:{0}".format(SANDBOX_NPROC), "--",
                                     "env", "-i", "-C", tree]
                                    + env + list(argv),
                                    stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
            timed_out = False
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out, code = True, 124
            # Detached and background processes die here, before anything
            # is read: none outlives the command.
            self._kill_all()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._sudo("kill", "-KILL", str(proc.pid))
                proc.wait(timeout=30)
        with open(log, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_CHARS * 4))
            out = fh.read().decode("utf-8", "replace")
        if timed_out:
            out += "\ntimed out after {0}s".format(timeout)
        self._sudo("rm", "-rf", "--one-file-system", tree, home)
        return {"exit": code, "output_tail": out[-TAIL_CHARS:]}

    def close(self):
        """Kill and clean up whatever went wrong before (P2): an OSError
        from a fork that failed, or any other exception, still gets the
        kill attempted and the copies removed, and close never raises."""
        import shutil
        if self.work:
            try:
                self._kill_all()
            except Exception:  # noqa: BLE001 -- close must not raise
                pass
            try:
                self._sudo("rm", "-rf", "--one-file-system", self.work)
            except Exception:  # noqa: BLE001
                pass
        if self.private:
            shutil.rmtree(self.private, ignore_errors=True)


def stage_code_run(pr_tree, reviewer_tree, added_files, timeout=CODE_RUN_TIMEOUT, sandbox=None,
                   base_tree=None, origin_url=None, modified_files=None):
    """The two kinds of PR code the code-run job may run, nothing else, all
    inside `sandbox` (UidSandbox by default): the change's named check, on
    the PR tree and again without the fix (FR-008(c): on `base_tree`, the
    merge-base tree, with only the named check's own file taken from the
    PR), and the default branch's gate runner against the PR tree. Their
    exit codes are staged as data. When the sandbox cannot be set up, or a
    process survives it, nothing is staged: `missing`, never an unisolated
    run (FR-012)."""
    pr_tree, reviewer_tree = os.path.abspath(pr_tree), os.path.abspath(reviewer_tree)
    box = sandbox if sandbox is not None else UidSandbox(origin_url=origin_url)
    path = named_check_file(added_files, modified_files)
    argv = named_check_argv(path) if path else None
    try:
        box.open(pr_tree, reviewer_tree)
        named = box.run(argv, timeout, 1) if argv else None
        without = None
        if argv and base_tree and os.path.isdir(base_tree):
            without = box.run(argv, timeout, 3, src=os.path.abspath(base_tree), overlay=[path])
        gates = box.run(["python3", "-I", box.gate_runner()], timeout, 2)
    except Exception as exc:  # noqa: BLE001 -- any failure is `missing`, never a crash (P2)
        return {"status": "missing", "reason": "code-run sandbox: {0}: {1}".format(
            type(exc).__name__, exc)[:500]}
    finally:
        box.close()
    tier = None if not path else ("added" if path in (added_files or []) else "modified")
    return {"status": "staged", "named_check": named, "named_check_tier": tier,
            "named_check_without_fix": without, "gate_suite": gates}


def check_fails_without_fix(code_run):
    """FR-008(c) from the staged results, where code can decide it:
    (answer, why), or (None, None) to leave the answer to the check agent.

    Missing results, no named check, no run without the fix, or a run that
    timed out (124) or could not start (127) is not determinable; an
    ADDED named check that passes without the fix (exit 0) is negative,
    while a MODIFIED one that passes there is left to the agent, with a
    note, because the fix may change that file or a fixture it reads. Any
    other
    failure without the fix is for the agent to judge from the output: it
    is positive only if the check fails for the reason the fix addresses,
    not because a helper the PR also adds is absent."""
    if (code_run or {}).get("status") != "staged":
        return UNDETERMINABLE, "code-run results missing"
    if not code_run.get("named_check"):
        return UNDETERMINABLE, "the change adds or changes no named check"
    without = code_run.get("named_check_without_fix")
    if not isinstance(without, dict) or not isinstance(without.get("exit"), int):
        return UNDETERMINABLE, "the named check was not run without the fix"
    if without["exit"] == 0:
        if code_run.get("named_check_tier") == "modified":
            # A modified check can be a file the fix itself changes, or read
            # a fixture the overlay leaves at the fixed version, so passing
            # on the overlay tree is no evidence (N1): the agent judges.
            return None, ("the modified named check passes on the merge-base tree with its own "
                          "file overlaid; the fix may change that file or a fixture it reads, so "
                          "the checking job's answer stands")
        return NEGATIVE, "the named check passes without the fix"
    if without["exit"] in (124, 127):
        return UNDETERMINABLE, "the named check without the fix timed out or could not start"
    return None, None


LINK_NOTE = "symlink to: {0}\n"


def neutralise_links(root):
    """Replace every symbolic link under `root` with a plain file naming its
    target, and return how many were replaced (A1).

    `git archive | tar -x` writes a PR's symlinks out as symlinks, and
    actions/upload-artifact resolves a symlink to its target's content. A
    link to /proc/self/environ would upload the uploading step's runtime
    token; a link into the runner's _temp would upload that directory. So
    no tree leaves prepare with a link in it: a directory link is
    unlinked, never descended. The target is kept as data, so a reviewer
    still sees what the PR committed."""
    replaced = 0
    for top, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in list(dirs) + list(files):
            path = os.path.join(top, name)
            if not os.path.islink(path):
                continue
            target = os.readlink(path)
            os.unlink(path)
            with open(path, "w", encoding="utf-8", errors="replace") as fh:
                fh.write(LINK_NOTE.format(target))
            replaced += 1
            if name in dirs:
                dirs.remove(name)
    return replaced


def links_under(root):
    """Every symbolic link left under `root` (lstat, never followed)."""
    found = []
    for top, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in dirs + files:
            if os.path.islink(os.path.join(top, name)):
                found.append(os.path.join(top, name))
    return found


# Names Claude Code would load from a tree as instructions or settings
# (memory files, the .claude/ directory with its settings, rules, skills,
# agents and commands, and project MCP servers). Compared case-insensitively.
AGENT_CONFIG_NAMES = ("claude.md", "claude.local.md", ".claude", ".mcp.json")
AS_DATA = ".as-data"


def _agent_loadable(name):
    return name.lower() in AGENT_CONFIG_NAMES


def defuse_agent_config(root):
    """Rename, at every depth under `root`, everything an agent could load
    as its own configuration, so the PR's files reach the find and check
    agents only as data (P1, FR-027). The content stays readable under a
    `.as-data` name; a name already taken (a PR may ship one) gets a
    numbered suffix. Returns the renamed paths, relative to `root`."""
    renamed = []
    for top, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in list(dirs) + list(files):
            if not _agent_loadable(name):
                continue
            src = os.path.join(top, name)
            dst, n = src + AS_DATA, 1
            while os.path.lexists(dst):
                n += 1
                dst = "{0}{1}-{2}".format(src, AS_DATA, n)
            os.rename(src, dst)
            renamed.append(os.path.relpath(src, root))
            if name in dirs:
                dirs.remove(name)
    return renamed


def agent_config_left(root):
    """Everything under `root` an agent could still load (never followed)."""
    found = []
    for top, dirs, files in os.walk(root, topdown=True, followlinks=False):
        found += [os.path.join(top, name) for name in dirs + files if _agent_loadable(name)]
    return found


def write_private(path, text):
    """The staged result, written by the runner once the sandbox user has
    no process left, mode 0600."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


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
        if re.search(r"\(HTTP 404\)|^gh: Not Found", proc.stderr or "", re.M):
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
    c.add_argument("--out", required=True)
    c.add_argument("--base-tree", default=None)
    c.add_argument("--origin-url", default=None)
    c.add_argument("--modified-files", default=None)
    r = sub.add_parser("record")
    r.add_argument("--input", required=True)
    r.add_argument("--handoff", action="store_true")
    f = sub.add_parser("finalize")
    for name in ("state", "find", "check", "code-run", "purpose", "dismissals"):
        f.add_argument("--" + name, default=None)
    f.add_argument("--head-sha", required=True); f.add_argument("--run-id", required=True)
    f.add_argument("--reviewer-commit", required=True); f.add_argument("--pr-state", default="open")
    f.add_argument("--pr-kind", default="fix")
    da = sub.add_parser("defuse-agent-config")
    da.add_argument("--root", required=True)
    nl = sub.add_parser("neutralise-links")
    nl.add_argument("--root", required=True)
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
                                args.run_id, args.reviewer_commit, args.pr_state,
                                pr_kind=args.pr_kind)
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
        modified = []
        if args.modified_files:
            with open(args.modified_files, encoding="utf-8") as fh:
                modified = [line.strip() for line in fh if line.strip()]
        write_private(args.out, json.dumps(stage_code_run(args.pr_tree, args.reviewer_tree, added,
                                                         base_tree=args.base_tree,
                                                         origin_url=args.origin_url,
                                                         modified_files=modified)))
        return 0
    if args.cmd == "defuse-agent-config":
        renamed = defuse_agent_config(args.root)
        left = agent_config_left(args.root)
        print(json.dumps({"renamed": len(renamed), "left": [os.path.relpath(x, args.root) for x in left]}))
        return 1 if left else 0
    if args.cmd == "neutralise-links":
        replaced = neutralise_links(args.root)
        left = links_under(args.root)
        print(json.dumps({"replaced": replaced, "left": len(left)}))
        return 1 if left else 0
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
