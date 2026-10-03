#!/usr/bin/env python3
"""Board loop route backstop (specs/057-autonomous-board-loop,
contracts/route-backstop.md, research.md D5/D6).

WHY THIS EXISTS
---------------
The route-propose agent's fix/spec proposal can only ever be NARROWED by
code, never widened (FR-017): `route()` calls the shared
wing-commander-size-path-backstop composite (via its own runtime wrapper,
outside this module -- see board-loop.yml's `route` job) with the board's
own thresholds, ORs in `contract_widened()`'s structural verdict, and
re-applies the same decision to the pushed branch's final diff
(`route_final_diff()`, FR-021). A fix this loop cannot push (a workflow
file, while the App holds no Workflows permission) is narrowed to "hold"
rather than to "spec": see `workflow_push_blocked_paths()`.

`contract_widened()` (research.md D6) is a structural check, not a size
check: it asks "did this diff touch the exact YAML keys that define a
published interface" -- a workflow's own `workflow_call:` block (inputs,
outputs, and everything else nested under it, a superset of the contract's
literal "inputs:/outputs:" wording, chosen because `secrets:` sits in the
same block and is just as much a deliberate-act boundary -- Principle VII)
or a `wing-commander-*` composite's top-level `inputs:`/`outputs:` keys.
"""
import re
import sys
import unicodedata

TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):")
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
DIFF_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def _top_level_key_ranges(text):
    """{key_name: (start_line, end_line_exclusive)}, 1-indexed, for every
    column-0 `key:` line in `text`."""
    lines = text.splitlines()
    keys = []
    for i, line in enumerate(lines, start=1):
        m = TOP_LEVEL_KEY_RE.match(line)
        if m:
            keys.append((m.group(1), i))
    ranges = {}
    for idx, (name, start) in enumerate(keys):
        end = keys[idx + 1][1] if idx + 1 < len(keys) else len(lines) + 1
        ranges[name] = (start, end)
    return ranges


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _protected_range_workflow(text):
    """The whole `on: workflow_call:` block's line range (1-indexed,
    end-exclusive), or None when the file carries no such trigger."""
    lines = text.splitlines()
    top = _top_level_key_ranges(text)
    on_range = top.get("on")
    if on_range is None:
        return None
    start, end = on_range

    wc_start = None
    wc_indent = None
    for i in range(start, end):
        line = lines[i - 1] if i - 1 < len(lines) else ""
        # A trailing `# comment` on the `workflow_call:` line itself is
        # valid YAML and must not make this block register as absent --
        # that would let a diff widen inputs:/outputs: underneath it while
        # contract_widened() silently reports nothing touched.
        m = re.match(r"^(\s+)workflow_call:\s*(\{\s*\})?\s*(#.*)?$", line)
        if m:
            wc_start = i
            wc_indent = len(m.group(1))
            break
    if wc_start is None:
        return None

    wc_end = end
    for i in range(wc_start + 1, end):
        line = lines[i - 1] if i - 1 < len(lines) else ""
        if line.strip() == "":
            continue
        if _indent_of(line) <= wc_indent:
            wc_end = i
            break
    return (wc_start, wc_end)


def _protected_range_composite(text):
    """The union range covering top-level `inputs:` and `outputs:` in a
    composite action.yml, or None when neither key is present."""
    top = _top_level_key_ranges(text)
    starts = [top[k][0] for k in ("inputs", "outputs") if k in top]
    ends = [top[k][1] for k in ("inputs", "outputs") if k in top]
    if not starts:
        return None
    return (min(starts), max(ends))


def _new_line_ranges_for_file(diff_text, path):
    """[(start, end_exclusive), ...] of new-file line numbers this diff
    touches for `path`, parsed from its own unified-diff hunk headers."""
    sections = []
    matches = list(DIFF_FILE_HEADER_RE.finditer(diff_text))
    for idx, m in enumerate(matches):
        if m.group(1) != path:
            continue
        section_start = m.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(diff_text)
        sections.append(diff_text[section_start:section_end])

    ranges = []
    for section in sections:
        for line in section.splitlines():
            hm = HUNK_HEADER_RE.match(line)
            if not hm:
                continue
            new_start = int(hm.group(1))
            new_len = int(hm.group(2)) if hm.group(2) else 1
            ranges.append((new_start, new_start + new_len))
    return ranges


def _is_workflow_path(path):
    return path.startswith(".github/workflows/") and (path.endswith(".yml") or path.endswith(".yaml"))


