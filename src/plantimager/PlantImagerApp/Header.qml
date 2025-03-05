import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P


Control {
    id: _control
    height: P.Style.bannerHeight


    background: Rectangle {
        anchors.fill: parent
        color: P.Style.colors.accent
    }

    Label {
        id: _title
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: P.Style.mediumMargin
        text: "ROMI Plant-Imager v3"
        font: P.Style.fonts.title
        color: P.Style.colors.lightText
    }

    P.IconButton {
        id: _shutdown_menu_button
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.rightMargin: P.Style.mediumMargin
        iconName: P.Icons.icons["power"]
        color: P.Style.colors.lightText
        hoverColor: P.Style.colors.foreground
        size: P.Style.iconMedium

        onClicked: {
            _shutdown_popup.open()
        }
    }

    Popup {
        id: _shutdown_popup
        modal: true
        x: P.Style.windowWidth/2 - width/2
        y: P.Style.windowHeight/2 - height/2
        ColumnLayout {
            anchors.fill: parent
            Button {
                id: _restart_button
                text: "Restart"
                Layout.fillWidth: true
            }
            Button {
                id: _shutdown_button
                text: "Shutdown"
                Layout.fillWidth: true
            }
            Button {
                id: _exit_button
                text: "Exit to desktop"
                onClicked: {
                    window.close()
                }
                Layout.fillWidth: true
            }
        }

    }


}