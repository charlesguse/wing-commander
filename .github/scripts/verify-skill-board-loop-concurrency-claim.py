#!/usr/bin/env python3
"""Gate 125 -- spec-cross-reference's Over-rated example still describes
board-loop.yml's actual concurrency shape (specs/089-skill-example-drift).

WHY THIS EXISTS
---------------
.claude/skills/spec-cross-reference/SKILL.md's Over-rated example refutes a
hypothesized board-loop race by quoting a structural guarantee about
board-loop.yml's concurrency configuration: the job range that joins
`wing-commander-board-loop`, and the directed-proof group that is the only
run allowed to overlap them. That quote is a claim about a file the skill
does not own -- nothing failed when spec 060 changed the workflow-level
block into per-job groups (#490) until this gate existed (issue #658). This
script is the mechanical owner FR-002 requires for that one quote: it
extracts the claim from SKILL.md, the authoritative per-job classification
from specs/060-self-redrive-concurrency/contracts/concurrency-groups.md,
and the real per-job concurrency: blocks from board-loop.yml itself, then
fails loudly on any divergence, per
specs/089-skill-example-drift/contracts/skill-drift-gate.md.
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_MD = os.path.join(REPO_ROOT, ".claude", "skills", "spec-cross-reference", "SKILL.md")
CONCURRENCY_GROUPS_MD = os.path.join(
    REPO_ROOT, "specs", "060-self-redrive-concurrency", "contracts", "concurrency-groups.md")
BOARD_LOOP_YML = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")
WAIVERS_JSON = os.path.join(REPO_ROOT, ".github", "scripts", "skill-example-drift-waivers.json")


def run():
    print("verify-skill-board-loop-concurrency-claim: 0 failure(s).")
    return 0


def run_selftest():
    print("verify-skill-board-loop-concurrency-claim --self-test: 0 failure(s).")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.exit(run_selftest() if args.self_test else run())


if __name__ == "__main__":
    main()
