"""Regression coverage for same-file node-id collisions (#3302).

``ids.py`` deliberately casefolds and strips punctuation so three independent
producers mint identical ids — which means DISTINCT declared names in one
file can normalize to one id (``Session``/``session()``,
``_get_connection``/``get_connection``, ``visit_TEXT``/``visit_text``). The
per-file ``seen_ids`` guard used to keep the first definition and silently
drop every later one, mis-attributing the loser's edges and body calls to
the survivor. The fix (extractors/collisions.py, the generalization of Go's
#2779 salt) keeps the plain id on ONE canonical member and gives every other
member a deterministic name-derived salt.

Same-raw-name re-definitions (``@overload`` stubs, ``if PY2:``/``else:``
conditional defs) are deliberately still ONE node — asserted here on purpose
so a future change to that collapse is a conscious one.
"""

from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Parser

from graphify.build import build_from_json, build_merge
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.collisions import (
    SymbolCollisionCensus,
    canonical_raw_name,
    collision_salt,
    exported_canonical_raw_name,
    salted_symbol_id,
)
from graphify.ids import make_id


def _extract(root: Path, pattern: str = "*") -> dict:
    return extract(
        sorted(p for p in root.rglob(pattern) if p.is_file()),
        cache_root=root,
        root=root,
        parallel=False,
    )


def _ids(result: dict, *, label: str, suffix: str) -> set[str]:
    return {
        node["id"]
        for node in result["nodes"]
        if str(node.get("source_file", "")).endswith(suffix)
        and str(node.get("label", "")).strip(".()") == label
    }


def _node(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n["id"] == nid), None)


ADAPTER_SRC = (
    "class Adapter:\n"
    "    def _get_connection(self):\n"
    "        return 1\n"
    "\n"
    "    def get_connection(self):\n"
    "        return self._get_connection()\n"
    "\n"
    "    def unrelated(self):\n"
    "        return 2\n"
)


def test_issue_repro_all_three_methods_survive(tmp_path: Path) -> None:
    """The #3302 repro: `_get_connection` and `get_connection` are two nodes.

    Pre-fix, `get_connection` (L5) had no node at all — its id was held by the
    private sibling — and both `method` edges plus the public body's calls
    were attributed to the private node.
    """
    (tmp_path / "mod.py").write_text(ADAPTER_SRC)
    result = _extract(tmp_path)

    private = _ids(result, label="_get_connection", suffix="mod.py")
    public = _ids(result, label="get_connection", suffix="mod.py")
    unrelated = _ids(result, label="unrelated", suffix="mod.py")
    assert len(private) == 1, f"private sibling missing: {private}"
    assert len(public) == 1, f"public sibling missing: {public}"
    assert len(unrelated) == 1
    assert private != public, "siblings collapsed onto one node id"

    # The PUBLIC spelling keeps the plain id — by-name references, docs, and
    # semantic-tier ids can only ever say `get_connection`.
    plain = make_id("mod", "adapter", "get_connection")
    assert public == {plain}
    assert private == {salted_symbol_id(plain, "_get_connection")}

    public_node = _node(result, plain)
    assert public_node is not None and public_node["source_location"] == "L5"

    # Each method edge points at its own sibling...
    method_targets = {
        e["target"] for e in result["edges"] if e.get("relation") == "method"
    }
    assert public | private | unrelated <= method_targets
    # ...and the public body's `self._get_connection()` binds to the PRIVATE
    # node (pre-fix it self-looped onto the collapsed survivor and vanished).
    calls = [
        e
        for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source") in public
    ]
    assert [e["target"] for e in calls] == list(private), calls


def test_case_collision_class_keeps_plain_id(tmp_path: Path) -> None:
    """`class Session` vs `def session()` (requests/sessions.py): two nodes.

    The class keeps the plain id it already holds in existing graphs; the
    factory function is salted. Its methods stay under the class's plain id.
    """
    (tmp_path / "sess.py").write_text(
        "class Session:\n"
        "    def request(self):\n"
        "        return 1\n"
        "\n"
        "def session():\n"
        "    return Session()\n"
    )
    result = _extract(tmp_path)

    plain = make_id("sess", "Session")
    assert _ids(result, label="Session", suffix="sess.py") == {plain}
    assert _ids(result, label="session", suffix="sess.py") == {
        salted_symbol_id(plain, "session")
    }
    assert _ids(result, label="request", suffix="sess.py") == {
        make_id(plain, "request")
    }


