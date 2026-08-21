#!/usr/bin/env python3
"""Gate 26 - the versioning contract holds against the repository's real refs.

WHY THIS EXISTS
---------------
`release.yml` is the only sanctioned way to cut a release, and inside it the
exact tag and the floating major tag are pushed together:

    git tag -a  "$TAG"   -m ...  ;  git push origin "refs/tags/$TAG"
    git tag -fa "$MAJOR" -m ...  ;  git push --force origin "refs/tags/$MAJOR"

Those four lines are inseparable, so `vX` can never trail a tag the workflow
itself created. That is a fact about one code path, not an invariant about
the repository. A tag cut by hand, through the Releases UI, or with `gh
release create` produces a normal-looking release and leaves `vX` where it
was - silently. That happened on 2026-08-14 and went unnoticed for three
days (#218): every adopter pinned to `@v2` missed six `fix:` commits in the
gap, and nothing anywhere went red.

Until this gate, nothing in the repository looked at refs at all.
`lint-workflows.yml` checks twenty-odd things about the pipeline's *files*;
the tags those files are published under were unchecked (#229).

WHAT IT CHECKS
--------------
Input is the output of `git ls-remote --tags <remote>`, which resolves both
questions in one unauthenticated call. An annotated tag appears twice -

    <tag-object-sha>   refs/tags/v2.5.1
    <commit-sha>       refs/tags/v2.5.1^{}

- and a lightweight tag appears once, its single sha already the commit. So
the presence of the `^{}` peel line IS the annotated/lightweight answer, and
the sha to compare is the peeled one where it exists.

  1. Every `vX.Y.Z` and every floating `vX` is an ANNOTATED tag object.
     `release.yml` uses `git tag -a`/`-fa` without exception, so a
     lightweight tag proves the tag did not come from `release.yml`. This is
     the leading indicator: it is true the moment the tag is pushed, before
     any divergence has had time to matter.

  2. For each major X that has release tags, `vX` exists and resolves to the
     same commit as the highest `vX.Y.Z` of THAT major. Per-major on
     purpose - `v1` legitimately trails `v2.0.0` forever once a v2 exists,
     and a check written against "the newest tag" would fire on it daily.

  3. Zero release tags is a FAILURE, not a clean pass. Same reasoning as
     Gate 7's `stages == 0` guard: a check whose subject silently vanished
     reports a success indistinguishable from one that verified something.

WHAT IT DOES NOT CHECK
----------------------
Whether `vX` points at a commit that is an ancestor of `main`, or whether
the tagged commit is the one someone intended. This gate answers "do the
refs agree with each other and with the contract", not "was this the right
commit to ship" - that judgement lives with whoever dispatched the release.

SELF-TEST
---------
`--self-test` runs the check against eleven fixtures, each a scrap of
`ls-remote` text; six must fail and five must pass. A fixture that fails for
the WRONG reason is itself a failure - assertions match the substring
identifying the specific defect, not merely "not empty" (#169: a harness
that cannot tell one failure from another is not testing the branch it
claims to). The grandfathered-tag pair runs the same listing with and
without the exception applied, so the suppression is shown to suppress
something real rather than being exercised only where it changes nothing.
"""
import argparse
import re
import subprocess
import sys

LS_REMOTE_RE = re.compile(r"^([0-9a-fA-F]{40})\s+refs/tags/(.+?)(\^\{\})?$")
RELEASE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
FLOATING_RE = re.compile(r"^v(\d+)$")

# Tags that are lightweight for a known, closed reason, and are left that way
# deliberately. Each entry must say WHICH incident, because an exception
# nobody can date is indistinguishable from a bug someone silenced - the
# specific complaint #149 makes about the existing invariant gate's "one
# unnamed omission". Retagging a published tag is not the cheaper fix: it
# force-pushes a ref adopters have already fetched, and the commit it names
# is unaffected either way.
#
# An entry here suppresses ONLY the annotated-tag check, and only for the
# named tag. Check 2 still holds it to the floating-tag contract, and
# `stale_exceptions()` fails the gate if an entry stops being needed.
LIGHTWEIGHT_EXCEPTIONS = {
    "v2.4.0": (
        "cut out-of-band on 2026-08-14 (#218). The divergence it caused was "
        "repaired by moving v2 forward; the tag object itself is still the "
        "evidence that it did not come from release.yml, and is kept as-is "
        "rather than force-pushed over."
    ),
}


