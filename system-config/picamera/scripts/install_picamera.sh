#!/usr/bin/sh

if [ "$1" ]; then
  user=$1
else
  user="romi"
fi

if [ -d "/home/$user" ]; then
    echo "No directory /home/{$user} found"
    exit 1
fi

cd "/home/$user" || exit 1

echo "installing dependencies"

sudo apt install git libzmq python3-zmq python3.11-dev ffmpeg libcap-dev python3-av python3-pil libturbojpeg0 libjpeg7 python3-libcamera python3-kms++

echo "creating virtual env"
python3 -m venv --system-site-packages --symlinks picamera-env

echo 'installing Plant_Imager3'
if [ -d "Plant-Imager3" ]
then
  (
  cd Plant_Imager3 || exit 1
  git fetch --all
  git checkout main
  git pull
  )
else
  git clone https://github.com/romi/Plant-Imager3.git
fi
picamera-env/bin/pip install Plant-Imager3/src/commons
picamera-env/bin/pip install Plant-Imager3/src/picamera

echo "installing picamera-server.service"
mkdir -p .config/systemd/user
copy Plant_Imager3/system-config/picamera/services/picamera-server.service .config/systemd/user/picamera-server.service

loginctl enable-linger "$user"
systemctl --user daemon-reload
systemctl --user enable picamera-server.service
systemctl --user start picamera-server.service

