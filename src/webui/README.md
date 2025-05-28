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
If you don't have`miniconda3` installed, please refer to the [official documentation](https://docs.conda.io/en/latest/miniconda.html).

To create a new conda environment:
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


## Development

To run the app in development mode, you have two options:
1. **Using the command-line interface:**
You can simply run the following command:
``` shell
   plant-imager-webui
```
This command is a convenience wrapper that sets up the necessary environment and starts the application.
2. **From the root directory of the repository:**
If you prefer to run the app directly from the source code, navigate to the root directory of the repository and execute:
``` shell
   python src/webui/plantimager/webui/app.py
```

Both methods will start the Dash-based web application in development mode, which includes features like automatic code reloading and detailed error messages, making it easier to develop and test your application efficiently.

## Production

### Running with uWSGI
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

### Additional Production Settings

For improved performance in production, consider these additional options:
```shell
uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master --processes 4 --threads 2 --thunder-lock
```

- `--processes 4`: Run 4 worker processes to handle requests in parallel
- `--threads 2`: Use 2 threads per worker process for additional concurrency
- `--thunder-lock`: Use a more efficient lock mechanism for multi-process deployments
