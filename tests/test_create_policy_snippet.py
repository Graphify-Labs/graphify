from pathlib import Path
def test_create_policy_recovered_with_references(tmp_path):
    """CREATE POLICY has no grammar rule (#3401): every policy statement
    disintegrates into loose tokens + an ERROR node with no CREATE text in
    it, so this is whole-file-regex-fallback only, not a walk-time recovery.
    Asserts both policies land as nodes, each with an applies_to edge to
    its table and a references edge to the function used in USING/CHECK.
    """
    from graphify.extractors.sql import extract_sql

    fixture = Path(__file__).parent / "fixtures" / "policies.sql"
    result = extract_sql(fixture)

    assert not result.get("error")

    node_labels = {n["label"] for n in result["nodes"]}
    assert "employees_select" in node_labels
    assert "employees_update" in node_labels

    def _label(nid):
        return next(n["label"] for n in result["nodes"] if n["id"] == nid)

    applies_to_targets = {
        _label(e["target"])
        for e in result["edges"]
        if e["relation"] == "applies_to"
    }
    assert "public.employees" in applies_to_targets

    references_targets = {
        _label(e["target"])
        for e in result["edges"]
        if e["relation"] == "references"
        and _label(e["source"]) in node_labels & {"employees_select", "employees_update"}
    }
    assert any("is_admin" in t for t in references_targets)
