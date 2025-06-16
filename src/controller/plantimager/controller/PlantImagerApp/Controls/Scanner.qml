import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P

Control {
    id: self_
    property var scanner: P.AppBridge.scanner

    Label {
        id: cnc_type
        anchors.top: pareant.top
        anchors.left: parent.left
        anchors.right: parent.right

        text: scanner.cnc_type
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignLeft;
        padding: P.Style.smallMargin
        leftPadding: P.Style.largeMargin

        font: P.Style.fonts.header

    }

    P.ProgressBar {
        id: progress

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: P.Style.largeMargin

        to: scanner.max_progress
        value: scanner.progress
    }
}