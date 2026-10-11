#!/usr/bin/env bash
# Stubbed `gh` for verify-reference-image-pin-sync.py. The harness copies it
# to <tmp>/bin/gh and points STUB_DIR at a per-case directory:
#   reach           one full_name per line: what `api user/repos` returns
#   runs            one run number per line: what `run list` returns
#   vars/<o>__<r>   the held value of the variable (absent: the read 404s)
#   probe_fail      repositories (one per line) whose variable read fails
#   set_fail        repositories (one per line) whose variable write is refused
#   log             every invocation, one line each, appended here
set -u
echo "GH_TOKEN=${GH_TOKEN:-} $*" >> "${STUB_DIR}/log"

listed() { [ -f "${STUB_DIR}/$1" ] && grep -qxiF -- "$2" "${STUB_DIR}/$1"; }

case "${1:-} ${2:-}" in
  "api user/repos"*)
    [ -f "${STUB_DIR}/reach" ] && cat "${STUB_DIR}/reach"
    exit 0
    ;;
  "api repos/"*)
    repo="${2#repos/}"
    repo="${repo%%/actions/*}"
    listed probe_fail "$repo" && exit 1
    f="${STUB_DIR}/vars/${repo/\//__}"
    [ -f "$f" ] || exit 1
    cat "$f"
    echo
    exit 0
    ;;
  "variable set")
    repo=""
    prev=""
    for a in "$@"; do
      [ "$prev" = "--repo" ] && repo="$a"
      prev="$a"
    done
    if listed set_fail "$repo"; then
      echo "REFUSED ${repo}" >> "${STUB_DIR}/log"
      exit 1
    fi
    exit 0
    ;;
  "run list")
    [ -f "${STUB_DIR}/runs" ] && cat "${STUB_DIR}/runs"
    exit 0
    ;;
esac
echo "gh-stub: unexpected call: $*" >&2
exit 2
