# Picamera stream experiments

## Capture and stream formats

There are multiple examples that can be found online
and in the picamera2 examples which outputs a variety 
of different stream and video formats.

### Sending raw h264 over a socket

This simply uses the h264 encoder included in the picamera2
 library to encode the video, then it opens a socket and
dumps the encoded video in the socket as a `FileOutput`.

Sender files are either `capture_stream.py` to send over tcp
or `capture_stream_udp.py` to send over udp (didn't make
it work yet)

Receive video with `netcat` and `mplayer` on Linux (for tcp example)
```shell
nc picamera2.wlan 10001 | mplayer -fps 200 -demuxer h264es -
```

Or with `ffmpeg` / `ffplay`
```shell
ffplay -f h264 -codec:v h264 -fflags nobuffer -i tcp://picamera2.wlan:10001
```


**Pros**
 - fast
 - low latency (dependent on buffering)
 - simple on the sender side

**Cons**
 - Needs manual decoding for most video player
 - Average video quality (might be fixable with better settings)

Decoding possible with `ffmpeg` or `pyav` frame by frame
 or possibly as a pipe with `ffmpeg`

### Sending h264 in a MPEG-TS (MPEG Transport Stream)

file: `pyav_stream.py`

Uses `PyavOutput` to mux the h264 encoded video in an MPEG Transport Stream
and opening a tcp server which will listen for a client
connection before sending the stream over a socket.

Receive with `netcat` and `mplayer`
```shell
nc picamera2.wlan 8888 | mplayer -fps 200 -demuxer mpegts -
```

Or receive with `ffmpeg` / `ffplay`:
```shell
ffplay -f mpegts -fflags nobuffer -i tcp://picamera2.wlan:8888
```

Or with vlc:
open address `tcp://picamera2.wlan:8888`

**Pros**
 - fast
 - low latency (dependent on buffering)
 - error corrections
 - encapsulated video format --> wider support for players

**Cons**
 - ?

### MJPEG HTTP server

file: `mjpeg_server.py`

Hosts an HTTP server which will serve a page with an image frame.
Each time a new frame is ready, the server will send the 
jpeg encoded frame marked with `'Content-Type', 'multipart/x-mixed-replace; boundary=FRAME'`
in the header. This will replace the old jpeg frame by the new one
on the page.

In essence: sends a new jpeg image each time a new one is ready.

Receive by accessing the page at http://picamera2.wlan:8000/

**Pros**
 - Conceptually easy
 - low latency (no buffering)
 - view in a web browser

**Cons**
 - not really a video format
 - not really mjpeg (which is a real but different format)

Could scrap the web page view but still send jpegs as video streaming
to an application.

### Streaming through a media server

file: `picam_stream.py`

Use a media server (MediaMTX) to which we publish a stream with
the `rtsp` protocol.

Encodes the captured video in h264 then uses `FFMpegOutput`
to encapsulate the video with the `rtsp` protocol and
publishes the stream to the `MediaMTX` server.

To receive, connect to the media server at the right path.

To launch:
```shell
cd mediamtx
./mediamtx
```

See more at:
 - https://www.wtip.net/blog/2023/07/picamera2-rtsp-streaming-with-multiple-resolution-feeds/
 - https://github.com/bluenviron/mediamtx

Receive with vlc:
open address: `rtsp://picamera2.wlan:8554/hqstream`

Receive with ffplay:
```shell
ffplay -max_delay 500000 -rtsp_transport udp rtsp://picamera2.wlan:8554/hqstream
```

**Pros**
 - 

