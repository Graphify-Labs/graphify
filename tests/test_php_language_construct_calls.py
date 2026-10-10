"""PHP language constructs must not bind to same-named user methods (#3830).

`empty($x)`, `isset($a)`, `eval($s)` and `die($m)` are keywords, but
tree-sitter-php parses them as an ordinary `function_call_expression`, and the
call pass resolves that callee by bare name. A reserved word is a legal method
name since PHP 7, so a class declaring `public function empty()` absorbed every
`empty(...)` in the corpus: an EXTRACTED edge from a sibling method in the same
file, and an INFERRED one from every other file through the case-insensitive
fold. On the Symfony corpus in #3830 one `ParseCollectionPaginator::empty()`
collected ~200 of these from ~150 files.

The filter (`_PHP_LANGUAGE_CONSTRUCTS`) is PHP-local and bare-call-only, the
same shape as `_GO_PREDECLARED_FUNCS`. The boundary tests at the bottom are the
reason: `$bag->empty()` is a genuine member call into that method and must still
resolve, and the construct's arguments must still be walked for calls.
"""
import pytest

from graphify.extract import extract


def _nodes_by_file(result, suffix):
    return [n for n in result["nodes"] if str(n.get("source_file", "")).endswith(suffix)]


def _label(node):
    return (node.get("label") or "").strip(".()")


def _ids(result, suffix, name):
    return {n["id"] for n in _nodes_by_file(result, suffix) if _label(n) == name}


def _edges_between(result, source_ids, target_ids):
    return [
        e for e in result["edges"]
        if e.get("source") in source_ids and e.get("target") in target_ids
    ]


def _extract_php(tmp_path):
    return extract(sorted(tmp_path.glob("*.php")), cache_root=tmp_path, parallel=False)


_BAG = (
    "<?php\n"
    "namespace App;\n"
    "\n"
    "class Bag\n"
    "{\n"
    "    private array $items = [];\n"
    "\n"
    "    public function empty(): bool\n"
    "    {\n"
    "        return $this->items === [];\n"
    "    }\n"
    "\n"
    "    public function isset(string $k): bool\n"
    "    {\n"
    "        return array_key_exists($k, $this->items);\n"
    "    }\n"
    "}\n"
)


