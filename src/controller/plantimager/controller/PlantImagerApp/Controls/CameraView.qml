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

    Label {
        id: _title
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.leftMargin: P.Style.mediumMargin
        height: P.Style.bannerHeight
        text: bridge.name
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

            P.CameraReceiver {
                id: receiver
                source: "tcp://Picamera2.wlan:8888"
                format: "mpegts"
                videoSink: videoOutput.videoSink
                autoPlay: false
                Component.onCompleted: {
                    componentComplete()
                }
            }
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
            text: "Button 1"
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Button 2"
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Button 3"
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Button 4"
        }

    }

}