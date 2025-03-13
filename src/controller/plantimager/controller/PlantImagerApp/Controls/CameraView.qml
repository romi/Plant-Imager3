import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P

Control {
    id: _self

    required property QtObject bridge

    Connections {
        target: bridge ? bridge : undefined
        ignoreUnknownSignals: true
        function onVideoReady() {
            receiver.play()
        }
    }

    Label {
        id: _title
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.leftMargin: P.Style.mediumMargin
        height: P.Style.bannerHeight
        text: bridge ? bridge.name : "Invalid"
        font: P.Style.fonts.header
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignLeft
        leftPadding: P.Style.smallMargin
    }

    StackLayout {
        id: media_control
        anchors.top: _title.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: P.Style.mediumMargin
        anchors.rightMargin: P.Style.mediumMargin
        height: Math.round(width/P.Style.videoRatio)

        VideoOutput {
            id: videoOutput
            Layout.fillWidth: true
            Layout.fillHeight: true

            Rectangle {
                anchors.fill: parent
                z: parent.z-1
                color: "black"
            }

            P.CameraVideoReceiver {
                id: receiver
                source: bridge ? bridge.videoSource : ""
                format: "mpegts"
                videoSink: videoOutput.videoSink
                autoPlay: false
                Component.onCompleted: {
                    componentComplete()
                }
            }

            StackLayout.onIsCurrentItemChanged: {
                if(StackLayout.isCurrentItem) {
                    receiver.autoPlay = true
                    receiver.play()
                } else {
                    receiver.autoPlay = false
                    receiver.stop()
                }
            }

        }

        Image {
            id: imageOutput
            Layout.fillWidth: true
            Layout.fillHeight: true

            Rectangle {
                anchors.fill: parent
                z: parent.z-1
                color: "black"
            }

            source: bridge ? bridge.imageSource : ""
            cache: false

        }
    }

    GridLayout {
        id: buttons_layout
        anchors.top: media_control.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: P.Style.mediumMargin

        rows: 2
        columns: 2
        uniformCellHeights: true
        uniformCellWidths: true
        rowSpacing: P.Style.smallMargin
        columnSpacing: P.Style.mediumMargin

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Video"
            onClicked: {
                bridge.startVideo()
                media_control.currentIndex = 0
            }
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Button 2"
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Image"

            onClicked: {
                bridge.stopVideo()
                media_control.currentIndex = 1
            }
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Take Picture"
            onClicked: {
                bridge.getImage()
            }
        }
    }
}