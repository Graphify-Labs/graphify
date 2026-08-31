"""Tests for multi-language AST extraction: JS/TS, Go, Rust, SQL."""
from __future__ import annotations
import shutil
from pathlib import Path
import pytest
from graphify.extract import extract_js, extract_go, extract_rust, extract, extract_sql

FIXTURES = Path(__file__).parent / "fixtures"


# ── helpers ──────────────────────────────────────────────────────────────────

def _labels(result):
    return [n["label"] for n in result["nodes"]]

def _call_pairs(result):
    node_by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in result["edges"] if e["relation"] == "calls"
    }

def _confidences(result):
    return {e["confidence"] for e in result["edges"]}


def _edges_with_relation(result, *relations):
    return [e for e in result["edges"] if e["relation"] in relations]


def _normalize_symbol_label(label: str) -> str:
    return label.strip("()").lstrip(".")


def _edge_labels(result, relation, context=None):
    labels = {n["id"]: _normalize_symbol_label(n["label"]) for n in result["nodes"]}
    pairs = set()
    for e in result["edges"]:
        if e.get("relation") != relation:
            continue
        if context is not None and e.get("context") != context:
            continue
        pairs.add((labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"])))
    return pairs


# ── TypeScript ────────────────────────────────────────────────────────────────

def test_ts_finds_class():
    r = extract_js(FIXTURES / "sample.ts")
    assert "error" not in r
    assert "HttpClient" in _labels(r)

def test_ts_finds_methods():
    r = extract_js(FIXTURES / "sample.ts")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_ts_finds_function():
    r = extract_js(FIXTURES / "sample.ts")
    assert any("buildHeaders" in l for l in _labels(r))

def test_ts_emits_calls():
    r = extract_js(FIXTURES / "sample.ts")
    calls = _call_pairs(r)
    # .post() calls .get()
    assert any("post" in src and "get" in tgt for src, tgt in calls)

def test_ts_calls_are_extracted():
    r = extract_js(FIXTURES / "sample.ts")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_ts_import_edges_have_import_context():
    r = extract_js(FIXTURES / "sample.ts")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_ts_call_edges_have_call_context():
    r = extract_js(FIXTURES / "sample.ts")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_ts_no_dangling_edges():
    r = extract_js(FIXTURES / "sample.ts")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


# ── Go ────────────────────────────────────────────────────────────────────────

def test_go_finds_struct():
    r = extract_go(FIXTURES / "sample.go")
    assert "error" not in r
    assert "Server" in _labels(r)

def test_go_finds_methods():
    r = extract_go(FIXTURES / "sample.go")
    labels = _labels(r)
    assert any("Start" in l for l in labels)
    assert any("Stop" in l for l in labels)

def test_go_finds_constructor():
    r = extract_go(FIXTURES / "sample.go")
    assert any("NewServer" in l for l in _labels(r))

def test_go_emits_calls():
    r = extract_go(FIXTURES / "sample.go")
    # main() calls NewServer and Start
    assert len(_call_pairs(r)) > 0

def test_go_has_extracted_calls():
    r = extract_go(FIXTURES / "sample.go")
    assert "EXTRACTED" in _confidences(r)


def test_go_import_edges_have_import_context():
    r = extract_go(FIXTURES / "sample.go")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_go_call_edges_have_call_context():
    r = extract_go(FIXTURES / "sample.go")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_go_no_dangling_edges():
    r = extract_go(FIXTURES / "sample.go")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


def test_go_embeds_struct_field():
    r = extract_go(FIXTURES / "sample.go")
    assert ("DataProcessor", "BaseProcessor") in _edge_labels(r, "embeds")


def test_go_interface_embedding_emits_embeds():
    r = extract_go(FIXTURES / "sample.go")
    assert ("ReaderLogger", "Logger") in _edge_labels(r, "embeds")


def test_go_struct_named_field_emits_field_context():
    r = extract_go(FIXTURES / "sample.go")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")


def test_go_method_parameter_return_contexts():
    r = extract_go(FIXTURES / "sample.go")
    assert ("Build", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("Build", "Result") in _edge_labels(r, "references", "return_type")


def test_go_method_declaration_emits_refs_only_when_name_present():
    """Regression: review feedback flagged a hypothetical UnboundLocalError in
    extract_go's method_declaration branch if `name_node` were None. Statically
    verify that every use of `method_nid` (and the `emit_go_method_refs` call
    that consumes it) is guarded by a `name_node` truthiness check — either
    nested inside `if name_node:` or following an early `if not name_node: return`.
    Same for function_declaration and `func_nid`.
    """
    import ast
    import inspect
    from graphify.extract import extract_go

    tree = ast.parse(inspect.getsource(extract_go))

    def _find_branch(root: ast.AST, type_literal: str) -> ast.If | None:
        """Return the `if t == '<type_literal>':` branch inside the walk function."""
        for child in ast.walk(root):
            if (isinstance(child, ast.If)
                    and isinstance(child.test, ast.Compare)
                    and isinstance(child.test.left, ast.Name)
                    and child.test.left.id == "t"
                    and len(child.test.comparators) == 1
                    and isinstance(child.test.comparators[0], ast.Constant)
                    and child.test.comparators[0].value == type_literal):
                return child
        return None

    method_branch = _find_branch(tree, "method_declaration")
    function_branch = _find_branch(tree, "function_declaration")
    assert method_branch is not None, "method_declaration branch not found in extract_go"
    assert function_branch is not None, "function_declaration branch not found in extract_go"

    def _is_early_return_on_falsy_name_node(stmt: ast.AST) -> bool:
        """True iff `stmt` is `if not name_node: return` (or raise/continue/break)."""
        if not isinstance(stmt, ast.If):
            return False
        test = stmt.test
        is_falsy_check = (
            isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name)
            and test.operand.id == "name_node"
        )
        if not is_falsy_check:
            return False
        terminators = (ast.Return, ast.Raise, ast.Continue, ast.Break)
        return any(isinstance(s, terminators) for s in stmt.body)

    def _guarded_by_name_node(branch: ast.If, var_name: str) -> bool:
        """True iff every read of `var_name` in `branch` is guarded by a
        `name_node` truthiness check — either lexically nested under
        `if name_node:` or after a preceding `if not name_node: return`."""
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(branch):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent

        def _stmt_chain(start: ast.AST) -> list[tuple[ast.stmt, list[ast.stmt]]]:
            """Walk up to each enclosing statement-list, returning (stmt, siblings)."""
            chain: list[tuple[ast.stmt, list[ast.stmt]]] = []
            cur: ast.AST | None = start
            while cur is not None:
                parent = parents.get(id(cur))
                if parent is None:
                    break
                if isinstance(cur, ast.stmt):
                    for attr in ("body", "orelse", "finalbody"):
                        siblings = getattr(parent, attr, None)
                        if isinstance(siblings, list) and cur in siblings:
                            chain.append((cur, siblings))
                            break
                cur = parent
            return chain

        def _is_guarded(use: ast.AST) -> bool:
            for stmt, siblings in _stmt_chain(use):
                parent = parents.get(id(stmt))
                # Case 1: lexically nested under `if name_node:` body
                if (isinstance(parent, ast.If)
                        and isinstance(parent.test, ast.Name)
                        and parent.test.id == "name_node"
                        and stmt in parent.body):
                    return True
                # Case 2: a preceding sibling is `if not name_node: return`
                idx = siblings.index(stmt)
                if any(_is_early_return_on_falsy_name_node(s) for s in siblings[:idx]):
                    return True
            return False

        for node in ast.walk(branch):
            if isinstance(node, ast.Name) and node.id == var_name:
                if not _is_guarded(node):
                    return False
        return True

    assert _guarded_by_name_node(method_branch, "method_nid"), (
        "method_nid use is not guarded by a name_node check in method_declaration branch"
    )
    assert _guarded_by_name_node(function_branch, "func_nid"), (
        "func_nid use is not guarded by a name_node check in function_declaration branch"
    )

    # Negative control: confirm the checker would actually reject the buggy
    # layout the reviewer described. A `method_nid` reference dangling without
    # any name_node guard must be caught.
    bad_source = (
        "def walk(node):\n"
        "    if t == 'method_declaration':\n"
        "        name_node = node.child_by_field_name('name')\n"
        "        if name_node:\n"
        "            method_nid = make_id('x')\n"
        "        emit_go_method_refs(node, method_nid, 1)\n"
        "        return\n"
    )
    bad_tree = ast.parse(bad_source)
    bad_branch = _find_branch(bad_tree, "method_declaration")
    assert bad_branch is not None
    assert not _guarded_by_name_node(bad_branch, "method_nid"), (
        "checker should reject method_nid used without a name_node guard"
    )


# ── Rust ──────────────────────────────────────────────────────────────────────

def test_rust_finds_struct():
    r = extract_rust(FIXTURES / "sample.rs")
    assert "error" not in r
    assert "Graph" in _labels(r)

def test_rust_finds_impl_methods():
    r = extract_rust(FIXTURES / "sample.rs")
    labels = _labels(r)
    assert any("add_node" in l for l in labels)
    assert any("add_edge" in l for l in labels)

def test_rust_finds_function():
    r = extract_rust(FIXTURES / "sample.rs")
    assert any("build_graph" in l for l in _labels(r))

def test_rust_emits_calls():
    r = extract_rust(FIXTURES / "sample.rs")
    calls = _call_pairs(r)
    assert any("build_graph" in src for src, _ in calls)

def test_rust_calls_are_extracted():
    r = extract_rust(FIXTURES / "sample.rs")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "EXTRACTED"


def test_rust_import_edges_have_import_context():
    r = extract_rust(FIXTURES / "sample.rs")
    import_edges = _edges_with_relation(r, "imports", "imports_from")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_rust_call_edges_have_call_context():
    r = extract_rust(FIXTURES / "sample.rs")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)

def test_rust_no_dangling_edges():
    r = extract_rust(FIXTURES / "sample.rs")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] in ("contains", "method", "calls"):
            assert e["source"] in node_ids


