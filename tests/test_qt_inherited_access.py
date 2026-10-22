"""REQ-QML-016-AC01 inheritance access is source proof, separate from meta lookup."""
import copy

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.qt_event_index import QtEventIndex
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_inherited_endpoints import SOURCE


@pytest.mark.parametrize("access", ["private", "protected", "default_class"])
def test_req_qml016_ac01_external_member_pointer_cannot_cross_nonpublic_base(tmp_path, access):
    """External C++ pointers cannot acquire public access through private/protected bases."""
    spelling = "" if access == "default_class" else access + " "
    source = SOURCE.replace("class Middle : public Grand", "class Middle : " + spelling + "Grand")
    result = analysis(tmp_path, {"events.cpp": source})
    modern, legacy = sites(result, "connect")
    assert qt_metadata(modern)["signal_status"] == "unavailable"
    assert qt_metadata(modern)["receiver_status"] == "unavailable"
    # QMetaObject/legacy access and an owning-class emission do not manufacture
    # a C++ pointer conversion. Their previously admitted mechanism is preserved.
    assert qt_metadata(legacy)["status"] == "resolved"
    assert qt_metadata(sites(result, "emission")[0])["status"] == "resolved"


def test_req_qml016_ac01_explicit_grandparent_pointer_requires_public_object_conversion(tmp_path):
    """Qualifying Grand directly does not bypass Child's private inherited base."""
    source = SOURCE.replace("class Middle : public Grand", "class Middle : private Grand")
    source = source.replace("&Child::changed", "&Grand::changed").replace("&Child::accept", "&Grand::accept")
    result = analysis(tmp_path, {"events.cpp": source})
    assert qt_metadata(sites(result, "connect")[0])["signal_status"] == "unavailable"
    assert qt_metadata(sites(result, "connect")[0])["signal_reason"] == "inheritance_access_unavailable"


def test_req_qml016_ac01_struct_default_and_virtual_access_are_captured_in_source_order(tmp_path):
    """Each comma resets default access; virtual does not replace explicit access."""
    source = SOURCE.replace("class Middle : public Grand { Q_OBJECT };", '''class Empty { };
struct Middle : Grand, virtual public Empty { Q_OBJECT };''')
    result = analysis(tmp_path, {"events.cpp": source})
    middle = next(node for node in sites(result, "class") if qt_metadata(node)["class_name"] == "Middle")
    assert qt_metadata(middle)["canonical_base_access"] == ["public", "public"]
    assert qt_metadata(middle)["canonical_base_access_status"] == "resolved"
    assert qt_metadata(sites(result, "connect")[0])["status"] == "resolved"


@pytest.mark.parametrize("invalid", ["missing", "count", "value", "shape", "status"])
def test_req_qml016_ac01_missing_or_corrupt_base_access_rejects_pointer_only(tmp_path, invalid):
    """Old or corrupt accepted facts cannot supply access authority from a default."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    nodes = copy.deepcopy(result["nodes"])
    middle = next(node for node in nodes if qt_metadata(node).get("kind") == "class"
                  and qt_metadata(node)["class_name"] == "Middle")
    update_qt(middle, **{"missing": {"canonical_base_access": None},
                         "count": {"canonical_base_access": []},
                         "value": {"canonical_base_access": ["invented"]},
                         "shape": {"canonical_base_access": [{}]},
                         "status": {"canonical_base_access_status": "unavailable"}}[invalid])
    before = copy.deepcopy(nodes)
    index = QtEventIndex(nodes)
    endpoint = {"form": "member_pointer", "class_name": "Child", "member_name": "changed"}
    result = index.member(endpoint, "Child", role="signal")
    assert result.status == "unavailable" and result.reason == "inheritance_access_unavailable"
    assert index.member({**endpoint, "form": "legacy"}, "Child", role="signal").status == "resolved"
    assert nodes == before


def test_req_qml016_ac01_class_default_resets_at_comma_and_comments_supply_no_authority(tmp_path):
    """A private empty mixin does not hide Grand's public declaration or carry its access."""
    source = SOURCE.replace("class Middle : public Grand { Q_OBJECT };", '''class Empty { };
class Middle : public /* documented base */ Grand, Empty { Q_OBJECT };''')
    result = analysis(tmp_path, {"events.cpp": source})
    middle = next(node for node in sites(result, "class") if qt_metadata(node)["class_name"] == "Middle")
    assert qt_metadata(middle)["canonical_base_names"] == ["Grand", "Empty"]
    assert qt_metadata(middle)["canonical_base_access"] == ["public", "private"]
    assert qt_metadata(sites(result, "connect")[0])["status"] == "resolved"
