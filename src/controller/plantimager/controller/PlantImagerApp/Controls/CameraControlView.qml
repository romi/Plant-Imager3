import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as PI

Flickable {
    id: _self

    required property QtObject bridge

    property var fullConfig: ({})
    property real exposureTime: 0
    property real analogueGain: 0
    property bool awbEnable: false
    property int awbMode: 0
    property real gainsR: 1.0
    property real gainsB: 1.0
    property string numpadTarget: ""

    function refreshFromBridge() {
        if (!bridge) {
            return
        }
        fullConfig = bridge.config
        if (fullConfig.ExposureTime !== undefined) {
            exposureTime = fullConfig.ExposureTime
        }
        if (fullConfig.AnalogueGain !== undefined) {
            analogueGain = fullConfig.AnalogueGain
        }
        if (fullConfig.AwbEnable !== undefined) {
            awbEnable = fullConfig.AwbEnable
        }
        if (fullConfig.AwbMode !== undefined) {
            awbMode = fullConfig.AwbMode
        }
        var gains = fullConfig.ColourGains
        if (gains !== undefined && gains.length === 2) {
            gainsR = gains[0]
            gainsB = gains[1]
        }
    }

    function mergedConfig() {
        return Object.assign({}, fullConfig, {
            "ExposureTime": Math.round(exposureTime),
            "AnalogueGain": analogueGain,
            "AwbEnable": awbEnable,
            "AwbMode": awbMode,
            "ColourGains": [gainsR, gainsB]
        })
    }

    function openNumpad(target, value) {
        numpadTarget = target
        _numpad.input = value
        _numpad.open()
    }

    contentHeight: control_column.height
    clip: true

    ColumnLayout {
        id: control_column
        width: _self.width
        spacing: P.Style.smallMargin

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: P.Style.bigHeight - 2 * P.Style.smallMargin
            color: "black"

            Image {
                anchors.fill: parent
                source: bridge ? bridge.imageSource : ""
                cache: false
                fillMode: Image.PreserveAspectFit
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin
            Label {
                Layout.preferredWidth: P.Style.controlLabelWidth
                text: "Exposure (µs)"
                font: P.Style.fonts.label
                elide: Text.ElideRight
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: exposureTime.toString()
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: openNumpad("ExposureTime", exposureTime)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin
            Label {
                Layout.preferredWidth: P.Style.controlLabelWidth
                text: "Gain"
                font: P.Style.fonts.label
                elide: Text.ElideRight
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: analogueGain.toString()
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: openNumpad("AnalogueGain", analogueGain)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin
            Label {
                Layout.preferredWidth: P.Style.controlLabelWidth
                text: "Auto WB"
                font: P.Style.fonts.label
                elide: Text.ElideRight
            }
            Switch {
                checked: awbEnable
                enabled: bridge ? bridge.status === "connected" : false
                onToggled: awbEnable = checked
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin
            Label {
                Layout.preferredWidth: P.Style.controlLabelWidth
                text: "WB mode"
                font: P.Style.fonts.label
                elide: Text.ElideRight
            }
            ComboBox {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                font: P.Style.fonts.buttonSmall
                model: bridge ? bridge.awbModeNames : []
                textRole: "name"
                valueRole: "value"
                currentIndex: bridge ? bridge.awbModeNames.findIndex(function(m) { return m.value === awbMode }) : -1
                enabled: bridge ? bridge.status === "connected" : false
                onActivated: awbMode = currentValue
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin
            Label {
                Layout.preferredWidth: P.Style.controlLabelWidth
                text: "Gains (R/B)"
                font: P.Style.fonts.label
                elide: Text.ElideRight
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: gainsR.toString()
                font: P.Style.fonts.buttonSmall
                enabled: (bridge ? bridge.status === "connected" : false) && !awbEnable
                onClicked: openNumpad("ColourGainsR", gainsR)
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: gainsB.toString()
                font: P.Style.fonts.buttonSmall
                enabled: (bridge ? bridge.status === "connected" : false) && !awbEnable
                onClicked: openNumpad("ColourGainsB", gainsB)
            }
        }

        Label {
            Layout.fillWidth: true
            visible: awbEnable
            text: "Manual gains need AWB off"
            font: P.Style.fonts.label
            color: P.Style.colors.warningColor
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            uniformCellWidths: true
            rowSpacing: P.Style.smallMargin
            columnSpacing: P.Style.smallMargin

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: "Apply"
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: bridge.config = mergedConfig()
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: "Set default"
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: bridge.setDefaultControls(mergedConfig())
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: "Reset"
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: bridge.resetControls(false)
            }
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.compactHeight
                text: "Factory"
                font: P.Style.fonts.buttonSmall
                enabled: bridge ? bridge.status === "connected" : false
                onClicked: bridge.resetControls(true)
            }
        }

        Label {
            Layout.fillWidth: true
            text: "Power"
            font: P.Style.fonts.label
            color: P.Style.colors.neutralColor
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: P.Style.smallMargin

            Item {
                Layout.fillWidth: true
            }
            P.IconButton {
                iconName: P.Icons.icons["refresh"]
                size: P.Style.iconMedium
                enabled: bridge ? bridge.status === "connected" : false
                ToolTip.text: "Restart camera service"
                ToolTip.visible: containsMouse
                onClicked: PI.AppBridge.sendCameraCommand(bridge.name, "restart_service")
            }
            Item {
                Layout.fillWidth: true
            }
            P.IconButton {
                iconName: P.Icons.icons["restart"]
                size: P.Style.iconMedium
                enabled: bridge ? bridge.status === "connected" : false
                ToolTip.text: "Reboot camera"
                ToolTip.visible: containsMouse
                onClicked: _reboot_dialog.open()
            }
            Item {
                Layout.fillWidth: true
            }
            P.IconButton {
                iconName: P.Icons.icons["power-off"]
                size: P.Style.iconMedium
                color: P.Style.colors.alertColor
                enabled: bridge ? bridge.status === "connected" : false
                ToolTip.text: "Power off camera"
                ToolTip.visible: containsMouse
                onClicked: _poweroff_dialog.open()
            }
            Item {
                Layout.fillWidth: true
            }
        }
    }

    P.ConfirmDialog {
        id: _reboot_dialog
        title: "Reboot camera?"
        message: "Reboot this camera? It will disappear until it comes back."
        confirmText: "Reboot"
        dangerous: true
        onConfirmed: PI.AppBridge.sendCameraCommand(bridge.name, "reboot")
    }

    P.ConfirmDialog {
        id: _poweroff_dialog
        title: "Power off camera?"
        message: "Power off this camera? It needs a manual restart afterwards."
        confirmText: "Power off"
        dangerous: true
        onConfirmed: PI.AppBridge.sendCameraCommand(bridge.name, "poweroff")
    }

    P.NumericKeyboardPopup {
        id: _numpad
        anchors.centerIn: Overlay.overlay
        onClosed: {
            if(numpadTarget === "ExposureTime") {
                exposureTime = input
            } else if(numpadTarget === "AnalogueGain") {
                analogueGain = input
            } else if(numpadTarget === "ColourGainsR") {
                gainsR = input
            } else if(numpadTarget === "ColourGainsB") {
                gainsB = input
            }
            numpadTarget = ""
        }
    }
}
