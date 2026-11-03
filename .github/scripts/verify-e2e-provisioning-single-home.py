#!/usr/bin/env python3
"""SC-007 (Constitution VIII) -- the E2E onboarding-element list, and the
TargetProfile mapping built from it, live in exactly one place:
`.github/scripts/e2e-provisioning/checks.sh` (the element list) and
`.github/scripts/e2e-provisioning/profiles.sh` (the TargetProfile mapping).

This feature's whole design point (FR-008/FR-010, research.md D2) is that
`provision-e2e-target.sh` and the generalized
`auto-update-spec-kit-scratch-preflight.yml` compute readiness through the
SAME functions rather than each re-deriving the answer -- the repository
already had three independent, slightly-different copies of "split
owner/name, mint a scoped token, check reachability" before this feature,
and it must not add a fourth for the onboarding-element list specifically.

This gate fails when:

  * a workflow or script outside checks.sh/profiles.sh defines its own copy
    of the onboarding-element key list (the seven element keys, as a
    literal array/list) or its own second `TargetProfile`-shaped mapping
    (a "profile name -> element list" table);
  * checks.sh no longer contains the element list, or profiles.sh no
    longer contains the TargetProfile mapping (the gate would then be
    protecting nothing -- update both together);
  * the generalized readiness-check workflow stops calling
    provision-e2e-target.sh (and, through it, checks.sh) -- "a gate that
    cannot fail proves nothing" only holds if the one real call site stays
    wired.

It also guards the wrapper pin (#1083): the rewrite that turns this
repository's own wrapper workflows into ones a test repository can run
lives only in `.github/actions/_shared/pin-e2e-wrapper.sh`. This gate
fails when:

  * auto-release.yml or provision-e2e-target.sh stops calling it, or any
    workflow or script outside it carries its own `uses: ./.github/
    workflows/` rewrite;
  * running the real script over every wrapper auto-release.yml's scaffold
    step copies leaves a local stage call, or leaves the wrapper passing
    `github.sha` as `pipeline-ref` -- in a test repository that is the
    test repository's commit, the pipeline repository can't fetch it, and
    every implement job failed its pipeline checkout with "not our ref";
  * a wrapper that passes a `pipeline-ref` comes out passing anything but
    the pipeline commit it was pinned to.

Self-test (--self-test): copies the real tree, then (a) passes it clean,
(b) pastes a second copy of the element list into a workflow and expects a
failure naming that line, (c) removes
auto-update-spec-kit-scratch-preflight.yml's call to
provision-e2e-target.sh and expects a failure, (d) drops the
pin script's pipeline-ref rewrite and expects the implement wrapper to
fail, and (e) puts auto-release.yml's old inline sed back and expects a
failure naming it, and (f) pastes an unescaped inline sed into
provision-e2e-target.sh and expects a failure naming it, (g) adds a prose
comment naming a wrapper's `uses: ./.github/workflows/` call and expects
no inline-rewrite failure, (h) pastes an inline sed into a script under
.github/scripts/e2e-provisioning/ and expects a failure naming it, (i)
swaps provision-e2e-target.sh's pin-script call for a plain read while its
pointer comment stays and expects a "does not call" failure, (j) renames
auto-release.yml's stage map away and expects a failure, and (k) runs the
pin script on a 2 MB file that still calls a stage by local path and
expects the refusal (a `printf | grep -q` pipe under pipefail lost it to
SIGPIPE).

Usage: python3 .github/scripts/verify-e2e-provisioning-single-home.py [--self-test]
"""
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHECKS = ".github/scripts/e2e-provisioning/checks.sh"
PROFILES = ".github/scripts/e2e-provisioning/profiles.sh"
READINESS_WORKFLOW = ".github/workflows/auto-update-spec-kit-scratch-preflight.yml"
PROVISION_SCRIPT = "provision-e2e-target.sh"
# This gate's own path -- it necessarily holds a reference copy of the
# canonical key list (and, in --self-test, a fixture pasting one) to know
# what to look for; that is not a second, independent definition and must
# not flag itself.
SELF_PATH = ".github/scripts/verify-e2e-provisioning-single-home.py"

