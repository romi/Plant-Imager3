import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P


Popup {
    id: popup

    property real input: 0
    property bool _decimal: false
    property int _places: 0
    property bool _fresh: true

    onOpened: _fresh = true

    function _consumeFresh() {
        if(_fresh) {
            _fresh = false
            input = 0
            _decimal = false
            _places = 0
        }
    }

    function pushDigit(n) {
        _consumeFresh()
        if (_decimal) {
            _places += 1
            input = Math.round((input + n / Math.pow(10, _places)) * 1e9) / 1e9
        } else {
            input = input * 10 + n
        }
    }

    function backspace() {
        _consumeFresh()
        if (_places > 0) {
            _places -= 1
            input = Math.floor(input * Math.pow(10, _places)) / Math.pow(10, _places)
            if (_places === 0) {
                _decimal = false
            }
        } else {
            _decimal = false
            input = Math.floor(input / 10)
        }
    }

    function clear() {
        input = 0
        _decimal = false
        _places = 0
    }

    modal: true
    width: 300
    height: 360

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

            onClicked: clear()

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
            onClicked: pushDigit(7)
        }
        Button {
            text: "8"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(8)
        }
        Button {
            text: "9"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(9)
        }
        Button {
            text: "4"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(4)
        }
        Button {
            text: "5"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(5)
        }
        Button {
            text: "6"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(6)
        }
        Button {
            text: "1"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(1)
        }
        Button {
            text: "2"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(2)
        }
        Button {
            text: "3"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(3)
        }
        Button {
            text: "⌫"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: backspace()
        }
        Button {
            text: "0"
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: pushDigit(0)
        }
        Button {
            text: "."
            Layout.fillWidth: true
            //Layout.fillHeight: true
            onClicked: {
                _consumeFresh()
                _decimal = true
            }
        }
        Button {
            text: "󰸞"
            Layout.fillWidth: true
            Layout.columnSpan: 3
            //Layout.fillHeight: true
            onClicked: popup.close()
        }
    }
}