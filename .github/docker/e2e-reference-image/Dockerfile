# Minimal reference image for wing-commander's own container-mode
# end-to-end verification leg (specs/054-e2e-container-coverage,
# research.md D5). Installs exactly the tools
# .github/scripts/required-tools.txt names -- nothing more. Not intended
# for adopter use (docs/adoption.md, "Runners and container images");
# this image exists solely so this repository's own auto-release.yml can
# dogfood the container: code path every published stage already carries.
#
# Kept in agreement with required-tools.txt by Gate 62
# (.github/scripts/verify-gate-62.py), which builds this image and
# inspects it the same way each stage's own verify-image-prerequisites
# job inspects an adopter's image. bash and timeout (coreutils) ship in
# the base image already, matching required-tools.txt's own note that
# both are assumed present on any Linux base.
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        nodejs \
        python3 \
        wget \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
