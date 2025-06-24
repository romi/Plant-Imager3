import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

import PlantImagerApp 1.0 as P
import PlantImagerApp.Camera as P
import PlantImagerApp.Style as P

ApplicationWindow {
    id: window
    visible: true
    width: P.Style.windowWidth
    height: P.Style.windowHeight
    flags: Qt.FramelessWindowHint
    //flags: Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint
    //visibility: Window.FullScreen

    header: P.Header {

    }

    P.LeftPane {
        id: left_pane
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.right: parent.horizontalCenter
    }

    P.RightPane {
        id: right_pane
        anchors.top: header.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.left: parent.horizontalCenter
    }

}