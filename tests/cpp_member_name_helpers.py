"""Neutral literal member names retain source ownership, roles and byte ranges."""
from graphify.extract import extract
from graphify.extractors.cpp_member_identity import member_fact


def source(*, owner="Panel", native=False, out_of_line=False, reverse=False):
    fields = ["UpperType Field;", "LowerType field;", "void (*Callback)();", "void (*callback)();"]
    upper = "Q_INVOKABLE " if native else ""
    lower = "Q_SLOT " if native else ""
    methods = [upper + "void Run()" + (";" if out_of_line else "{upper();}"),
               lower + "void run()" + (";" if out_of_line else "{lower();}")]
    entries = fields + methods
    if reverse:
        entries.reverse()
    base = ":public QObject" if native else ""
    marker = "Q_OBJECT\nQML_NAMED_ELEMENT(CaseOwner)\n" if native else ""
    text = ("struct UpperType{};struct LowerType{};void upper(){}void lower(){}\n"
            f"class {owner}{base}{{\n" + marker + "public:\n" + "\n".join(entries) + "\n};\n")
    if out_of_line:
        text += f"void {owner}::Run(){{upper();}}\nvoid {owner}::run(){{lower();}}\n"
    return text


def owner_node(result, name="Panel"):
    nodes = [node for node in result["nodes"] if node["label"] == name and node.get("_callable_class")]
    assert len(nodes) == 1
    return nodes[0]


def owned(result, name="Panel"):
    owner = owner_node(result, name)
    targets = {edge["target"] for edge in result["edges"] if edge["source"] == owner["id"]
               and edge["relation"] in {"method", "defines"}}
    return [node for node in result["nodes"] if node["id"] in targets]


def members(result):
    return [(node, fact) for node in result["nodes"] if (fact := member_fact(node))]


def span(raw, fact):
    value = fact["span"]
    assert 0 <= value["start_byte"] < value["end_byte"] <= len(raw)
    for end in ("start", "end"):
        prefix = raw[:value[end + "_byte"]]
        assert (value[end + "_row"], value[end + "_column"]) == (prefix.count(b"\n"), len(prefix.rsplit(b"\n", 1)[-1]))
    return raw[value["start_byte"]:value["end_byte"]]


def project(root, raw, *, native=False):
    path = root / "unit.cpp"
    path.write_bytes(raw)
    if native:
        (root / "Main.qml").write_bytes(b"import Public.MemberNames 1.0\nCaseOwner{function invoke(){Run();run();}}\n")
        (root / "CMakeLists.txt").write_bytes(b"qt_add_qml_module(app URI Public.MemberNames VERSION 1.0 QML_FILES Main.qml SOURCES unit.cpp)\n")
        (root / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    return path


def facade(root):
    paths = sorted(path for path in root.iterdir() if path.is_file() and path.suffix in {".cpp", ".h", ".qml", ".py", ".txt"})
    cold = extract(paths, root=root, cache_root=root, parallel=False)
    warm = extract(paths, root=root, cache_root=root, parallel=False)
    assert cold == warm and not cold["failed_sources"] and not cold["qml_failures"]
    return cold
