#!/usr/bin/env bash
# .github/actions/_shared/open-clarification-marker.sh
#
# The one home of the colon-form marker scan that intake.yml's and
# clarify.yml's readiness cross-check runs against a spec.md (FR-004–FR-008).
# Before #1099 each workflow carried its own `grep -q '\[NEEDS
# CLARIFICATION:'`; a spec that DESCRIBES the marker (spec 122) quotes it in
# code, and the bare grep read that quotation as an open question and vetoed
# a spec that had none.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/open-clarification-marker.sh" <spec.md>
# from a composite only; wing-commander-clarification-marker is the front
# door the published stages use (Gate 60).
# -- `bash file`, never the file itself (count-tasks-checkboxes.sh: same
# reason). Exit 0: an open marker is present. Exit 1: none. Any other exit
# (2: the file could not be read; awk missing or failing) is no answer, and
# the composite fails its step on it rather than read it as "none".
#
# What counts as code, and why each rule leans toward FINDING a marker:
# a false "no marker" lets "Review the spec PR" be announced over an open
# question, the dangerous direction; a false "marker" is #1099's false veto,
# which is loud and recoverable.
#   - Fenced blocks open on ``` or ~~~ (any leading whitespace, so fences
#     nested in list items count) and close only on a run of the SAME
#     character at least as long (CommonMark), so a ````markdown block
#     quoting a ``` fence stays one block. A ``` line whose info string
#     holds a backtick is not a fence (CommonMark): ```x``` on one line is
#     inline code, not a range opener.
#   - A fence never closed is not treated as code: its lines are scanned as
#     prose, so a missing closing fence cannot hide every marker below it.
#   - An inline span is a backtick run closed by a run of exactly the same
#     length on the same line (so ``a ` b`` is one span); an unmatched run
#     is literal text, so one stray backtick cannot swallow a marker.
set -uo pipefail

SPEC="${1:-}"
if [ -z "$SPEC" ] || [ ! -r "$SPEC" ]; then
  echo "open-clarification-marker.sh: cannot read '${SPEC}'" >&2
  exit 2
fi

awk '
function strip_spans(s,    out, i, n, rest, t, pos, j, m, found) {
  out = ""
  while ((i = index(s, "`")) > 0) {
    out = out substr(s, 1, i - 1)
    s = substr(s, i)
    n = 0
    while (substr(s, n + 1, 1) == "`") n++
    rest = substr(s, n + 1)
    found = 0; pos = 0; t = rest
    while ((j = index(t, "`")) > 0) {
      m = 0
      while (substr(t, j + m, 1) == "`") m++
      if (m == n) { found = pos + j; break }
      pos += j + m - 1
      t = substr(t, j + m)
    }
    if (found) { s = substr(rest, found + n) }
    else { out = out substr(s, 1, n); s = rest }
  }
  return out s
}
function prose(line) {
  if (index(strip_spans(line), "[NEEDS CLARIFICATION:") > 0) hit = 1
}
{
  line = $0
  if (!infence) {
    if (match(line, /^[ \t]*(```+|~~~+)/)) {
      fence = substr(line, RSTART, RLENGTH)
      sub(/^[ \t]*/, "", fence)
      ch = substr(fence, 1, 1)
      info = substr(line, RSTART + RLENGTH)
      if (!(ch == "`" && index(info, "`") > 0)) {
        infence = 1; flen = length(fence); nbuf = 0
        buf[++nbuf] = line
        next
      }
    }
    prose(line)
    next
  }
  buf[++nbuf] = line
  close_line = line
  sub(/^[ \t]*/, "", close_line)
  run = 0
  while (substr(close_line, run + 1, 1) == ch) run++
  tail = substr(close_line, run + 1)
  if (run >= flen && tail ~ /^[ \t]*$/) infence = 0
}
END {
  if (infence) for (k = 1; k <= nbuf; k++) prose(buf[k])
  exit hit ? 0 : 1
}
' "$SPEC"
