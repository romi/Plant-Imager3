# PlantImager NGINX

This Docker container runs an NGINX server configured as a reverse proxy for the PlantImager project.

## Overview
The purpose of this proxy is to route incoming requests to appropriate backend services, making it easier to access different components of the PlantImager system through friendly URLs.

## Proxy Configuration
The NGINX reverse proxy is configured to route requests as follows:
- **Test endpoint**: returns a simple status message for testing purposes `/test`
- **PlantDB service**: Requests to are proxied to `/plantdb``http://localhost:5000`
- **WebUI service**: Requests to are proxied to the controller URL and port specified during build time `/webui`

This setup allows you to access different components of your application through a single entry point, improving the organization and accessibility of your services.

## Generating Self-Signed SSL Certificates
For secure HTTPS connections, you'll need SSL certificates.
Follow these steps to generate self-signed certificates for development/testing.

### Install OpenSSL
If not already installed, install OpenSSL using your package manager:
``` bash
sudo apt-get update
sudo apt-get install openssl
```

### Generate Private Key and Certificate
Generate self-signed certificates with:
``` bash
# Create an ssl directory
cd docker/nginx
mkdir ssl

# Generate a private key
openssl genpkey -algorithm RSA -out ssl/key.pem

# Generate a self-signed certificate using the private key
openssl req -new -x509 -key ssl/key.pem -out ssl/cert.pem -days 365
```
During the process, you will be prompted to enter information such as Country, State, Organization, etc.
You can fill this in with your details.

> **Note**:
> For production environments, consider using certificates from a trusted Certificate Authority.


## Build the docker image
To build the Docker image, you need to specify the following build arguments:
- `SERVER_URL`: the URL of the NGINX server;
- `CONTROLLER_URL`: the URL of the controller (serving the WebUI);
- `CONTROLLER_PORT`: the port of the controller.

Use the following command:
```shell
cd docker/nginx
sudo docker build \
  --build-arg SERVER_URL='server_url.com' \
  --build-arg CONTROLLER_URL='controller_url.com' \
  --build-arg CONTROLLER_PORT='8080' \
  -t roboticsmicrofarms/plantimager_nginx:latest .
```

> **Note**:
> Replace the placeholder URLs and port with your actual values.


## Run a container
After building the image, you can run the container with:
```shell
sudo docker run -d --name plantimager_nginx \
  -p 443:443 -p 8080:8080 -p 80:80 \
  roboticsmicrofarms/plantimager_nginx:latest
```

This command:
- Runs the container in detached mode (`-d`)
- Names the container `plantimager_nginx`
- Maps the following ports:
    - Host port 80 → container port 80 (HTTP)
    - Host port 443 → container port 443 (HTTPS)
    - Host port 8080 → container port 8080 (controller traffic)


## Stop & Clean Up
To stop the `plantimager_nginx` container and remove it:
```bash
sudo docker stop plantimager_nginx || echo "Container plantimager_nginx not running!"
sudo docker rm plantimager_nginx || echo "No stopped plantimager_nginx to remove!"
```

## Advanced Configuration
The Docker image uses two configuration files:
- `nginx.conf`: Contains general NGINX settings like worker processes, connection limits, and logging 
- `default.conf`: Contains the specific proxy routing rules 

You can modify these files to adjust the proxy behavior before building the image.
