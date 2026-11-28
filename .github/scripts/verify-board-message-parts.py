#!/usr/bin/env python3
"""Gate 184 (spec 130, FR-008): the board loop's message renderer.

Mode 1 renders every checked-in fixture in
fixtures/board-message-parts/ -- plus a derived "one part missing" variant
of each *-full fixture and an over-length variant -- and fails when a
rendered message lacks a part (neither filled nor gap text), lets fenced
text close its fence, reduces a review to a bare "No findings", exceeds the
57000 UTF-16 budget, or accepts a summary with a closing keyword.

`--self-test` feeds the checker a deliberately broken render for each
failure branch and requires each to be caught.
"""

import copy
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wc_message_parts as mp  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "board-message-parts")
PART_SETS = {"render-explanation": mp.EXPLANATION_PARTS,
             "render-review": mp.REVIEW_PARTS,
             "render-incomplete": mp.REVIEW_PARTS,
             "render-options": (("options", "Options"),),
             "summary": (("issue", "The issue"),
                         ("what_this_pr_does", "What this PR does"))}


def render(mode, identifier, data):
    if mode == "render-explanation" and "line" in data:
        return mp.render_explanation(
            mp.explanation_parts(data.get("parts"), data["line"],
                                 data.get("pr_title", "")), identifier)
    if mode == "render-explanation":
        return mp.render_explanation(data.get("parts", data), identifier)
    if mode == "render-incomplete":
        return mp.render_incomplete_review(identifier)
    if mode == "render-options":
        return mp.render_options(data.get("parts", data), identifier)
    if mode == "render-review":
        return mp.render_review(data.get("parts", {}), identifier,
                                data.get("findings", []))
    return mp.render_summary(data.get("issue"), data.get("pr"), identifier)


def check_body(mode, identifier, body, data):
    """Problems with one rendered body (empty list when sound)."""
    problems = []
    for _part, label in PART_SETS[mode]:
        if "**{0}**".format(label) not in body:
            problems.append("part {0!r} absent".format(label))
    if mode != "summary" and identifier not in body:
        problems.append("identifier {0} not named".format(identifier))
    if mode in ("render-review", "render-incomplete"):
        if re.fullmatch(r"\W*No findings\.?\W*", body.strip()):
            problems.append("review reduces to a bare 'No findings'")
    problems += part_text_problems(mode, body, data)
    if mp.utf16_len(body) > mp.TOTAL_BUDGET:
        problems.append("body over the {0}-unit budget".format(mp.TOTAL_BUDGET))
    # A fence must not be closed early: every line that opens a fence is
    # matched by a later line of the same length, and nothing outside the
    # fences contains user-controlled HTML.
    open_fence = None
    for line in body.split("\n"):
        m = re.match(r"^(`{3,})\s*$", line)
        if open_fence is None:
            if m:
                open_fence = m.group(1)
        elif m and len(m.group(1)) >= len(open_fence):
            open_fence = None
    if open_fence is not None:
        problems.append("a fence is never closed")
    outside = _outside_fences(body)
    for text in _texts(data):
        # Every HTML tag in a user text must stay inside a fence; the
        # renderer's own <details>/<summary> wrapper is not user text.
        leaked = [tag for tag in re.findall(r"<[A-Za-z/!][^>\n]*>", text)
                  if not re.match(r"</?(details|summary)\b", tag, re.I)
                  and tag in outside]
        if leaked:
            problems.append("user HTML escaped its fence: {0}".format(leaked[0]))
            break
    return problems


def _effective_parts(mode, data):
    """The part values the renderer was given, as it resolves them."""
    if not isinstance(data, dict):
        return {}
    if mode == "render-explanation":
        if "line" in data:
            return mp.explanation_parts(data.get("parts"), data["line"],
                                        data.get("pr_title", ""))
        parts = data.get("parts", data)
        return parts if isinstance(parts, dict) else {}
    if mode == "render-options":
        parts = data.get("parts", data)
        options = parts.get("options") if isinstance(parts, dict) else None
        return {"options": options.get("text") if isinstance(options, dict)
                else options}
    if mode == "render-incomplete":
        return {}
    if mode == "summary":
        return {"issue": data.get("issue"), "what_this_pr_does": data.get("pr")}
    parts = data.get("parts", {})
    return parts if isinstance(parts, dict) else {}


