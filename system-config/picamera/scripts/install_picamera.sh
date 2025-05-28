#!/usr/bin/sh

echo "$# $0 $1 $2 $3 $4"

if [ "$#" -ne 3 ]; then
    echo "Expected 3 arguments: user, registry ip:port, self ip address"
    exit 1
fi


if [ "$1" ]; then
  user=$1
else
  user=$USER
fi

registry_address="$2"
self_ip="$3"

if [ ! -d "/home/$user" ]; then
    echo "No directory /home/$user found"
    exit 1
fi

cd "/home/$user" || exit 1

systemctl --user is-active --quiet picamera-server.service && systemctl --user stop picamera-server.service

echo "installing dependencies"

sudo apt update
sudo apt install git python3-zmq python3.11-dev ffmpeg libcap-dev python3-av python3-pil libturbojpeg0 libjpeg7 python3-libcamera python3-kms++ || exit 1

if [ ! -d "/home/$user/picamera-env" ]
then
  echo "creating virtual env"
  python3 -m venv --system-site-packages --symlinks picamera-env || exit 1
fi

echo 'installing Plant_Imager3'
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

picamera-env/bin/pip install Plant-Imager3/src/commons || exit 1
picamera-env/bin/pip install Plant-Imager3/src/picamera || exit 1

echo "installing picamera-server.service"
mkdir -p .config/systemd/user
cp Plant-Imager3/system-config/picamera/services/picamera-server.service .config/systemd/user/picamera-server.service

sed -i "s/PI_REGISTRY=.*/PI_REGISTRY=$registry_address/" .config/systemd/user/picamera-server.service
sed -i "s/IP_ADDR=.*/IP_ADDR=$self_ip/" .config/systemd/user/picamera-server.service
sed -i "s/ExecStart=\/home\/.*\/picamera-env\/bin\/picamera-server/ExecStart=\/home\/$user\/picamera-env\/bin\/picamera-server/" .config/systemd/user/picamera-server.service

loginctl enable-linger "$user"
systemctl --user daemon-reload
systemctl --user enable picamera-server.service
systemctl --user start picamera-server.service

