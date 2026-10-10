#!/usr/bin/env python3
"""Composite `run:` bodies import from the trusted copy (spec 095
FR-011/FR-013/FR-014).

Resolves the composite actions reachable (`uses: ./...`, transitively) from
the covered workflows -- board-loop's fix/review/readiness jobs and the
lifecycle stages -- and scans every `run:` body for a workspace-relative
script path (`.github/scripts/...`, `.github/actions/...`). Those paths are
the agent-writable checkout; a composite must reach its scripts through
`$GITHUB_ACTION_PATH`, the pre-agent snapshot (`$RUNNER_TEMP/wc-pristine`)
or another path outside the workspace.

Fails loud when the reachable set cannot be determined: a `uses: ./...`
that names a composite with no action.yml, or a covered workflow that
cannot be read. A composite moved out of view must not turn the scan into a
silent pass.

wing-commander-contained-gate-suite is exempt by design: running the gate
suite over the agent's workspace is its entire job, and it does so in a
credential-free job (spec 095 US1).

NOTE ON GATE NUMBERING: this gate was first registered as Gate 143. It is
numbered 151, not 143: 141-146 were taken by spec 110's PR #982 and 147-148
by spec 112's PR #1003, which claimed them first among the open
lifecycle branches.

Usage:
    python3 .github/scripts/verify-composite-run-provenance.py
    python3 .github/scripts/verify-composite-run-provenance.py --self-test
"""
import os
import re
import sys
import tempfile
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures", "095-composite-run")

COVERED_WORKFLOWS = (
    "board-loop.yml", "intake.yml", "clarify.yml", "plan.yml", "tasks.yml",
    "implement.yml", "finalize.yml", "pr-conversation.yml",
)
Exemption = namedtuple("Exemption", "reason issue permanent permanent_reason decided_by",
                       defaults=(False, None, ()))

# Exempt by design (see module docstring). Gate 124 reads this table.
EXEMPT_COMPOSITES = {
    "wing-commander-contained-gate-suite": Exemption(
        reason=("runs the gate suite over an agent-written head on purpose, in a "
                "credential-free job"),
        issue=(),
        permanent=True,
        permanent_reason="Running the agent's gate suite is the composite's whole job.",
    ),
}

USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?(\./[^\s'\"#]+)")
RUN_RE = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*?)\s*$")
BLOCK_MARKERS = ("|", "|-", "|+", ">", ">-", ">+")
WORKSPACE_PATH_RE = re.compile(
    r"(?<![\w$}./:-])(?:\./)?\.github/(?:scripts|actions)/[\w./-]*")


class Unresolvable(Exception):
    pass


def run_bodies(text):
    """Yield (lineno, line) for every non-comment line of every `run:`
    value in a YAML document."""
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        match = RUN_RE.match(lines[idx])
        if not match:
            idx += 1
            continue
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        if lines[idx].lstrip().startswith("-"):
            indent += 2
        inline = match.group(2)
        if inline and inline not in BLOCK_MARKERS:
            if not inline.startswith("#"):
                yield idx + 1, inline
            idx += 1
            continue
        idx += 1
        while idx < len(lines):
            line = lines[idx]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            if line.strip() and not line.lstrip().startswith("#"):
                yield idx + 1, line
            idx += 1


def composite_uses(text):
    return [m.group(1) for m in map(USES_RE.match, text.splitlines()) if m]


def composite_name(use):
    """`./.wc-pristine-repo/.github/actions/X` or `./.github/actions/X` -> X;
    None when the path is not a composite under .github/actions."""
    match = re.search(r"\.github/actions/([\w-]+(?:/[\w-]+)?)/?$", use)
    return match.group(1) if match else None


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise Unresolvable("cannot read {0}: {1}".format(path, exc))


def reachable_composites(root, workflows):
    """Return {name: action.yml text} for every composite reachable from
    `workflows`; raise Unresolvable when one cannot be resolved."""
    pending = []
    for wf in workflows:
        text = read(os.path.join(root, ".github", "workflows", wf))
        pending += composite_uses(text)
    found = {}
    while pending:
        use = pending.pop()
        name = composite_name(use)
        if name is None:
            raise Unresolvable("uses: {0} is not a composite under "
                               ".github/actions".format(use))
        if name in found:
            continue
        path = os.path.join(root, ".github", "actions", name, "action.yml")
        found[name] = read(path)
        pending += composite_uses(found[name])
    return found


def check(root, workflows=COVERED_WORKFLOWS, exempt=EXEMPT_COMPOSITES):
    try:
        composites = reachable_composites(root, workflows)
    except Unresolvable as exc:
        return ["reachable composite set cannot be determined: {0}".format(exc)]
    if not composites:
        return ["reachable composite set is empty -- the covered workflows "
                "moved out of view"]
    errors = []
    for name in sorted(composites):
        if name in exempt:
            continue
        for lineno, line in run_bodies(composites[name]):
            if WORKSPACE_PATH_RE.search(line):
                errors.append("{0}/action.yml:{1}: run: body reaches a "
                              "workspace-relative script path; use "
                              "$GITHUB_ACTION_PATH or the pre-agent snapshot: "
                              "{2}".format(name, lineno, line.strip()[:120]))
    return errors


def run():
    errors = check(ROOT)
    for err in errors:
        print("::error::" + err)
    if not errors:
        print("verify-composite-run-provenance: ok")
    return 1 if errors else 0


def _fixture_root(tmp, case):
    """Copy a fixture case (workflows/, actions/) under tmp/.github."""
    src = os.path.join(FIXTURES, case)
    for top in ("workflows", "actions"):
        for dirpath, _dirs, files in os.walk(os.path.join(src, top)):
            rel = os.path.relpath(dirpath, src)
            dest = os.path.join(tmp, ".github", rel)
            os.makedirs(dest, exist_ok=True)
            for name in files:
                with open(os.path.join(dirpath, name), "rb") as s, \
                        open(os.path.join(dest, name), "wb") as d:
                    d.write(s.read())
    return tmp


def self_test():
    failures = []
    cases = (
        ("workspace-relative", True),
        ("undeterminable", True),
        ("moved-out-of-view", True),
        ("action-path", False),
    )
    for case, want_error in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, case)
            errors = check(root, workflows=("w.yml",), exempt=())
        if bool(errors) != want_error:
            failures.append("{0}: got {1!r}, want error={2}".format(
                case, errors, want_error))
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture_root(tmp, "workspace-relative")
        if check(root, workflows=("w.yml",),
                 exempt=("bad",)):
            failures.append("exempt composite still flagged")
    for failure in failures:
        print("SELF-TEST FAIL: " + failure, file=sys.stderr)
    if failures:
        return 1
    print("verify-composite-run-provenance self-test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
