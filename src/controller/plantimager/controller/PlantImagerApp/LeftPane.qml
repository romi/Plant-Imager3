import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P
import PlantImagerApp as P

Control {
    id: _self

    ColumnLayout {
        id: layout

        anchors.fill: parent

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
        }
    }


}