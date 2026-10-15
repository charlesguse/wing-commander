#!/usr/bin/env python3
"""Gate: spec-meta.json self-identity, in a project and after graduation
(spec 114 FR-008, FR-016, US4).

Drives the real `_shared/read-spec-meta.sh` -- the one reader every stage
reaches through wing-commander-spec-meta -- against scratch repositories with
a scratch bare origin, over two fixture sets:

  * fixtures/project-graduation/cases.json: a project folder whose records
    carry the project-relative `spec_dir = specs/<NNN-slug>` and a
    `spec_branch` that will not resolve once copied. Each record is read once
    at `P/specs/<NNN-slug>` on `<prefix>P/<NNN-slug>` and once again after the
    folder is copied to a repository root, at `specs/<NNN-slug>` on
    `<prefix><NNN-slug>`. Both rules hold at both places: a project-relative
    record passes, a record carrying the project path is refused. The copied
    project's next feature number continues its own sequence;
  * fixtures/project-root-compat/cases.json: a root record written before
    spec 114 still passes unchanged (FR-016).

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED = os.path.join(ROOT, ".github", "actions", "_shared")
READER = os.path.join(SHARED, "read-spec-meta.sh")
NAMES = os.path.join(SHARED, "project-name.sh")
GRADUATION = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-graduation", "cases.json")
ROOT_COMPAT = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-root-compat", "cases.json")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(tmp, files, branches):
    """A clone of a fresh bare origin whose `branches` all carry `files`."""
    origin, work = os.path.join(tmp, "origin.git"), os.path.join(tmp, "work")
    git(tmp, "init", "-q", "--bare", origin)
    git(tmp, "init", "-q", work)
    git(work, "config", "user.email", "g@example.invalid")
    git(work, "config", "user.name", "gate")
    git(work, "remote", "add", "origin", origin)
    for rel, record in files.items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "records")
    for b in branches:
        git(work, "push", "-q", "origin", f"HEAD:refs/heads/{b}")
    return work


def read(work, prefix, slug, spec_dir=""):
    r = subprocess.run(["bash", READER, prefix, slug, spec_dir], cwd=work,
                       capture_output=True, text=True, check=False)
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def check_place(where, work, prefix, project, cases, errors):
    for case in cases:
        slug = f"{project}/{case['slug']}" if project else case["slug"]
        got = read(work, prefix, slug)
        ok = got.get("meta_identity_ok") == "true"
        if got.get("meta_found") != "true":
            errors.append(f"{where} {slug}: record not found ({got!r})")
        elif ok != case["identity_ok"]:
            errors.append(f"{where} {slug}: identity_ok={ok}, want {case['identity_ok']}")
        elif ok and got.get("meta_issue") != case["issue"]:
            errors.append(f"{where} {slug}: issue {got.get('meta_issue')!r}, want {case['issue']!r}")


def main():
    with open(GRADUATION, encoding="utf-8") as fh:
        grad = json.load(fh)
    with open(ROOT_COMPAT, encoding="utf-8") as fh:
        compat = json.load(fh)
    prefix = grad["env"]["SPEC_PREFIX"]
    project = grad["project"]
    errors = []
    checked = 0
    # In the project: P/specs/<NNN-slug> on <prefix>P/<NNN-slug>.
    with tempfile.TemporaryDirectory() as tmp:
        files = {f"{project}/{rel}": rec for rel, rec in grad["folder"].items()}
        branches = [f"{prefix}{project}/{c['slug']}" for c in grad["identity"]]
        work = repo(tmp, files, branches)
        check_place("in project", work, prefix, project, grad["identity"], errors)
        checked += len(grad["identity"])
    # Copied out to a root: the same bytes at specs/<NNN-slug>; the records'
    # spec_branch names a project branch that does not exist here, and no
    # reader requires it to resolve.
    with tempfile.TemporaryDirectory() as tmp:
        branches = [f"{prefix}{c['slug']}" for c in grad["identity"]]
        work = repo(tmp, dict(grad["folder"]), branches)
        check_place("graduated", work, prefix, "", grad["identity"], errors)
        checked += len(grad["identity"])
        r = subprocess.run(["bash", NAMES, "next-number", ""], cwd=work, capture_output=True,
                           text=True, env={**os.environ, **grad["env"]}, check=False)
        if r.stdout.strip() != grad["next_number"]:
            errors.append(f"graduated next-number {r.stdout.strip()!r}, want {grad['next_number']!r} ({r.stderr.strip()!r})")
    # A root record written before spec 114 (FR-016).
    pre = compat["pre_feature_spec_meta"]
    with tempfile.TemporaryDirectory() as tmp:
        slug = pre["record"]["spec_dir"].split("/", 1)[1]
        work = repo(tmp, {pre["path"]: pre["record"]}, [f"{prefix}{slug}"])
        got = read(work, prefix, slug)
        if got.get("meta_identity_ok") != "true" or got.get("meta_issue") != str(pre["record"]["issue"]):
            errors.append(f"pre-feature root record no longer passes: {got!r}")
        checked += 1
    # The slug's project and the spec directory's must agree: alpha's branch
    # carries beta's folder too, and reading beta's record off alpha's branch
    # (or a root slug's branch) is not this specification's record.
    with tempfile.TemporaryDirectory() as tmp:
        record = {"spec_dir": "specs/001-x", "issue": 7, "stage": "plan", "iteration": 1}
        files = {f"{p}/specs/001-x/spec-meta.json": record for p in ("alpha", "beta")}
        work = repo(tmp, files, [f"{prefix}alpha/001-x", f"{prefix}001-x"])
        for slug, spec_dir in (("alpha/001-x", "beta/specs/001-x"), ("001-x", "beta/specs/001-x"),
                               ("alpha/001-x", "specs/001-x")):
            got = read(work, prefix, slug, spec_dir)
            if got.get("meta_found") == "true" or got.get("meta_identity_ok") == "true":
                errors.append(f"cross-project read: slug {slug!r} with spec-dir {spec_dir!r} read a record ({got!r})")
            checked += 1
        got = read(work, prefix, "alpha/001-x", "alpha/specs/001-x")
        if got.get("meta_identity_ok") != "true":
            errors.append(f"same-project read: slug 'alpha/001-x' with spec-dir 'alpha/specs/001-x' refused ({got!r})")
        checked += 1
    if errors:
        print("verify-spec-meta-self-identity: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-spec-meta-self-identity: OK ({checked} record read(s), graduation numbering checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