def _is_wc_composite_action_path(path):
    return (path.startswith(".github/actions/wing-commander-")
            and path.split("/")[-1] in ("action.yml", "action.yaml"))


def normalize_repo_path(path):
    """A drafted path as a repository-relative path: backslashes made
    forward, any leading "./" dropped, and a unified-diff "a/" or "b/"
    prefix dropped in front of ".github/"."""
    p = str(path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for prefix in ("a/", "b/"):
        if p.startswith(prefix + ".github/"):
            p = p[len(prefix):]
    return p


WORKFLOW_CALL_RE = re.compile(r"\bworkflow_call\b")


def _contract_block(path, text):
    """The text of `path`'s published-contract block in `text` -- a
    workflow's whole `on: workflow_call:` block, or a composite's top-level
    `inputs:`/`outputs:` -- trailing whitespace dropped, or None when the
    file is absent or has none."""
    if not text:
        return None
    rng = (_protected_range_workflow(text) if _is_workflow_path(path)
           else _protected_range_composite(text))
    if rng is None:
        return None
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines[rng[0] - 1:rng[1] - 1]).strip()


def contract_changed(path, old_text, new_text):
    """True when the change from `old_text` (None: the file did not exist)
    to `new_text` (None or empty: the file is gone) widens or breaks the
    published contract at `path` (Principle VII): its contract block
    differs -- which covers adding or removing `workflow_call:` and adding
    or removing a composite's inputs/outputs -- or a `wing-commander-*`
    composite was added or deleted outright."""
    path = normalize_repo_path(path)
    if _is_wc_composite_action_path(path):
        if (old_text is None) != (not new_text):
            return True
    elif not _is_workflow_path(path):
        return False
    return _contract_block(path, old_text) != _contract_block(path, new_text)


def _split_hunks(diff_text):
    """The hunk bodies of one file's unified diff, each a list of its
    ' '/'-'/'+' lines; header lines are found with HUNK_HEADER_RE (the
    module's one hunk-header parser) and their line numbers are ignored."""
    hunks = []
    current = None
    for line in (diff_text or "").splitlines():
        if HUNK_HEADER_RE.match(line):
            current = []
            hunks.append(current)
        elif current is not None and line[:1] in (" ", "-", "+") and not line.startswith(("+++", "---")):
            current.append(line)
        elif current is not None and line == "":
            current.append(" ")
    return hunks


def _apply_drafted_diff(old_text, diff_text):
    """main's `old_text` with the drafted hunks applied, each located by
    its own context and removed lines -- never by the line numbers in its
    header, which an agent can get wrong -- or None when any hunk cannot be
    located (no hunks, a hunk with no old-side lines in an existing file,
    or old-side lines that do not occur in order)."""
    hunks = _split_hunks(diff_text)
    if not hunks:
        return None
    old_lines = (old_text or "").splitlines()
    result = []
    pos = 0
    for hunk in hunks:
        src = [line[1:] for line in hunk if line[:1] in (" ", "-")]
        dst = [line[1:] for line in hunk if line[:1] in (" ", "+")]
        if not src:
            if old_lines:
                return None
            result.extend(dst)
            continue
        at = None
        for i in range(pos, len(old_lines) - len(src) + 1):
            if [l.rstrip() for l in old_lines[i:i + len(src)]] == [l.rstrip() for l in src]:
                at = i
                break
        if at is None:
            return None
        result.extend(old_lines[pos:at])
        result.extend(dst)
        pos = at + len(src)
    result.extend(old_lines[pos:])
    return "\n".join(result) + ("\n" if result else "")


COMPOSITE_CONTRACT_KEY_RE = re.compile(r"^(inputs|outputs):")


def _unapplied_diff_signals_contract(path, diff):
    """For a drafted diff _apply_drafted_diff() could not place: True when
    one of its own added or removed lines names the contract outright -- a
    workflow's `workflow_call` trigger, or a composite's column-0
    `inputs:`/`outputs:` key. A wholly new file always applies, so the
    create case never reaches here."""
    changed = [line[1:] for line in (diff or "").splitlines()
               if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))]
    if _is_workflow_path(path):
        return any(WORKFLOW_CALL_RE.search(line) for line in changed)
    if _is_wc_composite_action_path(path):
        return any(COMPOSITE_CONTRACT_KEY_RE.match(line) for line in changed)
    return False