def test_collision_ids_are_order_independent(tmp_path: Path) -> None:
    """Reversing declaration order must not move a single id (#2779's rule).

    The hard case on purpose: with `def session()` FIRST, the first mint pass
    hands it the plain id and the class's method ids derive from a salted
    class id — settling the census re-runs the walk so every derived id is
    re-minted from the canonical assignment.
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
    (a / "sess.py").write_text(
        "class Session:\n"
        "    def request(self):\n"
        "        return 1\n"
        "\n"
        "def session():\n"
        "    return Session()\n"
    )
    (b / "sess.py").write_text(
        "def session():\n"
        "    return Session()\n"
        "\n"
        "class Session:\n"
        "    def request(self):\n"
        "        return 1\n"
    )
    ids_a = {n["id"] for n in _extract(a)["nodes"]}
    ids_b = {n["id"] for n in _extract(b)["nodes"]}
    assert ids_a == ids_b, f"declaration order moved ids: {ids_a ^ ids_b}"


def test_extraction_is_reproducible_across_runs(tmp_path: Path) -> None:
    """Same input, same ids — twice over, node for node, edge for edge."""
    (tmp_path / "mod.py").write_text(ADAPTER_SRC)

    def _shape(result: dict) -> tuple:
        nodes = tuple(
            sorted((n["id"], n["label"], n.get("source_location", "")) for n in result["nodes"])
        )
        edges = tuple(
            sorted(
                (e["source"], e["target"], e["relation"], e.get("source_location", ""))
                for e in result["edges"]
            )
        )
        return nodes, edges

    first = _shape(_extract(tmp_path))
    second = _shape(_extract(tmp_path))
    assert first == second


def test_underscore_ladder_public_spelling_keeps_plain_id(tmp_path: Path) -> None:
    """`_get_module` vs `__get_module` (six's `_SixMetaPathImporter` pair)."""
    (tmp_path / "imp.py").write_text(
        "class Importer:\n"
        "    def __get_module(self):\n"
        "        return 1\n"
        "\n"
        "    def _get_module(self):\n"
        "        return 2\n"
    )
    result = _extract(tmp_path)

    plain = make_id("imp", "importer", "get_module")
    assert _ids(result, label="_get_module", suffix="imp.py") == {plain}
    assert _ids(result, label="__get_module", suffix="imp.py") == {
        salted_symbol_id(plain, "__get_module")
    }


def test_conditional_redefinition_stays_one_node(tmp_path: Path) -> None:
    """Same raw name defined twice (six's `if PY2:` style) is ONE symbol.

    Deliberate: splitting same-raw-name re-definitions would fabricate a node
    per `@overload` stub / conditional branch. The node points at the FIRST
    definition site; the collapsed site is recorded as metadata.
    """
    (tmp_path / "six.py").write_text(
        "def get_unbound_function(f):\n"
        "    return f\n"
        "\n"
        "def get_unbound_function(f):\n"
        "    return f.__func__\n"
    )
    result = _extract(tmp_path)

    ids = _ids(result, label="get_unbound_function", suffix="six.py")
    assert ids == {make_id("six", "get_unbound_function")}
    node = _node(result, next(iter(ids)))
    assert node["source_location"] == "L1"
    assert node.get("metadata", {}).get("redefinition_lines") == [4]


def test_case_only_same_kind_pair_is_all_salted(tmp_path: Path) -> None:
    """`visit_TEXT` vs `visit_text`: no rule singles one out, so BOTH are
    salted and the plain id stays unbound (#2779's all-salted branch) —
    better that an ambiguous reference resolves to nothing than to an
    arbitrary winner."""
    (tmp_path / "vis.py").write_text(
        "class Compiler:\n"
        "    def visit_TEXT(self, e):\n"
        "        return 1\n"
        "\n"
        "    def visit_text(self, e):\n"
        "        return 2\n"
    )
    result = _extract(tmp_path)

    plain = make_id("vis", "compiler", "visit_text")
    upper = _ids(result, label="visit_TEXT", suffix="vis.py")
    lower = _ids(result, label="visit_text", suffix="vis.py")
    assert upper == {salted_symbol_id(plain, "visit_TEXT")}
    assert lower == {salted_symbol_id(plain, "visit_text")}
    assert plain not in {n["id"] for n in result["nodes"]}


def test_typescript_case_only_methods_survive(tmp_path: Path) -> None:
    """The engine fix is language-agnostic: `ontext` vs `onText`
    (vuejs/core's parser.ts pair) both get nodes in TypeScript too."""
    (tmp_path / "parser.ts").write_text(
        "class Tokenizer {\n"
        "  ontext(start: number): void {}\n"
        "  onText(content: string): void {}\n"
        "}\n"
    )
    result = _extract(tmp_path)

    lower = _ids(result, label="ontext", suffix="parser.ts")
    upper = _ids(result, label="onText", suffix="parser.ts")
    assert len(lower) == 1 and len(upper) == 1, f"ontext={lower} onText={upper}"
    assert lower != upper, "ontext and onText collapsed onto one node id"


def test_rust_type_and_fn_case_pair_survive(tmp_path: Path) -> None:
    """`struct Filter` vs `fn filter` (ripgrep's walk.rs pair): both noded;
    the type keeps the plain id and impl methods stay under it."""
    (tmp_path / "walk.rs").write_text(
        "pub fn filter(x: i32) -> i32 { x }\n"
        "\n"
        "pub struct Filter { pub n: i32 }\n"
        "\n"
        "impl Filter {\n"
        "    pub fn run(&self) -> i32 { self.n }\n"
        "}\n"
    )
    result = _extract(tmp_path)

    plain = make_id("walk", "Filter")
    assert _ids(result, label="Filter", suffix="walk.rs") == {plain}
    assert _ids(result, label="filter", suffix="walk.rs") == {
        salted_symbol_id(plain, "filter")
    }
    method_edges = [
        e for e in result["edges"] if e.get("relation") == "method"
    ]
    assert [(e["source"], e["target"]) for e in method_edges] == [
        (plain, make_id(plain, "run"))
    ]


def test_rust_cfg_gated_same_name_fns_stay_one_node(tmp_path: Path) -> None:
    """`#[cfg(unix)]` / `#[cfg(windows)]` twins of one fn share a raw name,
    so they deliberately stay a single node (the Rust analogue of Python's
    conditional re-definition)."""
    (tmp_path / "os.rs").write_text(
        "#[cfg(unix)]\n"
        "pub fn device_num(x: i32) -> i32 { x }\n"
        "\n"
        "#[cfg(windows)]\n"
        "pub fn device_num(x: i32) -> i32 { x + 1 }\n"
    )
    result = _extract(tmp_path)
    assert _ids(result, label="device_num", suffix="os.rs") == {
        make_id("os", "device_num")
    }


def test_every_non_nested_definition_has_a_node(tmp_path: Path) -> None:
    """The corrected #3302 invariant, swept with an independent parser.

    For every distinct (class scope, raw name) pair among NON-nested
    definitions, exactly one node sits at the pair's first definition line.
    Function-nested definitions stay unmodeled (a deliberate scope choice)
    and same-raw-name re-definitions stay one node — which is why the
    invariant counts distinct pairs, not definition sites.
    """
    (tmp_path / "kitchen.py").write_text(
        "class Adapter:\n"
        "    def _get_connection(self):\n"
        "        return 1\n"
        "\n"
        "    def get_connection(self):\n"
        "        return self._get_connection()\n"
        "\n"
        "def session():\n"
        "    return Session()\n"
        "\n"
        "class Session:\n"
        "    def visit_TEXT(self, e):\n"
        "        return 1\n"
        "\n"
        "    def visit_text(self, e):\n"
        "        return 2\n"
        "\n"
        "def helper():\n"
        "    def local():  # nested: deliberately unmodeled\n"
        "        return 3\n"
        "    return local()\n"
        "\n"
        "def helper():  # conditional-style re-definition: one node\n"
        "    return 4\n"
    )
    result = _extract(tmp_path)

    language = Language(tree_sitter_python.language())
    source = (tmp_path / "kitchen.py").read_bytes()
    tree = Parser(language).parse(source)

    first_sites: dict[tuple[str, str], int] = {}
    nested: list[tuple[str, int]] = []

    def scan(node, class_name: str, func_depth: int) -> None:
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                name_node = child.child_by_field_name("name")
                name = source[name_node.start_byte:name_node.end_byte].decode()
                line = child.start_point[0] + 1
                if func_depth:
                    nested.append((name, line))
                else:
                    first_sites.setdefault((class_name, name), line)
                body = child.child_by_field_name("body")
                if child.type == "class_definition":
                    scan(body, name, func_depth)
                else:
                    scan(body, class_name, func_depth + 1)
            else:
                scan(child, class_name, func_depth)

    scan(tree.root_node, "", 0)
    assert len(first_sites) == 8 and len(nested) == 1  # fixture sanity

    by_line: dict[int, list[dict]] = {}
    for node in result["nodes"]:
        loc = str(node.get("source_location", ""))
        if loc.startswith("L"):
            by_line.setdefault(int(loc[1:]), []).append(node)

    for (scope, name), line in first_sites.items():
        labels = {
            str(n.get("label", "")).strip(".()") for n in by_line.get(line, [])
        }
        assert name in labels, f"no node for {scope or '<module>'}.{name} at L{line}"
    for name, line in nested:
        assert not by_line.get(line), f"nested def {name} unexpectedly noded"
    # Node count: file node + one node per distinct non-nested pair, no more.
    assert len(result["nodes"]) == 1 + len(first_sites)


def test_salt_depends_only_on_the_raw_name() -> None:
    """Unit coverage for the salt itself: content-derived, unicode-stable."""
    assert collision_salt("_get_connection") == collision_salt("_get_connection")
    assert collision_salt("_get_connection") != collision_salt("get_connection")
    # Turkish dotted-İ family (#2614's normalize_id territory): the salt reads
    # the RAW spelling, so case variants that normalize together still salt
    # apart, deterministically.
    assert salted_symbol_id("mod_islemyap", "İslemYap") == salted_symbol_id(
        "mod_islemyap", "İslemYap"
    )
    assert salted_symbol_id("mod_islemyap", "İslemYap") != salted_symbol_id(
        "mod_islemyap", "islemyap"
    )
    # The salted id is itself a canonical id (round-trips normalize_id).
    salted = salted_symbol_id("mod_adapter_get_connection", "_get_connection")
    assert salted == make_id(salted)


def test_canonical_preference_rules() -> None:
    """The default preference: fewest leading underscores, then the unique
    class-like member, else nobody (all salted)."""
    assert canonical_raw_name({"_foo": "function", "foo": "function"}) == "foo"
    assert canonical_raw_name({"__foo": "function", "_foo": "function"}) == "_foo"
    assert canonical_raw_name({"Session": "class", "session": "function"}) == "Session"
    assert canonical_raw_name({"visit_TEXT": "function", "visit_text": "function"}) is None
    assert canonical_raw_name({"ARRAY": "class", "array": "class"}) is None
    # Go's #2779 preference is unchanged by the generalization.
    assert exported_canonical_raw_name({"Run": "function", "run": "function"}) == "Run"
    assert exported_canonical_raw_name({"Run": "function", "RUN": "function"}) is None


def test_llm_plain_id_reconciles_to_canonical_sibling(tmp_path: Path) -> None:
    """The semantic tier can only say the plain lowercase id (llm.py spec has
    no case/underscore channel). Both reconciliation paths must land on the
    CANONICAL sibling: an LLM edge endpoint via norm_to_id, and a semantic
    ghost node via the (source_file, label) merge — never on the salted one.
    """
    (tmp_path / "mod.py").write_text(ADAPTER_SRC)
    result = _extract(tmp_path)
    plain = make_id("mod", "adapter", "get_connection")
    salted = salted_symbol_id(plain, "_get_connection")
    assert {plain, salted} <= {n["id"] for n in result["nodes"]}

    extraction = {
        "nodes": result["nodes"]
        + [
            # LLM ghost twin of the canonical method: bare-stem id, same file
            # and label, no _origin stamp.
            {
                "id": "adapter_get_connection",
                "label": ".get_connection()",
                "file_type": "code",
                "source_file": "mod.py",
            },
            {
                "id": "concept_pooling",
                "label": "Connection pooling",
                "file_type": "concept",
                "source_file": "mod.py",
            },
        ],
        "edges": result["edges"]
        + [
            {
                "source": "concept_pooling",
                "target": plain,
                "relation": "describes",
                "confidence": "INFERRED",
                "source_file": "mod.py",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction, root=str(tmp_path), directed=False)

    assert "adapter_get_connection" not in G.nodes, "LLM ghost survived"
    assert salted in G.nodes, "salted sibling lost in build"
    assert G.has_edge("concept_pooling", plain)
    assert not G.has_edge("concept_pooling", salted)


def test_incremental_merge_over_prefix_graph(tmp_path: Path) -> None:
    """A hook-style partial rebuild over a PRE-fix graph.json stays coherent.

    The stored graph knows only the collapsed plain id. Re-extracting just the
    colliding file adds the salted sibling; the canonical member keeps the
    plain id, so the stored cross-file call edge from the untouched app file
    still resolves — no dangling edges, no re-pointed callers.
    """
    (tmp_path / "adapters.py").write_text(
        "def get_connection():\n"
        "    return 1\n"
    )
    (tmp_path / "app.py").write_text(
        "from adapters import get_connection\n"
        "\n"
        "def main():\n"
        "    return get_connection()\n"
    )

    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    # The edit that pre-fix would have silently dropped the PUBLIC symbol for:
    # a private sibling added ABOVE it.
    (tmp_path / "adapters.py").write_text(
        "def _get_connection():\n"
        "    return 1\n"
        "\n"
        "def get_connection():\n"
        "    return _get_connection()\n"
    )
    partial = extract(
        [tmp_path / "adapters.py"],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
    )
    merged = build_merge(
        [partial], graph_path=str(graph_path), root=str(tmp_path), directed=False
    )

    plain = make_id("adapters", "get_connection")
    assert plain in merged.nodes
    assert salted_symbol_id(plain, "_get_connection") in merged.nodes
    main_targets = {
        merged.nodes[d.get("_tgt", v)].get("label")
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "calls" and "main" in str(d.get("_src", u))
    }
    assert main_targets == {"get_connection()"}, (
        f"cross-file edge re-pointed after partial rebuild: {main_targets}"
    )


def test_docstring_rationale_targets_salted_sibling(tmp_path: Path) -> None:
    """A salted sibling's docstring attaches to the SALTED node (#3302).

    ``_extract_python_rationale`` used to re-derive ids with its own copy of
    the recipe, so after the census re-keyed a sibling the docstring landed on
    whichever member held the plain id — the same mis-attribution class the
    collision fix removes.
    """
    (tmp_path / "adapters.py").write_text(
        "class Adapter:\n"
        "    def _get_connection(self):\n"
        '        """PRIVATE: pool bookkeeping that callers must not touch."""\n'
        "        return 1\n"
        "\n"
        "    def get_connection(self):\n"
        '        """PUBLIC: the documented entry point every caller uses."""\n'
        "        return self._get_connection()\n"
    )
    result = _extract(tmp_path)

    plain = make_id("adapters", "adapter", "get_connection")
    salted = salted_symbol_id(plain, "_get_connection")
    targets_by_label = {
        _node(result, e["source"])["label"]: e["target"]
        for e in result["edges"]
        if e.get("relation") == "rationale_for"
        and _node(result, e["source"]) is not None
        and "entry point" not in _node(result, e["source"])["label"]
        and "PRIVATE" in _node(result, e["source"])["label"]
    }
    assert targets_by_label, "private docstring produced no rationale edge"
    assert set(targets_by_label.values()) == {salted}, (
        f"private docstring attached to the wrong sibling: {targets_by_label}"
    )
    public_targets = {
        e["target"]
        for e in result["edges"]
        if e.get("relation") == "rationale_for"
        and (_node(result, e["source"]) or {}).get("label", "").startswith("PUBLIC")
    }
    assert public_targets == {plain}


def test_docstring_rationale_never_dangles_in_all_salted_file(tmp_path: Path) -> None:
    """In the all-salted branch the plain id has NO node; every docstring
    rationale must target the emitted salted node, and no ``rationale_for``
    edge may point at an id absent from the node set."""
    (tmp_path / "compiler.py").write_text(
        "class Compiler:\n"
        "    def visit_TEXT(self, t):\n"
        '        """Render the SQL TEXT type for DDL emission."""\n'
        "        return t\n"
        "\n"
        "    def visit_text(self, t):\n"
        '        """Render a text() construct inside a SELECT."""\n'
        "        return t\n"
    )
    result = _extract(tmp_path)

    node_ids = {n["id"] for n in result["nodes"]}
    rationale_edges = [
        e for e in result["edges"] if e.get("relation") == "rationale_for"
    ]
    dangling = [e for e in rationale_edges if e["target"] not in node_ids]
    assert not dangling, f"dangling rationale edges: {dangling}"

    plain = make_id("compiler", "compiler", "visit_text")
    upper = salted_symbol_id(plain, "visit_TEXT")
    lower = salted_symbol_id(plain, "visit_text")
    per_sibling = {
        e["target"]
        for e in rationale_edges
        if (_node(result, e["source"]) or {}).get("label", "").startswith("Render")
    }
    assert per_sibling == {upper, lower}, per_sibling


def test_incremental_merge_all_salted_repoints_stored_edges(tmp_path: Path) -> None:
    """All-salted branch over a stored graph: the plain id ceases to exist,
    but stored cross-file edges from files the update does NOT re-extract are
    re-pointed onto the sibling their stored label always meant — not
    silently dropped (#3302 build_merge endpoint repair).
    """
    (tmp_path / "vis.py").write_text(
        "def visit_TEXT(e):\n"
        "    return 1\n"
    )
    (tmp_path / "app.py").write_text(
        "from vis import visit_TEXT\n"
        "\n"
        "def main():\n"
        "    return visit_TEXT(None)\n"
    )
    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    plain = make_id("vis", "visit_text")
    assert plain in graph.nodes  # the stored shape a pre-fix graph has

    # The edit: a case-only same-kind sibling joins — NO canonical member.
    (tmp_path / "vis.py").write_text(
        "def visit_TEXT(e):\n"
        "    return 1\n"
        "\n"
        "def visit_text(e):\n"
        "    return 2\n"
    )
    partial = extract(
        [tmp_path / "vis.py"], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    merged = build_merge(
        [partial], graph_path=str(graph_path), root=str(tmp_path), directed=False
    )

    upper = salted_symbol_id(plain, "visit_TEXT")
    assert plain not in merged.nodes
    assert upper in merged.nodes
    calls = [
        (d.get("_src", u), d.get("_tgt", v))
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "calls"
    ]
    assert calls == [(make_id("app", "main"), upper)], (
        f"stored call edge dropped or mis-pointed: {calls}"
    )
    import_targets = {
        d.get("_tgt", v)
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "imports"
    }
    assert upper in import_targets, "stored imports edge dropped"


def test_incremental_merge_canonical_flip_repoints_stored_caller(tmp_path: Path) -> None:
    """Partial rebuild where the canonical member is NOT the prior occupant.

    The stored graph's plain id belongs to ``def session()``; the edit adds
    ``class Session``, which the preference makes canonical. The stored
    cross-file ``calls`` edge from the untouched app file must follow the
    FUNCTION onto its salted id — not silently re-point onto the class.
    """
    (tmp_path / "sess.py").write_text(
        "def session():\n"
        "    return 1\n"
    )
    (tmp_path / "app.py").write_text(
        "from sess import session\n"
        "\n"
        "def main():\n"
        "    return session()\n"
    )
    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    plain = make_id("sess", "session")
    assert graph.nodes[plain]["label"] == "session()"

    (tmp_path / "sess.py").write_text(
        "def session():\n"
        "    return Session()\n"
        "\n"
        "class Session:\n"
        "    def request(self):\n"
        "        return 2\n"
    )
    partial = extract(
        [tmp_path / "sess.py"], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    merged = build_merge(
        [partial], graph_path=str(graph_path), root=str(tmp_path), directed=False
    )

    salted = salted_symbol_id(plain, "session")
    assert merged.nodes[plain]["label"] == "Session"
    assert merged.nodes[salted]["label"] == "session()"
    app_calls = {
        d.get("_tgt", v)
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "calls"
        and d.get("_src", u) == make_id("app", "main")
    }
    assert app_calls == {salted}, (
        f"untouched caller's stored edge landed on {app_calls}, not the function"
    )
    import_targets = {
        d.get("_tgt", v)
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "imports"
    }
    assert salted in import_targets, "stored imports edge lost the function"


def test_incremental_merge_reverse_move_rebinds_plain_id(tmp_path: Path) -> None:
    """The mirror direction: a stored POST-fix graph holds the salted id, the
    edit deletes the canonical member, and the survivor re-binds the plain id.
    Stored edges naming the salted id must follow it back."""
    (tmp_path / "sess.py").write_text(
        "def session():\n"
        "    return Session()\n"
        "\n"
        "class Session:\n"
        "    def request(self):\n"
        "        return 2\n"
    )
    (tmp_path / "app.py").write_text(
        "from sess import session\n"
        "\n"
        "def main():\n"
        "    return session()\n"
    )
    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    plain = make_id("sess", "session")
    salted = salted_symbol_id(plain, "session")
    assert graph.nodes[plain]["label"] == "Session"
    assert graph.nodes[salted]["label"] == "session()"

    (tmp_path / "sess.py").write_text(
        "def session():\n"
        "    return 1\n"
    )
    partial = extract(
        [tmp_path / "sess.py"], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    merged = build_merge(
        [partial], graph_path=str(graph_path), root=str(tmp_path), directed=False
    )

    assert salted not in merged.nodes
    assert merged.nodes[plain]["label"] == "session()"
    app_calls = {
        d.get("_tgt", v)
        for u, v, d in merged.edges(data=True)
        if d.get("relation") == "calls"
        and d.get("_src", u) == make_id("app", "main")
    }
    assert app_calls == {plain}, f"stored call edge lost: {app_calls}"


def test_shrink_guard_names_stub_collapse_cause_and_force_writes(
    tmp_path: Path, capsys
) -> None:
    """Recovered siblings can COLLAPSE more sourceless reference stubs than
    they add real definitions, so a legitimate net node shrink is possible and
    the #479 guard refuses a default overwrite. The refusal must name this
    cause and the documented upgrade path (a --force full rebuild, which
    writes with force=True) must land the new graph."""
    fixture = {
        "nodes": [
            {"id": "a", "label": "a.py", "file_type": "code",
             "source_file": "a.py", "source_location": "L1"},
            {"id": "a_generative", "label": "generative()", "file_type": "code",
             "source_file": "a.py", "source_location": "L2"},
            # Two per-file sourceless reference stubs a recovered definition
            # would collapse (the #1402 shape).
            {"id": "stub_one", "label": "Generative", "file_type": "code",
             "source_file": ""},
            {"id": "stub_two", "label": "Generative", "file_type": "code",
             "source_file": ""},
        ],
        "edges": [
            {"source": "a", "target": "a_generative", "relation": "contains",
             "confidence": "EXTRACTED", "source_file": "a.py", "weight": 1.0},
            {"source": "a_generative", "target": "stub_one",
             "relation": "references", "confidence": "EXTRACTED",
             "source_file": "a.py", "weight": 1.0},
            {"source": "a_generative", "target": "stub_two",
             "relation": "references", "confidence": "EXTRACTED",
             "source_file": "a.py", "weight": 1.0},
        ],
    }
    existing = build_from_json(fixture, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    assert to_json(existing, {0: list(existing.nodes)}, str(graph_path))

    shrunk = {
        "nodes": fixture["nodes"][:2]
        + [{"id": "a_generative_x", "label": "Generative", "file_type": "code",
            "source_file": "a.py", "source_location": "L9"}],
        "edges": fixture["edges"][:1],
    }
    smaller = build_from_json(shrunk, root=str(tmp_path), directed=False)
    assert smaller.number_of_nodes() < existing.number_of_nodes()

    assert not to_json(smaller, {0: list(smaller.nodes)}, str(graph_path))
    err = capsys.readouterr().err
    assert "#3302" in err, err
    assert "--force" in err, err

    assert to_json(
        smaller, {0: list(smaller.nodes)}, str(graph_path), force=True
    )


def test_raw_merge_path_repoints_stored_edges_too(tmp_path: Path) -> None:
    """`extract --no-cluster` incrementals go through merge_raw_extraction,
    which mirrors build_merge — the #3302 endpoint repair must not drift
    between the two paths."""
    from graphify.build import merge_raw_extraction

    (tmp_path / "vis.py").write_text("def visit_TEXT(e):\n    return 1\n")
    (tmp_path / "app.py").write_text(
        "from vis import visit_TEXT\n"
        "\n"
        "def main():\n"
        "    return visit_TEXT(None)\n"
    )
    full = _extract(tmp_path)
    graph = build_from_json(full, root=str(tmp_path), directed=False)
    graph_path = tmp_path / "graph.json"
    to_json(graph, {i: [n] for i, n in enumerate(graph.nodes)}, str(graph_path))

    (tmp_path / "vis.py").write_text(
        "def visit_TEXT(e):\n"
        "    return 1\n"
        "\n"
        "def visit_text(e):\n"
        "    return 2\n"
    )
    partial = extract(
        [tmp_path / "vis.py"], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    merged = merge_raw_extraction(
        dict(partial), graph_path=str(graph_path), root=str(tmp_path)
    )

    plain = make_id("vis", "visit_text")
    upper = salted_symbol_id(plain, "visit_TEXT")
    node_ids = {n.get("id") for n in merged["nodes"] if isinstance(n, dict)}
    assert plain not in node_ids and upper in node_ids
    calls = [
        (e.get("source"), e.get("target"))
        for e in merged["edges"]
        if isinstance(e, dict) and e.get("relation") == "calls"
    ]
    assert (make_id("app", "main"), upper) in calls, calls
    assert all(t != plain for _s, t in calls)

def test_salt_truncation_collision_falls_back_to_the_plain_id() -> None:
    """The ~2^-24 path: when the 6-hex salt is itself already taken, collapse
    onto the PLAIN id, never onto whatever holds the salted one.

    Returning the salted id would hand this definition's edges and body calls
    to an unrelated symbol, and would make callers record a
    `redefinition_lines` entry for a raw name that never repeated. The
    pre-#3302 behaviour — first-wins on the plain id — is the correct soft
    failure. Raised by review on #3322.
    """
    census = SymbolCollisionCensus()
    plain = make_id("mod", "adapter", "get_connection")
    salted = salted_symbol_id(plain, "_get_connection")

    # `get_connection` mints first and keeps the plain id.
    assert census.assign(plain, "get_connection", "function", set()) == (plain, False)

    # Now `_get_connection` arrives with BOTH the plain id and its own salt
    # already handed out this pass.
    effective, already_present = census.assign(
        plain, "_get_connection", "function", {plain, salted}
    )

    assert effective == plain, "must collapse onto the plain id, not the salt"
    assert already_present is True
    assert effective != salted