def test_rust_trait_impl_emits_implements():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("DataProcessor", "Processor") in _edge_labels(r, "implements")


def test_rust_supertrait_emits_inherits():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("Logger", "Processor") in _edge_labels(r, "inherits")


def test_rust_enum_variant_references():
    """Enum variant payload types must emit `references` edges.

    Tuple variants (`Click(T)`) and struct variants (`Resize { x: T }`) nest
    their field types under enum_variant_list -> enum_variant; that path was
    never traversed, so every enum-variant type reference was dropped.
    """
    r = extract_rust(FIXTURES / "sample.rs")
    refs = _edge_labels(r, "references")
    assert ("GraphEvent", "Graph") in refs, "tuple-variant reference missing"
    assert ("GraphEvent", "DataProcessor") in refs, "struct-variant reference missing"


def test_rust_struct_field_emits_field_context():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("DataProcessor", "Result") in _edge_labels(r, "references", "field")
    assert ("DataProcessor", "DataProcessor") not in _edge_labels(r, "references", "field")


def test_rust_tuple_struct_field_references():
    """Tuple struct fields (`struct Wrapper(A, B);`) nest their positional types
    under ordered_field_declaration_list with no field_declaration wrapper -- the
    same shape as tuple enum variants. That path was not traversed for structs, so
    tuple-struct field type references were silently dropped.
    """
    r = extract_rust(FIXTURES / "sample.rs")
    field_refs = _edge_labels(r, "references", "field")
    assert ("GraphPair", "Graph") in field_refs, "tuple-struct field reference missing"
    assert ("GraphPair", "Result") in field_refs, "tuple-struct generic field reference missing"
    assert ("GraphPair", "DataProcessor") in _edge_labels(r, "references", "generic_arg")


def test_rust_method_parameter_return_and_generic_contexts():
    r = extract_rust(FIXTURES / "sample.rs")
    assert ("build", "DataProcessor") in _edge_labels(r, "references", "parameter_type")
    assert ("build", "Result") in _edge_labels(r, "references", "return_type")
    assert ("build", "DataProcessor") in _edge_labels(r, "references", "generic_arg")


def test_rust_no_cross_crate_spurious_edges():
    """Scoped calls (Type::method) and blocklisted names must not produce
    INFERRED cross-crate calls edges (#908)."""
    from graphify.extract import extract
    crate_a = FIXTURES / "crate_a" / "src" / "lib.rs"
    crate_b = FIXTURES / "crate_b" / "src" / "lib.rs"
    r = extract([crate_a, crate_b])
    node_ids_a = {n["id"] for n in r["nodes"] if "crate_a" in (n.get("source_file") or "")}
    node_ids_b = {n["id"] for n in r["nodes"] if "crate_b" in (n.get("source_file") or "")}
    # No calls edge should cross from crate_b into crate_a
    cross_crate_calls = [
        e for e in r["edges"]
        if e["relation"] == "calls"
        and e["source"] in node_ids_b
        and e["target"] in node_ids_a
    ]
    assert cross_crate_calls == [], (
        f"Spurious cross-crate edges: {cross_crate_calls}"
    )


# ── extract() dispatch ────────────────────────────────────────────────────────

def test_extract_dispatches_all_languages():
    files = [
        FIXTURES / "sample.py",
        FIXTURES / "sample.ts",
        FIXTURES / "sample.go",
        FIXTURES / "sample.rs",
    ]
    r = extract(files)
    source_files = {n["source_file"] for n in r["nodes"] if n["source_file"]}
    # All four files should contribute nodes
    assert any("sample.py" in f for f in source_files)
    assert any("sample.ts" in f for f in source_files)
    assert any("sample.go" in f for f in source_files)
    assert any("sample.rs" in f for f in source_files)


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_hit_returns_same_result(tmp_path):
    src = FIXTURES / "sample.py"
    dst = tmp_path / "sample.py"
    dst.write_bytes(src.read_bytes())

    r1 = extract([dst])
    r2 = extract([dst])
    assert len(r1["nodes"]) == len(r2["nodes"])
    assert len(r1["edges"]) == len(r2["edges"])

