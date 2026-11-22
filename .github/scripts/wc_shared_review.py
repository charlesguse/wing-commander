#!/usr/bin/env python3
"""The shared PR reviewer's deterministic half (specs/127-shared-pr-reviewer).

Everything that gates a durable record is code here, not agent text
(Principle IX): the round record and its marker, finding identity, the
FR-015 transition table, the open-set fold, the blocking rule, the verdict,
request validation, run confirmation, the round budget and the hand-off.
shared-pr-reviewer.yml stays thin and calls the CLI at the bottom.

Gate registration (T002, research D3): wc_published_stages.published_stages()
derives "published" as every workflow declaring on.workflow_call, with no
exclusion form. An unpublished callable needs one added to that derivation
(see UNPUBLISHED_REASON for the reason string); until it exists the callable
is not registered as unpublished (T020).

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
UNPUBLISHED_REASON = "internal callable of the report-only shared reviewer (spec 127), not published"
MAX_RECORD_CHARS = 20000
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
    was dropped); `open_set` is never truncated."""
    payload = dict(record)
    payload.setdefault("schema", SCHEMA)
    payload.setdefault("reviewer", REVIEWER)
    if handoff:
        payload["kind"] = "handoff"
        payload.pop("verdict", None)
    findings = list(payload.get("findings") or [])
    payload["findings"] = findings
    dropped = 0
    while len(_marker(payload)) > MAX_RECORD_CHARS and payload["findings"]:
        payload["findings"].pop()
        dropped += 1
        payload["findings_truncated"] = dropped
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
    for d in dismissals or []:
        fid = (d or {}).get("id")
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
    check_for = {}
    for c in checks or []:
        if isinstance(c, dict):
            check_for[c.get("id") or c.get("key")] = c
    notes, serial = [], 0

    def settle(f, c):
        f["in_scope"] = c.get("in_scope") is True
        f["reachable"] = c.get("reachable") is True

    for cand in candidates or []:
        c = check_for.get(cand.get("key")) or {}
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
        if f.get("status") not in OPEN_STATUSES or not fid in check_for or fid.startswith("F%d-" % round_no):
            continue
        c = check_for[fid]
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
    `open_set` and `findings` carry the statuses; later rounds win."""
    state = {}
    for rec in sorted(confirmed_rounds, key=lambda r: r["round"]):
        for f in (rec.get("findings") or []) + (rec.get("open_set") or []):
            if isinstance(f, dict) and f.get("id"):
                state[f["id"]] = f
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
    return "fix"


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
    r = sub.add_parser("record")
    r.add_argument("--input", required=True)
    r.add_argument("--handoff", action="store_true")
    v = sub.add_parser("validate-output")
    v.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "guard":
        ok, reason = guard(args.ref, args.default_branch, args.kind, args.paused)
        print(json.dumps({"proceed": ok, "reason": reason}))
        return 0 if ok else 0
    if args.cmd == "prepare":
        with open(args.body_file, encoding="utf-8") as fh:
            body = fh.read()
        labels = [x for x in args.labels.split(",") if x]
        print(json.dumps({"kind": derive_kind(args.head_branch, labels),
                          "purpose_source": resolve_purpose_source(args.pr, body)}))
        return 0
    if args.cmd == "validate-output":
        data = _load(args.input)
        ok = isinstance(data, dict) and isinstance(data.get("candidates", data.get("checks", [])), list)
        print(json.dumps({"ok": ok}))
        return 0 if ok else 1
    print(build_record(_load(args.input), handoff=args.handoff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
