#!/usr/bin/env python3
"""Gate 47 -- pointer comments and canonical-copy markers are real, not prose.

CLAUDE.md's "Shared logic has exactly one home" section says repeated
comment prose gets ONE canonical comment and every other site points at it
(`-- see clarify.yml`). This is the gate behind that sentence; without it
the rule is one a reviewer has to remember.

WHAT IT CHECKS, over `#` comments in .github/workflows/*.yml
-----------------------------------------------------------
(a) EVERY POINTER RESOLVES. `-- see` marks a pointer; if the text after it
    names a `NAME.yml` / `NAME.yaml` / `.../NAME.md`, that file must exist.
    Same-file pointers (`-- see above in this file.`) name nothing to
    resolve and are exempt.

(b) EVERY CROSS-FILE POINTER'S TOPIC SHOWS UP AT THE TARGET. Resolving a
    path proves the file exists, not that the pointer aims at the right
    thing. So the sentence before `-- see` is stripped of stopwords and at
    least one remaining 4+-letter word must appear, whole-word, at the
    target (its comments for a workflow, its full text for a `.md`). A
    generic overlap test, deliberately not a list of expected phrases --
    a list goes stale silently (#149, wc_gate_registry.py). It works
    because a real pointer and its target describe the same thing in the
    same words; a misaimed one shares no vocabulary. Same-file pointers
    are vacuous here and exempt.

(c) EVERY CANONICAL MARKER IS POINTED AT. Pointers ship in two phrasings:
    the `-- see FILE.` form above, and `(see intake.yml)` / `(see intake
    stage)` for the per-stage metrics-summary step. A bare `(see ...)`
    scan would be far too noisy (`(see above)`, `(see the error above)`),
    so the second form counts only when the named file actually exists
    under .github/workflows/ -- grounded in the filesystem, not a list of
    stage names. A marker is justified when some pointer from ANOTHER file
    resolves here and its topic words overlap the block's (test (b)).

Deliberately excluded: rewriting or deduplicating comment prose. This
checks only that the pointer mechanism is wired to something real.

USAGE
-----
    python3 .github/scripts/verify-comment-canonical-pointers.py
    python3 .github/scripts/verify-comment-canonical-pointers.py --self-test
"""
import glob
import os
import re
import sys
import tempfile

WORKFLOWS_DIR = ".github/workflows"

POINTER_MARK = re.compile(r"--\s*see\b", re.IGNORECASE)
# Both fragments together, not just "(canonical copy" alone: a rationale
# comment (this gate's own Gate 47 block included) can legitimately
# mention the marker phrase in backticks while explaining the convention,
# and matching on the shorter fragment alone turns that prose into a
# phantom marker instance. Every real marker in this repo carries both.
CANONICAL_MARK_PARTS = ("(canonical copy", "do not condense")

# A concrete file the pointer names: `something.yml`, `something.yaml`, or
# a (possibly path-qualified) `something.md`. Bounded by \b so a trailing
# sentence period ("clarify.yml.") is never swallowed into the match.
TARGET_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:ya?ml|md))\b")

# The second, narrower pointer phrasing this repo actually ships for the
# per-stage metrics-summary duplication -- see part (c) in the module
# docstring for why it is recognised only here, and only when filesystem-
# grounded.
AUX_POINTER_RES = [
    re.compile(r"\(see ([A-Za-z0-9_-]+)\.ya?ml\)"),
    re.compile(r"\(see ([A-Za-z0-9_-]+) stage\)"),
]

STOPWORDS = {
    "this", "that", "these", "those", "with", "from", "into", "than",
    "then", "such", "only", "must", "when", "while", "after", "before",
    "above", "below", "there", "where", "which", "whose", "being", "never",
    "always", "about", "again", "against", "between", "both", "each",
    "have", "has", "had", "here", "over", "under", "still", "also", "just",
    "very", "more", "most", "some", "same", "other", "does", "done", "will",
    "would", "could", "should", "were", "was", "are", "not", "but", "for",
    "and", "the", "own", "its", "it's", "per", "via", "gate", "gated",
    "run", "step", "file", "line", "lines", "copy",
}


