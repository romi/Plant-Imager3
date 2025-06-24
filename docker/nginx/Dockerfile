FROM nginx

# Metadata labels for the Docker image
LABEL maintainer="Jonathan LEGRAND <jonathan.legrand@ens-lyon.fr>"
LABEL license="LGPL-3.0-or-later"
LABEL description="Plant Imager Proxy"

# Define build arguments to be passed during image creation
ARG SERVER_URL="127.0.0.1"
ARG CONTROLLER_URL="127.0.0.1"
ARG CONTROLLER_PORT="8080"
ARG PLANTDB_URL="127.0.0.1"
ARG PLANTDB_PORT="5000"
ARG P3DX_URL="127.0.0.1"
ARG P3DX_PORT="5050"

# Create directory for SSL certificates
RUN mkdir -p /etc/nginx/ssl

# Copy SSL certificates (you'll need to create these files)
COPY ssl/cert.pem /etc/nginx/ssl/
COPY ssl/key.pem /etc/nginx/ssl/

# Copy the default configuration file to NGINX directory
COPY default.conf .

# Substitute environment variables in the configuration file and save it
RUN envsubst "\$SERVER_URL \$CONTROLLER_URL \$CONTROLLER_PORT \$PLANTDB_URL \$PLANTDB_PORT \P3DX_URL \P3DX_PORT" < default.conf > /etc/nginx/conf.d/default.conf

# Copy custom NGINX configuration to the appropriate location
COPY nginx.conf /etc/nginx/nginx.conf