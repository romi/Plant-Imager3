#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#  Copyright (c) 2022 Univ. Lyon, ENS de Lyon, UCB Lyon 1, CNRS, INRAe, Inria
#  All rights reserved.
#  This file is part of the TimageTK library, and is released under the "GPLv3"
#  license. Please see the LICENSE.md file that should have been included as
#  part of this package.
# ------------------------------------------------------------------------------

"""WSGI Entry Point for Plant Imager Web Interface

This module provides the WSGI entry point to run the Plant Imager web application using a WSGI-compatible server.
It sets up the Dash web application and configures it to connect with the REST API backend.

Key Features
------------
- Configures and initializes the Plant Imager Dash application for WSGI deployment
- Sets up the correct URL base path name for the application
- Allows for custom configuration of the server host, port, and proxy settings

Usage Examples
--------------
Run the web interface with default REST API settings using a WSGI server like uWSGI
```shell
uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master
```

Run with Gunicorn
```shell
gunicorn wsgi:application
```

Direct call with Python for development purposes:
```shell
python src/webui/plantimager/webui/wsgi.py
```
Should then be accessible under: https://localhost:8080/webui/
"""
from threading import Thread

import zmq

from plantdb.client.plantdb_client import api_prefix
from plantimager.webui.app import setup_web_app
from plantimager.webui.controller_proxy import RPCController

# - Create connexion with controller
context = zmq.Context()
controller_thread = Thread(target=lambda ctx: RPCController(ctx, "tcp://localhost:14567"), args=(context,))
controller_thread.daemon = True
controller_thread.start()

# Get the Dash application
dash_app = setup_web_app("localhost", 8080, api_prefix(), proxy=True)
# Use the Flask server attribute of the Dash application
application = dash_app.server

if __name__ == "__main__":
    from werkzeug.serving import run_simple

    # SSL context for development testing
    ssl_context = ('docker/nginx/ssl/cert.pem', 'docker/nginx/ssl/key.pem')
    run_simple('localhost', 8080, application, ssl_context=ssl_context)