def test_cache_miss_after_file_change(tmp_path):
    dst = tmp_path / "a.py"
    dst.write_text("def foo(): pass\n")
    r1 = extract([dst])

    dst.write_text("def foo(): pass\ndef bar(): pass\n")
    r2 = extract([dst])
    # bar() should appear in the second result
    labels2 = [n["label"] for n in r2["nodes"]]
    assert any("bar" in l for l in labels2)


# ── SQL ───────────────────────────────────────────────────────────────────────

def _extract_sql_or_skip(fixture: str = "sample.sql"):
    pytest.importorskip("tree_sitter_sql")
    return extract_sql(FIXTURES / fixture)


def test_sql_finds_tables():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("users" in l for l in labels)
    assert any("organizations" in l for l in labels)


def test_sql_create_table_inside_transaction_block():
    """#2953: DDL wrapped in BEGIN; ... COMMIT; must emit table nodes."""
    r = _extract_sql_or_skip("sample_transaction.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("alfa" in l for l in labels)
    assert any("gamma" in l for l in labels)
    assert any("delta" in l for l in labels)
    refs = [
        (e["source"], e["target"])
        for e in r["edges"]
        if e["relation"] == "references"
    ]
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    assert any(
        "delta" in node_by_id.get(s, "") and "alfa" in node_by_id.get(t, "")
        for s, t in refs
    )

def test_sql_finds_view():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("active_users" in l for l in labels)

def test_sql_finds_function():
    r = _extract_sql_or_skip()
    labels = [n["label"] for n in r["nodes"]]
    assert any("get_user" in l for l in labels)

def test_sql_emits_foreign_key_edge():
    r = _extract_sql_or_skip()
    relations = {e["relation"] for e in r["edges"]}
    assert "references" in relations

def test_sql_emits_reads_from_edge():
    r = _extract_sql_or_skip()
    relations = {e["relation"] for e in r["edges"]}
    assert "reads_from" in relations

def test_sql_no_dangling_edges():
    r = _extract_sql_or_skip()
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"

def test_sql_tsql_bracketed_procedure_is_recovered(tmp_path):
    """T-SQL CREATE PROCEDURE [Schema].[Name] ... AS BEGIN...END.

    The grammar has no create_procedure parse for T-SQL's AS BEGIN...END body
    idiom, so the statement lands in ERROR recovery — where a name pattern
    without a bracket-delimited alternative recovered nothing. In a T-SQL
    codebase that brackets every identifier (a common house standard), that
    made every stored procedure invisible.
    """
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "proc.sql"
    p.write_text(
        "CREATE PROCEDURE [dbo].[usp_LoadDebtors]\n"
        "    @BatchId INT\n"
        "AS\n"
        "BEGIN\n"
        "    SET NOCOUNT ON;\n"
        "    INSERT INTO dbo.Debtors (Id) SELECT Id FROM staging.Debtors;\n"
        "END;\n"
    )
    r = extract_sql(p)
    routine = [n["label"] for n in r["nodes"] if n["label"] != "proc.sql"]
    assert routine == ["[dbo].[usp_LoadDebtors]()"], routine


def test_sql_tsql_create_or_alter_procedure_is_recovered(tmp_path):
    """T-SQL spells idempotent re-creation CREATE OR ALTER (no OR REPLACE)."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "proc.sql"
    p.write_text(
        "CREATE OR ALTER PROCEDURE [Utils].[ValidateSourceView]\n"
        "AS\nBEGIN\n    SELECT 1;\nEND;\n"
        "CREATE OR ALTER PROCEDURE usp_Bare AS\nBEGIN\n SELECT 1;\nEND;\n"
    )
    r = extract_sql(p)
    labels = sorted(n["label"] for n in r["nodes"] if n["label"] != "proc.sql")
    assert labels == ["[Utils].[ValidateSourceView]()", "usp_Bare()"], labels


def test_sql_escaped_closing_bracket_in_routine_name_is_consumed(tmp_path):
    """T-SQL escapes a literal ] inside a bracketed identifier by doubling it:
    [a]]b] names the identifier a]b. A pattern that stops at the first ]
    truncated the name to [dbo].[a] — a phantom that could collide with a
    genuinely-named [dbo].[a]."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "proc.sql"
    p.write_text("CREATE PROCEDURE [dbo].[a]]b]\nAS\nBEGIN\n    SELECT 1;\nEND;\n")
    r = extract_sql(p)
    routine = [n["label"] for n in r["nodes"] if n["label"] != "proc.sql"]
    assert routine == ["[dbo].[a]]b]()"], routine


def test_sql_recovery_sites_agree_on_the_captured_name(tmp_path):
    """A mixed-delimiter name (dbo.[usp_Mixed]) must yield exactly ONE node.

    The walk-time ERROR scan and the whole-file has_error fallback recover the
    same statement; when their patterns drifted, they captured different names
    (`dbo.[usp_Mixed]` vs `dbo`), minted different ids, and _add_node's
    id-dedupe never fired — one procedure became two nodes, one of them a
    phantom named after the schema. Sharing _ROUTINE_RECOVERY_RX makes the
    drift impossible; this pins the observable behaviour.
    """
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "proc.sql"
    p.write_text("CREATE PROCEDURE dbo.[usp_Mixed] AS\nBEGIN\n SELECT 1;\nEND;\n")
    r = extract_sql(p)
    routine = [n["label"] for n in r["nodes"] if n["label"] != "proc.sql"]
    assert routine == ["dbo.[usp_Mixed]()"], routine


