#!/usr/bin/env python3
"""Deterministic hold/dispatch decision for wing-commander-fold-analyze.

Reads the analyze agent's JSON (contracts/fold-analyze.md) -- the fenced
```wing-commander-fold-analyze``` block ending the agent's final message in
its claude-execution-output.json, or a bare JSON file -- and prints a JSON
object {decision, hold-reason, report-markdown, question-markdown}. With
--out-dir the two markdown bodies are also written there as report.md and
question.md (empty when not applicable).

    decide.py --fold-id ID [--tasks N] [--open-holds none|IDS]
              [--execution-output FILE | --input FILE | --failed] [--out-dir DIR]
    decide.py --section < tasks.md.diff   (the fold's added lines, ticks left out)

`hold` iff a finding has category == constitution-conflict, or the check
failed or its output does not match the schema. Otherwise `dispatch`.
`skipped` when the fold section has no tasks (--tasks 0). A dispatch or a
skip becomes `blocked` while another fold hold is open on the lifecycle
(--open-holds `none` or fold ids, from wing-commander-fold-open-holds):
nothing dispatches until it is answered, and the release that answers it
dispatches implement then. An empty --open-holds (the read never ran or
failed) holds as analyze-failed.
"""
import argparse
import json
import os
import re
import sys

CATEGORIES = {"constitution-conflict", "inconsistency", "duplication", "other"}
KEYS = ("severity", "category", "fold_task", "location", "principle", "detail")
FENCE = "wing-commander-fold-analyze"
FENCE_RE = re.compile(r"```" + re.escape(FENCE) + r"[ \t]*\n(.*?)\n```", re.DOTALL)


CHECKBOX_RE = re.compile(r"^(\s*- )\[[ xX]\]")


def untick(line):
    return CHECKBOX_RE.sub(r"\1[ ]", line)


def hunks(patch):
    """(removed lines, added lines) for each hunk of a `git diff -U0`.
    The one home of the hunk parsing: wc_fold_hold.py reads ticks with it."""
    out, minus, plus, in_hunk = [], [], [], False
    for line in patch.splitlines() + ["@@"]:
        if line.startswith("@@"):
            if in_hunk:
                out.append((minus, plus))
            minus, plus, in_hunk = [], [], True
        elif in_hunk and line.startswith("-"):
            minus.append(line[1:])
        elif in_hunk and line.startswith("+"):
            plus.append(line[1:])
    return out


def fold_section(patch):
    """The lines a fold added, from a `git diff -U0` of tasks.md: every
    added line but a tick -- one whose only change is its checkbox, an
    implement cycle's push in the same window, never the fold's own."""
    out = []
    for minus, plus in hunks(patch):
        gone = set(untick(line) for line in minus)
        out.extend(line for line in plus if untick(line) not in gone)
    return out


def from_transcript(path):
    """The fenced JSON text of the transcript's last result, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            transcript = json.load(fh)
    except (OSError, ValueError):
        return None
    entries = transcript if isinstance(transcript, list) else [transcript]
    results = [e for e in entries if isinstance(e, dict) and e.get("type") == "result"]
    if not results:
        return None
    text = results[-1].get("result") or ""
    blocks = FENCE_RE.findall(text if isinstance(text, str) else "")
    # The last block: an earlier one may quote the spec under review.
    return blocks[-1] if blocks else None


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
        # null reads as absent ("principle" is for constitution conflicts
        # only); any other non-string is a schema mismatch.
        for k in KEYS:
            if f.get(k) is None:
                f[k] = ""
            elif not isinstance(f[k], str):
                return None
            else:
                f[k] = inert(f[k])
    return data["findings"]


def inert(text):
    """Agent text as one line with `<`/`>` as entities: the report and the
    question are posted under the App's identity, so a `<!-- ... -->` the
    agent echoes (from a fold section's reviewer text) must not read back
    as a hold-state or resolved marker (wc_fold_hold.py)."""
    return " ".join(text.split()).replace("<", "&lt;").replace(">", "&gt;")


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
                "before implement.\n\nOptions: proceed anyway, or retry the check. "
                "A maintainer answers with a comment on this issue reading "
                "`/fold-hold proceed` or `/fold-hold retry`."
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
            "constitution:\n\n" + items + "\n\nOptions: the review is right, so "
            "amend the spec; the spec is right, so drop the fold task; or proceed "
            "anyway. A maintainer answers with a comment on this issue reading "
            "`/fold-hold amend`, `/fold-hold drop` or `/fold-hold proceed`."
        ),
    }


def block(result, open_holds, fold_id=""):
    """`dispatch`/`skipped` -> `blocked` while other holds are open.
    open_holds None (the open-hold read never ran or failed) holds the
    fold as analyze-failed: nothing vouches that no hold is open."""
    if open_holds is None and result["decision"] != "hold":
        return decide(fold_id, 1, "", True)
    if not open_holds or result["decision"] not in ("dispatch", "skipped"):
        return result
    note = ("Not dispatched: fold hold(s) {0} are open on this lifecycle, and "
            "every fold dispatch waits until they are answered.").format(
                ", ".join("`{0}`".format(inert(h)) for h in open_holds))
    report_md = result["report-markdown"]
    return dict(result, decision="blocked",
                **{"report-markdown": (report_md + "\n\n" + note) if report_md else note})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--section"]:
        # The stage step's scoping: a `git diff -U0` on stdin.
        for line in fold_section(sys.stdin.read()):
            print(line)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold-id", required=True)
    ap.add_argument("--tasks", type=int, default=1)
    ap.add_argument("--input", default="")
    ap.add_argument("--execution-output", default="")
    ap.add_argument("--failed", action="store_true")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--open-holds", default="",
                    help="`none`, or comma-separated fold ids of the other open holds; "
                         "empty means the read never ran (analyze-failed)")
    a = ap.parse_args(argv)
    text = None
    if not a.failed:
        if a.execution_output:
            text = from_transcript(a.execution_output)
        elif a.input:
            try:
                with open(a.input, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                text = None
    failed = a.failed or text is None
    holds = None if not a.open_holds else (
        [] if a.open_holds == "none" else [h for h in a.open_holds.split(",") if h])
    result = block(decide(a.fold_id, a.tasks, text or "", failed), holds, a.fold_id)
    if a.out_dir:
        for name, key in (("report.md", "report-markdown"), ("question.md", "question-markdown")):
            with open(os.path.join(a.out_dir, name), "w", encoding="utf-8") as fh:
                fh.write(result[key] + ("\n" if result[key] else ""))
    json.dump(result, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