def parse_ls_remote(text):
    """-> (direct, peeled): name -> sha. Non-tag/malformed lines ignored."""
    direct, peeled = {}, {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LS_REMOTE_RE.match(line)
        if not m:
            continue
        sha, name, peel = m.group(1).lower(), m.group(2), m.group(3)
        (peeled if peel else direct)[name] = sha
    return direct, peeled


def check_refs(text, exceptions=None):
    """-> list of failure strings. Empty means the contract holds.

    `exceptions` overrides LIGHTWEIGHT_EXCEPTIONS. The self-test passes its
    own set so the fixtures exercise the exception MACHINERY rather than
    this repository's current grandfathered tags, which would otherwise
    have to be replicated into every fixture and would drift the moment
    one was added.
    """
    if exceptions is None:
        exceptions = LIGHTWEIGHT_EXCEPTIONS
    direct, peeled = parse_ls_remote(text)
    failures = []

    def commit_of(name):
        # An annotated tag's ref sha is the tag OBJECT; the peel line carries
        # the commit. A lightweight tag has no peel line and points directly.
        return peeled.get(name, direct.get(name))

    releases = {}   # major -> [((x, y, z), name), ...]
    floating = {}   # major -> name
    for name in sorted(set(direct) | set(peeled)):
        m = RELEASE_RE.match(name)
        if m:
            major = int(m.group(1))
            releases.setdefault(major, []).append(
                (tuple(int(g) for g in m.groups()), name))
            continue
        m = FLOATING_RE.match(name)
        if m:
            floating[int(m.group(1))] = name

    # --- 3. the empty-subject guard, first: every check below is vacuous
    # without release tags, and "no failures" would read as a clean pass.
    if not releases:
        failures.append(
            "no vX.Y.Z release tags exist on the remote at all. Either the "
            "listing could not be read or every release tag was deleted; "
            "both are conditions this gate must report rather than pass.")
        return failures

    # --- 1. annotated-ness, for release tags and floating tags alike
    named = [n for names in releases.values() for _, n in names]
    all_tags = set(named) | set(floating.values())
    for name in sorted(all_tags):
        if name not in peeled:
            if name in exceptions:
                continue
            failures.append(
                "{0} is a LIGHTWEIGHT tag. release.yml creates every tag with "
                "`git tag -a`/`-fa`, so this tag did not come from it - it was "
                "cut by hand, through the Releases UI, or with `gh release "
                "create`, and the floating major tag was not advanced with it "
                "(#218).".format(name))

    # --- 2. per-major floating-tag agreement
    for major in sorted(releases):
        _, highest_name = max(releases[major])
        float_name = floating.get(major)
        if float_name is None:
            failures.append(
                "v{0} does not exist, but {1} does. Every release.yml run "
                "creates or force-moves the floating major tag alongside the "
                "exact tag; a major with releases and no floating tag means an "
                "adopter pinned to @v{0} resolves nothing.".format(
                    major, highest_name))
            continue
        want, got = commit_of(highest_name), commit_of(float_name)
        if want != got:
            failures.append(
                "{0} resolves to {1} but the highest v{2} release, {3}, is "
                "{4}. Adopters pinned to @{0} are not receiving {3} "
                "(#218).".format(float_name, got, major, highest_name, want))

    # A floating tag for a major with no release tags at all.
    for major in sorted(set(floating) - set(releases)):
        failures.append(
            "{0} exists but no v{1}.Y.Z release tag does, so the floating tag "
            "points at something no release ever named.".format(
                floating[major], major))

    # --- an exception that is no longer needed is drift, not tidiness. If a
    # grandfathered tag becomes annotated or is deleted, the entry stops
    # documenting anything and starts hiding the next one silently.
    for name in sorted(exceptions):
        if name not in all_tags:
            failures.append(
                "{0} is listed in LIGHTWEIGHT_EXCEPTIONS but no longer exists "
                "on the remote. Remove the entry - a standing exception for a "
                "tag nobody can inspect suppresses the next tag that reuses "
                "the name.".format(name))
        elif name in peeled:
            failures.append(
                "{0} is listed in LIGHTWEIGHT_EXCEPTIONS but is now an "
                "ANNOTATED tag. The exception is stale; remove it so the check "
                "covers this tag again.".format(name))

    return failures


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
A = "a" * 40   # tag-object shas - deliberately NOT commit shas, so a check
B = "b" * 40   # that compares the wrong column fails these fixtures
C1 = "1" * 40  # commit of v1.9.0
C2 = "2" * 40  # commit of v2.0.0
C3 = "3" * 40  # commit of v2.5.1

HEALTHY = """
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
{B}\trefs/tags/v2.5.1
{C3}\trefs/tags/v2.5.1^{{}}
{A}\trefs/tags/v2
{C3}\trefs/tags/v2^{{}}
""".format(A=A, B=B, C2=C2, C3=C3)

TWO_MAJORS = """
{A}\trefs/tags/v1.9.0
{C1}\trefs/tags/v1.9.0^{{}}
{B}\trefs/tags/v1
{C1}\trefs/tags/v1^{{}}
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
{B}\trefs/tags/v2
{C2}\trefs/tags/v2^{{}}
""".format(A=A, B=B, C1=C1, C2=C2)

NOISE = """
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
{A}\trefs/tags/v2
{C2}\trefs/tags/v2^{{}}
{B}\trefs/tags/spec-kit-v0.15.1
{B}\trefs/tags/not-a-version
""".format(A=A, B=B, C2=C2)

LIGHTWEIGHT = """
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
{C3}\trefs/tags/v2.5.1
{A}\trefs/tags/v2
{C2}\trefs/tags/v2^{{}}
""".format(A=A, C2=C2, C3=C3)

TRAILING = """
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
{B}\trefs/tags/v2.5.1
{C3}\trefs/tags/v2.5.1^{{}}
{A}\trefs/tags/v2
{C2}\trefs/tags/v2^{{}}
""".format(A=A, B=B, C2=C2, C3=C3)

NO_FLOATING = """
{A}\trefs/tags/v2.0.0
{C2}\trefs/tags/v2.0.0^{{}}
""".format(A=A, C2=C2)

GRANDFATHERED = """
{A}	refs/tags/v2.0.0
{C2}	refs/tags/v2.0.0^{{}}
{C1}	refs/tags/v2.4.0
{B}	refs/tags/v2.5.1
{C3}	refs/tags/v2.5.1^{{}}
{A}	refs/tags/v2
{C3}	refs/tags/v2^{{}}
""".format(A=A, B=B, C1=C1, C2=C2, C3=C3)

FIXTURES = [
    # (name, ls-remote text, expected substring or None, exceptions)
    ("healthy single major", HEALTHY, None, {}),
    ("v1 trails v2 legitimately (per-major, must not fire)", TWO_MAJORS,
     None, {}),
    ("non-version tags are ignored", NOISE, None, {}),
    ("lightweight release tag", LIGHTWEIGHT, "v2.5.1 is a LIGHTWEIGHT tag",
     {}),
    ("floating tag trails highest same-major release", TRAILING,
     "Adopters pinned to @v2 are not receiving v2.5.1", {}),
    ("major has releases but no floating tag", NO_FLOATING,
     "v2 does not exist, but v2.0.0 does", {}),
    ("empty listing is not a clean pass", "",
     "no vX.Y.Z release tags exist on the remote at all", {}),
    # the exception machinery itself
    # this repository's real shape: one grandfathered lightweight tag,
    # floating tag correct. Must pass WITH the exception and fail
    # WITHOUT it - a suppression that suppresses nothing is not tested
    # by a fixture that only ever runs with it applied (#169).
    ("grandfathered lightweight tag is allowed", GRANDFATHERED, None,
     {"v2.4.0": "test fixture"}),
    ("the same tag WITHOUT the exception is caught", GRANDFATHERED,
     "v2.4.0 is a LIGHTWEIGHT tag", {}),
    ("an exception for an annotated tag is reported stale", HEALTHY,
     "v2.5.1 is listed in LIGHTWEIGHT_EXCEPTIONS but is now an ANNOTATED",
     {"v2.5.1": "test fixture"}),
    ("an exception for a vanished tag is reported stale", HEALTHY,
     "v9.9.9 is listed in LIGHTWEIGHT_EXCEPTIONS but no longer exists",
     {"v9.9.9": "test fixture"}),
]


def self_test():
    bad = 0
    for name, text, expect, exceptions in FIXTURES:
        failures = check_refs(text, exceptions=exceptions)
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
    print("Gate 26 self-test: {0}/{1} fixtures behaved as specified.".format(
        len(FIXTURES) - bad, len(FIXTURES)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="Gate 26 - versioning refs")
    ap.add_argument("--self-test", action="store_true",
                    help="run the fixtures instead of reading a remote")
    ap.add_argument("--refs-file",
                    help="read `git ls-remote --tags` output from this file "
                         "instead of invoking git")
    ap.add_argument("--remote", default="origin",
                    help="remote to list tags from (default: origin)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.refs_file:
        with open(args.refs_file, encoding="utf-8") as fh:
            text = fh.read()
    else:
        try:
            text = subprocess.run(
                ["git", "ls-remote", "--tags", args.remote],
                check=True, capture_output=True, text=True,
                timeout=60).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError) as exc:
            # Fail closed. An unreadable listing has the same shape as "no
            # tags", and check 3 already refuses to read that as a pass.
            print("::error::Gate 26: could not list tags from {0!r}: "
                  "{1}".format(args.remote, exc))
            return 1

    direct, peeled = parse_ls_remote(text)
    failures = check_refs(text)
    for failure in failures:
        print("::error::Gate 26: {0}".format(failure))
    print("Gate 26: checked {0} tag ref(s) against the versioning contract; "
          "{1} failure(s).".format(len(set(direct) | set(peeled)),
                                   len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
