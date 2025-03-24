import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp.Camera as P
import PlantImagerApp as P

ItemDelegate {
    id: _self

    property QtObject bridge: P.AppBridge.getCameraBridgeAtIndex(index)

    height: P.Style.cameraDelegateHeight
    width: ListView.view.width

    highlighted: ListView.isCurrentItem

    onClicked: {
        ListView.view.currentIndex = index
    }

    background: Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: P.Style.colors.foreground
    }

    Label {
        id: _title
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.bottom: parent.verticalCenter
        anchors.leftMargin: P.Style.mediumMargin
        verticalAlignment: Text.AlignVCenter
        leftPadding: P.Style.smallMargin

        text: bridge.name
        font: P.Style.fonts.header
    }
    P.Icon {
        id: _status_icon
        anchors.top: _title.bottom
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: P.Style.mediumMargin
        size: P.Style.iconSmall
        icon: getStatusIcon()
        color: getStatusColor()
    }
    Label {
        id: _status
        anchors.top: _title.bottom
        anchors.left: _status_icon.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: P.Style.smallMargin

        verticalAlignment: Text.AlignVCenter
        text: bridge.status
        font: P.Style.fonts.label
        color: getStatusColor()
    }

    P.Icon {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.rightMargin: P.Style.mediumMargin
        //width: height

        icon: _self.ListView.isCurrentItem ? P.Icons.icons["triangle"] : P.Icons.icons["triangle-outline"]
        //icon:  P.Icons.icons["triangle"]
        color: P.Style.colors.foreground
        size: P.Style.iconMedium
        rotation: 90
    }


    function getStatusIcon() {
        if(bridge.statusClass === "ok") {
            return P.Icons.icons["check-circle"]
        } else if(bridge.statusClass === "error") {
            return P.Icons.icons["alert-circle"]
        } else {
            return P.Icons.icons["panorama-fisheye"]
        }
    }

    function  getStatusColor() {
        if(bridge.statusClass === "ok") {
            return P.Style.colors.okColor
        } else if(bridge.statusClass === "error") {
            return P.Style.colors.alertColor
        } else {
            return P.Style.colors.neutralColor
        }
    }
}