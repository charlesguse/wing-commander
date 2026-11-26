#!/usr/bin/env python3
"""Gate: project-aware files hold no root-only path pattern (spec 114 FR-020).

A file converted for subfolder projects must reach the spec directory, the
Spec Kit state and the skills through the shared project logic
(`_shared/project-name.sh`, the `wing-commander-project` composite), never by
rebuilding a root-only path or splitting a name by hand. Six patterns count:

  root-spec-dir        a spec directory built as `specs/<any variable>`
  root-specify         a bare `.specify/` path (no project prefix before it)
  root-specs-scan      a `ls`/`find` over a bare `specs/`
  root-skill-path      a bare `.claude/skills/speckit-*` path
  inline-project-split a project or NNN-slug cut out of a slug, spec dir or
                       branch with `%/*`, `##*/`, `%specs/*` or `%%/specs/*`
  inline-kv-helper     a copy of the `kv KEY TEXT` body that reads one key of
                       the parser's output; its one home is _shared/kv.sh

A Windows separator reads as `/`.

Each converted file may keep a fixed number of hits (its documented root
branch: the empty-project case that must stay byte-identical); a hit beyond
that count fails. Reject fixtures under fixtures/project-single-home/ each
carry one pattern and must be caught; accept.txt must stay clean.

The inline-project-split allowances are also run (#889, folded from
#1036): every allowed hit must sit in a step INLINE_SPLIT_SITES lists, and
each listed step is executed as shipped on a root, a one-segment and a
nested project name (an implement branch with -iterN too), its outputs
compared with `project-name.sh names`. SPLIT_PARITY_MUTATIONS are
hand-edits the comparison must catch.

project-name.sh is the home of the rules and is not scanned. Every other
published stage workflow (on.workflow_call), every composite under
.github/actions/ and every shared script under .github/actions/_shared/ is
scanned (T046); a file absent from ALLOWED may hold no hit at all.
Exit 0 when the gate holds; 1 otherwise.
"""
import glob
import os
import re
import sys

from wc_published_stages import published_stages

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-single-home")
HOME = ".github/actions/_shared/project-name.sh"

PATTERNS = {
    # Any variable or expression right after a bare `specs/` -- `$feature`,
    # `${name}`, `${{ inputs.x }}` -- not only one named like a slug.
    "root-spec-dir": re.compile(r"""(?:^|[\s"'(=])specs/\$(?:\{\{\s*|\{)?[A-Za-z_]"""),
    "root-specify": re.compile(r"""(?:^|[\s"'(=])\.specify/"""),
    "root-specs-scan": re.compile(r"\b(?:ls|find)\s+(?:-\w+\s+)*specs/"),
    "root-skill-path": re.compile(r"""(?:^|[\s"'(=])\.claude/skills/speckit-"""),
    # A lifecycle name split by hand (T066/MF-21): the project or the bare
    # NNN-slug cut out of a slug, spec dir or branch with `%/*`, `##*/`,
    # `%specs/*` or `%%/specs/*` instead of read by the parser.
    "inline-project-split": re.compile(
        r"\$\{\w*(?:slug|SLUG|spec_dir|SPEC_DIR|record_dir|branch|BRANCH)\w*(?:%/\*|##\*/|%specs/\*|%%/specs/\*)\}"),
    # The kv helper's body, pasted instead of sourcing _shared/kv.sh.
    "inline-kv-helper": re.compile(r"""sed\s+-n\s+["']s/\^\$\{?1\}?=//p"""),
}

