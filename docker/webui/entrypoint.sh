#!/bin/bash

# Activate the virtual environment
source /home/romi/venv/bin/activate
# Start the WebUI App
#exec uwsgi --http :${SERVER_PORT:-8080} --module plantimager.webui.wsgi:application --callable application --master --processes=4 --threads=2 --buffer-size=32768
# Execute whatever command was passed to the container
/bin/bash -c "$@"