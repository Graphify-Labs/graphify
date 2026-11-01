import QtQuick 2.15
import Public.Tools 1.0

Item {
    id: root
    objectName: "publicRoot"
    property int status: service.status
    Service { id: service }
    function refresh() { service.refresh() }
}
