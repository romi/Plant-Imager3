FROM nginx

# Metadata labels for the Docker image
LABEL maintainer="Jonathan LEGRAND <jonathan.legrand@ens-lyon.fr>"
LABEL license="LGPL-3.0-or-later"
LABEL description="Plant Imager Proxy"

# Define build arguments to be passed during image creation
ARG SERVER_HOST="127.0.0.1"
ARG CONTROLLER_HOST="127.0.0.1"
ARG CONTROLLER_PORT="8080"
ARG CONTROLLER_PREFIX="/webui"
ARG PLANTDB_HOST="127.0.0.1"
ARG PLANTDB_PORT="5000"
ARG PLANTDB_PREFIX="/plantdb"
ARG P3DX_HOST="127.0.0.1"
ARG P3DX_PORT="5050"
ARG P3DX_PREFIX="/p3dx"
ARG P3DV_HOST="127.0.0.1"
ARG P3DV_PORT="8081"
ARG P3DV_PREFIX="/p3dv"

# Create directories for SSL certificates and a temporary directory
RUN mkdir -p /etc/nginx/ssl /tmp

# Copy the default configuration file to NGINX directory
COPY default.conf .

# Substitute environment variables in the configuration file and save it
RUN envsubst "\$SERVER_HOST \$CONTROLLER_HOST \$CONTROLLER_PORT \$CONTROLLER_PREFIX \$PLANTDB_HOST \$PLANTDB_PORT \$PLANTDB_PREFIX \$P3DX_HOST \$P3DX_PORT \$P3DX_PREFIX \$P3DV_HOST \$P3DV_PORT \$P3DV_PREFIX" < default.conf > /etc/nginx/conf.d/default.conf

# Copy custom NGINX configuration to the appropriate location
COPY nginx.conf /etc/nginx/nginx.conf