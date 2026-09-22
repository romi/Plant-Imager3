import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P
import PlantImagerApp as P

Control {
    id: self_
    property var scanner: P.AppBridge ? P.AppBridge.scanner : null
    signal closeRequested()

    property var tlInfo: null
    property bool hasJob: false
    property string tlState: ""
    property int tlTotal: 0
    property int tlNextIdx: 0
    property string nextIso: ""
    property string nextLocal: ""

    function tlStatusIcon(s) {
        if (s === "COMPLETED") return P.Icons.icons["check-circle"]
        if (s === "FAILED") return P.Icons.icons["alert-circle"]
        if (s === "SCHEDULED" || s === "RUNNING") return P.Icons.icons["timer"]
        return P.Icons.icons["panorama-fisheye"]
    }
    function tlStatusColor(s) {
        if (s === "COMPLETED") return P.Style.colors.okColor
        if (s === "FAILED") return P.Style.colors.alertColor
        if (s === "SCHEDULED" || s === "RUNNING") return P.Style.colors.warningColor
        return P.Style.colors.neutralColor
    }
    function rowStatus(i) {
        if (!hasJob || !tlInfo) return "pending"
        var scans = tlInfo.scans || []
        var rec = null
        for (var j = 0; j < scans.length; j++) {
            var sid = scans[j].scan_id || ""
            if (sid.endsWith("_" + i)) { rec = scans[j]; break }
            if (i === 0 && sid === tlInfo.timelapse_id) { rec = scans[j]; break }
        }
        if (rec) {
            var st = rec.status || ""
            if (st === "succeeded" || st === "completed" || st === "COMPLETED") return "done"
            if (st === "failed" || st === "FAILED") return "failed"
            if (st === "skipped") return "skipped"
            return st
        }
        if (i < tlNextIdx) return "skipped"
        if (i === tlNextIdx && tlState === "RUNNING") return "running"
        if (i === tlNextIdx && tlState === "SCHEDULED") return "next"
        return "pending"
    }
    function rowIcon(st) {
        if (st === "done") return P.Icons.icons["check-circle"]
        if (st === "failed") return P.Icons.icons["alert-circle"]
        if (st === "next" || st === "running") return P.Icons.icons["timer"]
        if (st === "skipped") return P.Icons.icons["panorama-fisheye"]
        return P.Icons.icons["panorama-fisheye"]
    }
    function rowColor(st) {
        if (st === "done") return P.Style.colors.okColor
        if (st === "failed") return P.Style.colors.alertColor
        if (st === "next" || st === "running") return P.Style.colors.warningColor
        if (st === "skipped") return P.Style.colors.warningColor
        return P.Style.colors.neutralColor
    }
    function formatLocal(iso) {
        if (!iso) return "\u2014"
        var d = new Date(iso)
        var dd = ("0" + d.getDate()).slice(-2)
        var mm = ("0" + (d.getMonth() + 1)).slice(-2)
        var hh = ("0" + d.getHours()).slice(-2)
        var mi = ("0" + d.getMinutes()).slice(-2)
        return dd + "/" + mm + " " + hh + ":" + mi
    }
    function refreshTl() {
        var d = scanner ? scanner.get_active_timelapse() : null
        tlInfo = d
        hasJob = !!d
        if (!d) { tlState = ""; tlTotal = 0; tlNextIdx = 0; nextIso = ""; nextLocal = "\u2014"; scheduleModel.clear(); return }
        tlState = d.state || ""
        tlTotal = d.schedule_times ? d.schedule_times.length : 0
        tlNextIdx = (d.next_idx !== undefined ? d.next_idx : 0)
        if (d.schedule_times && d.next_idx < d.schedule_times.length) {
            nextIso = d.schedule_times[d.next_idx]
            nextLocal = formatLocal(nextIso)
        } else { nextIso = ""; nextLocal = "\u2014" }
        scheduleModel.clear()
        if (d.schedule_times) {
            for (var i = 0; i < d.schedule_times.length; i++) {
                scheduleModel.append({ idx: i, iso: d.schedule_times[i], local: formatLocal(d.schedule_times[i]), st: rowStatus(i) })
            }
        }
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

    ListModel { id: scheduleModel }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: P.Style.smallMargin
        spacing: P.Style.smallMargin

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: P.Style.mediumHeight

            Label {
                text: "Timelapse"
                font: P.Style.fonts.header
                Layout.fillWidth: true
                verticalAlignment: Text.AlignVCenter
                leftPadding: P.Style.largeMargin
            }
            P.IconButton {
                iconName: P.Icons.icons["close"]
                color: P.Style.colors.foreground
                hoverColor: P.Style.colors.accent
                size: P.Style.iconMedium
                Layout.preferredHeight: P.Style.mediumHeight
                onClicked: closeRequested()
            }
        }

        // Empty state
        Label {
            visible: !hasJob
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "No timelapse"
            font: P.Style.fonts.label
            color: P.Style.colors.neutralColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        // Summary (fixed)
        ColumnLayout {
            visible: hasJob
            Layout.fillWidth: true
            spacing: 2

            Label {
                text: tlInfo ? tlInfo.timelapse_id : ""
                font: P.Style.fonts.header
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: P.Style.smallMargin

                P.Icon {
                    size: P.Style.iconSmall
                    icon: tlStatusIcon(tlState)
                    color: tlStatusColor(tlState)
                }
                Label {
                    text: tlState + "  " + tlNextIdx + "/" + tlTotal
                    font: P.Style.fonts.label
                    color: tlStatusColor(tlState)
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Label {
                    text: nextLocal
                    font: P.Style.fonts.label
                    color: P.Style.colors.foreground
                    elide: Text.ElideRight
                }
            }
            Label {
                text: tlInfo ? (tlInfo.mode || "") : ""
                font: P.Style.fonts.label
                color: P.Style.colors.foreground
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }

        Rectangle {
            visible: hasJob
            Layout.fillWidth: true
            height: 1
            color: P.Style.colors.foreground
            opacity: 0.2
        }

        // Schedule list
        ListView {
            visible: hasJob
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: scheduleModel
            ScrollBar.vertical: ScrollBar {}

            delegate: RowLayout {
                width: ListView.view.width
                height: 40
                spacing: P.Style.smallMargin

                Label {
                    text: "#" + model.idx + " \u00b7 " + model.local
                    font: P.Style.fonts.label
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    verticalAlignment: Text.AlignVCenter
                }
                P.Icon {
                    size: P.Style.iconSmall
                    icon: rowIcon(model.st)
                    color: rowColor(model.st)
                }
                Label {
                    text: model.st
                    font: P.Style.fonts.label
                    color: rowColor(model.st)
                    Layout.preferredWidth: 70
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                }
            }
        }
    }
}
