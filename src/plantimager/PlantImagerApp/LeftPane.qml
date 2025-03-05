import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P

Control {
    id: _self

    ColumnLayout {
        id: clayout
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right


        P.CameraDelegate {
            id: camera2
            bridge: P.CameraBridge {
                Component.onCompleted: {
                    console.log("Camera Bridge ", name, status)
                }
            }

            Layout.fillWidth: true
            onClicked: {
                console.log("Select ", camera2.bridge.name)
            }
        }
    }

}