# The wrapper pin's one home and the two places that must call it (#1083).
PIN_SCRIPT = ".github/actions/_shared/pin-e2e-wrapper.sh"
PIN_CALLERS = (".github/workflows/auto-release.yml", ".github/scripts/provision-e2e-target.sh")
AUTO_RELEASE = ".github/workflows/auto-release.yml"
# An inline copy of the stage-call rewrite: a sed substitution whose
# pattern is the local `uses: ./.github/workflows/` call, with the dots
# escaped or not. The `s` must start a word and its delimiter must be
# punctuation that closes the pattern later on the line, so prose such as
# "the wrapper's uses: ./.github/workflows/x.yml call" is not a sed.
INLINE_PIN_RE = re.compile(r"(?<!\w)s([^\w\s])uses: \\?\./\\?\.github/workflows/[^\n]*?\1")
# A real call of the pin script: `bash "<root>/.github/actions/_shared/
# pin-e2e-wrapper.sh"` on a line that is not a comment -- the pointer
# comment at each call site names the script too, and must not count.
PIN_CALL_RE = re.compile(r'^(?![ \t]*#)[^\n]*\bbash[ \t]+"[^"\n]*/\.github/actions/_shared/pin-e2e-wrapper\.sh"', re.M)
# The scaffold step's wrapper -> stage map: `[wing-commander-5-implement.yml]=implement.yml`.
STAGE_MAP_RE = re.compile(r"^\s*\[(wing-commander-[\w.-]+\.yml)\]=([\w.-]+\.yml)\s*$", re.M)
FAKE_COMMIT = "0123456789abcdef0123456789abcdef01234567"

# The seven OnboardingElement keys (data-model.md), in the exact order
# data-model.md and profiles.sh's spec-kit-scratch/auto-release lists carry
# them. profiles.sh deliberately never spells all seven as adjacent
# literals -- auto-release's list is spec-kit-scratch's three PLUS four
# more, built by array expansion (`"${SPEC_KIT_SCRATCH_ELEMENTS[@]}"`),
# precisely so the superset relationship holds by construction. A second,
# independent definition would restate them as a literal list in this same
# conventional order with nothing but punctuation/whitespace between each
# pair -- the shape a copy-paste produces, and NOT the shape ordinary prose,
# test assertions, or code that merely mentions these identifiers produces.
ELEMENT_KEYS = [
    "repository", "app_installation", "scratch_marker",
    "claude_credential", "spec_request_label", "wrapper_set", "container_image_pin",
]
KEY_WORD_RES = [re.compile(r"\b" + re.escape(k) + r"\b") for k in ELEMENT_KEYS]
_SEP = r'[\s,"\'\[\]\(\)\{\}]{0,20}'
CANONICAL_LIST_RE = re.compile(
    _SEP.join(r"\b" + re.escape(k) + r"\b" for k in ELEMENT_KEYS))


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def has_every_key(text):
    return all(r.search(text) for r in KEY_WORD_RES)


def clustered_copy_lines(text):
    """-> [(line number, matched text)] for every literal restatement of the
    seven element keys, in canonical order, separated by nothing but
    punctuation/whitespace -- a second, independent copy of the element
    list, as opposed to prose, a test assertion, or code that merely
    mentions these identifiers with real tokens in between."""
    out = []
    for m in CANONICAL_LIST_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append((line, " ".join(m.group(0).split())[:120]))
    return out


