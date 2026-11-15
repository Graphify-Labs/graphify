"""Local C++ values cannot bind to same-named corpus symbols."""
import pytest
from graphify.extract import extract


@pytest.mark.parametrize("declaration", ["auto box = [](int x){return x;};", "std::function<int(int)> box = [](int x){return x;};", "TFunction<int(int)> box;"])
@pytest.mark.parametrize("same_file", [False, True])
def test_local_callable_shadows_function(tmp_path, declaration, same_file):
    other = "int box(int x){return x;}"
    a = tmp_path / "a.cpp"
    a.write_text((other if same_file else "") + "\nint run(){" + declaration + " return box(1);}", encoding="utf-8")
    paths = [a]
    if not same_file:
        b = tmp_path / "b.cpp"
        b.write_text(other, encoding="utf-8")
        paths.append(b)
    r = extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path)
    caller = next(n["id"] for n in r["nodes"] if n["label"] == "run()")
    assert not any(e["source"] == caller and e["relation"] == "calls" for e in r["edges"])


def test_block_local_does_not_hide_a_later_free_call(tmp_path):
    a = tmp_path / "a.cpp"
    a.write_text("void box() {}\nvoid run() {{auto box=[]{}; box();} box();}", encoding="utf-8")
    r = extract([a], root=tmp_path, parallel=False, cache_root=tmp_path)
    calls = [e for e in r["edges"] if e["relation"] == "calls"]
    assert len(calls) == 1
    assert calls[0]["source_location"] == "L2"


def test_parameter_shadowing_keeps_nested_argument_calls(tmp_path):
    a = tmp_path / "a.cpp"
    a.write_text("int helper(){return 1;}\nint run(std::function<int(int)> box){return box(helper());}", encoding="utf-8")
    b = tmp_path / "b.cpp"
    b.write_text("int box(int x){return x;}", encoding="utf-8")
    r = extract([a,b], root=tmp_path, parallel=False, cache_root=tmp_path)
    nodes = {n["id"]: n for n in r["nodes"]}
    caller = next(n["id"] for n in r["nodes"] if n["label"] == "run()")
    calls = [e for e in r["edges"] if e["source"] == caller and e["relation"] == "calls"]
    assert [nodes[e["target"]]["label"] for e in calls] == ["helper()"]
