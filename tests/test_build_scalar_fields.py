from copy import deepcopy

import pytest

from graphify.build import build, build_from_json
from graphify.validate import validate_extraction


@pytest.mark.parametrize("assemble", [build_from_json, lambda data: build([data])])
def test_malformed_extraction_fields_do_not_break_good_records(assemble):
    data = {
        "nodes": [
            {"id": "a", "label": 123, "file_type": "code", "source_file": 42},
            {"id": 2, "label": "Target", "file_type": "code", "source_file": "b.py"},
            {"id": None, "label": "Bad", "file_type": "code", "source_file": "a.py"},
            {"id": True, "label": "Also bad", "file_type": "code", "source_file": "a.py"},
        ],
        "edges": [
            {"source": "a", "target": 2, "relation": "calls",
             "confidence": "EXTRACTED", "source_file": 42},
            {"source": "a", "target": 2, "relation": ["calls"],
             "confidence": "EXTRACTED", "source_file": "a.py"},
            {"source": True, "target": 2, "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "a.py"},
        ],
    }
    errors = validate_extraction(data)
    for field in ("id", "label", "source_file", "relation", "source", "target"):
        assert any(field in error and "must be a string" in error for error in errors)
    graph = assemble(deepcopy(data))
    assert set(graph) == {"a", "2"}
    assert graph.nodes["a"]["label"] == "a"
    assert graph.nodes["a"]["source_file"] == ""
    assert graph["a"]["2"]["relation"] == "calls"
    assert graph["a"]["2"]["source_file"] == "b.py"
    assert graph.number_of_edges() == 1
