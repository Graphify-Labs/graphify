FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/runner \
    HOME=/tmp/graphify-home \
    XDG_CONFIG_HOME=/tmp/graphify-xdg \
    GRAPHIFY_SANDBOX_REPO=/mnt/graphify-repo \
    GRAPHIFY_SANDBOX_OUTPUT=/sandbox-out \
    GRAPHIFY_SANDBOX_PROJECT=/tmp/graphify-project \
    GRAPHIFY_SANDBOX_USER_CWD=/tmp/graphify-user-cwd \
    GRAPHIFY_SANDBOX_SOURCE=/tmp/graphify-source

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install "PyYAML>=6.0.3"

RUN mkdir -p \
      /runner/tools/install_sandbox \
      /tmp/graphify-home \
      /tmp/graphify-xdg \
      /tmp/graphify-project \
      /tmp/graphify-user-cwd \
      /sandbox-out \
    && touch /runner/tools/__init__.py \
    && chmod -R 0777 \
      /tmp/graphify-home \
      /tmp/graphify-xdg \
      /tmp/graphify-project \
      /tmp/graphify-user-cwd \
      /sandbox-out

COPY . /runner/tools/install_sandbox/

WORKDIR /tmp/graphify-project
ENTRYPOINT ["python", "-m", "tools.install_sandbox.sandbox_runner"]
