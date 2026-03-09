# ============= Builder stage for uwsgi =============
FROM ubuntu:24.04 AS builder

# Prevent stop building ubuntu at time zone selection.
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
# Variables required by `pip`:
ENV PATH="/root/.local/bin:${PATH}"

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -yq --no-install-recommends \
        # Install python3.12 & pip
        python3 python3-pip python3-venv \
        # Install 'gcc', 'libc6-dev' & 'python3-dev' to be able to build uwsgi
        gcc libc6-dev python3-dev

RUN --mount=type=cache,target=/root/.cache/pip \
    echo "Building uwsgi..." && \
    # Create a virtual environment
    python3 -m venv /home/root/venv && \
    # Activate the virtual environment and install packages
    . /home/root/venv/bin/activate && \
    # Update required tools to build uwsgi
    python3 -m pip install --no-cache-dir \
        wheel setuptools pip --upgrade && \
    # Build uwsgi
    python3 -m pip install --no-cache-dir \
        uwsgi

# ============= Final stage =============
FROM ubuntu:24.04 AS runtime

LABEL maintainer="Jonathan LEGRAND <jonathan.legrand@ens-lyon.fr>"
LABEL corresponding_author="Peter Hanappe <peter@romi-project.eu>"
LABEL project="Robotics for microfarms"
LABEL homepage="https://docs.romi-project.eu/documentation"
LABEL repository="https://github.com/romi/plant-imager"
LABEL license="LGPL-3.0-or-later"
LABEL description="Plant Imager WebUI"

ARG PLANTDB_BRANCH=""
ENV PLANTDB_GIT="https://github.com/romi/plantdb.git"

# Set user name and id variables:
ENV USER_NAME="romi"
ENV USER_ID=2020

# Prevent stop building ubuntu at time zone selection.
ENV DEBIAN_FRONTEND=noninteractive
# Variables required by Python:
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
# Variables required by `pip`:
ENV PATH="${PATH}:/home/${USER_NAME}/.local/bin"

# Change Shell to 'bash', default is 'sh':
SHELL ["/bin/bash", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    # Install system dependencies:
    apt-get update && apt-get install -y --no-install-recommends \
      # Install some basic tools
      ca-certificates curl git nano rsync \
      # Install python3.12 & pip
      python3 python3-pip python3-venv \
      # Add python3-dev to ensure libpython is available for uwsgi
      python3-dev \
      # Add adduser package to create users (not found in the Ubuntu 24.04 image)
      adduser && \
    # Clean package manager:
    apt-get clean -y && \
    apt-get autoremove -y && \
    # Cleanup package manager and temp files
    rm -rf /var/lib/apt/lists/* 2>/dev/null || true && \
    rm -rf /tmp/* /var/tmp/* 2>/dev/null || true && \
    rm -rf /var/cache/apt/archives/*.deb 2>/dev/null || true && \
    # Remove man pages and docs
    find /usr/share/man /usr/share/doc /usr/share/info -delete 2>/dev/null || true && \
    # Keep only C.UTF-8 locale
    cd /usr/share/locale/ && \
    find . -mindepth 1 -maxdepth 1 ! -name 'C.UTF-8' -exec rm -rf {} + 2>/dev/null || true && \
    # Create a non-root user and create a "home" folder for it:
    adduser --disabled-password --gecos '' --uid ${USER_ID} ${USER_NAME} && \
    chown -R ${USER_NAME}: /home/${USER_NAME}

# Copy uwsgi from builder stage
COPY --from=builder --chown=${USER_NAME} /home/root/venv/bin/uwsgi /home/${USER_NAME}/venv/bin/
COPY --from=builder --chown=${USER_NAME} /home/root/venv/lib/python3.12/site-packages/ /home/${USER_NAME}/venv/lib/python3.12/site-packages/

# Change to the non-root user
USER ${USER_NAME}
# Change working directory
WORKDIR /home/${USER_NAME}
# Copy the source files (repository):
COPY --chown=${USER_NAME} src/commons/ commons/
COPY --chown=${USER_NAME} src/webui/ webui/

RUN --mount=type=cache,target=/root/.cache/pip \
    # Create a virtual environment
    echo "\n\n# Create a virtual environment..." && \
    python3 -m venv /home/${USER_NAME}/venv && \
    # Activate the virtual environment and install packages
    . /home/${USER_NAME}/venv/bin/activate && \
    echo "\n\n# Upgrade pip & setuptools to latest versions..." && \
    python3 -m pip install --upgrade pip setuptools && \
    echo "\n\n# Install 'plantimager.commons' from sources..." && \
    python3 -m pip install --no-cache-dir commons/. && \
    echo "\n\n# Install 'plantimager.webui' from sources..." && \
    python3 -m pip install --no-cache-dir webui/. && \
    # Conditionally clone and install plantdb if a branch is specified
    if [ -n "${PLANTDB_BRANCH}" ]; then \
        echo "\n\n# Clone plantdb branch ${PLANTDB_BRANCH}..." && \
        git clone -b "${PLANTDB_BRANCH}" "${PLANTDB_GIT}" plantdb && \
        echo "\n\n# Install plantdb.commons from cloned repository..." && \
        python3 -m pip install --no-cache-dir plantdb/src/commons/. && \
        echo "\n\n# Install plantdb.client from cloned repository..." && \
        python3 -m pip install --no-cache-dir plantdb/src/client/.; \
    fi && \
    # Clean pip cache:
    python3 -m pip cache purge

COPY --chown=${USER_NAME} docker/webui/entrypoint.sh .
ENTRYPOINT ["./entrypoint.sh"]