#!/usr/bin/env python3
"""Fold-time analyze: deterministic prepare and decide steps around a
read-only agent verdict (specs/119-lifecycle-hold-label, FR-008..FR-016).

``prepare``  builds fold-input.json from the fold's own commits only.
``decide``   validates the agent verdict against that input and says whether
             to hold. The agent never decides; only well-formed objections
             that name a real principle and a real added task can hold.
"""
import argparse
import json
import re
import subprocess
import sys

TASK_LINE_RE = re.compile(r"^\+\s*-\s*\[[ xX]\]\s+(.*\S)\s*$")
HEADING_RE = re.compile(r"^#{2,4}\s+(.*\S)\s*$")


def added_tasks_from_diff(diff_text):
    """Return ``[{id, line}]`` for task lines added in a tasks.md diff.

    ``id`` is the task line text after the checkbox (the fold title line).
    Lines starting ``+++`` are file headers, not additions.
    """
    tasks = []
    seen = set()
    for raw in (diff_text or "").splitlines():
        if raw.startswith("+++"):
            continue
        m = TASK_LINE_RE.match(raw)
        if not m:
            continue
        title = m.group(1)
        if title in seen:
            continue
        seen.add(title)
        tasks.append({"id": title, "line": raw[1:].strip()})
    return tasks


def principles_from_constitution(text):
    """Principle headings: ``### I. Name`` style headings (roman/number led)."""
    out = []
    for raw in (text or "").splitlines():
        m = HEADING_RE.match(raw)
        if m and re.match(r"^(?:[IVXLC]+|\d+)[.)]\s", m.group(1)):
            out.append(m.group(1))
    return out


def build_input(base_sha, head_sha, diff_text, spec_md, constitution):
    return {
        "fold_base_sha": base_sha,
        "fold_head_sha": head_sha,
        "added_tasks": added_tasks_from_diff(diff_text),
        "spec_md": spec_md,
        "constitution": constitution,
        "principles": principles_from_constitution(constitution),
    }


def decide(fold_input, verdict):
    """Return ``{hold, held_items, recorded_items, status, first_attempt?}``.

    ``verdict`` is the parsed agent JSON, or None when the artifact was
    missing/unparseable (``agent-failed``).
    """
    result = {"hold": False, "held_items": [], "recorded_items": [],
              "status": "ok"}
    if verdict is None:
        result["status"] = "agent-failed"
        return result
    objections = verdict.get("objections") if isinstance(verdict, dict) else None
    if not isinstance(objections, list):
        result["status"] = "malformed"
        return result
    ids = {t["id"] for t in fold_input.get("added_tasks", [])}
    principles = set(fold_input.get("principles", []))
    for obj in objections:
        well_formed = (
            isinstance(obj, dict)
            and isinstance(obj.get("task"), str)
            and isinstance(obj.get("constitution_conflict"), bool)
            and isinstance(obj.get("reasoning"), str)
            and (obj.get("principle") is None or isinstance(obj.get("principle"), str))
        )
        if not well_formed:
            result["status"] = "malformed"
            result["held_items"] = []
            result["hold"] = False
            return result
        valid_hold = (obj["constitution_conflict"] and obj["principle"] in principles
                      and obj["task"] in ids)
        (result["held_items"] if valid_hold else result["recorded_items"]).append(obj)
    result["hold"] = bool(result["held_items"])
    return result


def is_first_attempt(run_attempt):
    """FR-016: only attempt 1 may dispatch, post reviews or record rounds."""
    try:
        return int(run_attempt) <= 1
    except (TypeError, ValueError):
        return False


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--tasks-file", required=True)
    p.add_argument("--spec-file", required=True)
    p.add_argument("--constitution-file", required=True)
    p.add_argument("--out", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--input", required=True)
    d.add_argument("--verdict", required=True)
    d.add_argument("--run-attempt", default="1")
    args = parser.parse_args(argv)
    if args.cmd == "prepare":
        diff = _git("diff", "-U0", f"{args.base}..{args.head}", "--", args.tasks_file)
        with open(args.spec_file, encoding="utf-8") as fh:
            spec = fh.read()
        with open(args.constitution_file, encoding="utf-8") as fh:
            const = fh.read()
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(build_input(args.base, args.head, diff, spec, const), fh)
        return 0
    with open(args.input, encoding="utf-8") as fh:
        fold_input = json.load(fh)
    try:
        with open(args.verdict, encoding="utf-8") as fh:
            verdict = json.load(fh)
    except (OSError, ValueError):
        verdict = None
    res = decide(fold_input, verdict)
    print(json.dumps(res))
    print(f"first-attempt={'true' if is_first_attempt(args.run_attempt) else 'false'}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
