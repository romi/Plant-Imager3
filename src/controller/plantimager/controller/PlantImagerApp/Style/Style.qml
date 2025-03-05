pragma Singleton

import QtQuick

QtObject {
    id: _self

    property int iconSmall: 12
    property int iconMedium: 25
    property int iconLarge: 30

    property int smallMargin: 5
    property int mediumMargin: 10
    property int largeMargin: 20

    property int smallHeight: 20
    property int mediumHeight: 40
    property int bigHeight: 80

    property int windowWidth: 800
    property int windowHeight: 480

    property int bannerHeight: 40
    property int cameraDelegateHeight: 60

    property int videoWidth: 640
    property int videoHeight: 480
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