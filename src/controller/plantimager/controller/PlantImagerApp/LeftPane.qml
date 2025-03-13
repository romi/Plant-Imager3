import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P
import PlantImagerApp as P

Control {
    id: _self

    ListView {
        anchors.fill: parent

        model: P.AppBridge.deviceList
        delegate: P.CameraDelegate
        onCurrentItemChanged: {
            if(currentIndex>=0) {
                P.AppBridge.currentCamera = currentItem.bridge
            }
        }
    }
}