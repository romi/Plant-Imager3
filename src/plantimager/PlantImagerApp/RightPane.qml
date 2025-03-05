import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P

Control {
    id: _self


    StackLayout {
        id: stack_l
        anchors.fill: parent
        currentIndex: 0

        P.CameraView {
            Layout.fillWidth: true
            Layout.fillHeight: true

            bridge: P.CameraBridge {

            }
        }
    }
}