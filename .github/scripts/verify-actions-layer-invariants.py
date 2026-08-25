#!/usr/bin/env python3
"""Gate: composite actions under .github/actions/** read no ambient state.

WHY THIS EXISTS
---------------
verify-stage-invariants.py (Gate 31) only walks .github/workflows — issue
#149's own text names .github/actions/** as the gap it doesn't cover. This
feature (specs/043-durable-metrics-record) adds/extends exactly two
composites there (wing-commander-metrics-summary, wing-commander-metrics-
persist), and FR-038 requires this coverage to exist before the feature
ships, not deferred to #149 in general. Reuses verify-stage-invariants.py's
comment-stripping and expression-span logic — the same "what does GitHub
actually evaluate as an expression" question, over a different directory.

WHAT IT CHECKS
--------------
Every action.yml/action.yaml under .github/actions/**:
  1. no `github.event.*` read
  2. no `vars.*` read
  3. no `uses: anthropics/claude-code-action` (FR-040a — this feature adds
     no agent invocation anywhere)

WAIVERS (.github/scripts/actions-invariant-waivers.json)
----------------------------------------------------------
Same shape as stage-invariant-waivers.json (exact file/pattern/count,
stale-checked). This feature's OWN new/changed files —
wing-commander-metrics-summary/action.yml and
wing-commander-metrics-persist/action.yml — may carry zero violations,
waived or not: a waiver naming either is rejected outright, so a pre-
existing violation elsewhere cannot be used to launder a new one here.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import tempfile

ACTIONS_DIR = ".github/actions"
WAIVERS_PATH = ".github/scripts/actions-invariant-waivers.json"
PROTECTED_FILES = (
    ACTIONS_DIR + "/wing-commander-metrics-summary/action.yml",
    ACTIONS_DIR + "/wing-commander-metrics-persist/action.yml",
)

# --------------------------------------------------------------------------
# Comment-stripping / expression-span detection, ported from
# verify-stage-invariants.py (Gate 31) — same "what does GitHub actually
# evaluate as an expression" question, over composite action.yml files
# instead of workflow files. Not imported (that file's hyphenated name is
# not an importable module); duplicated deliberately rather than risking a
# refactor of Gate 31's already-tested logic under this feature's own scope.
# --------------------------------------------------------------------------
_BLOCK_SCALAR_HEADER_RE = re.compile(r":\s*[|>](?:[+-]?[0-9]*|[0-9]*[+-]?)\s*(?:#.*)?$")
_HEREDOC_RE = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
EXPR_RE = re.compile(r"\$\{\{.*?\}\}", re.S)
IF_RE = re.compile(r"^[ \t]*(?:-[ \t]+)?if:[ \t]*", re.M)


def _block_scalar_body_lines(text):
    lines = text.split("\n")
    body = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip(" ")
        if (stripped and not stripped.startswith("#")
                and _BLOCK_SCALAR_HEADER_RE.search(line)):
            indent = len(line) - len(stripped)
            base = None
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    body[j] = base
                    j += 1
                    continue
                nindent = len(nxt) - len(nxt.lstrip(" "))
                if nindent <= indent:
                    break
                if base is None:
                    base = nindent
                body[j] = base
                j += 1
            i = j
            continue
        i += 1
    return body


def strip_comments(text):
    body_lines = _block_scalar_body_lines(text)
    out = []
    pending_heredocs = []
    for idx, line in enumerate(text.split("\n")):
        if idx not in body_lines:
            pending_heredocs = []
        elif pending_heredocs:
            terminator, strip_tabs = pending_heredocs[0]
            base = body_lines[idx] or 0
            dedented = line[base:] if line[:base].strip() == "" else line
            if strip_tabs:
                dedented = dedented.lstrip("\t")
            if dedented == terminator:
                pending_heredocs.pop(0)
            out.append(line)
            continue
        in_single = in_double = False
        cut = None
        i = 0
        while i < len(line):
            char = line[i]
            if in_single:
                if char == "'":
                    in_single = False
            elif in_double:
                if char == "\\":
                    i += 1
                elif char == '"':
                    in_double = False
            elif char == "'":
                in_single = True
            elif char == '"':
                in_double = True
            elif char == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
            i += 1
        if idx in body_lines:
            code_part = line if cut is None else line[:cut]
            pending_heredocs.extend(
                (m.group(2), "<<-" in m.group(0))
                for m in _HEREDOC_RE.finditer(code_part))
        out.append(line if cut is None else line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def expression_spans(text):
    spans = [(m.start(), m.end()) for m in EXPR_RE.finditer(text)]
    for match in IF_RE.finditer(text):
        eol = text.find("\n", match.end())
        spans.append((match.end(), len(text) if eol < 0 else eol))
    return spans


EXPRESSION_INVARIANTS = {
    "github.event": (
        re.compile(r"github\.event[A-Za-z0-9_.]*"),
        "reads github.event — a composite action is a published mechanism, "
        "never a trigger owner; event facts arrive only as declared inputs "
        "(constitution VII)",
    ),
    "vars": (
        re.compile(r"\bvars\.[A-Za-z_][A-Za-z0-9_]*"),
        "reads vars.* — configuration reaches a composite action only as a "
        "declared input, so an adopter can see every knob in its interface "
        "(constitution VII)",
    ),
}
CLAUDE_ACTION_RE = re.compile(
    r"^[ \t]*(?:-[ \t]+)?uses:[ \t]*anthropics/claude-code-action", re.M)
CLAUDE_ACTION_MESSAGE = (
    "invokes anthropics/claude-code-action — this feature adds no agent "
    "invocation anywhere (FR-040a, constitution IX)"
)


class Finding(object):
    def __init__(self, path, line, check, text):
        self.path = path
        self.line = line
        self.check = check
        self.text = text


def scan_text(path, text):
    code = strip_comments(text)
    spans = expression_spans(code)
    findings = []
    for check, (pattern, _) in sorted(EXPRESSION_INVARIANTS.items()):
        for match in pattern.finditer(code):
            if not any(start <= match.start() < end for start, end in spans):
                continue
            findings.append(Finding(path, code[:match.start()].count("\n") + 1,
                                    check, match.group(0)))
    for match in CLAUDE_ACTION_RE.finditer(code):
        findings.append(Finding(path, code[:match.start()].count("\n") + 1,
                                "claude-code-action", match.group(0).strip()))
    return sorted(findings, key=lambda f: (f.line, f.check, f.text))


def _rel(root, path):
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return rel[2:] if rel.startswith("./") else rel


def action_manifest_paths(root="."):
    base = os.path.join(root, *ACTIONS_DIR.split("/"))
    out = []
    for pattern in ("action.yml", "action.yaml"):
        out.extend(glob.glob(os.path.join(base, "*", pattern)))
        out.extend(glob.glob(os.path.join(base, "**", pattern), recursive=True))
    return sorted(set(out))


def load_waivers(root="."):
    path = os.path.join(root, *WAIVERS_PATH.split("/"))
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError) as exc:
        return [], ["{0} could not be read ({1}).".format(WAIVERS_PATH, exc)]
    waivers = data.get("waivers") if isinstance(data, dict) else data
    if not isinstance(waivers, list):
        return [], ["{0} must contain a \"waivers\" list.".format(WAIVERS_PATH)]
    return waivers, []


REQUIRED_WAIVER_FIELDS = ("file", "check", "pattern", "count", "reason", "issue")


def check_waiver_shape(waivers):
    failures = []
    for index, waiver in enumerate(waivers):
        where = "{0} entry {1}".format(WAIVERS_PATH, index)
        if not isinstance(waiver, dict):
            failures.append("{0} is not an object.".format(where))
            continue
        missing = [f for f in REQUIRED_WAIVER_FIELDS if not waiver.get(f)]
        if missing:
            failures.append("{0} is missing {1}.".format(where, ", ".join(missing)))
            continue
        if waiver["file"] in PROTECTED_FILES:
            failures.append(
                "{0} waives {1}, one of this feature's own new/changed "
                "files. Those files must carry zero violations, waived or "
                "not.".format(where, waiver["file"]))
            continue
        known = set(EXPRESSION_INVARIANTS) | {"claude-code-action"}
        if waiver["check"] not in known:
            failures.append("{0} waives check {1!r}, which is not one of "
                            "{2}.".format(where, waiver["check"],
                                          ", ".join(sorted(known))))
            continue
        try:
            re.compile(waiver["pattern"])
        except re.error as exc:
            failures.append("{0} has an invalid pattern {1!r}: {2}".format(
                where, waiver["pattern"], exc))
        if not isinstance(waiver["count"], int):
            failures.append("{0} count must be an integer, got {1!r}.".format(
                where, waiver["count"]))
    return failures


def apply_waivers(findings, waivers, manifests):
    failures = []
    waived = set()
    for index, waiver in enumerate(waivers):
        where = "{0} entry {1}".format(WAIVERS_PATH, index)
        if waiver["file"] not in manifests:
            failures.append("{0} waives {1}, which is not a discovered "
                            "action manifest in this checkout.".format(
                                where, waiver["file"]))
            continue
        pattern = re.compile(waiver["pattern"])
        matched = [f for f in findings
                   if f.path == waiver["file"] and f.check == waiver["check"]
                   and pattern.search(f.text)]
        if not matched:
            failures.append("{0} waives {1} in {2} with pattern {3!r}, and "
                            "nothing matches it any more.".format(
                                where, waiver["check"], waiver["file"],
                                waiver["pattern"]))
            continue
        if len(matched) != waiver["count"]:
            failures.append("{0} declares {1} finding(s), but {2} match.".format(
                where, waiver["count"], len(matched)))
            continue
        waived.update(id(f) for f in matched)
    return [f for f in findings if id(f) not in waived], failures


def evaluate(root="."):
    manifests = [_rel(root, p) for p in action_manifest_paths(root)]
    if not manifests:
        return (["no action.yml/action.yaml discovered under {0} — this "
                 "gate examined nothing.".format(ACTIONS_DIR)], [], [], 0)

    findings = []
    for rel in manifests:
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            source = handle.read()
        findings.extend(scan_text(rel, source))

    failures = []
    for f in findings:
        if f.path in PROTECTED_FILES:
            _, message = (EXPRESSION_INVARIANTS.get(f.check)
                          or (None, CLAUDE_ACTION_MESSAGE))
            failures.append(
                "{0}:{1}: `{2}` — {3}. This is one of this feature's own "
                "new/changed files, which may carry zero violations, waived "
                "or not.".format(f.path, f.line, f.text, message))

    non_protected = [f for f in findings if f.path not in PROTECTED_FILES]
    waivers, waiver_failures = load_waivers(root)
    failures.extend(waiver_failures)
    shape_failures = check_waiver_shape(waivers)
    failures.extend(shape_failures)
    if shape_failures or waiver_failures:
        return failures, manifests, findings, 0

    unwaived, stale = apply_waivers(non_protected, waivers, manifests)
    failures.extend(stale)
    for f in unwaived:
        _, message = (EXPRESSION_INVARIANTS.get(f.check)
                      or (None, CLAUDE_ACTION_MESSAGE))
        failures.append(
            "{0}:{1}: `{2}` — {3}. If deliberate, register it in {4}.".format(
                f.path, f.line, f.text, message, WAIVERS_PATH))
    waived_count = len(non_protected) - len(unwaived)
    return failures, manifests, findings, waived_count


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
CLEAN_ACTION = """\
name: clean
description: a well-behaved composite
inputs:
  thing:
    required: true
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "${{ inputs.thing }}"
"""

EVENT_READ_ACTION = """\
name: bad
description: reads ambient state
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "${{ github.event.issue.number }}"
"""

VARS_READ_ACTION = """\
name: bad
description: reads ambient state
runs:
  using: composite
  steps:
    - shell: bash
      env:
        MODEL: ${{ vars.WING_COMMANDER_SPEC_MODEL }}
      run: echo "$MODEL"
