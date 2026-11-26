from graphify.extract import extract


def test_go_selector_respects_import_shadowing(tmp_path):
    files = {
        "go.mod": "module example.com/m\n\ngo 1.22\n",
        "store/store.go": "package store\nfunc Save() {}\n",
        "app/app.go": """package app
import alias "example.com/m/store"
type Local struct{}
func (Local) Save() {}
func Register(func()) {}
func Before() { alias.Save() }
func Nested() {
    {
        alias := Local{}
        alias.Save()
    }
    alias.Save()
}
func Callback(alias Local) { Register(alias.Save) }
func Param(alias Local) { alias.Save() }
func Unknown(alias interface{Save()}) { alias.Save() }
""",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = extract([tmp_path / name for name in files], root=tmp_path,
                     cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}

    def targets(caller, relation="calls"):
        return {
            (nodes[edge["target"]]["source_file"], nodes[edge["target"]]["label"])
            for edge in result["edges"]
            if edge["relation"] == relation
            and nodes[edge["source"]]["label"] == caller
            and nodes[edge["target"]]["label"] in {"Save()", ".Save()"}
        }

    package = ("store/store.go", "Save()")
    local = ("app/app.go", ".Save()")
    assert targets("Before()") == {package}
    assert targets("Nested()") == {package, local}
    assert targets("Callback()", "indirect_call") == {local}
    assert targets("Param()") == {local}
    assert targets("Unknown()") == set()
