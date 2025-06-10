import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P


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
        x: window.width/2 - width/2
        y: window.height/2 - height/2
        ColumnLayout {
            anchors.fill: parent
            Button {
                id: _restart_app_button
                text: "Restart App"
                Layout.fillWidth: true
                enabled: P.AppBridge.is_systemd_service
                visible: enabled

                onClicked: {
                    P.AppBridge.restart_app()
                }
            }
            Button {
                id: _restart_host_button
                text: "Restart Host"
                Layout.fillWidth: true

                onClicked: {
                    restart_host_dialog.open()
                }
                MessageDialog {
                    id: restart_host_dialog
                    flags: Qt.FramelessWindowHint
                    text: "Are you sure you want to restart the host?"
                    buttons: MessageDialog.Yes | MessageDialog.Cancel

                    onAccepted: {
                        P.AppBridge.reboot_host()
                    }
                }
            }
            Button {
                id: _shutdown_button
                text: "Shutdown"
                Layout.fillWidth: true
                onClicked: {
                    shutdown_host_dialog.open()
                }
                MessageDialog {
                    id: shutdown_host_dialog
                    flags: Qt.FramelessWindowHint
                    text: "Are you sure you want to shutdown the host?"
                    buttons: MessageDialog.Yes | MessageDialog.Cancel

                    onAccepted: {
                        P.AppBridge.shutdown_host()
                    }
                }
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