def test_sql_tsql_proc_shorthand_is_recovered(tmp_path):
    """T-SQL's official PROC shorthand, including CREATE OR ALTER PROC with a
    qualified bracket-delimited name, must recover like the long form."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "proc.sql"
    p.write_text(
        "CREATE OR ALTER PROC [dbo].[usp_Short]\n"
        "AS\nBEGIN\n    SELECT 1;\nEND;\n"
        "CREATE PROC usp_BareShort AS\nBEGIN\n SELECT 1;\nEND;\n"
    )
    r = extract_sql(p)
    labels = sorted(n["label"] for n in r["nodes"] if n["label"] != "proc.sql")
    assert labels == ["[dbo].[usp_Short]()", "usp_BareShort()"], labels


def test_sql_commented_ddl_is_not_fabricated_by_error_recovery(tmp_path):
    """An unrelated syntax error arms the whole-file recovery scan; DDL that
    exists only inside comments must not fabricate routine nodes from it."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "broken.sql"
    p.write_text(
        "-- CREATE PROCEDURE [dbo].[usp_LineComment] AS BEGIN SELECT 1; END;\n"
        "/*\nCREATE OR ALTER PROC dbo.usp_BlockComment AS\nBEGIN SELECT 1; END;\n*/\n"
        "CREATE PROCEDURE [dbo].[usp_Real]\nAS\nBEGIN\n    SELECT 1;\nEND;\n"
        "THIS IS NOT SQL AT ALL %%%;\n"
        # Sandwiched between broken segments so one ERROR blob's byte span
        # covers the comment — the shape that made a per-ERROR-node scan
        # unsound (a fragment can lack the comment opener entirely) and is
        # why recovery scans only the whole masked file:
        "%%% BROKEN JUNK\n"
        "-- CREATE PROC [dbo].[usp_ErrComment] AS BEGIN SELECT 1; END;\n"
        "%%% MORE BROKEN JUNK\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"] if n["label"] != "broken.sql"]
    assert "[dbo].[usp_Real]()" in labels, labels
    assert not any("Comment" in l for l in labels), (
        f"commented-out DDL fabricated a node: {labels}"
    )


def test_sql_comment_openers_inside_string_literals_do_not_hide_ddl(tmp_path):
    """A `--` or `/*` inside a string literal is data, not a comment opener.

    Both recovery scans mask comments before matching, and a mask that reads
    `'-- note'` as a line comment blanks to end-of-line — hiding a routine
    declared after the literal — while a `/*` inside a string blanks
    everything through the next real `*/`, swallowing whole statements
    between. Both must recover normally. This is behavior coverage: the
    grammar's own fb_proc_or_trigger recovery can rescue these shapes even
    under a literal-blind mask, so the mutation-killing pin for the mask
    itself is test_mask_sql_comments_preserves_literals_and_blanks_comments.
    """
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "strings.sql"
    # The lines carrying the literals start with junk so they cannot parse as
    # proper statements: literal and routine land in the SAME ERROR blob, and
    # only the mask decides whether the routine survives. (A literal in a
    # statement that parses never reaches the masked scans at all.)
    p.write_text(
        "%%% INSERT INTO log VALUES ('-- note'); "
        "CREATE PROCEDURE [dbo].[usp_AfterLineString] AS BEGIN SELECT 1; END;\n"
        "%%% SELECT 'open /* here' AS x; "
        "CREATE PROCEDURE [dbo].[usp_AfterBlockString] AS BEGIN SELECT 1; END;\n"
        "/* a real comment, giving the false opener a closer to reach */\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"] if n["label"] != "strings.sql"]
    assert "[dbo].[usp_AfterLineString]()" in labels, labels
    assert "[dbo].[usp_AfterBlockString]()" in labels, labels


def test_mask_sql_comments_literal_and_comment_handling():
    """Unit pin for _mask_sql_comments: comment openers inside literals are
    data, not comment starts; single-quoted strings are blanked (dynamic SQL
    must not be recoverable); double-quoted and bracket identifiers are
    preserved verbatim (they carry recoverable names); comments blank to
    spaces with newlines and offsets preserved, an unclosed block comment
    running to end-of-file."""
    from graphify.extractors.sql import _mask_sql_comments as mask

    # a comment opener inside a literal never blanks past the literal
    assert mask("select '-- x' from t") == "select        from t"
    assert mask("select 'a /* b' as x, 1") == "select          as x, 1"
    # '' escape is consumed as one literal (no blanking past the string)
    src = "select 'it''s -- ok', 1"
    expected = "select " + " " * len("'it''s -- ok'") + ", 1"
    assert mask(src) == expected and len(mask(src)) == len(src)
    # identifier literals are preserved verbatim, escapes included
    assert mask('CREATE FUNCTION "public"."a""b"()') == 'CREATE FUNCTION "public"."a""b"()'
    assert mask("CREATE PROCEDURE [dbo].[a]]b] AS x") == "CREATE PROCEDURE [dbo].[a]]b] AS x"
    # ...but a span that is unterminated or would swallow a comment opener is
    # NOT trusted as an identifier. A distrusted span is irreducibly
    # ambiguous, and any single reading exposed text another reading blanks
    # (re-emitting the delimiter and rescanning even re-paired later single
    # quotes, uncovering dynamic SQL), so the mask blanks the UNION of every
    # reading: the rest of the line, plus carried comment state for a raw /*
    # left open on it. The trade: a genuine [a--b] identifier loses its line,
    # never fabricating anything.
    ghost = "SELECT [Col FROM t -- CREATE PROC [dbo].[usp_Ghost] AS BEGIN SELECT 1; END;"
    assert "CREATE" not in mask(ghost) and len(mask(ghost)) == len(ghost)
    ghost2 = 'SELECT "Col FROM t /* CREATE PROC dbo.usp_Ghost AS BEGIN SELECT 1; END */'
    assert "CREATE" not in mask(ghost2) and len(mask(ghost2)) == len(ghost2)
    out = mask("select [a--b] from t")
    assert out == "select " + " " * len("[a--b] from t") and len(out) == len("select [a--b] from t")
    # a distrusted span cannot re-pair later single quotes: the dynamic SQL
    # after it stays masked (the re-emit-and-rescan defect, found by fuzzing)
    repair = "SELECT [Col's -- x] ; EXEC(N'CREATE PROC [dbo].[usp_Fake] AS BEGIN SELECT 1; END');"
    assert "CREATE" not in mask(repair) and len(mask(repair)) == len(repair)
    # a raw /* on a distrusted line with no */ carries across the newline —
    # some reading of the broken line left it open
    carry = "SELECT [a--b] /*\nCREATE PROC dbo.Fake AS BEGIN SELECT 1; END\n"
    assert "CREATE" not in mask(carry) and len(mask(carry)) == len(carry)
    # where a carry closes MID-line, the remainder of that line is blanked
    # too (under the no-carry reading the whole line may be comment or
    # string — emitting the post-*/ tail verbatim was an exposure, found by
    # differential fuzzing); recovery resumes on the NEXT line
    carry_closed = "SELECT [a--b] /*\nx */ CREATE PROC dbo.Lost AS x\nCREATE PROC dbo.Kept AS x\n"
    out = mask(carry_closed)
    assert "dbo.Lost" not in out and len(out) == len(carry_closed)
    assert "CREATE PROC dbo.Kept" in out
    # and a fresh /* after the close carries again
    recarry = "SELECT [a--b] /*\nx */ y /*\nCREATE PROC dbo.Ghost3 AS x\n"
    assert "Ghost3" not in mask(recarry)
    # dynamic SQL contents cannot survive the mask
    dyn = "EXEC(N'CREATE PROC [dbo].[Fake] AS BEGIN SELECT 1; END');"
    assert "CREATE" not in mask(dyn) and len(mask(dyn)) == len(dyn)
    # comments blank to spaces, newlines kept, offsets stable
    assert mask("a -- b") == "a     "
    assert mask("x /* y */ z") == "x         z"
    masked = mask("a /* m\nl */ b")
    assert masked == "a     \n     b" and len(masked) == len("a /* m\nl */ b")
    # an unclosed block comment masks to end-of-file, newlines kept
    unclosed = "/* CREATE PROC [dbo].[Ghost] AS\nBEGIN SELECT 1; END"
    assert "CREATE" not in mask(unclosed) and len(mask(unclosed)) == len(unclosed)
    # a /* inside a MULTI-LINE string is consumed as (blanked, line-scoped)
    # string content — it must NOT open a comment that swallows the file
    multi = (
        "SET @sql = N'SELECT a /* c1\n , b FROM t';\nGO\n"
        "CREATE PROCEDURE dbo.usp_Real AS BEGIN SELECT 1; END;\n"
    )
    out = mask(multi)
    assert "CREATE PROCEDURE dbo.usp_Real" in out and len(out) == len(multi)
    # block comments NEST (SQL Server and PostgreSQL both nest /* */): DDL
    # commented out inside a nested comment must not survive the mask
    nested = "/* outer\n   /* inner */\n   CREATE PROC dbo.usp_Fake AS BEGIN SELECT 1; END;\n*/\n"
    out = mask(nested)
    assert "CREATE" not in out and len(out) == len(nested)


