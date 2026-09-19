#!/usr/bin/env bash
# TargetProfile data (data-model.md). `spec-kit-scratch`'s element list is
# written out once; `auto-release`'s is built BY EXTENDING it in code, so the
# "auto-release is a strict superset of spec-kit-scratch" invariant holds by
# construction rather than by two lists staying in sync by hand.
set -uo pipefail

SPEC_KIT_SCRATCH_ELEMENTS=(repository app_installation scratch_marker)
AUTO_RELEASE_ELEMENTS=(
  "${SPEC_KIT_SCRATCH_ELEMENTS[@]}"
  claude_credential spec_request_label wrapper_set container_image_pin
)

# profile_elements PROFILE -- prints PROFILE's required OnboardingElement
# keys, one per line, in order. Exits non-zero, printing nothing, for an
# unrecognized profile name.
profile_elements() {
  case "$1" in
    spec-kit-scratch) printf '%s\n' "${SPEC_KIT_SCRATCH_ELEMENTS[@]}" ;;
    auto-release)     printf '%s\n' "${AUTO_RELEASE_ELEMENTS[@]}" ;;
    *)
      echo "profiles.sh: unknown profile '$1' (expected auto-release or spec-kit-scratch)" >&2
      return 1
      ;;
  esac
}