# file -> {pattern: hits allowed}. A hit is a documented root branch.
ALLOWED = {
    # spec-dir-rel is project-relative by definition.
    ".github/actions/wing-commander-project/action.yml": {"root-spec-dir": 1},
    ".github/actions/wing-commander-context/action.yml": {"root-spec-dir": 1},
    # Two input-description lines name the artifacts in prose; the third
    # skill hit is the root branch's `ls -d` (the empty-project case).
    ".github/actions/wing-commander-preflight/action.yml": {
        "root-specify": 2, "root-skill-path": 3},
    # The two `case` arms that match a root `.specify/` script grant to
    # derive its P-prefixed twin (spec 114, FR-006).
    ".github/actions/wing-commander-tool-args/action.yml": {"root-specify": 2},
    # Each agent step's literal default-allowed-tools (Gate 27 reads it as a
    # literal list) grants the root-form `.specify/` scripts; tool-args adds
    # the project's twin, so the literal is the root branch.
    ".github/workflows/implement.yml": {"root-specify": 2},
    ".github/workflows/plan.yml": {"root-specify": 2},
    ".github/workflows/tasks.yml": {"root-specify": 2},
    # The project-guidance prose names "its .specify/" for a routed project.
    ".github/workflows/intake.yml": {"root-specify": 1},
    # rel_dir is the project-relative spec_dir spec-meta.json records.
    ".github/workflows/rebase.yml": {"root-spec-dir": 1},
    # Upgrades the adopter's root Spec Kit install, which is not a lifecycle
    # and has no project; a subfolder project's own upgrade is out of scope.
    # The 13th root-specify hit is comment-reply's guard reading that same
    # root pin to refuse a candidate not newer than it (#1267).
    ".github/workflows/auto-update-spec-kit.yml": {"root-specify": 13, "root-skill-path": 1},
    # The kv helper's one home.
    ".github/actions/_shared/kv.sh": {"inline-kv-helper": 1},
}

# inline-project-split hits that cannot reach the parser: each sits in a job
# that runs before any pipeline checkout exists (a one-step pre-job whose
# outputs name the next job's concurrency group), or in the credential-free
# gate-suite job, where wing-commander-project's token-bearing callout may
# not run. Each validates the name's shape first, and the job that acts on
# the value re-reads it through wing-commander-project, which refuses any
# name the inline split would read differently. check_split_parity()
# runs each of them against the parser, so an allowance is never just
# trusted.
INLINE_SPLIT_ALLOWED = {
    ".github/workflows/plan.yml": 2,              # resolve-spec
    ".github/workflows/tasks.yml": 6,             # resolve-spec x3
    ".github/workflows/cleanup.yml": 1,           # select
    ".github/workflows/pr-conversation.yml": 2,   # resolve-identity
    ".github/workflows/implement.yml": 1,         # gate-suite-implement-cycle
}
for _rel, _n in INLINE_SPLIT_ALLOWED.items():
    ALLOWED.setdefault(_rel, {})["inline-project-split"] = _n

# Where each INLINE_SPLIT_ALLOWED hit lives: (file, job, step id). The
# split-parity check (#889, folded from #1036) runs every one of these
# steps as shipped, on the fixture names below, and fails when a step
# reads a name differently from `_shared/project-name.sh names`. Every
# allowed hit must sit in a listed step, so a new inline split cannot
# reach the allowance without a parity run behind it.
INLINE_SPLIT_SITES = (
    (".github/workflows/plan.yml", "resolve-spec", "spec"),
    (".github/workflows/tasks.yml", "resolve-spec", "spec"),
    (".github/workflows/tasks.yml", "stalled", "identity"),
    (".github/workflows/tasks.yml", "stalled-approved", "identity"),
    (".github/workflows/cleanup.yml", "select", "pick"),
    (".github/workflows/pr-conversation.yml", "resolve-identity", "identity"),
    (".github/workflows/implement.yml", "gate-suite-implement-cycle", "head"),
)
# Root, one project segment and a nested project; implement branches also
# carry -iterN.
SPLIT_FIXTURE_NAMES = ("001-root-feature", "web/012-add-thing", "apps/web/013-deep-nest")
SPLIT_PREFIXES = {
    "SPEC_DRAFT_PREFIX": "spec-draft/", "SPEC_PREFIX": "spec/",
    "PLAN_PREFIX": "plan/", "TASKS_PREFIX": "tasks/", "IMPL_PREFIX": "impl/",
}


