#!/usr/bin/env bash
# The single documented, maintainer-run entry point for standing up or
# converging an E2E target repository (contracts/cli.md, FR-001/FR-014).
# Runs under the invoking shell's own `gh` authentication only -- never
# under an App installation token (FR-003) -- and is never invoked from a
# GitHub Actions job (FR-014).
set -uo pipefail

SP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SP/../.." && pwd)"
# shellcheck source=e2e-provisioning/profiles.sh
source "$SP/e2e-provisioning/profiles.sh"
# shellcheck source=e2e-provisioning/checks.sh
source "$SP/e2e-provisioning/checks.sh"

declare -A WRAPPER_STAGE_FILE=(
  [wing-commander-1-intake.yml]=intake.yml
  [wing-commander-2-clarify.yml]=clarify.yml
  [wing-commander-3-plan.yml]=plan.yml
  [wing-commander-4-tasks.yml]=tasks.yml
  [wing-commander-5-implement.yml]=implement.yml
  [wing-commander-6-finalize.yml]=finalize.yml
  [wing-commander-7-cleanup.yml]=cleanup.yml
  [wing-commander-rebase.yml]=rebase.yml
)

usage() {
  echo "Usage: provision-e2e-target.sh --repo OWNER/NAME --profile auto-release|spec-kit-scratch [--check-only]" >&2
}

REPO="" PROFILE="" CHECK_ONLY=false
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { echo "provision-e2e-target.sh: --repo requires a value" >&2; usage; exit 1; }
      REPO="$2"; shift 2 ;;
    --profile)
      [ $# -ge 2 ] || { echo "provision-e2e-target.sh: --profile requires a value" >&2; usage; exit 1; }
      PROFILE="$2"; shift 2 ;;
    --check-only)
      CHECK_ONLY=true; shift ;;
    *)
      echo "provision-e2e-target.sh: unrecognized argument '$1'. No other flags." >&2
      usage; exit 1 ;;
  esac
done
# checks.sh's check_scratch_marker reads this to treat the marker element as
# not applicable on the read-only path (T044) -- exported before checks.sh
# is ever called against a real target.
export WC_CHECK_ONLY="$CHECK_ONLY"

if [ -z "$REPO" ]; then
  echo "provision-e2e-target.sh: --repo is required" >&2; usage; exit 1
fi
if [ -z "$PROFILE" ]; then
  echo "provision-e2e-target.sh: --profile is required" >&2; usage; exit 1
fi
case "$PROFILE" in
  auto-release|spec-kit-scratch) : ;;
  *)
    echo "provision-e2e-target.sh: --profile must be 'auto-release' or 'spec-kit-scratch', got '$PROFILE'" >&2
    usage; exit 1 ;;
esac
case "$REPO" in
  */*/*|/*|*/|*[[:space:]]*)
    echo "provision-e2e-target.sh: --repo '$REPO' is not an OWNER/NAME pair" >&2
    exit 1 ;;
  */*) : ;;
  *)
    echo "provision-e2e-target.sh: --repo '$REPO' is not an OWNER/NAME pair" >&2
    exit 1 ;;
esac

OWNER="${REPO%%/*}"
NAME="${REPO#*/}"

# this_repo_from_git: derives OWNER/NAME of the repository this checkout
# belongs to, from `git remote`, WITHOUT any `gh` call -- FR-007's
# self-refusal must happen before any `gh` call is made, so it cannot
# resolve "this repository" through `gh repo view`.
this_repo_from_git() {
  local url rest
  url="$(git -C "$REPO_ROOT" config --get remote.origin.url 2>/dev/null)" || return 1
  # A checkout's HTTPS remote can embed a live credential
  # (https://x-access-token:<token>@github.com/owner/name.git) -- match on
  # "github.com" and take what follows the separator, so the URL itself,
  # token included, is never captured into a variable this script might
  # echo, log, or write into a commit.
  case "$url" in
    *github.com[:/]*) rest="${url#*github.com[:/]}" ;;
    *) return 1 ;;
  esac
  rest="${rest%.git}"
  rest="${rest%/}"
  [ -n "$rest" ] && printf '%s' "$rest"
}

# resolve_this_repo: this_repo_from_git(), falling back to GITHUB_REPOSITORY
# (an env var, never a `gh` call, so this still runs before any `gh` call is
# made) when the git remote can't be resolved -- e.g. a checkout with no
# `origin` or an unparsable remote URL. T045: the old code silently skipped
# the self-refusal entirely when this_repo_from_git failed, leaving only the
# marker rail between a mutating run and this repository.
resolve_this_repo() {
  local r
  r="$(this_repo_from_git || true)"
  [ -n "$r" ] || r="${GITHUB_REPOSITORY:-}"
  printf '%s' "$r"
}

# --- FR-007: refuse self-targeting, before any gh call ---------------------
THIS_REPO="$(resolve_this_repo)"
if [ -n "$THIS_REPO" ]; then
  repo_lc="$(printf '%s' "$REPO" | tr '[:upper:]' '[:lower:]')"
  self_lc="$(printf '%s' "$THIS_REPO" | tr '[:upper:]' '[:lower:]')"
  if [ "$repo_lc" = "$self_lc" ]; then
    echo "provision-e2e-target.sh: refusing to target this repository ($THIS_REPO) -- FR-007" >&2
    exit 1
  fi
