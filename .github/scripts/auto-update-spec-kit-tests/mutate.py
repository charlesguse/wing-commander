"""Replace one exact literal occurrence of OLD with NEW inside an extracted
step file, or fail loudly if OLD is no longer present.

Backs run_step_mutated() in lib.sh (T033) — the auto-update-spec-kit-tests
harness's answer to Gate 9/19's MUTATIONS section: re-run a suite's
multi-page scenarios against the pre-fix shape of the step and assert they
then fail, so the suite is proven able to fail rather than merely happening
to pass. OLD/NEW arrive as files, not argv strings, because the literal
shell text being swapped is full of quotes and brackets that argv/shell
quoting would otherwise mangle.

Usage: mutate.py <step-file> <old-file> <new-file> <out-file>
Exit 1 (no output written) if <old-file>'s content is not found verbatim in
<step-file> — the caller must treat this as "the mutation no longer
applies," not as "the step is fixed."
"""
import sys


def main():
    if len(sys.argv) != 5:
        sys.stderr.write("usage: mutate.py <step-file> <old-file> <new-file> <out-file>\n")
        return 2
    step_path, old_path, new_path, out_path = sys.argv[1:5]
    with open(step_path, encoding="utf-8") as fh:
        content = fh.read()
    with open(old_path, encoding="utf-8") as fh:
        old = fh.read()
    with open(new_path, encoding="utf-8") as fh:
        new = fh.read()
    if old not in content:
        sys.stderr.write(f"mutate.py: old text not found verbatim in {step_path}\n")
        return 1
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content.replace(old, new, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