"""

CLAUDE_ACTION_STEP = """\
name: bad
description: invokes an agent
runs:
  using: composite
  steps:
    - uses: anthropics/claude-code-action@v1
      with:
        prompt: hi
"""


def _write(root, files):
    for relpath, source in files.items():
        full = os.path.join(root, *ACTIONS_DIR.split("/"), relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)


def _waiver(file, check, pattern, count):
    return {"file": ACTIONS_DIR + "/" + file, "check": check,
            "pattern": pattern, "count": count,
            "reason": "self-test fixture", "issue": "#149"}


FIXTURES = [
    ("a clean action passes",
     {"clean/action.yml": CLEAN_ACTION}, None, None),
    ("a github.event read is caught",
     {"clean/action.yml": CLEAN_ACTION, "bad/action.yml": EVENT_READ_ACTION},
     None, "bad/action.yml:7: `github.event.issue.number`"),
    ("a vars.* read is caught",
     {"clean/action.yml": CLEAN_ACTION, "bad/action.yml": VARS_READ_ACTION},
     None, "bad/action.yml:8: `vars.WING_COMMANDER_SPEC_MODEL`"),
    ("a claude-code-action invocation is caught",
     {"clean/action.yml": CLEAN_ACTION,
      "bad/action.yml": CLAUDE_ACTION_STEP},
     None, "invokes anthropics/claude-code-action"),
    ("a matching waiver suppresses a finding in an unprotected file",
     {"clean/action.yml": CLEAN_ACTION, "bad/action.yml": VARS_READ_ACTION},
     [_waiver("bad/action.yml", "vars", r"^vars\.WING_COMMANDER_[A-Z_]+$", 1)],
     None),
    ("a waiver naming a protected file is rejected outright",
     {"clean/action.yml": CLEAN_ACTION,
      "wing-commander-metrics-summary/action.yml": VARS_READ_ACTION},
     [_waiver("wing-commander-metrics-summary/action.yml", "vars",
               r"^vars\.", 1)],
     "must carry zero violations, waived or not"),
    ("a violation in a protected file is caught even with no waiver at all",
     {"clean/action.yml": CLEAN_ACTION,
      "wing-commander-metrics-persist/action.yml": VARS_READ_ACTION},
     None,
     "wing-commander-metrics-persist/action.yml:8: "
     "`vars.WING_COMMANDER_SPEC_MODEL`"),
]


def self_test():
    bad = 0
    for name, files, waivers, expect in FIXTURES:
        root = tempfile.mkdtemp(prefix="wc-actions-invariants-")
        try:
            _write(root, files)
            if waivers is not None:
                scripts = os.path.join(root, ".github", "scripts")
                os.makedirs(scripts, exist_ok=True)
                with open(os.path.join(scripts, "actions-invariant-waivers.json"),
                          "w", encoding="utf-8", newline="\n") as handle:
                    json.dump({"waivers": waivers}, handle, indent=2)
            failures, _, _, _ = evaluate(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        joined = " | ".join(failures)
        if expect is None:
            if failures:
                bad += 1
                print("[FAIL] {0}: expected a clean pass, got: {1}".format(
                    name, joined))
            else:
                print("[ok] {0}: clean".format(name))
        elif not failures:
            bad += 1
            print("[FAIL] {0}: expected a failure containing {1!r}, got a "
                  "clean pass".format(name, expect))
        elif expect not in joined:
            bad += 1
            print("[FAIL] {0}: failed for the WRONG reason. expected {1!r}, "
                  "got: {2}".format(name, expect, joined))
        else:
            print("[ok] {0}: caught".format(name))
    print("verify-actions-layer-invariants self-test: {0}/{1} fixtures "
          "behaved as specified.".format(len(FIXTURES) - bad, len(FIXTURES)))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Composite actions under .github/actions/** read no "
                    "ambient state and invoke no agent")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.isdir(os.path.join(args.root, *ACTIONS_DIR.split("/"))):
        print("::error::verify-actions-layer-invariants: {0} does not exist "
              "under {1!r}.".format(ACTIONS_DIR, args.root))
        return 1

    failures, manifests, findings, waived = evaluate(args.root)
    for f in failures:
        print("::error::verify-actions-layer-invariants: {0}".format(f))
    print("verify-actions-layer-invariants: {0} action manifest(s), {1} "
          "finding(s), {2} waived; {3} failure(s).".format(
              len(manifests), len(findings), waived, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
