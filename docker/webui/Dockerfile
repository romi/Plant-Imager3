# ============= Builder stage for uwsgi =============
FROM ubuntu:24.04 AS builder

# Prevent stop building ubuntu at time zone selection.
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && \
    apt-get install -yq --no-install-recommends \
        # Install python3.12 & pip
        python3 python3-pip python3-venv \
        # Install 'gcc', 'libc6-dev' & 'python3-dev' to be able to build uwsgi
        gcc libc6-dev python3-dev && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*

RUN echo "Building uWSGI..." && \
    # Create a virtual environment
    python3 -m venv /home/${USER_NAME}/venv && \
    # Activate the virtual environment and install packages
    . /home/${USER_NAME}/venv/bin/activate && \
    # Upgrade pip & setuptools to latest versions
    pip install --upgrade pip setuptools wheel && \
    # Build uwsgi
    python3 -m pip install --no-cache-dir uwsgi && \
    # Copy the built file(s) to access them in runtime stage
    cp /home/${USER_NAME}/venv/bin/uwsgi /usr/local/bin/

# ============= Final stage =============
FROM ubuntu:24.04 AS runtime

LABEL maintainer="Jonathan LEGRAND <jonathan.legrand@ens-lyon.fr>"
LABEL corresponding_author="Peter Hanappe <peter@romi-project.eu>"
LABEL project="Robotics for microfarms"
LABEL homepage="https://docs.romi-project.eu/documentation"
LABEL repository="https://github.com/romi/plant-imager"
LABEL license="LGPL-3.0-or-later"
LABEL description="Plant Imager WebUI"

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

# URI prefix to use when behind a reverse proxy (NGINX)
ENV URL_PREFIX=""
ENV SERVER_PORT="8080"
EXPOSE ${SERVER_PORT}

# Change Shell to 'bash', default is 'sh':
SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    # Install system dependencies:
    apt-get install -y --no-install-recommends \
      nano git ca-certificates rsync \
      # Install python3.12 & pip
      python3 python3-pip python3-venv \
      # Add python3-dev to ensure libpython is available for uwsgi
      python3-dev \
      # Add adduser package to create users (not found in the Ubuntu 24.04 image)
      adduser && \
    # Clean package manager:
    apt-get clean -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* && \
    # Create a non-root user and create a "home" folder for it:
    adduser --disabled-password --gecos '' --uid ${USER_ID} ${USER_NAME} && \
    chown -R ${USER_NAME}: /home/${USER_NAME}

# Copy uwsgi from builder stage
COPY --from=builder /usr/local/bin/uwsgi /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.12/dist-packages/ /usr/local/lib/python3.12/dist-packages/

# Change to the non-root user
USER ${USER_NAME}
# Change working directory
WORKDIR /home/${USER_NAME}

# Copy the source files (repository):
COPY --chown=${USER_NAME} src/commons/ commons/
COPY --chown=${USER_NAME} src/webui/ webui/
COPY --chown=${USER_NAME} docker/webui/entrypoint.sh /home/${USER_NAME}/entrypoint.sh

RUN echo "\n\n# Create a virtual environment..." && \
    python3 -m venv /home/${USER_NAME}/venv && \
    # Activate the virtual environment and install packages
    . /home/${USER_NAME}/venv/bin/activate && \
    echo "\n\n# Upgrade pip & setuptools to latest versions..." && \
    python3 -m pip install --upgrade pip setuptools && \
    echo "\n\n# Install 'plantimager.commons' from sources..." && \
    python3 -m pip install --no-cache-dir commons/. && \
    echo "\n\n# Install 'plantimager.webui' from sources..." && \
    python3 -m pip install --no-cache-dir webui/. && \
    # Clean pip cache:
    python3 -m pip cache purge

ENTRYPOINT ["./entrypoint.sh"]
