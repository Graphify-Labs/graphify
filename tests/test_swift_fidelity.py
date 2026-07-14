from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _labels(result: dict) -> dict[str, str]:
    return {str(node["id"]): str(node.get("label", "")) for node in result["nodes"]}


def _edges(result: dict, relation: str) -> list[tuple[str, str, dict]]:
    labels = _labels(result)
    return [
        (labels.get(str(edge["source"]), ""), labels.get(str(edge["target"]), ""), edge)
        for edge in result["edges"]
        if edge.get("relation") == relation
    ]


def _nodes(result: dict) -> dict[str, dict]:
    return {str(node["id"]): node for node in result["nodes"]}


def _method_owner(result: dict, method_id: str) -> str:
    labels = _labels(result)
    return next(
        labels.get(str(edge["source"]), "")
        for edge in result["edges"]
        if edge.get("relation") == "method" and str(edge.get("target")) == method_id
    )


def test_swift_overloads_have_distinct_signature_ids_and_literal_calls_resolve(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Service.swift",
        """class Service {
  func load(_ id: String) {}
  func load(_ id: Int) {}
  func go() { load("x"); load(1) }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    overloads = [node for node in result["nodes"] if node.get("label") == ".load()"]
    assert len(overloads) == 2
    assert len({node["id"] for node in overloads}) == 2
    go_calls = [target for source, target, _ in _edges(result, "calls") if source == ".go()"]
    assert go_calls.count(".load()") == 2


def test_swift_unique_default_argument_call_remains_extracted(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Defaults.swift",
        'func greet(_ name: String = "world") {}\nfunc go() { greet() }\n',
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    calls = [
        edge
        for caller, target, edge in _edges(result, "calls")
        if caller == "go()" and target == "greet()"
    ]
    assert len(calls) == 1
    assert calls[0]["confidence"] == "EXTRACTED"


def test_swift_static_call_resolves_without_a_type_table(tmp_path: Path) -> None:
    service = _write(
        tmp_path / "Service.swift",
        "class Service { static func build() {} }\n",
    )
    main = _write(tmp_path / "Main.swift", "func go() { Service.build() }\n")
    result = extract(
        [service, main],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    calls = [
        edge
        for caller, target, edge in _edges(result, "calls")
        if caller == "go()" and target == ".build()"
    ]
    assert len(calls) == 1
    assert calls[0]["confidence"] == "EXTRACTED"


def test_swift_overload_identity_covers_extensions_and_declaration_details(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "Overloads.swift",
        """protocol Left {}
protocol Right {}
class Service {
  func load(_ value: String) {}
  static func dispatch(_ value: Int) {}
  func dispatch(_ value: Int) {}
}
extension Service { func load(_ value: Int) {} }
func make() -> Int { 1 }
func make() -> String { "" }
func constrained<T: Left>(_ value: T) {}
func constrained<T: Right>(_ value: T) {}
func run(_ service: Service) { service.load(1) }
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    assert len([node for node in result["nodes"] if node.get("label") == ".load()"]) == 2
    assert len([node for node in result["nodes"] if node.get("label") == ".dispatch()"]) == 2
    assert len([node for node in result["nodes"] if node.get("label") == "make()"]) == 2
    assert len([node for node in result["nodes"] if node.get("label") == "constrained()"]) == 2

    nodes = _nodes(result)
    call_targets = [
        nodes[str(edge["target"])]
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and _labels(result).get(str(edge["source"])) == "run()"
    ]
    assert any(
        node.get("label") == ".load()"
        and (node.get("metadata") or {}).get("parameter_types") == ["Int"]
        for node in call_targets
    )


def test_swift_receiver_types_are_scoped_per_method(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Scopes.swift",
        """class A { func ping() {} }
class B { func ping() {} }
class Runner {
  func one(_ value: A) { value.ping() }
  func two(_ value: B) { value.ping() }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    labels = _labels(result)
    calls = {
        labels[str(edge["source"])]: _method_owner(result, str(edge["target"]))
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and labels.get(str(edge.get("target"))) == ".ping()"
    }
    assert calls == {".one()": "A", ".two()": "B"}


def test_swift_typed_arguments_and_trailing_closures_select_overloads(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "Calls.swift",
        """class Service {
  func load(_ value: String) {}
  func load(_ value: Int) {}
}
func perform() {}
func perform(_ body: () -> Void) {}
func run(_ service: Service, _ value: String) {
  service.load(value)
  perform {}
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    nodes = _nodes(result)
    labels = _labels(result)
    targets = [
        nodes[str(edge["target"])]
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and labels.get(str(edge["source"])) == "run()"
    ]
    assert any(
        node.get("label") == ".load()"
        and (node.get("metadata") or {}).get("parameter_types") == ["String"]
        for node in targets
    )
    assert any(
        node.get("label") == "perform()"
        and (node.get("metadata") or {}).get("arity") == 1
        for node in targets
    )


def test_swift_protocol_requirements_associated_types_and_aliases(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Repository.swift",
        """protocol Repository {
  associatedtype Item
  var item: Item { get }
  func load(_ id: String) -> Item
}
class Store: Repository {
  typealias Item = String
  var item: String = ""
  func load(_ id: String) -> String { item }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    types = {node.get("type") for node in result["nodes"]}
    assert "associated_type" in types
    assert "type_alias" in types
    assert "protocol_requirement" in types
    assert "protocol_property_requirement" in types
    requirement_edges = [
        edge for _, _, edge in _edges(result, "implements")
        if edge.get("context", "").startswith("protocol_")
    ]
    assert {edge["context"] for edge in requirement_edges} == {
        "protocol_requirement",
        "protocol_property_requirement",
    }


def test_swift_cross_file_protocol_requirements_use_associated_type_bindings(
    tmp_path: Path,
) -> None:
    protocol = _write(
        tmp_path / "Repository.swift",
        """protocol Repository {
  associatedtype Item
  init(value: Item)
  subscript(index: Int) -> Item { get }
  var item: Item { get set }
  func save(_ item: Item) -> Item
}
""",
    )
    store = _write(
        tmp_path / "Store.swift",
        """class Store: Repository {
  typealias Item = String
  required init(value: String) {}
  subscript(index: Int) -> String { "" }
  var item: String = ""
  func save(_ item: String) -> String { item }
}
""",
    )
    result = extract(
        [protocol, store],
        cache_root=tmp_path,
        parallel=False,
    )
    labels = _labels(result)
    type_conformances = [
        (source, target)
        for source, target, edge in _edges(result, "implements")
        if not edge.get("context")
    ]
    assert ("Store", "Repository") in type_conformances

    member_implementations = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "implements"
        and str(edge.get("context", "")).startswith("protocol_")
    ]
    assert len(member_implementations) == 4
    assert {labels[str(edge["source"])] for edge in member_implementations} == {
        ".init()",
        ".subscript()",
        ".save()",
        "item",
    }


def test_swift_protocol_requirement_mismatches_fail_closed(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Mismatch.swift",
        """protocol Contract {
  var value: String { get set }
  func load(_ value: String) -> String
}
class Broken: Contract {
  let value: Int = 0
  static func load(_ value: String) -> Int { 0 }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    assert not [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "implements"
        and str(edge.get("context", "")).startswith("protocol_")
    ]


def test_swift_protocol_generic_alias_async_and_static_property_semantics(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "AdvancedProtocol.swift",
        """protocol Contract {
  associatedtype Item
  static var count: Int { get }
  func save(_ values: Item) async -> Item
}
struct Good: Contract {
  typealias Item = [String]
  static var count: Int = 0
  func save(_ values: [String]) -> [String] { values }
}
struct Bad: Contract {
  typealias Item = [String]
  var count: Int = 0
  func save(_ values: [String]) async -> [String] { values }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    labels = _labels(result)
    owners = {
        str(edge["target"]): labels.get(str(edge["source"]), "")
        for edge in result["edges"]
        if edge.get("relation") in ("method", "defines")
    }
    member_edges = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "implements"
        and str(edge.get("context", "")).startswith("protocol_")
    ]
    assert {
        (owners.get(str(edge["source"])), labels.get(str(edge["source"])))
        for edge in member_edges
    } == {("Good", ".save()"), ("Good", "count"), ("Bad", ".save()")}


def test_swift_protocol_extension_methods_are_default_implementations(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "Defaults.swift",
        """protocol ValueProvider { func value() -> Int }
extension ValueProvider { func value() -> Int { 1 } }
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    value_nodes = [
        node for node in result["nodes"] if node.get("label") == ".value()"
    ]
    assert len(value_nodes) == 2
    assert sum(node.get("type") == "protocol_requirement" for node in value_nodes) == 1


def test_swift_deep_property_receiver_and_factory_return_chain_resolve(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "Chain.swift",
        """class Service { func fetch() {} }
class Container { let service: Service = Service() }
class Root { let container: Container = Container() }
class Factory { static func make() -> Service { Service() } }
class Runner {
  let root: Root = Root()
  func run() { self.root.container.service.fetch() }
  func runFactory() { Factory.make().fetch() }
}
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    run_calls = [target for source, target, _ in _edges(result, "calls") if source == ".run()"]
    factory_calls = [target for source, target, _ in _edges(result, "calls") if source == ".runFactory()"]
    assert ".fetch()" in run_calls
    assert ".fetch()" in factory_calls
    assert ".make()" in factory_calls


def test_swift_free_factory_and_cross_file_overloads_resolve(tmp_path: Path) -> None:
    definitions = _write(
        tmp_path / "Definitions.swift",
        """class Service { func fetch() {} }
func make() -> Service { Service() }
func load(_ value: String) {}
func load(_ value: Int) {}
""",
    )
    usage = _write(
        tmp_path / "Usage.swift",
        "func run() { make().fetch(); load(1) }\n",
    )
    result = extract(
        [definitions, usage],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    nodes = _nodes(result)
    labels = _labels(result)
    targets = [
        nodes[str(edge["target"])]
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and labels.get(str(edge["source"])) == "run()"
    ]
    assert {node.get("label") for node in targets} >= {
        "make()",
        ".fetch()",
        "load()",
    }
    assert any(
        node.get("label") == "load()"
        and (node.get("metadata") or {}).get("parameter_types") == ["Int"]
        for node in targets
    )


def test_swift_extension_merge_survives_canonical_id_remap_and_stubs(
    tmp_path: Path,
) -> None:
    declaration = _write(tmp_path / "Foo.swift", "class Foo {}\n")
    extension = _write(
        tmp_path / "Foo+Extension.swift",
        "extension Foo { func describe() {} }\n",
    )
    usage = _write(
        tmp_path / "Use.swift",
        "func use(_ value: Foo) { value.describe() }\n",
    )
    result = extract(
        [declaration, extension, usage],
        cache_root=tmp_path,
        parallel=False,
    )
    foo_nodes = [node for node in result["nodes"] if node.get("label") == "Foo"]
    assert len(foo_nodes) == 1
    foo_id = str(foo_nodes[0]["id"])
    describe_ids = {
        str(edge["target"])
        for edge in result["edges"]
        if edge.get("relation") == "method" and str(edge.get("source")) == foo_id
    }
    assert any(_labels(result).get(method_id) == ".describe()" for method_id in describe_ids)


def test_swiftpm_manifest_maps_targets_products_dependencies_and_sources(tmp_path: Path) -> None:
    manifest = _write(
        tmp_path / "Package.swift",
        """// swift-tools-version: 5.9
import PackageDescription
let package = Package(
  name: "Demo",
  products: [.library(name: "Demo", targets: ["Core"])],
  dependencies: [.package(url: "https://example.com/Dep.git", from: "1.0.0")],
  targets: [
    .target(name: "Core"),
    .target(name: "App", dependencies: ["Core"])
  ]
)
""",
    )
    core = _write(tmp_path / "Sources" / "Core" / "Core.swift", "public func core() {}\n")
    app = _write(tmp_path / "Sources" / "App" / "Main.swift", "import Core\nfunc main() { core() }\n")
    result = extract(
        [manifest, core, app],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    labels = set(_labels(result).values())
    node_ids = [str(node["id"]) for node in result["nodes"]]
    assert len(node_ids) == len(set(node_ids))
    assert all(
        str(edge[endpoint]) in set(node_ids)
        for edge in result["edges"]
        for endpoint in ("source", "target")
    )
    assert {"Demo", "Core", "App", "Core.swift", "Main.swift"} <= labels
    assert ("Demo", "Core") in [(a, b) for a, b, _ in _edges(result, "contains")]
    assert ("Core", "Core.swift") in [(a, b) for a, b, _ in _edges(result, "contains")]
    assert ("Main.swift", "Core") in [(a, b) for a, b, _ in _edges(result, "imports")]
    assert ("Demo", "Dep") in [(a, b) for a, b, _ in _edges(result, "depends_on")]

    graph = build_from_json(result)
    labels = {str(node_id): str(data.get("label", "")) for node_id, data in graph.nodes(data=True)}
    built_dependencies = {
        (labels.get(str(source), ""), labels.get(str(target), ""))
        for source, target, data in graph.edges(data=True)
        if data.get("relation") == "depends_on"
    }
    assert ("Demo", "Dep") in built_dependencies


def test_swiftpm_membership_honors_input_scope_sources_excludes_and_cache(
    tmp_path: Path,
) -> None:
    manifest = _write(
        tmp_path / "Package.swift",
        """import PackageDescription
let package = Package(
  name: "Scoped",
  targets: [.target(
    name: "Core",
    exclude: ["Selected/Excluded.swift"],
    sources: ["Selected"]
  )]
)
""",
    )
    included = _write(
        tmp_path / "Sources" / "Core" / "Selected" / "Included.swift",
        "public func included() {}\n",
    )
    excluded = _write(
        tmp_path / "Sources" / "Core" / "Selected" / "Excluded.swift",
        "public func excluded() {}\n",
    )
    outside = _write(
        tmp_path / "Sources" / "Core" / "Outside.swift",
        "public func outside() {}\n",
    )

    cache = tmp_path / ".cache"
    first = extract(
        [manifest, included, excluded, outside],
        cache_root=cache,
        parallel=False,
    )
    first_members = {
        target
        for source, target, edge in _edges(first, "contains")
        if source == "Core" and edge.get("context") == "target_source"
    }
    assert first_members == {"Included.swift"}

    added = _write(
        tmp_path / "Sources" / "Core" / "Selected" / "Added.swift",
        "public func added() {}\n",
    )
    included.unlink()
    second = extract(
        [manifest, added, excluded, outside],
        cache_root=cache,
        parallel=False,
    )
    second_members = {
        target
        for source, target, edge in _edges(second, "contains")
        if source == "Core" and edge.get("context") == "target_source"
    }
    assert second_members == {"Added.swift"}

    manifest_only = extract([manifest], cache_root=cache, parallel=False)
    assert not [
        edge
        for _, _, edge in _edges(manifest_only, "contains")
        if edge.get("context") == "target_source"
    ]


def test_swiftpm_same_named_targets_are_manifest_qualified(tmp_path: Path) -> None:
    one_manifest = _write(
        tmp_path / "One" / "Package.swift",
        'import PackageDescription\nlet package = Package(name: "Same", targets: [.target(name: "Core")])\n',
    )
    one_source = _write(
        tmp_path / "One" / "Sources" / "Core" / "One.swift",
        "public func one() {}\n",
    )
    two_manifest = _write(
        tmp_path / "Two" / "Package.swift",
        'import PackageDescription\nlet package = Package(name: "Same", targets: [.target(name: "Core")])\n',
    )
    two_source = _write(
        tmp_path / "Two" / "Sources" / "Core" / "Two.swift",
        "public func two() {}\n",
    )
    result = extract(
        [one_manifest, one_source, two_manifest, two_source],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    core_nodes = [
        node
        for node in result["nodes"]
        if node.get("label") == "Core" and node.get("type") == "module"
    ]
    assert len(core_nodes) == 2
    assert len({str(node["id"]) for node in core_nodes}) == 2


def test_swiftpm_does_not_link_sources_without_extracted_file_nodes(
    tmp_path: Path,
) -> None:
    manifest = _write(
        tmp_path / "Package.swift",
        'import PackageDescription\nlet package = Package(name: "Native", targets: [.target(name: "Core")])\n',
    )
    assembly = _write(tmp_path / "Sources" / "Core" / "start.S", ".globl _start\n")
    result = extract(
        [manifest, assembly],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    node_ids = {str(node["id"]) for node in result["nodes"]}
    assert all(
        str(edge[endpoint]) in node_ids
        for edge in result["edges"]
        for endpoint in ("source", "target")
    )
    assert not [
        edge
        for edge in result["edges"]
        if edge.get("context") == "target_source"
    ]
