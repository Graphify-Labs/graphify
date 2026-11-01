"""INC-QML-112: alias graph IDs cannot substitute source-owned native endpoints."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.cpp_alias_helpers import declarations
from tests.test_qt_native_alias_scope import DECLARATIONS, endpoint_links, native_facts, native_signal, persisted


@pytest.mark.parametrize("form", ["using", "typedef"])
def test_req_qml022_ac02_case_distinct_aliases_preserve_actual_native_signal_owners(tmp_path, form):
    """The existing native type-scope owner resolves each literal alias independently of its graph ID."""
    aliases = ("using Alias=Sender;\nusing alias=Other;\n" if form == "using" else
               "typedef Sender Alias;\ntypedef Other alias;\n")
    raw = DECLARATIONS + aliases + """void wire(Alias *upper, alias *lower, Receiver *receiver) {
 QObject::connect(upper, &Alias::changed, receiver, &Receiver::accept);
 QObject::connect(lower, &alias::changed, receiver, &Receiver::accept);
}
"""
    result, payload, graph = persisted(tmp_path, raw)
    assert len(declarations(result)) == 2
    sites = native_facts(result, "connect")
    assert len(sites) == 2
    for site, owner in zip(sites, ("Sender", "Other")):
        actual = native_signal(result, owner)["id"]
        assert qt_metadata(site)["status"] == "resolved" and qt_metadata(site)["signal_target_id"] == actual
        links = endpoint_links(payload, site)
        assert len(links) == 1 and links[0]["target"] == actual
        assert graph.has_edge(links[0]["source"], actual) and not graph.has_edge(actual, links[0]["source"])
