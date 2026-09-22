import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P

Control {
    id: self_
    property var scanner: P.AppBridge ? P.AppBridge.scanner : null
    signal switchToCncPanel()

    Label {
        id: cnc_type
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right

        text: scanner ? scanner.cnc_type : ""
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignLeft;
        padding: P.Style.smallMargin
        leftPadding: P.Style.largeMargin

        font: P.Style.fonts.header

    }

    Button {
        id: cnc_panel_open_button
        anchors.top: cnc_type.bottom
        anchors.left: parent.left
        anchors.margins: P.Style.mediumMargin

        text: "CNC Panel"
        enabled: scanner ? (scanner.cnc_type === "GRBL CNC" && !scanner.scanInProgress || true) : false

        onClicked: switchToCncPanel()

    }

    P.ProgressBar {
        id: progress

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: P.Style.largeMargin

        to: scanner ? scanner.max_progress : 1
        value: scanner ? scanner.progress : 0
    }
}