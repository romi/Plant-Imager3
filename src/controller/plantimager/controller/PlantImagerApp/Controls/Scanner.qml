import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P

Control {
    id: self_
    property var scanner: P.AppBridge ? P.AppBridge.scanner : null
    signal switchToCncPanel()
    signal switchToTimelapsePanel()

    property var tlInfo: null
    property int tlCurrent: 0
    property int tlTotal: 0
    property string tlState: ""
    property string nextIso: ""
    property bool hasJob: false
    property string remainingText: "\u2014"

    function tlStatusIcon() {
        if (!hasJob || tlState === "") return P.Icons.icons["panorama-fisheye"]
        if (tlState === "COMPLETED") return P.Icons.icons["check-circle"]
        if (tlState === "FAILED") return P.Icons.icons["alert-circle"]
        if (tlState === "SCHEDULED" || tlState === "RUNNING") return P.Icons.icons["timer"]
        return P.Icons.icons["panorama-fisheye"]
    }
    function tlStatusColor() {
        if (!hasJob || tlState === "") return P.Style.colors.neutralColor
        if (tlState === "COMPLETED") return P.Style.colors.okColor
        if (tlState === "FAILED") return P.Style.colors.alertColor
        if (tlState === "SCHEDULED" || tlState === "RUNNING") return P.Style.colors.warningColor
        return P.Style.colors.neutralColor
    }
    function updateRemaining() {
        if (!hasJob || !nextIso) { remainingText = "\u2014"; return }
        var diff = new Date(nextIso) - new Date()
        if (diff <= 0) { remainingText = "now"; return }
        var m = Math.floor(diff / 60000)
        var h = Math.floor(m / 60)
        m = m % 60
        if (h > 0) remainingText = "in " + h + "h " + m + "m"
        else remainingText = "in " + m + "m"
    }
    function refreshTl() {
        var d = scanner ? scanner.get_active_timelapse() : null
        tlInfo = d
        hasJob = !!d
        if (!d) { tlState = ""; tlCurrent = 0; tlTotal = 0; nextIso = ""; remainingText = "\u2014"; return }
        tlState = d.state || ""
        tlTotal = d.schedule_times ? d.schedule_times.length : 0
        tlCurrent = (d.next_idx !== undefined ? d.next_idx : 0)
        if (d.schedule_times && d.next_idx < d.schedule_times.length) nextIso = d.schedule_times[d.next_idx]
        else nextIso = ""
        updateRemaining()
    }

    Component.onCompleted: refreshTl()

    Connections {
        target: scanner
        function onTimelapseChanged() { refreshTl() }
        function onTimelapseStateChanged() { refreshTl() }
        function onTimelapseProgressChanged() { refreshTl() }
        function onTimelapseFinished() { refreshTl() }
        function onTimelapseErrorOccurred() { refreshTl() }
    }

    Timer {
        interval: 30000
        repeat: true
        running: hasJob && nextIso !== ""
        onTriggered: updateRemaining()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: P.Style.smallMargin
        spacing: P.Style.smallMargin

        Label {
            id: cnc_type
            Layout.fillWidth: true
            text: scanner ? scanner.cnc_type : ""
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignLeft
            leftPadding: P.Style.largeMargin
            font: P.Style.fonts.header
        }

        RowLayout {
            id: statusRow
            Layout.fillWidth: true
            spacing: P.Style.smallMargin

            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                P.Icon {
                    size: P.Style.iconSmall
                    icon: tlStatusIcon()
                    color: tlStatusColor()
                }
                Label {
                    text: hasJob ? tlState : "No timelapse"
                    font: P.Style.fonts.label
                    color: tlStatusColor()
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                P.Icon {
                    size: P.Style.iconSmall
                    icon: P.Icons.icons["power"]
                    color: P.Style.colors.foreground
                }
                Label {
                    text: scanner ? (scanner.power_mode + " / " + scanner.cnc_state) : ""
                    font: P.Style.fonts.label
                    color: P.Style.colors.foreground
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                P.Icon {
                    size: P.Style.iconSmall
                    icon: P.Icons.icons["clock-outline"]
                    color: P.Style.colors.foreground
                }
                Label {
                    text: remainingText
                    font: P.Style.fonts.label
                    color: P.Style.colors.foreground
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }

        RowLayout {
            id: buttonRow
            Layout.fillWidth: true
            spacing: P.Style.smallMargin

            Button {
                id: cnc_panel_open_button
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.mediumHeight
                text: "CNC Panel"
                onClicked: switchToCncPanel()
            }
            Button {
                id: timelapse_panel_open_button
                Layout.fillWidth: true
                Layout.preferredHeight: P.Style.mediumHeight
                text: hasJob ? ("Timelapse " + tlCurrent + "/" + tlTotal) : "Timelapse"
                onClicked: switchToTimelapsePanel()
            }
        }

        P.ProgressBar {
            id: progress
            Layout.fillWidth: true
            to: scanner ? scanner.max_progress : 1
            value: scanner ? scanner.progress : 0
        }
        P.ProgressBar {
            id: tlProgress
            Layout.fillWidth: true
            visible: hasJob
            to: Math.max(1, tlTotal)
            value: tlCurrent
        }
    }
}
