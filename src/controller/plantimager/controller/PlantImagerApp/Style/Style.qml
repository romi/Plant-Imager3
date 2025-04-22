pragma Singleton

import QtQuick

QtObject {
    id: _self

    property int scale: 2

    property int iconSmall: scale * 12
    property int iconMedium: scale * 25
    property int iconLarge: scale * 30

    property int smallMargin: scale * 5
    property int mediumMargin: scale * 10
    property int largeMargin: scale * 20

    property int smallHeight: scale * 20
    property int mediumHeight: scale * 40
    property int bigHeight: scale * 80

    property int windowWidth: scale * 800
    property int windowHeight: scale * 480

    property int bannerHeight: scale * 40
    property int cameraDelegateHeight: scale * 60

    property int videoWidth: scale * 640
    property int videoHeight: scale * 480
    property real videoRatio: videoWidth/videoHeight

    property QtObject colors: QtObject {
        property color accent: "#00A960"
        property color accentFaded: "#99ddbf"
        property color background: "#F3F3F3"
        property color foreground: "#202020"
        property color lightText: "#FFFFFF"

        property color okColor: "#00A960"
        property color alertColor: "#e24c3e"
        property color neutralColor: "#ACB7C9"
    }
    
    property QtObject fonts: QtObject {
        id: _fonts;

        property font title: Qt.font({
            family: "Nunito Sans",
            weight: Font.Bold,
            pointSize: 14,
        })

        property font header: Qt.font({
            family: "Nunito Sans",
            weight: Font.DemiBold, //"Regular",
            pointSize: 12,
        })

        property font subHeader: Qt.font({
            family: "Nunito Sans",
            weight: Font.Bold, //"Regular",
            pointSize: 11,
        })

        property font label: Qt.font({
            family: "Nunito Sans",
            weight: "Light",
            pointSize: 10,
        })

        property font button: Qt.font({
            family: "Nunito Sans",
            weight: Font.Bold,
            pointSize: 10,
        })

        property font buttonSmall: Qt.font({
            family: "Nunito Sans",
            weight: Font.Bold,
            pointSize: 9,
        })

        property font buttonHovered: Qt.font({
            family: "Nunito Sans",
            weight: Font.Bold,
            pointSize: 10,
            underline: true
        })
    }

}