#!/usr/bin/env bash
# One deterministic check function per OnboardingElement (data-model.md),
# plus assemble_report(), which both provision-e2e-target.sh (privileged,
# local) and the generalized auto-update-spec-kit-scratch-preflight.yml
# (read-only, CI) source and call — the single home FR-008/FR-010 require.
#
# Every check function takes (owner, name) and returns 0 for ready, 1 for
# not-ready. Every check makes only read calls (FR-009: never inspects a
# secret's value, only its presence).
set -uo pipefail

SCRATCH_MARKER="Wing Commander E2E scratch target — provisioned by provision-e2e-target.sh, do not use for real work"

WRAPPER_FILES=(
  wing-commander-1-intake.yml
  wing-commander-2-clarify.yml
  wing-commander-3-plan.yml
  wing-commander-4-tasks.yml
  wing-commander-5-implement.yml
  wing-commander-6-finalize.yml
  wing-commander-7-cleanup.yml
  wing-commander-rebase.yml
)

# ---- repository -------------------------------------------------------
check_repository() { # check_repository OWNER NAME
  gh repo view "$1/$2" >/dev/null 2>&1
}
remaining_action_repository() {
  printf 'Repository %s/%s does not exist yet. Run provision-e2e-target.sh --repo %s/%s --profile <profile> (without --check-only) to create it.' "$1" "$2" "$1" "$2"
}

# ---- app_installation (the one DeclaredManualStep, remedy: manual) -----
# GET /repos/{owner}/{repo}/installation is App-JWT-only (REST API
# reference, Apps category): an installation access token OR a
# maintainer's own PAT gets a flat 401/403 regardless of whether the App
# is actually installed, so the call can never report "ready" for either
# caller -- and attempting it from the local path (T043) risks reading a
# credential-rejection error as "not installed" rather than what it is.
# WC_APP_INSTALLATION_KNOWN_READY is the only source of truth this element
# ever trusts: the generalized readiness workflow sets it after
# actions/create-github-app-token has already minted a token scoped to
# this exact target, which only succeeds if the App is installed there.
# The local, privileged path has no equivalent signal, so it always
# reports this element as the outstanding declared manual step;
# convergence is observed by dispatching the readiness check (Story 2)
# after installing the App, not by this script re-verifying it under a
# maintainer's own credential.
check_app_installation() { # check_app_installation OWNER NAME
  [ "${WC_APP_INSTALLATION_KNOWN_READY:-}" = "true" ]
}
remaining_action_app_installation() {
  printf 'Install the wing-commander App on %s/%s: https://github.com/settings/installations -- this cannot be verified with a maintainer'\''s own credential (T043); confirm it by dispatching the readiness check (auto-update-spec-kit-scratch-preflight.yml) once installed.' "$1" "$2"
}

# ---- scratch_marker (research.md D3) -----------------------------------
# has_scratch_marker: true iff the repository's description already carries
# the marker this script writes. Kept separate from check_scratch_marker
# (below) so act_scratch_marker can claim an EMPTY repository immediately,
# rather than only once it is no longer empty (T038/T039) -- "ready" and
# "already marked" are different questions.
has_scratch_marker() { # has_scratch_marker OWNER NAME
  local desc
  desc="$(gh repo view "$1/$2" --json description -q .description 2>/dev/null)" || return 1
  [ "$desc" = "$SCRATCH_MARKER" ]
}
# ready iff the repository does not exist yet (nothing to conflict with),
# has zero commits (isEmpty), or its description already carries the
# marker this script writes on first successful provisioning. On the
# --check-only path (WC_CHECK_ONLY=true) this element is not applicable and
# always reports ready (T044): it exists to gate the MUTATING path against
# adopting a foreign repository (data-model.md D3), a concern that does not
# arise when nothing mutates. Without this exemption, a hand-onboarded,
# pre-053 target with real content and no marker would read as permanently
# not-ready under a read-only check, which is exactly what FR-011 and User
# Story 2's Independent Test rule out. Any other pre-existing, non-empty,
# unmarked repository is not ready on the mutating path. `isEmpty` is used
# rather than `diskUsage == 0` -- GitHub's reported disk usage for a
# freshly pushed, still-tiny repository can itself read 0 for a time, which
# would make a genuinely non-empty repository look claimable.
check_scratch_marker() { # check_scratch_marker OWNER NAME
  local owner="$1" name="$2" json empty
  [ "${WC_CHECK_ONLY:-}" = "true" ] && return 0
  if ! gh repo view "$owner/$name" >/dev/null 2>&1; then
    return 0
  fi
  has_scratch_marker "$owner" "$name" && return 0
  json="$(gh repo view "$owner/$name" --json isEmpty 2>/dev/null)" || return 1
  empty="$(jq -r '.isEmpty // false' <<<"$json")"
  [ "$empty" = "true" ]
}
remaining_action_scratch_marker() {
  local owner="$1" name="$2" desc
  desc="$(gh repo view "$owner/$name" --json description -q .description 2>/dev/null)"
  printf '%s/%s already has commits and its description does not carry the scratch marker, so it cannot be established as a reusable scratch verification target. Found description: %s' "$owner" "$name" "${desc:-<none>}"
}

