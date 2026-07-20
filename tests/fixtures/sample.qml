import QtQuick 2.15
import QtQuick.Controls 2.15
import "helpers.js" as Helpers

Item {
    id: root

    property string title: "hello"
    property alias labelText: label.text
    property list<Item> items

    signal activated(int index)

    function refresh() {
        label.text = root.title
        helper()
    }

    function helper() {
        Helpers.log("refreshed")
    }

    anchors {
        left: parent.left
        right: parent.right
    }

    Text {
        id: label
        text: root.title
        font {
            pixelSize: 14
        }
    }

    Behavior on width {
        NumberAnimation { duration: 120 }
    }

    CustomPanel {
        id: panel
        onClicked: root.refresh()
    }

    states: [
        State { name: "open" }
    ]

    component InlineBadge: Rectangle {
        id: badge
        color: "red"
    }
}
