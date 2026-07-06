"""Regression tests: TypeScript/JavaScript decorator references.

`@Component`, `@Injectable`, `@Input`, `@Inject`, `@Entity`, … emitted no edge
to the decorator symbol — the `decorator` node kind was never walked. This is
framework-critical (Angular, NestJS, Vue class components, TypeORM).

Decorators are emitted as `references` edges with context="decorator" from the
decorated entity: the class for class/field/parameter decorators, the method
for method (and its parameter) decorators. Targets resolve through the same
sourceless-stub path as type references, so a decorator imported from another
module collapses onto its real definition.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _class_nid(file: str, cls: str) -> str:
    return _make_id(_file_stem(Path(file)), cls)


def _method_nid(file: str, cls: str, method: str) -> str:
    return _make_id(_class_nid(file, cls), method)


def _has_deco(result: dict, owner_nid: str, deco: str) -> bool:
    """True if owner_nid references the (cross-file, bare-stub) decorator symbol."""
    tgt = _make_id(deco)
    return any(
        e["source"] == owner_nid
        and e["target"] == tgt
        and e["relation"] == "references"
        and e.get("context") == "decorator"
        for e in result["edges"]
    )


def test_class_decorator_on_exported_class(tmp_path):
    # The canonical Angular shape: decorator sits on the wrapping export_statement.
    f = _write(tmp_path / "src" / "c.ts",
               "@Component({ selector: 'app' })\n"
               "export class AppComponent {}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/c.ts", "AppComponent"), "Component")


def test_class_decorator_on_plain_class(tmp_path):
    f = _write(tmp_path / "src" / "s.ts",
               "@Injectable()\nclass Service {}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/s.ts", "Service"), "Injectable")


def test_stacked_class_decorators(tmp_path):
    f = _write(tmp_path / "src" / "s.ts",
               "@Injectable()\n@Entity()\nexport class Repo {}\n")
    r = extract([f], cache_root=tmp_path)
    nid = _class_nid("src/s.ts", "Repo")
    assert _has_deco(r, nid, "Injectable")
    assert _has_deco(r, nid, "Entity")


def test_method_decorator_attributes_to_method(tmp_path):
    f = _write(tmp_path / "src" / "c.ts",
               "export class C {\n"
               "  @HostListener('click') onClick() {}\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _method_nid("src/c.ts", "C", "onClick"), "HostListener")
    # and NOT to the class
    assert not _has_deco(r, _class_nid("src/c.ts", "C"), "HostListener")


def test_stacked_method_decorators(tmp_path):
    f = _write(tmp_path / "src" / "c.ts",
               "export class C {\n"
               "  @Get('/') @UseGuards(Auth) list() {}\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    nid = _method_nid("src/c.ts", "C", "list")
    assert _has_deco(r, nid, "Get")
    assert _has_deco(r, nid, "UseGuards")


def test_field_decorator_attributes_to_class(tmp_path):
    # The field is not a graph node, so its decorator attributes to the class.
    f = _write(tmp_path / "src" / "c.ts",
               "export class C {\n"
               "  @Input() name: string;\n"
               "  @Column() age: number;\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    nid = _class_nid("src/c.ts", "C")
    assert _has_deco(r, nid, "Input")
    assert _has_deco(r, nid, "Column")


def test_parameter_decorator_attributes_to_constructor(tmp_path):
    f = _write(tmp_path / "src" / "c.ts",
               "export class C {\n"
               "  constructor(@Inject(TOKEN) private s: Svc) {}\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _method_nid("src/c.ts", "C", "constructor"), "Inject")


def test_namespaced_decorator_uses_property_name(tmp_path):
    f = _write(tmp_path / "src" / "c.ts",
               "@core.Component({})\nexport class Widget {}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/c.ts", "Widget"), "Component")


def test_external_decorator_stub_disambiguated_per_file(tmp_path):
    """An external decorator (definition absent from the corpus — the common
    framework case) still emits a `references`/`decorator` edge from every class
    that applies it — the core behavior of this fix.

    Convergence note (v0.9.0+): the edges no longer collapse onto a single shared
    bare-name stub. v0.9.0 embeds the full repo-relative path in node IDs and
    #1462 disambiguates imported type stubs across files, so the same external
    `Injectable` referenced from two files now resolves to two distinct per-file
    stubs (`src_a_ts_injectable`, `src_b_ts_injectable`) rather than one hub. (A
    single in-corpus reference still keeps the bare `injectable` stub — only
    cross-file, unresolved references are split.)"""
    a = _write(tmp_path / "src" / "a.ts", "@Injectable()\nexport class A {}\n")
    b = _write(tmp_path / "src" / "b.ts", "@Injectable()\nexport class B {}\n")
    r = extract([a, b], cache_root=tmp_path)

    # Each class emits exactly one decorator-context edge to an `Injectable`
    # node (checked by label, since the stub id is now path-qualified).
    id_to_label = {n["id"]: n.get("label") for n in r["nodes"]}
    deco_edges = [
        e for e in r["edges"]
        if e["relation"] == "references" and e.get("context") == "decorator"
    ]
    a_targets = [e["target"] for e in deco_edges if e["source"] == _class_nid("src/a.ts", "A")]
    b_targets = [e["target"] for e in deco_edges if e["source"] == _class_nid("src/b.ts", "B")]
    assert len(a_targets) == 1 and id_to_label.get(a_targets[0]) == "Injectable"
    assert len(b_targets) == 1 and id_to_label.get(b_targets[0]) == "Injectable"

    # v0.9.0 full-path IDs + #1462 stub disambiguation: external stubs are split
    # per file, so the two no longer converge on one shared hub.
    assert a_targets[0] != b_targets[0], (
        "external decorator stubs are disambiguated per file in v0.9.0+; "
        "they no longer converge on a single shared stub"
    )
