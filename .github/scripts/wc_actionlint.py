#!/usr/bin/env python3
"""What the two actionlint gates share, so they cannot disagree.

Gate 46 (verify-actionlint.py) is the schema/expression pass over every
workflow file, with shellcheck off. Gate 48 (verify-stage-shell-lint.py)
is the shellcheck pass over the opt-in list of stages, and the closure
check that says every published stage is either on that list or
knowingly off it. release.yml's Gate 1a runs both scripts at release
time; lint-workflows.yml runs both on every pull request. What they
share is the pinned-binary cache and the allowance strings below.

TWO THINGS LIVE HERE
--------------------
1. THE ALLOWANCE DIAGNOSTICS pass 1 accounts for: three actionlint-1.7.7
   schema-gap diagnostics counted one-per-binding
   (verify-actionlint.classify) and a fourth -ignore'd outright. They
   are constants of Gate 46 alone today -- pass 2 no longer runs
   actionlint at all (see verify-stage-shell-lint.py for why), so there
   is no second -ignore list for them to drift from. Until #291 there
   was: release.yml's pass 2 knew two of the four, #286 taught pass 1
   the container.credentials pair, and the 2026-09-08 v2.7.0 dispatch
   went red on 44 of them (#290). Kept here rather than in
   verify-actionlint.py so that if a second consumer ever appears it
   reads the same tuple rather than copying it.

2. THE PINNED-BINARY FETCHER. Neither actionlint nor shellcheck is on a
   maintainer's Windows machine, and actionlint silently DISABLES its
   shellcheck integration when the command is not found -- so a gate
   that relied on PATH would pass locally by linting less than CI.
   Both binaries are downloaded once, at a pinned version, into a
   version-named directory under the OS temp dir (RUNNER_TEMP in CI):
   a lint gate has no business leaving a file in the tree it lints,
   and the version in the directory name makes a bump a fresh download
   rather than a stale hit. Every archive is sha256-checked against the
   pin below BEFORE anything is extracted: a release asset that has
   been replaced, or a download that was tampered with in flight, fails
   the gate rather than running on a maintainer's machine.

   Where the hashes came from. actionlint's are copied from the
   publisher's actionlint_1.7.7_checksums.txt release asset. shellcheck
   publishes no checksum file, so each 0.10.0 asset was downloaded once
   from the release page on 2026-09-12 and hashed (sha256) here; a
   mismatch on a future download therefore means the asset changed
   after that date. A version bump replaces every entry.
"""
import hashlib
import io
import os
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ACTIONLINT_VERSION = "1.7.7"
SHELLCHECK_VERSION = "0.10.0"

# sha256 of each release archive, keyed by the (osname, arch) host() returns.
# actionlint: actionlint_1.7.7_checksums.txt. shellcheck: hashed from the
# assets, see the docstring.
ACTIONLINT_SHA256 = {
    ("windows", "amd64"): "7f12f1801bca3d480d67aaf7774f4c2a6359a3ca8eebe382c95c10c9704aa731",
    ("windows", "arm64"): "76e9514cfac18e5677aa04f3a89873c981f16a2f2353bb97372a86cd09b1f5a8",
    ("linux", "amd64"): "023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757",
    ("linux", "arm64"): "401942f9c24ed71e4fe71b76c7d638f66d8633575c4016efd2977ce7c28317d0",
    ("darwin", "amd64"): "28e5de5a05fc558474f638323d736d822fff183d2d492f0aecb2b73cc44584f5",
    ("darwin", "arm64"): "2693315b9093aeacb4ebd91a993fea54fc215057bf0da2659056b4bc033873db",
}
SHELLCHECK_SHA256 = {
    # shellcheck ships one Windows archive (x86-64), used on arm64 too.
    ("windows", "amd64"): "eb6cd53a54ea97a56540e9d296ce7e2fa68715aa507ff23574646c1e12b2e143",
    ("windows", "arm64"): "eb6cd53a54ea97a56540e9d296ce7e2fa68715aa507ff23574646c1e12b2e143",
    ("linux", "amd64"): "6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87",
    ("linux", "arm64"): "324a7e89de8fa2aed0d0c28f3dab59cf84c6d74264022c00c22af665ed1a09bb",
    ("darwin", "amd64"): "ef27684f23279d112d8ad84e0823642e43f838993bbb8c0963db9b58a90464c2",
    ("darwin", "arm64"): "bbd2f14826328eee7679da7221f2bc3afb011f6a928b848c80c321f6046ddf81",
}

# Ignored outright by both passes: a documented context property 1.7.7
# does not know (specs/031 research.md D3). The message names the
# property, so nothing else can hide behind the pattern.
IGNORED = 'property "job_workflow_sha" is not defined'
# Counted by pass 1, one diagnostic per binding, so each allowance goes
# loudly stale the day actionlint learns the shape -- see
# verify-actionlint.py's docstring for the evidence behind each.
KNOWN = 'unexpected key "deployment" for "environment" section'
CRED_SCALAR = '"credentials" section is scalar node but mapping node is expected'
CRED_USERPASS = 'both "username" and "password" must be specified in "credentials" section'
COUNTED = (KNOWN, CRED_SCALAR, CRED_USERPASS)