def scan(root="."):
    failures = []
    checks_path = os.path.join(root, CHECKS)
    profiles_path = os.path.join(root, PROFILES)
    if not os.path.isfile(checks_path):
        failures.append(f"{CHECKS} is missing -- it is the one home of the onboarding-element checks.")
    elif not has_every_key(_read(checks_path)):
        failures.append(f"{CHECKS} no longer defines (or references) every onboarding-element "
                         f"key this gate protects; if the list moved, move this gate's CHECKS with it.")
    if not os.path.isfile(profiles_path):
        failures.append(f"{PROFILES} is missing -- it is the one home of the TargetProfile mapping.")
    elif not has_every_key(_read(profiles_path)):
        failures.append(f"{PROFILES} no longer contains the onboarding-element list this gate "
                         f"protects; if it moved, move this gate's PROFILES with it.")

    files = (glob.glob(os.path.join(root, ".github/workflows/*.yml"))
             + glob.glob(os.path.join(root, ".github/workflows/*.yaml"))
             + glob.glob(os.path.join(root, ".github/scripts/*.py"))
             + glob.glob(os.path.join(root, ".github/scripts/*.sh"))
             + glob.glob(os.path.join(root, ".github/scripts/e2e-provisioning-tests/*.sh"))
             + glob.glob(os.path.join(root, ".github/actions/**/action.yml"), recursive=True)
             + glob.glob(os.path.join(root, ".github/actions/**/action.yaml"), recursive=True))
    for f in sorted(files):
        rel = os.path.relpath(f, root).replace("\\", "/")
        if rel in (CHECKS, PROFILES, SELF_PATH):
            continue
        for n, first_line in clustered_copy_lines(_read(f)):
            failures.append(
                f"{rel}:{n}: all seven onboarding-element keys appear clustered here -- a second, "
                f"independent copy of the element list. The one home is {PROFILES} (the "
                f"TargetProfile mapping) or {CHECKS} (the checks themselves): {first_line}")

    workflow_path = os.path.join(root, READINESS_WORKFLOW)
    if not os.path.isfile(workflow_path):
        failures.append(f"{READINESS_WORKFLOW} is missing.")
    elif PROVISION_SCRIPT not in _read(workflow_path):
        failures.append(f"{READINESS_WORKFLOW} does not call {PROVISION_SCRIPT} -- it must compute "
                         f"readiness through the shared checks.sh/profiles.sh library (via that "
                         f"script), not a re-derived check of its own.")
    return failures + scan_wrapper_pin(root)


def scan_wrapper_pin(root="."):
    """The wrapper pin's one home, and what it produces on the real wrappers (#1083)."""
    failures = []
    pin = os.path.join(root, PIN_SCRIPT)
    if not os.path.isfile(pin):
        return [f"{PIN_SCRIPT} is missing -- it is the one home of the e2e wrapper pin."]
    for caller in PIN_CALLERS:
        path = os.path.join(root, caller)
        if not os.path.isfile(path):
            failures.append(f"{caller} is missing.")
        elif not PIN_CALL_RE.search(_read(path)):
            failures.append(f"{caller} does not call {PIN_SCRIPT} -- the e2e wrapper pin must go "
                            f"through it, not a rewrite of its own.")
    files = set()
    for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml",
                    ".github/scripts/**/*.sh", ".github/scripts/**/*.py",
                    ".github/actions/**/*.sh", ".github/actions/**/action.yml",
                    ".github/actions/**/action.yaml"):
        files.update(glob.glob(os.path.join(root, pattern), recursive=True))
    for f in sorted(files):
        rel = os.path.relpath(f, root).replace("\\", "/")
        if rel in (PIN_SCRIPT, SELF_PATH):
            continue
        text = _read(f)
        for m in INLINE_PIN_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            failures.append(f"{rel}:{line}: an inline rewrite of a wrapper's local stage call -- "
                            f"the one home is {PIN_SCRIPT}, which also pins pipeline-ref.")

    ar = os.path.join(root, AUTO_RELEASE)
    pairs = STAGE_MAP_RE.findall(_read(ar)) if os.path.isfile(ar) else []
    if not pairs:
        failures.append(f"{AUTO_RELEASE}: could not find the scaffold step's wrapper -> stage map "
                        f"([wing-commander-N-x.yml]=x.yml); if it moved, move this gate with it.")
    for wrapper, stage in pairs:
        src = os.path.join(root, ".github/workflows", wrapper)
        if not os.path.isfile(src):
            failures.append(f"{AUTO_RELEASE} copies {wrapper}, which does not exist.")
            continue
        r = subprocess.run(["bash", pin, src, stage, "example/pipeline", "e2e-verify-tag", FAKE_COMMIT],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"{PIN_SCRIPT} refused {wrapper}: {r.stderr.strip()[:300]}")
            continue
        out = r.stdout
        if re.search(r"uses: \./\.github/workflows/", out):
            failures.append(f"{wrapper}: still calls its stage by local path after pinning.")
        if f"uses: example/pipeline/.github/workflows/{stage}@e2e-verify-tag" not in out:
            failures.append(f"{wrapper}: pinning did not produce a call to {stage} at the pin tag.")
        for ref in re.findall(r"^\s*pipeline-ref:\s*(.*?)\s*$", out, re.M):
            if ref != FAKE_COMMIT:
                failures.append(f"{wrapper}: pinned wrapper passes pipeline-ref {ref!r}, not the "
                                f"pipeline commit it was pinned to -- in a test repository the "
                                f"pipeline checkout would fail (#1083).")
    return failures


