# shellcheck shell=bash
# The one home of how a workspace bundle is read (spec 095,
# contracts/workspace-bundle.md), for both of its consumers: the
# credential-free gate job (contained-gate-suite.sh) and the publisher
# (restore-gate-bundle.sh). Sourced, never executed.
#
# The bundle carries exactly one ref, HEAD (build-gate-bundle.sh); a
# refs/* refspec would match nothing and import no objects.

# wc_is_sha VALUE -- true when VALUE is a 40-hex commit SHA.
wc_is_sha() {
  printf '%s' "$1" | grep -Eq '^[0-9a-f]{40}$'
}

# wc_import_bundle BUNDLE -- verify BUNDLE, fetch its HEAD into
# refs/wc-gate/head, and print that commit's SHA. Returns 2 when the bundle
# fails verification (corrupt, or a prerequisite this repository does not
# hold) and 3 when the fetch fails; the caller says which, in its own terms.
wc_import_bundle() {
  local bundle="$1"
  git bundle verify "$bundle" >/dev/null 2>&1 || return 2
  git fetch --quiet --no-tags "$bundle" "+HEAD:refs/wc-gate/head" 2>/dev/null || return 3
  git rev-parse --verify --quiet refs/wc-gate/head
}
