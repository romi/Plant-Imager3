import QtQuick
import QtQuick.Controls

import PlantImagerApp.Controls as P
import PlantImagerApp.Style as P

Button
{
    id: _control;

    property alias iconName: _icon.icon;
    property alias size: _icon.size;
    property alias rotation: _icon.rotation;
    property alias flip: _icon.flip

    property color color : P.Style.colors.accent;
    property color hoverColor : P.Style.colors.accentFaded;

    property alias containsMouse: _icon_area.containsMouse

    implicitHeight: implicitContentHeight;
    implicitWidth: implicitContentWidth;

    background: Rectangle {
        visible: false;
    }

    contentItem: P.Icon {
        id: _icon;
        anchors.centerIn: parent

        color: _control.hoverColor && _icon_area.containsMouse ? _control.hoverColor : _control.color

        MouseArea {
            id: _icon_area;
            anchors.fill: parent;
            anchors.margins: -2
            hoverEnabled: true;

            onClicked: {
                _control.clicked()
            }
        }
    }
}