def test_mask_sql_comments_invariants_fuzz():
    """Deterministic fuzz over the mask's structural invariants.

    Both rounds of masking defects were shapes nobody thought to write down,
    so pin properties instead: (1) one output character per input character,
    (2) newlines exactly preserved, (3) blanked spans are spaces, (4) the
    mask is idempotent — re-masking its own output changes nothing (the
    quote re-pairing defect broke this: exposed text re-masked differently).
    """
    import random

    from graphify.extractors.sql import _mask_sql_comments as mask

    rng = random.Random(0xC0FFEE)
    alphabet = "ab[]\"'-*/ \n;.$"
    for _ in range(20_000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 26)))
        out = mask(s)
        assert len(out) == len(s), (s, out)
        for a, b in zip(s, out):
            assert (a == "\n") == (b == "\n"), (s, out)
            assert b == a or b == " ", (s, out)
        assert mask(out) == out, (s, out)


# Frozen copy of _mask_sql_comments as of the 2026-08-24 hardening series,
# for the differential monotonicity fuzz below. Deliberately NOT imported
# from graphify: the point is that future edits to the live mask are
# compared against this fixed baseline. Update it only when a deliberate,
# reviewed decision changes what the mask must blank.
def _frozen_mask_2026_08_24(text: str) -> str:
    """Blank comment and string-literal spans, preserving every offset.

    One output character per input character: non-newline characters inside
    a blanked span become spaces and newlines are kept, so positions and
    line numbers computed against the masked text are valid against the
    original. Double-quoted and bracket-delimited identifiers are preserved
    verbatim (they carry recoverable routine names); single-quoted strings,
    line comments, and (nesting-aware) block comments are blanked. Used by
    both routine-recovery scans so CREATE PROCEDURE/FUNCTION DDL reachable
    only through a comment or a single-quoted string cannot fabricate a
    routine node when an unrelated parse error arms recovery.
    """
    out: list[str] = []
    i, n = 0, len(text)

    def _blank(upto: int) -> int:
        """Blank [i, upto), keeping newlines; return upto."""
        for c in text[i:upto]:
            out.append("\n" if c == "\n" else " ")
        return upto

    def _blank_tail_and_carry(start: int) -> int:
        """Blank from start to end-of-line, carrying comment state forward.

        The union-of-readings blank for an ambiguous stretch: the rest of the
        line is blanked outright; if the raw text of that stretch leaves a /*
        unclosed on its own line (the maximum comment depth any reading could
        be left holding), blanking continues, nesting-aware, to the closing
        */ or EOF. Where a carry closes MID-line the same rule applies to the
        remainder of that line — under the reading where the carry never
        opened, that whole line may be a comment or a string, so emitting the
        post-*/ text verbatim exposed it (found by differential fuzzing).
        Repeats until a line ends with no carry pending. Appends one output
        character per input character; returns the resume index.
        """
        k = start
        while True:
            eol = text.find("\n", k)
            eol = n if eol == -1 else eol
            depth = 0
            m2 = k
            while m2 < eol:
                if text.startswith("/*", m2):
                    depth += 1
                    m2 += 2
                elif text.startswith("*/", m2):
                    if depth:
                        depth -= 1
                    m2 += 2
                else:
                    m2 += 1
            for ch in text[k:eol]:
                out.append("\n" if ch == "\n" else " ")
            k = eol
            if not depth:
                return k
            j2 = k
            while j2 < n and depth:
                if text.startswith("/*", j2):
                    depth += 1
                    j2 += 2
                elif text.startswith("*/", j2):
                    depth -= 1
                    j2 += 2
                else:
                    j2 += 1
            for ch in text[k:j2]:
                out.append("\n" if ch == "\n" else " ")
            k = j2
            if k >= n:
                return k
            # the carry closed mid-line: the remainder of THIS line is the
            # same ambiguous stretch — loop and blank it too

    while i < n:
        c = text[i]
        if c == "'":
            # Single-quoted string: blank it. '' is an escaped quote; a
            # newline abandons the literal (see the comment above).
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            i = _blank(j)
        elif c == '"' or c == "[":
            # Delimited identifier: preserve verbatim. Doubled closers are
            # escapes. A span is DISTRUSTED when it is unterminated (no
            # closer before the newline) or would swallow a comment opener
            # on its way to the closer ('SELECT [Col FROM t -- CREATE PROC
            # [dbo]' closes on [dbo]'s bracket) — a stray delimiter is
            # ordinary in exactly the broken files this mask runs on.
            #
            # A distrusted span is irreducibly ambiguous (identifier data vs
            # stray delimiter before real comments/strings), and any attempt
            # to pick one reading exposed text the other reading blanks —
            # re-emitting the delimiter and rescanning even re-paired later
            # single quotes and uncovered dynamic SQL. So blank the UNION of
            # every reading: the rest of the line is blanked outright, and
            # any raw /* on it with no later */ on the same line carries
            # forward as (nesting-aware) comment state, since some reading
            # may have left it open — and where that carry closes mid-line,
            # the remainder of THAT line gets the same treatment, repeated
            # until a line ends carry-free (under the no-carry reading the
            # close line may itself be all comment or string, so emitting its
            # post-*/ tail verbatim was an exposure). Over-blanking loses at
            # most routines on lines already entangled with the broken one (a
            # conservative false negative; a routine named like [a--b] is
            # inside that loss); under-blanking is what fabricates, and every
            # reading's blank set stays a subset of this one.
            closer = '"' if c == '"' else "]"
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == closer:
                    if j + 1 < n and text[j + 1] == closer:
                        j += 2
                        continue
                    j += 1
                    closed = True
                    break
                j += 1
            span = text[i:j]
            if closed and "--" not in span and "/*" not in span:
                out.append(span)
                i = j
            else:
                i = _blank_tail_and_carry(i)
        elif c == "-" and i + 1 < n and text[i + 1] == "-":
            j = i
            while j < n and text[j] != "\n":
                j += 1
            i = _blank(j)
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            depth, j = 1, i + 2
            while j < n and depth:
                if text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    depth += 1
                    j += 2
                elif text[j] == "*" and j + 1 < n and text[j + 1] == "/":
                    depth -= 1
                    j += 2
                else:
                    j += 1
            i = _blank(j)  # unclosed comment: j == n, blanks to end-of-file
        else:
            out.append(c)
            i += 1
    return "".join(out)