def _section(body, label, labels):
    """The text under the `**label**` heading up to the next part heading."""
    start = body.find("\n**{0}**\n".format(label))
    if start == -1:
        start = 0 if body.startswith("**{0}**\n".format(label)) else -1
    if start == -1:
        return None
    end = len(body)
    for other in labels:
        if other == label:
            continue
        idx = body.find("\n**{0}**\n".format(other), start + 1)
        if idx != -1:
            end = min(end, idx)
    return body[start:end]


def part_text_problems(mode, body, data):
    """MF004: the text after each label, not just the label. A gap part must
    carry its fixed gap text; a filled part must carry its own text and no
    gap text."""
    problems = []
    parts = _effective_parts(mode, data)
    labels = [label for _p, label in PART_SETS[mode]]
    findings = data.get("findings") if isinstance(data, dict) else None
    for part, label in PART_SETS[mode]:
        section = _section(body, label, labels)
        if section is None:
            continue  # the absent-label check reports it
        if mode == "render-incomplete":
            state, text, kind = "gap", "", "incomplete"
        else:
            state, text, kind = mp.normalize_part(parts.get(part), part)
        if mode == "render-review" and part == "open":
            if mp.items_present(findings):
                if "finding(s) open" not in section:
                    problems.append("part 'Open' does not list the findings")
                continue
            if state == "gap":
                if "Nothing is open" not in section:
                    problems.append("part 'Open' with no findings does not "
                                    "say nothing is open")
                continue
        if state == "filled":
            first = text.splitlines()[0].strip()[:30] if text else ""
            if first and first not in section:
                problems.append("part {0!r} lost its text".format(label))
            if "not provided" in section.split("```", 1)[0]:
                problems.append("part {0!r} filled but rendered as a gap"
                                .format(label))
        elif mp.gap_text(part, kind) not in section:
            problems.append("part {0!r} lacks its gap text".format(label))
    return problems


# The forms GitHub closes an issue on; a pull URL closes nothing.
CLOSING_FORMS = ("Closes #5", "Fixes GH-5", "Resolves o/r#5",
                 "Closes https://github.com/o/r/issues/5")


def _refuses(text):
    """Whether the summary renderer refuses `text` for a closing keyword."""
    try:
        mp.render_summary(text, "pr", "#7")
    except mp.Refusal as exc:
        return str(exc).startswith("closing keyword")
    return False


def closing_forms_problems(matcher=None):
    """MF004: every closing form the summary must refuse is refused."""
    matcher = matcher or _refuses
    return ["closing form {0!r} not matched".format(form)
            for form in CLOSING_FORMS if not matcher(form)]


def _texts(data):
    parts = data.get("parts", data) if isinstance(data, dict) else {}
    return [v for v in parts.values() if isinstance(v, str)] \
        if isinstance(parts, dict) else []


def _outside_fences(body):
    out, open_fence = [], None
    for line in body.split("\n"):
        m = re.match(r"^(`{3,})\s*$", line)
        if open_fence is None:
            if m:
                open_fence = m.group(1)
            else:
                out.append(line)
        elif m and len(m.group(1)) >= len(open_fence):
            open_fence = None
    return "\n".join(out)


def run_extract_case(name, fx):
    """An extract-explanation fixture: the fixer's final message in, the
    parts the loop keeps out (exactly)."""
    got = mp.explanation_from_text(fx["input"].get("result", ""))
    if got != fx["expect"]:
        return ["{0}: extracted {1!r}, expected {2!r}".format(
            name, got, fx["expect"])]
    return []


def run_case(name, mode, identifier, data, expect):
    if mode == "extract-explanation":
        return run_extract_case(name, {"input": data, "expect": expect})
    try:
        body = render(mode, identifier, data)
    except mp.Refusal:
        return [] if expect == "refuse" else [
            "{0}: refused but expected a render".format(name)]
    if expect == "refuse":
        return ["{0}: rendered but expected a refusal".format(name)]
    return ["{0}: {1}".format(name, p)
            for p in check_body(mode, identifier, body, data)]


