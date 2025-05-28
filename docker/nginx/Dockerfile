FROM nginx

# Metadata labels for the Docker image
LABEL maintainer="Jonathan LEGRAND <jonathan.legrand@ens-lyon.fr>"
LABEL license="LGPL-3.0-or-later"
LABEL description="Plant Imager Proxy"

# Define build arguments to be passed during image creation
ARG SERVER_URL
ARG CONTROLLER_URL
ARG CONTROLLER_PORT

# Create directory for SSL certificates
RUN mkdir -p /etc/nginx/ssl

# Copy SSL certificates (you'll need to create these files)
COPY ssl/cert.pem /etc/nginx/ssl/
COPY ssl/key.pem /etc/nginx/ssl/

# Copy the default configuration file to NGINX directory
COPY default.conf .

# Substitute environment variables in the configuration file and save it
RUN envsubst "\$SERVER_URL \$CONTROLLER_URL \$CONTROLLER_PORT" < default.conf > /etc/nginx/conf.d/default.conf

# Copy custom NGINX configuration to the appropriate location
COPY nginx.conf /etc/nginx/nginx.conf