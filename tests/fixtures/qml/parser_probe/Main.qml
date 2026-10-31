// Synthetic Qt 6.5 syntax profile; parsing does not validate runtime types.
import QtQuick
import QtQuick.Controls 6.5 as Controls
import "./components" as Local
import "helpers.js" as Helpers

Item {
    id: root
    required property string title
    readonly property int doubled: count * 2
    default property list<QtObject> extras
    property int count: 1
    property alias editorText: editor.text
    signal activated(int value, string label)
    signal changed(value: int)

    function bump(step: int): int {
        const total = count + step;
        count = total;
        activated(total, title);
        return total;
    }

    onCountChanged: {
        const message = "punctuation: {}; //";
        if (count > 0) { bump(1); }
    }

    Controls.TextField {
        id: editor
        text: root.title
        onTextChanged: root.count = text.length
    }
}
