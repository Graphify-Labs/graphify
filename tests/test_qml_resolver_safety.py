"""Production join failures must not publish partial Qt/QML graphs."""
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.qml_safety import QmlSafetyError, require_complete_qml


def test_native_join_failure_is_guarded_and_successful_retry_is_clean(tmp_path, monkeypatch):
    import graphify.qml_resolution as resolver
    path = tmp_path / "Main.qml"
    path.write_text("Item { property int value: 3 }", encoding="utf-8")
    real = resolver.resolve_qml_project

    def broken(*args, **kwargs):
        args[1].append({"id": "partial_join_must_not_escape"})
        raise RuntimeError("private backend failure details")

    monkeypatch.setattr(resolver, "resolve_qml_project", broken)
    failed = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert failed["qml_failures"][0]["code"] == "QML_RESOLUTION_FAILED"
    assert not any(n["id"] == "partial_join_must_not_escape" for n in failed["nodes"])
    assert "private backend" not in str(failed)
    with pytest.raises(QmlSafetyError, match="QML_GRAPH_PRESERVED"):
        require_complete_qml(failed, [path], root=tmp_path, operation="test")
    monkeypatch.setattr(resolver, "resolve_qml_project", real)
    retried = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not retried["qml_failures"] and not retried["failed_sources"]
    require_complete_qml(retried, [path], root=tmp_path, operation="retry")


def test_nested_object_scope_keys_have_fixed_transport_size(tmp_path):
    from graphify.extractors.qml import extract_qml
    path = tmp_path / "Nested.qml"
    path.write_text("Item {" * 30 + "property int value: 1" + "}" * 30, encoding="utf-8")
    result = extract_qml(path, root=tmp_path)
    assert not result.get("error")
    scopes = [n["metadata"]["qml"]["object_scope_key"] for n in result["nodes"]
              if n["metadata"]["qml"]["kind"] == "object"]
    assert len(scopes) == 30 and len(set(scopes)) == 30
    assert {len(scope) for scope in scopes} == {64}
