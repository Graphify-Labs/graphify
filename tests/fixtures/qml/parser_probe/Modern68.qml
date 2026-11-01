// Synthetic Qt 6.8 syntax profile; this is not a running Qt application.
pragma ComponentBehavior: Bound
import QtQuick 6.8

Item {
    id: outer
    enum Mode { Idle = 0, Active = 1 }
    component Tile: Rectangle {
        id: tile
        required property int value
        property alias ownValue: tile.value
    }
    Tile { value: 3 }
    property var mapper: (value) => value + 1
    Component.onCompleted: mapper(Mode.Active)
}
