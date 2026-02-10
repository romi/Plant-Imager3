# Starting up the services

In this section we detail how to configure and start the services stack.

## Configuration File Breakdown

### `.env`

```dotenv
SERVER_HOST=plantimager.local
# Plant Imager WebUI (webui service)
CONTROLLER_HOST="plantimager_webui"  # internal docker DNS, can be an IP if external
CONTROLLER_PORT=8080
CONTROLLER_PREFIX="/webui"
# PlantDB REST API (plantdb servie)
PLANTDB_HOST="plantimager_plantdb"  # internal docker DNS
PLANTDB_PORT=5000
PLANTDB_PREFIX="/plantdb"
# Plant 3D Explorer UI (p3dx service)
P3DX_HOST="plantimager_p3dx"  # internal docker DNS
P3DX_PORT=80
P3DX_PREFIX="/p3dx"
# Plant 3D Vision WebTerm (p3dv service)
P3DV_HOST="plantimager_p3dv"  # internal docker DNS
P3DV_PORT=8081
P3DV_PREFIX="/p3dv"

SSL_CERT_LOC="Plant-Imager3/docker/nginx/ssl"  # location of the serf-signed certificates
ROMI_DB="/data/ROMI/"  # path to the database to use, here a bind mount, can be a volume 
COLMAP_VERSION="3.13.0"
P3DV_BASE_IMG='colmap/colmap:20251107.4118'  # 3.13.0
```

* These variables are substituted into the `docker-compose.yml` at build time (via `${VAR}` syntax).
* They drive the NGINX configuration and the service hostnames used by the containers.

### `docker-compose.yml`

* **Build Arguments** – `docker-compose` passes the environment variables as build arguments to `nginx`, `p3dx`, and
  `p3dv` Dockerfiles.
* **Volumes** –
    * `nginx_cert` – Shared certs for NGINX and `webui`.
    * `uwsgi_sockets` – Shared UNIX socket for the uWSGI workers.
    * `p3dv_cfg`, `webterm_users` – Persist configuration and user data for P3DV.
    * `/data/ROMI/test_owner` – Local development database mount (replace with a persistent volume in production).
* **Ports** –
    * `80:80` & `443:443` expose NGINX externally.
    * `CONTROLLER_PORT` and
      `PLANTDB_PORT` are also mapped for debugging, but in production you would typically not expose them.
* **Dependencies** –
    * `nginx` waits for `ssl_cert`, `plantdb`, `p3dx`, and `p3dv`.
    * `webui` depends on `ssl_cert`.

## Service stack

