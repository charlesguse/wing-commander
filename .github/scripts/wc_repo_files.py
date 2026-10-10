#!/usr/bin/env python3
"""Which files are the repository, for a gate that scans all of them.

repo_files(root) -> the git-tracked files (`git ls-files -z`),
repo-root-relative and '/'-separated, when `root` is the top of a git
working tree: the repository's content is what is committed, not whatever
else sits on disk. An implement run checks the pipeline repository out at
`.wing-commander-pipeline/` beside the tree under test, untracked, and a
developer's `.claude/worktrees/*` hold whole other checkouts; walking the
filesystem scanned those copies and failed gates on every implement cycle
(#808, #822, #823). Same idiom as verify-stage-tool-lists.py's
_glob_has_match(). Outside a git working tree (a synthetic fixture), or
when git cannot answer, the on-disk files stand in for tracked ones,
`.git/` excluded. That only adds files: a gate that hunts for copies
fails rather than passes, but one that asks whether a file exists can
be satisfied by an untracked leftover. git runs without the variables that locate a repository
(LOCATING_ENV), so a hook's GIT_DIR cannot point it at another one. The
GIT_CONFIG_* entries stay: in a caller's container they carry the
safe.directory setting git needs to read a workspace owned by another
uid (clarify.yml), and without it every listing would fall back to the
walk.
"""
import os
import subprocess

LOCATING_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE", "GIT_PREFIX")


def git_env(environ=None):
    """`environ` (default os.environ) without LOCATING_ENV."""
    environ = os.environ if environ is None else environ
    return {k: v for k, v in environ.items() if k not in LOCATING_ENV}


def _git(root, *args):
    env = git_env()
    return subprocess.run(["git", "-C", root, *args], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def repo_files(root="."):
    """-> sorted repo-root-relative paths of the repository's files."""
    try:
        top = _git(root, "rev-parse", "--show-toplevel")
        # Only when root IS the top: a fixture directory nested inside some
        # other repository's work tree is not that repository.
        same = os.path.normcase(os.path.realpath(os.fsdecode(top.stdout).strip()))
        if top.returncode == 0 and same == os.path.normcase(os.path.realpath(root)):
            proc = _git(root, "ls-files", "-z")
            if proc.returncode == 0:
                return sorted(os.fsdecode(p) for p in proc.stdout.split(b"\0") if p)
    except OSError:
        pass
    rels = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            rels.append(os.path.relpath(
                os.path.join(dirpath, filename), root).replace(os.sep, "/"))
    return sorted(rels)
