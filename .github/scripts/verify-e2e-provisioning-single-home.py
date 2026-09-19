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

Self-test (--self-test): copies the real tree, then (a) passes it clean,
(b) pastes a second copy of the element list into a workflow and expects a
failure naming that line, (c) removes
auto-update-spec-kit-scratch-preflight.yml's call to
provision-e2e-target.sh and expects a failure.

Usage: python3 .github/scripts/verify-e2e-provisioning-single-home.py [--self-test]
"""
import glob
import io
import os
import re
import shutil
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
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::verify-e2e-provisioning-single-home self-test: {p}")
    if problems:
        return 1
    print("verify-e2e-provisioning-single-home self-test: clean tree passes; a pasted copy of the "
          "element list and a dropped call to provision-e2e-target.sh each fail.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::verify-e2e-provisioning-single-home: {f}")
    print(f"verify-e2e-provisioning-single-home: the onboarding-element list has one home "
          f"({CHECKS}/{PROFILES}); {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