elif [ "$CHECK_ONLY" != "true" ]; then
  # Neither signal resolved, and this is the mutating path: refuse rather
  # than proceed unable to rule out targeting this repository (T045). A
  # read-only --check-only run mutates nothing, so it is allowed to proceed
  # unresolved.
  echo "provision-e2e-target.sh: could not determine this repository's own OWNER/NAME (no resolvable git remote and GITHUB_REPOSITORY is unset) -- refusing to proceed on the mutating path without being able to rule out targeting this repository -- FR-007/T045" >&2
  exit 1
fi

act_repository() { # act_repository OWNER NAME
  gh repo create "$1/$2" --private >/dev/null
}

act_claude_credential() { # act_claude_credential OWNER NAME
  if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    printf '%s' "$CLAUDE_CODE_OAUTH_TOKEN" | gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo "$1/$2" >/dev/null
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    printf '%s' "$ANTHROPIC_API_KEY" | gh secret set ANTHROPIC_API_KEY --repo "$1/$2" >/dev/null
  fi
  # Neither set: element stays not-ready; remaining_action_claude_credential
  # explains it (research.md D5). Never treated as the FR-015 manual step.
}

act_spec_request_label() { # act_spec_request_label OWNER NAME
  gh label create spec-request --repo "$1/$2" >/dev/null 2>&1 || true
}

# act_wrapper_set writes each wrapper file through the Contents API
# (`gh api ... -X PUT`) rather than a git clone/push -- it needs no working
# tree beyond this checkout's own wrapper files (research.md D6: the same
# files auto-release.yml's scaffold step copies) and no local git identity
# on the target, only the maintainer's own `gh` authentication (FR-003).
act_wrapper_set() { # act_wrapper_set OWNER NAME
  local owner="$1" name="$2" default_branch head_sha this_repo f stage content sha b64 upstream upstream_sha
  this_repo="$(this_repo_from_git)" || {
    echo "provision-e2e-target.sh: could not determine this repository's OWNER/NAME from its git remote -- refusing to pin wrapper workflows in $owner/$name to an unresolvable source (T042)" >&2
    exit 1
  }
  head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  # T042/T049: a HEAD not yet reachable from this checkout's upstream branch
  # would pin wrappers to a commit the target's own Actions runs cannot
  # fetch. This stays a warning, not a hard failure, by design: committing
  # and pinning before pushing is a normal, safe local sequence (this
  # feature's own implement stage does exactly that -- gate-check locally,
  # commit, push after), and a hard failure here would block that legitimate
  # sequence more often than it would catch a real mistake. The downstream
  # failure mode if the SHA truly never gets pushed is not a vacuous pass:
  # the target's own Actions run fails loudly and immediately at the
  # unresolvable `uses:` ref, self-diagnosing at the exact point of the
  # actual defect -- unlike a value silently written wrong (e.g. T040),
  # this never reports `ready: true` for a target whose wrapper pin will
  # not actually resolve as long as the run that observes readiness happens
  # after the push, which quickstart.md's own sequencing already requires.
  upstream="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" || upstream=""
  if [ -n "$upstream" ]; then
    upstream_sha="$(git -C "$REPO_ROOT" rev-parse "$upstream" 2>/dev/null)" || upstream_sha=""
    if [ "$upstream_sha" != "$head_sha" ]; then
      echo "provision-e2e-target.sh: warning: HEAD ($head_sha) is ahead of $upstream -- push it before $owner/$name's Actions runs need to resolve wrapper workflows pinned to it (T042)" >&2
    fi
  else
    echo "provision-e2e-target.sh: warning: this checkout's current branch has no upstream tracking branch -- cannot confirm HEAD ($head_sha) will be reachable from $this_repo when $owner/$name's Actions runs resolve pinned wrapper workflows (T042)" >&2
  fi
  default_branch="$(gh repo view "$owner/$name" --json defaultBranchRef -q '.defaultBranchRef.name // empty' 2>/dev/null)"
  [ -n "$default_branch" ] || default_branch="main"
  for f in "${WRAPPER_FILES[@]}"; do
    stage="${WRAPPER_STAGE_FILE[$f]}"
    content="$(sed -e "s#uses: \./\.github/workflows/${stage}#uses: ${this_repo}/.github/workflows/${stage}@${head_sha}#" \
      "$REPO_ROOT/.github/workflows/$f")"
    # docs/adoption.md's own instruction, applied the same way
    # auto-release.yml's scaffold step applies it: replace the literal
    # `main` in the two wrappers whose gate/trigger names it with the
    # target's actual default branch.
    if [ "$f" = "wing-commander-3-plan.yml" ]; then
      content="$(printf '%s\n' "$content" | sed "s/== 'main'/== '${default_branch}'/")"
    fi
    if [ "$f" = "wing-commander-rebase.yml" ]; then
      content="$(printf '%s\n' "$content" | sed "s/branches: \[main\]/branches: [${default_branch}]/")"
    fi
    b64="$(printf '%s\n' "$content" | base64 | tr -d '\n')"
    sha="$(gh api "repos/$owner/$name/contents/.github/workflows/$f" -q .sha 2>/dev/null || true)"
    if [ -n "$sha" ]; then
      gh api "repos/$owner/$name/contents/.github/workflows/$f" -X PUT \
        -f message="chore: install wing-commander wrapper workflows" \
        -f content="$b64" -f branch="$default_branch" -f sha="$sha" >/dev/null
    else
      gh api "repos/$owner/$name/contents/.github/workflows/$f" -X PUT \
        -f message="chore: install wing-commander wrapper workflows" \
        -f content="$b64" -f branch="$default_branch" >/dev/null
    fi
  done
}

