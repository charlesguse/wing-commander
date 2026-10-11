#!/usr/bin/env bash
# Stubbed `gh` for verify-reference-image-pin-sync.py. The harness copies it
# to <tmp>/bin/gh and points STUB_DIR at a per-case directory:
#   reach           one full_name per line: what `api user/repos` returns
#   runs            one "<number> <id> <status> <conclusion>" line per run: what `run list` returns
#   jobs/<id>       "<job name> <conclusion>" lines: what `run view <id>` returns (absent: it fails)
#   vars/<o>__<r>   the held value of the variable (absent: the read 404s)
#   probe_fail      repositories (one per line) whose variable read is refused (403)
#   run_list_fail   present: `run list` fails
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
    if listed probe_fail "$repo"; then
      echo "gh: Resource not accessible by personal access token (HTTP 403)" >&2
      exit 1
    fi
    f="${STUB_DIR}/vars/${repo/\//__}"
    if [ ! -f "$f" ]; then
      echo "gh: Not Found (HTTP 404)" >&2
      exit 1
    fi
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
  "run view")
    f="${STUB_DIR}/jobs/${3:-}"
    [ -f "$f" ] || exit 1
    cat "$f"
    exit 0
    ;;
  "run list")
    [ -f "${STUB_DIR}/run_list_fail" ] && exit 1
    [ -f "${STUB_DIR}/runs" ] && cat "${STUB_DIR}/runs"
    exit 0
    ;;
esac
echo "gh-stub: unexpected call: $*" >&2
exit 2
