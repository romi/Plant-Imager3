FROM continuumio/miniconda3

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

# Variables required by Python:
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
# Variables required by `pip`:
ENV PATH="${PATH}:/home/${USER_NAME}/.local/bin"

RUN apt-get update && \
    # Install system dependencies:
    apt-get install -y --no-install-recommends \
      nano && \
    # Clean cache:
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # Create a non-root user and create a "home" folder for it:
    adduser --disabled-password --gecos '' --uid ${USER_ID} ${USER_NAME} && \
    chown -R ${USER_NAME}: /home/${USER_NAME} && \
    # Create the folder used to mount the database:
    mkdir -p ${ROMI_DB} && \
    touch ${ROMI_DB}/romidb && \
    chown -R ${USER_NAME} ${ROMI_DB} && \
    # Allow non-root user to call conda:
    chown -R ${USER_NAME}: /opt/conda/

# Change to the non-root user
USER ${USER_NAME}
# Change working directory
WORKDIR /home/${USER_NAME}

# Copy the source files (repository):
COPY --chown=${USER_NAME} ./ Plant-Imager3/

RUN echo "\n\n# Installing 'plantimager.commons' from sources..." && \
    python3 -m pip install --no-cache-dir Plant-Imager3/commons/. && \
    echo "\n\n# Installing 'plantimager.webui' from sources..." && \
    python3 -m pip install --no-cache-dir Plant-Imager3/webui/. && \
    # Clean pip cache:
    python3 -m pip cache purge

COPY --chown=${USER_NAME} docker/entrypoint.sh .
ENTRYPOINT ["./entrypoint.sh"]