act_container_image_pin() { # act_container_image_pin OWNER NAME
  local value
  # T040: a failed read (auth, cwd, network) must never be treated as "this
  # repository pins no image" -- that silently overwrites the target's pin
  # with an empty string instead of failing loudly. An explicit empty
  # STRING read successfully from this_repo_container_image is still a
  # valid value (FR-017) and is written as-is; `gh variable set --body ""`
  # is a normal, supported call that stores an empty-string variable value.
  value="$(this_repo_container_image)" || {
    echo "provision-e2e-target.sh: could not read this repository's own WING_COMMANDER_CONTAINER_IMAGE value -- refusing to pin $1/$2 to an empty value that may only be a read failure (FR-017)" >&2
    exit 1
  }
  gh variable set WING_COMMANDER_CONTAINER_IMAGE --repo "$1/$2" --body "$value" >/dev/null
}

act_scratch_marker() { # act_scratch_marker OWNER NAME
  gh repo edit "$1/$2" --description "$SCRATCH_MARKER" >/dev/null
}

if [ "$CHECK_ONLY" != "true" ]; then
  # data-model.md D3: refuse a foreign, non-empty, unmarked repository
  # before any privileged action -- T025 hardens this ordering. Scoped to
  # the mutating path only (T037): a --check-only run against a
  # hand-onboarded, non-empty, unmarked target (the normal shape of an
  # existing pre-053 target) must still produce a full ReadinessReport
  # naming scratch_marker as the not-ready element, not a bare stderr
  # refusal with no JSON on stdout (FR-011, US2 Acceptance Scenario 2).
  if ! check_scratch_marker "$OWNER" "$NAME"; then
    echo "provision-e2e-target.sh: $(remaining_action_scratch_marker "$OWNER" "$NAME")" >&2
    exit 1
  fi

  if ! check_repository "$OWNER" "$NAME"; then
    act_repository "$OWNER" "$NAME"
  fi
  # T038/T039: claim the marker immediately once the repository exists,
  # before any other privileged action (e.g. wrapper_set) can give it
  # content -- whenever it is ABSENT, regardless of how empty the
  # repository still is. A run that dies partway now leaves a
  # marked-but-incomplete, re-runnable repository, never a non-empty,
  # unmarked one that the refusal above would then block forever. (Before
  # this fix, act_scratch_marker was gated on `! check_scratch_marker`,
  # which already reports an empty repository as ready -- so the marker was
  # never actually written until the repository was no longer empty, by
  # which point a foreign-non-empty-unmarked refusal was permanent.)
  if ! has_scratch_marker "$OWNER" "$NAME"; then
    # T046: the script runs under `set -uo pipefail`, not `-e`, so a failed
    # write here (permission, rate limit) would otherwise be silently
    # ignored and the run would proceed to push wrapper content -- exactly
    # the non-empty, unmarked, permanently-refused state T038/T039's
    # marker-first ordering was meant to prevent. Exit before any further
    # privileged action if the write itself did not succeed.
    if ! act_scratch_marker "$OWNER" "$NAME"; then
      echo "provision-e2e-target.sh: failed to write the scratch marker to $OWNER/$NAME -- refusing to proceed with any further privileged action (T046)" >&2
      exit 1
    fi
  fi

  mapfile -t ELEMENTS < <(profile_elements "$PROFILE")
  for key in "${ELEMENTS[@]}"; do
    case "$key" in
      # app_installation is the DeclaredManualStep: never performed, only
      # checked (FR-015). repository and scratch_marker are handled above,
      # in that order, before this loop.
      app_installation|repository|scratch_marker) continue ;;
    esac
    if ! "check_$key" "$OWNER" "$NAME"; then
      "act_$key" "$OWNER" "$NAME"
    fi
  done
fi

REPORT="$(assemble_report "$OWNER" "$NAME" "$PROFILE")"
printf '%s\n' "$REPORT"

{
  echo "Readiness report for $OWNER/$NAME ($PROFILE):"
  jq -r '.elements[] | (if .ready then "  [ready]     " else "  [NOT READY] " end) + .key + (if .remaining_action then " -- " + .remaining_action else "" end)' <<<"$REPORT"
} >&2

if [ "$(jq -r .ready <<<"$REPORT")" = "true" ]; then
  exit 0
fi
exit 1
