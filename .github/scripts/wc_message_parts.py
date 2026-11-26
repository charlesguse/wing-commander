"""Surface-independent renderer for the board loop's explanatory messages
(spec 130, contracts/message-parts.md): the first comment, the PR-body
summary and the review comment.

Every part of a set is always rendered, filled or as gap text, so a
reader never has to guess what is missing. Agent-written and backlog
text goes through `fenced_section` (#580); labels and gap text are
fixed and sit outside the fence.

CLI: python3 -I wc_message_parts.py render-explanation|render-review|summary
         |render-options --in FILE --id ID
     python3 -I wc_message_parts.py extract-explanation --in TRANSCRIPT
Exit 0 with the body on stdout; exit 2 on refusal. extract-explanation
prints the fixer's explanation parts as one line of JSON and always
exits 0 ({} when the transcript carries no usable block).
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
    r"(?:(?:the|this|that|issue|bug|pr|pull request|ticket)\b[\s:]*)*"
    r"(?:[\w.-]+/[\w.-]+)?(?:#\d+|GH-\d+|https?://\S+/(?:issues|pull)/\d+)",
    re.IGNORECASE)


# The fenced block the board loop's fixer ends its final message with
# (board-loop.yml's "Fixer" prompt); the loop supplies `line` itself.
EXPLANATION_TAG = "wing-commander-explanation"
AGENT_EXPLANATION_PARTS = ("code", "issue", "why_it_matters", "options",
                           "what_this_pr_does")
AGENT_PART_CAP = 8000


# First-line markers on the loop's own explaining and options comments, so
# readiness can read back from the PR whether a later options comment is
# owed and whether it was posted (research.md D4; board_readiness.py reads
# them). Fixed text: agent text never starts a comment.
EXPLANATION_MARKER = "<!-- wing-commander-explanation id={0} options={1} -->"
OPTIONS_MARKER = "<!-- wing-commander-options id={0} -->"
EXPLANATION_MARKER_RE = re.compile(
    r"<!-- wing-commander-explanation id=(\S+) options=(follow|given) -->")
OPTIONS_MARKER_RE = re.compile(r"<!-- wing-commander-options id=(\S+) -->")


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


def normalize_part(raw, part="options"):
    """(state, text, kind) for one raw input value. state is filled,
    follow or gap; kind says why a gap is a gap. Only the options part
    can be "follow": on any other part that state is a gap."""
    if raw is None:
        return "gap", "", "missing"
    if isinstance(raw, dict):
        if raw.get("state") == "follow" and part == "options":
            return "follow", "", "follow"
        return normalize_part(raw.get("text"), part) if "text" in raw else (
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
        state, text, kind = normalize_part(parts.get(part), part)
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
    text = cut.decode("utf-16-le", errors="ignore")
    # Close what the cut left open, so the marker is not swallowed by a
    # code fence or a <details> block.
    fence = None
    details = 0
    for line in text.split("\n"):
        stripped = line.lstrip()
        run = len(stripped) - len(stripped.lstrip("`"))
        if run >= 3:
            if fence is None:
                fence = run
            elif run >= fence and not stripped.strip("`"):
                fence = None
        elif fence is None:
            details += stripped.count("<details>") - stripped.count("</details>")
    closing = ""
    if fence is not None:
        closing += "\n" + "`" * fence
    closing += "\n</details>" * max(details, 0)
    return text + closing + "\n\n(truncated)"


def render_explanation(parts, identifier):
    _check_identifier(identifier)
    marker = EXPLANATION_MARKER.format(
        identifier, "follow" if options_follow(parts) else "given")
    return marker + "\n" + _assemble(
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
        listed = "{0} in-scope finding(s) open:\n".format(len(items)) + "\n".join(
            "- " + item for item in items)
        existing = parts.get("open")
        if (isinstance(existing, str) and existing.strip()
                and not re.match(r"\s*(nothing|none|no )", existing, re.I)):
            listed = existing.strip() + "\n" + listed
        parts["open"] = listed
    return _assemble(
        "Board loop review of `{0}` against its stated question.".format(
            identifier), REVIEW_PARTS, parts)


def render_incomplete_review(identifier):
    _check_identifier(identifier)
    lines =["Board loop review of `{0}`: review did not complete.".format(
        identifier), ""]
    for part, label in REVIEW_PARTS:
        lines.append("**{0}**\n\n_{1}_\n".format(
            label, gap_text(part, "incomplete")))
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
    if isinstance(first_comment, str) and re.match(r"^https://\S+$",
                                                   first_comment):
        pointer = "The full explanation is in this comment on the PR: " + first_comment
    else:
        pointer = ("The board loop posts the full explanation as a comment "
                   "on this PR; if the step failed, no such comment exists")
    out.append(pointer + ".")
    return _cap("\n".join(out))


def _capped(value):
    return value[:AGENT_PART_CAP] if isinstance(value, str) else None


def explanation_from_text(text):
    """The fixer's explanation parts from its final message: the last
    ```wing-commander-explanation``` block, kept to the agent's parts
    (never `line`, which the loop quotes verbatim) and to string values
    or an options `{"state": "follow", "text": ...}`. Anything else is
    dropped, so the renderer shows it as a gap."""
    from wc_fence_extract import extract_fenced_json
    parsed, _err = extract_fenced_json(text, EXPLANATION_TAG)
    if not isinstance(parsed, dict):
        return {}
    parts = {}
    for key in AGENT_EXPLANATION_PARTS:
        value = parsed.get(key)
        if (key == "options" and isinstance(value, dict)
                and value.get("state") == "follow"):
            parts[key] = {"state": "follow",
                          "text": _capped(value.get("text")) or ""}
        elif _capped(value) is not None:
            parts[key] = _capped(value)
    return parts


def explanation_from_transcript(path):
    """explanation_from_text() of the last result record in a
    claude-execution-output.json; {} when there is none."""
    try:
        with open(path, encoding="utf-8") as fh:
            transcript = json.load(fh)
    except (OSError, ValueError):
        return {}
    entries = transcript if isinstance(transcript, list) else [transcript]
    results = [e for e in entries
               if isinstance(e, dict) and e.get("type") == "result"]
    if not results or not isinstance(results[-1].get("result"), str):
        return {}
    return explanation_from_text(results[-1]["result"])


def explanation_parts(agent_parts, line, pr_title=""):
    """The first comment's parts: the agent's, with `line` always the
    loop's own verbatim text and `what_this_pr_does` falling back to the
    PR title when the agent gave none."""
    parts = {k: v for k, v in (agent_parts or {}).items()
             if k in AGENT_EXPLANATION_PARTS}
    parts["line"] = line
    if normalize_part(parts.get("what_this_pr_does"))[0] != "filled":
        if isinstance(pr_title, str) and pr_title.strip():
            parts["what_this_pr_does"] = pr_title
    return parts


def options_follow(parts):
    """True when the first comment's Options part says they follow
    (FR-003), so the later options comment is owed."""
    options = (parts or {}).get("options") if isinstance(parts, dict) else None
    return normalize_part(options)[0] == "follow"


def render_options(parts, identifier):
    """The later comment FR-003 owes when Options said they follow: the
    alternatives, fenced, or gap text naming that none were given."""
    _check_identifier(identifier)
    options = (parts or {}).get("options") if isinstance(parts, dict) else None
    text = options.get("text") if isinstance(options, dict) else options
    return OPTIONS_MARKER.format(identifier) + "\n" + _assemble(
        "Board loop: the options for `{0}`, as the first comment said would "
        "follow.".format(identifier), (("options", "Options"),),
        {"options": text})


def options_comment_owed(comments, bot_login):
    """research.md D4, read back from the PR's own comments (oldest
    first; each {"login"|"user": {"login"}, "body"}): the loop's own
    explaining comment said the options follow, and no later loop options
    comment for the same identifier exists. Comments by anyone but
    `bot_login` are never evidence either way."""
    owed = set()
    for comment in comments or []:
        if not isinstance(comment, dict):
            continue
        login = (comment.get("login")
                 or (comment.get("user") or {}).get("login")
                 or (comment.get("author") or {}).get("login"))
        if not bot_login or login != bot_login:
            continue
        first = (comment.get("body") or "").split("\n", 1)[0].strip()
        m = EXPLANATION_MARKER_RE.fullmatch(first)
        if m:
            if m.group(2) == "follow":
                owed.add(m.group(1))
            else:
                owed.discard(m.group(1))
            continue
        m = OPTIONS_MARKER_RE.fullmatch(first)
        if m:
            owed.discard(m.group(1))
    return bool(owed)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("render-explanation", "render-review", "summary",
                         "render-incomplete", "render-options",
                         "extract-explanation"))
    parser.add_argument("--in", dest="infile", default="")
    parser.add_argument("--id", dest="identifier", default="")
    args = parser.parse_args(argv)
    if args.mode == "extract-explanation":
        sys.stdout.write(json.dumps(
            explanation_from_transcript(args.infile), sort_keys=True,
            separators=(",", ":")) + "\n")
        return 0
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
        if args.mode == "render-explanation" and "line" in data:
            # board-loop.yml's fix job: the fixer's parts plus the loop's
            # own line text and PR title (explanation_parts()).
            body = render_explanation(
                explanation_parts(data.get("parts"), data["line"],
                                  data.get("pr_title", "")),
                args.identifier)
        elif args.mode == "render-explanation":
            body = render_explanation(data.get("parts", data), args.identifier)
        elif args.mode == "render-review":
            body = render_review(data.get("parts", {}), args.identifier,
                                 data.get("findings", []))
        elif args.mode == "render-incomplete":
            body = render_incomplete_review(args.identifier)
        elif args.mode == "render-options":
            # Empty output when Options did not say they follow: no later
            # comment is owed (FR-003).
            parts = data.get("parts", data)
            body = (render_options(parts, args.identifier)
                    if options_follow(parts) else "")
            if not body:
                return 0
        elif "parts" in data:
            # board-loop.yml's "Open the PR": the fixer's parts, with the
            # PR title standing in for an unfilled What this PR does.
            parts = explanation_parts(data.get("parts"), "",
                                      data.get("pr_title", ""))
            body = render_summary(parts.get("issue"),
                                  parts.get("what_this_pr_does"),
                                  args.identifier)
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
