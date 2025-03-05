import QtQuick
import QtQuick.Controls

import PlantImagerApp.Style as P

Control
{
  id: _control;

  property string icon: "";
  property int size: P.Style.iconMedium;
  property color color: P.Style.colors.textColorBase;
  property alias rotation: _text.rotation;
  property bool flip: false;

  readonly property real _implicitSize: icon.toString() ? size : 0

  implicitWidth: _implicitSize
  implicitHeight: _implicitSize

  FontLoader {
    id: _loader;
    source: "qrc:/ttf/materialdesignicons-webfont.ttf";
  }

  Text {
    id: _text
    anchors.fill: _control;

    color: _control.color;
    text: _control.icon;
    font.pixelSize: _control.size;
    font.family: _loader.name;
    verticalAlignment: Text.AlignVCenter;
    horizontalAlignment: Text.AlignHCenter;
    padding: 0

    transform: Scale {
      origin.x: _text.x + _text.width/2;
      xScale: _control.flip ? -1 : 1;
    }
  }
}
