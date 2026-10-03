// Invalid tokens are deliberate; the later property should remain recoverable.
import QtQuick
Item {
    property int broken: @@@;
    property string retained: "safe"
}
