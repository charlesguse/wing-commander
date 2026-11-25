"""Surface-independent renderer for the board loop's explanatory messages
(spec 130, contracts/message-parts.md): the first comment, the PR-body
summary and the review comment.

Every part of a set is always rendered, filled or as gap text, so a
reader never has to guess what is missing. Agent-written and backlog
text goes through `fenced_section` (#580); labels and gap text are
fixed and sit outside the fence.

CLI: python3 -I wc_message_parts.py render-explanation|render-review|summary
         --in FILE --id ID
Exit 0 with the body on stdout; exit 2 on refusal.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board_spec_request_body import fenced_section, utf16_len  # noqa: E402

TOTAL_BUDGET = 57000
LEAD_PART_BUDGET = 1500
DETAILS_SLACK = 600

EXPLANATION_PARTS = (
    ("line", "The line"),
    ("code", "The code"),
    ("issue", "The issue"),
    ("why_it_matters", "Why it matters"),
    ("options", "Options"),
    ("what_this_pr_does", "What this PR does"),
)
REVIEW_PARTS = (
    ("asked", "Asked"),
    ("checked", "Checked"),
    ("decided", "Decided"),
    ("not_decided", "Not decided"),
    ("open", "Open"),
)

IDENTIFIER_RE = re.compile(r"^(bl-[0-9a-f]{4,64}|#[0-9]{1,9})$")
CLOSING_RE = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[\s:]*"
    r"(?:[\w.-]+/[\w.-]+)?(?:#\d+|https?://\S+/(?:issues|pull)/\d+)",
    re.IGNORECASE)


class Refusal(Exception):
    """The input cannot be rendered safely; the CLI exits 2."""


def _label(part_set, part):
    return dict(part_set)[part]


def gap_text(part, kind):
    """Fixed text for a part with nothing to show. `kind` is one of
    missing, empty, invalid, follow, incomplete."""
    label = None
    for part_set in (EXPLANATION_PARTS, REVIEW_PARTS):
        if part in dict(part_set):
            label = dict(part_set)[part]
            break
    label = label or part
    if kind == "follow":
        return "{0}: options follow in a later comment.".format(label)
    reasons = {
        "missing": "the author did not provide it",
        "empty": "the author left it empty",
        "invalid": "the value was not text",
        "incomplete": "the review did not complete",
    }
    return "{0}: not provided -- {1}.".format(
        label, reasons.get(kind, reasons["missing"]))


def normalize_part(raw):
    """(state, text, kind) for one raw input value. state is filled,
    follow or gap; kind says why a gap is a gap."""
    if raw is None:
        return "gap", "", "missing"
    if isinstance(raw, dict):
        if raw.get("state") == "follow":
            return "follow", "", "follow"
        return normalize_part(raw.get("text")) if "text" in raw else (
            "gap", "", "missing")
    if not isinstance(raw, str):
        return "gap", "", "invalid"
    if not raw.strip():
        return "gap", "", "empty"
    return "filled", raw.strip(), ""


def _check_identifier(identifier):
    if not isinstance(identifier, str) or not IDENTIFIER_RE.match(identifier):
        raise Refusal("identifier must be bl-<hex> or #N")


def _assemble(title, part_set, parts, extra_overflow=None):
    """Lead (labelled parts, each one screen-bounded) then <details>
    overflow, the whole under TOTAL_BUDGET UTF-16 units."""
    if not isinstance(parts, dict):
        parts = {}
    lead = [title, ""]
    overflow = []
    for part, label in part_set:
        state, text, kind = normalize_part(parts.get(part))
        if state == "filled":
            lead.append(fenced_section("**{0}**".format(label), text,
                                       LEAD_PART_BUDGET))
            if utf16_len(text) > LEAD_PART_BUDGET:
                overflow.append((label, text))
        else:
            lead.append("**{0}**\n\n_{1}_".format(label, gap_text(part, kind)))
        lead.append("")
    lead_text = "\n".join(lead)
    if extra_overflow:
        overflow.extend(extra_overflow)
    if not overflow:
        return _cap(lead_text)
    remaining = TOTAL_BUDGET - utf16_len(lead_text) - DETAILS_SLACK
    remaining -= 200 * len(overflow)
    if remaining <= 0:
        return _cap(lead_text)
    each = remaining // len(overflow)
    blocks = ["<details><summary>Full text of long parts</summary>", ""]
    for label, text in overflow:
        blocks.append(fenced_section("**{0}** (full)".format(label), text,
                                     each))
        blocks.append("")
    blocks.append("</details>")
    return _cap(lead_text + "\n" + "\n".join(blocks))


def _cap(body):
    if utf16_len(body) <= TOTAL_BUDGET:
        return body
    cut = body.encode("utf-16-le")[: (TOTAL_BUDGET - 100) * 2]
    return cut.decode("utf-16-le", errors="ignore") + "\n\n(truncated)"


def render_explanation(parts, identifier):
    _check_identifier(identifier)
    return _assemble(
        "Board loop: what `{0}` is and what this PR does.".format(identifier),
        EXPLANATION_PARTS, parts)


def render_review(parts, identifier, findings):
    _check_identifier(identifier)
    parts = dict(parts) if isinstance(parts, dict) else {}
    items = []
    for finding in findings or []:
        if isinstance(finding, str):
            items.append(finding)
        elif isinstance(finding, dict):
            items.append(json.dumps(finding, sort_keys=True))
    if items:
        listed = "\n".join("- " + item for item in items)
        existing = parts.get("open")
        if isinstance(existing, str) and existing.strip():
            listed = existing.strip() + "\n" + listed
        parts["open"] = listed
    return _assemble(
        "Board loop review of `{0}` against its stated question.".format(
            identifier), REVIEW_PARTS, parts)


def render_incomplete_review(identifier):
    _check_identifier(identifier)
    parts = {p: {"state": "gap", "text": ""} for p, _ in REVIEW_PARTS}
    lines = ["Board loop review of `{0}`: review did not complete.".format(
        identifier), ""]
    for part, label in REVIEW_PARTS:
        lines.append("**{0}**\n\n_{1}_\n".format(
            label, gap_text(part, "incomplete")))
    del parts
    return "\n".join(lines)


def render_summary(issue, pr, identifier, first_comment=""):
    _check_identifier(identifier)
    for text in (issue, pr):
        match = CLOSING_RE.search(text if isinstance(text, str) else "")
        if match:
            raise Refusal("closing keyword in summary: {0!r}".format(
                match.group(1)))
    issue_state, issue_text, issue_kind = normalize_part(issue)
    pr_state, pr_text, pr_kind = normalize_part(pr)
    out = []
    for key, label, state, text, kind in (
            ("issue", "The issue", issue_state, issue_text, issue_kind),
            ("what_this_pr_does", "What this PR does", pr_state, pr_text,
             pr_kind)):
        if state == "filled":
            out.append(fenced_section("**{0}**".format(label), text, 3000))
        else:
            out.append("**{0}**\n\n_{1}_".format(label, gap_text(key, kind)))
        out.append("")
    pointer = "The full explanation is in the first comment on this PR"
    if isinstance(first_comment, str) and re.match(r"^https://\S+$",
                                                   first_comment):
        pointer += ": " + first_comment
    out.append(pointer + ".")
    return _cap("\n".join(out))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("render-explanation", "render-review", "summary",
                         "render-incomplete"))
    parser.add_argument("--in", dest="infile", default="")
    parser.add_argument("--id", dest="identifier", required=True)
    args = parser.parse_args(argv)
    data = {}
    if args.infile:
        try:
            with open(args.infile, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        if args.mode == "render-explanation":
            body = render_explanation(data.get("parts", data), args.identifier)
        elif args.mode == "render-review":
            body = render_review(data.get("parts", {}), args.identifier,
                                 data.get("findings", []))
        elif args.mode == "render-incomplete":
            body = render_incomplete_review(args.identifier)
        else:
            body = render_summary(data.get("issue"), data.get("pr"),
                                  args.identifier,
                                  data.get("first_comment", ""))
    except Refusal as exc:
        print("refused: {0}".format(exc), file=sys.stderr)
        return 2
    sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
