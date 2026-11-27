#!/usr/bin/env python3
"""Workflow-side glue for spec-pr-review.yml (spec 122): everything that
touches git, the filesystem or `gh`, so spec_pr_review.py stays pure.

    spec_pr_review_actions.py prepare   FINDINGS ACTIONS SPEC_DIR OUT
        Join the validated findings with the reviewer's per-finding action
        entries (by index), resolve each fix's precedent, and write OUT, the
        input of `spec_pr_review.py check-fixes`, plus OUT.items (the joined
        records the `apply` and `render` steps read).
    spec_pr_review_actions.py apply     CHECKED ITEMS SPEC_DIR
        Apply the pushable fixes (exact-text replacement) and append the
        pushable owner-decision markers to SPEC_DIR/spec.md, in the working
        tree. Prints {"fixes": n, "markers": n}.

The reviewer output is DATA (IX): an action entry that does not name an
existing finding index, or whose fix text is not found exactly once, is
dropped and its finding stays report-only. An out-of-scope finding
(spec_pr_review.in_scope) gets no fix and no marker: its item is class
`out-of-scope`, listed in the review and recorded for the plan stage only.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_pr_review import in_scope  # noqa: E402

CLASSES = ("unambiguous-error", "owner-decision")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _lines(path, ref=None):
    if ref:
        res = subprocess.run(["git", "show", "%s:%s" % (ref, path)],
                             capture_output=True, text=True)
        return res.stdout.splitlines() if res.returncode == 0 else None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return None


TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def _trusted_comment(raw):
    """An issue-comment precedent counts only when a trusted author wrote it
    on the lifecycle issue (SPEC_LIFECYCLE_ISSUE). Fails closed when unset."""
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(data, dict) or \
            data.get("author_association") not in TRUSTED_ASSOCIATIONS:
        return False
    issue = os.environ.get("SPEC_LIFECYCLE_ISSUE", "")
    if not issue:
        return False
    return str(data.get("issue_url", "")).endswith("/issues/" + issue)


def _in_spec_dir(path, spec_dir):
    """A relative path under SPEC_DIR with no `..` segment (FR-026: a head
    precedent lives in the spec's own files)."""
    base = spec_dir.strip("/")
    return (bool(base) and not path.startswith("/")
            and ".." not in path.split("/") and path.startswith(base + "/"))


def _plain(text):
    """Agent text bound for an App-authored comment must not open an HTML
    comment: the select job trusts the App's `<!-- spec-pr-review-stopped`
    / `-failed` markers, so a reviewer could otherwise forge one."""
    return str(text).replace("<!--", "&lt;!--")


def resolve_precedent(prec, spec_dir=""):
    if not isinstance(prec, dict):
        return {}
    kind, ref = prec.get("kind"), str(prec.get("ref") or "")
    out = {"kind": kind, "ref": ref, "resolved": False}
    if kind in ("default-branch", "head"):
        path, _, line = ref.rpartition(":")
        if kind == "head" and not _in_spec_dir(path, spec_dir):
            return out
        if path and line.isdigit() and int(line) >= 1:
            lines = _lines(path, "origin/main" if kind == "default-branch" else None)
            out["resolved"] = lines is not None and int(line) <= len(lines)
    elif kind == "issue-comment" and ref.isdigit():
        res = subprocess.run(
            ["gh", "api", "repos/%s/issues/comments/%s" % (
                os.environ.get("GITHUB_REPOSITORY", ""), ref)],
            capture_output=True, text=True)
        out["resolved"] = res.returncode == 0 and _trusted_comment(res.stdout)
    if out["resolved"] and kind in ("default-branch", "head"):
        # The cited line must carry content, not be blank.
        lines = _lines(path, "origin/main" if kind == "default-branch" else None)
        out["resolved"] = bool(lines[int(line) - 1].strip())
    return out


def prepare(findings_path, actions_path, spec_dir, out_path):
    findings = _load(findings_path)
    actions = _load(actions_path) if os.path.isfile(actions_path) else []
    by_index = {a.get("index"): a for a in actions
                if isinstance(a, dict) and isinstance(a.get("index"), int)}
    items, fixes = [], []
    for i, f in enumerate(findings):
        if not in_scope(f):
            # Report-only: no fix, no marker, no question (owner decision
            # 2026-11-27, #890). The item keeps its index so `apply` and
            # the join stay positional.
            items.append({"finding": dict(f, title=_plain(f.get("title", "")),
                                          what=_plain(f.get("what", ""))),
                          "class": "out-of-scope", "in_scope": False})
            continue
        act = by_index.get(i, {})
        # Doubtful classification is an owner decision (FR-015a).
        cls = act.get("class") if act.get("class") in CLASSES else "owner-decision"
        item = {"finding": f, "class": cls, "in_scope": True}
        if cls == "unambiguous-error":
            fx = act.get("fix") if isinstance(act.get("fix"), dict) else {}
            path = fx.get("path") or ""
            old, new = fx.get("old"), fx.get("new")
            text = None
            try:
                # Raw text, exactly as `apply` reads it, so both agree on
                # uniqueness (CRLF and multi-line old text included).
                with open(path, encoding="utf-8", newline="") as fh:
                    text = fh.read()
            except OSError:
                text = None
            if isinstance(old, str) and isinstance(new, str) and old \
                    and text is not None and text.count(old) == 1:
                item["fix"] = {"path": path, "old": old, "new": new}
                fixes.append({
                    "id": i, "finding": f.get("title"), "paths": [path], "kind": "fix",
                    "lines_changed": len(old.splitlines()) + len(new.splitlines()),
                    "precedent": resolve_precedent(act.get("precedent"), spec_dir)})
            else:
                item["class"] = cls = "owner-decision"
        if cls == "owner-decision":
            q = _plain(act.get("question") or f.get("what") or f.get("title") or "")
            item["question"] = q.replace("\n", " ").replace("]", ")")
            # Anything but a list is no options (a string would split into
            # characters, null would fail the round); the marker is then
            # blocked as question-incomplete.
            opts = act.get("options")
            item["options"] = [_plain(o) for o in opts][:4] if isinstance(opts, list) else []
            item["recommendation"] = _plain(act.get("recommendation") or "")
            if isinstance(f, dict) and "title" in f:
                item["finding"] = dict(f, title=_plain(f.get("title")))
            fixes.append({"id": i, "finding": f.get("title"),
                          "options_count": len(item["options"]),
                          "has_recommendation": bool(item["recommendation"].strip()),
                          "paths": [os.path.join(spec_dir, "spec.md")],
                          "kind": "marker",
                          "lines_changed": 1})
        items.append(item)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"spec_dir": spec_dir, "fixes": fixes}, fh)
    with open(out_path + ".items", "w", encoding="utf-8") as fh:
        json.dump(items, fh)
    return 0