def test_construct_in_another_file_does_not_bind_to_user_method(tmp_path):
    """The cross-file case: `empty($to)` in Mailer.php is not Bag::empty()."""
    (tmp_path / "Bag.php").write_text(_BAG)
    (tmp_path / "Mailer.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "class Mailer\n"
        "{\n"
        "    public function send(array $to): void\n"
        "    {\n"
        "        if (empty($to) || !isset($to[0])) {\n"
        "            return;\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    method_ids = _ids(result, "Bag.php", "empty") | _ids(result, "Bag.php", "isset")
    send_ids = _ids(result, "Mailer.php", "send")
    assert method_ids and send_ids, "the methods and the caller must still be extracted"

    phantom = _edges_between(result, send_ids, method_ids)
    assert phantom == [], f"a construct in Mailer.php bound to a Bag method: {phantom}"


def test_user_method_node_survives_the_filter(tmp_path):
    """Filtering call targets must not delete the same-named method itself."""
    (tmp_path / "Bag.php").write_text(_BAG)
    result = _extract_php(tmp_path)
    labels = {_label(n) for n in _nodes_by_file(result, "Bag.php")}
    assert {"empty", "isset"} <= labels, f"a Bag method disappeared; labels were {sorted(labels)}"


def test_construct_does_not_bind_in_file(tmp_path):
    """The same-file case, which was minted EXTRACTED.

    The call pass resolves a bare callee against the file's own label index
    before anything reaches raw_calls, so gating only the cross-file pass would
    leave this edge behind.
    """
    (tmp_path / "Bag.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "class Bag\n"
        "{\n"
        "    private array $items = [];\n"
        "\n"
        "    public function empty(): bool\n"
        "    {\n"
        "        return $this->items === [];\n"
        "    }\n"
        "\n"
        "    public function isset(string $k): bool\n"
        "    {\n"
        "        return array_key_exists($k, $this->items);\n"
        "    }\n"
        "\n"
        "    public function add(string $k, $v): void\n"
        "    {\n"
        "        if (empty($k) || isset($this->items[$k])) {\n"
        "            return;\n"
        "        }\n"
        "        $this->items[$k] = $v;\n"
        "    }\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    method_ids = _ids(result, "Bag.php", "empty") | _ids(result, "Bag.php", "isset")
    add_ids = _ids(result, "Bag.php", "add")
    assert method_ids and add_ids, "both methods and the caller must still be extracted"

    phantom = _edges_between(result, add_ids, method_ids)
    assert phantom == [], f"a construct in add() bound to a sibling method: {phantom}"


def test_construct_is_matched_case_insensitively(tmp_path):
    """`EMPTY($a)` is the same construct; PHP names fold case.

    The cross-file pass folds PHP names on purpose, so an upper-case spelling
    that skipped the filter would still land on `empty()` through that fold.
    """
    (tmp_path / "Bag.php").write_text(_BAG)
    (tmp_path / "helpers.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "function blank(array $a): bool\n"
        "{\n"
        "    return EMPTY($a);\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    method_ids = _ids(result, "Bag.php", "empty")
    blank_ids = _ids(result, "helpers.php", "blank")
    assert method_ids and blank_ids, "the method and the caller must still be extracted"

    phantom = _edges_between(result, blank_ids, method_ids)
    assert phantom == [], f"EMPTY() bound to Bag::empty(): {phantom}"


def test_member_call_to_construct_named_method_survives(tmp_path):
    """`$other->empty()` really does call the method, so the filter must not reach it.

    It is a member_call_expression, not a function_call_expression. Filtering
    by name alone would drop this genuine edge. Kept in one file because
    cross-file PHP member calls do not resolve yet (the other half of #3830),
    so a two-file version would pass or fail for reasons unrelated to this
    filter.
    """
    (tmp_path / "Bag.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "class Bag\n"
        "{\n"
        "    public function empty(): bool\n"
        "    {\n"
        "        return true;\n"
        "    }\n"
        "\n"
        "    public function bothEmpty(Bag $other): bool\n"
        "    {\n"
        "        return $other->empty();\n"
        "    }\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    method_ids = _ids(result, "Bag.php", "empty")
    caller_ids = _ids(result, "Bag.php", "bothEmpty")
    assert method_ids and caller_ids, "the method and the caller must still be extracted"

    resolved = _edges_between(result, caller_ids, method_ids)
    assert resolved, "a genuine $other->empty() member call must still resolve"


def test_calls_inside_construct_arguments_still_resolve(tmp_path):
    """Dropping the construct must not drop the calls written inside it."""
    (tmp_path / "Repo.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "class Repo\n"
        "{\n"
        "    public function load(): array\n"
        "    {\n"
        "        return [];\n"
        "    }\n"
        "\n"
        "    public function missing(): bool\n"
        "    {\n"
        "        return empty($this->load());\n"
        "    }\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    load_ids = _ids(result, "Repo.php", "load")
    missing_ids = _ids(result, "Repo.php", "missing")
    assert load_ids and missing_ids, "both methods must still be extracted"

    resolved = _edges_between(result, missing_ids, load_ids)
    assert resolved, "$this->load() inside empty(...) must still resolve"


def test_non_construct_function_call_still_resolves(tmp_path):
    """The guard is a no-op for a genuine user function."""
    (tmp_path / "helpers.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "function format_name(string $n): string\n"
        "{\n"
        "    return trim($n);\n"
        "}\n"
    )
    (tmp_path / "User.php").write_text(
        "<?php\n"
        "namespace App;\n"
        "\n"
        "class User\n"
        "{\n"
        "    public function label(string $n): string\n"
        "    {\n"
        "        return format_name($n);\n"
        "    }\n"
        "}\n"
    )
    result = _extract_php(tmp_path)
    target_ids = _ids(result, "helpers.php", "format_name")
    caller_ids = _ids(result, "User.php", "label")
    assert target_ids and caller_ids, "the function and the caller must still be extracted"

    resolved = _edges_between(result, caller_ids, target_ids)
    assert resolved, "a genuine cross-file function call must still resolve"


@pytest.mark.parametrize("name, statement", [
    ("die", "die($value);"),
    ("eval", "eval($value);"),
    ("array", "$result = array($value);"),
    ("exit", "exit($value);"),
    ("list", "list($value) = $values;"),
    ("unset", "unset($value);"),
])
def test_construct_named_methods_keep_only_real_member_calls(tmp_path, name, statement):
    """Keyword use must not bind, while the same-named member remains callable."""
    (tmp_path / "Bag.php").write_text(
        "<?php\nclass Bag {\n"
        f" public function {name}($value) {{ return $value; }}\n"
        f" public function constructUse($value, $values) {{ {statement} }}\n"
        f" public function memberUse($value) {{ return $this->{name}($value); }}\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "outside.php").write_text(
        f"<?php\nfunction externalUse($value, $values) {{ {statement} }}\n",
        encoding="utf-8",
    )
    result = _extract_php(tmp_path)
    target = _ids(result, "Bag.php", name)
    local = _ids(result, "Bag.php", "constructUse")
    external = _ids(result, "outside.php", "externalUse")
    member = _ids(result, "Bag.php", "memberUse")
    assert target and local and external and member
    assert not _edges_between(result, local | external, target)
    assert _edges_between(result, member, target)


def test_builtin_named_self_method_uses_its_own_class_and_php_case_rules(tmp_path):
    source = tmp_path / "Bag.php"
    source.write_text(
        "<?php\nclass Bag { public function list() {}\n"
        " public function useList() { $this->LIST(); } }\n"
        "class Other { public function list() {} }\n",
        encoding="utf-8",
    )
    result = _extract_php(tmp_path)
    bag = next(n["id"] for n in result["nodes"] if n["label"] == "Bag")
    other = next(n["id"] for n in result["nodes"] if n["label"] == "Other")
    targets = _ids(result, "Bag.php", "list")
    bag_targets = {e["target"] for e in result["edges"]
                   if e["source"] == bag and e["relation"] == "method"} & targets
    other_targets = {e["target"] for e in result["edges"]
                     if e["source"] == other and e["relation"] == "method"} & targets
    caller = _ids(result, "Bag.php", "useList")
    assert bag_targets and other_targets and caller
    assert _edges_between(result, caller, bag_targets)
    assert not _edges_between(result, caller, other_targets)


def test_builtin_named_self_call_does_not_bind_to_another_class(tmp_path):
    (tmp_path / "Bag.php").write_text(
        "<?php\nclass Bag { public function useList() { $this->list(); } }\n"
        "class Other { public function list() {} }\n",
        encoding="utf-8",
    )
    result = _extract_php(tmp_path)
    caller = _ids(result, "Bag.php", "useList")
    target = _ids(result, "Bag.php", "list")
    assert caller and target
    assert not _edges_between(result, caller, target)


def test_builtin_named_self_call_does_not_bind_to_a_free_function(tmp_path):
    (tmp_path / "Bag.php").write_text(
        "<?php\nfunction open() {}\n"
        "class Bag { public function useOpen() { $this->open(); } }\n",
        encoding="utf-8",
    )
    result = _extract_php(tmp_path)
    caller = _ids(result, "Bag.php", "useOpen")
    target = _ids(result, "Bag.php", "open")
    assert caller and target
    assert not _edges_between(result, caller, target)


def test_builtin_named_this_call_without_a_class_owner_stays_unresolved(tmp_path):
    (tmp_path / "Bag.php").write_text(
        "<?php\nfunction useList() { $this->list(); }\n"
        "function makeListCallable() { return function() { $this->list(); }; }\n"
        "class Other { public function list() {} }\n",
        encoding="utf-8",
    )
    result = _extract_php(tmp_path)
    target = _ids(result, "Bag.php", "list")
    assert target and _ids(result, "Bag.php", "useList")
    assert _ids(result, "Bag.php", "makeListCallable")
    assert not any(e["relation"] == "calls" and e["target"] in target
                   for e in result["edges"])
