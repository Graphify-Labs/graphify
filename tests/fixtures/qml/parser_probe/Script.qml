// Comments and strings deliberately imitate QML; the parser must keep JS scopes.
import QtQuick
Item {
    property var transform: (value) => ({ label: "}", value: value + 1 })
    function evaluate(input) {
        let value = input;
        { let value = 3; value += 1; }
        const outside = value;
        return transform(outside).value;
    }
    Component.onCompleted: {
        const literal = "signal fake(int x) { import Broken }";
        /* A brace } and fake declaration: signal phantom() */
        evaluate(2);
    }
}
