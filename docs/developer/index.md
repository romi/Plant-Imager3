# Developer Documentation

This section contains information for developers working on the Plant-Imager3 project.

## Project Structure

The Plant-Imager3 project is organized as a collection of Python namespace packages:

- `plantimager.commons`: Common utilities and interfaces
- `plantimager.controller`: Main control interface and hardware abstraction
- `plantimager.picamera`: Camera functionality for Raspberry Pi Zero W
- `plantimager.webui`: Web-based user interface

## Development Environment

### Quick Setup

To quickly set up the development environment for Plant-Imager3, use the following comprehensive setup script:

```shell
# Create a new Conda environment with Python 3.11 and IPython
conda create -n plant-imager3 'python==3.11' ipython -y
# Activate the newly created environment
conda activate plant-imager3

# Install project subpackages in editable mode
pip install -e src/commons/.
pip install -e src/controller/.
pip install -e src/picamera/.

# Install plantdb server dependencies
pip install plantdb.server
```

### System Requirements

To run the QtApp, you must install the required Mesa packages.
On Ubuntu, you can do this by executing the following commands:

```shell
sudo apt update
sudo apt install libegl1-mesa libgl1-mesa-dri libgl1-mesa-glx mesa-utils
```

## Documentation

The documentation for Plant-Imager3 is built using [MkDocs](https://www.mkdocs.org/) with the [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme.

### Building the Documentation

To build the documentation locally, follow these steps:

1. Install the required dependencies:
   ```shell
   pip install mkdocs mkdocs-material mkdocs-gen-files mkdocs-literate-nav mkdocs-section-index mkdocstrings mkdocstrings-python markdown-exec
   ```

2. Build the documentation:
   ```shell
   mkdocs build
   ```

3. Serve the documentation locally:
   ```shell
   mkdocs serve
   ```

4. Open your browser and navigate to [http://localhost:8000](http://localhost:8000)

### Documentation Structure

The documentation is organized as follows:

- **Home**: Overview of the project
- **Reference API**: Automatically generated API documentation
- **Developer**: Information for developers