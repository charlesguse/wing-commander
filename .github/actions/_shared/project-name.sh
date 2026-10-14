#!/usr/bin/env bash
# .github/actions/_shared/project-name.sh
#
# The one home for subfolder-project logic (spec 114): the project-path
# grammar, the name parser in both directions, the label-budget arithmetic,
# per-project feature numbering and routing-prefix validation. Workflows
# reach it only through the wing-commander-project composite; contract:
# specs/114-subfolder-project-lifecycles/contracts/project-path-and-names.md.
#
# Invoke with `bash project-name.sh <subcommand> [args]` -- never the file
# itself, so its executable bit is never load-bearing (read-spec-meta.sh,
# same reason). Prints `key=value` lines on stdout; reasons go to stderr.
#
#   validate-path <P>       grammar only            -> project=<P>
#   check-folder <P>        filesystem rules        -> (nothing)
#   parse <kind> <name>     kind: branch|label|slug|spec-dir
#                                                   -> project=<P> slug=<NNN-slug>
#   names <kind> <name>     parse, plus qualified=<P/NNN-slug>
#                           spec_dir=<P/specs/NNN-slug> spec_dir_rel=<specs/NNN-slug>
#   spec-dir <P> <NNN-slug>                         -> P/specs/<NNN-slug>
#   slug-budget <P>                                 -> integer (44 - len(P))
#   next-number <P>         env SPEC_DRAFT_PREFIX, SPEC_PREFIX
#                                                   -> zero-padded number
#   validate-prefix <pfx>                           -> (nothing)
#
# `parse branch` strips the first matching flat prefix from SPEC_DRAFT_PREFIX,
# SPEC_PREFIX, IMPL_PREFIX and, when set, PLAN_PREFIX and TASKS_PREFIX
# (longest first), then -- for an implement
# branch only -- a trailing -iterN.
# The empty project (root) is written as an empty `project=`.
set -uo pipefail

MAX_PATH_LEN=28
LABEL_BUDGET_BASE=44

fail() { echo "project-name: $*" >&2; exit 1; }

validate_path() {
  local p="$1" seg
  [ -n "$p" ] || fail "empty project path"
  case "$p" in /*) fail "absolute path '$p'" ;; esac
  [ "${#p}" -le "$MAX_PATH_LEN" ] || fail "'$p' is longer than $MAX_PATH_LEN characters"
  printf '%s' "$p" | grep -Eq '^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*$' \
    || fail "'$p' is not lowercase [a-z0-9-] segments separated by single '/'"
  local IFS=/
  for seg in $p; do
    [ "$seg" != "specs" ] || fail "'$p' has a segment named 'specs'"
    printf '%s' "$seg" | grep -Eq '^[0-9]{3}-' && fail "'$p' has a segment shaped like a feature number ('$seg')"
  done
  return 0
}

check_folder() {
  local p="$1" acc="" seg entry
  validate_path "$p" || exit 1
  local IFS=/
  for seg in $p; do
    acc="${acc:+$acc/}$seg"
    [ ! -L "$acc" ] || fail "project folder '$p': '$acc' is a symlink"
    [ -d "$acc" ] || fail "project folder '$p' is not a directory on this ref"
  done
  unset IFS
  # Every piece of Spec Kit state an agent reads or runs must be real: a
  # symlink could point it at another project's (or nobody's) files.
  for entry in .specify .specify/memory .specify/scripts .claude .claude/skills specs; do
    if [ -L "$p/$entry" ]; then fail "project folder '$p': '$entry' is a symlink"; fi
  done
  [ -d "$p/.specify" ] || fail "project folder '$p' has no .specify/ (not a Spec Kit project)"
  [ -d "$p/.claude" ] || fail "project folder '$p' has no .claude/"
  if [ ! -f "$p/.specify/memory/constitution.md" ] || [ -L "$p/.specify/memory/constitution.md" ]; then
    fail "project folder '$p' has no real .specify/memory/constitution.md"
  fi
  local found=0 d
  for d in "$p"/.claude/skills/speckit-*; do
    [ -e "$d" ] || continue
    [ ! -L "$d" ] || fail "project folder '$p': '${d#"$p"/}' is a symlink"
    [ ! -L "$d/SKILL.md" ] || fail "project folder '$p': '${d#"$p"/}/SKILL.md' is a symlink"
    found=1
  done
  [ "$found" = 1 ] || fail "project folder '$p' has no .claude/skills/speckit-* skills"
  return 0
}

strip_prefix() { # strip longest matching non-empty prefix from $1 among the rest
  local name="$1" best="" pfx
  shift
  for pfx in "$@"; do
    [ -n "$pfx" ] || continue
    case "$name" in
      "$pfx"*) [ "${#pfx}" -gt "${#best}" ] && best="$pfx" ;;
    esac
  done
  if [ -n "$best" ]; then printf '%s' "${name#"$best"}"; return 0; fi
  if [ "$#" -gt 0 ] && [ -n "${*//[[:space:]]/}" ]; then return 1; fi
  printf '%s' "$name"
}