def _rel(path):
    return path.replace(os.sep, "/")


def workflow_files(root="."):
    base = os.path.join(root, WORKFLOWS_DIR)
    return sorted(_rel(p) for p in glob.glob(os.path.join(base, "*.yml")))


def _is_comment(line):
    return line.strip().startswith("#")


def _strip_comment(line):
    s = line.strip()[1:]
    return s[1:] if s.startswith(" ") else s


def comment_blocks(path):
    """Every maximal run of consecutive `#`-comment lines in a file.

    -> list of {"start": 1-based line no, "lines": [(lineno, text), ...]}
    A block ends at the first non-comment line (blank included), which is
    exactly the paragraph boundary this repo's comment style uses.
    """
    with open(path, encoding="utf-8") as f:
        raw_lines = f.read().splitlines()
    blocks = []
    cur = []
    for i, line in enumerate(raw_lines, start=1):
        if _is_comment(line):
            cur.append((i, _strip_comment(line)))
        else:
            if cur:
                blocks.append({"start": cur[0][0], "lines": cur})
                cur = []
    if cur:
        blocks.append({"start": cur[0][0], "lines": cur})
    return blocks


def _joined(block):
    """Join a block's comment lines into one string for scanning.

    Plain `" ".join` breaks a path or word that this repo's line-wrapping
    split across two comment lines with no space in the source (a `-- see`
    target continuing on the next line, e.g.
    `specs/037-agent-turn-budget-guard/\\n# data-model.md.`, or an ordinary
    hyphenated word wrap) -- inserting a space there would fragment
    `specs/.../data-model.md` into two tokens and make TARGET_RE miss it.
    A line ending in "/" or "-" is a continuation marker in this repo's
    prose, so those joins skip the space; everything else gets one.
    """
    out = ""
    for _, text in block["lines"]:
        if not out:
            out = text
        elif out.endswith(("/", "-")):
            out += text
        else:
            out += " " + text
    return out


def file_comment_text(path):
    return "\n".join(_joined(b) for b in comment_blocks(path))


def _local_topic(prefix):
    """The last sentence-ish chunk of `prefix` -- the part actually
    describing what the pointer points at, not the whole paragraph above
    it (a block can carry more than one sentence before the pointer)."""
    parts = [p for p in re.split(r"(?<=[.;:])\s+", prefix.strip()) if p.strip()]
    return parts[-1] if parts else prefix


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")


def significant_words(text):
    out = set()
    for w in _WORD_RE.findall(text.lower()):
        w = w.strip("'-")
        if len(w) >= 4 and w not in STOPWORDS:
            out.add(w)
    return out


def resolve_target_path(root, target):
    """A pointer target string -> the path it names, repo-relative rules:
    a name with a "/" is repo-root-relative (specs/.../research.md); a bare
    name (clarify.yml) lives in .github/workflows/."""
    if "/" in target:
        return os.path.join(root, target)
    return os.path.join(root, WORKFLOWS_DIR, target)


def extract_pointers(root, path):
    """Every `-- see` pointer in `path`.

    -> list of dicts: file, line, prefix, target (None if same-file),
       target_path (resolved, only if target is not None)
    """
    out = []
    for block in comment_blocks(path):
        joined = _joined(block)
        for m in POINTER_MARK.finditer(joined):
            prefix = joined[:m.start()]
            suffix = joined[m.end():]
            tm = TARGET_RE.search(suffix)
            target = tm.group(1) if tm else None
            rec = {
                "file": path,
                "line": block["start"],
                "prefix": _local_topic(prefix),
                "target": target,
            }
            if target:
                rec["target_path"] = resolve_target_path(root, target)
            out.append(rec)
    return out


