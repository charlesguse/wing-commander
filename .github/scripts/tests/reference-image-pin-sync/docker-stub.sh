#!/usr/bin/env bash
# Stubbed `docker` for verify-reference-image-pin-sync.py's dogfood copy
# cases. The harness copies it to <tmp>/bin/docker and points STUB_DIR at a
# per-case directory:
#   login_fail    present: `login` fails
#   login_stdin   written: what `login --password-stdin` read
#   held          the digest the target resolves to (absent: inspect fails
#                 "not found")
#   inspect_fail  present: `imagetools inspect` fails, printing its content
#                 to stderr (a denied read, a registry error)
#   create_fail   present: `imagetools create` fails, printing its content
#                 to stderr
#   after         the digest the target resolves to after a create
#                 (absent: the source's digest)
#   readback_fail present: a create leaves the target unreadable
#   log           every invocation, one line each, appended here
set -u
echo "docker $*" >> "${STUB_DIR}/log"

# Docker refuses a repository path that is not lower case (the tag may be).
refuse_upper() { # ref
  local name="${1%%[:@]*}"
  [ "${1#ghcr.io/}" != "$1" ] && name="ghcr.io/$(printf '%s' "${1#ghcr.io/}" | sed 's/[:@].*//')"
  if [ "$name" != "${name,,}" ]; then
    echo "ERROR: invalid reference format: repository name (${name}) must be lowercase" >&2
    exit 1
  fi
}

case "${1:-} ${2:-} ${3:-}" in
  "login "*)
    cat > "${STUB_DIR}/login_stdin"
    if [ -f "${STUB_DIR}/login_fail" ]; then
      echo "Error response from daemon: unauthorized" >&2
      exit 1
    fi
    echo "Login Succeeded"
    ;;
  "logout "*)
    ;;
  "buildx imagetools inspect")
    refuse_upper "${4:-}"
    if [ -f "${STUB_DIR}/inspect_fail" ]; then
      cat "${STUB_DIR}/inspect_fail" >&2
      exit 1
    fi
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
    refuse_upper "${5:-}"
    src="${!#}"
    if [ -f "${STUB_DIR}/readback_fail" ]; then
      rm -f "${STUB_DIR}/held"
      exit 0
    fi
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
