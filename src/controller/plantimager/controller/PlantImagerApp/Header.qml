import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

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

    Rectangle {
        id: _mqtt_dot
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: _fleet_menu_button.left
        anchors.rightMargin: P.Style.smallMargin
        width: P.Style.iconSmall
        height: P.Style.iconSmall
        radius: width / 2
        color: P.AppBridge.mqtt.connected ? P.Style.colors.lightText : P.Style.colors.alertColor
    }

    P.IconButton {
        id: _fleet_menu_button
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: _shutdown_menu_button.left
        anchors.rightMargin: P.Style.smallMargin
        iconName: P.Icons.icons["server-network"]
        color: P.Style.colors.lightText
        hoverColor: P.Style.colors.foreground
        size: P.Style.iconMedium
        enabled: P.AppBridge.mqtt.connected

        onClicked: {
            _fleet_popup.open()
        }
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
        anchors.centerIn: Overlay.overlay
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
                P.ConfirmDialog {
                    id: restart_host_dialog
                    title: "Restart host?"
                    message: "Are you sure you want to restart the host?"
                    confirmText: "Restart"
                    dangerous: true
                    onConfirmed: P.AppBridge.reboot_host()
                }
            }
            Button {
                id: _shutdown_button
                text: "Shutdown"
                Layout.fillWidth: true
                onClicked: {
                    shutdown_host_dialog.open()
                }
                P.ConfirmDialog {
                    id: shutdown_host_dialog
                    title: "Shutdown host?"
                    message: "Are you sure you want to shutdown the host?"
                    confirmText: "Shutdown"
                    dangerous: true
                    onConfirmed: P.AppBridge.shutdown_host()
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

    Popup {
        id: _fleet_popup
        modal: true
        anchors.centerIn: Overlay.overlay
        ColumnLayout {
            anchors.fill: parent
            Button {
                id: _fleet_restart_button
                text: "Restart all cameras"
                Layout.fillWidth: true
                onClicked: {
                    _fleet_popup.close()
                    P.AppBridge.sendFleetCommand("restart_service")
                }
            }
            Button {
                id: _fleet_reboot_button
                text: "Reboot all cameras"
                Layout.fillWidth: true
                onClicked: {
                    fleet_reboot_dialog.open()
                }
                P.ConfirmDialog {
                    id: fleet_reboot_dialog
                    title: "Reboot all cameras?"
                    message: "Every camera on this broker will reboot and disappear until it comes back."
                    confirmText: "Reboot all"
                    dangerous: true
                    onConfirmed: {
                        _fleet_popup.close()
                        P.AppBridge.sendFleetCommand("reboot")
                    }
                }
            }
            Button {
                id: _fleet_poweroff_button
                text: "Power off all cameras"
                Layout.fillWidth: true
                onClicked: {
                    fleet_poweroff_dialog.open()
                }
                P.ConfirmDialog {
                    id: fleet_poweroff_dialog
                    title: "Power off all cameras?"
                    message: "Every camera on this broker will power off. Each needs a manual restart afterwards."
                    confirmText: "Power off all"
                    dangerous: true
                    onConfirmed: {
                        _fleet_popup.close()
                        P.AppBridge.sendFleetCommand("poweroff")
                    }
                }
            }
        }

    }


}