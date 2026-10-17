#!/usr/bin/env bash
# .github/actions/_shared/count-tasks-checkboxes.sh
#
# The one place that counts a tasks.md's checkbox state at a git ref
# (research.md D2/D3). Before this feature, the checked-count comparison
# used to classify a truncated cycle (implement.yml's Arm A) was a bare
# `grep -c '^\s*- \[[xX]\]'` pasted once per arm, and no reader ever counted
# UNCHECKED boxes at all -- the convergence signal instead inferred
# "nothing left" from the absence of a `converge:` commit, which is exactly
# the proxy spec 059 replaces. A third paste of the same idiom to add the
# unchecked count would be the shape CLAUDE.md's "Shared logic has exactly
# one home" forbids, so this script is now the one home both counts (and
# the literal unchecked-item text used for the remaining-work report) come
# from; count-tasks-checkboxes.sh is the only file Gate 99's structural
# check needs to keep in sync.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/count-tasks-checkboxes.sh" <ref> <path>
# -- `bash file`, never the file itself, so its executable bit (which a
# plain checkout does not reliably preserve) is never load-bearing
# (count-turns.sh, read-spec-meta.sh: same reason).
#
# Unlike read-spec-meta.sh, a ref:path this script cannot read is NOT a
# valid state: FR-006/Principle VIII require an unreadable tasks.md to fail
# the calling step loudly rather than report a count of zero, which would
# read as "converged" -- exactly the false pass a scan that cannot reach
# its subject must not produce. So this script exits non-zero with a
# message on stderr, and prints nothing on stdout, when `git show
# "$ref:$path"` fails.
#
# On success, counts task-list checkbox lines with one `awk` pass that
# tracks fenced-code-block state (a fence-opening ``` or ~~~, after
# stripping leading whitespace, toggles an in-fence flag; nothing inside a
# fence is counted -- FR-004's "a naive line match would count prose as an
# outstanding task and hold a finished spec in the loop forever"). Emits,
# on stdout, `key=value`/heredoc lines already shaped as the calling
# composite's own outputs (contracts/convergence-signal.md §1), so the
# composite step can append this script's stdout straight to
# $GITHUB_OUTPUT with no reshaping:
#   checked-count=<n>            count of ^\s*- \[[xX]\] lines outside a fence
#   unchecked-count=<n>          count of ^\s*- \[ \] lines outside a fence
#   unchecked-items<<WING_COMMANDER_UNCHECKED_ITEMS_EOF
#   <literal text of every counted unchecked line, in file order>
#   WING_COMMANDER_UNCHECKED_ITEMS_EOF
# -- the same heredoc-style marker convention implement.yml's read-back
# steps already use for their own multi-line `remaining` output
# (implement.yml's "Read back cycle outcome", `remaining<<WING_COMMANDER_
# REMAINING_EOF`).
set -uo pipefail

REF="${1:-}"
TASKS_PATH="${2:-}"

if [ -z "$REF" ] || [ -z "$TASKS_PATH" ]; then
  echo "count-tasks-checkboxes.sh: usage: count-tasks-checkboxes.sh <ref> <path>" >&2
  exit 1
fi

content="$(git show "${REF}:${TASKS_PATH}" 2>&1)"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "count-tasks-checkboxes.sh: could not read '${TASKS_PATH}' at ref '${REF}': $content" >&2
  exit 1
fi

