#!/usr/bin/bash

# Format text in bold for better visibility in terminal output
bold() {
    echo -e "\033[1m$1\033[0m"
}

# Display comprehensive help information about script usage and arguments
show_usage() {
  echo -e "$(bold USAGE):"
  echo "  $0 [user] <registry_address> <self_ip>"
  echo ""

  echo -e "$(bold DESCRIPTION):"
  echo "  Install and configure the PiCamera server on a Raspberry Pi device.
  This script installs necessary dependencies, sets up a Python virtual environment,
  clones the Plant-Imager3 repository, and configures the picamera-server as a systemd service."
  echo ""

  echo -e "$(bold ARGUMENTS):"
  echo "  user
    Optional: Username to install for (defaults to current user: $USER)."
  echo "  registry_address
    Mandatory: Address of the registry server in format ip:port."
  echo "  self_ip
    Mandatory: IP address of this device."
  echo ""

  echo -e "$(bold EXAMPLES):"
  echo "  $0 pi 192.168.1.100:5000 192.168.1.101"  # Example with specified user
  echo "  $0 10.0.0.5:5000 10.0.0.10"              # Example using current user
  echo ""

  echo -e "$(bold NOTE):"
  echo "  The script must be run as a user with sudo privileges."
}

# Show help and exit if -h or --help flag was provided
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage
    exit 0
fi

# Validate that correct number of arguments are provided (2-3 args required)
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "$(bold ERROR): Incorrect number of arguments."
    show_usage
    exit 1
fi

# Parse input arguments based on count
if [ "$#" -eq 2 ]; then
    # Two arguments mode: use current user
    user=$USER
    registry_address="$1"
    self_ip="$2"
else
    # Three arguments mode: use specified user
    user="$1"
    registry_address="$2"
    self_ip="$3"
fi

# Ensure target user's home directory exists
if [ ! -d "/home/$user" ]; then
    echo "$(bold ERROR): No directory /home/$user found"
    exit 1
fi

# Change to user's home directory
cd "/home/$user" || exit 1

# Stop existing services if running (user units from pre-step-13 installs
# as well as the current system units).
systemctl --user is-active --quiet picamera-server.service && systemctl --user stop picamera-server.service
systemctl is-active --quiet picamera-server.service && sudo systemctl stop picamera-server.service
systemctl is-active --quiet picamera-mqtt-agent.service && sudo systemctl stop picamera-mqtt-agent.service

echo "installing dependencies"
# Update apt and install required system packages
sudo apt update
sudo apt install git python3-zmq python3.11-dev ffmpeg libcap-dev python3-av python3-pil libturbojpeg0 libjpeg7 python3-libcamera python3-kms++ || exit 1

# Create Python virtual environment if it doesn't exist
# --system-site-packages allows access to system Python packages
# --symlinks uses symlinks instead of copies for better disk usage
if [ ! -d "/home/$user/picamera-env" ]
then
  echo "creating virtual env"
  python3 -m venv --system-site-packages --symlinks picamera-env || exit 1
fi

echo 'installing Plant_Imager3'
# Clone or update the Plant-Imager3 repository
if [ -d "Plant-Imager3" ]
then
  (
  cd Plant-Imager3 || exit 1
  #git fetch --all
  #git checkout main
  #git pull
  )
else
  git clone https://github.com/romi/Plant-Imager3.git
fi

# Install required Python packages from the cloned repository
picamera-env/bin/pip install Plant-Imager3/src/commons || exit 1
picamera-env/bin/pip install Plant-Imager3/src/picamera || exit 1

echo "installing picamera systemd services"
# System unit files, daemon-reload, enable and start are handled by
# the picamera-install entry point (templates live in the package).
# It writes to /etc/systemd/system, so it needs sudo.
sudo picamera-env/bin/picamera-install --user "$user" --registry "$registry_address" --ip "$self_ip" --start || exit 1


