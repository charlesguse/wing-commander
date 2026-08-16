"""A `gh` stub backed by a JSON state file ($GH_STATE).

Implements only the subcommands auto-update-spec-kit.yml actually calls, with
real semantics (issues have bodies/labels/comments/state; edits mutate them),
so the settle state machine and the act/comment-reply branches can be executed
rather than desk-read. Every invocation is appended to $GH_CALLS.

State shape:
  {"issues": {"7": {"number":7,"state":"open","title":..,"body":..,
                    "labels":[..],"comments":[{"id":..,"body":..,"user":..}]}},
   "prs": {"12": {"number":12,"title":..,"body":..,"url":..,"merged":bool}},
   "labels": [...],
   "releases_file": "/path/to/releases.json",
   "default_branch": "main",
   "next_issue": 100, "next_pr": 200}
"""
import json
import os
import shutil
import subprocess
import sys

STATE = os.environ["GH_STATE"]
CALLS = os.environ.get("GH_CALLS")


def load():
    with open(STATE, encoding="utf-8") as fh:
        s = json.load(fh)
    s.setdefault("issues", {})
    s.setdefault("prs", {})
    s.setdefault("labels", [])
    s.setdefault("default_branch", "main")
    s.setdefault("next_issue", 100)
    s.setdefault("next_pr", 200)
    return s


def save(s):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)


def log(argv):
    if CALLS:
        with open(CALLS, "a", encoding="utf-8") as fh:
            fh.write(" ".join(argv) + "\n")


def opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def body_of(argv):
    """--body TEXT or --body-file PATH"""
    bf = opt(argv, "--body-file")
    if bf:
        with open(bf, encoding="utf-8") as fh:
            return fh.read()
    return opt(argv, "--body", "")


def jq(data_str, expr):
    """Delegate --jq to the real jq binary so filter semantics are authentic.

    Must hard-fail rather than return empty: a silently-missing jq turns every
    `gh ... --jq` read into "" and the suites then fail in a dozen confusing
    places instead of one obvious one.
    """
    jq_bin = os.environ.get("WC_JQ") or shutil.which("jq")
    if not jq_bin:
        sys.stderr.write("gh stub: jq not found on PATH (set WC_JQ to override)\n")
        raise SystemExit(2)
    p = subprocess.run([jq_bin, "-r", expr], input=data_str,
                       capture_output=True, text=True)
    sys.stderr.write(p.stderr)
    if p.returncode != 0:
        raise SystemExit(2)
    return p.stdout


def emit(data_obj, argv):
    """Print JSON, applying --jq if present."""
    s = json.dumps(data_obj)
    if "--jq" in argv:
        sys.stdout.write(jq(s, opt(argv, "--jq")))
    else:
        sys.stdout.write(s)


PAGE_SIZE = 30


def emit_paginated(data_list, argv):
    """Print JSON the way real `gh api ... --paginate` does: split into
    PAGE_SIZE-item pages and call emit() once per page, writing directly to
    stdout with no added separator between pages — reproducing the N
    concatenated JSON documents shape --jq produces across real pagination
    (research.md D4, spec 036). Falls back to a single emit() when
    --paginate is absent, unchanged from before this feature."""
    if "--paginate" not in argv:
        emit(data_list, argv)
        return
    if not data_list:
        emit([], argv)
        return
    for i in range(0, len(data_list), PAGE_SIZE):
        emit(data_list[i:i + PAGE_SIZE], argv)


def issue_json(iss, fields):
    """Project an issue onto --json fields using REAL gh output shapes.

    `labels` in particular is a list of OBJECTS in gh's output, not a list of
    strings. The stub stores plain strings internally (every assertion in the
    suites reads them that way), so the object shape is put on here — at the
    boundary the workflow actually parses. A stub that returns strings would
    let `.labels[]?.name` silently evaluate to empty and pass.

    `state` is UPPERCASE in `gh issue view --json state` (the GraphQL
    IssueState enum) but lowercase in `gh search issues --json state` — the
    same split rebase.yml:783 and watchdog.yml:1676 both comment on. The stub
    stores lowercase internally, so the case is put on here, at the `issue
    view` boundary only. Nothing in this stage reads it today (the sweep that
    did was removed with the scratch-repository lifecycle), but a stub that
    hands back the wrong case is a trap: the reaper that DID read it compared
    against "OPEN", so a lowercase stub made every issue look closed and the
    fixture-passing fix would have been to break the workflow instead.
    """
    out = {}
    for f in fields:
        if f == "labels":
            out[f] = [{"name": l} for l in iss.get("labels", [])]
        elif f == "comments":
            out[f] = [{"body": c["body"]} for c in iss.get("comments", [])]
        elif f == "state":
            out[f] = str(iss.get(f) or "").upper()
        else:
            out[f] = iss.get(f)
    return out