def load_fixtures():
    cases = []
    for path in sorted(glob.glob(os.path.join(FIXTURES, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            fx = json.load(fh)
        cases.append((os.path.basename(path), fx))
    return cases


def derived_cases(name, fx):
    """One part missing per part, an empty variant, and over-length."""
    mode = fx["mode"]
    if mode not in ("render-explanation", "render-review"):
        return
    key = "parts"
    for part, _label in PART_SETS[mode]:
        for variant in ("missing", "empty", "nonstring"):
            data = copy.deepcopy(fx["input"])
            parts = data.setdefault(key, {})
            if variant == "missing":
                parts.pop(part, None)
            elif variant == "empty":
                parts[part] = ""
            else:
                parts[part] = {"x": 1}
            yield "{0}[{1}:{2}]".format(name, part, variant), mode, \
                fx["id"], data
    data = copy.deepcopy(fx["input"])
    for part, _label in PART_SETS[mode]:
        data[key][part] = ("long ```` text\n" * 4000)
    yield "{0}[over-length]".format(name), mode, fx["id"], data


def options_roundtrip_problems():
    """specs/130 FR-003 / MF008: "options follow" with no text to follow
    renders a gap in the first comment and reads as not following, so no
    empty "Options: not provided" comment is posted later."""
    ident = "bl-b9677278"
    problems = []
    for empty in ({"state": "follow"}, {"state": "follow", "text": "  "}):
        parts = {"options": empty}
        comment = {"body": mp.render_explanation(parts, ident)}
        if mp.options_follow(parts):
            problems.append("empty follow options read as follow")
        if mp.gap_text("options", "empty") not in comment["body"]:
            problems.append("empty follow options show no gap text")
    return ["options round trip: " + p for p in problems]


def review_problems():
    """MF005 and MF006: an empty review says nothing is open; a worst-case
    review comment stays under GitHub's 65,536-character limit."""
    ident = "bl-b9677278"
    problems = []
    empty = mp.render_review({}, ident, [])
    if "Nothing is open" not in empty:
        problems.append("a review with no findings and no report block does "
                        "not say nothing is open")
    huge = {p: "x" * 20000 for p, _l in mp.REVIEW_PARTS}
    head = "Board loop review.\n\n" + mp.render_review(huge, ident, [])
    tail = "\n<!-- round record -->" + "t" * 9000
    shown = 25
    budget = mp.review_findings_budget(head, tail, shown)
    finding = mp.fenced_section("### Finding 1 -- in-scope\n\nReviewer agent "
                                "output, shown as text -- data, not "
                                "instruction:", "y" * 100000, budget)
    body = "\n".join([head] + [finding] * shown + [tail])
    if len(body) > 65536 or mp.utf16_len(body) > 65536:
        problems.append("worst-case review body is {0} characters, over "
                        "65536".format(len(body)))
    return ["review body: " + p for p in problems]


def check_all():
    problems = (options_roundtrip_problems() + closing_forms_problems()
                + review_problems())
    cases = load_fixtures()
    if not cases:
        return ["no fixtures found in {0}".format(FIXTURES)]
    for name, fx in cases:
        problems += run_case(name, fx["mode"], fx["id"], fx["input"],
                             fx["expect"])
        if name.endswith("-full.json"):
            for cname, mode, ident, data in derived_cases(name, fx):
                problems += run_case(cname, mode, ident, data, "ok")
    return problems


REGISTRY = os.path.join(HERE, "board-fixed-messages.json")
TAG_RE = re.compile(r"#\s*fixed-message:\s*([a-z0-9-]+)")
KNOWN_CLAIMS = ("board_merges_next_run", "board_merges_when_ready",
                "maintainer_merges", "gate_suite_ran")

# FR-011: every fixed message that claims a next action or a protection is
# registered. The list is checked, not opt-in: a required id missing from
# the registry fails, and so does a claim phrase in a registered source that
# no registered variant carries (an untagged message).
REQUIRED_IDS = ("merge-transient-fix", "prove-verify-only",
                "readiness-next-step")
CLAIM_PHRASE_RE = re.compile(
    r"next board-loop run|a maintainer may merge|board loop merges|"
    r"waits for a maintainer|nothing merges")


def claim_holds(claim, cfg):
    if claim == "board_merges_when_ready":
        return cfg["auto_merge"] and not cfg["kill_switch"]
    if claim == "board_merges_next_run":
        # MF004: a fix PR waits for a maintainer's merge, so the claim that
        # the board merges it next run never holds for the fix class.
        return (cfg["auto_merge"] and not cfg["kill_switch"]
                and cfg.get("pr_class") != "fix")
    return claim in KNOWN_CLAIMS


def _matches(when, cfg):
    return all(cfg.get(k) == v for k, v in (when or {}).items())


def check_registry(registry, read_source, required=REQUIRED_IDS):
    """Mode 2: every configuration (auto-merge x kill switch x PR class) a
    registered message can be posted in has exactly one variant whose
    claims hold there; every tag in a source names a registered id."""
    problems = []
    messages = registry.get("messages") or []
    ids = {m.get("id") for m in messages}
    sources = {m.get("source") for m in messages}
    for m in messages:
        reach = m.get("reachable") or {}
        for auto in (True, False):
            for kill in (True, False):
                for klass in ("fix", "bump"):
                    cfg = {"auto_merge": auto, "kill_switch": kill,
                           "pr_class": klass}
                    if not _matches(reach, cfg):
                        continue
                    hits = [v for v in m.get("variants") or []
                            if _matches(v.get("when"), cfg)]
                    if len(hits) != 1:
                        problems.append("{0}: {1} variant(s) match {2}".format(
                            m.get("id"), len(hits), cfg))
                        continue
                    for claim in hits[0].get("claims") or []:
                        if not claim_holds(claim, cfg):
                            problems.append(
                                "{0}: claim {1} contradicted under {2}".format(
                                    m.get("id"), claim, cfg))
        # T018: the posting-time source still carries the registered text.
        text_src = read_source(m.get("source"))
        flat = re.sub(r'"\s*\n\s*"', "", text_src or "")
        if text_src is None:
            problems.append("{0}: source {1} unreadable".format(
                m.get("id"), m.get("source")))
            continue
        for v in m.get("variants") or []:
            if v.get("text") not in flat:
                problems.append("{0}: registered text no longer in {1}: "
                                "{2!r}".format(m.get("id"), m.get("source"),
                                               v.get("text")))
        if "fixed-message: {0}".format(m.get("id")) not in text_src:
            problems.append("{0}: source {1} lacks its fixed-message tag"
                            .format(m.get("id"), m.get("source")))
    for needed in required:
        if needed not in ids:
            problems.append("required fixed message {0} is not registered"
                            .format(needed))
    for source in sources:
        text_src = read_source(source) or ""
        flat = re.sub(r'"\s*\n\s*"', "", text_src)
        registered = " ".join(v.get("text") or ""
                              for m in messages if m.get("source") == source
                              for v in m.get("variants") or [])
        for hit in CLAIM_PHRASE_RE.finditer(flat):
            if hit.group(0) not in registered:
                problems.append("untagged fixed message in {0}: the claim "
                                "phrase {1!r} is in no registered variant"
                                .format(source, hit.group(0)))
        for tag in TAG_RE.findall(text_src):
            if tag not in ids:
                problems.append("unregistered fixed message {0} in {1}"
                                .format(tag, source))
    return problems


def _read_source(name):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            return fh.read()
    except (OSError, TypeError):
        return None


WORKFLOWS = os.path.join(HERE, os.pardir, "workflows")
PASTED_RE = re.compile(r"\*\*(The line|The code|Why it matters|Not decided)\*\*"
                       r"|_PARTS\s*=|def (render_explanation|render_review)")


def single_home_problems(texts):
    """T020 / CLAUDE.md "one home": no workflow carries the renderer's
    labels or part tables; they call wc_message_parts.py."""
    return ["{0}: pasted renderer logic ({1!r}); call wc_message_parts.py"
            .format(name, m.group(0))
            for name, text in texts for m in [PASTED_RE.search(text)] if m]


BOARD_LOOP = os.path.join(WORKFLOWS, "board-loop.yml")


def _step(text, name):
    """The text of the step called `name` up to the next step, or ''."""
    m = re.search(r"\n      - name: " + re.escape(name) + r"\n", text)
    if not m:
        return ""
    end = text.find("\n      - name: ", m.end())
    return text[m.end(): end if end != -1 else len(text)]


def wiring_problems(text):
    """T023 (FR-001..FR-004): the fixer is asked for every part it
    supplies, in the block wc_message_parts reads; fix-agent extracts
    them and hands them on; fix renders the first comment, the body
    summary and the options comment from them, for issue items too."""
    problems = []
    fixer = _step(text, "Fixer")
    if "```" + mp.EXPLANATION_TAG not in fixer:
        problems.append("Fixer prompt does not ask for a ```{0}``` block"
                        .format(mp.EXPLANATION_TAG))
    for part in mp.AGENT_EXPLANATION_PARTS:
        if '"{0}"'.format(part) not in fixer:
            problems.append("Fixer prompt does not ask for part {0!r}"
                            .format(part))
    if '"state": "follow"' not in fixer:
        problems.append("Fixer prompt does not offer options state follow")
    extract = _step(text, "Extract the fixer's explanation parts")
    if "wc_message_parts.py\" extract-explanation" not in extract:
        problems.append("fix-agent does not extract the explanation parts "
                        "with wc_message_parts.py extract-explanation")
    if "explain-parts: ${{ steps.explain-extract.outputs.parts }}" not in text:
        problems.append("fix-agent does not output explain-parts")
    consumer = "${{ needs.fix-agent.outputs.explain-parts }}"
    opener = _step(text, "Open the PR")
    if consumer not in opener or "wc_message_parts.py\" summary" not in opener:
        problems.append("Open the PR does not render the body summary from "
                        "explain-parts")
    explain = _step(text, "Explain the line on the PR (fix)")
    if consumer not in explain:
        problems.append("Explain the line on the PR (fix) does not read "
                        "explain-parts")
    if "wc_message_parts.py\" render-options" not in explain:
        problems.append("Explain the line on the PR (fix) never posts the "
                        "options comment")
    if re.search(r"(?m)^\s*exit [1-9]", explain):
        problems.append("Explain the line on the PR (fix) can fail the step: "
                        "a failed comment must warn so the route backstop "
                        "re-check, cross-link and issue marker still run (MF003)")
    m = re.search(r"(?:^|\n)        if: ([^\n]*)", explain)
    if m and "BOARD_LINE_ID" in m.group(1):
        problems.append("Explain the line on the PR (fix) skips issue items "
                        "(FR-001a)")
    return problems


def wiring_check():
    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            return wiring_problems(fh.read())
    except OSError as exc:
        return ["board-loop.yml unreadable: {0}".format(exc)]


def wiring_self_test():
    """Each wiring branch is caught on a mutated board-loop.yml."""
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()
    failed = []
    if wiring_problems(text):
        failed.append("sound board-loop.yml flagged")
    mutations = {
        "missing explanation tag": ("```" + mp.EXPLANATION_TAG, "```x"),
        "missing why_it_matters ask": ('"why_it_matters": "why', '"w": "why'),
        "missing follow offer": ('"state": "follow"', '"state": "x"'),
        "no extract step": ("extract-explanation --in", "x --in"),
        "no explain-parts output":
            ("explain-parts: ${{ steps.explain-extract", "x: ${{ steps.e"),
        "no options comment": ("render-options --in", "x --in"),
        "explain step fails on a refused comment":
            ("post the explanation and its options by hand (specs/130 FR-003).\"\n              exit 0",
             "post the explanation and its options by hand (specs/130 FR-003).\"\n              exit 1"),
        "issue items skipped":
            ("        if: steps.push-pr.outputs.pr-url != ''\n        env:\n"
             "          GH_TOKEN: ${{ env.WC_BOT_TOKEN }}\n"
             "          ISSUE_NUMBER: ${{ needs.select.outputs.issue-number }}\n"
             "          PR_NUMBER",
             "        if: steps.push-pr.outputs.pr-url != '' && "
             "env.BOARD_LINE_ID != ''\n        env:\n"
             "          GH_TOKEN: ${{ env.WC_BOT_TOKEN }}\n"
             "          ISSUE_NUMBER: ${{ needs.select.outputs.issue-number }}\n"
             "          PR_NUMBER"),
    }
    for label, (old, new) in mutations.items():
        if old not in text:
            failed.append("{0} (mutation target gone)".format(label))
        elif not wiring_problems(text.replace(old, new)):
            failed.append(label)
    return failed


def single_home_check():
    texts = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, "*.yml"))):
        with open(path, encoding="utf-8") as fh:
            texts.append((os.path.basename(path), fh.read()))
    return single_home_problems(texts)


