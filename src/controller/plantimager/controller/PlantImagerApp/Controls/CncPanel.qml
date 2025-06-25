import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P


Control {
    id: self

    property var scanner: P.AppBridge.scanner

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: P.Style.mediumMargin

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            Button {
                id: moveToCenterButton

                Layout.preferredHeight: P.Style.mediumHeight
                text: "Move to center"

                onClicked: {
                    scanner.move_to_center()
                }
                enabled: !scanner.scanner_working
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.maximumHeight: 2
            Layout.alignment: Qt.AlignTop

            color: P.Style.colors.foreground
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            Label {

                text: scanner.path_info
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignLeft;
                padding: P.Style.smallMargin
                leftPadding: P.Style.mediumMargin

                font: P.Style.fonts.label
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            Button {
                id: moveToPathButton

                Layout.preferredHeight: P.Style.mediumHeight
                text: "Move to position in path"

                onClicked: {
                    scanner.move_to_position_in_path(parseInt(pos_edit.text))
                }

                enabled: !scanner.scanner_working
            }

            TextInput {
                id: pos_edit
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignRight

                text: "0"

                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
                MouseArea {
                    id: _icon_area;
                    anchors.fill: parent;
                    anchors.margins: -2
                    hoverEnabled: true;

                    onClicked: {
                        keyboard_popup.input = parseInt(pos_edit.text)
                        keyboard_popup.open()
                    }
                }
                P.NumericKeyboardPopup {
                    id: keyboard_popup
                    anchors.centerIn: Overlay.overlay
                    onClosed: {
                        pos_edit.text = input.toString()
                    }
                }
            }
        }
    }
}