// UTF-8 and CRLF are intentional; columns count bytes, not Unicode characters.
import QtQuick
Item {
    id: root
    property string café: "雪😀"; property int après: 2
    function résumé(étape) { return café + étape; }
}
