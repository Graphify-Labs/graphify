// Lowercase grouped properties must not become instantiated component types.
import QtQuick
Text {
    id: label
    anchors { left: parent.left; topMargin: 4 }
    font { pixelSize: 12; bold: true }
    text: "Grouped properties"
}
