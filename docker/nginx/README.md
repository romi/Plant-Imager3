# PlantImager NGINX

This Docker container runs an NGINX server configured as a reverse proxy for the PlantImager project.

## Overview

The purpose of this proxy is to route incoming requests to appropriate backend services, making it easier to access different components of the PlantImager system through friendly URLs.

## Proxy Configuration

The NGINX reverse proxy is configured to route requests as follows:


| URL Path   | Service                            |
|------------|------------------------------------|
| `/test`    | NGINX test route                   |
| `/plantdb` | PlantDB REST API (backend)         |
| `/webui`   | WebUI (frontend)                   |
| `/p3dx`    | Plant 3D Explorer (frontend)       |
| `/p3dv`    | Plant 3D Vision WebTerm (frontend) |

This setup allows you to access different components of your application through a single entry point, improving the organization and accessibility of your services.

## Generating Self-Signed SSL Certificates

For secure HTTPS connections, you'll need SSL certificates.
Follow these steps to generate **self-signed** certificates for development/testing.

### Install OpenSSL

If not already installed, install OpenSSL using your package manager:

``` bash
sudo apt-get update
sudo apt-get install openssl
```

### Generate Private Key and Certificate

First create an `ssl` folder in the `docker/nginx` directory of the cloned sources.
It will receive the `openssl.cnf`, `key.pem` and `cert.pem` files created hereafter and used by the server (`key.pem` +
`cert.pem`) and clients (`cert.pem`).

#### 1. Create a Configuration File

Then, create an OpenSSL configuration file (e.g., `openssl.cnf`) as follows:

``` 
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no
default_bits = 2048
default_md = sha256

[ca]
default_days = 365

[req_distinguished_name]
C = <FR>
ST = <Your-State>
L = <Your-City>
O = <Your-Organization>
OU = <Your-Department>
CN = <personal.server.fr>

[v3_req]
basicConstraints = CA:FALSE
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = <personal.server.fr>
DNS.2 = <personal>
DNS.3 = <server.fr>
# Add any additional hostnames or IP addresses here
# IP.1 = 192.168.1.1
```

You will to replace all parameters within angle brackets `<>` to suits your needs.

#### 2. Generate the Certificate and Private Key

Run the following command to generate a self-signed certificate with the configuration:

``` bash
# Generate a self-signed certificate and the private key
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout ssl/key.pem -out ssl/cert.pem -config ssl/openssl.cnf -extensions v3_req
```

This command:

- Creates a self-signed X.509 certificate
- Valid for 365 days
- Using a 2048-bit RSA key
- Private key in `key.pem`
- Certificate in `cert.pem`
- Uses the configuration file `openssl.cnf`
- Includes the extensions (like SAN)

#### 3. Verify the Certificate

Check that the certificate includes the correct Subject Alternative Names:

``` bash
openssl x509 -in ssl/cert.pem -text -noout | grep DNS
```

> **Note**:
> For production environments, consider using certificates from a trusted Certificate Authority.
> This requires a registered domain name pointing to your server AND port 80 or 443 open to the internet for domain validation.

## Build the NGINX docker image

To build the NGINX Docker image, you need to specify the following build arguments:

- `SERVER_HOST`: the URL of the NGINX server acting as reverse proxy;
- `CONTROLLER_HOST`: the URL of the controller (serving the WebUI);
- `CONTROLLER_PORT`: the port of the controller.
- `CONTROLLER_PREFIX`: the URL prefix redirecting to the controller service.
- `PLANTDB_HOST`: the URL of the PlantDB REST API (serving the dataset);
- `PLANTDB_PORT`: the port of the PlantDB REST API.
- `PLANTDB_PREFIX`: the URL prefix redirecting to the PlantDB REST API service.
- `P3DV_HOST`: the URL of the WebTerm (plant-3d-vision reconstruction and analysis tools);
- `P3DV_PORT`: the port of the WebTerm.
- `P3DV_PREFIX`: the URL prefix redirecting to the WebTerm service.
- `P3DX_HOST`: the URL of the plant 3D explorer (dedicated viewer);
- `P3DX_PORT`: the port of the plant 3D explorer.
- `P3DX_PREFIX`: the URL prefix redirecting to the plant 3D explorer service.

Use the following command:

```shell
cd docker/nginx
sudo docker build \
  --build-arg SERVER_HOST='dev.romi.local' \
  --build-arg CONTROLLER_HOST='plantimager_webui' \
  --build-arg CONTROLLER_PORT='8080' \
  --build-arg CONTROLLER_PREFIX='/webui' \
  --build-arg PLANTDB_HOST='plantimager_plantdb' \
  --build-arg PLANTDB_PORT='5000' \
  --build-arg PLANTDB_PREFIX='/plantdb' \
  --build-arg P3DV_HOST='plantimager_p3dv' \
  --build-arg P3DV_PORT='8081' \
  --build-arg P3DV_PREFIX='/p3dv' \
  --build-arg P3DX_HOST='plantimager_p3dx' \
  --build-arg P3DX_PORT='80' \
  --build-arg P3DX_PREFIX='/p3dx' \
  -t roboticsmicrofarms/plantimager_nginx:latest .
```

> **Note**:
> - Replace the URLs and port with your actual values.
> - If the backend and frontend apps run in containers, you can use the container names (`plantimager_*`) as URL.

## Run the Container

After building the image, you can run the container with:

```shell
sudo docker run -d --name plantimager_nginx \
  -p 443:443 -p 80:80 \
  -v /path/to/cert/ssl/:/etc/nginx/ssl/ \
  roboticsmicrofarms/plantimager_nginx:latest
```

This command:

- Runs the container in detached mode (`-d`)
- Names the container `plantimager_nginx`
- Bind the path whe you create your OpenSSL certificates (`/path/to/cert/ssl/`) to the location NGINX expect them to be (`/etc/nginx/ssl/`)
- Maps the following ports:
    - Host port 80 → container port 80 (HTTP)
    - Host port 443 → container port 443 (HTTPS)

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

## Obtaining Trusted SSL Certificates

For production environments, self-signed certificates aren't recommended as they trigger browser warnings and don't provide the security guarantees of certificates from trusted Certificate Authorities (CAs).

Here's how to obtain and use trusted SSL certificates from [Let's Encrypt](https://letsencrypt.org/), a free, automated, and open Certificate Authority that provides trusted SSL certificates.

### Prerequisites:

- A registered domain name pointing to your server
- Port 80 or 443 open to the internet for domain validation

### Using Certbot with Docker:

1. **Set up a Certbot Docker container**:
    ```bash
    sudo docker run -it --rm \
      -v /etc/letsencrypt:/etc/letsencrypt \
      -v /var/lib/letsencrypt:/var/lib/letsencrypt \
      -p 80:80 \
      certbot/certbot certonly --standalone \
      -d your-domain.com \
      --email your-email@example.com \
      --agree-tos
    ```
2. **Copy certificates to your NGINX SSL directory**:
    ```bash
    mkdir -p docker/nginx/ssl
    cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/nginx/ssl/cert.pem
    cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/nginx/ssl/key.pem
    ```
3. **Set up auto-renewal** (add to `crontab`):
    ```bash
    0 0 * * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt certbot/certbot renew --quiet && cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /path/to/docker/nginx/ssl/cert.pem && cp /etc/letsencrypt/live/your-domain.com/privkey.pem /path/to/docker/nginx/ssl/key.pem
    ```

### Updated Security

1. **Add HSTS header** to enforce HTTPS (add to your `default.conf`):
    ```nginx
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    ```
2. **Protect private keys**: Use secure file permissions (`chmod 600 ssl/key.pem`)