```yaml
services:

  ssl_cert:
    # Copy the certificates to the `nginx_cert` volume
    image: roboticsmicrofarms/plantimager_nginx:latest
    restart: no
    volumes:
      - ${SSL_CERT_LOC}:/tmp  # location of the certificates to copy
      - nginx_cert:/etc/nginx/ssl/  # volume (shared with nginx service) hosting the copied certificates
    command: /bin/bash -c 'cp /tmp/*.pem /etc/nginx/ssl/'

  nginx:
    # NGINX service forwarding requests by reverse proxy
    build:
      context: Plant-Imager3/docker/nginx/  # Build context for the Nginx service
      dockerfile: Dockerfile  # Specify the Dockerfile for building the image
      args:
        SERVER_HOST: ${SERVER_HOST}
        CONTROLLER_HOST: ${CONTROLLER_HOST}
        CONTROLLER_PORT: ${CONTROLLER_PORT}
        CONTROLLER_PREFIX: ${CONTROLLER_PREFIX}
        PLANTDB_HOST: ${PLANTDB_HOST}
        PLANTDB_PORT: ${PLANTDB_PORT}
        PLANTDB_PREFIX: ${PLANTDB_PREFIX}
        P3DX_HOST: ${P3DX_HOST}
        P3DX_PORT: ${P3DX_PORT}
        P3DX_PREFIX: ${P3DX_PREFIX}
        P3DV_HOST: ${P3DV_HOST}
        P3DV_PORT: ${P3DV_PORT}
        P3DV_PREFIX: ${P3DV_PREFIX}
    image: roboticsmicrofarms/plantimager_nginx:latest
    container_name: plantimager_nginx
    ports:
      - 80:80    # HTTP traffic (redirected to HTTPS)
      - 443:443  # HTTPS traffic
      #- 8080:8080
    restart: unless-stopped
    volumes:
      - uwsgi_sockets:/tmp
      - nginx_cert:/etc/nginx/ssl/
    networks:
      - plantimager-net
    depends_on:
      - ssl_cert
      - plantdb
      - p3dx
      - p3dv
      - webui

  plantdb:
    # PlantDB REST API service, in production mode, served by uWSGI
    build:
      context: plantdb/
      dockerfile: docker/Dockerfile
    image: roboticsmicrofarms/plantdb:0.14.6
    container_name: plantimager_plantdb
    expose:
      - ${PLANTDB_PORT}  # Expose port internally to the network
    environment:
      PLANTDB_API_PREFIX: ${PLANTDB_PREFIX}
      PLANTDB_API_SSL: true
    command: [ "uwsgi \
               --http=:${PLANTDB_PORT} \
               --socket=/tmp/uwsgi.sock --chmod-socket=666 \
               --module=plantdb.server.cli.wsgi:application \
               --callable=application \
               --master \
               --processes=4 --threads=2 --buffer-size=32768" ]
    restart: unless-stopped
    user: "${UID:-2020}:${GID:-2020}"
    volumes:
      - ${ROMI_DB}:/myapp/db
      - uwsgi_sockets:/tmp
    networks:
      - plantimager-net
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:${PLANTDB_PORT}${PLANTDB_PREFIX}/health" ]
      interval: 120s
      timeout: 10s
      retries: 3
      start_period: 40s

  p3dx:
    # P3DX service, in production mode, served by NGINX
    build:
      context: plant-3d-explorer/
      dockerfile: docker/production/Dockerfile
      args:
        API_URL: http://${SERVER_HOST}${PLANTDB_PREFIX}
        BASENAME: ${P3DX_PREFIX}
    image: roboticsmicrofarms/plantimager_p3dx:0.1.2
    container_name: plantimager_p3dx
    expose:
      - ${P3DX_PORT}  # Expose port internally to the network
    environment:
      REACT_APP_API_URL: http://${SERVER_HOST}${PLANTDB_PREFIX}
      REACT_APP_BASENAME: ${P3DX_PREFIX}
      # Tells the development server to serve assets from the subdirectory
      PUBLIC_URL: ${P3DX_PREFIX}
      # Tells the dev server where to listen for WebSockets
      WDS_SOCKET_PATH: ${P3DX_PREFIX}/sockjs-node
    restart: unless-stopped
    networks:
      - plantimager-net
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:${P3DX_PORT}${P3DX_PREFIX}" ]
      interval: 120s
      timeout: 10s
      retries: 3
      start_period: 40s

  p3dv:
    # P3DV service, in production mode, served by Gunicorn
    build:
      context: plant-3d-vision/
      dockerfile: docker/Dockerfile
      args:
        COLMAP_VERSION: ${COLMAP_VERSION:-'3.8'}
        CUDA_CC: ${CUDA_CC:-'75'}
        P3DV_BASE_IMG: ${P3DV_BASE_IMG}
    image: roboticsmicrofarms/plant-3d-vision:colmap_${COLMAP_VERSION:-'3.8'}
    container_name: plantimager_p3dv
    expose:
      - ${P3DV_PORT}  # Expose port internally to the network
    environment:
      PLANTDB_API: ${PLANTDB_HOST}/${PLANTDB_PREFIX}
      WEBTERM_PROXY: true
      WEBTERM_PREFIX: ${P3DV_PREFIX}
    command: [ "gunicorn \
               --worker-class eventlet \
               -w 1 \
               --bind 0.0.0.0:${P3DV_PORT} \
               plant3dvision.webterm.wsgi:application" ]
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [ gpu ]
    volumes:
      - ${ROMI_DB}:/myapp/db
      - p3dv_cfg:/myapp/cfg
      - webterm_users:/myapp/users
    networks:
      - plantimager-net

  # WebUI is served from the RasPi controller, use this for development purposes
  webui:
    build:
      context: Plant-Imager3/  # Build context for the WebUI service
      dockerfile: docker/webui/Dockerfile  # Specify the Dockerfile for building the image
      args:
        PLANTDB_BRANCH: 'feature/authentication'
    image: roboticsmicrofarms/plantimager_webui:latest
    container_name: plantimager_webui
    environment:
      ALLOW_PRIVATE_IP: true  # use true for tests with 'localhost'
      CERT_PATH: /etc/nginx/ssl/cert.pem  # self-signed certificate for SSL/TLS verification
      PLANTDB_HOST: ${SERVER_HOST}
      PLANTDB_PORT: ${PLANTDB_PORT}
      PLANTDB_PREFIX: ""
      PLANTDB_SSL: true
      WEBUI_PROXY: true
      WEBUI_PREFIX: ${CONTROLLER_PREFIX}
    command: [ "uwsgi \
               --http=:${CONTROLLER_PORT} \
               --module=plantimager.webui.wsgi:application \
               --callable=application \
               --master \
               --processes=4 --threads=2 --buffer-size=32768" ]
    restart: unless-stopped
    extra_hosts:
      - "dev.romi.local:host-gateway"
    volumes:
      - nginx_cert:/etc/nginx/ssl/
    networks:
      - plantimager-net
    depends_on:
      - ssl_cert

networks:
  plantimager-net:
    driver: bridge

volumes:
  nginx_cert:
    external: false
  uwsgi_sockets:
    external: false
  romi_db_test: # This volume hosts PlantDB FSDB files
    external: false  # set to `true` use an existing volume
  p3dv_cfg: # This volume hosts P3DV WebTerm configuration files
    external: false  # set to `true` use an existing volume
  webterm_users: # This volume hosts P3DV WebTerm users database
    external: false  # set to `true` use an existing volume

```

## Getting the Stack Running (Development)

```shell
# 1. Ensure Docker is running
docker compose version

# 2. Build and start all services
docker compose up --build
```

* Docker will build each image (or pull if already available).
* The `nginx` container will wait for the other services to be healthy before starting to accept traffic.

Open your browser at `http://plantimager.local` (or
`https://plantimager.local` if you add proper certificates). You should see the Plant‑Imager WebUI. The other services are accessible through the following URLs:

| URL        | Service           |
|------------|-------------------|
| `/webui`   | WebUI (frontend)  |
| `/plantdb` | REST API          |
| `/p3dx`    | 3D Explorer       |
| `/p3dv`    | 3D Vision WebTerm |
