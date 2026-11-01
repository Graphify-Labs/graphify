"""INC-QML-91: lexical generic property data cannot borrow concrete classes."""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_csharp


def pairs(result):
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {(labels[edge["source"]], labels[edge["target"]]) for edge in result["edges"]
            if edge["relation"] == "calls"}


@pytest.mark.parametrize("storage", ["property", "field", "local"])
def test_req_qml022_ac06_lexical_generic_storage_never_selects_same_spelled_class(tmp_path, storage):
    """The same T rejection applies to a real property and its existing field/local peers."""
    path = tmp_path / "Members.cs"
    member = {"property": "public T Item{get;set;}", "field": "public T Item;", "local": ""}[storage]
    declaration = "T Item=default;" if storage == "local" else ""
    path.write_text("class T{public void Run(){}}class Holder<T>{" + member
                    + "void Use(){" + declaration + "Item.Run();}}")
    direct = extract_csharp(path)
    if storage != "local":
        actual = next(node for node in direct["nodes"] if node["label"] == "Item")
        assert any(edge["target"] == actual["id"] and edge["relation"] == "defines" for edge in direct["edges"])
    for _ in range(2):
        result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
        assert (".Use()", ".Run()") not in pairs(result)


@pytest.mark.parametrize("declared", ["Worker", "Concrete.Worker", "global::Worker"])
def test_req_qml022_ac06_concrete_property_receiver_remains_eligible(tmp_path, declared):
    """Built-in global and ordinary namespace qualification are actual concrete source spellings."""
    path = tmp_path / "Members.cs"
    worker = "class Worker{public void Run(){}}"
    path.write_text(("namespace Concrete{" + worker + "}" if declared.startswith("Concrete.") else worker)
                    + "class Holder<Worker>{public " + declared + " Item{get;set;}void Use(){Item.Run();}}")
    # The unqualified Worker here is deliberately a type parameter; only the
    # actual qualified forms may bypass it. A different ordinary concrete name
    # is exercised by the inherited/local control below.
    expected = declared != "Worker"
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert ((".Use()", ".Run()") in pairs(result)) is expected


def test_req_qml022_ac06_generic_property_shadows_inherited_data_but_concrete_local_survives(tmp_path):
    """An unavailable new property blocks inherited type borrowing without poisoning a nearer typed local."""
    path = tmp_path / "Members.cs"
    path.write_text("class T{public void Run(){}}class Worker{public void Work(){}}"
                    "class Parent{public Worker Item;}class Holder<T>:Parent{public new T Item{get;set;}"
                    "void Unknown(){Item.Work();}void Known(){Worker Item=null;Item.Work();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert (".Unknown()", ".Work()") not in pairs(result)
    assert (".Known()", ".Work()") in pairs(result)


def test_req_qml022_ac06_ordinary_concrete_property_is_unchanged_inside_nested_local(tmp_path):
    """Method/local generic scopes do not erase a differently named concrete property type."""
    path = tmp_path / "Members.cs"
    path.write_text("class Worker{public void Run(){}}class Holder<T>{public Worker Item{get;set;}"
                    "void Use<U>(){void Local<V>(){Item.Run();}Local<int>();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert ("Local()", ".Run()") in pairs(result)
