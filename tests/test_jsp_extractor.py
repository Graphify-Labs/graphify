"""Extraction coverage for JavaServer Pages (.jsp, .jspf, .jspx).

Before this extractor a JSP was neither classified as code nor dispatched to an
extractor, so a Java web application's views contributed nothing to the graph:
the page that imports `com.example.shop.Product`, includes a header fragment
and forwards to another view was invisible.

:func:`extract_jsp` is regex-based, like the Razor and Blade extractors. It
reads page-directive imports, static and dynamic includes, forwards, taglib
directives, `jsp:useBean`, and the methods declared in `<%! %>` blocks, in both
classic and XML (JSP document) syntax, and skips anything computed at request
time.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from graphify.detect import FileType, classify_file
from graphify.extract import _get_extractor, _make_id, collect_files, extract, extract_jsp
from graphify.validate import validate_extraction

FIXTURES = Path(__file__).parent / "fixtures"
WEBAPP = FIXTURES / "jsp_webapp"
VIEWS = WEBAPP / "src" / "main" / "webapp" / "WEB-INF" / "views"
LIST_JSP = VIEWS / "orders" / "list.jsp"
DETAIL_JSPX = VIEWS / "orders" / "detail.jspx"
INDEX_JSP = WEBAPP / "src" / "main" / "webapp" / "index.jsp"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _label_of(result: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in result["nodes"]}


def _targets(result: dict, relation: str) -> dict[str, dict]:
    """Target label (or target_file for a resolved page) -> edge."""
    labels = _label_of(result)
    out: dict[str, dict] = {}
    for e in _edges(result, relation):
        key = e.get("target_file") or labels.get(e["target"], e["target"])
        out[str(key)] = e
    return out


def _assert_well_formed(result: dict) -> None:
    """No duplicate node ids, and every edge endpoint is a node of this result,
    except a resolved page link, which targets another file's node and carries
    the `target_file` stamp that lets extract() canonicalize it."""
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids))
    node_ids = set(ids)
    for e in result["edges"]:
        assert e["source"] in node_ids
        if e["target"] not in node_ids:
            assert e.get("target_file"), e
            assert e["target"] == _make_id(e["target_file"])
            assert Path(e["target_file"]).is_file()


# -- registration ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["page.jsp", "fragment.jspf", "doc.jspx", "PAGE.JSP"])
def test_jsp_suffixes_are_code_and_dispatched(name):
    # Regression: `.jsp`/`.jspf`/`.jspx` were absent from CODE_EXTENSIONS and from
    # the dispatch table, so detect() did not count them as code and extract()
    # had no extractor for them (both returned None before this change).
    assert classify_file(Path(name)) == FileType.CODE
    assert _get_extractor(Path(name)) is extract_jsp


def test_jsp_is_in_the_jvm_language_family():
    from graphify.extract import _LANG_FAMILY_BY_EXT
    for ext in (".jsp", ".jspf", ".jspx"):
        assert _LANG_FAMILY_BY_EXT[ext] == _LANG_FAMILY_BY_EXT[".java"] == "jvm"


def test_collect_files_picks_up_jsp_tree():
    names = {p.name for p in collect_files(WEBAPP)}
    assert {"list.jsp", "header.jspf", "detail.jspx", "index.jsp"} <= names


# -- fixture: classic syntax ------------------------------------------------------

def test_list_jsp_is_well_formed_and_valid():
    result = extract_jsp(LIST_JSP)
    assert "error" not in result
    _assert_well_formed(result)
    assert validate_extraction(
        {"nodes": result["nodes"],
         "edges": [e for e in result["edges"] if "target_file" not in e]}
    ) == []


def test_page_import_edges_and_line_numbers():
    result = extract_jsp(LIST_JSP)
    imports = _targets(result, "imports")
    # Comma-separated list on one line, then a multi-line attribute value.
    assert imports["com.example.shop.Product"]["source_location"] == "L2"
    assert imports["java.util.List"]["source_location"] == "L2"
    assert imports["com.example.shop.OrderService"]["source_location"] == "L4"
    assert imports["java.text.NumberFormat"]["source_location"] == "L5"
    edge = imports["com.example.shop.Product"]
    assert edge["context"] == "import"
    assert edge["confidence"] == "EXTRACTED"
    assert edge["metadata"]["target_fqn"] == "com.example.shop.Product"


def test_import_stub_does_not_claim_the_class_is_defined_in_the_jsp():
    result = extract_jsp(LIST_JSP)
    stub = next(n for n in result["nodes"] if n["label"] == "com.example.shop.Product")
    assert stub["id"] == _make_id("com.example.shop.Product")
    assert stub["source_file"] == ""
    assert stub["source_location"] == ""


def test_wildcard_import_produces_no_edge():
    result = extract_jsp(LIST_JSP)
    labels = set(_targets(result, "imports"))
    assert not any(label.endswith("*") or label in ("java.util", "util") for label in labels)


def test_commented_out_directives_produce_nothing():
    result = extract_jsp(LIST_JSP)
    labels = set(_label_of(result).values())
    assert not any("OldCart" in label or "old-banner" in label for label in labels)
    assert not any("old-banner" in str(e.get("metadata")) for e in result["edges"])


def test_static_include_resolves_context_root_path():
    result = extract_jsp(LIST_JSP)
    header = VIEWS / "common" / "header.jspf"
    edge = _targets(result, "includes")[str(header)]
    assert edge["target"] == _make_id(str(header))
    assert edge["source_location"] == "L10"
    assert edge["metadata"]["include_kind"] == "static"
    assert edge["metadata"]["raw_path"] == "/WEB-INF/views/common/header.jspf"


def test_dynamic_include_resolves_relative_path():
    result = extract_jsp(LIST_JSP)
    footer = VIEWS / "common" / "footer.jsp"
    edge = _targets(result, "includes")[str(footer)]
    assert edge["source_location"] == "L30"
    assert edge["metadata"]["include_kind"] == "dynamic"


def test_unresolved_include_keeps_a_stub():
    result = extract_jsp(LIST_JSP)
    edge = _targets(result, "includes")["sidebar.jsp"]
    assert "target_file" not in edge
    stub = next(n for n in result["nodes"] if n["id"] == edge["target"])
    assert stub["label"] == "sidebar.jsp"
    assert stub["source_location"] == "L35"


def test_expression_valued_includes_are_skipped():
    # `page="<%= ... %>"` and `page="${...}"` name a page chosen at request time.
    result = extract_jsp(LIST_JSP)
    assert len(_edges(result, "includes")) == 3  # header, footer, sidebar
    assert not any("extra" in label.lower() for label in _label_of(result).values())


def test_taglib_uri_and_tagdir():
    result = extract_jsp(LIST_JSP)
    imports = _targets(result, "imports")
    core = imports["http://java.sun.com/jsp/jstl/core"]
    assert core["metadata"] == {
        "taglib_kind": "uri", "uri": "http://java.sun.com/jsp/jstl/core", "prefix": "c",
    }
    assert core["source_location"] == "L6"
    tags = imports["/WEB-INF/tags"]
    assert tags["metadata"]["taglib_kind"] == "tagdir"
    assert tags["metadata"]["prefix"] == "shop"
    assert tags["source_location"] == "L7"


def test_use_bean_references_class():
    result = extract_jsp(LIST_JSP)
    edge = _targets(result, "references")["com.example.shop.OrderService"]
    assert edge["source_location"] == "L11"
    assert edge["context"] == "field"
    assert edge["metadata"] == {
        "target_fqn": "com.example.shop.OrderService",
        "bean_attribute": "class",
        "bean_id": "orders",
        "ref_token": "OrderService",
        "qualified": True,
        "ref_qualifier": "com.example.shop",
    }


def test_declaration_methods_become_contained_nodes():
    result = extract_jsp(LIST_JSP)
    stem = LIST_JSP.with_suffix("").as_posix()
    by_id = {n["id"]: n for n in result["nodes"]}
    for name, line in (("formatPrice", "L13"), ("countItems", "L20")):
        nid = _make_id(stem, name)
        assert by_id[nid]["label"] == f".{name}()"
        assert by_id[nid]["source_location"] == line
        assert by_id[nid]["source_file"] == str(LIST_JSP)
    contained = {e["target"] for e in _edges(result, "contains")}
    assert contained == {_make_id(stem, "formatPrice"), _make_id(stem, "countItems")}


def test_forward_to_context_root_page():
    result = extract_jsp(INDEX_JSP)
    edge = _targets(result, "references")[str(LIST_JSP)]
    assert edge["source_location"] == "L2"
    assert edge["metadata"]["jsp_action"] == "forward"


# -- fixture: XML syntax ------------------------------------------------------------

def test_jspx_document_syntax():
    result = extract_jsp(DETAIL_JSPX)
    _assert_well_formed(result)
    imports = _targets(result, "imports")
    assert set(imports) == {"com.example.shop.Product"}  # the commented one is ignored
    assert imports["com.example.shop.Product"]["source_location"] == "L4"

    header = VIEWS / "common" / "header.jspf"
    include = _targets(result, "includes")[str(header)]
    assert include["metadata"]["include_kind"] == "static"
    assert include["source_location"] == "L5"

    refs = _targets(result, "references")
    bean = refs["com.example.shop.Product"]
    assert bean["metadata"]["bean_attribute"] == "type"
    assert bean["source_location"] == "L7"
    forward = refs["/missing/fallback.jsp"]  # unresolved context-root forward: stub
    assert "target_file" not in forward
    assert forward["source_location"] == "L14"

    methods = {n["label"]: n["source_location"] for n in result["nodes"]
               if n["label"].startswith(".")}
    assert methods == {".isFree()": "L9"}


# -- focused cases (tmp_path) -------------------------------------------------------

def test_quotes_whitespace_and_repeated_import_attribute(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        "<%@page import='a.b.One' import=\"a.b.Two\"%>\n"
        "<%@ page\n"
        "    import = \"a.b.Three ,\n"
        "              a.b.*,\n"
        "              a.b.Four\" %>\n",
    )
    result = extract_jsp(page)
    imports = {k: v["source_location"] for k, v in _targets(result, "imports").items()}
    assert imports == {"a.b.One": "L1", "a.b.Two": "L1", "a.b.Three": "L3", "a.b.Four": "L5"}


def test_xml_page_directive_in_classic_jsp(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        "<html>\n"
        "<jsp:directive.page import=\"a.b.C, a.b.D\" />\n"
        "<jsp:directive.include file=\"frag.jspf\"/>\n",
    )
    frag = _write(tmp_path / "frag.jspf", "<p>frag</p>\n")
    result = extract_jsp(page)
    assert set(_targets(result, "imports")) == {"a.b.C", "a.b.D"}
    assert set(_targets(result, "includes")) == {str(frag)}


def test_context_root_is_the_webinf_ancestor(tmp_path):
    # `/` paths are relative to the web application root (the directory that
    # holds WEB-INF), not to the filesystem root or the page's own directory.
    webapp = tmp_path / "app"
    _write(webapp / "WEB-INF" / "web.xml", "<web-app/>\n")
    target = _write(webapp / "shared" / "nav.jspf", "<nav/>\n")
    _write(tmp_path / "shared" / "nav.jspf", "<nav>outside</nav>\n")  # must not win
    page = _write(webapp / "views" / "deep" / "p.jsp", '<%@ include file="/shared/nav.jspf" %>\n')
    result = extract_jsp(page)
    assert set(_targets(result, "includes")) == {str(target)}


def test_context_root_falls_back_to_nearest_ancestor_without_webinf(tmp_path):
    target = _write(tmp_path / "root" / "inc" / "a.jspf", "x\n")
    page = _write(tmp_path / "root" / "pages" / "p.jsp", '<jsp:include page="/inc/a.jspf"/>\n')
    result = extract_jsp(page)
    assert set(_targets(result, "includes")) == {str(target)}


def test_context_path_cannot_escape_its_root(tmp_path):
    _write(tmp_path / "secret.jspf", "x\n")
    page = _write(tmp_path / "app" / "WEB-INF" / "p.jsp",
                  '<%@ include file="/../secret.jspf" %>\n')
    _write(tmp_path / "app" / "WEB-INF" / "web.xml", "<web-app/>\n")
    result = extract_jsp(page)
    edge = _edges(result, "includes")[0]
    assert "target_file" not in edge
    assert _label_of(result)[edge["target"]] == "/../secret.jspf"


def test_query_string_is_not_part_of_the_file_name(tmp_path):
    target = _write(tmp_path / "next.jsp", "x\n")
    page = _write(tmp_path / "p.jsp", '<jsp:forward page="next.jsp?step=2"/>\n')
    result = extract_jsp(page)
    assert set(_targets(result, "references")) == {str(target)}


@pytest.mark.parametrize("value", [
    "<%= nextPage %>", "${next}", "#{bean.next}", "%= nextPage %",
])
def test_request_time_values_produce_no_edge(tmp_path, value):
    page = _write(
        tmp_path / "p.jsp",
        f'<jsp:include page="{value}"/>\n'
        f'<jsp:forward page="{value}"/>\n'
        f'<%@ taglib prefix="x" uri="{value}" %>\n'
        f'<jsp:useBean id="b" class="{value}"/>\n',
    )
    result = extract_jsp(page)
    assert result["edges"] == []
    assert len(result["nodes"]) == 1


def test_use_bean_type_and_bean_name(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        '<jsp:useBean id="cart"\n'
        '             type="com.example.shop.Cart"\n'
        '             beanName="com.example.shop.SessionCart" scope="session"/>\n',
    )
    result = extract_jsp(page)
    refs = _targets(result, "references")
    assert refs["com.example.shop.Cart"]["source_location"] == "L2"
    assert refs["com.example.shop.Cart"]["metadata"]["bean_attribute"] == "type"
    assert refs["com.example.shop.SessionCart"]["source_location"] == "L3"
    assert refs["com.example.shop.SessionCart"]["metadata"]["bean_attribute"] == "beanName"


def test_comments_hide_everything_inside_them(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        "<%--\n"
        '<%@ page import="a.b.Hidden" %>\n'
        '<jsp:include page="hidden.jsp"/>\n'
        "<%! public void hidden() {} %>\n"
        "--%>\n"
        '<%@ page import="a.b.Shown" %>\n',
    )
    result = extract_jsp(page)
    assert set(_label_of(result).values()) == {"p.jsp", "a.b.Shown"}
    assert result["edges"][0]["source_location"] == "L6"


def test_html_comment_does_not_hide_classic_jsp_elements(tmp_path):
    # In classic syntax `<!-- -->` is template text: the container still
    # executes the JSP elements inside it, so they are real dependencies.
    page = _write(tmp_path / "p.jsp", '<!-- <%@ page import="a.b.Live" %> -->\n')
    result = extract_jsp(page)
    assert set(_targets(result, "imports")) == {"a.b.Live"}


def test_markup_inside_scriptlets_is_not_an_action(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        '<% String s = "<jsp:include page=\\"ghost.jsp\\"/>"; %>\n'
        '<%= "<%@ include file=\\"ghost2.jsp\\" %>" %>\n'
        '<jsp:include page="real.jsp"/>\n',
    )
    result = extract_jsp(page)
    assert set(_targets(result, "includes")) == {"real.jsp"}
    assert _edges(result, "includes")[0]["source_location"] == "L3"


def test_declaration_methods_ignore_statements_and_nested_code(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        "<%!\n"
        "    private static final int LIMIT = 10;\n"
        "    // public void commentedOut() {}\n"
        "    @Deprecated\n"
        "    public static <T> java.util.List<T> wrap(T item) throws java.io.IOException {\n"
        "        if (item == null) { return null; }\n"
        "        String s = \"public void inString() {\";\n"
        "        return java.util.List.of(item);\n"
        "    }\n"
        "    int[] sizes(java.util.Map<String, int[]> m) { return new int[0]; }\n"
        "    void touch() { }\n"
        "    class Helper { void inner() {} }\n"
        "%>\n",
    )
    result = extract_jsp(page)
    methods = {n["label"]: n["source_location"] for n in result["nodes"]
               if n["label"].startswith(".")}
    assert methods == {".wrap()": "L5", ".sizes()": "L10", ".touch()": "L11"}


def test_xml_declaration_with_entities(tmp_path):
    page = _write(
        tmp_path / "p.jspx",
        '<jsp:root xmlns:jsp="http://java.sun.com/JSP/Page" version="2.0">\n'
        "<jsp:declaration>\n"
        "  int clamp(int v) { return v &lt; 0 ? 0 : v; }\n"
        "  boolean both(boolean a, boolean b) { return a &amp;&amp; b; }\n"
        "</jsp:declaration>\n"
        "</jsp:root>\n",
    )
    result = extract_jsp(page)
    methods = {n["label"]: n["source_location"] for n in result["nodes"]
               if n["label"].startswith(".")}
    assert methods == {".clamp()": "L3", ".both()": "L4"}


def test_no_duplicate_nodes_for_repeated_references(tmp_path):
    page = _write(
        tmp_path / "p.jsp",
        '<%@ page import="a.b.C" %>\n'
        '<%@ page import="a.b.C" %>\n'
        '<jsp:useBean id="c" class="a.b.C"/>\n'
        '<jsp:include page="missing.jsp"/>\n'
        '<jsp:include page="missing.jsp"/>\n',
    )
    result = extract_jsp(page)
    _assert_well_formed(result)
    assert [n["label"] for n in result["nodes"]].count("a.b.C") == 1
    assert len(_edges(result, "imports")) == 2  # one per line
    assert len(_edges(result, "includes")) == 2


def test_extraction_is_deterministic():
    assert extract_jsp(LIST_JSP) == extract_jsp(LIST_JSP)


def test_unreadable_file_reports_error(tmp_path):
    result = extract_jsp(tmp_path / "missing.jsp")
    assert result["nodes"] == [] and result["edges"] == []
    assert "error" in result


# -- end to end ----------------------------------------------------------------------

@pytest.fixture
def webapp_copy(tmp_path) -> Path:
    root = tmp_path / "webapp"
    shutil.copytree(WEBAPP, root)
    return root


def _run(root: Path, files: list[Path], cache: Path) -> tuple[dict, dict]:
    result = extract(files, cache_root=cache, root=root)
    by_id = {n["id"]: n for n in result["nodes"]}
    return result, by_id


def _edge_targets(result: dict, by_id: dict, source_label: str, relation: str) -> dict[str, dict]:
    """target label -> target node for edges out of the file labelled ``source_label``."""
    src_ids = {nid for nid, n in by_id.items() if n["label"] == source_label}
    return {
        by_id[e["target"]]["label"]: by_id[e["target"]]
        for e in result["edges"]
        if e["source"] in src_ids and e["relation"] == relation and e["target"] in by_id
    }


def test_end_to_end_jsp_links_to_real_java_class_and_template_nodes(webapp_copy, tmp_path):
    files = collect_files(webapp_copy)
    result, by_id = _run(webapp_copy, files, tmp_path / "cache")

    # Every edge a JSP contributed has both endpoints in the graph. (The Java
    # extractor's own `java.util.*` import edges are not checked here.)
    jsp_sources = {n["source_file"] for n in by_id.values()
                   if str(n.get("source_file", "")).endswith((".jsp", ".jspf", ".jspx"))}
    for e in result["edges"]:
        if e["source_file"] in jsp_sources:
            assert e["source"] in by_id and e["target"] in by_id, e
        assert "target_file" not in e
    assert not any("origin_file" in n for n in by_id.values())

    imports = _edge_targets(result, by_id, "list.jsp", "imports")
    product = imports["Product"]
    assert product["source_file"].endswith("com/example/shop/Product.java")
    assert imports["OrderService"]["source_file"].endswith("OrderService.java")
    # External classes stay on shared sourceless FQN stubs.
    assert imports["java.util.List"]["source_file"] == ""
    assert imports["java.text.NumberFormat"]["source_file"] == ""
    # The sourceless FQN stubs for internal classes were absorbed.
    assert not any(n["label"].startswith("com.example.shop.") for n in by_id.values())

    bean = _edge_targets(result, by_id, "list.jsp", "references")["OrderService"]
    assert bean["source_file"].endswith("OrderService.java")
    assert _edge_targets(result, by_id, "detail.jspx", "references")["Product"] is product

    includes = _edge_targets(result, by_id, "list.jsp", "includes")
    assert includes["header.jspf"]["source_file"].endswith("WEB-INF/views/common/header.jspf")
    assert includes["footer.jsp"]["source_file"].endswith("WEB-INF/views/common/footer.jsp")
    assert includes["sidebar.jsp"]["source_file"].endswith("orders/list.jsp")  # stub
    forward = _edge_targets(result, by_id, "index.jsp", "references")
    assert forward["list.jsp"]["source_file"].endswith("WEB-INF/views/orders/list.jsp")


def test_end_to_end_external_import_does_not_merge_into_same_named_class(tmp_path):
    # An import of a class the corpus does not define must not be rebound to an
    # unrelated internal class that merely shares its simple name (#2504).
    root = tmp_path / "proj"
    _write(root / "src" / "com" / "example" / "ui" / "Component.java",
           "package com.example.ui;\n\npublic class Component {\n}\n")
    a = _write(root / "web" / "a.jsp", '<%@ page import="org.acme.web.Component" %>\n')
    b = _write(root / "web" / "b.jsp", '<%@ page import="org.acme.web.Component" %>\n')
    result, by_id = _run(root, collect_files(root), tmp_path / "cache")
    for page in ("a.jsp", "b.jsp"):
        target = _edge_targets(result, by_id, page, "imports")
        assert set(target) == {"org.acme.web.Component"}
        assert target["org.acme.web.Component"]["source_file"] == ""
    # Both pages share one stub for the one external class.
    stubs = [n for n in by_id.values() if n["label"] == "org.acme.web.Component"]
    assert len(stubs) == 1
    assert a.exists() and b.exists()


def test_end_to_end_flat_layout_still_links_to_the_class(tmp_path):
    # With package directories directly under the scan root, the FQN stub id
    # (`com_example_shop_product`) equals the Java file node id, so the
    # collision pass salts them apart. The import must still land on the class
    # node, and nothing may dangle.
    root = tmp_path / "flat"
    _write(root / "com" / "example" / "shop" / "Product.java",
           "package com.example.shop;\n\npublic class Product {\n}\n")
    _write(root / "views" / "p.jsp", '<%@ page import="com.example.shop.Product" %>\n')
    result, by_id = _run(root, collect_files(root), tmp_path / "cache")
    target = _edge_targets(result, by_id, "p.jsp", "imports")
    assert target["Product"]["source_file"].endswith("com/example/shop/Product.java")
    for e in result["edges"]:
        assert e["source"] in by_id and e["target"] in by_id, e


def test_end_to_end_jsp_alone_keeps_import_on_stub(webapp_copy, tmp_path):
    # Documented limitation: resolution happens within one extract() batch. A
    # JSP re-extracted without the Java sources it imports keeps its edge on
    # the sourceless FQN stub, exactly as a Java importer does.
    result, by_id = _run(webapp_copy, [webapp_copy / LIST_JSP.relative_to(WEBAPP)],
                         tmp_path / "cache")
    imports = _edge_targets(result, by_id, "list.jsp", "imports")
    assert imports["com.example.shop.Product"]["source_file"] == ""