def apply(checked_path, items_path, spec_dir):
    checked = _load(checked_path)
    ok = set(checked.get("pushable", []))
    n_fix = n_marker = 0
    marker_lines = []
    for idx, item in enumerate(_load(items_path)):
        if idx not in ok:
            continue
        if item["class"] == "unambiguous-error":
            path = item["fix"]["path"]
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
            if text.count(item["fix"]["old"]) != 1:
                # A pushable fix that cannot be applied must fail loud, not be
                # skipped and then announced as ready.
                sys.stderr.write("spec_pr_review_actions: fix for %r no longer "
                                 "matches exactly once\n" % item["finding"].get("title"))
                return 1
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text.replace(item["fix"]["old"], item["fix"]["new"]))
            n_fix += 1
        else:
            marker_lines.append("[NEEDS CLARIFICATION: %s]" % item["question"])
            n_marker += 1
    if marker_lines:
        with open(os.path.join(spec_dir, "spec.md"), "a", encoding="utf-8") as fh:
            fh.write("\n" + "\n".join(marker_lines) + "\n")
    json.dump({"fixes": n_fix, "markers": n_marker}, sys.stdout)
    sys.stdout.write("\n")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) == 5 and argv[0] == "prepare":
            return prepare(*argv[1:])
        if len(argv) == 4 and argv[0] == "apply":
            return apply(*argv[1:])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write("spec_pr_review_actions: %s\n" % exc)
        return 1
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
