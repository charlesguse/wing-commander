#!/usr/bin/env bash
# Stubbed `docker` for verify-reference-image-pin-sync.py's dogfood copy
# cases. The harness copies it to <tmp>/bin/docker and points STUB_DIR at a
# per-case directory:
#   login_fail    present: `login` fails
#   login_stdin   written: what `login --password-stdin` read
#   held          the digest the target resolves to (absent: inspect fails)
#   create_fail   present: `imagetools create` fails, printing its content
#                 to stderr
#   after         the digest the target resolves to after a create
#                 (absent: the source's digest)
#   log           every invocation, one line each, appended here
set -u
echo "docker $*" >> "${STUB_DIR}/log"

case "${1:-} ${2:-} ${3:-}" in
  "login "*)
    cat > "${STUB_DIR}/login_stdin"
    if [ -f "${STUB_DIR}/login_fail" ]; then
      echo "Error response from daemon: unauthorized" >&2
      exit 1
    fi
    echo "Login Succeeded"
    ;;
  "buildx imagetools inspect")
    if [ ! -f "${STUB_DIR}/held" ]; then
      echo "ERROR: ${4:-}: not found" >&2
      exit 1
    fi
    printf '{"mediaType":"application/vnd.oci.image.index.v1+json","digest":"%s","size":1}\n' \
      "$(cat "${STUB_DIR}/held")"
    ;;
  "buildx imagetools create")
    if [ -f "${STUB_DIR}/create_fail" ]; then
      cat "${STUB_DIR}/create_fail" >&2
      exit 1
    fi
    src="${!#}"
    if [ -f "${STUB_DIR}/after" ]; then
      cp "${STUB_DIR}/after" "${STUB_DIR}/held"
    else
      printf '%s' "${src##*@}" > "${STUB_DIR}/held"
    fi
    ;;
  *)
    echo "docker stub: unexpected call: $*" >&2
    exit 2
    ;;
esac
