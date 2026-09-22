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
(`route_final_diff()`, FR-021).

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


def touches_protected_file(diff_paths):
    """Coarse, pre-push proxy for contract_widened() (research.md D6):
    before a fix has been pushed, this job has only the route-propose
    agent's drafted diff snippets, not the new side's full file content
    contract_widened() needs to locate the workflow_call:/inputs:/outputs:
    block precisely -- so the pre-push route step treats ANY touched
    `.github/workflows/*.yml` or `wing-commander-*` composite `action.yml`
    as provisionally contract-widening (never under-protects; may
    over-flag a workflow/composite change that turns out not to touch the
    published surface, which route_final_diff()'s precise post-push check
    corrects once the real diff and file content exist)."""
    return [p for p in diff_paths
            if _is_workflow_path(p) or _is_wc_composite_action_path(p)]


def contract_widened(diff_paths, diff_text, file_contents=None):
    """research.md D6. `file_contents`: optional {path: new-side full text}
    -- when omitted, this function cannot determine protected line ranges
    for a path and treats it conservatively (not widened for that path
    alone; callers that need path content read it from the checkout they
    already have, e.g. board-loop.yml's route job on disk).

    Returns the subset of diff_paths that are contract-widening."""
    file_contents = file_contents or {}
    widened = []
    for path in diff_paths:
        if not (_is_workflow_path(path) or _is_wc_composite_action_path(path)):
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


def route(agent_proposal, file_changes, board_max_files, board_max_lines,
          measure_backstop, diff_paths=None, diff_text=None, file_contents=None,
          widened_paths_override=None):
    """FR-016..FR-020. `measure_backstop` is a callable
    (file_changes, max_files, max_lines) -> (over_threshold, files, lines)
    -- the runtime caller (board-loop.yml) supplies one that shells out to
    wing-commander-size-path-backstop; the gate supplies a pure fixture
    stand-in. Narrows agent_proposal ("fix" -> "spec") only, never widens
    ("spec" stays "spec", FR-017). `widened_paths_override`, when not None,
    is used instead of calling contract_widened() internally -- the
    pre-push route job passes touches_protected_file()'s coarser result
    here (research.md D6's precise check needs the new side's full file
    content, unavailable before a fix has been pushed)."""
    over_threshold, files, lines = measure_backstop(file_changes, board_max_files, board_max_lines)
    if widened_paths_override is not None:
        widened_paths = widened_paths_override
    else:
        widened_paths = contract_widened(diff_paths or [], diff_text or "", file_contents)

    if agent_proposal == "spec":
        backstop_verdict = "spec"
        reason = "under_threshold" if not (over_threshold or widened_paths) else (
            "contract_widening" if widened_paths else "over_threshold")
    elif widened_paths:
        backstop_verdict = "spec"
        reason = "contract_widening"
    elif over_threshold:
        backstop_verdict = "spec"
        reason = "over_threshold"
    else:
        backstop_verdict = "fix"
        reason = "under_threshold"

    measured = {"files": files, "lines": lines}
    if reason == "contract_widening":
        measured["contract_touched_paths"] = widened_paths

    return {
        "agent_proposal": agent_proposal,
        "backstop_verdict": backstop_verdict,
        "reason": reason,
        "measured": measured,
    }


def route_final_diff(route_decision, final_diff, board_max_files, board_max_lines,
                      measure_backstop, diff_paths=None, diff_text=None, file_contents=None):
    """FR-021/FR-018: re-applies route() to the pushed branch's final diff.
    A newly introduced breach is reported (never merges/deletes anything --
    the caller in board-loop.yml owns leaving the branch/PR open under a
    notice and filing the spun-off spec-request)."""
    re_evaluated = route(route_decision.get("agent_proposal", "fix"), final_diff,
                          board_max_files, board_max_lines, measure_backstop,
                          diff_paths=diff_paths, diff_text=diff_text, file_contents=file_contents)
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
