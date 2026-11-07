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
dropped and its finding stays report-only.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


def resolve_precedent(prec):
    if not isinstance(prec, dict):
        return {}
    kind, ref = prec.get("kind"), str(prec.get("ref") or "")
    out = {"kind": kind, "ref": ref, "resolved": False}
    if kind in ("default-branch", "head"):
        path, _, line = ref.rpartition(":")
        if path and line.isdigit() and int(line) >= 1:
            lines = _lines(path, "origin/main" if kind == "default-branch" else None)
            out["resolved"] = lines is not None and int(line) <= len(lines)
    elif kind == "issue-comment" and ref.isdigit():
        res = subprocess.run(
            ["gh", "api", "repos/%s/issues/comments/%s" % (
                os.environ.get("GITHUB_REPOSITORY", ""), ref)],
            capture_output=True, text=True)
        out["resolved"] = res.returncode == 0
    return out


def prepare(findings_path, actions_path, spec_dir, out_path):
    findings = _load(findings_path)
    actions = _load(actions_path) if os.path.isfile(actions_path) else []
    by_index = {a.get("index"): a for a in actions
                if isinstance(a, dict) and isinstance(a.get("index"), int)}
    items, fixes = [], []
    for i, f in enumerate(findings):
        act = by_index.get(i, {})
        # Doubtful classification is an owner decision (FR-015a).
        cls = act.get("class") if act.get("class") in CLASSES else "owner-decision"
        item = {"finding": f, "class": cls}
        if cls == "unambiguous-error":
            fx = act.get("fix") if isinstance(act.get("fix"), dict) else {}
            path = fx.get("path") or ""
            old, new = fx.get("old"), fx.get("new")
            text = None
            lines = _lines(path)
            if lines is not None:
                text = "\n".join(lines) + "\n"
            if isinstance(old, str) and isinstance(new, str) and old \
                    and text is not None and text.count(old) == 1:
                item["fix"] = {"path": path, "old": old, "new": new}
                fixes.append({
                    "finding": f.get("title"), "paths": [path], "kind": "fix",
                    "lines_changed": len(old.splitlines()) + len(new.splitlines()),
                    "precedent": resolve_precedent(act.get("precedent"))})
            else:
                item["class"] = cls = "owner-decision"
        if cls == "owner-decision":
            q = str(act.get("question") or f.get("what") or f.get("title") or "")
            item["question"] = q.replace("\n", " ").replace("]", ")")
            item["options"] = [str(o) for o in act.get("options", [])][:4]
            item["recommendation"] = str(act.get("recommendation") or "")
            fixes.append({"finding": f.get("title"),
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
    for item in _load(items_path):
        title = item["finding"].get("title")
        if title not in ok:
            continue
        if item["class"] == "unambiguous-error":
            path = item["fix"]["path"]
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if text.count(item["fix"]["old"]) != 1:
                continue
            with open(path, "w", encoding="utf-8") as fh:
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