def scan(text):
    """{pattern: count} over non-comment lines of `text`."""
    counts = {name: 0 for name in PATTERNS}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        # A Windows separator (`specs\$slug`, `.specify\`) is the same path.
        line = line.replace("\\\\", "/").replace("\\", "/")
        for name, rx in PATTERNS.items():
            if rx.search(line):
                counts[name] += 1
    return counts


def scope():
    """Repository-relative paths of every file this gate scans."""
    files = {os.path.relpath(p, ROOT) for p in published_stages(ROOT)}
    actions = os.path.join(ROOT, ".github", "actions")
    for pattern in ("*/action.yml", "*/action.yaml", "_shared/*.sh"):
        files |= {os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(actions, pattern))}
    files.discard(HOME)
    return sorted(f.replace(os.sep, "/") for f in files)


def _split_hits(text):
    return scan(text)["inline-project-split"]


def _load_steps(texts):
    """{(file, job, step id): step} for INLINE_SPLIT_SITES, from `texts`
    ({file: workflow text}); a missing site is reported, not raised."""
    import yaml

    steps, errors = {}, []
    docs = {}
    for rel, job, sid in INLINE_SPLIT_SITES:
        if rel not in docs:
            docs[rel] = yaml.safe_load(texts[rel])
        found = [st for st in (docs[rel].get("jobs", {}).get(job, {}).get("steps") or [])
                 if st.get("id") == sid]
        if len(found) != 1:
            errors.append(f"{rel}: split-parity site {job}/{sid} not found (update INLINE_SPLIT_SITES)")
        else:
            steps[(rel, job, sid)] = found[0]
    return steps, errors


def _parser(kind, name):
    import subprocess

    out = subprocess.run(
        ["bash", os.path.join(ROOT, HOME), "names", kind, name],
        capture_output=True, text=True, env={**os.environ, **SPLIT_PREFIXES})
    if out.returncode != 0:
        raise RuntimeError(f"project-name.sh names {kind} {name}: {out.stderr.strip()}")
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)


