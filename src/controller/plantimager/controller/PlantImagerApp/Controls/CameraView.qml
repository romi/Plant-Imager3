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

    onBridgeChanged: {
        if(bridge !== undefined && bridge !== null) {
            if(bridge.mode === "STILL") {
                video_button.checked = false
                image_button.checked = true
            } else if(bridge.mode === "VIDEO") {
                image_button.checked = false
                video_button.checked = true
            }
        }
        //focus_highlight_button.text = bridge.displayMode ? bridge.displayMode : " "
    }

    Connections {
        target: bridge
        ignoreUnknownSignals: false
        function onVideoReady() {
            receiver.play()
        }
        function onModeChanged() {
            if(bridge.mode === "STILL") {
                video_button.checked = false
                image_button.checked = true
            } else if(bridge.mode === "VIDEO") {
                image_button.checked = false
                video_button.checked = true
            }
        }
    }

    Label {
        id: _title
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.leftMargin: P.Style.mediumMargin
        height: P.Style.bannerHeight
        text: bridge ? (bridge.name ? bridge.name : "No Camera connected" ): "Invalid"
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
                rotation: bridge ? bridge.rotation : 0
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
            fillMode: Image.PreserveAspectFit

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
            id: video_button
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Video"
            autoExclusive: true
            checkable: true
            checked: false
            enabled: bridge ? bridge.status === "connected" : false
            onClicked: {
                bridge.mode = "VIDEO"
            }
            onCheckedChanged: {
                if(checked) {
                    media_control.currentIndex = 0
                }
            }
        }

        Button {
            id: focus_highlight_button
            Layout.fillWidth: true
            Layout.fillHeight: true
            enabled: bridge ? bridge.status !== "invalid" : false
            text: bridge ? bridge.displayMode : ""
            onClicked: {
                if(bridge) {
                    bridge.nextDisplayMode()
                }
            }
        }

        Button {
            id: image_button
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "Image"
            autoExclusive: true
            checkable: true
            checked: false
            enabled: bridge ? bridge.status === "connected" : false

            onClicked: {
                bridge.mode = "STILL"
            }
            onCheckedChanged: {
                if(checked) {
                    media_control.currentIndex = 1
                }
            }
        }

        Button {
            Layout.fillWidth: true
            Layout.fillHeight: true
            enabled: bridge ? bridge.status === "connected" : false
            text: "Take Picture"
            onClicked: {
                bridge.getLoresImage()
            }
        }
    }
}