def registry_check():
    try:
        with open(REGISTRY, encoding="utf-8") as fh:
            registry = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["fixed-message registry unreadable: {0}".format(exc)]
    return check_registry(registry, _read_source)


def registry_self_test():
    """Each failure branch of check_registry is caught."""
    failed = []
    base = {"messages": [{"id": "m", "source": "s",
                          "variants": [{"when": {}, "text": "hello",
                                        "claims": ["maintainer_merges"]}]}]}
    src = "# fixed-message: m\nx = 'hello'\n"
    def chk(registry, read_source, required=("m",)):
        return check_registry(registry, read_source, required)
    if chk(base, lambda _n: src):
        failed.append("sound registry flagged")
    contra = copy.deepcopy(base)
    contra["messages"][0]["variants"][0]["claims"] = ["board_merges_next_run"]
    if not chk(contra, lambda _n: src):
        failed.append("contradicted claim accepted")
    if not chk(base, lambda _n: src + "# fixed-message: other\n"):
        failed.append("unregistered fixed message accepted")
    if not chk(base, lambda _n: "# fixed-message: m\n"):
        failed.append("drifted source text accepted")
    split = copy.deepcopy(base)
    split["messages"][0]["variants"] = [
        {"when": {"pr_class": "fix"}, "text": "hello", "claims": []}]
    if not chk(split, lambda _n: src):
        failed.append("uncovered configuration accepted")
    # MF002: an untagged message -- a claim phrase in a registered source
    # that no registered variant carries -- is caught.
    if not chk(base, lambda _n: src + "z = 'a maintainer may merge it'\n"):
        failed.append("untagged claim message accepted")
    if not chk(base, lambda _n: src, required=("m", "gone")):
        failed.append("missing required message accepted")
    return failed


