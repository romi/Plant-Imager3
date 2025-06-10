import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    id: splash
    width: 400
    height: 400
    visible: true
    flags: Qt.SplashScreen | Qt.WindowStaysOnTop
    color: "#ffffff"

    Image {
        id: logo
        width: parent.width * 0.6
        height: width
        anchors.centerIn: parent
        source: "Style/ROMI_ICON_green.png"
        fillMode: Image.PreserveAspectFit
    }

    BusyIndicator {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: logo.bottom
        anchors.topMargin: 20
        running: loader.status !== Loader.Ready
    }

    Loader {
        id: loader
        asynchronous: true
        source: "Main.qml"
        onLoaded: {
            splash.hide()
            item.show()
            item.visibility = Window.FullScreen
            item.closing.connect((closeEvent) => {
                closeEvent.accepted = true
                splash.show()
                splash.close()
            })
        }
    }
}