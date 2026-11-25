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
   pin BEFORE anything is extracted: a release asset that has
   been replaced, or a download that was tampered with in flight, fails
   the gate rather than running on a maintainer's machine.

   Where the hashes came from. actionlint's are copied from the
   publisher's actionlint_1.7.7_checksums.txt release asset; a version
   bump replaces every entry. shellcheck's version and hashes are not
   kept here: they live in SHELLCHECK_PIN_FILE, which the e2e reference
   image's Dockerfile also reads, so the shellcheck this gate runs and
   the one the implement agent runs inside that image cannot drift
   (#1204). That file says where its hashes came from.
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

# sha256 of each release archive, keyed by the (osname, arch) host() returns.
# actionlint: actionlint_1.7.7_checksums.txt.
ACTIONLINT_SHA256 = {
    ("windows", "amd64"): "7f12f1801bca3d480d67aaf7774f4c2a6359a3ca8eebe382c95c10c9704aa731",
    ("windows", "arm64"): "76e9514cfac18e5677aa04f3a89873c981f16a2f2353bb97372a86cd09b1f5a8",
    ("linux", "amd64"): "023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757",
    ("linux", "arm64"): "401942f9c24ed71e4fe71b76c7d638f66d8633575c4016efd2977ce7c28317d0",
    ("darwin", "amd64"): "28e5de5a05fc558474f638323d736d822fff183d2d492f0aecb2b73cc44584f5",
    ("darwin", "arm64"): "2693315b9093aeacb4ebd91a993fea54fc215057bf0da2659056b4bc033873db",
}

# The shellcheck pin's one home, in the reference image's build context
# because docker build reads nothing outside it -- see the file's header.
SHELLCHECK_PIN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "docker",
    "e2e-reference-image", "shellcheck.pin")


def read_shellcheck_pin(path=SHELLCHECK_PIN_FILE):
    """-> (version, {(osname, arch): sha256}) from the pin file.

    Lines are `version=X` and `sha256.<os>.<arch>=<hex>`; `#` lines and
    blanks are skipped. Anything else, a repeated key, a key line with
    whitespace around it, or a file with no version is a hard failure: a
    pin that half-parses would download one version and hash-check
    another. Whitespace fails rather than being stripped because the
    Dockerfile's sed reads the same lines and would keep it (#1204); a CR
    line ending is the one thing both readers drop. shellcheck ships one
    Windows archive (x86-64), so a windows/amd64 hash also answers for
    windows/arm64.
    """
    version, table = None, {}
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line != line.strip():
                sys.exit(f"{path}:{n}: whitespace around a pin line, which the "
                         f"reference image's Dockerfile would read differently: "
                         f"{line!r}")
            key, sep, value = line.partition("=")
            parts = key.split(".")
            if sep and key == "version" and version is None and value:
                version = value
            elif (sep and len(parts) == 3 and parts[0] == "sha256"
                  and (parts[1], parts[2]) not in table
                  and len(value) == 64
                  and all(c in "0123456789abcdef" for c in value)):
                table[(parts[1], parts[2])] = value
            else:
                sys.exit(f"{path}:{n}: not a `version=` or `sha256.<os>.<arch>="
                         f"<64 hex>` line, or a repeat of one: {line!r}")
    if version is None:
        sys.exit(f"{path}: no `version=` line")
    if ("windows", "amd64") in table:
        table.setdefault(("windows", "arm64"), table[("windows", "amd64")])
    return version, table


SHELLCHECK_VERSION, SHELLCHECK_SHA256 = read_shellcheck_pin()

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
                       cache_root=None, home="wc_actionlint.py"):
    """Path to a pinned binary, downloading `url` into the temp cache once.

    `member` is the archive entry holding the binary; the archive kind
    is read off the URL (.zip, .tar.gz, .tar.xz). The target is
    <cache>/<cache_name>/<exe_name>; the version belongs in cache_name.
    `sha256` is the archive's expected digest, checked before
    extraction; a mismatch is a hard failure, never a warning.
    `cache_root` overrides the OS temp dir (self-tests only). `home` is
    the file that holds the pin, named when the digest does not match.

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
                 f"the pin in {home} deliberately.")
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


def _pin(table, osname, arch, home="wc_actionlint.py"):
    """`home` is the file a maintainer adds the missing digest to:
    shellcheck's live only in SHELLCHECK_PIN_FILE (#1204)."""
    try:
        return table[(osname, arch)]
    except KeyError:
        sys.exit(f"no pinned sha256 for {osname}/{arch}; add the archive's "
                 f"digest to {home} before this host can run the gate.")


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
                              url, member, _pin(SHELLCHECK_SHA256, osname, arch,
                                                SHELLCHECK_PIN_FILE),
                              home=SHELLCHECK_PIN_FILE)
