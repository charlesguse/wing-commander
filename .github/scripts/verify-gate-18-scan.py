#!/usr/bin/env python3
"""Gate 18 - every paginated read is safe by construction.

Under `--paginate`, `gh api` applies whatever `--jq` filter it is given to
EACH page separately and concatenates the raw outputs; it does not slurp
first. A filter that collects results into an array (`--jq '[...]'`), or no
`--jq` at all, therefore resolves to page-shaped garbage the moment a read
passes its first page - silently (spec 036, issue #182).

This is the repository-wide scan. `verify-gate-18.py` is its self-test, and
the two answer different questions: this one asks whether the tree is clean,
that one asks whether the detector can still detect. Both are needed, and a
green self-test on a broken tree is not a contradiction - it is the reason
they are separate files.

WHY THIS IS A FILE
------------------
It used to be an inline `python3 - <<'PYEOF'` heredoc in
lint-workflows.yml. wc_gate_registry's convention is mechanical and
file-based - `.github/scripts/verify-*.py` is a check - so a heredoc matched
nothing: `run-local-gates.py` could not reach it and `verify-gate-wiring.py`
did not know it existed. It ran in CI and only in CI.

The cost was not hypothetical. specs/036's T024 mutation drill says to break
`watchdog.yml`, run `run-local-gates.py`, and confirm Gate 18 fails naming
the offending line. Run as written against a deliberately broken tree, it
reported all green - the only Gate 18 piece the runner could reach was the
self-test, which is green on a broken repository by design. A drill whose
command cannot fail is worth less than no drill, because performing it
produces evidence of the wrong thing (#213).

Usage: python3 .github/scripts/verify-gate-18-scan.py
"""
import glob, os, re, sys, yaml

EXCLUDE_DIR = ".wing-commander-pipeline"
GH_INVOKE_RE = re.compile(r'\bgh\s+api\b.*?--paginate\b')
JQ_ARG_RE = re.compile(
    r"--jq\s+'((?:[^'\\]|\\.)*)'|--jq\s+\"((?:[^\"\\]|\\.)*)\"")
EXEMPT_RE = re.compile(r'wc-pagination-exempt:\s*\S')
CORRECT_FORM = ('gh api "<path>" --paginate --jq '
                '\'.[] | <per-item filter>\' | jq -s \'.\'')


def check_line(line):
    """None if not a --paginate call; else (ok, rule)."""
    if not GH_INVOKE_RE.search(line):
        return None
    m = JQ_ARG_RE.search(line)
    if m is None:
        if "--jq" in line:
            return True, None       # unparseable form: do not guess
        return False, "no-filter"
    expr = (m.group(1) if m.group(1) is not None else m.group(2)).strip()
    if expr.startswith("["):
        return False, "array-collecting"
    return True, None


def is_exempt(lines, idx):
    for i in (idx, idx - 1):
        if 0 <= i < len(lines) and EXEMPT_RE.search(lines[i]):
            return True
    return False


def logical_lines(lines):
    """Join backslash-continued physical lines into one logical
    line each, keyed by the FIRST physical line's index. A
    `gh api ... --paginate \\` call whose `--jq` argument is on a
    continuation line (intake.yml, Gate 1's own workflow-listing
    read) must be judged as one command, or the continuation's
    `--jq` is invisible to a per-line scanner and every such
    legitimate call misreports as a false no-filter failure."""
    i, n = 0, len(lines)
    while i < n:
        first = i
        parts = [lines[i]]
        while parts[-1].rstrip().endswith("\\") and i + 1 < n:
            i += 1
            parts.append(lines[i])
        joined = " ".join(p.rstrip().rstrip("\\").rstrip() for p in parts)
        yield joined, first
        i += 1


def scan(path, lines, offset, failures):
    for line, i in logical_lines(lines):
        verdict = check_line(line)
        if verdict is None:
            continue
        ok, rule = verdict
        if ok or is_exempt(lines, i):
            continue
        failures.append(
            f"::error file={path},line={offset + i + 1}::Gate 18: "
            f"this --paginate `gh api` call ({rule}) does not emit "
            f"one JSON value per line, so it resolves to "
            f"page-shaped garbage past the first page. Rewrite it "
            f"as `{CORRECT_FORM}`, or if this read must genuinely "
            f"produce one array per page, add a same-line or "
            f"immediately-preceding `# wc-pagination-exempt: "
            f"<reason>` comment.")


def find_run_blocks(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    raw_lines = raw.splitlines()
    try:
        doc = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return
    if not isinstance(doc, dict):
        return
    steps = []
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if isinstance(job, dict):
                steps.extend(job.get("steps") or [])
    runs_block = doc.get("runs")
    if isinstance(runs_block, dict):
        steps.extend(runs_block.get("steps") or [])
    cursor = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if not run:
            continue
        run = str(run)
        inner = run.splitlines()
        anchor_idx = next((i for i, l in enumerate(inner) if l.strip()), None)
        if anchor_idx is None:
            continue
        anchor_text = inner[anchor_idx].strip()
        found = next((i for i in range(cursor, len(raw_lines))
                     if raw_lines[i].strip() == anchor_text), None)
        if found is None:
            found = next((i for i in range(len(raw_lines))
                         if raw_lines[i].strip() == anchor_text), None)
        if found is None:
            continue
        first_line_no = found - anchor_idx + 1
        cursor = found + 1
        yield inner, first_line_no - 1


LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"

# Without this, running from anywhere but the repository root makes the
# workflow and action globs below match nothing while the `**/*.py` sweep
# still matches whatever happens to be under the cwd, so the scan reports
# "scanned every workflow, composite action, and checked-in script; 0
# failure(s)" having scanned none of them - a pass it did not earn, and the
# same shape as #213 in the very file #213 created. The globs are relative
# by design (failure lines must be repo-relative for `::error file=` to
# resolve), so the cwd is load-bearing and has to be asserted, not assumed.
#
# `--fixture-root` exists because verify-gate-18.py drives THIS scan against
# synthetic trees, and two of its thirteen fixtures deliberately contain no
# .github/workflows/ at all (a composite action alone; a bare scripts/*.sh)
# - the reach-beyond-workflows coverage that is the point of those cases.
# No content heuristic can tell such a tree from a wrong cwd, so the caller
# that knows has to say so. Production never passes it: CI and
# run-local-gates.py both invoke this bare, which is the guarded path.
if "--fixture-root" not in sys.argv and not os.path.isfile(LINT_WORKFLOW):
    sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

failures = []
for path in sorted(glob.glob(".github/workflows/*.yml")
                   + glob.glob(".github/workflows/*.yaml")
                   + glob.glob(".github/actions/**/action.yml", recursive=True)
                   + glob.glob(".github/actions/**/action.yaml", recursive=True)):
    for inner_lines, offset in find_run_blocks(path):
        scan(path, inner_lines, offset, failures)

for path in sorted(set(glob.glob("**/*.sh", recursive=True)
                       + glob.glob("**/*.py", recursive=True))):
    norm = path.replace(os.sep, "/")
    if norm == EXCLUDE_DIR or norm.startswith(EXCLUDE_DIR + "/"):
        continue
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    scan(norm, lines, 0, failures)

for f in failures:
    print(f)
print(f"Gate 18: scanned every workflow, composite action, and "
      f"checked-in script; {len(failures)} failure(s).")
sys.exit(1 if failures else 0)