parse() {
  local kind="$1" name="$2" rest
  case "$kind" in
    branch)
      rest=$(strip_prefix "$name" "${SPEC_DRAFT_PREFIX:-}" "${SPEC_PREFIX:-}" "${IMPL_PREFIX:-}" \
               "${PLAN_PREFIX:-}" "${TASKS_PREFIX:-}") \
        || fail "branch '$name' carries none of the configured prefixes"
      # -iterN belongs to implement branches only: a spec or spec-draft
      # slug that happens to end in it keeps it. The branch is an implement
      # branch when the prefix actually stripped (the longest match) is
      # IMPL_PREFIX; with overlapping prefixes (`wc/` and `wc/spec/`) the
      # longer one wins, and a prefix IMPL_PREFIX shares with another stage
      # reads as implement.
      if [ -n "${IMPL_PREFIX:-}" ] && [ "${name%"$rest"}" = "$IMPL_PREFIX" ]; then
        rest=$(printf '%s' "$rest" | sed -E 's/-iter[0-9]+$//')
      fi
      ;;
    label)
      case "$name" in spec:*) rest="${name#spec:}" ;; *) fail "label '$name' does not start with 'spec:'" ;; esac
      ;;
    slug) rest="$name" ;;
    spec-dir)
      local tail
      case "$name" in
        specs/*) tail="${name#specs/}"; rest="$tail" ;;
        */specs/*) tail="${name##*/specs/}"; rest="${name%/specs/*}/$tail" ;;
        *) fail "spec-dir '$name' is not [P/]specs/<NNN-slug>" ;;
      esac
      case "$tail" in */*) fail "spec-dir '$name' has extra segments" ;; esac
      ;;
    *) fail "unknown kind '$kind'" ;;
  esac
  local slug="${rest##*/}" proj=""
  # A leading '/' (or '//') would leave an empty project, which is the
  # root: refuse it rather than fall back.
  case "$rest" in
    /*) fail "'$name' has an empty project path before '${rest#/}'" ;;
    */*) proj="${rest%/*}" ;;
  esac
  printf '%s' "$slug" | grep -Eq '^[0-9]{3}-[a-z0-9-]+$' || fail "'$name' does not end in <NNN-slug>"
  if [ -n "$proj" ]; then validate_path "$proj" || exit 1; fi
  echo "project=$proj"
  echo "slug=$slug"
}

# names <kind> <name>: parse, then every name the lifecycle derives from
# (P, NNN-slug), so a caller never rebuilds one by splitting a path itself.
names() {
  local out p s
  out="$(parse "$1" "$2")" || exit 1
  p="$(printf '%s\n' "$out" | sed -n 's/^project=//p')"
  s="$(printf '%s\n' "$out" | sed -n 's/^slug=//p')"
  echo "project=$p"
  echo "slug=$s"
  echo "qualified=${p:+$p/}$s"
  echo "spec_dir=${p:+$p/}specs/$s"
  echo "spec_dir_rel=specs/$s"
}