def drafted_contract_widened(file_changes, read_text, unknown=None):
    """The pre-push half of FR-021's contract check, run on the route
    agent's drafted change (`file-changes`: [{"path", "diff"}]) against
    main's own file content -- `read_text(path)` returns it, or None for a
    file main does not have. Each drafted diff is applied to main's text by
    content (_apply_drafted_diff()), and the path is returned when
    contract_changed() says the result widens or breaks the published
    contract (Principle VII). A diff that cannot be applied is an unknown,
    not a widening: it counts only when its own changed lines carry a
    contract signal (_unapplied_diff_signals_contract()). Anything else is
    left to the precise check on the pushed diff, route_final_diff()
    (FR-021), which files the spec as a breach if the real change widens
    a contract -- the way route() leaves a rate-limited agent's missing
    proposal to a later run instead of guessing. Counting every unappliable
    diff on a file with a contract block sent plain plumbing fixes to a
    spec-proposal (#936). A change to a workflow's `run:` code or a
    composite's `runs:` steps is never a contract change, however many
    workflow files it edits.

    `unknown`, when a list, receives each path whose effect is left
    unknown. A workflow file this loop cannot push is held, never pushed,
    so no final-diff check follows: route() records those paths, and the
    hold comment tells the maintainer the contract effect is unchecked."""
    widened = []
    for fc in file_changes or []:
        if not isinstance(fc, dict):
            continue
        path = normalize_repo_path(fc.get("path"))
        if not (_is_workflow_path(path) or _is_wc_composite_action_path(path)):
            continue
        diff = fc.get("diff") if isinstance(fc.get("diff"), str) else ""
        old_text = read_text(path)
        new_text = _apply_drafted_diff(old_text, diff)
        if new_text is None:
            if _unapplied_diff_signals_contract(path, diff):
                widened.append(path)
            else:
                if unknown is not None:
                    unknown.append(path)
                print("note: board_route_backstop: the drafted diff for {0} could not be applied "
                      "to main; whether it changes a contract is left to the final-diff "
                      "check.".format(path), file=sys.stderr)
            continue
        if contract_changed(path, old_text, new_text):
            widened.append(path)
    return widened


def workflow_push_blocked_paths(diff_paths, can_push_workflows):
    """The paths in `diff_paths` under `.github/workflows/` (any file, not
    only *.yml) this loop cannot push, or [] when it can. The wing-commander App holds no Workflows
    permission (docs/setup.md), and GitHub refuses a push that changes a
    workflow file without it, so a fix whose drafted diff edits one cannot
    land from this loop however small it is. `can_push_workflows` is the
    maintainer's statement that the App has been granted that permission
    (`WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS`).

    This replaced the pre-push `touches_protected_file()` proxy, which
    counted every touched workflow or `wing-commander-*` composite as
    contract-widening and so routed nearly every fix in this repository to
    a spec (the 2026-10-01 board reset). Contract widening is decided by
    `drafted_contract_widened()` before push and `contract_widened()` on
    the pushed diff (`route_final_diff()`, FR-021); a workflow change that
    widens a contract is spec-shaped, never held."""
    if can_push_workflows:
        return []
    # GitHub refuses a push that changes ANY file under .github/workflows/
    # without the permission, not only *.yml.
    return [p for p in (normalize_repo_path(d) for d in diff_paths)
            if p.startswith(".github/workflows/")]


def read_base_contents(base_sha, paths):
    """{path: the file's text at `base_sha`, or None when it has none} for
    every workflow or `wing-commander-*` composite path in `paths` -- the
    `base_contents` contract_widened() compares against. The one home for
    this read (board-loop.yml's fix and readiness final-diff checks).
    None, never {}, when `base_sha` is empty: no base, no comparison."""
    import subprocess
    if not base_sha:
        return None
    contents = {}
    for path in paths:
        if not (_is_workflow_path(path) or _is_wc_composite_action_path(path)):
            continue
        shown = subprocess.run(["git", "show", "{0}:{1}".format(base_sha, path)],
                               capture_output=True, text=True)
        contents[path] = shown.stdout if shown.returncode == 0 else None
    return contents


