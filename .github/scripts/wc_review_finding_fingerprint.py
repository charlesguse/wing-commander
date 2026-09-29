#!/usr/bin/env python3
"""The one home of this repository's review-finding fingerprint formula
(specs/062-lifecycle-review-gate T028).

board-loop.yml's out-of-scope filing step computed this inline
(`hashlib.sha256("{issue}|{norm(title)}|{norm(file_path)}")`) before this
extraction; lifecycle-review-gate.yml's `disposition` job (US2) is this
module's second caller, and CLAUDE.md's "Shared logic has exactly one
home" rule is why the formula moved here instead of being pasted a second
time. This is NOT spec 076's (unplanned) verbatim-anchor fingerprint
scheme -- that spec is still `stage: spec` with no `plan.md` as of this
writing; this module is the repository's actual, currently-duplicable
idiom, extracted verbatim.
"""
import hashlib
import re


def norm(value):
    """Lowercase, collapse runs of non-word characters to a single space,
    and trim -- the exact normalisation board-loop.yml's inline formula
    already applied to a finding's title and file path before hashing."""
    return " ".join(re.sub(r"[\W_]+", " ", str(value).lower()).split())


def fingerprint(issue_number, title, file_path):
    """The stable dedup key for one review finding, scoped to the issue it
    was found against: sha256("<issue>|<norm(title)>|<norm(file_path)>")."""
    return hashlib.sha256("{0}|{1}|{2}".format(
        issue_number, norm(title), norm(file_path)
    ).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("usage: wc_review_finding_fingerprint.py <issue> <title> <file_path>",
              file=sys.stderr)
        sys.exit(2)
    print(fingerprint(sys.argv[1], sys.argv[2], sys.argv[3]))
