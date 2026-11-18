"""Regression tests for Pascal/Delphi calls through a global object variable.

Delphi applications are built on global singletons: a unit declares
``var DM: TDM = nil;`` beside its data module and every other unit calls
``DM.OpenPeriod``. The per-file pass throws the qualifier away and looks the
bare member name up in the CALLER's scope, so these calls either vanish or --
worse -- bind to a same-named method of the calling class.

``graphify.pascal_singleton_resolution`` resolves them through the variable's
declared type. The fixtures encode the cases that must NOT resolve as much as
the ones that must: a published form field, a local, an array and an unused
unit each shadow or invalidate a global of the same name.

Static fixtures rather than tmp_path, for the reason given in
tests/test_pascal_resolution.py: the extractor's cross-file lookups walk UP
from the source file, and the system temp directory is not a stable project
root.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract, extract_pascal

FIXTURES = Path(__file__).parent / "fixtures" / "pascal_singleton"
DATA = FIXTURES / "Data.pas"
CALLER = FIXTURES / "Caller.pas"
STRANGER = FIXTURES / "Stranger.pas"


def _graph(*paths: Path) -> dict:
    with tempfile.TemporaryDirectory() as cache:
        return extract(list(paths), cache_root=Path(cache), parallel=False)


def _calls(graph: dict) -> set[tuple[str, str, str, str]]:
    """``(caller file, caller label, callee label, callee file)`` per call edge.

    Both fixtures declare a ``Run()``, so the caller's file is part of the
    identity here, not decoration.
    """
    labels = {n["id"]: str(n.get("label", "")) for n in graph["nodes"]}
    files = {n["id"]: Path(str(n.get("source_file", ""))).name for n in graph["nodes"]}
    return {
        (files.get(e["source"], ""), labels.get(e["source"], ""),
         labels.get(e["target"], ""), files.get(e["target"], ""))
        for e in graph["edges"] if e.get("relation") == "calls"
    }


def test_call_through_a_global_reaches_the_method():
    """`DM.Calc(2026)` -- the plain case, which resolved to nothing before."""
    assert ("Caller.pas", "Run()", "Calc()", "Data.pas") in _calls(_graph(DATA, CALLER))


def test_parameterless_qualified_call_is_seen_at_all():
    """`DM.OpenPeriod;` has no exprCall wrapper in the grammar, so the call
    pass never looked at this shape and produced nothing for it."""
    assert ("Caller.pas", "Run()", "OpenPeriod()", "Data.pas") in _calls(_graph(DATA, CALLER))


def test_global_call_beats_a_same_named_method_on_the_caller():
    """The correctness case. `TCallerForm` has its own `Shared`, so resolving
    `DM.Shared` by bare name binds the call to the calling class instead of
    to the data module."""
    calls = _calls(_graph(DATA, CALLER))
    assert ("Caller.pas", "Run()", "Shared()", "Data.pas") in calls
    assert ("Caller.pas", "Run()", "Shared()", "Caller.pas") not in calls


def test_method_inherited_by_the_globals_class_resolves():
    """`Derived.Inherited_Only` is declared on TBase, not TDerived, so this
    only works if the resolver walks the repaired `inherits` chain."""
    assert ("Caller.pas", "Run()", "Inherited_Only()", "Data.pas") in _calls(_graph(DATA, CALLER))


def test_shadowed_names_produce_no_call_at_all():
    """A Delphi form publishes its components as plain fields, so `Query`
    inside a form method is the component -- even though this very unit also
    declares a global `Query: TDM`. `Local: TDM` shadows likewise. Exactly one
    `OpenPeriod()` call may survive: the genuine `DM.OpenPeriod`.
    """
    calls = _calls(_graph(DATA, CALLER))
    reaching = [c for c in calls if c[2] == "OpenPeriod()"]
    assert reaching == [("Caller.pas", "Run()", "OpenPeriod()", "Data.pas")], reaching


def test_local_and_field_qualifiers_are_withheld_by_the_extractor():
    """The shadow decision belongs to the extractor, which alone can see the
    routine's own declarations."""
    qualifiers = [rc.get("qualifier") for rc in extract_pascal(CALLER)["raw_calls"]]
    assert "dm" in qualifiers
    assert "local" not in qualifiers
    assert "query" not in qualifiers


def test_self_is_not_treated_as_a_global():
    """`Self.Shared` must keep reaching the inherited-call resolver rather
    than being diverted to the object-aware one."""
    assert all(rc.get("qualifier") != "self" for rc in extract_pascal(CALLER)["raw_calls"])


def test_array_typed_global_is_not_given_its_element_type():
    """`Sizes: array[1..12] of TDM` is an array, not a TDM."""
    globals_declared = extract_pascal(DATA)["global_vars"]
    assert globals_declared.get("dm") == "tdm"
    assert "sizes" not in globals_declared


def test_global_is_invisible_without_a_uses_clause():
    """Pascal identifier visibility is not transitive. Stranger.pas does not
    use Data, so its `DM.OpenPeriod` must not be attributed to Data's global
    even though the whole corpus is in front of the resolver."""
    calls = _calls(_graph(DATA, CALLER, STRANGER))
    assert not [c for c in calls if c[0] == "Stranger.pas"]
    # ...while the unit that DOES use Data still resolves.
    assert ("Caller.pas", "Run()", "OpenPeriod()", "Data.pas") in calls