def pr_json(pr, fields):
    """Project a PR onto --json fields using REAL gh output shapes.

    `headRefName` is `gh`'s field name; the stub stores it as `head` (the
    same key `pr create` already writes and `--head` already filters on).
    Every stub PR is implicitly open (no closed-PR modelling exists — see
    `sub == "list"` below), so `state` is fixed at "OPEN".
    """
    out = {}
    for f in fields:
        if f == "headRefName":
            out[f] = pr.get("head")
        elif f == "state":
            out[f] = "OPEN"
        else:
            out[f] = pr.get(f)
    return out


def maybe_fail(argv):
    """Simulate an API failure for a subcommand named in $GH_STUB_FAIL.

    Comma-separated selectors; a selector matches when ALL of its
    whitespace-separated tokens appear in argv. Token-subset rather than
    prefix matching so sibling calls can be told apart — settle makes two
    `gh issue list` calls and the tests need to fail either one alone:
      "issue list"            -> both
      "issue list --label"    -> only the labelled lookup
      "issue list 200"        -> only the migration scan (--limit 200)

    The settle lookup has a failure branch that decides whether a duplicate
    issue gets filed. Without injection that branch can only be desk-read,
    which is exactly how #167 shipped.
    """
    spec = os.environ.get("GH_STUB_FAIL", "").strip()
    if not spec:
        return False
    have = set(argv)
    for sel in (p.strip() for p in spec.split(",")):
        if sel and set(sel.split()).issubset(have):
            sys.stderr.write("gh: injected failure for '%s' (GH_STUB_FAIL)\n" % sel)
            return True
    return False


