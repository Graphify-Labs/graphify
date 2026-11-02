"""A C++ `x.m()` / `x->m()` binds by x's type, not by whichever `m` the file declares.

Through `Base* b`, `b->draw()` used to bind to the file's own `Derived::draw` as
EXTRACTED, purely because the names matched.
"""

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]) -> dict[tuple[str, str], str]:
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache")
    node = {n["id"]: n for n in result["nodes"]}

    def name(nid: str) -> str:
        n = node.get(nid, {})
        return f'{n.get("source_file", "").rsplit("/", 1)[-1].rsplit(chr(92), 1)[-1]}:{n.get("label", nid)}'

    return {
        (name(e["source"]), name(e["target"])): e["confidence"]
        for e in result["edges"]
        if e["relation"] == "calls"
    }


HEADER = "class Base { public: virtual void draw(); void lock(); };\n"


def test_base_pointer_call_reaches_the_base_method(tmp_path):
    calls = _calls(tmp_path, {
        "base.h": HEADER,
        "derived.cpp": (
            '#include "base.h"\n'
            "class Derived : public Base { public: void draw() override; };\n"
            "void Derived::draw() {}\n"
            "void render(Base* b) { b->draw(); }\n"
        ),
    })
    assert ("derived.cpp:render()", "base.h:.draw()") in calls
    assert not any(src == "derived.cpp:render()" and tgt.startswith("derived.cpp:")
                   for src, tgt in calls)


def test_untyped_receiver_does_not_bind_by_name(tmp_path):
    calls = _calls(tmp_path, {"widget.cpp": (
        "class Widget { public: void paint(); };\n"
        "void Widget::paint() {}\n"
        "template <typename T> void show(T& t) { t.paint(); }\n"
    )})
    assert not any(src.endswith("show()") for src, _ in calls)


def test_typed_local_receiver_still_resolves(tmp_path):
    calls = _calls(tmp_path, {"widget.cpp": (
        "class Widget { public: void paint(); };\n"
        "void run() { Widget w; w.paint(); }\n"
    )})
    assert ("widget.cpp:run()", "widget.cpp:.paint()") in calls


def test_this_call_keeps_in_file_binding(tmp_path):
    calls = _calls(tmp_path, {"widget.cpp": (
        "class Widget { public: void paint(); void run(); };\n"
        "void Widget::run() { this->paint(); }\n"
    )})
    assert any(src.endswith("run()") and tgt.endswith("paint()") for src, tgt in calls)