def _run_step(step, env, tmp):
    """Run a step's `run:` as the runner would (its shell), with `env` and
    a `gh` stub; return its GITHUB_OUTPUT as a dict, or (None, reason)."""
    import subprocess

    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    stub = os.path.join(bindir, "gh")
    with open(stub, "w", encoding="utf-8") as fh:
        fh.write(
            "#!/usr/bin/env bash\n"
            "case \"$*\" in\n"
            "  *defaultBranchRef*) echo main ;;\n"
            "  *baseRefName*) echo \"$STUB_BASE_REF\" ;;\n"
            "  *headRefName*) echo \"$STUB_HEAD_REF\" ;;\n"
            "  *) echo \"gh stub: unexpected call: $*\" >&2; exit 1 ;;\n"
            "esac\n")
    os.chmod(stub, 0o755)
    script = os.path.join(tmp, "step.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(step["run"])
    output = os.path.join(tmp, "output")
    open(output, "w").close()
    full_env = {
        "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
        "HOME": tmp, "GITHUB_OUTPUT": output,
        "GITHUB_STEP_SUMMARY": os.path.join(tmp, "summary"),
        "GITHUB_REPOSITORY": "owner/repo", **env,
    }
    flags = ["--noprofile", "--norc", "-eo", "pipefail"] if step.get("shell") == "bash" else ["-e"]
    res = subprocess.run(["bash", *flags, script], capture_output=True, text=True,
                         env=full_env, cwd=tmp)
    if res.returncode != 0:
        return None, f"exited {res.returncode}: {(res.stdout + res.stderr).strip()[:300]}"
    with open(output, encoding="utf-8") as fh:
        return dict(line.split("=", 1) for line in fh.read().splitlines() if "=" in line), None


def _site_cases(rel, job, sid, name):
    """[(label, env, {output key: expected value})] for one site and one
    fixture name, every expectation taken from project-name.sh."""
    p = _parser("slug", name)
    want = {"project": p["project"], "spec-dir": p["spec_dir"]}
    if rel.endswith("plan.yml"):
        return [
            ("slug input", {"INPUT_SLUG": name, "HEAD_REF": "", **SPLIT_PREFIXES},
             {"slug": name, **want}),
            ("head ref", {"INPUT_SLUG": "", "HEAD_REF": "spec-draft/" + name, **SPLIT_PREFIXES},
             {"slug": name, **want}),
        ]
    if rel.endswith("tasks.yml"):
        keys = {"slug": name, "spec-dir": p["spec_dir"]}
        if job == "resolve-spec":
            keys["project"] = p["project"]
        cases = [("slug input", {"MODE": "draft", "INPUT_SLUG": name, "HEAD_REF": "", **SPLIT_PREFIXES}, keys)]
        for mode, prefix in (("approved", "tasks/"), ("draft", "plan/")):
            cases.append((f"{mode} head ref",
                          {"MODE": mode, "INPUT_SLUG": "", "HEAD_REF": prefix + name, **SPLIT_PREFIXES},
                          keys))
        return cases
    if rel.endswith("cleanup.yml"):
        cases = []
        for var, prefix in SPLIT_PREFIXES.items():
            ref = prefix + name + ("-iter4" if var == "IMPL_PREFIX" else "")
            b = _parser("branch", ref)
            cases.append((f"head ref {ref}",
                          {"HEAD_REF": ref, "BASE_REF": "main", "MERGED": "true", "DB": "main",
                           **SPLIT_PREFIXES},
                          {"spec-dir": b["spec_dir"]}))
        return cases
    if rel.endswith("pr-conversation.yml"):
        return [("spec branch", {"DEFAULT_BRANCH_INPUT": "main", "GH_TOKEN": "unused", "PR_NUMBER": "7",
                                 "STUB_BASE_REF": "main", "STUB_HEAD_REF": "spec/" + name,
                                 **SPLIT_PREFIXES},
                 {"qualifies": "true", "slug": name, **want})]
    if rel.endswith("implement.yml"):
        # The ref the step builds must parse back to the spec dir it was given.
        return [("spec dir", {"SPEC_DIR_INPUT": p["spec_dir"], "SPEC_PREFIX": "spec/"},
                 {"ref": "spec/" + p["qualified"]})]
    raise RuntimeError(f"no split-parity cases for {rel}")


def check_split_parity(texts, only=None):
    """Errors for INLINE_SPLIT_SITES over `texts` ({file: workflow text}):
    every allowed inline split sits in a listed step, and each listed step
    reads every fixture name the way project-name.sh does. `only` limits
    the step runs to one file (the mutation self-check)."""
    import shutil
    import tempfile

    errors = []
    steps, errors_load = _load_steps(texts)
    errors += errors_load
    for rel, allowed in INLINE_SPLIT_ALLOWED.items():
        in_sites = sum(_split_hits(st.get("run", "")) for (r, _j, _s), st in steps.items() if r == rel)
        total = _split_hits(texts[rel])
        if total != in_sites:
            errors.append(f"{rel}: {total - in_sites} inline-project-split hit(s) outside the "
                          "INLINE_SPLIT_SITES steps -- list the step so its split is run against the parser")
        if in_sites != allowed:
            errors.append(f"{rel}: the INLINE_SPLIT_SITES steps hold {in_sites} inline split(s), "
                          f"INLINE_SPLIT_ALLOWED says {allowed}")
    for (rel, job, sid), step in steps.items():
        if only is not None and rel != only:
            continue
        for name in SPLIT_FIXTURE_NAMES:
            for label, env, want in _site_cases(rel, job, sid, name):
                tmp = tempfile.mkdtemp(prefix="wc-split-parity-")
                try:
                    got, why = _run_step(step, env, tmp)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                where = f"{rel} {job}/{sid} ({name}, {label})"
                if got is None:
                    errors.append(f"{where}: {why}")
                    continue
                for key, value in want.items():
                    if got.get(key) != value:
                        errors.append(f"{where}: {key}={got.get(key)!r}, project-name.sh reads {value!r}")
    return errors


# Mutations the split-parity check must catch, each one a plausible
# hand-edit of a listed step: (file, old, new, what it breaks).
SPLIT_PARITY_MUTATIONS = (
    (".github/workflows/plan.yml", 'project="${slug%/*}"', 'project="${slug%%/*}"',
     "a nested project cut at its first segment"),
    (".github/workflows/tasks.yml", 'specs/${slug##*/}', 'specs/${slug#*/}',
     "a spec dir that keeps the project's inner segments"),
    (".github/workflows/cleanup.yml", 'slug="${slug%-iter*}"', ':',
     "an implement branch's -iterN kept in the spec dir"),
    (".github/workflows/implement.yml", '${SPEC_DIR_INPUT#"${project_part}specs/"}',
     '${SPEC_DIR_INPUT##*/}', "a ref that drops the project"),
)


def check_split_parity_catches_mutations(texts):
    errors = []
    for rel, old, new, what in SPLIT_PARITY_MUTATIONS:
        if old not in texts[rel]:
            errors.append(f"split-parity mutation for {rel} no longer applies ({old!r}); update it")
            continue
        mutated = dict(texts)
        mutated[rel] = texts[rel].replace(old, new, 1)
        if not check_split_parity(mutated, only=rel):
            errors.append(f"split-parity check missed {what} in {rel}")
    # A split added to a step the site list does not name is refused too.
    rel = ".github/workflows/plan.yml"
    extra = dict(texts)
    extra[rel] = texts[rel].replace(
        "    steps:\n", "    steps:\n      - run: echo \"${slug##*/}\"\n", 1)
    if not any("outside the INLINE_SPLIT_SITES" in e for e in check_split_parity(extra, only=rel)):
        errors.append("split-parity check missed an inline split outside the listed steps")
    return errors


def main():
    errors = []
    files = scope()
    for rel in ALLOWED:
        if rel not in files:
            errors.append(f"{rel}: has an allowance but is not in scope (stale entry)")
    for rel in files:
        allowed = ALLOWED.get(rel, {})
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            counts = scan(fh.read())
        for name, n in counts.items():
            if n > allowed.get(name, 0):
                errors.append(
                    f"{rel}: {n} {name} hit(s), {allowed.get(name, 0)} allowed -- "
                    "route it through _shared/project-name.sh / wing-commander-project")
    caught = set()
    for fname in sorted(os.listdir(FIXTURES)):
        with open(os.path.join(FIXTURES, fname), encoding="utf-8") as fh:
            counts = scan(fh.read())
        hits = {name for name, n in counts.items() if n}
        if fname == "accept.txt":
            if hits:
                errors.append(f"fixture accept.txt wrongly flagged: {sorted(hits)}")
        elif fname.startswith("reject-"):
            # reject-<pattern>[--<variant>].txt
            name = fname[len("reject-"):].rsplit(".", 1)[0].split("--", 1)[0]
            if name not in hits:
                errors.append(f"fixture {fname} was not caught as {name}")
            caught |= hits
    for name in PATTERNS:
        if name not in caught:
            errors.append(f"pattern {name} has no reject fixture that catches it")
    split_texts = {}
    for rel in INLINE_SPLIT_ALLOWED:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            split_texts[rel] = fh.read()
    errors += check_split_parity(split_texts)
    errors += check_split_parity_catches_mutations(split_texts)
    if errors:
        print("verify-project-single-home: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-project-single-home: OK ({len(files)} file(s) in scope, {len(ALLOWED)} with allowances)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