def main():
    argv = sys.argv[1:]
    log(sys.argv)
    if maybe_fail(argv):
        return 1
    s = load()
    cmd = argv[0] if argv else ""

    # ---- gh api ---------------------------------------------------------
    if cmd == "api":
        path = argv[1]
        if "spec-kit/releases" in path:
            rf = s.get("releases_file")
            data = json.load(open(rf, encoding="utf-8")) if rf else []
            emit_paginated(data, argv)
            return 0
        if "/issues/comments/" in path:
            cid = path.rstrip("/").split("/")[-1]
            for iss in s["issues"].values():
                for c in iss.get("comments", []):
                    if str(c.get("id")) == str(cid):
                        emit({"body": c.get("body", ""),
                              "user": {"login": c.get("user", "someone")}}, argv)
                        return 0
            sys.stderr.write("gh: comment not found\n")
            return 1
        sys.stderr.write("gh stub: unhandled api path %s\n" % path)
        return 1

    # ---- gh repo view ---------------------------------------------------
    # Every repository is treated as existing and visible. The e2e-stage's
    # not-visible branch is exercised with GH_STUB_FAIL="repo view" instead
    # of a repository registry: this feature no longer creates or deletes
    # repositories, so there is no repository state for the stub to model.
    if cmd == "repo" and argv[1] == "view":
        emit({"defaultBranchRef": {"name": s["default_branch"]}}, argv)
        return 0

    # ---- gh search issues ----------------------------------------------
    if cmd == "search" and argv[1] == "issues":
        query = next((a for a in argv[2:] if not a.startswith("--")
                      and a != opt(argv, "--repo") and a != opt(argv, "--json")), "")
        # emulate `"phrase" in:body` matching
        phrase = query.split('"')[1] if '"' in query else query
        hits = [i for i in s["issues"].values() if phrase in i.get("body", "")]
        fields = (opt(argv, "--json") or "number,state,body").split(",")
        emit([{f: i.get(f) for f in fields} for i in hits], argv)
        return 0

    # ---- gh issue ------------------------------------------------------
    if cmd == "issue":
        sub = argv[1]
        if sub == "create":
            n = s["next_issue"]; s["next_issue"] = n + 1
            labels = [l for a, l in zip(argv, argv[1:]) if a == "--label"]
            s["issues"][str(n)] = {"number": n, "state": "open",
                                   "title": opt(argv, "--title", ""),
                                   "body": body_of(argv), "labels": labels,
                                   "comments": []}
            save(s)
            print("https://github.com/%s/issues/%d" % (os.environ.get("GITHUB_REPOSITORY", "o/r"), n))
            return 0
        num = argv[2]
        iss = s["issues"].get(str(num))
        if sub == "view":
            if not iss:
                sys.stderr.write("gh: issue not found\n"); return 1
            fields = (opt(argv, "--json") or "body").split(",")
            emit(issue_json(iss, fields), argv)
            return 0
        if sub == "edit":
            if not iss:
                sys.stderr.write("gh: issue not found\n"); return 1
            if "--body-file" in argv or "--body" in argv:
                iss["body"] = body_of(argv)
            for a, l in zip(argv, argv[1:]):
                if a == "--add-label" and l not in iss["labels"]:
                    iss["labels"].append(l)
            save(s); return 0
        if sub == "comment":
            if not iss:
                sys.stderr.write("gh: issue not found\n"); return 1
            iss.setdefault("comments", []).append(
                {"id": 9000 + len(iss.get("comments", [])), "body": body_of(argv),
                 "user": os.environ.get("GH_STUB_ACTOR", "wing-commander[bot]")})
            save(s); return 0
        if sub == "list":
            label = opt(argv, "--label")
            state = opt(argv, "--state", "open")
            hits = [i for i in s["issues"].values()
                    if (state == "all" or i.get("state") == state)
                    and (label is None or label in i.get("labels", []))]
            # Newest first, then honour --limit: the settle migration scan
            # reasons about hitting its window, so the window has to be real.
            hits.sort(key=lambda i: i.get("number", 0), reverse=True)
            limit = opt(argv, "--limit")
            if limit:
                hits = hits[:int(limit)]
            fields = (opt(argv, "--json") or "number").split(",")
            emit([issue_json(i, fields) for i in hits], argv)
            return 0

    # ---- gh pr ---------------------------------------------------------
    if cmd == "pr":
        sub = argv[1]
        if sub == "create":
            n = s["next_pr"]; s["next_pr"] = n + 1
            url = "https://github.com/%s/pull/%d" % (os.environ.get("GITHUB_REPOSITORY", "o/r"), n)
            s["prs"][str(n)] = {"number": n, "title": opt(argv, "--title", ""),
                                "body": body_of(argv), "url": url,
                                "base": opt(argv, "--base"), "head": opt(argv, "--head"),
                                "mergedAt": None}
            save(s); print(url); return 0
        if sub == "list":
            head = opt(argv, "--head")
            # No PR in the stub is ever closed (no `pr close`/`pr merge`
            # mutator exists), so `--state closed` matches nothing and
            # `--state open`/`--state all` match everything — sufficient for
            # every scenario this feature's guard needs (research.md).
            state = opt(argv, "--state", "open")
            hits = [] if state == "closed" else list(s["prs"].values())
            if head is not None:
                hits = [p for p in hits if p.get("head") == head]
            fields = (opt(argv, "--json") or "number").split(",")
            emit([pr_json(p, fields) for p in hits], argv)
            return 0
        num = argv[2]
        pr = s["prs"].get(str(num))
        if sub == "view":
            if not pr:
                sys.stderr.write("gh: pr not found\n"); return 1
            fields = (opt(argv, "--json") or "body").split(",")
            emit(pr_json(pr, fields), argv)
            return 0

    # ---- gh label create ------------------------------------------------
    if cmd == "label" and argv[1] == "create":
        name = argv[2]
        if name not in s["labels"]:
            s["labels"].append(name); save(s)
        return 0

    sys.stderr.write("gh stub: unhandled command: %s\n" % " ".join(argv))
    return 1


if __name__ == "__main__":
    sys.exit(main())