def _cache_root():
    return os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()


def host():
    """(osname, machine) the way the release archives spell them.

    osname: "windows" | "darwin" | "linux". machine: "amd64" | "arm64".
    """
    machine = os.environ.get("PROCESSOR_ARCHITECTURE", "") \
        if os.name == "nt" else os.uname().machine
    arch = "arm64" if machine.lower() in ("arm64", "aarch64") else "amd64"
    if sys.platform.startswith("win"):
        return "windows", arch
    if sys.platform == "darwin":
        return "darwin", arch
    return "linux", arch


def ensure_pinned_tool(cache_name, exe_name, url, member, sha256,
                       cache_root=None):
    """Path to a pinned binary, downloading `url` into the temp cache once.

    `member` is the archive entry holding the binary; the archive kind
    is read off the URL (.zip, .tar.gz, .tar.xz). The target is
    <cache>/<cache_name>/<exe_name>; the version belongs in cache_name.
    `sha256` is the archive's expected digest, checked before
    extraction; a mismatch is a hard failure, never a warning.
    `cache_root` overrides the OS temp dir (self-tests only).

    Extracted next to the target under a per-process name and renamed
    into place, so a second process racing this one sees either nothing
    or a whole binary. The pid matters: run-local-gates.py runs a gate
    and its --self-test concurrently (--jobs), and on a cold cache both
    start here at once -- a shared ".part" would have them writing one
    file together and renaming a torn binary into place (or, on
    Windows, failing the rename on the other's open handle).
    """
    cache = os.path.join(cache_root or _cache_root(), cache_name)
    target = os.path.join(cache, exe_name)
    if os.path.exists(target):
        return target
    os.makedirs(cache, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = resp.read()
    except OSError as e:
        sys.exit(f"could not download {exe_name} ({url}): {e}. If this "
                 f"machine is offline, note that CI runs this gate "
                 f"regardless -- it is not skippable by being unreachable.")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != sha256:
        sys.exit(f"sha256 mismatch for {url}: expected {sha256}, got "
                 f"{digest} ({len(payload)} bytes). The release asset is "
                 f"not the one this repository pinned; nothing was "
                 f"extracted. If the publisher re-cut the asset, update "
                 f"the pin in wc_actionlint.py deliberately.")
    part = f"{target}.{os.getpid()}.part"
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as z, \
                open(part, "wb") as out:
            out.write(z.read(member))
    else:
        mode = "r:xz" if url.endswith(".tar.xz") else "r:gz"
        with tarfile.open(fileobj=io.BytesIO(payload), mode=mode) as t:
            with t.extractfile(member) as src, open(part, "wb") as out:
                out.write(src.read())
        os.chmod(part, os.stat(part).st_mode
                 | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        if os.path.exists(target):
            os.remove(part)        # a sibling won the race; its copy is whole
        else:
            os.replace(part, target)
    except OSError:
        # The rename lost to a sibling that renamed -- and may already be
        # executing -- its own copy (Windows refuses to replace a running
        # exe). Theirs is whole; keep it and drop ours.
        if not os.path.exists(target):
            raise
        try:
            os.remove(part)
        except OSError:
            pass
    return target


def _pin(table, osname, arch):
    try:
        return table[(osname, arch)]
    except KeyError:
        sys.exit(f"no pinned sha256 for {osname}/{arch}; add the archive's "
                 f"digest to wc_actionlint.py before this host can run the "
                 f"gate.")


def ensure_actionlint():
    """Path to the pinned actionlint (rhysd/actionlint releases)."""
    osname, arch = host()
    exe = "actionlint.exe" if osname == "windows" else "actionlint"
    ext = "zip" if osname == "windows" else "tar.gz"
    url = (f"https://github.com/rhysd/actionlint/releases/download/"
           f"v{ACTIONLINT_VERSION}/actionlint_{ACTIONLINT_VERSION}_"
           f"{osname}_{arch}.{ext}")
    return ensure_pinned_tool(f"wc-actionlint-{ACTIONLINT_VERSION}", exe,
                              url, exe, _pin(ACTIONLINT_SHA256, osname, arch))


def ensure_shellcheck():
    """Path to the pinned shellcheck (koalaman/shellcheck releases).

    The Windows release is a flat zip; linux/darwin are tar.xz with the
    binary under a version-named directory, and spell the machine
    x86_64/aarch64 rather than actionlint's amd64/arm64.
    """
    osname, arch = host()
    base = (f"https://github.com/koalaman/shellcheck/releases/download/"
            f"v{SHELLCHECK_VERSION}/shellcheck-v{SHELLCHECK_VERSION}")
    if osname == "windows":
        exe, url, member = "shellcheck.exe", f"{base}.zip", "shellcheck.exe"
    else:
        machine = "aarch64" if arch == "arm64" else "x86_64"
        exe = "shellcheck"
        url = f"{base}.{osname}.{machine}.tar.xz"
        member = f"shellcheck-v{SHELLCHECK_VERSION}/shellcheck"
    return ensure_pinned_tool(f"wc-shellcheck-{SHELLCHECK_VERSION}", exe,
                              url, member, _pin(SHELLCHECK_SHA256, osname, arch))
