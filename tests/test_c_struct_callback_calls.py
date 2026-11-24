from graphify.extract import extract


def test_c_member_callbacks_do_not_bind_to_free_functions(tmp_path):
    source = tmp_path / "a.c"
    source.write_text("""
struct Ops { void (*run)(void); };
void run(void) {}
void invoke_pointer(struct Ops *ops) { ops->run(); }
void invoke_value(struct Ops ops) { ops.run(); }
void direct(void) { run(); }
""", encoding="utf-8")
    result = extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    callers = {labels[e["source"]] for e in result["edges"]
               if e["relation"] == "calls" and labels[e["target"]] == "run()"}
    assert callers == {"direct()"}
