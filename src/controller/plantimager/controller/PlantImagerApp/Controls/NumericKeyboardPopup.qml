import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P


Popup {
    id: popup

    property int input: 0

    modal: true
    width: 300
    height: 320

    GridLayout {
        id: grid

        anchors.fill: parent
        anchors.margins: P.Style.mediumMargin

        columns: 3
        //rowSpacing: P.Style.smallMargin
        columnSpacing: P.Style.smallMargin
        uniformCellHeights: true
        uniformCellWidths: true

        Button {
            id: clearButton
            Layout.fillWidth: true
            text: "Clear"

            onClicked: {
                input = 0
            }

        }
        TextInput {
            id: inputField
            Layout.fillWidth: true
            Layout.columnSpan: 2

            anchors.margins: P.Style.mediumMargin

            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignRight

            font: P.Style.fonts.label

            text: input.toString()
            readOnly: true
            cursorVisible: false

        }

        Button {
            text: "7"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 7
        }
        Button {
            text: "8"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 8
        }
        Button {
            text: "9"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 9
        }
        Button {
            text: "4"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 4
        }
        Button {
            text: "5"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 5
        }
        Button {
            text: "6"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 6
        }
        Button {
            text: "1"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 1
        }
        Button {
            text: "2"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 2
        }
        Button {
            text: "3"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10 + 3
        }
        Button {
            text: "⌫"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = Math.floor(input / 10)
        }
        Button {
            text: "0"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: input = input * 10
        }
        Button {
            text: "󰸞"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: popup.close()
        }
    }
}