def test_mask_sql_comments_monotone_against_frozen_baseline():
    """Differential fuzz: the live mask must never EXPOSE a character the
    frozen baseline blanks. Blanking more is allowed (conservative); blanking
    less is the fabrication channel — every masking defect in the 2026-08-24
    series (quote re-pairing, carry-close exposure) was a monotonicity
    violation of exactly this kind, and none was caught by hand-written
    shapes first.

    If an INTENTIONAL over-blanking change lands (the live mask blanks more
    than the baseline), this still passes; if an intentional EXPOSURE change
    lands (the mask deliberately blanks less), refresh the frozen copy above
    to the new revision as part of that reviewed change — do not delete the
    test or loosen the property.
    """
    import random

    from graphify.extractors.sql import _mask_sql_comments as mask

    rng = random.Random(0xBA5E11E)
    alphabet = "ab[]\"'-*/ \n;.$"
    for _ in range(20_000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40)))
        live = mask(s)
        base = _frozen_mask_2026_08_24(s)
        assert len(live) == len(base) == len(s)
        for idx, (b, lv, orig) in enumerate(zip(base, live, s)):
            if b == " " and orig != " ":
                assert lv == " ", (
                    f"live mask exposes char {idx} ({orig!r}) that the frozen "
                    f"baseline blanks:\n input={s!r}\n base={base!r}\n live={live!r}"
                )


def test_sql_dynamic_sql_and_unclosed_comment_do_not_fabricate_routines(tmp_path):
    """DDL text reachable only through a single-quoted string (dynamic SQL) or
    an unterminated block comment must not mint routine nodes when an
    unrelated parse error arms the recovery scans."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "dynamic.sql"
    p.write_text(
        "THIS IS NOT SQL AT ALL %%%;\n"
        "EXEC(N'CREATE OR ALTER PROC [dbo].[usp_Dynamic] AS BEGIN SELECT 1; END');\n"
        "SET @sql = N'SELECT 1 /* opener inside a multi-line string\n"
        " must not swallow what follows';\n"
        "/* nested /* comments */ hide this:\n"
        "CREATE PROC [dbo].[usp_Nested] AS BEGIN SELECT 1; END;\n*/\n"
        "SELECT [Col FROM t -- CREATE PROC [dbo].[usp_Bracketed] AS BEGIN SELECT 1; END;\n"
        "CREATE PROCEDURE [dbo].[usp_Real]\nAS\nBEGIN\n    SELECT 1;\nEND;\n"
        "/* an unterminated comment swallows the rest of the file\n"
        "CREATE PROC [dbo].[usp_Unterminated] AS BEGIN SELECT 1; END;\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"] if n["label"] != "dynamic.sql"]
    assert "[dbo].[usp_Real]()" in labels, labels
    fabricated = [
        label for label in labels
        if any(k in label for k in ("Dynamic", "Nested", "Bracketed", "Unterminated"))
    ]
    assert not fabricated, (
        f"string-embedded or comment-swallowed DDL fabricated a node: {labels}"
    )


def test_sql_ddl_keywords_inside_delimited_identifiers_do_not_fabricate(tmp_path):
    """A preserved delimited identifier keeps its text verbatim in the masked
    scan (it may BE a recoverable name), so DDL keywords occurring inside one
    ('SELECT 1 AS [CREATE PROCEDURE dbo.usp_Phantom pending]') were matched
    by the recovery regex and minted a phantom routine. Recovery now skips a
    match whose CREATE starts inside a preserved identifier span — a genuine
    statement's NAME may be a delimited identifier; its CREATE never is."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "alias.sql"
    p.write_text(
        "THIS IS NOT SQL AT ALL %%%;\n"
        "SELECT 1 AS [CREATE PROCEDURE dbo.usp_Phantom pending];\n"
        'SELECT 2 AS "CREATE PROC dbo.usp_Phantom2 queued";\n'
        "CREATE PROCEDURE [dbo].[usp_Real]\nAS\nBEGIN\n    SELECT 1;\nEND;\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"] if n["label"] != "alias.sql"]
    assert labels == ["[dbo].[usp_Real]()"], labels


def test_sql_create_inside_a_bare_word_does_not_fabricate(tmp_path):
    """CREATE must match as a word: without a leading boundary the recovery
    regex matched CREATE inside a bare identifier, so 'SELECT AUTOCREATE
    PROCEDURE x FROM t;' in an error-bearing file minted a phantom x().
    (Delimited identifiers are span-skipped at the scan site; a bare word
    has no span, so the regex itself must refuse.)"""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "bare.sql"
    p.write_text(
        "THIS IS NOT SQL AT ALL %%%;\n"
        "SELECT AUTOCREATE PROCEDURE x FROM t;\n"
        "EXEC dbo.PRECREATE FUNCTION y;\n"
        "CREATE PROCEDURE [dbo].[usp_Real]\nAS\nBEGIN\n    SELECT 1;\nEND;\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"] if n["label"] != "bare.sql"]
    assert labels == ["[dbo].[usp_Real]()"], labels