def contract_widened(diff_paths, diff_text, file_contents=None, base_contents=None):
    """research.md D6. `file_contents`: optional {path: new-side full text}
    -- when omitted, this function cannot determine protected line ranges
    for a path and treats it conservatively (not widened for that path
    alone; callers that need path content read it from the checkout they
    already have, e.g. board-loop.yml's route job on disk).
    `base_contents`: optional {path: base-side full text, or None when the
    base has no such file}. A path present in it is decided by
    contract_changed() instead -- the base and new contract blocks
    compared whole -- which also sees a contract REMOVED (a dropped
    `workflow_call:`, a deleted composite or inputs/outputs block) that the
    new side alone cannot show.

    Returns the subset of diff_paths that are contract-widening."""
    file_contents = file_contents or {}
    widened = []
    for path in diff_paths:
        if not (_is_workflow_path(path) or _is_wc_composite_action_path(path)):
            continue
        if base_contents is not None and path in base_contents:
            if contract_changed(path, base_contents[path], file_contents.get(path)):
                widened.append(path)
            continue
        text = file_contents.get(path)
        if text is None:
            continue
        protected = (_protected_range_workflow(text) if _is_workflow_path(path)
                     else _protected_range_composite(text))
        if protected is None:
            continue
        p_start, p_end = protected
        touched_ranges = _new_line_ranges_for_file(diff_text, path)
        for t_start, t_end in touched_ranges:
            if t_start < p_end and p_start < t_end:
                widened.append(path)
                break
    return widened


PROPOSAL_CATEGORIES = ("fix", "spec")


def normalize_category(category):
    """The one home for reading route-propose's `category` (#548): "fix"
    or "spec" after stripping whitespace and lowercasing, so "SPEC",
    " spec " and "Fix" count as the agent's proposal; None for anything
    else (a typo, a non-string, null). board-loop.yml's extract step
    counts a proposal as extracted exactly when this is not None, and
    route() treats None as no usable proposal -- spec, the safe
    direction -- so the two can never disagree."""
    if not isinstance(category, str):
        return None
    category = category.strip().lower()
    return category if category in PROPOSAL_CATEGORIES else None


def route(agent_proposal, file_changes, board_max_files, board_max_lines,
          measure_backstop, diff_paths=None, diff_text=None, file_contents=None,
          widened_paths_override=None, proposal_extracted=True,
          workflow_push_blocked=None, base_contents=None,
          agent_rate_limited=False, contract_unknown_paths=None):
    """FR-016..FR-020. `measure_backstop` is a callable
    (file_changes, max_files, max_lines) -> (over_threshold, files, lines)
    -- the runtime caller (board-loop.yml) supplies one that shells out to
    wing-commander-size-path-backstop; the gate supplies a pure fixture
    stand-in. Narrows agent_proposal ("fix" -> "spec") only, never widens
    ("spec" stays "spec", FR-017). `widened_paths_override`, when not None,
    is used instead of calling contract_widened() internally -- the
    pre-push route job passes drafted_contract_widened()'s result here
    (the drafted diff's hunks located against main's file content), and
    route_final_diff() runs the precise check on the pushed diff.
    `workflow_push_blocked` (workflow_push_blocked_paths()'s result) turns
    an otherwise-fix verdict into "hold", reason "workflow_scope": the fix
    is fix-shaped but this loop cannot push it, so it waits for a
    maintainer as the one issue it already is -- never a spec, which is for
    design trade-offs, not push permissions.
    `proposal_extracted` is False when the caller had no usable proposal
    from the agent and fell back to a default `spec` -- that spec is then
    reported as `no_usable_proposal`, never as the agent's own judgment
    (#534). `agent_proposal` is read through normalize_category(); a
    value outside fix/spec is no usable proposal whatever
    `proposal_extracted` says, so it is spec, never fix (#548). The
    decision records the normalised value.
    `agent_rate_limited` is True when the route agent's own verdict was
    rate-limited (an API 429). No usable proposal from a rate-limited agent
    is "defer", reason "agent_rate_limited", never the default spec: the
    agent judged nothing, and filing a spec-proposal closed the original
    as a duplicate during a usage outage (#902 -> #907, #906 -> #908).
    Defer takes no durable action. The issue's route marker (triage writes
    it before route runs) keeps it in flight, and the next run triages it
    again -- a rate-limited triage then defers too and posts nothing
    (board_triage.defer_on_rate_limit()) -- and routes it once the usage
    window resets.
    `contract_unknown_paths` (drafted_contract_widened()'s `unknown`): on a
    hold, the held paths among them are recorded as
    `measured.contract_unknown_paths`, because a held fix is never pushed
    and so never reaches route_final_diff()'s contract check."""
    category = normalize_category(agent_proposal)
    if category is None:
        agent_proposal, proposal_extracted = "spec", False
    else:
        agent_proposal = category
    over_threshold, files, lines = measure_backstop(file_changes, board_max_files, board_max_lines)
    if widened_paths_override is not None:
        widened_paths = widened_paths_override
    else:
        widened_paths = contract_widened(diff_paths or [], diff_text or "", file_contents,
                                         base_contents)

    if agent_proposal == "spec":
        backstop_verdict = "spec"
        # #534: when no backstop condition fired, the spec verdict is the
        # agent's own judgment -- say so, rather than "under_threshold",
        # which read as a size backstop firing on an item measured at zero.
        # A default spec the caller fell back to (no usable proposal) is
        # not the agent's judgment either, and says so. A backstop
        # condition that also fired keeps its own reason.
        if widened_paths:
            reason = "contract_widening"
        elif over_threshold:
            reason = "over_threshold"
        elif proposal_extracted:
            reason = "agent_proposed_spec"
        elif agent_rate_limited:
            backstop_verdict = "defer"
            reason = "agent_rate_limited"
        else:
            reason = "no_usable_proposal"
    elif widened_paths:
        backstop_verdict = "spec"
        reason = "contract_widening"
    elif over_threshold:
        backstop_verdict = "spec"
        reason = "over_threshold"
    elif workflow_push_blocked:
        backstop_verdict = "hold"
        reason = "workflow_scope"
    else:
        backstop_verdict = "fix"
        reason = "under_threshold"

    measured = {"files": files, "lines": lines}
    if reason == "contract_widening":
        measured["contract_touched_paths"] = widened_paths
    if reason == "workflow_scope":
        measured["workflow_paths"] = list(workflow_push_blocked)
        unchecked = [p for p in contract_unknown_paths or [] if p in measured["workflow_paths"]]
        if unchecked:
            measured["contract_unknown_paths"] = unchecked

    return {
        "agent_proposal": agent_proposal,
        "backstop_verdict": backstop_verdict,
        "reason": reason,
        "measured": measured,
    }