next_number() {
  local p="$1" highest dp="${SPEC_DRAFT_PREFIX:-}" sp="${SPEC_PREFIX:-}" base="specs" ref rem
  [ -z "$p" ] || { validate_path "$p" || exit 1; base="$p/specs"; }
  highest=$(
    {
      ls -d "$base"/[0-9][0-9][0-9]-* 2>/dev/null | sed "s|^$base/||"
      git ls-remote --heads origin "refs/heads/$dp*" "refs/heads/$sp*" 2>/dev/null \
        | sed -E 's|^[0-9a-f]+[[:space:]]+refs/heads/||' \
        | while IFS= read -r ref; do
            rem=""
            case "$ref" in
              "$dp"*) [ -n "$dp" ] && rem="${ref#"$dp"}" ;;
            esac
            if [ -z "$rem" ]; then
              case "$ref" in "$sp"*) [ -n "$sp" ] && rem="${ref#"$sp"}" ;; esac
            fi
            [ -n "$rem" ] || continue
            if [ -z "$p" ]; then
              case "$rem" in */*) continue ;; esac
              printf '%s\n' "$rem"
            else
              case "$rem" in
                "$p"/*) rem="${rem#"$p"/}"; case "$rem" in */*) continue ;; esac; printf '%s\n' "$rem" ;;
              esac
            fi
          done
    } | grep -oE '^[0-9]{3}' | sort -n | tail -1
  )
  printf '%03d\n' $(( 10#${highest:-000} + 1 ))
}

validate_prefix() {
  local pfx="$1" bare fam
  printf '%s' "$pfx" | grep -Eq '^[a-z0-9][a-z0-9-]*:$' || fail "routing prefix '$pfx' must match ^[a-z0-9][a-z0-9-]*:\$"
  [ $(( ${#pfx} + MAX_PATH_LEN )) -le 50 ] || fail "routing prefix '$pfx' is too long (len + $MAX_PATH_LEN must be <= 50)"
  bare="${pfx%:}"
  # `route` stands for the whole write-boundary routing label family without
  # spelling its label (write-boundary gate (m): that default has one home,
  # implement.yml).
  for fam in spec stage model board disposition findings route spec-request spec-proposal ${FINDINGS_LABEL_PREFIX:+"${FINDINGS_LABEL_PREFIX%:}"}; do
    if [ "$bare" = "$fam" ] || [ "${fam#"$bare"}" != "$fam" ] || [ "${bare#"$fam"}" != "$bare" ]; then
      fail "routing prefix '$pfx' overlaps the '$fam' label family"
    fi
  done
  return 0
}

cmd="${1:-}"
[ "$#" -gt 0 ] && shift
case "$cmd" in
  validate-path) [ "$#" -eq 1 ] || fail "usage: validate-path <P>"; validate_path "$1" && echo "project=$1" ;;
  check-folder) [ "$#" -eq 1 ] || fail "usage: check-folder <P>"; check_folder "$1" ;;
  parse) [ "$#" -eq 2 ] || fail "usage: parse <kind> <name>"; parse "$1" "$2" ;;
  names) [ "$#" -eq 2 ] || fail "usage: names <kind> <name>"; names "$1" "$2" ;;
  spec-dir) [ "$#" -eq 2 ] || fail "usage: spec-dir <P> <NNN-slug>"; echo "${1:+$1/}specs/$2" ;;
  slug-budget) [ "$#" -eq 1 ] || fail "usage: slug-budget <P>"; echo $(( LABEL_BUDGET_BASE - ${#1} )) ;;
  next-number) [ "$#" -eq 1 ] || fail "usage: next-number <P>"; next_number "$1" ;;
  validate-prefix) [ "$#" -eq 1 ] || fail "usage: validate-prefix <prefix>"; validate_prefix "$1" ;;
  *) fail "unknown subcommand '$cmd'" ;;
esac
