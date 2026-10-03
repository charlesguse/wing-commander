#!/usr/bin/env python3
"""Gate 47 -- pointer comments and canonical-copy markers are real, not prose.

CLAUDE.md's "Shared logic has exactly one home" section says repeated
comment prose gets ONE canonical comment and every other site points at it
(`-- see clarify.yml`). This is the gate behind that sentence; without it
the rule is one a reviewer has to remember.

WHAT IT CHECKS, over `#` comments in .github/workflows/*.yml
-----------------------------------------------------------
(a) EVERY POINTER RESOLVES. `-- see` marks a pointer; if the text after it
    names a `NAME.yml` / `NAME.yaml` / `.../NAME.md` / `NAME.py`, that file
    must exist. A bare `NAME.py` resolves under .github/scripts/, the same
    way a bare `NAME.yml` resolves under .github/workflows/ (#439 review --
    a pointer at a gate script's own docstring, the canonical home for
    that script's self-test regression list, is a real, intended target,
    not only workflow-to-workflow prose). Same-file pointers (`-- see
    above in this file.`) name nothing to resolve and are exempt.

    A pointer that NAMES its own file (`-- see clarify.yml.` inside
    clarify.yml) is a violation, not an exemption (#704): it is almost
    always a sibling stage's pointer pasted back into the canonical file,
    it points nowhere, and test (b) below would pass it trivially because
    a file's comments always share vocabulary with themselves. A `-- see`
    written inside quotes (`"-- see clarify.yml."`) is a canonical block
    QUOTING the pointer form its siblings use, not a pointer, and is not
    scanned.

(b) EVERY CROSS-FILE POINTER'S TOPIC SHOWS UP AT THE TARGET. Resolving a
    path proves the file exists, not that the pointer aims at the right
    thing. So the sentence before `-- see` is stripped of stopwords and at
    least one remaining 4+-letter word must appear, whole-word, at the
    target (its comments for a workflow, its full text for a `.md` or
    `.py`). A generic overlap test, deliberately not a list of expected
    phrases -- a list goes stale silently (#149, wc_gate_registry.py). It
    works because a real pointer and its target describe the same thing in
    the same words; a misaimed one shares no vocabulary. Same-file
    pointers are vacuous here and exempt.

(c) EVERY CANONICAL MARKER IS POINTED AT. Pointers ship in two phrasings:
    the `-- see FILE.` form above, and `(see intake.yml)` / `(see intake
    stage)` for the per-stage metrics-summary step. A bare `(see ...)`
    scan would be far too noisy (`(see above)`, `(see the error above)`),
    so the second form counts only when the named file actually exists
    under .github/workflows/ -- grounded in the filesystem, not a list of
    stage names. A marker is justified when some pointer from ANOTHER file
    resolves here and its topic words overlap the block's (test (b)).

(d) EVERY CANONICAL BLOCK IS NAMED AND REGISTERED. A marker reads
    `(canonical copy: <name>; do not condense)`, and
    .github/scripts/canonical-comment-blocks.json lists every (file, name)
    pair. A registered block that is gone from its file fails, and so does
    a marker the register does not list, an unnamed marker, or a name used
    twice in one file. Test (b) cannot see a deleted block: its pointers
    keep resolving to whatever other comment in the same file shares their
    words (#747 -- deleting clarify.yml's #266 inspection guidance passed
    with all four of its pointers still "resolving"). The register is the
    record of what was there, so retiring a block is a visible change to
    it, made together with the pointers that relied on the block.

A quoted `-- see` example skips (a)'s self-pointer test and (b), never
(a)'s existence test: a quoted pointer naming a file that does not exist
is still wrong. An aux `(see X.yml)` naming its own file is a self-pointer
too. Every violation names the pointer's own line, not its block's first.

Deliberately excluded: rewriting or deduplicating comment prose. This
checks only that the pointer mechanism is wired to something real.

USAGE
-----
    python3 .github/scripts/verify-comment-canonical-pointers.py
    python3 .github/scripts/verify-comment-canonical-pointers.py --self-test
"""
import glob
import json
import os
import re
import sys
import tempfile

WORKFLOWS_DIR = ".github/workflows"
SCRIPTS_DIR = ".github/scripts"