RATIONALE_MAX_CHARS = 200


def one_line_rationale(proposal, limit=RATIONALE_MAX_CHARS):
    """#534: the route-propose agent's own one-line rationale for its
    proposal (its `reasoning` field, or `rationale`), made safe to render
    inside a code span in an issue comment or spec-request footer -- or ""
    when it gave none. The text is agent-authored DATA: whitespace is
    collapsed to one line, backticks become `'` so it cannot close the
    code span it is rendered in, and HTML comment delimiters are removed
    so it can never forge or break the board item marker, whose structure
    only code renders (write_marker). `*` becomes `\u2217` so no
    `**Run:**` line can form (board_stop_check reads the last
    MARKER_RUN_RE match, and the route comment puts this line after the
    marker), and every Unicode format (Cf) character -- bidi overrides,
    zero-width joiners/spaces -- is dropped."""
    if not isinstance(proposal, dict):
        return ""
    text = proposal.get("reasoning")
    if not isinstance(text, str) or not text.strip():
        text = proposal.get("rationale")
    if not isinstance(text, str):
        return ""
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = " ".join(text.split())
    text = text.replace("`", "'").replace("*", "\u2217")
    while "<!--" in text or "-->" in text:
        text = text.replace("<!--", "").replace("-->", "")
    text = text.strip()
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + "..."
    return text


def route_final_diff(route_decision, final_diff, board_max_files, board_max_lines,
                      measure_backstop, diff_paths=None, diff_text=None, file_contents=None,
                      base_contents=None):
    """FR-021/FR-018: re-applies route() to the pushed branch's final diff.
    A newly introduced breach is reported (never merges/deletes anything --
    the caller in board-loop.yml owns leaving the branch/PR open under a
    notice and filing the spun-off spec proposal). `base_contents` (see
    contract_widened()) lets the check see a contract removed, not only
    one added."""
    re_evaluated = route(route_decision.get("agent_proposal", "fix"), final_diff,
                          board_max_files, board_max_lines, measure_backstop,
                          diff_paths=diff_paths, diff_text=diff_text, file_contents=file_contents,
                          base_contents=base_contents)
    if re_evaluated["backstop_verdict"] == "spec" and route_decision.get("backstop_verdict") != "spec":
        re_evaluated["reason"] = "post_push_final_diff_breach"
    return re_evaluated


def main():
    """No runtime entry point of its own -- board-loop.yml's route job
    calls route()/route_final_diff() via a small inline Python snippet that
    supplies measure_backstop() (shelling out to the composite) and the
    checkout's own file contents. This stub exists only so the module is
    importable and lints cleanly as a script."""
    sys.exit(0)


if __name__ == "__main__":
    main()