def self_test():
    good =render("render-review", "bl-b9677278", {"parts": {}, "findings": []})
    data = {"parts": {}}
    broken = {
        "dropped part": good.replace("**Checked**", "**X**"),
        "bare No findings": "No findings.",
        "unnamed identifier": good.replace("bl-b9677278", "that"),
        "unclosed fence": good + "\n```\nopen",
        "over budget": good + "x" * (mp.TOTAL_BUDGET + 1),
    }
    failed = []
    for label, body in broken.items():
        if not check_body("render-review", "bl-b9677278", body, data):
            failed.append(label)
    try:
        mp.render_summary("a", "Closes #5", "bl-b9677278")
        failed.append("closing keyword accepted")
    except mp.Refusal:
        pass
    # MF004: one mutation per check on the text after the labels.
    ident = "bl-b9677278"
    gap_data = {"parts": {"code": "real code text"}}
    gap_body = render("render-explanation", ident, gap_data)
    for label, mutated in (
            ("gap text dropped",
             gap_body.replace(mp.gap_text("issue", "missing"), "")),
            ("every filled part rendered as a gap",
             render("render-explanation", ident, {"parts": {}}))):
        if not check_body("render-explanation", ident, mutated, gap_data):
            failed.append(label)
    if check_body("render-explanation", ident, gap_body, gap_data):
        failed.append("sound explanation flagged")
    if not closing_forms_problems(lambda form: bool(re.search(r"#\d+", form))):
        failed.append("a closing matcher without its GH-N and URL forms")
    swapped = {"messages": [{
        "id": "m", "source": "s", "reachable": {"auto_merge": True,
                                                 "kill_switch": False},
        "variants": [{"when": {"pr_class": "fix"}, "text": "hello",
                      "claims": ["board_merges_next_run"]},
                     {"when": {"pr_class": "bump"}, "text": "hello",
                      "claims": ["board_merges_next_run"]}]}]}
    if not check_registry(swapped, lambda _n: "# fixed-message: m\nhello\n",
                          required=("m",)):
        failed.append("fix-class claim swapped to board_merges_next_run")
    failed += registry_self_test()
    failed += wiring_self_test()
    if not single_home_problems([("x.yml", "echo '**Why it matters**'")]):
        failed.append("pasted renderer label accepted")
    return failed


def main(argv):
    if "--self-test" in argv:
        failed = self_test()
        for label in failed:
            print("::error::verify-board-message-parts self-test: "
                  "{0} was not caught".format(label))
        if not failed:
            print("verify-board-message-parts self-test: every mutation caught")
        return 1 if failed else 0
    problems = (check_all() + registry_check() + single_home_check()
                + wiring_check())
    for problem in problems:
        print("::error::verify-board-message-parts: {0}".format(problem))
    if not problems:
        print("verify-board-message-parts: all fixtures render every part")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
