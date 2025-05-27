# PlantImager NGINX

This Docker container runs an NGINX server configured as a reverse proxy for the PlantImager project.

The purpose of this proxy is to route incoming requests to appropriate backend services, making it easier to access different components through friendly URLs.

## Proxy Configuration

The NGINX reverse proxy is configured to route requests as follows:

- **Test endpoint**: `/test` returns a simple status message for testing purposes.
- **PlantDB service**: Requests to `/plantdb` are proxied to `http://localhost:5000`.
- **WebUI service**: Requests to `/webui` are proxied to the controller URL and port specified during build time.

This setup allows you to access different components of your application through a single entry point, improving the organization and accessibility of your services.

## Build the docker image

To build the Docker image, you need to specify:
- the URL of the nginx server;
- the URL of the controller (serving the webui);
- the port of the controller.

```shell
cd docker/nginx
sudo docker build \
  --build-arg SERVER_URL='server_url.com' \
  --build-arg CONTROLLER_URL='controller_url.com' \
  --build-arg CONTROLLER_PORT='8080' \
  -t roboticsmicrofarms/plantimager_nginx:latest .
```

## Run a container

After building the image, you can run the container with the following command:

```shell
sudo docker run --name plantimager_nginx \
  -p 8080:8080 -p 80:80 \
  roboticsmicrofarms/plantimager_nginx:latest
```