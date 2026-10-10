# Minimal reference image for wing-commander's own container-mode
# end-to-end verification leg (specs/054-e2e-container-coverage,
# research.md D5). Installs the tools .github/scripts/required-tools.txt
# names, plus what this repository's OWN implement jobs need on top of
# them -- nothing more. Not intended for adopter use (docs/adoption.md,
# "Runners and container images"); this image exists solely so this
# repository's own auto-release.yml can dogfood the container: code path
# every published stage already carries.
#
# Kept in agreement with required-tools.txt by Gate 62
# (.github/scripts/verify-gate-62.py), which builds this image and
# inspects it the same way each stage's own verify-image-prerequisites
# job inspects an adopter's image. bash and timeout (coreutils) ship in
# the base image already, matching required-tools.txt's own note that
# both are assumed present on any Linux base.
#
# The extras are not adopter prerequisites, so required-tools.txt does not
# list them (an adopter repository has no local gate suite). This
# repository pins WING_COMMANDER_CONTAINER_IMAGE to this image, so its
# implement jobs run inside it and need:
#   - python3-yaml: the local gate suite (run-local-gates.py and most
#     verify-*.py) imports yaml. Without it implement.yml's "Preflight:
#     gate-suite prerequisites" step reports ready=false and every
#     gate-run task stays unchecked, cycle after cycle (#989).
#   - python-is-python3: the implement prompt and CLAUDE.md name the suite
#     as `python .github/scripts/run-local-gates.py`, and the image has
#     no `python` without it.
#   - shellcheck, yamllint: the lint tools implement.yml's agent prompt
#     tells the agent to use; actionlint also shells out to shellcheck for
#     the shell inside run: blocks, and silently skips that without it.
#     actionlint itself is installed by the implement job at run time.
# Gate 62 also runs implement.yml's own preflight step inside the built
# image and checks every command the agent prompt names, reading both
# from implement.yml itself, so the gate keeps no copy of either list.
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        nodejs \
        python3 \
        python-is-python3 \
        python3-yaml \
        shellcheck \
        unzip \
        wget \
        yamllint \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