# gh_permission_denied OUTPUT -- true if a failed gh call's captured output
# looks like the caller's token was rejected for lacking a permission scope
# (e.g. an App installation token with no Secrets/Variables read -- the App
# is documented, and gated, to have Contents/Issues/Pull requests only:
# docs/setup.md), rather than the resource simply not existing.
gh_permission_denied() {
  case "$1" in
    *"HTTP 403"*|*"Resource not accessible by integration"*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---- claude_credential (auto-release only) -----------------------------
check_claude_credential() { # check_claude_credential OWNER NAME
  local out rc
  out="$(gh secret list --repo "$1/$2" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    gh_permission_denied "$out" && CLAUDE_CREDENTIAL_NOT_CHECKABLE=true
    return 1
  fi
  printf '%s\n' "$out" | awk '{print $1}' | grep -qE '^(CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY)$'
}
remaining_action_claude_credential() {
  if [ "${CLAUDE_CREDENTIAL_NOT_CHECKABLE:-}" = "true" ]; then
    printf 'Not checkable with this token: the wing-commander App has no Secrets read permission on %s/%s (docs/setup.md declares Contents, Issues, Pull requests only). Run provision-e2e-target.sh --repo %s/%s --profile auto-release --check-only locally under your own gh authentication to check this element.' "$1" "$2" "$1" "$2"
    return
  fi
  printf 'Export CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in this shell, then re-run provision-e2e-target.sh --repo %s/%s --profile auto-release to write it to %s/%s as a repository secret.' "$1" "$2" "$1" "$2"
}

# ---- spec_request_label (auto-release only) ----------------------------
check_spec_request_label() { # check_spec_request_label OWNER NAME
  # `gh label view` is not a real `gh label` subcommand (gh offers
  # clone/create/delete/edit/list only) -- this call can never pass against
  # the real CLI. Read the label directly through the REST API instead.
  gh api "repos/$1/$2/labels/spec-request" >/dev/null 2>&1
}
remaining_action_spec_request_label() {
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to create the spec-request label on %s/%s.' "$1" "$2" "$1" "$2"
}

# ---- wrapper_set (auto-release only) -----------------------------------
check_wrapper_set() { # check_wrapper_set OWNER NAME
  local owner="$1" name="$2" f
  for f in "${WRAPPER_FILES[@]}"; do
    gh api "repos/$owner/$name/contents/.github/workflows/$f" >/dev/null 2>&1 || return 1
  done
  return 0
}
remaining_action_wrapper_set() {
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to push the eight wing-commander-*.yml wrapper workflows to %s/%s'\''s default branch.' "$1" "$2" "$1" "$2"
}

# ---- container_image_pin (auto-release only) ---------------------------
# "This repository's own pinned value" is read once (research.md D4) so the
# two cannot drift into a second literal. `WC_SOURCE_CONTAINER_IMAGE`, when
# SET (even to an empty string -- FR-017: no pinned image is itself a valid
# pinned value), is trusted as that value -- the generalized readiness-check
# workflow sets it directly from `vars.WING_COMMANDER_CONTAINER_IMAGE`,
# because the token it hands checks.sh is scoped only to the target and
# cannot read this repository's own variables back via the API. Unset
# (the local, maintainer-run path), it is derived live from this checkout's
# own repository.
this_repo_container_image() {
  if [ -n "${WC_SOURCE_CONTAINER_IMAGE+set}" ]; then
    printf '%s' "$WC_SOURCE_CONTAINER_IMAGE"
    return 0
  fi
  local self
  self="${GITHUB_REPOSITORY:-}"
  if [ -z "$self" ]; then
    self="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || return 1
  fi
  gh variable list --repo "$self" --json name,value -q '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value' 2>/dev/null
}
check_container_image_pin() { # check_container_image_pin OWNER NAME
  local owner="$1" name="$2" want got rc err
  want="$(this_repo_container_image)" || return 1
  got="$(gh variable list --repo "$owner/$name" --json name,value -q '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value' 2>/dev/null)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    # Re-run once, capturing stderr alone, purely to classify the failure
    # (T047): folding stderr into $got via `2>&1` on the first attempt let a
    # successful call's incidental stderr noise corrupt the compared value
    # into a false not-ready mismatch, so the value used for the comparison
    # above is always stdout-only.
    err="$(gh variable list --repo "$owner/$name" --json name,value -q '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value' 2>&1 1>/dev/null)"
    gh_permission_denied "$err" && CONTAINER_IMAGE_PIN_NOT_CHECKABLE=true
    return 1
  fi
  [ "$got" = "$want" ]
}
remaining_action_container_image_pin() {
  if [ "${CONTAINER_IMAGE_PIN_NOT_CHECKABLE:-}" = "true" ]; then
    printf 'Not checkable with this token: the wing-commander App has no Variables read permission on %s/%s (docs/setup.md declares Contents, Issues, Pull requests only). Run provision-e2e-target.sh --repo %s/%s --profile auto-release --check-only locally under your own gh authentication to check this element.' "$1" "$2" "$1" "$2"
    return
  fi
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to set WING_COMMANDER_CONTAINER_IMAGE on %s/%s to match this repository'\''s own pinned value.' "$1" "$2" "$1" "$2"
}

# ---- ReadinessReport assembly (data-model.md, contracts/readiness-report.schema.json) --
assemble_report() { # assemble_report OWNER NAME PROFILE
  local owner="$1" name="$2" profile="$3" key ready action entry
  local elements_json="[]" all_ready=true
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    if "check_$key" "$owner" "$name"; then
      ready=true; action=""
    else
      ready=false; all_ready=false
      action="$("remaining_action_$key" "$owner" "$name")"
    fi
    entry="$(jq -n --arg key "$key" --argjson ready "$ready" --arg action "$action" \
      '{key: $key, ready: $ready, remaining_action: (if $ready then null else $action end)}')"
    elements_json="$(jq --argjson e "$entry" '. + [$e]' <<<"$elements_json")"
  done < <(profile_elements "$profile") || return 1
  jq -n --arg target "$owner/$name" --arg profile "$profile" --argjson elements "$elements_json" \
    --argjson ready "$all_ready" --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{target: $target, profile: $profile, elements: $elements, ready: $ready, generated_at: $generated_at}'
}
