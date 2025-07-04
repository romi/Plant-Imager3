import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P
import PlantImagerApp as P

Control {
    id: _self

    StackLayout {
        id: stack
        anchors.fill: parent

        currentIndex: 0

        ColumnLayout {
            id: layout

            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true

                model: P.AppBridge.deviceList

                delegate: P.CameraDelegate {

                }
                onCurrentItemChanged: {
                    if(currentIndex>=0) {
                        P.AppBridge.currentCamera = currentItem.bridge
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "transparent"
                border.width: 1
                border.color: "black"
            }

            P.Scanner {
                id: scanner_pannel
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.cameraDelegateHeight*3
                Layout.minimumHeight: P.Style.cameraDelegateHeight*2

                scanner: P.AppBridge.scanner

                onSwitchToCncPanel: stack.currentIndex = 1
            }
        }

        Control {
            id: cnc_panel
            Layout.fillWidth: true
            Layout.fillHeight: true

            Label {
                id: cnc_panel_title
                anchors.top: parent.top
                anchors.left: parent.left
                height: P.Style.mediumHeight

                text: "CNC Panel"
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignLeft;
                leftPadding: P.Style.largeMargin

                font: P.Style.fonts.header
            }

            P.IconButton {
                id: close_panel
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.rightMargin: P.Style.mediumMargin
                height: P.Style.mediumHeight

                iconName: P.Icons.icons["close"]
                color: P.Style.colors.foreground
                hoverColor: P.Style.colors.accent
                size: P.Style.iconMedium

                onClicked: {
                    stack.currentIndex = 0
                }
            }

            P.CncPanel {
                anchors.top: cnc_panel_title.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
            }
        }
    }
}