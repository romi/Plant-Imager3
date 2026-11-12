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

    // The icon lives as a plain child (not contentItem): a Control
    // collapses an anchored contentItem to ~0px (measured live), which
    // shrank the hover/click area below the visible glyph. Sizing comes
    // from the icon explicitly, and a full-box MouseArea owns input.
    implicitWidth: _icon.implicitWidth + 4;
    implicitHeight: _icon.implicitHeight + 4;

    background: Rectangle {
        visible: false;
    }

    P.Icon {
        id: _icon;
        anchors.centerIn: parent;

        color: _control.hoverColor && _icon_area.containsMouse ? _control.hoverColor : _control.color
    }

    MouseArea {
        id: _icon_area;
        anchors.fill: parent;
        hoverEnabled: true;

        onClicked: {
            _control.clicked()
        }
    }
}
