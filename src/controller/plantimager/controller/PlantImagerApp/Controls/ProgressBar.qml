import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Style as P


Control {
    id: root

    property real from: 0.0
    property real to: 1.0
    property real value: 0.0

    implicitHeight: label.contentHeight


    Label {
        id: label

        anchors.top: parent.top
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: Math.max(contentWidth, P.Style.progressBarLabelWidth)

        font: P.Style.fonts.label
        text: Math.round((root.value - root.from)/root.to*100).toString() + "%"
        verticalAlignment: Text.AlignVCenter

    }

    ProgressBar {
        id: pbar
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.left: label.right
        anchors.leftMargin: P.Style.mediumMargin
        Layout.fillHeight: true
        Layout.fillWidth: true
        from: root.from
        to: root.to
        value: root.value
    }
}