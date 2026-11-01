"""REQ-QML-022-AC03/06: one immutable unit amortizes inclusion-guard classification."""
from graphify.extract import extract
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp, walk
import graphify.extractors.cpp_include_guards as guards
import graphify.extractors.qt_cpp_identity as identities


def test_guarded_declarations_reuse_one_source_guard_classification(tmp_path, monkeypatch):
    """Two hundred real locals retain identity without repeating a complete header walk per binding."""
    source = ("#ifndef LOADER_HPP\n#define LOADER_HPP\nvoid boot() { QQmlApplicationEngine engine;\n"
              + "\n".join(f"int item{i} = 0;" for i in range(200)) + "\n}\n#endif\n")
    path = tmp_path / "loader.hpp"
    path.write_bytes(source.encode())
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    calls, classify = [], guards.is_include_guard

    def observed(node):
        accepted = classify(node)
        if accepted:
            calls.append(node.start_byte)
        return accepted

    monkeypatch.setattr(guards, "is_include_guard", observed)
    # Characterize the old direct imported predicate too, without replacing
    # classification behavior. The new identity path uses its unit-owned index.
    if hasattr(identities, "is_include_guard"):
        monkeypatch.setattr(identities, "is_include_guard", observed)
    unit = read_cpp(path, tmp_path)
    mapping = map_cpp(unit, result["nodes"], result["edges"], root=tmp_path)
    index = identities.CppDeclarationIdentity(unit, mapping)
    assert set(index.declarations) == {"engine", *(f"item{i}" for i in range(200))}
    assert all(not record["conditional"] for group in index.declarations.values() for record in group)
    position = source.index("\n}")
    assert index.resolve("engine", position)["status"] == "resolved"
    guard = next(node for node in walk(unit.tree) if node.type == "preproc_ifdef")
    assert unit.include_guards.accepts(guard)
    assert len(calls) <= 2, "one immutable unit must not rescan the whole header for every local"
