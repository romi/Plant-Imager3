# Test notebook

## Generate a video stream with ffmpeg

### 1. `mpegts` stream

```shell
ffmpeg -f lavfi -i testsrc=duration=300:size=1280x720:rate=30 -framerate 30 -map v -c:v libx264 -preset ultrafast -crf 22 -f mpegts -vf format=yuv420p tcp://0.0.0.0:8888\?listen=1
```

 - `-f lavfi` : selects Libavfilter input virtual device
 - `-i testsrc=duration=30:size=1280x720:rate=30` : configures input as `testsrc` video pattern
with a duration of 30 seconds, a size of 1280x720 and a framerate of 30 ([link](https://www.bogotobogo.com/FFMpeg/ffmpeg_video_test_patterns_src.php))
 - `-framerate 30` sets input framerate to 30
 - `-map v` : maps video input for to further treatments (here just output)
 - `-c:v libx264` : selects video codec to use h264 encoding ([link](https://trac.ffmpeg.org/wiki/Encode/H.264))
 - `-preset ultrafast -crf 22` : h264 codec parameters (ultrafast encoding and quality)
 - `-f mpegts` : sets output format as mpeg transport stream (MPEG-TS)
 - `-vf format=yuv420p` use pixel format `yuv42p` for output color
 - `tcp://0.0.0.0:8888\?listen=1` : output on a tcp socket and tells ffmpeg to listen for 1 
connection on any interface on the port 8888

#### `mpegts` playback with gstreamer

`gst-plugins-bad` needs to be installed

```shell
gst-launch-1.0 tcpclientsrc host=127.0.0.1 port=8888 ! tsparse set-timestamps=true ! video/mpegts ! tsdemux ! video/x-h264 ! h264parse ! decodebin ! videoconvert ! glimagesink
```

### 2. `h264` stream

```shell
ffmpeg -f lavfi -i testsrc=duration=30:size=1280x720:rate=30 -map v -c:v libx264 -preset ultrafast -crf 22 -f h264 tcp://0.0.0.0:10001\?listen=1
```


