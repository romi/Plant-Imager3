# [![ROMI_logo](docs/assets/images/ROMI_logo_green_25.svg)](https://romi-project.eu) / plantimager.webui

[![Licence](https://img.shields.io/github/license/romi/plantdb?color=lightgray)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Python Version](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fromi%2Fplantdb%2Frefs%2Fheads%2Fdev%2Fsrc%2Fcommons%2Fpyproject.toml&logo=python&logoColor=white)]()

A Dash-based Python package for the main controller (Raspberry Pi 4 or 5).
It offers a client interface for plant scanning.

This package provides a web-based user interface for plant scanning:

- Dash-based web application
- Scan configuration and execution
- Integration with the controller package


## Environment Setup

We strongly recommend using isolated environments to install ROMI libraries.

This documentation uses `conda` as both an environment and package manager.
If you don't have `miniconda3` installed, please refer to the [official documentation](https://docs.conda.io/en/latest/miniconda.html).

To create a new conda environment, named `plant-imager3`, with Python3.11 & IPython:
``` shell
conda create -n plant-imager3 'python==3.11' ipython
```

## Installation

### Developer - Installing from Source Code

If you are a developer and need to work on the source code or make modifications, follow these steps:
1. **Activate your environment:** First, activate your conda environment:
    ``` shell
    conda activate plant-imager3  # Make sure your development environment is activated!
    ```
2. **Install from sources:** Install the package directly from the source directory using pip:
    ``` shell
    python -m pip install src/webui
    ```
This method allows you to work on the code and test changes locally before committing them.

### User - Installing via pip Package

For regular users who just need to use the application without modifying the source code, follow these steps:
1. **Activate your environment:** First, activate your conda environment:
    ``` shell
    conda activate plant-imager3  # Make sure your user environment is activated!
    ```
2. **Install via pip:** Install the package using pip from the Python Package Index (PyPI):
    ``` shell
    pip install plantimager.webui
    ```
This method installs a pre-built version of the application, making it quick and easy to set up.



## Usage

### Development

To run the app in development mode, you have two options:
1. **Using the command-line interface:** You can simply run the following command:
    ``` shell
    plant-imager-webui
    ```
2. **From the root directory of the repository:** If you prefer to run the app directly from the source code, navigate to the root directory of the repository and execute:
    ``` shell
    python src/webui/plantimager/webui/app.py
    ```

Both methods will start the Dash-based web application in development mode, which includes features like automatic code reloading and detailed error messages, making it easier to develop and test your application efficiently.

### Production

#### Running with uWSGI
`uWSGI` is a fast, self-healing, and extensively configurable application server that can serve Python applications.
It provides various features such as load balancing, process management, and more, making it well-suited for running web applications in a production environment.

To run the Dash app in production mode, you need to install `uwsgi`:
```shell
pip install uwsgi
```

Start the application with uWSGI using the following command:
```shell
uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master
```

Key parameters explained:
- `--http :8080`: Bind to port 8080 and handle HTTP requests directly
- `--module plantimager.webui.wsgi:application`: Path to the WSGI module and application object
- `--callable application`: Specify the WSGI callable name (application is the standard name)
- `--master`: Enable master process mode for better resource management and reliability

#### Additional Production Settings

For improved performance in production, consider these additional options:
```shell
uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master --processes 4 --threads 2 --thunder-lock
```

- `--processes 4`: Run 4 worker processes to handle requests in parallel
- `--threads 2`: Use 2 threads per worker process for additional concurrency
- `--thunder-lock`: Use a more efficient lock mechanism for multi-process deployments


#### Security Recommendations

1. **Use a volume for certificates** - This allows you to update certificates without rebuilding the container
2. **Use a proper certificate authority** - Let's Encrypt is free and widely trusted
3. **Set up auto-renewal** - Let's Encrypt certificates expire after 90 days
4. **Use strong SSL settings** - As included in the configuration

## Docker

### Build Image
To build the `roboticsmicrofarms/plantimager_webui` docker image, you may use the convenience `build.sh` script.
This will create a Docker image with everything needed to run the web UI.

1. Open your terminal.
2. Run the following command:
   ```shell
   ./docker/webui/build.sh -t latest
   ```

This command uses the build script located in the `./docker/webui/` directory to create the Docker image and tags it as "latest".

### Start a Container

Once you've built the Docker image, you can run it as a container. This will start the web UI application.

1. Open your terminal.
2. Run the following command:
    ```shell
    docker run -it --rm --name plantimager_webui -p 8080:8080 roboticsmicrofarms/plantimager_webui:latest "uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master  --processes 4 --threads 2 --thunder-lock"
    ```

Let's break down what this command does:
- `docker run`: This starts a new Docker container.
- `-it`: This runs the container in interactive mode with a terminal attached.
- `--rm`: This automatically removes the container when it stops.
- `--name plantimager_webui`: This gives your container a name, making it easier to manage.
- `-p 8080:8080`: This maps port 8080 on your local machine to port 8080 in the Docker container, so you can access the web UI.
- `roboticsmicrofarms/plantimager_webui:latest`: This specifies which Docker image to use (the one we built earlier).
- `"uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master"`: These are the parameters that start the web server inside the container.

After running this command, you should be able to access the web UI by opening your browser and navigating to `http://localhost:8080/webui`.

If you encounter any issues or need further assistance, please refer to the [Docker documentation](https://docs.docker.com/) for more details.


## Let's Encrypt Certificates

Let's Encrypt is a free, automated, and open Certificate Authority that provides TLS certificates trusted by all major browsers.

### How Let's Encrypt Works
1. **Domain Validation**: Let's Encrypt validates that you control a domain before issuing a certificate
2. **Automated**: The entire process can be automated using the Certbot client
3. **Short Validity**: Certificates are valid for 90 days to encourage automation
4. **Renewal**: Certificates must be renewed before expiration

### Setting Up Let's Encrypt with NGINX in Docker

#### Method 1: Using Certbot with Docker

1. **Create a Docker network for your services**:
   ``` bash
   docker network create web
   ```
1. **Run Certbot in Docker to obtain certificates**:
   ``` bash
   docker run -it --rm \
     -v /etc/letsencrypt:/etc/letsencrypt \
     -v /var/lib/letsencrypt:/var/lib/letsencrypt \
     -p 80:80 \
     certbot/certbot certonly --standalone \
     -d yourdomain.com --agree-tos -m your-email@example.com
   ```
1. **Mount the certificates in your NGINX container**:
   ``` bash
   docker run -d \
     -v /etc/letsencrypt:/etc/letsencrypt \
     -p 80:80 -p 443:443 \
     --network web \
     your-nginx-image
   ```
1. **Update your NGINX configuration to use the certificates**:
   ``` nginx
   ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
   ```

#### Method 2: Using Docker Compose with Nginx and Certbot

``` yaml
services:
  nginx:
    image: your-nginx-image
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    command: "/bin/sh -c 'while :; do sleep 6h & wait $${!}; nginx -s reload; done & nginx -g \"daemon off;\"'"
    
  certbot:
    image: certbot/certbot
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

### Let's Encrypt Certificate Renewal

Certificates expire after 90 days and must be renewed. Set up automatic renewal:
1. **Using a Cron Job on the Host**:
   ``` 
   0 12 * * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt certbot/certbot renew --quiet && docker exec nginx nginx -s reload
   ```
2. **Using a Docker Container** (as shown in Docker Compose example above)

### Testing Your SSL Configuration

After setting up, test your SSL configuration using:
1. **SSL Labs**: [https://www.ssllabs.com/ssltest/](https://www.ssllabs.com/ssltest/)
2. **Mozilla Observatory**: [https://observatory.mozilla.org/](https://observatory.mozilla.org/)

These tools will analyze your HTTPS implementation and suggest improvements.