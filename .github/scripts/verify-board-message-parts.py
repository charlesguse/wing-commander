#!/usr/bin/env python3
"""Gate (spec 130, FR-008): the board loop's message renderer.

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
             "summary": (("issue", "The issue"),
                         ("what_this_pr_does", "What this PR does"))}


def render(mode, identifier, data):
    if mode == "render-explanation":
        return mp.render_explanation(data.get("parts", data), identifier)
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
    if mode == "render-review":
        if re.fullmatch(r"\W*No findings\.?\W*", body.strip()):
            problems.append("review reduces to a bare 'No findings'")
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
    for text in _texts(data):
        if "<script" in text and "<script" in _outside_fences(body):
            problems.append("user HTML escaped its fence")
    return problems


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


def run_case(name, mode, identifier, data, expect):
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
    if mode == "summary":
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


def check_all():
    problems = []
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
KNOWN_CLAIMS = ("board_merges_next_run", "maintainer_merges", "gate_suite_ran")


def claim_holds(claim, cfg):
    if claim == "board_merges_next_run":
        return cfg["auto_merge"] and not cfg["kill_switch"]
    return claim in KNOWN_CLAIMS


def _matches(when, cfg):
    return all(cfg.get(k) == v for k, v in (when or {}).items())


def check_registry(registry, read_source):
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
    for source in sources:
        for tag in TAG_RE.findall(read_source(source) or ""):
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
    if check_registry(base, lambda _n: src):
        failed.append("sound registry flagged")
    contra = copy.deepcopy(base)
    contra["messages"][0]["variants"][0]["claims"] = ["board_merges_next_run"]
    if not check_registry(contra, lambda _n: src):
        failed.append("contradicted claim accepted")
    if not check_registry(base, lambda _n: src + "# fixed-message: other\n"):
        failed.append("unregistered fixed message accepted")
    if not check_registry(base, lambda _n: "# fixed-message: m\n"):
        failed.append("drifted source text accepted")
    split = copy.deepcopy(base)
    split["messages"][0]["variants"] = [
        {"when": {"pr_class": "fix"}, "text": "hello", "claims": []}]
    if not check_registry(split, lambda _n: src):
        failed.append("uncovered configuration accepted")
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
    failed += registry_self_test()
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
    problems = check_all() + registry_check() + single_home_check()
    for problem in problems:
        print("::error::verify-board-message-parts: {0}".format(problem))
    if not problems:
        print("verify-board-message-parts: all fixtures render every part")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