def test_resolver_only_adds_extracted_call_edges():
    """The resolver is additive: everything it contributes is a `calls` edge
    carrying its own context and a source location."""
    graph = _graph(DATA, CALLER)
    added = [e for e in graph["edges"] if e.get("context") == "global object call"]
    assert added, "fixtures should produce at least one resolved call"
    for edge in added:
        assert edge["relation"] == "calls"
        assert edge["confidence"] == "EXTRACTED"
        assert edge["source_location"]
        assert edge["source_file"].endswith("Caller.pas")


# --- the two shapes the on-disk fixtures above cannot produce ----------------
#
# Both of these bit on a real Delphi corpus while every fixture test passed,
# because a fixture keeps its units in one directory: the used unit is then
# always found on disk, and the merged paths always match the extractor's.
# They are pinned here against the resolver's inputs directly.

def _corpus() -> tuple[list[dict], list[dict]]:
    """A two-unit corpus in the standard Delphi layout, as the merge leaves it.

    `source_file` is relativised on the nodes, and the `uses Shared` edge
    points at a target id with NO node: the external stub for a unit the
    per-file pass could not find is materialised after resolvers run.
    """
    nodes = [
        {"id": "datamodules_shared_pas", "label": "Shared.pas",
         "source_file": "DataModules/Shared.pas"},
        {"id": "shared_tshareddm", "label": "TSharedDM",
         "source_file": "DataModules/Shared.pas"},
        {"id": "shared_loadperiod", "label": "LoadPeriod()",
         "source_file": "DataModules/Shared.pas"},
        {"id": "projects_app_appform_pas", "label": "AppForm.pas",
         "source_file": "Projects/App/AppForm.pas"},
        {"id": "appform_tappform", "label": "TAppForm",
         "source_file": "Projects/App/AppForm.pas"},
        {"id": "appform_go", "label": "Go()",
         "source_file": "Projects/App/AppForm.pas"},
    ]
    edges = [
        {"source": "datamodules_shared_pas", "target": "shared_tshareddm",
         "relation": "contains"},
        {"source": "shared_tshareddm", "target": "shared_loadperiod",
         "relation": "method"},
        {"source": "projects_app_appform_pas", "target": "appform_tappform",
         "relation": "contains"},
        {"source": "appform_tappform", "target": "appform_go", "relation": "method"},
        {"source": "projects_app_appform_pas", "target": "shared", "relation": "imports"},
    ]
    return nodes, edges


def _per_file() -> list[dict]:
    """Per-file results still carry the ABSOLUTE path the extractor was handed."""
    return [
        {"nodes": [{"id": "datamodules_shared_pas", "label": "Shared.pas",
                    "source_file": r"C:\proj\DataModules\Shared.pas"}],
         "edges": [], "raw_calls": [],
         "global_vars": {"shareddm": "tshareddm"}},
        {"nodes": [{"id": "projects_app_appform_pas", "label": "AppForm.pas",
                    "source_file": r"C:\proj\Projects\App\AppForm.pas"}],
         "edges": [],
         "raw_calls": [{"source_file": r"C:\proj\Projects\App\AppForm.pas",
                        "source_location": "L15", "caller_nid": "appform_go",
                        "callee": "loadperiod", "qualifier": "shareddm"}],
         "global_vars": {}},
    ]


def test_uses_resolves_when_the_unit_stub_has_no_node_yet():
    """`uses Shared` leaves an edge to `_make_id("Shared")` and no node, which
    is what a Delphi tree with units outside the project directory produces for
    nearly every import. Matching the edge's target id against the corpus is
    the only way to see the unit from here."""
    from graphify.pascal_singleton_resolution import resolve_pascal_singleton_calls

    nodes, edges = _corpus()
    resolve_pascal_singleton_calls(_per_file(), nodes, edges)
    added = [e for e in edges if e.get("relation") == "calls"]
    assert added, "the call through SharedDM should resolve"
    assert added[0]["source"] == "appform_go"
    assert added[0]["target"] == "shared_loadperiod"


def test_absolute_extractor_paths_are_matched_to_relativised_graph_paths():
    """The globals live in a per-file result keyed by an absolute path while
    the graph is keyed by a relative one. extract.py's own call index warns
    about exactly this: key on ids, not on source_file strings."""
    from graphify.pascal_singleton_resolution import resolve_pascal_singleton_calls

    nodes, edges = _corpus()
    per_file = _per_file()
    # Make the mismatch total: no path component is shared with the graph's.
    per_file[0]["nodes"][0]["source_file"] = r"D:\elsewhere\DataModules\Shared.pas"
    per_file[1]["raw_calls"][0]["source_file"] = r"D:\elsewhere\Projects\App\AppForm.pas"
    resolve_pascal_singleton_calls(per_file, nodes, edges)
    assert [e for e in edges if e.get("relation") == "calls"]


def test_no_uses_clause_means_no_edge_in_the_split_layout():
    """The control: without the import edge the global is simply not in scope,
    however unambiguous its name is across the corpus."""
    from graphify.pascal_singleton_resolution import resolve_pascal_singleton_calls

    nodes, edges = _corpus()
    edges = [e for e in edges if e.get("relation") != "imports"]
    resolve_pascal_singleton_calls(_per_file(), nodes, edges)
    assert not [e for e in edges if e.get("relation") == "calls"]