def test_sql_escaped_double_quote_in_routine_name_is_consumed(tmp_path):
    """ANSI SQL escapes a literal double quote inside a delimited identifier
    by doubling it: "a""b" names the identifier a"b. A pattern that stops at
    the first closing quote truncated the recovered name to "dbo"."a" — the
    "" twin of the bracket ]] escape handled above.

    The AS BEGIN body idiom keeps the whole statement in ERROR recovery: for a
    statement the grammar CAN parse, tree-sitter-sql itself truncates the
    object_reference at the "" escape (emitting `"b"` as a stray ERROR child),
    which is an upstream grammar defect this extractor cannot repair."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "fn.sql"
    p.write_text('CREATE PROCEDURE "dbo"."a""b"\nAS\nBEGIN\n    SELECT 1;\nEND;\n')
    r = extract_sql(p)
    routine = [n["label"] for n in r["nodes"] if n["label"] != "fn.sql"]
    assert routine == ['"dbo"."a""b"()'], routine


def test_sql_cte_is_not_read_as_a_table():
    """#2577: a name bound by WITH ... AS (...) is scoped to its statement, not a table.

    Emitting it as a reads_from target minted a bare, sourceless stub carrying no
    schema, file, or language namespace, so a CTE named `levels` or `slug` collided
    with a same-named node from another language. The real table in the same
    FROM/JOIN must still resolve.
    """
    r = _extract_sql_or_skip("sample_cte.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert "levels" not in labels, "CTE name leaked into the graph as a table node"

    reads = [e for e in r["edges"] if e["relation"] == "reads_from"]
    assert reads, "the real table reference should still emit a reads_from edge"
    assert not any(e["target"] == "levels" for e in reads), "CTE emitted as a reads_from target"

    # the real v_roles -> users edge is kept
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    assert (nid["v_roles"], nid["users"]) in {(e["source"], e["target"]) for e in reads}

def test_sql_column_list_cte_is_not_read_as_a_table(tmp_path):
    """#2577: `WITH levels(a, b) AS (...)` — the name precedes a column list."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE users (id INT, role TEXT);\n"
        "CREATE VIEW v AS\n"
        "  WITH levels(role, rank) AS (SELECT 'admin', 1)\n"
        "  SELECT * FROM users JOIN levels ON levels.role = users.role;\n"
    )
    r = extract_sql(p)
    labels = [n["label"] for n in r["nodes"]]
    assert "levels" not in labels
    reads = [e for e in r["edges"] if e["relation"] == "reads_from"]
    assert not any(e["target"] == "levels" for e in reads)

