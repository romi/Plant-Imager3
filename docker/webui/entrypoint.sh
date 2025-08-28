#!/bin/bash

# Activate the virtual environment
source /home/${USER_NAME}/venv/bin/activate
# Start the WebUI App
exec uwsgi --http :${SERVER_PORT} --module plantimager.webui.wsgi:application --callable application --master