POINTER_MARK = re.compile(r"--\s*see\b", re.IGNORECASE)
# A `-- see` opened by one of these is quoted prose describing the pointer
# form, not a pointer -- part (a) of the module docstring.
QUOTE_CHARS = ('"', "`")
# Both fragments together, not just "(canonical copy" alone: a rationale
# comment (this gate's own Gate 47 block included) can legitimately
# mention the marker phrase in backticks while explaining the convention,
# and matching on the shorter fragment alone turns that prose into a
# phantom marker instance. Every real marker in this repo carries both.
CANONICAL_MARK_PARTS = ("(canonical copy", "do not condense")
# Part (d): the name a marker carries, `(canonical copy: <name>; ...`.
CANONICAL_NAME_RE = re.compile(r"\(canonical copy:\s*([a-z0-9][a-z0-9-]*)\s*;")
CANONICAL_REGISTER = SCRIPTS_DIR + "/canonical-comment-blocks.json"

# A concrete file the pointer names: `something.yml`, `something.yaml`,
# `something.py`, or a (possibly path-qualified) `something.md`. Bounded by
# \b so a trailing sentence period ("clarify.yml.") is never swallowed into
# the match. `.py` added #439 review: a pointer at a gate script's own
# docstring (the canonical home for that script's self-test regression
# list, say) was silently unvalidated before -- TARGET_RE never matched it,
# so extract_pointers() never even tried to resolve it.
TARGET_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:ya?ml|md|py))\b")

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
    return _joined_with_lines(block)[0]


def _joined_with_lines(block):
    """_joined(block), plus [(offset, lineno)] for where each source line
    starts in it -- so a pointer found in the joined text reports its own
    line, not the block's first (#747 review of #829)."""
    out = ""
    starts = []
    for lineno, text in block["lines"]:
        if not out:
            starts.append((0, lineno))
            out = text
        elif out.endswith(("/", "-")):
            starts.append((len(out), lineno))
            out += text
        else:
            starts.append((len(out) + 1, lineno))
            out += " " + text
    return out, starts