def test_sql_cte_shadows_same_named_table_within_its_statement(tmp_path):
    """#2577: inside the declaring statement the CTE shadows a real same-named
    table (SQL scoping), so v1's FROM binds to the CTE and emits nothing; v2 has
    no CTE in scope and reads the real table. Exactly one deterministic edge."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE levels (role TEXT);\n"
        "CREATE VIEW v1 AS WITH levels AS (SELECT 'admin' AS role)"
        " SELECT * FROM levels;\n"
        "CREATE VIEW v2 AS SELECT * FROM levels;\n"
    )
    r = extract_sql(p)
    reads = [e for e in r["edges"] if e["relation"] == "reads_from"]
    assert len(reads) == 1, f"expected exactly one reads_from, got {reads}"
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    assert reads[0]["source"] == nid["v2"]
    assert reads[0]["target"] == nid["levels"]  # the real, sourced table node

def test_sql_subquery_cte_does_not_suppress_outer_real_table(tmp_path):
    """#2577 refinement: a WITH inside a subquery is scoped to that subquery
    only. A statement-wide pre-collect would also swallow the OUTER reference
    to the real `t2`, dropping a true edge — per-subtree scoping keeps it."""
    pytest.importorskip("tree_sitter_sql")
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE t2 (id INT);\n"
        "CREATE VIEW v6 AS SELECT * FROM t2 JOIN"
        " (WITH t2 AS (SELECT 1 AS id) SELECT * FROM t2) sub"
        " ON sub.id = t2.id;\n"
    )
    r = extract_sql(p)
    nid = {n["label"]: n["id"] for n in r["nodes"]}
    reads = {(e["source"], e["target"]) for e in r["edges"]
             if e["relation"] == "reads_from"}
    assert (nid["v6"], nid["t2"]) in reads, (
        "outer reference to the real t2 table was wrongly suppressed"
    )

def test_php_builtin_base_class_never_inherits_from_cross_language_class(tmp_path):
    """#2812: `class FooApiException extends \\Exception` names PHP's global
    built-in. The sourceless stub it mints was unique corpus-wide, so the rewire
    bound it to an unrelated TypeScript `Exception` class and the PHP class
    inherited across languages. No supertype edge may target a TypeScript node."""
    ts = tmp_path / "app" / "exception.ts"
    ts.parent.mkdir(parents=True)
    ts.write_text(
        "export class Exception extends Error {\n"
        "  constructor(message: string) { super(message); }\n"
        "}\n"
    )
    php = tmp_path / "packages" / "FooApiException.php"
    php.parent.mkdir(parents=True)
    php.write_text(
        "<?php\n"
        "\n"
        "namespace Foo\\Exceptions;\n"
        "\n"
        "class FooApiException extends \\Exception\n"
        "{\n"
        "}\n"
    )

    r = extract([php, ts], root=tmp_path)
    ts_nodes = {n["id"] for n in r["nodes"]
                if str(n.get("source_file", "")).endswith(".ts")}
    supertypes = [e for e in r["edges"]
                  if e["relation"] in ("inherits", "implements", "extends")
                  and str(e.get("source_file", "")).endswith(".php")]
    assert supertypes, "PHP inheritance was not extracted at all"
    for e in supertypes:
        assert e["target"] not in ts_nodes, (
            f"PHP supertype leaked cross-language: {e}"
        )
    # The base stays on its sourceless external stub rather than vanishing.
    sourceless = {n["id"] for n in r["nodes"] if not n.get("source_file")}
    assert any(e["target"] in sourceless for e in supertypes), (
        f"PHP base class lost its external stub: {supertypes}"
    )


def test_sql_cte_never_binds_to_cross_language_symbol(tmp_path):
    """#2577: the reported leak — the CTE's sourceless stub was unique corpus-wide,
    so _rewire_unique_stub_nodes bound it to a same-named symbol from ANOTHER
    language (schema_v_roles -> ui_levels). With the CTE excluded, no reads_from
    edge may target a TypeScript node."""
    pytest.importorskip("tree_sitter_sql")
    sql = tmp_path / "schema.sql"
    sql.write_text(
        "CREATE TABLE users (id INT, role TEXT);\n"
        "CREATE VIEW v_roles AS\n"
        "  WITH levels AS (SELECT 'admin' AS role)\n"
        "  SELECT * FROM users JOIN levels ON levels.role = users.role;\n"
    )
    ts = tmp_path / "ui.ts"
    ts.write_text("export function levels() { return ['admin']; }\n")

    r = extract([sql, ts], root=tmp_path)
    ts_nodes = {n["id"] for n in r["nodes"]
                if str(n.get("source_file", "")).endswith(".ts")}
    for e in r["edges"]:
        if e["relation"] == "reads_from":
            assert e["target"] not in ts_nodes, (
                f"SQL reads_from leaked cross-language: {e}"
            )

def test_sql_cross_file_fk_resolves_and_never_leaks_scan_path(tmp_path):
    """#2324: a REFERENCES target defined in ANOTHER file must collapse onto the
    real table node (via the sourceless-stub rewire), and no node id or edge
    endpoint may embed the absolute scan path. Before the fix, the fallback
    minted a node-less id under the referencing file's own stem, which with
    absolute inputs leaked the machine path AND could never match the m1
    definition, so prisma-style cross-migration FKs dangled."""
    pytest.importorskip("tree_sitter_sql")
    from graphify.ids import make_id

    m1 = tmp_path / "prisma" / "migrations" / "m1"
    m2 = tmp_path / "prisma" / "migrations" / "m2"
    m1.mkdir(parents=True)
    m2.mkdir(parents=True)
    (m1 / "migration.sql").write_text(
        'CREATE TABLE "Tenant" (\n'
        '    "id" TEXT NOT NULL,\n'
        '    CONSTRAINT "Tenant_pkey" PRIMARY KEY ("id")\n'
        ');\n'
    )
    (m2 / "migration.sql").write_text(
        'CREATE TABLE "StockGapEvent" (\n'
        '    "id" TEXT NOT NULL,\n'
        '    "tenantId" TEXT NOT NULL,\n'
        '    CONSTRAINT "StockGapEvent_pkey" PRIMARY KEY ("id")\n'
        ');\n'
        'ALTER TABLE "StockGapEvent" ADD CONSTRAINT "StockGapEvent_tenantId_fkey"'
        ' FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id");\n'
    )

    r = extract(
        [(m1 / "migration.sql").resolve(), (m2 / "migration.sql").resolve()],
        root=tmp_path,
    )
    node_ids = {n["id"] for n in r["nodes"]}

    # (a) the FK resolved cross-file onto the REAL Tenant definition node
    tenant_ids = [i for i in node_ids if i.endswith("m1_migration_tenant")]
    assert len(tenant_ids) == 1, f"expected one real Tenant node, got {tenant_ids}"
    ref_targets = {e["target"] for e in r["edges"] if e["relation"] == "references"}
    assert tenant_ids[0] in ref_targets, (
        f"cross-file FK did not rewire onto {tenant_ids[0]}; "
        f"references targets: {ref_targets}"
    )

    # (b) no dangling endpoints anywhere
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"

    # (c) the absolute scan path never leaks into any id or endpoint
    abs_slug = make_id(str(tmp_path.resolve()))
    for i in node_ids:
        assert abs_slug not in i, f"absolute path leaked into node id: {i}"
    for e in r["edges"]:
        assert abs_slug not in e["source"], f"absolute path leaked: {e['source']}"
        assert abs_slug not in e["target"], f"absolute path leaked: {e['target']}"

def test_sql_alter_table_fk_edge():
    """ALTER TABLE ... FOREIGN KEY ... REFERENCES produces a references edge."""
    r = _extract_sql_or_skip("sample_alter_fk.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"

def test_sql_schema_qualified_names():
    """Schema-qualified table names (Schema.Table) are preserved."""
    r = _extract_sql_or_skip("sample_schema_qualified.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert any("Sales.Customer" in l for l in labels)
    assert any("Sales.SalesOrder" in l for l in labels)

def test_sql_schema_qualified_alter_fk():
    """ALTER TABLE with schema-qualified names produces correct edges."""
    r = _extract_sql_or_skip("sample_schema_qualified.sql")
    fk_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert len(fk_edges) >= 1
    node_ids = {n["id"] for n in r["nodes"]}
    for e in fk_edges:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"

def test_sql_plpgsql_functions_survive_parse_errors():
    """PL/pgSQL bodies make tree-sitter-sql emit ERROR nodes; the functions
    must still be extracted (#1910), without cascading into later statements."""
    r = _extract_sql_or_skip("sample_plpgsql.sql")
    labels = [n["label"] for n in r["nodes"]]
    # Both PL/pgSQL functions extracted, schema-qualified name kept whole
    assert "exposed.important_function()" in labels
    assert "tagged_quote_fn()" in labels
    # Tables before and after the broken functions still extract
    assert any("accounts" in l for l in labels)
    assert any("audit_log" in l for l in labels)
    # No spurious or empty nodes from the error recovery
    for l in labels:
        assert l, "empty node label"
        assert l != "ERROR"
    # Every function got a contains edge from the file node
    contains_targets = {e["target"] for e in r["edges"] if e["relation"] == "contains"}
    fn_ids = {n["id"] for n in r["nodes"] if n["label"].endswith("()")}
    assert fn_ids <= contains_targets

def test_sql_plpgsql_clean_function_not_double_emitted():
    """A cleanly-parsed LANGUAGE sql function in the same file is emitted once."""
    r = _extract_sql_or_skip("sample_plpgsql.sql")
    labels = [n["label"] for n in r["nodes"]]
    assert labels.count("plain_sql_fn()") == 1
    # And nothing else is duplicated either
    ids = [n["id"] for n in r["nodes"]]
    assert len(ids) == len(set(ids))

def test_sql_quoted_plpgsql_routines_are_recovered():
    """#2180: quoted identifiers must not defeat the ERROR-node name recovery.

    Generated PostgreSQL DDL (Supabase-style dumps, for example) quotes every
    identifier: CREATE OR REPLACE FUNCTION "public"."fn"(...). The recovery
    pattern matched a bare [\\w$.]+, which stops at the leading quote, so every
    routine whose body also failed to parse -- RAISE, PERFORM, :=, IF..THEN,
    bare NULL; -- was dropped with no warning and exit code 0. The same body
    with an *unquoted* name recovered fine, which is why the drop looked like it
    depended only on the body statement.
    """
    r = _extract_sql_or_skip("sample_plpgsql_quoted.sql")
    labels = [n["label"] for n in r["nodes"]]
    for name in (
        "raise_exception_fn",
        "raise_notice_fn",
        "perform_fn",
        "assign_fn",
        "if_then_fn",
        "null_body_fn",
        "quoted_proc",
    ):
        assert f'"public"."{name}"()' in labels, f"{name} dropped from a quoted-DDL file (#2180)"

def test_sql_quoted_plpgsql_file_stays_clean():
    """The #2180 recovery must not add junk, duplicates, or drop the tables."""
    r = _extract_sql_or_skip("sample_plpgsql_quoted.sql")
    labels = [n["label"] for n in r["nodes"]]
    # Tables before and after the unparseable routines still extract.
    assert any("accounts" in l for l in labels)
    assert any("audit_log" in l for l in labels)
    # No empty or ERROR labels leaked out of the recovery.
    for l in labels:
        assert l, "empty node label"
        assert l != "ERROR"
    # Nothing emitted twice (a routine must not come from both paths).
    ids = [n["id"] for n in r["nodes"]]
    assert len(ids) == len(set(ids)), "duplicate node ids"
    assert len(labels) == len(set(labels)), f"duplicate labels: {labels}"
    # Every recovered routine is reachable from the file node.
    contains_targets = {e["target"] for e in r["edges"] if e["relation"] == "contains"}
    fn_ids = {n["id"] for n in r["nodes"] if n["label"].endswith("()")}
    assert fn_ids <= contains_targets
