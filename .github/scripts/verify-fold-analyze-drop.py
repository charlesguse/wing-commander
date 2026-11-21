#!/usr/bin/env python3
"""Gate: the fold-time analyze and drop scripts keep their branch behaviour
(specs/119-lifecycle-hold-label, FR-011..FR-016, FR-023).

Runs one in-line case per failure branch against wc_fold_analyze.py and
wc_fold_drop.py, so a regression in either fails here rather than in a
fold run that only exists in Actions.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_fold_analyze as fa  # noqa: E402
import wc_fold_drop as fd  # noqa: E402

CONSTITUTION = "### I. Test First\n### II. Single Home\nprose\n"
DIFF = (
    "+++ b/specs/x/tasks.md\n"
    "+- [ ] Review finding: Lock the file\n"
    "+- [ ] Recurring review finding: Fix the typo\n"
)
FOLD = fa.build_input("a", "b", DIFF, "spec", CONSTITUTION)


def verdict(**kw):
    obj = {"task": "Review finding: Lock the file",
           "constitution_conflict": True, "principle": "I. Test First",
           "reasoning": "r"}
    obj.update(kw)
    return {"objections": [obj]}


def analyze_cases():
    errs = []

    def expect(name, got, want):
        if got != want:
            errs.append(f"analyze {name}: got {got!r}, want {want!r}")

    expect("principles", FOLD["principles"], ["I. Test First", "II. Single Home"])
    expect("added", [t["id"] for t in FOLD["added_tasks"]],
           ["Review finding: Lock the file", "Recurring review finding: Fix the typo"])
    expect("hold", fa.decide(FOLD, verdict())["hold"], True)
    r = fa.decide(FOLD, verdict(constitution_conflict=False, principle=None))
    expect("record-only", (r["hold"], len(r["recorded_items"])), (False, 1))
    expect("malformed", fa.decide(FOLD, {"objections": "x"})["status"], "malformed")
    expect("malformed-item", fa.decide(FOLD, {"objections": [{"task": 1}]})["status"],
           "malformed")
    expect("unknown-principle", fa.decide(FOLD, verdict(principle="IX. Nope"))["hold"],
           False)
    expect("task-not-in-fold", fa.decide(FOLD, verdict(task="Other"))["hold"], False)
    expect("agent-failed", fa.decide(FOLD, None)["status"], "agent-failed")
    expect("no-diff", fa.build_input("a", "b", "", "s", CONSTITUTION)["added_tasks"], [])
    expect("first-attempt", (fa.is_first_attempt("1"), fa.is_first_attempt("2"),
                             fa.is_first_attempt("x")), (True, False, False))
    return errs


TASKS = (
    "- [ ] T1 plain\n"
    "- [ ] Review finding: A\n"
    "- [x] Review finding: Done\n"
    "- [ ] Review finding: Twin\n"
    "- [ ] Review finding: Twin\n"
)


def drop_cases():
    errs = []

    def expect(name, got, want):
        if got != want:
            errs.append(f"drop {name}: got {got!r}, want {want!r}")

    expect("parse", fd.parse("drop:\n- Review finding: A\n"), {"titles": ["Review finding: A"]})
    expect("parse-quoted", fd.parse("> drop\ndrop\n- [ ] Recurring review finding: B"),
           {"titles": ["Recurring review finding: B"]})
    expect("parse-stop", fd.parse("stop"), None)
    expect("parse-prose", fd.parse("please drop it"), None)

    def run(titles, assoc="MEMBER"):
        return fd.apply(TASKS, titles, assoc, "42")

    new, out, msg, _ = run(["Review finding: A"])
    expect("removed", out, {"Review finding: A": "removed"})
    expect("removed-text", "Review finding: A" in new, False)
    expect("trailer", "Wing-Commander-Drop: 42" in msg, True)
    expect("unknown", run(["Review finding: Z"])[1], {"Review finding: Z": "unknown"})
    expect("not-fold", run(["T1 plain"])[1], {"T1 plain": "not-fold-task"})
    expect("checked", run(["Review finding: Done"])[1],
           {"Review finding: Done": "already-checked"})
    new, out, msg, _ = run(["Review finding: A"], "NONE")
    expect("non-maintainer", (out, new, msg), ({"*": "non-maintainer"}, TASKS, ""))
    new, _, _, _ = run(["Review finding: Twin"])
    expect("same-titled", "Twin" in new, False)
    return errs


def main(argv):
    errs = analyze_cases() + drop_cases()
    for e in errs:
        print(f"FAIL: {e}")
    if errs:
        return 1
    print("fold analyze/drop branches: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