def _line_at(starts, offset):
    line = starts[0][1] if starts else 0
    for start, lineno in starts:
        if start > offset:
            break
        line = lineno
    return line


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
    `.py` name (verify-x.py) lives in .github/scripts/ (#439 review); any
    other bare name (clarify.yml) lives in .github/workflows/."""
    if "/" in target:
        return os.path.join(root, target)
    if target.endswith(".py"):
        return os.path.join(root, SCRIPTS_DIR, target)
    return os.path.join(root, WORKFLOWS_DIR, target)


def extract_pointers(root, path):
    """Every `-- see` pointer in `path`.

    -> list of dicts: file, line, prefix, target (None if same-file),
       target_path (resolved, only if target is not None)
    """
    out = []
    for block in comment_blocks(path):
        joined, starts = _joined_with_lines(block)
        for m in POINTER_MARK.finditer(joined):
            # A quoted example of the pointer form -- (a): kept, so the
            # file it names must still exist, but never a self-pointer or
            # a topic to test.
            quoted = m.start() > 0 and joined[m.start() - 1] in QUOTE_CHARS
            prefix = joined[:m.start()]
            suffix = joined[m.end():]
            tm = TARGET_RE.search(suffix)
            target = tm.group(1) if tm else None
            rec = {
                "file": path,
                "line": _line_at(starts, m.start()),
                "prefix": _local_topic(prefix),
                "target": target,
                "quoted": quoted,
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
        joined, starts = _joined_with_lines(block)
        for regex in AUX_POINTER_RES:
            for m in regex.finditer(joined):
                target = m.group(1) + ".yml"
                target_path = resolve_target_path(root, target)
                if not os.path.isfile(target_path):
                    continue
                prefix = joined[:m.start()]
                out.append({
                    "file": path,
                    "line": _line_at(starts, m.start()),
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
        marker_text = dict(block["lines"])[marker_line]
        nm = CANONICAL_NAME_RE.search(marker_text)
        out.append({
            "file": path,
            "line": marker_line,
            "name": nm.group(1) if nm else None,
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

            # (a) the named file exists -- quoted or not.
            if not os.path.isfile(p["target_path"]):
                violations.append(
                    f"{p['file']}:{p['line']}: pointer '-- see {p['target']}' "
                    f"names a file that does not exist ({p['target_path']!r})")
                continue
            if p["quoted"]:
                continue  # a quoted example names a real file; nothing more to test

            # (a) a pointer naming its own file points nowhere (#704).
            if (os.path.normcase(os.path.abspath(p["target_path"]))
                    == os.path.normcase(os.path.abspath(p["file"]))):
                violations.append(
                    f"{p['file']}:{p['line']}: pointer '-- see {p['target']}' "
                    f"names its own file -- a self-pointer resolves to "
                    f"nothing; drop it, or point at the real canonical copy")
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
    for path in workflow_files(root):
        for p in extract_aux_pointers(root, path):
            if (os.path.normcase(os.path.abspath(p["target_path"]))
                    == os.path.normcase(os.path.abspath(p["file"]))):
                violations.append(
                    f"{p['file']}:{p['line']}: pointer '(see {p['target']})' "
                    f"names its own file -- a self-pointer resolves to "
                    f"nothing; drop it, or point at the real canonical copy")
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


def check_canonical_register(root):
    """Runs (d): every canonical block is named, and the named set equals
    the register's.

    -> violations: list[str]
    """
    violations = []
    found = {}
    for path in workflow_files(root):
        base = os.path.basename(path)
        for block in extract_canonical_blocks(path):
            if block["name"] is None:
                violations.append(
                    f"{block['file']}:{block['line']}: canonical marker carries "
                    f"no name -- write `(canonical copy: <name>; do not "
                    f"condense)` and list ({base}, <name>) in "
                    f"{CANONICAL_REGISTER} (#747)")
                continue
            key = (base, block["name"])
            if key in found:
                violations.append(
                    f"{block['file']}:{block['line']}: canonical name "
                    f"{block['name']!r} is already used at {base}:{found[key]}")
                continue
            found[key] = block["line"]
    register_path = os.path.join(root, CANONICAL_REGISTER)
    try:
        with open(register_path, encoding="utf-8") as f:
            rows = json.load(f).get("blocks") or []
        registered = {(r["file"], r["name"]) for r in rows}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if not found:
            return violations
        return violations + [f"{CANONICAL_REGISTER}:1: cannot read the canonical "
                             f"block register ({exc}) -- part (d) has nothing to "
                             f"compare the markers against"]
    for base, name in sorted(registered - set(found)):
        violations.append(
            f"{WORKFLOWS_DIR}/{base}:1: canonical block {base}#{name}, listed in "
            f"{CANONICAL_REGISTER}, is gone. Its `-- see {base}` pointers now "
            f"resolve to whatever other comment shares their words (#747). "
            f"Restore the block, or retire it: drop its register row and every "
            f"pointer that relied on it, in one change.")
    for base, name in sorted(set(found) - registered):
        violations.append(
            f"{WORKFLOWS_DIR}/{base}:{found[(base, name)]}: canonical block "
            f"{base}#{name} is not listed in {CANONICAL_REGISTER} -- add a row "
            f"so deleting it later fails this gate")
    return violations


def run_gate(root="."):
    p_violations, p_count = check_pointers(root)
    c_violations, c_count = check_canonical_markers(root)
    violations = p_violations + c_violations + check_canonical_register(root)

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

        # A bare `.py` target resolves under .github/scripts/, not
        # .github/workflows/ (#439 review) -- a pointer at a gate script's
        # own docstring, sharing real vocabulary with the pointing comment.
        script_dir = os.path.join(td, SCRIPTS_DIR)
        os.makedirs(script_dir, exist_ok=True)
        _write(os.path.join(script_dir, "verify-example-gate.py"), (
            '"""Gate N -- checks widget frobnication.\n\n'
            "SELF-TEST\n---------\nEach mutation the self-test replays is "
            "listed once, here.\n\"\"\"\n"))
        _write(os.path.join(wf, "good-py.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # the mutation list -- see verify-example-gate.py.\n"
            "      - run: echo good\n"))
        py_p, _ = check_pointers(td)
        check("a bare .py pointer resolves under .github/scripts/",
              not py_p, f"got {py_p!r}")
        os.remove(os.path.join(script_dir, "verify-example-gate.py"))
        os.remove(os.path.join(wf, "good-py.yml"))

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

        # Defect 2b (check a, #704): a pointer that names its own file.
        # Its topic words overlap its own comments by construction, so
        # before #704 check (b) passed it trivially. A quoted example of
        # the pointer form in the same file is prose, not a pointer.
        _write(os.path.join(wf, "self-point.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # Siblings point back here with \"-- see self-point.yml.\".\n"
            "      - run: echo quoted\n"
            "      # headless has no turn-boundary resume -- see self-point.yml.\n"
            "      - run: echo self\n"
            "      # Or in code style: `-- see self-point.yml`.\n"
            "      - run: echo backtick\n"))
        p, _ = check_pointers(td)
        check("pointer naming its own file is caught",
              any("self-point.yml:7" in v and "names its own file" in v
                  for v in p),
              f"got {p!r}")
        check("quoted '-- see' example is not scanned as a pointer",
              not any("self-point.yml:5" in v for v in p),
              f"got {p!r}")
        check("backtick-quoted '-- see' example is not scanned as a pointer",
              not any("self-point.yml:9" in v for v in p),
              f"got {p!r}")
        os.remove(os.path.join(wf, "self-point.yml"))

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
        os.remove(os.path.join(wf, "aux-canon.yml"))
        os.remove(os.path.join(wf, "aux-pointer.yml"))

        # Part (d), #747: the reproduction. canon.yml's block is deleted
        # while another comment there keeps good.yml's pointer resolving --
        # (b) still passes, and only the register notices.
        register = os.path.join(td, CANONICAL_REGISTER)

        def write_register(*pairs):
            _write(register, json.dumps(
                {"blocks": [{"file": f, "name": n} for f, n in pairs]}))

        _write(os.path.join(wf, "canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # (canonical copy: subagent-sync; do not condense)\n"
            "      # Force subagents synchronous -- headless has no turn-boundary\n"
            "      # resume, so a backgrounded subagent silently drops work.\n"
            "      - run: echo canonical\n"))
        write_register(("canon.yml", "subagent-sync"))
        check("a named, registered canonical block passes (d)",
              not check_canonical_register(td),
              f"got {check_canonical_register(td)!r}")
        _write(os.path.join(wf, "canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # An unrelated note that happens to say headless and resume.\n"
            "      - run: echo canonical\n"))
        p, _ = check_pointers(td)
        d = check_canonical_register(td)
        check("a deleted canonical block still passes (b) -- the #747 blind spot",
              not p, f"got {p!r}")
        check("a deleted canonical block fails (d), naming it (#747)",
              any("canon.yml#subagent-sync" in v and "is gone" in v for v in d),
              f"got {d!r}")

        _write(os.path.join(wf, "canon.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # (canonical copy: subagent-sync; do not condense)\n"
            "      # Force subagents synchronous.\n"
            "      - run: echo one\n"
            "      # (canonical copy: subagent-sync; do not condense)\n"
            "      # The same name again.\n"
            "      - run: echo two\n"
            "      # (canonical copy; do not condense)\n"
            "      # A marker with no name.\n"
            "      - run: echo three\n"
            "      # (canonical copy: never-registered; do not condense)\n"
            "      # A named marker the register does not list.\n"
            "      - run: echo four\n"))
        d = check_canonical_register(td)
        check("a canonical name used twice in one file fails (d)",
              any("canon.yml:8" in v and "already used" in v for v in d), f"got {d!r}")
        check("an unnamed canonical marker fails (d)",
              any("canon.yml:11" in v and "carries no name" in v for v in d), f"got {d!r}")
        check("a canonical marker missing from the register fails (d)",
              any("canon.yml#never-registered" in v and "not listed" in v for v in d),
              f"got {d!r}")

        # A quoted pointer is not exempt from its target existing; an aux
        # pointer naming its own file is a self-pointer; a pointer reports
        # its own line, not its block's first (#747, review of #829).
        _write(os.path.join(wf, "extras.yml"), (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      # A block whose pointer sits on its third line: the\n"
            "      # subagent synchronous headless resume rule\n"
            "      # -- see nowhere-at-all.yml.\n"
            "      - run: echo own-line\n"
            "      # Quoted, but naming a missing file: `-- see gone-quoted.yml`.\n"
            "      - run: echo quoted\n"
            "      # Surface this run's metrics (see extras.yml).\n"
            "      - run: echo aux-self\n"))
        p, _ = check_pointers(td)
        check("a pointer's violation names its own line, not its block's first",
              any("extras.yml:7:" in v and "nowhere-at-all.yml" in v for v in p),
              f"got {p!r}")
        check("a quoted pointer naming a missing file still fails (a)",
              any("extras.yml:9:" in v and "gone-quoted.yml" in v for v in p),
              f"got {p!r}")
        check("an aux '(see X.yml)' pointer naming its own file fails (a)",
              any("extras.yml:11:" in v and "names its own file" in v for v in p),
              f"got {p!r}")

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