def extract_aux_pointers(root, path):
    """The second, narrower `(see X.yml)` / `(see X stage)` pointer form,
    accepted ONLY when the named file actually exists under
    .github/workflows/ (see module docstring part (c))."""
    out = []
    for block in comment_blocks(path):
        joined = _joined(block)
        for regex in AUX_POINTER_RES:
            for m in regex.finditer(joined):
                target = m.group(1) + ".yml"
                target_path = resolve_target_path(root, target)
                if not os.path.isfile(target_path):
                    continue
                prefix = joined[:m.start()]
                out.append({
                    "file": path,
                    "line": block["start"],
                    "prefix": _local_topic(prefix),
                    "target": target,
                    "target_path": target_path,
                })
    return out


def extract_canonical_blocks(path):
    """Every `(canonical copy` block in `path`.

    -> list of dicts: file, line, topic_words (from the rest of the block)
    """
    out = []
    for block in comment_blocks(path):
        marker_line = None
        for lineno, text in block["lines"]:
            if all(part in text for part in CANONICAL_MARK_PARTS):
                marker_line = lineno
                break
        if marker_line is None:
            continue
        rest = " ".join(text for lineno, text in block["lines"]
                         if lineno != marker_line)
        out.append({
            "file": path,
            "line": marker_line,
            "words": significant_words(rest),
        })
    return out


def _target_text(target_path):
    if target_path.endswith((".yml", ".yaml")):
        return file_comment_text(target_path)
    with open(target_path, encoding="utf-8") as f:
        return f.read()


def check_pointers(root):
    """Runs (a) and (b) over every workflow file's `-- see` pointers.

    -> (violations: list[str], pointer_count: int)
    """
    violations = []
    count = 0
    for path in workflow_files(root):
        for p in extract_pointers(root, path):
            count += 1
            if p["target"] is None:
                continue  # same-file pointer -- nothing external to check

            # (a) the named file exists.
            if not os.path.isfile(p["target_path"]):
                violations.append(
                    f"{p['file']}:{p['line']}: pointer '-- see {p['target']}' "
                    f"names a file that does not exist ({p['target_path']!r})")
                continue

            # (b) the pointer's topic shows up at the target.
            topic_words = significant_words(p["prefix"])
            if not topic_words:
                continue  # nothing to check the overlap against
            target_words = significant_words(_target_text(p["target_path"]))
            if not (topic_words & target_words):
                violations.append(
                    f"{p['file']}:{p['line']}: pointer '-- see {p['target']}' "
                    f"(topic: {p['prefix']!r}) shares no significant word "
                    f"with {p['target']}'s own text -- looks aimed at the "
                    f"wrong file")
    return violations, count


def check_canonical_markers(root):
    """Runs (c) over every `(canonical copy` marker.

    -> (violations: list[str], marker_count: int)
    """
    files = workflow_files(root)
    all_pointers = []
    for path in files:
        all_pointers.extend(extract_pointers(root, path))
        all_pointers.extend(extract_aux_pointers(root, path))

    violations = []
    count = 0
    for path in files:
        for block in extract_canonical_blocks(path):
            count += 1
            candidates = [
                p for p in all_pointers
                if p["file"] != path and p.get("target_path")
                and os.path.normcase(os.path.abspath(p["target_path"]))
                    == os.path.normcase(os.path.abspath(path))
            ]
            justified = any(
                significant_words(c["prefix"]) & block["words"]
                for c in candidates
            )
            if not justified:
                violations.append(
                    f"{block['file']}:{block['line']}: '(canonical copy' "
                    f"marker has no pointer (from another file) whose "
                    f"topic overlaps it -- {len(candidates)} pointer(s) to "
                    f"this file found, none on-topic")
    return violations, count


