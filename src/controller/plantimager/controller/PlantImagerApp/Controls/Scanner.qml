import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P
import PlantImagerApp as P

Control {
    id: self_
    property object scanner: P.AppBridge.scanner

    ProgressBar {
        id: progress

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom

        to: scanner.max_progress
        value: scanner.progress
    }
}