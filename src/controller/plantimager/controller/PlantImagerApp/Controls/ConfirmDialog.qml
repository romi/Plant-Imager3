import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P

Dialog {
    id: _dialog

    property alias message: _message.text
    property string cancelText: "Cancel"
    property string confirmText: "Confirm"
    property bool dangerous: false

    signal confirmed()

    modal: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: Overlay.overlay
    width: 360

    ColumnLayout {
        anchors.fill: parent
        spacing: P.Style.smallMargin

        Label {
            id: _message
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font: P.Style.fonts.label
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.mediumHeight
                Layout.preferredWidth: 140
                text: cancelText
                font: P.Style.fonts.buttonSmall
                Material.background: P.Style.colors.neutralColor
                Material.foreground: P.Style.colors.lightText
                onClicked: _dialog.close()
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.mediumHeight
                Layout.preferredWidth: 140
                text: confirmText
                font: P.Style.fonts.buttonSmall
                Material.background: dangerous ? P.Style.colors.alertColor : P.Style.colors.okColor
                Material.foreground: P.Style.colors.lightText
                onClicked: {
                    confirmed()
                    _dialog.close()
                }
            }
        }
    }
}