counts="$(printf '%s\n' "$content" | awk '
  # Line classes, first match wins (specs/117 data-model.md): standing
  # instruction, then maintainer task, then implementation task.
  function is_standing(line,    t) {
    t = tolower(line)
    sub(/^[ \t]*- \[[ xX]\][ \t]*/, "", t)
    sub(/^[tm][0-9]+[ \t]*/, "", t)
    if (t ~ /^complete every remaining/) return 1
    if (t ~ /^keep the gates green/) return 1
    if (t ~ /^after each cycle/) return 1
    if (t ~ /^run the (full )?gate suite/) {
      # A deliverable noun after it makes it a real task, not a standing line.
      if (t ~ /and fix/ || t ~ /`/ || t ~ /\//) return 0
      return 1
    }
    return 0
  }
  function is_maintainer(line,    t) {
    t = line
    sub(/^[ \t]*- \[[ xX]\]/, "", t)
    t = substr(t, 1, 40)
    return index(t, " [maintainer] ") > 0
  }
  {
    stripped = $0
    sub(/^[ \t]+/, "", stripped)
    if (stripped ~ /^(```|~~~)/) {
      in_fence = !in_fence
      next
    }
    if (in_fence) next
    if ($0 ~ /^[ \t]*- \[[xX ]\]/) {
      is_checked = ($0 ~ /^[ \t]*- \[[xX]\]/)
      if (is_checked) checked++; else { unchecked++; items = items $0 "\n" }
      if (is_standing($0)) {
        standing++
      } else if (is_maintainer($0)) {
        if (!is_checked) maint = maint $0 "\n"
      } else if (is_checked) {
        impl_checked++
      } else {
        impl_unchecked++
        impl_items = impl_items $0 "\n"
      }
    }
  }
  END {
    printf "%d\x1f%d\x1f%d\x1f%d\x1f%d\x1f%s\x1f%s\x1f%s", checked+0, unchecked+0, impl_checked+0, impl_unchecked+0, standing+0, items, impl_items, maint
  }
')"

checked_count="${counts%%$'\x1f'*}";         counts="${counts#*$'\x1f'}"
unchecked_count="${counts%%$'\x1f'*}";       counts="${counts#*$'\x1f'}"
impl_checked_count="${counts%%$'\x1f'*}";    counts="${counts#*$'\x1f'}"
impl_unchecked_count="${counts%%$'\x1f'*}";  counts="${counts#*$'\x1f'}"
standing_count="${counts%%$'\x1f'*}";        counts="${counts#*$'\x1f'}"
unchecked_items="${counts%%$'\x1f'*}";       counts="${counts#*$'\x1f'}"
impl_items="${counts%%$'\x1f'*}";            maint_items="${counts#*$'\x1f'}"
# Mid-record items keep their trailing newline (only the last field's is
# stripped by the command substitution); drop it so each heredoc below ends
# with exactly one.
unchecked_items="${unchecked_items%$'\n'}"
impl_items="${impl_items%$'\n'}"
maint_items="${maint_items%$'\n'}"

printf 'checked-count=%s\n' "$checked_count"
printf 'unchecked-count=%s\n' "$unchecked_count"
printf 'unchecked-items<<WING_COMMANDER_UNCHECKED_ITEMS_EOF\n'
# "$(...)" above strips the items' trailing newline, so the last item must
# get its newline back here -- without it the closing delimiter lands on the
# same line as that item and $GITHUB_OUTPUT rejects the whole block
# ("Matching delimiter not found"), failing every cycle that still has an
# unchecked task.
[ -z "$unchecked_items" ] || printf '%s\n' "$unchecked_items"
printf 'WING_COMMANDER_UNCHECKED_ITEMS_EOF\n'
# Classified view (specs/117 data-model.md): standing instructions are in
# neither impl-* count; [maintainer] tasks are listed but never counted.
printf 'impl-checked-count=%s\n' "$impl_checked_count"
printf 'impl-unchecked-count=%s\n' "$impl_unchecked_count"
printf 'standing-count=%s\n' "$standing_count"
printf 'impl-unchecked-items<<WING_COMMANDER_IMPL_ITEMS_EOF\n'
[ -z "$impl_items" ] || printf '%s\n' "$impl_items"
printf 'WING_COMMANDER_IMPL_ITEMS_EOF\n'
printf 'maintainer-items<<WING_COMMANDER_MAINTAINER_ITEMS_EOF\n'
[ -z "$maint_items" ] || printf '%s\n' "$maint_items"
printf 'WING_COMMANDER_MAINTAINER_ITEMS_EOF\n'
