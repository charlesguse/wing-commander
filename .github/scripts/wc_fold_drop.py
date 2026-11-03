#!/usr/bin/env python3
"""Deterministic fold-task drop (specs/119-lifecycle-hold-label, FR-023).

Grammar (research D8): the first non-quoted line is ``drop`` or ``drop:``
(case-insensitive); following lines are ``- Review finding: <title>`` or
``- Recurring review finding: <title>``, optionally prefixed ``- [ ] ``.
Disjoint from the stop grammar: a stop is the whole comment ``stop``/``/stop``.
"""
import json
import re
import sys

DROP_RE = re.compile(r"^drop\s*:?\s*$", re.I)
# Any bullet names a task; whether it is a fold task is decided in apply()
# (so ``not-fold-task`` is reachable from a parsed comment).
TITLE_RE = re.compile(r"^-\s+(?:\[[ xX]\]\s+)?(\S.*?)\s*$")
TASK_RE = re.compile(r"^(\s*-\s*)\[([ xX])\](\s+)(.*\S)\s*$")


def parse(comment):
    """Return ``{comment_titles: [...]}`` or None when not a drop command."""
    lines = [ln.rstrip() for ln in (comment or "").splitlines()
             if ln.strip() and not ln.lstrip().startswith(">")]
    if not lines or not DROP_RE.match(lines[0].strip()):
        return None
    titles = []
    for ln in lines[1:]:
        m = TITLE_RE.match(ln.strip())
        if m and m.group(1) not in titles:
            titles.append(m.group(1))
    return {"titles": titles}


def _fold_task_title(text):
    return text if text.startswith(("Review finding:", "Recurring review finding:")) else None


def apply(tasks_text, titles, author_association, comment_id, dropped_titles=()):
    """Return ``(new_text, outcomes, commit_message, reply)``.

    ``dropped_titles`` are titles an earlier drop commit already removed; a
    fold title absent from tasks.md and in that set is ``already-absent``.

    ``outcomes`` maps title -> removed|unknown|not-fold-task|already-checked|
    already-absent, or the whole comment is ``non-maintainer`` (no change).
    """
    if author_association not in ("OWNER", "MEMBER", "COLLABORATOR"):
        return tasks_text, {"*": "non-maintainer"}, "", (
            "Only a maintainer can drop a folded task; nothing was changed.")
    lines = tasks_text.split("\n")
    outcomes = {}
    removed = []
    for title in titles:
        idxs = [i for i, ln in enumerate(lines)
                if (m := TASK_RE.match(ln)) and m.group(4) == title]
        if not idxs:
            if _fold_task_title(title) is None:
                outcomes[title] = "not-fold-task"
            elif title in dropped_titles:
                outcomes[title] = "already-absent"
            else:
                outcomes[title] = "unknown"
            continue
        unchecked = [i for i in idxs if TASK_RE.match(lines[i]).group(2) == " "]
        if _fold_task_title(title) is None:
            outcomes[title] = "not-fold-task"
        elif not unchecked:
            outcomes[title] = "already-checked"
        else:
            for i in unchecked:
                removed.append((i, title))
            outcomes[title] = "removed"
    drop_idx = {i for i, _ in removed}
    new_lines = [ln for i, ln in enumerate(lines) if i not in drop_idx]
    done = [t for t, o in outcomes.items() if o == "removed"]
    msg = ""
    if done:
        msg = "implement: drop folded tasks\n\n" + "\n".join(
            [f"Wing-Commander-Drop: {comment_id}"] + [f"Dropped: {t}" for t in done])
    reply_lines = []
    for t, o in outcomes.items():
        reply_lines.append(f"- `{t}`: {o}")
    reply = "Drop result:\n" + "\n".join(reply_lines) if reply_lines else \
        "Drop named no tasks; nothing was changed."
    return "\n".join(new_lines), outcomes, msg, reply


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "parse" and len(argv) == 1:
        print(json.dumps(parse(sys.stdin.read())))
        return 0
    if argv and argv[0] == "apply" and len(argv) == 4:
        # apply <tasks.md> <author_association> <comment_id>; comment on stdin.
        parsed = parse(sys.stdin.read())
        if parsed is None:
            print("not a drop command", file=sys.stderr)
            return 1
        with open(argv[1], encoding="utf-8") as fh:
            text = fh.read()
        new, outcomes, msg, reply = apply(text, parsed["titles"], argv[2], argv[3])
        with open(argv[1], "w", encoding="utf-8") as fh:
            fh.write(new)
        print(json.dumps({"outcomes": outcomes, "commit_message": msg, "reply": reply}))
        return 0
    print("usage: wc_fold_drop.py parse < comment | apply TASKS ASSOC ID < comment",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