def _copy_tree(dst):
    for rel in (".github/workflows", ".github/actions", ".github/scripts"):
        shutil.copytree(rel, os.path.join(dst, rel))


def self_test():
    problems = []
    root = tempfile.mkdtemp(prefix="verify_e2e_provisioning_home_")
    try:
        clean = os.path.join(root, "clean")
        _copy_tree(clean)
        got = scan(clean)
        if got:
            problems.append("clean copy of the real tree FAILED: " + "; ".join(got))

        pasted = os.path.join(root, "pasted")
        _copy_tree(pasted)
        target = os.path.join(pasted, ".github/workflows/plan.yml")
        with io.open(target, "a", encoding="utf-8") as fh:
            fh.write(
                "\n# pasted-copy fixture\n"
                "      - name: Fixture step\n"
                "        run: |\n"
                "          ELEMENTS=(repository app_installation scratch_marker claude_credential "
                "spec_request_label wrapper_set container_image_pin)\n")
        got = scan(pasted)
        if not any("workflows/plan.yml" in g and "independent copy" in g for g in got):
            problems.append(f"a pasted copy of the element list in plan.yml was NOT detected; got: {got}")

        dropped = os.path.join(root, "dropped")
        _copy_tree(dropped)
        wf = os.path.join(dropped, READINESS_WORKFLOW)
        text = _read(wf).replace(PROVISION_SCRIPT, "some-other-script.sh")
        with io.open(wf, "w", encoding="utf-8") as fh:
            fh.write(text)
        got = scan(dropped)
        if not any(READINESS_WORKFLOW in g and "does not call" in g for g in got):
            problems.append(f"the readiness workflow dropping its call to {PROVISION_SCRIPT} was NOT "
                             f"detected; got: {got}")

        unpinned = os.path.join(root, "unpinned")
        _copy_tree(unpinned)
        pin = os.path.join(unpinned, PIN_SCRIPT)
        text = _read(pin)
        # Drop the rewrite and disarm the refusal, so what's left is the
        # old, uses:-only pin: the scan's own check must still catch it.
        mutated = "".join(l for l in text.splitlines(True) if '-e "s#pipeline-ref' not in l)
        mutated = mutated.replace("'pipeline-ref:.*github\\.sha'", "'^never-matches$'")
        if mutated.count("\n") == text.count("\n") or "never-matches" not in mutated:
            problems.append(f"fixture: could not find the pipeline-ref rewrite and refusal in {PIN_SCRIPT}")
        with io.open(pin, "w", encoding="utf-8") as fh:
            fh.write(mutated)
        got = scan(unpinned)
        if not any("wing-commander-5-implement.yml" in g and "pipeline-ref" in g for g in got):
            problems.append(f"a pin that leaves the implement wrapper passing github.sha as "
                            f"pipeline-ref was NOT detected; got: {got}")

        inline = os.path.join(root, "inline")
        _copy_tree(inline)
        ar = os.path.join(inline, AUTO_RELEASE)
        with io.open(ar, "a", encoding="utf-8") as fh:
            fh.write('\n# inline-pin fixture\n# sed -i "s#uses: \\./\\.github/workflows/${stage}#uses: x@y#" f\n')
        got = scan(inline)
        if not any(AUTO_RELEASE in g and "inline rewrite" in g for g in got):
            problems.append(f"an inline sed pin pasted back into {AUTO_RELEASE} was NOT detected; got: {got}")

        unescaped = os.path.join(root, "unescaped")
        _copy_tree(unescaped)
        prov = os.path.join(unescaped, ".github/scripts", PROVISION_SCRIPT)
        with io.open(prov, "a", encoding="utf-8") as fh:
            fh.write('\n# unescaped-pin fixture\n# sed "s|uses: ./.github/workflows/${stage}|uses: x@y|" f\n')
        got = scan(unescaped)
        if not any(PROVISION_SCRIPT in g and "inline rewrite" in g for g in got):
            problems.append(f"an inline sed pin with unescaped dots pasted into {PROVISION_SCRIPT} was "
                            f"NOT detected; got: {got}")

        prose = os.path.join(root, "prose")
        _copy_tree(prose)
        with io.open(os.path.join(prose, AUTO_RELEASE), "a", encoding="utf-8") as fh:
            fh.write("\n# prose fixture: the implement wrapper's uses: ./.github/workflows/implement.yml "
                     "call, and it calls uses: ./.github/workflows/plan.yml too\n")
        got = scan(prose)
        if any("inline rewrite" in g for g in got):
            problems.append(f"a prose comment naming a wrapper's local stage call was flagged as an "
                            f"inline sed pin; got: {got}")

        nested = os.path.join(root, "nested")
        _copy_tree(nested)
        with io.open(os.path.join(nested, CHECKS), "a", encoding="utf-8") as fh:
            fh.write('\n# nested-pin fixture\n# sed "s#uses: \\./\\.github/workflows/${stage}#uses: x@y#" f\n')
        got = scan(nested)
        if not any(CHECKS in g and "inline rewrite" in g for g in got):
            problems.append(f"an inline sed pin pasted into {CHECKS} was NOT detected; got: {got}")

        uncalled = os.path.join(root, "uncalled")
        _copy_tree(uncalled)
        prov = os.path.join(uncalled, ".github/scripts", PROVISION_SCRIPT)
        text = _read(prov)
        call = 'bash "$REPO_ROOT/.github/actions/_shared/pin-e2e-wrapper.sh"'
        if text.count(call) != 1:
            problems.append(f"fixture: could not find {PROVISION_SCRIPT}'s pin-script call")
        with io.open(prov, "w", encoding="utf-8") as fh:
            fh.write(text.replace(call, "cat"))
        got = scan(uncalled)
        if not any(PROVISION_SCRIPT in g and "does not call" in g for g in got):
            problems.append(f"{PROVISION_SCRIPT} dropping its pin-script call (pointer comment kept) "
                            f"was NOT detected; got: {got}")

        nomap = os.path.join(root, "nomap")
        _copy_tree(nomap)
        ar = os.path.join(nomap, AUTO_RELEASE)
        text = _read(ar)
        with io.open(ar, "w", encoding="utf-8") as fh:
            fh.write(text.replace("[wing-commander-", "[wc-"))
        got = scan(nomap)
        if not any("wrapper -> stage map" in g for g in got):
            problems.append(f"{AUTO_RELEASE} losing its wrapper -> stage map was NOT detected; got: {got}")

        big = os.path.join(root, "big.yml")
        with io.open(big, "w", encoding="utf-8") as fh:
            # The pin rewrites every local stage call, so the unpinnable line
            # is a pipeline-ref the rewrite's pattern doesn't match.
            fh.write("    pipeline-ref: ${{ format('{0}', github.sha) }}\n" + ("# pad " + "x" * 70 + "\n") * 30000)
        r = subprocess.run(["bash", PIN_SCRIPT, big, "nomatch.yml", "o/r", "t", FAKE_COMMIT],
                           capture_output=True, text=True)
        if r.returncode == 0:
            problems.append(f"{PIN_SCRIPT} printed a 2 MB wrapper that still calls a stage by local "
                            f"path instead of refusing it")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::verify-e2e-provisioning-single-home self-test: {p}")
    if problems:
        return 1
    print("verify-e2e-provisioning-single-home self-test: clean tree passes; a pasted copy of the "
          "element list, a dropped call to provision-e2e-target.sh, a pin that leaves pipeline-ref "
          "at github.sha, an inline sed pin (escaped or not, nested or not), a caller that drops its "
          "pin-script call, a missing stage map and a large unpinnable wrapper each fail; prose naming "
          "a local stage call passes.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::verify-e2e-provisioning-single-home: {f}")
    print(f"verify-e2e-provisioning-single-home: the onboarding-element list has one home "
          f"({CHECKS}/{PROFILES}) and the wrapper pin has one home ({PIN_SCRIPT}); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