def run_gate(root="."):
    p_violations, p_count = check_pointers(root)
    c_violations, c_count = check_canonical_markers(root)
    violations = p_violations + c_violations

    for v in violations:
        file_part = v.split(":", 1)[0]
        print(f"::error file={file_part}::verify-comment-canonical-pointers: {v}")

    print(f"verify-comment-canonical-pointers: {p_count} pointer(s), "
          f"{c_count} canonical marker(s) checked, {len(violations)} "
          f"violation(s).")
    return 1 if violations else 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def self_test():
    """Synthetic fixtures proving each check actually catches its defect.

    Built fresh in a tempdir rather than checked-in fixture files: the
    thing under test is a rule about the LIVE tree's comments, and a
    committed fixture would itself need this gate's own byte-sensitivity
    rules applied to it forever, which is exactly the maintenance burden
    CLAUDE.md warns wing-commander's comment conventions create.
    """
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        wf = os.path.join(td, WORKFLOWS_DIR)

        # A clean pair: a canonical copy in canon.yml, and a pointer in
        # good.yml whose topic prose shares real vocabulary with it.
        _write(os.path.join(wf, "canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # (canonical copy -- pointed at from other stage workflows; do not condense)\n"
            "      # Force subagents synchronous -- headless has no turn-boundary\n"
            "      # resume, so a backgrounded subagent silently drops work.\n"
            "      - run: echo canonical\n"))
        _write(os.path.join(wf, "good.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # headless has no turn-boundary resume -- see canon.yml.\n"
            "      - run: echo good\n"))

        clean_p, _ = check_pointers(td)
        check("clean cross-file pointer produces no violation",
              not clean_p, f"got {clean_p!r}")
        clean_c, _ = check_canonical_markers(td)
        check("canonical marker justified by an on-topic pointer",
              not clean_c, f"got {clean_c!r}")

        # Defect 1 (check a): a pointer naming a file that does not exist.
        _write(os.path.join(wf, "bad-target.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # some unrelated topic -- see nonexistent-file.yml.\n"
            "      - run: echo bad\n"))
        p, _ = check_pointers(td)
        check("pointer to a nonexistent file is caught",
              any("nonexistent-file.yml" in v and "does not exist" in v
                  for v in p),
              f"got {p!r}")
        os.remove(os.path.join(wf, "bad-target.yml"))

        # Defect 2 (check b): a pointer that resolves, but whose topic
        # shares no vocabulary with the target -- aimed at the wrong file.
        _write(os.path.join(wf, "bad-topic.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # completely unrelated gizmo frobnication logic -- see canon.yml.\n"
            "      - run: echo bad-topic\n"))
        p, _ = check_pointers(td)
        check("pointer with no topic overlap at its target is caught",
              any("bad-topic.yml" in v and "shares no significant word" in v
                  for v in p),
              f"got {p!r}")
        os.remove(os.path.join(wf, "bad-topic.yml"))

        # Defect 3 (check c): a canonical marker nothing points at.
        _write(os.path.join(wf, "orphan-canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # (canonical copy -- pointed at from other stage workflows; do not condense)\n"
            "      # Nothing else in this synthetic fixture ever references\n"
            "      # this particular paragraph's vocabulary at all.\n"
            "      - run: echo orphan\n"))
        c, _ = check_canonical_markers(td)
        check("canonical marker with no justifying pointer is caught",
              any("orphan-canon.yml" in v for v in c),
              f"got {c!r}")
        os.remove(os.path.join(wf, "orphan-canon.yml"))

        # The aux "(see X stage)" form counts as justification for (c) --
        # part (c) of the module docstring.
        _write(os.path.join(wf, "aux-canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # (canonical copy -- pointed at from other stage workflows; do not condense)\n"
            "      # Surface this run's own metrics in the run summary.\n"
            "      - run: echo aux\n"))
        _write(os.path.join(wf, "aux-pointer.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # Surface this run's own metrics in the run summary (see aux-canon stage).\n"
            "      - run: echo aux-pointer\n"))
        c, _ = check_canonical_markers(td)
        check("aux '(see X stage)' pointer justifies a canonical marker",
              not any("aux-canon.yml" in v for v in c),
              f"got {c!r}")

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
