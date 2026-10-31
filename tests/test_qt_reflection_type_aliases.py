"""REQ-QML-017: a supported findChild filter needs SDK QObject identity."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_receiver_boundaries import persisted, source


@pytest.mark.parametrize("declaration,filter_type,resolved", [
    ("", "QObject", True),
    ("", "::QObject", True),
    ("class Other {}; using QObject = Other;", "QObject", False),
    ("class Other {}; typedef Other QObject;", "QObject", False),
    ("class QObject {};", "QObject", False),
])
def test_req_qml017_ac02_findchild_filter_rejects_shadowed_sdk_type(tmp_path, declaration, filter_type, resolved):
    """Original pointer spelling cannot authorize a child cast to another class."""
    tail = f'root->findChild<{filter_type}*>("child");'
    result, site, links = persisted(tmp_path, tail,
        'import QtQuick\nItem { Item { objectName: "child" } }',
        extra={"access.cpp": declaration + "\n" + source(tmp_path, tail)})
    assert bool(links) is resolved
    assert qt_metadata(site)["status"] == ("resolved" if resolved else "unsupported")
    if not resolved:
        assert qt_metadata(site)["reason"] == "find_child_type_unsupported"
