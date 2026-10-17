#!/usr/bin/env bash
# .github/actions/_shared/render-remaining-work.sh
#
# The one home of the remaining-work report (specs/117 D7): finalize used to
# ask its summarising agent to copy every unchecked tasks.md line into
# finalize-remaining.md, which listed unbuilt code and owner-only steps
# together (and standing instructions as if they were work). The two item
# lists now come from count-tasks-checkboxes.sh's `maintainer-items` and
# `impl-unchecked-items` outputs and are rendered here, deterministically.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/render-remaining-work.sh" \
#     <maintainer-items-file> <impl-items-file> [<routed-items-file>]
# Writes markdown on stdout: `## Maintainer steps` when the first list is
# non-empty, `## Unfinished implementation` (with a stall statement) when the
# second is; nothing at all when both are empty. The optional third file is
# the write-boundary lookup's `rendered` text (`- <line> — routed, see <url>`):
# an item whose literal line matches one of those is written as that routed
# line instead, so a routed item still points at its tracked issue.
set -uo pipefail

MAINT_FILE="${1:-}"
IMPL_FILE="${2:-}"
ROUTED_FILE="${3:-}"

if [ -z "$MAINT_FILE" ] || [ -z "$IMPL_FILE" ]; then
  echo "render-remaining-work.sh: usage: render-remaining-work.sh <maintainer-items-file> <impl-items-file> [<routed-items-file>]" >&2
  exit 1
fi

routed=()
if [ -n "$ROUTED_FILE" ] && [ -f "$ROUTED_FILE" ]; then
  while IFS= read -r r; do
    [ -n "${r//[[:space:]]/}" ] && routed+=("$r")
  done < "$ROUTED_FILE"
fi

# items <file>: the non-blank lines, each swapped for its routed rendering
# when the lookup matched it.
#   items <file> keep   -> only the lines the lookup did not route
#   items <file> routed -> only the routed lines (rendered)
# A routed item is out-of-boundary work the implement stage cannot do, so it
# is reported with the owner's steps and never counts as stalled implementation.
items() {
  local line r hit
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "${line//[[:space:]]/}" ] || continue
    hit=0
    for r in "${routed[@]+"${routed[@]}"}"; do
      if [[ "$r" == "- $line — routed, see "* ]]; then
        # The routed text is "- <line> — routed...": the line already
        # carries its own bullet, so drop the lookup's to avoid "- - [ ]".
        line="${r#- }"
        hit=1
        break
      fi
    done
    case "$2" in
      all) printf '%s\n' "$line" ;;
      keep) [ "$hit" -eq 1 ] || printf '%s\n' "$line" ;;
      routed) [ "$hit" -ne 1 ] || printf '%s\n' "$line" ;;
    esac
  done < "$1"
}

maint="$(items "$MAINT_FILE" all)"
routed_impl="$(items "$IMPL_FILE" routed)"
impl="$(items "$IMPL_FILE" keep)"
if [ -n "$routed_impl" ]; then
  maint="${maint:+$maint$'\n'}$routed_impl"
fi
# The number of genuinely unbuilt tasks: the one source the caller reads.
if [ -n "${RENDER_IMPL_COUNT_FILE:-}" ]; then
  if [ -n "$impl" ]; then
    printf '%s\n' "$impl" | wc -l | tr -d ' ' > "$RENDER_IMPL_COUNT_FILE"
  else
    echo 0 > "$RENDER_IMPL_COUNT_FILE"
  fi
fi

sep=""
if [ -n "$maint" ]; then
  printf '## Maintainer steps\n\n%s\n' "$maint"
  sep=$'\n'
fi
if [ -n "$impl" ]; then
  n="$(printf '%s\n' "$impl" | wc -l | tr -d ' ')"
  printf '%s## Unfinished implementation\n\n' "$sep"
  printf 'The lifecycle stalled with implementation outstanding: %s task(s) were never built. They need another implement run, not a review.\n\n' "$n"
  printf '%s\n' "$impl"
fi
