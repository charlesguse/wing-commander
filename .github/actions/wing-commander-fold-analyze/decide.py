#!/usr/bin/env python3
"""Deterministic hold/dispatch decision for wing-commander-fold-analyze.

Reads the analyze agent's JSON (contracts/fold-analyze.md) and prints a JSON
object {decision, hold-reason, report-markdown, question-markdown}.

    decide.py --fold-id ID [--tasks N] [--input FILE | --failed]

`hold` iff a finding has category == constitution-conflict, or the check
failed or its output does not match the schema. Otherwise `dispatch`.
`skipped` when the fold section has no tasks (--tasks 0).
"""
import argparse
import json
import sys

CATEGORIES = {"constitution-conflict", "inconsistency", "duplication", "other"}
KEYS = ("severity", "category", "fold_task", "location", "principle", "detail")


def parse(text):
    """Return the findings list, or None when the output is invalid."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None
    for f in data["findings"]:
        if not isinstance(f, dict) or f.get("category") not in CATEGORIES:
            return None
        if any(not isinstance(f.get(k, ""), str) for k in KEYS):
            return None
    return data["findings"]


def report(findings):
    if not findings:
        return "Fold analyze: no findings."
    lines = ["Fold analyze findings:", ""]
    for f in findings:
        lines.append(
            "- [{}] {} -- task {} ({}): {}".format(
                f.get("severity", ""), f["category"], f.get("fold_task", ""),
                f.get("location", ""), f.get("detail", ""),
            )
        )
    return "\n".join(lines)


def decide(fold_id, tasks, text, failed):
    marker = "<!-- wing-commander-fold-hold: fold={} -->".format(fold_id)
    if tasks == 0:
        return {"decision": "skipped", "hold-reason": "",
                "report-markdown": "", "question-markdown": ""}
    findings = None if failed else parse(text)
    if findings is None:
        return {
            "decision": "hold", "hold-reason": "analyze-failed",
            "report-markdown": "",
            "question-markdown": (
                marker + "\nThe analyze check on fold `" + fold_id
                + "` failed or returned unusable output, so the fold is held "
                "before implement.\n\nOptions: proceed anyway, or retry the check."
            ),
        }
    conflicts = [f for f in findings if f["category"] == "constitution-conflict"]
    if not conflicts:
        return {"decision": "dispatch", "hold-reason": "",
                "report-markdown": report(findings), "question-markdown": ""}
    items = "\n".join(
        "- task {}: conflicts with {} -- {}".format(
            f.get("fold_task", ""), f.get("principle", "") or "(unnamed principle)",
            f.get("detail", ""))
        for f in conflicts
    )
    return {
        "decision": "hold", "hold-reason": "constitution-conflict",
        "report-markdown": report(findings),
        "question-markdown": (
            marker + "\nFold `" + fold_id + "` adds tasks that conflict with the "
            "constitution:\n\n" + items + "\n\nOptions: amend the spec, drop the "
            "fold task, or proceed anyway."
        ),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold-id", required=True)
    ap.add_argument("--tasks", type=int, default=1)
    ap.add_argument("--input", default="")
    ap.add_argument("--failed", action="store_true")
    a = ap.parse_args(argv)
    text = ""
    if a.input and not a.failed:
        try:
            with open(a.input, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            a.failed = True
    elif not a.input:
        a.failed = True
    json.dump(decide(a.fold_id, a.tasks, text, a.failed), sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
