import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P


Control {
    id: self

    property var scanner: P.AppBridge ? P.AppBridge.scanner : null

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: P.Style.mediumMargin

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: P.Style.smallMargin

            Button {
                id: enableManualButton
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.mediumHeight
                text: "Enable Manual"
                visible: scanner ? scanner.power_mode !== "MANUAL" : true
                enabled: scanner ? true : false
                onClicked: { if (scanner) scanner.enable_manual() }
            }
            Label {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                text: scanner ? (scanner.power_mode + " / " + scanner.cnc_state) : ""
                font: P.Style.fonts.label
                color: P.Style.colors.foreground
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            visible: scanner ? scanner.power_mode === "MANUAL" : false
            Button {
                id: moveToCenterButton

                Layout.preferredHeight: P.Style.mediumHeight
                text: "Move to center"

                onClicked: {
                    if (scanner) scanner.move_to_center()
                }
                enabled: scanner ? !scanner.scanner_working : false
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

                text: scanner ? scanner.path_info : ""
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
            visible: scanner ? scanner.power_mode === "MANUAL" : false
            Button {
                id: moveToPathButton

                Layout.preferredHeight: P.Style.mediumHeight
                text: "Move to position in path"

                onClicked: {
                    if (scanner) scanner.move_to_position_in_path(parseInt(pos_edit.text))
                }

                enabled: scanner ? !scanner.scanner_working : false
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